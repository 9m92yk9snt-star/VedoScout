from copy import deepcopy
import numpy as np
import pytest

import evidence_feedback as feedback
import action_evidence_review as inspection
import physical_match_reconstruction as physical
import fix10a_vision_providers as vision
import test_fix10a_physical_reconstruction as fixture
import test_fix13_action_inspections as pixels


def trace(center=1000, name="w", scene="scene"):
    frames = [{**pixels.frame(ms), "scene_id": scene} for ms in range(center - 500, center + 2001, 50)]
    return {"trace_id": name, "window": {"dense_window_id": name, "scene_id": scene,
            "start_ms": center - 500, "end_ms": center + 2000}, "decoded_frames": frames,
            "contacts": {"accepted": [], "unresolved": [{"media_ms": center}]},
            "touch_graph": {"touches": []}, "strike_evidence": [], "outcome_evidence": [],
            "jersey_consensus": {}, "action_inspections": [{"status": "COMPLETED", "selected": True,
                "center_ms": center, "requested_media_ms": [center - 500, center + 2000]}]}


def test_feedback_is_bounded_and_reaches_late_video_without_expected_event_labels():
    traces = [trace(t, str(t), "scene_" + str(t)) for t in range(1000, 62000, 5000)]
    plan = feedback.build_plan(traces, budget=4)
    chosen = [j for j in plan["jobs"] if j["selected"]]
    assert plan["selected"] == 4 and plan["deferred"] == len(traces) - 4
    assert max(j["center_ms"] for j in chosen) == 61000
    assert min(j["center_ms"] for j in chosen) == 1000
    assert all(j["phase"] == "FEEDBACK" and j["end_ms"] - j["start_ms"] <= 1050 for j in chosen)
    assert all(not ({"goal", "assist", "expected_jersey_number", "kind"} & set(j)) for j in chosen)
    assert not feedback.build_plan(traces, budget=0)["selected"]


@pytest.mark.parametrize("barrier", ["cut_barrier", "used_fallback", "time_authority", "scene_id"])
def test_feedback_stops_at_frame_barriers(barrier):
    source = trace()
    row = next(f for f in source["decoded_frames"] if f["media_ms"] == 1150)
    row[barrier] = "REQUESTED_TIME" if barrier == "time_authority" else "other" if barrier == "scene_id" else True
    chosen = feedback.build_plan([source])["jobs"][0]
    assert chosen["end_ms"] == 1100
    bad = next(f for f in source["decoded_frames"] if f["media_ms"] == 1000)
    bad[barrier] = row[barrier]
    assert not feedback.build_plan([source])["jobs"]


def test_same_pixels_and_feedback_results_cannot_open_another_review():
    source = trace()
    job = feedback.build_plan([source])["jobs"][0]
    source["action_inspections"][0]["requested_media_ms"] = inspection.frame_times(job, source["decoded_frames"])
    plan = feedback.build_plan([source])
    assert not plan["jobs"] and plan["rejected"][0]["reason"] == "NO_NEW_REVIEW_INPUT"
    source["evidence_feedback"] = {"round": 1}
    assert not feedback.build_plan([source])["jobs"]


def test_verified_identity_with_a_missing_ball_path_still_gets_contact_feedback():
    source = trace()
    for f in source["decoded_frames"]:
        f["global_target"] = {"proof_eligible": True, "status": "VERIFIED", "local_track_id": "p1"}
    source["contacts"] = {"accepted": [{"media_ms": 1000}], "unresolved": []}
    source["touch_graph"] = {"touches": [{"media_ms": 1000, "global_target_id": "GLOBAL_TARGET", "contact_role": "RECEIVE_CONTROL"}]}
    source["action_inspections"] = []
    chosen = feedback.build_plan([source])["jobs"][0]
    assert chosen["reason"] == "TARGET_RELEASE_OR_BALL_GAP"
    assert chosen["before"]["identity_frames"] == 0 and chosen["before"]["target_ball_frames"] > 0


def test_unrelated_opponent_outcome_cannot_take_the_target_outcome_priority():
    source = trace()
    source["strike_evidence"] = [{"strike_id": "other", "global_target_id": None}]
    source["outcome_evidence"] = [{"strike_id": "other", "media_ms": 1500, "physical_outcome": "UNRESOLVED"}]
    chosen = feedback.build_plan([source])["jobs"][0]
    assert chosen["center_ms"] == 1000 and chosen["reason"] == "PHYSICAL_CONTACT_GAP"


