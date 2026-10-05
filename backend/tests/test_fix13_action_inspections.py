"""Inspection cannot turn an uncertain contact/model story into event proof."""
from copy import deepcopy
import json
from pathlib import Path
import sys

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import action_evidence_review as inspection
import fix10a_goal_direction as direction
import fix10a_vision_providers as vision
import goal_review_scheduler as scheduler
import physical_match_reconstruction as physical
import fix10b_reconciliation as reconciliation
import jersey_consensus


BODY = {"x": .2, "y": .3, "w": .1, "h": .2}
BALL = {"x": .24, "y": .49, "w": .01, "h": .01}


def frame(ms=1000):
    return {"media_ms": ms, "scene_id": "scene", "time_authority": "ACTUAL_MEDIA_PTS",
            "global_target": {"status": "UNRESOLVED", "proof_eligible": False},
            "players": [{"local_track_id": "p1", "association_state": "VERIFIED_LOCAL", "box": deepcopy(BODY)}],
            "ball_candidates": []}


def window(scene="scene", start=0, end=8000, name="w"):
    return {"scene_id": scene, "start_ms": start, "end_ms": end, "dense_window_id": name}


def action(start, end, kind="OTHER", contact=None):
    return {"action_id": str(start), "start_ms": start, "end_ms": end, "kind": kind, "contact_ms": contact}


def test_unknown_labels_and_unproved_contacts_have_a_bounded_whole_video_inspection_path():
    analysis = {"sequences": [{"scene_id": "early", "actions": [action(t, t + 150) for t in range(100, 1800, 200)]},
                               {"scene_id": "late", "actions": [action(56000, 58000, "OFF_BALL_RUN")]}]}
    plan = inspection.build_plan([window("early"), window("late", 53000, 59000, "late")], analysis, budget=2)
    chosen = [j for j in plan["jobs"] if j["selected"]]
    assert {j["scene_id"] for j in chosen} == {"early", "late"}
    assert plan["selected"] == 2 and plan["deferred"] > 0
    assert all("kind" not in j and "expected_jersey_number" not in j for j in plan["jobs"])


def test_inspection_covers_later_time_cells_in_one_scene_before_repeating_early_noise():
    actions = [action(t, t + 150) for t in range(100, 1800, 200)] + [action(56000, 58000)]
    plan = inspection.build_plan([window(end=59000)], {"sequences": [{"scene_id": "scene", "actions": actions}]}, budget=2)
    assert [j["center_ms"] for j in plan["jobs"] if j["selected"]] == [175, 57000]


def test_duplicate_observation_and_empty_semantic_scene_do_not_consume_repeated_slots():
    duplicate = {**action(1000, 1400), "duplicate_of": "1000"}
    plan = inspection.build_plan([window(), window("missed", 9000, 13000, "missing")],
        {"sequences": [{"scene_id": "scene", "actions": [action(1000, 1400), duplicate]}]})
    assert len(plan["jobs"]) == 2
    assert plan["jobs"][1]["reason"] == "PHYSICAL_RECALL_WITHOUT_SEMANTIC_CONTACT"
    assert not inspection.build_plan([window()], {}, budget=0)["selected"]
    assert not inspection.build_plan([window(end=0)], {})["jobs"]


def test_invalid_times_are_rejected_and_contact_sampling_keeps_early_and_terminal_context():
    analysis = {"sequences": [{"scene_id": "scene", "actions": [action(float("nan"), 1400), action(1000, 1200, "DUEL", 1100)]}]}
    job = inspection.build_plan([window()], analysis)["jobs"][0]
    frames = [frame(ms) for ms in range(800, 4000, 50)]
    requested = inspection.frame_times(job, frames)
    assert len(requested) <= 12 and 1100 in requested and 3700 in requested
    assert any(1100 < ms < 1300 for ms in requested)
    assert not inspection.frame_times(job, [{**frame(1100), "used_fallback": True}])


def observed(ball=None, body=BODY, ms=1000):
    return {"frames": [{"media_ms": ms, "scene_id": "scene", "ball_candidates": [ball] if ball else [],
                        "jersey_bodies": [{"box": deepcopy(body)}], "goal": True, "player_number": "15"}]}


def corroborated():
    return {"box": deepcopy(BALL), "proposal_box": deepcopy(BALL), "confidence": .8,
            "source": "NATIVE_REVIEW_ROI_DETECTOR", "pixel_corroborated": True}


@pytest.mark.parametrize("change", [{"pixel_corroborated": False}, {"source": "MODEL"}, {"confidence": .001},
                                   {"confidence": float("nan")}, {"proposal_box": {**BALL, "x": .8}}])
