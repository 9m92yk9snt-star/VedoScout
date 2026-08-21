"""FIX 09B.0 — integration tests for unified identity → FIX08 actor authority.

These tests exercise the real legacy event_ledger actor gate.  They protect the
migration invariant that FIX09A can extend event-contact coverage without ever
turning unresolved/predicted identity into proof.
"""
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

import event_ledger  # noqa: E402
import unified_event_bridge as bridge  # noqa: E402


BOX = {"x": 0.20, "y": 0.25, "w": 0.10, "h": 0.30}


def tl_point(ms, *, box=None, predicted=False, proof=True, scene="scene_001"):
    return {
        "media_ms": int(ms),
        "scene_id": scene,
        "local_track_id": "p01",
        "box": dict(box or BOX),
        "state": "OCCLUDED" if predicted else "VISIBLE",
        "identity_score": 0.9,
        "geometry_source": "predicted" if predicted else "detection",
        "predicted": bool(predicted),
        "proof_eligible": bool(proof),
    }


def timeline(points, unresolved=None):
    return {
        "version": 1,
        "status": "ok",
        "global_target_id": "GLOBAL_TARGET",
        "scenes": [{"scene_id": "scene_001", "start_ms": 0, "end_ms": 2000}],
        "target_points": list(points),
        "unresolved_intervals": list(unresolved or []),
    }


def dense_points(*, predicted_ms=None):
    rows = []
    for ms in range(0, 2000, 100):
        pred = ms == predicted_ms
        rows.append(tl_point(ms, predicted=pred, proof=not pred))
    return rows


def discovery(contact_ms=1000):
    return {
        "events": [{
            "sequence_id": "s1",
            "start_ms": 900,
            "contact_ms": int(contact_ms),
            "end_ms": 1200,
            "action_type": "SHOT",
            "foot": "RIGHT",
            "actor_box": dict(BOX),
            "outcome": "SAVED",
            "outcome_visible": True,
            "scoring_chain": None,
            "description": "Target shoots and goalkeeper saves.",
        }],
        "coverage": [{"start_ms": 0, "end_ms": 2000,
                      "target_seen": True, "events_found": 1}],
    }


def test_B0E01_fix09a_global_geometry_can_reach_real_fix08_actor_gate():
    """A FIX04 gap must no longer mean an automatic event loss when the
    unified GLOBAL_TARGET has proof-grade geometry at the action contact."""
    bundle = bridge.build_identity_bundle(
        fix04_track=None,
        identity_timeline=timeline(dense_points()),
        anchors=[],
    )
    tr, source = bridge.choose_event_track(bundle, fallback_fix04_track=None)
    assert source == "UNIFIED_IDENTITY"
    assert tr and tr["metrics"]["geometry_points"] >= 10

    led = event_ledger.build_ledger(discovery(), tr, 2.0)
    assert led["track_usable"] is True
    assert led["candidates_total"] == 1
    assert led["candidates_verified"] == 1
    assert len(led["events"]) == 1
    assert led["events"][0]["actor_spatial_verified"] is True


def test_B0E02_predicted_identity_never_becomes_contact_proof_by_interpolation():
    """A continuity-only point at the contact time is a hard barrier, even
    though valid neighbours are only 100 ms away on both sides."""
    bundle = bridge.build_identity_bundle(
        fix04_track=None,
        identity_timeline=timeline(dense_points(predicted_ms=1000)),
        anchors=[],
    )
    tr, source = bridge.choose_event_track(bundle, fallback_fix04_track=None)
    assert source == "UNIFIED_IDENTITY"
    barriers = [p for p in tr["points"] if p.get("identity_barrier")]
    assert any(abs(p["t"] - 1.0) < 1e-9 for p in barriers)

    led = event_ledger.build_ledger(discovery(), tr, 2.0)
    assert led["candidates_verified"] == 0
    assert led["dropped"] == [{"sequence_id": "s1", "reason": "TRACK_GAP"}]