def test_search_times_focus_unresolved_contacts_without_using_semantic_event_labels():
    source = trace()
    source["contacts"]["unresolved"] = [{"media_ms": 650}, {"media_ms": 1500}]
    source["action_inspections"] = []
    analysis = {"sequences": [{"scene_id": "scene", "actions": [pixels.action(1400, 1800, "OTHER", 1500)]}]}
    chosen = feedback.build_plan([source], analysis=analysis)["jobs"][0]
    assert chosen["center_ms"] == 1500
    analysis["sequences"][0]["actions"][0]["kind"] = "GOAL"
    assert feedback.build_plan([source], analysis=analysis)["jobs"][0] == chosen


@pytest.mark.parametrize("native", [True, False])
def test_new_pixels_reenter_contact_gates_once_without_retracking_or_model_event_promotion(monkeypatch, native):
    frames = [{**fixture._frame(ms), "scene_id": "scene_001"} for ms in range(900, 3301, 50)]
    fixture._patch_window(monkeypatch, frames=frames, contact=fixture._contact_result())
    window = {**fixture.WINDOW, "end_ms": 3300}
    monkeypatch.setattr(physical.dense_replay, "select_critical_windows", lambda *_: [deepcopy(window)])
    refinement_calls = []
    monkeypatch.setattr(physical.dense_track_refinement, "refine_window", lambda *_a, **_k:
                        refinement_calls.append(True) or {"frames": deepcopy(frames)})
    monkeypatch.setattr(physical.ball_contact_engine, "detect_contact_candidates",
        lambda rows, *_: [True] if any(f.get("ball_candidates") for f in rows) else [])
    monkeypatch.setattr(physical.ball_contact_engine, "resolve_contacts",
        lambda candidates: fixture._contact_result(accepted=[fixture._accepted_contact(ms=1100)] if candidates else []))
    monkeypatch.setattr(physical.shot_outcome_engine, "find_strike_releases", lambda *_: [])
    monkeypatch.setattr(physical.shot_outcome_engine, "find_scoring_control_contacts", lambda *_: [])
    calls, published = [], []
    def inspect(_video, job, _frames):
        calls.append(job.get("phase", "INITIAL"))
        if job.get("phase") != "FEEDBACK":
            return {"status": "COMPLETED", "frames": [], "requested_media_ms": inspection.frame_times(job, _frames)}
        ball = {"box": deepcopy(pixels.BALL), "proposal_box": deepcopy(pixels.BALL), "confidence": .95,
                "source": "NATIVE_REVIEW_ROI_DETECTOR", "pixel_corroborated": native}
        return {"status": "COMPLETED", "goal": True, "actor_number": "15", "frames": [
            {"media_ms": 1100, "scene_id": "scene_001", "ball_candidates": [ball]}]}
    plan, analysis, graph, authority = fixture._base_inputs()
    analysis["sequences"][0]["actions"] = [pixels.action(1100, 3000, "OTHER", 1100)]
    result = physical.reconstruct_physical_match("unused", plan, analysis, graph, authority,
                action_evidence_provider=inspect, trace_callback=lambda t: published.append(deepcopy(t)),
                source_video={"sha256": "source-hash"})
    assert calls == ["INITIAL", "FEEDBACK"] and len(refinement_calls) == 1
    final = result["traces"][0]
    assert final["source_video"]["sha256"] == "source-hash"
    assert final["evidence_feedback"]["before"]["verified_contacts"] == 0
    assert final["evidence_feedback"]["after"]["verified_contacts"] == int(native)
    assert final["first_pass_evidence"]["contacts"]["accepted"] == []
    assert len(final["action_inspections"]) == 2 and published[-1]["evidence_feedback"]["round"] == 1
    assert not final["strike_evidence"] and "canonical_events" not in result


def test_unavailable_or_failed_feedback_keeps_original_evidence(monkeypatch):
    original = trace()
    originals = deepcopy([original])
    untouched, _, audit = physical.run_feedback_round([original], "unused", {}, {}, {}, {})
    assert untouched == originals and not audit["configured"] and audit["executed_windows"] == 0
    monkeypatch.setattr(physical, "reconstruct_physical_match", lambda *_a, **_k:
        {"traces": [], "windows": [{"dense_window_id": "w", "status": "error", "error_stage": "action_pixels"}]})
    untouched, _, audit = physical.run_feedback_round([original], "unused", {}, {}, {}, {}, action_evidence_provider=lambda *_: {})
    assert untouched == originals and audit["failed_windows"][0]["error_stage"] == "action_pixels"


