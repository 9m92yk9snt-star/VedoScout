"""FIX10A8 — bounded event-trace / black-box recorder.

The trace captures physical evidence for one dense football window so a later
review can identify exactly where truth changed.  Raw image arrays are never
persisted here.  The primary multimodal observation may be stored only as a
comparison record; it is not an input to physical reconstruction.
"""
from __future__ import annotations

import gzip
import hashlib
import json
from copy import deepcopy

VERSION = 1
MAX_FRAMES = 720
MAX_PLAYERS_PER_FRAME = 32
MAX_BALL_CANDIDATES = 6
MAX_CONTACT_ROWS = 240
MAX_PRIMARY_ACTIONS = 80


def _num(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _strip_images(value):
    """Recursively remove raw image-like fields from persisted trace payloads."""
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            name = str(key).lower()
            if name in {"frame_bgr", "frame", "image", "image_bgr", "crop_bgr", "pixels"}:
                continue
            # Numpy-like arrays must never leak through under an unexpected key.
            if hasattr(item, "shape") and hasattr(item, "dtype"):
                continue
            out[key] = _strip_images(item)
        return out
    if isinstance(value, (list, tuple)):
        return [_strip_images(x) for x in value]
    return deepcopy(value)


def _compact_dense_frames(frames):
    rows = []
    for frame in frames or []:
        if not isinstance(frame, dict) or not _num(frame.get("media_ms")):
            continue
        players = []
        for p in (frame.get("players") or [])[:MAX_PLAYERS_PER_FRAME]:
            if not isinstance(p, dict):
                continue
            players.append(_strip_images(p))
        balls = [
            _strip_images(x) for x in (frame.get("ball_candidates") or [])[:MAX_BALL_CANDIDATES]
            if isinstance(x, dict)
        ]
        rows.append({
            "media_ms": int(round(float(frame["media_ms"]))),
            "scene_id": frame.get("scene_id"),
            "cut_barrier": bool(frame.get("cut_barrier") or frame.get("cut")),
            "time_authority": frame.get("time_authority"),
            "used_fallback": bool(frame.get("used_fallback")),
            "camera_state": frame.get("camera_state"),
            "global_target": _strip_images(frame.get("global_target") or {}),
            "players": players,
            "ball_candidates": balls,
        })
        if len(rows) >= MAX_FRAMES:
            break
    return rows


def _primary_comparison(sequence_analysis, window):
    """Extract model-authored rows only for later comparison/audit."""
    if not isinstance(sequence_analysis, dict) or not isinstance(window, dict):
        return {"role": "COMPARISON_ONLY", "sequences": []}
    wanted = set(x for x in (window.get("source_sequence_ids") or []) if isinstance(x, str))
    scene = window.get("scene_id")
    start, end = int(window.get("start_ms") or 0), int(window.get("end_ms") or 0)
    seqs = []
    action_count = 0
    for seq in sequence_analysis.get("sequences") or []:
        if not isinstance(seq, dict):
            continue
        if wanted and seq.get("sequence_id") not in wanted:
            continue
        if scene is not None and seq.get("scene_id") != scene:
            continue
        actions = []
        for action in seq.get("actions") or []:
            if not isinstance(action, dict) or action_count >= MAX_PRIMARY_ACTIONS:
                continue
            a0 = int(action.get("start_ms") or 0)
            a1 = int(action.get("end_ms") or a0)
            chain = action.get("causal_chain") if isinstance(action.get("causal_chain"), dict) else {}
            later = [chain.get(k) for k in ("receiver_ms", "teammate_shot_ms", "goal_outcome_ms")]
            later = [int(x) for x in later if _num(x)]
            physical_end = max([a1, *later]) if later else a1
            if physical_end < start or a0 > end:
                continue
            actions.append(_strip_images(action))
            action_count += 1
        if actions:
            seqs.append({
                "sequence_id": seq.get("sequence_id"),
                "scene_id": seq.get("scene_id"),
                "summary": str(seq.get("summary") or "")[:500],
                "actions": actions,
            })
    return {"role": "COMPARISON_ONLY", "sequences": seqs}


def build_event_trace(*, trace_id: str, source_video: dict | None, window: dict,
                      dense_frames, ball_trajectory, contact_result: dict | None,
                      touch_graph: dict | None, jersey_consensus: dict | None = None,
                      strike_evidence=None, outcome_evidence=None,
                      sequence_analysis: dict | None = None,
                      contradictions=None, unresolved_reasons=None) -> dict:
    """Build one persistence-safe physical trace for a critical window."""
    contacts = contact_result if isinstance(contact_result, dict) else {}
    graph = touch_graph if isinstance(touch_graph, dict) else {}
    jerseys = jersey_consensus if isinstance(jersey_consensus, dict) else {}
    trajectory = [
        _strip_images(x) for x in (ball_trajectory or [])[:MAX_FRAMES]
        if isinstance(x, dict)
    ]
    return {
        "version": VERSION,
        "trace_id": str(trace_id)[:120],
        "source_video": _strip_images(source_video or {}),
        "window": _strip_images(window),
        "decoded_frames": _compact_dense_frames(dense_frames),
        "ball_trajectory": trajectory,
        "contacts": {
            "accepted": [_strip_images(x) for x in (contacts.get("accepted") or [])[:MAX_CONTACT_ROWS]],
            "unresolved": [_strip_images(x) for x in (contacts.get("unresolved") or [])[:MAX_CONTACT_ROWS]],
            "rejected": [_strip_images(x) for x in (contacts.get("rejected") or [])[:MAX_CONTACT_ROWS]],
            "metrics": _strip_images(contacts.get("metrics") or {}),
        },
        "touch_graph": _strip_images(graph),
        "jersey_consensus": _strip_images(jerseys.get("consensus_by_track") or jerseys),
        "strike_evidence": [_strip_images(x) for x in (strike_evidence or [])],
        "outcome_evidence": [_strip_images(x) for x in (outcome_evidence or [])],
        "primary_observation": _primary_comparison(sequence_analysis, window),
        "contradictions": list(dict.fromkeys(
            str(x)[:240] for x in (contradictions or []) if str(x).strip()
        )),
        "unresolved_reasons": list(dict.fromkeys(
            str(x)[:240] for x in (unresolved_reasons or []) if str(x).strip()
        )),
    }


def compact_trace_summary(trace: dict | None) -> dict:
    """Mongo-safe summary; dense evidence remains in the external trace object."""
    row = trace if isinstance(trace, dict) else {}
    contacts = row.get("contacts") if isinstance(row.get("contacts"), dict) else {}
    graph = row.get("touch_graph") if isinstance(row.get("touch_graph"), dict) else {}
    jerseys = row.get("jersey_consensus") if isinstance(row.get("jersey_consensus"), dict) else {}
    outcomes = row.get("outcome_evidence") or []
    return {
        "version": VERSION,
        "trace_id": row.get("trace_id"),
        "window": _strip_images(row.get("window") or {}),
        "frames": len(row.get("decoded_frames") or []),
        "ball_rows": len(row.get("ball_trajectory") or []),
        "accepted_contacts": len(contacts.get("accepted") or []),
        "unresolved_contacts": len(contacts.get("unresolved") or []),
        "touches": len(graph.get("touches") or []),
        "verified_touches": sum(
            isinstance(t, dict) and t.get("status") == "VERIFIED"
            for t in (graph.get("touches") or [])
        ),
        "jersey_tracks": len(jerseys),
        "physical_outcomes": [
            x.get("physical_outcome") for x in outcomes
            if isinstance(x, dict) and x.get("physical_outcome")
        ][:20],
        "contradictions": list(row.get("contradictions") or [])[:20],
        "unresolved_reasons": list(row.get("unresolved_reasons") or [])[:20],
    }


def _canonical_json_bytes(payload) -> bytes:
    clean = _strip_images(payload)
    return json.dumps(
        clean,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def encode_trace_gzip(trace: dict) -> bytes:
    """Deterministic gzip representation for R2/local artifact persistence."""
    return gzip.compress(_canonical_json_bytes(trace), compresslevel=9, mtime=0)


def decode_trace_gzip(data: bytes) -> dict:
    return json.loads(gzip.decompress(bytes(data)).decode("utf-8"))


def trace_sha256(trace: dict) -> str:
    return hashlib.sha256(_canonical_json_bytes(trace)).hexdigest()
