"""FIX09B.2 — high-recall sequence planning + result-contract tests."""
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

import football_sequence_intelligence as fsi  # noqa: E402


TARGET_BOX = {"x": 0.10, "y": 0.20, "w": 0.10, "h": 0.30}
OTHER_BOX = {"x": 0.55, "y": 0.20, "w": 0.10, "h": 0.30}


def frame(ms, *, scene="scene_001", target_status="VERIFIED", target_id="p001",
          candidates=None, ball_box=None, holder=None, relation="LOOSE_OR_IN_FLIGHT",
          players=None, proof=True):
    plist = list(players or [
        {"media_ms": ms, "scene_id": scene, "local_track_id": "p001",
         "box": dict(TARGET_BOX), "confidence": .9, "team": "target_team",
         "global_target_candidate": True, "global_target_verified": target_id == "p001"},
        {"media_ms": ms, "scene_id": scene, "local_track_id": "p002",
         "box": dict(OTHER_BOX), "confidence": .9, "team": "opponent",
         "global_target_candidate": False, "global_target_verified": False},
    ])
    cands = list(candidates if candidates is not None else ([target_id] if target_id else []))
    return {
        "media_ms": ms,
        "scene_id": scene,
        "players": plist,
        "global_target": {
            "status": target_status,
            "local_track_id": target_id if target_status == "VERIFIED" else None,
            "candidate_local_track_ids": cands,
            "identity_strength": "GLOBAL",
            "proof_eligible": proof,
        },
        "ball": ({"media_ms": ms, "box": dict(ball_box), "confidence": .8,
                  "state": "DETECTED"} if ball_box else None),
        "ball_state": "DETECTED" if ball_box else "MISSING",
        "ball_candidates": [],
        "possession": {
            "status": "LIKELY" if holder else ("NO_BALL" if not ball_box else "NONE"),
            "holder_local_track_id": holder,
            "candidate_local_track_ids": [holder] if holder else [],
            "target_relation": relation,
        },
    }


def graph(frames, scenes=None):
    if scenes is None:
        by_scene = {}
        for f in frames:
            by_scene.setdefault(f["scene_id"], []).append(f["media_ms"])
        scenes = [{"scene_id": sid, "start_ms": min(ms), "end_ms": max(ms)}
                  for sid, ms in by_scene.items()]
    return {
        "version": 1, "status": "ok", "global_target_id": "GLOBAL_TARGET",
        "timebase": "canonical_media_ms", "scenes": scenes,
        "frames": frames, "player_points": [], "ball_points": [], "metrics": {},
    }


def ball_near_target():
    return {"x": .145, "y": .485, "w": .02, "h": .02}


def test_b201_every_target_active_span_gets_broad_sequence_coverage_even_without_ball():
    frames = [frame(ms) for ms in (0, 250, 500, 750, 1000)]
    plan = fsi.build_sequence_plan(graph(frames))
    assert plan["status"] == "ok"
    assert plan["analysis_windows"]
    w = plan["analysis_windows"][0]
    assert w["start_ms"] == 0
    assert w["end_ms"] == 1000
    assert w["coverage_reason"] == "GLOBAL_TARGET_ACTIVE"


def test_b202_hard_scene_boundaries_are_never_crossed_by_analysis_windows():
    frames = [
        frame(0, scene="scene_001"), frame(500, scene="scene_001"),
        frame(1000, scene="scene_002"), frame(1500, scene="scene_002"),
    ]
    scenes = [
        {"scene_id": "scene_001", "start_ms": 0, "end_ms": 500},
        {"scene_id": "scene_002", "start_ms": 1000, "end_ms": 1500},
    ]
    plan = fsi.build_sequence_plan(graph(frames, scenes))
    assert len(plan["analysis_windows"]) == 2
    assert {(w["scene_id"], w["start_ms"], w["end_ms"]) for w in plan["analysis_windows"]} == {
        ("scene_001", 0, 500), ("scene_002", 1000, 1500)
    }


def test_b203_no_target_coverage_is_explicit_not_fabricated():
    f = frame(0, target_status="UNRESOLVED", target_id=None, candidates=[])
    plan = fsi.build_sequence_plan(graph([f]))
    assert plan["status"] == "no_target_coverage"
    assert plan["analysis_windows"] == []


