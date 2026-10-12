"""Fresh native seed selection, without repairing rejected required anchors."""
from copy import deepcopy

import pytest

import ball_trajectory as bt
import physical_match_reconstruction as pmr


def setup(width=1000, height=1000):
    frames = []
    for i, (ms, confidence) in enumerate(((1000, .15), (1040, .035), (1060, .22), (1100, .40))):
        x = .20 + (ms-1000)/1000*.30*height/width
        frames.append({"media_ms": ms, "scene_id": "synthetic", "players": [],
            "time_authority": "ACTUAL_MEDIA_PTS", "used_fallback": False,
            "camera_state": "AFFINE_VERIFIED" if i else "SEED_OR_FIRST_FRAME",
            "frame_dimensions": {"width": width, "height": height, "source": "DECODED_NATIVE_PIXELS"},
            "camera_motion": {"source": "NATIVE_BACKGROUND_AFFINE", "units": "DECODED_PIXELS",
                "from_media_ms": frames[-1]["media_ms"], "to_media_ms": ms,
                "matrix": [[1., 0., 0.], [0., 1., 0.]]} if i else None,
            "ball_candidates": [{"box": {"x": x, "y": .50, "w": 12/width, "h": 12/height},
                                 "confidence": confidence}]})
    def point(frame):
        return {"media_ms": frame["media_ms"], "state": "MEASURED", "proof_eligible": True,
            "time_authority": "ACTUAL_MEDIA_PTS", "used_fallback": False,
            **deepcopy(frame["ball_candidates"][0])}
    contact, provisional = point(frames[0]), point(frames[1])
    provisional["source"] = "VERIFIED_RELEASE_CONTACT_BALL_AFTER"
    provisional["remote_spare_ball_used"] = False
    return frames, contact, provisional


@pytest.mark.parametrize("width,height", [(1000,1000), (1920,1080), (1080,1920)])
def test_earliest_eligible_same_ball_measurement_replaces_only_the_fresh_weak_seed(width,height):
    frames, contact, provisional = setup(width,height)
    before = deepcopy((frames,contact,provisional))
    qualified = bt.qualify_native_release_seed(frames,contact,provisional,"synthetic")
    assert qualified["anchor"]["media_ms"] == 1060
    assert qualified["anchor"]["box"] == frames[2]["ball_candidates"][0]["box"]
    assert qualified["anchor"]["confidence"] == .22
    assert qualified["audit"]["contact_binding"]["measured_times_ms"] == [1000,1060]
    assert qualified["audit"]["original_anchor"] == provisional
    assert qualified["audit"]["release_confidence_floor"] == bt.RELEASE_REACQUIRE_MIN_CONFIDENCE == .04
    assert qualified["audit"]["provisional_consistency"]["proof_eligible"] is False
    assert (frames,contact,provisional) == before


@pytest.mark.parametrize("reverse", [False,True])
def test_high_confidence_reserve_cannot_replace_the_contact_ball(reverse):
    frames, contact, provisional = setup()
    for frame in frames:
        frame["ball_candidates"].append({"box": {"x": .85,"y": .5,"w": .012,"h": .012}, "confidence": .99})
        if reverse:
            frame["ball_candidates"].reverse()
    q = bt.qualify_native_release_seed(frames,contact,provisional,"synthetic")
    assert q["anchor"]["box"]["x"] == pytest.approx(.218)
    assert q["anchor"]["confidence"] == .22


@pytest.mark.parametrize("change", [
    {"proof_eligible": False}, {"identity_rejection": "CONTACT_TO_RELEASE_ANCHOR_UNPROVEN"},
    {"used_fallback": True}, {"cut_barrier": True}, {"cut": True},
    {"state": "PREDICTED"}, {"state": "SEARCH_ONLY"},
    {"time_authority": "FRAME_INDEX_FPS_FALLBACK"}, {"scene_id": "other"},
    {"media_ms": 1040.0}, {"confidence": float("nan")}, {"confidence": float("inf")},
    {"confidence": True}, {"confidence": ".035"}, {"confidence": -.01},
    {"confidence": .04}, {"confidence": .99},
])
def test_invalid_rejected_or_already_eligible_seed_is_never_substituted(change):
    frames, contact, provisional = setup()
    provisional.update(change)
    assert bt.qualify_native_release_seed(frames,contact,provisional,"synthetic") is None


@pytest.mark.parametrize("change", [{"proof_eligible": False}, {"state": "SEARCH_ONLY"},
    {"used_fallback": True}, {"media_ms": 1000.0}, {"scene_id": "other"},
    {"confidence": float("nan")}, {"confidence": True}, {"confidence": ".15"}])
def test_an_eligible_future_ball_cannot_repair_a_missing_contact_proof(change):
    frames, contact, provisional = setup()
    contact.update(change)
    assert bt.qualify_native_release_seed(frames,contact,provisional,"synthetic") is None


@pytest.mark.parametrize("change", [{"camera_motion": None}, {"camera_state": "UNRESOLVED"},
    {"cut_barrier": True}, {"scene_id": "other"}, {"used_fallback": True},
    {"time_authority": "FRAME_INDEX_FPS_FALLBACK"}])
