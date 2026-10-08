import io
import numpy as np
import cv2
from PIL import Image
import pytest

from player_selection import selection_metadata, full_body_anchors, decode_mask, valid_mask, suggest_mask, tracking_preview, valid_image_shape
from unified_identity_authority import build_unified_identity_authority
from player_tracking import _masked_ncc, track_player

BOX = {"x": .3, "y": .2, "w": .2, "h": .4}


def test_partial_and_human_link_are_not_interpolated_into_hidden_proof():
    anchors = [{"t": 4, "box": BOX, "segment": 0, "visibility": "partial", "continuity": [
        {"t": 4.5, "box": BOX, "segment": 0, "same_player": True}]}]
    assert [a["t"] for a in full_body_anchors(anchors)] == [4.5]
    result = build_unified_identity_authority(anchors=anchors)
    points = {p["media_ms"]: p for p in result["target_points"]}
    assert set(points) == {4000, 4500}
    assert not points[4000]["proof_eligible"]
    assert not points[4000]["tap_authority"]
    assert points[4500]["proof_eligible"]


def test_cross_scene_distant_unconfirmed_and_partial_links_rejected():
    a = {"t": 4, "box": BOX, "segment": 0, "continuity": [
        {"t": 4.5, "box": BOX, "segment": 1, "same_player": True},
        {"t": 8, "box": BOX, "segment": 0, "same_player": True}]}
    assert "continuity" not in selection_metadata(a)
    for extras in ({"same_player": False}, {"visibility": "partial"}):
        a["continuity"] = [{"t": 4.5, "box": BOX, "segment": 0, "same_player": True, **extras}]
        assert "continuity" not in selection_metadata(a)


def test_opponent_negative_blocks_only_that_moment_not_whole_scene():
    opponent = {"x": .6, "y": .2, "w": .15, "h": .4}
    a = {"t": 4, "box": BOX, "exclude_points": [{"x": .65, "y": .3}]}
    track = {"points": [{"t": t, **opponent, "conf": .95} for t in [4, 5]]}
    result = build_unified_identity_authority(fix04_track=track, anchors=[a])
    assert not any(p["proof_eligible"] and p.get("box") == opponent and p["media_ms"] == 4000 for p in result["target_points"])
    assert any(p["proof_eligible"] and p["media_ms"] == 5000 for p in result["target_points"])


def test_overlap_is_partial_even_if_client_says_full():
    a = {"t": 4, "box": BOX, "exclude_points": [{"x": .4, "y": .3}]}
    assert selection_metadata(a)["visibility"] == "partial"
    assert not full_body_anchors([a])
    assert track_player("does-not-exist", [a])["seed_count"] == 0


def test_mask_validation_bounded_and_decoding_has_exact_area():
    mask = {"width": 96, "height": 192, "runs": [100, 50, 18282]}
    assert valid_mask(mask)
    assert np.count_nonzero(decode_mask(mask)) == 50
    for bad in ({**mask, "runs": [0, 999999]}, {**mask, "width": 100}, {**mask, "runs": [True, 18431]}, {**mask, "runs": [-1, 18433]}):
        assert not valid_mask(bad)
        assert decode_mask(bad) is None


def test_masked_ncc_ignores_background_and_stays_finite():
    rng = np.random.default_rng(4)
    target = rng.integers(0, 255, (24, 14), dtype=np.uint8)
    mask = np.zeros_like(target); mask[4:20, 4:10] = 255
    scene = rng.integers(0, 255, (70, 90), dtype=np.uint8)
    correct = rng.integers(0, 255, target.shape, dtype=np.uint8)
    correct[mask > 0] = target[mask > 0]
    wrong = target.copy(); wrong[mask > 0] = rng.integers(0, 255, np.count_nonzero(mask), dtype=np.uint8)
    scene[5:29, 5:19] = wrong; scene[35:59, 55:69] = correct
    scores = _masked_ncc(scene, target, mask)
    assert np.isfinite(scores).all()
    assert np.unravel_index(scores.argmax(), scores.shape) == (35, 55)
    assert scores[35, 55] > .99
    assert np.isfinite(_masked_ncc(np.zeros((40, 40), np.uint8), np.zeros_like(target), mask)).all()


