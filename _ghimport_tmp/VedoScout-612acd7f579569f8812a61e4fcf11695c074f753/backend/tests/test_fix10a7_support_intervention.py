from __future__ import annotations
import sys
from pathlib import Path
import numpy as np

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

import ball_contact_engine as bce
import ball_trajectory as bt
import cv_detect
import dense_track_refinement as dtr
import post_strike_intervention as a7
import touch_graph as tg


def _box(x, y, w=.02, h=.02):
    return {"x": x, "y": y, "w": w, "h": h}


def _support(x, y=.40, conf=.006):
    return {"box": _box(x, y), "confidence": conf, "support_only": True, "proof_eligible": False}


def _player(track="p002", x=.34, y=.28, w=.16, h=.22, state="VERIFIED_LOCAL"):
    return {"local_track_id": track, "box": _box(x, y, w, h), "association_state": state}


def _frame(ms, support=None, players=None, *, cut=False):
    return {
        "media_ms": ms,
        "scene_id": "s1",
        "used_fallback": False,
        "time_authority": "ACTUAL_MEDIA_PTS",
        "cut_barrier": cut,
        "players": list(players or []),
        "ball_candidates": [],
        "a7_ball_support_candidates": list(support or []),
    }


def _anchor():
    return [{
        "media_ms": 1000,
        "scene_id": "s1",
        "state": "MEASURED",
        "box": _box(.20, .40),
        "confidence": .8,
        "time_authority": "ACTUAL_MEDIA_PTS",
        "used_fallback": False,
        "proof_eligible": True,
    }]


def _strike():
    return {"status": "VERIFIED_PHYSICAL_RELEASE", "media_ms": 1000,
            "scene_id": "s1", "player_track_id": "p001", "proof_eligible": True}


def _verified_support_sequence(track="p002"):
    # Ball travels right, meets the same body on three frames, and reverses.
    body = _player(track=track)
    return [
        _frame(1040, [_support(.24)]),
        _frame(1080, [_support(.31)]),
        _frame(1120, [_support(.43)], [body]),
        _frame(1160, [_support(.39)], [body]),
        _frame(1200, [_support(.35)], [body]),
        _frame(1240, [_support(.31)], [body]),
        _frame(1280, [_support(.28)]),
    ]


def test_a7s01_multiframe_support_can_verify_independent_intervention():
    out = a7.detect_post_strike_intervention(_strike(), _verified_support_sequence(), _anchor())
    assert out["status"] == "VERIFIED"
    assert out["player_track_id"] == "p002"
    assert out["support_hit_count"] >= 3
    assert out["raw_support_proposals_proof_eligible"] is False
    assert out["proof_eligible"] is True
    assert out["touch_graph_mutated"] is False
    assert out["source"] == "A7_SUPPORT_ONLY_FULL_BODY_INTERVENTION"


def test_a7s02_single_frame_body_nearness_cannot_verify():
    frames = _verified_support_sequence()
    for frame in frames:
        if frame["media_ms"] != 1120:
            frame["players"] = []
    out = a7.detect_post_strike_intervention(_strike(), frames, _anchor())
    assert out["status"] == "UNRESOLVED"
    assert out["reason"] == "A7_SUPPORT_NO_MULTIFRAME_BODY_CLUSTER"


def test_a7s03_competing_materially_different_ball_paths_fail_closed():
    frames = []
    for i, ms in enumerate((1040,1080,1120,1160,1200,1240,1280)):
        x = .24 + .04 * i
        frames.append(_frame(ms, [_support(x, .30, .006), _support(x, .50, .006)]))
    path = a7._build_support_paths(_strike(), frames, _anchor())
    assert path["status"] == "UNRESOLVED"
    assert path["reason"] == "A7_SUPPORT_COMPETING_BALL_PATHS"


