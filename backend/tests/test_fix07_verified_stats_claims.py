"""FIX 07 — VERIFIED STATS & CLAIM RECONCILIATION (V01–V50).

Deterministic only: synthetic dictionaries, mocked verifier seam. ZERO live
LLM/verifier/network calls. Verified events are the only statistical
authority; report text must agree with verified_stats.
"""
import asyncio
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

import server  # noqa: E402
import verified_stats as vstats  # noqa: E402
from evidence_authority import attach_event_evidence_authority  # noqa: E402


def _ev(ts, et, at, res, vis=True, **kw):
    return {"timestamp": ts, "title": kw.pop("title", "Event"),
            "description": kw.pop("description", "Seen action."),
            "action_type": at.lower(), "cross_verified": kw.pop("cross_verified", True),
            "canonical_event_type": et, "canonical_action_type": at,
            "canonical_result": res, "outcome_visible": vis, **kw}


def _goal(ts="01:10", **kw):
    return _ev(ts, "GOAL", "SHOT", "SCORED", True, **kw)


def _assist(ts="02:10", at="PASS", **kw):
    return _ev(ts, "ASSIST", at, "TEAMMATE_SCORED", True, **kw)


def _stats(events, scan=None):
    full = {"action_timeline": list(events)}
    full = attach_event_evidence_authority(full)
    return vstats.build_verified_stats(full, scan), full


# ------------------------------------------------- V01–V08 scoring gates

def test_V01_basic_scoring():
    vs, _ = _stats([_goal(), _assist("02:00"), _assist("03:00"), _assist("04:00", at="CROSS")])
    assert vs["goals"] == 1 and vs["assists"] == 3


def test_V02_unverified_goal_not_counted():
    vs, _ = _stats([_goal(cross_verified=False)])
    assert vs["goals"] == 0 and vs["shots"] == 0


def test_V03_shot_outcome_not_visible():
    vs, _ = _stats([_ev("01:00", "SHOT", "SHOT", "OUTCOME_NOT_VISIBLE", False)])
    assert vs["shots"] == 1 and vs["goals"] == 0


def test_V04_goal_hard_gate():
    vs, _ = _stats([_ev("01:00", "GOAL", "SHOT", "SAVED", True),
                    _ev("02:00", "GOAL", "SHOT", "SCORED", False)])
    assert vs["goals"] == 0
    # normalisation also demotes at the source
    et, at, res, vis = vstats.normalize_canonical("GOAL", "SHOT", "SCORED", False)
    assert et == "SHOT" and res == "OUTCOME_NOT_VISIBLE" and vis is False


def test_V05_assist_hard_gate():
    vs, _ = _stats([_ev("01:00", "ASSIST", "PASS", "TEAMMATE_SHOT", True),
                    _ev("02:00", "ASSIST", "PASS", "TEAMMATE_SCORED", False)])
    assert vs["assists"] == 0
    et, at, res, vis = vstats.normalize_canonical("ASSIST", "PASS", "TEAMMATE_SCORED", False)
    assert et != "ASSIST"


def test_V06_goal_also_shot_once():
    vs, _ = _stats([_goal()])
    assert vs["goals"] == 1 and vs["shots"] == 1


def test_V07_assist_also_key_pass():
    vs, _ = _stats([_assist()])
    assert vs["assists"] == 1 and vs["key_passes"] == 1


def test_V08_shots_on_target():
    vs, _ = _stats([_goal("01:00"),
                    _ev("02:00", "SHOT", "SHOT", "SAVED", True),
                    _ev("03:00", "SHOT", "SHOT", "OFF_TARGET", True),
                    _ev("04:00", "SHOT", "SHOT", "BLOCKED", True)])
    assert vs["shots"] == 4 and vs["shots_on_target"] == 2


# ------------------------------------------------- V09–V20 counting rules

def test_V09_V10_pass_attempted_completed():
    vs, _ = _stats([_ev("01:00", "PASS", "PASS", "COMPLETED", True),
                    _ev("02:00", "PASS", "PASS", "INCOMPLETE", True)])
    assert vs["passes_attempted"] == 2 and vs["passes_completed"] == 1


def test_V11_assist_pass_completed():
    vs, _ = _stats([_assist()])
    assert vs["passes_attempted"] == 1 and vs["passes_completed"] == 1


