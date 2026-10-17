"""First-read authority/reuse regressions. All model replies are test doubles."""
from copy import deepcopy
import ast
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Optional

import pytest

import action_evidence_review as review
import canonical_event_resolver as resolver
import football_sequence_intelligence as sequence
import physical_match_reconstruction as physical
import unified_analysis_engine as engine
from test_fix09b3_canonical_event_resolver import TB, OB, frame, graph, authority


SOURCE = hashlib.sha256(b"canonical source").hexdigest()
VIDEO_INPUT = {"protocol": "TEMPORAL_VIDEO_INPUT_V1", "model": "gemini-2.5-pro",
    "model_video_sha256": hashlib.sha256(b"actual analysis rendition").hexdigest(),
    "reference_sha256": [hashlib.sha256(b"original selected-player crop").hexdigest()],
    "requested_fps": 8., "sampling_attached_to_provider_payload": False,
    "provider_receipt_confirmed": False}
WINDOW = {"sequence_id": "seq1", "scene_id": "scene_001", "start_ms": 0, "end_ms": 4000}


def response(kind="SHOT", outcome="SAVED"):
    action = {"action_id": "a1", "kind": kind, "start_ms": 800, "contact_ms": 1000, "end_ms": 1200,
        "target_status": "VERIFIED", "actor_local_track_id": None,
        "actor_evidence": [{"media_ms": ms, "box": deepcopy(TB), "visibility": "VISIBLE"} for ms in (800, 1000)],
        "evidence_ms": [800, 1000], "outcome": outcome, "outcome_visible": True,
        "outcome_evidence_ms": [2000, 3000], "contact_visibility": "VISIBLE",
        "selected_reference_match": {"same_player": True, "confidence": "high", "evidence_ms": [800],
            "features": ["hair", "boots"], "continuous_visible_actor": True},
        "causal_chain": {"target_contact_ms": 1000, "goal_outcome_ms": 3000,
            "continuous_visible_sequence": True}}
    if outcome == "TEAMMATE_GOAL":
        action["causal_chain"].update(receiver_local_track_id="p003", receiver_ms=1600,
            teammate_shot_ms=2200, finisher_local_track_id="p003", receiver_team="TEAMMATE",
            receiver_finisher_same_player=True)
    return {"sequences": [{**WINDOW, "actions": [action]}],
        "coverage": [{"sequence_id": "seq1", "reviewed": True, "target_seen": True, "actions_found": 1}]}


def prepared(*, missing_bodies=False):
    frames = [frame(ms, target=None, status="UNRESOLVED", teams={}) for ms in (800, 1000, 1200, 1600, 2000, 2200, 3000, 4000)]
    # The same visible person acquires a different native ID at contact. No
    # bootstrap OCR, native team certificate or verified target is supplied.
    for f in frames:
        if f["media_ms"] >= 1000:
            f["players"][0]["local_track_id"] = "changed-native-id"
        if missing_bodies:
            f["players"] = []
    return {"sequence_plan": {"analysis_windows": [deepcopy(WINDOW)], "refinement_windows": []},
        "scene_graph": graph(frames), "authority": authority(), "metrics": {"sequence_windows": 1}}


def audited(raw):
    return sequence.source_observation_receipt(raw, json.dumps(raw), "Actual existing video prompt", VIDEO_INPUT, SOURCE)


def finalise(raw=None, *, ctx=None):
    raw = response() if raw is None else raw
    return engine.finalise_analysis(raw, prepared() if ctx is None else ctx, source_observations=[audited(raw)])


@pytest.mark.parametrize("kind,outcome,event_type", [("SHOT", "SAVED", "SHOT"), ("SHOT", "GOAL", "GOAL"),
    ("PASS", "TEAMMATE_GOAL", "ASSIST")])