def test_b204_target_possession_and_ball_proximity_request_dense_refinement():
    frames = [
        frame(0),
        frame(250, ball_box=ball_near_target(), holder="p001",
              relation="TARGET_LIKELY_POSSESSION"),
        frame(500, ball_box=ball_near_target(), holder="p001",
              relation="TARGET_LIKELY_POSSESSION"),
    ]
    plan = fsi.build_sequence_plan(graph(frames))
    assert plan["refinement_windows"]
    reasons = set().union(*(set(r["reasons"]) for r in plan["refinement_windows"]))
    assert "TARGET_POSSESSION" in reasons
    assert "BALL_NEAR_TARGET" in reasons
    assert all(r["review_hz"] == fsi.HIGH_REVIEW_HZ for r in plan["refinement_windows"])


def test_b205_identity_ambiguity_is_a_refinement_trigger_not_an_identity_guess():
    near2 = {"x": .12, "y": .20, "w": .10, "h": .30}
    players = [
        {"media_ms": 0, "scene_id": "scene_001", "local_track_id": "p001",
         "box": dict(TARGET_BOX), "global_target_candidate": True, "global_target_verified": False},
        {"media_ms": 0, "scene_id": "scene_001", "local_track_id": "p002",
         "box": near2, "global_target_candidate": True, "global_target_verified": False},
    ]
    f = frame(0, target_status="HYPOTHESES", target_id=None,
              candidates=["p001", "p002"], players=players, proof=False)
    plan = fsi.build_sequence_plan(graph([f]))
    assert plan["analysis_windows"], "hypotheses remain in broad recall coverage"
    assert any("IDENTITY_AMBIGUITY" in r["reasons"] for r in plan["refinement_windows"])


def test_b206_long_visible_span_splits_into_overlapping_bounded_windows():
    frames = [frame(ms) for ms in range(0, 21001, 1000)]
    plan = fsi.build_sequence_plan(graph(frames))
    assert len(plan["analysis_windows"]) >= 3
    assert all(w["end_ms"] - w["start_ms"] <= fsi.MAX_ANALYSIS_WINDOW_MS
               for w in plan["analysis_windows"])
    assert plan["analysis_windows"][1]["start_ms"] < plan["analysis_windows"][0]["end_ms"]


def test_b207_prompt_requires_complete_sequences_visible_evidence_and_no_action_cap():
    plan = fsi.build_sequence_plan(graph([frame(0), frame(500)]))
    prompt = fsi.build_analysis_prompt(plan, {"player_name": "Target", "position": "LW"}, {})
    assert "EVERY clearly observable football contribution" in prompt
    assert "Do not cap the number of actions" in prompt
    assert "Never select a player because he performs an interesting action" in prompt
    assert "evidence_ms" in prompt
    assert "A cut breaks the causal chain" in prompt


def _plan_one():
    return fsi.build_sequence_plan(graph([frame(0), frame(500), frame(1000)]))


def _action(window, **overrides):
    base = {
        "action_id": "a1", "kind": "SHOT",
        "start_ms": window["start_ms"], "contact_ms": 500, "end_ms": window["end_ms"],
        "target_status": "VERIFIED", "actor_local_track_id": "p001",
        "actor_candidate_local_track_ids": ["p001"], "actor_box": dict(TARGET_BOX),
        "actor_evidence": [{"media_ms": 500, "box": dict(TARGET_BOX), "visibility": "VISIBLE"}],
        "evidence_ms": [500], "foot": "RIGHT",
        "pressure": {"level": "MEDIUM", "nearby_players": 1},
        "details": ["changes direction before the strike"],
        "outcome": "SAVED", "outcome_visible": True,
        "causal_chain": {"target_contact_ms": 500, "receiver_local_track_id": None,
                         "receiver_ms": None, "teammate_shot_ms": None,
                         "goal_outcome_ms": None, "continuous_visible_sequence": True},
        "contact_visibility": "VISIBLE", "duplicate_of": None,
    }
    base.update(overrides)
    return base


def test_b208_valid_sequence_action_survives_structured_normalisation():
    plan = _plan_one(); w = plan["analysis_windows"][0]
    raw = {"sequences": [{"sequence_id": w["sequence_id"], "scene_id": w["scene_id"],
                           "summary": "target shoots", "actions": [_action(w)]}],
           "coverage": [{"sequence_id": w["sequence_id"], "reviewed": True,
                         "target_seen": True, "actions_found": 1}]}
    out = fsi.normalise_sequence_analysis(raw, plan)
    assert out["coverage_complete"] is True
    assert out["metrics"]["actions_total"] == 1
    a = out["sequences"][0]["actions"][0]
    assert a["kind"] == "SHOT" and a["outcome"] == "SAVED" and a["foot"] == "RIGHT"


