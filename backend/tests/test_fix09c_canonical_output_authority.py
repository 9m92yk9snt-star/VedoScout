"""FIX09C — one event truth projected to every report/evidence surface."""
import copy
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

import canonical_output_authority as coa  # noqa: E402


BOX = {"x": .1, "y": .2, "w": .1, "h": .3}


def event(*, eid="evt_fixed", et="GOAL", at="SHOT", out="GOAL", ms=1000,
          causal=True, contact_geom=True, details=None):
    proof = {
        "proof_start_ms": 500, "proof_end_ms": 2500,
        "evidence_ms": [900, 1000, 1400],
        "actor_keyframes": [
            {"media_ms": 900, "box": dict(BOX), "visibility": "VISIBLE"},
            {"media_ms": 1100, "box": dict(BOX), "visibility": "VISIBLE"},
        ],
        "contact_geometry": ({"media_ms": ms, "box": dict(BOX), "visibility": "VISIBLE"}
                             if contact_geom else None),
        "contact_visibility": "VISIBLE" if contact_geom else "OCCLUDED",
        "outcome_ms": 1400 if et == "GOAL" else None,
        "proof_eligible": True, "causal_verified": causal,
    }
    return {
        "event_id": eid, "global_target_id": "GLOBAL_TARGET", "scene_id": "scene_001",
        "sequence_id": "seq_1", "source_sequence_ids": ["seq_1"],
        "source_action_ids": ["a1"], "start_ms": 800, "contact_ms": ms,
        "end_ms": 1600, "canonical_ms": ms,
        "canonical_event_type": et, "canonical_action_type": at,
        "canonical_outcome": out, "causal_verified": causal,
        "resolution_reason": "test", "actor_local_track_id": "p001",
        "identity_resolution": "VISIBLE_TARGET_MATCH", "foot": "RIGHT",
        "pressure": {"level": "MEDIUM", "nearby_players": 1},
        "details": details or ["turns before the action", "creates separation"],
        "proof": proof,
        "causal_chain": {"target_contact_ms": ms, "goal_outcome_ms": 1400},
    }


def bundle(events):
    return {"status": "ok", "events": list(events), "unresolved": [], "rejected": [],
            "metrics": {"observations_total": len(events), "events_accepted": len(events)}}


def test_c01_projected_timeline_preserves_stable_b3_event_id_and_exact_ms():
    e = event()
    row = coa.project_timeline(bundle([e]))[0]
    assert row["event_id"] == "evt_fixed"
    assert row["event_start_ms"] == 1000
    assert row["timestamp"] == "00:01"
    assert row["cross_verified"] is True
    assert row["event_source"] == "fix09b_canonical"


def test_c02_goal_maps_into_existing_fix07_stats_contract_without_losing_rich_type():
    row = coa.project_event(event())
    assert row["canonical_event_type"] == "GOAL"
    assert row["canonical_action_type"] == "SHOT"
    assert row["canonical_result"] == "SCORED"
    assert row["football_event_type"] == "GOAL"


def test_c03_assist_maps_to_pass_plus_teammate_scored_for_fix07():
    row = coa.project_event(event(et="ASSIST", at="PASS", out="TEAMMATE_GOAL"))
    assert row["canonical_event_type"] == "ASSIST"
    assert row["canonical_action_type"] == "PASS"
    assert row["canonical_result"] == "TEAMMATE_SCORED"


def test_c04_micro_action_remains_rich_detail_but_does_not_fake_a_stats_category():
    row = coa.project_event(event(et="FEINT", at="FEINT", out="UNKNOWN", causal=True))
    assert row["football_action_type"] == "FEINT"
    assert row["canonical_action_type"] == "OTHER"
    assert row["canonical_event_type"] == "OTHER"
    assert row["title"] == "Body feint"


def test_c05_visible_contact_is_the_event_native_proof_frame():
    row = coa.build_event_native_evidence(bundle([event(contact_geom=True)]))[0]
    assert row["event_id"] == "evt_fixed"
    assert row["evidence_time_ms"] == 1000
    assert row["event_keyframe_kind"] == "CONTACT"
    assert row["event_track_locked"] is True
    assert row["event_track_box"] == BOX


def test_c06_occluded_contact_uses_adjacent_visible_same_event_frame_not_fake_contact_box():
    row = coa.build_event_native_evidence(bundle([event(contact_geom=False)]))[0]
    assert row["event_id"] == "evt_fixed"
    assert row["evidence_time_ms"] in (900, 1100)
    assert row["event_keyframe_kind"] == "ADJACENT_VISIBLE"
    assert row["canonical_event_ms"] == 1000


def test_c07_evidence_without_visible_actor_keyframe_is_omitted_not_fabricated():
    e = event(contact_geom=False)
    e["proof"]["actor_keyframes"] = []
    assert coa.build_event_native_evidence(bundle([e])) == []


def test_c08_apply_to_report_replaces_model_timeline_with_canonical_truth():
    full = {"action_timeline": [{"timestamp": "00:09", "title": "invented"}],
            "video_comments": []}
    out = coa.apply_to_report(full, bundle([event()]), {"coverage_complete": True})
    assert len(out["action_timeline"]) == 1
    assert out["action_timeline"][0]["event_id"] == "evt_fixed"
    assert out["event_discovery"]["authority"] == "FIX09B_CANONICAL_EVENTS"
    assert out["event_discovery"]["event_discovery_complete"] is True


def test_c09_apply_to_report_keeps_unrelated_existing_comments_and_adds_bound_event_evidence():
    full = {"video_comments": [{"timestamp": "00:05", "comment": "existing"}]}
    out = coa.apply_to_report(full, bundle([event()]), {"coverage_complete": True})
    assert len(out["video_comments"]) == 2
    bound = [r for r in out["video_comments"] if r.get("event_id") == "evt_fixed"]
    assert len(bound) == 1


def test_c10_apply_is_idempotent_for_event_native_evidence_by_event_id():
    full = {"video_comments": []}
    out = coa.apply_to_report(full, bundle([event()]), {"coverage_complete": True})
    out = coa.apply_to_report(out, bundle([event()]), {"coverage_complete": True})
    assert len([r for r in out["video_comments"] if r.get("event_id") == "evt_fixed"]) == 1


def test_c11_compat_ledger_is_projection_only_and_reports_b3_as_authority():
    led = coa.build_ledger_compat(bundle([event()]), coverage_complete=True)
    assert led["authority"] == "FIX09B_CANONICAL_EVENTS"
    assert led["discovery_complete"] is True
    assert led["track_usable"] is True
    assert led["events"][0]["event_id"] == "evt_fixed"


def test_c12_output_projection_does_not_mutate_canonical_bundle():
    b = bundle([event()]); before = copy.deepcopy(b)
    coa.project_timeline(b)
    coa.build_event_native_evidence(b)
    assert b == before


def test_c13_proof_window_is_carried_from_same_canonical_event():
    row = coa.project_event(event())
    assert row["proof_window"] == {"start_ms": 500, "end_ms": 2500}


def test_c14_event_native_evidence_priority_prefers_goal_and_assist():
    evs = [
        event(eid="p", et="PASS", at="PASS", out="COMPLETED", ms=100),
        event(eid="g", et="GOAL", at="SHOT", out="GOAL", ms=200),
        event(eid="a", et="ASSIST", at="PASS", out="TEAMMATE_GOAL", ms=300),
    ]
    rows = coa.build_event_native_evidence(bundle(evs), max_rows=2)
    assert [r["event_id"] for r in rows] == ["g", "a"]
