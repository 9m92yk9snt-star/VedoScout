"""FIX09B.0 — deterministic unified GLOBAL_TARGET authority tests."""
import copy
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

import unified_identity_authority as uia  # noqa: E402


def f4(*rows):
    return {"points": [
        {"t": t, "x": x, "y": y, "w": w, "h": h, "conf": conf}
        for (t, x, y, w, h, conf) in rows
    ]}


def ap(ms, x, y, w=.10, h=.20, state="VISIBLE", predicted=False, proof=True, scene="scene_001"):
    return {"media_ms": ms, "scene_id": scene, "local_track_id": "p01",
            "box": {"x": x, "y": y, "w": w, "h": h}, "state": state,
            "predicted": predicted, "proof_eligible": proof,
            "identity_score": .82, "geometry_source": "detection" if not predicted else "predicted"}


def tl(*points, scenes=None, unresolved=None):
    return {"status": "ok", "global_target_id": "GLOBAL_TARGET",
            "scenes": scenes or [{"scene_id": "scene_001", "start_ms": 0, "end_ms": 10000}],
            "target_points": list(points), "unresolved_intervals": unresolved or []}


def test_b01_fix09a_global_only_becomes_canonical_authority():
    a = uia.build_unified_identity_authority(None, tl(ap(1000, .2, .3)))
    assert a["status"] == "ok"
    assert a["global_target_id"] == "GLOBAL_TARGET"
    p = a["target_points"][0]
    assert p["identity_strength"] == "GLOBAL"
    assert p["sources"] == ["FIX09A"]
    assert p["proof_eligible"] is True


def test_b02_fix04_local_only_is_kept_without_claiming_global_reid():
    a = uia.build_unified_identity_authority(f4((1.0, .2, .3, .1, .2, .8)), None)
    p = a["target_points"][0]
    assert p["identity_strength"] == "LOCAL"
    assert p["primary_source"] == "FIX04"
    assert p["global_target_id"] == "GLOBAL_TARGET"


def test_b03_source_agreement_fuses_identity_evidence():
    a = uia.build_unified_identity_authority(
        f4((1.0, .20, .30, .10, .20, .8)), tl(ap(1000, .205, .30)))
    assert a["metrics"]["fused_points"] >= 1
    assert all(p["state"] != "UNRESOLVED" for p in a["target_points"])
    assert any(set(p["sources"]) == {"FIX04", "FIX09A"} for p in a["target_points"])


def test_b04_real_source_conflict_outside_tap_is_not_guessed():
    a = uia.build_unified_identity_authority(
        f4((5.0, .10, .20, .10, .20, .9)), tl(ap(5000, .75, .20)))
    assert a["metrics"]["conflict_points"] >= 1
    conflicts = [p for p in a["target_points"] if p["state"] == "UNRESOLVED"]
    assert conflicts and all(p["box"] is None and not p["proof_eligible"] for p in conflicts)
    assert {h["source"] for h in conflicts[0]["hypotheses"]} == {"FIX04", "FIX09A"}


def test_b05_user_tap_is_absolute_authority_during_source_conflict():
    a = uia.build_unified_identity_authority(
        f4((5.0, .10, .20, .10, .20, .9)), tl(ap(5000, .75, .20)),
        anchors=[{"t": 5.0, "box": {"x": .1, "y": .2, "w": .1, "h": .2}}])
    pins = [p for p in a["target_points"] if p["tap_authority"]]
    assert pins
    assert all(p["primary_source"] == "USER_TAP" for p in pins)
    assert all(p["state"] == "PINNED" and p["proof_eligible"] for p in pins)
    assert pins[0]["box"]["x"] == .1


def test_b06_predicted_occlusion_is_never_proof_eligible():
    a = uia.build_unified_identity_authority(
        None, tl(ap(1200, .2, .3, state="OCCLUDED", predicted=True, proof=False)))
    p = a["target_points"][0]
    assert p["state"] == "OCCLUDED"
    assert p["identity_strength"] == "PREDICTED"
    assert p["predicted"] is True
    assert p["proof_eligible"] is False