def test_b209_timestamp_outside_supplied_same_scene_window_is_rejected_not_clipped():
    plan = _plan_one(); w = plan["analysis_windows"][0]
    bad = _action(w, start_ms=max(0, w["start_ms"] - 1), end_ms=w["end_ms"] + 1)
    raw = {"sequences": [{"sequence_id": w["sequence_id"], "scene_id": w["scene_id"],
                           "actions": [bad]}], "coverage": []}
    out = fsi.normalise_sequence_analysis(raw, plan)
    assert out["metrics"]["actions_total"] == 0


def test_b210_action_without_any_visible_evidence_is_not_a_fact():
    plan = _plan_one(); w = plan["analysis_windows"][0]
    bad = _action(w, evidence_ms=[], actor_evidence=[])
    raw = {"sequences": [{"sequence_id": w["sequence_id"], "scene_id": w["scene_id"],
                           "actions": [bad]}]}
    out = fsi.normalise_sequence_analysis(raw, plan)
    assert out["metrics"]["actions_total"] == 0


def test_b211_occluded_contact_can_survive_when_adjacent_same_action_evidence_exists():
    plan = _plan_one(); w = plan["analysis_windows"][0]
    a = _action(
        w, contact_visibility="OCCLUDED", actor_box=None,
        actor_evidence=[{"media_ms": 450, "box": dict(TARGET_BOX), "visibility": "VISIBLE"},
                        {"media_ms": 550, "box": dict(TARGET_BOX), "visibility": "VISIBLE"}],
        evidence_ms=[450, 550],
    )
    raw = {"sequences": [{"sequence_id": w["sequence_id"], "scene_id": w["scene_id"],
                           "actions": [a]}]}
    out = fsi.normalise_sequence_analysis(raw, plan)
    got = out["sequences"][0]["actions"][0]
    assert got["contact_visibility"] == "OCCLUDED"
    assert got["actor_box"] is None
    assert len(got["actor_evidence"]) == 2


def test_b212_unknown_sequence_or_wrong_scene_cannot_enter_analysis_truth():
    plan = _plan_one(); w = plan["analysis_windows"][0]
    raw = {"sequences": [
        {"sequence_id": "invented", "scene_id": w["scene_id"], "actions": [_action(w)]},
        {"sequence_id": w["sequence_id"], "scene_id": "wrong_scene", "actions": [_action(w)]},
    ]}
    out = fsi.normalise_sequence_analysis(raw, plan)
    assert out["sequences"] == []


def test_b213_coverage_is_complete_only_when_every_planned_window_was_reviewed():
    frames = [frame(ms) for ms in range(0, 16001, 1000)]
    plan = fsi.build_sequence_plan(graph(frames))
    assert len(plan["analysis_windows"]) >= 2
    sid = plan["analysis_windows"][0]["sequence_id"]
    out = fsi.normalise_sequence_analysis({
        "sequences": [],
        "coverage": [{"sequence_id": sid, "reviewed": True, "target_seen": True, "actions_found": 0}],
    }, plan)
    assert out["coverage_complete"] is False


def test_b214_duplicate_action_ids_are_not_counted_twice():
    plan = _plan_one(); w = plan["analysis_windows"][0]
    a1 = _action(w)
    a2 = _action(w, kind="PASS")
    raw = {"sequences": [{"sequence_id": w["sequence_id"], "scene_id": w["scene_id"],
                           "actions": [a1, a2]}]}
    out = fsi.normalise_sequence_analysis(raw, plan)
    assert out["metrics"]["actions_total"] == 1


def test_b215_causal_timestamps_outside_window_are_removed_not_rewritten():
    plan = _plan_one(); w = plan["analysis_windows"][0]
    chain = {"target_contact_ms": 500, "receiver_local_track_id": "p003",
             "receiver_ms": 700, "teammate_shot_ms": w["end_ms"] + 1000,
             "goal_outcome_ms": w["end_ms"] + 1200, "continuous_visible_sequence": True}
    a = _action(w, kind="PASS", outcome="TEAMMATE_GOAL", causal_chain=chain)
    raw = {"sequences": [{"sequence_id": w["sequence_id"], "scene_id": w["scene_id"],
                           "actions": [a]}]}
    out = fsi.normalise_sequence_analysis(raw, plan)
    got = out["sequences"][0]["actions"][0]["causal_chain"]
    assert got["target_contact_ms"] == 500 and got["receiver_ms"] == 700
    assert got["teammate_shot_ms"] is None and got["goal_outcome_ms"] is None


