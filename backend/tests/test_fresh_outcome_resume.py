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
             "start_ms": p["start_ms"], "end_ms": p["end_ms"], "reference_ids": p["reference_ids"]}
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
