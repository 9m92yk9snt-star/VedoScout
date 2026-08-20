"""FIX 06 — PACE / DISTANCE CAMERA + PERSPECTIVE COMPENSATION (F01–F25).

Deterministic, synthetic, in-memory tests. Physical speed/distance may only
come from camera-compensated player residual on accepted FIX04 geometry at
FIX03 actual media time. Unsafe camera transforms fail closed.
"""
import hashlib
import sys
from pathlib import Path

import cv2
import numpy as np

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

import motion_compensation as mc  # noqa: E402
from speed_metrics import compute_speed_metrics  # noqa: E402

W, H = 480, 270
DT = 0.08
AGE = 12                 # height 1.53 m, sprint threshold 16 km/h
HEIGHT_M = 1.53


def master_texture(seed=7, mw=W * 3, mh=H * 2):
    rng = np.random.RandomState(seed)
    m = rng.randint(0, 256, (mh, mw)).astype(np.uint8)
    return cv2.GaussianBlur(m, (0, 0), 1.2)


def pan_frames(n, dx=0, dy=0, base=(60, 40), seed=7):
    m = master_texture(seed)
    return [m[base[1] + k * dy:base[1] + k * dy + H,
              base[0] + k * dx:base[0] + k * dx + W].copy() for k in range(n)]


def zoom_frames(n, step=1.008, seed=7):
    """Camera zoom about the frame centre: shrinking central crop → resize."""
    m = master_texture(seed)
    out, boxes_scale = [], []
    for k in range(n):
        s = step ** k
        cw, ch = W / s, H / s
        x0 = int(round(m.shape[1] / 2 - cw / 2))
        y0 = int(round(m.shape[0] / 2 - ch / 2))
        crop = m[y0:y0 + int(round(ch)), x0:x0 + int(round(cw))]
        out.append(cv2.resize(crop, (W, H), interpolation=cv2.INTER_LINEAR))
        boxes_scale.append(s)
    return out, boxes_scale


def track_pts(boxes, ts=None):
    ts = ts or [k * DT for k in range(len(boxes))]
    return [{"t": t, "x": b[0], "y": b[1], "w": b[2], "h": b[3]}
            for t, b in zip(ts, boxes)]


def static_boxes(n, x=0.42, y=0.40, w=0.08, h=0.25):
    return [(x, y, w, h)] * n


def run_boxes(n, dx_px, x0=0.12, y=0.40, w=0.08, h=0.25, width=W):
    return [(x0 + k * dx_px / width, y, w, h) for k in range(n)]


def metrics(frames, boxes, ts=None, age=AGE, taps=None):
    pts = track_pts(boxes, ts)
    motion = mc.samples_from_frames(frames, pts)
    segs = [[pts[0]["t"], pts[-1]["t"]]] if ts is None else None
    if segs is None:  # split segments on gaps
        segs, s0 = [], pts[0]["t"]
        for a, b in zip(pts, pts[1:]):
            if b["t"] - a["t"] > mc.MAX_INTERVAL_S:
                segs.append([s0, a["t"]])
                s0 = b["t"]
        segs.append([s0, pts[-1]["t"]])
    track = {"points": pts, "segments": segs}
    return compute_speed_metrics(track, age, trusted_windows=taps, motion=motion), motion


def kmh_of(dx_px, h_norm=0.25, dt=DT, fh=H):
    return dx_px / (h_norm * fh) * HEIGHT_M / dt * 3.6


N = 55  # 54 intervals ≥ MIN_POINTS/MIN_SAMPLES/MIN_TRACKED_S gates


# ------------------------------------------------- F01–F03 static + camera

def test_F01_static_player_pure_pan():
    # WORLD-static player: under a pan his box moves WITH the background
    boxes = [(0.72 - k * 6 / W, 0.40, 0.08, 0.25) for k in range(N)]
    met, motion = metrics(pan_frames(N, dx=6), boxes)
    assert met is not None
    assert met["top_speed_kmh"] <= 1.5, "camera pan became player speed"
    assert met["sprint_count"] == 0
    assert met["distance_tracked_m"] <= 3, "raw screen movement survived"
    assert met["camera_compensated"] is True


