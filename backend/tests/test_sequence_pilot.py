"""Meaningful failure cases; all responses here are synthetic, not model proof."""
from copy import deepcopy
import hashlib
import json
import multiprocessing
from pathlib import Path
import sys
import time

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import sequence_pilot as p
import sequence_pilot_transport as t
from scripts.run_sequence_pilot import run


def fixture():
    frames = [{"frame_id": f"s{i:09}", "media_ms": i} for i in (0, 125, 250, 500, 750, 1000, 1250, 1500, 1750, 2000, 2500, 3000, 4000, 5000, 6000, 8000)]
    packet = {"packet_id": "first", "phase": "INITIAL", "start_ms": 0, "end_ms": 8000,
              "frame_ids": [f["frame_id"] for f in frames], "reference_ids": ["r1"]}
    manifest = {"source_video_sha256": "source", "source_end_ms": 8000, "frames": frames,
                "references": [], "packets": [packet], "preparation_seconds": 0,
                "input_coverage": {"max_sample_gap_ms": 125}}
    people = [{"person_id": "passer", "selected": True, "kit_consistent": True, "reference_ids": ["r1"],
               "evidence_frames": ["s000000500"]},
              {"person_id": "finisher", "selected": False, "kit_consistent": True, "reference_ids": [],
               "evidence_frames": ["s000001250", "s000001500"]}]
    action = {"action_id": "a1", "kind": "PASS", "actor": "passer", "start_frame": "s000000500",
        "contact_frame": "s000001000", "end_frame": "s000001250", "actor_evidence_frames": ["s000000500", "s000001000"],
        "ball_id": "active", "outcome": "TEAMMATE_GOAL", "receiver": "finisher", "receiver_frame": "s000001250",
        "receiver_is_teammate": True, "finisher": "finisher", "shot_frame": "s000001500", "outcome_frame": "s000002000",
        "same_active_ball": True, "continuous_play": True,
        "outcome_evidence": [{"frame": "s000002000", "fact": "The moving ball is inside the goal."}]}
    play = {"start_frame": "s000000000", "end_frame": "s000003000", "people": people, "actions": [action], "questions": []}
    return manifest, packet, {"plays": [play]}


def test_shared_profile_cannot_invent_references_or_change_source_frames():
    manifest, _, _ = fixture()
    manifest["references"] = [{"reference_id": "r1"}]
    profile = {"identity_clear": True, "appearance": "Visible white kit and light hair",
               "canonical_reference_ids": ["r1"]}
    reused = p.apply_identity_profile(manifest, profile)
    assert reused["frames"] == manifest["frames"]
    assert reused["packets"][0]["frame_ids"] == manifest["packets"][0]["frame_ids"]
    assert "identity_profile" not in manifest
    profile["canonical_reference_ids"] = ["invented"]
    with pytest.raises(ValueError, match="IDENTITY_PROFILE_UNRESOLVED"):
        p.apply_identity_profile(manifest, profile)


def test_unclear_identity_profile_does_not_silently_choose_a_player():
    manifest, _, _ = fixture()
    manifest["references"] = [{"reference_id": "r1"}]
    with pytest.raises(ValueError, match="IDENTITY_PROFILE_UNRESOLVED"):
        p.apply_identity_profile(manifest, {"identity_clear": False, "appearance": "Two different players",
                                          "canonical_reference_ids": ["r1"]})


def resolved(data=None):
    manifest, packet, original = fixture()
    return p.resolve_response(data or original, manifest, packet, {"origin": "SYNTHETIC_TEST_ONLY"})


def test_direct_assist_credits_passer_not_receivers_goal():
    r = p.reconcile([resolved()])
    assert r["counts"] == {"ASSIST": 1}
    assert r["target_events"][0]["actor"] == "passer"


@pytest.mark.parametrize("field,value", [("same_active_ball", False), ("continuous_play", False),
    ("receiver_is_teammate", None), ("receiver_frame", "not_supplied"), ("shot_frame", None), ("finisher", "another_person")])
def test_missing_causal_link_does_not_become_assist(field, value):
    _, _, data = fixture(); data["plays"][0]["actions"][0][field] = value
    r = p.reconcile([resolved(data)])
    assert "ASSIST" not in r["counts"]
    assert any(q["reason"] == "RECEIVER" for q in r["questions"])


