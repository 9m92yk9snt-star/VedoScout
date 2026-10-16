"""Regression controls for the Orman200 failure patterns; no live providers."""
from copy import deepcopy
import base64
import hashlib
import json

import numpy as np
import pytest

import action_evidence_review as inspection
import dense_identity_continuity as identity
import fix10a_goal_direction as direction
import fix10a_vision_providers as vision
import fix10b_reconciliation as reconciliation
import full_video_event_recall as recall
import goal_review_scheduler as scheduler
import sequence_observation_context as context
import test_fix29_connected_sequences as fixtures
import test_fix13_action_inspections as jobs


def reference_observation():
    return {"selected_reference": {"source": "USER_SELECTED_SOURCE_PIXELS", "source_video_sha256": "video",
                                   "input_sha256": "crops"},
        "target_observations": [{"media_ms": ms, "local_track_id": "p", "confidence": "high",
                                 "features": ["hair", "boots"]} for ms in (0, 200)]}


def test_selected_appearance_works_without_a_number_and_is_shared_with_contacts():
    frames = [fixtures.frame(ms) for ms in range(0, 1001, 20)]
    raw = deepcopy(frames)
    identified = identity.apply_reference_matches(frames, reference_observation())
    touches = {"touches": [{"media_ms": 500, "player_track_id": "p", "status": "VERIFIED", "proof_eligible": True}]}
    result = identity.apply(identified, touches)
    assert result["frames"][-1]["global_target"]["proof_eligible"]
    assert result["touch_graph"]["touches"][0]["global_target_id"] == "GLOBAL_TARGET"
    assert identified[0]["global_target"]["appearance_evidence"]["number_required"] is False
    assert frames == raw


@pytest.mark.parametrize("failure", ["no_reference", "only_kit", "one_frame", "low_confidence", "cut", "fallback",
                                       "opponent", "competing_body", "ambiguous_track", "identity_conflict", "different_selected_body"])
def test_appearance_does_not_invent_identity_when_evidence_cannot_distinguish_the_player(failure):
    frames = [fixtures.frame(ms) for ms in range(0, 401, 20)]
    obs = reference_observation()
    if failure == "no_reference": obs.pop("selected_reference")
    elif failure == "only_kit":
        for row in obs["target_observations"]: row["features"] = ["kit_colour", "number"]
    elif failure == "one_frame": obs["target_observations"].pop()
    elif failure == "low_confidence":
        for row in obs["target_observations"]: row["confidence"] = "low"
    elif failure == "cut": frames[5]["cut_barrier"] = True
    elif failure == "fallback": frames[5]["used_fallback"] = True
    elif failure == "opponent":
        for f in frames: f["players"][0]["team"] = "opponent"
    elif failure == "competing_body":
        for f in frames: f["players"].append({**deepcopy(f["players"][0]), "local_track_id": "other"})
    elif failure == "ambiguous_track": frames[5]["players"][0]["association_state"] = "HYPOTHESES"
    elif failure == "identity_conflict": frames[5]["global_target"]["reason"] = "SOURCE_CONFLICT"
    elif failure == "different_selected_body": frames[5]["global_target"] = {
        "reason": "OK_EXACT", "proof_eligible": True, "local_track_id": "other"}
    result = identity.apply_reference_matches(frames, obs)
    assert not any(f["global_target"].get("reason") == "MULTI_FRAME_SELECTED_APPEARANCE" for f in result)


def test_a_coarse_cut_gap_cannot_veto_an_uninterrupted_native_body_but_actual_cuts_stop_it():
    rows = fixtures.series()
    for f in rows[1:]: f["global_target"]["reason"] = "SCENE_CUT"
    result = identity.apply(rows)
    assert result["frames"][-1]["global_target"]["proof_eligible"]
    rows[50]["cut_barrier"] = True
    assert not identity.apply(rows)["frames"][-1]["global_target"]["proof_eligible"]
    rows[50].pop("cut_barrier")
    rows[25]["players"][0].pop("jersey_crop_quality")
    assert not identity.apply(rows)["frames"][-1]["global_target"]["proof_eligible"]


@pytest.mark.parametrize("reason", ["target_absent", "reid_failed", "ambiguous_duel", "SOURCE_CONFLICT", None])
def test_fresh_native_evidence_can_resolve_a_coarse_unknown_while_source_conflicts_stay_visible(reason):
    rows = [fixtures.frame(ms) for ms in range(0, 401, 20)]
    for f in rows:
        f["global_target"].update(reason="UNRESOLVED_IDENTITY", identity_barrier_reasons=[reason] if reason else [])
    identified = identity.apply_reference_matches(rows, reference_observation())
    output = identity.apply(identified)["frames"]
    assert output[0]["global_target"].get("proof_eligible") is (reason in {"target_absent", "reid_failed", "ambiguous_duel"})


