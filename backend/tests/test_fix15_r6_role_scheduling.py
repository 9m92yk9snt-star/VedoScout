"""Role search scheduling is not role, team or event proof."""
from copy import deepcopy

import pytest
import fix10a_vision_providers as fvp


def frame(ms, track):
    return {"media_ms": ms, "time_authority": "ACTUAL_MEDIA_PTS", "used_fallback": False,
            "players": [{"local_track_id": track, "association_state": "VERIFIED_LOCAL",
                         "box": {"x": .2, "y": .2, "w": .2, "h": .4}}]}


def intervention(track, ms):
    return {"status": "VERIFIED", "proof_eligible": True, "player_track_id": track,
            "media_ms": ms, "scene_id": "synthetic"}


def strike(ms, target=False):
    return {"status": "VERIFIED_PHYSICAL_RELEASE", "proof_eligible": True,
            "player_track_id": "kicker", "media_ms": ms, "scene_id": "synthetic",
            "global_target_id": "GLOBAL_TARGET" if target else None}


def test_unreadable_actor_does_not_consume_track_budget(monkeypatch):
    monkeypatch.setattr(fvp, "MAX_ROLE_TRACKS", 2)
    requests = fvp._role_review_requests([frame(1100, "readable_1"), frame(1200, "readable_2")],
                                       {"no_crop": 1000, "readable_1": 1100, "readable_2": 1200})
    assert {r["track_id"] for r in requests} == {"readable_1", "readable_2"}


def test_hypothesis_fallback_tiny_and_wrong_time_crops_do_not_consume_budget(monkeypatch):
    monkeypatch.setattr(fvp, "MAX_ROLE_TRACKS", 1)
    rows = [frame(1100, t) for t in ("hypothesis", "fallback", "tiny", "wrong_pts", "usable")]
    rows[0]["players"][0]["association_state"] = "HYPOTHESES"
    rows[1]["used_fallback"] = True
    rows[2]["players"][0]["box"]["w"] = .001
    rows[3]["time_authority"] = "SYNTHETIC_FRAME_INDEX"
    requests = fvp._role_review_requests(rows, {t: 1100 for t in
        ("hypothesis", "fallback", "tiny", "wrong_pts", "usable")})
    assert {r["track_id"] for r in requests} == {"usable"}


def test_verified_target_parent_has_search_priority_not_role_authority():
    strikes = [strike(900), strike(1200), strike(1500, True)]
    interventions = [intervention("early", 1000), intervention("middle", 1300),
                     intervention("target_chain_actor", 1600)]
    before = deepcopy((strikes, interventions))
    times = fvp._verified_intervention_track_times(interventions, strikes, {"touches": []})
    assert list(times)[0] == "target_chain_actor"
    assert times["target_chain_actor"] == 1600
    assert (strikes, interventions) == before
    assert all("role" not in row for row in interventions)


def test_relevant_parent_pivot_not_oldest_unrelated_touch(monkeypatch):
    interventions = [intervention("same_actor", 1000), intervention("same_actor", 3100)]
    strikes = [strike(900), strike(3000, True)]
    times = fvp._verified_intervention_track_times(interventions, strikes, {"touches": []})
    assert times == {"same_actor": 3100}
    seen = []
    monkeypatch.setattr(fvp, "_read_frames", lambda _v, requested: seen.extend(requested) or {})
    bundle = fvp.build_shadow_providers("fake-test-key", "synthetic", "never-open.mp4")
    graph = {"touches": [{"status": "VERIFIED", "player_track_id": "same_actor",
                          "media_ms": 1010, "scene_id": "synthetic"}]}
    bundle.role_evidence_provider("never-open.mp4", {}, strikes, graph,
                                 [frame(3000, "same_actor"), frame(3200, "same_actor")], interventions)
    assert seen == [3000, 3200]
    assert bundle.role_calls == 0


def test_parent_array_mismatch_cannot_invent_priority():
    times = fvp._verified_intervention_track_times(
        [intervention("early", 1000), intervention("later", 1600)],
        [strike(1500, True)], {"touches": []})
    assert list(times) == ["early", "later"]


def test_unverified_parent_or_intervention_never_gets_target_priority():
    parents = [strike(900), strike(1500, True), strike(1800, True)]
    parents[1]["proof_eligible"] = False
    rows = [intervention("early", 1000), intervention("unverified_parent", 1600),
            intervention("unverified_actor", 1900)]
    rows[2]["status"] = "UNRESOLVED"
    times = fvp._verified_intervention_track_times(rows, parents, {"touches": []})
    assert list(times) == ["early", "unverified_parent"]


def test_track_and_frame_caps_remain_bounded(monkeypatch):
    monkeypatch.setattr(fvp, "MAX_ROLE_TRACKS", 2)
    monkeypatch.setattr(fvp, "MAX_ROLE_FRAMES_PER_TRACK", 3)
    evidence = [frame(ms, track) for track in ("a", "b", "c") for ms in (1000, 1200, 1400, 1600)]
    requests = fvp._role_review_requests(evidence, {"a": 1200, "b": 1200, "c": 1200})
    assert len(requests) == 6
    assert {r["track_id"] for r in requests} == {"a", "b"}
    monkeypatch.setattr(fvp, "MAX_ROLE_FRAMES_PER_TRACK", 0)
    assert fvp._role_review_requests(evidence, {"a": 1200}) == []


@pytest.mark.parametrize("confidence,first", [(.9, "teammate_actor"), (.69, "unrelated")])
def test_teammate_priority_requires_the_existing_verified_causal_team_gate(confidence, first):
    parents = [strike(900, True), strike(1000), strike(1200)]
    parents[2]["touch_id"] = "teammate_touch"
    rows = [intervention("unused", 950), intervention("unrelated", 1100),
            intervention("teammate_actor", 1300)]
    rows[0]["status"] = "UNRESOLVED"
    graph = {"touches": [{"touch_id": "teammate_touch", "status": "VERIFIED",
                           "proof_eligible": True,
                           "team_relation": {"status": "SUPPORTING", "team": "target_team",
                                             "confidence": confidence}}]}
    times = fvp._verified_intervention_track_times(rows, parents, graph)
    assert list(times)[0] == first


@pytest.mark.parametrize("change", [{"scene_id": "other"}, {"media_ms": 1400}])
def test_scene_or_time_mismatch_cannot_bind_intervention_to_target_parent(change):
    parents = [strike(900), strike(1500, True)]
    rows = [intervention("early", 1000), intervention("unbound", 1600)]
    rows[1].update(change)
    times = fvp._verified_intervention_track_times(rows, parents, {"touches": []})
    assert list(times) == ["early", "unbound"]
