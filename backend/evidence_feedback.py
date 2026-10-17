"""One bounded inspection round driven by observed gaps, never desired events."""
from collections import defaultdict
from copy import deepcopy
import hashlib
import json
import os

import action_evidence_review as inspection
import goal_review_scheduler as scheduler
import attack_sequence_search
import sequence_observation_context

MAX_FEEDBACK_REVIEWS = min(8, max(0, int(os.environ.get("FIX13_MAX_FEEDBACK_REVIEWS", "8"))))


def _target_contact_search(contact, frames, scene):
    """A measured target body can focus a search while its touch stays unproved."""
    ms = contact.get("media_ms")
    if not inspection._num(ms) or contact.get("time_authority") != "ACTUAL_MEDIA_PTS":
        return False
    available = [f for f in frames if f.get("scene_id") == scene
                 and f.get("time_authority") == "ACTUAL_MEDIA_PTS"
                 and not f.get("cut_barrier") and not f.get("used_fallback")]
    frame = min(available, key=lambda f: abs(f["media_ms"] - ms), default=None)
    if frame is None or abs(frame["media_ms"] - ms) > inspection.MAX_FRAME_ALIGNMENT_MS:
        return False
    target = frame.get("global_target") or {}
    track = target.get("local_track_id")
    return bool(target.get("status") == "VERIFIED" and target.get("proof_eligible") is True
                and isinstance(track, str) and track
                and (track == contact.get("player_track_id")
                     or track in (contact.get("player_candidate_track_ids") or [])))


def gaps(trace):
    trajectory = {b.get("media_ms"): b for b in trace.get("ball_trajectory") or []}
    return {
        "identity_frames": sum((f.get("global_target") or {}).get("proof_eligible") is not True
                               for f in trace.get("decoded_frames") or []),
        "unresolved_contacts": len((trace.get("contacts") or {}).get("unresolved") or []),
        "verified_contacts": len((trace.get("contacts") or {}).get("accepted") or []),
        "unresolved_outcomes": sum(str(o.get("physical_outcome") or "").startswith("UNRESOLVED")
                                   and (o.get("goal_geometry_evidence") or {}).get("reason") != "OUTCOME_ALREADY_RESOLVED_FROM_SOURCE_CLIP"
                                   for o in trace.get("outcome_evidence") or []),
        "target_ball_frames": sum((f.get("global_target") or {}).get("proof_eligible") is True
                                  and (trajectory.get(f.get("media_ms")) or {}).get("proof_eligible") is not True
                                  for f in trace.get("decoded_frames") or []),
        "uninspected_frames": len({ms for job in trace.get("action_inspections") or []
                                    if job.get("selected") and job.get("status") == "PARTIAL_RESPONSE"
                                    for ms in job.get("missing_media_ms") or [] if inspection._num(ms)}),
    }


