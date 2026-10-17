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
                     system_message="Observe football video. Return valid JSON only."):
    """Registered owned-child reader. Return the raw reply before parsing."""
    from emergentintegrations.llm.chat import LlmChat, UserMessage, FileContentWithMimeType
    import litellm
    fps = _fps(fps)
    refs = [str(p) for p in reference_paths if p and Path(p).is_file()]
    audit = {"protocol": "TEMPORAL_VIDEO_INPUT_V1", "model": MODEL,
             "requested_fps": fps, "model_video_sha256": sha256(video_path),
             "reference_sha256": [sha256(p) for p in refs],
             "sampling_attached_to_provider_payload": False,
             "provider_receipt_confirmed": False}
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