def test_V12_cross_assist():
    vs, _ = _stats([_assist(at="CROSS")])
    assert vs["assists"] == 1
    assert vs["crosses_attempted"] == 1 and vs["crosses_completed"] == 1
    assert vs["passes_attempted"] == 0


def test_V13_key_pass():
    vs, _ = _stats([_ev("01:00", "KEY_PASS", "PASS", "TEAMMATE_SHOT", True)])
    assert vs["key_passes"] == 1
    assert vs["passes_attempted"] == 1 and vs["passes_completed"] == 1


def test_V14_V15_dribbles():
    vs, _ = _stats([_ev("01:00", "DRIBBLE", "DRIBBLE", "SUCCESS", True),
                    _ev("02:00", "DRIBBLE", "DRIBBLE", "FAILED", True)])
    assert vs["dribbles_attempted"] == 2 and vs["successful_dribbles"] == 1


def test_V16_duels():
    vs, _ = _stats([_ev("01:00", "DUEL", "DUEL", "WON", True),
                    _ev("02:00", "DUEL", "DUEL", "LOST", True),
                    _ev("03:00", "DUEL", "DUEL", "UNRESOLVED", False)])
    assert vs["duels_contested"] == 2 and vs["duels_won"] == 1


def test_V17_tackles():
    vs, _ = _stats([_ev("01:00", "TACKLE", "TACKLE", "WON", True),
                    _ev("02:00", "TACKLE", "TACKLE", "LOST", True)])
    assert vs["tackles_attempted"] == 2 and vs["tackles_won"] == 1


def test_V18_V19_interception_recovery():
    vs, _ = _stats([_ev("01:00", "INTERCEPTION", "INTERCEPTION", "POSSESSION_WON", True),
                    _ev("02:00", "RECOVERY", "RECOVERY", "POSSESSION_WON", True)])
    assert vs["interceptions"] == 1 and vs["recoveries"] == 1
    assert vs["defensive_actions"] == 2


def test_V20_pass_completion_pct():
    evs = [_ev(f"01:{i:02d}", "PASS", "PASS",
               "COMPLETED" if i < 8 else "INCOMPLETE", True) for i in range(10)]
    vs, _ = _stats(evs)
    assert vs["passes_attempted"] == 10 and vs["passes_completed"] == 8
    assert vs["pass_completion_pct"] == 80


# ---------------------------------------------- V21–V24 duplicate / junk

def test_V21_duplicate_event_id_counts_once():
    vs, _ = _stats([_goal(event_id="evt_dup"), _goal("01:20", event_id="evt_dup")])
    assert vs["goals"] == 1 and vs["shots"] == 1


def test_V22_exact_time_duplicate_counts_once():
    vs, _ = _stats([_goal(event_id="evt_a", event_start_ms=70000),
                    _goal(event_id="evt_b", event_start_ms=70000)])
    assert vs["goals"] == 1 and vs["shots"] == 1


def test_V23_no_fuzzy_dedup():
    vs, _ = _stats([_ev("01:10", "SHOT", "SHOT", "SAVED", True),
                    _ev("01:11", "SHOT", "SHOT", "SAVED", True)])
    assert vs["shots"] == 2, "nearby events were fuzzy-merged"


def test_V24_invalid_canonical_no_invented_stat():
    vs, _ = _stats([_ev("01:00", "UNCLASSIFIED", "UNKNOWN", "UNKNOWN", False)])
    assert vs["total_actions"] == 0
    assert all(vs[k] == 0 for k in ("goals", "assists", "shots", "passes_attempted"))


# ------------------------------------------- V25 match_stats authority

def test_V25_model_match_stats_contradiction():
    full = {"action_timeline": [_goal(), _assist("02:00"), _assist("03:00"),
                                _assist("04:00")],
            "match_stats": {"goals": 3, "assists": 0, "minutes_analysed": 12}}
    full = attach_event_evidence_authority(full)
    full = vstats.apply_verified_stats_authority(full)
    ms = full["match_stats"]
    assert ms["goals"] == 1 and ms["assists"] == 3
    assert ms["source"] == "verified_events"
    assert ms["minutes_analysed"] == 12


# ------------------------------------------- V26–V31 prose reconciliation

def _recon(full):
    full = attach_event_evidence_authority(full)
    return vstats.apply_verified_stats_authority(full)


def test_V26_executive_summary_goal_contradiction():
    full = _recon({"action_timeline": [_goal()],
                   "executive_summary": "A dominant display. Scored three goals. Strong engine."})
    assert "three goals" not in full["executive_summary"].lower()
    assert "dominant" in full["executive_summary"].lower()


