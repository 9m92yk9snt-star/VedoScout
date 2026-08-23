"""FIX10A A7 supporting goal-plane direction evidence.

This adapter wraps the existing independent goal-geometry provider and adds a
pixel-only estimate of which side of the goal line is the playable field side.
It never receives semantic event labels, expected outcomes or canonical truth.
Missing/ambiguous orientation stays unresolved.
"""
from __future__ import annotations

import asyncio
import base64
import json
import math
import os
import tempfile
from pathlib import Path

import cv2

import video_timebase
from emergentintegrations.llm.chat import LlmChat, UserMessage, ImageContent

VERSION = 1
VERIFY_PROVIDER = "openai"
VERIFY_MODEL = os.environ.get("FIX10A_SUPPORT_VISION_MODEL", "gpt-4o")
MAX_GOAL_REVIEWS_PER_REPORT = int(os.environ.get("FIX10A_MAX_GOAL_REVIEWS_PER_REPORT", "16"))
MIN_FIELD_SIDE_FRAMES = 2


def _num(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _extract_json(text: str) -> dict | None:
    raw = str(text or "")
    start, end = raw.find("{"), raw.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        data = json.loads(raw[start:end + 1])
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _b64(path: str | Path) -> str:
    return base64.b64encode(Path(path).read_bytes()).decode()


def _read_frames(video_path: str, requested_ms) -> list[tuple[int, object]]:
    wanted = sorted({max(0, int(round(float(ms)))) for ms in requested_ms if _num(ms)})
    if not wanted:
        return []
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        cap.release()
        return []
    fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
    out = []
    try:
        for requested in wanted:
            ok, frame, actual_s = video_timebase.read_frame_at(
                cap, requested / 1000.0, fps=fps
            )
            if ok and frame is not None:
                out.append((int(round(float(actual_s) * 1000.0)), frame))
    finally:
        cap.release()
    return out


def _write_jpg(path: Path, image) -> bool:
    try:
        return bool(cv2.imwrite(str(path), image, [int(cv2.IMWRITE_JPEG_QUALITY), 90]))
    except Exception:
        return False


async def read_field_side_evidence(api_key: str, session_id: str,
                                   frame_paths: list[str], media_ms: list[int]) -> dict:
    """Read only visible playable-field side points from goal-context frames."""
    try:
        pairs = [
            (Path(path), int(ms)) for path, ms in zip(frame_paths, media_ms)
            if path and Path(path).exists() and _num(ms)
        ]
        if len(pairs) < MIN_FIELD_SIDE_FRAMES or not api_key:
            return {"status": "UNRESOLVED", "rows": [], "reason": "insufficient_frames"}
        timeline = ", ".join(
            f"image {i + 1}={ms}ms" for i, (_path, ms) in enumerate(pairs)
        )
        chat = LlmChat(
            api_key=api_key,
            session_id=session_id,
            system_message=(
                "You inspect only visible football pitch/goal geometry. "
                "Do not infer event outcomes. Respond with strict JSON only."
            ),
        ).with_model(VERIFY_PROVIDER, VERIFY_MODEL)
        prompt = (
            f"These are chronological football frames: {timeline}. No event label or expected outcome is provided.\n"
            "For each image, consider the relevant visible goal mouth. If you can clearly distinguish the playable "
            "pitch IN FRONT OF that goal from the area behind the goal line/net, return ONE normalized point (x,y) "
            "that lies clearly on playable pitch immediately in front of the goal line. The point must not lie on the "
            "line, inside the goal/net, behind the goal, in the crowd, or on an ambiguous surface. If the relevant "
            "goal or playable field side is not visually clear, set visible=false. Do not use ball direction, player "
            "reaction, scoreboard, celebration, or any presumed shot outcome. Coordinates are 0..1 from top-left.\n"
            'Respond ONLY: {"frames":[{"idx":1,"visible":true|false,'
            '"field_side":{"x":0.0,"y":0.0}|null,'
            '"confidence":"high"|"medium"|"low","reason":"<short visual reason>"}]}'
        )
        msg = UserMessage(
            text=prompt,
            file_contents=[ImageContent(image_base64=_b64(path)) for path, _ms in pairs],
        )
        resp = await asyncio.wait_for(chat.send_message(msg), timeout=90)
        text = resp if isinstance(resp, str) else getattr(resp, "text", None) or str(resp)
        data = _extract_json(text) or {}
        rows = []
        for row in data.get("frames") or []:
            if not isinstance(row, dict) or row.get("visible") is not True:
                continue
            confidence = str(row.get("confidence") or "low").lower()
            if confidence not in {"high", "medium"}:
                continue
            try:
                idx = int(row.get("idx"))
                point = row.get("field_side") or {}
                x, y = float(point["x"]), float(point["y"])
            except (TypeError, ValueError, KeyError):
                continue
            if not (1 <= idx <= len(pairs)):
                continue
            if not (math.isfinite(x) and math.isfinite(y) and 0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
                continue
            rows.append({
                "media_ms": int(pairs[idx - 1][1]),
                "point": {"x": x, "y": y},
                "confidence": confidence,
                "reason": str(row.get("reason") or "visible_field_side")[:160],
            })
        return {
            "status": "VERIFIED" if len(rows) >= MIN_FIELD_SIDE_FRAMES else "UNRESOLVED",
            "rows": rows,
            "reason": "MULTI_FRAME_FIELD_SIDE_VISIBLE" if len(rows) >= MIN_FIELD_SIDE_FRAMES
                      else "FIELD_SIDE_VISIBILITY_INSUFFICIENT",
        }
    except Exception:
        return {"status": "UNRESOLVED", "rows": [], "reason": "field_side_reader_error"}


class GoalDirectionProvider:
    """Per-report bounded wrapper around the existing goal-geometry callback."""

    def __init__(self, base_provider, api_key: str | None, session_prefix: str,
                 video_path: str, max_reviews: int | None = None):
        self.base_provider = base_provider
        self.api_key = str(api_key or "")
        self.session_prefix = str(session_prefix or "fix10a")
        self.video_path = str(video_path or "")
        self.max_reviews = max(0, int(
            MAX_GOAL_REVIEWS_PER_REPORT if max_reviews is None else max_reviews
        ))
        self.calls = 0
        self._cache = {}

    def __call__(self, window: dict, strike: dict):
        if self.base_provider is None:
            return None
        strike_ms = int(strike.get("media_ms")) if isinstance(strike, dict) and _num(strike.get("media_ms")) else None
        window_id = str(window.get("dense_window_id") or "") if isinstance(window, dict) else ""
        cache_key = (window_id, strike_ms)
        if cache_key in self._cache:
            return self._cache[cache_key]
        if self.calls >= self.max_reviews:
            result = {
                "status": "UNRESOLVED",
                "source": "INDEPENDENT_MULTI_FRAME_GOAL_REVIEW",
                "line_by_ms": [],
                "field_side_status": "UNRESOLVED",
                "field_side_by_ms": [],
                "reason": "GOAL_REVIEW_BUDGET_EXHAUSTED",
                "visual_crossing_audit": {
                    "status": "UNRESOLVED", "confidence": "low",
                    "reason": "GOAL_REVIEW_BUDGET_EXHAUSTED",
                },
            }
            self._cache[cache_key] = result
            return result
        self.calls += 1
        try:
            base = self.base_provider(window, strike)
        except Exception:
            base = None
        if not isinstance(base, dict):
            self._cache[cache_key] = base
            return base
        result = dict(base)
        lines = [
            row for row in result.get("line_by_ms") or []
            if isinstance(row, dict) and _num(row.get("media_ms"))
        ]
        if (
            not self.api_key or not self.video_path or len(lines) < MIN_FIELD_SIDE_FRAMES
            or result.get("source") != "INDEPENDENT_MULTI_FRAME_GOAL_REVIEW"
        ):
            result["field_side_status"] = "UNRESOLVED"
            result["field_side_by_ms"] = []
            self._cache[cache_key] = result
            return result
        frames = _read_frames(self.video_path, [row["media_ms"] for row in lines])
        if len(frames) < MIN_FIELD_SIDE_FRAMES:
            result["field_side_status"] = "UNRESOLVED"
            result["field_side_by_ms"] = []
            self._cache[cache_key] = result
            return result
        with tempfile.TemporaryDirectory(prefix="fix10a_field_side_") as temp:
            root = Path(temp)
            paths, actual_ms = [], []
            for index, (ms, frame) in enumerate(frames):
                path = root / f"field_side_{index:03d}.jpg"
                if _write_jpg(path, frame):
                    paths.append(str(path)); actual_ms.append(int(ms))
            if len(paths) < MIN_FIELD_SIDE_FRAMES:
                evidence = {"status": "UNRESOLVED", "rows": [], "reason": "frame_write_failed"}
            else:
                try:
                    evidence = asyncio.run(read_field_side_evidence(
                        self.api_key,
                        f"{self.session_prefix}-field-side-{strike_ms}",
                        paths,
                        actual_ms,
                    ))
                except Exception:
                    evidence = {"status": "UNRESOLVED", "rows": [], "reason": "field_side_reader_error"}
        result["field_side_status"] = str(evidence.get("status") or "UNRESOLVED")
        result["field_side_by_ms"] = list(evidence.get("rows") or [])
        result["field_side_source"] = "INDEPENDENT_PLAYABLE_PITCH_REVIEW"
        result["field_side_reason"] = str(evidence.get("reason") or "field_side_unresolved")[:180]
        self._cache[cache_key] = result
        return result


def wrap_goal_geometry_provider(base_provider, api_key: str | None,
                                session_prefix: str, video_path: str,
                                max_reviews: int | None = None):
    return GoalDirectionProvider(
        base_provider, api_key, session_prefix, video_path, max_reviews=max_reviews
    )
