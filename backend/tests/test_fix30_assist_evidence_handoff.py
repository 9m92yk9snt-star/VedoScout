"""Use existing event-local evidence consistently across the scoring chain."""
from copy import deepcopy

import pytest

import cross_window_evidence as overlap
import fix10b_reconciliation as recon
import test_fix10b_reconciliation as events
import test_fix13_cross_window_evidence as windows

BOX = {"x": .3, "y": .4, "w": .1, "h": .2}


def local_team_case(split=False):
    target = events.strike(1000, "target", target=True)
    scorer = events.strike(2200, "finisher" if split else "receiver")
    touches = [events.touch(1000, "target", target=True), events.touch(1500, "receiver"),
               events.touch(2200, scorer["player_track_id"])]
    for touch in touches[1:]:
        touch["team_relation"] = {"status": "UNRESOLVED", "team": None,
                                  "reason": "CONFLICTING_DENSE_TEAM_LABELS"}
        touch["contact_geometry"] = {"actor_box_used": deepcopy(BOX)}
    trace = events.trace(touches, [target, scorer],
                         [events.outcome(target, goal=False), events.outcome(scorer, crossing_ms=2600)])
    trace["decoded_frames"] = []
    for ms in (1480, 1500, 1520, 1800, 1950, 2180, 2200, 2220):
        trace["decoded_frames"].append({"media_ms": ms, "scene_id": "scene_007",
            "time_authority": "ACTUAL_MEDIA_PTS", "used_fallback": False,
            "players": [{"local_track_id": "finisher" if split and ms >= 1950 else "receiver",
                "association_state": "VERIFIED_LOCAL", "box": deepcopy(BOX),
                "team": "target_team", "team_confidence": .92, "team_source": "NATIVE_KIT_PIXELS"}]})
    return trace


@pytest.mark.parametrize("split", [False, True])
def test_local_receiver_and_finisher_team_evidence_can_complete_the_same_assist(split):
    trace = local_team_case(split)
    original = deepcopy(trace)
    proposals = recon.proposals_from_trace(trace)
    assists = [p for p in proposals if p["kind"] == "ASSIST"]
    assert len(assists) == 1
    assert assists[0]["receiver_team_evidence"]["source"] == "TIME_LOCAL_EVENT_BODY_TEAM"
    assert trace == original
    canonical = recon.reconcile_canonical_events(events.canonical([]), events.physical([trace]))
    assert canonical["counts"]["ASSIST"] == 1 and not canonical["counts"].get("GOAL")


@pytest.mark.parametrize("failure", ["opponent", "wrong_body", "sparse", "conflicting", "fallback", "cut", "requested_pts", "duplicate_pts", "unverified_goal"])
def test_local_team_reuse_does_not_guess_an_assist(failure):
    trace = local_team_case()
    if failure == "unverified_goal":
        trace["outcome_evidence"][-1] = events.outcome(trace["strike_evidence"][-1], goal=False)
    elif failure == "sparse":
        trace["decoded_frames"] = trace["decoded_frames"][:1]
    elif failure == "duplicate_pts":
        trace["decoded_frames"] = [deepcopy(trace["decoded_frames"][0]) for _ in range(3)]
    elif failure == "conflicting":
        trace["decoded_frames"][1]["players"][0]["team"] = "opponent"
    else:
        for frame in trace["decoded_frames"]:
            if failure == "opponent": frame["players"][0]["team"] = "opponent"
            elif failure == "wrong_body": frame["players"][0]["box"]["x"] = .8
            elif failure == "fallback": frame["used_fallback"] = True
            elif failure == "cut": frame["cut_barrier"] = True
            elif failure == "requested_pts": frame["time_authority"] = "REQUESTED_TIME"
    assert not any(p["kind"] == "ASSIST" for p in recon.proposals_from_trace(trace))


@pytest.mark.parametrize("flag", ["cut", "cut_barrier"])
def test_a_receiver_track_split_cannot_cross_a_real_source_cut(flag):
    trace = local_team_case(split=True)
    next(frame for frame in trace["decoded_frames"] if frame["media_ms"] == 1800)[flag] = True
    assert not any(p["kind"] == "ASSIST" for p in recon.proposals_from_trace(trace))


def test_cross_window_control_finish_keeps_its_verified_ball_anchor():
    traces = windows.cases()
    scorer = traces[1]["strike_evidence"][0]
    scorer["status"] = "VERIFIED_PHYSICAL_SCORING_CONTACT"
    scorer["active_ball_anchor"]["source"] = "VERIFIED_SCORING_CONTROL_BALL_AFTER"
    result = recon.collect_proposals({"traces": traces})
    assert len([p for p in result if p["kind"] == "ASSIST"]) == 1
    assert any(s.get("cross_window_ball_anchor_eligible") for c in overlap.build({"traces": traces})["contexts"]
               for s in c["strike_evidence"] if s.get("native_source_trace_id") == "right")


@pytest.mark.parametrize("failure", ["wrong_source", "unmeasured", "spare_ball", "gap"])
def test_cross_window_control_finish_cannot_lose_its_ball_binding(failure):
    traces = windows.cases()
    scorer = traces[1]["strike_evidence"][0]
    scorer["status"] = "VERIFIED_PHYSICAL_SCORING_CONTACT"
    anchor = scorer["active_ball_anchor"]
    anchor["source"] = "VERIFIED_SCORING_CONTROL_BALL_AFTER"
    if failure == "wrong_source": anchor["source"] = "MODEL_STORY"
    elif failure == "unmeasured": anchor["proof_eligible"] = False
    elif failure == "spare_ball": anchor["box"]["x"] = .9
    elif failure == "gap": traces[1]["ball_trajectory"][8]["proof_eligible"] = False
    assert not any(p["kind"] == "ASSIST" for p in recon.collect_proposals({"traces": traces}))