def test_V27_hat_trick_contradiction():
    full = _recon({"action_timeline": [_goal()],
                   "final_summary": "A true hat-trick performance."})
    assert "hat" not in full["final_summary"].lower()
    assert full["final_summary"].strip(), "high-value field left empty"
    assert "Verified in this footage: 1 goal" in full["final_summary"]


def test_V28_brace_contradiction():
    full = _recon({"action_timeline": [_goal()],
                   "executive_summary": "Scored a brace today."})
    assert "brace" not in full["executive_summary"].lower()


def test_V29_scored_twice_contradiction():
    full = _recon({"action_timeline": [_goal()],
                   "executive_summary": "He scored twice in ten minutes."})
    assert "scored twice" not in full["executive_summary"].lower()


def test_V30_assist_contradiction():
    full = _recon({"action_timeline": [_assist()],
                   "executive_summary": "Delivered three assists tonight."})
    assert "three assists" not in full["executive_summary"].lower()


def test_V31_correct_aggregate_allowed():
    text = "Verified involvement: 1 goal and 3 assists."
    full = _recon({"action_timeline": [_goal(), _assist("02:00"), _assist("03:00"),
                                       _assist("04:00")],
                   "executive_summary": text})
    assert full["executive_summary"] == text


# ------------------------------------------- V32–V35 event-bound text

def test_V32_shot_event_false_goal_text():
    full = _recon({"action_timeline": [
        _ev("01:00", "SHOT", "SHOT", "OUTCOME_NOT_VISIBLE", False,
            title="Goal from distance", description="Scores from distance with power.")]})
    e = full["action_timeline"][0]
    assert "goal" not in e["title"].lower()
    assert "scores" not in e["description"].lower()


def test_V33_pass_event_false_assist_text():
    full = _recon({"action_timeline": [
        _ev("01:00", "PASS", "PASS", "COMPLETED", True,
            description="Assists the winner with a clever ball.")]})
    e = full["action_timeline"][0]
    assert "assist" not in e["description"].lower()


def test_V34_snapshot_cinematic_false_goal_total():
    full = _recon({"action_timeline": [_goal()],
                   "snapshot": {"biggest_strength": "Three-goal performance"},
                   "snapshot_moments": [{"title": "Three-goal performance", "desc": "x."}]})
    assert "three-goal" not in str(full["snapshot"]).lower()
    assert "three-goal" not in str(full["snapshot_moments"]).lower()


def test_V35_bound_video_comment():
    shot = _ev("01:00", "SHOT", "SHOT", "SAVED", True)
    full = {"action_timeline": [shot],
            "video_comments": [{"timestamp": "01:00", "comment": "Scores into the corner."}]}
    full = _recon(full)
    c = full["video_comments"][0]
    assert c.get("event_id") == full["action_timeline"][0]["event_id"]
    assert "scores" not in c["comment"].lower()


# ------------------------------------------- V36–V45 scoring scan merge

def _disc(ts, et, at, res, vis=True, identity="CONFIRMED", note="scan note"):
    return {"timestamp": ts, "identity": identity, "canonical_event_type": et,
            "canonical_action_type": at, "canonical_result": res,
            "outcome_visible": vis, "note": note}


def _merged_stats(timeline, discovered):
    full = {"action_timeline": list(timeline)}
    full["_scoring_scan"] = vstats.merge_discovered_scoring_events(full, discovered)
    full = attach_event_evidence_authority(full)
    full = vstats.apply_verified_stats_authority(full)
    return full


def test_V36_discover_missed_goal():
    full = _merged_stats([], [_disc("01:10", "GOAL", "SHOT", "SCORED")])
    evs = full["action_timeline"]
    assert len(evs) == 1 and evs[0]["title"] == "Goal"
    assert evs[0]["event_id"], "FIX01 did not assign the normal event_id"
    assert evs[0].get("discovered_by_scoring_scan") is True
    assert full["verified_stats"]["goals"] == 1


def test_V37_discover_missed_assist():
    full = _merged_stats([], [_disc("02:10", "ASSIST", "PASS", "TEAMMATE_SCORED")])
    assert full["verified_stats"]["assists"] == 1
    assert full["action_timeline"][0]["title"] == "Assist"


