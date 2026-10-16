"""Independent claims and bounded tap authority; no model or video calls."""
from pathlib import Path
import sys
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import player_identity_timeline as timeline
import report_fact_authority as facts
import unified_identity_authority as authority
import dense_identity_continuity as dense


def test_assist_does_not_authorize_a_goal_claim_in_the_same_sentence():
    events = [{"canonical_event_type": "ASSIST", "causal_verified": True}]
    assert not facts._supports("He scored a goal and provided an assist.", events)


def test_goal_does_not_authorize_a_save_claim_in_the_same_sentence():
    events = [{"canonical_event_type": "GOAL", "causal_verified": True}]
    assert not facts._supports("He scored a goal after forcing a save.", events)


def test_assist_and_save_do_not_authorize_an_unproved_goal():
    events = [{"canonical_event_type": "ASSIST", "causal_verified": True},
              {"canonical_event_type": "SHOT", "canonical_outcome": "SAVED"}]
    assert not facts._supports("He scored a goal, forced a save and made an assist.", events)


def test_all_supported_claims_are_retained():
    events = [{"canonical_event_type": "ASSIST", "causal_verified": True},
              {"canonical_event_type": "GOAL", "causal_verified": True},
              {"canonical_event_type": "SHOT", "canonical_outcome": "SAVED"}]
    assert facts._supports("He scored a goal, forced a save and made an assist.", events)


@pytest.mark.parametrize("text", ["He scored two goals.", "Two well-taken goals.",
                                  "He scored 2 goals."])
def test_one_goal_does_not_support_a_multiple_goal_claim(text):
    assert not facts._supports(text, [{"canonical_event_type": "GOAL", "causal_verified": True}])


def test_supported_scoring_count_is_retained():
    assert facts._supports("Two well-taken goals.", [
        {"event_id": str(i), "canonical_event_type": "GOAL", "causal_verified": True}
        for i in range(2)])


def sample(ms, score, gap=0):
    return {"ms": ms, "box": (100, 100, 30, 60), "emb": {"score": score},
            "overlap": False, "gap_before": gap}


def test_distant_future_tap_cannot_confirm_an_earlier_wrong_body_resume():
    rows = [sample(0, .9), sample(1000, .1, gap=3), sample(1200, .1),
            sample(10000, .9, gap=3)]
    kept = timeline._resume_trim(rows, lambda e: e["score"], [10000])
    assert [s["ms"] for s in kept] == [0]


def test_nearby_tap_can_confirm_a_resumed_body():
    rows = [sample(0, .9), sample(1000, .1, gap=3), sample(1200, .1)]
    assert timeline._resume_trim(rows, lambda e: e["score"], [1200]) == rows


@pytest.mark.parametrize("pin_new_view", [False, True])
def test_enriched_profile_cannot_lend_late_identity_to_a_wrong_track_prefix(pin_new_view):
    observations = []
    for k in range(20):
        kind = "reference" if k < 8 else "wrong" if k < 13 else "new_view"
        observations.append({"media_ms": k * 200, "cut": k == 8,
                             "cam_dx": 0, "cam_dy": 0, "width": 480, "height": 270,
                             "detections": [{"box": (100, 100, 30, 60),
                                             "emb": {"kind": kind}, "team": None}]})
    def base(e):
        return .9 if e["kind"] == "reference" else .2
    def pair(a, b):
        return .9 if a["kind"] != "wrong" and b["kind"] != "wrong" else .1
    taps = [{"media_ms": 0, "box": (100, 100, 30, 60)}]
    if pin_new_view:
        taps.append({"media_ms": 2800, "box": (100, 100, 30, 60)})
    result = timeline.assemble_timeline(observations, taps, base, pair_sim=pair)
    second = [p for p in result["target_points"] if p["scene_id"] == "scene_002"
              and p.get("proof_eligible")]
    assert any(p["media_ms"] >= 2600 for p in second), "new view should be recovered"
    assert not any(p["media_ms"] < 2600 for p in second), "earlier wrong body is not the target"
    if pin_new_view:
        assert any(p["media_ms"] == 2800 for p in second), "tap must follow its split fragment"


def test_nearby_frames_on_opposite_sides_of_a_cut_are_not_fused():
    box = {"x": .2, "y": .3, "w": .1, "h": .2}
    global_track = {"scenes": [{"scene_id": "a", "start_ms": 0, "end_ms": 1000},
                               {"scene_id": "b", "start_ms": 1001, "end_ms": 2000}],
                    "target_points": [{"media_ms": 999, "scene_id": "a", "box": box,
                                       "proof_eligible": True}]}
    local_track = {"points": [{"t": 1.002, **box, "conf": .9}]}
    output = authority.build_unified_identity_authority(local_track, global_track)
    assert not any(p["identity_strength"] == "FUSED" for p in output["target_points"])


@pytest.mark.parametrize("reason", ["UNRESOLVED_IDENTITY", "SOURCE_CONFLICT",
                                    "DENSE_TARGET_COMPETING_ASSOCIATION"])
def test_dense_body_continuity_cannot_overrule_an_explicit_identity_conflict(reason):
    frames = [{"media_ms": ms, "scene_id": "a", "time_authority": "ACTUAL_MEDIA_PTS",
               "players": [{"local_track_id": "p1", "association_state": "VERIFIED_LOCAL",
                            "box": {"x": .2, "y": .3, "w": .1, "h": .2}}],
               "global_target": {"status": "VERIFIED", "proof_eligible": True,
                                 "local_track_id": "p1", "reason": "OK_EXACT"}
                   if ms == 1000 else {"status": "UNRESOLVED", "proof_eligible": False,
                                      "reason": reason if ms == 1017 else "TARGET_GAP"}}
              for ms in [1000, 1017, 1034]]
    output = dense.apply(frames)["frames"]
    assert not output[1]["global_target"].get("proof_eligible")
    assert not output[2]["global_target"].get("proof_eligible"), "cannot propagate across the conflict"
