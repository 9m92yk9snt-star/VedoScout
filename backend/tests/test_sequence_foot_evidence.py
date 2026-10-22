"""Synthetic contract tests, not claims of successful live anatomical recognition."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

import pytest
import sequence_pilot as p
import sequence_report_adapter as adapter
from sequence_foot_evidence import assess_foot, filter_foot_prose
from report_fact_authority import _supports
from test_sequence_pilot import fixture, bracketed_shot


def foot_claim(side="LEFT"):
    fact = lambda frame: {"frame": frame, "fact": "Visible anatomical leg continuity in this synthetic frame."}
    return {"actor": "passer", "side": side, "assessment": "SUPPORTED",
            "basis": "CONTINUOUS_LEG_SEQUENCE", "other_contact_actors_excluded": True,
            "orientation_evidence": [fact("s000000500")],
            "right_leg_evidence": [fact("s000000500"), fact("s000001000")],
            "left_leg_evidence": [fact("s000000500"), fact("s000001000")],
            "contact_evidence": [fact("s000000750"), fact("s000001000")]}


def resolve(data):
    manifest, packet, _ = fixture()
    return p.resolve_response(data, manifest, packet, {"origin": "SYNTHETIC_TEST_ONLY"})


@pytest.mark.parametrize("side", ["LEFT", "RIGHT"])
def test_supported_anatomical_sequence_preserves_correct_side_without_changing_goal(side):
    data = bracketed_shot()
    data["plays"][0]["actions"][0]["anatomical_foot"] = foot_claim(side)
    result = p.reconcile([resolve(data)])
    assert result["counts"] == {"GOAL": 1}
    assert result["target_events"][0]["foot"] == side


@pytest.mark.parametrize("key,value", [
    ("assessment", "PROBABLE"), ("assessment", "UNCERTAIN"), ("assessment", []),
    ("side", []), ("basis", []), ("other_contact_actors_excluded", False),
    ("actor", "finisher"), ("left_leg_evidence", []),
    ("right_leg_evidence", [{"frame": "invented", "fact": "not a source frame"}]),
    ("orientation_evidence", [{"frame": "s000002000", "fact": "only after contact"}]),
    ("contact_evidence", [{"frame": "s000000750", "fact": "no departure"}]),
])
def test_probable_hidden_or_malformed_side_stays_unknown_without_discarding_goal(key, value):
    data = bracketed_shot(); claim = foot_claim(); claim[key] = value
    data["plays"][0]["actions"][0]["anatomical_foot"] = claim
    result = p.reconcile([resolve(data)])
    assert result["counts"] == {"GOAL": 1}
    assert result["target_events"][0]["foot"] == "UNKNOWN"


def test_explicit_foot_question_cannot_publish_even_a_supported_foot_label():
    data = bracketed_shot(); play = data["plays"][0]
    play["actions"][0]["anatomical_foot"] = foot_claim()
    play["questions"] = [{"reason": "FOOT", "action_id": "a1", "question": "Left or right?"}]
    result = p.reconcile([resolve(data)])
    assert result["counts"] == {"GOAL": 1}
    assert result["target_events"][0]["foot"] == "UNKNOWN"
    assert result["questions"][0]["reason"] == "FOOT"
    manifest, _, _ = fixture()
    assert p.plan_contact_reviews(manifest, result, complete_terminal_context=True) == []


@pytest.mark.parametrize("reason", ["CONTACT", "IDENTITY", "OUTCOME"])
def test_contact_scorer_or_outcome_doubt_still_blocks_goal_despite_supported_side(reason):
    data = bracketed_shot(); play = data["plays"][0]
    play["actions"][0]["anatomical_foot"] = foot_claim()
    play["questions"] = [{"reason": reason, "action_id": "a1", "question": "Who redirected the ball?"}]
    assert p.reconcile([resolve(data)])["target_events"] == []


def test_conflicting_supported_sides_withhold_foot_without_erasing_goal():
    data = bracketed_shot(); data["plays"][0]["actions"][0]["anatomical_foot"] = foot_claim()
    first = resolve(data)
    data["plays"][0]["actions"][0]["anatomical_foot"] = foot_claim("RIGHT")
    second = resolve(data)
    result = p.reconcile([first, second])
    assert result["counts"] == {"GOAL": 1}
    assert result["target_events"][0]["foot"] == "UNKNOWN"
    assert result["target_events"][0]["foot_question_unresolved"] is True


def test_later_uncertain_limb_review_cannot_silently_inherit_an_earlier_supported_side():
    data = bracketed_shot(); data["plays"][0]["actions"][0]["anatomical_foot"] = foot_claim()
    first = resolve(data)
    data["plays"][0]["actions"][0]["anatomical_foot"]["assessment"] = "PROBABLE"
    second = resolve(data)
    assert p.reconcile([first, second])["target_events"][0]["foot"] == "UNKNOWN"
    assert p.reconcile([second, first])["target_events"][0]["foot"] == "UNKNOWN"


def test_canonical_revalidates_foot_and_propagates_source_frames_to_existing_report():
    manifest, packet, _ = fixture(); manifest["references"] = [{"reference_id": "r1"}]
    data = bracketed_shot(); data["plays"][0]["actions"][0]["anatomical_foot"] = foot_claim()
    raw = json.dumps(data)
    receipt = {"packet_id": packet["packet_id"], "payload_sha256": "synthetic-payload",
        "response_sha256": hashlib.sha256(raw.encode()).hexdigest(), "raw_response": raw,
        "origin": "LIVE_MODEL_REQUEST", "status": "COMPLETED", "provider": "SYNTHETIC_TEST_ONLY"}
    result = p.reconcile([p.resolve_response(data, manifest, packet, receipt)])
    result.update(source_video_sha256="source", status="MODEL_OBSERVATIONS_RETURNED",
                  fresh_end_to_end_run=True, model_jobs_completed=1)
    bundle = adapter.canonical_bundle(result, manifest, [receipt])
    event = bundle["events"][0]
    assert event["foot"] == "LEFT"
    assert "s000000500" in event["proof"]["cited_frames"]
    report = adapter.build_report({"summary": "Observed goal"}, bundle)
    assert report["action_timeline"][0]["foot"] == "LEFT"
    bad = deepcopy(result); bad["target_events"][0]["anatomical_foot"]["assessment"] = "PROBABLE"
    assert adapter.canonical_bundle(bad, manifest, [receipt])["events"][0]["foot"] == "UNKNOWN"
    bad["target_events"][0].pop("anatomical_foot")
    bad["target_events"][0]["foot"] = "RIGHT"
    assert adapter.canonical_bundle(bad, manifest, [receipt])["events"][0]["foot"] == "UNKNOWN"


def test_unverified_side_is_omitted_from_player_prose_and_wrong_side_is_rejected():
    assert filter_foot_prose("He finishes with his left foot. He stays involved.", "UNKNOWN") == "He finishes. He stays involved."
    assert not _supports("A left-footed finish.", [{"foot": "UNKNOWN"}])
    assert not _supports("A right-footed finish.", [{"foot": "LEFT"}])
    assert _supports("Controlled with his left foot.", [{"foot": "LEFT"}])


def test_terminal_review_includes_anatomical_approach_without_adding_jobs():
    manifest, packet, _ = fixture(); data = bracketed_shot()
    play = data["plays"][0]
    play["questions"] = [{"reason": "CONTACT", "action_id": "a1", "question": "Which actor?"}]
    result = p.reconcile([p.resolve_response(data, manifest, packet, {})])
    jobs = p.plan_contact_reviews(manifest, result, complete_terminal_context=True)
    assert len(jobs) == 1
    assert jobs[0]["detail_start_ms"] == 0
    assert jobs[0]["detail_end_ms"] >= 2500


def test_actual_orman600_probable_reply_is_not_upgraded_by_the_new_contract():
    saved = json.loads((Path(__file__).resolve().parents[2] /
        'docs/examples/sequence-foot-probable-regression.json').read_text())
    receipt = saved['receipt']
    assert hashlib.sha256(receipt['raw_response'].encode()).hexdigest() == receipt['response_sha256']
    review = json.loads(receipt['raw_response'])['contact_review']
    assert review['striking_foot'] == 'LEFT' and review['assessment'] == 'probable'
    # Translate only field names for an offline contract check; never rewrite
    # or reinject the saved model reply into live analysis.
    claim = {'actor': 'selected', 'side': review['striking_foot'],
             'assessment': review['assessment'].upper()}
    frames = {f['frame_id']: f['media_ms'] for f in saved['source_frames']}
    checked = assess_foot(claim, actor='selected', interval=review['contact_interval_ms'],
                          frames=frames, bounds=(15400, 17000))
    assert checked['foot'] == 'UNKNOWN'
    assert checked['foot_review']['candidate_side'] == 'LEFT'
    assert checked['foot_review']['assessment'] == 'PROBABLE'