def test_V38_existing_plus_scan_same_goal():
    full = _merged_stats([_goal("01:10")], [_disc("01:10", "GOAL", "SHOT", "SCORED")])
    assert len(full["action_timeline"]) == 1
    assert full["verified_stats"]["goals"] == 1


def test_V39_existing_plus_scan_same_assist():
    full = _merged_stats([_assist("02:10")], [_disc("02:10", "ASSIST", "PASS", "TEAMMATE_SCORED")])
    assert len(full["action_timeline"]) == 1
    assert full["verified_stats"]["assists"] == 1


def test_V40_shot_leaves_frame():
    full = _merged_stats([], [_disc("01:10", "GOAL", "SHOT", "OUTCOME_NOT_VISIBLE", vis=False)])
    vs = full["verified_stats"]
    assert vs["goals"] == 0
    assert vs["scoring_scan"]["unresolved_goal_attempts"] == 1
    assert len(full["action_timeline"]) == 0


def test_V41_final_pass_goal_unseen():
    full = _merged_stats([], [_disc("02:10", "ASSIST", "PASS", "OUTCOME_NOT_VISIBLE", vis=False)])
    vs = full["verified_stats"]
    assert vs["assists"] == 0
    assert vs["scoring_scan"]["unresolved_assist_candidates"] == 1


def test_V42_wrong_player_scores():
    full = _merged_stats([], [_disc("01:10", "GOAL", "SHOT", "SCORED", identity="WRONG_PLAYER")])
    assert full["verified_stats"]["goals"] == 0
    assert len(full["action_timeline"]) == 0


def test_V43_wrong_player_assist():
    full = _merged_stats([], [_disc("02:10", "ASSIST", "PASS", "TEAMMATE_SCORED",
                                    identity="NOT_VISIBLE")])
    assert full["verified_stats"]["assists"] == 0


def test_V44_empty_pass1_timeline_scan_runs_once(monkeypatch):
    calls = {"n": 0}

    async def fake_verify(**kw):
        calls["n"] += 1
        assert "SCORING INVOLVEMENT SCAN" in kw["prompt"]
        return {"verdicts": [],
                "discovered_scoring_events": [_disc("01:10", "GOAL", "SHOT", "SCORED")],
                "independent_scores": {}}

    monkeypatch.setattr(server, "call_gemini_with_video", fake_verify)
    full = {"action_timeline": [], "scores": {}}
    asyncio.run(server._cross_verify_full_report(
        "t-fix07", full, file_path="/tmp/none.mp4", marker_path=None,
        crop_path_str=None, anchor_crops=None, anchor_payload_list=[],
        gt_track=None, gt_t_off=None, doc={"player_details": {}}))
    assert calls["n"] == 1, "verifier must run exactly ONCE"
    full = attach_event_evidence_authority(full)
    full = vstats.apply_verified_stats_authority(full)
    assert full["verified_stats"]["goals"] == 1
    assert full["verified_stats"]["scoring_scan"]["performed"] is True


def test_V45_complete_scoring_example():
    timeline = [_assist("02:00"), _assist("03:00")]
    discovered = [
        _disc("01:10", "GOAL", "SHOT", "SCORED"),                 # missed goal
        _disc("03:00", "ASSIST", "PASS", "TEAMMATE_SCORED"),      # duplicate
        _disc("04:00", "ASSIST", "CROSS", "TEAMMATE_SCORED"),     # missed assist
    ]
    full = _merged_stats(timeline, discovered)
    vs = full["verified_stats"]
    assert vs["goals"] == 1 and vs["assists"] == 3
    assert len(full["action_timeline"]) == 4
    assert full["verified_stat_line"] == "1 goal · 3 assists · 1 shot"