def test_both_participants_cannot_be_selected_person():
    _, _, data = fixture(); data["plays"][0]["people"][1].update(selected=True, reference_ids=["r1"])
    r = p.reconcile([resolved(data)])
    assert r["target_events"] == []
    assert any(q["reason"] == "IDENTITY_CONFLICT" for q in r["questions"])
    assert len(r["events"]) == 1  # retain the visible play for targeted attribution


def test_kit_contradiction_overrides_positive_target_label():
    _, _, data = fixture(); data["plays"][0]["people"][0]["kit_consistent"] = False
    assert p.reconcile([resolved(data)])["target_events"] == []


def test_opponent_receipt_preserves_incomplete_pass():
    _, _, data = fixture(); data["plays"][0]["actions"][0]["receiver_is_teammate"] = False
    e = p.reconcile([resolved(data)])["target_events"][0]
    assert (e["event_type"], e["outcome"]) == ("PASS", "INCOMPLETE")


def shot(outcome="GOAL"):
    _, _, data = fixture(); a = data["plays"][0]["actions"][0]
    a.update(kind="SHOT", outcome=outcome, end_frame="s000003000")
    return data


def test_spare_ball_without_active_ball_continuity_is_not_goal():
    data = shot(); data["plays"][0]["actions"][0]["same_active_ball"] = None
    assert p.reconcile([resolved(data)])["target_events"] == []


def test_keeper_dive_without_outcome_evidence_does_not_verify_save():
    data = shot("SAVED"); data["plays"][0]["actions"][0]["outcome_evidence"] = []
    assert p.reconcile([resolved(data)])["target_events"] == []


def test_save_does_not_need_separate_native_ball_or_keeper_boxes():
    e = p.reconcile([resolved(shot("SAVED"))])["target_events"][0]
    assert (e["event_type"], e["outcome"]) == ("SHOT", "SAVED")


def test_outcome_after_contact_must_be_chronological():
    data = shot(); data["plays"][0]["actions"][0]["outcome_frame"] = "s000000750"
    assert p.reconcile([resolved(data)])["target_events"] == []


def test_source_frame_outside_packet_does_not_become_evidence():
    _, _, data = fixture(); data["plays"][0]["actions"][0]["actor_evidence_frames"] = ["s000999999"]
    r = resolved(data)
    assert not r["events"] and r["invalid_rows"]


def test_two_observations_of_terminal_goal_merge_despite_contact_disagreement():
    a, b = resolved(shot()), resolved(shot())
    b["events"][0].update(event_id="different", contact_ms=1500, source_packet_ids=["second"])
    r = p.reconcile([a, b])
    assert r["counts"] == {"GOAL": 1}
    assert r["target_events"][0]["contact_interval_ms"] == [1000, 1500]
    assert len(r["target_events"][0]["receipts"]) == 2


def test_different_rebound_shots_are_retained():
    a, b = resolved(shot("SAVED")), resolved(shot("GOAL"))
    b["events"][0].update(event_id="rebound", start_ms=2500, contact_ms=3000, outcome_ms=4000, end_ms=5000)
    assert p.reconcile([a, b])["counts"] == {"SHOT": 1, "GOAL": 1}


def test_fast_rebound_is_not_a_conflict_just_because_outcomes_are_close():
    a, b = resolved(shot("SAVED")), resolved(shot("GOAL"))
    b["events"][0].update(event_id="rebound", contact_ms=1500, outcome_ms=2125)
    assert p.reconcile([a, b])["counts"] == {"SHOT": 1, "GOAL": 1}


def test_conflict_cannot_be_settled_by_third_initial_opinion():
    r = p.reconcile([resolved(shot("SAVED")), resolved(shot("GOAL")), resolved(shot("GOAL"))])
    assert r["counts"] == {} and r["conflicts"]


def test_specific_followup_can_settle_conflict_and_keep_provenance():
    followup = resolved(shot("SAVED")); followup["events"][0]["review_phase"] = "FOLLOWUP"
    r = p.reconcile([resolved(shot("SAVED")), resolved(shot("GOAL")), followup])
    assert r["counts"] == {"SHOT": 1} and not r["conflicts"]
    assert r["target_events"][0]["superseded_observations"]


