"""FIX09B.1 — deterministic multi-player + ball scene-graph tests.

These tests exercise only the pure graph assembly layer. They deliberately do
not require OpenCV, the ONNX detector, network calls, or model inference.
"""
import copy
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

import football_scene_graph as fsg  # noqa: E402


TARGET = {"x": 0.10, "y": 0.20, "w": 0.10, "h": 0.30}
OTHER = {"x": 0.65, "y": 0.22, "w": 0.10, "h": 0.30}


def authority(rows=None, unresolved=None):
    pts = []
    for ms, box in (rows or []):
        pts.append({
            "media_ms": int(ms),
            "scene_id": "identity_scene_001",
            "global_target_id": "GLOBAL_TARGET",
            "box": dict(box),
            "state": "VISIBLE",
            "identity_strength": "GLOBAL",
            "sources": ["FIX09A"],
            "primary_source": "FIX09A",
            "predicted": False,
            "proof_eligible": True,
            "tap_authority": False,
            "reason": None,
            "hypotheses": [],
        })
    return {
        "version": 1,
        "status": "ok" if pts else "unresolved",
        "global_target_id": "GLOBAL_TARGET",
        "timebase": "canonical_media_ms",
        "scenes": [{"scene_id": "identity_scene_001", "start_ms": 0, "end_ms": 5000}],
        "target_points": pts,
        "unresolved_intervals": list(unresolved or []),
        "tap_times_ms": [],
        "metrics": {},
    }


def det(box, conf=0.9, team=None):
    return {"box": dict(box), "confidence": conf, "team": team}


def ball(x=0.145, y=0.485, conf=0.8):
    return {"box": {"x": x, "y": y, "w": 0.02, "h": 0.02}, "confidence": conf}


def obs(ms, players=None, balls=None, cut=False, cam_dx=0.0, cam_dy=0.0):
    return {
        "media_ms": int(ms),
        "cut": bool(cut),
        "cam_dx": cam_dx,
        "cam_dy": cam_dy,
        "players": list(players or []),
        "balls": list(balls or []),
    }


def test_b101_empty_input_is_explicitly_empty():
    out = fsg.assemble_scene_graph([], authority())
    assert out["status"] == "empty"
    assert out["frames"] == []
    assert out["global_target_id"] == "GLOBAL_TARGET"


def test_b102_verified_global_target_maps_to_one_scene_local_track():
    auth = authority([(0, TARGET), (125, TARGET), (250, TARGET)])
    out = fsg.assemble_scene_graph([
        obs(0, [det(TARGET), det(OTHER)]),
        obs(125, [det(TARGET), det(OTHER)]),
        obs(250, [det(TARGET), det(OTHER)]),
    ], auth)
    assert out["status"] == "ok"
    assert out["metrics"]["target_verified_frames"] == 3
    ids = [fr["global_target"]["local_track_id"] for fr in out["frames"]]
    assert len(set(ids)) == 1
    assert all(fr["global_target"]["status"] == "VERIFIED" for fr in out["frames"])


def test_b103_scene_cut_resets_only_local_tracks_not_global_target_identity():
    auth = authority([(0, TARGET), (125, TARGET), (1000, TARGET), (1125, TARGET)])
    out = fsg.assemble_scene_graph([
        obs(0, [det(TARGET), det(OTHER)]),
        obs(125, [det(TARGET), det(OTHER)]),
        obs(1000, [det(TARGET), det(OTHER)], cut=True),
        obs(1125, [det(TARGET), det(OTHER)]),
    ], auth)
    assert len(out["scenes"]) == 2
    assert out["frames"][0]["scene_id"] != out["frames"][2]["scene_id"]
    assert out["frames"][0]["global_target"]["status"] == "VERIFIED"
    assert out["frames"][2]["global_target"]["status"] == "VERIFIED"
    # p001 may legally repeat because player ids are scene-local, never global.
    assert out["frames"][0]["global_target"]["local_track_id"] == "p001"
    assert out["frames"][2]["global_target"]["local_track_id"] == "p001"


def test_b104_close_two-player_target_mapping_remains_bounded_hypotheses():
    # Equal-distance bodies on opposite sides of the canonical target must not
    # be resolved by list order or detector confidence.
    left = {"x": 0.09, "y": 0.20, "w": 0.10, "h": 0.30}
    right = {"x": 0.11, "y": 0.20, "w": 0.10, "h": 0.30}
    auth = authority([(0, TARGET)])
    out = fsg.assemble_scene_graph([obs(0, [det(left), det(right)])], auth)
    tm = out["frames"][0]["global_target"]
    assert tm["status"] == "HYPOTHESES"
    assert tm["local_track_id"] is None
    assert 2 <= len(tm["candidate_local_track_ids"]) <= 3
    assert tm["proof_eligible"] is False