def test_unproved_intermediate_native_step_prevents_selection(change):
    frames, contact, provisional = setup()
    frames[1].update(change)
    assert bt.qualify_native_release_seed(frames,contact,provisional,"synthetic") is None


def test_legacy_trace_has_no_new_seed_substitution_contract():
    frames, contact, provisional = setup()
    for frame in frames:
        frame.pop("camera_motion")
    assert bt.qualify_native_release_seed(frames,contact,provisional,"synthetic") is None


def test_weak_proposal_on_another_ball_cannot_be_repaired_using_contact_motion():
    frames, contact, provisional = setup()
    frames[1]["ball_candidates"][0]["box"]["x"] = .80
    provisional["box"]["x"] = .80
    assert bt.qualify_native_release_seed(frames,contact,provisional,"synthetic") is None


def test_a_low_confidence_search_or_predicted_proposal_is_not_a_native_source():
    frames, contact, provisional = setup()
    frames[1]["ball_candidates"][0]["proof_eligible"] = False
    assert bt.qualify_native_release_seed(frames,contact,provisional,"synthetic") is None


def test_provisional_box_must_be_an_exact_raw_native_proposal():
    frames, contact, provisional = setup()
    provisional["box"]["x"] += .001
    assert bt.qualify_native_release_seed(frames,contact,provisional,"synthetic") is None


def test_ambiguous_weak_objects_do_not_get_a_confidence_tiebreak():
    frames, contact, provisional = setup()
    peer = deepcopy(frames[1]["ball_candidates"][0])
    peer["box"]["x"] += .001
    peer["confidence"] = .99
    frames[1]["ball_candidates"].append(peer)
    assert bt.qualify_native_release_seed(frames,contact,provisional,"synthetic") is None


def test_an_ambiguous_future_measurement_is_not_a_qualified_seed():
    frames, contact, provisional = setup()
    frames[3]["ball_candidates"] = []
    peer = deepcopy(frames[2]["ball_candidates"][0])
    peer["box"]["x"] += .001
    peer["confidence"] = .99
    frames[2]["ball_candidates"].append(peer)
    assert bt.qualify_native_release_seed(frames,contact,provisional,"synthetic") is None


def test_an_unobserved_ball_gap_does_not_expand_the_seed_selection_horizon():
    frames, contact, provisional = setup()
    frames[2]["ball_candidates"] = []
    assert bt.qualify_native_release_seed(frames,contact,provisional,"synthetic") is None


def test_seed_past_the_existing_contact_horizon_cannot_be_qualified():
    frames, contact, provisional = setup()
    provisional["media_ms"] = 1301
    assert bt.qualify_native_release_seed(frames,contact,provisional,"synthetic") is None


@pytest.mark.parametrize("source", ["VERIFIED_RELEASE_CONTACT_BALL_AFTER", "VERIFIED_SCORING_CONTROL_BALL_AFTER"])
def test_live_and_replay_shared_producer_keeps_original_touch_and_audits_qualified_seed(source):
    frames, contact, provisional = setup()
    provisional["source"] = source
    strike = {"touch_id": "t", "scene_id": "synthetic", "active_ball_anchor": provisional}
    graph = {"touches": [{"touch_id": "t", "status": "VERIFIED", "proof_eligible": True,
                         "ball_at_contact": contact, "ball_after": deepcopy(provisional)}]}
    original_graph = deepcopy(graph)
    path = pmr._strike_ball_paths([strike],graph,frames,[{"box": {"x": .9}}])[0]
    assert path["source"] == "VERIFIED_RELEASE_ANCHOR"
    assert path["contact_binding"]["measured_times_ms"] == [1000,1060]
    assert [r["media_ms"] for r in path["rows"]] == [1060,1100]
    assert strike["active_ball_anchor"]["media_ms"] == 1060
    assert strike["release_seed_qualification"]["original_anchor"]["media_ms"] == 1040
    assert graph == original_graph
    # A second call uses the exact chosen anchor; it cannot repeat substitution.
    again = pmr._strike_ball_paths([strike],graph,frames,[])[0]
    assert again == path


@pytest.mark.parametrize("change", [
    {"proof_eligible": False}, {"identity_rejection": "REJECTED"}, {"source": "EXTERNAL_REQUIRED_ANCHOR"},
])
def test_shared_producer_never_substitutes_for_a_rejected_or_external_required_seed(change):
    frames, contact, provisional = setup()
    provisional.update(change)
    strike = {"touch_id": "t", "scene_id": "synthetic", "active_ball_anchor": provisional}
    graph = {"touches": [{"touch_id": "t", "status": "VERIFIED", "proof_eligible": True,
                         "ball_at_contact": contact, "ball_after": deepcopy(provisional)}]}
    path = pmr._strike_ball_paths([strike],graph,frames,[{"box": {"x": .9}}])[0]
    assert path["source"] == "REJECTED_RELEASE_ANCHOR"
    assert path["rows"] == []
    assert strike["active_ball_anchor"]["media_ms"] == 1040
    assert "release_seed_qualification" not in strike