def test_packets_cover_entire_source_and_keep_context_overlap():
    jobs = p.plan_packets(76748)
    assert [(j["start_ms"], j["end_ms"]) for j in jobs] == [(0, 30000), (24000, 54000), (48000, 76748)]
    assert all(a["end_ms"] - b["start_ms"] == 6000 for a, b in zip(jobs, jobs[1:]))


def test_missing_link_review_keeps_full_play_and_aftermath():
    manifest, _, _ = fixture()
    r = p.reconcile([resolved(shot("UNKNOWN"))])
    jobs = p.followup_plan(manifest, r)
    assert len(jobs) == 1 and jobs[0]["start_ms"] == 0 and jobs[0]["end_ms"] == 8000
    assert jobs[0]["question"]["reason"] == "OUTCOME"


def test_no_generic_second_read_for_complete_assist():
    manifest, _, _ = fixture()
    assert p.followup_plan(manifest, p.reconcile([resolved()])) == []


def test_wider_packet_already_answered_outcome_does_not_trigger_another_call():
    manifest, _, _ = fixture()
    initial = resolved(shot("UNKNOWN")); later = resolved(shot("SAVED"))
    later["events"][0].update(source_packet_ids=["wider"], source_action_keys=["wider:0:a1"])
    merged = p.reconcile([initial, later])
    assert merged["counts"] == {"SHOT": 1}
    assert p.followup_plan(manifest, merged) == []


def test_original_taps_drop_derived_colours_and_legacy_target_labels():
    row = {"t": 2., "box": {"x": .2, "y": .3, "w": .1, "h": .2}, "target_point": {"x": .25, "y": .4},
           "jersey_name": "navy blue", "global_target_id": "wrong"}
    taps = p.original_taps({"raw_marker_anchors": json.dumps(json.dumps([row]))})
    assert "jersey_name" not in taps[0] and "global_target_id" not in taps[0]


def test_positive_reference_match_cannot_silently_deny_identity_in_consensus_mode():
    manifest, packet, _ = fixture()
    manifest["reference_policy"] = "CONSENSUS_RAW"
    observation = shot("GOAL")
    observation["plays"][0]["people"][0]["selected"] = False
    result = p.resolve_response(observation, manifest, packet, {"origin": "SYNTHETIC_TEST_ONLY"})
    assert result["events"][0]["selected_player"] is None
    assert any(q["reason"] == "IDENTITY" for q in result["questions"])
    assert not p.reconcile([result])["target_events"]


def test_consensus_delivery_excludes_automatic_mask_images_but_keeps_original_crop():
    manifest, packet, _ = fixture()
    manifest["reference_policy"] = "CONSENSUS_RAW"
    reference = {"reference_id": "r1", "media_ms": 0, "path": "original-human-crop.jpg", "sha256": "original",
                 "box": {"x": .2, "y": .3, "w": .1, "h": .2}, "target_point": {"x": .25, "y": .4}}
    manifest["references"] = [reference]
    packet["frame_ids"] = []
    reference["masked_view"] = {"path": "wrong-neighbour-mask.jpg", "sha256": "untrusted"}
    items = p.packet_items(manifest, packet)
    assert any(i.get("path") == reference["path"] for i in items)
    assert not any(i.get("path") == "wrong-neighbour-mask.jpg" for i in items)


def test_visual_packet_boundaries_follow_changed_pixels_and_cover_every_frame(tmp_path):
    import cv2
    import numpy as np
    frames = []
    for index in range(29):
        path = tmp_path / f"{index}.jpg"
        colour = (0, 0, 220) if index < 8 else (220, 0, 0) if index < 18 else (0, 220, 0)
        assert cv2.imwrite(str(path), np.full((80, 60, 3), colour, dtype=np.uint8))
        frames.append({"frame_id": f"f{index}", "media_ms": index * 500, "path": str(path)})
    packets, audit = p.plan_visual_packets(frames, frames[-1]["media_ms"])
    assert [c["media_ms"] for c in audit["changes"]] == [4000, 9000]
    assert all(any(j["start_ms"] <= f["media_ms"] <= j["end_ms"] for j in packets) for f in frames)
    for f in frames:
        f["media_ms"] += 1000
    _packets, shifted = p.plan_visual_packets(frames, frames[-1]["media_ms"])
    assert [c["media_ms"] for c in shifted["changes"]] == [5000, 10000]


