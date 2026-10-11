"""Native kit conflicts reject body swaps; colour never supplies identity."""
from copy import deepcopy
from pathlib import Path
import sys

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import dense_track_refinement as dense

BOX = {"x": .3, "y": .2, "w": .1, "h": .3}
WHITE = [128., 128.]
BLUE = [132., 100.]
IDENTITY = np.array([[1., 0., 0.], [0., 1., 0.]])


def detection(chroma=WHITE, box=BOX):
    return {"box": deepcopy(box), "confidence": .9, "kit_chroma": deepcopy(chroma)}


def frame(ms, **extra):
    return {"media_ms": ms, "scene_id": "s", "frame_bgr": np.zeros((100, 100, 3), np.uint8),
            "used_fallback": False, "time_authority": "ACTUAL_MEDIA_PTS", **extra}


def refine(monkeypatch, detections, times=None, **frame_extras):
    monkeypatch.setattr(dense.uia, "resolve_target_at", lambda *_a, **_k: (None, "UNRESOLVED"))
    rows = iter(detections)
    times = times or [index * 133 for index in range(len(detections))]
    return dense.refine_window([frame(ms, **frame_extras) for ms in times], {}, {}, "s",
                              detector_fn=lambda _image: (next(rows), []),
                              camera_estimator=lambda *_a: (IDENTITY, 20))


def reference(times=(0, 133, 266), chromas=None):
    chromas = chromas or [WHITE] * len(times)
    return {"_local_kit_history": [{"media_ms": t, "chroma": deepcopy(c)} for t, c in zip(times, chromas)]}


def test_stable_native_kit_rejects_opponent_inheriting_same_local_id(monkeypatch):
    out = refine(monkeypatch, [[detection()]] * 3 + [[detection(BLUE)]])
    frames = out["frames"]
    old_id = frames[0]["players"][0]["local_track_id"]
    assert all(f["players"][0]["local_track_id"] == old_id for f in frames[:3])
    assert frames[3]["players"][0]["local_track_id"] != old_id
    assert frames[3]["players"][0]["association_state"] == "NEW_LOCAL_TRACK"
    rejected = frames[3]["local_kit_association_rejections"]
    assert len(rejected) == 1
    assert rejected[0]["local_track_id"] == old_id
    assert rejected[0]["canonical_identity_authority"] is False
    assert out["metrics"]["local_kit_association_rejections"] == 1


def test_colour_can_reject_but_never_upgrade_global_target(monkeypatch):
    out = refine(monkeypatch, [[detection()]] * 4)
    assert all(f["global_target"]["status"] == "UNRESOLVED" for f in out["frames"])
    assert all(f["global_target"]["proof_eligible"] is False for f in out["frames"])
    assert not any(f["local_kit_association_rejections"] for f in out["frames"])


def test_same_kit_equal_body_alternatives_remain_ambiguous(monkeypatch):
    left, right = {**BOX, "x": .295}, {**BOX, "x": .305}
    out = refine(monkeypatch, [[detection()]] * 3 + [[detection(WHITE, left), detection(WHITE, right)]])
    bodies = out["frames"][-1]["players"]
    assert len(bodies) == 2
    assert all(b["association_state"] == "HYPOTHESES" for b in bodies)
    assert all(b["local_track_id"] is None for b in bodies)


def test_incompatible_alternative_removed_without_changing_geometric_gate(monkeypatch):
    out = refine(monkeypatch, [[detection()]] * 3 + [[detection(BLUE), detection(WHITE)]])
    last = out["frames"][-1]
    old_id = out["frames"][0]["players"][0]["local_track_id"]
    assert next(b for b in last["players"] if b["kit_chroma"] == WHITE)["local_track_id"] == old_id
    assert next(b for b in last["players"] if b["kit_chroma"] == BLUE)["local_track_id"] != old_id
    assert last["global_target"]["status"] == "UNRESOLVED"


def test_same_kit_far_body_still_cannot_steal_local_id(monkeypatch):
    far = {**BOX, "x": .8}
    out = refine(monkeypatch, [[detection()]] * 3 + [[detection(WHITE, far)]])
    assert out["frames"][-1]["players"][0]["local_track_id"] != out["frames"][0]["players"][0]["local_track_id"]


@pytest.mark.parametrize("times", [(0,), (0, 133), (0, 17, 34), (0, 0, 133)])
def test_insufficient_or_non_independent_reference_cannot_reject(times):
    assert dense._local_kit_conflict(reference(times), detection(BLUE), 400) is None


def test_unstable_reference_cannot_reject_another_colour():
    assert dense._local_kit_conflict(reference(chromas=[WHITE, BLUE, WHITE]), detection([180, 180]), 400) is None


def test_stale_history_cannot_reject_or_bridge_arbitrary_gaps():
    assert dense._local_kit_conflict(reference(), detection(BLUE), 1800) is None


