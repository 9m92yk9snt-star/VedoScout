"""FIX10A5 — physical Touch Graph / possession-chain tests."""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

import touch_graph as tg  # noqa: E402


P15 = {"x": 0.10, "y": 0.20, "w": 0.10, "h": 0.30}
P10 = {"x": 0.48, "y": 0.20, "w": 0.10, "h": 0.30}
P12 = {"x": 0.56, "y": 0.20, "w": 0.10, "h": 0.30}


def _contact(ms, player, *, kind="CONTROL_TOUCH", status="VERIFIED", conf=0.88,
             before=None, after=None, scene="scene_001"):
    return {
        "contact_id": f"c_{ms}_{player or 'amb'}",
        "media_ms": int(ms),
        "scene_id": scene,
        "player_track_id": player,
        "player_candidate_track_ids": [player] if player else ["p010", "p012"],
        "status": status,
        "contact_visibility": "VISIBLE" if status == "VERIFIED" else "OCCLUDED",
        "proof_eligible": status == "VERIFIED",
        "foot": "UNKNOWN",
        "confidence": float(conf),
        "contact_geometry": {"score": 0.9, "distance_h": 0.1},
        "trajectory_evidence": {"score": 0.8},
        "possession_evidence": {
            "kind": kind,
            "score": 1.0 if kind in {"RELEASE", "RECEIVE"} else 0.65,
            "before_holder": before,
            "after_holder": after,
        },
        "ball_before": {"media_ms": int(ms) - 40, "state": "MEASURED"},
        "ball_after": {"media_ms": int(ms) + 40, "state": "MEASURED"},
        "rejection_reasons": [],
    }


def _player(track_id, box, team="target_team"):
    return {
        "local_track_id": track_id,
        "box": dict(box),
        "team": team,
        "team_confidence": 0.9,
        "team_source": "KIT_CHROMA_SCENE_CLUSTER",
    }


def _dense(ms, *, target_track=None, target_status="UNRESOLVED"):
    return {
        "media_ms": int(ms),
        "scene_id": "scene_001",
        "players": [
            _player("p015", P15),
            _player("p010", P10),
            _player("p012", P12),
        ],
        "global_target": {
            "status": target_status,
            "local_track_id": target_track if target_status == "VERIFIED" else None,
            "candidate_local_track_ids": [target_track] if target_track else [],
            "proof_eligible": target_status == "VERIFIED",
        },
    }


def _identity_ok(monkeypatch):
    monkeypatch.setattr(
        tg.uia,
        "resolve_target_at",
        lambda *_a, **_k: ({"proof_eligible": True, "box": dict(P15)}, "OK_EXACT"),
    )


def test_a501_repeated_frame_contacts_collapse_to_one_physical_touch(monkeypatch):
    _identity_ok(monkeypatch)
    result = tg.build_touch_graph(
        {"contacts": [
            _contact(1000, "p015", before="p015", after="p015"),
            _contact(1080, "p015", before="p015", after="p015"),
        ]},
        {}, [_dense(1040, target_track="p015", target_status="VERIFIED")],
    )
    assert len(result["touches"]) == 1
    touch = result["touches"][0]
    assert touch["frame_contact_count"] == 2
    assert touch["media_ms"] == 1000
    assert touch["end_ms"] == 1080


def test_a502_separate_real_touches_are_not_collapsed(monkeypatch):
    _identity_ok(monkeypatch)
    result = tg.build_touch_graph(
        {"contacts": [
            _contact(1000, "p015", before="p015", after=None, kind="RELEASE"),
            _contact(1300, "p015", before=None, after="p015", kind="RECEIVE"),
        ]},
        {}, [_dense(1000, target_track="p015", target_status="VERIFIED"),
             _dense(1300, target_track="p015", target_status="VERIFIED")],
    )
    assert len(result["touches"]) == 2
    assert result["touches"][0]["touch_id"] != result["touches"][1]["touch_id"]


def test_a503_target_release_to_other_player_touch_is_ordered(monkeypatch):
    _identity_ok(monkeypatch)
    result = tg.build_touch_graph(
        {"contacts": [
            _contact(1000, "p015", kind="RELEASE", before="p015", after=None),
            _contact(1300, "p010", kind="RECEIVE", before=None, after="p010"),
        ]},
        {}, [_dense(1000, target_track="p015", target_status="VERIFIED"), _dense(1300)],
    )
    assert [t["player_track_id"] for t in result["touches"]] == ["p015", "p010"]
    assert result["touches"][0]["global_target_id"] == "GLOBAL_TARGET"
    assert result["touches"][1]["global_target_id"] is None


def test_a504_nearby_number12_without_physical_contact_gets_zero_touch_nodes(monkeypatch):
    _identity_ok(monkeypatch)
    # p012 exists in every dense frame and is spatially close to p010, but A5
    # consumes accepted contacts rather than proximity and must create no p012 touch.
    result = tg.build_touch_graph(
        {"contacts": [
            _contact(1000, "p015", kind="RELEASE", before="p015", after=None),
            _contact(1300, "p010", kind="RECEIVE", before=None, after="p010"),
        ]},
        {}, [_dense(1000, target_track="p015", target_status="VERIFIED"), _dense(1300)],
    )
    assert sum(t["player_track_id"] == "p012" for t in result["touches"]) == 0
    assert result["touches"][1]["player_track_id"] == "p010"


def test_a505_release_creates_explicit_free_ball_in_flight_segment(monkeypatch):
    _identity_ok(monkeypatch)
    result = tg.build_touch_graph(
        {"contacts": [
            _contact(1000, "p015", kind="RELEASE", before="p015", after=None),
            _contact(1300, "p010", kind="RECEIVE", before=None, after="p010"),
        ]},
        {}, [_dense(1000, target_track="p015", target_status="VERIFIED"), _dense(1300)],
    )
    assert len(result["possession_segments"]) == 1
    segment = result["possession_segments"][0]
    assert segment["status"] == "FREE_BALL_IN_FLIGHT"
    assert segment["holder_local_track_id"] is None
    assert segment["start_ms"] == 1000
    assert segment["end_ms"] == 1300


def test_a506_identity_ambiguity_propagates_instead_of_upgrading_target(monkeypatch):
    monkeypatch.setattr(
        tg.uia,
        "resolve_target_at",
        lambda *_a, **_k: ({"proof_eligible": False, "box": dict(P15)}, "INTERPOLATED"),
    )
    result = tg.build_touch_graph(
        {"contacts": [_contact(1000, "p015")]},
        {}, [_dense(1000, target_track="p015", target_status="HYPOTHESES")],
    )
    touch = result["touches"][0]
    assert touch["status"] == "VERIFIED"  # physical touch may still be verified
    assert touch["global_target_id"] is None
    assert touch["global_target_resolution"]["status"] == "UNRESOLVED"


def test_a507_touch_graph_has_no_goal_assist_or_canonical_event_authority(monkeypatch):
    _identity_ok(monkeypatch)
    result = tg.build_touch_graph(
        {"contacts": [_contact(1000, "p015")]},
        {}, [_dense(1000, target_track="p015", target_status="VERIFIED")],
    )
    assert "canonical_events" not in result
    assert "goals" not in result
    assert "assists" not in result
    touch = result["touches"][0]
    forbidden = {"goal", "assist", "scorer", "canonical_event_type"}
    assert forbidden.isdisjoint(touch)
