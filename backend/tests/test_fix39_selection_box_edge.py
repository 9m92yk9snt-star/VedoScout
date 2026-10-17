"""Measured report-300 selection geometry; no model replies or event labels.

These coordinates reproduce the exported tap/body conflict at one actual PTS.
Passing these controls does not verify a shot, goal, assist or full-video time.
"""
from copy import deepcopy

import pytest

import dense_track_refinement as dense
import football_scene_graph as graph
import player_selection as selection
import unified_identity_authority as uia


SELECTED = {"x": .5639, "y": .4078, "w": .0963, "h": .1177}
POINT = {"x": .5741510003480544, "y": .4641176317242876}
BODIES = [
    {"local_track_id": "outside_point_hit", "association_state": "HYPOTHESES",
     "candidate_local_track_ids": ["outside_point_hit"], "confidence": .37954097986221313,
     "box": {"x": .5195458984375, "y": .409375, "w": .061123046875, "h": .0953125}},
    {"local_track_id": "enclosed_body", "association_state": "VERIFIED_LOCAL",
     "confidence": .4136628806591034,
     "box": {"x": .58900390625, "y": .4234375, "w": .0583447265625, "h": .0796875}},
    {"local_track_id": "second_neighbour", "association_state": "VERIFIED_LOCAL",
     "confidence": .4669508635997772,
     "box": {"x": .6362353515625, "y": .4234375, "w": .05556640625, "h": .0609375}},
]


def rectangles(bodies=BODIES):
    return [tuple(b["box"][k] for k in ("x", "y", "w", "h")) for b in bodies]


@pytest.mark.parametrize("scale", [1., 480., 1920.])
def test_measured_point_hit_outside_selection_binds_enclosed_adjacent_body(scale):
    boxes = [tuple(v * scale for v in b) for b in rectangles()]
    point = tuple(POINT[k] * scale for k in ("x", "y"))
    box = tuple(SELECTED[k] * scale for k in ("x", "y", "w", "h"))
    before = deepcopy(boxes)
    assert selection.body_indices_at_point(boxes, point) == [0]
    assert selection.body_indices_at_point(boxes, point, selection_box=box) == [1]
    assert boxes == before


@pytest.mark.parametrize("consumer,ms", [(dense._resolve_dense_target, 21482), (graph._target_candidates, 21480)])
def test_both_production_consumers_recover_same_measured_body(consumer, ms):
    anchor = {"t": 21.48, "box": deepcopy(SELECTED), "target_point": deepcopy(POINT)}
    authority = uia.build_unified_identity_authority(anchors=[anchor])
    players = deepcopy(BODIES)
    before = deepcopy((authority, players))
    result = consumer(authority, ms, players)
    assert result["proof_eligible"] is True
    assert result["local_track_id"] == "enclosed_body"
    assert (authority, players) == before


def test_conflicting_edge_without_measured_replacement_does_not_promote_bystander():
    assert selection.body_indices_at_point(rectangles(BODIES[:1]), tuple(POINT.values()),
                                           selection_box=SELECTED) == []


def test_multiple_enclosed_bodies_remain_ambiguous_instead_of_using_confidence():
    bodies = deepcopy(BODIES[:2])
    bodies.append({**deepcopy(bodies[1]), "local_track_id": "another", "confidence": .999})
    assert selection.body_indices_at_point(rectangles(bodies), tuple(POINT.values()),
                                           selection_box=SELECTED) == [1, 2]


def test_exclusion_and_visible_mask_cannot_be_overridden_by_box_repair():
    point = tuple(POINT.values())
    owner = BODIES[1]["box"]
    negative = (owner["x"] + owner["w"] / 2, owner["y"] + owner["h"] / 2)
    assert selection.body_indices_at_point(rectangles(), point, [negative], selection_box=SELECTED) == []
    invalid_mask = {"width": 96, "height": 192, "runs": [18432]}
    assert selection.body_indices_at_point(rectangles(), point, selection_box=SELECTED,
                                           visible_mask=invalid_mask) == []


@pytest.mark.parametrize("change", ["point_in_background", "point_centre", "far_replacement", "tiny_replacement"])
def test_repair_never_becomes_generic_nearest_body_selection(change):
    bodies, point, selected = deepcopy(BODIES), dict(POINT), dict(SELECTED)
    if change == "point_in_background":
        point["y"] = .52
    elif change == "point_centre":
        selected.update(x=.53, w=.13)
    elif change == "far_replacement":
        bodies[1]["box"]["x"] = .625
    else:
        bodies[1]["box"].update(w=.01, h=.01)
    result = selection.body_indices_at_point(rectangles(bodies), tuple(point.values()), selection_box=selected)
    assert 1 not in result


