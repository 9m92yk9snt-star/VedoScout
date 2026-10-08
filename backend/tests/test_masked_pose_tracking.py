"""Tilted foreground recovery and wrong-player safety, with real OpenCV.

Synthetic textured kits give known player positions without publishing match
frames. No model calls, database, downloaded weights or new human anchors.
"""
import cv2
import numpy as np
import pytest

from player_tracking import _cut_flags, _match_region, _pose_templates, _run_direction, MATCH_MIN


W, H = 480, 270
X, Y, BW, BH = 200, 92, 64, 104
BOX = [X, Y, X + BW, Y + BH]


def scene_factory():
    rng = np.random.default_rng(2026)
    background = cv2.GaussianBlur(rng.integers(20, 160, (H, W, 3), dtype=np.uint8), (11, 11), 0)
    mask = np.zeros((BH, BW), np.uint8); mask[20:84, 16:48] = 255
    kit = np.full((BH, BW, 3), (30, 30, 220), np.uint8)
    kit = np.clip(kit.astype(int) + rng.integers(-65, 66, (BH, BW, 1)), 0, 255).astype(np.uint8)

    def frame(time, angle=0, dx=0, wrong_kit=False, rival=None, absent=False, new_scene=False):
        bgr = np.full_like(background, 245) if new_scene else background.copy()
        transform = cv2.getRotationMatrix2D((BW / 2, BH / 2), angle, 1)
        moved = cv2.warpAffine(kit, transform, (BW, BH))
        owned = cv2.warpAffine(mask, transform, (BW, BH), flags=cv2.INTER_NEAREST)
        if wrong_kit:
            moved = moved[:, :, ::-1]
        if not absent:
            roi = bgr[Y:Y + BH, X + dx:X + dx + BW]; roi[owned > 0] = moved[owned > 0]
        if rival is not None:
            transform = cv2.getRotationMatrix2D((BW / 2, BH / 2), -angle, 1)
            other = cv2.warpAffine(kit, transform, (BW, BH))
            other_mask = cv2.warpAffine(mask, transform, (BW, BH), flags=cv2.INTER_NEAREST)
            roi = bgr[Y:Y + BH, X + rival:X + rival + BW]; roi[other_mask > 0] = other[other_mask > 0]
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        hsv = cv2.cvtColor(cv2.resize(bgr, (240, 135)), cv2.COLOR_BGR2HSV)
        tiny = cv2.resize(gray, (160, 90)).astype(np.float32)
        return time, gray, hsv, tiny

    return frame, mask


@pytest.mark.parametrize("angle", [-15, 15])
def test_failed_rigid_match_is_recovered_at_the_known_player_position(angle):
    frame, mask = scene_factory()
    seed, target = frame(0), frame(.12, angle, dx=4)
    template = seed[1][Y:Y + BH, X:X + BW]
    args = (target[1], template, BW, BH, BW, BH, X + BW / 2, Y + BH / 2, BW * 1.2, BH * 1.2)
    assert _match_region(*args, seed_mask=mask)[0] < MATCH_MIN
    out, doubts = {}, []
    _run_direction([seed, target], 0, BOX, out, 1, doubts, [False, False], seed_mask=mask)
    assert len(out) == 1 and not doubts
    point = out[.12]
    assert abs(point["x"] * W - (X + 4)) < 2 and abs(point["y"] * H - Y) < 2
    assert point["matching_method"] == "masked_pose" and point["pose_degrees"] == angle


def test_backward_recovery_uses_original_selected_pixels_too():
    frame, mask = scene_factory()
    frames = [frame(0, 15, dx=-8), frame(.12, -15, dx=-4), frame(.24)]
    out, doubts = {}, []
    _run_direction(frames, 2, BOX, out, -1, doubts, [False] * 3, seed_mask=mask)
    assert set(out) == {0, .12} and not doubts
    assert abs(out[0]["x"] * W - (X - 8)) < 2
    assert abs(out[.12]["x"] * W - (X - 4)) < 2


def test_warped_foreground_is_invariant_to_unselected_background_pixels():
    rng = np.random.default_rng(6)
    template = rng.integers(0, 255, (BH, BW), dtype=np.uint8)
    mask = np.zeros_like(template); mask[20:84, 16:48] = 255
    changed = template.copy(); changed[mask == 0] = 255 - changed[mask == 0]
    original, altered = list(_pose_templates(template, mask)), list(_pose_templates(changed, mask))
    assert len(original) == len(altered) == 5
    for (a, owned, angle), (b, other_owned, other_angle) in zip(original, altered):
        assert angle == other_angle and abs(angle) <= 15
        np.testing.assert_array_equal(owned, other_owned)
        np.testing.assert_array_equal(a[owned > 0], b[owned > 0])
        assert (owned > 0).sum() >= .9 * (mask > 0).sum()


def test_pose_search_cannot_increase_support_by_discarding_clipped_pixels():
    mask = np.full((BH, BW), 255, np.uint8)
    variants = list(_pose_templates(np.full_like(mask, 100), mask))
    for _, owned, _ in variants:
        assert (owned > 0).sum() >= .9 * mask.size
    assert len(variants) < 5


def test_similar_grayscale_wrong_kit_still_fails_colour_veto():
    frame, mask = scene_factory()
    frames = [frame(0)] + [frame(i * .12, 15, i * 4, wrong_kit=True) for i in range(1, 4)]
    out, doubts = {}, []
    _run_direction(frames, 0, BOX, out, 1, doubts, [False] * 4, seed_mask=mask)
    assert not out
    assert "kit-colour change" in doubts[0]["reason"]


@pytest.mark.parametrize("separation, reason", [(44, "overlap"), (64, "identity ambiguous")])
def test_rival_at_another_orientation_still_blocks_player_assignment(separation, reason):
    frame, mask = scene_factory()
    frames = [frame(0)] + [frame(i * .12, 15, i * 4, rival=separation) for i in range(1, 4)]
    out, doubts = {}, []
    _run_direction(frames, 0, BOX, out, 1, doubts, [False] * 4, seed_mask=mask)
    assert not out
    assert reason in doubts[0]["reason"]


def test_disappeared_player_is_not_filled_by_a_pose_hypothesis():
    frame, mask = scene_factory()
    frames = [frame(0)] + [frame(i * .12, absent=True) for i in range(1, 4)]
    out, doubts = {}, []
    _run_direction(frames, 0, BOX, out, 1, doubts, [False] * 4, seed_mask=mask)
    assert not out and "player lost" in doubts[0]["reason"]


def test_no_torso_colour_reference_prevents_pose_recovery_from_a_fragment():
    frame, mask = scene_factory()
    mask[:int(BH * .6)] = 0
    frames = [frame(0)] + [frame(i * .12, 15, i * 4) for i in range(1, 4)]
    out, doubts = {}, []
    _run_direction(frames, 0, BOX, out, 1, doubts, [False] * 4, seed_mask=mask)
    assert not out and "player lost" in doubts[0]["reason"]


def test_visible_similar_player_after_cut_cannot_be_rescued_into_continuity():
    frame, mask = scene_factory()
    frames = [frame(0), frame(.12, 15, dx=4, new_scene=True)]
    cuts = _cut_flags(frames)
    assert cuts == [False, True]
    out, doubts = {}, []
    _run_direction(frames, 0, BOX, out, 1, doubts, cuts, seed_mask=mask)
    assert not out and "scene cut" in doubts[0]["reason"]