def test_b105_unresolved_identity_hypotheses_project_to_physical_local_tracks():
    auth = authority([])
    auth["target_points"] = [{
        "media_ms": 1000,
        "scene_id": "identity_scene_001",
        "global_target_id": "GLOBAL_TARGET",
        "box": None,
        "state": "UNRESOLVED",
        "identity_strength": "UNRESOLVED",
        "sources": ["FIX04", "FIX09A"],
        "primary_source": None,
        "predicted": False,
        "proof_eligible": False,
        "tap_authority": False,
        "reason": "SOURCE_CONFLICT",
        "hypotheses": [
            {"source": "FIX04", "media_ms": 1000, "box": dict(TARGET)},
            {"source": "FIX09A", "media_ms": 1000, "box": dict(OTHER)},
        ],
    }]
    out = fsg.assemble_scene_graph([obs(1000, [det(TARGET), det(OTHER)])], auth)
    tm = out["frames"][0]["global_target"]
    assert tm["status"] == "HYPOTHESES"
    assert tm["local_track_id"] is None
    assert len(tm["candidate_local_track_ids"]) == 2
    assert tm["proof_eligible"] is False


def test_b106_missing_ball_is_explicit_and_never_fabricated():
    auth = authority([(0, TARGET)])
    out = fsg.assemble_scene_graph([obs(0, [det(TARGET)], [])], auth)
    fr = out["frames"][0]
    assert fr["ball"] is None
    assert fr["ball_state"] == "MISSING"
    assert fr["possession"]["status"] == "NO_BALL"


def test_b107_ball_near_target_feet_creates_target_possession_hypothesis():
    auth = authority([(0, TARGET)])
    out = fsg.assemble_scene_graph([obs(0, [det(TARGET), det(OTHER)], [ball()])], auth)
    p = out["frames"][0]["possession"]
    assert p["holder_local_track_id"] == out["frames"][0]["global_target"]["local_track_id"]
    assert p["target_relation"] == "TARGET_LIKELY_POSSESSION"
    assert out["metrics"]["target_possession_frames"] == 1


def test_b108_ball_continuity_can_beat_a_far_high_confidence_false_candidate():
    auth = authority([(0, TARGET), (125, TARGET)])
    near0 = ball(0.145, 0.485, 0.75)
    near1 = ball(0.155, 0.485, 0.52)
    far1 = ball(0.85, 0.10, 0.88)
    out = fsg.assemble_scene_graph([
        obs(0, [det(TARGET)], [near0]),
        obs(125, [det(TARGET)], [far1, near1]),
    ], auth)
    b = out["frames"][1]["ball"]
    assert abs(b["box"]["x"] - near1["box"]["x"]) < 1e-9


def test_b109_ambiguous_possession_does_not_pick_a_holder():
    p1 = {"x": 0.10, "y": 0.20, "w": 0.10, "h": 0.30}
    p2 = {"x": 0.18, "y": 0.20, "w": 0.10, "h": 0.30}
    mid_ball = ball(0.18, 0.485, 0.8)
    auth = authority([(0, p1)])
    out = fsg.assemble_scene_graph([obs(0, [det(p1), det(p2)], [mid_ball])], auth)
    pos = out["frames"][0]["possession"]
    assert pos["status"] in ("AMBIGUOUS", "CANDIDATE")
    if pos["status"] == "AMBIGUOUS":
        assert pos["holder_local_track_id"] is None


def test_b110_scene_graph_does_not_mutate_identity_authority():
    auth = authority([(0, TARGET), (125, TARGET)])
    before = copy.deepcopy(auth)
    fsg.assemble_scene_graph([
        obs(0, [det(TARGET)], [ball()]),
        obs(125, [det(TARGET)], [ball(0.15, 0.485, 0.8)]),
    ], auth)
    assert auth == before


def test_b111_team_labels_are_preserved_when_supplied_by_ingestion():
    auth = authority([(0, TARGET)])
    out = fsg.assemble_scene_graph([
        obs(0, [det(TARGET, team="target_team"), det(OTHER, team="opponent")])
    ], auth)
    teams = {p["team"] for p in out["frames"][0]["players"]}
    assert teams == {"target_team", "opponent"}


def test_b112_every_frame_uses_canonical_media_ms_and_global_target_contract():
    auth = authority([(250, TARGET), (500, TARGET)])
    out = fsg.assemble_scene_graph([
        obs(500, [det(TARGET)]),
        obs(250, [det(TARGET)]),
    ], auth)
    assert out["timebase"] == "canonical_media_ms"
    assert [f["media_ms"] for f in out["frames"]] == [250, 500]
    assert out["global_target_id"] == "GLOBAL_TARGET"
