"""Regressions for the failure modes in live report 361e3bb7.

Synthetic controls test the safety boundaries; an optional local replay uses
the unchanged evidence ZIP without putting private footage in the repository.
"""
from copy import deepcopy
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import dense_identity_continuity as identity
import report_fact_authority as facts
import goal_review_scheduler as scheduler
import verified_stats as stats


def frame(ms, target=False, track="p1"):
    return {"media_ms": ms, "scene_id": "s1", "time_authority": "ACTUAL_MEDIA_PTS",
            "global_target": {"status": "VERIFIED" if target else "UNRESOLVED",
                              "proof_eligible": target, "reason": "OK_NEAREST_TAP_FRAME" if target else "TARGET_GAP",
                              "local_track_id": track if target else None},
            "players": [{"local_track_id": "p1", "association_state": "VERIFIED_LOCAL",
                         "box": {"x": .2, "y": .3, "w": .1, "h": .2}}]}


def test_body_identity_survives_unreadable_number_and_coarse_gap():
    rows = [frame(ms, target=ms == 300) for ms in range(0, 701, 50)]
    before = deepcopy(rows)
    result = identity.apply(rows)
    assert all(f["global_target"]["proof_eligible"] for f in result["frames"])
    assert result["diagnostic"]["promoted_frames"] == 14
    assert rows == before


def test_later_jersey_handoff_is_shared_back_into_frames_and_other_contacts():
    rows = [frame(ms) for ms in range(0, 601, 50)]
    touch = {"touch_id": "seed", "media_ms": 300, "scene_id": "s1", "player_track_id": "p1",
             "status": "VERIFIED", "proof_eligible": True, "global_target_id": "GLOBAL_TARGET",
             "global_target_resolution": {"status": "VERIFIED", "reason": "UNIQUE_MULTI_FRAME_JERSEY_REID_AFTER_USER_TAP"}}
    previous = {**touch, "media_ms": 100, "touch_id": "previous", "global_target_id": None,
                "global_target_resolution": {"status": "UNRESOLVED"}}
    candidate = {**previous, "media_ms": 150, "status": "CANDIDATE_OCCLUDED"}
    result = identity.apply(rows, {"touches": [previous, candidate, touch]})
    assert result["frames"][2]["global_target"]["local_track_id"] == "p1"
    assert result["touch_graph"]["touches"][0]["global_target_id"] == "GLOBAL_TARGET"
    assert result["touch_graph"]["touches"][1]["global_target_id"] is None


def test_body_continuity_stops_at_cut_ambiguity_competitor_or_pts_gap():
    for change in ({"cut_barrier": True}, {"used_fallback": True}, {"scene_id": "s2"},
                   {"players": []}, {"global_target": {"status": "VERIFIED", "proof_eligible": True, "local_track_id": "p2"}}):
        rows = [frame(100, target=True), {**frame(150), **change}, frame(200)]
        result = identity.apply(rows)
        assert not result["frames"][-1]["global_target"]["proof_eligible"]
    assert not identity.apply([frame(100, target=True), frame(300)])["frames"][-1]["global_target"]["proof_eligible"]


def test_propagation_is_bounded_and_cannot_be_reseeded_from_its_own_output():
    rows = [frame(ms, target=ms == 0) for ms in range(0, 1501, 50)]
    result = identity.apply(rows)
    assert not result["frames"][-1]["global_target"]["proof_eligible"]
    second = identity.apply(result["frames"])
    assert not second["frames"][-1]["global_target"]["proof_eligible"]


def event(kind="GOAL", ms=30000):
    return {"event_id": "evt", "canonical_ms": ms, "start_ms": ms, "end_ms": ms,
            "canonical_event_type": kind, "canonical_action_type": "SHOT",
            "canonical_outcome": "GOAL", "causal_verified": True,
            "proof": {"proof_eligible": True}}


def full_report():
    return {"parent_summary": {"paragraphs": ["We saw him score three excellent goals in this short clip."]},
            "executive_summary": "His finishing was clinical.",
            "technical": {"shooting": {"score": 9, "confidence": "High", "cannot_evaluate": False,
                                         "evidence": [{"timestamp": "00:30", "what": "Scores with his left foot."}]}},
            "scores": {"technical": 9, "overall_development": 9},
            "video_comments": [{"timestamp": "00:30", "comment": "GOAL: He scores."}],
            "training_plan": {"weekly_focus": "Practice finishing to score more goals."}}


def test_live_adjective_count_hole_is_closed_and_training_is_preserved():
    assert not stats._sentence_supported("He scores three excellent goals.", {"goals": None, "assists": None})
    source = full_report()
    result = facts.apply(source, {"events": []})
    assert "three excellent goals" not in str(result["parent_summary"])
    assert result["technical"]["shooting"]["score"] is None
    assert result["technical"]["shooting"]["cannot_evaluate"] is True
    assert result["scores"]["overall_development"] is None
    assert not result["video_comments"]
    assert result["training_plan"] == source["training_plan"]
    assert source["technical"]["shooting"]["score"] == 9


def test_qualified_goal_supports_grade_but_other_players_actions_do_not():
    report = full_report()
    report["parent_summary"] = {"paragraphs": ["He scored a goal."]}
    result = facts.apply(report, {"events": [event()]})
    assert result["technical"]["shooting"]["score"] == 9
    assert result["technical"]["shooting"]["evidence"][0]["canonical_event_ids"] == ["evt"]
    assert result["technical"]["shooting"]["evidence"][0]["event_id"] == "evt"
    assert len(result["video_comments"]) == 1
    rejected = facts.apply(report, {"events": [{**event(), "proof": {"proof_eligible": False}}]})
    assert rejected["technical"]["shooting"]["score"] is None
    different_time = facts.apply(report, {"events": [event(ms=50000)]})
    assert different_time["technical"]["shooting"]["score"] is None


