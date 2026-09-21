"""FIX10A fail-closed proof gate for A7 ball-dependent physical outcomes.

A7 historically treated every ``state == MEASURED`` trajectory row with actual
media PTS as eligible whole-ball geometry.  FIX10A pixel recovery introduces a
second measurement source whose rows may be useful for search/continuity before
they are independently certified for proof.  This gate prevents an uncertified
measurement from becoming goal-plane truth.

The module can only certify or DOWNGRADE an already-produced physical crossing.
It never creates contacts, touches, canonical goals, assists, scorer identity or
stats.  A second proof lane accepts only a machine-checked independent
multi-frame whole-ball transition when ordinary detector proof is unavailable.
"""
from __future__ import annotations

from copy import deepcopy

VERSION = 1
BALL_ROW_NEAR_MS = 80


def _num(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _valid_visual_box(box):
    if not isinstance(box, dict):
        return False
    try:
        x, y, w, h = (float(box[k]) for k in ("x", "y", "w", "h"))
    except (KeyError, TypeError, ValueError):
        return False
    return -0.1 <= x <= 1.1 and -0.1 <= y <= 1.1 and 0 < w <= 1.2 and 0 < h <= 1.2


def _proof_row_at(ball_trajectory, media_ms):
    rows = [
        row for row in (ball_trajectory or [])
        if isinstance(row, dict)
        and row.get("state") == "MEASURED"
        and _num(row.get("media_ms"))
        and isinstance(row.get("box"), dict)
        and row.get("proof_eligible") is True
        and row.get("time_authority") == "ACTUAL_MEDIA_PTS"
        and row.get("used_fallback") is not True
    ]
    if not rows or not _num(media_ms):
        return None
    best = min(rows, key=lambda row: abs(int(row["media_ms"]) - int(media_ms)))
    return best if abs(int(best["media_ms"]) - int(media_ms)) <= BALL_ROW_NEAR_MS else None


def _downgrade(outcome: dict, reason: str, details=None) -> dict:
    row = deepcopy(outcome) if isinstance(outcome, dict) else {}
    crossing = deepcopy(row.get("goal_plane_crossing")) if isinstance(row.get("goal_plane_crossing"), dict) else {}
    crossing["pre_proof_gate_status"] = crossing.get("status")
    crossing["pre_proof_gate_reason"] = crossing.get("reason")
    crossing["status"] = "UNRESOLVED"
    crossing["crossing_ms"] = None
    crossing["reason"] = reason
    crossing["proof_gate"] = {"status": "UNRESOLVED", "details": details or {}}
    row["goal_plane_crossing"] = crossing
    intervention = row.get("intervention") if isinstance(row.get("intervention"), dict) else {}
    row["physical_outcome"] = (
        "PLAYER_INTERVENTION" if intervention.get("status") == "VERIFIED" else "UNRESOLVED"
    )
    row["ball_proof_gate"] = {"status": "UNRESOLVED", "reason": reason, "details": details or {}}
    row["canonical_event_type"] = None
    return row


def apply_ball_proof_gate(outcome: dict, ball_trajectory) -> dict:
    """Require proof-eligible measured ball rows for an A7 crossing segment.

    The whole-ball engine supplies ``from_ms`` and ``to_ms`` in its physical
    crossing evidence.  Both sides must map to independently proof-eligible
    measured rows.  This is deliberately stricter than accepting a generic
    ``MEASURED`` state.
    """
    row = deepcopy(outcome) if isinstance(outcome, dict) else {}
    crossing = row.get("goal_plane_crossing") if isinstance(row.get("goal_plane_crossing"), dict) else {}
    if crossing.get("status") != "VERIFIED":
        return row
    evidence = crossing.get("evidence") or []
    segment = next((item for item in evidence if isinstance(item, dict)), None)
    if not segment or not (_num(segment.get("from_ms")) and _num(segment.get("to_ms"))):
        return _downgrade(row, "BALL_PROOF_SEGMENT_EVIDENCE_MISSING")
    from_ms, to_ms = int(segment["from_ms"]), int(segment["to_ms"])

    if str(segment.get("proof_lane") or "") == "OCCLUDED_TRAJECTORY_GOAL":
        anchors = [int(ms) for ms in (segment.get("anchor_media_ms") or []) if _num(ms)]
        detector_ms = [int(ms) for ms in (segment.get("detector_anchor_media_ms") or []) if _num(ms)]
        provider_ms = [int(ms) for ms in (segment.get("provider_anchor_media_ms") or []) if _num(ms)]
        detector_rows = [_proof_row_at(ball_trajectory, ms) for ms in detector_ms]
        detector_proof_times = {
            int(r["media_ms"]) for r in detector_rows
            if isinstance(r, dict) and _num(r.get("media_ms"))
        }
        occ = crossing.get("occlusion_audit") if isinstance(crossing.get("occlusion_audit"), dict) else {}
        reaction = crossing.get("reaction_support") if isinstance(crossing.get("reaction_support"), dict) else {}
        visual = crossing.get("visual_audit") if isinstance(crossing.get("visual_audit"), dict) else {}
        direction_gate = row.get("direction_gate") if isinstance(row.get("direction_gate"), dict) else {}
        crossing_ms = segment.get("crossing_ms")
        mode = str(segment.get("anchor_mode") or "")

        provider_rows = []
        structured = [r for r in (visual.get("structured_evidence") or []) if isinstance(r, dict)]
        for ms in provider_ms:
            match = next((
                r for r in structured
                if _num(r.get("media_ms")) and int(r["media_ms"]) == ms
                and r.get("ball_visible") is True
                and str(r.get("confidence") or "low").lower() in {"high", "medium"}
                and str(r.get("relation") or "UNRESOLVED").upper() in {"FIELD_SIDE", "ON_OR_STRADDLING_LINE"}
                and _valid_visual_box(r.get("ball_box"))
            ), None)
            provider_rows.append(match)
        provider_visual_times = {
            int(r["media_ms"]) for r in provider_rows
            if isinstance(r, dict) and _num(r.get("media_ms"))
        }

        link = segment.get("detector_visual_link") if isinstance(segment.get("detector_visual_link"), dict) else None
        detector_only_ok = bool(
            mode == "DETECTOR_ONLY"
            and len(detector_ms) >= 3
            and len(detector_proof_times) >= 3
            and all(isinstance(r, dict) for r in detector_rows)
            and not provider_ms
        )
        hybrid_ok = bool(
            mode == "HYBRID_DETECTOR_PROVIDER"
            and len(detector_ms) >= 1
            and len(detector_proof_times) >= 1
            and all(isinstance(r, dict) for r in detector_rows)
            and len(provider_ms) >= 2
            and len(provider_visual_times) >= 2
            and all(isinstance(r, dict) for r in provider_rows)
            and occ.get("same_ball_pre_occlusion") is True
            and isinstance(link, dict)
            and _num(link.get("center_distance"))
            and float(link.get("center_distance")) <= 0.075
        )
        valid = bool(
            len(anchors) >= 3
            and (detector_only_ok or hybrid_ok)
            and segment.get("same_ball_pre_occlusion") is True
            and str(occ.get("status") or "").upper() == "VERIFIED_OCCLUSION"
            and str(occ.get("confidence") or "low").lower() in {"high", "medium"}
            and str(reaction.get("status") or "").upper() == "VERIFIED"
            and crossing.get("direction_status") == "VERIFIED"
            and crossing.get("direction") == "FIELD_TO_GOAL"
            and direction_gate.get("status") == "VERIFIED"
            and _num(crossing_ms)
            and from_ms < int(crossing_ms) <= to_ms
            and _num(segment.get("trajectory_r2"))
            and float(segment.get("trajectory_r2")) >= 0.92
            and _num(segment.get("trajectory_residual"))
            and float(segment.get("trajectory_residual")) <= 0.018
            and _num(segment.get("projected_mouth_margin"))
            and _num(segment.get("required_mouth_margin"))
            and float(segment.get("projected_mouth_margin")) > float(segment.get("required_mouth_margin"))
        )
        details = {
            "from_ms": from_ms, "to_ms": to_ms,
            "crossing_ms": int(crossing_ms) if _num(crossing_ms) else None,
            "proof_lane": "OCCLUDED_TRAJECTORY_GOAL",
            "anchor_mode": mode,
            "anchor_media_ms": anchors,
            "detector_anchor_media_ms": detector_ms,
            "provider_anchor_media_ms": provider_ms,
            "detector_proof_count": len(detector_proof_times),
            "provider_visual_count": len(provider_visual_times),
            "detector_visual_link": deepcopy(link),
            "direction_verified": crossing.get("direction_status") == "VERIFIED",
            "occlusion_verified": str(occ.get("status") or "").upper() == "VERIFIED_OCCLUSION",
            "reaction_support_verified": str(reaction.get("status") or "").upper() == "VERIFIED",
            "reaction_is_support_only": segment.get("reaction_support_only") is True,
        }
        if not valid:
            return _downgrade(row, "OCCLUDED_GOAL_PHYSICAL_PROOF_INVALID", details)
        crossing = deepcopy(crossing)
        crossing["proof_gate"] = {"status": "VERIFIED", "details": details}
        row["goal_plane_crossing"] = crossing
        row["ball_proof_gate"] = {
            "status": "VERIFIED",
            "reason": "BOUNDED_OCCLUDED_GOAL_CROSSING_CERTIFIED_FROM_PROOF_ANCHORS",
            "details": details,
        }
        return row

    if str(segment.get("proof_lane") or "") == "STRUCTURED_VISUAL_WHOLE_BALL":
        audit = crossing.get("visual_audit") if isinstance(crossing.get("visual_audit"), dict) else {}
        crossing_ms = segment.get("crossing_ms")
        direction_gate = row.get("direction_gate") if isinstance(row.get("direction_gate"), dict) else {}
        valid = bool(
            segment.get("source") == "INDEPENDENT_MULTI_FRAME_GOAL_REVIEW"
            and segment.get("same_ball_continuity") is True
            and audit.get("proof_ready") is True
            and audit.get("same_ball_continuity") is True
            and str(audit.get("status") or "").upper() == "VERIFIED_CROSSING"
            and str(audit.get("confidence") or "").lower() == "high"
            and crossing.get("direction_status") == "VERIFIED"
            and crossing.get("direction") == "FIELD_TO_GOAL"
            and direction_gate.get("status") == "VERIFIED"
            and _num(crossing_ms)
            and from_ms < int(crossing_ms) <= to_ms
        )
        details = {
            "from_ms": from_ms,
            "to_ms": to_ms,
            "crossing_ms": int(crossing_ms) if _num(crossing_ms) else None,
            "proof_lane": "STRUCTURED_VISUAL_WHOLE_BALL",
            "same_ball_continuity": bool(segment.get("same_ball_continuity")),
            "direction_verified": crossing.get("direction_status") == "VERIFIED",
            "audit_proof_ready": audit.get("proof_ready") is True,
        }
        if not valid:
            return _downgrade(row, "STRUCTURED_VISUAL_WHOLE_BALL_PROOF_INVALID", details)
        crossing = deepcopy(crossing)
        crossing["proof_gate"] = {"status": "VERIFIED", "details": details}
        row["goal_plane_crossing"] = crossing
        row["ball_proof_gate"] = {
            "status": "VERIFIED",
            "reason": "STRUCTURED_VISUAL_WHOLE_BALL_CROSSING_PROOF",
            "details": details,
        }
        return row

    before = _proof_row_at(ball_trajectory, from_ms)
    after = _proof_row_at(ball_trajectory, to_ms)
    details = {
        "from_ms": from_ms,
        "to_ms": to_ms,
        "before_proof": before is not None,
        "after_proof": after is not None,
        "before_source": before.get("measurement_source") if isinstance(before, dict) else None,
        "after_source": after.get("measurement_source") if isinstance(after, dict) else None,
    }
    if before is None or after is None:
        return _downgrade(row, "WHOLE_BALL_CROSSING_USES_UNCERTIFIED_MEASUREMENT", details)
    crossing = deepcopy(crossing)
    crossing["proof_gate"] = {"status": "VERIFIED", "details": details}
    row["goal_plane_crossing"] = crossing
    row["ball_proof_gate"] = {
        "status": "VERIFIED",
        "reason": "CROSSING_BOUNDED_BY_PROOF_ELIGIBLE_BALL_MEASUREMENTS",
        "details": details,
    }
    return row
