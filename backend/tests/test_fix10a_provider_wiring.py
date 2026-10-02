"""FIX10A provider wiring / authority-boundary regression tests."""
from __future__ import annotations

import sys
import copy
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

import fix10a_runtime as fxr  # noqa: E402
import physical_match_reconstruction as pmr  # noqa: E402


def test_pw01_role_provider_result_reaches_a7_without_canonical_output(monkeypatch):
    window = {"dense_window_id": "d1", "scene_id": "s1", "start_ms": 900, "end_ms": 1400}
    dense = [{
        "media_ms": 1000, "scene_id": "s1", "used_fallback": False,
        "time_authority": "ACTUAL_MEDIA_PTS", "players": [], "global_target": {},
    }]
    monkeypatch.setattr(pmr.dense_replay, "select_critical_windows", lambda *_a: [window])
    monkeypatch.setattr(pmr.dense_replay, "iter_dense_frames", lambda *_a, **_k: iter([]))
    monkeypatch.setattr(pmr.dense_track_refinement, "refine_window", lambda *_a, **_k: {"frames": dense})
    monkeypatch.setattr(pmr.ball_trajectory, "reconstruct_ball_trajectory", lambda *_a: [])
    monkeypatch.setattr(pmr.ball_contact_engine, "detect_contact_candidates", lambda *_a: [])
    monkeypatch.setattr(pmr.ball_contact_engine, "resolve_contacts", lambda *_a: {"contacts": [], "accepted": [], "unresolved": []})
    monkeypatch.setattr(pmr.touch_graph, "build_touch_graph", lambda *_a: {"touches": []})
    monkeypatch.setattr(pmr.jersey_consensus, "select_jersey_review_requests", lambda *_a: [])
    monkeypatch.setattr(
        pmr.jersey_consensus, "apply_jersey_consensus",
        lambda frames, touches, _votes: {"window_evidence": frames, "touch_graph": touches, "consensus_by_track": {}},
    )
    strike = {
        "strike_id": "s", "media_ms": 1000, "scene_id": "s1", "player_track_id": "p015",
        "active_ball_anchor": {
            "media_ms": 1010, "state": "MEASURED_REACQUISITION",
            "box": {"x": .5, "y": .5, "w": .02, "h": .02},
            "proof_eligible": True, "time_authority": "ACTUAL_MEDIA_PTS",
            "used_fallback": False,
        },
    }
    monkeypatch.setattr(pmr.shot_outcome_engine, "find_strike_releases", lambda *_a: [strike])
    captured = {}
    shot_trajectory = [{"media_ms": 1010, "state": "MEASURED", "box": strike["active_ball_anchor"]["box"]}]
    monkeypatch.setattr(
        pmr.ball_trajectory, "reconstruct_ball_trajectory_from_release_anchor",
        lambda *_a: copy.deepcopy(shot_trajectory),
    )

    def fake_intervention(_strike, _frames, trajectory):
        captured["intervention_trajectory"] = trajectory
        return {"status": "NONE", "proof_eligible": False}

    monkeypatch.setattr(
        pmr.post_strike_intervention, "detect_post_strike_intervention", fake_intervention
    )

    def fake_outcome(_strike, trajectory, _touches, **kwargs):
        captured.update(kwargs)
        captured["outcome_trajectory"] = trajectory
        return {"physical_outcome": "PLAYER_INTERVENTION", "goal_plane_crossing": {"status": "UNRESOLVED"}}

    monkeypatch.setattr(pmr.shot_outcome_engine, "reconstruct_post_strike_outcome", fake_outcome)

    def role_provider(video_path, got_window, strikes, touch_graph, window_evidence):
        assert video_path == "video.mp4"
        assert got_window["dense_window_id"] == "d1"
        assert strikes[0]["strike_id"] == "s"
        return {"p001": {"status": "VERIFIED", "role": "GOALKEEPER", "reason": "pixels"}}

    def fake_direction(outcome, trajectory, *_a):
        captured["direction_trajectory"] = trajectory
        return outcome

    def fake_ball_proof(outcome, trajectory, *_a):
        captured["proof_trajectory"] = trajectory
        return outcome

    monkeypatch.setattr(pmr.fix10a_goal_direction, "apply_direction_gate", fake_direction)
    monkeypatch.setattr(pmr.fix10a_ball_proof_gate, "apply_ball_proof_gate", fake_ball_proof)
    out = pmr.reconstruct_physical_match(
        "video.mp4", {"analysis_windows": []}, {"sequences": []}, {}, {},
        role_evidence_provider=role_provider,
    )
    assert captured["role_evidence"]["p001"]["role"] == "GOALKEEPER"
    assert captured["intervention_trajectory"] == shot_trajectory
    assert captured["outcome_trajectory"] == shot_trajectory
    assert captured["direction_trajectory"] == shot_trajectory
    assert captured["proof_trajectory"] == shot_trajectory
    assert out["windows"][0]["role_evidence_tracks"] == 1
    assert "canonical_events" not in out
    assert "verified_stats" not in out


