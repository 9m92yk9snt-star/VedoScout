"""One video transport with explicit temporal sampling and source provenance.

The deployed LiteLLM 1.80 converter drops per-file video metadata. Attach the
documented Gemini Part.videoMetadata after conversion, inside the owned SDK
child only. Emergent keys use an OpenAI-compatible proxy, whose downstream
conversion cannot be patched here. Short evidence clips therefore hold each
source view for a full playback second: the documented 1-fps default retains
their source sampling even through that proxy. No parent globals are patched.
"""
from __future__ import annotations

import asyncio
import base64
from contextlib import contextmanager
import hashlib
from importlib import metadata
import json
import math
from pathlib import Path

import support_vision_runner

VIDEO_FPS = 8.0
PLAYBACK_FPS = 1.0
VIDEO_TIMEOUT_S = 150.0
MODEL = "gemini-2.5-pro"
VISUAL_OBSERVATION_POLICY = (
    "Use video pixels and the original selected-player references as football event evidence. "
    "Ignore music, commentary, cheers and other audio when identifying, timing, confirming or rejecting events. "
    "State clearly visible actions directly. Preserve uncertainty for unseen identity, contact or outcomes; "
    "never raise certainty merely to complete the response. Return valid JSON only."
)


def _direct_gemini_video(api_key, prompt, video_path, refs, fps, system_message, timeout_s):
    """One bounded native request for a focused review, without SDK/proxy state.

    Keep the production model, source-indexed clip and reference order. The
    request sets sampling on the actual video Part; the response cannot attest
    which frames the provider internally inspected. No retry or file upload.
    """
    import urllib.error
    import urllib.request
    if not api_key:
        raise ValueError("MODEL_KEY_NOT_CONFIGURED")
    if sum(4*((Path(p).stat().st_size+2)//3) for p in [*refs, video_path]) > 20_000_000:
        raise ValueError("FOCUSED_VIDEO_REQUEST_TOO_LARGE")
    parts = [{"inlineData": {"mimeType": "image/jpeg",
              "data": base64.b64encode(Path(p).read_bytes()).decode()}} for p in refs]
    parts.extend([{"inlineData": {"mimeType": "video/mp4",
                   "data": base64.b64encode(Path(video_path).read_bytes()).decode()},
                   "videoMetadata": {"fps": fps}}, {"text": prompt}])
    payload = json.dumps({"contents": [{"role": "user", "parts": parts}],
        "systemInstruction": {"parts": [{"text": system_message}]},
        "generationConfig": {"temperature": 0, "responseMimeType": "application/json",
                             "maxOutputTokens": 32768}}, separators=(",", ":")).encode()
    if len(payload) > 20_000_000:
        raise ValueError("FOCUSED_VIDEO_REQUEST_TOO_LARGE")
    request = urllib.request.Request(
        "https://generativelanguage.googleapis.com/v1beta/models/"+MODEL+":generateContent",
        data=payload, method="POST", headers={"Content-Type": "application/json", "x-goog-api-key": api_key})
    try:
        with urllib.request.urlopen(request, timeout=float(timeout_s)) as response:
            reply = response.read(4_000_001)
    except urllib.error.HTTPError as exc:
        status = int(exc.code)
        exc.close()
        return {"error_code": "HTTP_"+str(status), "http_status": status}
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return {"error_code": "TIMEOUT" if isinstance(exc, TimeoutError)
                or isinstance(getattr(exc, "reason", None), TimeoutError) else "REQUEST_FAILED"}
    try:
        if len(reply) > 4_000_000:
            raise ValueError("OVERSIZED_RESPONSE")
        data = json.loads(reply)
        candidates = data.get("candidates") or []
        if len(candidates) != 1 or candidates[0].get("finishReason") != "STOP":
            return {"error_code": "INCOMPLETE_RESPONSE"}
        text = "".join(p["text"] for p in (candidates[0].get("content") or {}).get("parts") or []
                       if isinstance(p, dict) and isinstance(p.get("text"), str) and not p.get("thought"))
        if not text:
            return {"error_code": "EMPTY_RESPONSE"}
        return {"raw_response": text, "model_version": data.get("modelVersion"),
                "response_id": data.get("responseId"), "usage_metadata": data.get("usageMetadata")}
    except (ValueError, TypeError, AttributeError, KeyError):
        return {"error_code": "INVALID_RESPONSE"}


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _fps(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 1 <= value <= 30:
        raise ValueError("INVALID_VIDEO_SAMPLING_RATE")
    return float(value)


def model_failure(exc):
    """Carry a safe category across child IPC, never a key or upstream body."""
    low = str(exc).lower()
    budget = ("budget" in low and "exceed" in low) or "insufficient_quota" in low or ("quota" in low and "exceed" in low)
    return {"error_code": "BUDGET" if budget else "TIMEOUT" if isinstance(exc, TimeoutError) else "REQUEST_FAILED"}


def response_text(result):
    if result.get("error_code") == "TIMEOUT":
        raise TimeoutError("AI_MODEL_REQUEST_TIMEOUT")
    if result.get("error_code"):
        # Preserve the server's established budget/refund mapping.
        raise RuntimeError("BudgetExceededError" if result["error_code"] == "BUDGET" else "AI_MODEL_REQUEST_FAILED")
    return result["raw_response"]


def attach_sampling(contents, fps):
    """Mutate only native video Parts, retaining bytes, images and offsets."""
    fps = _fps(fps)
    parts = []
    for content in contents:
        for part in content.get("parts") or []:
            media = next((part[k] for k in ("inline_data", "inlineData", "file_data", "fileData")
                          if isinstance(part.get(k), dict)), {})
            mime = media.get("mime_type", media.get("mimeType", ""))
            if not str(mime).startswith("video/"):
                continue
            old = part.pop("video_metadata", None) or part.get("videoMetadata") or {}
            part["videoMetadata"] = {**old, "fps": fps}
            parts.append(dict(part["videoMetadata"]))
    return parts


@contextmanager
def native_sampling(config_class, fps, audit):
    """Scoped compatibility for the pinned converter; used only in its child.

    Every invocation has its own child (batch limit=1), so two reports cannot
    change each other's rate. Restore inherited methods correctly, too.
    """
    original = config_class._transform_messages
    owned = config_class.__dict__.get("_transform_messages")
    def convert(self, *args, **kwargs):
        contents = original(self, *args, **kwargs)
        prepared = attach_sampling(contents, fps)
        if not prepared:
            raise ValueError("VIDEO_PART_NOT_PRESENT_IN_PROVIDER_PAYLOAD")
        audit["native_video_metadata"] = prepared
        audit["sampling_attached_to_provider_payload"] = True
        return contents
    config_class._transform_messages = convert
    try:
        yield
    finally:
        if owned is None:
            delattr(config_class, "_transform_messages")
        else:
            config_class._transform_messages = owned


async def read_video(api_key, session_id, prompt, video_path, reference_paths=(),
                     *, timeout_s=VIDEO_TIMEOUT_S, fps=VIDEO_FPS, source_clock=None,
                     system_message="Observe football video. Return valid JSON only.", transport="sdk"):
    """Registered owned-child reader. Return the raw reply before parsing."""
    if transport not in {"sdk", "gemini-rest"}:
        raise ValueError("UNKNOWN_VIDEO_TRANSPORT")
    system_message = VISUAL_OBSERVATION_POLICY + "\n\n" + str(system_message or "")
    fps = _fps(fps)
    refs = [str(p) for p in reference_paths if p and Path(p).is_file()]
    audit = {"protocol": "TEMPORAL_VIDEO_INPUT_V1", "model": MODEL,
             "requested_fps": fps, "model_video_sha256": sha256(video_path),
             "reference_sha256": [sha256(p) for p in refs],
             "sampling_attached_to_provider_payload": False,
             "provider_receipt_confirmed": False,
             "event_evidence_policy": "VISUAL_OBSERVATION_ONLY",
             "system_instruction_sha256": hashlib.sha256(system_message.encode()).hexdigest()}
    if source_clock is not None:
        # Inspect the actual encoded file, rather than trusting a prompt or an
        # SDK field which a proxy/converter may silently discard.
        import cv2
        cap = cv2.VideoCapture(str(video_path))
        try:
            count, rate = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)), cap.get(cv2.CAP_PROP_FPS)
            if (not cap.isOpened() or rate != PLAYBACK_FPS or count != len(source_clock)
                    or len(source_clock) < 2 or any(type(t) is not int for t in source_clock)
                    or any(b <= a for a, b in zip(source_clock, source_clock[1:]))):
                raise ValueError("INVALID_SOURCE_INDEXED_VIDEO")
        finally:
            cap.release()
        fps = PLAYBACK_FPS
        audit.update(requested_fps=fps, sampling_strategy="SOURCE_INDEXED_1FPS_PLAYBACK",
            source_sampling_fps=round((len(source_clock)-1)*1000/(source_clock[-1]-source_clock[0]), 4),
            max_source_gap_ms=max(b-a for a, b in zip(source_clock, source_clock[1:])),
            min_source_gap_ms=min(b-a for a, b in zip(source_clock, source_clock[1:])),
            playback_fps=rate, frame_count=count,
            frame_source_ms=list(source_clock), sampling_prepared_for_provider=True)
    if transport == "gemini-rest":
        result = await asyncio.to_thread(_direct_gemini_video, api_key, prompt, video_path,
                                        refs, fps, system_message, timeout_s)
        audit.update(transport="GEMINI_REST", provider_conversion="DIRECT_NATIVE",
                     native_video_metadata=[{"fps": fps}],
                     sampling_attached_to_provider_payload=True)
        for key in ("http_status", "model_version", "response_id", "usage_metadata"):
            if key in result:
                audit[key] = result.pop(key)
        return {**result, "video_input": audit}
    from emergentintegrations.llm.chat import LlmChat, UserMessage, FileContentWithMimeType
    import litellm
    for package in ("emergentintegrations", "litellm"):
        try:
            audit[package + "_version"] = metadata.version(package)
        except metadata.PackageNotFoundError:
            pass
    chat = LlmChat(api_key=api_key, session_id=session_id, system_message=system_message).with_model("gemini", MODEL)
    chat.extra_params = {**(getattr(chat, "extra_params", None) or {}),
                         "timeout": float(timeout_s), "temperature": 0.0,
                         "num_retries": 0, "max_retries": 0}
    attachments = [FileContentWithMimeType(file_path=p, mime_type="image/jpeg") for p in refs]
    attachments.append(FileContentWithMimeType(file_path=str(video_path), mime_type="video/mp4"))
    message = UserMessage(text=prompt, file_contents=attachments)
    try:
        with native_sampling(litellm.GoogleAIStudioGeminiConfig, fps, audit):
            response = await asyncio.wait_for(chat.send_message(message), timeout=float(timeout_s) + 5)
    except Exception as exc:
        return {**model_failure(exc), "video_input": audit}
    audit["provider_conversion"] = ("LOCAL_NATIVE" if audit["sampling_attached_to_provider_payload"]
                                    else "PROXY_UNCONFIRMED")
    return {"raw_response": response if isinstance(response, str) else str(response), "video_input": audit}


class IsolatedVideoChat:
    """analysis_jobs.model_call adapter, retaining its existing audit/lease path."""
    def __init__(self, api_key, session_id, video_path, reference_paths=(), *, timeout_s=150.0, fps=VIDEO_FPS,
                 system_message="Observe football video. Return valid JSON only."):
        self.api_key, self.session_id = api_key, session_id
        self.video_path, self.reference_paths = str(video_path), list(reference_paths)
        self.timeout_s, self.fps = float(timeout_s), _fps(fps)
        self.system_message = system_message
        self.video_input_audit = {"protocol": "TEMPORAL_VIDEO_INPUT_V1", "requested_fps": self.fps,
                                  "sampling_attached_to_provider_payload": False,
                                  "provider_receipt_confirmed": False}

    async def send_message(self, message):
        prompt = message if isinstance(message, str) else message.text
        calls = [((self.api_key, self.session_id, prompt, self.video_path, self.reference_paths),
                  {"timeout_s": self.timeout_s, "fps": self.fps, "system_message": self.system_message})]
        result = await asyncio.to_thread(support_vision_runner.run_support_vision, read_video, calls,
            limit=1, deadline_s=self.timeout_s + 5 + support_vision_runner.DEADLINE_MARGIN_S, label="temporal_video")
        row = result[0]
        self.video_input_audit = row["video_input"]
        return response_text(row)


async def read_text(api_key, session_id, prompt, *, timeout_s=180.):
    """The report writer receives the resolved observations, with no video rediscovery."""
    from emergentintegrations.llm.chat import LlmChat, UserMessage
    chat = LlmChat(api_key=api_key, session_id=session_id,
        system_message="Write the scouting report from the supplied verified observations. Return valid JSON only.").with_model("gemini", MODEL)
    chat.extra_params = {**(getattr(chat, "extra_params", None) or {}), "timeout": float(timeout_s),
                         "temperature": 0., "num_retries": 0, "max_retries": 0}
    try:
        result = await asyncio.wait_for(chat.send_message(UserMessage(text=prompt, file_contents=[])), timeout=timeout_s+5)
    except Exception as exc:
        return model_failure(exc)
    return {"raw_response": result if isinstance(result, str) else str(result)}


class IsolatedTextChat:
    def __init__(self, api_key, session_id, timeout_s=180.):
        self.api_key, self.session_id, self.timeout_s = api_key, session_id, float(timeout_s)

    async def send_message(self, prompt):
        result = await asyncio.to_thread(support_vision_runner.run_support_vision, read_text,
            [((self.api_key, self.session_id, prompt), {"timeout_s": self.timeout_s})], limit=1,
            deadline_s=self.timeout_s+5+support_vision_runner.DEADLINE_MARGIN_S, label="report_facts")
        return response_text(result[0])


def write_motion_clip(paths, source_ms, destination, *, max_dimension=1280):
    """Encode chronological source views; indices carry the original VFR clock.

    Playback time is not source time. Every frame is labelled with its exact
    source timestamp, and model output is mapped by index back to that clock.
    """
    import cv2
    if len(paths) != len(source_ms) or len(paths) < 2 or any(b <= a for a, b in zip(source_ms, source_ms[1:])):
        raise ValueError("INVALID_MOTION_CLIP_SOURCE_CLOCK")
    first = cv2.imread(str(paths[0]))
    if first is None:
        raise ValueError("MOTION_CLIP_FRAME_UNAVAILABLE")
    h, w = first.shape[:2]
    if max_dimension not in (1280, 1920):
        raise ValueError("INVALID_MOTION_CLIP_DIMENSION")
    scale = min(1., max_dimension/max(h, w))
    size = (max(2, int(w*scale)//2*2), max(2, int(h*scale)//2*2))
    writer = cv2.VideoWriter(str(destination), cv2.VideoWriter_fourcc(*"mp4v"), PLAYBACK_FPS, size)
    if not writer.isOpened():
        writer.release()
        raise ValueError("MOTION_CLIP_ENCODER_UNAVAILABLE")
    try:
        for index, (path, ms) in enumerate(zip(paths, source_ms), 1):
            image = first if index == 1 else cv2.imread(str(path))
            if image is None or image.shape[:2] != (h, w):
                raise ValueError("MOTION_CLIP_FRAME_GEOMETRY_CHANGED")
            image = cv2.resize(image, size)
            cv2.rectangle(image, (0, 0), (size[0], 30), (0, 0, 0), -1)
            cv2.putText(image, f"frame {index} | source {ms} ms", (5, 21),
                        cv2.FONT_HERSHEY_SIMPLEX, .52, (255, 255, 255), 1, cv2.LINE_AA)
            writer.write(image)
    finally:
        writer.release()
    return {"protocol": "SOURCE_INDEXED_MOTION_CLIP_V1", "playback_fps": PLAYBACK_FPS,
            "source_sampling_fps": round((len(source_ms)-1)*1000/(source_ms[-1]-source_ms[0]), 4),
            "frame_source_ms": list(source_ms), "frame_count": len(source_ms),
            "source_start_ms": source_ms[0], "source_end_ms": source_ms[-1],
            "max_source_gap_ms": max(b-a for a, b in zip(source_ms, source_ms[1:])),
            "min_source_gap_ms": min(b-a for a, b in zip(source_ms, source_ms[1:])),
            "clip_sha256": sha256(destination)}
