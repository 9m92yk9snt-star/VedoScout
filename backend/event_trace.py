"""FIX10A8 — bounded event-trace / black-box recorder.

The trace captures physical evidence for one dense football window so a later
review can identify exactly where truth changed. Raw image arrays are never
persisted here. The primary multimodal observation may be stored only as a
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
MAX_DIAGNOSTIC_OUTCOMES = 20
MAX_DIAGNOSTIC_JERSEYS = 24


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


def _median_positive_delta(rows) -> int:
    times = sorted({
        int(row["media_ms"]) for row in rows or []
        if isinstance(row, dict) and _num(row.get("media_ms"))
    })
    deltas = [b - a for a, b in zip(times, times[1:]) if b > a]
    if not deltas:
        return 0
    deltas.sort()
    return int(deltas[len(deltas) // 2])


def _longest_state_run_ms(rows, predicate, sample_interval_ms: int) -> int:
    ordered = sorted(
        (row for row in rows or [] if isinstance(row, dict) and _num(row.get("media_ms"))),
        key=lambda row: int(row["media_ms"]),
    )
    longest = 0
    start = last = None
    for row in ordered:
        ms = int(row["media_ms"])
        if predicate(row):
            if start is None:
                start = ms
            last = ms
            continue
        if start is not None and last is not None:
            longest = max(longest, last - start + max(0, int(sample_interval_ms)))
        start = last = None
    if start is not None and last is not None:
        longest = max(longest, last - start + max(0, int(sample_interval_ms)))
    return int(max(0, longest))


def _ball_diagnostics(decoded_frames, trajectory) -> dict:
    frames = [x for x in decoded_frames or [] if isinstance(x, dict)]
    rows = [
        x for x in trajectory or []
        if isinstance(x, dict) and _num(x.get("media_ms"))
    ]
    states = {}
    for row in rows:
        state = str(row.get("state") or "UNKNOWN").upper()
        states[state] = states.get(state, 0) + 1
    measured = int(states.get("MEASURED", 0))
    total = len(rows)
    candidate_frames = sum(bool(frame.get("ball_candidates")) for frame in frames)
    total_candidates = sum(len(frame.get("ball_candidates") or []) for frame in frames)
    sample_interval = _median_positive_delta(rows or frames)
    measured_times = sorted(
        int(row["media_ms"]) for row in rows
        if str(row.get("state") or "").upper() == "MEASURED"
    )
    return {
        "decoded_frames": len(frames),
        "frames_with_ball_candidates": int(candidate_frames),
        "ball_candidate_frame_ratio": round(candidate_frames / len(frames), 4) if frames else 0.0,
        "total_ball_candidates": int(total_candidates),
        "trajectory_rows": total,
        "trajectory_states": dict(sorted(states.items())),
        "measured_rows": measured,
        "measured_ratio": round(measured / total, 4) if total else 0.0,
        "median_sample_interval_ms": int(sample_interval),
        "longest_missing_run_ms": _longest_state_run_ms(
            rows,
            lambda row: str(row.get("state") or "").upper() == "MISSING",
            sample_interval,
        ),
        "longest_unmeasured_run_ms": _longest_state_run_ms(
            rows,
            lambda row: str(row.get("state") or "").upper() != "MEASURED",
            sample_interval,
        ),
        "first_measured_ms": measured_times[0] if measured_times else None,
        "last_measured_ms": measured_times[-1] if measured_times else None,
    }


def _contact_diagnostics(contacts: dict) -> dict:
    row = contacts if isinstance(contacts, dict) else {}
    return {
        "accepted": len(row.get("accepted") or []),
        "unresolved": len(row.get("unresolved") or []),
        "rejected": len(row.get("rejected") or []),
        "metrics": _strip_images(row.get("metrics") or {}),
    }


def _jersey_diagnostics(jerseys: dict) -> dict:
    source = jerseys if isinstance(jerseys, dict) else {}
    status_counts = {}
    tracks = []
    for track_id, row in sorted(source.items(), key=lambda item: str(item[0])):
        if not isinstance(row, dict):
            continue
        status = str(row.get("status") or "UNKNOWN").upper()
        status_counts[status] = status_counts.get(status, 0) + 1
        tracks.append({
            "track_id": str(track_id)[:80],
            "status": status,
            "number": row.get("number"),
            "leading_number": row.get("leading_number"),
            "top_posterior": row.get("top_posterior"),
            "margin": row.get("margin"),
            "agreeing_frames": row.get("agreeing_frames"),
            "reason": str(row.get("reason") or "")[:160],
        })
        if len(tracks) >= MAX_DIAGNOSTIC_JERSEYS:
            break
    return {
        "tracks_reviewed": len(source),
        "status_counts": dict(sorted(status_counts.items())),
        "tracks": tracks,
    }


def _outcome_diagnostics(outcomes) -> list[dict]:
    rows = []
    for outcome in outcomes or []:
        if not isinstance(outcome, dict):
            continue
        crossing = outcome.get("goal_plane_crossing") if isinstance(outcome.get("goal_plane_crossing"), dict) else {}
        geometry = outcome.get("goal_geometry_evidence") if isinstance(outcome.get("goal_geometry_evidence"), dict) else {}
        intervention = outcome.get("intervention") if isinstance(outcome.get("intervention"), dict) else {}
        role = outcome.get("intervention_role") if isinstance(outcome.get("intervention_role"), dict) else {}
        save = outcome.get("save_evidence") if isinstance(outcome.get("save_evidence"), dict) else {}
        direction = outcome.get("direction_gate") if isinstance(outcome.get("direction_gate"), dict) else {}
        visual = crossing.get("visual_audit") if isinstance(crossing.get("visual_audit"), dict) else {}
        rows.append({
            "strike_id": outcome.get("strike_id"),
            "media_ms": outcome.get("media_ms"),
            "physical_outcome": outcome.get("physical_outcome"),
            "terminal_ball_state": outcome.get("terminal_ball_state"),
            "trajectory_rows_reviewed": outcome.get("trajectory_rows_reviewed"),
            "goal_crossing": {
                "status": crossing.get("status"),
                "reason": crossing.get("reason"),
                "crossing_ms": crossing.get("crossing_ms"),
                "direction": crossing.get("direction"),
                "direction_status": crossing.get("direction_status"),
                "undirected_status": crossing.get("undirected_status"),
                "visual_audit_status": visual.get("status"),
            },
            "goal_geometry": {
                "status": geometry.get("status"),
                "source": geometry.get("source"),
                "line_frames": len(geometry.get("line_by_ms") or []),
                "field_side_status": geometry.get("field_side_status"),
                "field_side_frames": len(geometry.get("field_side_by_ms") or []),
                "field_side_reason": geometry.get("field_side_reason"),
            },
            "intervention": {
                "status": intervention.get("status"),
                "player_track_id": intervention.get("player_track_id"),
                "media_ms": intervention.get("media_ms"),
                "kind": intervention.get("kind"),
            },
            "role": {
                "status": role.get("status"),
                "role": role.get("role"),
                "reason": role.get("reason"),
            },
            "save": {
                "status": save.get("status"),
                "reason": save.get("reason"),
            },
            "direction_gate": {
                "status": direction.get("status"),
                "reason": direction.get("reason"),
            },
        })
        if len(rows) >= MAX_DIAGNOSTIC_OUTCOMES:
            break
    return rows


def _diagnostics(decoded_frames, trajectory, contacts, graph, jerseys, outcomes) -> dict:
    touch_rows = graph.get("touches") or [] if isinstance(graph, dict) else []
    return {
        "ball": _ball_diagnostics(decoded_frames, trajectory),
        "contacts": _contact_diagnostics(contacts),
        "touches": {
            "total": len(touch_rows),
            "verified": sum(
                isinstance(touch, dict) and touch.get("status") == "VERIFIED"
                for touch in touch_rows
            ),
        },
        "jersey": _jersey_diagnostics(jerseys),
        "outcomes": _outcome_diagnostics(outcomes),
    }


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
    decoded = _compact_dense_frames(dense_frames)
    trajectory = [
        _strip_images(x) for x in (ball_trajectory or [])[:MAX_FRAMES]
        if isinstance(x, dict)
    ]
    consensus = jerseys.get("consensus_by_track") or jerseys
    outcomes = [_strip_images(x) for x in (outcome_evidence or []) if isinstance(x, dict)]
    diagnostics = _diagnostics(
        decoded, trajectory, contacts, graph,
        consensus if isinstance(consensus, dict) else {}, outcomes,
    )
    return {
        "version": VERSION,
        "trace_id": str(trace_id)[:120],
        "source_video": _strip_images(source_video or {}),
        "window": _strip_images(window),
        "decoded_frames": decoded,
        "ball_trajectory": trajectory,
        "contacts": {
            "accepted": [_strip_images(x) for x in (contacts.get("accepted") or [])[:MAX_CONTACT_ROWS]],
            "unresolved": [_strip_images(x) for x in (contacts.get("unresolved") or [])[:MAX_CONTACT_ROWS]],
            "rejected": [_strip_images(x) for x in (contacts.get("rejected") or [])[:MAX_CONTACT_ROWS]],
            "metrics": _strip_images(contacts.get("metrics") or {}),
        },
        "touch_graph": _strip_images(graph),
        "jersey_consensus": _strip_images(consensus),
        "strike_evidence": [_strip_images(x) for x in (strike_evidence or [])],
        "outcome_evidence": outcomes,
        "diagnostics": diagnostics,
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
    diagnostics = row.get("diagnostics") if isinstance(row.get("diagnostics"), dict) else {}
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
        "diagnostics": _strip_images(diagnostics),
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
