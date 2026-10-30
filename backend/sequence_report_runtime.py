"""Default full-report engine, with a bounded, owned source-analysis process.

The legacy detector/reconstruction is never called here, including on failure.
All external persistence and the facts-only writer are injected by the server.
"""
import asyncio
from datetime import datetime, timezone
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import signal
import sys
import tempfile
import time

import sequence_pilot as pilot
import sequence_pilot_transport as transport
import sequence_report_adapter as adapter
from evidence_authority import attach_clip_authority, compute_proof_frame_verified
from report_fact_authority import assessment_prompt
from sequence_run_checkpoint import code_fingerprint, failure_metadata


def enabled():
    """All new full reports use sequences; obsolete environment flags cannot
    silently reactivate legacy reconstruction. The server only regenerates
    Sequence assets; historical completed reports remain readable.
    """
    return True


class SequenceProcessFailure(RuntimeError):
    def __init__(self, diagnostics):
        super().__init__("SEQUENCE_PROCESS_FAILED")
        self.diagnostics = diagnostics


class SequenceProcessTimeout(TimeoutError):
    def __init__(self, diagnostics):
        super().__init__("SEQUENCE_PROCESS_TIMEOUT")
        self.diagnostics = diagnostics


async def owned_process(args, *, timeout_s, log_path):
    """Cancellation/timeout also kills model workers; never leave paid orphans."""
    with Path(log_path).open("wb") as log:
        process = await asyncio.create_subprocess_exec(*map(str, args), stdout=log, stderr=log,
                                                       start_new_session=True)
        try:
            await asyncio.wait_for(process.wait(), timeout_s)
        except BaseException as exc:
            if process.returncode is None:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                await process.wait()
            if isinstance(exc, TimeoutError):
                raise SequenceProcessTimeout({"returncode": process.returncode, "timeout": True}) from None
            raise
        if process.returncode:
            # Do not expose provider output, filesystem paths or credentials.
            raise SequenceProcessFailure({"returncode": process.returncode, "timeout": False})


