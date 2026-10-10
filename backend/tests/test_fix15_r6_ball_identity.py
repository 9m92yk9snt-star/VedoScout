"""Generic release-ball regressions; no original-video labels or timestamps."""
from copy import deepcopy

import pytest
import ball_trajectory as bt


def box(x, size=.01):
    return {"x": x, "y": .50, "w": size, "h": size}


def anchor():
    return {"media_ms": 1000, "box": box(.20), "confidence": .9,
            "state": "MEASURED", "proof_eligible": True,
            "time_authority": "ACTUAL_MEDIA_PTS", "used_fallback": False}


def frame(ms, candidates):
    return {"media_ms": ms, "scene_id": "synthetic",
            "time_authority": "ACTUAL_MEDIA_PTS", "used_fallback": False,
            "players": [], "ball_candidates": candidates}


def candidate(x, confidence=.9, size=.01):
    return {"box": box(x, size), "confidence": confidence}


@pytest.mark.parametrize("reverse,mirror,scale", [
    (False, False, 1.), (True, False, 1.), (False, True, 1.),
    (True, True, .5), (False, False, .5),
])
def test_measured_motion_keeps_moving_ball_not_stationary_competitor(reverse, mirror, scale):
    seed = anchor()
    frames = []
    expected = {1000: seed["box"]["x"]}
    for i in range(1, 9):
        ms = 1000 + 33 * i
        x = .20 + .9 * 33 * i / 1000
        choices = [candidate(x, confidence=.10)]
        if i >= 2:
            choices.append(candidate(.224, confidence=.99))
        if reverse:
            choices.reverse()
        frames.append(frame(ms, choices))
        expected[ms] = x

    def transform(b):
        b["x"] = .5 + scale * (b["x"] - .5)
        b["y"] = .5 + scale * (b["y"] - .5)
        b["w"] *= scale
        b["h"] *= scale
        if mirror:
            b["x"] = 1. - b["x"] - b["w"]
    for b in [seed["box"], *(c["box"] for f in frames for c in f["ball_candidates"])]:
        transform(b)
    expected = {ms: (1. - (.5 + scale * (x - .5)) - .01 * scale
                     if mirror else .5 + scale * (x - .5)) for ms, x in expected.items()}
    before = deepcopy((frames, seed))
    rows = bt.reconstruct_ball_trajectory_from_release_anchor(frames, seed, "synthetic")
    assert [r["media_ms"] for r in rows] == list(expected)
    assert all(r["box"]["x"] == pytest.approx(expected[r["media_ms"]]) for r in rows)
    assert all(r["proof_eligible"] and r["state"] == "MEASURED" for r in rows)
    assert (frames, seed) == before


def test_single_candidate_positive_path_is_not_dropped():
    frames = [frame(1000 + 33 * i, [candidate(.20 + .02 * i)]) for i in range(1, 6)]
    rows = bt.reconstruct_ball_trajectory_from_release_anchor(frames, anchor(), "synthetic")
    assert [r["media_ms"] for r in rows] == [1000, 1033, 1066, 1099, 1132, 1165]


def test_long_gap_cannot_expand_radius_and_reattach_another_object():
    frames = [frame(1033, [candidate(.2297)]), frame(1233, [candidate(.65)]),
              frame(1266, [candidate(.67)])]
    rows = bt.reconstruct_ball_trajectory_from_release_anchor(frames, anchor(), "synthetic")
    assert [r["media_ms"] for r in rows] == [1000, 1033]


def test_ambiguous_first_observation_does_not_bootstrap_an_identity():
    frames = [frame(1033, [candidate(.2297), candidate(.231)]),
              frame(1099, [candidate(.224)])]
    rows = bt.reconstruct_ball_trajectory_from_release_anchor(frames, anchor(), "synthetic")
    assert [r["media_ms"] for r in rows] == [1000]


def test_equal_motion_support_remains_unresolved_regardless_of_confidence():
    frames = [frame(1033, [candidate(.2297)]),
              frame(1066, [candidate(.2574, .10), candidate(.2614, .99)])]
    rows = bt.reconstruct_ball_trajectory_from_release_anchor(frames, anchor(), "synthetic")
    assert [r["media_ms"] for r in rows] == [1000, 1033]


