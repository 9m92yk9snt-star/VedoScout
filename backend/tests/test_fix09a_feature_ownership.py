"""Pixels outside the selected body mask must never become identity proof."""
import numpy as np

import cv_shadow as cv


def test_hidden_zone_pixels_cannot_change_player_embedding(monkeypatch):
    mask = np.full((100, 20), 255, np.uint8)
    mask[:18] = 0

    def crop(frame, _box):
        return frame, mask.copy(), False, (0, 0)

    monkeypatch.setattr(cv, "_comp_mask_crop", crop)
    white = np.full((100, 20, 3), 240, np.uint8)
    a, b = white.copy(), white.copy()
    a[:18] = (255, 0, 0)
    b[:18] = (0, 0, 255)
    ea = cv._zone_embedding(a, (0, 0, 20, 100), 140)
    eb = cv._zone_embedding(b, (0, 0, 20, 100), 140)
    for za, zb in zip(ea["zones"], eb["zones"]):
        np.testing.assert_array_equal(za, zb)
    assert ea["zone_support"] == [False, True, True, True]
    assert cv._sim(ea, eb) == .75


def test_occluder_pixels_are_never_used_when_a_zone_is_fully_hidden(monkeypatch):
    monkeypatch.setattr(cv, "_comp_mask_crop", lambda frame, _: (
        frame, np.full((100, 20), 255, np.uint8), False, (0, 0)))
    frame = np.full((100, 20, 3), 240, np.uint8)
    obscured = cv._zone_embedding(frame, (0, 0, 20, 100), 140,
                                 occluders=[(0, 0, 20, 18)])
    visible = cv._zone_embedding(frame, (0, 0, 20, 100), 140)
    assert obscured["owned"] is True
    assert cv._sim(obscured, visible) == .75
    assert cv._sim_relaxed(obscured, [{"emb": visible}]) == .75


def test_completely_masked_body_has_no_identity_support(monkeypatch):
    monkeypatch.setattr(cv, "_comp_mask_crop", lambda frame, _: (
        frame, np.zeros((100, 20), np.uint8), True, (0, 0)))
    frame = np.full((100, 20, 3), 240, np.uint8)
    embedding = cv._zone_embedding(frame, (0, 0, 20, 100), 140)
    assert embedding["owned"] is False
    assert cv._sim(embedding, embedding) == 0.0


def test_coarser_view_cannot_restore_hidden_fine_zone():
    zone = np.array([140., 128., 128., 0., 0., 0.])
    close = {"zones": [zone] * 4, "zone_support": [False, True, True, True], "aspect": 2.0}
    medium = {"zones": [zone] * 3, "aspect": 2.0}
    assert cv._sim(close, medium) == 2 / 3
    # Existing fully visible/legacy embeddings retain their original score.
    close["zone_support"] = [True] * 4
    assert cv._sim(close, medium) == 1.0
