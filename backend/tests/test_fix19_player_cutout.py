"""Selection geometry, foreground exclusion and hidden-player proof safety."""
from io import BytesIO

import numpy as np
import pytest
from PIL import Image

import native_player_segmentation as native
import prompt_player_segmentation as prompt
from player_selection import decode_mask, selection_metadata, full_body_anchors
from unified_identity_authority import build_unified_identity_authority

BOX = {"x": .25, "y": .1, "w": .5, "h": .8}
POINT = {"x": .5, "y": .4}


def image_bytes():
    stream = BytesIO()
    Image.new("RGB", (100, 200), (40, 120, 40)).save(stream, "JPEG")
    return stream.getvalue()


def silhouette():
    mask = np.zeros((200, 100), np.uint8)
    mask[15:35, 45:55] = 1  # head
    mask[35:115, 30:70] = 1  # body/shirt
    mask[50:70, 15:85] = 1  # arms
    mask[115:185, 35:47] = 1
    mask[115:185, 53:65] = 1
    return mask


def instance(mask):
    return {"mask": mask, "box": (15, 15, 70, 170), "score": .9}


def pixel(result, x, y):
    b = result["box"]
    gx = min(95, max(0, int((x - b["x"]) / b["w"] * 96)))
    gy = min(191, max(0, int((y - b["y"]) / b["h"] * 192)))
    return bool(decode_mask(result["mask"])[gy, gx])


def test_clear_outline_retains_head_shirt_arms_and_legs(monkeypatch):
    monkeypatch.setattr(native, "_instances", lambda image: ([instance(silhouette())], "test-model"))
    result = native.suggest_person_cutout(image_bytes(), BOX, POINT)
    assert result["status"] == "suggested"
    for point in [(.5, .12), (.5, .4), (.2, .3), (.8, .3), (.41, .85), (.59, .85)]:
        assert pixel(result, *point)
    assert not pixel(result, .2, .8)  # grass stays background
    assert result["box"] != BOX  # fitted to measured outline
    assert result["mask"]["method"] == "native_person_instance"


@pytest.mark.parametrize("count,reason", [(0, "no_visible_person"), (2, "ambiguous_person")])
def test_missing_or_competing_people_never_get_a_guessed_mask(monkeypatch, count, reason):
    monkeypatch.setattr(native, "_instances", lambda image: ([instance(silhouette()) for _ in range(count)], "test-model"))
    result = native.suggest_person_cutout(image_bytes(), BOX, POINT)
    assert result == {"status": "unavailable", "reason": reason}


def test_shirt_only_outline_is_not_presented_as_a_full_player(monkeypatch):
    mask = np.zeros((200, 100), np.uint8); mask[65:100, 30:70] = 1
    monkeypatch.setattr(native, "_instances", lambda image: ([instance(mask)], "test-model"))
    result = native.suggest_person_cutout(image_bytes(), BOX, POINT)
    assert result == {"status": "unavailable", "reason": "partial_outline"}


def test_manual_area_is_kept_instead_of_auto_snapping(monkeypatch):
    monkeypatch.setattr(native, "_instances", lambda image: ([instance(silhouette())], "test-model"))
    result = native.suggest_person_cutout(image_bytes(), BOX, POINT, auto_box=False)
    assert result["box"] == BOX


def test_behind_keeps_area_and_visible_fragments_without_foreground(monkeypatch):
    visible = np.zeros((200, 100), np.uint8)
    visible[65:95, 40:60] = 1
    visible[140:175, 38:48] = 1  # disconnected visible leg
    calls = []

    def segmented(image, positives, negatives, bounds):
        calls.append((positives, negatives, bounds))
        return visible, {"encoder": "test-encoder", "decoder": "test-decoder"}

    monkeypatch.setattr(prompt, "segment_visible_player", segmented)
    result = native.suggest_person_cutout(image_bytes(), BOX, POINT, [{"x": .7, "y": .4}], player_behind=True)
    assert result["status"] == "suggested" and result["box"] == BOX
    assert result["player_behind"] and result["visible_only"]
    assert result["mask"]["method"] == "native_person_prompt"
    assert pixel(result, .5, .4) and pixel(result, .43, .8)
    assert not pixel(result, .7, .4)  # foreground person
    assert not pixel(result, .5, .6)  # hidden region is not filled
    assert calls == [([(50., 80.)], [(70., 80.)], (25, 20, 75, 180))]