def test_incompatible_size_cannot_win_on_position_or_confidence():
    frames = [frame(1033, [candidate(.2297)]),
              frame(1066, [candidate(.2594, .10), candidate(.2297, .99, .04)])]
    rows = bt.reconstruct_ball_trajectory_from_release_anchor(frames, anchor(), "synthetic")
    assert rows[-1]["media_ms"] == 1066
    assert rows[-1]["box"] == box(.2594)


@pytest.mark.parametrize("change", [
    {"used_fallback": True}, {"time_authority": "SYNTHETIC_FRAME_INDEX"},
    {"time_authority": None},
])
def test_noncanonical_frame_never_becomes_measured_authority(change):
    f = frame(1033, [candidate(.2297)])
    f.update(change)
    assert len(bt.reconstruct_ball_trajectory_from_release_anchor([f], anchor(), "synthetic")) == 1


@pytest.mark.parametrize("change", [
    {"state": "PREDICTED"}, {"proof_eligible": False}, {"used_fallback": True},
    {"time_authority": "SYNTHETIC_FRAME_INDEX"},
])
def test_explicit_nonproof_candidate_never_becomes_measured_authority(change):
    c = candidate(.2297)
    c.update(change)
    assert len(bt.reconstruct_ball_trajectory_from_release_anchor(
        [frame(1033, [c])], anchor(), "synthetic")) == 1


@pytest.mark.parametrize("change", [{"cut_barrier": True}, {"scene_id": "other"}])
def test_cut_or_scene_boundary_ends_path(change):
    f = frame(1066, [candidate(.2594)])
    f.update(change)
    rows = bt.reconstruct_ball_trajectory_from_release_anchor(
        [frame(1033, [candidate(.2297)]), f, frame(1099, [candidate(.2891)])],
        anchor(), "synthetic")
    assert [r["media_ms"] for r in rows] == [1000, 1033]


def test_camera_label_without_measured_transform_cannot_authorize_jump():
    f = frame(1033, [candidate(.90)])
    f["camera_state"] = "AFFINE_VERIFIED"
    assert len(bt.reconstruct_ball_trajectory_from_release_anchor([f], anchor(), "synthetic")) == 1


@pytest.mark.parametrize("seed,required", [({"proof_eligible": False}, False), (None, True)])
def test_rejected_required_anchor_never_falls_back_to_global_ball(seed, required):
    global_path = [{"media_ms": 1033, "state": "MEASURED", "box": box(.80)}]
    chosen = bt.select_release_ball_trajectory([], seed, "synthetic", global_path,
                                              anchor_required=required)
    assert chosen["rows"] == []
    assert chosen["source"] == "REJECTED_RELEASE_ANCHOR"


def test_legacy_anchor_absent_path_remains_compatible():
    global_path = [{"media_ms": 1033, "state": "MEASURED", "box": box(.80)}]
    chosen = bt.select_release_ball_trajectory([], None, "synthetic", global_path)
    assert chosen["rows"] == global_path
    assert chosen["source"] == "WINDOW_GLOBAL_TRAJECTORY"


def test_single_poor_motion_fit_cannot_win_merely_by_lacking_competitors():
    frames = [frame(1033, [candidate(.2297)]), frame(1066, [candidate(.30)])]
    rows = bt.reconstruct_ball_trajectory_from_release_anchor(frames, anchor(), "synthetic")
    assert [r["media_ms"] for r in rows] == [1000, 1033]


def test_pending_jump_with_incompatible_confirmation_scale_stays_unproved():
    seed = anchor()
    seed["box"] = box(.49, .02)
    pending = frame(1017, [candidate(.72, size=.02)])
    pending["players"] = [{"local_track_id": "body", "association_state": "VERIFIED_LOCAL",
                            "box": {"x": .68, "y": .35, "w": .10, "h": .20}}]
    confirm = frame(1034, [candidate(.74, size=.08)])
    rows = bt.reconstruct_ball_trajectory_from_release_anchor([pending, confirm], seed, "synthetic")
    assert [r["media_ms"] for r in rows] == [1000]
