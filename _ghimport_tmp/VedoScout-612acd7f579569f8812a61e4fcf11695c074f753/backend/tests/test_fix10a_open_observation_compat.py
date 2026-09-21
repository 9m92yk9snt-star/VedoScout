"""FIX10A — open-world observation preservation regression tests."""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

import open_observation_compat as ooc  # noqa: E402


def test_open01_unknown_action_survives_as_raw_kind():
    raw = {
        "kind": "SHOULDER_DROP_WITH_INSIDE_EXIT",
        "raw_description": "Drops the shoulder, shifts defender, then exits inside.",
        "details": ["defender commits outside"],
    }
    legacy = {"kind": "OTHER", "start_ms": 1000, "end_ms": 1200}
    out = ooc.preserve_open_observation(raw, legacy)
    assert out["kind"] == "OTHER"
    assert out["raw_kind"] == "SHOULDER_DROP_WITH_INSIDE_EXIT"
    assert "exits inside" in out["raw_description"]


def test_open02_legacy_canonical_fields_cannot_be_overwritten_by_raw_data():
    raw = {"kind": "GOAL", "outcome": "GOAL", "actor_local_track_id": "wrong"}
    legacy = {
        "kind": "OTHER", "outcome": "UNKNOWN",
        "actor_local_track_id": None, "start_ms": 1000, "end_ms": 1100,
    }
    out = ooc.preserve_open_observation(raw, legacy)
    assert out["kind"] == "OTHER"
    assert out["outcome"] == "UNKNOWN"
    assert out["actor_local_track_id"] is None
    assert out["raw_kind"] == "GOAL"


def test_open03_raw_observation_is_never_countable_stat_authority():
    out = ooc.preserve_open_observation(
        {"kind": "SHOT", "raw_description": "possible strike"},
        {"kind": "OTHER"},
    )
    assert out["raw_countable_stat"] is False
    assert out["raw_observation_authority"] == "PERCEPTION_CONTEXT_ONLY"
    assert ooc.raw_observation_is_countable(out) is False


def test_open04_malformed_unbounded_text_is_sanitized_and_bounded():
    raw = {
        "kind": "X\x00" + "Y" * 400,
        "raw_description": "  visible\n\tbehaviour  " + "z" * 1000,
        "details": ["a\x00b" + "q" * 500] * 30,
    }
    out = ooc.preserve_open_observation(raw, {"kind": "OTHER"})
    assert "\x00" not in out["raw_kind"]
    assert len(out["raw_kind"]) <= ooc.MAX_RAW_KIND
    assert len(out["raw_description"]) <= ooc.MAX_RAW_DESCRIPTION
    assert len(out["raw_details"]) <= ooc.MAX_RAW_DETAILS
    assert all("\x00" not in x and len(x) <= ooc.MAX_RAW_DETAIL for x in out["raw_details"])
