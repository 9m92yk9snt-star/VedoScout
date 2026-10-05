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
import hashlib
import math
import os
import tempfile
from copy import deepcopy
from pathlib import Path

import cv2

import video_timebase
try:  # Supporting vision is optional; the physical engine must still import.
    from emergentintegrations.llm.chat import LlmChat, UserMessage, ImageContent
except ImportError:  # pragma: no cover - availability is deployment-specific
    LlmChat = UserMessage = ImageContent = None

VERSION = 1
VERIFY_PROVIDER = "openai"
VERIFY_MODEL = os.environ.get("FIX10A_SUPPORT_VISION_MODEL", "gpt-4o")
MAX_GOAL_REVIEWS_PER_REPORT = int(os.environ.get("FIX10A_MAX_GOAL_REVIEWS_PER_REPORT", "16"))
MAX_GOAL_CLARIFICATIONS_PER_REPORT = int(os.environ.get("FIX10A_MAX_GOAL_CLARIFICATIONS_PER_REPORT", "16"))
MIN_FIELD_SIDE_FRAMES = 2
GEOMETRY_NEAR_MS = 500
BALL_ROW_NEAR_MS = 80
FIELD_SIDE_MIN_DISTANCE = 0.01


def _num(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _valid_box(box) -> bool:
    if not isinstance(box, dict):
        return False
    try:
        x, y, w, h = (float(box[k]) for k in ("x", "y", "w", "h"))
    except (KeyError, TypeError, ValueError):
        return False
    return -0.1 <= x <= 1.1 and -0.1 <= y <= 1.1 and 0 < w <= 1.2 and 0 < h <= 1.2


def _center(box):
    return float(box["x"]) + float(box["w"]) / 2.0, float(box["y"]) + float(box["h"]) / 2.0


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
            "model_review_audit": {
                "provider": VERIFY_PROVIDER, "model": VERIFY_MODEL, "raw_response": text[:50000],
                "media_ms": [ms for _, ms in pairs],
                "response_sha256": hashlib.sha256(text.encode()).hexdigest(),
                "input_sha256": hashlib.sha256(prompt.encode() + b"".join(path.read_bytes() for path, _ in pairs)).hexdigest(),
            },
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
        self.clarification_calls = 0
        self.field_side_calls = 0
        self.max_clarifications = max(0, MAX_GOAL_CLARIFICATIONS_PER_REPORT)
        self._cache = {}

    def __call__(self, window: dict, strike: dict):
        if self.base_provider is None:
            return None
        strike_ms = int(strike.get("media_ms")) if isinstance(strike, dict) and _num(strike.get("media_ms")) else None
        if strike_ms is None:
            return None
        scene_id = str((strike or {}).get("scene_id") or (window or {}).get("scene_id") or "")
        # Geometry is about the same physical ball at a media instant, not a
        # window-local track ID. Overlap must not spend another review budget.
        start_ms = max(int((window or {}).get("start_ms") or 0), (strike_ms or 0) - 150)
        end_ms = min(int((window or {}).get("end_ms") or (strike_ms or 0) + 2600), (strike_ms or 0) + 2600)
        context = strike.get("_review_context") or {}
        if all(_num(context.get(k)) for k in ("start_ms", "end_ms", "media_ms")):
            start_ms, end_ms = int(context["start_ms"]), int(context["end_ms"])
            window = {**window, "start_ms": start_ms, "end_ms": end_ms}
            strike = {**strike, "media_ms": int(context["media_ms"])}
        anchor = strike.get("active_ball_anchor") or {}
        ball_key = (int(anchor["media_ms"]), tuple(round(float(anchor["box"][k]), 5) for k in ("x", "y", "w", "h"))) \
            if _num(anchor.get("media_ms")) and _valid_box(anchor.get("box")) else None
        cache_key = (scene_id or str((window or {}).get("dense_window_id") or ""),
                     strike.get("_review_episode_id") or (strike_ms, ball_key))
        for saved_start, saved_end, saved in self._cache.get(cache_key, []):
            if saved_start <= start_ms and saved_end >= end_ms:
                result = deepcopy(saved)
                if isinstance(result, dict):
                    result["review_delivery"] = {"status": "REUSED", "start_ms": saved_start,
                                                 "end_ms": saved_end}
                return result

        def remember(value):
            if isinstance(value, dict):
                value["review_delivery"] = {"status": "EXECUTED", "start_ms": start_ms, "end_ms": end_ms}
            self._cache.setdefault(cache_key, []).append((start_ms, end_ms, deepcopy(value)))
            return value
        clarification = (strike or {}).get("_review_lane") == "CLARIFICATION"
        exhausted = (self.clarification_calls >= self.max_clarifications if clarification
                     else self.calls >= self.max_reviews)
        budget_reason = "GOAL_CLARIFICATION_BUDGET_EXHAUSTED" if clarification else "GOAL_REVIEW_BUDGET_EXHAUSTED"
        if exhausted:
            result = {
                "status": "UNRESOLVED",
                "source": "INDEPENDENT_MULTI_FRAME_GOAL_REVIEW",
                "line_by_ms": [],
                "field_side_status": "UNRESOLVED",
                "field_side_by_ms": [],
                "reason": budget_reason,
                "visual_crossing_audit": {
                    "status": "UNRESOLVED", "confidence": "low",
                    "reason": budget_reason,
                },
            }
            return result
        if clarification:
            self.clarification_calls += 1
        else:
            self.calls += 1
        try:
            base = self.base_provider(window, strike)
        except Exception:
            base = {"status": "UNRESOLVED", "source": "INDEPENDENT_MULTI_FRAME_GOAL_REVIEW",
                    "reason": "goal_geometry_reader_error", "line_by_ms": []}
        if not isinstance(base, dict):
            return remember(base)
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
            return remember(result)
        frames = _read_frames(self.video_path, [row["media_ms"] for row in lines])
        if len(frames) < MIN_FIELD_SIDE_FRAMES:
            result["field_side_status"] = "UNRESOLVED"
            result["field_side_by_ms"] = []
            return remember(result)
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
                    self.field_side_calls += 1
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
        result["field_side_model_audit"] = evidence.get("model_review_audit")
        result["field_side_reason"] = str(evidence.get("reason") or "field_side_unresolved")[:180]
        return remember(result)


def wrap_goal_geometry_provider(base_provider, api_key: str | None,
                                session_prefix: str, video_path: str,
                                max_reviews: int | None = None):
    return GoalDirectionProvider(
        base_provider, api_key, session_prefix, video_path, max_reviews=max_reviews
    )


def _segment_from_line(line):
    if not isinstance(line, dict):
        return None
    try:
        p1, p2 = line["p1"], line["p2"]
        a = (float(p1["x"]), float(p1["y"]))
        b = (float(p2["x"]), float(p2["y"]))
    except (TypeError, KeyError, ValueError):
        return None
    if not all(math.isfinite(v) for v in (*a, *b)) or a == b:
        return None
    dx, dy = b[0] - a[0], b[1] - a[1]
    if abs(dx) >= abs(dy):
        return (a, b) if a[0] <= b[0] else (b, a)
    return (a, b) if a[1] <= b[1] else (b, a)


def _nearest_timed(rows, media_ms, max_ms=GEOMETRY_NEAR_MS):
    valid = [
        row for row in rows or []
        if isinstance(row, dict) and _num(row.get("media_ms"))
    ]
    if not valid or not _num(media_ms):
        return None
    best = min(valid, key=lambda row: abs(int(row["media_ms"]) - int(media_ms)))
    return best if abs(int(best["media_ms"]) - int(media_ms)) <= max_ms else None


def _line_at(goal_geometry, media_ms):
    if not isinstance(goal_geometry, dict):
        return None
    timed = _nearest_timed(goal_geometry.get("line_by_ms"), media_ms)
    if timed:
        segment = _segment_from_line(timed.get("line"))
        if segment is not None:
            return segment
    return _segment_from_line(goal_geometry.get("line"))


def _field_point_at(goal_geometry, media_ms):
    if not isinstance(goal_geometry, dict):
        return None
    if str(goal_geometry.get("field_side_status") or "UNRESOLVED").upper() != "VERIFIED":
        return None
    timed = _nearest_timed(goal_geometry.get("field_side_by_ms"), media_ms)
    if not timed:
        return None
    point = timed.get("point")
    if not isinstance(point, dict):
        return None
    try:
        x, y = float(point["x"]), float(point["y"])
    except (TypeError, ValueError, KeyError):
        return None
    if not (math.isfinite(x) and math.isfinite(y) and 0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
        return None
    return (x, y)


def _signed_side(point, segment):
    if point is None or segment is None:
        return None
    a, b = segment
    vx, vy = b[0] - a[0], b[1] - a[1]
    length = math.hypot(vx, vy)
    if length <= 1e-9:
        return None
    nx, ny = -vy / length, vx / length
    return (point[0] - a[0]) * nx + (point[1] - a[1]) * ny


def _ball_row_at(ball_trajectory, media_ms):
    rows = [
        row for row in ball_trajectory or []
        if isinstance(row, dict) and row.get("state") == "MEASURED"
        and _num(row.get("media_ms")) and _valid_box(row.get("box"))
        and row.get("used_fallback") is not True
    ]
    if not rows or not _num(media_ms):
        return None
    best = min(rows, key=lambda row: abs(int(row["media_ms"]) - int(media_ms)))
    return best if abs(int(best["media_ms"]) - int(media_ms)) <= BALL_ROW_NEAR_MS else None


def _downgrade_crossing(outcome, reason: str, details=None):
    row = deepcopy(outcome) if isinstance(outcome, dict) else {}
    crossing = deepcopy(row.get("goal_plane_crossing")) if isinstance(row.get("goal_plane_crossing"), dict) else {}
    crossing["undirected_status"] = crossing.get("status")
    crossing["undirected_reason"] = crossing.get("reason")
    crossing["status"] = "UNRESOLVED"
    crossing["crossing_ms"] = None
    crossing["reason"] = reason
    crossing["direction"] = "UNRESOLVED"
    crossing["direction_evidence"] = details or {}
    row["goal_plane_crossing"] = crossing
    intervention = row.get("intervention") if isinstance(row.get("intervention"), dict) else {}
    row["physical_outcome"] = (
        "PLAYER_INTERVENTION" if intervention.get("status") == "VERIFIED" else "UNRESOLVED"
    )
    row["direction_gate"] = {"status": "UNRESOLVED", "reason": reason}
    row["canonical_event_type"] = None
    return row


def apply_direction_gate(outcome: dict, ball_trajectory, goal_geometry) -> dict:
    """Require field→goal direction for independent verified whole-ball crossings.

    Legacy/static deterministic geometry is left unchanged.  The gate only
    tightens results created from the independent multi-frame goal provider.
    """
    row = deepcopy(outcome) if isinstance(outcome, dict) else {}
    crossing = row.get("goal_plane_crossing") if isinstance(row.get("goal_plane_crossing"), dict) else {}
    if crossing.get("status") != "VERIFIED":
        return row
    if not isinstance(goal_geometry, dict) or goal_geometry.get("source") != "INDEPENDENT_MULTI_FRAME_GOAL_REVIEW":
        return row
    evidence = crossing.get("evidence") or []
    first = next((item for item in evidence if isinstance(item, dict)), None)
    if not first or not (_num(first.get("from_ms")) and _num(first.get("to_ms"))):
        return _downgrade_crossing(row, "CROSSING_SEGMENT_EVIDENCE_MISSING")
    from_ms, to_ms = int(first["from_ms"]), int(first["to_ms"])

    # Occlusion-aware lane: only the pre-occlusion ball is a detector-backed
    # measurement.  The resolver carries an explicit projected point just
    # beyond the line, derived from the bounded proof-eligible trajectory.
    # This direction gate independently verifies that the measured pre-ball is
    # on the playable-field side and the projection is on the opposite side.
    if str(first.get("proof_lane") or "") == "OCCLUDED_TRAJECTORY_GOAL":
        occ = goal_geometry.get("occlusion_crossing_audit") if isinstance(goal_geometry.get("occlusion_crossing_audit"), dict) else {}
        reaction = goal_geometry.get("reaction_support_evidence") if isinstance(goal_geometry.get("reaction_support_evidence"), dict) else {}
        anchors = first.get("anchor_media_ms") if isinstance(first.get("anchor_media_ms"), list) else []
        if not (
            str(occ.get("status") or "").upper() == "VERIFIED_OCCLUSION"
            and str(occ.get("confidence") or "low").lower() in {"high", "medium"}
            and str(reaction.get("status") or "").upper() == "VERIFIED"
            and first.get("same_ball_pre_occlusion") is True
            and len([ms for ms in anchors if _num(ms)]) >= 3
            and _num(first.get("trajectory_r2"))
            and float(first.get("trajectory_r2")) >= 0.92
        ):
            return _downgrade_crossing(row, "OCCLUDED_GOAL_DIRECTION_EVIDENCE_INVALID")
        before_point = first.get("pre_ball_center") if isinstance(first.get("pre_ball_center"), dict) else None
        after_point = first.get("projected_after_point") if isinstance(first.get("projected_after_point"), dict) else None
        try:
            before_xy = (float(before_point["x"]), float(before_point["y"]))
            after_xy = (float(after_point["x"]), float(after_point["y"]))
        except (TypeError, KeyError, ValueError):
            return _downgrade_crossing(row, "OCCLUDED_GOAL_PROJECTED_POINTS_MISSING")
        if not all(math.isfinite(v) and -0.1 <= v <= 1.1 for v in (*before_xy, *after_xy)):
            return _downgrade_crossing(row, "OCCLUDED_GOAL_PROJECTED_POINTS_INVALID")
        before_line, after_line = _line_at(goal_geometry, from_ms), _line_at(goal_geometry, to_ms)
        before_field, after_field = _field_point_at(goal_geometry, from_ms), _field_point_at(goal_geometry, to_ms)
        if not all(x is not None for x in (before_line, after_line, before_field, after_field)):
            return _downgrade_crossing(row, "FIELD_SIDE_ORIENTATION_UNAVAILABLE")
        before_field_d = _signed_side(before_field, before_line)
        after_field_d = _signed_side(after_field, after_line)
        before_ball_d = _signed_side(before_xy, before_line)
        after_projected_d = _signed_side(after_xy, after_line)
        values = (before_field_d, after_field_d, before_ball_d, after_projected_d)
        if any(value is None for value in values):
            return _downgrade_crossing(row, "FIELD_SIDE_ORIENTATION_UNAVAILABLE")
        if abs(before_field_d) < FIELD_SIDE_MIN_DISTANCE or abs(after_field_d) < FIELD_SIDE_MIN_DISTANCE:
            return _downgrade_crossing(row, "FIELD_SIDE_POINT_TOO_CLOSE_TO_GOAL_LINE")
        before_field_sign = 1 if before_field_d > 0 else -1
        after_field_sign = 1 if after_field_d > 0 else -1
        before_ball_sign = 1 if before_ball_d > 0 else -1 if before_ball_d < 0 else 0
        after_projected_sign = 1 if after_projected_d > 0 else -1 if after_projected_d < 0 else 0
        details = {
            "from_ms": from_ms, "to_ms": to_ms,
            "before_field_sign": before_field_sign, "after_field_sign": after_field_sign,
            "before_ball_sign": before_ball_sign, "after_projected_sign": after_projected_sign,
            "proof_lane": "OCCLUDED_TRAJECTORY_GOAL",
            "anchor_media_ms": [int(ms) for ms in anchors if _num(ms)],
        }
        if before_field_sign != after_field_sign:
            return _downgrade_crossing(row, "FIELD_SIDE_ORIENTATION_CONTRADICTS_ACROSS_OCCLUSION", details)
        if before_ball_sign == before_field_sign and after_projected_sign == -after_field_sign:
            crossing = deepcopy(crossing)
            crossing["direction"] = "FIELD_TO_GOAL"
            crossing["direction_status"] = "VERIFIED"
            crossing["direction_evidence"] = details
            row["goal_plane_crossing"] = crossing
            row["direction_gate"] = {
                "status": "VERIFIED",
                "reason": "OCCLUDED_TRAJECTORY_FIELD_TO_GOAL_DIRECTION_VERIFIED",
            }
            return row
        if before_ball_sign == -before_field_sign:
            return _downgrade_crossing(row, "OCCLUDED_TRAJECTORY_STARTS_GOAL_SIDE", details)
        return _downgrade_crossing(row, "FIELD_TO_GOAL_DIRECTION_NOT_PROVEN", details)

    # Detector-loss recovery lane: the structured visual proof already carries
    # a strict, continuous whole-ball FIELD_SIDE -> BEYOND transition.  We do
    # not fabricate detector rows here.  Instead, an independent field-side
    # review must still orient the visible goal geometry at both endpoints.
    if str(first.get("proof_lane") or "") == "STRUCTURED_VISUAL_WHOLE_BALL":
        audit = goal_geometry.get("visual_crossing_audit") if isinstance(goal_geometry.get("visual_crossing_audit"), dict) else {}
        if not (
            audit.get("proof_ready") is True
            and audit.get("same_ball_continuity") is True
            and str(audit.get("status") or "").upper() == "VERIFIED_CROSSING"
            and str(audit.get("confidence") or "").lower() == "high"
        ):
            return _downgrade_crossing(row, "STRUCTURED_VISUAL_DIRECTION_EVIDENCE_INVALID")
        crossing_ms = first.get("crossing_ms")
        if not _num(crossing_ms) or not (from_ms < int(crossing_ms) <= to_ms):
            return _downgrade_crossing(row, "STRUCTURED_VISUAL_CROSSING_TIME_INVALID")
        before_line, after_line = _line_at(goal_geometry, from_ms), _line_at(goal_geometry, to_ms)
        before_field, after_field = _field_point_at(goal_geometry, from_ms), _field_point_at(goal_geometry, to_ms)
        if not all(x is not None for x in (before_line, after_line, before_field, after_field)):
            return _downgrade_crossing(row, "FIELD_SIDE_ORIENTATION_UNAVAILABLE")
        before_field_d = _signed_side(before_field, before_line)
        after_field_d = _signed_side(after_field, after_line)
        if before_field_d is None or after_field_d is None:
            return _downgrade_crossing(row, "FIELD_SIDE_ORIENTATION_UNAVAILABLE")
        if abs(before_field_d) < FIELD_SIDE_MIN_DISTANCE or abs(after_field_d) < FIELD_SIDE_MIN_DISTANCE:
            return _downgrade_crossing(row, "FIELD_SIDE_POINT_TOO_CLOSE_TO_GOAL_LINE")
        before_field_sign = 1 if before_field_d > 0 else -1
        after_field_sign = 1 if after_field_d > 0 else -1
        if before_field_sign != after_field_sign:
            return _downgrade_crossing(
                row, "FIELD_SIDE_ORIENTATION_CONTRADICTS_ACROSS_VISUAL_PROOF",
                {"from_ms": from_ms, "to_ms": to_ms,
                 "before_field_sign": before_field_sign, "after_field_sign": after_field_sign},
            )
        details = {
            "from_ms": from_ms, "to_ms": to_ms, "crossing_ms": int(crossing_ms),
            "before_field_sign": before_field_sign, "after_field_sign": after_field_sign,
            "proof_lane": "STRUCTURED_VISUAL_WHOLE_BALL",
            "same_ball_continuity": True,
        }
        crossing = deepcopy(crossing)
        crossing["direction"] = "FIELD_TO_GOAL"
        crossing["direction_status"] = "VERIFIED"
        crossing["direction_evidence"] = details
        row["goal_plane_crossing"] = crossing
        row["direction_gate"] = {
            "status": "VERIFIED",
            "reason": "STRUCTURED_VISUAL_FIELD_TO_GOAL_DIRECTION_VERIFIED",
        }
        return row

    before_ball, after_ball = _ball_row_at(ball_trajectory, from_ms), _ball_row_at(ball_trajectory, to_ms)
    before_line, after_line = _line_at(goal_geometry, from_ms), _line_at(goal_geometry, to_ms)
    before_field, after_field = _field_point_at(goal_geometry, from_ms), _field_point_at(goal_geometry, to_ms)
    if not all(x is not None for x in (before_ball, after_ball, before_line, after_line, before_field, after_field)):
        return _downgrade_crossing(row, "FIELD_SIDE_ORIENTATION_UNAVAILABLE")
    before_field_d = _signed_side(before_field, before_line)
    after_field_d = _signed_side(after_field, after_line)
    before_ball_d = _signed_side(_center(before_ball["box"]), before_line)
    after_ball_d = _signed_side(_center(after_ball["box"]), after_line)
    values = (before_field_d, after_field_d, before_ball_d, after_ball_d)
    if any(value is None for value in values):
        return _downgrade_crossing(row, "FIELD_SIDE_ORIENTATION_UNAVAILABLE")
    if abs(before_field_d) < FIELD_SIDE_MIN_DISTANCE or abs(after_field_d) < FIELD_SIDE_MIN_DISTANCE:
        return _downgrade_crossing(row, "FIELD_SIDE_POINT_TOO_CLOSE_TO_GOAL_LINE")
    before_field_sign = 1 if before_field_d > 0 else -1
    after_field_sign = 1 if after_field_d > 0 else -1
    before_ball_sign = 1 if before_ball_d > 0 else -1 if before_ball_d < 0 else 0
    after_ball_sign = 1 if after_ball_d > 0 else -1 if after_ball_d < 0 else 0
    details = {
        "from_ms": from_ms,
        "to_ms": to_ms,
        "before_field_sign": before_field_sign,
        "after_field_sign": after_field_sign,
        "before_ball_sign": before_ball_sign,
        "after_ball_sign": after_ball_sign,
    }
    if before_ball_sign == before_field_sign and after_ball_sign == -after_field_sign:
        crossing = deepcopy(crossing)
        crossing["direction"] = "FIELD_TO_GOAL"
        crossing["direction_status"] = "VERIFIED"
        crossing["direction_evidence"] = details
        row["goal_plane_crossing"] = crossing
        row["direction_gate"] = {"status": "VERIFIED", "reason": "FIELD_TO_GOAL_DIRECTION_VERIFIED"}
        return row
    if before_ball_sign == -before_field_sign and after_ball_sign == after_field_sign:
        return _downgrade_crossing(row, "REVERSE_GOAL_TO_FIELD_CROSSING", details)
    return _downgrade_crossing(row, "FIELD_TO_GOAL_DIRECTION_NOT_PROVEN", details)
