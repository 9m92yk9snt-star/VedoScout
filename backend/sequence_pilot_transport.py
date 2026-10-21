"""Bounded image-sequence calls through native Gemini or the Universal Key API.

Only Python's standard library is required. No Emergent environment/SDK, global
SDK patch, deployment or production database is involved. Transient HTTP 429
responses get at most one bounded retry per request, within the batch deadline.
Credentials are read inside owned child processes and never persisted.
"""
from __future__ import annotations

import base64
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import hashlib
import json
import multiprocessing
import os
from pathlib import Path
import re
import time
import urllib.error
import urllib.request

KEY_ENV = {"gemini": "GEMINI_API_KEY", "emergent": "EMERGENT_LLM_KEY"}
# Includes the entire encoded JSON body, below the existing 20 MB inline limit.
MAX_REQUEST_BYTES = 19_500_000
MAX_RESPONSE_BYTES = 2_000_000
MAX_CALL_SECONDS = 210.
MAX_RATE_LIMIT_WAIT_SECONDS = 30.
RATE_LIMIT_DEFAULT_WAIT_SECONDS = 2.
STOP_ERRORS = frozenset({"MODEL_ACCESS_DENIED", "MODEL_KEY_NOT_CONFIGURED", "MODEL_QUOTA_OR_RATE_LIMIT"})


def limit_diagnostics(exc):
    """Retain only known error categories and a bounded numeric retry delay.

    Never persist arbitrary messages, response bodies or general headers.
    Missing/unknown provider detail remains unknown, rather than guessing quota.
    """
    result = {"limit_kind": "UNSPECIFIED"}
    known = {"insufficient_quota": "QUOTA_EXHAUSTED", "quota_exceeded": "QUOTA_EXHAUSTED",
             "billing_hard_limit_reached": "QUOTA_EXHAUSTED", "insufficient_credits": "QUOTA_EXHAUSTED",
             "rate_limit_exceeded": "RATE_LIMITED", "rate_limit_error": "RATE_LIMITED",
             "too_many_requests": "RATE_LIMITED"}
    try:
        delay = (exc.headers or {}).get("Retry-After", "")
        if isinstance(delay, str) and delay.strip():
            # Do not silently retry early when a provider sends an HTTP-date,
            # an excessively long cooldown or an unparseable nonempty header.
            result["retry_after_unusable"] = True
            try:
                if re.fullmatch(r"\d{1,5}(?:\.\d{1,3})?", delay.strip()):
                    seconds = float(delay)
                else:
                    until = parsedate_to_datetime(delay.strip())
                    if until.tzinfo is None:
                        until = until.replace(tzinfo=timezone.utc)
                    seconds = max(0., (until - datetime.now(timezone.utc)).total_seconds())
                if 0 <= seconds <= 86400:
                    result["retry_after_seconds"] = seconds
                    result.pop("retry_after_unusable")
            except (ValueError, TypeError, OverflowError):
                pass
        raw = exc.read(4097)
        if len(raw) <= 4096:
            data = json.loads(raw)
            error = data.get("error") if isinstance(data, dict) else None
            if isinstance(error, dict):
                for field in ("code", "type"):
                    code = error.get(field)
                    if isinstance(code, str) and code in known:
                        result.update(limit_kind=known[code], provider_error_code=code)
                        break
    except (ValueError, TypeError, OSError):
        pass
    return result