async def discover(video, anchors_document, work, *, checkpoint=None, resume=None, progress=None):
    started = time.monotonic()
    root = Path(work)
    inputs = root / "inputs"
    (inputs / "video").mkdir(parents=True)
    (inputs / "video" / "source.mp4").symlink_to(Path(video).resolve())
    pilot.original_taps(anchors_document)  # preflight before any paid work
    pilot.write_json(inputs / "anchors.json", anchors_document)
    sums = [(pilot.digest(inputs / name), name) for name in ("video/source.mp4", "anchors.json")]
    (inputs / "SHA256SUMS").write_text("".join(f"{sha}  {name}\n" for sha, name in sums))
    script = Path(__file__).parent / "scripts" / "run_sequence_pilot.py"
    prepared, output = root / "prepared", root / "observations"
    phase = "preparation"
    source_started_at = datetime.now(timezone.utc).isoformat()
    if progress:
        await progress({"phase": "preparation", "started_at": source_started_at})
    async def process():
        nonlocal phase
        await owned_process([sys.executable, script, "prepare", "--evidence-dir", inputs,
                             "--output", prepared, "--scene-packets", "--max-edge", "1280"],
                            timeout_s=75, log_path=root / "preparation.log")
        phase = "observations"
        if progress:
            await progress({"phase": "source", "started_at": source_started_at,
                            "initial_total": len(pilot.read_json(prepared / "manifest.json")["packets"]),
                            "initial_completed": 0, "updated_at": datetime.now(timezone.utc).isoformat()})
        budget = max(1, 900 - (time.monotonic() - started))
        args = [sys.executable, script, "run", "--prepared", prepared / "manifest.json",
                         "--output", output, "--provider", "emergent", "--model", "gpt-6-astra",
                         "--reasoning-effort", "medium", "--budget-s", str(budget), "--per-call-s", "120",
                         "--max-initial", "12", "--max-followups", "6", "--fresh-originals",
                         "--contact-reviews", "--automatic-outcomes", "--image-detail", "high"]
        if resume:
            pilot.write_json(root / "retry.json", resume)
            args += ["--retry-receipts", root / "retry.json"]
        await owned_process(args, timeout_s=budget + 10, log_path=root / "observations.log")

    seen = None
    async def persist_progress():
        nonlocal seen
        if not checkpoint or not (prepared / "manifest.json").exists():
            return
        manifest = pilot.read_json(prepared / "manifest.json")
        # Retain previous completed work even if this retry is interrupted before
        # the rebuilt runner has reached its packet. Every reuse is checked again.
        by_id = {r["packet_id"]: r for r in (resume or {}).get("receipts", [])}
        by_id.update({p.stem: pilot.read_json(p) for p in sorted((output / "responses").glob("*.json"))})
        rows = [by_id[k] for k in sorted(by_id)]
        value = {"code_sha256": code_fingerprint(), "source_video_sha256": manifest["source_video_sha256"],
                 "original_taps_sha256": manifest["original_taps_sha256"], "receipts": rows}
        payload = json.dumps(value, sort_keys=True).encode()
        if len(payload) > 4_000_000:
            raise ValueError("SEQUENCE_RETRY_TOO_LARGE")
        signature = hashlib.sha256(payload).hexdigest()
        if signature != seen:
            await checkpoint(value)
            if progress:
                initial_ids = {p["packet_id"] for p in manifest["packets"]}
                current = [pilot.read_json(p) for p in sorted((output / "responses").glob("*.json"))]
                complete = [r for r in current if r.get("status") == "COMPLETED"]
                durations = [r["elapsed_seconds"] for r in complete if isinstance(r.get("elapsed_seconds"), (int, float))]
                await progress({"phase": "source", "started_at": source_started_at,
                    "updated_at": datetime.now(timezone.utc).isoformat(), "initial_total": len(initial_ids),
                    "initial_completed": sum(r.get("packet_id") in initial_ids for r in complete),
                    "completed_jobs": len(complete), "mean_job_seconds": sum(durations)/len(durations) if durations else 85})
            seen = signature

    task = asyncio.create_task(process())
    try:
        while not task.done():
            await asyncio.wait({task}, timeout=.5)
            await persist_progress()
        await task
    except (SequenceProcessFailure, SequenceProcessTimeout) as exc:
        result = pilot.read_json(output / "result.json") if (output / "result.json").exists() else {}
        rows = result.get("model_jobs") or [pilot.read_json(p) for p in sorted((output / "responses").glob("*.json"))]
        exc.diagnostics = failure_metadata(phase, time.monotonic()-started, result=result, receipts=rows,
                                           **exc.diagnostics)
        raise
    finally:
        if not task.done():
            task.cancel()
        try:
            await task
        except BaseException:
            pass
        await persist_progress()
    result = pilot.read_json(output / "result.json")
    manifest = pilot.read_json(prepared / "manifest.json")
    frames = {f["frame_id"]: f for f in manifest["frames"]}
    for path in sorted(output.rglob("contact-review-manifest.json")):
        review = pilot.read_json(path)
        if review["source_video_sha256"] != manifest["source_video_sha256"]:
            raise ValueError("SEQUENCE_REVIEW_SOURCE_CHANGED")
        frames.update({f["frame_id"]: f for f in review["frames"]})
    manifest["frames"] = sorted(frames.values(), key=lambda f: f["media_ms"])
    receipts = [pilot.read_json(p) for p in sorted((output / "responses").glob("*.json"))]
    return result, manifest, receipts


def writer_model():
    model = os.environ.get("SEQUENCE_REPORT_WRITER_MODEL", "gemini-2.5-pro").strip()
    if model not in {"gemini-2.5-pro", "gpt-6-astra"}:
        raise ValueError("SEQUENCE_REPORT_WRITER_MODEL_NOT_VALIDATED")
    return model


WRITER_SECTIONS = (
    ("player_type", "executive_summary", "content_analysis", "technical", "tactical",
     "physical", "mentality", "scores", "scores_confidence", "overall_benchmark", "evidence_quality_note"),
    ("scout_view", "potential_assessment", "training_plan", "parent_summary", "parent_tips",
     "coach_notes", "snapshot", "development_roadmap", "development_priorities_detailed",
     "scout_outlook", "final_summary", "parents_package", "next_match_missions",
     "parent_value_metrics", "grow_your_game", "parent_corner"),
)