async def test_same_pixel_call_gets_selected_crops_and_returns_only_supplied_body_matches(monkeypatch, tmp_path):
    sent = []
    class Chat:
        def __init__(self, **_kwargs): pass
        def with_model(self, *_args): return self
        def with_params(self, **_kwargs): return self
        async def send_message(self, msg):
            sent.append(msg)
            return json.dumps({"frames": [{"idx": 1, "balls": [], "selected_body_ids": []}],
                "target_observations": [{"idx": 1, "body_id": "body_1", "confidence": "high", "features": ["hair", "boots"]},
                                        {"idx": 1, "body_id": "invented", "confidence": "high"}, {"idx": 2, "body_id": "body_1"}]})
    path = tmp_path / "source.jpg"; path.write_bytes(b"timeline pixels")
    monkeypatch.setattr(vision, "LlmChat", Chat)
    result = await vision.read_action_pixel_evidence("fake", "session", [str(path)], [1000],
        body_candidates=[{"media_ms": 1000, "bodies": [{"body_id": "body_1"}]}],
        selected_reference={"images": [base64.b64encode(b"selected source crop").decode()]})
    assert len(sent) == 1 and len(sent[0].file_contents) == 2
    assert "shirt number is hidden" in sent[0].text
    assert "Do not infer identity" not in sent[0].text
    assert len(result["target_observations"]) == 1
    assert result["target_observations"][0]["media_ms"] == 1000
    assert len(result["input_sha256"]) == 64