def test_b07_production_adapter_excludes_conflict_and_predicted_geometry():
    a = uia.build_unified_identity_authority(
        f4((1.0, .2, .3, .1, .2, .8), (5.0, .1, .2, .1, .2, .9)),
        tl(ap(1000, .205, .30), ap(3000, .3, .3, predicted=True, proof=False), ap(5000, .75, .2)))
    tr = uia.to_production_track(a)
    assert tr["authority"] == "UNIFIED_IDENTITY"
    assert tr["global_target_id"] == "GLOBAL_TARGET"
    assert all(abs(p["t"] - 3.0) > .001 for p in tr["points"])
    assert all(abs(p["t"] - 5.0) > .001 for p in tr["points"])
    assert any(abs(p["t"] - 1.0) < .001 for p in tr["points"])


def test_b08_resolve_exact_point():
    a = uia.build_unified_identity_authority(None, tl(ap(1000, .2, .3)))
    p, why = uia.resolve_target_at(a, 1000, proof_required=True)
    assert why == "OK_EXACT"
    assert p["box"]["x"] == .2


def test_b09_resolve_bounded_same_scene_interpolation():
    a = uia.build_unified_identity_authority(None, tl(ap(1000, .2, .3), ap(1200, .3, .3)))
    p, why = uia.resolve_target_at(a, 1100, proof_required=True)
    assert why == "OK_INTERPOLATED"
    assert abs(p["box"]["x"] - .25) < 1e-9
    assert p["proof_eligible"] is False


def test_b10_never_interpolate_across_scene_cut():
    scenes = [{"scene_id": "scene_001", "start_ms": 0, "end_ms": 1050},
              {"scene_id": "scene_002", "start_ms": 1051, "end_ms": 3000}]
    a = uia.build_unified_identity_authority(
        None, tl(ap(1000, .2, .3, scene="scene_001"), ap(1200, .7, .3, scene="scene_002"), scenes=scenes))
    p, why = uia.resolve_target_at(a, 1100)
    assert p is None and why == "SCENE_CUT"


def test_b11_never_interpolate_through_unresolved_interval():
    a = uia.build_unified_identity_authority(
        None, tl(ap(1000, .2, .3), ap(1400, .3, .3),
                 unresolved=[{"scene_id": "scene_001", "start_ms": 1100, "end_ms": 1300,
                              "reason": "ambiguous_duel"}]))
    p, why = uia.resolve_target_at(a, 1200)
    assert p is None and why == "UNRESOLVED_IDENTITY"


def test_b12_build_does_not_mutate_existing_fix_outputs():
    old = f4((1.0, .2, .3, .1, .2, .8))
    new = tl(ap(1000, .2, .3))
    old0, new0 = copy.deepcopy(old), copy.deepcopy(new)
    uia.build_unified_identity_authority(old, new, anchors=[{"t": 1.0}])
    assert old == old0
    assert new == new0


def test_b13_anchor_time_offset_uses_canonical_media_time():
    a = uia.build_unified_identity_authority(
        f4((1.5, .1, .2, .1, .2, .9)), tl(ap(1500, .8, .2)),
        anchors=[{"t": 1.0}], anchor_time_offset=.5)
    assert 1500 in a["tap_times_ms"]
    assert any(p["tap_authority"] for p in a["target_points"])


def test_b14_invalid_sources_fail_safe_to_empty():
    a = uia.build_unified_identity_authority({"points": [{"t": "bad"}]}, {"target_points": [{}]})
    assert a["status"] == "empty"
    assert a["target_points"] == []


def test_b15_production_adapter_emits_same_scene_contiguous_segments():
    a = uia.build_unified_identity_authority(
        None,
        tl(
            ap(0, .20, .30), ap(200, .21, .30), ap(400, .22, .30),
            ap(1000, .30, .30, scene="scene_002"),
            ap(1200, .31, .30, scene="scene_002"),
            ap(1400, .32, .30, scene="scene_002"),
            scenes=[
                {"scene_id": "scene_001", "start_ms": 0, "end_ms": 500},
                {"scene_id": "scene_002", "start_ms": 900, "end_ms": 1500},
            ],
        ),
    )
    tr = uia.to_production_track(a)
    assert tr["segments"] == [[0.0, 0.4], [1.0, 1.4]]


def test_b16_exact_point_inside_unresolved_interval_is_not_identity_proof():
    a = uia.build_unified_identity_authority(
        None,
        tl(ap(1000, .2, .3), unresolved=[{
            "scene_id": "scene_001", "start_ms": 950, "end_ms": 1050,
            "reason": "REID_UNRESOLVED",
        }]),
    )
    p, why = uia.resolve_target_at(a, 1000, proof_required=True)
    assert p is None and why == "UNRESOLVED_IDENTITY"


