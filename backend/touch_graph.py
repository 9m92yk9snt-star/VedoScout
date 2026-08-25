"""FIX10A5 — physical Touch Graph and possession-chain reconstruction.

Consumes resolved FIX10A4 contacts and turns repeated frame-level evidence into
ordered physical touches plus bounded possession/free-ball segments.  This is
still evidence only: it never emits GOAL, ASSIST, scorer or canonical events.
GLOBAL_TARGET may be attached only when the pre-existing identity authority and
its dense local-track mapping both support the same player at that time.
"""
from __future__ import annotations

import hashlib
from copy import deepcopy

import unified_identity_authority as uia

VERSION = 1
TOUCH_MERGE_MS = 160
DENSE_NEAR_MS = 100
TARGET_NEAR_MS = 250


def _num(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _touch_id(scene_id: str, start_ms: int, end_ms: int, actor_key: str) -> str:
    raw = f"{scene_id}|{int(start_ms)}|{int(end_ms)}|{actor_key}".encode("utf-8")
    return "touch_" + hashlib.sha1(raw).hexdigest()[:16]


def _actor_signature(row: dict) -> tuple:
    track = row.get("player_track_id") if isinstance(row.get("player_track_id"), str) else None
    candidates = tuple(sorted(x for x in (row.get("player_candidate_track_ids") or []) if isinstance(x, str)))
    return (track, candidates, str(row.get("status") or "UNRESOLVED"))


def _nearest_dense_frame(dense_frames, media_ms):
    rows = [
        f for f in (dense_frames or [])
        if isinstance(f, dict) and _num(f.get("media_ms"))
    ]
    if not rows:
        return None
    best = min(rows, key=lambda f: abs(int(f["media_ms"]) - int(media_ms)))
    return best if abs(int(best["media_ms"]) - int(media_ms)) <= DENSE_NEAR_MS else None


def _dense_player(frame, track_id):
    if not isinstance(frame, dict) or not isinstance(track_id, str):
        return None
    return next((
        p for p in frame.get("players") or []
        if isinstance(p, dict) and p.get("local_track_id") == track_id
    ), None)


def _team_relation(dense_frames, media_ms, track_id):
    frame = _nearest_dense_frame(dense_frames, media_ms)
    player = _dense_player(frame, track_id)
    if not isinstance(player, dict):
        return {"status": "UNRESOLVED", "team": None, "confidence": None, "source": None}
    team = player.get("team")
    confidence = player.get("team_confidence")
    source = player.get("team_source")
    if team not in {"target_team", "opponent", "other"} or not _num(confidence):
        return {"status": "UNRESOLVED", "team": team, "confidence": confidence, "source": source}
    return {
        "status": "SUPPORTING",
        "team": team,
        "confidence": round(float(confidence), 4),
        "source": source,
    }


def _global_target_binding(identity_authority, dense_frames, media_ms, track_id):
    """Attach GLOBAL_TARGET only through the already-owned identity authority."""
    if not isinstance(track_id, str):
        return {"global_target_id": None, "status": "UNRESOLVED", "reason": "NO_SINGLE_LOCAL_ACTOR"}
    frame = _nearest_dense_frame(dense_frames, media_ms)
    dense_target = frame.get("global_target") if isinstance(frame, dict) and isinstance(frame.get("global_target"), dict) else {}
    if not (
        dense_target.get("status") == "VERIFIED"
        and dense_target.get("proof_eligible") is True
        and dense_target.get("local_track_id") == track_id
    ):
        return {"global_target_id": None, "status": "UNRESOLVED",
                "reason": "DENSE_TARGET_MAPPING_NOT_VERIFIED"}
    resolved, why = uia.resolve_target_at(
        identity_authority if isinstance(identity_authority, dict) else {},
        int(media_ms), proof_required=True, max_interp_ms=TARGET_NEAR_MS,
    )
    if not isinstance(resolved, dict) or resolved.get("proof_eligible") is not True:
        return {"global_target_id": None, "status": "UNRESOLVED",
                "reason": why or "GLOBAL_TARGET_AUTHORITY_NOT_PROOF_ELIGIBLE"}
    return {"global_target_id": uia.GLOBAL_TARGET_ID, "status": "VERIFIED", "reason": why}


def _merge_group(group: list[dict], identity_authority, dense_frames) -> dict:
    first, last = group[0], group[-1]
    start_ms, end_ms = int(first["media_ms"]), int(last["media_ms"])
    track_id = first.get("player_track_id") if isinstance(first.get("player_track_id"), str) else None
    candidates = list(dict.fromkeys(
        x for row in group for x in (row.get("player_candidate_track_ids") or []) if isinstance(x, str)
    ))
    actor_key = track_id or "+".join(sorted(candidates)) or "unknown"
    statuses = {str(row.get("status") or "UNRESOLVED") for row in group}
    status = "VERIFIED" if statuses == {"VERIFIED"} and track_id else (
        "CANDIDATE_OCCLUDED" if statuses == {"CANDIDATE_OCCLUDED"} and track_id else "HYPOTHESES"
    )
    representative_ms = int(round(sum(int(row["media_ms"]) for row in group) / len(group)))
    identity = _global_target_binding(identity_authority, dense_frames, representative_ms, track_id)
    team = _team_relation(dense_frames, representative_ms, track_id)
    possession_kinds = [
        str((row.get("possession_evidence") or {}).get("kind") or "UNRESOLVED")
        for row in group
    ]
    before_holders = [
        (row.get("possession_evidence") or {}).get("before_holder") for row in group
        if (row.get("possession_evidence") or {}).get("before_holder") is not None
    ]
    after_holders = [
        (row.get("possession_evidence") or {}).get("after_holder") for row in group
        if (row.get("possession_evidence") or {}).get("after_holder") is not None
    ]
    contradictions = list(dict.fromkeys(
        x for row in group for x in (row.get("rejection_reasons") or []) if isinstance(x, str)
    ))
    trajectory_change = max(
        [float((row.get("trajectory_evidence") or {}).get("score") or 0.0) for row in group] or [0.0]
    )
    confidence = sum(float(row.get("confidence") or 0.0) for row in group) / max(1, len(group))
    visibility = (
        "VISIBLE" if any(row.get("contact_visibility") == "VISIBLE" for row in group)
        else "OCCLUDED"
    )
    possession_before = before_holders[-1] if before_holders else None
    possession_after = after_holders[-1] if after_holders else None
    return {
        "touch_id": _touch_id(str(first.get("scene_id") or "scene_unknown"), start_ms, end_ms, actor_key),
        "media_ms": start_ms,
        "end_ms": end_ms,
        "representative_ms": representative_ms,
        "scene_id": first.get("scene_id"),
        "player_track_id": track_id,
        "player_candidate_track_ids": candidates,
        "global_target_id": identity.get("global_target_id"),
        "global_target_resolution": identity,
        "team_relation": team,
        "jersey_posterior": None,
        "status": status,
        "visibility": visibility,
        "foot": "UNKNOWN",
        "ball_before": deepcopy(first.get("ball_before")),
        "ball_after": deepcopy(last.get("ball_after")),
        "contact_geometry": deepcopy(max(
            group,
            key=lambda row: float((row.get("contact_geometry") or {}).get("score") or 0.0),
        ).get("contact_geometry") or {}),
        "trajectory_change": round(trajectory_change, 4),
        "possession_before": possession_before,
        "possession_after": possession_after,
        "possession_kinds": list(dict.fromkeys(possession_kinds)),
        "confidence": round(confidence, 4),
        "proof_eligible": bool(status == "VERIFIED" and all(row.get("proof_eligible") is True for row in group)),
        "contradictions": contradictions,
        "source_contact_ids": [row.get("contact_id") for row in group if row.get("contact_id")],
        "frame_contact_count": len(group),
    }


def build_possession_segments(touches) -> list[dict]:
    """Build ordered possession/free-ball intervals from physical touch truth."""
    rows = sorted(
        [deepcopy(t) for t in (touches or []) if isinstance(t, dict) and _num(t.get("media_ms"))],
        key=lambda t: (int(t["media_ms"]), int(t.get("end_ms") or t["media_ms"])),
    )
    segments = []
    for i, touch in enumerate(rows[:-1]):
        nxt = rows[i + 1]
        start_ms = int(touch.get("end_ms") or touch["media_ms"])
        end_ms = int(nxt["media_ms"])
        if end_ms <= start_ms:
            continue
        same_scene = touch.get("scene_id") == nxt.get("scene_id")
        if not same_scene:
            segments.append({
                "start_ms": start_ms, "end_ms": end_ms,
                "scene_id": touch.get("scene_id"), "status": "BARRIER",
                "holder_local_track_id": None, "reason": "SCENE_BOUNDARY",
            })
            continue
        actor = touch.get("player_track_id") if touch.get("status") == "VERIFIED" else None
        after = touch.get("possession_after")
        kinds = set(touch.get("possession_kinds") or [])
        if actor and after == actor and kinds.intersection({"RECEIVE", "CONTROL_TOUCH"}):
            segments.append({
                "start_ms": start_ms, "end_ms": end_ms,
                "scene_id": touch.get("scene_id"), "status": "POSSESSION",
                "holder_local_track_id": actor,
                "reason": "VERIFIED_TOUCH_WITH_AFTER_CONTROL",
            })
        elif touch.get("status") == "VERIFIED" and (
            "RELEASE" in kinds or after is None or after != actor
        ):
            segments.append({
                "start_ms": start_ms, "end_ms": end_ms,
                "scene_id": touch.get("scene_id"), "status": "FREE_BALL_IN_FLIGHT",
                "holder_local_track_id": None,
                "reason": "VERIFIED_RELEASE_OR_NO_CONTROL",
            })
        else:
            segments.append({
                "start_ms": start_ms, "end_ms": end_ms,
                "scene_id": touch.get("scene_id"), "status": "UNRESOLVED",
                "holder_local_track_id": None,
                "reason": "TOUCH_OR_CONTROL_UNRESOLVED",
            })
    return segments


def build_touch_graph(contact_result: dict | None, identity_authority: dict | None = None,
                      dense_frames=None) -> dict:
    """Collapse repeated physical contact frames into ordered touch nodes."""
    result = contact_result if isinstance(contact_result, dict) else {}
    contacts = [
        deepcopy(row) for row in result.get("contacts") or []
        if isinstance(row, dict) and _num(row.get("media_ms"))
        and str(row.get("status") or "") in {"VERIFIED", "HYPOTHESES", "CANDIDATE_OCCLUDED"}
    ]
    contacts.sort(key=lambda row: (str(row.get("scene_id") or ""), int(row["media_ms"])))
    groups = []
    for row in contacts:
        if not groups:
            groups.append([row]); continue
        prev = groups[-1][-1]
        same_scene = str(prev.get("scene_id") or "") == str(row.get("scene_id") or "")
        same_actor = _actor_signature(prev) == _actor_signature(row)
        close = int(row["media_ms"]) - int(prev["media_ms"]) <= TOUCH_MERGE_MS
        if same_scene and same_actor and close:
            groups[-1].append(row)
        else:
            groups.append([row])
    touches = [_merge_group(group, identity_authority or {}, dense_frames or []) for group in groups]
    touches.sort(key=lambda row: int(row["media_ms"]))
    possession = build_possession_segments(touches)
    return {
        "version": VERSION,
        "status": "ok" if touches else "empty",
        "timebase": "canonical_media_ms",
        "touches": touches,
        "possession_segments": possession,
        "metrics": {
            "frame_contacts": len(contacts),
            "touches": len(touches),
            "verified_touches": sum(t.get("status") == "VERIFIED" for t in touches),
            "unresolved_touches": sum(t.get("status") != "VERIFIED" for t in touches),
            "free_ball_segments": sum(s.get("status") == "FREE_BALL_IN_FLIGHT" for s in possession),
        },
    }