def build_plan(traces, budget=None, analysis=None):
    limit = MAX_FEEDBACK_REVIEWS if budget is None else min(8, max(0, int(budget)))
    candidates, rejected = [], []
    hints = defaultdict(list)
    requests = {id(t): sequence_observation_context.model_requests(t) + attack_sequence_search.questions(t) for t in traces}
    shared_requests = defaultdict(list)
    for trace in traces:
        sha = (trace.get("source_video") or {}).get("sha256")
        if sha:
            shared_requests[(sha, (trace.get("window") or {}).get("scene_id"))].extend(requests[id(trace)])
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
        before = gaps(trace)
        valid = lambda f: f.get("scene_id") == window["scene_id"] and not f.get("cut_barrier") \
            and not f.get("used_fallback") and f.get("time_authority") == "ACTUAL_MEDIA_PTS"
        sha = (trace.get("source_video") or {}).get("sha256")
        centers = sequence_observation_context.requested_centers(trace, frames,
            shared_requests.get((sha, window["scene_id"]), []) if sha else attack_sequence_search.questions(trace))
        motion_requests = [r for r in requests[id(trace)] if r.get("search_protocol") == "SOURCE_INDEXED_MOTION_CLIP_V1"]
        for job in trace.get("action_inspections") or []:
            if job.get("selected") and job.get("status") == "PARTIAL_RESPONSE":
                centers.extend((1, ms, "PIXEL_RESPONSE_COVERAGE_GAP")
                               for ms in job.get("missing_media_ms") or [] if inspection._num(ms))
        strikes = {s.get("strike_id"): s for s in trace.get("strike_evidence") or []}
        for outcome in trace.get("outcome_evidence") or []:
            if (outcome.get("goal_geometry_evidence") or {}).get("reason") == "OUTCOME_ALREADY_RESOLVED_FROM_SOURCE_CLIP":
                continue
            strike = strikes.get(outcome.get("strike_id")) or {}
            relevant = strike.get("global_target_id") == "GLOBAL_TARGET" \
                or (outcome.get("goal_review_eligibility") or {}).get("eligible") is True
            if relevant and str(outcome.get("physical_outcome") or "").startswith("UNRESOLVED"):
                release = strike.get("status") == "VERIFIED_PHYSICAL_RELEASE"
                centers.append((0 if release else 2, outcome.get("media_ms"), "OUTCOME_CONTACT_GAP"))
        # A native release must be inspectable before target ownership is known.
        # Opening a crop search supplies neither an identity nor a shot outcome.
        for strike in trace.get("strike_evidence") or []:
            if (strike.get("status") == "VERIFIED_PHYSICAL_RELEASE"
                    and strike.get("proof_eligible") is True
                    and strike.get("global_target_id") != "GLOBAL_TARGET"):
                centers.append((1, strike.get("media_ms"), "PHYSICAL_RELEASE_IDENTITY_GAP"))
        for contact in (trace.get("contacts") or {}).get("unresolved") or []:
            focused = _target_contact_search(contact, frames, window["scene_id"])
            centers.append((0 if focused else 2, contact.get("media_ms"),
                            "TARGET_CONTACT_EVIDENCE_GAP" if focused else "PHYSICAL_CONTACT_GAP"))
        if before["target_ball_frames"]:
            path = {b.get("media_ms"): b for b in trace.get("ball_trajectory") or []}
            for touch in (trace.get("touch_graph") or {}).get("touches") or []:
                ms = touch.get("media_ms")
                if touch.get("global_target_id") == "GLOBAL_TARGET" and inspection._num(ms) and any(
                        ms - 180 <= f["media_ms"] <= ms + 350
                        and (f.get("global_target") or {}).get("proof_eligible") is True
                        and (path.get(f["media_ms"]) or {}).get("proof_eligible") is not True for f in frames):
                    role = touch.get("contact_role") or {}
                    release = isinstance(role, dict) and role.get("status") == "VERIFIED" and role.get("role") == "RELEASE"
                    centers.append((0 if release else 3, ms, "TARGET_RELEASE_OR_BALL_GAP"))
        if before["identity_frames"] or not (trace.get("contacts") or {}).get("accepted"):
            for job in trace.get("action_inspections") or []:
                if job.get("reason") == "SOURCE_SEQUENCE_ALREADY_RESOLVED":
                    continue
                summary = trace.get("motion_observation_summary") or {}
                if (job.get("observation_protocol") == "SOURCE_INDEXED_MOTION_CLIP_V1"
                        and job.get("clip_review_complete") is True and summary.get("counts")
                        and not summary.get("unresolved") and not summary.get("rejected")):
                    continue  # a resolved full play needs no generic identity re-read
                if job.get("selected") and job.get("status") not in {"ERROR", "UNAVAILABLE", "NOT_CONFIGURED", "DEFERRED"}:
                    centers.append((3, job.get("center_ms"), "IDENTITY_OR_CONTACT_GAP"))
        # Retry the most specific physical gap per window. No action kind or
        # expected jersey/goal/assist is supplied to the inspection reader.
        search_times = hints[window["scene_id"]] + [j["center_ms"] for j in trace.get("action_inspections") or []
                                                   if inspection._num(j.get("center_ms"))]
        def candidate_priority(candidate):
            rank, ms, _ = candidate
            distance = min((abs(ms - hint) for hint in search_times), default=0) if inspection._num(ms) else float("inf")
            return rank, distance, ms if inspection._num(ms) else -1
        selected_searches = []
        for priority, center, reason in sorted(set(centers), key=candidate_priority):
            if selected_searches and (priority >= 0 or any(abs(center-old) < 700 for old in selected_searches)):
                continue
            if not inspection._num(center):
                continue
            index = min(range(len(frames)), key=lambda i: abs(frames[i]["media_ms"] - center))
            if not valid(frames[index]) or abs(frames[index]["media_ms"] - center) > 80:
                continue
            specific = next((r for r in motion_requests
                if reason == "MODEL_SEQUENCE_"+r["question"] and abs(center-r["media_ms"]-
                    (250 if r.get("direction") == "AFTER" else -150 if r.get("direction") == "BEFORE" else 0)) <= 80), None)
            # A receiver/outcome search keeps the original passer and later
            # finish in context. The previous fixed +700 ms crop often ended
            # before the teammate's shot. Reuse the already decoded scene.
            chain_search = specific and specific["question"] in {"CONTACT", "RECEIVER", "SHOT", "OUTCOME"}
            anchor = specific.get("anchor_media_ms", center) if specific else center
            if specific and specific["question"] == "CONTACT":
                desired_end = min(frames[-1]["media_ms"], anchor+350)
                desired_start = max(frames[0]["media_ms"], desired_end-8000)
            else:
                desired_start = min(anchor-400, center-350) if chain_search else center-350
                desired_end = min(frames[-1]["media_ms"], desired_start+8000) if chain_search else center+700
            left = right = index
            while left and frames[left - 1]["media_ms"] >= desired_start and valid(frames[left - 1]) \
                    and frames[left]["media_ms"] - frames[left - 1]["media_ms"] <= 80:
                left -= 1
            while right + 1 < len(frames) and frames[right + 1]["media_ms"] <= desired_end and valid(frames[right + 1]) \
                    and frames[right + 1]["media_ms"] - frames[right]["media_ms"] <= 80:
                right += 1
            start, end = frames[left]["media_ms"], frames[right]["media_ms"]
            if end - start < 150:
                continue
            job = {"dense_window_id": trace["trace_id"], "scene_id": window["scene_id"],
                   "start_ms": int(start), "end_ms": int(end), "center_ms": int(center),
                   "has_contact_time": not (specific and specific["question"] == "CONTACT"),
                   "source_action_ids": [], "phase": "FEEDBACK",
                   "reason": reason, "priority": priority, "before": before}
            if specific:
                job.update(missing_link_question=specific["question"], anchor_media_ms=anchor,
                    focus_track_id=specific.get("focus_track_id"),
                    search_centers_ms=[specific["media_ms"], anchor])
            requested = inspection.motion_frame_times(job, frames) if specific else inspection.frame_times(job, frames)
            if any(requested == old.get("requested_media_ms") and (not specific or
                    old.get("missing_link_question") == specific["question"]
                    and old.get("anchor_media_ms") == anchor and old.get("focus_track_id") == specific.get("focus_track_id"))
                    for old in trace.get("action_inspections") or []):
                rejected.append({"trace_id": trace["trace_id"], "reason": "NO_NEW_REVIEW_INPUT", "center_ms": center})
                continue
            job["inspection_id"] = "feedback_" + hashlib.sha256(json.dumps(
                [trace["trace_id"], reason, start, end, requested]).encode()).hexdigest()[:20]
            job["requested_media_ms"] = requested
            candidates.append(job)
            selected_searches.append(center)
            if specific or priority >= 0 or len(selected_searches) >= 2:
                break
    # Overlapping dense/recall windows can request the identical source pixels.
    # Keep the most specific search once, rather than spending two reader calls.
    unique, seen_inputs = [], set()
    for job in sorted(candidates, key=lambda j: (j["priority"], j["center_ms"], j["dense_window_id"])):
        signature = (job["scene_id"], tuple(job["requested_media_ms"]))
        if signature in seen_inputs:
            rejected.append({"trace_id": job["dense_window_id"], "center_ms": job["center_ms"],
                             "reason": "OVERLAPPING_FEEDBACK_PIXELS_ALREADY_SCHEDULED"})
            continue
        seen_inputs.add(signature)
        unique.append(job)
    cells = defaultdict(list)
    for job in unique:
        cells[(job["scene_id"], job["center_ms"] // scheduler.TIME_CELL_MS)].append(job)
    for jobs in cells.values():
        jobs.sort(key=lambda j: (j["priority"], j["center_ms"]))
    ordered, visited, visited_scenes = [], set(), set()
    while cells:
        available = ([c for c in cells if c[0] not in visited_scenes]
                     or [c for c in cells if c not in visited] or list(cells))
        def priority(cell):
            job = cells[cell][0]
            distance = min((abs(job["center_ms"] - old["center_ms"]) for old in ordered), default=0)
            return (job["priority"], -distance, job["center_ms"])
        cell = min(available, key=priority)
        visited.add(cell)
        visited_scenes.add(cell[0])
        job = deepcopy(cells[cell].pop(0))
        job.update(selected=len(ordered) < limit, selection_rank=len(ordered))
        ordered.append(job)
        if not cells[cell]:
            del cells[cell]
    return {"budget": limit, "rounds": 1, "selected": sum(j["selected"] for j in ordered),
            "deferred": sum(not j["selected"] for j in ordered), "jobs": ordered, "rejected": rejected}
