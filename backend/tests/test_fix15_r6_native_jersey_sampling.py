"""Native crop selection improves inputs without asserting digits or identity."""
from copy import deepcopy
from pathlib import Path
import sys

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import dense_track_refinement as dense
import jersey_consensus as jersey
import fix10a_vision_providers as vision

SMALL = {"x": .2, "y": .2, "w": .05, "h": .1}
LARGE = {**SMALL, "w": .1, "h": .2}
GRAPH = {"touches": [{"player_track_id": "actor", "media_ms": 1100}]}


def row(ms=1000, box=SMALL, *, native=True, **quality):
    player = {"local_track_id": "actor", "box": deepcopy(box), "association_state": "VERIFIED_LOCAL"}
    if native:
        player["jersey_crop_quality"] = {"source": "NATIVE_TORSO_PIXELS", "width_px": 40,
                                       "height_px": 48, "sharpness": 40., "isolated": True,
                                       "canonical_identity_authority": False, **quality}
    return {"media_ms": ms, "time_authority": "ACTUAL_MEDIA_PTS", "used_fallback": False,
            "players": [player], "global_target": {"status": "UNRESOLVED", "proof_eligible": False}}


def test_measured_torso_can_be_reviewed_despite_small_share_of_portrait_frame():
    frame = row()
    before = deepcopy(frame)
    requests = jersey.select_jersey_review_requests([frame], GRAPH)
    assert len(requests) == 1
    assert requests[0]["expected_jersey_number"] is None
    assert frame == before
    assert frame["global_target"]["proof_eligible"] is False


def test_legacy_records_keep_existing_area_gate_and_order():
    assert jersey.select_jersey_review_requests([row(native=False)], GRAPH) == []
    frames = [row(ms, LARGE, native=False) for ms in (1400, 1000, 1200)]
    requests = jersey.select_jersey_review_requests(frames, GRAPH)
    assert [r["media_ms"] for r in requests] == [1000, 1200, 1400]


@pytest.mark.parametrize("quality", [
    {"width_px": 31}, {"height_px": 39}, {"sharpness": 11.99}, {"isolated": False},
    {"width_px": True}, {"height_px": "48"}, {"sharpness": float("nan")},
    {"sharpness": float("inf")}, {"source": "MODEL_INFERRED"}, {"isolated": 1},
])
def test_bad_measured_crop_cannot_fall_back_to_large_area(quality):
    assert jersey.select_jersey_review_requests([row(box=LARGE, **quality)], GRAPH) == []


@pytest.mark.parametrize("extra", [{"used_fallback": True}, {"time_authority": "FRAME_INDEX_FPS_FALLBACK"},
                                  {"time_authority": None}, {"media_ms": float("nan")},
                                  {"media_ms": float("inf")}])
def test_untrusted_or_nonfinite_time_cannot_admit_native_crop(extra):
    frame = {**row(box=LARGE), **extra}
    assert jersey.select_jersey_review_requests([frame], GRAPH) == []


def test_hypothesis_or_uninvolved_player_cannot_acquire_review_identity():
    frame = row()
    frame["players"][0]["association_state"] = "HYPOTHESES"
    assert jersey.select_jersey_review_requests([frame], GRAPH) == []
    assert jersey.select_jersey_review_requests([row()], {"touches": []}) == []


def test_temporal_bands_do_not_spend_all_reads_on_largest_late_crop():
    frames = [row(1000 + index * 200, sharpness=20. + index) for index in range(10)]
    requests = jersey.select_jersey_review_requests(frames, GRAPH)
    times = sorted(r["media_ms"] for r in requests)
    assert len(requests) == jersey.MAX_REVIEW_FRAMES
    assert any(t <= 1400 for t in times)
    assert any(t >= 2400 for t in times)
    assert all(b - a >= jersey.MIN_TEMPORAL_SEPARATION_MS for a, b in zip(times, times[1:]))
    assert requests[0]["media_ms"] == 2800


def test_merge_preserves_native_selection_instead_of_reordering_by_touch_distance():
    ordinary = jersey.select_jersey_review_requests([row(1000), row(1800, sharpness=90)], GRAPH)
    assert ordinary[0]["media_ms"] == 1800
    merged = jersey.merge_jersey_review_requests([], ordinary, GRAPH)
    assert merged[0]["media_ms"] == 1800
    assert all(r["expected_jersey_number"] is None for r in merged)


def test_independent_pixel_inspection_still_precedes_ordinary_crops():
    ordinary = jersey.select_jersey_review_requests([row(1000), row(1400)], GRAPH)
    pixel = [{"track_id": "actor", "media_ms": 1800, "box": deepcopy(SMALL)}]
    merged = jersey.merge_jersey_review_requests(pixel, ordinary, GRAPH)
    assert merged[0]["media_ms"] == 1800
    assert merged[0]["pixel_selected"] is True


def test_provider_budget_and_physically_involved_actor_priority_unchanged(monkeypatch):
    ordinary = jersey.select_jersey_review_requests([row(1000), row(1400)], GRAPH)
    pixels = [{"track_id": f"bystander{i}", "media_ms": 2000, "box": deepcopy(LARGE)} for i in range(30)]
    merged = jersey.merge_jersey_review_requests(pixels, ordinary, GRAPH)
    monkeypatch.setattr(vision, "MAX_JERSEY_REQUESTS", 2)
    results = vision.ShadowVisionProviders(None, "offline").jersey_vote_provider("unused", merged)
    assert set(results) == {"actor"}
    assert all(v["readable"] is False for values in results.values() for v in values)


def test_repeated_or_nearby_frames_do_not_fill_independent_read_slots():
    requests = jersey.select_jersey_review_requests([row(ms) for ms in (1000, 1000, 1017, 1400)], GRAPH)
    assert len(requests) == 2
    assert len({r["media_ms"] for r in requests}) == 2


def test_small_cv_image_cannot_claim_upscaled_or_original_pixel_support(monkeypatch):
    monkeypatch.setattr(dense.uia, "resolve_target_at", lambda *_a, **_k: (None, "UNRESOLVED"))
    image = np.indices((100, 100)).sum(axis=0).astype(np.uint8) % 2 * 255
    frame = {"media_ms": 1000, "frame_bgr": np.repeat(image[:, :, None], 3, axis=2),
             "time_authority": "ACTUAL_MEDIA_PTS", "used_fallback": False,
             "source_width": 8000, "source_height": 8000}
    out = dense.refine_window([frame], {}, {}, "s", detector_fn=lambda _f: ([{"box": LARGE}], []))
    quality = out["frames"][0]["players"][0]["jersey_crop_quality"]
    assert quality["width_px"] < jersey.MIN_TORSO_WIDTH_PX
    assert quality["height_px"] < jersey.MIN_TORSO_HEIGHT_PX
    assert quality["canonical_identity_authority"] is False


def test_overlap_is_measured_against_all_native_bodies():
    gray = np.zeros((400, 400), np.uint8)
    first = {"box": LARGE}
    other = {"box": {**LARGE, "x": .21}}
    assert dense._jersey_crop_quality(gray, first, [first, other])["isolated"] is False


def test_selection_cues_cannot_supply_jersey_votes_or_upgrade_target():
    frame = row()
    requests = jersey.select_jersey_review_requests([frame], GRAPH)
    assert requests and requests[0]["expected_jersey_number"] is None
    result = jersey.apply_jersey_consensus([frame], GRAPH, {})
    assert result["consensus_by_track"] == {}
    assert result["window_evidence"][0]["global_target"] == frame["global_target"]