def test_model_proposals_or_failed_pixel_checks_cannot_supply_physical_ball_rows(change):
    out = inspection.apply_observations([frame()], observed({**corroborated(), **change}), "inspection")
    assert not out["frames"][0]["ball_candidates"]
    assert out["frames"][0]["global_target"]["proof_eligible"] is False
    assert "goal" not in out["frames"][0] and "player_number" not in out["frames"][0]


def test_new_detector_pixel_rows_are_proposals_and_keep_identity_unchanged():
    original = [frame()]
    out = inspection.apply_observations(original, observed(corroborated()), "inspection")
    assert out["added_ball_candidates"] == 1
    assert out["frames"][0]["global_target"] == original[0]["global_target"]
    assert original[0]["ball_candidates"] == []
    assert out["jersey_requests"][0]["expected_jersey_number"] is None
    assert not inspection.apply_observations(original, observed(corroborated(), ms=1017), "inspection")["added_ball_candidates"]
    assert not inspection.apply_observations([{**frame(), "cut_barrier": True}], observed(corroborated()), "inspection")["added_ball_candidates"]


def test_raw_number_audit_is_preserved_once_without_replicating_into_dense_frames():
    raw = {"provider": "openai", "raw_response": "x" * 50000, "input_sha256": "hash"}
    votes = [{"readable": True, "number": "15", "confidence": "high", "media_ms": ms, "model_review_audit": raw}
             for ms in (1000, 1200)]
    result = jersey_consensus.apply_jersey_consensus([frame(ms) for ms in range(1000, 2000, 20)], {}, {"p1": votes})
    assert result["consensus_by_track"]["p1"]["status"] == "VERIFIED"
    assert len(result["model_audits_by_track"]["p1"]) == 2
    assert "raw_response" not in json.dumps(result["window_evidence"])


def test_ambiguous_body_crop_cannot_feed_number_consensus_for_a_neighbour():
    row = frame()
    row["players"].append({"local_track_id": "p2", "association_state": "VERIFIED_LOCAL", "box": {**BODY, "x": .23}})
    assert not inspection.apply_observations([row], observed(), "inspection")["jersey_requests"]
    row = frame()
    row["players"][0]["association_state"] = "HYPOTHESES"
    assert not inspection.apply_observations([row], observed(), "inspection")["jersey_requests"]


def test_native_roi_detector_keeps_original_frame_coordinates_and_its_own_confidence(monkeypatch):
    def detect(_detector, crop, **kwargs):
        assert kwargs["_detail_pass"] is True
        height, width = crop.shape[:2]
        # The centered proposal defines a 180x180 crop in this image.
        return [], [{"box": {"x": .5 - 5 / width, "y": .5 - 5 / height, "w": 10 / width, "h": 10 / height}, "confidence": .73}]
    monkeypatch.setattr(vision.action_evidence_review, "MAX_ACTION_REVIEWS", 16)
    import dense_track_refinement
    monkeypatch.setattr(dense_track_refinement, "_detect_dense_people_and_ball", detect)
    proposal = {"x": .495, "y": .495, "w": .01, "h": .01}
    rows = vision.corroborate_ball_pixels(object(), np.zeros((1000, 1000, 3), np.uint8), proposal)
    assert rows[0]["box"] == pytest.approx(proposal)
    assert rows[0]["confidence"] == .73 and rows[0]["pixel_corroborated"]


async def test_pixel_reader_receives_no_semantic_outcome_or_target_number_and_preserves_raw_audit(monkeypatch, tmp_path):
    sent = []
    class Chat:
        def __init__(self, **_kwargs): pass
        def with_model(self, *_args): return self
        async def send_message(self, message):
            sent.append(message.text)
            return '{"frames":[{"idx":1,"balls":[],"jersey_bodies":[]}]}'
    path = tmp_path / "frame.jpg"
    path.write_bytes(b"pixel-input")
    monkeypatch.setattr(vision, "LlmChat", Chat)
    result = await vision.read_action_pixel_evidence("key", "session", [str(path)], [1000])
    assert result["status"] == "COMPLETED" and json.loads(result["raw_response"])["frames"]
    assert len(result["input_sha256"]) == len(result["response_sha256"]) == 64
    assert "15" not in sent[0] and "GOAL" not in sent[0] and "ASSIST" not in sent[0]