def test_existing_read_can_identify_actor_and_complete_the_chain_once(kind, outcome, event_type):
    raw = response(kind, outcome)
    before = deepcopy(raw)
    result = finalise(raw)
    event, = result["canonical_events"]["events"]
    assert event["identity_resolution"] == "SOURCE_VIDEO_SELECTED_PLAYER"
    assert event["actor_local_track_id"] == "changed-native-id"
    assert event["canonical_event_type"] == event_type and event["canonical_outcome"] == outcome
    assert resolver.has_motion_proof(event)
    video = event["proof"]["video_observation"]
    assert video["source_video_sha256"] == SOURCE and video["reference_sha256"] == VIDEO_INPUT["reference_sha256"]
    assert video["provider_receipt_confirmed"] is False  # no fictitious provider acknowledgement
    assert {2000, 3000} <= set(event["proof"]["evidence_ms"])
    assert raw == before


def test_source_reference_comparison_does_not_require_a_native_body_detection():
    event, = finalise(ctx=prepared(missing_bodies=True))["canonical_events"]["events"]
    assert event["actor_local_track_id"] == "GLOBAL_TARGET" and event["causal_verified"]


@pytest.mark.parametrize("failure", ["no_runtime_receipt", "model_attests_own_input", "edited_action", "wrong_scene",
    "no_reference_image", "no_visible_reference", "low_reference_confidence", "no_actor_continuity"])
def test_labels_and_unbound_or_incomplete_identity_claims_do_not_gain_authority(failure):
    raw = response()
    receipt = audited(raw)
    if failure == "no_runtime_receipt": receipt = {}
    elif failure == "model_attests_own_input":
        raw["source_observations"] = [receipt]
        raw["sequences"][0]["actions"][0]["video_observation"] = receipt
        receipt = {}
    elif failure == "edited_action": raw["sequences"][0]["actions"][0]["contact_ms"] = 1100
    elif failure == "wrong_scene": raw["sequences"][0]["scene_id"] = "other-scene"
    elif failure == "no_reference_image":
        receipt = sequence.source_observation_receipt(raw, json.dumps(raw), "prompt",
            {**VIDEO_INPUT, "reference_sha256": []}, SOURCE)
    else:
        match = raw["sequences"][0]["actions"][0]["selected_reference_match"]
        if failure == "no_visible_reference": match["evidence_ms"] = [1500]
        elif failure == "low_reference_confidence": match["confidence"] = "low"
        else: match["continuous_visible_actor"] = False
        receipt = audited(raw)
    result = engine.finalise_analysis(raw, prepared(), source_observations=[receipt])
    assert not result["canonical_events"]["events"]


@pytest.mark.parametrize("contradiction", ["visible_other_body", "direct_selected_geometry", "reference_is_other_player"])
def test_actual_identity_contradictions_still_reopen_or_reject_the_observation(contradiction):
    raw, ctx = response(), prepared()
    if contradiction == "visible_other_body":
        for f in ctx["scene_graph"]["frames"]:
            f["global_target"].update(status="VERIFIED", proof_eligible=True, local_track_id="p002")
    elif contradiction == "direct_selected_geometry": ctx["authority"] = authority([(800, OB)])
    else: raw["sequences"][0]["actions"][0]["selected_reference_match"]["same_player"] = False
    result = finalise(raw, ctx=ctx)["canonical_events"]
    assert not result["events"] and (result["unresolved"] or result["rejected"])


@pytest.mark.parametrize("missing", ["contact", "conflicting_contact", "outcome_pixels", "continuous_play", "outcome_before_contact"])
def test_missing_link_preserves_the_observed_shot_without_promoting_its_outcome(missing):
    raw = response()
    action = raw["sequences"][0]["actions"][0]
    if missing == "contact":
        action["contact_ms"] = action["causal_chain"]["target_contact_ms"] = None
    elif missing == "conflicting_contact": action["causal_chain"]["target_contact_ms"] = 1100
    elif missing == "outcome_pixels":
        action["outcome_evidence_ms"] = []
        action["causal_chain"]["goal_outcome_ms"] = None
    elif missing == "continuous_play": action["causal_chain"]["continuous_visible_sequence"] = False
    else:
        action["causal_chain"]["goal_outcome_ms"] = 500
        action["outcome_evidence_ms"] = []
    event, = finalise(raw)["canonical_events"]["events"]
    assert event["canonical_event_type"] == "SHOT" and event["canonical_outcome"] == "UNKNOWN"
    assert event["causal_verified"] is False


