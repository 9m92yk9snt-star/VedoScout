"""Measured contact gaps open bounded searches without granting event proof."""
from copy import deepcopy

import pytest

import evidence_feedback as feedback
import jersey_consensus as jerseys
import test_fix13_evidence_feedback as fixture


def release_trace(ms=1000, name="release", scene="scene", *, target=False):
    trace = fixture.trace(ms, name, scene)
    trace["contacts"] = {"accepted": [{"media_ms": ms}], "unresolved": []}
    trace["action_inspections"] = []
    trace["strike_evidence"] = [{"strike_id": "release-" + name, "media_ms": ms,
        "status": "VERIFIED_PHYSICAL_RELEASE", "proof_eligible": True,
        "global_target_id": "GLOBAL_TARGET" if target else None}]
    return trace


def test_unassigned_physical_release_gets_identity_search_before_outcome_authority():
    source = release_trace()
    before = deepcopy(source)
    plan = feedback.build_plan([source])
    assert plan["selected"] == 1
    job = plan["jobs"][0]
    assert job["center_ms"] == 1000
    assert job["reason"] == "PHYSICAL_RELEASE_IDENTITY_GAP"
    assert not ({"expected_type", "expected_outcome", "expected_jersey_number", "global_target_id"} & set(job))
    assert source == before and source["strike_evidence"][0]["global_target_id"] is None


def test_measured_release_identity_gap_precedes_a_generic_unresolved_contact():
    source = release_trace(ms=1800)
    source["contacts"]["unresolved"] = [{"media_ms": 1500}]
    job = feedback.build_plan([source])["jobs"][0]
    assert job["center_ms"] == 1800 and job["reason"] == "PHYSICAL_RELEASE_IDENTITY_GAP"


@pytest.mark.parametrize("change", [{"proof_eligible": False}, {"status": "HYPOTHESES"},
                                   {"media_ms": True}, {"media_ms": float("nan")}])
def test_unqualified_release_does_not_acquire_a_priority_search(change):
    source = release_trace()
    source["strike_evidence"][0].update(change)
    assert not feedback.build_plan([source])["jobs"]


def test_ambiguous_contact_at_a_measured_target_body_precedes_unrelated_contact_hint():
    source = fixture.trace()
    for frame in source["decoded_frames"]:
        frame["global_target"] = {"status": "VERIFIED", "proof_eligible": True, "local_track_id": "p1"}
    source["contacts"] = {"accepted": [], "unresolved": [
        {"media_ms": 650, "player_track_id": "other", "time_authority": "ACTUAL_MEDIA_PTS"},
        {"media_ms": 1100, "player_track_id": None, "player_candidate_track_ids": ["p1", "other"],
         "time_authority": "ACTUAL_MEDIA_PTS", "proof_eligible": False, "status": "HYPOTHESES"}]}
    before = deepcopy(source)
    job = feedback.build_plan([source])["jobs"][0]
    assert job["center_ms"] == 1100 and job["reason"] == "TARGET_CONTACT_EVIDENCE_GAP"
    assert source == before
    assert source["contacts"]["unresolved"][1]["proof_eligible"] is False


def test_ordinary_target_control_ball_gap_does_not_starve_a_real_contact_gap():
    source = fixture.trace()
    for frame in source["decoded_frames"]:
        frame["global_target"] = {"status": "VERIFIED", "proof_eligible": True, "local_track_id": "p1"}
    source["touch_graph"] = {"touches": [{"media_ms": 650, "global_target_id": "GLOBAL_TARGET",
        "contact_role": {"status": "VERIFIED", "role": "RECEIVE_CONTROL"}}]}
    source["contacts"]["unresolved"] = [{"media_ms": 1400}]
    job = feedback.build_plan([source])["jobs"][0]
    assert job["center_ms"] == 1400 and job["reason"] == "PHYSICAL_CONTACT_GAP"


def target_release_gap(ms, name, scene):
    trace = fixture.trace(ms, name, scene)
    trace["contacts"] = {"accepted": [{"media_ms": ms}], "unresolved": []}
    for frame in trace["decoded_frames"]:
        frame["global_target"] = {"status": "VERIFIED", "proof_eligible": True, "local_track_id": "p1"}
    trace["touch_graph"] = {"touches": [{"media_ms": ms, "global_target_id": "GLOBAL_TARGET",
        "contact_role": {"status": "VERIFIED", "role": "RELEASE"}}]}
    return trace


