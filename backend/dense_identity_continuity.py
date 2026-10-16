"""Share bounded identity proofs across an uninterrupted physical body track.

A shirt number is a possible seed, not a per-frame requirement. Coarse identity
gaps are not physical contradictions. Cuts, ambiguous body associations and a
different verified target are contradictions and terminate propagation.
"""
from copy import deepcopy
import math

import unified_identity_authority as uia
from goal_review_scheduler import _iou

MAX_CONTINUITY_MS = 1200
MAX_FRAME_GAP_MS = 80
SEED_REASONS = {"OK_EXACT", "OK_NEAREST_TAP_FRAME",
                "PROOF_TARGET_SINGLE_CANDIDATE_HYPOTHESIS_COLLAPSE"}
IDENTITY_BARRIERS = {"UNRESOLVED_IDENTITY", "SOURCE_CONFLICT", "SCENE_CUT",
                     "USER_EXCLUDED_OPPONENT", "USER_PARTIAL_VISIBLE_BODY",
                     "DENSE_TARGET_COMPETING_ASSOCIATION"}


def _body(frame, track):
    bodies = [p for p in frame.get("players") or []
              if p.get("local_track_id") == track
              and p.get("association_state") == "VERIFIED_LOCAL"
              and uia._valid_box(p.get("box"))]
    return bodies[0] if len(bodies) == 1 else None


def _native_unique_step(before, after, track):
    """Long continuity needs actual, isolated detections, not an ID string.

    Keep the old short bridge for legacy measurements. Beyond it, every step
    must have a native body observation and a unique forward/backward match.
    A new independent seed can start another segment after a crossing/cut.
    """
    import cv_detect
    a, b = _body(before, track), _body(after, track)
    if (a and b and a.get("team") in {"target_team", "opponent"}
            and b.get("team") in {"target_team", "opponent"} and a["team"] != b["team"]):
        return False
    for frame, body in ((before, a), (after, b)):
        if body is None:
            return False
        confidence = body.get("confidence")
        quality = body.get("jersey_crop_quality")
        quality = quality if isinstance(quality, dict) else {}
        if (not isinstance(confidence, (int, float)) or isinstance(confidence, bool)
                or not math.isfinite(confidence) or confidence <= cv_detect.CONF_T
                or quality.get("source") != "NATIVE_TORSO_PIXELS" or quality.get("isolated") is not True):
            return False
        if any(p is not body and _iou(p.get("box"), body["box"]) >= .25
               for p in frame.get("players") or []):
            return False
    return (len([p for p in after.get("players") or [] if uia.boxes_agree(a["box"], p.get("box"))]) == 1
            and len([p for p in before.get("players") or [] if uia.boxes_agree(b["box"], p.get("box"))]) == 1)


