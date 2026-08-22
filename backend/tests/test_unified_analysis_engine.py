"""Integrated FIX09B→FIX09C orchestration contract tests."""
import copy
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

import unified_analysis_engine as uae  # noqa: E402


def test_engine_prepare_uses_one_authority_through_scene_graph_and_plan(monkeypatch):
    authority = {"target_points": [{"media_ms": 1000}], "global_target_id": "GLOBAL_TARGET"}
    bundle = {"authority": authority, "identity_context": {"global_target_id": "GLOBAL_TARGET"}}
    seen = {}

    monkeypatch.setattr(uae.unified_event_bridge, "build_identity_bundle", lambda **kw: bundle)

    def graph(video, auth):
        seen["graph_auth"] = auth
        return {"frames": [{"media_ms": 1000}], "global_target_id": "GLOBAL_TARGET"}
    monkeypatch.setattr(uae.football_scene_graph, "build_scene_graph", graph)

    def plan(g):
        seen["plan_graph"] = g
        return {"analysis_windows": [{"sequence_id": "s1"}], "refinement_windows": []}
    monkeypatch.setattr(uae.football_sequence_intelligence, "build_sequence_plan", plan)
    monkeypatch.setattr(uae.football_sequence_intelligence, "build_analysis_prompt",
                        lambda p, pd, ic: "PROMPT")
    monkeypatch.setattr(uae.unified_identity_authority, "to_production_track",
                        lambda auth: {"points": [{"t": 1.0}]})
    monkeypatch.setattr(uae.unified_event_bridge, "choose_event_track",
                        lambda b, fallback_fix04_track=None: ({"points": [{"t": 1.0}]}, "UNIFIED"))

    out = uae.prepare_analysis(
        video_path="video.mp4", fix04_track={"points": []}, identity_timeline={},
        anchors=[], identity_profile={}, player_details={})
    assert out["status"] == "prepared"
    assert out["authority"] is authority
    assert seen["graph_auth"] is authority
    assert seen["plan_graph"] is out["scene_graph"]
    assert out["analysis_prompt"] == "PROMPT"
    assert out["event_track_source"] == "UNIFIED"


def test_engine_finalise_flows_normalised_sequences_into_b3_then_c(monkeypatch):
    prepared = {
        "sequence_plan": {"analysis_windows": [{"sequence_id": "s1"}]},
        "scene_graph": {"frames": []}, "authority": {"global_target_id": "GLOBAL_TARGET"},
        "production_track": {"points": []}, "event_track": {"points": []},
        "event_track_source": "UNIFIED", "metrics": {"identity_points": 3},
    }
    norm = {"coverage_complete": True, "metrics": {"actions_total": 5}, "sequences": []}
    canonical = {"status": "ok", "events": [{"event_id": "e1"}],
                 "metrics": {"events_accepted": 1, "observations_unresolved": 1,
                             "observations_rejected": 2}}
    seen = {}
    monkeypatch.setattr(uae.football_sequence_intelligence, "normalise_sequence_analysis",
                        lambda raw, plan: norm)

    def resolve(sa, sg, auth):
        seen.update(sa=sa, sg=sg, auth=auth)
        return canonical
    monkeypatch.setattr(uae.canonical_event_resolver, "resolve_canonical_events", resolve)
    monkeypatch.setattr(uae.canonical_output_authority, "build_ledger_compat",
                        lambda c, coverage_complete=False: {"authority": "FIX09B_CANONICAL_EVENTS"})
    monkeypatch.setattr(uae.canonical_output_authority, "project_timeline",
                        lambda c: [{"event_id": "e1"}])
    monkeypatch.setattr(uae.canonical_output_authority, "build_event_native_evidence",
                        lambda c: [{"event_id": "e1"}])

    out = uae.finalise_analysis({"raw": True}, prepared)
    assert seen["sa"] is norm and seen["sg"] is prepared["scene_graph"] and seen["auth"] is prepared["authority"]
    assert out["status"] == "ok"
    assert out["canonical_events"] is canonical
    assert out["action_timeline"] == [{"event_id": "e1"}]
    assert out["metrics"]["actions_observed"] == 5
    assert out["metrics"]["events_accepted"] == 1


