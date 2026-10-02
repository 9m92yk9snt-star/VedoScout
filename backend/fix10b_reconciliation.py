"""FIX10B — proof-gated reconciliation from FIX10A physical evidence.

FIX10A reconstructs physical truth but intentionally has no canonical authority.
FIX10B is the separate deterministic bridge that may strengthen/correct target
canonical events only when a complete physical proof chain exists.

Core invariant: GLOBAL_TARGET is the player being analysed, not the owner of
all events in the surrounding sequence.  A target release followed by a
verified teammate receive -> teammate strike -> verified goal-plane crossing is
an ASSIST for the target; the teammate owns the scoring strike.

This module performs no detection, model calls, database writes or report
mutation.  Missing/ambiguous evidence fails closed and leaves canonical truth
unchanged.
"""
from __future__ import annotations

import hashlib
import math
from copy import deepcopy

VERSION = 1
GLOBAL_TARGET_ID = "GLOBAL_TARGET"
DIRECT_RECEIVE_MAX_MS = 2400
DIRECT_SHOT_MAX_MS = 4200
DIRECT_GOAL_MAX_MS = 5200
CANONICAL_MATCH_MS = 900
TEAM_CONFIDENCE_MIN = 0.70
PASS_ACTIONS = {"PASS", "CROSS", "KEY_PASS"}

# A defender/keeper touch does not erase an assist when independent A7 evidence
# proves a deflection rather than control and the same active ball reaches a
# teammate's scoring release.  The endpoint/corridor bounds keep a stationary
# spare ball elsewhere in the frame out of that causal chain.
DEFLECTED_SHOT_MAX_MS = 4200
DEFLECTED_GOAL_MAX_MS = 5200
DEFLECTED_ENDPOINT_MAX_NORM = 0.16
DEFLECTED_LINEAGE_RADIUS_NORM = 0.10
LOCAL_TEAM_LOOKBACK_MS = 25
LOCAL_TEAM_LOOKAHEAD_MS = 90
LOCAL_TEAM_MIN_SAMPLES = 2
INTERVENTION_TEAM_AFTER_MIN_MS = 25
INTERVENTION_TEAM_AFTER_MAX_MS = 350
SCORING_CROSSING_MATCH_MS = 500

# FIX11 teammate local-track stitching. A local MOT id may split through a
# short occlusion; this must not silently erase a real assist. Stitching is
# conservative and never changes GLOBAL_TARGET identity.
TRACK_STITCH_STRICT_MS = 500
TRACK_STITCH_JERSEY_MS = 1400
TRACK_STITCH_CENTER_H = 0.95
TRACK_STITCH_STRICT_CENTER_H = 0.55
TRACK_STITCH_SCALE_MIN = 0.55
TRACK_STITCH_SCALE_MAX = 1.85