def test_reference_matching_uses_buildup_without_changing_contact_time():
    r = p.reconcile([resolved()])
    case = {"case_id": "held_out", "reference_ms": 600, "expected_type": "ASSIST", "expected_outcome": "TEAMMATE_GOAL", "tolerance_ms": 0}
    result = p.assess_reference_cases([case], r)
    assert result["all_reference_cases_matched"]
    assert result["cases"][0]["observed_contact_ms"] == 1000


def test_expected_reference_file_never_enters_preparation_or_request_code():
    import inspect
    assert "assess_reference_cases" not in inspect.getsource(p.prepare)
    assert "reference_ms" not in p.PROMPT and "23680" not in p.PROMPT
    assert "reference_ms" not in inspect.getsource(p.packet_items)


def image_item(tmp_path):
    image = tmp_path / "frame.jpg"; image.write_bytes(b"test-jpeg")
    return {"type": "image", "path": str(image), "sha256": hashlib.sha256(b"test-jpeg").hexdigest()}


@pytest.mark.parametrize("provider", ["gemini", "emergent"])
def test_gemini3_uses_its_supported_reasoning_and_temperature_defaults(provider):
    _, body, _ = t.build_request(provider, "gemini-3.1-pro-preview", [{"type": "text", "text": "observe"}], reasoning_effort="low")
    body = json.loads(body)
    config = body["generationConfig"] if provider == "gemini" else body
    assert "temperature" not in config
    if provider == "gemini":
        assert config["thinkingConfig"] == {"thinkingLevel": "LOW"}
    else:
        assert body["model"] == "gemini/gemini-3.1-pro-preview"
        assert body["reasoning_effort"] == "low"


@pytest.mark.parametrize("provider", ["gemini", "emergent"])
def test_model_detail_setting_is_distinct_from_source_image_bytes(tmp_path, provider):
    item = image_item(tmp_path)
    _, standard, a = t.build_request(provider, "gemini-2.5-pro", [item])
    _, detailed, b = t.build_request(provider, "gemini-2.5-pro", [item], image_detail="high")
    assert a["images"] == b["images"]
    assert a["requested_image_detail"] is None and b["requested_image_detail"] == "high"
    body = json.loads(detailed)
    if provider == "gemini":
        assert body["generationConfig"]["mediaResolution"] == "MEDIA_RESOLUTION_HIGH"
        assert "mediaResolution" not in json.loads(standard)["generationConfig"]
    else:
        assert body["messages"][0]["content"][0]["image_url"]["detail"] == "high"
        assert "detail" not in json.loads(standard)["messages"][0]["content"][0]["image_url"]


@pytest.mark.parametrize("provider", ["gemini", "emergent"])
def test_both_adapters_deliver_all_images_as_explicit_ordered_parts(tmp_path, provider):
    item = image_item(tmp_path)
    _url, body, audit = t.build_request(provider, "gemini-2.5-pro", [{"type": "text", "text": "source time 125ms"}, item])
    wire = json.loads(body)
    assert audit["explicit_image_count"] == 1
    assert "videoMetadata" not in body.decode() and "video_url" not in body.decode()
    parts = wire["contents"][0]["parts"] if provider == "gemini" else wire["messages"][0]["content"]
    assert len(parts) == 2


def test_modified_prepared_image_stops_before_network(tmp_path):
    item = image_item(tmp_path); Path(item["path"]).write_bytes(b"changed")
    with pytest.raises(ValueError, match="PREPARED_IMAGE_CHANGED"):
        t.build_request("gemini", "gemini-2.5-pro", [item])


def test_oversized_request_is_rejected_without_silently_dropping_frames(tmp_path, monkeypatch):
    monkeypatch.setattr(t, "MAX_REQUEST_BYTES", 10)
    with pytest.raises(ValueError, match="REQUEST_IMAGE_BUDGET_EXCEEDED"):
        t.build_request("gemini", "gemini-2.5-pro", [image_item(tmp_path)])