async def write_facts(prompt, *, canonical=None):
    """Two bounded text sections; presentation consumes the completed assessment.

    No new perception, network retry or automatic model fallback. Canonical
    timelines, comments and statistics are supplied by the application.
    """
    model = writer_model()
    receipts, report = [], {}
    for section, keys in enumerate(WRITER_SECTIONS, 1):
        section_prompt = prompt + (
            "\nSECTION OUTPUT CONTRACT (overrides the full example's root fields): "
            "Return ONLY these root keys: " + json.dumps(keys) + ". "
            "Keep their nested schema. Keep text concise: at most one short sentence per notes, reason, "
            "benchmark explanation or verdict field; at most two evidence rows per skill. "
            "For unsupported skills use null score and a short honest missing-evidence reason; "
            "do not pad the report with repeated prose. Keep the whole response below 6000 tokens. "
            "Do not return action_timeline, video_comments or match_stats: the application supplies them.")
        if section == 2:
            section_prompt += ("\nCOMPLETED ASSESSMENT (authoritative for scores, uncertainty and advice): "
                               + json.dumps(report, ensure_ascii=False, separators=(",", ":")))
        jobs = [{"packet_id": f"report_section_{section}", "max_output_tokens": 12288,
                 "items": [{"type": "text", "text": section_prompt}]}]
        if model == "gpt-6-astra":
            jobs[0]["reasoning_effort"] = "low"
        rows = await asyncio.to_thread(transport.run_jobs, jobs, "emergent", model,
                                       deadline=time.monotonic()+195, per_call_s=180)
        receipt = rows[0]
        receipts.append(receipt)
        if receipt.get("status") != "COMPLETED":
            raise ReportWriterFailure("SEQUENCE_REPORT_WRITER_FAILED", receipts)
        try:
            text = receipt["raw_response"].strip()
            if text.startswith("```"):
                text = "\n".join(text.splitlines()[1:-1])
            prose = json.loads(text)
            if not isinstance(prose, dict) or set(prose) != set(keys):
                raise ValueError("REPORT_SECTION_KEYS_REQUIRED")
            if section == 1 and not all(isinstance(prose.get(k), dict)
                    for k in ("technical", "tactical", "physical", "mentality", "scores")):
                raise ValueError("REPORT_JSON_OBJECT_REQUIRED")
            report.update(prose)
            if section == 1 and canonical is not None:
                # Presentation must consume the same checked assessment that
                # will be published, including withheld scores and tiers.
                checked = adapter.build_report(report, canonical)
                report = {k: checked[k] for k in keys}
        except ValueError:
            raise ReportWriterFailure("SEQUENCE_REPORT_WRITER_INVALID", receipts)
    return {"report": report, "receipts": receipts}


class ReportWriterFailure(RuntimeError):
    def __init__(self, code, receipts):
        super().__init__(code)
        self.receipts = receipts


def retained_source(doc, source, selection_sha):
    """Resume only this failed report's complete, unchanged source checkpoint.

    Never accept an inferred identity profile, a different selection or a
    checkpoint interpreted by different source-analysis code.
    """
    # Admission claims the retry before this function runs, changing failed to
    # generating. Both states are eligible; ready reports never enter recovery.
    if doc.get("analysis_engine") != adapter.ENGINE or doc.get("full_report_status") not in {"failed", "generating"}:
        return None
    audit = doc.get("sequence_audit") or {}
    result = audit.get("result") or {}
    code = code_fingerprint()
    if (audit.get("source_video_sha256") != source
            or audit.get("original_selection_values_sha256") != selection_sha
            or result.get("code_sha256") != code
            or result.get("identity_mode") != "FRESH_ORIGINAL_SELECTIONS"
            or result.get("status") != "MODEL_OBSERVATIONS_RETURNED"):
        return None
    manifest = {"source_video_sha256": source, "original_taps_sha256": audit.get("original_taps_sha256"),
                "frames": audit.get("source_frames") or [], "references": audit.get("references") or []}
    receipts = audit.get("receipts") or []
    adapter.canonical_bundle(result, manifest, receipts)  # recheck all receipts and role bindings
    return deepcopy(result), manifest, deepcopy(receipts)


def retained_retry(doc, source, selection_sha):
    retry = doc.get("sequence_retry") or {}
    if (doc.get("analysis_engine") == adapter.ENGINE and doc.get("full_report_status") in {"failed", "generating"}
            and doc.get("id") and retry.get("report_id") == doc["id"]
            and retry.get("source_video_sha256") == source
            and retry.get("original_selection_values_sha256") == selection_sha
            and retry.get("code_sha256") == code_fingerprint()):
        return deepcopy(retry)
    return None