def test_V46_canonical_other_stats_example():
    evs = [
        _goal("00:10"),
        _ev("00:20", "SHOT", "SHOT", "SAVED", True),
        _ev("00:30", "SHOT", "SHOT", "OFF_TARGET", True),
        _ev("00:40", "SHOT", "SHOT", "OUTCOME_NOT_VISIBLE", False),
        _assist("01:00"), _assist("01:10"),
        _assist("01:20", at="CROSS"),
        _ev("01:30", "KEY_PASS", "PASS", "TEAMMATE_SHOT", True),
        _ev("01:40", "CROSS", "CROSS", "COMPLETED", True),
    ]
    evs += [_ev(f"02:{i:02d}", "PASS", "PASS",
                "COMPLETED" if i < 6 else "INCOMPLETE", True) for i in range(9)]
    evs += [_ev("03:00", "DRIBBLE", "DRIBBLE", "SUCCESS", True),
            _ev("03:10", "DRIBBLE", "DRIBBLE", "SUCCESS", True),
            _ev("03:20", "DRIBBLE", "DRIBBLE", "FAILED", True)]
    evs += [_ev(f"04:{i:02d}", "DUEL", "DUEL", "WON" if i < 3 else "LOST", True)
            for i in range(5)]
    evs += [_ev("05:00", "TACKLE", "TACKLE", "WON", True),
            _ev("05:10", "TACKLE", "TACKLE", "LOST", True),
            _ev("05:20", "INTERCEPTION", "INTERCEPTION", "POSSESSION_WON", True),
            _ev("05:30", "RECOVERY", "RECOVERY", "POSSESSION_WON", True),
            _ev("05:40", "RECOVERY", "RECOVERY", "SUCCESS", True)]
    vs, _ = _stats(evs)
    assert vs["goals"] == 1 and vs["assists"] == 3
    assert vs["shots"] == 4 and vs["shots_on_target"] == 2
    assert vs["key_passes"] == 4
    assert vs["passes_attempted"] == 12 and vs["passes_completed"] == 9
    assert vs["pass_completion_pct"] == 75
    assert vs["crosses_attempted"] == 2 and vs["crosses_completed"] == 2
    assert vs["dribbles_attempted"] == 3 and vs["successful_dribbles"] == 2
    assert vs["duels_contested"] == 5 and vs["duels_won"] == 3
    assert vs["tackles_attempted"] == 2 and vs["tackles_won"] == 1
    assert vs["interceptions"] == 1 and vs["recoveries"] == 2
    assert vs["defensive_actions"] == 5


# ------------------------------------------- V47–V50 authority guards

def test_V47_fix02_semantics_unchanged():
    timeline = [{"timestamp": "01:00", "title": "a", "action_type": "pass"},
                {"timestamp": "02:00", "title": "b", "action_type": "pass"},
                {"timestamp": "03:00", "title": "c", "action_type": "pass"}]
    verify = {"verdicts": [
        {"claim_id": 0, "identity": "WRONG_PLAYER", "event": "CONFIRMED"},
        {"claim_id": 1, "identity": "CONFIRMED", "event": "NOT_SEEN"},
        {"claim_id": 2, "identity": "NOT_VISIBLE", "event": "CONFIRMED"},
    ], "independent_scores": {}}
    full = {"action_timeline": timeline, "scores": {}}
    server._apply_cross_verification(full, verify, None)
    assert full["action_timeline"] == [], "FIX02 keep/drop semantics changed"


def test_V48_fix01_ids_preserved():
    e = _goal(event_id="evt_keep", event_start_ms=70000)
    full = {"action_timeline": [e],
            "video_comments": [{"timestamp": "01:10", "comment": "x.",
                                "evidence_id": "evd_keep", "evidence_time_ms": 70000}]}
    full = attach_event_evidence_authority(full)
    full = vstats.apply_verified_stats_authority(full)
    assert full["action_timeline"][0]["event_id"] == "evt_keep"
    assert full["action_timeline"][0]["event_start_ms"] == 70000
    assert full["video_comments"][0]["evidence_id"] == "evd_keep"


def test_V49_retry_path_runs_same_pipeline():
    src = (BACKEND / "server.py").read_text()
    assert src.count("vstats.apply_verified_stats_authority(") == 2, \
        "normal + corrective paths must both run the FIX07 authority"
    for chunk in src.split("attach_event_evidence_authority(")[1:]:
        head = chunk[:400]
        if "apply_fail_closed_proof_authority" in head:
            assert "apply_verified_stats_authority" in head, \
                "FIX07 must run between FIX01 attach and the proof gate"


def test_V50_zero_new_model_calls():
    vsrc = (BACKEND / "verified_stats.py").read_text()
    for token in ("LlmChat", "call_gemini", "verify_frame_identity", "httpx",
                  "aiohttp", "requests.", "urllib", "socket", "emergentintegrations"):
        assert token not in vsrc, f"forbidden call path in verified_stats.py: {token}"
    src = (BACKEND / "server.py").read_text()
    body = src.split("async def _cross_verify_full_report", 1)[1]
    body = body.split("\nasync def ", 1)[0]
    assert body.count("call_gemini_with_video(") == 1, \
        "the cross-verification stage must stay a single verifier call"
