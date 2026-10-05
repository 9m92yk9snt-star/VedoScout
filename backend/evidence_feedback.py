"""One bounded inspection round driven by observed gaps, never desired events."""
from collections import defaultdict
from copy import deepcopy
import hashlib
import json
import os

import action_evidence_review as inspection
import goal_review_scheduler as scheduler

MAX_FEEDBACK_REVIEWS = min(8, max(0, int(os.environ.get("FIX13_MAX_FEEDBACK_REVIEWS", "4"))))


def gaps(trace):
    trajectory = {b.get("media_ms"): b for b in trace.get("ball_trajectory") or []}
    return {
        "identity_frames": sum((f.get("global_target") or {}).get("proof_eligible") is not True
                               for f in trace.get("decoded_frames") or []),
        "unresolved_contacts": len((trace.get("contacts") or {}).get("unresolved") or []),
        "verified_contacts": len((trace.get("contacts") or {}).get("accepted") or []),
        "unresolved_outcomes": sum(str(o.get("physical_outcome") or "").startswith("UNRESOLVED")
                                   for o in trace.get("outcome_evidence") or []),
        "target_ball_frames": sum((f.get("global_target") or {}).get("proof_eligible") is True
                                  and (trajectory.get(f.get("media_ms")) or {}).get("proof_eligible") is not True
                                  for f in trace.get("decoded_frames") or []),
    }


