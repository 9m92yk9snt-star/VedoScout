"""Contact-to-release identity must be measured, not a coordinate coincidence."""
from copy import deepcopy

import pytest

import ball_trajectory as bt
import contact_role_resolver as crr
import fix10a_vision_providers as fvp
import physical_match_reconstruction as pmr


def box(x):
    return {"x": x, "y": .5, "w": .01, "h": .01}


def point(ms, x):
    return {"media_ms": ms, "box": box(x), "confidence": .9,
            "state": "MEASURED", "proof_eligible": True,
            "time_authority": "ACTUAL_MEDIA_PTS", "used_fallback": False}


def frame(ms, xs, **changes):
    return {"media_ms": ms, "scene_id": "synthetic", "time_authority": "ACTUAL_MEDIA_PTS",
            "used_fallback": False, "camera_state": "AFFINE_VERIFIED", "players": [],
            "ball_candidates": [{"box": box(x), "confidence": .9} for x in xs], **changes}


def select(frames, contact, anchor, **kwargs):
    return bt.select_release_ball_trajectory(
        frames, anchor, "synthetic", [{"media_ms": 1500, "box": box(.9)}],
        anchor_required=True, contact_ball=contact, contact_required=True, **kwargs)


def test_unique_contact_path_binds_the_post_contact_seed_without_mutating_inputs():
    contact, anchor = point(1000, .20), point(1066, .24)
    frames = [frame(1033, [.22, .85]), frame(1066, [.24, .85]), frame(1099, [.26, .85])]
    before = deepcopy((frames, contact, anchor))
    selected = select(frames, contact, anchor)
    assert [r["media_ms"] for r in selected["rows"]] == [1066, 1099]
    assert selected["contact_binding"]["status"] == "VERIFIED"
    assert selected["contact_binding"]["measured_times_ms"] == [1000, 1033, 1066]
    assert (frames, contact, anchor) == before


def test_high_confidence_stationary_competitor_cannot_be_the_release_seed():
    frames = [frame(1000, [.20, .80]), frame(1033, [.22, .80]), frame(1066, [.24, .80])]
    selected = select(frames, point(1000, .20), point(1033, .80))
    assert selected["rows"] == []
    assert selected["source"] == "REJECTED_RELEASE_ANCHOR"
    assert selected["contact_binding"]["reason"] == "CONTACT_TO_RELEASE_ANCHOR_UNPROVEN"


def test_verified_contact_motion_is_not_discarded_at_the_post_contact_seed():
    frames = [frame(1033, [.23, .80]), frame(1066, [.26, .80]),
              frame(1099, [.271, .29])]
    frames[-1]["ball_candidates"][0]["confidence"] = .99
    frames[-1]["ball_candidates"][1]["confidence"] = .30
    selected = select(frames, point(1000, .20), point(1066, .26))
    assert selected["contact_binding"]["status"] == "VERIFIED"
    assert [r["media_ms"] for r in selected["rows"]] == [1066, 1099]
    assert [r["box"]["x"] for r in selected["rows"]] == pytest.approx([.26, .29])


def test_post_contact_duration_starts_at_the_seed_not_at_the_contact():
    frames = [frame(1033, [.22]), frame(1066, [.24]), frame(1099, [.26]), frame(1132, [.28])]
    selected = select(frames, point(1000, .20), point(1066, .24), max_duration_ms=33)
    assert [r["media_ms"] for r in selected["rows"]] == [1066, 1099]


def test_old_competitor_position_is_not_a_permanent_identity_exclusion():
    # The other object moves away. The active ball subsequently passes through
    # its OLD coordinates on a uniquely measured, continuous contact path.
    frames = [frame(1000, [.20, .50]), frame(1033, [.30, .70]),
              frame(1066, [.40, .75]), frame(1099, [.50, .80]), frame(1132, [.60, .85])]
    selected = select(frames, point(1000, .20), point(1099, .50))
    assert selected["contact_binding"]["status"] == "VERIFIED"
    assert [r["box"]["x"] for r in selected["rows"]] == pytest.approx([.50, .60])


@pytest.mark.parametrize("change", [
    {"proof_eligible": False}, {"used_fallback": True}, {"state": "PREDICTED"},
    {"time_authority": "SYNTHETIC_FRAME_INDEX"}, {"media_ms": float("nan")},
])
def test_invalid_contact_cannot_authorize_a_good_looking_post_contact_seed(change):
    contact = {**point(1000, .20), **change}
    selected = select([frame(1033, [.22])], contact, point(1033, .22))
    assert selected["rows"] == []
    assert selected["contact_binding"]["reason"] == "CONTACT_BALL_NOT_PROOF_ELIGIBLE"


def test_present_but_missing_contact_does_not_use_legacy_fallback():
    assert select([frame(1033, [.22])], None, point(1033, .22))["rows"] == []


@pytest.mark.parametrize("change", [
    {"cut_barrier": True}, {"camera_state": "UNRESOLVED:insufficient_background"},
    {"scene_id": "other"}, {"time_authority": "SYNTHETIC_FRAME_INDEX"},
])
def test_contact_bridge_does_not_cross_an_unproved_step(change):
    selected = select([frame(1033, [.22], **change), frame(1066, [.24])],
                      point(1000, .20), point(1066, .24))
    assert selected["rows"] == []


@pytest.mark.parametrize("seed_ms", [999, 1301])
def test_seed_before_contact_or_outside_existing_contact_horizon_is_rejected(seed_ms):
    assert select([], point(1000, .20), point(seed_ms, .20))["rows"] == []