@pytest.mark.parametrize("omit", ["contact_ms", "target_contact_ms", "outcome_evidence_ms", "goal_outcome_ms"])
def test_a_source_timestamp_does_not_need_to_be_repeated_in_a_second_field(omit):
    raw = response()
    action = raw["sequences"][0]["actions"][0]
    (action if omit in action else action["causal_chain"]).pop(omit)
    event, = finalise(raw)["canonical_events"]["events"]
    assert event["contact_ms"] == 1000 and event["canonical_outcome"] == "SAVED"


def test_retry_cannot_borrow_a_different_responses_action_provenance():
    first = response()
    retry = response("SHOT", "GOAL")
    merged = engine.merge_model_attempts([first, retry])
    old_only = engine.finalise_analysis(merged, prepared(), source_observations=[audited(first)])
    assert not old_only["canonical_events"]["events"]
    result = engine.finalise_analysis(merged, prepared(), source_observations=[audited(first), audited(retry)])
    event, = result["canonical_events"]["events"]
    assert event["canonical_event_type"] == "GOAL"
    assert event["proof"]["video_observation"]["response_sha256"] == audited(retry)["response_sha256"]


@pytest.mark.parametrize("cut_ms", [1000, 2000])
def test_an_actual_cut_cannot_join_reference_contact_and_outcome(cut_ms):
    ctx = prepared()
    next(f for f in ctx["scene_graph"]["frames"] if f["media_ms"] == cut_ms)["cut_barrier"] = True
    result = finalise(ctx=ctx)
    assert not any(resolver.has_motion_proof(e) for e in result["canonical_events"]["events"])


def test_source_clock_is_preserved_without_reference_event_times():
    shift = 17321
    raw, ctx = response(), prepared()
    action = raw["sequences"][0]["actions"][0]
    for key in ("start_ms", "contact_ms", "end_ms"):
        action[key] += shift
    for rows in (action["actor_evidence"], ctx["scene_graph"]["frames"]):
        for row in rows:
            row["media_ms"] += shift
    action["evidence_ms"] = [ms+shift for ms in action["evidence_ms"]]
    action["outcome_evidence_ms"] = [ms+shift for ms in action["outcome_evidence_ms"]]
    action["selected_reference_match"]["evidence_ms"] = [800+shift]
    for key in ("target_contact_ms", "goal_outcome_ms"):
        action["causal_chain"][key] += shift
    for row in (raw["sequences"][0], ctx["sequence_plan"]["analysis_windows"][0]):
        row["start_ms"] += shift
        row["end_ms"] += shift
    event, = finalise(raw, ctx=ctx)["canonical_events"]["events"]
    assert event["contact_ms"] == 1000+shift and event["canonical_outcome"] == "SAVED"


def inspection_plan(result, **kwargs):
    return review.build_plan([{**WINDOW, "dense_window_id": "native-window"}], result["sequence_analysis"],
        observed_events=result["canonical_events"]["events"], source_video_sha256=SOURCE, **kwargs)


def test_fully_resolved_existing_read_replaces_its_inspection_without_spending_the_budget():
    plan = inspection_plan(finalise(), budget=1)
    assert plan["selected"] == plan["deferred"] == 0 and plan["reused"] == 1
    job, = plan["jobs"]
    assert job["reason"] == "SOURCE_SEQUENCE_ALREADY_RESOLVED" and job["reused_event_ids"]