def build_request(provider, model, items, *, reasoning_effort=None, image_detail=None, max_output_tokens=None):
    if provider not in KEY_ENV or not re.fullmatch(r"[A-Za-z0-9_./-]+", model):
        raise ValueError("INVALID_MODEL_PROVIDER")
    gemini3 = model.removeprefix("gemini/").startswith("gemini-3")
    if image_detail not in {None, "high"}:
        raise ValueError("INVALID_IMAGE_DETAIL")
    if max_output_tokens is not None and (type(max_output_tokens) is not int or not 1024 <= max_output_tokens <= 32768):
        raise ValueError("INVALID_OUTPUT_TOKEN_BUDGET")
    output_limit = max_output_tokens if max_output_tokens is not None else 16384
    parts, content, image_audit, video_audit = [], [], [], []
    for item in items:
        if item["type"] == "text":
            parts.append({"text": item["text"]})
            content.append({"type": "text", "text": item["text"]})
        else:
            pixels = Path(item["path"]).read_bytes()
            sha = hashlib.sha256(pixels).hexdigest()
            if sha != item["sha256"]:
                raise ValueError("PREPARED_IMAGE_CHANGED")
            encoded = base64.b64encode(pixels).decode()
            if item["type"] == "video":
                fps = item.get("fps")
                # Gemini VideoMetadata.fps accepts at most 24, independently of source FPS.
                if isinstance(fps, bool) or not isinstance(fps, (int, float)) or not 1 <= fps <= 24:
                    raise ValueError("INVALID_VIDEO_FPS")
                parts.append({"inlineData": {"mimeType": "video/mp4", "data": encoded}, "videoMetadata": {"fps": fps}})
                file = {"file_data": "data:video/mp4;base64," + encoded, "format": "video/mp4",
                        "video_metadata": {"fps": fps}}
                if image_detail:
                    file["detail"] = image_detail
                content.append({"type": "file", "file": file})
                video_audit.append({"sha256": sha, "bytes": len(pixels), "requested_fps": fps})
                continue
            parts.append({"inlineData": {"mimeType": "image/jpeg", "data": encoded}})
            image_url = {"url": "data:image/jpeg;base64," + encoded}
            if image_detail:
                image_url["detail"] = image_detail
            content.append({"type": "image_url", "image_url": image_url})
            image_audit.append({"sha256": sha, "bytes": len(pixels)})
    if provider == "gemini":
        url = "https://generativelanguage.googleapis.com/v1beta/models/" + model + ":generateContent"
        body = {"contents": [{"role": "user", "parts": parts}], "generationConfig": {
            "temperature": 0, "responseMimeType": "application/json", "maxOutputTokens": output_limit}}
        if image_detail:
            body["generationConfig"]["mediaResolution"] = "MEDIA_RESOLUTION_HIGH"
    else:
        url = "https://integrations.emergentagent.com/llm/chat/completions"
        wire_model = "gemini/" + model if model.startswith("gemini-") else model
        body = {"model": wire_model, "messages": [{"role": "user", "content": content}],
                "temperature": 0, "response_format": {"type": "json_object"}, "max_tokens": output_limit}
    if gemini3:
        # Google recommends its default temperature for Gemini 3 reasoning.
        (body["generationConfig"] if provider == "gemini" else body).pop("temperature", None)
    if provider == "emergent" and model.startswith(("gpt-5", "gpt-6")):
        body.pop("temperature", None)
        body["max_completion_tokens"] = body.pop("max_tokens")
    if reasoning_effort is not None:
        if reasoning_effort not in {"low", "medium"} or (reasoning_effort == "medium" and
                not (provider == "emergent" and model.startswith(("gpt-5", "gpt-6")))):
            raise ValueError("INVALID_REASONING_EFFORT")
        if provider == "emergent":
            body["reasoning_effort"] = reasoning_effort
        else:
            body["generationConfig"]["thinkingConfig"] = (
                {"thinkingLevel": "LOW"} if gemini3 else {"thinkingBudget": 1024})
    payload = json.dumps(body, separators=(",", ":")).encode()
    if len(payload) > MAX_REQUEST_BYTES:
        raise ValueError("REQUEST_IMAGE_BUDGET_EXCEEDED")
    return url, payload, {"payload_sha256": hashlib.sha256(payload).hexdigest(), "payload_bytes": len(payload),
                          "explicit_image_count": len(image_audit), "images": image_audit,
                          "frame_sampling_in_provider_metadata": bool(video_audit), "videos": video_audit,
                          "requested_image_detail": image_detail}


