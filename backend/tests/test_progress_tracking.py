"""
Tests for the Progress Tracking module — Tier 3 progress engine.
"""
import asyncio
from datetime import datetime, timezone, timedelta

import pytest
from progress_tracking import (
    _verdict, _age_adjusted_percentile, _compute_badges,
    _archetype_tier_from_report, _band_for_age,
    _build_archetype_overlay, _build_mission_status,
    _normalize_name, _pass_active, PASS_CREDITS,
)


# ─── Verdict logic ────────────────────────────────────────────────────────

def _snap(months_ago, age, overall, **pillars):
    base = datetime.now(timezone.utc) - timedelta(days=months_ago * 30)
    return {
        "date": base.isoformat(),
        "age": age,
        "overall": overall,
        "pillars": {"technical": pillars.get("tech"),
                    "tactical": pillars.get("tac"),
                    "physical": pillars.get("phys"),
                    "mental": pillars.get("ment"),
                    "decision_making": pillars.get("dm")},
    }


def test_verdict_first_report_when_one():
    assert _verdict([_snap(0, 13, 7.0)]) == "first_report"


def test_verdict_ahead_when_fast_growth():
    timeline = [_snap(6, 13, 6.5), _snap(0, 14, 7.5)]
    assert _verdict(timeline) == "ahead"


def test_verdict_plateau_when_no_change():
    timeline = [_snap(6, 13, 7.0), _snap(0, 14, 7.0)]
    assert _verdict(timeline) == "plateau"


def test_verdict_on_track_when_moderate():
    timeline = [_snap(6, 13, 7.0), _snap(0, 14, 7.2)]
    assert _verdict(timeline) == "on_track"


# ─── Age-adjusted percentile ──────────────────────────────────────────────

def test_age_adjusted_percentile_known_anchor():
    # 7.0 at age 13 sits at the bracket base → 50th percentile
    assert _age_adjusted_percentile(7.0, 13) == 50.0


def test_age_adjusted_percentile_age_aware_drop():
    # Same score 7.0 at age 17 is BELOW the bracket base of 7.5 → lower percentile
    pct13 = _age_adjusted_percentile(7.0, 13)
    pct17 = _age_adjusted_percentile(7.0, 17)
    assert pct17 < pct13


def test_age_adjusted_percentile_bounded():
    assert _age_adjusted_percentile(0, 10) >= 2.0
    assert _age_adjusted_percentile(10, 21) <= 98.0
    assert _age_adjusted_percentile(None, 10) is None


# ─── Badges ───────────────────────────────────────────────────────────────

def test_first_century_badge():
    timeline = [_snap(0, 13, 7.0, tech=8.0)]
    badges = _compute_badges(timeline)
    assert any(b["id"] == "first_century" for b in badges)


def test_pro_unlock_badge_at_u12_plus():
    timeline = [_snap(0, 13, 7.0)]
    badges = _compute_badges(timeline)
    assert any(b["id"] == "pro_unlock" for b in badges)


def test_no_pro_unlock_below_u12():
    timeline = [_snap(0, 10, 6.0)]
    badges = _compute_badges(timeline)
    assert not any(b["id"] == "pro_unlock" for b in badges)


def test_stage_up_badge_when_crosses_band():
    timeline = [_snap(24, 10, 6.0), _snap(0, 13, 7.0)]  # U11 → U14
    badges = _compute_badges(timeline)
    assert any(b["id"] == "stage_up" for b in badges)


# ─── Archetype overlay ────────────────────────────────────────────────────

def test_archetype_band_resolution():
    assert _band_for_age(10) == "U11"
    assert _band_for_age(13) == "U14"
    assert _band_for_age(15) == "U17"
    assert _band_for_age(19) == "U21"
    assert _band_for_age(None) is None


def test_archetype_tier_from_report_uses_benchmark_tier():
    rep = {"archetype": {"match_strength": 7.0},
           "full_report": {"overall_benchmark": {"tier": "elite_academy"}}}
    assert _archetype_tier_from_report(rep) == "elite"


def test_archetype_tier_falls_back_to_match_strength():
    rep = {"archetype": {"match_strength": 7.6}, "full_report": {}}
    assert _archetype_tier_from_report(rep) == "high"


def test_archetype_overlay_builds_curve_points():
    timeline = [_snap(6, 13, 6.5), _snap(0, 14, 7.5)]
    reports = [{"archetype": {"match_strength": 8.0}, "full_report": {"overall_benchmark": {"tier": "pro_academy"}}}] * 2
    overlay = _build_archetype_overlay(timeline, reports)
    assert overlay is not None
    assert overlay["tier_key"] == "high"
    assert len(overlay["points"]) == 2
    assert overlay["points"][0]["archetype_overall"] is not None
    assert overlay["points"][0]["band"] == "U14"


# ─── Mission status ───────────────────────────────────────────────────────

def test_mission_status_evaluates_previous_focus_hit():
    reports = [
        {"id": "r1", "player_details": {"age": 13},
         "full_report": {"scores": {"overall_development": 6.5, "technical": 6.0, "tactical": 7.0, "physical": 5.5}},
         "mission_focus": ["technical", "physical"]},
        {"id": "r2", "player_details": {"age": 14},
         "full_report": {"scores": {"overall_development": 7.5, "technical": 7.5, "tactical": 7.5, "physical": 7.0}}},
    ]
    mission = _build_mission_status(reports)
    assert mission["previous_mission"] == ["technical", "physical"]
    pillar_results = {r["pillar"]: r for r in mission["previous_results"]}
    assert pillar_results["technical"]["improved"] is True
    assert pillar_results["physical"]["improved"] is True
    assert len(mission["next_mission"]) <= 2


def test_mission_status_handles_single_report():
    reports = [{"id": "r1", "player_details": {"age": 13},
                "full_report": {"scores": {"technical": 6.0, "tactical": 7.0}}}]
    mission = _build_mission_status(reports)
    assert mission["previous_mission"] is None
    assert mission["next_mission"]  # always suggests weakest


# ─── Pass + name helpers ──────────────────────────────────────────────────

def test_normalize_name():
    assert _normalize_name("  Lukas   A. ") == "lukas a."
    assert _normalize_name("") == ""


def test_pass_active_when_credits_and_not_expired():
    exp = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
    state = _pass_active({"progress_pass": {"credits_remaining": 2, "expires_at": exp}})
    assert state["active"] is True
    assert state["credits_remaining"] == 2


def test_pass_inactive_when_expired():
    exp = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    state = _pass_active({"progress_pass": {"credits_remaining": 2, "expires_at": exp}})
    assert state["active"] is False


def test_pass_inactive_when_no_credits():
    exp = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
    state = _pass_active({"progress_pass": {"credits_remaining": 0, "expires_at": exp}})
    assert state["active"] is False


def test_pass_credits_constant():
    assert PASS_CREDITS == 3