@pytest.mark.parametrize("gap", ["unresolved_action", "unresolved_outcome", "partial_coverage", "outside_review", "foreign_source", "empty_window"])
def test_unresolved_or_unreviewed_work_keeps_its_inspection(gap):
    result = finalise()
    if gap == "unresolved_action": result["canonical_events"]["events"] = []
    elif gap == "unresolved_outcome": result["canonical_events"]["events"][0]["causal_verified"] = False
    elif gap == "partial_coverage": result["sequence_analysis"]["coverage"][0]["contract_complete"] = False
    elif gap == "outside_review": result["sequence_analysis"]["sequences"][0]["end_ms"] = 3900
    elif gap == "foreign_source": result["canonical_events"]["events"][0]["proof"]["video_observation"]["source_video_sha256"] = "different"
    else: result["sequence_analysis"]["sequences"][0]["actions"] = []
    plan = inspection_plan(result)
    assert plan["selected"] == 1 and plan["reused"] == 0


def test_reused_read_frees_its_allocation_for_another_unresolved_window():
    result = finalise()
    other = {"dense_window_id": "unreviewed-window", "scene_id": "new-scene", "start_ms": 5000, "end_ms": 7000}
    plan = review.build_plan([{**WINDOW, "dense_window_id": "native-window"}, other], result["sequence_analysis"], budget=1,
        observed_events=result["canonical_events"]["events"], source_video_sha256=SOURCE)
    assert plan["selected"] == plan["reused"] == 1 and plan["deferred"] == 0
    assert next(j for j in plan["jobs"] if j["selected"])["scene_id"] == "new-scene"


def test_an_overlapping_unresolved_observation_is_not_hidden_by_a_complete_window():
    result = finalise()
    other = deepcopy(result["sequence_analysis"]["sequences"][0])
    other["sequence_id"] = "overlapping-sequence"
    other["actions"][0]["action_id"] = "unresolved-action"
    result["sequence_analysis"]["sequences"].append(other)
    assert inspection_plan(result)["selected"] == 1


def test_unrelated_native_release_keeps_its_search_after_an_observed_result_is_reused():
    import attack_sequence_search
    import test_fix10a_physical_reconstruction as fixture
    frames = [fixture._frame(ms) for ms in range(0, 4001, 50)]
    def strike(name, ms):
        return {"strike_id": name, "scene_id": "scene_001", "media_ms": ms,
            "player_track_id": "p010", "global_target_id": "GLOBAL_TARGET",
            "proof_eligible": True, "status": "VERIFIED_PHYSICAL_RELEASE"}
    trace = {"window": WINDOW, "decoded_frames": frames,
        "strike_evidence": [strike("already-observed", 1000), strike("new-release", 2500)],
        "outcome_evidence": [{"strike_id": "already-observed", "goal_geometry_evidence": {
            "reason": "OUTCOME_ALREADY_RESOLVED_FROM_SOURCE_CLIP"}}]}
    questions = attack_sequence_search.questions(trace)
    assert questions and {q["strike_id"] for q in questions} == {"new-release"}


def test_an_observed_assist_finish_is_reused_when_the_native_finisher_id_changes():
    event, = finalise(response("PASS", "TEAMMATE_GOAL"))["canonical_events"]["events"]
    role = next(r for r in event["proof"]["receiver_team_evidence"]["evidence"] if r["role"] == "TEAMMATE_FINISHER")
    native = {"media_ms": 2200, "scene_id": "scene_001", "players": [
        {"local_track_id": "native-finisher", "box": deepcopy(role["box"])}]}
    strike = {"scene_id": "scene_001", "player_track_id": "native-finisher", "media_ms": 2200}
    assert physical._motion_event_for_strike(strike, [event]) is None
    assert physical._motion_event_for_strike(strike, [event], [native]) is event
    assert physical._motion_event_for_strike(strike, [event], [{**native, "media_ms": 2300}]) is None