def extract_reply(provider, body):
    if provider == "gemini":
        candidates = body.get("candidates") or []
        if len(candidates) != 1 or candidates[0].get("finishReason") != "STOP":
            raise ValueError("INCOMPLETE_MODEL_RESPONSE")
        text = "".join(p["text"] for p in (candidates[0].get("content") or {}).get("parts") or []
                       if isinstance(p.get("text"), str) and not p.get("thought"))
        info = {"model_version": body.get("modelVersion"), "response_id": body.get("responseId"),
                "usage": body.get("usageMetadata")}
    else:
        choices = body.get("choices") or []
        if len(choices) != 1 or choices[0].get("finish_reason") != "stop":
            raise ValueError("INCOMPLETE_MODEL_RESPONSE")
        text = (choices[0].get("message") or {}).get("content")
        info = {"model_version": body.get("model"), "response_id": body.get("id"), "usage": body.get("usage")}
    if not isinstance(text, str) or not text.strip():
        raise ValueError("EMPTY_MODEL_RESPONSE")
    return text, info


def _worker(connection, job, provider, model, timeout_s):
    started = time.monotonic()
    audit = {"packet_id": job["packet_id"], "provider": provider, "requested_model": model,
             "origin": "LIVE_MODEL_REQUEST", "status": "NOT_SENT"}
    try:
        key = os.environ.get(KEY_ENV[provider])
        if not key:
            raise ValueError("MODEL_KEY_NOT_CONFIGURED")
        url, payload, prepared = build_request(provider, model, job["items"],
            reasoning_effort=job.get("reasoning_effort"), image_detail=job.get("image_detail"),
            max_output_tokens=job.get("max_output_tokens"))
        audit["requested_reasoning_effort"] = job.get("reasoning_effort")
        audit.update(prepared)
        headers = {"Content-Type": "application/json"}
        headers.update({"x-goog-api-key": key} if provider == "gemini" else {"Authorization": "Bearer " + key})
        request = urllib.request.Request(url, data=payload, method="POST", headers=headers)
        audit["status"] = "SENT"
        with urllib.request.urlopen(request, timeout=timeout_s) as response:
            data = response.read(MAX_RESPONSE_BYTES + 1)
        if len(data) > MAX_RESPONSE_BYTES:
            raise ValueError("RESPONSE_BYTE_BUDGET_EXCEEDED")
        text, info = extract_reply(provider, json.loads(data))
        audit.update(info, status="COMPLETED", raw_response=text,
                     response_sha256=hashlib.sha256(text.encode()).hexdigest())
    except urllib.error.HTTPError as exc:
        audit.update(status="ERROR", http_status=exc.code,
                     error="MODEL_ACCESS_DENIED" if exc.code in {401, 403} else
                           "MODEL_QUOTA_OR_RATE_LIMIT" if exc.code in {402, 429} else "MODEL_HTTP_ERROR")
        if exc.code in {402, 429}:
            audit.update(limit_diagnostics(exc))
        exc.close()
    except TimeoutError:
        audit.update(status="ERROR", error="MODEL_CALL_TIMEOUT")
    except (urllib.error.URLError, OSError):
        audit.update(status="ERROR", error="MODEL_CONNECTION_FAILED")
    except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        allowed = {"MODEL_KEY_NOT_CONFIGURED", "PREPARED_IMAGE_CHANGED", "INVALID_MODEL_PROVIDER",
                   "REQUEST_IMAGE_BUDGET_EXCEEDED", "RESPONSE_BYTE_BUDGET_EXCEEDED",
                   "INCOMPLETE_MODEL_RESPONSE", "EMPTY_MODEL_RESPONSE"}
        audit.update(status="ERROR", error=str(exc) if str(exc) in allowed else "INVALID_PROVIDER_RESPONSE")
    finally:
        audit["elapsed_seconds"] = round(time.monotonic() - started, 3)
        try:
            connection.send(audit)
        finally:
            connection.close()


def _stop(process):
    if process.is_alive():
        process.terminate()
    process.join(timeout=.5)
    if process.is_alive():
        process.kill()
        process.join(timeout=.5)
    process.close()