@pytest.mark.parametrize("chroma", [None, [True, 128], [float("nan"), 128], [128], [300, 100]])
def test_missing_invalid_or_nonfinite_current_chroma_is_not_rejection(chroma):
    assert dense._local_kit_conflict(reference(), detection(chroma), 400) is None


@pytest.mark.parametrize("chroma", [[129, 127], [130, 124], [128, 110]])
def test_modest_colour_change_does_not_reject(chroma):
    assert dense._local_kit_conflict(reference(), detection(chroma), 400) is None


def test_history_requires_temporally_independent_measurements():
    track = {}
    det = detection()
    for ms in (0, 17, 34, 133, 150, 266):
        dense._update_local_kit_history(track, det, [det], ms, eligible=True)
    assert [r["media_ms"] for r in track["_local_kit_history"]] == [0, 133, 266]
    assert dense._local_kit_conflict(track, detection(BLUE), 400) is not None


def test_history_excludes_overlapping_body_crops():
    track = {}
    det, other = detection(), detection(BLUE, {**BOX, "x": .31})
    for ms in (0, 133, 266):
        dense._update_local_kit_history(track, det, [det, other], ms, eligible=True)
    assert "_local_kit_history" not in track


def test_fallback_time_cannot_establish_local_kit_reference(monkeypatch):
    out = refine(monkeypatch, [[detection()]] * 3 + [[detection(BLUE)]],
                 used_fallback=True, time_authority="FRAME_INDEX_FPS_FALLBACK")
    assert not any(f["local_kit_association_rejections"] for f in out["frames"])
    assert out["metrics"]["target_verified_frames"] == 0


def test_rejected_crop_does_not_replace_old_id_and_unproven_competitor_stays_ambiguous(monkeypatch):
    out = refine(monkeypatch, [[detection()]] * 3 + [[detection(BLUE)], [detection()]])
    old_id = out["frames"][0]["players"][0]["local_track_id"]
    body = out["frames"][-1]["players"][0]
    assert body["local_track_id"] is None
    assert body["association_state"] == "HYPOTHESES"
    assert old_id in body["candidate_local_track_ids"]
    assert len(out["frames"][3]["local_kit_association_rejections"]) == 1


def test_conflict_lookup_cannot_poison_the_measured_reference():
    track = reference()
    before = deepcopy(track)
    assert dense._local_kit_conflict(track, detection(BLUE), 400) is not None
    assert track == before


def test_moderate_measured_kit_change_stays_hypothesis_not_false_identity(monkeypatch):
    out = refine(monkeypatch, [[detection()]] * 3 + [[detection([128., 113.])]])
    last = out["frames"][-1]
    body = last["players"][0]
    assert body["association_state"] == "HYPOTHESES"
    assert body["local_track_id"] is None
    assert body["candidate_local_track_ids"] == [out["frames"][0]["players"][0]["local_track_id"]]
    assert last["local_kit_association_rejections"] == []
    assert len(last["local_kit_association_cautions"]) == 1
    assert last["global_target"]["proof_eligible"] is False


def test_moderate_colour_read_cannot_overwrite_accepted_geometry(monkeypatch):
    out = refine(monkeypatch, [[detection()]] * 3 + [[detection([128., 113.])], [detection()]])
    old_id = out["frames"][0]["players"][0]["local_track_id"]
    assert out["frames"][3]["players"][0]["local_track_id"] is None
    assert out["frames"][4]["players"][0]["local_track_id"] == old_id


def test_kit_uncertainty_preserves_other_admissible_body_ids(monkeypatch):
    other_box = {**BOX, "x": .45}
    moderate = [128., 113.]
    previous = [detection(), detection(moderate, other_box)]
    out = refine(monkeypatch, [previous] * 3 + [[detection(moderate, {**BOX, "x": .38})]])
    initial_ids = {p["local_track_id"] for p in out["frames"][0]["players"]}
    body = out["frames"][-1]["players"][0]
    assert body["local_track_id"] is None
    assert body["association_state"] == "HYPOTHESES"
    assert body["association_reason"] == "LOCAL_KIT_CONTINUITY_UNCERTAIN"
    assert set(body["candidate_local_track_ids"]) == initial_ids
    assert set(body["candidate_predicted_boxes"]) == initial_ids


def test_hard_cut_resets_local_id_and_appearance_reference(monkeypatch):
    monkeypatch.setattr(dense.uia, "resolve_target_at", lambda *_a, **_k: (None, "UNRESOLVED"))
    dets = iter([[detection()]] * 3 + [[detection(BLUE)]])
    frames = [frame(0), frame(133), frame(266), frame(400, cut=True)]
    out = dense.refine_window(frames, {}, {}, "s", detector_fn=lambda _f: (next(dets), []),
                              camera_estimator=lambda *_a: (IDENTITY, 20))
    assert out["frames"][-1]["cut_barrier"] is True
    assert out["frames"][-1]["players"][0]["local_track_id"] != out["frames"][0]["players"][0]["local_track_id"]
    assert out["frames"][-1]["local_kit_association_rejections"] == []
