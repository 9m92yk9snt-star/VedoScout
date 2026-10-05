"""FIX10A supporting vision providers for A6/A7 shadow evidence.

These adapters turn bounded raw video pixels into supporting evidence only:
- jersey-number frame votes for the existing deterministic A6 consensus,
- multi-frame goalkeeper/outfield role evidence for A7,
- independent multi-frame goal geometry + crossing audit for A7.

They never receive the primary sequence story, expected jersey numbers, GOAL /
SAVED labels, canonical events, stats or proof state.  Every reader is
fail-closed: missing/ambiguous pixels return unresolved evidence.
"""
from __future__ import annotations
from copy import deepcopy

import asyncio
import base64
import json
import hashlib
import inspect
import math
import os
import tempfile
from pathlib import Path

import cv2

import identity_verify
import video_timebase
import action_evidence_review
import goal_review_scheduler
try:  # Supporting vision is optional and always fails closed when unavailable.
    from emergentintegrations.llm.chat import LlmChat, UserMessage, ImageContent
except ImportError:  # pragma: no cover - availability is deployment-specific
    LlmChat = None

    class _UnavailableMessage:
        """Lightweight payload used by injected test chats when the SDK is absent."""

        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    UserMessage = ImageContent = _UnavailableMessage

VERSION = 1
VERIFY_PROVIDER = "openai"
VERIFY_MODEL = os.environ.get("FIX10A_SUPPORT_VISION_MODEL", "gpt-4o")

MAX_JERSEY_REQUESTS = int(os.environ.get("FIX10A_MAX_JERSEY_READS", "24"))
MAX_ROLE_TRACKS = int(os.environ.get("FIX10A_MAX_ROLE_TRACKS", "4"))
MAX_ROLE_FRAMES_PER_TRACK = int(os.environ.get("FIX10A_MAX_ROLE_FRAMES", "4"))
MAX_GOAL_FRAMES = int(os.environ.get("FIX10A_MAX_GOAL_FRAMES", "12"))

ROLE_REVIEW_RADIUS_MS = 900
ROLE_MIN_SEPARATION_MS = 150
ROLE_MIN_BOX_AREA = 0.006
ROLE_MIN_AGREEING = 2
ROLE_MIN_POSTERIOR = 0.75
ROLE_MIN_MARGIN = 0.30

_CONF_WEIGHT = {"high": 1.0, "medium": 0.60, "low": 0.25}