def test_engine_marks_incomplete_model_window_coverage_as_partial(monkeypatch):
    monkeypatch.setattr(uae.football_sequence_intelligence, "normalise_sequence_analysis",
                        lambda raw, plan: {"coverage_complete": False, "metrics": {}, "sequences": []})
    monkeypatch.setattr(uae.canonical_event_resolver, "resolve_canonical_events",
                        lambda sa, sg, auth: {"status": "empty", "events": [], "metrics": {}})
    monkeypatch.setattr(uae.canonical_output_authority, "build_ledger_compat",
                        lambda c, coverage_complete=False: {})
    monkeypatch.setattr(uae.canonical_output_authority, "project_timeline", lambda c: [])
    monkeypatch.setattr(uae.canonical_output_authority, "build_event_native_evidence", lambda c: [])
    out = uae.finalise_analysis({}, {"sequence_plan": {}, "scene_graph": {}, "authority": {}})
    assert out["status"] == "partial_coverage"
    assert out["metrics"]["coverage_complete"] is False


def test_engine_apply_result_to_report_delegates_only_canonical_truth(monkeypatch):
    canonical = {"events": [{"event_id": "e1"}]}; sequence = {"coverage_complete": True}
    result = {"canonical_events": canonical, "sequence_analysis": sequence}
    called = {}

    def apply(full, c, s):
        called.update(c=c, s=s)
        full["action_timeline"] = [{"event_id": "e1"}]
        return full
    monkeypatch.setattr(uae.canonical_output_authority, "apply_to_report", apply)
    full = {"action_timeline": [{"event_id": "legacy"}]}
    out = uae.apply_result_to_report(full, result)
    assert called == {"c": canonical, "s": sequence}
    assert out["action_timeline"] == [{"event_id": "e1"}]


def test_persistence_payload_contains_authoritative_layers_not_prompt_text():
    result = {
        "status": "ok", "identity_authority": {"a": 1}, "scene_graph": {"b": 2},
        "sequence_plan": {"c": 3}, "sequence_analysis": {"d": 4},
        "canonical_events": {"e": 5}, "event_ledger": {"f": 6},
        "metrics": {"g": 7}, "production_track": {"points": []},
        "event_track_source": "UNIFIED", "analysis_prompt": "SHOULD_NOT_PERSIST",
    }
    p = uae.persistence_payload(result)
    assert p["canonical_events"] == {"e": 5}
    assert p["unified_event_track_source"] == "UNIFIED"
    assert "analysis_prompt" not in p


def test_prepare_does_not_mutate_fix04_identity_or_anchor_inputs(monkeypatch):
    fix = {"points": [{"t": 1.0, "x": .1, "y": .2, "w": .1, "h": .3}]}
    tl = {"target_points": [{"media_ms": 1000, "box": {"x": .1, "y": .2, "w": .1, "h": .3}}]}
    anchors = [{"t": 1.0, "box": {"x": .1, "y": .2, "w": .1, "h": .3}}]
    before = copy.deepcopy((fix, tl, anchors))
    monkeypatch.setattr(uae.unified_event_bridge, "build_identity_bundle",
                        lambda **kw: {"authority": {}, "identity_context": {}})
    monkeypatch.setattr(uae.football_scene_graph, "build_scene_graph", lambda video, auth: {"frames": []})
    monkeypatch.setattr(uae.football_sequence_intelligence, "build_sequence_plan",
                        lambda g: {"analysis_windows": [], "refinement_windows": []})
    monkeypatch.setattr(uae.football_sequence_intelligence, "build_analysis_prompt", lambda p, pd, ic: "")
    monkeypatch.setattr(uae.unified_identity_authority, "to_production_track", lambda a: {"points": []})
    monkeypatch.setattr(uae.unified_event_bridge, "choose_event_track",
                        lambda b, fallback_fix04_track=None: ({"points": []}, "FIX04_FALLBACK"))
    uae.prepare_analysis(video_path="v", fix04_track=fix, identity_timeline=tl, anchors=anchors)
    assert (fix, tl, anchors) == before