def test_clear_off_centre_point_still_beats_broad_crop_centre():
    boxes = [(.20, .30, .12, .50), (.50, .30, .17, .50)]
    selected = (.15, .30, .60, .50)
    assert selection.body_indices_at_point(boxes, (.23, .43), selection_box=selected) == [0]


def test_same_geometry_has_same_answer_after_source_clock_change():
    for ms in (1000, 37000):
        authority = uia.build_unified_identity_authority(anchors=[
            {"t": ms / 1000, "box": SELECTED, "target_point": POINT}])
        result = dense._resolve_dense_target(authority, ms, deepcopy(BODIES))
        assert result["local_track_id"] == "enclosed_body"
        assert result["selection_binding"] == "USER_SELECTED_BOX_EDGE_RECONCILIATION"


def reference_trace(same_player):
    # Explicit model-reply test double, distinct from the measured geometry above.
    from test_fix31_temporal_video import motion_trace
    trace = motion_trace("SHOT", "GOAL")
    obs = trace["action_inspections"][0]
    obs["selected_reference"] = {"source": "USER_SELECTED_SOURCE_PIXELS",
        "source_video_sha256": "source", "input_sha256": "reference-input"}
    obs["video_input"]["reference_sha256"] = ["actual-adapter-reference"]
    obs["video_actions"][0]["selected_reference_match"] = {
        "same_player": same_player, "confidence": "high", "evidence_indices": [1, 3],
        "continuous_visible_actor": True, "features": ["kit", "hair"]}
    return trace


def test_same_video_negative_reference_comparison_overrides_wrong_native_target():
    import dense_event_reconciliation as reconciliation
    result = reconciliation.resolve_motion_observations(reference_trace(False))
    assert not result["events"]
    rejected, = result["rejected"]
    assert rejected["reason"] == "SOURCE_VIDEO_OTHER_PLAYER"


def test_positive_same_video_comparison_can_identify_actor_without_second_native_approval():
    import dense_event_reconciliation as reconciliation
    trace = reference_trace(True)
    for f in trace["decoded_frames"]:
        f["global_target"] = {"status": "UNRESOLVED", "proof_eligible": False}
    result = reconciliation.resolve_motion_observations(trace)
    event, = result["events"]
    assert event["identity_resolution"] == "SOURCE_VIDEO_SELECTED_PLAYER"
    assert event["canonical_event_type"] == "GOAL"


@pytest.mark.parametrize("missing", ["source", "reference", "actor_evidence", "boolean"])
def test_unbound_comparison_cannot_claim_reference_authority(missing):
    import sequence_observation_context as context
    trace = reference_trace(False)
    obs = trace["action_inspections"][0]
    if missing == "source": obs["selected_reference"]["source_video_sha256"] = "other-source"
    elif missing == "reference": obs["video_input"]["reference_sha256"] = []
    elif missing == "actor_evidence": obs["video_actions"][0]["selected_reference_match"]["evidence_indices"] = [24]
    else: obs["video_actions"][0]["selected_reference_match"]["same_player"] = "false"
    packet = context.video_observations(obs, trace["decoded_frames"], trace["window"])
    action, = packet["sequences"][0]["actions"]
    assert "selected_reference_match" not in action["video_observation"]


@pytest.mark.parametrize("contradiction", [{"same_player": False}, {"kit_consistent": False}])
def test_negative_target_observation_cannot_bootstrap_identity(contradiction):
    import fix10a_vision_providers as vision
    parsed = {"target_observations": [{"idx": 1, "body_id": "body_1", "confidence": "high",
                                      "features": ["hair", "boots"], **contradiction}]}
    manifest = [{"media_ms": 1000, "bodies": [{"body_id": "body_1"}]}]
    assert vision._target_observations(parsed, [1000], manifest) == []


@pytest.mark.parametrize("contradiction", [{"same_player": False}, {"kit_consistent": False}])
def test_identity_consumer_preserves_negative_comparison_even_for_direct_motion(contradiction):
    import dense_identity_continuity as identity
    trace = reference_trace(False)
    for f in trace["decoded_frames"]:
        f["global_target"] = {"status": "UNRESOLVED", "proof_eligible": False}
    obs = trace["action_inspections"][0]
    obs["target_observations"] = [{"media_ms": 900, "local_track_id": "p002",
        "confidence": "high", "features": ["hair", "boots"], **contradiction}]
    before = deepcopy(trace["decoded_frames"])
    assert identity.apply_reference_matches(trace["decoded_frames"], obs) == before