def test_truncated_model_reply_is_not_accepted():
    with pytest.raises(ValueError, match="INCOMPLETE_MODEL_RESPONSE"):
        t.extract_reply("gemini", {"candidates": [{"finishReason": "MAX_TOKENS"}]})


def stall_worker(connection, job, provider, model, timeout_s):
    time.sleep(30)


def denied_worker(connection, job, provider, model, timeout_s):
    connection.send({"packet_id": job["packet_id"], "status": "ERROR", "error": "MODEL_ACCESS_DENIED"})
    connection.close()


def test_access_denied_stops_queued_work_without_alternate_route():
    result = t.run_jobs([{"packet_id": "first"}, {"packet_id": "second"}], "gemini", "gemini-2.5-pro",
                       deadline=time.monotonic() + 5, workers=1, worker=denied_worker)
    assert result[0]["error"] == "MODEL_ACCESS_DENIED"
    assert result[1]["status"] == "NOT_SENT"


def test_wall_deadline_kills_real_worker_process():
    before = {c.pid for c in multiprocessing.active_children()}
    started = time.monotonic()
    result = t.run_jobs([{"packet_id": "timeout"}], "gemini", "gemini-2.5-pro",
                       deadline=started + .4, per_call_s=.3, worker=stall_worker)
    assert time.monotonic() - started < 3
    assert result[0]["error"] == "MODEL_WALL_DEADLINE_EXCEEDED"
    assert {c.pid for c in multiprocessing.active_children()} == before


def test_no_model_key_does_not_fake_success_or_use_historical_answers(tmp_path, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    manifest, _, _ = fixture(); path = tmp_path / "manifest.json"; p.write_json(path, manifest)
    result = run(path, tmp_path / "run")
    assert result["status"] == "MODEL_KEY_NOT_CONFIGURED"
    assert result["model_jobs"] == [] and result["target_events"] == []


def source_export(tmp_path):
    """Small actual CFR file to exercise decoder PTS, crops and checksums."""
    import cv2
    import numpy as np
    root = tmp_path / "export"; (root / "video").mkdir(parents=True)
    video = root / "video" / "source.mp4"
    writer = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*"mp4v"), 20., (96, 160))
    assert writer.isOpened()
    for i in range(16):
        frame = np.zeros((160, 96, 3), dtype=np.uint8)
        frame[:, :, 1] = 90
        frame[50:100, 20+i:40+i] = 240
        writer.write(frame)
    writer.release()
    tap = {"t": .15, "box": {"x": .2, "y": .3, "w": .3, "h": .4},
           "target_point": {"x": .3, "y": .4}, "player_behind": True,
           "exclude_points": [{"x": .45, "y": .5}],
           "visible_mask": {"width": 96, "height": 192, "runs": [0, 96*192]}}
    p.write_json(root / "anchors.json", {"raw_marker_anchors": json.dumps([tap])})
    (root / "SHA256SUMS").write_text("\n".join(f"{p.digest(file)}  {file.relative_to(root).as_posix()}"
        for file in (video, root / "anchors.json")) + "\n")
    return root


def test_actual_decoder_preparation_retains_taps_masks_and_source_clock(tmp_path):
    root = source_export(tmp_path)
    manifest = p.prepare(root, tmp_path / "prepared", fps=8, max_edge=768)
    assert manifest["input_coverage"]["decoded_source_frames"] == 16
    assert manifest["input_coverage"]["complete"]
    assert manifest["input_coverage"]["max_sample_gap_ms"] <= 150
    assert manifest["model_calls"] == manifest["detector_forwards"] == 0
    ref = manifest["references"][0]
    assert ref["media_ms"] == 150 and ref["target_point"] == {"x": .3, "y": .4}
    assert ref["masked_view"] and ref["selection_hints"]["player_behind"]
    assert ref["selection_hints"]["exclude_points"] == [{"x": .45, "y": .5}]


def test_changed_source_checksum_stops_before_sampling(tmp_path):
    root = source_export(tmp_path)
    (root / "anchors.json").write_text("{}")
    with pytest.raises(ValueError, match="SOURCE_INPUT_CHECKSUM_MISMATCH"):
        p.prepare(root, tmp_path / "prepared")