@pytest.mark.parametrize("failure", [None, "different_source", "incomplete_event", "cut", "fallback",
    "different_clock", "ambiguous_body", "unverified_body", "source_conflict"])
def test_known_actor_is_shared_with_dense_measurements_without_another_identity_call(failure):
    import dense_identity_continuity as identity
    import test_fix10a_physical_reconstruction as fixture
    events = finalise()["canonical_events"]["events"]
    frames = [fixture._frame(ms) for ms in (800, 1000)]
    for f in frames:
        f["players"][1]["box"] = deepcopy(OB)
    frames[1]["players"][0]["local_track_id"] = "another-dense-id"
    source = SOURCE
    if failure == "different_source": source = "different-source"
    elif failure == "incomplete_event": events[0]["causal_verified"] = False
    for f in frames:
        if failure == "cut": f["cut_barrier"] = True
        elif failure == "fallback": f["used_fallback"] = True
        elif failure == "different_clock": f["media_ms"] += 31
        elif failure == "ambiguous_body": f["players"][1]["box"] = deepcopy(TB)
        elif failure == "unverified_body": f["players"][0]["association_state"] = "HYPOTHESES"
        elif failure == "source_conflict": f["global_target"]["reason"] = "SOURCE_CONFLICT"
    before = deepcopy(frames)
    output = identity.apply_reference_matches(frames, {"source_events": events, "source_video_sha256": source})
    assert frames == before
    if failure:
        assert not any(f["global_target"].get("proof_eligible") for f in output)
    else:
        assert [f["global_target"]["local_track_id"] for f in output] == ["p010", "another-dense-id"]
        assert all(f["global_target"]["reason"] == "SOURCE_VIDEO_SELECTED_PERSON" for f in output)


def test_reconstruction_reuses_the_initial_result_and_still_runs_native_recall(monkeypatch):
    import test_fix10a_physical_reconstruction as fixture
    result = finalise()
    native_frames = [fixture._frame(ms) for ms in range(0, 4001, 50)]
    fixture._patch_window(monkeypatch, frames=native_frames, contact=fixture._contact_result())
    window = {**WINDOW, "dense_window_id": "native-window"}
    monkeypatch.setattr(physical.dense_replay, "select_critical_windows", lambda *_: [window])
    counts = {"native_contacts": 0}
    def contacts(*_):
        counts["native_contacts"] += 1
        return fixture._contact_result()
    monkeypatch.setattr(physical.ball_contact_engine, "resolve_contacts", contacts)
    strike = {"strike_id": "native-contact", "scene_id": "scene_001", "media_ms": 1000,
        "player_track_id": "changed-native-id", "global_target_id": "GLOBAL_TARGET",
        "proof_eligible": True, "status": "VERIFIED_PHYSICAL_RELEASE"}
    monkeypatch.setattr(physical.shot_outcome_engine, "find_strike_releases", lambda *_: [strike])
    monkeypatch.setattr(physical.shot_outcome_engine, "find_scoring_control_contacts", lambda *_: [])
    monkeypatch.setattr(physical, "_strike_ball_paths", lambda *_: pytest.fail("same ball path reconstructed again"))
    monkeypatch.setattr(physical.shot_outcome_engine, "reconstruct_post_strike_outcome",
        lambda *_a, **_kw: pytest.fail("same outcome reconstructed again"))
    def duplicate(*_a, **_kw): pytest.fail("already resolved play sent to another model")
    output = physical.reconstruct_physical_match("source.mp4", result["sequence_plan"], result["sequence_analysis"],
        result["scene_graph"], result["identity_authority"], action_evidence_provider=duplicate,
        role_evidence_provider=duplicate, goal_geometry_provider=duplicate,
        observed_events=result["canonical_events"]["events"], source_video={"sha256": SOURCE})
    assert output["status"] == "ok" and counts["native_contacts"] == 1
    assert output["action_inspection_plan"]["reused"] == 1
    trace, = output["traces"]
    assert len(trace["decoded_frames"]) == len(native_frames)
    assert trace["motion_observation_summary"]["outcomes_reused"] == 1
    import fix10b_runtime
    reconciled = fix10b_runtime.reconcile_unified_result(result, output)
    event, = reconciled["canonical_events"]["events"]
    assert event["canonical_outcome"] == "SAVED" and resolver.has_motion_proof(event)
    assert event["proof"]["video_observation"]["authority"] == "WHOLE_VIDEO_SEQUENCE_OBSERVATION"