def test_F02_static_player_camera_tilt():
    boxes = [(0.42, 0.60 - k * 2 / H, 0.08, 0.25) for k in range(N)]
    met, _ = metrics(pan_frames(N, dy=2), boxes)
    assert met is not None
    assert met["top_speed_kmh"] <= 1.5, "camera tilt became player speed"
    assert met["distance_tracked_m"] <= 3


def test_F03_static_player_camera_zoom():
    frames, scales = zoom_frames(N, step=1.008)
    boxes = []
    for s in scales:  # a static player's box scales about the frame centre
        bw, bh = 0.08 * s, 0.25 * s
        cx, cy = 0.5 + (0.42 + 0.04 - 0.5) * s, 0.5 + (0.40 + 0.125 - 0.5) * s
        boxes.append((cx - bw / 2, cy - bh / 2, bw, bh))
    met, _ = metrics(frames, boxes)
    assert met is not None
    assert met["top_speed_kmh"] <= 2.5, "zoom became a sprint"
    assert met["sprint_count"] == 0
    assert met["distance_tracked_m"] <= 3


# ------------------------------------------------- F04–F06 player runs

def test_F04_player_run_static_camera():
    expected = kmh_of(8)
    met, _ = metrics(pan_frames(N, dx=0), run_boxes(N, 8))
    assert met is not None
    assert abs(met["top_speed_kmh"] - expected) <= expected * 0.25
    exp_dist = 54 * 8 / (0.25 * H) * HEIGHT_M
    assert abs(met["distance_tracked_m"] - exp_dist) <= exp_dist * 0.25


def test_F05_player_run_camera_follow():
    # camera follows the running player: box stays screen-static, the
    # background shifts — the residual must retain the player's movement
    expected = kmh_of(8)
    met, _ = metrics(pan_frames(N, dx=8), static_boxes(N))
    assert met is not None
    assert abs(met["top_speed_kmh"] - expected) <= expected * 0.25, \
        "camera-follow removed the player's own movement"


def test_F06_player_run_pan_plus_zoom():
    m = master_texture()
    frames, boxes = [], []
    ox, s = 60.0, 1.0
    px, py = 0.30 * W, 0.40 * H + 0.125 * H  # bottom-centre px
    bw, bh = 0.08 * W, 0.25 * H
    for k in range(N):
        cw = W / s
        x0 = int(round(ox))
        crop = m[40:40 + int(round(H / s)), x0:x0 + int(round(cw))]
        frames.append(cv2.resize(crop, (W, H), interpolation=cv2.INTER_LINEAR))
        boxes.append(((px - bw / 2) / W, (py - bh) / H, bw / W, bh / H))
        # camera step: pan 5 master-px + zoom 1.004; the player moves +6 px
        # in the NEW frame's coordinates on top of the camera transform
        s2 = s * 1.004
        a = s2 / s
        tx = (ox - (ox + 5.0)) * s2 / 1.0  # master offset → frame translation
        px, py = a * px + tx, a * py
        bw, bh = bw * a, bh * a
        px += 6.0
        ox += 5.0
        s = s2
    expected = kmh_of(6)
    met, _ = metrics(frames, boxes)
    assert met is not None
    assert abs(met["top_speed_kmh"] - expected) <= expected * 0.30, \
        "combined pan+zoom compensation lost the player residual"


# --------------------------------------- F07/F08 transform quality gates

def test_F07_camera_transform_failure_skips():
    flat = [np.full((H, W), 128, np.uint8) for _ in range(N)]
    met, motion = metrics(flat, run_boxes(N, 8))
    assert all(not s["ok"] for s in motion["samples"]), "raw fallback happened"
    assert all(s["reason"] == "features" for s in motion["samples"])
    assert met is None, "physical metrics published without camera support"