async def generate(video, doc, *, template, writer=write_facts, discovery=discover, checkpoint=None):
    started = time.monotonic()
    if writer is write_facts:
        writer_model()  # reject unknown configuration before paid discovery
    if doc.get("anchor_time_offset") not in (None, 0, 0.):
        raise ValueError("SEQUENCE_NONZERO_ANCHOR_OFFSET_NOT_VALIDATED")
    # Raw original selection only; never re-use an inferred identity profile.
    raw = doc.get("raw_marker_anchors")
    if not raw:
        raise ValueError("SEQUENCE_ORIGINAL_SELECTIONS_REQUIRED")
    anchor_document = {"raw_marker_anchors": raw}
    pilot.original_taps(anchor_document)
    source = await asyncio.to_thread(pilot.digest, Path(video))
    selection_sha = hashlib.sha256(json.dumps(anchor_document, sort_keys=True).encode()).hexdigest()
    retained = retained_source(doc, source, selection_sha) if discovery is discover else None
    with tempfile.TemporaryDirectory(prefix="sequence-report-") as work:
        retry = retained_retry(doc, source, selection_sha)
        async def save_progress(value):
            if checkpoint:
                await checkpoint({"sequence_retry": {**value, "report_id": doc.get("id"),
                                                      "original_selection_values_sha256": selection_sha}})
        async def save_live_progress(value):
            if checkpoint:
                await checkpoint({"sequence_progress": value,
                    "sequence_runtime_signature": hashlib.sha256(json.dumps(code_fingerprint(), sort_keys=True).encode()).hexdigest()})
        if retained:
            result, manifest, receipts = retained
        elif discovery is discover:
            result, manifest, receipts = await discover(video, anchor_document, work, checkpoint=save_progress,
                                                       resume=retry, progress=save_live_progress)
        else:
            result, manifest, receipts = await discovery(video, anchor_document, work)
        # Persist paid observations before projection/writing can fail. A failed
        # writer must never discard nine minutes of source-reading receipts.
        audit = {"result": result, "receipts": receipts, "writer_receipts": [],
                 "source_video_sha256": source,
                 "original_taps_sha256": manifest.get("original_taps_sha256"),
                 "original_selection_values_sha256": selection_sha,
                 "source_checkpoint_reused": retained is not None,
                 "source_frames": [{"frame_id": f["frame_id"], "media_ms": f["media_ms"]} for f in manifest["frames"]],
                 "references": [{k: r[k] for k in ("reference_id", "media_ms", "sha256")} for r in manifest["references"]]}
        if len(json.dumps(audit).encode()) > 4_000_000:
            raise ValueError("SEQUENCE_AUDIT_TOO_LARGE")
        if checkpoint:
            await checkpoint({"sequence_audit": audit})
        if manifest["source_video_sha256"] != source:
            raise ValueError("SEQUENCE_SOURCE_CHANGED")
        bundle = adapter.canonical_bundle(result, manifest, receipts)
        observed = time.monotonic()
        if retained:
            audit["original_source_analysis_seconds"] = (doc.get("sequence_audit") or {}).get(
                "original_source_analysis_seconds", (doc.get("sequence_timings") or {}).get("source_analysis_seconds"))
        else:
            audit["original_source_analysis_seconds"] = round(observed-started, 3)
        source_timings = {"source_analysis_seconds": round(observed-started, 3),
                          "source_phase_reused": retained is not None,
                          "source_jobs_reused": result.get("retry_reused_jobs", 0),
                          "retained_source_analysis_seconds": audit["original_source_analysis_seconds"] if retained else None}
        prompt = assessment_prompt(template, bundle, doc.get("player_details"),
                                   {"coverage_status": "PARTIAL", "engine": adapter.ENGINE,
                                    "anatomical_foot_side": "Use LEFT/RIGHT only from the bound canonical event's supported foot field. UNKNOWN and probable candidates must not become foot claims. A preferred-foot profile is not contact proof. Do not grade overall weak-foot ability from isolated contacts."})
        audit["writer_prompt_sha256"] = hashlib.sha256(prompt.encode()).hexdigest()
        if checkpoint:
            await checkpoint({"canonical_events": bundle, "sequence_audit": audit,
                              "sequence_timings": source_timings})
            await save_live_progress({"phase": "writer", "started_at": datetime.now(timezone.utc).isoformat()})
        try:
            operation = writer(prompt, canonical=bundle) if writer is write_facts else writer(prompt)
            written = await asyncio.wait_for(operation, timeout=420)
        except ReportWriterFailure as exc:
            audit["writer_receipts"] = exc.receipts
            if checkpoint:
                await checkpoint({"sequence_audit": audit})
            raise
        full = adapter.build_report(written["report"], bundle)
        # Store replayable raw model receipts with the report, not ephemeral paths.
        audit["writer_receipts"] = written["receipts"]
        if len(json.dumps(audit).encode()) > 4_000_000:
            raise ValueError("SEQUENCE_AUDIT_TOO_LARGE")
        return {"analysis_engine": adapter.ENGINE, "canonical_events": bundle,
                "sequence_progress": {"phase": "assets", "started_at": datetime.now(timezone.utc).isoformat()},
                "sequence_audit": audit, "full_report": full,
                "sequence_timings": {**source_timings,
                                     "facts_writer_and_projection_seconds": round(time.monotonic()-observed, 3),
                                     "before_assets_seconds": round(time.monotonic()-started, 3)}}


