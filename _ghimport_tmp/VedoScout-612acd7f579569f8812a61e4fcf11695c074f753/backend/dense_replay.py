"""FIX10A1 — true dense replay for critical football windows.

This module is evidence ingestion only.  It selects bounded, same-scene windows
from the existing FIX09B sequence plan/normalised observations and decodes every
available source frame in those windows using the canonical FIX03 media PTS
contract.  It never classifies events, resolves player identity, or changes the
existing B3/FIX09C authority.
"""
from __future__ import annotations

import hashlib
from copy import deepcopy

import cv2

import video_timebase

VERSION = 1
WINDOW_PAD_BEFORE_MS = 750
WINDOW_PAD_AFTER_MS = 1250
MERGE_GAP_MS = 250
MAX_DENSE_WINDOW_MS = 8000


def _num(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _int_ms(value):
    return int(round(float(value))) if _num(value) else None


def _stable_id(scene_id: str, start_ms: int, end_ms: int) -> str:
    raw = f"{scene_id}|{int(start_ms)}|{int(end_ms)}".encode("utf-8")
    return "dense_" + hashlib.sha1(raw).hexdigest()[:16]


def _scene_bounds(sequence_plan: dict | None) -> dict[str, tuple[int, int]]:
    """Infer hard scene bounds from already-clipped FIX09B windows."""
    plan = sequence_plan if isinstance(sequence_plan, dict) else {}
    bounds: dict[str, list[int]] = {}
    for key in ("analysis_windows", "refinement_windows"):
        for row in plan.get(key) or []:
            if not isinstance(row, dict):
                continue
            scene = str(row.get("scene_id") or "")
            start, end = _int_ms(row.get("start_ms")), _int_ms(row.get("end_ms"))
            if not scene or start is None or end is None:
                continue
            lo, hi = sorted((max(0, start), max(0, end)))
            if scene not in bounds:
                bounds[scene] = [lo, hi]
            else:
                bounds[scene][0] = min(bounds[scene][0], lo)
                bounds[scene][1] = max(bounds[scene][1], hi)
    return {scene: (row[0], row[1]) for scene, row in bounds.items()}


def _clip_to_scene(scene: str, start_ms: int, end_ms: int,
                   bounds: dict[str, tuple[int, int]],
                   fallback_start=None, fallback_end=None):
    lo, hi = sorted((max(0, int(start_ms)), max(0, int(end_ms))))
    if scene in bounds:
        slo, shi = bounds[scene]
        lo, hi = max(lo, slo), min(hi, shi)
    if _num(fallback_start):
        lo = max(lo, int(round(float(fallback_start))))
    if _num(fallback_end):
        hi = min(hi, int(round(float(fallback_end))))
    return (lo, hi) if hi >= lo else None


def _action_requires_dense_replay(action: dict) -> tuple[bool, list[str]]:
    reasons = []
    if _num(action.get("contact_ms")):
        reasons.append("ACTION_CONTACT")
    outcome = str(action.get("outcome") or "UNKNOWN").upper()
    if outcome != "UNKNOWN" or action.get("outcome_visible") is True:
        reasons.append("ACTION_OUTCOME")
    chain = action.get("causal_chain") if isinstance(action.get("causal_chain"), dict) else {}
    chain_keys = ("target_contact_ms", "receiver_ms", "teammate_shot_ms", "goal_outcome_ms")
    if any(_num(chain.get(k)) for k in chain_keys) or chain.get("continuous_visible_sequence") is True:
        reasons.append("CAUSAL_CHAIN")
    target_state = str(action.get("target_status") or "UNRESOLVED").upper()
    if target_state != "VERIFIED":
        reasons.append("IDENTITY_AMBIGUITY")
    contact_visibility = str(action.get("contact_visibility") or "UNKNOWN").upper()
    if contact_visibility in {"PARTIAL", "OCCLUDED", "UNKNOWN"}:
        reasons.append("CONTACT_AMBIGUITY")
    return bool(reasons), reasons


def _merge_seed_rows(rows: list[dict]) -> list[dict]:
    merged = []
    for row in sorted(rows, key=lambda r: (r["scene_id"], r["start_ms"], r["end_ms"])):
        if (merged and merged[-1]["scene_id"] == row["scene_id"]
                and row["start_ms"] <= merged[-1]["end_ms"] + MERGE_GAP_MS):
            cur = merged[-1]
            cur["start_ms"] = min(cur["start_ms"], row["start_ms"])
            cur["end_ms"] = max(cur["end_ms"], row["end_ms"])
            for key in ("reasons", "source_refinement_ids", "source_sequence_ids", "source_action_ids"):
                cur[key] = list(dict.fromkeys([*(cur.get(key) or []), *(row.get(key) or [])]))
        else:
            merged.append(deepcopy(row))
    return merged


def _split_long_row(row: dict) -> list[dict]:
    start, end = int(row["start_ms"]), int(row["end_ms"])
    if end - start <= MAX_DENSE_WINDOW_MS:
        out = deepcopy(row)
        out["dense_window_id"] = _stable_id(out["scene_id"], start, end)
        return [out]
    pieces = []
    cursor = start
    while cursor <= end:
        piece_end = min(end, cursor + MAX_DENSE_WINDOW_MS)
        piece = deepcopy(row)
        piece["start_ms"] = cursor
        piece["end_ms"] = piece_end
        piece["dense_window_id"] = _stable_id(piece["scene_id"], cursor, piece_end)
        pieces.append(piece)
        if piece_end >= end:
            break
        # Inclusive millisecond windows: +1 prevents duplicate boundary truth.
        cursor = piece_end + 1
    return pieces


def select_critical_windows(sequence_plan: dict | None,
                            sequence_analysis: dict | None) -> list[dict]:
    """Return merged/split same-scene dense replay windows.

    Existing refinement windows are always retained.  Normalised actions add a
    replay seed only when physical contact/outcome/causal-chain evidence or
    identity/contact ambiguity makes denser inspection useful.  Scene ids are
    hard boundaries; rows from different scenes are never merged.
    """
    plan = sequence_plan if isinstance(sequence_plan, dict) else {}
    analysis = sequence_analysis if isinstance(sequence_analysis, dict) else {}
    bounds = _scene_bounds(plan)
    seeds = []

    for row in plan.get("refinement_windows") or []:
        if not isinstance(row, dict):
            continue
        scene = str(row.get("scene_id") or "")
        start, end = _int_ms(row.get("start_ms")), _int_ms(row.get("end_ms"))
        if not scene or start is None or end is None:
            continue
        clipped = _clip_to_scene(scene, start, end, bounds)
        if clipped is None:
            continue
        seeds.append({
            "scene_id": scene,
            "start_ms": clipped[0],
            "end_ms": clipped[1],
            "reasons": list(dict.fromkeys(["FIX09B_REFINEMENT", *(row.get("reasons") or [])])),
            "source_refinement_ids": [row.get("refinement_id")] if row.get("refinement_id") else [],
            "source_sequence_ids": [x for x in (row.get("sequence_ids") or []) if isinstance(x, str)],
            "source_action_ids": [],
        })

    for seq in analysis.get("sequences") or []:
        if not isinstance(seq, dict):
            continue
        scene = str(seq.get("scene_id") or "")
        seq_start, seq_end = _int_ms(seq.get("start_ms")), _int_ms(seq.get("end_ms"))
        if not scene or seq_start is None or seq_end is None:
            continue
        for action in seq.get("actions") or []:
            if not isinstance(action, dict):
                continue
            needed, reasons = _action_requires_dense_replay(action)
            if not needed:
                continue
            action_start = _int_ms(action.get("start_ms"))
            action_end = _int_ms(action.get("end_ms"))
            if action_start is None or action_end is None:
                continue
            causal = action.get("causal_chain") if isinstance(action.get("causal_chain"), dict) else {}
            later_ms = [
                _int_ms(causal.get(k))
                for k in ("target_contact_ms", "receiver_ms", "teammate_shot_ms", "goal_outcome_ms")
            ]
            later_ms = [x for x in later_ms if x is not None]
            physical_end = max([action_end, *later_ms])
            clipped = _clip_to_scene(
                scene,
                action_start - WINDOW_PAD_BEFORE_MS,
                physical_end + WINDOW_PAD_AFTER_MS,
                bounds,
                fallback_start=seq_start,
                fallback_end=seq_end,
            )
            if clipped is None:
                continue
            seeds.append({
                "scene_id": scene,
                "start_ms": clipped[0],
                "end_ms": clipped[1],
                "reasons": reasons,
                "source_refinement_ids": [],
                "source_sequence_ids": [seq.get("sequence_id")] if seq.get("sequence_id") else [],
                "source_action_ids": [action.get("action_id")] if action.get("action_id") else [],
            })

    out = []
    for row in _merge_seed_rows(seeds):
        out.extend(_split_long_row(row))
    return out


def iter_dense_frames(video_path: str, start_ms: int, end_ms: int,
                      proc_max_width: int = 960):
    """Yield EVERY decoded source frame in [start_ms, end_ms].

    Temporal sampling is forbidden.  Spatial downscale is permitted for local
    CV work.  `used_fallback` and `time_authority` explicitly expose whether a
    backend failed to provide actual media PTS; fallback time is never labelled
    exact proof time.
    """
    start = max(0, int(start_ms))
    end = max(0, int(end_ms))
    if end < start:
        start, end = end, start
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        cap.release()
        return
    try:
        fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
        ok, t, used_fallback = video_timebase.seek_with_preroll(cap, start / 1000.0, fps)
        while ok:
            media_ms = int(round(float(t) * 1000.0))
            if media_ms > end:
                break
            if media_ms >= start:
                okr, frame = cap.retrieve()
                if okr and frame is not None:
                    source_h, source_w = frame.shape[:2]
                    out = frame
                    if proc_max_width and proc_max_width > 0 and source_w > proc_max_width:
                        scale = float(proc_max_width) / float(source_w)
                        out = cv2.resize(
                            frame,
                            (int(proc_max_width), max(2, int(round(source_h * scale)))),
                            interpolation=cv2.INTER_AREA,
                        )
                    h, w = out.shape[:2]
                    yield {
                        "media_ms": media_ms,
                        "used_fallback": bool(used_fallback),
                        "time_authority": (
                            "FRAME_INDEX_FPS_FALLBACK" if used_fallback else "ACTUAL_MEDIA_PTS"
                        ),
                        "width": int(w),
                        "height": int(h),
                        "source_width": int(source_w),
                        "source_height": int(source_h),
                        "frame_bgr": out,
                    }
            ok, t, used_fallback = video_timebase.grab_frame_time_seconds(cap, fps)
    finally:
        cap.release()


def compact_frame_meta(frame_row: dict | None) -> dict:
    """Remove image arrays before diagnostics/persistence."""
    row = frame_row if isinstance(frame_row, dict) else {}
    return {k: deepcopy(v) for k, v in row.items() if k != "frame_bgr"}
