# FIX 04 — TRACKING GEOMETRY behavioural tests (G1–G23).
# Deterministic only: synthetic frames rendered in memory (plus one real
# encoded video for the end-to-end contract). ZERO live LLM/verifier calls,
# zero DB. Identity authority (user taps) is never redesigned here.
import sys
from pathlib import Path

import cv2
import numpy as np
import pytest

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

import player_tracking  # noqa: E402
import tracking_geometry  # noqa: E402
from player_tracking import _cut_flags, _read_window, _run_direction, track_player  # noqa: E402

W, H = 480, 270
DT = 0.08  # 12.5 Hz sample cadence
VFR_TIMES = [0.00, 0.04, 0.11, 0.15, 0.24, 0.31, 0.35, 0.44, 0.51, 0.55]

_BG_RNG = np.random.RandomState(42)
_bg = cv2.GaussianBlur(_BG_RNG.randint(0, 256, (900, 1800)).astype("float32"), (0, 0), 2.5)
BIGBG = cv2.normalize(_bg, None, 25, 230, cv2.NORM_MINMAX).astype("uint8")
BG_X0, BG_Y0 = 600, 300

KIT_RED = (40, 40, 220)    # gray luma ≈ 94
KIT_GREEN = (0, 160, 0)    # SAME gray luma ≈ 94, completely different hue


# ---------------------------------------------------------------- rendering

def draw_player(bgr, cx, cy, w, h, kit=KIT_RED, noise_seed=None, jitter=(0, 0)):
    x0, y0 = int(round(cx - w / 2)), int(round(cy - h / 2))
    x1, y1 = x0 + int(round(w)), y0 + int(round(h))
    cv2.rectangle(bgr, (x0, y0), (x1 - 1, y1 - 1), kit, -1)
    iw, ih = x1 - x0, y1 - y0
    jx, jy = int(jitter[0]), int(jitter[1])
    # pattern blocks live in the LOWER 40% — the torso (upper 60%, the
    # production jersey-histogram zone) stays pure kit colour
    cv2.rectangle(bgr, (x0 + int(iw * 0.08) + jx, y0 + int(ih * 0.62) + jy),
                  (x0 + int(iw * 0.45) + jx, y0 + int(ih * 0.95) + jy), (250, 250, 250), -1)
    cv2.rectangle(bgr, (x0 + int(iw * 0.55) + jx, y0 + int(ih * 0.62) + jy),
                  (x0 + int(iw * 0.92) + jx, y0 + int(ih * 0.95) + jy), (10, 10, 10), -1)
    if noise_seed is not None:  # deterministic "pose" speckle (keeps NCC < LOCK_CONF)
        r = np.random.RandomState(noise_seed)
        ny0, ny1 = max(0, y0), min(bgr.shape[0], y1)
        nx0, nx1 = max(0, x0), min(bgr.shape[1], x1)
        if ny1 > ny0 and nx1 > nx0:
            n = r.randint(-60, 61, (ny1 - ny0, nx1 - nx0, 1)).astype("int16")
            bgr[ny0:ny1, nx0:nx1] = np.clip(
                bgr[ny0:ny1, nx0:nx1].astype("int16") + n, 0, 255).astype("uint8")


def make_bgr(players=(), bg_shift=(0.0, 0.0)):
    """players: (cx, cy, w, h, kit, noise_seed). bg_shift = how far background
    CONTENT has moved (image px, camera pan) relative to frame 0."""
    ox = BG_X0 - int(round(bg_shift[0]))
    oy = BG_Y0 - int(round(bg_shift[1]))
    base = BIGBG[oy:oy + H, ox:ox + W]
    bgr = cv2.merge([base, base, base]).copy()
    for p in players:
        draw_player(bgr, *p)
    return bgr


