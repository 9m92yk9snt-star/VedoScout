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
                "PROOF_TARGET_SINGLE_CANDIDATE_HYPOTHESIS_COLLAPSE",
                "MULTI_FRAME_SELECTED_APPEARANCE", "SOURCE_VIDEO_SELECTED_PERSON"}
IDENTITY_BARRIERS = {"UNRESOLVED_IDENTITY", "SOURCE_CONFLICT",
                     "USER_EXCLUDED_OPPONENT", "USER_PARTIAL_VISIBLE_BODY",
                     "DENSE_TARGET_COMPETING_ASSOCIATION"}


def _hard_barrier(target):
    # A coarse reader's absence/failed re-ID can be resolved by fresh native
    # observations. Preserve actual source contradictions and user exclusions.
    reasons = target.get("identity_barrier_reasons") or []
    if target.get("reason") == "UNRESOLVED_IDENTITY" and reasons and all(
            r in {"target_absent", "reid_failed", "ambiguous_duel"} for r in reasons):
        return False
    return target.get("reason") in IDENTITY_BARRIERS


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


def apply_reference_matches(frames, observation):
    """Fuse the existing pixel reader's comparisons to actual selected crops.

    A source-video comparison is direct identity evidence at its cited frame.
    It need not repeat the comparison under each changing native track ID.
    Static crop reads retain their independent multi-frame requirements.
    """
    rows = deepcopy(frames or [])
    reference = (observation or {}).get("selected_reference") or {}
    if (reference.get("source") != "USER_SELECTED_SOURCE_PIXELS"
            or not reference.get("source_video_sha256") or not reference.get("input_sha256")):
        return rows
    import sequence_observation_context
    scene = next((f.get("scene_id") for f in rows), None)
    source_times = [f["media_ms"] for f in rows if sequence_observation_context.actual(f, scene)]
    if not source_times:
        return rows
    direct_motion = (observation.get("source_video_sha256") == reference["source_video_sha256"]
        and bool(sequence_observation_context.video_observations(observation, rows,
            {"scene_id": scene, "start_ms": min(source_times), "end_ms": max(source_times)}).get("sequences")))
    by_ms = {f["media_ms"]: f for f in rows}
    votes = {}
    for match in (observation or {}).get("target_observations") or []:
        f = by_ms.get(match.get("media_ms"))
        track = match.get("local_track_id")
        features = set(v for v in match.get("features") or [] if isinstance(v, str)
                       and v in {"hair", "build", "socks", "boots", "sleeves"})
        if (f is None or match.get("confidence") != "high" or (not direct_motion and len(features) < 2)
                or f.get("time_authority") != "ACTUAL_MEDIA_PTS"
                or any(f.get(k) for k in ("cut", "cut_barrier", "used_fallback"))):
            continue
        body = _body(f, track)
        target = f.get("global_target") or {}
        barrier = _hard_barrier(target) and (not direct_motion or target.get("reason") in {
            "SOURCE_CONFLICT", "USER_EXCLUDED_OPPONENT", "USER_PARTIAL_VISIBLE_BODY"})
        if (body is None or (not direct_motion and not _native_unique_step(f, f, track))
                or (not direct_motion and body.get("team") == "opponent") or barrier
                or target.get("proof_eligible") is True and target.get("local_track_id") != track):
            continue
        votes.setdefault((f.get("scene_id"), track), set()).add(f["media_ms"])
    for (scene, track), times in votes.items():
        if not direct_motion:
            if len(times) < 2 or max(times)-min(times) < 150:
                continue
            path = [f for f in rows if min(times) <= f["media_ms"] <= max(times)]
            if (any(f.get("scene_id") != scene or f.get("time_authority") != "ACTUAL_MEDIA_PTS"
                or any(f.get(k) for k in ("cut", "cut_barrier", "used_fallback"))
                or _hard_barrier(f.get("global_target") or {})
                or ((f.get("global_target") or {}).get("proof_eligible") is True
                    and (f.get("global_target") or {}).get("local_track_id") != track)
                or _body(f, track) is None for f in path)
                or any(b["media_ms"]-a["media_ms"] > MAX_FRAME_GAP_MS
                       or not _native_unique_step(a, b, track) for a, b in zip(path, path[1:]))):
                continue
        for ms in times:
            if any(other != track and other_scene == scene and ms in other_times
                   for (other_scene, other), other_times in votes.items()):
                continue
            f = by_ms[ms]
            if (f.get("global_target") or {}).get("proof_eligible") is True:
                continue
            f["global_target"] = {"status": "VERIFIED", "proof_eligible": True,
                "reason": "SOURCE_VIDEO_SELECTED_PERSON" if direct_motion else "MULTI_FRAME_SELECTED_APPEARANCE",
                "local_track_id": track,
                "candidate_local_track_ids": [track], "body_box": deepcopy(_body(f, track)["box"]),
                "appearance_evidence": {**deepcopy(reference), "evidence_ms": sorted(times),
                                        "number_required": False}}
    return rows


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
                # SCENE_CUT from the sparse timeline means its surrounding
                # samples straddle a cut. It is not a cut in this exact frame.
                # An uninterrupted native body path can resolve that gap;
                # actual decoded cuts and identity conflicts still stop it.
                coarse_gap = target.get("reason") in {"SCENE_CUT", "UNRESOLVED_IDENTITY"}
                if ((extended or coarse_gap) and not measured_segment
                        or abs(f["media_ms"] - previous["media_ms"]) > MAX_FRAME_GAP_MS
                        or f.get("scene_id") != seed.get("scene_id")
                        or f.get("cut_barrier") or f.get("cut") or f.get("used_fallback")
                        or f.get("time_authority") != "ACTUAL_MEDIA_PTS"
                        or _hard_barrier(target)
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