def run_jobs(jobs, provider, model, *, deadline, per_call_s=90., workers=2, worker=_worker, on_result=None):
    """Two owned children; a wall deadline stops actual work, including hung IO."""
    if provider not in KEY_ENV or not 1 <= workers <= 2 or not 0 < per_call_s <= MAX_CALL_SECONDS:
        raise ValueError("INVALID_EXECUTION_BUDGET")
    pending, active, results, abort = list(jobs), {}, [], False
    rate_retries, histories, resume_at = set(), {}, 0.
    context = multiprocessing.get_context("spawn")
    try:
        while pending or active:
            now = time.monotonic()
            while pending and len(active) < workers and resume_at <= now < deadline and not abort:
                job = pending.pop(0)
                parent, child = context.Pipe(duplex=False)
                process = context.Process(target=worker, args=(child, job, provider, model, min(per_call_s, deadline - now)))
                process.start()
                child.close()
                active[process.pid] = (process, parent, job, min(deadline, now + per_call_s))
                now = time.monotonic()
            for pid, (process, pipe, job, expires) in list(active.items()):
                result = None
                if pipe.poll():
                    try:
                        result = pipe.recv()
                    except EOFError:
                        result = {"packet_id": job["packet_id"], "status": "ERROR", "error": "MODEL_CHILD_EXITED"}
                elif now >= expires or abort or not process.is_alive():
                    result = {"packet_id": job["packet_id"], "status": "ERROR",
                              "error": ("MODEL_ACCESS_STOPPED" if abort else
                                        "MODEL_WALL_DEADLINE_EXCEEDED" if now >= expires else "MODEL_CHILD_EXITED")}
                if result is not None:
                    now = time.monotonic()
                    packet_id = job["packet_id"]
                    delay = result.get("retry_after_seconds", RATE_LIMIT_DEFAULT_WAIT_SECONDS)
                    retry_rate_limit = (result.get("http_status") == 429
                        and result.get("error") == "MODEL_QUOTA_OR_RATE_LIMIT"
                        and result.get("limit_kind") != "QUOTA_EXHAUSTED"
                        and not result.get("retry_after_unusable")
                        and packet_id not in rate_retries
                        and type(delay) in {int, float} and 0 <= delay <= MAX_RATE_LIMIT_WAIT_SECONDS
                        and now + max(1., delay) + per_call_s < deadline and not abort)
                    if retry_rate_limit:
                        rate_retries.add(packet_id)
                        histories[packet_id] = {k: result[k] for k in (
                            "error", "http_status", "limit_kind", "retry_after_seconds") if k in result}
                        result = {**result, "rate_limit_retry_scheduled": True}
                        pending.insert(0, job)
                        # Pause all new requests, including queued unrelated jobs.
                        # Already running requests retain their ownership/deadline.
                        resume_at = max(resume_at, now + max(1., delay))
                    else:
                        if packet_id in histories:
                            result = {**result, "rate_limit_retry_count": 1,
                                      "prior_rate_limit": histories[packet_id]}
                        results.append(result)
                    if on_result:
                        on_result(result)
                    abort = abort or (not retry_rate_limit and result.get("error") in STOP_ERRORS)
                    pipe.close(); _stop(process); del active[pid]
            if (now >= deadline or abort) and not active:
                for job in pending:
                    result = {"packet_id": job["packet_id"], "status": "NOT_SENT",
                              "error": "MODEL_ACCESS_STOPPED" if abort else "RUN_TIME_BUDGET_EXHAUSTED"}
                    if job["packet_id"] in histories:
                        result["prior_rate_limit"] = histories[job["packet_id"]]
                    results.append(result)
                    if on_result:
                        on_result(result)
                pending.clear()
            if active or (pending and now < resume_at and now < deadline and not abort):
                time.sleep(.02)
    finally:
        for process, pipe, _job, _expires in active.values():
            pipe.close(); _stop(process)
    order = {job["packet_id"]: i for i, job in enumerate(jobs)}
    return sorted(results, key=lambda r: order[r["packet_id"]])
