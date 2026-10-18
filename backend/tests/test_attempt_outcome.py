"""Navigation and delivered-evidence checks; no synthetic perception claims."""
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.probe_attempt_outcome import outcome_gap, identity_review_manifest


def native_gap():
    return {"source_video_sha256":"source", "plays":[{
        "selected_packet":"play", "source_start_ms":19000, "source_end_ms":26000,
        "raw_native_observations":{
            "players":[{"id":"p1","selected":True}],
            "ball_sequence":[{"actor":"p1","action":"shot","clip_s":4.7}],
            "outcome":{"kind":"miss"}}}]}


def test_gap_is_navigation_not_the_old_outcome_or_user_answer():
    native = native_gap()
    job = outcome_gap({"source_video_sha256":"source", "references":[]}, native)
    assert job["packet_id"] == "play"
    assert job["detail_start_ms"] == 23500 and job["detail_end_ms"] == 25300
    assert "miss" not in job["question"] and "SAVED" not in json.dumps(job)


def test_mismatched_source_and_nonunique_navigation_stop_before_images_or_call():
    manifest = {"source_video_sha256":"source", "references":[]}
    native = native_gap()
    with pytest.raises(ValueError, match="SOURCE_INPUT_MISMATCH"):
        outcome_gap({**manifest,"source_video_sha256":"other"}, native)
    native["plays"] *= 2
    with pytest.raises(ValueError, match="UNIQUE_OUTCOME_GAP_REQUIRED"):
        outcome_gap(manifest, native)


def test_real_navigation_is_the_existing_native_models_unresolved_attempt():
    path = Path(__file__).resolve().parents[2]/"docs/examples/native-full-source-observations.json"
    native = json.loads(path.read_text())
    job = outcome_gap({"source_video_sha256":native["source_video_sha256"],"references":[]}, native)
    assert job["packet_id"] == "sequence_003"
    assert (job["start_ms"], job["end_ms"]) == (19266,25631)
    assert (job["detail_start_ms"], job["detail_end_ms"]) == (23566,25366)


def test_fresh_identity_does_not_inherit_disputed_description_or_drop_references():
    manifest = {"references":[{"reference_id":f"r{i}", "media_ms":i} for i in range(1,11)], "packets":[]}
    profile = {"identity_clear":True, "appearance":"prior claim about a beard",
               "canonical_reference_ids":["r2","r6","r7"], "contradictions":"r5 is different"}
    fresh, ids = identity_review_manifest(manifest, profile, True)
    assert "identity_profile" not in fresh
    assert ids == [f"r{i}" for i in range(1,11)]
    assert "beard" not in json.dumps(fresh)
    shared, canonical = identity_review_manifest(manifest, profile)
    assert shared["identity_profile"] == profile and canonical == ["r2","r6","r7"]
    assert "identity_profile" not in manifest