def test_reference_crops_are_source_bound_and_cleared_when_video_changes(monkeypatch, tmp_path):
    path = tmp_path / "video.mp4"; path.write_bytes(b"canonical video bytes")
    monkeypatch.setattr(vision, "_read_frames", lambda _p, times: {
        ms: (ms, np.full((200, 100, 3), 120, np.uint8)) for ms in times})
    authority = {"target_points": [{"media_ms": ms, "box": {"x": .1, "y": .1, "w": .3, "h": .5},
        "tap_authority": True, "proof_eligible": True, "primary_source": "USER_TAP"} for ms in range(8)]}
    bundle = vision.ShadowVisionProviders("", "test").bind_video_path(str(path)).bind_selected_reference(authority)
    assert bundle._selected_reference["source_video_sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert len(bundle._selected_reference["images"]) == 3
    bundle.bind_video_path(str(tmp_path / "other.mp4"))
    assert bundle._selected_reference is None


def test_shifted_recall_and_semantic_splits_become_one_bounded_cover_without_losing_scenes():
    def w(a, b, scene="scene"):
        return {"start_ms": a, "end_ms": b, "scene_id": scene, "source_action_ids": [str(a)]}
    original = [w(0, 8000), w(6200, 14200), w(8001, 16001), w(12400, 19200), w(19466, 25466, "next")]
    output = recall.union_dense_windows(original, [])
    assert len(output) == 4
    assert all(row["end_ms"]-row["start_ms"] <= 8000 for row in output)
    assert {ms for row in original for ms in range(row["start_ms"], row["end_ms"]+1)} == {
        ms for row in output for ms in range(row["start_ms"], row["end_ms"]+1)}
    assert output[-1]["start_ms"] == 19466 and output[-1]["scene_id"] == "next"


def test_shared_inspection_keeps_each_original_contact_inside_the_same_image_budget():
    window = {"start_ms": 0, "end_ms": 4000, "scene_id": "scene", "dense_window_id": "w"}
    analysis = {"sequences": [{"scene_id": "scene", "actions": [{"action_id": str(ms), "start_ms": ms-100,
        "end_ms": ms+100, "contact_ms": ms} for ms in (600, 1800, 3000)]}]}
    plan = inspection.build_plan([window], analysis)
    assert len(plan["jobs"]) == 1 and len(plan["jobs"][0]["source_action_ids"]) == 3
    times = inspection.frame_times(plan["jobs"][0], fixtures.series())
    assert {600, 1800, 3000} <= set(times) and len(times) == 12


def test_a_rough_model_search_box_can_be_refined_to_one_smaller_native_ball(monkeypatch):
    native = {"box": {"x": .24, "y": .49, "w": .008, "h": .004}, "confidence": .8}
    search = {"x": .20, "y": .47, "w": .10, "h": .06}
    monkeypatch.setattr(vision, "_native_ball_roi", lambda *_: ([native], search))
    balls = vision.corroborate_ball_pixels(object(), np.zeros((10, 10, 3), np.uint8), search)
    assert len(balls) == 1 and balls[0]["box"] == native["box"]
    # The search rectangle's size never becomes the measured ball's size.
    assert balls[0]["proposal_corroboration"] == "UNIQUE_NATIVE_BALL_INSIDE_SEARCH_REGION"
    result = inspection.apply_observations([jobs.frame()], jobs.observed(balls[0]), "inspection")
    assert result["added_ball_candidates"] == 1
    assert result["frames"][0]["ball_candidates"][0]["box"] == native["box"]


@pytest.mark.parametrize("failure", ["competing", "outside", "no_detection"])
def test_rough_search_boxes_cannot_authorize_an_ambiguous_or_missing_ball(monkeypatch, failure):
    native = {"box": {"x": .24, "y": .49, "w": .008, "h": .004}, "confidence": .8}
    search = {"x": .20, "y": .47, "w": .10, "h": .06}
    balls = [native]
    if failure == "competing": balls += [{**native, "box": {**native["box"], "x": .28}}]
    elif failure == "outside": balls[0]["box"]["x"] = .70
    else: balls = []
    monkeypatch.setattr(vision, "_native_ball_roi", lambda *_: (balls, search))
    assert not vision.corroborate_ball_pixels(object(), np.zeros((10, 10, 3), np.uint8), search)


def test_useless_geometry_work_does_not_consume_the_budget_for_a_valid_contact():
    seen = []
    provider = direction.GoalDirectionProvider(lambda w, s: seen.append(s["media_ms"]) or {}, "", "test", "unused", max_reviews=1)
    dead = jobs.review_job(1000); dead["strike"]["active_ball_anchor"]["proof_eligible"] = False
    result = provider(dead["window"], dead["strike"])
    assert result["review_delivery"]["status"] == "SKIPPED" and not seen
    good = jobs.review_job(3000)
    provider(good["window"], good["strike"])
    assert seen == [3000]


def test_unused_known_identity_capacity_can_inspect_unknown_actors_without_extra_calls(monkeypatch):
    monkeypatch.setattr(direction, "MAX_GOAL_REVIEWS_PER_REPORT", 2)
    monkeypatch.setattr(direction, "MAX_GOAL_CLARIFICATIONS_PER_REPORT", 3)
    seen = []
    provider = direction.GoalDirectionProvider(lambda w, s: seen.append(s["media_ms"]) or {}, "", "test", "unused")
    for ms in range(1000, 7000, 1000):
        job = jobs.review_job(ms)
        job["strike"]["_review_lane"] = "CLARIFICATION"
        provider(job["window"], job["strike"])
    assert len(seen) == 5 and provider.calls == 0 and provider.clarification_calls == 5


def role_case():
    # Source pattern: canonical SHOT at 57200; target visible left, native
    # contact and independent SHOT_MOTION belong to a different body at 57364.
    f = fixtures.frame(57364, seed=True, track="target", scene="scene")
    f["players"].append({**deepcopy(f["players"][0]), "local_track_id": "finisher",
                         "box": {"x": .70, "y": .46, "w": .08, "h": .10}})
    event = {"event_id": "e", "scene_id": "scene", "canonical_ms": 57200, "canonical_event_type": "SHOT",
             "canonical_action_type": "SHOT", "canonical_outcome": "OFF_TARGET", "causal_verified": True}
    trace = {"trace_id": "w", "window": {"scene_id": "scene", "start_ms": 53000, "end_ms": 58931},
        "decoded_frames": [f], "strike_evidence": [{"media_ms": 57381, "scene_id": "scene", "player_track_id": "finisher",
            "strike_id": "s", "proof_eligible": True, "status": "VERIFIED_PHYSICAL_SCORING_CONTACT"}],
        "action_inspections": [{"sequence_reasoning": {"hypotheses": [{"steps": [
            {"media_ms": 57364, "body_id": "body_1", "observation": "SHOT_MOTION"}]}]}}]}
    return event, trace


def test_later_native_actor_conflict_reopens_a_false_miss_without_creating_an_assist():
    event, trace = role_case()
    result = reconciliation.reconcile_canonical_events({"events": [event]}, {"status": "ok", "traces": [trace]})
    assert not result["events"] and result["status"] == "unresolved"
    assert result["unresolved"][0]["original_event"]["canonical_outcome"] == "OFF_TARGET"
    assert result["reconciliation"]["shot_role_conflicts_reopened"] == 1
    assert event["canonical_outcome"] == "OFF_TARGET"  # original audit input remains untouched
    import fix10b_runtime
    summary = fix10b_runtime._summary(result)
    assert summary["status"] == "applied" and summary["shot_role_conflicts_reopened"] == 1


@pytest.mark.parametrize("failure", ["same_actor", "no_native_contact", "no_identity", "cut", "invented_body", "proven_outcome", "target_shot_then_rebound"])
def test_model_hypotheses_cannot_revoke_a_proved_event_or_invent_an_actor_conflict(failure):
    event, trace = role_case()
    if failure == "same_actor": trace["decoded_frames"][0]["global_target"]["local_track_id"] = "finisher"
    elif failure == "no_native_contact": trace["strike_evidence"] = []
    elif failure == "no_identity": trace["decoded_frames"][0]["global_target"]["proof_eligible"] = False
    elif failure == "cut": trace["decoded_frames"][0]["cut_barrier"] = True
    elif failure == "invented_body": trace["action_inspections"][0]["sequence_reasoning"]["hypotheses"][0]["steps"][0]["body_id"] = "invented"
    elif failure == "proven_outcome": event["reconciliation_authority"] = "FIX10B_PHYSICAL_RECONCILIATION"
    elif failure == "target_shot_then_rebound": trace["strike_evidence"].append({
        "media_ms": 57100, "scene_id": "scene", "player_track_id": "target", "global_target_id": "GLOBAL_TARGET",
        "proof_eligible": True, "status": "VERIFIED_PHYSICAL_RELEASE"})
    assert not reconciliation._shot_role_conflicts([event], {"traces": [trace]})
