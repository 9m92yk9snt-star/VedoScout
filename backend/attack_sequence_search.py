"""Bidirectional attack search from existing contacts and terminal observations.

All plans choose where to inspect. A backward edge is a search relationship,
not a proved pass, assist, same-ball link or target identity.
"""
from copy import deepcopy

import sequence_observation_context as observations


def segments(trace):
    scene = (trace.get("window") or {}).get("scene_id")
    by_ms = {}
    for f in trace.get("decoded_frames") or []:
        if not observations.num(f.get("media_ms")):
            continue
        ms = f["media_ms"]
        # Conflicting duplicate source images are a barrier, not two votes.
        if ms in by_ms and by_ms[ms] != f:
            by_ms[ms] = {"media_ms": ms}
        else:
            by_ms[ms] = f
    result, current = [], []
    for ms, f in sorted(by_ms.items()):
        valid = observations.actual(f, scene)
        if not valid or current and ms-current[-1]["media_ms"] > 80:
            if current:
                result.append(current)
            current = []
        if valid:
            current.append(f)
    if current:
        result.append(current)
    return result


def build(trace):
    window = trace.get("window") or {}
    scene = window.get("scene_id")
    pieces = segments(trace)
    contacts = sorted([t for t in (trace.get("touch_graph") or {}).get("touches") or []
                       if t.get("status") == "VERIFIED" and t.get("proof_eligible") is True
                       and t.get("scene_id") == scene and observations.num(t.get("media_ms"))],
                      key=lambda t: t["media_ms"])
    outcomes = {o.get("strike_id"): o for o in trace.get("outcome_evidence") or []}
    episodes, questions = [], []
    for strike in trace.get("strike_evidence") or []:
        ms = strike.get("media_ms")
        if (not observations.num(ms) or strike.get("scene_id") != scene or strike.get("proof_eligible") is not True
                or strike.get("status") not in {"VERIFIED_PHYSICAL_RELEASE", "VERIFIED_PHYSICAL_SCORING_CONTACT"}):
            continue
        piece = next((p for p in pieces if p[0]["media_ms"] <= ms <= p[-1]["media_ms"]), None)
        if not piece or not any(abs(f["media_ms"]-ms) <= 20 for f in piece):
            continue
        start, end = piece[0]["media_ms"], piece[-1]["media_ms"]
        outcome = outcomes.get(strike.get("strike_id")) or {}
        if (outcome.get("goal_geometry_evidence") or {}).get("reason") == "OUTCOME_ALREADY_RESOLVED_FROM_SOURCE_CLIP":
            continue  # the same observed finish needs no second forward/backward search
        crossing = outcome.get("goal_plane_crossing") or {}
        terminal = crossing.get("crossing_ms") if crossing.get("status") == "VERIFIED" else None
        if observations.num(terminal) and ms <= terminal <= end:
            end = min(end, terminal+400)
        local = [t for t in contacts if start <= t["media_ms"] <= end]
        before = [t for t in local if t["media_ms"] < ms]
        after = [t for t in local if t["media_ms"] > ms]
        episode = {"strike_id": strike.get("strike_id"), "contact_ms": ms,
            "start_ms": start, "end_ms": end, "scene_id": scene,
            "strategy": "FORWARD_FROM_CONTACT_AND_BACKWARD_FROM_TERMINAL",
            "backward_contacts": [t.get("touch_id") for t in before[-8:]],
            "forward_contacts": [t.get("touch_id") for t in after[:8]],
            "terminal_observed_ms": terminal, "canonical_authority": False}
        episodes.append(episode)
        actual_ms = min((f["media_ms"] for f in piece), key=lambda t: abs(t-ms))
        target_known = strike.get("global_target_id") == "GLOBAL_TARGET"
        utility = 2 + 2*target_known + 3*(terminal is not None)
        if not target_known and terminal is not None:
            questions.append({"media_ms": actual_ms, "question": "IDENTITY", "direction": "AROUND",
                "source": "MEASURED_CHAIN_SEARCH", "utility": utility, "canonical_authority": False,
                "reason": "CONTACT_OBSERVED_ACTOR_UNRESOLVED", "strike_id": strike.get("strike_id")})
        if target_known and terminal is None:
            next_other = next((t for t in after if t.get("player_track_id") != strike.get("player_track_id")), None)
            pivot = next_other["media_ms"] if next_other else actual_ms
            questions.append({"media_ms": pivot, "question": "RECEIVER" if next_other else "OUTCOME",
                "direction": "AROUND" if next_other else "AFTER", "source": "MEASURED_CHAIN_SEARCH",
                "utility": utility, "canonical_authority": False, "reason": "FOLLOW_TARGET_RELEASE",
                "strike_id": strike.get("strike_id")})
        if terminal is not None:
            # Search back from an observed end even when the earlier passer's
            # identity/contact role was not available on the first pass.
            previous_actor = next((t for t in reversed(before)
                if t.get("player_track_id") != strike.get("player_track_id")), None)
            if previous_actor:
                questions.append({"media_ms": previous_actor["media_ms"], "question": "CONTACT",
                    "direction": "AROUND", "source": "MEASURED_CHAIN_SEARCH", "utility": utility+1,
                    "canonical_authority": False, "reason": "BACKTRACK_FROM_OBSERVED_TERMINAL",
                    "strike_id": strike.get("strike_id")})
    # Same observed question is asked once; a richer measured chain leads.
    unique = {}
    for q in sorted(questions, key=lambda q: (-q["utility"], q["media_ms"], q["question"])):
        unique.setdefault((q["media_ms"], q["question"]), q)
    return {"source": "MEASURED_ATTACK_SEARCH", "canonical_authority": False,
            "episodes": episodes, "questions": list(unique.values())}


def review_context(trace, strike, plan=None):
    plan = plan if isinstance(plan, dict) else build(trace)
    episode = next((e for e in plan["episodes"] if e["strike_id"] == strike.get("strike_id")), None)
    if episode is None:
        return None
    return {"start_ms": max(episode["start_ms"], strike["media_ms"]-150),
            "end_ms": episode["end_ms"], "media_ms": strike["media_ms"],
            "source": "CONTIGUOUS_MEASURED_ATTACK_CONTEXT", "canonical_authority": False}


def questions(trace):
    return deepcopy(build(trace)["questions"])