def _num(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _goal_review_times(strike_ms: int, end_ms: int, budget: int, start_ms: int = 0):
    """Keep release, terminal context and dense early frames within the budget."""
    offsets = (-150, 0, 50, 100, 150, 200, 300, 450, 650, 900, 1350, 1700, 2200, 2600)
    candidates = sorted({max(0, strike_ms + offset) for offset in offsets
                         if start_ms <= strike_ms + offset <= end_ms})
    if not candidates or budget <= 0:
        return []
    # A chronological head slice loses the terminal outcome. Prioritize both
    # ends, then early crossing detail and the remaining late-flight context.
    priority = [strike_ms, candidates[-1], max(0, strike_ms - 150)]
    priority.extend(strike_ms + offset for offset in (50, 100, 150, 200))
    priority.extend(reversed(candidates))
    selected = []
    for ms in priority:
        if ms in candidates and ms not in selected:
            selected.append(ms)
        if len(selected) >= budget:
            break
    return sorted(selected)


def _valid_box(box) -> bool:
    if not isinstance(box, dict):
        return False
    try:
        x, y, w, h = (float(box[k]) for k in ("x", "y", "w", "h"))
    except (KeyError, TypeError, ValueError):
        return False
    return all(math.isfinite(v) for v in (x, y, w, h)) and -0.05 <= x <= 1.05 and -0.05 <= y <= 1.05 and 0 < w <= 1.1 and 0 < h <= 1.1


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


def _model_audit(raw, prompt, paths, times=None):
    return {"provider": VERIFY_PROVIDER, "model": VERIFY_MODEL, "raw_response": str(raw)[:50000],
            "response_sha256": hashlib.sha256(str(raw).encode()).hexdigest(),
            "input_sha256": hashlib.sha256(prompt.encode() + b"".join(Path(p).read_bytes() for p in paths)).hexdigest(),
            "media_ms": list(times or [])}


def _read_frames(video_path: str, requested_ms) -> dict[int, tuple[int, object]]:
    """Read exact/nearest frames by canonical media time; values are actual PTS."""
    wanted = sorted({max(0, int(round(float(ms)))) for ms in requested_ms if _num(ms)})
    if not wanted:
        return {}
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        cap.release()
        return {}
    fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
    out = {}
    try:
        for ms in wanted:
            ok, frame, actual_s = video_timebase.read_frame_at(cap, ms / 1000.0, fps=fps)
            if ok and frame is not None:
                out[ms] = (int(round(float(actual_s) * 1000.0)), frame)
    finally:
        cap.release()
    return out


def _crop(frame, box: dict, pad_x=0.12, pad_y=0.08):
    if frame is None or not hasattr(frame, "shape") or not _valid_box(box):
        return None
    h, w = frame.shape[:2]
    x0 = (float(box["x"]) - float(box["w"]) * pad_x) * w
    y0 = (float(box["y"]) - float(box["h"]) * pad_y) * h
    x1 = (float(box["x"]) + float(box["w"]) * (1.0 + pad_x)) * w
    y1 = (float(box["y"]) + float(box["h"]) * (1.0 + pad_y)) * h
    ix0, iy0 = max(0, int(math.floor(x0))), max(0, int(math.floor(y0)))
    ix1, iy1 = min(w, int(math.ceil(x1))), min(h, int(math.ceil(y1)))
    if ix1 - ix0 < 8 or iy1 - iy0 < 12:
        return None
    return frame[iy0:iy1, ix0:ix1].copy()


def _write_jpg(path: Path, image) -> bool:
    if image is None:
        return False
    try:
        return bool(cv2.imwrite(str(path), image, [int(cv2.IMWRITE_JPEG_QUALITY), 90]))
    except Exception:
        return False


async def _bounded_gather(coros, limit=3):
    semaphore = asyncio.Semaphore(max(1, int(limit)))

    async def _one(coro):
        async with semaphore:
            return await coro

    return await asyncio.gather(*[_one(coro) for coro in coros])


async def read_visible_player_role(api_key: str, session_id: str,
                                   tight_crop_path: str, context_frame_path: str) -> dict:
    """Independent pixel-only role read; no event story or expected role input."""
    try:
        tight, context = Path(tight_crop_path), Path(context_frame_path)
        if not (tight.exists() and context.exists() and api_key):
            return {"role": "UNKNOWN", "confidence": "low", "reason": "input_missing"}
        chat = LlmChat(
            api_key=api_key,
            session_id=session_id,
            system_message=(
                "You classify only visibly supported football player roles. "
                "Never infer a role from an event outcome. Respond with strict JSON only."
            ),
        ).with_model(VERIFY_PROVIDER, VERIFY_MODEL)
        prompt = (
            "Image 1 is a tight crop of one football player. Image 2 is the SAME frame with wider match context. "
            "Classify only that cropped player's visible role. Use GOALKEEPER only when direct visual cues support it "
            "(for example goalkeeper-specific kit/gloves together with goal-area context). Use OUTFIELD only when the "
            "player is visibly an outfield player. If role cues are hidden, small, ambiguous or merely inferred from "
            "what the ball is doing, use UNKNOWN. Do not identify the player and do not infer from a shot/save story.\n"
            'Respond ONLY: {"role":"GOALKEEPER"|"OUTFIELD"|"UNKNOWN", '
            '"confidence":"high"|"medium"|"low", "reason":"<short visual reason>"}'
        )
        msg = UserMessage(
            text=prompt,
            file_contents=[ImageContent(image_base64=_b64(tight)), ImageContent(image_base64=_b64(context))],
        )
        resp = await asyncio.wait_for(chat.send_message(msg), timeout=60)
        text = resp if isinstance(resp, str) else getattr(resp, "text", None) or str(resp)
        data = _extract_json(text) or {}
        role = str(data.get("role") or "UNKNOWN").upper()
        confidence = str(data.get("confidence") or "low").lower()
        if role not in {"GOALKEEPER", "OUTFIELD", "UNKNOWN"}:
            role = "UNKNOWN"
        if confidence not in _CONF_WEIGHT:
            confidence = "low"
        if confidence == "low":
            role = "UNKNOWN"
        return {"role": role, "confidence": confidence,
                "model_review_audit": _model_audit(text, prompt, [tight, context]),
                "reason": str(data.get("reason") or "role_unresolved")[:180]}
    except Exception:
        return {"role": "UNKNOWN", "confidence": "low", "reason": "role_reader_error"}


def aggregate_role_votes(votes) -> dict:
    cleaned = []
    for vote in votes or []:
        if not isinstance(vote, dict):
            continue
        role = str(vote.get("role") or "UNKNOWN").upper()
        confidence = str(vote.get("confidence") or "low").lower()
        if role not in {"GOALKEEPER", "OUTFIELD", "UNKNOWN"}:
            role = "UNKNOWN"
        if confidence not in _CONF_WEIGHT:
            confidence = "low"
        cleaned.append({
            "media_ms": int(vote["media_ms"]) if _num(vote.get("media_ms")) else None,
            "role": role,
            "confidence": confidence,
            "reason": str(vote.get("reason") or "")[:180],
            "model_review_audit": deepcopy(vote.get("model_review_audit")),
        })
    by_frame = {}
    for vote in cleaned:
        if vote["role"] in {"GOALKEEPER", "OUTFIELD"} and vote["media_ms"] is not None:
            by_frame.setdefault(vote["media_ms"], []).append(vote)
    usable = []
    for media_ms, rows in sorted(by_frame.items()):
        if len({row["role"] for row in rows}) != 1:
            continue
        if usable and media_ms - usable[-1]["media_ms"] < ROLE_MIN_SEPARATION_MS:
            continue
        usable.append(max(rows, key=lambda row: _CONF_WEIGHT[row["confidence"]]))
    if not usable:
        return {"version": VERSION, "status": "UNRESOLVED", "role": None,
                "posterior": {}, "agreeing_frames": 0, "votes": cleaned,
                "reason": "NO_VISIBLE_ROLE_EVIDENCE"}
    weights, support = {}, {}
    for vote in usable:
        role = vote["role"]
        weights[role] = weights.get(role, 0.0) + _CONF_WEIGHT[vote["confidence"]]
        if vote["confidence"] in {"high", "medium"}:
            support[role] = support.get(role, 0) + 1
    total = sum(weights.values())
    posterior = {role: weight / total for role, weight in weights.items()} if total > 0 else {}
    ordered = sorted(posterior.items(), key=lambda row: (-row[1], row[0]))
    top_role, top_prob = ordered[0]
    second = ordered[1][1] if len(ordered) > 1 else 0.0
    margin = top_prob - second
    agreeing = int(support.get(top_role, 0))
    verified = bool(
        agreeing >= ROLE_MIN_AGREEING
        and top_prob >= ROLE_MIN_POSTERIOR
        and margin >= ROLE_MIN_MARGIN
    )
    return {
        "version": VERSION,
        "status": "VERIFIED" if verified else "UNRESOLVED",
        "role": top_role if verified else None,
        "leading_role": top_role,
        "posterior": {k: round(v, 4) for k, v in ordered},
        "confidence_method": "weighted_frame_support_not_calibrated_probability",
        "agreeing_frames": agreeing,
        "margin": round(margin, 4),
        "votes": cleaned,
        "reason": "MULTI_FRAME_ROLE_CONSENSUS" if verified else "INSUFFICIENT_ROLE_CONSENSUS",
    }


async def read_goal_scene_evidence(api_key: str, session_id: str,
                                   frame_paths: list[str], media_ms: list[int], ball_reference=None) -> dict:
    """Independent multi-frame goal geometry, ball/occlusion and reaction audit.

    Reactions are deliberately returned as support-only observations.  They do
    not change the direct whole-ball ``crossing`` verdict inside this reader.
    """
    empty = {
        "geometry_status": "UNRESOLVED", "frames": [],
        "crossing": "UNRESOLVED", "crossing_confidence": "low",
        "ball_evidence": [], "same_ball_continuity": False,
        "first_crossing_idx": None, "first_crossing_media_ms": None,
        "field_side_before_media_ms": None, "beyond_line_media_ms": None,
        "proof_ready": False, "proof_reason": "insufficient_frames",
        "occlusion_crossing_audit": {
            "status": "UNRESOLVED", "confidence": "low",
            "occlusion_start_media_ms": None, "occlusion_end_media_ms": None,
            "last_field_side_media_ms": None,
            "first_beyond_after_occlusion_media_ms": None,
            "occlusion_rows": [], "visual_contradiction": False,
            "reason": "insufficient_frames",
        },
        "reaction_support_evidence": {
            "status": "UNRESOLVED", "confidence": "low",
            "release_player_celebration": {},
            "goal_mouth_defender_response": {},
            "goal_mouth_defender_ball_contact": {},
            "reason": "insufficient_frames",
        },
        "reason": "insufficient_frames",
    }
    try:
        pairs = [
            (Path(path), int(ms)) for path, ms in zip(frame_paths, media_ms)
            if path and Path(path).exists() and _num(ms)
        ]
        if len(pairs) < 2 or not api_key:
            return dict(empty)
        timeline = ", ".join(f"image {i + 1}={ms}ms" for i, (_path, ms) in enumerate(pairs))
        chat = LlmChat(
            api_key=api_key,
            session_id=session_id,
            system_message=(
                "You inspect football goal geometry, ball visibility, literal occlusion and post-shot body reactions "
                "from chronological images. Never infer a GOAL/SAVE from celebration, scoreboards or expected events. "
                "Return only visible observations as strict JSON."
            ),
        ).with_model(VERIFY_PROVIDER, VERIFY_MODEL)
        prompt = (
            f"These images are chronological match frames: {timeline}. The first images are at/just after a "
            "physically detected ball release; no semantic event label is provided.\n"
            "GEOMETRY: For every image where the SAME relevant goal mouth is clearly visible, return the two goalpost "
            "BASE points where each post meets the ground/goal line, normalized 0..1. Do not estimate a hidden post. "
            "visible=false when both bases are not clear.\n"
            "BALL AUDIT: Follow only the visibly observable MOVING match ball in chronological order. For EVERY image "
            "return one ball_evidence row. FIELD_SIDE means the whole visible ball is on the playable-field side of the "
            "goal plane. ON_OR_STRADDLING_LINE means any part overlaps the plane. BEYOND_LINE_INSIDE_MOUTH means the "
            "ENTIRE visible ball is clearly beyond the plane and between the inner post edges. OCCLUDED_GOAL_MOUTH is "
            "allowed ONLY when the same moving ball was visible immediately before but is now hidden specifically by a "
            "player/body in the goal-mouth / goal-line region; ball_visible must be false. OTHER means visible elsewhere. "
            "UNRESOLVED means relation/identity is unclear. For hidden rows set occluder to PLAYER_BODY, "
            "GOALKEEPER_BODY, GOAL_STRUCTURE, OTHER or UNKNOWN.\n"
            "DIRECT CROSSING: same_ball_continuity=true ONLY if the ball is visible and continuously identifiable in "
            "every sampled image from the last FIELD_SIDE frame through the first BEYOND_LINE_INSIDE_MOUTH frame. Any "
            "hidden interval makes it false. CROSSED means that strict visible whole-ball transition is proven; "
            "NOT_CROSSED means a continuous visible sequence proves it did not cross; otherwise UNRESOLVED.\n"
            "REACTIONS (SUPPORT ONLY): Follow the same release player only if visually traceable from the release frames. "
            "Report celebration OBSERVED only for a clear post-shot celebratory cue such as both arms raised / obvious "
            "goal celebration, never merely running. For the player stationed in/nearest the relevant goal mouth, report "
            "ball_contact as OBSERVED_CONTACT only if literal ball-body contact is visible; NO_VISIBLE_CONTACT only means "
            "none is visible, not that contact is impossible. Report response=LATE_OR_NO_REACTION only when the player is "
            "visibly static/late after release rather than making a timely save action. These reaction fields must NOT "
            "change the crossing verdict.\n"
            'Respond ONLY: {"geometry_status":"VERIFIED"|"UNRESOLVED", "frames":['
            '{"idx":1,"visible":true|false,"p1":{"x":0.0,"y":0.0}|null,'
            '"p2":{"x":0.0,"y":0.0}|null,"confidence":"high"|"medium"|"low"}],'
            '"ball_evidence":[{"idx":1,"ball_visible":true|false,'
            '"relation":"FIELD_SIDE"|"ON_OR_STRADDLING_LINE"|"BEYOND_LINE_INSIDE_MOUTH"|'
            '"OCCLUDED_GOAL_MOUTH"|"OTHER"|"UNRESOLVED",'
            '"ball_box":{"x":0.0,"y":0.0,"w":0.0,"h":0.0}|null,'
            '"occluder":"PLAYER_BODY"|"GOALKEEPER_BODY"|"GOAL_STRUCTURE"|"OTHER"|"UNKNOWN",'
            '"confidence":"high"|"medium"|"low","reason":"<short literal visual reason>"}],'
            '"same_ball_continuity":true|false,"first_crossing_idx":1|null,'
            '"crossing":"CROSSED"|"NOT_CROSSED"|"UNRESOLVED",'
            '"crossing_confidence":"high"|"medium"|"low",'
            '"reaction_evidence":{"release_player_tracked":true|false,'
            '"release_player_celebration":"OBSERVED"|"NOT_OBSERVED"|"UNRESOLVED",'
            '"release_player_confidence":"high"|"medium"|"low",'
            '"goal_mouth_defender_tracked":true|false,'
            '"goal_mouth_defender_ball_contact":"OBSERVED_CONTACT"|"NO_VISIBLE_CONTACT"|"UNRESOLVED",'
            '"goal_mouth_defender_response":"ACTIVE_SAVE_ATTEMPT"|"LATE_OR_NO_REACTION"|"OTHER"|"UNRESOLVED",'
            '"goal_mouth_defender_confidence":"high"|"medium"|"low"},'
            '"reason":"<short visual reason>"}'
        )
        msg = UserMessage(
            text=prompt,
            file_contents=[ImageContent(image_base64=_b64(path)) for path, _ms in pairs],
        )
        if isinstance(ball_reference, dict) and _valid_box(ball_reference.get("box")):
            prompt += ("\nThe physically measured active ball reference is " + json.dumps(ball_reference, sort_keys=True)
                       + ". Include this reference frame in ball_evidence and assess crossings only AFTER this reference. "
                         "Follow ONLY this ball from this image onward. If its visible continuation is ambiguous or a "
                         "different ball reaches the goal, same_ball_continuity must be false. This reference supplies no expected result.")
            msg = UserMessage(text=prompt, file_contents=[ImageContent(image_base64=_b64(path)) for path, _ms in pairs])
        resp = await asyncio.wait_for(chat.send_message(msg), timeout=90)
        text = resp if isinstance(resp, str) else getattr(resp, "text", None) or str(resp)
        data = _extract_json(text) or {}

        cleaned_frames = []
        for row in data.get("frames") or []:
            if not isinstance(row, dict) or row.get("visible") is not True:
                continue
            try:
                idx = int(row.get("idx"))
            except (TypeError, ValueError):
                continue
            if not 1 <= idx <= len(pairs):
                continue
            p1, p2 = row.get("p1"), row.get("p2")
            try:
                a = {"x": float(p1["x"]), "y": float(p1["y"])}
                b = {"x": float(p2["x"]), "y": float(p2["y"])}
            except (TypeError, KeyError, ValueError):
                continue
            if not all(0.0 <= v <= 1.0 and math.isfinite(v) for v in (a["x"], a["y"], b["x"], b["y"])):
                continue
            if math.hypot(a["x"] - b["x"], a["y"] - b["y"]) < 0.04:
                continue
            confidence = str(row.get("confidence") or "low").lower()
            if confidence not in _CONF_WEIGHT or confidence == "low":
                continue
            cleaned_frames.append({
                "idx": idx,
                "media_ms": int(pairs[idx - 1][1]),
                "line": {"p1": a, "p2": b},
                "confidence": confidence,
            })
        geometry_verified = len(cleaned_frames) >= 2

        crossing = str(data.get("crossing") or "UNRESOLVED").upper()
        crossing_conf = str(data.get("crossing_confidence") or "low").lower()
        if crossing not in {"CROSSED", "NOT_CROSSED", "UNRESOLVED"}:
            crossing = "UNRESOLVED"
        if crossing_conf not in _CONF_WEIGHT:
            crossing_conf = "low"
        if crossing_conf == "low":
            crossing = "UNRESOLVED"

        allowed_relations = {
            "FIELD_SIDE", "ON_OR_STRADDLING_LINE", "BEYOND_LINE_INSIDE_MOUTH",
            "OCCLUDED_GOAL_MOUTH", "OTHER", "UNRESOLVED",
        }
        allowed_occluders = {"PLAYER_BODY", "GOALKEEPER_BODY", "GOAL_STRUCTURE", "OTHER", "UNKNOWN"}
        ball_rows_by_idx = {}
        for row in data.get("ball_evidence") or []:
            if not isinstance(row, dict):
                continue
            try:
                idx = int(row.get("idx"))
            except (TypeError, ValueError):
                continue
            if not 1 <= idx <= len(pairs) or idx in ball_rows_by_idx:
                continue
            relation = str(row.get("relation") or "UNRESOLVED").upper()
            if relation not in allowed_relations:
                relation = "UNRESOLVED"
            confidence = str(row.get("confidence") or "low").lower()
            if confidence not in _CONF_WEIGHT:
                confidence = "low"
            occluder = str(row.get("occluder") or "UNKNOWN").upper()
            if occluder not in allowed_occluders:
                occluder = "UNKNOWN"
            ball_box = row.get("ball_box") if _valid_box(row.get("ball_box")) else None
            ball_rows_by_idx[idx] = {
                "idx": idx,
                "media_ms": int(pairs[idx - 1][1]),
                "ball_visible": row.get("ball_visible") is True,
                "relation": relation,
                "ball_box": dict(ball_box) if isinstance(ball_box, dict) else None,
                "occluder": occluder,
                "confidence": confidence,
                "reason": str(row.get("reason") or "ball_relation_review")[:180],
            }
        ball_evidence = [ball_rows_by_idx[idx] for idx in sorted(ball_rows_by_idx)]

        same_ball = data.get("same_ball_continuity") is True
        try:
            crossing_idx = int(data.get("first_crossing_idx")) if data.get("first_crossing_idx") is not None else None
        except (TypeError, ValueError):
            crossing_idx = None
        if crossing_idx is not None and not 1 <= crossing_idx <= len(pairs):
            crossing_idx = None
        field_candidates = [
            row for row in ball_evidence
            if crossing_idx is not None and row["idx"] < crossing_idx
            and row["ball_visible"] and row["relation"] == "FIELD_SIDE"
            and row["confidence"] == "high"
        ]
        beyond_candidates = [
            row for row in ball_evidence
            if crossing_idx is not None and row["idx"] >= crossing_idx
            and row["ball_visible"] and row["relation"] == "BEYOND_LINE_INSIDE_MOUTH"
            and row["confidence"] == "high"
        ]
        before = max(field_candidates, key=lambda row: row["idx"], default=None)
        after = min(beyond_candidates, key=lambda row: row["idx"], default=None)
        earliest_beyond = min(
            (row["idx"] for row in ball_evidence
             if row["ball_visible"] and row["relation"] == "BEYOND_LINE_INSIDE_MOUTH"
             and row["confidence"] in {"high", "medium"}),
            default=None,
        )
        path_rows = []
        path_complete = False
        if before is not None and after is not None:
            path_rows = [ball_rows_by_idx.get(idx) for idx in range(int(before["idx"]), int(after["idx"]) + 1)]
            path_complete = bool(
                len(path_rows) >= 3
                and all(
                    isinstance(row, dict)
                    and row.get("ball_visible") is True
                    and row.get("confidence") in {"high", "medium"}
                    and row.get("relation") in {
                        "FIELD_SIDE", "ON_OR_STRADDLING_LINE", "BEYOND_LINE_INSIDE_MOUTH"
                    }
                    for row in path_rows
                )
            )
        proof_ready = bool(
            geometry_verified and crossing == "CROSSED" and crossing_conf == "high"
            and same_ball and crossing_idx is not None and before is not None and after is not None
            and earliest_beyond == crossing_idx == int(after["idx"]) and path_complete
        )
        proof_reason = (
            "STRUCTURED_MULTI_FRAME_WHOLE_BALL_CROSSING" if proof_ready
            else "STRUCTURED_WHOLE_BALL_CROSSING_NOT_PROVEN"
        )

        # Literal goal-mouth occlusion audit.  This validates *only* that a
        # bounded body occlusion exists after a clear FIELD_SIDE ball.  It does
        # not infer that the ball crossed the line.
        occ_candidates = [
            row for row in ball_evidence
            if row.get("ball_visible") is False
            and row.get("relation") == "OCCLUDED_GOAL_MOUTH"
            and row.get("confidence") in {"high", "medium"}
            and row.get("occluder") in {"PLAYER_BODY", "GOALKEEPER_BODY"}
        ]
        occ_rows = []
        if occ_candidates:
            ordered = sorted(occ_candidates, key=lambda r: r["idx"])
            occ_rows = [ordered[0]]
            for row in ordered[1:]:
                if int(row["idx"]) == int(occ_rows[-1]["idx"]) + 1:
                    occ_rows.append(row)
                else:
                    break
        occ_start = int(occ_rows[0]["media_ms"]) if occ_rows else None
        occ_end = int(occ_rows[-1]["media_ms"]) if occ_rows else None
        before_occ = max(
            (row for row in ball_evidence
             if occ_rows and row["idx"] < occ_rows[0]["idx"]
             and row.get("ball_visible") is True and row.get("relation") == "FIELD_SIDE"
             and row.get("confidence") == "high"),
            key=lambda row: row["idx"], default=None,
        )
        beyond_after_occ = min(
            (row for row in ball_evidence
             if occ_rows and row["idx"] > occ_rows[-1]["idx"]
             and row.get("ball_visible") is True
             and row.get("relation") == "BEYOND_LINE_INSIDE_MOUTH"
             and row.get("confidence") in {"high", "medium"}),
            key=lambda row: row["idx"], default=None,
        )
        visual_contradiction = bool(
            occ_rows and any(
                row.get("ball_visible") is True and row.get("confidence") == "high"
                and row.get("relation") in {"FIELD_SIDE", "OTHER"}
                and int(occ_rows[-1]["idx"]) < int(row["idx"]) <= int(occ_rows[-1]["idx"]) + 2
                for row in ball_evidence
            )
        )
        pre_occ_visible_rows = []
        same_ball_pre_occlusion = False
        if occ_rows and before_occ is not None:
            # Preserve a contiguous, bounded visible-ball path immediately
            # before the first body-occluded frame.  Boxes are provider
            # observations at exact sampled media times; they never masquerade
            # as detector measurements.
            start_idx = max(1, int(occ_rows[0]["idx"]) - 4)
            candidate_rows = [
                ball_rows_by_idx.get(idx)
                for idx in range(start_idx, int(occ_rows[0]["idx"]))
            ]
            candidate_rows = [row for row in candidate_rows if isinstance(row, dict)]
            tail = []
            for row in reversed(candidate_rows):
                if not (
                    row.get("ball_visible") is True
                    and row.get("confidence") in {"high", "medium"}
                    and row.get("relation") in {"FIELD_SIDE", "ON_OR_STRADDLING_LINE"}
                    and isinstance(row.get("ball_box"), dict)
                ):
                    break
                tail.append(row)
            pre_occ_visible_rows = list(reversed(tail))
            same_ball_pre_occlusion = len(pre_occ_visible_rows) >= 2
        occ_span_ok = bool(
            occ_start is not None and occ_end is not None and 0 <= occ_end - occ_start <= 900
        )
        occ_verified = bool(
            geometry_verified and occ_rows and before_occ is not None and occ_span_ok
            and same_ball_pre_occlusion and not visual_contradiction
        )
        occ_conf = (
            "high" if occ_verified and all(r.get("confidence") == "high" for r in occ_rows)
            else "medium" if occ_verified else "low"
        )
        occlusion_audit = {
            "status": "VERIFIED_OCCLUSION" if occ_verified else "UNRESOLVED",
            "confidence": occ_conf,
            "occlusion_start_media_ms": occ_start,
            "occlusion_end_media_ms": occ_end,
            "last_field_side_media_ms": int(before_occ["media_ms"]) if isinstance(before_occ, dict) else None,
            "first_beyond_after_occlusion_media_ms": int(beyond_after_occ["media_ms"]) if isinstance(beyond_after_occ, dict) else None,
            "occlusion_rows": [dict(row) for row in occ_rows],
            "pre_occlusion_visible_rows": [dict(row) for row in pre_occ_visible_rows],
            "same_ball_pre_occlusion": same_ball_pre_occlusion,
            "visual_contradiction": visual_contradiction,
            "reason": (
                "BOUNDED_PLAYER_BODY_GOAL_MOUTH_OCCLUSION" if occ_verified
                else "GOAL_MOUTH_OCCLUSION_NOT_PROVEN"
            ),
        }

        # Reaction evidence remains support only.  A positive support verdict
        # requires two separate literal observations and is never fed into the
        # direct whole-ball CROSSED verdict above.
        react = data.get("reaction_evidence") if isinstance(data.get("reaction_evidence"), dict) else {}
        release_tracked = react.get("release_player_tracked") is True
        celebration = str(react.get("release_player_celebration") or "UNRESOLVED").upper()
        celebration_conf = str(react.get("release_player_confidence") or "low").lower()
        defender_tracked = react.get("goal_mouth_defender_tracked") is True
        defender_contact = str(react.get("goal_mouth_defender_ball_contact") or "UNRESOLVED").upper()
        defender_response = str(react.get("goal_mouth_defender_response") or "UNRESOLVED").upper()
        defender_conf = str(react.get("goal_mouth_defender_confidence") or "low").lower()
        if celebration not in {"OBSERVED", "NOT_OBSERVED", "UNRESOLVED"}:
            celebration = "UNRESOLVED"
        if defender_contact not in {"OBSERVED_CONTACT", "NO_VISIBLE_CONTACT", "UNRESOLVED"}:
            defender_contact = "UNRESOLVED"
        if defender_response not in {"ACTIVE_SAVE_ATTEMPT", "LATE_OR_NO_REACTION", "OTHER", "UNRESOLVED"}:
            defender_response = "UNRESOLVED"
        if celebration_conf not in _CONF_WEIGHT:
            celebration_conf = "low"
        if defender_conf not in _CONF_WEIGHT:
            defender_conf = "low"
        contact_contradiction = bool(
            defender_tracked and defender_contact == "OBSERVED_CONTACT"
            and defender_conf in {"high", "medium"}
        )
        reaction_verified = bool(
            release_tracked and celebration == "OBSERVED" and celebration_conf in {"high", "medium"}
            and defender_tracked and defender_response == "LATE_OR_NO_REACTION"
            and defender_conf in {"high", "medium"}
            and not contact_contradiction
        )
        reaction_conf = (
            "high" if reaction_verified and celebration_conf == "high" and defender_conf == "high"
            else "medium" if reaction_verified else "low"
        )
        reaction_support = {
            "status": "CONTRADICTED" if contact_contradiction else ("VERIFIED" if reaction_verified else "UNRESOLVED"),
            "confidence": reaction_conf,
            "release_player_celebration": {
                "status": celebration, "confidence": celebration_conf, "tracked": release_tracked,
            },
            "goal_mouth_defender_response": {
                "status": defender_response, "confidence": defender_conf, "tracked": defender_tracked,
            },
            "goal_mouth_defender_ball_contact": {
                "status": defender_contact, "confidence": defender_conf, "tracked": defender_tracked,
            },
            "reason": (
                "VISIBLE_DEFENDER_BALL_CONTACT_CONTRADICTS_UNOPPOSED_REACTION_SUPPORT" if contact_contradiction
                else "CELEBRATION_PLUS_LATE_OR_NO_GOAL_MOUTH_REACTION" if reaction_verified
                else "REACTION_SUPPORT_INSUFFICIENT"
            ),
        }

        return {
            "geometry_status": "VERIFIED" if geometry_verified else "UNRESOLVED",
            "model_review_audit": _model_audit(text, prompt, [p for p, _ in pairs], [ms for _, ms in pairs]),
            "frames": cleaned_frames,
            "crossing": crossing,
            "crossing_confidence": crossing_conf,
            "ball_evidence": ball_evidence,
            "same_ball_continuity": same_ball,
            "first_crossing_idx": crossing_idx,
            "first_crossing_media_ms": int(pairs[crossing_idx - 1][1]) if crossing_idx is not None else None,
            "field_side_before_media_ms": int(before["media_ms"]) if isinstance(before, dict) else None,
            "beyond_line_media_ms": int(after["media_ms"]) if isinstance(after, dict) else None,
            "proof_ready": proof_ready,
            "proof_reason": proof_reason,
            "occlusion_crossing_audit": occlusion_audit,
            "reaction_support_evidence": reaction_support,
            "reason": str(data.get("reason") or "goal_scene_review")[:220],
        }
    except Exception:
        failed = dict(empty)
        failed["proof_reason"] = "goal_scene_reader_error"
        failed["reason"] = "goal_scene_reader_error"
        return failed

def _first_post_strike_other_touches(strikes, touch_graph) -> dict[str, int]:
    graph = touch_graph if isinstance(touch_graph, dict) else {}
    touches = [t for t in graph.get("touches") or [] if isinstance(t, dict)]
    out = {}
    for strike in strikes or []:
        if not isinstance(strike, dict) or not _num(strike.get("media_ms")):
            continue
        start = int(strike["media_ms"])
        actor = strike.get("player_track_id")
        scene = strike.get("scene_id")
        candidates = [
            t for t in touches
            if t.get("status") == "VERIFIED"
            and isinstance(t.get("player_track_id"), str)
            and t.get("player_track_id") != actor
            and t.get("scene_id") == scene
            and _num(t.get("media_ms"))
            and start < int(t["media_ms"]) <= start + 3000
        ]
        if not candidates:
            continue
        first = min(candidates, key=lambda t: int(t["media_ms"]))
        track = first["player_track_id"]
        out.setdefault(track, int(first.get("representative_ms") or first["media_ms"]))
    return out


def _verified_intervention_track_times(interventions) -> dict[str, int]:
    """Return only independently VERIFIED A7 intervention actors.

    A7 full-body intervention deliberately bypasses A4/A5 Touch Graph semantics.
    Supporting role review therefore needs a direct, evidence-only handoff from
    the already-verified A7 actor; otherwise a hand/arm save can never request a
    goalkeeper-role read.  No role is inferred here.
    """
    out = {}
    for row in interventions or []:
        if not isinstance(row, dict):
            continue
        if row.get("status") != "VERIFIED" or row.get("proof_eligible") is not True:
            continue
        track = row.get("player_track_id")
        if not isinstance(track, str) or not _num(row.get("media_ms")):
            continue
        media_ms = int(row["media_ms"])
        out[track] = min(media_ms, out.get(track, media_ms))
    return out


def _role_review_requests(window_evidence, track_times: dict[str, int]) -> list[dict]:
    requests = []
    for track, pivot_ms in list(track_times.items())[:MAX_ROLE_TRACKS]:
        candidates = []
        for frame in window_evidence or []:
            if not isinstance(frame, dict) or not _num(frame.get("media_ms")):
                continue
            ms = int(frame["media_ms"])
            if abs(ms - int(pivot_ms)) > ROLE_REVIEW_RADIUS_MS or frame.get("used_fallback") is True:
                continue
            for player in frame.get("players") or []:
                if not isinstance(player, dict) or player.get("local_track_id") != track:
                    continue
                box = player.get("box")
                if not _valid_box(box) or str(player.get("association_state") or "") == "HYPOTHESES":
                    continue
                area = float(box["w"]) * float(box["h"])
                if area < ROLE_MIN_BOX_AREA:
                    continue
                candidates.append({"track_id": track, "media_ms": ms, "box": dict(box), "area": area})
        ranked = sorted(candidates, key=lambda row: (-row["area"], abs(row["media_ms"] - pivot_ms)))
        chosen = []
        for row in ranked:
            if any(abs(row["media_ms"] - old["media_ms"]) < ROLE_MIN_SEPARATION_MS for old in chosen):
                continue
            chosen.append(row)
            if len(chosen) >= MAX_ROLE_FRAMES_PER_TRACK:
                break
        requests.extend(sorted(chosen, key=lambda row: row["media_ms"]))
    return requests


async def read_action_pixel_evidence(api_key, session_id, paths, media_ms):
    """Locate visible pixels for independent re-detection/crop review only."""
    import hashlib
    if not api_key or LlmChat is None:
        return {"status": "UNAVAILABLE", "reason": "action_pixel_reader_unavailable", "frames": []}
    timeline = ", ".join(f"image {i + 1}={ms}ms" for i, ms in enumerate(media_ms))
    prompt = (
        f"Chronological football images: {timeline}. Inspect visible pixels only. "
        "No selected player, jersey number, action label or expected result is supplied. "
        "Locate the visible football (not spare balls, field markings, socks or guessed hidden positions). "
        "If you cannot distinguish the active ball, return no ball boxes for that image. "
        "Also locate player bodies whose jersey digits are clearly exposed and could be inspected in a tight crop. "
        "Do not read or guess the digits; a separate crop reader does that. Do not infer identity, a pass, a shot, "
        "a goal, an assist, ball ownership or an outcome. Coordinates are normalized 0..1 from the full image top-left. "
        'Return only {"frames":[{"idx":1,"balls":[{"box":{"x":0,"y":0,"w":0.01,"h":0.01},'
        '"confidence":"high"|"medium"|"low"}],"jersey_bodies":[{"box":{"x":0,"y":0,"w":0.1,"h":0.2},'
        '"confidence":"high"|"medium"|"low"}]}]} . Empty lists are valid.'
    )
    try:
        chat = LlmChat(api_key=api_key, session_id=session_id,
                       system_message="Inspect visible pixel locations only. Return strict JSON.").with_model(VERIFY_PROVIDER, VERIFY_MODEL)
        response = await asyncio.wait_for(chat.send_message(UserMessage(
            text=prompt, file_contents=[ImageContent(image_base64=_b64(p)) for p in paths])), timeout=90)
        raw = response if isinstance(response, str) else getattr(response, "text", None) or str(response)
        parsed = _extract_json(raw)
        valid = isinstance((parsed or {}).get("frames"), list)
        return {"status": "COMPLETED" if valid else "INVALID_RESPONSE",
                "reason": "PIXEL_PROPOSALS_ONLY" if valid else "action_pixel_reader_invalid_json",
                "frames": parsed["frames"] if valid else [], "model": VERIFY_MODEL, "provider": VERIFY_PROVIDER,
                "raw_response": raw[:50000], "response_sha256": hashlib.sha256(raw.encode()).hexdigest(),
                "input_sha256": hashlib.sha256(prompt.encode() + b"".join(Path(p).read_bytes() for p in paths)).hexdigest()}
    except Exception as exc:
        return {"status": "ERROR", "reason": "action_pixel_reader_error", "error_type": type(exc).__name__,
                "frames": [], "model": VERIFY_MODEL, "provider": VERIFY_PROVIDER}


def corroborate_ball_pixels(detector, image, proposal):
    """A model box is a search ROI; only native class-32 detection supplies a row."""
    if not _valid_box(proposal):
        return []
    proposal = {key: float(proposal[key]) for key in ("x", "y", "w", "h")}
    if proposal["w"] > .08 or proposal["h"] > .04:
        return []
    import dense_track_refinement
    height, width = image.shape[:2]
    cx = (proposal["x"] + proposal["w"] / 2) * width
    cy = (proposal["y"] + proposal["h"] / 2) * height
    half_w, half_h = max(.09 * width, 4 * proposal["w"] * width), max(.045 * height, 4 * proposal["h"] * height)
    x0, y0 = max(0, int(cx - half_w)), max(0, int(cy - half_h))
    x1, y1 = min(width, int(cx + half_w)), min(height, int(cy + half_h))
    if x1 - x0 < 16 or y1 - y0 < 16:
        return []
    _people, balls = dense_track_refinement._detect_dense_people_and_ball(
        detector, image[y0:y1, x0:x1], _detail_pass=True)
    accepted = []
    for ball in balls:
        box = ball["box"]
        box = {"x": (x0 + box["x"] * (x1 - x0)) / width,
               "y": (y0 + box["y"] * (y1 - y0)) / height,
               "w": box["w"] * (x1 - x0) / width, "h": box["h"] * (y1 - y0) / height}
        if box["w"] <= .08 and box["h"] <= .04 and goal_review_scheduler._iou(box, proposal) >= .20:
            accepted.append({"box": box, "confidence": ball["confidence"],
                             "source": "NATIVE_REVIEW_ROI_DETECTOR", "pixel_corroborated": True,
                             "proposal_box": deepcopy(proposal)})
    return accepted


def _active_ball_link(review, reference):
    if not isinstance(reference, dict):
        return {"status": "UNRESOLVED", "reason": "CONTACT_BALL_REFERENCE_UNAVAILABLE"}
    matching = [r for r in (review or {}).get("ball_evidence") or [] if isinstance(r, dict)
                and r.get("media_ms") == reference["media_ms"] and r.get("ball_visible") is True
                and r.get("confidence") in {"high", "medium"}
                and goal_review_scheduler._iou(r.get("ball_box"), reference["box"]) >= .20]
    return {"status": "VERIFIED" if len(matching) == 1 else "UNRESOLVED",
            "reason": "VISUAL_PATH_LINKED_TO_MEASURED_CONTACT_BALL" if len(matching) == 1
                      else "REVIEWED_BALL_NOT_BOUND_TO_CONTACT",
            "media_ms": reference["media_ms"], "measured_box": deepcopy(reference["box"]),
            "visual_box": deepcopy(matching[0]["ball_box"]) if len(matching) == 1 else None}


class ShadowVisionProviders:
    """Stateful/cached sync callbacks used inside the FIX10A worker thread."""

    def __init__(self, api_key: str | None, session_prefix: str):
        self.api_key = str(api_key or "")
        self.session_prefix = str(session_prefix or "fix10a")
        self._goal_cache = {}
        self._jersey_cache = {}
        self.jersey_calls = 0
        self._inspection_cache = {}
        self.inspection_calls = 0
        self.role_calls = 0
        self.goal_calls = 0

    def action_evidence_provider(self, video_path, job, dense_frames):
        requested = action_evidence_review.frame_times(job, dense_frames)
        if len(requested) < 2:
            return {"status": "UNRESOLVED", "reason": "ACTION_INSPECTION_FRAMES_UNAVAILABLE", "frames": []}
        cache_key = (str(video_path), job["inspection_id"], tuple(requested))
        if cache_key in self._inspection_cache:
            return deepcopy(self._inspection_cache[cache_key])
        if self.inspection_calls >= action_evidence_review.MAX_ACTION_REVIEWS:
            return {"status": "DEFERRED", "reason": "ACTION_INSPECTION_BUDGET_EXHAUSTED", "frames": []}
        if not self.api_key:
            return {"status": "UNAVAILABLE", "reason": "action_pixel_reader_unavailable", "frames": []}
        decoded = _read_frames(video_path, requested)
        images = {}
        self.inspection_calls += 1
        with tempfile.TemporaryDirectory(prefix="action_pixels_") as directory:
            paths, times = [], []
            for index, requested_ms in enumerate(requested):
                got = decoded.get(requested_ms)
                if not got or got[0] in images:
                    continue
                actual_ms, image = got
                if not job["start_ms"] <= actual_ms <= job["end_ms"]:
                    continue
                path = Path(directory) / f"pixels_{index:03d}.jpg"
                if _write_jpg(path, image):
                    paths.append(str(path)); times.append(int(actual_ms)); images[int(actual_ms)] = image
            if len(paths) < 2:
                return {"status": "UNRESOLVED", "reason": "ACTION_INSPECTION_DECODE_INSUFFICIENT", "frames": []}
            review = asyncio.run(read_action_pixel_evidence(
                self.api_key, f"{self.session_prefix}-pixels-{job['inspection_id']}", paths, times))
        import dense_track_refinement
        detector = dense_track_refinement._default_detector()
        rows = []
        seen_indices = set()
        for row in (review.get("frames") or [])[:action_evidence_review.MAX_ACTION_FRAMES]:
            if not isinstance(row, dict) or not isinstance(row.get("idx"), int) or isinstance(row.get("idx"), bool):
                continue
            index = row["idx"] - 1
            if not 0 <= index < len(times) or index in seen_indices:
                continue
            seen_indices.add(index)
            media_ms = times[index]
            balls = []
            proposals = row.get("balls") if isinstance(row.get("balls"), list) else []
            for ball in proposals[:3]:
                if isinstance(ball, dict) and ball.get("confidence") in {"high", "medium"}:
                    balls.extend(corroborate_ball_pixels(detector, images[media_ms], ball.get("box")))
            proposals = row.get("jersey_bodies") if isinstance(row.get("jersey_bodies"), list) else []
            bodies = [p for p in proposals[:6] if isinstance(p, dict)
                      and p.get("confidence") in {"high", "medium"} and _valid_box(p.get("box"))]
            rows.append({"media_ms": media_ms, "scene_id": job["scene_id"],
                         "ball_candidates": balls, "jersey_bodies": bodies})
        result = {**review, "frames": rows, "time_authority": "ACTUAL_MEDIA_PTS",
                  "requested_media_ms": requested, "decoded_media_ms": times,
                  "canonical_authority": False, "ball_corroboration": "NATIVE_CLASS_32_DETECTOR"}
        self._inspection_cache[cache_key] = deepcopy(result)
        return result

    def jersey_vote_provider(self, video_path: str, requests) -> dict:
        candidates = [r for r in (requests or []) if isinstance(r, dict)]
        candidates.sort(key=lambda r: (int(r.get("selection_rank") or 1) > 2,
                                       int(r.get("review_priority") or 0),
                                       int(r.get("selection_rank") or 1)))
        rows = candidates[:MAX_JERSEY_REQUESTS]
        if not rows:
            return {}
        if not self.api_key:
            return {str(row.get("track_id")): [{"readable": False, "number": None,
                     "reason": "reader_unavailable", "confidence": "low"}] for row in rows}
        frames = _read_frames(video_path, [r.get("media_ms") for r in rows])
        votes_by_track = {}
        with tempfile.TemporaryDirectory(prefix="fix10a_jersey_") as temp:
            jobs = []
            job_meta = []
            root = Path(temp)
            for index, row in enumerate(rows):
                track = row.get("track_id")
                requested_ms = row.get("media_ms")
                box = row.get("box")
                if not isinstance(track, str) or not _num(requested_ms) or not _valid_box(box):
                    continue
                got = frames.get(int(requested_ms))
                if not got:
                    continue
                actual_ms, frame = got
                cache_key = (int(actual_ms), tuple(round(float(box[k]), 5) for k in ("x", "y", "w", "h")))
                if cache_key in self._jersey_cache:
                    vote = deepcopy(self._jersey_cache[cache_key])
                    vote.update(media_ms=int(actual_ms), request_id=row.get("request_id"), reused=True)
                    votes_by_track.setdefault(track, []).append(vote)
                    continue
                crop = _crop(frame, box)
                path = root / f"jersey_{index:03d}.jpg"
                if crop is None or not _write_jpg(path, crop):
                    continue
                jobs.append(identity_verify.read_visible_jersey_number(
                    self.api_key,
                    f"{self.session_prefix}-jersey-{index}",
                    str(path),
                ))
                job_meta.append((track, actual_ms, row.get("request_id"), cache_key))
            if not jobs:
                return votes_by_track
            self.jersey_calls += len(jobs)
            try:
                results = asyncio.run(_bounded_gather(jobs, limit=3))
            except Exception:
                results = [{"readable": False, "number": None, "confidence": "low",
                            "reason": "reader_error"} for _ in job_meta]
            for (track, actual_ms, request_id, cache_key), result in zip(job_meta, results):
                vote = dict(result) if isinstance(result, dict) else {
                    "readable": False, "number": None, "confidence": "low", "reason": "reader_unavailable"
                }
                vote.update({"media_ms": int(actual_ms), "request_id": request_id})
                self._jersey_cache[cache_key] = deepcopy(vote)
                # Expected jersey number is deliberately never passed to the reader.
                votes_by_track.setdefault(track, []).append(vote)
        return votes_by_track

    def role_evidence_provider(self, video_path: str, window: dict, strikes,
                               touch_graph: dict, window_evidence, interventions=None) -> dict:
        if not self.api_key:
            return {}
        # A7 intervention actors are primary role-review candidates because A7
        # intentionally does not create ordinary A4/A5 touches. Touch-derived
        # candidates remain useful as secondary supporting context.
        track_times = _verified_intervention_track_times(interventions)
        for track, media_ms in _first_post_strike_other_touches(strikes, touch_graph).items():
            track_times[track] = min(media_ms, track_times.get(track, media_ms))
        requests = _role_review_requests(window_evidence, track_times)
        if not requests:
            return {}
        frames = _read_frames(video_path, [r["media_ms"] for r in requests])
        raw_votes = {}
        with tempfile.TemporaryDirectory(prefix="fix10a_role_") as temp:
            root = Path(temp)
            jobs, job_meta = [], []
            for index, row in enumerate(requests):
                got = frames.get(int(row["media_ms"]))
                if not got:
                    continue
                actual_ms, frame = got
                crop = _crop(frame, row["box"], pad_x=0.18, pad_y=0.10)
                tight = root / f"role_tight_{index:03d}.jpg"
                context = root / f"role_context_{index:03d}.jpg"
                if crop is None or not _write_jpg(tight, crop) or not _write_jpg(context, frame):
                    continue
                jobs.append(read_visible_player_role(
                    self.api_key,
                    f"{self.session_prefix}-role-{index}",
                    str(tight), str(context),
                ))
                job_meta.append((row["track_id"], int(actual_ms)))
            if not jobs:
                return {}
            self.role_calls += len(jobs)
            try:
                results = asyncio.run(_bounded_gather(jobs, limit=2))
            except Exception:
                results = [{"role": "UNKNOWN", "confidence": "low",
                            "reason": "role_reader_error"} for _ in job_meta]
            for (track, actual_ms), result in zip(job_meta, results):
                vote = dict(result) if isinstance(result, dict) else {
                    "role": "UNKNOWN", "confidence": "low", "reason": "reader_unavailable"
                }
                vote["media_ms"] = int(actual_ms)
                raw_votes.setdefault(track, []).append(vote)
        return {track: aggregate_role_votes(votes) for track, votes in raw_votes.items()}

    def goal_geometry_provider(self, window: dict, strike: dict):
        if not self.api_key or not isinstance(strike, dict) or not _num(strike.get("media_ms")):
            return None
        video_path = str(getattr(self, "video_path", "") or "")
        if not video_path:
            return None
        strike_ms = int(strike["media_ms"])
        end_ms = int(window.get("end_ms")) if isinstance(window, dict) and _num(window.get("end_ms")) else strike_ms + 2600
        # Dense around the first post-release second so a body occlusion at
        # the goal line is actually sampled; later frames preserve reaction
        # context.  The provider call remains bounded by MAX_GOAL_FRAMES.
        start_ms = int(window.get("start_ms") or 0)
        requested = _goal_review_times(strike_ms, end_ms, MAX_GOAL_FRAMES, start_ms=start_ms)
        anchor = strike.get("active_ball_anchor") or {}
        anchor_valid = bool(_num(anchor.get("media_ms")) and _valid_box(anchor.get("box"))
                            and anchor.get("proof_eligible") is True and anchor.get("time_authority") == "ACTUAL_MEDIA_PTS"
                            and not anchor.get("used_fallback") and anchor.get("state") in {"MEASURED", "MEASURED_REACQUISITION"}
                            and start_ms <= anchor["media_ms"] <= end_ms)
        if anchor_valid and int(anchor["media_ms"]) not in requested and MAX_GOAL_FRAMES > 0:
            if len(requested) >= MAX_GOAL_FRAMES:
                removable = [ms for ms in requested if ms not in {strike_ms, requested[-1]}]
                if removable:
                    requested.remove(min(removable, key=lambda ms: abs(ms - anchor["media_ms"])))
                else:
                    requested.pop(0)
            requested = sorted([*requested, int(anchor["media_ms"])])
        requires_reference = bool(anchor or strike.get("status") in {"VERIFIED_PHYSICAL_RELEASE", "VERIFIED_PHYSICAL_SCORING_CONTACT"})
        anchor_key = (int(anchor["media_ms"]), tuple(float(anchor["box"][k]) for k in ("x", "y", "w", "h"))) if anchor_valid else None
        cache_key = (str(window.get("dense_window_id") if isinstance(window, dict) else ""), strike_ms, tuple(requested),
                     (requires_reference, anchor_key))
        if cache_key in self._goal_cache:
            return self._goal_cache[cache_key]
        frames = _read_frames(video_path, requested)
        if len(frames) < 2:
            self._goal_cache[cache_key] = None
            return None
        with tempfile.TemporaryDirectory(prefix="fix10a_goal_") as temp:
            root = Path(temp)
            paths, actual_times = [], []
            seen_actual_ms = set()
            for index, requested_ms in enumerate(requested):
                got = frames.get(int(requested_ms))
                if not got:
                    continue
                actual_ms, frame = got
                actual_ms = int(actual_ms)
                if actual_ms < start_ms or actual_ms > end_ms:
                    continue
                if actual_ms in seen_actual_ms:
                    continue
                path = root / f"goal_{index:03d}.jpg"
                if _write_jpg(path, frame):
                    seen_actual_ms.add(actual_ms)
                    paths.append(str(path)); actual_times.append(actual_ms)
            if len(paths) < 2:
                self._goal_cache[cache_key] = None
                return None
            try:
                self.goal_calls += 1
                reference = {"idx": actual_times.index(int(anchor["media_ms"])) + 1,
                             "media_ms": int(anchor["media_ms"]), "box": deepcopy(anchor["box"])} \
                    if anchor_valid and int(anchor["media_ms"]) in actual_times else None
                kwargs = {"ball_reference": reference} if "ball_reference" in inspect.signature(read_goal_scene_evidence).parameters else {}
                review = asyncio.run(read_goal_scene_evidence(
                    self.api_key,
                    f"{self.session_prefix}-goal-{strike_ms}",
                    paths, actual_times, **kwargs,
                ))
            except Exception:
                review = {}
        rows = review.get("frames") or [] if isinstance(review, dict) else []
        link = _active_ball_link(review, reference) if requires_reference else None
        if not rows:
            result = {
                "status": "UNRESOLVED",
                "model_review_audit": (review or {}).get("model_review_audit"),
                "source": "INDEPENDENT_MULTI_FRAME_GOAL_REVIEW",
                "line_by_ms": [],
                "visual_crossing_audit": {
                    "status": "UNRESOLVED", "confidence": "low",
                    "reason": str((review or {}).get("reason") or "goal_geometry_unresolved")[:220],
                    "proof_ready": False,
                    "proof_reason": str((review or {}).get("proof_reason") or "goal_geometry_unresolved")[:220],
                    "same_ball_continuity": False,
                    "first_crossing_media_ms": None,
                    "field_side_before_media_ms": None,
                    "beyond_line_media_ms": None,
                    "structured_evidence": [],
                },
                "occlusion_crossing_audit": dict((review or {}).get("occlusion_crossing_audit") or {
                    "status": "UNRESOLVED", "confidence": "low",
                    "reason": "goal_geometry_unresolved",
                }),
                "reaction_support_evidence": dict((review or {}).get("reaction_support_evidence") or {
                    "status": "UNRESOLVED", "confidence": "low",
                    "reason": "goal_geometry_unresolved",
                }),
            }
            self._goal_cache[cache_key] = result
            if requires_reference:
                result["visual_crossing_audit"]["active_ball_link"] = link
            return result
        # Keep every accepted per-frame geometry row.  The legacy/static line is
        # the row nearest the middle of the post-release review and is retained
        # only for backwards-compatible A7 consumers; line_by_ms is authoritative
        # supporting geometry for newer consumers.
        target_ms = strike_ms + 800
        nearest = min(rows, key=lambda row: abs(int(row["media_ms"]) - target_ms))
        crossing = str((review or {}).get("crossing") or "UNRESOLVED").upper()
        crossing_conf = str((review or {}).get("crossing_confidence") or "low").lower()
        audit_status = (
            "VERIFIED_CROSSING" if crossing == "CROSSED" and crossing_conf in {"high", "medium"}
            else "VERIFIED_NO_CROSSING" if crossing == "NOT_CROSSED" and crossing_conf in {"high", "medium"}
            else "UNRESOLVED"
        )
        result = {
            "status": "VERIFIED" if (review or {}).get("geometry_status") == "VERIFIED" else "UNRESOLVED",
            "model_review_audit": (review or {}).get("model_review_audit"),
            "source": "INDEPENDENT_MULTI_FRAME_GOAL_REVIEW",
            "line": dict(nearest["line"]),
            "line_media_ms": int(nearest["media_ms"]),
            "line_by_ms": [
                {"media_ms": int(row["media_ms"]), "line": dict(row["line"]),
                 "confidence": row.get("confidence")}
                for row in rows
            ],
            "visual_crossing_audit": {
                "status": audit_status,
                "confidence": crossing_conf,
                "reason": str((review or {}).get("reason") or "goal_scene_review")[:220],
                "proof_ready": bool((review or {}).get("proof_ready")),
                "proof_reason": str((review or {}).get("proof_reason") or "STRUCTURED_WHOLE_BALL_CROSSING_NOT_PROVEN")[:220],
                "same_ball_continuity": (review or {}).get("same_ball_continuity") is True,
                "first_crossing_media_ms": (review or {}).get("first_crossing_media_ms"),
                "field_side_before_media_ms": (review or {}).get("field_side_before_media_ms"),
                "beyond_line_media_ms": (review or {}).get("beyond_line_media_ms"),
                "structured_evidence": list((review or {}).get("ball_evidence") or []),
            },
            # Separate support lanes.  Neither is allowed to create a crossing
            # by itself; shot_outcome_engine requires a bounded physical
            # trajectory projection before these can contribute.
            "occlusion_crossing_audit": dict((review or {}).get("occlusion_crossing_audit") or {
                "status": "UNRESOLVED", "confidence": "low",
                "reason": "GOAL_MOUTH_OCCLUSION_NOT_PROVEN",
            }),
            "reaction_support_evidence": dict((review or {}).get("reaction_support_evidence") or {
                "status": "UNRESOLVED", "confidence": "low",
                "reason": "REACTION_SUPPORT_INSUFFICIENT",
            }),
        }
        if requires_reference:
            result["visual_crossing_audit"]["active_ball_link"] = link
            result["active_ball_reference"] = reference
            if link["status"] != "VERIFIED":
                result["visual_crossing_audit"].update(status="UNRESOLVED", proof_ready=False,
                    reason=link["reason"], proof_reason=link["reason"], same_ball_continuity=False)
        self._goal_cache[cache_key] = result
        return result

    def bind_video_path(self, video_path: str):
        self.video_path = str(video_path or "")
        return self


def build_shadow_providers(api_key: str | None, session_prefix: str, video_path: str | None = None) -> ShadowVisionProviders:
    bundle = ShadowVisionProviders(api_key, session_prefix)
    if video_path:
        bundle.bind_video_path(video_path)
    return bundle