def _num(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _ms(row, key="media_ms"):
    return int(round(float(row[key]))) if isinstance(row, dict) and _num(row.get(key)) else None


def _verified_release(strike: dict) -> bool:
    return bool(
        isinstance(strike, dict)
        and strike.get("status") == "VERIFIED_PHYSICAL_RELEASE"
        and strike.get("proof_eligible") is True
        and isinstance(strike.get("player_track_id"), str)
        and _num(strike.get("media_ms"))
    )


def _verified_scoring_contact(strike: dict) -> bool:
    return bool(
        isinstance(strike, dict)
        and strike.get("status") in {
            "VERIFIED_PHYSICAL_RELEASE",
            "VERIFIED_PHYSICAL_SCORING_CONTACT",
        }
        and strike.get("proof_eligible") is True
        and isinstance(strike.get("player_track_id"), str)
        and _num(strike.get("media_ms"))
    )


def _verified_goal(outcome: dict) -> bool:
    if not isinstance(outcome, dict):
        return False
    crossing = outcome.get("goal_plane_crossing") if isinstance(outcome.get("goal_plane_crossing"), dict) else {}
    return bool(
        outcome.get("status") == "ok"
        and outcome.get("physical_outcome") == "GOAL_PLANE_CROSSING"
        and crossing.get("status") == "VERIFIED"
        and _num(crossing.get("crossing_ms"))
    )


def _verified_save(outcome: dict) -> bool:
    if not isinstance(outcome, dict):
        return False
    save = outcome.get("save_evidence") if isinstance(outcome.get("save_evidence"), dict) else {}
    intervention = outcome.get("intervention") if isinstance(outcome.get("intervention"), dict) else {}
    role = outcome.get("intervention_role") if isinstance(outcome.get("intervention_role"), dict) else {}
    crossing = outcome.get("goal_plane_crossing") if isinstance(outcome.get("goal_plane_crossing"), dict) else {}
    return bool(
        outcome.get("status") == "ok"
        and outcome.get("physical_outcome") == "GOALKEEPER_SAVE_EVIDENCE"
        and save.get("status") == "VERIFIED"
        and intervention.get("status") == "VERIFIED"
        and role.get("status") == "VERIFIED"
        and role.get("role") == "GOALKEEPER"
        and crossing.get("status") != "VERIFIED"
    )


def _verified_touch(touch: dict) -> bool:
    return bool(
        isinstance(touch, dict)
        and touch.get("status") == "VERIFIED"
        and touch.get("proof_eligible") is True
        and isinstance(touch.get("player_track_id"), str)
        and _num(touch.get("representative_ms") if _num(touch.get("representative_ms")) else touch.get("media_ms"))
    )


def _touch_ms(touch: dict):
    if not isinstance(touch, dict):
        return None
    value = touch.get("representative_ms") if _num(touch.get("representative_ms")) else touch.get("media_ms")
    return int(round(float(value))) if _num(value) else None


def _team_is_target(touch: dict) -> bool:
    rel = touch.get("team_relation") if isinstance(touch, dict) and isinstance(touch.get("team_relation"), dict) else {}
    conf = rel.get("confidence")
    return bool(
        rel.get("status") == "SUPPORTING"
        and rel.get("team") == "target_team"
        and _num(conf) and float(conf) >= TEAM_CONFIDENCE_MIN
    )


def _outcomes_by_strike(trace: dict) -> dict[str, dict]:
    out = {}
    for row in trace.get("outcome_evidence") or [] if isinstance(trace, dict) else []:
        if isinstance(row, dict) and isinstance(row.get("strike_id"), str):
            out[row["strike_id"]] = row
    return out


def _touches(trace: dict) -> list[dict]:
    graph = trace.get("touch_graph") if isinstance(trace, dict) and isinstance(trace.get("touch_graph"), dict) else {}
    rows = [deepcopy(x) for x in graph.get("touches") or [] if _verified_touch(x)]
    rows.sort(key=lambda x: (_touch_ms(x) or 0, str(x.get("touch_id") or "")))
    return rows


def _strikes(trace: dict) -> list[dict]:
    rows = [deepcopy(x) for x in trace.get("strike_evidence") or [] if _verified_scoring_contact(x)] if isinstance(trace, dict) else []
    rows.sort(key=lambda x: (_ms(x) or 0, str(x.get("strike_id") or "")))
    return rows


def _first_other_touch_after(touches, *, actor, scene, after_ms, max_ms):
    rows = [
        t for t in touches
        if t.get("scene_id") == scene
        and t.get("player_track_id") != actor
        and t.get("global_target_id") != GLOBAL_TARGET_ID
        and _touch_ms(t) is not None
        and int(after_ms) < int(_touch_ms(t)) <= int(after_ms) + int(max_ms)
    ]
    return min(rows, key=lambda t: int(_touch_ms(t)), default=None)


def _same_actor_recontact_before(touches, *, actor, scene, after_ms, before_ms) -> bool:
    """An early dribble release cannot be retrospectively called the assist pass."""
    return any(
        t.get("scene_id") == scene
        and (
            t.get("player_track_id") == actor
            or t.get("global_target_id") == GLOBAL_TARGET_ID
        )
        and _touch_ms(t) is not None
        and int(after_ms) < int(_touch_ms(t)) < int(before_ms)
        for t in touches
    )


def _intervening_other_touch(touches, *, allowed_actors, scene, start_ms, end_ms) -> bool:
    allowed = {x for x in (allowed_actors or []) if isinstance(x, str)}
    return any(
        t.get("scene_id") == scene
        and t.get("player_track_id") not in allowed
        and _touch_ms(t) is not None
        and int(start_ms) < int(_touch_ms(t)) < int(end_ms)
        for t in touches
    )


def _touch_by_id(touches, touch_id):
    if not isinstance(touch_id, str):
        return None
    return next((t for t in touches if t.get("touch_id") == touch_id), None)


def _verified_jersey_number(touch):
    row = touch.get("jersey_posterior") if isinstance(touch, dict) and isinstance(touch.get("jersey_posterior"), dict) else {}
    number = row.get("number")
    return str(number) if row.get("status") == "VERIFIED" and number is not None else None


def _valid_box(box):
    if not isinstance(box, dict):
        return False
    try:
        x, y, w, h = (float(box[k]) for k in ("x", "y", "w", "h"))
    except (KeyError, TypeError, ValueError):
        return False
    return -0.1 <= x <= 1.1 and -0.1 <= y <= 1.1 and 0 < w <= 1.2 and 0 < h <= 1.2


def _box_center(box):
    return (
        float(box["x"]) + float(box["w"]) / 2.0,
        float(box["y"]) + float(box["h"]) / 2.0,
    )


def _box_continuity(a, b, *, strict=False):
    if not (_valid_box(a) and _valid_box(b)):
        return False, None
    acx, acy = float(a["x"]) + float(a["w"]) / 2.0, float(a["y"]) + float(a["h"]) / 2.0
    bcx, bcy = float(b["x"]) + float(b["w"]) / 2.0, float(b["y"]) + float(b["h"]) / 2.0
    ah, bh = float(a["h"]), float(b["h"])
    ratio = ah / max(bh, 1e-9)
    distance_h = ((acx - bcx) ** 2 + (acy - bcy) ** 2) ** 0.5 / max(ah, bh, 1e-9)
    limit = TRACK_STITCH_STRICT_CENTER_H if strict else TRACK_STITCH_CENTER_H
    ok = TRACK_STITCH_SCALE_MIN <= ratio <= TRACK_STITCH_SCALE_MAX and distance_h <= limit
    return ok, {"center_distance_h": round(distance_h, 4), "height_ratio": round(ratio, 4)}


def _track_boxes(trace, track_id, scene, start_ms, end_ms):
    rows = []
    for frame in trace.get("decoded_frames") or [] if isinstance(trace, dict) else []:
        if not isinstance(frame, dict) or frame.get("scene_id") != scene or not _num(frame.get("media_ms")):
            continue
        ms = int(frame["media_ms"])
        if not int(start_ms) <= ms <= int(end_ms):
            continue
        for player in frame.get("players") or []:
            if isinstance(player, dict) and player.get("local_track_id") == track_id and _valid_box(player.get("box")):
                rows.append({"media_ms": ms, "box": deepcopy(player["box"])})
                break
    rows.sort(key=lambda x: x["media_ms"])
    return rows


def _time_local_team_evidence(trace, *, track_id, scene, media_ms,
                              reference_box, start_offset_ms, end_offset_ms,
                              min_samples=LOCAL_TEAM_MIN_SAMPLES):
    """Resolve team only on the concrete body surrounding one physical event.

    Whole-track voting can conflict when MOT ids collide.  This bounded view is
    tied to the event's actor box and therefore cannot inherit an earlier body.
    """
    if not (isinstance(track_id, str) and _valid_box(reference_box)):
        return {"status": "UNRESOLVED", "reason": "EVENT_ACTOR_GEOMETRY_MISSING"}
    rows = []
    for frame in trace.get("decoded_frames") or [] if isinstance(trace, dict) else []:
        if not isinstance(frame, dict) or frame.get("scene_id") != scene or not _num(frame.get("media_ms")):
            continue
        frame_ms = int(frame["media_ms"])
        if not int(media_ms) + int(start_offset_ms) <= frame_ms <= int(media_ms) + int(end_offset_ms):
            continue
        for player in frame.get("players") or []:
            if not (
                isinstance(player, dict)
                and player.get("local_track_id") == track_id
                and player.get("association_state") != "HYPOTHESES"
                and _valid_box(player.get("box"))
            ):
                continue
            geometry_ok, _geometry = _box_continuity(reference_box, player["box"], strict=True)
            team = str(player.get("team") or "").lower()
            confidence = player.get("team_confidence")
            if (
                geometry_ok and team in {"target_team", "opponent"}
                and _num(confidence) and float(confidence) >= TEAM_CONFIDENCE_MIN
            ):
                rows.append({
                    "media_ms": frame_ms,
                    "team": team,
                    "confidence": float(confidence),
                    "source": player.get("team_source"),
                })
            break
    target = [row for row in rows if row["team"] == "target_team"]
    opponent = [row for row in rows if row["team"] == "opponent"]
    if len(target) >= int(min_samples) and not opponent:
        chosen, team = target, "target_team"
    elif len(opponent) >= int(min_samples) and not target:
        chosen, team = opponent, "opponent"
    else:
        return {
            "status": "UNRESOLVED",
            "reason": "CONFLICTING_OR_SPARSE_TIME_LOCAL_TEAM_EVIDENCE",
            "target_samples": len(target),
            "opponent_samples": len(opponent),
        }
    return {
        "status": "SUPPORTING",
        "team": team,
        "confidence": round(sum(row["confidence"] for row in chosen) / len(chosen), 4),
        "source": "TIME_LOCAL_EVENT_BODY_TEAM",
        "sample_count": len(chosen),
        "evidence_ms": [row["media_ms"] for row in chosen],
        "underlying_sources": sorted({str(row.get("source")) for row in chosen if row.get("source")}),
    }


def _touch_actor_box(touch):
    geometry = touch.get("contact_geometry") if isinstance(touch, dict) and isinstance(touch.get("contact_geometry"), dict) else {}
    box = geometry.get("actor_box_used")
    return box if _valid_box(box) else None


def _scorer_team_evidence(trace, touch):
    if _team_is_target(touch):
        return deepcopy(touch.get("team_relation") or {})
    media_ms = _touch_ms(touch)
    if media_ms is None:
        return {"status": "UNRESOLVED", "reason": "SCORER_TOUCH_TIME_MISSING"}
    return _time_local_team_evidence(
        trace,
        track_id=touch.get("player_track_id"),
        scene=touch.get("scene_id"),
        media_ms=media_ms,
        reference_box=_touch_actor_box(touch),
        start_offset_ms=-LOCAL_TEAM_LOOKBACK_MS,
        end_offset_ms=LOCAL_TEAM_LOOKAHEAD_MS,
    )


def _intervention_team_evidence(trace, intervention, scene):
    if not (isinstance(intervention, dict) and _num(intervention.get("media_ms"))):
        return {"status": "UNRESOLVED", "reason": "INTERVENTION_TIME_MISSING"}
    return _time_local_team_evidence(
        trace,
        track_id=intervention.get("player_track_id"),
        scene=scene,
        media_ms=int(intervention["media_ms"]),
        reference_box=intervention.get("player_box"),
        start_offset_ms=INTERVENTION_TEAM_AFTER_MIN_MS,
        end_offset_ms=INTERVENTION_TEAM_AFTER_MAX_MS,
    )


def _visual_goal_mouth_defender_evidence(target_outcome, local_team, intervention):
    """Use literal defender contact only when the local body box is ambiguous.

    A diving goalkeeper can be merged into an overlapping outfield detection.
    In that narrow case, time-local kit voting describes the wrong body.  The
    independent goal review may resolve the party only when it visibly tracks
    a goal-mouth defender making both ball contact and an active save attempt.
    It cannot replace missing physics: A7 still has to prove the deflection and
    lack of sustained control, and the target outcome must prove the crossing.
    """
    if not _verified_goal(target_outcome):
        return {"status": "UNRESOLVED", "reason": "TARGET_GOAL_CROSSING_UNVERIFIED"}
    geometry = (
        target_outcome.get("goal_geometry_evidence")
        if isinstance(target_outcome, dict)
        and isinstance(target_outcome.get("goal_geometry_evidence"), dict)
        else {}
    )
    if geometry.get("source") != "INDEPENDENT_MULTI_FRAME_GOAL_REVIEW":
        return {"status": "UNRESOLVED", "reason": "INDEPENDENT_GOAL_REVIEW_MISSING"}
    reaction = (
        geometry.get("reaction_support_evidence")
        if isinstance(geometry.get("reaction_support_evidence"), dict)
        else {}
    )
    contact = (
        reaction.get("goal_mouth_defender_ball_contact")
        if isinstance(reaction.get("goal_mouth_defender_ball_contact"), dict)
        else {}
    )
    response = (
        reaction.get("goal_mouth_defender_response")
        if isinstance(reaction.get("goal_mouth_defender_response"), dict)
        else {}
    )
    contact_confidence = str(contact.get("confidence") or "low").lower()
    response_confidence = str(response.get("confidence") or "low").lower()
    if not (
        contact.get("tracked") is True
        and contact.get("status") == "OBSERVED_CONTACT"
        and contact_confidence in {"high", "medium"}
        and response.get("tracked") is True
        and response.get("status") == "ACTIVE_SAVE_ATTEMPT"
        and response_confidence in {"high", "medium"}
    ):
        return {"status": "UNRESOLVED", "reason": "VISIBLE_DEFENDER_CONTACT_NOT_PROVEN"}

    player_box = intervention.get("player_box") if isinstance(intervention, dict) else None
    association_ambiguous = bool(
        _valid_box(player_box)
        and float(player_box["w"]) / max(float(player_box["h"]), 1e-9) >= 0.90
    )
    if (
        isinstance(local_team, dict)
        and local_team.get("status") == "SUPPORTING"
        and local_team.get("team") == "target_team"
        and not association_ambiguous
    ):
        return {
            "status": "UNRESOLVED",
            "reason": "LOCAL_TARGET_TEAM_BODY_NOT_GEOMETRICALLY_AMBIGUOUS",
        }
    confidence = .95 if contact_confidence == response_confidence == "high" else .80
    return {
        "status": "SUPPORTING",
        "team": "opponent",
        "confidence": confidence,
        "source": "INDEPENDENT_VISUAL_GOAL_MOUTH_DEFENDER_CONTACT",
        "reason": "VISIBLE_DEFENDER_CONTACT_PLUS_ACTIVE_SAVE_ATTEMPT",
        "association_ambiguous": association_ambiguous,
        "local_track_team_evidence": deepcopy(local_team or {}),
        "visual_contact_evidence": deepcopy(contact),
        "visual_response_evidence": deepcopy(response),
    }


def _measured_contact_ball(touch):
    ball = touch.get("ball_at_contact") if isinstance(touch, dict) and isinstance(touch.get("ball_at_contact"), dict) else {}
    return ball if (
        ball.get("state") in {"MEASURED", "MEASURED_REACQUISITION"}
        and ball.get("proof_eligible") is True
        and ball.get("time_authority") == "ACTUAL_MEDIA_PTS"
        and ball.get("used_fallback") is not True
        and _valid_box(ball.get("box"))
    ) else None


def _verified_release_anchor(strike):
    anchor = strike.get("active_ball_anchor") if isinstance(strike, dict) and isinstance(strike.get("active_ball_anchor"), dict) else {}
    return bool(
        anchor.get("proof_eligible") is True
        and anchor.get("time_authority") == "ACTUAL_MEDIA_PTS"
        and anchor.get("used_fallback") is not True
        and anchor.get("source") == "VERIFIED_RELEASE_CONTACT_BALL_AFTER"
        and anchor.get("remote_spare_ball_used") is False
        and _valid_box(anchor.get("box"))
    )


def _deflected_ball_lineage(touches, *, intervention, scorer_touch, scene):
    """Verify endpoint continuity and isolate unrelated/spare-ball touches."""
    if not (
        isinstance(intervention, dict)
        and _num(intervention.get("media_ms"))
        and _valid_box(intervention.get("ball_box"))
        and _verified_touch(scorer_touch)
    ):
        return {"status": "UNRESOLVED", "reason": "DEFLECTED_LINEAGE_ENDPOINT_MISSING"}
    scorer_ball = _measured_contact_ball(scorer_touch)
    if scorer_ball is None:
        return {"status": "UNRESOLVED", "reason": "SCORER_MEASURED_CONTACT_BALL_MISSING"}
    start_ms = int(intervention["media_ms"])
    end_ms = int(_touch_ms(scorer_touch))
    if end_ms <= start_ms:
        return {"status": "UNRESOLVED", "reason": "DEFLECTED_LINEAGE_TIME_ORDER"}
    sx, sy = _box_center(intervention["ball_box"])
    ex, ey = _box_center(scorer_ball["box"])
    endpoint_distance = math.hypot(ex - sx, ey - sy)
    if endpoint_distance > DEFLECTED_ENDPOINT_MAX_NORM:
        return {
            "status": "UNRESOLVED", "reason": "DEFLECTED_LINEAGE_ENDPOINTS_TOO_FAR",
            "endpoint_distance": round(endpoint_distance, 4),
        }

    ignored_remote = []
    for touch in touches:
        touch_ms = _touch_ms(touch)
        if not (
            _verified_touch(touch)
            and touch.get("scene_id") == scene
            and touch_ms is not None
            and start_ms < int(touch_ms) < end_ms
        ):
            continue
        ball = _measured_contact_ball(touch)
        if ball is None:
            return {"status": "UNRESOLVED", "reason": "INTERVENING_TOUCH_BALL_GEOMETRY_MISSING"}
        fraction = (int(touch_ms) - start_ms) / max(1, end_ms - start_ms)
        px, py = sx + (ex - sx) * fraction, sy + (ey - sy) * fraction
        bx, by = _box_center(ball["box"])
        distance = math.hypot(bx - px, by - py)
        if distance <= DEFLECTED_LINEAGE_RADIUS_NORM:
            return {
                "status": "UNRESOLVED", "reason": "INTERVENING_TOUCH_ON_ACTIVE_BALL_LINEAGE",
                "blocking_touch_id": touch.get("touch_id"),
                "distance_to_lineage": round(distance, 4),
            }
        ignored_remote.append({
            "touch_id": touch.get("touch_id"),
            "media_ms": int(touch_ms),
            "distance_to_lineage": round(distance, 4),
            "reason": "REMOTE_BALL_TOUCH_OUTSIDE_ACTIVE_LINEAGE",
        })
    return {
        "status": "VERIFIED",
        "reason": "MEASURED_DEFLECTION_TO_SCORER_ENDPOINT_CONTINUITY",
        "intervention_ms": start_ms,
        "scorer_contact_ms": end_ms,
        "endpoint_distance": round(endpoint_distance, 4),
        "ignored_remote_ball_touches": ignored_remote,
    }


def _same_actor_after_track_split(trace, receiver_touch, scorer_touch):
    """Conservatively stitch one teammate across a local MOT id split.

    Direct local-id equality remains the primary path. Different ids can be
    linked only when team evidence agrees, the tracks are not simultaneously
    visible, and frame geometry is continuous. Longer gaps additionally require
    the same independently VERIFIED jersey number.
    """
    if not (_verified_touch(receiver_touch) and _verified_touch(scorer_touch)):
        return False, {"status": "UNRESOLVED", "reason": "TOUCH_NOT_VERIFIED"}
    left = receiver_touch.get("player_track_id")
    right = scorer_touch.get("player_track_id")
    if left == right:
        return True, {"status": "DIRECT", "from_track": left, "to_track": right}
    if not (isinstance(left, str) and isinstance(right, str)):
        return False, {"status": "UNRESOLVED", "reason": "TRACK_ID_MISSING"}
    if not (_team_is_target(receiver_touch) and _team_is_target(scorer_touch)):
        return False, {"status": "UNRESOLVED", "reason": "TEAM_CONTINUITY_UNVERIFIED"}

    scene = receiver_touch.get("scene_id")
    if scene != scorer_touch.get("scene_id"):
        return False, {"status": "UNRESOLVED", "reason": "SCENE_BOUNDARY"}
    start_ms, end_ms = _touch_ms(receiver_touch), _touch_ms(scorer_touch)
    if start_ms is None or end_ms is None or end_ms < start_ms:
        return False, {"status": "UNRESOLVED", "reason": "INVALID_TOUCH_TIME"}

    left_rows = _track_boxes(trace, left, scene, start_ms, end_ms)
    right_rows = _track_boxes(trace, right, scene, start_ms, end_ms)
    if not left_rows or not right_rows:
        return False, {"status": "UNRESOLVED", "reason": "TRACK_GEOMETRY_MISSING"}

    right_times = {r["media_ms"] for r in right_rows}
    if any(r["media_ms"] in right_times for r in left_rows):
        return False, {"status": "REJECTED", "reason": "TRACKS_VISIBLE_CONCURRENTLY"}

    left_last = left_rows[-1]
    right_first = right_rows[0]
    gap_ms = int(right_first["media_ms"]) - int(left_last["media_ms"])
    if gap_ms < 0:
        return False, {"status": "REJECTED", "reason": "TRACK_ORDER_CONFLICT"}

    left_jersey = _verified_jersey_number(receiver_touch)
    right_jersey = _verified_jersey_number(scorer_touch)
    jersey_match = bool(left_jersey and right_jersey and left_jersey == right_jersey)
    max_gap = TRACK_STITCH_JERSEY_MS if jersey_match else TRACK_STITCH_STRICT_MS
    if gap_ms > max_gap:
        return False, {
            "status": "UNRESOLVED", "reason": "TRACK_GAP_TOO_LONG",
            "gap_ms": gap_ms, "jersey_match": jersey_match,
        }

    geometry_ok, geometry = _box_continuity(
        left_last["box"], right_first["box"], strict=not jersey_match
    )
    if not geometry_ok:
        return False, {
            "status": "UNRESOLVED", "reason": "TRACK_GEOMETRY_DISCONTINUITY",
            "gap_ms": gap_ms, "jersey_match": jersey_match, "geometry": geometry,
        }
    return True, {
        "status": "VERIFIED_STITCH",
        "reason": "SAME_TEAM_GEOMETRY_AND_JERSEY" if jersey_match else "STRICT_SAME_TEAM_GEOMETRY",
        "from_track": left,
        "to_track": right,
        "gap_ms": gap_ms,
        "jersey_number": left_jersey if jersey_match else None,
        "geometry": geometry,
    }


def _goal_proof(outcome: dict) -> dict:
    crossing = outcome.get("goal_plane_crossing") if isinstance(outcome, dict) and isinstance(outcome.get("goal_plane_crossing"), dict) else {}
    return {
        "status": crossing.get("status"),
        "crossing_ms": crossing.get("crossing_ms"),
        "reason": crossing.get("reason"),
        "evidence": deepcopy(crossing.get("evidence") or []),
        "visual_audit": deepcopy(crossing.get("visual_audit") or {}),
    }


def _save_proof(outcome: dict) -> dict:
    row = outcome if isinstance(outcome, dict) else {}
    return {
        "save_evidence": deepcopy(row.get("save_evidence") or {}),
        "intervention": deepcopy(row.get("intervention") or {}),
        "intervention_role": deepcopy(row.get("intervention_role") or {}),
        "goal_plane_crossing": deepcopy(row.get("goal_plane_crossing") or {}),
    }


def _superseding_scoring_release(trace, target, strikes, outcomes, touches):
    """Return a later owner of the same verified goal, if one is proven."""
    target_outcome = outcomes.get(target.get("strike_id"))
    if not _verified_goal(target_outcome):
        return None
    target_crossing = int((target_outcome.get("goal_plane_crossing") or {})["crossing_ms"])
    target_ms = int(target["media_ms"])
    scene = target.get("scene_id")
    for candidate in strikes:
        candidate_ms = _ms(candidate)
        if not (
            candidate.get("scene_id") == scene
            and candidate_ms is not None
            and target_ms < int(candidate_ms) < target_crossing
        ):
            continue
        candidate_outcome = outcomes.get(candidate.get("strike_id"))
        if not _verified_goal(candidate_outcome):
            continue
        candidate_crossing = int((candidate_outcome.get("goal_plane_crossing") or {})["crossing_ms"])
        if abs(candidate_crossing - target_crossing) > SCORING_CROSSING_MATCH_MS:
            continue
        if candidate.get("global_target_id") == GLOBAL_TARGET_ID:
            return candidate
        candidate_touch = _touch_by_id(touches, candidate.get("touch_id"))
        team = _scorer_team_evidence(trace, candidate_touch)
        if (
            team.get("status") == "SUPPORTING"
            and team.get("team") == "target_team"
            and _num(team.get("confidence"))
            and float(team["confidence"]) >= TEAM_CONFIDENCE_MIN
        ):
            return candidate
    return None


def _later_release_blocks_control_goal(target, strikes, crossing_ms):
    """A receive/control touch cannot own a goal after another actor releases it.

    Controlled finishes are admitted because close-range scoring contacts do
    not always look like a clean RELEASE to the possession state machine.  The
    exception must stay narrow: once a different player has a later verified
    physical release before the crossing, the earlier control touch is not the
    final scoring contact.  Ordinary target releases keep the existing
    deflection-aware ownership path.
    """
    if not (
        isinstance(target, dict)
        and target.get("status") == "VERIFIED_PHYSICAL_SCORING_CONTACT"
        and _num(target.get("media_ms"))
        and _num(crossing_ms)
    ):
        return None
    target_ms = int(target["media_ms"])
    actor = target.get("player_track_id")
    scene = target.get("scene_id")
    candidates = [
        row for row in strikes
        if _verified_release(row)
        and row.get("scene_id") == scene
        and row.get("player_track_id") != actor
        and _ms(row) is not None
        and target_ms < int(_ms(row)) < int(crossing_ms)
    ]
    return min(candidates, key=lambda row: int(_ms(row)), default=None)


def _proposal_id(kind: str, scene: str, target_ms: int, scorer_track: str | None = None) -> str:
    raw = f"{kind}|{scene}|{int(target_ms)}|{scorer_track or ''}".encode("utf-8")
    return "fix10b_" + hashlib.sha1(raw).hexdigest()[:16]


def proposals_from_trace(trace: dict | None) -> list[dict]:
    """Derive only scoring proposals with complete physical chains."""
    row = trace if isinstance(trace, dict) else {}
    touches = _touches(row)
    strikes = _strikes(row)
    outcomes = _outcomes_by_strike(row)
    proposals = []

    # Direct target scoring release -> verified whole-ball goal-plane crossing.
    for strike in strikes:
        if strike.get("global_target_id") != GLOBAL_TARGET_ID:
            continue
        outcome = outcomes.get(strike.get("strike_id"))
        if not _verified_goal(outcome):
            continue
        crossing_ms = int((outcome.get("goal_plane_crossing") or {})["crossing_ms"])
        if _later_release_blocks_control_goal(strike, strikes, crossing_ms) is not None:
            continue
        # Goal geometry answers whether the ball crossed, not who owns the
        # final scoring contact.  A later verified target/teammate release with
        # the same crossing supersedes this earlier release's goal ownership.
        if _superseding_scoring_release(row, strike, strikes, outcomes, touches) is not None:
            continue
        scene = str(strike.get("scene_id") or "scene_unknown")
        contact_ms = int(strike["media_ms"])
        contact_kind = (
            "SCORING_CONTROL_CONTACT"
            if strike.get("status") == "VERIFIED_PHYSICAL_SCORING_CONTACT"
            else "RELEASE"
        )
        proposals.append({
            "proposal_id": _proposal_id("GOAL", scene, contact_ms, strike.get("player_track_id")),
            "kind": "GOAL",
            "scene_id": scene,
            "target_contact_ms": contact_ms,
            "target_track_id": strike.get("player_track_id"),
            "scorer_track_id": strike.get("player_track_id"),
            "receiver_track_id": None,
            "receiver_ms": None,
            "teammate_shot_ms": None,
            "goal_outcome_ms": crossing_ms,
            "physical_outcome_ms": crossing_ms,
            "source_trace_id": row.get("trace_id"),
            "source_touch_id": strike.get("touch_id"),
            "source_strike_id": strike.get("strike_id"),
            "target_contact_kind": contact_kind,
            "goal_proof": _goal_proof(outcome),
            "proof_eligible": True,
            "reason": f"TARGET_{contact_kind}_PLUS_VERIFIED_GOAL_PLANE_CROSSING",
        })

    # Target physical release -> verified goalkeeper intervention/save. This is
    # independent of the semantic model having already emitted a SHOT row.
    for strike in strikes:
        if strike.get("global_target_id") != GLOBAL_TARGET_ID or not _verified_release(strike):
            continue
        outcome = outcomes.get(strike.get("strike_id"))
        if not _verified_save(outcome):
            continue
        scene = str(strike.get("scene_id") or "scene_unknown")
        contact_ms = int(strike["media_ms"])
        proposals.append({
            "proposal_id": _proposal_id("SHOT", scene, contact_ms, strike.get("player_track_id")),
            "kind": "SHOT",
            "scene_id": scene,
            "target_contact_ms": contact_ms,
            "target_track_id": strike.get("player_track_id"),
            "scorer_track_id": strike.get("player_track_id"),
            "receiver_track_id": None,
            "receiver_ms": None,
            "teammate_shot_ms": None,
            "goal_outcome_ms": None,
            "physical_outcome_ms": (
                int((outcome.get("intervention") or {}).get("media_ms"))
                if _num((outcome.get("intervention") or {}).get("media_ms"))
                else contact_ms
            ),
            "canonical_outcome": "SAVED",
            "source_trace_id": row.get("trace_id"),
            "source_touch_id": strike.get("touch_id"),
            "source_strike_id": strike.get("strike_id"),
            "goal_proof": _goal_proof(outcome),
            "save_proof": _save_proof(outcome),
            "proof_eligible": True,
            "reason": "TARGET_RELEASE_PLUS_VERIFIED_GOALKEEPER_SAVE",
        })

    # Direct assist: target release -> first other verified touch is teammate ->
    # same teammate owns the next scoring release -> verified goal crossing.
    for target in strikes:
        if target.get("global_target_id") != GLOBAL_TARGET_ID or not _verified_release(target):
            continue
        scene = str(target.get("scene_id") or "scene_unknown")
        target_ms = int(target["media_ms"])
        target_track = target.get("player_track_id")
        receiver = _first_other_touch_after(
            touches, actor=target_track, scene=scene, after_ms=target_ms,
            max_ms=DIRECT_RECEIVE_MAX_MS,
        )
        if not isinstance(receiver, dict) or not _team_is_target(receiver):
            continue
        receiver_track = receiver.get("player_track_id")
        receiver_ms = _touch_ms(receiver)
        if not isinstance(receiver_track, str) or receiver_track == target_track or receiver_ms is None:
            continue
        target_outcome = outcomes.get(target.get("strike_id")) or {}
        target_intervention = (
            target_outcome.get("a7_intervention_evidence")
            if isinstance(target_outcome.get("a7_intervention_evidence"), dict)
            else target_outcome.get("intervention")
            if isinstance(target_outcome.get("intervention"), dict)
            else {}
        )
        if (
            target_intervention.get("status") == "VERIFIED"
            and target_intervention.get("proof_eligible") is True
            and _num(target_intervention.get("media_ms"))
            and target_ms < int(target_intervention["media_ms"]) < int(receiver_ms)
        ):
            # This is not a direct target->receiver chain.  A deflection can
            # still preserve the assist, but only through the stricter lane
            # below that proves intervention party, no control and ball lineage.
            continue
        if _same_actor_recontact_before(
            touches, actor=target_track, scene=scene,
            after_ms=target_ms, before_ms=receiver_ms,
        ):
            continue

        receiver_strikes = [
            s for s in strikes
            if s.get("scene_id") == scene
            and _ms(s) is not None
            and int(receiver_ms) <= int(_ms(s)) <= target_ms + DIRECT_SHOT_MAX_MS
        ]
        scoring = None
        scoring_outcome = None
        scoring_stitch = None
        for strike in receiver_strikes:
            scorer_track = strike.get("player_track_id")
            if scorer_track == receiver_track:
                same_actor = True
                stitch = {
                    "status": "DIRECT",
                    "from_track": receiver_track,
                    "to_track": scorer_track,
                }
            else:
                scorer_touch = _touch_by_id(touches, strike.get("touch_id"))
                same_actor, stitch = _same_actor_after_track_split(
                    row, receiver, scorer_touch
                )
            if not same_actor:
                continue
            shot_ms = int(strike["media_ms"])
            if _intervening_other_touch(
                touches,
                allowed_actors={receiver_track, scorer_track},
                scene=scene,
                start_ms=int(receiver_ms),
                end_ms=shot_ms,
            ):
                continue
            outcome = outcomes.get(strike.get("strike_id"))
            if not _verified_goal(outcome):
                continue
            crossing_ms = int((outcome.get("goal_plane_crossing") or {})["crossing_ms"])
            if crossing_ms > target_ms + DIRECT_GOAL_MAX_MS:
                continue
            scoring, scoring_outcome, scoring_stitch = strike, outcome, stitch
            break
        if scoring is None:
            continue

        shot_ms = int(scoring["media_ms"])
        crossing_ms = int((scoring_outcome.get("goal_plane_crossing") or {})["crossing_ms"])
        proposals.append({
            "proposal_id": _proposal_id("ASSIST", scene, target_ms, receiver_track),
            "kind": "ASSIST",
            "scene_id": scene,
            "target_contact_ms": target_ms,
            "target_track_id": target_track,
            "receiver_track_id": receiver_track,
            "receiver_ms": int(receiver_ms),
            "scorer_track_id": scoring.get("player_track_id"),
            "teammate_shot_ms": shot_ms,
            "goal_outcome_ms": crossing_ms,
            "physical_outcome_ms": crossing_ms,
            "source_trace_id": row.get("trace_id"),
            "source_touch_id": target.get("touch_id"),
            "source_strike_id": scoring.get("strike_id"),
            "goal_proof": _goal_proof(scoring_outcome),
            "receiver_team_evidence": deepcopy(receiver.get("team_relation") or {}),
            "receiver_actor_stitch": deepcopy(scoring_stitch or {}),
            "proof_eligible": True,
            "reason": "TARGET_RELEASE_TO_TEAMMATE_RECEIVE_TO_TEAMMATE_GOAL",
        })

    # Deflected assist: target release -> independently verified opponent
    # deflection without sustained control -> same active ball reaches a
    # target-team scorer -> verified goal crossing.  A remote/spare-ball touch
    # is diagnostic and ignored only when it lies outside the strict measured
    # endpoint corridor.
    for target in strikes:
        if target.get("global_target_id") != GLOBAL_TARGET_ID or not _verified_release_anchor(target):
            continue
        scene = str(target.get("scene_id") or "scene_unknown")
        target_ms = int(target["media_ms"])
        target_outcome = outcomes.get(target.get("strike_id")) or {}
        intervention = (
            target_outcome.get("a7_intervention_evidence")
            if isinstance(target_outcome.get("a7_intervention_evidence"), dict)
            else target_outcome.get("intervention")
            if isinstance(target_outcome.get("intervention"), dict)
            else {}
        )
        if not (
            intervention.get("status") == "VERIFIED"
            and intervention.get("proof_eligible") is True
            and intervention.get("kind") == "DEFLECTION_OR_PARRY_LIKE"
            and _num(intervention.get("media_ms"))
            and target_ms < int(intervention["media_ms"]) <= target_ms + DEFLECTED_SHOT_MAX_MS
            and _valid_box(intervention.get("ball_box"))
        ):
            continue
        control = intervention.get("control_evidence") if isinstance(intervention.get("control_evidence"), dict) else {}
        if control.get("status") == "VERIFIED":
            continue
        intervention_team = _intervention_team_evidence(row, intervention, scene)
        if not (
            intervention_team.get("status") == "SUPPORTING"
            and intervention_team.get("team") == "opponent"
            and _num(intervention_team.get("confidence"))
            and float(intervention_team["confidence"]) >= TEAM_CONFIDENCE_MIN
        ):
            intervention_team = _visual_goal_mouth_defender_evidence(
                target_outcome, intervention_team, intervention
            )
        if not (
            intervention_team.get("status") == "SUPPORTING"
            and intervention_team.get("team") == "opponent"
            and _num(intervention_team.get("confidence"))
            and float(intervention_team["confidence"]) >= TEAM_CONFIDENCE_MIN
        ):
            continue

        scoring = None
        scoring_outcome = None
        scorer_touch = None
        scorer_team = None
        lineage = None
        for candidate in strikes:
            shot_ms = _ms(candidate)
            if not (
                candidate.get("scene_id") == scene
                and candidate.get("global_target_id") != GLOBAL_TARGET_ID
                and shot_ms is not None
                and int(intervention["media_ms"]) < int(shot_ms) <= target_ms + DEFLECTED_SHOT_MAX_MS
            ):
                continue
            candidate_outcome = outcomes.get(candidate.get("strike_id"))
            if not _verified_goal(candidate_outcome):
                continue
            crossing_ms = int((candidate_outcome.get("goal_plane_crossing") or {})["crossing_ms"])
            if crossing_ms > target_ms + DEFLECTED_GOAL_MAX_MS:
                continue
            candidate_touch = _touch_by_id(touches, candidate.get("touch_id"))
            if not _verified_touch(candidate_touch):
                continue
            candidate_team = _scorer_team_evidence(row, candidate_touch)
            if not (
                candidate_team.get("status") == "SUPPORTING"
                and candidate_team.get("team") == "target_team"
                and _num(candidate_team.get("confidence"))
                and float(candidate_team["confidence"]) >= TEAM_CONFIDENCE_MIN
            ):
                continue
            candidate_lineage = _deflected_ball_lineage(
                touches,
                intervention=intervention,
                scorer_touch=candidate_touch,
                scene=scene,
            )
            if candidate_lineage.get("status") != "VERIFIED":
                continue
            if any(
                isinstance(frame, dict)
                and frame.get("scene_id") == scene
                and frame.get("cut_barrier") is True
                and _num(frame.get("media_ms"))
                and target_ms < int(frame["media_ms"]) < crossing_ms
                for frame in row.get("decoded_frames") or []
            ):
                continue
            scoring = candidate
            scoring_outcome = candidate_outcome
            scorer_touch = candidate_touch
            scorer_team = candidate_team
            lineage = candidate_lineage
            break
        if scoring is None:
            continue

        shot_ms = int(scoring["media_ms"])
        crossing_ms = int((scoring_outcome.get("goal_plane_crossing") or {})["crossing_ms"])
        proposals.append({
            "proposal_id": _proposal_id("ASSIST", scene, target_ms, scoring.get("player_track_id")),
            "kind": "ASSIST",
            "scene_id": scene,
            "target_contact_ms": target_ms,
            "target_track_id": target.get("player_track_id"),
            "receiver_track_id": scoring.get("player_track_id"),
            "receiver_ms": shot_ms,
            "scorer_track_id": scoring.get("player_track_id"),
            "teammate_shot_ms": shot_ms,
            "goal_outcome_ms": crossing_ms,
            "physical_outcome_ms": crossing_ms,
            "source_trace_id": row.get("trace_id"),
            "source_touch_id": target.get("touch_id"),
            "source_strike_id": scoring.get("strike_id"),
            "goal_proof": _goal_proof(scoring_outcome),
            "receiver_team_evidence": deepcopy(scorer_team or {}),
            "receiver_actor_stitch": {"status": "DIRECT", "from_track": scoring.get("player_track_id"),
                                      "to_track": scoring.get("player_track_id")},
            "deflection_proof": {
                "intervention": deepcopy(intervention),
                "intervention_team_evidence": deepcopy(intervention_team),
                "active_ball_lineage": deepcopy(lineage or {}),
            },
            "proof_eligible": True,
            "reason": "TARGET_RELEASE_OPPONENT_DEFLECTION_WITHOUT_CONTROL_TO_TEAMMATE_GOAL",
        })

    return proposals


def collect_proposals(physical_result: dict | None) -> list[dict]:
    physical = physical_result if isinstance(physical_result, dict) else {}
    rows = []
    for trace in physical.get("traces") or []:
        if isinstance(trace, dict):
            rows.extend(proposals_from_trace(trace))
    # Overlapping FIX10A windows can contain the same real chain. Keep one
    # deterministic proposal per kind/scene/target/scorer within a tight bound.
    deduped = []
    for proposal in sorted(rows, key=lambda p: (p["scene_id"], p["target_contact_ms"], p["kind"])):
        duplicate = next((
            old for old in deduped
            if old["kind"] == proposal["kind"]
            and old["scene_id"] == proposal["scene_id"]
            and old.get("scorer_track_id") == proposal.get("scorer_track_id")
            and abs(int(old["target_contact_ms"]) - int(proposal["target_contact_ms"])) <= 220
        ), None)
        if duplicate is None:
            deduped.append(proposal)
    return deduped


def _event_match(events, proposal):
    scene = proposal.get("scene_id")
    target_ms = int(proposal["target_contact_ms"])
    candidates = [
        e for e in events
        if isinstance(e, dict)
        and e.get("scene_id") == scene
        and _num(e.get("canonical_ms"))
        and abs(int(e["canonical_ms"]) - target_ms) <= CANONICAL_MATCH_MS
    ]
    if proposal.get("kind") in {"GOAL", "SHOT"}:
        preferred = [e for e in candidates if e.get("canonical_action_type") == "SHOT"]
    else:
        preferred = [e for e in candidates if e.get("canonical_action_type") in PASS_ACTIONS]
        # A model may have mislabelled the target's pass as a SHOT/GOAL. The
        # complete physical teammate chain is allowed to correct that ownership
        # error, so fall back to the nearest target event when no pass row exists.
    pool = preferred or candidates
    return min(pool, key=lambda e: abs(int(e["canonical_ms"]) - target_ms), default=None)


def _physical_proof(proposal) -> dict:
    evidence_ms = [
        proposal.get("target_contact_ms"),
        proposal.get("receiver_ms"),
        proposal.get("teammate_shot_ms"),
        proposal.get("goal_outcome_ms"),
        proposal.get("physical_outcome_ms"),
    ]
    return {
        "source": "FIX10B_PHYSICAL_RECONCILIATION",
        "proposal_id": proposal.get("proposal_id"),
        "source_trace_id": proposal.get("source_trace_id"),
        "source_touch_id": proposal.get("source_touch_id"),
        "source_strike_id": proposal.get("source_strike_id"),
        "target_contact_kind": proposal.get("target_contact_kind"),
        "evidence_ms": [int(x) for x in evidence_ms if _num(x)],
        "goal_proof": deepcopy(proposal.get("goal_proof") or {}),
        "save_proof": deepcopy(proposal.get("save_proof") or {}),
        "receiver_team_evidence": deepcopy(proposal.get("receiver_team_evidence") or {}),
        "receiver_actor_stitch": deepcopy(proposal.get("receiver_actor_stitch") or {}),
        "deflection_proof": deepcopy(proposal.get("deflection_proof") or {}),
        "proof_eligible": proposal.get("proof_eligible") is True,
    }


def _synth_event(proposal) -> dict:
    contact = int(proposal["target_contact_ms"])
    scene = str(proposal.get("scene_id") or "scene_unknown")
    kind = proposal["kind"]
    outcome_ms = int(
        proposal.get("physical_outcome_ms")
        if _num(proposal.get("physical_outcome_ms"))
        else proposal.get("goal_outcome_ms")
        if _num(proposal.get("goal_outcome_ms"))
        else contact
    )
    action_type = "SHOT" if kind in {"GOAL", "SHOT"} else "PASS"
    chain = {
        "target_contact_ms": contact,
        "receiver_local_track_id": proposal.get("receiver_track_id"),
        "receiver_ms": proposal.get("receiver_ms"),
        "teammate_shot_ms": proposal.get("teammate_shot_ms"),
        "goal_outcome_ms": proposal.get("goal_outcome_ms"),
        "continuous_visible_sequence": True,
    }
    proof = {
        "proof_start_ms": contact,
        "proof_end_ms": outcome_ms,
        "evidence_ms": _physical_proof(proposal)["evidence_ms"],
        "actor_keyframes": [],
        "contact_geometry": None,
        "contact_visibility": "PHYSICALLY_VERIFIED",
        "outcome_ms": outcome_ms,
        "proof_eligible": True,
        "causal_verified": True,
        "receiver_team_evidence": deepcopy(proposal.get("receiver_team_evidence") or {}),
        "receiver_actor_stitch": deepcopy(proposal.get("receiver_actor_stitch") or {}),
        "deflection_proof": deepcopy(proposal.get("deflection_proof") or {}),
        "save_proof": deepcopy(proposal.get("save_proof") or {}),
        "fix10b_physical": _physical_proof(proposal),
    }
    return {
        "event_id": proposal["proposal_id"],
        "global_target_id": GLOBAL_TARGET_ID,
        "scene_id": scene,
        "sequence_id": None,
        "source_sequence_ids": [],
        "source_action_ids": [],
        "start_ms": contact,
        "contact_ms": contact,
        "end_ms": outcome_ms,
        "canonical_ms": contact,
        "canonical_event_type": kind,
        "canonical_action_type": action_type,
        "canonical_outcome": (
            "GOAL" if kind == "GOAL"
            else str(proposal.get("canonical_outcome") or "UNKNOWN") if kind == "SHOT"
            else "TEAMMATE_GOAL"
        ),
        "causal_verified": True,
        "resolution_reason": proposal.get("reason"),
        "actor_local_track_id": proposal.get("target_track_id"),
        "identity_resolution": (
            "FIX10A_VERIFIED_GLOBAL_TARGET_SCORING_CONTACT"
            if proposal.get("target_contact_kind") == "SCORING_CONTROL_CONTACT"
            else "FIX10A_VERIFIED_GLOBAL_TARGET_PHYSICAL_RELEASE"
        ),
        "foot": "UNKNOWN",
        "pressure": {},
        "details": [],
        "proof": proof,
        "causal_chain": chain,
        "receiver_team_resolution": deepcopy(proposal.get("receiver_team_evidence") or {}),
        "receiver_actor_stitch": deepcopy(proposal.get("receiver_actor_stitch") or {}),
        "reconciliation_authority": "FIX10B_PHYSICAL_RECONCILIATION",
    }


def _apply_proposal(event: dict, proposal: dict) -> dict:
    out = deepcopy(event)
    before = {
        "canonical_event_type": out.get("canonical_event_type"),
        "canonical_action_type": out.get("canonical_action_type"),
        "canonical_outcome": out.get("canonical_outcome"),
    }
    if proposal["kind"] == "GOAL":
        out["canonical_event_type"] = "GOAL"
        out["canonical_action_type"] = "SHOT"
        out["canonical_outcome"] = "GOAL"
    elif proposal["kind"] == "SHOT":
        out["canonical_event_type"] = "SHOT"
        out["canonical_action_type"] = "SHOT"
        out["canonical_outcome"] = str(proposal.get("canonical_outcome") or "UNKNOWN")
    else:
        out["canonical_event_type"] = "ASSIST"
        if out.get("canonical_action_type") not in PASS_ACTIONS:
            out["canonical_action_type"] = "PASS"
        out["canonical_outcome"] = "TEAMMATE_GOAL"
        out["receiver_team_resolution"] = deepcopy(proposal.get("receiver_team_evidence") or {})
    out["causal_verified"] = True
    out["resolution_reason"] = proposal.get("reason")
    out["actor_local_track_id"] = proposal.get("target_track_id") or out.get("actor_local_track_id")
    out["global_target_id"] = GLOBAL_TARGET_ID
    if proposal.get("target_contact_kind") == "SCORING_CONTROL_CONTACT":
        out["identity_resolution"] = "FIX10A_VERIFIED_GLOBAL_TARGET_SCORING_CONTACT"
    out["causal_chain"] = {
        "target_contact_ms": proposal.get("target_contact_ms"),
        "receiver_local_track_id": proposal.get("receiver_track_id"),
        "receiver_ms": proposal.get("receiver_ms"),
        "teammate_shot_ms": proposal.get("teammate_shot_ms"),
        "goal_outcome_ms": proposal.get("goal_outcome_ms"),
        "continuous_visible_sequence": True,
    }
    proof = deepcopy(out.get("proof") or {})
    proof["proof_eligible"] = True
    proof["causal_verified"] = True
    proof["outcome_ms"] = (
        proposal.get("physical_outcome_ms")
        if _num(proposal.get("physical_outcome_ms"))
        else proposal.get("goal_outcome_ms")
    )
    proof["fix10b_physical"] = _physical_proof(proposal)
    merged_ms = set(proof.get("evidence_ms") or [])
    merged_ms.update(_physical_proof(proposal)["evidence_ms"])
    proof["evidence_ms"] = sorted(int(x) for x in merged_ms if _num(x))[:60]
    if proposal["kind"] == "ASSIST":
        proof["receiver_team_evidence"] = deepcopy(proposal.get("receiver_team_evidence") or {})
        proof["receiver_actor_stitch"] = deepcopy(proposal.get("receiver_actor_stitch") or {})
    if proposal["kind"] == "SHOT":
        proof["save_proof"] = deepcopy(proposal.get("save_proof") or {})
    out["proof"] = proof
    out["reconciliation_authority"] = "FIX10B_PHYSICAL_RECONCILIATION"
    out["fix10b_previous_classification"] = before
    return out


def _dedupe_events(events):
    # FIX10B only dedupes target scoring classifications at the same physical
    # contact. Non-scoring/micro events remain untouched.
    out = []
    for event in sorted(events, key=lambda e: (str(e.get("scene_id") or ""), int(e.get("canonical_ms") or 0), str(e.get("event_id") or ""))):
        duplicate = next((
            old for old in out
            if event.get("canonical_event_type") in {"GOAL", "ASSIST", "SHOT"}
            and old.get("canonical_event_type") == event.get("canonical_event_type")
            and old.get("scene_id") == event.get("scene_id")
            and _num(old.get("canonical_ms")) and _num(event.get("canonical_ms"))
            and abs(int(old["canonical_ms"]) - int(event["canonical_ms"])) <= 220
        ), None)
        if duplicate is None:
            out.append(event)
    return out


def _recount(bundle: dict) -> dict:
    events = bundle.get("events") or []
    counts = {}
    for event in events:
        if isinstance(event, dict):
            kind = str(event.get("canonical_event_type") or "OTHER")
            counts[kind] = counts.get(kind, 0) + 1
    metrics = deepcopy(bundle.get("metrics") or {})
    metrics.update({
        "events_accepted": len(events),
        "goals": counts.get("GOAL", 0),
        "assists": counts.get("ASSIST", 0),
        "shots": counts.get("SHOT", 0) + counts.get("GOAL", 0),
    })
    bundle["counts"] = counts
    bundle["metrics"] = metrics
    bundle["status"] = "ok" if events else bundle.get("status", "empty")
    return bundle


def reconcile_canonical_events(canonical_bundle: dict | None,
                               physical_result: dict | None) -> dict:
    """Return a copied FIX10B canonical bundle and an auditable change set."""
    canonical = deepcopy(canonical_bundle) if isinstance(canonical_bundle, dict) else {
        "version": 1, "status": "empty", "global_target_id": GLOBAL_TARGET_ID,
        "timebase": "canonical_media_ms", "events": [], "unresolved": [],
        "rejected": [], "counts": {}, "metrics": {},
    }
    events = [deepcopy(e) for e in canonical.get("events") or [] if isinstance(e, dict)]
    proposals = collect_proposals(physical_result)
    changes = []

    # If the same target contact has both a GOAL and an ASSIST proposal, the
    # chain is contradictory and neither gets authority.
    contradictory = set()
    for i, left in enumerate(proposals):
        for right in proposals[i + 1:]:
            if (left["scene_id"] == right["scene_id"]
                    and abs(int(left["target_contact_ms"]) - int(right["target_contact_ms"])) <= 220
                    and left["kind"] != right["kind"]):
                contradictory.update({left["proposal_id"], right["proposal_id"]})

    applied = []
    for proposal in proposals:
        if proposal["proposal_id"] in contradictory or proposal.get("proof_eligible") is not True:
            continue
        match = _event_match(events, proposal)
        if match is None:
            new_event = _synth_event(proposal)
            events.append(new_event)
            changes.append({
                "proposal_id": proposal["proposal_id"], "change": "ADDED_PHYSICAL_EVENT",
                "event_id": new_event.get("event_id"), "to": proposal["kind"],
            })
        else:
            index = events.index(match)
            before = deepcopy(match)
            events[index] = _apply_proposal(match, proposal)
            changes.append({
                "proposal_id": proposal["proposal_id"], "change": "RECLASSIFIED_CANONICAL_EVENT",
                "event_id": match.get("event_id"),
                "from": before.get("canonical_event_type"), "to": proposal["kind"],
            })
        applied.append(proposal["proposal_id"])

    # A semantic GOAL/ASSIST chain can have internally consistent timestamps
    # while attributing the teammate's strike to the target. Once FIX10B is
    # authoritative, scoring needs a matching verified physical proposal.
    # Keep unmatched claims visible for review, but never publish them as
    # verified target goals/assists or count them in the report.
    scoring_unresolved = []
    verified_events = []
    for event in events:
        if (event.get("canonical_event_type") in {"GOAL", "ASSIST"}
                and event.get("reconciliation_authority") != "FIX10B_PHYSICAL_RECONCILIATION"):
            scoring_unresolved.append({
                "event_id": event.get("event_id"),
                "scene_id": event.get("scene_id"),
                "canonical_ms": event.get("canonical_ms"),
                "claimed_event_type": event.get("canonical_event_type"),
                "reason": "SCORING_PHYSICAL_PROOF_MISSING",
            })
        else:
            verified_events.append(event)
    canonical["events"] = _dedupe_events(verified_events)
    canonical["unresolved"] = list(canonical.get("unresolved") or []) + scoring_unresolved
    if scoring_unresolved and not canonical["events"]:
        canonical["status"] = "unresolved"
    metrics = deepcopy(canonical.get("metrics") or {})
    metrics["observations_unresolved"] = int(metrics.get("observations_unresolved") or 0) + len(scoring_unresolved)
    canonical["metrics"] = metrics
    canonical["version"] = f"FIX10B.{VERSION}"
    canonical["global_target_id"] = GLOBAL_TARGET_ID
    canonical["timebase"] = "canonical_media_ms"
    canonical["reconciliation"] = {
        "version": VERSION,
        "authority": "FIX10B_PHYSICAL_RECONCILIATION",
        "proposals_total": len(proposals),
        "proposals_applied": len(applied),
        "proposals_contradictory": len(contradictory),
        "applied_proposal_ids": applied,
        "changes": changes,
        "scoring_claims_unresolved": len(scoring_unresolved),
        "physical_status": (physical_result or {}).get("status") if isinstance(physical_result, dict) else None,
    }
    return _recount(canonical)