def test_F08_foreground_mover_cannot_define_camera():
    frames = pan_frames(N, dx=0)
    patch = master_texture(seed=99)[:70, :70]
    for k, f in enumerate(frames):  # a second mover far from the target box
        x = 20 + k * 5
        f[180:250, x:x + 70] = patch
    met, motion = metrics(frames, static_boxes(N))
    ok = [s for s in motion["samples"] if s["ok"]]
    assert ok, "background consensus should survive one foreground mover"
    assert met is None or met["top_speed_kmh"] <= 1.5, \
        "a moving foreground object defined the camera transform"


# --------------------------------------------- F09/F10 actual media time

def test_F09_actual_dt_irregular_timestamps():
    dts = [0.06, 0.14, 0.08, 0.12, 0.10]
    ts, t = [0.0], 0.0
    for k in range(1, N):
        t += dts[k % len(dts)]
        ts.append(round(t, 4))
    # constant WORLD speed: displacement proportional to the actual dt
    px_per_s = 100.0
    boxes, x = [], 0.12
    prev_t = 0.0
    for tt in ts:
        x += px_per_s * (tt - prev_t) / W
        prev_t = tt
        boxes.append((x, 0.40, 0.08, 0.25))
    expected = px_per_s / (0.25 * H) * HEIGHT_M * 3.6
    met, _ = metrics(pan_frames(N, dx=0), boxes, ts=ts)
    assert met is not None
    assert abs(met["top_speed_kmh"] - expected) <= expected * 0.20, \
        "speed did not use actual media dt"


def test_F10_segment_gap_never_bridged():
    n1 = 28
    ts = [k * DT for k in range(n1)] + [4.0 + k * DT for k in range(n1)]
    boxes = static_boxes(n1, x=0.20) + static_boxes(n1, x=0.55)  # jump across gap
    met, motion = metrics(pan_frames(2 * n1, dx=0), boxes, ts=ts)
    assert all(s["t1"] - s["t0"] <= mc.MAX_INTERVAL_S for s in motion["samples"])
    assert met is not None
    assert met["distance_tracked_m"] <= 3, "movement was bridged across a track gap"


# ------------------------------------------- F11/F12 real frame geometry

def test_F11_4to3_video_no_aspect_assumption():
    fw, fh = 320, 240
    m = master_texture(seed=11, mw=fw * 3, mh=fh * 2)
    frames = [m[40:40 + fh, 60:60 + fw].copy() for _ in range(N)]
    boxes = [(0.10 + k * 6 / fw, 0.40, 0.10, 0.25) for k in range(N)]
    expected = 6 / (0.25 * fh) * HEIGHT_M / DT * 3.6
    met, _ = metrics(frames, boxes)
    assert met is not None
    assert abs(met["top_speed_kmh"] - expected) <= expected * 0.25, \
        "16:9 assumption distorted a 4:3 video"


def test_F12_portrait_dimensions():
    fw, fh = 270, 480
    m = master_texture(seed=12, mw=fw * 3, mh=fh * 2)
    frames = [m[40:40 + fh, 60:60 + fw].copy() for _ in range(N)]
    boxes = [(0.10 + k * 5 / fw, 0.40, 0.12, 0.15) for k in range(N)]
    expected = 5 / (0.15 * fh) * HEIGHT_M / DT * 3.6
    met, _ = metrics(frames, boxes)
    assert met is not None
    assert abs(met["top_speed_kmh"] - expected) <= expected * 0.25, \
        "portrait geometry mis-scaled"


# ----------------------------------- F13 perspective near vs far players

def test_F13_near_vs_far_comparable_speeds():
    target = 8.0  # km/h equivalent world movement
    far_dx = target * (0.12 * H) / (HEIGHT_M / DT * 3.6)
    near_dx = target * (0.45 * H) / (HEIGHT_M / DT * 3.6)
    met_far, _ = metrics(pan_frames(N, dx=0), run_boxes(N, far_dx, h=0.12, y=0.20))
    met_near, _ = metrics(pan_frames(N, dx=0), run_boxes(N, near_dx, h=0.45, y=0.45))
    assert met_far is not None and met_near is not None
    hi = max(met_far["top_speed_kmh"], met_near["top_speed_kmh"])
    assert abs(met_far["top_speed_kmh"] - met_near["top_speed_kmh"]) <= 0.25 * hi, \
        "perspective scaling failed: near and far speeds diverge"


