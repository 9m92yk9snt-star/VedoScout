"""Inspection admission before contact/identity proof, never event authority.

All action labels are eligible, including OTHER and runs. Their times are search
hints only. New ball rows need native-pixel detector corroboration; jersey crops
must bind to one measured body and use the existing independent number reader.
"""
from collections import defaultdict
from copy import deepcopy
import hashlib
import json
import math
import os

import goal_review_scheduler as scheduler

MAX_ACTION_REVIEWS = max(0, int(os.environ.get("FIX13_MAX_ACTION_REVIEWS", "16")))
MAX_ACTION_FRAMES = 12
MAX_FRAME_ALIGNMENT_MS = 20


def _num(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def build_plan(windows, analysis, budget=None):
    """Reserve a report-wide allocation before windows spend any model calls."""
    limit = MAX_ACTION_REVIEWS if budget is None else max(0, int(budget))
    windows = [w for w in windows if _num(w.get("start_ms")) and _num(w.get("end_ms"))
               and w["end_ms"] - w["start_ms"] >= 150 and w.get("scene_id")]
    candidates = []
    for sequence in (analysis or {}).get("sequences") or []:
        scene = sequence.get("scene_id")
        for action in sequence.get("actions") or []:
            start, end = action.get("start_ms"), action.get("end_ms")
            if not (_num(start) and _num(end) and 0 <= start <= end) or action.get("duplicate_of"):
                continue
            center = action.get("contact_ms")
            has_contact = bool(_num(center) and start <= center <= end)
            if not has_contact:
                center = (start + end) / 2
            available = [w for w in windows if w.get("scene_id") == scene
                         and w["start_ms"] <= center <= w["end_ms"]]
            if not available:
                continue
            desired_end = max(end + 600, center + 2600) if has_contact else end + 600
            window = max(available, key=lambda w: min(w["end_ms"], desired_end) - max(w["start_ms"], start - 300))
            left = max(int(window["start_ms"]), int(start - 300), int(center - (300 if has_contact else 1200)))
            right = min(int(window["end_ms"]), int(desired_end), int(center + (2600 if has_contact else 1200)))
            if right - left < 150:
                continue
            candidates.append({"scene_id": scene, "start_ms": left, "end_ms": right,
                               "center_ms": int(center), "dense_window_id": window["dense_window_id"],
                               "has_contact_time": has_contact,
                               "source_action_ids": [action.get("action_id")],
                               "reason": "OBSERVATION_NEEDS_PIXEL_INSPECTION"})
    # Physical recall still has an inspection path if the semantic provider
    # missed a scene entirely. No presumed goal/assist is needed to open it.
    for window in windows:
        if any(
                j["scene_id"] == window.get("scene_id") and window["start_ms"] <= j["center_ms"] <= window["end_ms"]
                for j in candidates):
            continue
        center = int((window["start_ms"] + window["end_ms"]) / 2)
        candidates.append({"scene_id": window.get("scene_id"), "start_ms": max(window["start_ms"], center - 1000),
                           "end_ms": min(window["end_ms"], center + 1000), "center_ms": center,
                           "dense_window_id": window["dense_window_id"], "source_action_ids": [],
                           "has_contact_time": False,
                           "reason": "PHYSICAL_RECALL_WITHOUT_SEMANTIC_CONTACT"})
    groups = []
    for job in sorted(candidates, key=lambda j: j["center_ms"]):
        previous = next((old for old in groups if old["scene_id"] == job["scene_id"]
                         and abs(old["center_ms"] - job["center_ms"]) <= 120), None)
        if previous is None:
            groups.append(job)
        else:
            previous["source_action_ids"].extend(job["source_action_ids"])
    scenes = defaultdict(lambda: defaultdict(list))
    for job in groups:
        scenes[str(job["scene_id"])][job["center_ms"] // scheduler.TIME_CELL_MS].append(job)
    for cells in scenes.values():
        for group in cells.values():
            group.sort(key=lambda j: (not j["has_contact_time"], j["center_ms"]))
    visits, ordered = defaultdict(int), []
    while scenes:
        minimum_visits = min(visits[(scene, cell)] for scene, cells in scenes.items() for cell in cells)
        eligible_scenes = [s for s in scenes if any(visits[(s, c)] == minimum_visits for c in scenes[s])]
        for scene in sorted(eligible_scenes, key=lambda s: min(g[0]["center_ms"] for g in scenes[s].values())):
            cells = scenes[scene]
            cell = min((c for c in cells if visits[(scene, c)] == minimum_visits), key=lambda c: cells[c][0]["center_ms"])
            job = cells[cell].pop(0)
            job["inspection_id"] = hashlib.sha256(json.dumps(
                [job["scene_id"], job["start_ms"], job["end_ms"]]).encode()).hexdigest()[:20]
            job["selection_rank"] = len(ordered)
            job["selected"] = len(ordered) < limit
            ordered.append(job)
            visits[(scene, cell)] += 1
            if not cells[cell]:
                del cells[cell]
            if not cells:
                del scenes[scene]
    return {"budget": limit, "selected": sum(j["selected"] for j in ordered),
            "deferred": sum(not j["selected"] for j in ordered), "jobs": ordered}


def frame_times(job, frames):
    available = sorted({int(f["media_ms"]) for f in frames if _num(f.get("media_ms"))
                        and f.get("scene_id") == job["scene_id"] and not f.get("cut_barrier")
                        and not f.get("used_fallback") and f.get("time_authority") == "ACTUAL_MEDIA_PTS"
                        and job["start_ms"] <= f["media_ms"] <= job["end_ms"]})
    if len(available) <= MAX_ACTION_FRAMES:
        return available
    if job.get("has_contact_time"):
        from fix10a_vision_providers import _goal_review_times
        wanted = _goal_review_times(job["center_ms"], job["end_ms"], MAX_ACTION_FRAMES, start_ms=job["start_ms"])
        return sorted({min(available, key=lambda ms: abs(ms - t)) for t in wanted})
    selected = {min(available, key=lambda ms: abs(ms - job["center_ms"]))}
    for index in range(MAX_ACTION_FRAMES - 1):
        wanted = available[0] + index * (available[-1] - available[0]) / (MAX_ACTION_FRAMES - 2)
        selected.add(min(available, key=lambda ms: abs(ms - wanted)))
    return sorted(selected)


def bind_body(frame, box):
    players = [p for p in frame.get("players") or [] if scheduler._iou(p.get("box"), box) >= .60]
    if len(players) != 1:
        return None
    player = players[0]
    if not player.get("local_track_id") or player.get("association_state") != "VERIFIED_LOCAL":
        return None
    # A detector ROI containing two torsos is not a safe jersey crop.
    if any(p is not player and scheduler._iou(p.get("box"), player["box"]) >= .25
           for p in frame.get("players") or []):
        return None
    return player


def apply_observations(frames, observations, inspection_id):
    """Copy only independently corroborated pixels, never model event labels."""
    result, requests = deepcopy(frames), []
    rejected = defaultdict(int)
    added = 0
    for row in (observations or {}).get("frames") or []:
        if not _num(row.get("media_ms")):
            continue
        matches = [f for f in result if abs(f["media_ms"] - row["media_ms"]) <= MAX_FRAME_ALIGNMENT_MS
                   and f.get("scene_id") == row.get("scene_id") and not f.get("used_fallback")
                   and not f.get("cut_barrier") and f.get("time_authority") == "ACTUAL_MEDIA_PTS"]
        # A different decoded frame is not proof at this frame's timestamp.
        frame = next((f for f in matches if f["media_ms"] == row["media_ms"]), None)
        if frame is None:
            rejected["ACTUAL_FRAME_NOT_PRESENT"] += 1
            continue
        for ball in row.get("ball_candidates") or []:
            if (ball.get("source") != "NATIVE_REVIEW_ROI_DETECTOR" or ball.get("pixel_corroborated") is not True
                    or not _num(ball.get("confidence"))
                    or scheduler._iou(ball.get("box"), ball.get("proposal_box")) < .20):
                rejected["BALL_NOT_CORROBORATED"] += 1
                continue
            import dense_track_refinement
            if ball["confidence"] < dense_track_refinement.DENSE_BALL_CONF_T or ball["box"]["w"] > .08 or ball["box"]["h"] > .04:
                rejected["DETECTOR_SCORE_OR_SIZE_FAILED"] += 1
                continue
            if any(scheduler._iou(ball.get("box"), old.get("box")) >= .5 for old in frame.get("ball_candidates") or []):
                continue
            frame.setdefault("ball_candidates", []).append(deepcopy(ball))
            added += 1
        for proposal in row.get("jersey_bodies") or []:
            player = bind_body(frame, proposal.get("box"))
            if player is not None:
                requests.append({"request_id": f"inspection_{inspection_id}_{player['local_track_id']}_{frame['media_ms']}",
                                 "media_ms": frame["media_ms"], "box": deepcopy(player["box"]),
                                 "track_id": player["local_track_id"], "review_priority": -1,
                                 "selection_rank": 1, "expected_jersey_number": None})
            else:
                rejected["BODY_NOT_UNIQUE_MEASURED_CROP"] += 1
    # Keep at most two temporally independent crops per body, using the same
    # consensus separation threshold as ordinary jersey review.
    import jersey_consensus
    selected = []
    for request in requests:
        previous = [r for r in selected if r["track_id"] == request["track_id"]]
        if len(previous) < 2 and not any(abs(r["media_ms"] - request["media_ms"]) < jersey_consensus.MIN_TEMPORAL_SEPARATION_MS
                                        for r in previous):
            request["selection_rank"] = len(previous) + 1
            selected.append(request)
    return {"frames": result, "jersey_requests": selected, "added_ball_candidates": added,
            "binding_rejections": dict(rejected)}