def test_real_stat_projection_remains_the_fact_authority_in_partial_coverage():
    report = full_report()
    report["analysis_authority"] = {"output": "FIX09C"}
    report["action_timeline"] = []
    report["_scoring_scan"] = {"performed": True, "physical_recall_verification_complete": False}
    result = stats.apply_verified_stats_authority(report)
    assert result["verified_stats"]["goals"] is None
    assert result["match_stats"]["observed_goals"] == 0
    assert result["report_fact_authority"]["status"] == "REVIEW_REQUIRED"
    assert result["technical"]["shooting"]["score"] is None


def job(scene, ms, lane="CLARIFICATION", role="RELEASE"):
    return {"window": {"scene_id": scene}, "strike": {"scene_id": scene, "media_ms": ms,
              "contact_role": {"role": role}}, "review": {"lane": lane}}


def test_budget_visits_late_scenes_before_repeated_early_contacts():
    rows = [job("early", t) for t in range(100, 2000, 100)] + [job("late", 56000)]
    ordered = scheduler.ordered_requests(rows, {})
    assert [j["window"]["scene_id"] for j in ordered[:2]] == ["early", "late"]
    assert len(ordered) == len(rows)


def test_verified_chain_and_releases_precede_uncertain_control_noise():
    ordered = scheduler.ordered_requests([job("s", 100, role="RECEIVE_CONTROL"),
                                         job("s", 300), job("v", 50000, lane="VERIFIED_CHAIN")], {})
    assert [j["strike"]["media_ms"] for j in ordered] == [50000, 300, 100]


def test_prompt_contract_forbids_a_second_match_history():
    block = facts.prompt_block({"events": [event()]})
    assert '"event_id":"evt"' in block
    assert "score=null" in block and "Missing events mean incomplete evidence" in block


def test_assessment_score_is_not_a_match_scoring_claim():
    assert facts._supports("A score of 7 reflects the verified receiving evidence.", [])
    assert not facts._supports("He scores a goal.", [])
    assert not facts._supports("He can score from this position.", [])


def test_malformed_or_nonfinite_event_times_cannot_bind_evidence():
    assert facts._matching([event(ms=None)], {"timestamp": "00:30"}) == []
    assert facts._matching([event()], {"evidence_time_ms": float("nan")}) == []


def test_unrelated_verified_action_cannot_support_a_shooting_grade():
    report = full_report()
    report["technical"]["shooting"]["evidence"][0]["what"] = "Excellent technique."
    result = facts.apply(report, {"events": [event(kind="PRESS")]})
    assert result["technical"]["shooting"]["score"] is None


def test_ambiguous_evidence_timestamp_cannot_choose_a_neighboring_event():
    result = facts.apply(full_report(), {"events": [event(), {**event(ms=30500), "event_id": "other"}]})
    assert result["technical"]["shooting"]["score"] is None
    report = full_report()
    report["technical"]["shooting"]["evidence"][0]["event_id"] = "evt"
    result = facts.apply(report, {"events": [event(), {**event(ms=30500), "event_id": "other"}]})
    assert result["technical"]["shooting"]["score"] == 9


def test_portrait_ground_detail_remaps_ball_without_changing_person_identity():
    import numpy as np
    import dense_track_refinement as dense
    class Net:
        calls = 0
        def setInput(self, _blob):
            pass
        def forward(self):
            self.calls += 1
            out = np.zeros((1, 84, 100), dtype=np.float32)
            if self.calls == 1:
                out[0, :4, 0] = [180, 300, 40, 80]
                out[0, 4, 0] = .9  # person in full portrait frame
            else:
                out[0, :4, 0] = [320, 90, 8, 8]
                out[0, 36, 0] = .8  # sports-ball in native ground band
            return out
    class Detector:
        ok = True
        net = Net()
    detector = Detector()
    people, balls = dense._detect_dense_people_and_ball(detector, np.zeros((1920, 1080, 3), np.uint8))
    assert detector.net.calls == 2
    assert len(people) == 1 and len(balls) == 1
    assert balls[0]["source"] == "NATIVE_GROUND_BAND_DETECTOR"
    assert abs(balls[0]["box"]["x"] - .49375) < .01
    assert .49 < balls[0]["box"]["y"] < .54
    assert balls[0].get("proof_eligible") is not True


def test_dense_identity_feedback_keeps_scoring_and_unseen_releases_unresolved(monkeypatch):
    import dense_event_reconciliation as feedback
    pending = {"unresolved": [{"action_id": "a", "actor_resolution": {
        "reason": "INSUFFICIENT_PHYSICAL_IDENTITY_EVIDENCE"}}], "events": []}
    physical = {"traces": [{"decoded_frames": [frame(100, target=True)], "strike_evidence": []}]}
    candidate = {**event(ms=100), "source_action_ids": ["a"], "scene_id": "s1"}
    for kind, event_type in (("SHOT", "GOAL"), ("PASS", "ASSIST"), ("PASS", "PASS")):
        monkeypatch.setattr(feedback.resolver, "resolve_canonical_events", lambda *_args: {
            "events": [{**candidate, "canonical_action_type": kind, "canonical_event_type": event_type}]})
        result = feedback.recover(pending, {}, physical, {})
        assert not result["events"] and len(result["unresolved"]) == 1
    monkeypatch.setattr(feedback.resolver, "resolve_canonical_events", lambda *_args: {
        "events": [{**candidate, "canonical_action_type": "SUPPORT", "canonical_event_type": "SUPPORT"}]})
    result = feedback.recover(pending, {}, physical, {})
    assert len(result["events"]) == 1 and not result["unresolved"]