def test_b216_reviewed_coverage_cannot_hide_an_omitted_sequence_row():
    plan = _plan_one(); w = plan["analysis_windows"][0]
    out = fsi.normalise_sequence_analysis({
        "sequences": [],
        "coverage": [{"sequence_id": w["sequence_id"], "reviewed": True,
                      "target_seen": False, "actions_found": 0}],
    }, plan)
    assert out["coverage_complete"] is False
    assert out["missing_sequence_ids"] == [w["sequence_id"]]
    assert out["coverage"][0]["contract_complete"] is False


def test_b217_actions_found_must_match_actions_that_survive_normalisation():
    plan = _plan_one(); w = plan["analysis_windows"][0]
    malformed = _action(w, evidence_ms=[], actor_evidence=[])
    out = fsi.normalise_sequence_analysis({
        "sequences": [{"sequence_id": w["sequence_id"], "scene_id": w["scene_id"],
                       "actions": [malformed]}],
        "coverage": [{"sequence_id": w["sequence_id"], "reviewed": True,
                      "target_seen": True, "actions_found": 1}],
    }, plan)
    assert out["coverage_complete"] is False
    assert out["action_count_mismatch_ids"] == [w["sequence_id"]]
    assert out["coverage"][0]["normalised_actions"] == 0


def test_b218_duplicate_contract_rows_are_incomplete_not_double_truth():
    plan = _plan_one(); w = plan["analysis_windows"][0]
    seq = {"sequence_id": w["sequence_id"], "scene_id": w["scene_id"], "actions": []}
    cov = {"sequence_id": w["sequence_id"], "reviewed": True,
           "target_seen": False, "actions_found": 0}
    out = fsi.normalise_sequence_analysis(
        {"sequences": [seq, dict(seq)], "coverage": [cov, dict(cov)]}, plan)
    assert out["coverage_complete"] is False
    assert out["coverage"][0]["sequence_rows"] == 2
    assert out["coverage"][0]["coverage_rows"] == 2


def test_b219_retry_subset_keeps_only_original_incomplete_windows_and_links():
    frames = [frame(ms) for ms in range(0, 16001, 1000)]
    plan = fsi.build_sequence_plan(graph(frames))
    assert len(plan["analysis_windows"]) >= 2
    wanted = plan["analysis_windows"][1]["sequence_id"]
    retry = fsi.subset_sequence_plan(plan, [wanted, "invented"])
    assert [w["sequence_id"] for w in retry["analysis_windows"]] == [wanted]
    assert all(r["sequence_ids"] == [wanted] for r in retry["refinement_windows"])
    assert retry["metrics"]["retry_subset"] is True


def test_b220_attempt_merge_replaces_only_retried_window_with_latest_rows():
    first = {
        "sequences": [
            {"sequence_id": "s1", "scene_id": "scene_001", "actions": []},
            {"sequence_id": "s2", "scene_id": "scene_001", "actions": []},
        ],
        "coverage": [
            {"sequence_id": "s1", "reviewed": True, "actions_found": 0},
            {"sequence_id": "s2", "reviewed": False, "actions_found": 0},
        ],
    }
    retry = {
        "sequences": [{"sequence_id": "s2", "scene_id": "scene_001",
                       "summary": "retried", "actions": []}],
        "coverage": [{"sequence_id": "s2", "reviewed": True, "actions_found": 0}],
    }
    merged = fsi.merge_raw_sequence_results([first, retry])
    assert merged["attempts"] == 2
    assert {s["sequence_id"] for s in merged["sequences"]} == {"s1", "s2"}
    assert next(s for s in merged["sequences"] if s["sequence_id"] == "s2")["summary"] == "retried"
    assert next(c for c in merged["coverage"] if c["sequence_id"] == "s2")["reviewed"] is True


def test_b221_attempt_merge_preserves_latest_duplicate_rows_for_contract_rejection():
    duplicate = {"sequence_id": "s1", "scene_id": "scene_001", "actions": []}
    cov = {"sequence_id": "s1", "reviewed": True, "actions_found": 0}
    merged = fsi.merge_raw_sequence_results([{
        "sequences": [duplicate, dict(duplicate)],
        "coverage": [cov, dict(cov)],
    }])
    assert len(merged["sequences"]) == 2
    assert len(merged["coverage"]) == 2
