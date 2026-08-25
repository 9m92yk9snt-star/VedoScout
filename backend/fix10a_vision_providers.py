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

import asyncio
import base64
import json
import math
import os
import tempfile
from pathlib import Path

import cv2

import identity_verify
import video_timebase
from emergentintegrations.llm.chat import LlmChat, UserMessage, ImageContent

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


def _valid_box(box) -> bool:
    if not isinstance(box, dict):
        return False
    try:
        x, y, w, h = (float(box[k]) for k in ("x", "y", "w", "h"))
    except (KeyError, TypeError, ValueError):
        return False
    return -0.05 <= x <= 1.05 and -0.05 <= y <= 1.05 and 0 < w <= 1.1 and 0 < h <= 1.1


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
        })
    usable = [v for v in cleaned if v["role"] in {"GOALKEEPER", "OUTFIELD"}]
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
        "agreeing_frames": agreeing,
        "margin": round(margin, 4),
        "votes": cleaned,
        "reason": "MULTI_FRAME_ROLE_CONSENSUS" if verified else "INSUFFICIENT_ROLE_CONSENSUS",
    }


async def read_goal_scene_evidence(api_key: str, session_id: str,
                                   frame_paths: list[str], media_ms: list[int]) -> dict:
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


class ShadowVisionProviders:
    """Stateful/cached sync callbacks used inside the FIX10A worker thread."""

    def __init__(self, api_key: str | None, session_prefix: str):
        self.api_key = str(api_key or "")
        self.session_prefix = str(session_prefix or "fix10a")
        self._goal_cache = {}

    def jersey_vote_provider(self, video_path: str, requests) -> dict:
        rows = [r for r in (requests or []) if isinstance(r, dict)][:MAX_JERSEY_REQUESTS]
        if not self.api_key or not rows:
            return {}
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
                crop = _crop(frame, box)
                path = root / f"jersey_{index:03d}.jpg"
                if crop is None or not _write_jpg(path, crop):
                    continue
                jobs.append(identity_verify.read_visible_jersey_number(
                    self.api_key,
                    f"{self.session_prefix}-jersey-{index}",
                    str(path),
                ))
                job_meta.append((track, actual_ms, row.get("request_id")))
            if not jobs:
                return {}
            try:
                results = asyncio.run(_bounded_gather(jobs, limit=3))
            except Exception:
                return {}
            for (track, actual_ms, request_id), result in zip(job_meta, results):
                vote = dict(result) if isinstance(result, dict) else {
                    "readable": False, "number": None, "confidence": "low", "reason": "reader_unavailable"
                }
                vote.update({"media_ms": int(actual_ms), "request_id": request_id})
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
            try:
                results = asyncio.run(_bounded_gather(jobs, limit=2))
            except Exception:
                return {}
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
        offsets = (-150, 0, 100, 200, 300, 400, 500, 650, 800, 1050, 1350, 1700, 2200, 2600)
        requested = [
            max(0, strike_ms + offset) for offset in offsets
            if strike_ms + offset <= end_ms + 100
        ][:MAX_GOAL_FRAMES]
        cache_key = (str(window.get("dense_window_id") if isinstance(window, dict) else ""), strike_ms, tuple(requested))
        if cache_key in self._goal_cache:
            return self._goal_cache[cache_key]
        frames = _read_frames(video_path, requested)
        if len(frames) < 2:
            self._goal_cache[cache_key] = None
            return None
        with tempfile.TemporaryDirectory(prefix="fix10a_goal_") as temp:
            root = Path(temp)
            paths, actual_times = [], []
            for index, requested_ms in enumerate(requested):
                got = frames.get(int(requested_ms))
                if not got:
                    continue
                actual_ms, frame = got
                path = root / f"goal_{index:03d}.jpg"
                if _write_jpg(path, frame):
                    paths.append(str(path)); actual_times.append(int(actual_ms))
            if len(paths) < 2:
                self._goal_cache[cache_key] = None
                return None
            try:
                review = asyncio.run(read_goal_scene_evidence(
                    self.api_key,
                    f"{self.session_prefix}-goal-{strike_ms}",
                    paths, actual_times,
                ))
            except Exception:
                review = {}
        rows = review.get("frames") or [] if isinstance(review, dict) else []
        if not rows:
            result = {
                "status": "UNRESOLVED",
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
