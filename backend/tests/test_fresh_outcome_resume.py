"""Actual receipt navigation and refusal checks, without model calls."""
from copy import deepcopy
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.resume_fresh_outcome import outcome_job, checked_observation


def current_review():
    root = Path(__file__).resolve().parents[2]
    saved = json.loads((root/"docs/examples/fresh-whole-source-review-receipts.json").read_text())
    initial = json.loads((root/"docs/examples/fresh-whole-source-initial-receipts.json").read_text())
    jobs = [{"packet_id": f"contact_review_{i+1:03}", "replaces_initial_packet_id": packet,
             "start_ms": p["core_start_ms"], "end_ms": p["core_end_ms"]-1, "reference_ids": p["reference_ids"]}
            for i, packet in enumerate(saved["result"]["superseded_initial_packet_ids"])
            for p in initial["replay_manifest"]["packets"] if p["packet_id"] == packet]
    # Review order is explicit in the actual response provenance, not chronological.
    for j in jobs:
        j["packet_id"] = {"sequence_003":"contact_review_002", "sequence_004":"contact_review_001",
                          "sequence_007":"contact_review_003"}[j["replaces_initial_packet_id"]]
    return saved, jobs


def test_actual_unknown_shot_derives_continuous_release_and_aftermath_without_answer():
    saved, jobs = current_review()
    job = outcome_job({}, saved["result"], jobs)
    shot = next(e for e in saved["result"]["events"] if e["kind"] == "SHOT"
                and e["selected_player"] is True and e["outcome"] == "UNKNOWN")
    assert job["detail_start_ms"] == shot["contact_interval_ms"][0]-100
    assert job["detail_end_ms"] == shot["contact_interval_ms"][1]+1500
    assert job["replaces_review_packet_id"] == "contact_review_002"
    assert "SAVED" not in json.dumps(job) and "GOAL" not in json.dumps(job)
    assert job["detail_start_ms"] < shot["contact_interval_ms"][0]
    assert job["detail_end_ms"] > 25000


def test_no_explicit_outcome_question_or_multiple_candidates_prevents_another_call():
    saved, jobs = current_review()
    changed = deepcopy(saved["result"])
    changed["questions"] = [q for q in changed["questions"] if q["reason"] != "OUTCOME"]
    with pytest.raises(ValueError, match="UNIQUE_EXPLICIT_TERMINAL_OUTCOME_REQUIRED"):
        outcome_job({}, changed, jobs)
    changed = deepcopy(saved["result"])
    shot = next(e for e in changed["events"] if e["kind"] == "SHOT" and e["selected_player"] is True
                and e["outcome"] == "UNKNOWN")
    changed["events"].append(deepcopy(shot))
    with pytest.raises(ValueError, match="UNIQUE_EXPLICIT_TERMINAL_OUTCOME_REQUIRED"):
        outcome_job({}, changed, jobs)


def test_tampered_actual_review_response_stops_before_resolution():
    saved, _ = current_review()
    receipt = saved["receipts"][1]
    with pytest.raises(ValueError, match="REVIEW_RECEIPT_MISMATCH"):
        checked_observation({**receipt,"raw_response":receipt["raw_response"]+" "}, {}, {})


def actual_outcome():
    path = Path(__file__).resolve().parents[2]/"docs/examples/fresh-outcome-approval-receipt.json"
    return json.loads(path.read_text())


def test_actual_continuous_outcome_reply_replays_selected_saved_shot_with_provenance():
    saved = actual_outcome()
    observed = checked_observation(saved["receipt"], saved["replay_context"], saved["result"]["job"])
    assert observed == saved["result"]["resolved_observations"]
    shot = next(e for e in observed["events"] if e["kind"] == "SHOT")
    assert shot["selected_player"] is True and shot["outcome"] == "SAVED" and shot["proof_eligible"]
    assert shot["contact_interval_ms"] == [23682,23749]
    assert observed["questions"] == [] and observed["invalid_rows"] == []
    assert saved["evaluation"]["continued_observations_pass"] is True
    assert saved["evaluation"]["fresh_run_complete"] is False
    assert saved["result"]["previous_terminal_observations"][0]["events"]


def test_actual_new_reply_cannot_approve_shot_with_an_explicit_target_contact_question():
    from scripts.resume_fresh_outcome import p
    saved = actual_outcome()
    data = json.loads(saved["receipt"]["raw_response"])
    play = next(play for play in data["plays"] if any(a["kind"] == "SHOT" for a in play["actions"]))
    action = next(a for a in play["actions"] if a["kind"] == "SHOT")
    play["questions"].append({"reason":"CONTACT","action_id":action["action_id"]})
    observed = p.resolve_response(data, saved["replay_context"], saved["result"]["job"],
        {k:saved["receipt"][k] for k in ("packet_id","payload_sha256","response_sha256","origin")})
    assert not next(e for e in observed["events"] if e["kind"] == "SHOT")["proof_eligible"]


def test_generic_outcome_planner_reproduces_actual_successful_navigation_and_refuses_ambiguity():
    from scripts.resume_fresh_outcome import p
    saved, parents = current_review()
    jobs = p.plan_outcome_reviews({}, saved["result"], parents)
    assert len(jobs) == 1
    actual = actual_outcome()["result"]["job"]
    assert all(actual[k] == value for k,value in jobs[0].items())
    assert p.plan_outcome_reviews({}, saved["result"], parents, limit=0) == []
    assert p.plan_outcome_reviews({}, saved["result"], parents+parents) == []
    assert p.plan_outcome_reviews({}, {**saved["result"],"questions":[]}, parents) == []