class _Reports:
    def __init__(self):
        self.calls = []

    async def update_one(self, query, update):
        self.calls.append((query, update))


class _DB:
    def __init__(self):
        self.reports = _Reports()


async def test_pw02_production_runtime_autowires_supporting_callbacks(monkeypatch):
    monkeypatch.setenv(fxr.SUPPORT_VISION_FLAG, "1")
    monkeypatch.setenv("EMERGENT_LLM_KEY", "test-key")

    def jersey(*_a, **_k):
        return {}

    def goal(*_a, **_k):
        return None

    def role(*_a, **_k):
        return {}

    class _Bundle:
        jersey_vote_provider = staticmethod(jersey)
        goal_geometry_provider = staticmethod(goal)
        role_evidence_provider = staticmethod(role)

    built = {}

    def fake_build(api_key, session_prefix, video_path):
        built.update({"api_key": api_key, "session_prefix": session_prefix, "video_path": video_path})
        return _Bundle()

    monkeypatch.setattr(fxr.fix10a_vision_providers, "build_shadow_providers", fake_build)
    captured = {}

    def fake_reconstruct(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return {
            "version": 1, "status": "ok", "timebase": "canonical_media_ms",
            "source_role": "CANONICAL_WEB_VIDEO", "source_video": {},
            "windows": [], "trace_summaries": [], "traces": [],
            "unresolved_reasons": [], "metrics": {},
        }

    monkeypatch.setattr(fxr.physical_match_reconstruction, "reconstruct_physical_match", fake_reconstruct)
    monkeypatch.setattr(
        fxr.fix10b_runtime,
        "build_candidate",
        lambda unified, physical: {
            "version": 2,
            "enabled": True,
            "mode": "production",
            "summary": {},
            "unified_result": dict(unified),
        },
    )
    unified = {
        "status": "ok", "sequence_plan": {},
        "sequence_analysis": {"coverage_complete": True, "sequences": []},
        "scene_graph": {}, "identity_authority": {},
    }
    db = _DB()
    out = await fxr.run(report_id="r1", video_path="video.mp4", unified_result=unified, db=db)
    assert built["api_key"] == "test-key"
    assert built["video_path"] == "video.mp4"
    assert captured["args"][5] is jersey
    wrapped_goal = captured["kwargs"]["goal_geometry_provider"]
    assert isinstance(wrapped_goal, fxr.fix10a_goal_direction.GoalDirectionProvider)
    assert wrapped_goal.base_provider is goal
    assert captured["kwargs"]["role_evidence_provider"] is role
    assert out["fix10a_supporting_vision"]["enabled"] is True
    assert out["fix10a_canonical_authority"] is False
    assert out["mode"] == "production"
    persisted = db.reports.calls[-1][1]["$set"]
    assert persisted["fix10a_canonical_authority"] is False
    assert persisted["fix10a_mode"] == "production"
    assert "canonical_events" not in persisted