def test_B0E03_explicit_identity_conflict_blocks_short_gap_interpolation():
    """Removing a conflict point alone is unsafe because FIX08 interpolates
    gaps <=250 ms.  Boundary barriers must stop that reconstruction."""
    auth = {
        "version": 1,
        "status": "ok",
        "global_target_id": "GLOBAL_TARGET",
        "timebase": "canonical_media_ms",
        "scenes": [{"scene_id": "scene_001", "start_ms": 0, "end_ms": 2000}],
        "target_points": [
            {
                "media_ms": ms, "scene_id": "scene_001", "global_target_id": "GLOBAL_TARGET",
                "box": dict(BOX), "state": "VISIBLE", "identity_strength": "GLOBAL",
                "sources": ["FIX09A"], "primary_source": "FIX09A", "predicted": False,
                "proof_eligible": True, "tap_authority": False, "reason": None,
                "hypotheses": [],
            }
            for ms in range(0, 2000, 100)
        ],
        "unresolved_intervals": [{
            "scene_id": "scene_001", "start_ms": 950, "end_ms": 1050,
            "reason": "SOURCE_CONFLICT",
        }],
        "tap_times_ms": [],
        "metrics": {},
    }
    tr = bridge.build_safe_event_track(auth)
    assert any(abs(p["t"] - 0.95) < 1e-9 and p.get("identity_barrier") for p in tr["points"])
    assert any(abs(p["t"] - 1.05) < 1e-9 and p.get("identity_barrier") for p in tr["points"])
    assert not any(abs(p["t"] - 1.0) < 1e-9 and not p.get("identity_barrier") for p in tr["points"])

    led = event_ledger.build_ledger(discovery(), tr, 2.0)
    assert led["candidates_verified"] == 0
    assert led["dropped"][0]["reason"] == "TRACK_GAP"


def test_B0E04_event_after_conflict_is_not_permanently_poisoned():
    """The ambiguity barrier is bounded; proof outside it remains available."""
    auth = {
        "version": 1,
        "status": "ok",
        "global_target_id": "GLOBAL_TARGET",
        "timebase": "canonical_media_ms",
        "scenes": [{"scene_id": "scene_001", "start_ms": 0, "end_ms": 2000}],
        "target_points": [
            {
                "media_ms": ms, "scene_id": "scene_001", "global_target_id": "GLOBAL_TARGET",
                "box": dict(BOX), "state": "VISIBLE", "identity_strength": "GLOBAL",
                "sources": ["FIX09A"], "primary_source": "FIX09A", "predicted": False,
                "proof_eligible": True, "tap_authority": False, "reason": None,
                "hypotheses": [],
            }
            for ms in range(0, 2000, 100)
        ],
        "unresolved_intervals": [{
            "scene_id": "scene_001", "start_ms": 950, "end_ms": 1050,
            "reason": "SOURCE_CONFLICT",
        }],
        "tap_times_ms": [],
        "metrics": {},
    }
    tr = bridge.build_safe_event_track(auth)
    led = event_ledger.build_ledger(discovery(contact_ms=1300), tr, 2.0)
    assert led["candidates_verified"] == 1


def test_B0E05_migration_gate_falls_back_when_unified_geometry_is_too_sparse():
    fallback = {"points": [{"t": i / 10, **BOX} for i in range(12)]}
    bundle = bridge.build_identity_bundle(
        fix04_track=None,
        identity_timeline=timeline([tl_point(i * 200) for i in range(5)]),
        anchors=[],
    )
    tr, source = bridge.choose_event_track(bundle, fallback_fix04_track=fallback)
    assert source == "FIX04_FALLBACK"
    assert tr is fallback


def test_B0E06_bridge_does_not_mutate_unified_authority():
    bundle = bridge.build_identity_bundle(
        fix04_track=None,
        identity_timeline=timeline(dense_points(predicted_ms=1000)),
        anchors=[],
    )
    auth = bundle["authority"]
    original = [dict(p) for p in auth["target_points"]]
    bridge.build_safe_event_track(auth)
    assert auth["target_points"] == original


def test_B0E07_identity_context_is_structured_and_bounded():
    bundle = bridge.build_identity_bundle(
        fix04_track=None,
        identity_timeline=timeline(dense_points()),
        anchors=[],
        identity_profile={
            "same_player": True,
            "confidence": 0.94,
            "description": "structured reference description",
            "jersey_number": "10",
            "unused_large_field": [1] * 1000,
        },
    )
    ctx = bundle["identity_context"]
    assert ctx["global_target_id"] == "GLOBAL_TARGET"
    assert ctx["timebase"] == "canonical_media_ms"
    assert ctx["scene_count"] == 1
    assert "unused_large_field" not in (ctx.get("identity_profile") or {})