def test_production_wires_the_existing_call_audit_and_canonical_events_forward():
    root = Path(__file__).resolve().parents[1]
    server = ast.parse((root / "server.py").read_text())
    task = next(n for n in server.body if isinstance(n, ast.AsyncFunctionDef) and n.name == "generate_full_report_task")
    calls = [n for n in ast.walk(task) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
             and n.func.id == "call_gemini_with_video" and any(k.arg == "observation_audit" for k in n.keywords)]
    assert len(calls) == 1 and "source_video_sha256" in {k.arg for k in calls[0].keywords}
    runtime = ast.parse((root / "fix10a_runtime.py").read_text())
    reconstruct = next(n for n in ast.walk(runtime) if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute) and n.func.attr == "to_thread"
        and n.args and isinstance(n.args[0], ast.Attribute)
        and n.args[0].attr == "reconstruct_physical_match")
    assert "observed_events" in {k.arg for k in reconstruct.keywords}


@pytest.mark.parametrize("retry", [False, True])
async def test_existing_server_call_records_the_actual_successful_attempt_without_an_extra_approval(tmp_path, retry):
    """Execute the production function with explicit transport/database doubles."""
    import asyncio
    import video_model_input
    root = Path(__file__).resolve().parents[1]
    tree = ast.parse((root / "server.py").read_text())
    function = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == "call_gemini_with_video")
    sent = []
    class Adapter:
        def __init__(self, _key, session, video, references, **_kwargs):
            self.session_id = session
            self.video_input_audit = deepcopy(VIDEO_INPUT)
            self.video, self.references = video, references
    async def model_call(_collection, adapter, message, **_kwargs):
        sent.append((adapter, message))
        return "invalid first response" if retry and len(sent) == 1 else json.dumps(response())
    source, reference = tmp_path / "source.mp4", tmp_path / "selected.jpg"
    source.write_bytes(b"source")
    reference.write_bytes(b"selected source pixels")
    no_log = lambda *_a, **_kw: None
    namespace = dict(Optional=Optional, Path=Path, asyncio=asyncio,
        EMERGENT_LLM_KEY="test-double", analysis_jobs=SimpleNamespace(model_call=model_call),
        db=SimpleNamespace(analysis_model_calls=None), extract_json=json.loads,
        _ensure_analysis_video=lambda p: p,
        logger=SimpleNamespace(warning=no_log, info=no_log, error=no_log, exception=no_log))
    module = ast.fix_missing_locations(ast.Module(body=[function], type_ignores=[]))
    exec(compile(module, str(root / "server.py"), "exec"), namespace)
    audit = {"stale_attempt": True}
    from unittest.mock import patch
    with patch.object(video_model_input, "IsolatedVideoChat", Adapter):
        result = await namespace["call_gemini_with_video"]("sequence-fixture", "Observe", str(source),
            anchor_crops=[str(reference)], observation_audit=audit, source_video_sha256=SOURCE)
    assert result == response() and len(sent) == (2 if retry else 1)
    assert "stale_attempt" not in audit
    assert audit["response_sha256"] == hashlib.sha256(json.dumps(result).encode()).hexdigest()
    assert audit["input_sha256"] == sequence.source_observation_receipt(
        result, json.dumps(result), sent[-1][1], sent[-1][0].video_input_audit, SOURCE)["input_sha256"]
    assert sent[-1][0].references == [str(reference)]
