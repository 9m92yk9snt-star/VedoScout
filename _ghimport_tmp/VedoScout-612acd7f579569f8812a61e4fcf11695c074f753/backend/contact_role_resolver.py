"""FIX10A Step 4 — contact-role and possession-continuity authority.

A verified physical contact is not automatically a ball release.  This module
adds a bounded, fail-closed role to touch evidence before strike extraction.
It consumes only FIX10A physical evidence already produced by A4/Step-3/A5;
no semantic event story, jersey number, fixture expectation or canonical event
is accepted as input.
"""
from __future__ import annotations

from copy import deepcopy

import ball_contact_engine as bce
import short_occlusion_contact_recovery as recovery

VERSION = 1
ROLE_RELEASE = "RELEASE"
ROLE_RECEIVE_CONTROL = "RECEIVE_CONTROL"
ROLE_UNRESOLVED = "UNRESOLVED"


def _num(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _verified_role(role: str, source: str, evidence: dict | None = None) -> dict:
    return {
        "version": VERSION,
        "status": "VERIFIED",
        "role": role,
        "source": source,
        "proof_eligible": True,
        "evidence": deepcopy(evidence) if isinstance(evidence, dict) else {},
    }


def _unresolved(reason: str, evidence: dict | None = None) -> dict:
    return {
        "version": VERSION,
        "status": "UNRESOLVED",
        "role": ROLE_UNRESOLVED,
        "source": "FIX10A_PHYSICAL_EVIDENCE",
        "proof_eligible": False,
        "reason": reason,
        "evidence": deepcopy(evidence) if isinstance(evidence, dict) else {},
    }


def _source_contacts(contact_result: dict | None) -> dict[str, dict]:
    result = contact_result if isinstance(contact_result, dict) else {}
    out = {}
    for row in result.get("contacts") or []:
        if not isinstance(row, dict):
            continue
        cid = row.get("contact_id")
        if isinstance(cid, str) and cid:
            out[cid] = row
    return out


def _ordinary_possession_role(touch: dict):
    kinds = {str(x) for x in (touch.get("possession_kinds") or [])}
    has_release = "RELEASE" in kinds
    has_control = bool(kinds.intersection({"RECEIVE", "CONTROL_TOUCH"}))
    if has_release and has_control:
        return _unresolved("CONFLICTING_A4_POSSESSION_TRANSITIONS", {"possession_kinds": sorted(kinds)})
    if has_release:
        return _verified_role(
            ROLE_RELEASE, "A4_POSSESSION_TRANSITION",
            {"possession_kinds": sorted(kinds), "possession_after": touch.get("possession_after")},
        )
    if has_control:
        return _verified_role(
            ROLE_RECEIVE_CONTROL, "A4_POSSESSION_TRANSITION",
            {"possession_kinds": sorted(kinds), "possession_after": touch.get("possession_after")},
        )
    return None


def _step3_role_from_contact(row: dict) -> dict:
    if not (
        isinstance(row, dict)
        and row.get("status") == "VERIFIED"
        and row.get("proof_eligible") is True
        and isinstance(row.get("player_track_id"), str)
    ):
        return _unresolved("STEP3_SOURCE_CONTACT_NOT_PROOF_ELIGIBLE")

    mode = str(row.get("recovery_mode") or "")
    if mode not in {"PRE_ANCHORED_SUPPORT_FLOW", "POST_GAP_MEASURED_REACQUISITION"}:
        return _unresolved("STEP3_RECOVERY_MODE_UNSUPPORTED", {"recovery_mode": mode or None})

    separation = row.get("separation_gain_h")
    geometry = row.get("contact_geometry") if isinstance(row.get("contact_geometry"), dict) else {}
    base_distance = geometry.get("distance_h")
    trajectory = row.get("trajectory_evidence") if isinstance(row.get("trajectory_evidence"), dict) else {}
    trajectory_score = trajectory.get("score")
    evidence = {
        "recovery_mode": mode,
        "separation_gain_h": separation,
        "contact_distance_h": base_distance,
        "trajectory_score": trajectory_score,
        "release_separation_margin_h": bce.POSSESSION_MARGIN_H,
        "possession_max_h": bce.POSSESSION_MAX_H,
        "step3_trajectory_signal_min": recovery.TRAJECTORY_SIGNAL_MIN,
    }
    if not (_num(separation) and _num(base_distance) and _num(trajectory_score)):
        return _unresolved("STEP3_ROLE_EVIDENCE_INCOMPLETE", evidence)

    separation = float(separation)
    base_distance = float(base_distance)
    trajectory_score = float(trajectory_score)
    after_distance = base_distance + separation
    evidence["after_distance_h"] = round(after_distance, 4)

    # A release needs both a strong physical consequence and material ball-to-
    # actor separation. The separation margin is the existing A4 possession
    # ambiguity margin; Step 4 does not lower or invent a weaker detector gate.
    if (
        separation >= float(bce.POSSESSION_MARGIN_H)
        and trajectory_score >= float(recovery.TRAJECTORY_SIGNAL_MIN)
    ):
        return _verified_role(ROLE_RELEASE, "STEP3_SEPARATION_CONTINUITY", evidence)

    # Conversely, a recovered contact can be control only while the measured
    # post-contact ball remains inside the existing A4 possession radius and
    # has not separated by the existing possession ambiguity margin.
    if (
        separation < float(bce.POSSESSION_MARGIN_H)
        and after_distance <= float(bce.POSSESSION_MAX_H)
    ):
        return _verified_role(ROLE_RECEIVE_CONTROL, "STEP3_POSSESSION_CONTINUITY", evidence)

    return _unresolved("STEP3_CONTACT_ROLE_NOT_PROVEN", evidence)


def resolve_touch_role(touch: dict | None, source_by_id: dict[str, dict] | None = None):
    """Return a role dict when physical evidence can review this touch.

    ``None`` means Step 4 has no role authority for that touch; legacy callers
    remain untouched. An explicit UNRESOLVED role means Step 4 reviewed the
    contact but could not prove a release and downstream strike extraction must
    fail closed rather than fall back to trajectory-change magnitude alone.
    """
    if not isinstance(touch, dict):
        return None
    if not (
        touch.get("status") == "VERIFIED"
        and touch.get("proof_eligible") is True
        and isinstance(touch.get("player_track_id"), str)
    ):
        return None

    ordinary = _ordinary_possession_role(touch)
    if ordinary is not None:
        return ordinary

    kinds = {str(x) for x in (touch.get("possession_kinds") or [])}
    if "SHORT_OCCLUSION_CONTACT_RECOVERY" not in kinds:
        return None

    source_by_id = source_by_id if isinstance(source_by_id, dict) else {}
    ids = [x for x in (touch.get("source_contact_ids") or []) if isinstance(x, str)]
    contacts = [source_by_id[x] for x in ids if x in source_by_id]
    if not contacts:
        return _unresolved("STEP3_SOURCE_CONTACT_MISSING", {"source_contact_ids": ids})

    actor = touch.get("player_track_id")
    if any(row.get("player_track_id") != actor for row in contacts):
        return _unresolved("STEP3_SOURCE_ACTOR_CONFLICT", {"source_contact_ids": ids})

    roles = [_step3_role_from_contact(row) for row in contacts]
    verified_roles = {
        row.get("role") for row in roles
        if isinstance(row, dict) and row.get("status") == "VERIFIED"
    }
    if len(verified_roles) == 1 and all(row.get("status") == "VERIFIED" for row in roles):
        role = next(iter(verified_roles))
        merged = {
            "source_contact_ids": ids,
            "source_roles": deepcopy(roles),
        }
        return _verified_role(role, "STEP3_AGGREGATED_CONTACT_ROLE", merged)
    return _unresolved(
        "STEP3_SOURCE_ROLE_CONFLICT_OR_UNRESOLVED",
        {"source_contact_ids": ids, "source_roles": deepcopy(roles)},
    )


def apply_contact_roles(touch_graph: dict | None, contact_result: dict | None) -> dict:
    """Attach fail-closed contact roles to a copied Touch Graph."""
    graph = deepcopy(touch_graph) if isinstance(touch_graph, dict) else {"touches": []}
    source_by_id = _source_contacts(contact_result)
    reviewed = verified_release = verified_control = unresolved = 0
    for touch in graph.get("touches") or []:
        if not isinstance(touch, dict):
            continue
        role = resolve_touch_role(touch, source_by_id)
        if role is None:
            continue
        touch["contact_role"] = role
        reviewed += 1
        if role.get("status") == "VERIFIED" and role.get("role") == ROLE_RELEASE:
            verified_release += 1
        elif role.get("status") == "VERIFIED" and role.get("role") == ROLE_RECEIVE_CONTROL:
            verified_control += 1
        else:
            unresolved += 1
    metrics = graph.setdefault("metrics", {})
    if isinstance(metrics, dict):
        metrics.update({
            "contact_roles_reviewed": reviewed,
            "verified_release_roles": verified_release,
            "verified_receive_control_roles": verified_control,
            "unresolved_contact_roles": unresolved,
        })
    graph["contact_role_version"] = VERSION
    return graph