def review_job(ms, name="w", end=8000, ball=BALL):
    strike = {"strike_id": f"s{ms}", "touch_id": f"t{ms}", "scene_id": "scene", "media_ms": ms,
              "player_track_id": "p1", "proof_eligible": True, "status": "VERIFIED_PHYSICAL_RELEASE",
              "active_ball_anchor": {"media_ms": ms, "box": deepcopy(ball)}, "contact_role": {"role": "RELEASE"}}
    return {"window": window(name=name, end=end), "strike": strike, "review": {"lane": "CLARIFICATION"},
            "touch_graph": {"touches": [{"touch_id": f"t{ms}", "contact_geometry": {"actor_box_used": deepcopy(BODY)}}]}}


def test_overlap_chooses_complete_context_once_but_competing_balls_remain_separate():
    jobs = [review_job(1000, "short", 1500), review_job(1017, "long", 4000),
            review_job(1000, "spare", ball={**BALL, "x": .8})]
    calls = []
    provider = direction.GoalDirectionProvider(lambda w, s: calls.append((w["end_ms"], s["media_ms"])) or {}, "", "test", "unused")
    ordered = scheduler.ordered_requests(jobs, {})
    for job in ordered:
        provider(job["window"], job["strike"])
    assert len(calls) == 2 and provider.clarification_calls == 2
    assert (3617, 1017) in calls
    assert "_review_context" not in jobs[0]["strike"]


def test_goal_budget_reaches_late_time_in_same_scene_and_has_separate_verified_reserve():
    jobs = [review_job(t) for t in range(100, 1900, 100)] + [review_job(56000, end=60000)]
    ordered = scheduler.ordered_requests(jobs, {})
    assert [j["strike"]["media_ms"] for j in ordered[:2]] == [100, 56000]
    assert direction.GoalDirectionProvider(lambda *_: {}, "", "t", "v").max_clarifications >= 5


@pytest.mark.parametrize("wrong_ball", [False, True])
def test_goal_reader_receives_exact_contact_ball_reference_and_cannot_follow_a_spare(monkeypatch, wrong_ball):
    captured = {}
    def decode(_video, requested):
        return {ms: (ms, np.zeros((64, 64, 3), np.uint8)) for ms in requested}
    def write(path, _image):
        path.write_bytes(b"frame")
        return True
    async def reader(_key, _session, _paths, times, ball_reference=None):
        captured.update(times=times, reference=ball_reference)
        line = {"p1": {"x": .9, "y": .3}, "p2": {"x": .9, "y": .7}}
        return {"geometry_status": "VERIFIED", "frames": [{"media_ms": ms, "line": line} for ms in times],
                "crossing": "CROSSED", "crossing_confidence": "high", "proof_ready": True, "same_ball_continuity": True,
                "ball_evidence": [{"media_ms": ball_reference["media_ms"], "ball_visible": True, "confidence": "high",
                                   "ball_box": {**BALL, "x": .8} if wrong_ball else BALL}]}
    monkeypatch.setattr(vision, "_read_frames", decode)
    monkeypatch.setattr(vision, "_write_jpg", write)
    monkeypatch.setattr(vision, "read_goal_scene_evidence", reader)
    bundle = vision.ShadowVisionProviders("key", "reference").bind_video_path("unused")
    strike = {"media_ms": 1000, "status": "VERIFIED_PHYSICAL_RELEASE", "active_ball_anchor": {
        "media_ms": 1017, "box": BALL, "proof_eligible": True, "time_authority": "ACTUAL_MEDIA_PTS", "state": "MEASURED"}}
    result = bundle.goal_geometry_provider(window(end=4000), strike)
    assert captured["times"][captured["reference"]["idx"] - 1] == 1017
    assert len(captured["times"]) <= vision.MAX_GOAL_FRAMES and captured["times"][-1] == 3600
    audit = result["visual_crossing_audit"]
    assert audit["active_ball_link"]["status"] == ("UNRESOLVED" if wrong_ball else "VERIFIED")
    if wrong_ball:
        assert not audit["proof_ready"] and audit["status"] == "UNRESOLVED"


def test_structured_visual_crossing_must_follow_the_contact_ball_before_it_crosses():
    import test_fix10a7_structured_goal_proof as fixture
    import shot_outcome_engine as engine
    import fix10a_ball_proof_gate as ball_gate
    for link in ({"status": "UNRESOLVED", "media_ms": 950}, {"status": "VERIFIED", "media_ms": 1300},
                 {"status": "VERIFIED", "media_ms": 950}):
        geometry = fixture._geometry()
        geometry["visual_crossing_audit"]["active_ball_link"] = link
        result = engine.reconstruct_post_strike_outcome(fixture._strike(), [], {}, goal_geometry=geometry)
        result = direction.apply_direction_gate(result, [], geometry)
        result = ball_gate.apply_ball_proof_gate(result, [])
        valid = link["status"] == "VERIFIED" and link["media_ms"] == 950
        assert (result["goal_plane_crossing"]["status"] == "VERIFIED") is valid


