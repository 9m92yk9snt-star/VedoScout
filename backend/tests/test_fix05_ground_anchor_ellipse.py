"""FIX 05 — GROUND ANCHOR / ELLIPSE HARDENING (E1–E18).

Deterministic, synthetic, in-memory tests. The ellipse is visualization only:
it must sit on the CURRENT accepted FIX04 geometry's real ground contact,
never trail/overshoot/guess, and hide whenever the contact is ambiguous.
"""
import sys
from pathlib import Path

import cv2
import numpy as np

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

import tele_clip  # noqa: E402
from tele_clip import _draw_ring, _ground_anchor, _smooth  # noqa: E402

GREEN = (50, 170, 60)     # BGR pitch — inside the renderer's green HSV mask
KIT = (36, 28, 200)       # BGR red kit — never green-masked
W, H = 480, 270


def pitch(w=W, h=H):
    return np.full((h, w, 3), GREEN, np.uint8)


def draw_player(frame, cx, feet_y, body_w=20, body_h=48, stance=10,
                colour=KIT, leg_frac=0.42):
    """Torso + hip + two legs whose soles END exactly at feet_y (ground contact)."""
    cx, feet_y = int(cx), int(feet_y)
    leg_h = int(body_h * leg_frac)
    cv2.rectangle(frame, (cx - body_w // 2, feet_y - body_h),
                  (cx + body_w // 2, feet_y - leg_h), colour, -1)
    lw = max(4, body_w // 4)
    hip = stance // 2 + lw // 2
    cv2.rectangle(frame, (cx - hip, feet_y - leg_h - 4),
                  (cx + hip, feet_y - leg_h + 2), colour, -1)
    for s in (-1, 1):
        lx = cx + s * stance // 2
        cv2.rectangle(frame, (lx - lw // 2, feet_y - leg_h),
                      (lx + lw // 2, feet_y - 1), colour, -1)
    return frame


def test_setup_masks_are_valid():
    hsv = cv2.cvtColor(np.uint8([[GREEN]]), cv2.COLOR_BGR2HSV)[0, 0]
    assert 30 <= hsv[0] <= 90 and hsv[1] >= 40 and hsv[2] >= 40, "pitch not green-masked"
    hsv = cv2.cvtColor(np.uint8([[KIT]]), cv2.COLOR_BGR2HSV)[0, 0]
    assert not (30 <= hsv[0] <= 90 and hsv[1] >= 40 and hsv[2] >= 40), "kit reads as grass"


# ---------------------------------------------------------------- E1 standing

def test_E1_standing_anchor_under_real_feet():
    f = draw_player(pitch(), 200, 200)
    res = _ground_anchor(f, 200, 200, 40, 60)
    assert res is not None
    ax, ay, foot_w = res
    assert abs(ax - 200) <= 4, "anchor not centred under the feet"
    assert abs(ay - 200) <= 6, "anchor not at the real ground contact"
    assert foot_w and foot_w >= 40 * 0.14


# --------------------------------------------- E2/E3/E4 position lag removal

def test_E2_no_positional_presmoothing():
    # a reversal sequence: pre-smoothing would round the corner — FIX05 keeps
    # (cx, feet_y) RAW while size may still be averaged
    pts = [{"t": i * 0.08, "x": (0.4 + 0.02 * min(i, 5) - 0.02 * max(0, i - 5)),
            "y": 0.5, "w": 0.06 + (0.02 if i == 4 else 0.0), "h": 0.2} for i in range(10)]
    sm = _smooth(pts)
    for s, p in zip(sm, pts):
        assert s[1] == p["x"] + p["w"] / 2.0, "position was pre-smoothed"
        assert s[2] == p["y"] + p["h"], "feet_y was pre-smoothed"
    assert any(abs(s[3] - (p["x"] and pts[i]["w"])) > 1e-9 for i, (s, p) in
               enumerate(zip(sm, pts)) if i in (2, 3, 4)), "size smoothing removed"


def _run_state_sequence(cxs, feet_y=200, bw=40, bh=60):
    state = {}
    anchors = []
    for cx in cxs:
        f = draw_player(pitch(), cx, feet_y)
        _draw_ring(f, cx / W, feet_y / H, bw / W, bh / H, 1.0, state=state)
        anchors.append(state["anchor"])
    return anchors


def test_E2_full_sprint_no_trailing():
    cxs = [80 + 12 * i for i in range(12)]
    anchors = _run_state_sequence(cxs)
    for (ax, ay), cx in zip(anchors, cxs):
        assert abs(ax - cx) <= 40 * 0.30 + 4, f"ring trails the sprint at {cx}"
    ax, _ = anchors[-1]
    assert abs(ax - cxs[-1]) <= 9, "steady sprint should be followed closely"


def test_E3_hard_stop_no_overshoot():
    cxs = [80 + 14 * i for i in range(6)] + [80 + 14 * 5] * 5
    anchors = _run_state_sequence(cxs)
    stop_x = cxs[-1]
    for ax, _ in anchors[6:]:
        assert ax <= stop_x + 4, "ring overshot the hard stop"
    assert abs(anchors[-1][0] - stop_x) <= 4, "ring did not settle on the stop"


def test_E4_sharp_reversal_no_old_direction_lag():
    cxs = [80 + 14 * i for i in range(7)] + [80 + 14 * 6 - 14 * k for k in range(1, 6)]
    anchors = _run_state_sequence(cxs)
    peak = max(cxs)
    for (ax, _), cx in zip(anchors[7:], cxs[7:]):
        assert ax <= peak + 4, "ring continued in the old direction"
        assert abs(ax - cx) <= 40 * 0.30 + 4, "ring outside the current bbox envelope"


# ------------------------------------------------------------ E5 wide stance

def test_E5_wide_stance_centred_bounded():
    f = draw_player(pitch(), 200, 200, stance=28)
    res = _ground_anchor(f, 200, 200, 40, 60)
    assert res is not None
    ax, ay, foot_w = res
    assert abs(ax - 200) <= 5, "wide stance not centred"
    assert foot_w >= 24, "stance footprint not captured"
    assert foot_w <= 40 * 1.2, "footprint exceeds the bounded envelope"


# --------------------------------------------------------- E6/E7 duel / overlap

def test_E6_close_same_kit_duel_never_anchors_neighbour():
    f = pitch()
    draw_player(f, 200, 200, body_w=14, stance=8)       # own body
    draw_player(f, 220, 200, body_w=20, stance=10)      # pressing neighbour
    # duel: FIX04 box centred between the contesting bodies
    res = _ground_anchor(f, 208, 200, 40, 60)
    assert res is None, "duel contact was guessed instead of hidden"


def test_E7_partial_overlap_keeps_own_anchor():
    f = pitch()
    draw_player(f, 200, 200, body_w=20, stance=10)
    draw_player(f, 246, 200, body_w=20, stance=10)      # nearby, minor overlap
    res = _ground_anchor(f, 200, 200, 40, 60)
    assert res is not None
    ax, ay, _ = res
    assert abs(ax - 200) <= 6, "anchor pulled toward the neighbour"
    assert abs(ax - 246) > 20


# ------------------------------------------------------------ E8 crouch/kneel

def test_E8_crouch_never_anchors_knee_or_thigh():
    f = pitch()
    # crouched: short wide body, soles still on the ground at y=200
    cv2.rectangle(f, (185, 172), (215, 199), KIT, -1)
    res = _ground_anchor(f, 200, 200, 40, 34)
    assert res is not None
    ax, ay, _ = res
    assert ay >= 200 - 34 * 0.2, "anchor climbed onto the crouched body"
    assert abs(ax - 200) <= 5


# ------------------------------------------------------------- E9 fall/slide

def test_E9_fall_slide_bounded_ground_contact():
    f = pitch()
    # sliding: horizontal body inside the bbox, contact extending BELOW the
    # torso-hugging bbox bottom
    cv2.rectangle(f, (175, 182), (228, 212), KIT, -1)
    res = _ground_anchor(f, 200, 200, 40, 60)
    assert res is not None
    ax, ay, _ = res
    assert 200 < ay <= 200 + 60 * 0.45, "slide contact outside the bounded envelope"
    assert abs(ax - 200) <= 40 * 0.45 + 1, "slide anchor left the target-owned columns"


# --------------------------------------------------------------- E10 airborne

def test_E10_airborne_never_rings_the_body():
    f = pitch()
    # airborne stride: the visible mass ends WELL above the accepted bbox
    # bottom (legs tucked / lost) — ringing that band would mark a knee/shin
    cv2.rectangle(f, (190, 145), (210, 172), KIT, -1)
    res = _ground_anchor(f, 200, 200, 40, 60)
    assert res is not None
    ax, ay, foot_w = res
    assert ay >= 200 - 60 * 0.35, "ring attached to the airborne body"
    assert foot_w is None, "an elevated band was reported as a real footprint"


# -------------------------------------------------------------- E11 pitch line

def test_E11_pitch_line_cannot_hijack_anchor():
    f = draw_player(pitch(), 200, 200)
    cv2.rectangle(f, (0, 201), (W - 1, 203), (255, 255, 255), -1)  # white line
    res = _ground_anchor(f, 200, 200, 40, 60)
    assert res is not None
    ax, ay, foot_w = res
    assert abs(ax - 200) <= 6, "line pulled the anchor sideways"
    assert ay <= 204 and ay >= 193, "anchor not at the feet"
    assert foot_w is None or foot_w < 40 * 0.85, "the line became the footprint"


# -------------------------------------------- E12/E13 perspective / oversized

def _changed_bbox(before, after, thresh=6):
    d = np.any(cv2.absdiff(before, after) > thresh, axis=2)
    ys, xs = np.nonzero(d)
    if not len(ys):
        return None
    return xs.min(), ys.min(), xs.max(), ys.max()


def test_E12_near_vs_far_perspective_sizing():
    fw, fh = 960, 540
    far = np.full((fh, fw, 3), GREEN, np.uint8)
    draw_player(far, 480, 170, body_w=12, body_h=40, stance=6)
    far_before = far.copy()
    _draw_ring(far, 480 / fw, 170 / fh, 20 / fw, 44 / fh, 1.0)
    near = np.full((fh, fw, 3), GREEN, np.uint8)
    draw_player(near, 480, 480, body_w=60, body_h=180, stance=32)
    near_before = near.copy()
    _draw_ring(near, 480 / fw, 480 / fh, 104 / fw, 190 / fh, 1.0)
    # strong threshold isolates the crisp painted LINE (glow/shadow excluded)
    fb = _changed_bbox(far_before, far, 25)
    nb = _changed_bbox(near_before, near, 25)
    assert fb and nb, "a ring failed to render"
    far_w, near_w = fb[2] - fb[0], nb[2] - nb[0]
    assert near_w >= far_w + 8, "near player must get a clearly larger ellipse"
    far_hw = (fb[3] - fb[1]) / max(1, far_w)
    near_hw = (nb[3] - nb[1]) / max(1, near_w)
    assert far_hw < near_hw, "distant ellipse must be flatter"


def test_E13_oversized_bbox_cannot_explode_ellipse():
    f = draw_player(pitch(), 240, 200)
    before = f.copy()
    _draw_ring(f, 240 / W, 200 / H, 0.25, 0.5, 1.0)  # wildly generous bbox
    cb = _changed_bbox(before, f, 25)
    assert cb is not None
    assert cb[2] - cb[0] <= W * 0.25, "oversized bbox exploded the ellipse"


# ---------------------------------------------------------------- E14 occlusion

def test_E14_boots_and_legs_occlude_ring():
    f = draw_player(pitch(), 200, 200, body_w=22, stance=12)
    before = f.copy()
    _draw_ring(f, 200 / W, 200 / H, 40 / W, 60 / H, 1.0)
    # torso interior must be restored EXACTLY (player in front of the paint)
    assert np.array_equal(f[176:180, 196:204], before[176:180, 196:204]), \
        "ring paint crossed in front of the body"
    # ankle pixels: near-exact (soft mask edge tolerance)
    leg_x = 200 + 12 // 2
    assert int(np.abs(f[196:198, leg_x - 1:leg_x + 1].astype(int)
                      - before[196:198, leg_x - 1:leg_x + 1].astype(int)).max()) <= 12, \
        "ring line visibly crosses the ankles"
    # and the ring IS painted on the grass beside the player
    side = np.abs(f[198:202, 176:182].astype(int) - before[198:202, 176:182].astype(int))
    assert side.max() > 8, "no visible ring on the pitch"


def test_E14b_restore_does_not_resurrect_neighbour():
    f = draw_player(pitch(), 200, 200, body_w=22, stance=12)
    draw_player(f, 219, 204, body_w=10, body_h=30, stance=6)  # separate body ON the ring line
    _draw_ring(f, 200 / W, 200 / H, 40 / W, 60 / H, 1.0)
    # where the ring line crosses the neighbour's column, the paint must still
    # be visible (the neighbour is NOT restored as part of the target)
    tgt_col = f[196:204, 217:222]
    kit_exact = np.all(tgt_col.reshape(-1, 3) == np.uint8(KIT), axis=1).mean()
    assert kit_exact < 0.5, "a broad mask restored the NEIGHBOUR over the ring"
    # while the TARGET's own ankles stay restored (soft mask edge tolerance)
    own_diff = np.abs(f[196:199, 205:208].astype(int) - np.uint8(KIT).astype(int))
    assert own_diff.max() <= 12, "the target's own leg lost its restore"


# ----------------------------------------------------------- E15 rescue rules

def test_E15_ambiguous_rescue_hides_ring():
    f = pitch()  # empty accepted box at ground level, TWO bodies above it
    draw_player(f, 192, 148, body_w=12, body_h=30, stance=6)
    draw_player(f, 210, 150, body_w=12, body_h=30, stance=6)
    assert _ground_anchor(f, 200, 200, 40, 60) is None, "ambiguous rescue guessed"


def test_E15b_single_clean_rescue_still_allowed():
    f = pitch()
    draw_player(f, 200, 148, body_w=14, body_h=32, stance=8)
    res = _ground_anchor(f, 200, 200, 40, 60)
    assert res is not None, "legitimate single-candidate rescue was blocked"
    ax, ay, _ = res
    assert abs(ax - 200) <= 6


def test_E15c_empty_scene_no_ring():
    assert _ground_anchor(pitch(), 200, 200, 40, 60) is None


# ------------------------------------------------------ E16 shared renderer

def test_E16_still_and_clip_share_one_renderer():
    tele_src = (BACKEND / "telestration.py").read_text()
    assert "_tc._draw_ring" in tele_src, "stills no longer use the shared renderer"
    assert "def _draw_ring" not in tele_src, "a second ring renderer exists in stills"
    assert "cv2.ellipse" not in tele_src, "an independent ellipse path exists in stills"
    server_src = (BACKEND / "server.py").read_text()
    assert "from tele_clip import pos_at, _draw_ring" in server_src, \
        "edge-crop evidence no longer uses the shared renderer"


# ------------------------------------------- E17 zero model / network calls

def test_E17_no_model_verifier_network_calls():
    src = (BACKEND / "tele_clip.py").read_text()
    for token in ("LlmChat", "emergentintegrations", "call_gemini", "verify_frame_identity",
                  "httpx", "aiohttp", "requests.", "urllib", "socket"):
        assert token not in src, f"forbidden call path in tele_clip.py: {token}"


# ------------------------------------ E18 FIX04 tracker / authority untouched

def test_E18_tracker_and_authority_untouched():
    pt = (BACKEND / "player_tracking.py").read_text()
    tg = (BACKEND / "tracking_geometry.py").read_text()
    for src in (pt, tg):
        assert "tele_clip" not in src and "_draw_ring" not in src and \
            "_ground_anchor" not in src, "FIX05 leaked into identity authority"
    assert "dual-hypothesis arbitration (C02)" in pt, "FIX04 C02 contract missing"
    assert "SCALE_HYST" in tg, "FIX04 scale hysteresis missing"
    assert "cv2.ellipse" not in pt and "cv2.ellipse" not in tg