# -------------------------------------------- F14–F16 jitter / outliers

def test_F14_bbox_height_jitter_no_speed():
    boxes = []
    for k in range(N):  # centre-anchored bbox size jitter, player static
        h = 0.25 * (1.12 if k % 2 else 0.88)
        boxes.append((0.42 + (0.08 - 0.08) / 2, 0.525 - h / 2, 0.08, h))
    met, _ = metrics(pan_frames(N, dx=0), boxes)
    assert met is not None
    assert met["top_speed_kmh"] <= 1.5, "bbox jitter manufactured speed"
    assert met["distance_tracked_m"] <= 2


def test_F15_zoom_scale_change_no_distance():
    frames, scales = zoom_frames(N, step=1.01)
    boxes = []
    for s in scales:
        bw, bh = 0.08 * s, 0.25 * s
        cx, cy = 0.5 + (0.46 - 0.5) * s, 0.5 + (0.525 - 0.5) * s
        boxes.append((cx - bw / 2, cy - bh / 2, bw, bh))
    met, _ = metrics(frames, boxes)
    assert met is not None
    assert met["distance_tracked_m"] <= 3, "bbox scale change became travel"


def test_F16_physical_outlier_rejected():
    boxes = static_boxes(N)
    boxes[27] = (0.42 + 150 / W, 0.40, 0.08, 0.25)  # one impossible teleport
    met, _ = metrics(pan_frames(N, dx=0), boxes)
    assert met is not None
    assert met["top_speed_kmh"] <= 2.0, "outlier survived into top speed"
    assert met["distance_tracked_m"] <= 3
    assert met["metric_samples_skipped"] >= 2


# ------------------------------------- F17/F18 top-speed value/time pair

def _rebuild_smooth(motion, h_norm=0.25):
    import statistics
    ok = [s for s in motion["samples"] if s["ok"]]
    kmh = [((s["rx"] ** 2 + s["ry"] ** 2) ** 0.5 / s["h_px"] * HEIGHT_M) / s["dt"] * 3.6
           for s in ok]
    sm = [statistics.median(kmh[max(0, i - 2):i + 3]) for i in range(len(kmh))]
    return [(s["t1"], v) for s, v in zip(ok, sm)]


def test_F17_top_speed_value_time_same_sample():
    # early plateau ~12 km/h, late 3-frame bump ~14 km/h — value & time must
    # come from the SAME smoothed compensated sample
    dxs = [12 if 10 <= k <= 20 else (14 if 44 <= k <= 47 else 4) for k in range(N - 1)]
    xs = [0.10]
    for d in dxs:
        xs.append(xs[-1] + d / W)
    boxes = [(x, 0.40, 0.08, 0.25) for x in xs]
    met, motion = metrics(pan_frames(N, dx=0), boxes)
    assert met is not None
    sm = _rebuild_smooth(motion)
    near = min(sm, key=lambda s: abs(s[0] - met["top_speed_t"]))
    assert abs(near[0] - met["top_speed_t"]) <= 0.05
    assert abs(round(near[1], 1) - met["top_speed_kmh"]) <= 0.1, \
        "top_speed_kmh and top_speed_t come from different samples"


def test_F18_tap_trusted_top_speed_same_sample():
    boxes = []
    for k in range(N):  # local max near t=1.6 (tap), global max near t=4.0
        dx = 10 if 18 <= k <= 24 else (14 if 48 <= k <= 52 else 4)
        prev = boxes[-1][0] if boxes else 0.08
        boxes.append((prev + dx / W, 0.40, 0.08, 0.25))
    met, motion = metrics(pan_frames(N, dx=0), boxes, taps=[1.6])
    assert met is not None
    assert met["top_trust"] == "tap"
    assert abs(met["top_speed_t"] - 1.6) <= 2.0, "trusted top speed left the tap window"
    sm = _rebuild_smooth(motion)
    near = min(sm, key=lambda s: abs(s[0] - met["top_speed_t"]))
    assert abs(round(near[1], 1) - met["top_speed_kmh"]) <= 0.1, \
        "trusted value and time are not the same sample"


