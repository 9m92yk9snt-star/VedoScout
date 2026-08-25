"""FIX10A — Sequence Intelligence open-world integration contract."""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

import football_sequence_intelligence as fsi  # noqa: E402


def test_open_int01_unknown_visible_action_survives_normalisation_without_stat_authority():
    plan = {
        "analysis_windows": [{
            "sequence_id": "seq_open",
            "scene_id": "scene_001",
            "start_ms": 1000,
            "end_ms": 3000,
        }]
    }
    raw = {
        "sequences": [{
            "sequence_id": "seq_open",
            "scene_id": "scene_001",
            "start_ms": 1000,
            "end_ms": 3000,
            "summary": "visible novel action",
            "actions": [{
                "action_id": "a-open-1",
                "kind": "SHOULDER_DROP_WITH_INSIDE_EXIT",
                "raw_kind": "SHOULDER_DROP_WITH_INSIDE_EXIT",
                "raw_description": "Shoulder drop shifts defender before an inside exit.",
                "start_ms": 1500,
                "contact_ms": None,
                "end_ms": 1900,
                "target_status": "VERIFIED",
                "actor_local_track_id": "p001",
                "actor_candidate_local_track_ids": ["p001"],
                "actor_box": {"x": .1, "y": .2, "w": .1, "h": .3},
                "actor_evidence": [{
                    "media_ms": 1600,
                    "box": {"x": .1, "y": .2, "w": .1, "h": .3},
                    "visibility": "VISIBLE",
                }],
                "evidence_ms": [1600, 1800],
                "foot": "UNKNOWN",
                "pressure": {"level": "MEDIUM", "nearby_players": 1},
                "details": ["defender shifts outside"],
                "outcome": "UNKNOWN",
                "outcome_visible": False,
                "causal_chain": {"continuous_visible_sequence": False},
                "contact_visibility": "UNKNOWN",
                "duplicate_of": None,
            }],
        }],
        "coverage": [{
            "sequence_id": "seq_open",
            "reviewed": True,
            "target_seen": True,
            "actions_found": 1,
        }],
    }
    out = fsi.normalise_sequence_analysis(raw, plan)
    assert out["coverage_complete"] is True
    action = out["sequences"][0]["actions"][0]
    assert action["kind"] == "OTHER"
    assert action["raw_kind"] == "SHOULDER_DROP_WITH_INSIDE_EXIT"
    assert "inside exit" in action["raw_description"]
    assert action["raw_observation_authority"] == "PERCEPTION_CONTEXT_ONLY"
    assert action["raw_countable_stat"] is False
    assert "SHOULDER_DROP_WITH_INSIDE_EXIT" not in fsi.ACTION_KINDS
