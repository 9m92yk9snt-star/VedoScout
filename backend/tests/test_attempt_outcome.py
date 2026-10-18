"""Navigation and delivered-evidence checks; no synthetic perception claims."""
import json
import hashlib
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.probe_attempt_outcome import outcome_gap, identity_review_manifest
import sequence_pilot as p


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


def retained_saved_shot():
    path = Path(__file__).resolve().parents[2]/"docs/examples/native-saved-shot-approval-receipt.json"
    saved = json.loads(path.read_text())
    context, receipt = saved["replay_context"], saved["receipt"]
    assert hashlib.sha256(receipt["raw_response"].encode()).hexdigest() == receipt["response_sha256"]
    packet = {"packet_id":receipt["packet_id"], "start_ms":19266, "end_ms":25631,
              "frame_ids":[f["frame_id"] for f in context["frames"]],
              "reference_ids":[r["reference_id"] for r in context["references"]],
              "contact_sequence_evidence":True}
    return saved, context, packet, json.loads(receipt["raw_response"])


def shot_replay(saved, context, packet, data):
    receipt = {key:saved["receipt"][key] for key in
               ("packet_id","payload_sha256","response_sha256","origin")}
    return p.reconcile([p.resolve_response(data, context, packet, receipt)])


def test_actual_fresh_identity_reply_accepts_selected_saved_shot():
    saved, context, packet, data = retained_saved_shot()
    result = shot_replay(saved, context, packet, data)
    assert result["target_events"] == saved["result"]["target_events"]
    shots = [e for e in result["target_events"] if e["kind"] == "SHOT"]
    assert len(shots) == 1 and shots[0]["outcome"] == "SAVED"
    assert shots[0]["selected_player"] is True and shots[0]["proof_eligible"]
    assert shots[0]["contact_interval_ms"] == [23682,23749]
    assert shots[0]["contact_ms"] is None and result["questions"] == []
    assert shots[0]["reference_ids"] == ["r5","r6","r10"]
    assert not any(e["event_type"] == "GOAL" for e in result["target_events"])
    # This replays a retained actual answer; it is not another perception trial.


@pytest.mark.parametrize("selected", [False, None])
def test_same_saved_outcome_without_player_identity_cannot_receive_selected_credit(selected):
    saved, context, packet, data = retained_saved_shot()
    data["plays"][0]["people"][0].update(selected=selected, reference_ids=[])
    assert not any(e["kind"] == "SHOT" for e in shot_replay(saved,context,packet,data)["target_events"])


@pytest.mark.parametrize("change", [
    {"same_active_ball":False}, {"contact_after_frame":None}, {"outcome_evidence":[]}])
def test_actor_identity_alone_cannot_replace_contact_and_active_ball_outcome(change):
    saved, context, packet, data = retained_saved_shot()
    next(a for a in data["plays"][0]["actions"] if a["kind"] == "SHOT").update(change)
    result = shot_replay(saved,context,packet,data)
    assert not any(e["kind"] == "SHOT" and e["outcome"] == "SAVED" for e in result["target_events"])


def test_actual_old_profile_reply_remains_unselected_on_replay():
    saved, context, packet, _ = retained_saved_shot()
    old = json.loads((Path(__file__).resolve().parents[2]/
                     "docs/examples/native-attempt-outcome-receipt.json").read_text())
    data = json.loads(old["receipt"]["raw_response"])
    result = shot_replay(old,context,packet,data)
    assert result["target_events"] == []
