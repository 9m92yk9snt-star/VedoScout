"""FIX10A Step 4 — contact-role and possession-continuity authority.

A verified physical contact is not automatically a ball release.  This module
adds a bounded, fail-closed role to touch evidence before strike extraction.
It consumes only FIX10A physical evidence already produced by A4/Step-3/A5;
no semantic event story, jersey number, fixture expectation or canonical event
is accepted as input.
"""
from __future__ import annotations

import math
from copy import deepcopy

import ball_contact_engine as bce
import short_occlusion_contact_recovery as recovery

VERSION = 1
ROLE_RELEASE = "RELEASE"
ROLE_RECEIVE_CONTROL = "RECEIVE_CONTROL"
ROLE_UNRESOLVED = "UNRESOLVED"

# A4 judges possession immediately around a contact. A real pass can remain
# inside that radius for the first adjacent sample and only become physically
# unambiguous a few frames later. Review a short, bounded tail without
# weakening A4's detector/contact gates. The strong-distance gate is stricter
# than ordinary possession: the ball must clear the possession radius by two
# existing ambiguity margins on multiple measured frames.
DELAYED_SEPARATION_WINDOW_MS = 420
DELAYED_CONTACT_CLUSTER_MS = 160
DELAYED_RECONTACT_GUARD_MS = 500
DELAYED_MIN_MEASURED = 4
DELAYED_MIN_STRONG = 3
DELAYED_STRONG_DISTANCE_H = bce.POSSESSION_MAX_H + 2.0 * bce.POSSESSION_MARGIN_H
DELAYED_MIN_GAIN_H = 2.0 * bce.POSSESSION_MARGIN_H
DELAYED_MONOTONIC_TOL_H = bce.POSSESSION_MARGIN_H / 2.0


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


def _valid_box(box) -> bool:
    return (
        isinstance(box, dict)
        and all(_num(box.get(k)) for k in ("x", "y", "w", "h"))
        and float(box["w"]) > 0.0
        and float(box["h"]) > 0.0
    )


def _player_by_id(frame: dict, track_id: str):
    for player in frame.get("players") or []:
        if not isinstance(player, dict):
            continue
        if (
            player.get("local_track_id") == track_id
            and player.get("association_state") == "VERIFIED_LOCAL"
            and _valid_box(player.get("box"))
        ):
            return player
    return None


def _target_compatible(frame: dict, track_id: str) -> bool:
    """Keep delayed evidence on the same selected-player hypothesis."""
    target = frame.get("global_target") if isinstance(frame.get("global_target"), dict) else {}
    status = str(target.get("status") or "")
    if status == "VERIFIED":
        return target.get("local_track_id") == track_id
    if status == "HYPOTHESES":
        return track_id in (target.get("candidate_local_track_ids") or [])
    return False


def _trajectory_rows(ball_trajectory):
    if isinstance(ball_trajectory, list):
        return [row for row in ball_trajectory if isinstance(row, dict)]
    if isinstance(ball_trajectory, dict):
        return [
            row for row in (ball_trajectory.get("points") or ball_trajectory.get("trajectory") or [])
            if isinstance(row, dict)
        ]
    return []


def _touch_end_ms(touch: dict) -> int:
    value = touch.get("end_ms") if _num(touch.get("end_ms")) else touch.get("media_ms")
    return int(round(float(value or 0)))


def _contact_cluster_end(touch: dict, touches) -> int:
    """Extend across immediately adjacent same-actor occlusion fragments."""
    actor = touch.get("player_track_id")
    scene = touch.get("scene_id")
    start = int(round(float(touch.get("media_ms") or 0)))
    end = _touch_end_ms(touch)
    rows = sorted(
        [
            row for row in (touches or [])
            if isinstance(row, dict)
            and row.get("player_track_id") == actor
            and row.get("scene_id") == scene
            and _num(row.get("media_ms"))
            and int(round(float(row["media_ms"]))) >= start
        ],
        key=lambda row: int(round(float(row["media_ms"]))),
    )
    for row in rows:
        row_start = int(round(float(row["media_ms"])))
        if row_start > end + DELAYED_CONTACT_CLUSTER_MS:
            break
        end = max(end, _touch_end_ms(row))
    return end