def apply(frames, touch_graph=None):
    """Return copies; never turn an uncertain physical contact into a fact."""
    rows = sorted(deepcopy(frames or []), key=lambda f: f["media_ms"])
    graph = deepcopy(touch_graph or {"touches": []})
    by_ms = {f["media_ms"]: i for i, f in enumerate(rows)}
    seeds = []
    for i, f in enumerate(rows):
        target = f.get("global_target") or {}
        if (target.get("status") == "VERIFIED" and target.get("proof_eligible") is True
                and target.get("reason") in SEED_REASONS):
            seeds.append((i, target.get("local_track_id"), target.get("reason")))
    for t in graph.get("touches") or []:
        resolution = t.get("global_target_resolution") or {}
        ms = t.get("representative_ms", t.get("media_ms"))
        if (t.get("status") == "VERIFIED" and t.get("proof_eligible") is True
                and t.get("global_target_id") == uia.GLOBAL_TARGET_ID
                and resolution.get("status") == "VERIFIED"
                and resolution.get("reason") in {"UNIQUE_MULTI_FRAME_JERSEY_REID_AFTER_USER_TAP",
                    "UNIQUE_MULTI_FRAME_JERSEY_REID_FROM_VERIFIED_REFERENCE"}
                and ms in by_ms):
            seeds.append((by_ms[ms], t.get("player_track_id"), resolution["reason"]))
    proposals = {}
    native_steps = {}
    for index, track, reason in seeds:
        seed = rows[index]
        seed_body = _body(seed, track)
        if not seed_body or seed.get("used_fallback") or seed.get("time_authority") != "ACTUAL_MEDIA_PTS":
            continue
        for direction in (-1, 1):
            previous, previous_body = seed, seed_body
            measured_segment = True
            for i in range(index, len(rows) if direction == 1 else -1, direction):
                f = rows[i]
                body = _body(f, track)
                target = f.get("global_target") or {}
                if measured_segment:
                    key = (*sorted((id(previous), id(f))), track)
                    if key not in native_steps:
                        native_steps[key] = _native_unique_step(previous, f, track)
                    measured_segment = native_steps[key]
                extended = abs(f["media_ms"] - seed["media_ms"]) > MAX_CONTINUITY_MS
                if (extended and not measured_segment
                        or abs(f["media_ms"] - previous["media_ms"]) > MAX_FRAME_GAP_MS
                        or f.get("scene_id") != seed.get("scene_id")
                        or f.get("cut_barrier") or f.get("cut") or f.get("used_fallback")
                        or f.get("time_authority") != "ACTUAL_MEDIA_PTS"
                        or target.get("reason") in IDENTITY_BARRIERS
                        or body is None
                        or not uia.boxes_agree(previous_body["box"], body["box"])
                        or (target.get("status") == "VERIFIED" and target.get("proof_eligible") is True
                            and target.get("local_track_id") != track)):
                    break
                # A multi-body association involving this track is an explicit
                # crossing ambiguity, even if a duplicate detection kept its ID.
                if any(p.get("association_state") == "HYPOTHESES"
                       and track in (p.get("candidate_local_track_ids") or [])
                       for p in f.get("players") or []):
                    break
                proposals.setdefault(i, {}).setdefault(track, {
                    "seed_ms": seed["media_ms"], "seed_reason": reason,
                    "native_segment_verified": measured_segment,
                    "extended_visible_track": extended})
                previous, previous_body = f, body
    promoted = 0
    for i, candidates in proposals.items():
        if len(candidates) != 1:
            continue
        f = rows[i]
        current = f.get("global_target") or {}
        if current.get("status") == "VERIFIED" and current.get("proof_eligible") is True:
            continue
        track, evidence = next(iter(candidates.items()))
        body = _body(f, track)
        f["global_target"] = {
            "status": "VERIFIED", "proof_eligible": True,
            "reason": ("MEASURED_VISIBLE_TRACK_CONTINUITY" if evidence["extended_visible_track"]
                       else "BOUNDED_DENSE_BODY_CONTINUITY"),
            "local_track_id": track, "candidate_local_track_ids": [track],
            "body_box": deepcopy(body["box"]),
            "body_team": body.get("team"),
            "body_team_confidence": body.get("team_confidence"),
            "body_team_source": body.get("team_source"),
            "continuity_evidence": {**evidence, "max_span_ms": MAX_CONTINUITY_MS,
                                    "same_scene": True, "association": "VERIFIED_LOCAL"},
        }
        promoted += 1
    bound = 0
    for t in graph.get("touches") or []:
        ms = t.get("representative_ms", t.get("media_ms"))
        f = rows[by_ms[ms]] if ms in by_ms else None
        target = (f or {}).get("global_target") or {}
        if (t.get("status") == "VERIFIED" and t.get("proof_eligible") is True
                and target.get("status") == "VERIFIED" and target.get("proof_eligible") is True
                and target.get("local_track_id") == t.get("player_track_id")
                and not t.get("global_target_id")):
            t["global_target_id"] = uia.GLOBAL_TARGET_ID
            t["global_target_resolution"] = {
                "status": "VERIFIED", "global_target_id": uia.GLOBAL_TARGET_ID,
                "reason": target.get("reason"),
                "continuity_evidence": deepcopy(target.get("continuity_evidence") or {}),
            }
            bound += 1
    diagnostic = {"version": 1, "promoted_frames": promoted, "bound_contacts": bound,
                  "max_continuity_ms": MAX_CONTINUITY_MS, "number_required_each_frame": False}
    graph["dense_identity_continuity"] = diagnostic
    return {"frames": rows, "touch_graph": graph, "diagnostic": diagnostic}