def render_assets(video, full, bundle, directory):
    """Actual source PTS and unannotated clips. Zero re-identification calls."""
    import cv2
    import subprocess
    import video_timebase
    from media_binaries import FFMPEG_BIN
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    if pilot.digest(Path(video)) != bundle["source_video_sha256"]:
        raise ValueError("SEQUENCE_ASSET_SOURCE_CHANGED")
    events = {e["event_id"]: e for e in bundle["events"]}
    cap = cv2.VideoCapture(str(video))
    assets = []
    try:
        for row in full.get("video_comments") or []:
            event = events.get(row.get("event_id"))
            if not event or not (row.get("sequence_event_native") is True
                                 and row.get("source_video_sha256") == bundle["source_video_sha256"]
                                 and row.get("evidence_time_ms") == event["proof"]["frame_ms"]
                                 and row.get("source_frame_id") == event["proof"]["frame_id"]):
                raise ValueError("SEQUENCE_ASSET_BINDING_INVALID")
            requested = row["evidence_time_ms"]
            ok, pixels, actual_s = video_timebase.read_frame_at(cap, requested / 1000.)
            if not ok or round(actual_s * 1000) != requested:
                raise ValueError("SEQUENCE_ACTUAL_FRAME_MISMATCH")
            image = directory / (row["evidence_id"] + ".jpg")
            if not cv2.imwrite(str(image), pixels):
                raise RuntimeError("SEQUENCE_FRAME_WRITE_FAILED")
            start = max(0, event["proof"]["proof_start_ms"] - 750) / 1000.
            end = (event["proof"]["proof_end_ms"] + 750) / 1000.
            clip = directory / (row["evidence_id"] + ".mp4")
            subprocess.run([FFMPEG_BIN, "-v", "error", "-y", "-ss", str(start), "-i", str(video),
                            "-t", str(end-start), "-an", "-vf", "scale=720:1280:force_original_aspect_ratio=decrease",
                            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "24", "-threads", "1",
                            "-movflags", "+faststart", str(clip)], check=True, timeout=45,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            row.update(frame_time_ms=round(actual_s*1000), frame_time_authority="ACTUAL_MEDIA_PTS",
                       identity_verified=True, identity_verification_status="SEQUENCE_SOURCE_CONTINUITY",
                       telestrated=False, tele_clip_start=start, tele_clip_end=end)
            from match_room import presentation
            row["match_room"] = presentation(event, event.get("visual_samples"))
            attach_clip_authority(row, start, end, {row["event_id"]: event["canonical_ms"]})
            assets.append((row, image, clip))
    finally:
        cap.release()
    return assets


async def persist_assets(collection, doc, video, directory, publish):
    started = time.monotonic()
    full = deepcopy(doc["full_report"])
    if not full.get("video_comments"):
        raise ValueError("SEQUENCE_SOURCE_PROOFS_MISSING")
    assets = await asyncio.to_thread(render_assets, video, full, doc["canonical_events"], directory)
    for row, image, clip in assets:
        row["frame_url"] = await publish(image, "image/jpeg")
        row["tele_clip_url"] = await publish(clip, "video/mp4")
        if not row["frame_url"] or not row["tele_clip_url"]:
            raise RuntimeError("SEQUENCE_ASSET_PUBLISH_FAILED")
        row["proof_frame_verified"] = compute_proof_frame_verified(row)
        if not row["proof_frame_verified"]:
            raise ValueError("SEQUENCE_PROOF_FRAME_NOT_VERIFIED")
    timings = {**doc.get("sequence_timings", {}), "assets_seconds": round(time.monotonic()-started, 3)}
    timings["total_processing_seconds"] = round(timings.get("before_assets_seconds", 0)+timings["assets_seconds"], 3)
    await collection.update_one({"id": doc["id"]}, {"$set": {
        "full_report": full, "sequence_timings": timings, "identity_gate_done": True,
        "full_report_status": "finalizing"}})
    return {"checked": len(assets), "hard_rejected": 0, "authority": adapter.ENGINE}