def test_oversized_packet_does_not_prevent_other_packet_from_running(tmp_path, monkeypatch):
    root = source_export(tmp_path)
    manifest = p.prepare(root, tmp_path / "prepared")
    second = deepcopy(manifest["packets"][0]); second["packet_id"] = "second"
    manifest["packets"].append(second)
    p.write_json(tmp_path / "prepared" / "manifest.json", manifest)
    original, attempts, executed = t.build_request, [], []
    def preflight(*args, **kwargs):
        attempts.append(True)
        if len(attempts) == 1:
            raise ValueError("REQUEST_IMAGE_BUDGET_EXCEEDED")
        return original(*args, **kwargs)
    def jobs(rows, *args, **kwargs):
        executed.extend(r["packet_id"] for r in rows)
        return [{"packet_id": r["packet_id"], "status": "COMPLETED", "raw_response": '{"plays":[]}',
                 "payload_sha256": "synthetic", "response_sha256": "synthetic",
                 "origin": "SYNTHETIC_TEST_ONLY"} for r in rows]
    monkeypatch.setenv("GEMINI_API_KEY", "SYNTHETIC_TEST_ONLY")
    monkeypatch.setattr(t, "build_request", preflight)
    monkeypatch.setattr(t, "run_jobs", jobs)
    result = run(tmp_path / "prepared" / "manifest.json", tmp_path / "result", max_followups=0)
    assert executed == ["second"]
    assert result["status"] == "PARTIAL_MODEL_RUN"
    assert result["model_jobs_completed"] == 1
    assert result["model_jobs"][0]["error"] == "REQUEST_IMAGE_BUDGET_EXCEEDED"


def test_targeted_detail_adds_real_frames_without_rebuilding_identity(tmp_path):
    root = source_export(tmp_path)
    manifest = p.prepare(root, tmp_path / "prepared", fps=4)
    question = {"reason": "OUTCOME", "start_ms": 0, "end_ms": 750, "focus_ms": 350, "source_packet_id": "sequence_001"}
    jobs = p.followup_plan(manifest, {"questions": [question]})
    enriched, jobs = p.prepare_followups(manifest, jobs, tmp_path / "detail")
    assert len(enriched["frames"]) > len(manifest["frames"])
    assert all(f["media_ms"] % 50 == 0 for f in enriched["frames"])
    assert enriched["references"] == manifest["references"]
    assert len(jobs) == 1 and jobs[0]["round"] == 1


def test_runner_preserves_initial_observations_if_targeted_preparation_fails(tmp_path, monkeypatch):
    root = source_export(tmp_path)
    manifest = p.prepare(root, tmp_path / "prepared")
    ids = [f["frame_id"] for f in manifest["frames"]]
    raw = {"plays": [{"start_frame": ids[0], "end_frame": ids[-1],
        "people": [{"person_id": "one", "selected": True, "kit_consistent": True,
                    "reference_ids": ["r1"], "evidence_frames": [ids[0]]}],
        "actions": [{"action_id": "shot", "kind": "SHOT", "actor": "one", "start_frame": ids[0],
                     "contact_frame": ids[1], "end_frame": ids[-1], "actor_evidence_frames": [ids[0]], "outcome": "UNKNOWN"}]}]}
    def synthetic_jobs(jobs, *args, **kwargs):
        return [{"packet_id": j["packet_id"], "status": "COMPLETED", "raw_response": json.dumps(raw),
                 "origin": "SYNTHETIC_TEST_ONLY", "payload_sha256": "a"*64, "response_sha256": "b"*64} for j in jobs]
    def fail_detail(*args, **kwargs):
        raise TimeoutError("DETAIL_PREPARATION_TIME_BUDGET_EXHAUSTED")
    monkeypatch.setenv("GEMINI_API_KEY", "SYNTHETIC_TEST_ONLY")
    monkeypatch.setattr(t, "run_jobs", synthetic_jobs)
    monkeypatch.setattr(p, "prepare_followups", fail_detail)
    result = run(tmp_path / "prepared" / "manifest.json", tmp_path / "result")
    assert result["status"] == "EXPERIMENT_STOPPED"
    assert result["error_code"] == "DETAIL_PREPARATION_TIME_BUDGET_EXHAUSTED"
    assert len(result["events"]) == 1 and result["counts"] == {}
    assert result["independent_visual_correctness_verified"] is False