def _has_quick_recontact(touch: dict, touches, cluster_end_ms: int) -> bool:
    actor = touch.get("player_track_id")
    scene = touch.get("scene_id")
    for row in touches or []:
        if not isinstance(row, dict) or row is touch:
            continue
        if row.get("player_track_id") != actor or row.get("scene_id") != scene:
            continue
        if not _num(row.get("media_ms")):
            continue
        row_ms = int(round(float(row["media_ms"])))
        if cluster_end_ms < row_ms <= cluster_end_ms + DELAYED_RECONTACT_GUARD_MS:
            return True
    return False


def _delayed_separation_role(touch: dict, touches, dense_frames, ball_trajectory):
    """Prove a selected-player release from a short measured post-contact tail.

    This is deliberately target-only: it closes a timing blind spot for the
    user-selected player's action without multiplying non-target strike/model
    candidates. Raw support proposals and predicted ball rows are excluded.
    """
    if not (
        touch.get("global_target_id") == "GLOBAL_TARGET"
        and isinstance(touch.get("global_target_resolution"), dict)
        and touch["global_target_resolution"].get("status") == "VERIFIED"
        and float(touch.get("trajectory_change") or 0.0) >= float(bce.TRAJECTORY_SIGNAL_MIN)
    ):
        return None
    geometry = touch.get("contact_geometry") if isinstance(touch.get("contact_geometry"), dict) else {}
    base_distance = geometry.get("distance_h")
    if not _num(base_distance) or float(base_distance) > float(bce.POSSESSION_MAX_H):
        return None

    actor = touch.get("player_track_id")
    scene = touch.get("scene_id")
    cluster_end = _contact_cluster_end(touch, touches)
    if _has_quick_recontact(touch, touches, cluster_end):
        return None

    frame_by_ms = {
        int(round(float(frame["media_ms"]))): frame
        for frame in (dense_frames or [])
        if isinstance(frame, dict) and _num(frame.get("media_ms"))
    }
    samples = []
    for row in _trajectory_rows(ball_trajectory):
        if not _num(row.get("media_ms")):
            continue
        media_ms = int(round(float(row["media_ms"])))
        if media_ms <= cluster_end or media_ms > cluster_end + DELAYED_SEPARATION_WINDOW_MS:
            continue
        if (
            row.get("state") != "MEASURED"
            or row.get("proof_eligible") is not True
            or row.get("scene_id", scene) != scene
            or not _valid_box(row.get("box"))
        ):
            continue
        frame = frame_by_ms.get(media_ms)
        if not isinstance(frame, dict) or frame.get("scene_id") != scene:
            continue
        if frame.get("cut_barrier") is True or frame.get("used_fallback") is True:
            continue
        player = _player_by_id(frame, actor)
        if player is None or not _target_compatible(frame, actor):
            continue
        pbox, bbox = player["box"], row["box"]
        foot_x = float(pbox["x"]) + float(pbox["w"]) / 2.0
        foot_y = float(pbox["y"]) + float(pbox["h"])
        ball_x = float(bbox["x"]) + float(bbox["w"]) / 2.0
        ball_y = float(bbox["y"]) + float(bbox["h"]) / 2.0
        distance_h = math.hypot(ball_x - foot_x, ball_y - foot_y) / float(pbox["h"])
        samples.append((media_ms, distance_h))

    if len(samples) < DELAYED_MIN_MEASURED:
        return None
    strong = [sample for sample in samples if sample[1] >= DELAYED_STRONG_DISTANCE_H]
    if len(strong) < DELAYED_MIN_STRONG:
        return None
    max_distance = max(distance for _ms, distance in samples)
    if max_distance - float(base_distance) < DELAYED_MIN_GAIN_H:
        return None
    reversals = sum(
        later + DELAYED_MONOTONIC_TOL_H < earlier
        for (_a_ms, earlier), (_b_ms, later) in zip(samples, samples[1:])
    )
    if reversals > 1:
        return None

    evidence = {
        "actor_track_id": actor,
        "cluster_end_ms": cluster_end,
        "first_measured_ms": samples[0][0],
        "last_measured_ms": samples[-1][0],
        "measured_samples": len(samples),
        "strong_separation_samples": len(strong),
        "contact_distance_h": round(float(base_distance), 4),
        "max_distance_h": round(max_distance, 4),
        "separation_gain_h": round(max_distance - float(base_distance), 4),
        "strong_distance_gate_h": round(float(DELAYED_STRONG_DISTANCE_H), 4),
        "reversals": reversals,
    }
    return _verified_role(ROLE_RELEASE, "A4_DELAYED_MEASURED_SEPARATION", evidence)


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
    if mode == "EXACT_TARGET_BODY_FLOW_RELEASE":
        recovery_evidence = (
            row.get("recovery_evidence")
            if isinstance(row.get("recovery_evidence"), dict) else {}
        )
        possession = (
            recovery_evidence.get("release_possession_evidence")
            if isinstance(recovery_evidence.get("release_possession_evidence"), dict) else {}
        )
        trajectory = (
            recovery_evidence.get("release_trajectory_evidence")
            if isinstance(recovery_evidence.get("release_trajectory_evidence"), dict) else {}
        )
        evidence = {
            "recovery_mode": mode,
            "release_evidence_ms": recovery_evidence.get("release_evidence_ms"),
            "possession_kind": possession.get("kind"),
            "possession_score": possession.get("score"),
            "trajectory_score": trajectory.get("score"),
            "body_flow_status": recovery_evidence.get("body_flow_status"),
            "ball_flow_status": recovery_evidence.get("ball_flow_status"),
            "all_ball_rows_measured_proof_eligible": recovery_evidence.get(
                "all_ball_rows_measured_proof_eligible"
            ),
        }
        if (
            possession.get("kind") == "RELEASE"
            and _num(possession.get("score"))
            and float(possession["score"]) >= float(bce.POSSESSION_SIGNAL_MIN)
            and _num(trajectory.get("score"))
            and float(trajectory["score"]) >= float(bce.TRAJECTORY_SIGNAL_MIN)
            and recovery_evidence.get("body_flow_status") == "VERIFIED_PATH"
            and recovery_evidence.get("ball_flow_status") == "VERIFIED_PATH"
            and recovery_evidence.get("all_ball_rows_measured_proof_eligible") is True
        ):
            return _verified_role(ROLE_RELEASE, "EXACT_TARGET_BODY_FLOW_RELEASE", evidence)
        return _unresolved("EXACT_TARGET_BODY_FLOW_RELEASE_INCOMPLETE", evidence)
    if mode not in {
        "PRE_ANCHORED_SUPPORT_FLOW",
        "POST_GAP_MEASURED_REACQUISITION",
        "EXACT_TARGET_SUPPORT_PATH",
    }:
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


def apply_contact_roles(touch_graph: dict | None, contact_result: dict | None, *,
                        dense_frames=None, ball_trajectory=None) -> dict:
    """Attach fail-closed contact roles to a copied Touch Graph."""
    graph = deepcopy(touch_graph) if isinstance(touch_graph, dict) else {"touches": []}
    source_by_id = _source_contacts(contact_result)
    graph_touches = graph.get("touches") or []
    reviewed = verified_release = verified_control = unresolved = delayed_release = 0
    for touch in graph_touches:
        if not isinstance(touch, dict):
            continue
        role = resolve_touch_role(touch, source_by_id)
        if role is None:
            continue
        if role.get("status") == "VERIFIED" and role.get("role") == ROLE_RECEIVE_CONTROL:
            delayed = _delayed_separation_role(
                touch, graph_touches, dense_frames or [], ball_trajectory or []
            )
            if delayed is not None:
                role = delayed
                delayed_release += 1
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
            "delayed_separation_releases": delayed_release,
        })
    graph["contact_role_version"] = VERSION
    return graph