def test_b17_interpolation_cannot_cross_barrier_before_requested_instant():
    a = uia.build_unified_identity_authority(
        None,
        tl(ap(900, .2, .3), ap(1100, .3, .3), unresolved=[{
            "scene_id": "scene_001", "start_ms": 950, "end_ms": 980,
            "reason": "REID_UNRESOLVED",
        }]),
    )
    p, why = uia.resolve_target_at(a, 1000, proof_required=False)
    assert p is None and why == "UNRESOLVED_IDENTITY"


def test_b18_production_adapter_excludes_exact_point_inside_identity_barrier():
    a = uia.build_unified_identity_authority(
        None,
        tl(ap(1000, .2, .3), unresolved=[{
            "scene_id": "scene_001", "start_ms": 950, "end_ms": 1050,
            "reason": "REID_UNRESOLVED",
        }]),
    )
    tr = uia.to_production_track(a)
    assert tr["points"] == []
    assert tr["segments"] == []


def test_b19_production_segments_never_bridge_identity_barrier():
    a = uia.build_unified_identity_authority(
        None,
        tl(
            *(ap(ms, .2 + ms / 10000.0, .3)
              for ms in (0, 200, 400, 600, 800, 1000)),
            unresolved=[{
                "scene_id": "scene_001", "start_ms": 450, "end_ms": 550,
                "reason": "REID_UNRESOLVED",
            }],
        ),
    )
    tr = uia.to_production_track(a)
    assert [p["t"] for p in tr["points"]] == [0.0, .2, .4, .6, .8, 1.0]
    assert tr["segments"] == [[0.0, .4], [.6, 1.0]]


def test_b20_direct_tap_survives_barrier_without_creating_false_continuity():
    a = uia.build_unified_identity_authority(
        f4((1.0, .2, .3, .1, .2, .9)),
        tl(ap(1000, .2, .3), unresolved=[{
            "scene_id": "scene_001", "start_ms": 950, "end_ms": 1050,
            "reason": "REID_UNRESOLVED",
        }]),
        anchors=[{"t": 1.0}],
    )
    tr = uia.to_production_track(a)
    assert [p["t"] for p in tr["points"]] == [1.0]
    assert tr["points"][0]["authority_source"] == "PINNED"
    assert tr["segments"] == []


def test_b21_selected_box_overrides_wrong_tracker_exactly_inside_barrier():
    selected = {"x": .4, "y": .3, "w": .1, "h": .2}
    a = uia.build_unified_identity_authority(
        f4((1.0, .1, .3, .1, .2, .9), (1.2, .1, .3, .1, .2, .9)),
        tl(ap(1000, .1, .3), ap(1200, .1, .3), unresolved=[{
            "scene_id": "scene_001", "start_ms": 950, "end_ms": 1250,
            "reason": "REID_UNRESOLVED",
        }]), anchors=[{"t": 1.0, "box": selected}])
    exact, why = uia.resolve_target_at(a, 1000, proof_required=True)
    assert why == "OK_EXACT" and exact["box"] == selected
    assert exact["primary_source"] == "USER_TAP"
    assert uia.resolve_target_at(a, 1200, proof_required=True) == (None, "UNRESOLVED_IDENTITY")
    assert [p["t"] for p in uia.to_production_track(a)["points"]] == [1.0]


def test_b22_selected_box_respects_time_offset_and_does_not_prove_neighbor():
    selected = {"x": .4, "y": .3, "w": .1, "h": .2}
    a = uia.build_unified_identity_authority(
        None, tl(unresolved=[{"scene_id": "scene_001", "start_ms": 1450,
                             "end_ms": 1550, "reason": "REID_UNRESOLVED"}]),
        anchors=[{"t": 1.0, "box": selected}], anchor_time_offset=.5)
    assert uia.resolve_target_at(a, 1500, proof_required=True)[0]["box"] == selected
    assert uia.resolve_target_at(a, 1516, proof_required=True)[0] is None


def test_b23_selected_box_does_not_pin_different_body_near_tap():
    a = uia.build_unified_identity_authority(
        f4((1.2, .1, .3, .1, .2, .9)), tl(ap(1200, .1, .3)),
        anchors=[{"t": 1.0, "box": {"x": .4, "y": .3, "w": .1, "h": .2}}])
    near, why = uia.resolve_target_at(a, 1200, proof_required=True)
    assert why == "OK_EXACT" and near["tap_authority"] is False