def finish(t, bgr):
    """Replicates production _read_window conversions for a 480w BGR frame."""
    g = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    hsv = cv2.cvtColor(cv2.resize(bgr, (240, max(2, bgr.shape[0] // 2))), cv2.COLOR_BGR2HSV)
    tiny = cv2.resize(g, (160, max(2, int(g.shape[0] * 160 / g.shape[1])))).astype("float32")
    return (t, g, hsv, tiny)


def frame_at(i, players=(), bg_shift=(0.0, 0.0)):
    return finish(i * DT, make_bgr(players, bg_shift))


def box_of(cx, cy, w=36, h=48):
    return [cx - w / 2.0, cy - h / 2.0, cx + w / 2.0, cy + h / 2.0]


def run_forward(frames, box_px, i0=0, cuts=None):
    out, doubts = {}, []
    _run_direction(frames, i0, box_px, out, +1, doubts, cuts)
    return sorted(out.values(), key=lambda p: p["t"]), doubts


def cx_of(p):
    return (p["x"] + p["w"] / 2.0) * W


def cy_of(p):
    return (p["y"] + p["h"] / 2.0) * H


# --------------------------------------------------------------- FakeCap

class FakeCap:
    """OpenCV/FFmpeg semantics: POS_MSEC is picture_pts, established only
    AFTER grab(). The setter is an approximate round(sec*fps) index seek."""

    def __init__(self, times_s, fps=20.0, w=160, h=120, opencv_seek=False):
        self.times = list(times_s)
        self.fps = fps
        self.w, self.h = w, h
        self.next_i = 0
        self.last_pts_ms = 0.0
        self.last_grabbed = None
        self.opencv_seek = opencv_seek

    def get(self, prop):
        if prop == cv2.CAP_PROP_POS_MSEC:
            return self.last_pts_ms
        if prop == cv2.CAP_PROP_POS_FRAMES:
            return float(self.next_i)
        if prop == cv2.CAP_PROP_FPS:
            return self.fps
        return 0.0

    def set(self, prop, value):
        if prop == cv2.CAP_PROP_POS_MSEC:
            if self.opencv_seek:
                idx = int(round((value / 1000.0) * self.fps))
                idx = max(0, min(idx, len(self.times)))
            else:
                target = value / 1000.0
                idx = 0
                for k, t in enumerate(self.times):
                    if t <= target + 1e-9:
                        idx = k
                    else:
                        break
            self.next_i = idx
            self.last_pts_ms = 0.0 if idx == 0 else self.times[min(idx, len(self.times)) - 1] * 1000.0
        return True

    def grab(self):
        if self.next_i >= len(self.times):
            return False
        self.last_grabbed = self.next_i
        self.last_pts_ms = self.times[self.next_i] * 1000.0
        self.next_i += 1
        return True

    def retrieve(self):
        if self.last_grabbed is None:
            return False, None
        return True, np.full((self.h, self.w, 3), self.last_grabbed % 250, dtype=np.uint8)

    def read(self):
        if not self.grab():
            return False, None
        return self.retrieve()

    def isOpened(self):
        return True

    def release(self):
        pass


# ------------------- G1 / G2 — frame ↔ time ownership inside the tracker

def test_G1_post_grab_pts_owns_each_frame():
    frames = _read_window(FakeCap(VFR_TIMES, fps=20.0), 0.0, 0.6, DT, fps=20.0)
    assert frames, "window decoded no frames"
    for t, g, _hsv, _tiny in frames:
        idx = VFR_TIMES.index(round(t, 2))
        # the frame stored with time t must BE the frame that carries pts t —
        # the old pre-grab read would pair frame N with frame N-1's timestamp
        assert int(g[0, 0]) == idx
    ts = [round(t, 2) for t, *_ in frames]
    assert ts == [0.00, 0.11, 0.24, 0.31, 0.44, 0.51]  # media-time sampling


def test_G2_vfr_times_stay_irregular_no_fps_grid():
    frames = _read_window(FakeCap(VFR_TIMES, fps=20.0), 0.0, 0.6, DT, fps=20.0)
    ts = [round(t, 2) for t, *_ in frames]
    assert set(ts) <= set(round(v, 2) for v in VFR_TIMES)
    deltas = {round(b - a, 2) for a, b in zip(ts, ts[1:])}
    assert len(deltas) > 1, "VFR deltas were flattened"
    grid = [round(i / 20.0, 2) for i in range(20)]
    assert any(t not in grid for t in ts), "times collapsed onto a frame_index/fps grid"


def test_G2b_window_inclusion_with_overshooting_seek():
    # real content 10 fps, container reports 30 fps: OpenCV's POS_MSEC setter
    # (round(sec*fps)) overshoots — adaptive preroll must recover
    times = [i * 0.1 for i in range(30)]
    cap = FakeCap(times, fps=30.0, opencv_seek=True)
    frames = _read_window(cap, 1.0, 2.0, DT, fps=30.0)
    ts = [round(t, 2) for t, *_ in frames]
    assert ts and ts[0] == 1.0 and all(1.0 <= t <= 2.0 for t in ts)
    for t, g, _hsv, _tiny in frames:
        assert int(g[0, 0]) == int(round(t * 10))  # same-frame pairing survives seek


# --------------------------- G3 / G4 / G21 / t_off — end-to-end contract

@pytest.fixture(scope="module")
def slow_video(tmp_path_factory):
    path = str(tmp_path_factory.mktemp("fix04") / "slow.mp4")
    wr = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"mp4v"), 25.0, (W, H))
    if not wr.isOpened():
        pytest.skip("no mp4v encoder available")
    for i in range(100):  # 4 s @ 25 fps, player drifts right 3 px/frame
        bgr = make_bgr()
        r = np.random.RandomState(700 + i)
        draw_player(bgr, 100 + 3 * i, 140, 36, 48, KIT_RED, noise_seed=500 + i,
                    jitter=(int(r.randint(-2, 3)), int(r.randint(-2, 3))))
        wr.write(bgr)
    wr.release()
    return path


TAP_BOX = {"x": round((250 - 18) / W, 4), "y": round((140 - 24) / H, 4),
           "w": round(36 / W, 4), "h": round(48 / H, 4)}


def test_G3_G4_G21_tap_seed_and_output_contract(slow_video):
    res = track_player(slow_video, [{"t": 2.0, "box": TAP_BOX}], t_off=0.0, span=1.5)
    assert set(res.keys()) == {"points", "segments", "doubt_moments", "t_off", "hz", "seed_count"}
    assert res["hz"] == 12.5 and res["seed_count"] == 1 and res["t_off"] == 0.0
    pts = res["points"]
    assert pts and all(set(p.keys()) == {"t", "x", "y", "w", "h", "conf"} for p in pts)
    seeds = [p for p in pts if p["conf"] == 1.0]
    assert len(seeds) == 1, "exactly one ground-truth tap point"
    sp = seeds[0]
    assert abs(sp["t"] - 2.0) <= 0.06
    assert (sp["x"], sp["y"], sp["w"], sp["h"]) == (
        TAP_BOX["x"], TAP_BOX["y"], TAP_BOX["w"], TAP_BOX["h"])  # EXACT tap bbox
    ts = [p["t"] for p in pts]
    assert min(ts) <= 1.1 and max(ts) >= 2.9 and len(pts) >= 20  # continuous coverage
    for p in pts:
        truth = 100 + 75.0 * p["t"]
        assert abs(cx_of(p) - truth) <= 14, f"t={p['t']} off track"
    assert res["segments"] and all(len(s) == 2 for s in res["segments"])


def test_toff_semantics_preserved(slow_video):
    res = track_player(slow_video, [{"t": 1.5, "box": TAP_BOX}], t_off=0.5, span=1.0)
    assert res["t_off"] == 0.5
    seeds = [p for p in res["points"] if p["conf"] == 1.0]
    assert seeds and abs(seeds[0]["t"] - 2.0) <= 0.06  # seed lands at tap+t_off


# ------------------------------------------------ G4 — normal slow motion

def test_G4_slow_motion_continuous_tracking():
    frames = [frame_at(i, [(120 + 6 * i, 135, 36, 48, KIT_RED, 100 + i)]) for i in range(21)]
    pts, doubts = run_forward(frames, box_of(120, 135))
    assert len(pts) >= 18 and not doubts
    for p in pts:
        truth = 120 + 6 * round(p["t"] / DT)
        assert abs(cx_of(p) - truth) <= 8


# --------------------------------------- G5 / G6 — sprint prediction, no lag

SPRINT_CX = [60]
for d in [8, 16, 24] + [30] * 9:
    SPRINT_CX.append(SPRINT_CX[-1] + d)


def test_G5_G6_sprint_found_by_bounded_prediction_no_lag():
    # 30 px/sample far exceeds the old fixed search reach (0.45*36 = 16.2 px)
    frames = [frame_at(i, [(SPRINT_CX[i], 135, 36, 48, KIT_RED, 200 + i)])
              for i in range(len(SPRINT_CX))]
    pts, doubts = run_forward(frames, box_of(60, 135))
    assert not doubts
    recorded = {round(p["t"] / DT): p for p in pts}
    for i in range(6, len(SPRINT_CX)):  # sustained sprint phase
        assert i in recorded, f"sprint frame {i} lost"
        p = recorded[i]
        assert abs(cx_of(p) - SPRINT_CX[i]) <= 9        # follows CURRENT position
        assert abs(cx_of(p) - SPRINT_CX[i - 1]) >= 20   # NOT the previous location


# ------------------------------------- G7 / G8 — camera-motion compensation

def test_G7_camera_pan_is_not_player_velocity(monkeypatch):
    captured = []
    orig = tracking_geometry.update_velocity

    def spy(vel, pc, nc, cam, dt):
        v = orig(vel, pc, nc, cam, dt)
        captured.append(v)
        return v

    monkeypatch.setattr(tracking_geometry, "update_velocity", spy)
    frames = []
    for i in range(20):
        shift = 15.0 * max(0, min(i, 14) - 4)  # pan 15 px/frame during i=5..14
        cx = 240 + shift                        # player is world-fixed
        frames.append(frame_at(i, [(cx, 135, 36, 48, KIT_RED, 300 + i)], bg_shift=(shift, 0)))
    pts, doubts = run_forward(frames, box_of(240, 135))
    assert len(pts) >= 17 and not doubts
    for p in pts:
        i = round(p["t"] / DT)
        truth = 240 + 15.0 * max(0, min(i, 14) - 4)
        assert abs(cx_of(p) - truth) <= 9
    # pan speed is 187 px/s — residual player velocity must stay near zero
    assert captured and max(abs(v[0]) for v in captured) < 60.0


def test_G8_pan_plus_player_motion_and_pan_reversal():
    frames = []
    cx, shift = 90.0, 0.0
    truth = []
    for i in range(20):
        if i > 0:
            if i <= 5:
                cx += 9            # player only
            elif i <= 12:
                shift += 21        # pan right + player → image motion 30 px/frame
                cx += 30
            else:
                shift -= 21        # pan REVERSES while player continues → -12 px/frame
                cx -= 12
        truth.append(cx)
        frames.append(frame_at(i, [(cx, 135, 36, 48, KIT_RED, 400 + i)], bg_shift=(shift, 0)))
    pts, doubts = run_forward(frames, box_of(90, 135))
    assert not doubts
    recorded = {round(p["t"] / DT): p for p in pts}
    assert len(recorded) >= 16, "combined camera+player motion lost the target"
    for i in range(13, 20):  # frames after the reversal — comp keeps the target
        assert i in recorded, f"lost after pan reversal at {i}"
        assert abs(cx_of(recorded[i]) - truth[i]) <= 9


# --------------------------------------------- G9 / G10 / G11 — bbox scale

def test_G9_scale_up_gradual():
    frames = [frame_at(i, [(240, 135, 36 * 1.035 ** i, 48 * 1.035 ** i, KIT_RED, 500 + i)])
              for i in range(17)]
    pts, _ = run_forward(frames, box_of(240, 135))
    assert len(pts) >= 14
    ws = [p["w"] * W for p in pts]
    assert ws[-1] >= 1.30 * 36, f"bbox did not grow: {ws[-1]:.1f}"
    for a, b in zip(ws, ws[1:]):  # ±6% step with integer rounding at small sizes
        assert 0.94 <= b / a <= 1.08, "scale change not gradual"


def test_G10_scale_down_gradual():
    frames = [frame_at(i, [(240, 135, 36 / 1.035 ** i, 48 / 1.035 ** i, KIT_RED, 550 + i)])
              for i in range(15)]
    pts, _ = run_forward(frames, box_of(240, 135))
    assert len(pts) >= 12
    ws = [p["w"] * W for p in pts]
    assert ws[-1] <= 0.78 * 36, f"bbox did not shrink: {ws[-1]:.1f}"
    for a, b in zip(ws, ws[1:]):  # ±6% step with integer rounding at small sizes
        assert 0.92 <= b / a <= 1.06, "scale change not gradual"


def test_G11_one_frame_scale_explosion_rejected():
    frames = []
    for i in range(14):
        size = 2.5 if i == 9 else 1.0  # one-frame implausible explosion
        frames.append(frame_at(i, [(150 + 4 * i, 135, 36 * size, 48 * size, KIT_RED, 600 + i)]))
    pts, _ = run_forward(frames, box_of(150, 135))
    for p in pts:
        assert p["w"] * W <= 36 * 1.2, "explosion was accepted into the track"
    recorded = {round(p["t"] / DT) for p in pts}
    after = [i for i in (10, 11, 12, 13) if i in recorded]
    assert len(after) >= 3, "template was corrupted by the spike"
    for p in pts:
        i = round(p["t"] / DT)
        if i >= 10:
            assert abs(cx_of(p) - (150 + 4 * i)) <= 9


# ----------------------------------------------------- G12 — teleport gate

def test_G12_implausible_jump_rejected_despite_high_ncc():
    frames = []
    for i in range(13):
        if i == 10:  # target occluded; identical decoy near the PREVIOUS spot
            players = [(SPRINT_CX[9] + 2, 135, 36, 48, KIT_RED, 660)]
        else:
            cx = SPRINT_CX[i] if i <= 9 else SPRINT_CX[9] + 30 * (i - 9)
            players = [(cx, 135, 36, 48, KIT_RED, 640 + i)]
        frames.append(frame_at(i, players))
    pts, doubts = run_forward(frames, box_of(60, 135))
    recorded = {round(p["t"] / DT): p for p in pts}
    assert 10 not in recorded, "teleport candidate was recorded"
    assert 11 in recorded and 12 in recorded, "tracking did not resume on the target"
    assert abs(cx_of(recorded[11]) - (SPRINT_CX[9] + 60)) <= 9
    assert abs(cx_of(recorded[12]) - (SPRINT_CX[9] + 90)) <= 9
    assert not doubts


# ------------------- G13 / G14 / G15 / G16 — same-kit crossover behaviour

def _crossover_frames(n=21):
    frames = []
    for i in range(n):
        tcx = 120 + 10 * i
        dcx = 400 - 12 * i
        players = [(tcx, 135, 36, 48, KIT_RED, 700 + i), (dcx, 135, 36, 48, KIT_RED, 800 + i)]
        frames.append(frame_at(i, players))
    return frames


def test_G13_G15_same_kit_crossover_never_switches_then_resumes():
    frames = _crossover_frames()
    pts, doubts = run_forward(frames, box_of(120, 135))
    assert not doubts
    for p in pts:
        i = round(p["t"] / DT)
        tcx, dcx = 120 + 10 * i, 400 - 12 * i
        if abs(tcx - dcx) >= 40:  # clearly separated → must be ON the tapped player
            assert abs(cx_of(p) - tcx) <= 12, f"lost the tapped player at {i}"
            assert abs(cx_of(p) - dcx) > 15, f"SWITCHED to the teammate at {i}"
        else:  # occlusion window: geometry may be pulled by the overlapping body,
            assert abs(cx_of(p) - tcx) <= 22  # but never abandons the target
    recorded = {round(p["t"] / DT) for p in pts}
    assert max(recorded) >= 18, "tracking did not resume after the crossover"
    assert all(i in recorded for i in (17, 18)), "no re-lock on the original trajectory"


def _escort_frames(escort_range):
    """Sprint target (prediction widens the search window) + identical-kit
    escort running 30 px ahead during `escort_range` — two complete, spatially
    distinct, near-equal candidates inside the search region."""
    frames = []
    cx = 60.0
    for i in range(16):
        if i > 0:
            cx += (8, 16, 24)[i - 1] if i <= 3 else 30
        players = [(cx + 30, 135, 36, 48, KIT_RED, 850 + i)] if i in escort_range else []
        players.append((cx, 135, 36, 48, KIT_RED, 800 + i))  # target drawn on top
        frames.append(frame_at(i, players))
    return frames


def test_G14_G15_ambiguous_frames_withheld_then_unique_resume():
    frames = _escort_frames(escort_range=range(8, 10))  # 2 ambiguous frames < limit
    pts, doubts = run_forward(frames, box_of(60, 135))
    recorded = {round(p["t"] / DT): p for p in pts}
    withheld = [i for i in (8, 9) if i not in recorded]
    assert withheld, "near-equal same-kit candidates became track data"
    resumed = [i for i in sorted(recorded) if i >= 10]
    assert resumed, "unique reappearance before the miss limit did not resume"
    truth = {i: 60 + sum((8, 16, 24)[k - 1] if k <= 3 else 30 for k in range(1, i + 1))
             for i in range(16)}
    for i in resumed:  # template purity: resumed matches are strong + on-target
        assert recorded[i]["conf"] >= 0.6
        assert abs(cx_of(recorded[i]) - truth[i]) <= 12
    assert not doubts


def test_G16_persistent_ambiguity_stops_with_doubt():
    frames = []
    for i in range(14):  # diagonal sprint; identical-kit escort locks on at i>=8
        cx, cy = 60 + 16 * i, 40 + 12 * i
        players = []
        if i >= 8:
            players.append((cx + 20, cy + 30, 36, 48, KIT_RED, 960 + i))  # escort behind
        players.append((cx, cy, 36, 48, KIT_RED, 930 + i))  # tapped target on top
        frames.append(frame_at(i, players))
    pts, doubts = run_forward(frames, box_of(60, 40))
    recorded = {round(p["t"] / DT): p for p in pts}
    assert not any(i >= 11 for i in recorded), "persistent ambiguity became track data"
    for i, p in recorded.items():  # everything recorded stays on the tapped player
        assert abs(cx_of(p) - (60 + 16 * i)) <= 9
    assert any("ambiguous" in d["reason"] for d in doubts), f"no ambiguity doubt: {doubts}"


# ----------------------- G17–G20 — existing protections remain in force

def test_G17_scene_cut_stop_remains():
    frames = [frame_at(i, [(150 + 5 * i, 135, 36, 48, KIT_RED, 1000 + i)]) for i in range(10)]
    cuts = [False] * 10
    cuts[5] = True
    pts, doubts = run_forward(frames, box_of(150, 135), cuts=cuts)
    assert all(round(p["t"] / DT) < 5 for p in pts)
    assert any("scene cut" in d["reason"] for d in doubts)


def test_G17b_cut_flags_work_on_new_frame_tuples():
    frames = [frame_at(i, [(150, 135, 36, 48, KIT_RED, 1050 + i)]) for i in range(8)]
    other = np.full((H, W, 3), 240, dtype=np.uint8)  # a completely different scene
    frames[6] = finish(6 * DT, other)
    flags = _cut_flags(frames)
    assert flags[6] is True or flags[6] == True  # noqa: E712
    assert not any(flags[:6])


def test_G18_colour_veto_remains():
    frames = []
    for i in range(13):
        if i <= 6:  # red-kit target
            players = [(150 + 4 * i, 135, 36, 48, KIT_RED, 1100 + i)]
        else:  # target gone; SAME-LUMA green-kit player continues the path
            players = [(150 + 4 * i, 135, 36, 48, KIT_GREEN, 1150 + i)]
        frames.append(frame_at(i, players))
    pts, doubts = run_forward(frames, box_of(150, 135))
    assert all(round(p["t"] / DT) <= 6 for p in pts), "green-kit impostor accepted"
    assert any("kit-colour" in d["reason"] for d in doubts)


def _morph_patch(alpha, seed):
    a_rng = np.random.RandomState(11)
    b_rng = np.random.RandomState(77)
    A = cv2.normalize(cv2.GaussianBlur(a_rng.randint(0, 256, (48, 36)).astype("float32"),
                                       (0, 0), 1.5), None, 0, 255, cv2.NORM_MINMAX)
    B = cv2.normalize(cv2.GaussianBlur(b_rng.randint(0, 256, (48, 36)).astype("float32"),
                                       (0, 0), 1.5), None, 0, 255, cv2.NORM_MINMAX)
    p = (1.0 - alpha) * A + alpha * B
    n = np.random.RandomState(seed).randint(-35, 36, p.shape).astype("float32")
    return np.clip(p + n, 0, 255).astype("uint8")


def test_G19_original_tap_drift_guard_remains():
    frames = []
    for i in range(14):
        bgr = make_bgr()
        patch = _morph_patch(min(1.0, i / 10.0), 1200 + i)
        x0, y0 = 240 - 18, 135 - 24
        bgr[y0:y0 + 48, x0:x0 + 36] = patch[:, :, None]
        frames.append(finish(i * DT, bgr))
    pts, doubts = run_forward(frames, box_of(240, 135))
    assert any("visual drift" in d["reason"] for d in doubts), f"doubts: {doubts}"
    assert len(pts) <= 8


def test_G20_static_background_latch_remains():
    frames = [frame_at(i, [(240, 135, 36, 48, KIT_RED, None)]) for i in range(12)]
    pts, doubts = run_forward(frames, box_of(240, 135))
    assert pts == [], "near-perfect static matches must be un-recorded"
    assert any("static background lock" in d["reason"] for d in doubts)


# --------------------------------------------- G22 / G23 — authority & cost

def test_G22_no_authority_fields_in_track_output(slow_video):
    res = track_player(slow_video, [{"t": 2.0, "box": TAP_BOX}], t_off=0.0, span=1.0)
    assert set(res.keys()) == {"points", "segments", "doubt_moments", "t_off", "hz", "seed_count"}
    for p in res["points"]:
        assert set(p.keys()) == {"t", "x", "y", "w", "h", "conf"}
    src = (BACKEND / "player_tracking.py").read_text()
    for field in ["event_id", "evidence_id", "authority_run_id", "proof_verified",
                  "proof_frame_verified", "identity_hard_reject"]:
        assert field not in src, f"tracker must not touch authority field {field}"


def test_G23_zero_model_calls_in_geometry_code():
    # primary proof = pinned call-count tests in the FIX01 suite (regression run);
    # this is the supporting source-level check for the two geometry modules
    for name in ["player_tracking.py", "tracking_geometry.py"]:
        src = (BACKEND / name).read_text()
        for pat in ["call_gemini", "openai", "verify_frame_identity", "verify_ring_placement",
                    "verify_preview_summary", "emergentintegrations", "httpx", "requests."]:
            assert pat not in src, f"{name} contains {pat}"


# --------------- G24–G26 — cold start, hard stop, sharp reversal (C01)

def test_G24_tap_during_full_sprint_no_ramp():
    # 28 px/sample from frame 1 — no acceleration ramp, no prior velocity
    frames = [frame_at(i, [(60 + 28 * i, 135, 36, 48, KIT_RED, 1300 + i)]) for i in range(13)]
    pts, doubts = run_forward(frames, box_of(60, 135))
    assert not doubts
    recorded = {round(p["t"] / DT): p for p in pts}
    assert all(i in recorded for i in range(2, 13)), f"sprint lost: {sorted(recorded)}"
    for i, p in recorded.items():
        assert abs(cx_of(p) - (60 + 28 * i)) <= 9        # follows CURRENT position
        assert abs(cx_of(p) - (60 + 28 * (i - 1))) >= 19  # no fake lag to previous


def test_G25_hard_stop_reacquired_not_teleport_rejected():
    cxs = list(SPRINT_CX[:9]) + [SPRINT_CX[8]] * 6  # sprint → dead stop at 258
    frames = [frame_at(i, [(cxs[i], 135, 36, 48, KIT_RED, 1350 + i)]) for i in range(15)]
    pts, doubts = run_forward(frames, box_of(60, 135))
    assert not doubts, f"hard stop misread as loss: {doubts}"
    recorded = {round(p["t"] / DT): p for p in pts}
    assert all(i in recorded for i in range(10, 15)), f"target lost after stop: {sorted(recorded)}"
    for i in range(10, 15):
        assert abs(cx_of(recorded[i]) - SPRINT_CX[8]) <= 9


def test_G26_sharp_reversal_reacquired_on_new_trajectory():
    cxs = list(SPRINT_CX[:9]) + [SPRINT_CX[8] - 12 * k for k in range(1, 7)]
    frames = [frame_at(i, [(cxs[i], 135, 36, 48, KIT_RED, 1400 + i)]) for i in range(15)]
    pts, doubts = run_forward(frames, box_of(60, 135))
    assert not doubts
    recorded = {round(p["t"] / DT): p for p in pts}
    assert all(i in recorded for i in range(10, 15)), f"reversal lost: {sorted(recorded)}"
    for i in range(10, 15):
        p = recorded[i]
        assert abs(cx_of(p) - cxs[i]) <= 9, "not following the NEW trajectory"
        assert p["conf"] >= 0.6  # template never learned an unconfirmed turn


# --------------- G27–G29 — close/merged same-kit crossover (C01)

def test_G27_close_duel_geometry_withheld():
    frames = []
    for i in range(12):
        cx = 150 + 6 * i
        players = []
        if i in (5, 6):  # teammate within < 0.6 bbox-width, partially visible
            players.append((cx + 14, 135 + 20, 36, 48, KIT_RED, 1460 + i))
        players.append((cx, 135, 36, 48, KIT_RED, 1450 + i))
        frames.append(frame_at(i, players))
    pts, doubts = run_forward(frames, box_of(150, 135))
    recorded = {round(p["t"] / DT): p for p in pts}
    assert 5 not in recorded and 6 not in recorded, "contaminated duel frames recorded"
    for i, p in recorded.items():  # never pulled toward the neighbour
        assert abs(cx_of(p) - (150 + 6 * i)) <= 9
    assert all(i in recorded for i in range(7, 12)), "did not resume after the duel"
    assert not doubts


def test_G28_partial_occlusion_crossover_resumes_clean():
    frames = []
    for i in range(16):
        tcx = 120 + 10 * i          # tapped target, steady
        pcx = 460 - 20 * i          # teammate crossing IN FRONT (drawn last)
        players = [(tcx, 135, 36, 48, KIT_RED, 1500 + i),
                   (pcx, 135 + 30, 36, 48, KIT_RED, 1550 + i)]
        frames.append(frame_at(i, players))
    pts, doubts = run_forward(frames, box_of(120, 135))
    assert not doubts
    recorded = {round(p["t"] / DT): p for p in pts}
    overlap = [i for i in range(16) if abs((460 - 20 * i) - (120 + 10 * i)) < 30]
    assert any(i not in recorded for i in overlap), "no occlusion frame was withheld"
    for i, p in recorded.items():
        tcx, pcx = 120 + 10 * i, 460 - 20 * i
        assert abs(cx_of(p) - tcx) <= 12, f"target lost at {i}"
        if abs(tcx - pcx) > 40:
            assert abs(cx_of(p) - pcx) > 20, f"switched to the crossing teammate at {i}"
        assert p["conf"] >= 0.6  # template not contaminated
    assert max(recorded) >= 14, "did not resume after separation"


def test_G29_merged_body_region_never_a_clean_bbox():
    frames = []
    for i in range(12):
        players = [(240, 135, 36, 48, KIT_RED, 1600 + i)]
        if i >= 5:  # partner merges into one wider foreground region
            players.insert(0, (240 + 16, 135 + 16, 36, 48, KIT_RED, 1650))
        frames.append(frame_at(i, players))
    pts, doubts = run_forward(frames, box_of(240, 135))
    recorded = {round(p["t"] / DT): p for p in pts}
    merged = [i for i in recorded if i >= 5]
    assert len(merged) <= 1, f"merged frames became authoritative geometry: {merged}"
    for i in merged:  # any surviving frame is the single tapped body, never the blob
        p = recorded[i]
        assert p["w"] * W <= 36 * 1.1 and p["h"] * H <= 48 * 1.1
        assert abs(cx_of(p) - 240) <= 8 and abs(cy_of(p) - 135) <= 8
        assert abs(cx_of(p) - 256) >= 12, "geometry pulled to the partner"
    for p in pts:
        assert p["w"] * W <= 36 * 1.2  # never a widened 'clean' single bbox
    assert any(("overlap" in d["reason"]) or ("ambiguous" in d["reason"]) for d in doubts), \
        f"no crowding doubt: {doubts}"
    assert not any(i >= 8 for i in recorded), "persistent merge did not stop the direction"


# --------------- G30 — unified conservative miss budget (C01)

def test_G30_mixed_rejection_streak_stops_direction():
    frames = []
    for i in range(10):
        if i <= 4:
            players = [(240, 135, 36, 48, KIT_RED, 1700 + i)]   # established target
        elif i == 5:
            players = []                                        # vanished → low NCC
        elif i == 6:                                            # two rivals → ambiguity
            players = [(240 - 8, 135 - 15, 36, 48, KIT_RED, 1750),
                       (240 + 12, 135 + 15, 36, 48, KIT_RED, 1751)]
        elif i == 7:                                            # far decoy → spatial hold
            players = [(240 + 40, 135, 36, 48, KIT_RED, 1752)]
        else:
            players = [(240, 135, 36, 48, KIT_RED, 1700 + i)]   # target returns too late
        frames.append(frame_at(i, players))
    pts, doubts = run_forward(frames, box_of(240, 135))
    recorded = {round(p["t"] / DT): p for p in pts}
    assert not any(i >= 5 for i in recorded), "wrong geometry recorded during the streak"
    assert doubts, "mixed rejection streak did not stop the direction"
    assert not any(i in recorded for i in (8, 9)), "stale re-lock after the stop"


# ------------------------------------------------- pure geometry helpers

def test_pure_teleport_gate_bounds():
    assert tracking_geometry.plausible_motion(20, 0, 36, 48, 0.08) is True
    assert tracking_geometry.plausible_motion(25, 0, 36, 48, 0.08) is False
    assert tracking_geometry.plausible_motion(25, 0, 36, 48, 0.16) is True  # scales with dt
    assert tracking_geometry.plausible_motion(0, 45, 36, 48, 0.08) is False


def test_pure_prediction_bounded_and_camera_compensated():
    dx, dy = tracking_geometry.predict_displacement((10000.0, 0.0), 0.08, 36, 48)
    assert dx == 36 * tracking_geometry.PRED_MAX_FRAC and dy == 0.0
    # displacement fully explained by camera → residual velocity stays ~0
    v = tracking_geometry.update_velocity((0.0, 0.0), (100, 100), (85, 100), (-15.0, 0.0), 0.08)
    assert abs(v[0]) < 1e-6 and abs(v[1]) < 1e-6
    assert tracking_geometry.update_velocity((7.0, 3.0), (0, 0), (1, 1), (0, 0), 0.0) == (7.0, 3.0)


def test_pure_scale_candidates_bounded_by_seed():
    assert set(tracking_geometry.scale_candidates(36, 48, 36, 48)) == {1.0, 1 / 1.06, 1.06}
    assert 1.06 not in tracking_geometry.scale_candidates(66, 88, 36, 48)   # 66*1.06 > 1.9*36
    assert 1 / 1.06 not in tracking_geometry.scale_candidates(20.5, 27.3, 36, 48)  # < 0.55*seed


def test_pure_ambiguity_and_second_peak():
    assert tracking_geometry.is_ambiguous(0.9, 0.85, 0.45) is True
    assert tracking_geometry.is_ambiguous(0.9, 0.60, 0.45) is False   # clear score gap
    assert tracking_geometry.is_ambiguous(0.9, 0.40, 0.45) is False   # below floor
    res = np.zeros((40, 40), dtype="float32")
    res[5, 5] = 0.9
    res[30, 32] = 0.85
    mx2, ml2 = tracking_geometry.second_peak(res, (5, 5), 12, 12)
    assert mx2 == pytest.approx(0.85) and ml2 == (32, 30)
    res2 = np.zeros((40, 40), dtype="float32")
    res2[5, 5] = 0.9
    res2[8, 10] = 0.88  # same-object shoulder → suppressed, NOT a distinct peak
    mx2b, _ = tracking_geometry.second_peak(res2, (5, 5), 12, 12)
    assert mx2b < 0.5


def test_pure_near_rival_contamination():
    res = np.zeros((40, 40), dtype="float32")
    res[20, 20] = 0.9
    res[20, 22] = 0.85  # inside the single-body mainlobe → not a rival
    assert tracking_geometry.is_contaminated(res, (20, 20), 36, 48, 0.9) is False
    res[24, 34] = 0.8   # dx=14 (band), dy=4 → strong near-field rival
    assert tracking_geometry.is_contaminated(res, (20, 20), 36, 48, 0.9) is True
    res[24, 34] = 0.5   # weak support in the band → clean
    assert tracking_geometry.is_contaminated(res, (20, 20), 36, 48, 0.9) is False
    res[24, 34] = 0.42
    assert tracking_geometry.is_contaminated(res, (20, 20), 36, 48, 0.5) is False  # weak match = lost, not crowded
    assert tracking_geometry.near_rival(np.zeros((1, 1), dtype="float32"), (0, 0), 36, 48) <= 0.0


def test_pure_camera_shift_recovers_translation_and_fails_safe():
    rng = np.random.RandomState(3)
    a = cv2.GaussianBlur(rng.rand(90, 160).astype("float32") * 255, (0, 0), 2)
    b = np.roll(a, 6, axis=1)
    dx, dy = tracking_geometry.estimate_camera_shift(a, b)
    assert abs(dx - 6) <= 0.5 and abs(dy) <= 0.5
    assert tracking_geometry.estimate_camera_shift(None, b) == (0.0, 0.0)
    assert tracking_geometry.estimate_camera_shift(a, a[:60]) == (0.0, 0.0)
    assert tracking_geometry.estimate_camera_shift("bad", "input") == (0.0, 0.0)
