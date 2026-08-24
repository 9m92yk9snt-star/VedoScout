from __future__ import annotations
import copy
import numpy as np
import fix10a_vision_providers as fvp
import physical_match_reconstruction as pmr


def _box():
    return {"x": .25, "y": .20, "w": .20, "h": .45}


def _frame(ms, track="p009"):
    return {
        "media_ms": ms, "scene_id": "s1", "used_fallback": False,
        "time_authority": "ACTUAL_MEDIA_PTS", "global_target": {},
        "players": [{"local_track_id": track, "box": _box(), "association_state": "VERIFIED_LOCAL"}],
        "ball_candidates": [], "a7_ball_support_candidates": [],
    }


def test_provider_uses_verified_a7_actor_without_touch_graph(monkeypatch):
    image = np.zeros((120, 160, 3), dtype=np.uint8)
    monkeypatch.setattr(fvp, "_read_frames", lambda _v, requested: {int(ms):(int(ms),image) for ms in requested})
    async def fake_role(*_a):
        return {"role":"GOALKEEPER","confidence":"high","reason":"visible gloves and keeper kit"}
    monkeypatch.setattr(fvp, "read_visible_player_role", fake_role)
    bundle = fvp.build_shadow_providers("key", "session", "video.mp4")
    evidence = [_frame(ms) for ms in (1200, 1400, 1600)]
    interventions = [{"status":"VERIFIED","proof_eligible":True,"player_track_id":"p009","media_ms":1400}]
    out = bundle.role_evidence_provider("video.mp4", {"scene_id":"s1"}, [], {"touches":[]}, evidence, interventions)
    assert set(out) == {"p009"}
    assert out["p009"]["status"] == "VERIFIED"
    assert out["p009"]["role"] == "GOALKEEPER"


def test_unverified_or_nonproof_intervention_cannot_trigger_role_review(monkeypatch):
    called = []
    monkeypatch.setattr(fvp, "_read_frames", lambda *_a: called.append(True) or {})
    bundle = fvp.build_shadow_providers("key", "session", "video.mp4")
    evidence = [_frame(ms) for ms in (1200, 1400, 1600)]
    bad = [
        {"status":"UNRESOLVED","proof_eligible":True,"player_track_id":"p009","media_ms":1400},
        {"status":"VERIFIED","proof_eligible":False,"player_track_id":"p010","media_ms":1400},
    ]
    out = bundle.role_evidence_provider("video.mp4", {"scene_id":"s1"}, [], {"touches":[]}, evidence, bad)
    assert out == {}
    assert called == []


def _patch_minimal(monkeypatch):
    window = {"dense_window_id":"d1","scene_id":"s1","start_ms":900,"end_ms":1800}
    dense = [_frame(1200), _frame(1400), _frame(1600)]
    monkeypatch.setattr(pmr.dense_replay, "select_critical_windows", lambda *_a: [window])
    monkeypatch.setattr(pmr.dense_replay, "iter_dense_frames", lambda *_a, **_k: iter([]))
    monkeypatch.setattr(pmr.dense_track_refinement, "refine_window", lambda *_a, **_k: {"frames": copy.deepcopy(dense)})
    monkeypatch.setattr(pmr.ball_trajectory, "reconstruct_ball_trajectory", lambda *_a: [])
    monkeypatch.setattr(pmr.ball_contact_engine, "detect_contact_candidates", lambda *_a: [])
    monkeypatch.setattr(pmr.ball_contact_engine, "resolve_contacts", lambda *_a: {"contacts":[],"accepted":[],"unresolved":[],"rejected":[]})
    monkeypatch.setattr(pmr.short_occlusion_contact_recovery, "recover_short_occlusion_contacts", lambda *_a, **_k: {"verified":[],"metrics":{"verified":0}})
    monkeypatch.setattr(pmr.short_occlusion_contact_recovery, "apply_recovered_contacts", lambda c,_r: c)
    monkeypatch.setattr(pmr.touch_graph, "build_touch_graph", lambda *_a: {"touches":[]})
    monkeypatch.setattr(pmr.jersey_consensus, "select_jersey_review_requests", lambda *_a: [])
    monkeypatch.setattr(pmr.jersey_consensus, "apply_jersey_consensus", lambda frames,touches,_votes: {"window_evidence":frames,"touch_graph":touches,"consensus_by_track":{}})
    strike = {"strike_id":"s1","status":"VERIFIED_PHYSICAL_RELEASE","media_ms":1000,"scene_id":"s1","player_track_id":"p015"}
    monkeypatch.setattr(pmr.shot_outcome_engine, "find_strike_releases", lambda *_a: [copy.deepcopy(strike)])
    monkeypatch.setattr(pmr.post_strike_intervention, "detect_post_strike_intervention", lambda *_a: {"status":"VERIFIED","proof_eligible":True,"player_track_id":"p009","media_ms":1400})
    monkeypatch.setattr(pmr.shot_outcome_engine, "reconstruct_post_strike_outcome", lambda *_a, **_k: {"physical_outcome":"PLAYER_INTERVENTION","goal_plane_crossing":{"status":"UNRESOLVED"}})
    monkeypatch.setattr(pmr.fix10a_goal_direction, "apply_direction_gate", lambda out,*_a: out)
    monkeypatch.setattr(pmr.fix10a_ball_proof_gate, "apply_ball_proof_gate", lambda out,*_a: out)
    return window


def test_orchestrator_hands_verified_a7_actor_to_six_arg_role_provider(monkeypatch):
    _patch_minimal(monkeypatch)
    seen = {}
    def role_provider(_video,_window,_strikes,_touches,_evidence,interventions):
        seen["interventions"] = interventions
        return {"p009":{"status":"VERIFIED","role":"GOALKEEPER","reason":"pixels"}}
    def apply(out,a7,roles):
        seen["roles"] = roles; seen["a7"] = a7; return out
    monkeypatch.setattr(pmr.post_strike_intervention, "apply_intervention_evidence", apply)
    out = pmr.reconstruct_physical_match("video.mp4", {"analysis_windows":[]}, {"sequences":[]}, {}, {}, role_evidence_provider=role_provider)
    assert seen["interventions"][0]["player_track_id"] == "p009"
    assert seen["roles"]["p009"]["role"] == "GOALKEEPER"
    assert seen["a7"]["player_track_id"] == "p009"
    assert out["windows"][0]["a7_verified_interventions"] == 1
    assert "canonical_events" not in out


def test_old_five_arg_role_provider_still_supported(monkeypatch):
    _patch_minimal(monkeypatch)
    called = []
    def role_provider(_video,_window,_strikes,_touches,_evidence):
        called.append(True)
        return {"p009":{"status":"VERIFIED","role":"GOALKEEPER","reason":"pixels"}}
    monkeypatch.setattr(pmr.post_strike_intervention, "apply_intervention_evidence", lambda out,*_a: out)
    pmr.reconstruct_physical_match("video.mp4", {"analysis_windows":[]}, {"sequences":[]}, {}, {}, role_evidence_provider=role_provider)
    assert called == [True]