def build_plan(traces, budget=None, analysis=None):
    limit = MAX_FEEDBACK_REVIEWS if budget is None else min(8, max(0, int(budget)))
    candidates, rejected = [], []
    hints = defaultdict(list)
    for sequence in (analysis or {}).get("sequences") or []:
        for action in sequence.get("actions") or []:
            ms = action.get("contact_ms")
            if not inspection._num(ms) and all(inspection._num(action.get(k)) for k in ("start_ms", "end_ms")):
                ms = (action["start_ms"] + action["end_ms"]) / 2
            if inspection._num(ms):
                hints[sequence.get("scene_id")].append(ms)
    for trace in traces:
        window = trace.get("window") or {}
        if trace.get("evidence_feedback"):
            continue  # a feedback result cannot open another round
        frames = sorted([f for f in trace.get("decoded_frames") or []
                         if inspection._num(f.get("media_ms"))], key=lambda f: f["media_ms"])
        if not frames or not window.get("scene_id"):
            continue
        valid = lambda f: f.get("scene_id") == window["scene_id"] and not f.get("cut_barrier") \
            and not f.get("used_fallback") and f.get("time_authority") == "ACTUAL_MEDIA_PTS"
        centers = []
        strikes = {s.get("strike_id"): s for s in trace.get("strike_evidence") or []}
        for outcome in trace.get("outcome_evidence") or []:
            strike = strikes.get(outcome.get("strike_id")) or {}
            relevant = strike.get("global_target_id") == "GLOBAL_TARGET" \
                or (outcome.get("goal_review_eligibility") or {}).get("eligible") is True
            if relevant and str(outcome.get("physical_outcome") or "").startswith("UNRESOLVED"):
                release = strike.get("status") == "VERIFIED_PHYSICAL_RELEASE"
                centers.append((1 if release else 2, outcome.get("media_ms"), "OUTCOME_CONTACT_GAP"))
        for contact in (trace.get("contacts") or {}).get("unresolved") or []:
            centers.append((1, contact.get("media_ms"), "PHYSICAL_CONTACT_GAP"))
        if gaps(trace)["target_ball_frames"]:
            path = {b.get("media_ms"): b for b in trace.get("ball_trajectory") or []}
            for touch in (trace.get("touch_graph") or {}).get("touches") or []:
                ms = touch.get("media_ms")
                if touch.get("global_target_id") == "GLOBAL_TARGET" and inspection._num(ms) and any(
                        ms - 180 <= f["media_ms"] <= ms + 350
                        and (f.get("global_target") or {}).get("proof_eligible") is True
                        and (path.get(f["media_ms"]) or {}).get("proof_eligible") is not True for f in frames):
                    centers.append((0, ms, "TARGET_RELEASE_OR_BALL_GAP"))
        if gaps(trace)["identity_frames"] or not (trace.get("contacts") or {}).get("accepted"):
            for job in trace.get("action_inspections") or []:
                if job.get("selected") and job.get("status") not in {"ERROR", "UNAVAILABLE", "NOT_CONFIGURED", "DEFERRED"}:
                    centers.append((2, job.get("center_ms"), "IDENTITY_OR_CONTACT_GAP"))
        # Retry the most specific physical gap per window. No action kind or
        # expected jersey/goal/assist is supplied to the inspection reader.
        search_times = hints[window["scene_id"]] + [j["center_ms"] for j in trace.get("action_inspections") or []
                                                   if inspection._num(j.get("center_ms"))]
        def candidate_priority(candidate):
            rank, ms, _ = candidate
            distance = min((abs(ms - hint) for hint in search_times), default=0) if inspection._num(ms) else float("inf")
            return rank, distance, ms if inspection._num(ms) else -1
        for priority, center, reason in sorted(centers, key=candidate_priority):
            if not inspection._num(center):
                continue
            index = min(range(len(frames)), key=lambda i: abs(frames[i]["media_ms"] - center))
            if not valid(frames[index]) or abs(frames[index]["media_ms"] - center) > 80:
                continue
            left = right = index
            while left and frames[left - 1]["media_ms"] >= center - 350 and valid(frames[left - 1]) \
                    and frames[left]["media_ms"] - frames[left - 1]["media_ms"] <= 80:
                left -= 1
            while right + 1 < len(frames) and frames[right + 1]["media_ms"] <= center + 700 and valid(frames[right + 1]) \
                    and frames[right + 1]["media_ms"] - frames[right]["media_ms"] <= 80:
                right += 1
            start, end = frames[left]["media_ms"], frames[right]["media_ms"]
            if end - start < 150:
                continue
            job = {"dense_window_id": trace["trace_id"], "scene_id": window["scene_id"],
                   "start_ms": int(start), "end_ms": int(end), "center_ms": int(center),
                   "has_contact_time": True, "source_action_ids": [], "phase": "FEEDBACK",
                   "reason": reason, "priority": priority, "before": gaps(trace)}
            requested = inspection.frame_times(job, frames)
            if any(requested == old.get("requested_media_ms") for old in trace.get("action_inspections") or []):
                rejected.append({"trace_id": trace["trace_id"], "reason": "NO_NEW_REVIEW_INPUT", "center_ms": center})
                continue
            job["inspection_id"] = "feedback_" + hashlib.sha256(json.dumps(
                [trace["trace_id"], reason, start, end, requested]).encode()).hexdigest()[:20]
            candidates.append(job)
            break
    cells = defaultdict(list)
    for job in candidates:
        cells[(job["scene_id"], job["center_ms"] // scheduler.TIME_CELL_MS)].append(job)
    for jobs in cells.values():
        jobs.sort(key=lambda j: (j["priority"], j["center_ms"]))
    ordered, visited = [], set()
    while cells:
        available = [c for c in cells if c not in visited] or list(cells)
        def priority(cell):
            job = cells[cell][0]
            distance = min((abs(job["center_ms"] - old["center_ms"]) for old in ordered), default=0)
            return (job["priority"], -distance, job["center_ms"])
        cell = min(available, key=priority)
        visited.add(cell)
        job = deepcopy(cells[cell].pop(0))
        job.update(selected=len(ordered) < limit, selection_rank=len(ordered))
        ordered.append(job)
        if not cells[cell]:
            del cells[cell]
    return {"budget": limit, "rounds": 1, "selected": sum(j["selected"] for j in ordered),
            "deferred": sum(not j["selected"] for j in ordered), "jobs": ordered, "rejected": rejected}