# ------------------------------------------ F19–F21 distance / coverage

def test_F19_distance_only_safe_intervals():
    frames = pan_frames(N, dx=0)
    for k in range(20, 26):  # camera transform must fail on these
        frames[k] = np.full((H, W), 128, np.uint8)
    met, motion = metrics(frames, run_boxes(N, 8))
    assert met is not None
    n_skip = sum(1 for s in motion["samples"] if not s["ok"])
    assert n_skip >= 5
    assert met["metric_samples_skipped"] >= 5
    full = 54 * 8 / (0.25 * H) * HEIGHT_M
    used = (54 - n_skip) * 8 / (0.25 * H) * HEIGHT_M
    assert met["distance_tracked_m"] < full * 0.95, "rejected intervals entered distance"
    assert abs(met["distance_tracked_m"] - used) <= used * 0.20


def test_F20_sprint_pan_safety():
    # camera pans fast (oscillating) over a WORLD-static player — raw screen
    # speed (14 px/frame ≈ sprint pace for age 9) would sprint, compensated 0
    m = master_texture()
    frames, boxes = [], []
    ox, x = 60, 0.62
    for k in range(N):
        frames.append(m[40:40 + H, ox:ox + W].copy())
        boxes.append((x, 0.40, 0.08, 0.25))
        d = 14 if (k // 18) % 2 == 0 else -14
        ox += d
        x -= d / W
    met, _ = metrics(frames, boxes, age=9)
    assert met is not None
    assert met["sprint_count"] == 0, "camera pan produced a sprint"
    assert met["top_speed_kmh"] <= 2.0


def test_F21_low_coverage_no_physical_claim():
    frames = pan_frames(N, dx=0)
    for k in range(8, N):  # most camera transforms fail
        frames[k] = np.full((H, W), 128, np.uint8)
    met, _ = metrics(frames, run_boxes(N, 8))
    assert met is None, "physical metrics published from a tiny unsafe sample"


# ---------------------------------------------------- F22 determinism

def test_F22_determinism():
    def once():
        return metrics(pan_frames(N, dx=5), run_boxes(N, 6))
    met1, mo1 = once()
    met2, mo2 = once()
    assert met1 == met2
    for a, b in zip(mo1["samples"], mo2["samples"]):
        assert a == b


# --------------------------------------- F23–F25 source / phase guards

def test_F23_zero_model_network_calls():
    for name in ("motion_compensation.py", "speed_metrics.py"):
        src = (BACKEND / name).read_text()
        for token in ("LlmChat", "emergentintegrations", "call_gemini", "verify_",
                      "httpx", "aiohttp", "requests.", "urllib", "socket"):
            assert token not in src, f"forbidden call path in {name}: {token}"


def test_F24_fix04_tracker_untouched():
    assert hashlib.sha256((BACKEND / "player_tracking.py").read_bytes()).hexdigest() == \
        "4b897f68680ec5abce43e36ae06818134fa09b418d8646640d0648abb3ba39ca"
    assert hashlib.sha256((BACKEND / "tracking_geometry.py").read_bytes()).hexdigest() == \
        "5782b2b413e4f0b55fd2a068cf7d1bc654fae336878416240659664db8e4f0c2"


def test_F25_fix05_ellipse_untouched():
    assert hashlib.sha256((BACKEND / "tele_clip.py").read_bytes()).hexdigest() == \
        "c095f49c2f2ed16cc0f1c69b38f880089869aac2eafdde971732e9f76f193451"
    assert hashlib.sha256((BACKEND / "telestration.py").read_bytes()).hexdigest() == \
        "9cf5ea5039d3a0f71671451a60f8f1a5014c1831ac5ac45ba28d2d1388ae51ec"