def test_recovered_pass_reopens_the_existing_receiver_review_in_another_window(monkeypatch):
    import test_fix13_cross_window_evidence as overlap
    left, right = overlap.cases()
    for tr in (left, right):
        tr.update(action_inspections=[], provider_diagnostics=[], provider_adapter_errors=[],
                  jersey_model_audits={}, jersey_consensus={}, unresolved_reasons=[])
    recovered = deepcopy(left)
    left["strike_evidence"] = []  # pass was absent before feedback
    left["contacts"] = {"accepted": [], "unresolved": [{"media_ms": 1000}]}
    right["outcome_evidence"][0].update(physical_outcome="UNRESOLVED", goal_plane_crossing={"status": "UNRESOLVED"})
    monkeypatch.setattr(physical, "reconstruct_physical_match", lambda *_a, **_k: {"traces": [deepcopy(recovered)],
        "windows": [{"dense_window_id": "left", "status": "ok"}]})
    scorer = right["strike_evidence"][0]
    job = {"window": right["window"], "strike": scorer, "review": {"lane": "CLARIFICATION"},
           "eligibility": {"eligible": False}, "touch_graph": right["touch_graph"],
           "shot_track": {"rows": right["ball_trajectory"], "source": "MEASURED", "seed_ms": 2600},
           "roles": {}, "intervention": {"status": "UNRESOLVED"}, "outcome_index": 0}
    seen = []
    out, _, audit = physical.run_feedback_round([left, right], "unused", {}, {}, {}, {},
        action_evidence_provider=lambda *_: {}, review_jobs=[job],
        goal_geometry_provider=lambda _w, s: seen.append(s) or None)
    assert audit["downstream_reviews_unlocked"] == 1 and len(seen) == 1
    assert seen[0]["_review_lane"] == "VERIFIED_CHAIN"
    receiver = next(t for t in out if t["trace_id"] == "right")
    assert receiver["outcome_evidence"][0]["goal_review_eligibility"]["target_release_ms"] == 1000
    assert receiver["outcome_evidence"][0]["goal_plane_crossing"]["status"] != "VERIFIED"
    assert receiver["feedback_prior_outcomes"]  # first-pass decision remains auditable


def test_feedback_has_a_separate_hard_model_budget_and_reuses_cached_role_pixels(monkeypatch):
    monkeypatch.setattr(inspection, "MAX_ACTION_REVIEWS", 1)
    monkeypatch.setattr(feedback, "MAX_FEEDBACK_REVIEWS", 1)
    monkeypatch.setattr(inspection, "frame_times", lambda *_: [1000, 1200])
    monkeypatch.setattr(vision, "_read_frames", lambda _v, times: {t: (t, np.zeros((100,100,3), dtype=np.uint8)) for t in times})
    monkeypatch.setattr(vision, "_write_jpg", lambda *_: True)
    monkeypatch.setattr(physical.dense_track_refinement, "_default_detector", lambda: None)
    async def pixels_reader(*_a, **_k): return {"status": "COMPLETED", "frames": []}
    monkeypatch.setattr(vision, "read_action_pixel_evidence", pixels_reader)
    bundle = vision.ShadowVisionProviders("fake", "test")
    base = {"start_ms": 900, "end_ms": 1400, "scene_id": "scene"}
    for name, phase in [("a", "INITIAL"), ("b", "INITIAL"), ("c", "FEEDBACK"), ("d", "FEEDBACK")]:
        result = bundle.action_evidence_provider("unused", {**base, "inspection_id": name, "phase": phase}, [])
        assert (result["status"] == "DEFERRED") is (name in {"b", "d"})
    assert bundle.inspection_calls == 2 and bundle.feedback_inspection_calls == 1
    requests = [{"media_ms": t, "track_id": "keeper", "box": deepcopy(pixels.BODY)} for t in (1000,1200)]
    monkeypatch.setattr(vision, "_role_review_requests", lambda *_: deepcopy(requests))
    async def role_reader(*_a): return {"role": "GOALKEEPER", "confidence": "high"}
    monkeypatch.setattr(vision, "read_visible_player_role", role_reader)
    first = bundle.role_evidence_provider("unused", {}, [], {}, [], [])
    second = bundle.role_evidence_provider("unused", {}, [], {}, [], [])
    assert first == second and bundle.role_calls == 2
    requests[0]["box"]["x"] += .1
    bundle.role_evidence_provider("unused", {}, [], {}, [], [])
    assert bundle.role_calls == 3  # a changed measured body crop needs its own read