def jpeg(array):
    out = io.BytesIO(); Image.fromarray(array).save(out, format="JPEG"); return out.getvalue()


def test_grabcut_suggestion_keeps_foreground_and_excludes_background():
    image = np.full((240, 160, 3), [35, 130, 35], np.uint8)
    image[45:190, 70:95] = [230, 230, 240]
    b = {"x": .35, "y": .1, "w": .35, "h": .8}
    result = suggest_mask(jpeg(image), b, {"x": .5, "y": .4}, [])
    assert result["status"] == "suggested"
    mask = decode_mask(result["mask"])
    assert mask[80, 40] > 0 and mask[80, 4] == 0
    assert np.count_nonzero(mask) < mask.size * .8


def test_preview_cannot_accept_partial_nonmonotonic_or_long_sequence():
    image = jpeg(np.zeros((100, 100, 3), np.uint8))
    for times, extras in (([0, .2, .4], {"visibility": "partial"}), ([0, .2, .1], {}), ([0, .2, 3], {})):
        with pytest.raises(ValueError):
            tracking_preview([image] * 3, times, {"box": BOX, **extras})


def test_decoded_image_dimensions_are_bounded_before_tracker_resizing():
    assert valid_image_shape(1080, 1920)
    for w, h in [(1, 3000000), (32, 4000), (5000, 32), (1920, 1920)]:
        assert not valid_image_shape(w, h)
    with pytest.raises(ValueError):
        suggest_mask(jpeg(np.zeros((4000, 32, 3), np.uint8)), BOX, {"x": .4, "y": .3}, [])


def test_partial_does_not_inherit_legacy_time_only_tap_authority():
    a = {"t": 4, "box": BOX, "visibility": "partial"}
    result = build_unified_identity_authority(fix04_track={"points": [{"t": 4.05, **BOX, "conf": .95}]}, anchors=[a])
    assert all(not p["tap_authority"] and not p["proof_eligible"] for p in result["target_points"])


def test_actual_frontend_serializer_preserves_hints_and_mask():
    import subprocess
    import json
    from pathlib import Path
    module = Path(__file__).resolve().parents[2] / "frontend/src/lib/anchorSerialization.mjs"
    a = {"t": 4.123, "box": BOX, "segment": 0, "visibility": "partial", "target_point": {"x": .4, "y": .3},
         "exclude_points": [{"x": .6, "y": .3}], "include_points": [{"x": .4, "y": .25}], "visible_mask": {"width": 96, "height": 192, "runs": [100, 50, 18282]},
         "continuity": [{"t": 4.5, "box": BOX, "segment": 0, "same_player": True}]}
    script = f"import {{ serializeMarkerAnchors }} from {json.dumps(module.as_uri())}; console.log(JSON.stringify(serializeMarkerAnchors(JSON.parse(process.argv[1]))));"
    result = json.loads(subprocess.check_output(["node", "--input-type=module", "-e", script, json.dumps([a])], text=True))[0]
    assert result["t"] == 4.12 and result["visibility"] == "partial"
    assert result["target_point"] == a["target_point"] and result["visible_mask"] == a["visible_mask"]
    assert result["include_points"] == a["include_points"]
    assert result["continuity"][0]["same_player"]
    assert selection_metadata(result)["continuity"][0]["t"] == 4.5


def test_human_mask_removes_opponent_pixels_from_identity_embedding(monkeypatch):
    import cv_shadow
    shape = (100, 20)
    monkeypatch.setattr(cv_shadow, "_comp_mask_crop", lambda frame, _: (frame, np.full(shape, 255, np.uint8), False, (0, 0)))
    owned = np.zeros(shape, np.uint8); owned[:, :10] = 255
    a = np.full((100, 20, 3), 240, np.uint8); b = a.copy()
    a[:, 10:] = (255, 0, 0); b[:, 10:] = (0, 0, 255)
    ea = cv_shadow._zone_embedding(a, (0, 0, 20, 100), 140, ownership_mask=owned)
    eb = cv_shadow._zone_embedding(b, (0, 0, 20, 100), 140, ownership_mask=owned)
    assert ea["owned"] and eb["owned"]
    for za, zb in zip(ea["zones"], eb["zones"]):
        np.testing.assert_array_equal(za, zb)