def test_fully_hidden_player_has_no_mask(monkeypatch):
    monkeypatch.setattr(prompt, "segment_visible_player", lambda *args: (None, {}))
    assert native.suggest_person_cutout(image_bytes(), BOX, POINT, player_behind=True) == {
        "status": "unavailable", "reason": "behind_player_not_isolated"}


def test_include_hint_must_belong_to_the_same_visible_instance(monkeypatch):
    monkeypatch.setattr(native, "_instances", lambda image: ([instance(silhouette())], "test-model"))
    result = native.suggest_person_cutout(image_bytes(), BOX, POINT, include_points=[{"x": .9, "y": .8}])
    assert result["status"] == "unavailable" and "mask" not in result


def test_negative_foreground_instance_is_removed_as_a_whole(monkeypatch):
    target = silhouette()
    front = np.zeros_like(target); front[50:160, 60:80] = 1
    monkeypatch.setattr(native, "_instances", lambda image: ([instance(target), instance(front)], "test-model"))
    result = native.suggest_person_cutout(image_bytes(), BOX, POINT, [{"x": .75, "y": .4}], auto_box=False)
    assert result["status"] == "suggested"
    assert not pixel(result, .65, .3)  # whole front mask, not just clicked pixel
    assert pixel(result, .5, .4)


def test_behind_flag_cannot_create_full_body_or_hidden_identity_proof():
    anchor = {"t": 4, "box": BOX, "target_point": POINT, "player_behind": True}
    normalized = {**anchor, **selection_metadata(anchor)}
    assert normalized["visibility"] == "partial" and not full_body_anchors([anchor])
    result = build_unified_identity_authority(anchors=[normalized])
    assert result["target_points"]
    assert all(not p["proof_eligible"] and not p["tap_authority"] for p in result["target_points"])


def test_prompt_alternatives_must_respect_every_positive_and_negative():
    good = np.full((10, 10), -1., np.float32); good[2:8, 2:5] = 1
    wrong = good.copy(); wrong[5, 7] = 1
    result = prompt.choose_prompt_mask(np.stack([wrong, good]), [.99, .8], [(3, 5)], [(7, 5)])
    np.testing.assert_array_equal(result, good > 0)


def test_foreground_exclusion_uses_full_outline_instead_of_shirt_only():
    shirt = np.full((15, 10), -1., np.float32); shirt[2:7, 2:5] = 1
    body = shirt.copy(); body[7:14, 2:5] = 1
    result = prompt.choose_prompt_mask(np.stack([shirt, body]), [.95, .8], [(3, 5)], [(7, 5)], prefer_largest=True)
    np.testing.assert_array_equal(result, body > 0)


@pytest.mark.parametrize("score", [.49, np.nan, np.inf])
def test_weak_or_invalid_prompt_output_stays_unresolved(score):
    mask = np.ones((1, 10, 10), np.float32)
    assert prompt.choose_prompt_mask(mask, [score], [(3, 5)], []) is None


def test_invalid_model_asset_is_not_loaded(monkeypatch, tmp_path):
    path = tmp_path / "bad.onnx"; path.write_bytes(b"not the pinned model")
    monkeypatch.setattr(native, "MODEL_PATH", path)
    with pytest.raises(ValueError, match="checksum"):
        native.PersonSegmenter()


def test_native_request_requires_a_visible_human_point():
    with pytest.raises(ValueError, match="visible part"):
        native.suggest_person_cutout(image_bytes(), BOX, None, player_behind=True)
