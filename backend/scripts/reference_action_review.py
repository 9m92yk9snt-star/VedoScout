"""Offline reference validation. Expected outcomes never enter model jobs."""
from copy import deepcopy
import hashlib
import json

import action_evidence_review as inspection

ALLOWED = {("SHOT", "SAVED"), ("GOAL", "GOAL"), ("ASSIST", "TEAMMATE_GOAL")}


def validate_cases(cases):
    if not isinstance(cases, list) or not 1 <= len(cases) <= inspection.MAX_ACTION_REVIEWS:
        raise ValueError("Reference cases must fit the existing pixel-review budget")
    result, ids, times = [], set(), set()
    for row in cases:
        if not isinstance(row, dict):
            raise ValueError("Each reference case must be an object")
        name, ms = row.get("case_id"), row.get("reference_ms")
        expected = (row.get("expected_type"), row.get("expected_outcome"))
        tolerance = row.get("tolerance_ms", 1000)
        if not isinstance(name, str) or not name or name in ids or not inspection._num(ms) or ms < 0:
            raise ValueError("Reference IDs and nonnegative times must be unique")
        if expected not in ALLOWED or not inspection._num(tolerance) or not 0 <= tolerance <= 1500:
            raise ValueError("Invalid reference outcome or matching tolerance")
        ms = int(round(ms))
        if ms in times:
            raise ValueError("Reference IDs and nonnegative times must be unique")
        ids.add(name); times.add(ms)
        result.append({"case_id": name, "reference_ms": ms,
                       "expected_type": expected[0], "expected_outcome": expected[1], "tolerance_ms": int(tolerance)})
    return result


def build_plan(traces, cases):
    jobs, unreviewable = [], []
    for case in validate_cases(cases):
        ms = case["reference_ms"]
        available = []
        for trace in traces:
            w = trace.get("window") or {}
            if not all(inspection._num(w.get(k)) for k in ("start_ms", "end_ms")) or not w.get("scene_id"):
                continue
            if not w["start_ms"] <= ms <= w["end_ms"]:
                continue
            if any(inspection._num(f.get("media_ms")) and abs(f["media_ms"] - ms) <= 80
                   and f.get("scene_id") == w["scene_id"] and f.get("time_authority") == "ACTUAL_MEDIA_PTS"
                   and not f.get("cut_barrier") and not f.get("used_fallback") for f in trace.get("decoded_frames") or []):
                available.append(trace)
        if not available:
            unreviewable.append({"case_id": case["case_id"], "reference_ms": ms, "reason": "REFERENCE_FRAMES_UNAVAILABLE"})
            continue
        trace = max(available, key=lambda t: (t["window"]["end_ms"] - ms, ms - t["window"]["start_ms"]))
        w = trace["window"]
        job = {"dense_window_id": trace["trace_id"], "scene_id": w["scene_id"],
               "start_ms": max(w["start_ms"], ms - 750), "end_ms": min(w["end_ms"], ms + 1600),
               "center_ms": ms, "has_contact_time": True, "source_action_ids": [],
               "reason": "OPERATOR_TIME_ONLY_SEARCH", "selected": True, "selection_rank": len(jobs)}
        job["inspection_id"] = "reference_" + hashlib.sha256(json.dumps(
            [trace["trace_id"], ms, job["start_ms"], job["end_ms"]]).encode()).hexdigest()[:20]
        if len(inspection.frame_times(job, trace.get("decoded_frames") or [])) < 2:
            unreviewable.append({"case_id": case["case_id"], "reference_ms": ms, "reason": "REFERENCE_FRAMES_INSUFFICIENT"})
        else:
            jobs.append(job)
    return {"budget": inspection.MAX_ACTION_REVIEWS, "selected": len(jobs), "deferred": 0,
            "jobs": jobs, "unreviewable": unreviewable, "mode": "OFFLINE_REFERENCE_REVIEW"}


def search_hints(plan):
    """Only times/scenes influence offline review scheduling, never expectations."""
    return {"sequences": [{"scene_id": j["scene_id"], "actions": [{"start_ms": j["center_ms"],
        "end_ms": j["center_ms"], "contact_ms": j["center_ms"]}]} for j in plan["jobs"]]}


def assess(cases, canonical, physical, plan):
    events = [e for e in (canonical or {}).get("events") or [] if isinstance(e, dict)]
    qualified = [e for e in events if e.get("global_target_id") == "GLOBAL_TARGET"
                 and e.get("causal_verified") is True and (e.get("proof") or {}).get("proof_eligible") is True
                 and ((e.get("proof") or {}).get("fix10b_physical") or {}).get("proof_eligible") is True]
    results, used = [], set()
    for case in validate_cases(cases):
        ms = case["reference_ms"]
        job = next((j for j in plan["jobs"] if j["center_ms"] == ms), None)
        scene = job.get("scene_id") if job else None
        trace = next((t for t in physical.get("traces") or [] if job and t["trace_id"] == job["dense_window_id"]), {})
        candidates = [e for e in qualified if e.get("event_id") and e["event_id"] not in used
                      and inspection._num(e.get("canonical_ms")) and abs(e["canonical_ms"] - ms) <= case["tolerance_ms"]
                      and e.get("scene_id") == scene and e.get("canonical_event_type") == case["expected_type"]
                      and e.get("canonical_outcome") == case["expected_outcome"]]
        event = min(candidates, key=lambda e: abs(e["canonical_ms"] - ms), default=None)
        if event:
            used.add(event["event_id"])
        inspections = [r for r in trace.get("action_inspections") or [] if job and r.get("inspection_id") == job["inspection_id"]]
        near = lambda row: inspection._num(row.get("media_ms")) and ms - 1000 <= row["media_ms"] <= ms + 1600
        unavailable = next((r["reason"] for r in plan.get("unreviewable") or [] if r["case_id"] == case["case_id"]), None)
        results.append({**case, "status": "PASS" if event else "NOT_VERIFIED",
                        "failure_reason": None if event else unavailable or "QUALIFIED_CANONICAL_EVENT_MISSING",
                        "event_id": event.get("event_id") if event else None,
                        "event_ms": event.get("canonical_ms") if event else None,
                        "inspection_status": inspections[-1].get("status") if inspections else "NOT_EXECUTED",
                        "source_trace_id": trace.get("trace_id"),
                        "nearby_contacts": [{k: c.get(k) for k in ("media_ms", "contact_id", "player_track_id", "status", "proof_eligible")}
                                            for c in (trace.get("contacts") or {}).get("contacts") or [] if near(c)],
                        "nearby_touches": [{k: t.get(k) for k in ("media_ms", "touch_id", "player_track_id", "global_target_id", "status", "proof_eligible", "contact_role")}
                                           for t in (trace.get("touch_graph") or {}).get("touches") or [] if near(t)],
                        "nearby_strikes": [{k: s.get(k) for k in ("media_ms", "strike_id", "player_track_id", "global_target_id", "status", "contact_role")}
                                           for s in trace.get("strike_evidence") or [] if near(s)],
                        "nearby_outcomes": [{k: o.get(k) for k in ("media_ms", "strike_id", "physical_outcome", "goal_review_eligibility", "goal_plane_crossing", "save")}
                                            for o in trace.get("outcome_evidence") or [] if near(o)],
                        "unresolved_reasons": deepcopy(trace.get("unresolved_reasons") or [])})
    return {"all_verified": all(r["status"] == "PASS" for r in results),
            "verified": sum(r["status"] == "PASS" for r in results), "requested": len(results),
            "canonical_authority": False, "expected_outcomes_supplied_to_models": False, "cases": results}