def test_a7s04_pose_aware_envelope_supports_diving_upper_body_not_below_feet():
    diving = _box(.30, .43, .18, .06)
    # Extended arm/upper-body area above a horizontal keeper is supported.
    assert a7._pose_aware_body_hit(diving, _box(.36, .385, .02, .02)) is True
    # Expansion below the feet/lower edge is intentionally tiny: A4 owns that zone.
    assert a7._pose_aware_body_hit(diving, _box(.36, .505, .02, .02)) is False


def test_a7s05_scene_cut_stops_support_path():
    frames = _verified_support_sequence()
    frames[2]["cut_barrier"] = True
    out = a7.detect_post_strike_intervention(_strike(), frames, _anchor())
    assert out["status"] == "UNRESOLVED"
    assert out["reason"] in {"A7_SUPPORT_PATH_TOO_SPARSE", "A7_SUPPORT_NO_MULTIFRAME_BODY_CLUSTER"}


def test_a7s06_support_only_candidates_are_invisible_to_a3_a4_a5():
    frames = _verified_support_sequence()
    trajectory = bt.reconstruct_ball_trajectory(frames)
    assert all(row["state"] == "MISSING" for row in trajectory)
    contacts = bce.resolve_contacts(bce.detect_contact_candidates(frames, trajectory))
    assert contacts["accepted"] == []
    graph = tg.build_touch_graph(contacts, {}, frames)
    assert graph.get("touches") == []


def test_a7s07_missing_proof_eligible_a3_anchor_fails_closed():
    bad_anchor = _anchor()
    bad_anchor[0]["proof_eligible"] = False
    out = a7.detect_post_strike_intervention(_strike(), _verified_support_sequence(), bad_anchor)
    assert out["status"] == "UNRESOLVED"
    assert out["reason"] == "A7_SUPPORT_NO_PROOF_ELIGIBLE_STRIKE_ANCHOR"


def test_a7s08_hypothesis_player_never_counts_in_support_cluster():
    frames = _verified_support_sequence()
    for frame in frames:
        for player in frame["players"]:
            player["association_state"] = "HYPOTHESES"
    out = a7.detect_post_strike_intervention(_strike(), frames, _anchor())
    assert out["status"] == "UNRESOLVED"


class _FakeNet:
    def setInput(self, _blob):
        pass
    def forward(self):
        raw = np.zeros((1, 84, 2), dtype=np.float32)
        raw[0, 0:4, 0] = [320, 320, 20, 20]
        raw[0, 4 + 32, 0] = .005  # support-only sports ball
        raw[0, 0:4, 1] = [300, 300, 80, 160]
        raw[0, 4, 1] = max(float(cv_detect.CONF_T) + .1, .8)
        return raw


class _FakeDetector:
    ok = True
    net = _FakeNet()


def test_a7s09_dense_support_floor_does_not_lower_a3_ball_floor():
    frame = np.zeros((640, 640, 3), dtype=np.uint8)
    people, a3_balls, support = dtr._detect_dense_people_and_ball(
        _FakeDetector(), frame, include_a7_support=True
    )
    assert len(people) == 1
    assert a3_balls == []
    assert len(support) == 1
    assert support[0]["support_only"] is True
    assert support[0]["proof_eligible"] is False
    assert dtr.DENSE_BALL_CONF_T == .03
    assert dtr.A7_BALL_SUPPORT_CONF_T == .001


def test_a7s10_injected_two_tuple_detector_contract_still_works():
    dense = [{"media_ms": 1000, "scene_id": "s1", "frame_bgr": np.zeros((32,32,3), dtype=np.uint8),
              "time_authority": "ACTUAL_MEDIA_PTS", "used_fallback": False}]
    out = dtr.refine_window(dense, {}, {}, "s1", detector_fn=lambda _frame: ([], []))
    assert out["status"] == "ok"
    assert out["frames"][0]["ball_candidates"] == []
    assert out["frames"][0]["a7_ball_support_candidates"] == []