def test_missing_measurements_cannot_certify_a_contact_bridge():
    assert select([], point(1000, .20), point(1033, .22))["rows"] == []


def test_long_contact_bridge_can_use_short_measured_gaps_but_not_an_unobserved_jump():
    selected = select([frame(1099, [.26])], point(1000, .20), point(1099, .26))
    assert selected["rows"] == []


def test_same_time_same_measurement_is_a_direct_contact_binding():
    contact = point(1000, .20)
    selected = select([], contact, deepcopy(contact))
    assert selected["contact_binding"]["status"] == "VERIFIED"
    assert selected["rows"][0]["box"] == contact["box"]


def test_same_time_different_measurements_cannot_be_the_same_contact_ball():
    assert select([], point(1000, .20), point(1000, .80))["rows"] == []


@pytest.mark.parametrize("camera_state", ["UNRESOLVED:no_matrix", "SEED_OR_FIRST_FRAME"])
def test_explicit_unverified_camera_step_ends_identity_not_just_skips_one_frame(camera_state):
    rows = bt.reconstruct_ball_trajectory_from_release_anchor(
        [frame(1033, [.22]), frame(1066, [.24], camera_state=camera_state), frame(1099, [.26])],
        point(1000, .20), "synthetic")
    assert [r["media_ms"] for r in rows] == [1000, 1033]


@pytest.mark.parametrize("candidate_ids", [["other"], ["wanted", "other"], []])
def test_competing_body_ids_do_not_consume_a_role_read(candidate_ids):
    frames = [{"media_ms": 1000, "players": [
        {"local_track_id": "wanted", "association_state": "VERIFIED_LOCAL",
         "candidate_local_track_ids": candidate_ids,
         "box": {"x": .2, "y": .2, "w": .2, "h": .4}}]}]
    assert fvp._role_review_requests(frames, {"wanted": 1000}) == []


def test_single_matching_body_id_remains_a_usable_role_crop():
    frames = [{"media_ms": 1000, "players": [
        {"local_track_id": "wanted", "association_state": "VERIFIED_LOCAL",
         "candidate_local_track_ids": ["wanted"],
         "box": {"x": .2, "y": .2, "w": .2, "h": .4}}]}]
    assert len(fvp._role_review_requests(frames, {"wanted": 1000})) == 1


def test_all_strike_callers_demote_a_seed_disconnected_from_the_contact():
    strike = {"strike_id": "release", "touch_id": "touch", "media_ms": 1000,
              "scene_id": "synthetic", "active_ball_anchor": point(1033, .80),
              "remote_spare_ball_used": False}
    graph = {"touches": [{"touch_id": "touch", "ball_at_contact": point(1000, .20)}]}
    frames = [frame(1033, [.22, .80])]
    paths = pmr._strike_ball_paths([strike], graph, frames, [{"box": box(.80)}])
    assert paths[0]["rows"] == []
    assert strike["active_ball_anchor"]["proof_eligible"] is False
    assert strike["remote_spare_ball_used"] is None
    assert graph["touches"][0]["ball_at_contact"]["proof_eligible"] is True


def test_contact_role_cannot_promote_a_stationary_seed_using_an_unrelated_path(monkeypatch):
    touch = {"touch_id": "control", "status": "VERIFIED", "proof_eligible": True,
             "media_ms": 1000, "scene_id": "synthetic", "player_track_id": "actor",
             "possession_kinds": ["CONTROL_TOUCH"], "ball_at_contact": point(1000, .20),
             "ball_after": point(1033, .80)}
    received = []
    monkeypatch.setattr(crr, "_delayed_separation_role", lambda _t, _ts, _fs, rows: received.append(rows))
    crr.apply_contact_roles({"touches": [touch]}, {"contacts": []},
                            dense_frames=[frame(1033, [.22, .80])], ball_trajectory=[point(1033, .80)])
    assert received == [[]]


def test_outcome_audit_preserves_rejection_reason_without_aliasing_the_path():
    path = {"rows": [], "source": "REJECTED_RELEASE_ANCHOR", "seed_ms": None,
            "contact_binding": {"status": "REJECTED", "reason": "CONTACT_TO_RELEASE_ANCHOR_UNPROVEN",
                                "measured_times_ms": [1000]}}
    outcome = pmr._apply_ball_path_audit({}, path)
    assert outcome["ball_trajectory_source"] == "REJECTED_RELEASE_ANCHOR"
    assert outcome["release_ball_binding"] == path["contact_binding"]
    outcome["release_ball_binding"]["measured_times_ms"].append(1033)
    assert path["contact_binding"]["measured_times_ms"] == [1000]


def test_goal_review_does_not_drop_the_rejected_contact_binding_audit():
    path = {"rows": [], "source": "REJECTED_RELEASE_ANCHOR", "seed_ms": None,
            "contact_binding": {"status": "REJECTED", "reason": "CONTACT_TO_RELEASE_ANCHOR_UNPROVEN",
                                "measured_times_ms": []}}
    job = {"strike": {"strike_id": "release", "media_ms": 1000, "scene_id": "synthetic"},
           "shot_track": path, "touch_graph": {"touches": []}, "roles": {},
           "review": {"lane": "NONE"}, "intervention": {"status": "UNRESOLVED"},
           "eligibility": {"eligible": False}}
    outcome = pmr._review_outcome(job, None, {"ball_trajectory_points": []})
    assert outcome["release_ball_binding"] == path["contact_binding"]
    assert outcome["ball_trajectory_source"] == "REJECTED_RELEASE_ANCHOR"
    assert outcome["goal_plane_crossing"]["status"] != "VERIFIED"