def test_inspection_runs_before_uncertain_contact_can_block_it_and_cannot_register_model_goal(monkeypatch):
    import test_fix10a_physical_reconstruction as fixture
    fixture._patch_window(monkeypatch, frames=[{**frame(1000), "scene_id": "scene_001"}, {**frame(1200), "scene_id": "scene_001"}],
                          contact=fixture._contact_result())
    seen = []
    def inspect(_video, job, frames):
        seen.append(job)
        assert not frames[0]["global_target"]["proof_eligible"]
        return {"status": "COMPLETED", "frames": [], "goal": True, "actor_number": "15"}
    plan, analysis, graph, authority = fixture._base_inputs()
    analysis["sequences"][0]["actions"] = [action(950, 1250, "OTHER")]
    result = physical.reconstruct_physical_match("unused", plan, analysis, graph, authority, action_evidence_provider=inspect)
    assert seen and result["status"] == "ok"
    trace = result["traces"][0]
    assert trace["action_inspections"][0]["goal"] is True
    assert not trace["strike_evidence"] and not reconciliation.proposals_from_trace(trace)


def test_final_goal_review_keeps_earlier_number_and_role_reader_failures(monkeypatch):
    import test_fix10a_physical_reconstruction as fixture
    fixture._patch_window(monkeypatch)
    strike = fixture._goal_review_strike(1000, "p010", "contact1", target=True)
    monkeypatch.setattr(physical.shot_outcome_engine, "find_strike_releases", lambda *_: [deepcopy(strike)])
    monkeypatch.setattr(physical.shot_outcome_engine, "find_scoring_control_contacts", lambda *_: [])
    plan, analysis, graph, authority = fixture._base_inputs()
    published = []
    result = physical.reconstruct_physical_match(
        "unused", plan, analysis, graph, authority,
        jersey_vote_provider=lambda *_: {"p010": [{"reason": "jersey_reader_invalid_json"}]},
        role_evidence_provider=lambda *_: {"p010": {"reason": "role_reader_error"}},
        goal_geometry_provider=lambda *_: {"status": "UNRESOLVED", "reason": "goal_reader_error"},
        trace_callback=lambda trace: published.append(deepcopy(trace)),
    )
    assert [t["goal_review_phase"] for t in published] == ["pending", "complete"]
    expected = {"jersey_reader_invalid_json", "role_reader_error", "goal_reader_error"}
    assert expected <= set(result["traces"][0]["provider_adapter_errors"])
    assert expected <= set(result["windows"][0]["provider_adapter_errors"])


def test_readonly_replay_keeps_no_key_offline_and_exports_checksummed_partial_results(monkeypatch, tmp_path):
    import hashlib
    import zipfile
    from scripts import replay_report_evidence as replay
    import test_fix10a_production_runtime as fixture
    original = fixture._trace()
    original["window"].update(scene_id="scene", dense_window_id="dense_001", start_ms=900, end_ms=1300)
    original["decoded_frames"] = [frame(), frame(1200)]
    source = fixture._unified()
    report = {"id": "test-report", "full_report": {}, "unified_identity_authority": {},
              "football_sequence_analysis": source["sequence_analysis"], "football_scene_graph": {},
              "canonical_events": source["canonical_events"], "fix10a_physical_summary": {"recall_coverage": {}}}
    payloads = {"report.json": json.dumps(report).encode(), "traces/000.json": json.dumps(original).encode()}
    filename = tmp_path / "input.zip"
    with zipfile.ZipFile(filename, "w") as z:
        for name, data in payloads.items(): z.writestr(name, data)
        z.writestr("SHA256SUMS", "".join(f"{hashlib.sha256(data).hexdigest()}  {name}\n" for name, data in payloads.items()))
    monkeypatch.delenv("EMERGENT_LLM_KEY", raising=False)
    output = tmp_path / "review"
    result = replay.replay(filename, output_dir=output)
    assert result["model_request_attempts"] == result["db_writes"] == 0
    assert not result["coverage"]["complete"]
    assert "SOURCE_SCENE_GRAPH_FRAMES_NOT_EXPORTED" in result["coverage"]["reasons"]
    with zipfile.ZipFile(output / "reviewed-evidence.zip") as z:
        for line in z.read("SHA256SUMS").decode().splitlines():
            digest, name = line.split(None, 1)
            assert hashlib.sha256(z.read(name.strip())).hexdigest() == digest
        assert json.loads(z.read("manifest.json"))["db_writes"] == 0
    with pytest.raises(RuntimeError, match="requires EMERGENT_LLM_KEY"):
        replay.replay(filename, support_vision=True)