def test_feedback_visits_distinct_scenes_before_spending_again_on_one_scene():
    sources = [target_release_gap(ms, str(ms), "busy") for ms in (1000, 11000, 21000)]
    sources += [fixture.trace(30000, "second", "second"), fixture.trace(40000, "third", "third")]
    selected = [j for j in feedback.build_plan(sources, budget=3)["jobs"] if j["selected"]]
    assert {j["scene_id"] for j in selected} == {"busy", "second", "third"}
    assert len(selected) == 3


def test_overlapping_windows_do_not_spend_feedback_twice_on_identical_source_frames():
    left, right = fixture.trace(name="left"), fixture.trace(name="right")
    before = deepcopy([left, right])
    plan = feedback.build_plan([left, right], budget=8)
    assert len(plan["jobs"]) == plan["selected"] == 1
    assert any(row["reason"] == "OVERLAPPING_FEEDBACK_PIXELS_ALREADY_SCHEDULED" for row in plan["rejected"])
    assert [left, right] == before


def test_equal_timestamps_in_different_scenes_remain_separate_searches():
    sources = [fixture.trace(name="left", scene="left"), fixture.trace(name="right", scene="right")]
    assert feedback.build_plan(sources, budget=8)["selected"] == 2


def test_feedback_budget_remains_hard_capped_even_with_many_measured_releases():
    sources = [release_trace(1000 + i * 5000, str(i), str(i)) for i in range(20)]
    assert feedback.build_plan(sources, budget=999)["selected"] == 8
    assert feedback.build_plan(sources, budget=0)["selected"] == 0


BOX = {"x": .2, "y": .2, "w": .1, "h": .2}


def jersey_inputs():
    graph = {"touches": [
        {"player_track_id": "other", "media_ms": 1000, "scene_id": "scene",
         "contact_role": {"status": "VERIFIED", "role": "RELEASE"}},
        {"player_track_id": "target", "media_ms": 1000, "scene_id": "scene", "status": "CANDIDATE_OCCLUDED"}]}
    frames = [{"media_ms": ms, "scene_id": "scene", "time_authority": "ACTUAL_MEDIA_PTS",
        "used_fallback": False, "cut_barrier": False,
        "global_target": {"status": "VERIFIED", "proof_eligible": True, "local_track_id": "target"},
        "players": [{"local_track_id": track, "box": {**BOX, "x": x}, "association_state": "VERIFIED_LOCAL",
            "jersey_crop_quality": {"source": "NATIVE_TORSO_PIXELS", "width_px": 40,
                "height_px": 48, "sharpness": 40., "isolated": True}}
                    for track, x in (("other", .2), ("target", .6))]}
              for ms in (1000, 1400)]
    return frames, graph


def test_involved_target_body_crops_lead_even_when_its_contact_is_unresolved():
    frames, graph = jersey_inputs()
    before = deepcopy((frames, graph))
    requests = jerseys.select_jersey_review_requests(frames, graph)
    assert [r["track_id"] for r in requests[:2]] == ["target", "target"]
    assert all(r["expected_jersey_number"] is None for r in requests)
    merged = jerseys.merge_jersey_review_requests([], requests, graph, window_evidence=frames)
    assert [r["track_id"] for r in merged[:2]] == ["target", "target"]
    assert (frames, graph) == before
    assert graph["touches"][1]["status"] == "CANDIDATE_OCCLUDED"
    assert "global_target_id" not in graph["touches"][1]


@pytest.mark.parametrize("change", [
    {"cut_barrier": True}, {"used_fallback": True}, {"time_authority": "REQUESTED_TIME"},
    {"scene_id": "different"}, {"global_target": {"status": "HYPOTHESES", "proof_eligible": False,
                                                "local_track_id": "target"}},
    {"global_target": {"status": "VERIFIED", "proof_eligible": True, "local_track_id": []}},
    {"global_target": {"status": "VERIFIED", "proof_eligible": True, "local_track_id": True}},
])
def test_untrusted_target_hint_does_not_jump_the_actor_crop_queue(change):
    frames, graph = jersey_inputs()
    frames = [{**f, **deepcopy(change)} for f in frames]
    requests = jerseys.select_jersey_review_requests(frames, graph)
    if requests:
        assert requests[0]["track_id"] == "other"


def test_a_target_body_without_any_physical_involvement_does_not_open_crop_reads():
    frames, _ = jersey_inputs()
    assert jerseys.select_jersey_review_requests(frames, {"touches": []}) == []
