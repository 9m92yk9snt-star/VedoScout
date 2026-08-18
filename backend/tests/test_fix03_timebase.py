# FIX 03 — CANONICAL TIMEBASE / VFR behavioural tests.
# Deterministic only: a pure-Python VFR VideoCapture stand-in drives every
# media-time assertion. ZERO live LLM calls, zero real video decoding.
import sys
from pathlib import Path

import cv2
import numpy as np

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

import video_timebase  # noqa: E402

# deliberately irregular (VFR) presentation timestamps
VFR_TIMES = [0.00, 0.04, 0.11, 0.15, 0.24, 0.31, 0.35, 0.44, 0.51, 0.55]
REGULAR_20FPS = [i * 0.05 for i in range(10)]


class FakeCap:
    """Deterministic VFR VideoCapture stand-in: a PTS list drives POS_MSEC."""

    def __init__(self, times_s, fps=20.0, w=160, h=120):
        self.times = list(times_s)
        self.i = 0
        self.fps = fps
        self.w, self.h = w, h
        self.seeks = []  # every cap.set() call, recorded

    def get(self, prop):
        if prop == cv2.CAP_PROP_POS_MSEC:
            if self.i < len(self.times):
                return self.times[self.i] * 1000.0
            return (self.times[-1] + 0.04) * 1000.0 if self.times else 0.0
        if prop == cv2.CAP_PROP_POS_FRAMES:
            return float(self.i)
        if prop == cv2.CAP_PROP_FPS:
            return self.fps
        if prop == cv2.CAP_PROP_FRAME_COUNT:
            return float(len(self.times))
        if prop == cv2.CAP_PROP_FRAME_WIDTH:
            return float(self.w)
        if prop == cv2.CAP_PROP_FRAME_HEIGHT:
            return float(self.h)
        return 0.0

    def set(self, prop, value):
        self.seeks.append((prop, float(value)))
        if prop == cv2.CAP_PROP_POS_MSEC:
            self.i = next((k for k, t in enumerate(self.times)
                           if t * 1000.0 >= value - 1e-6), len(self.times))
        elif prop == cv2.CAP_PROP_POS_FRAMES:
            self.i = int(value)
        return True

    def grab(self):
        if self.i >= len(self.times):
            return False
        self.i += 1
        return True

    def retrieve(self):
        return True, np.zeros((self.h, self.w, 3), dtype=np.uint8)

    def read(self):
        if not self.grab():
            return False, None
        return True, np.zeros((self.h, self.w, 3), dtype=np.uint8)

    def isOpened(self):
        return True

    def release(self):
        pass


def _decode_all_times(cap, fps):
    out = []
    while True:
        t, fb = video_timebase.next_frame_time_seconds(cap, fps)
        ok, _ = cap.read()
        if not ok:
            break
        out.append(round(t, 4))
    return out


# ---------- T1 / T9 — VFR is never reinterpreted as frame_index/fps ----------

def test_T1_T9_vfr_sequence_not_flattened_to_fps_grid():
    cap = FakeCap(VFR_TIMES, fps=20.0)
    ts = _decode_all_times(cap, 20.0)
    assert ts == [round(t, 4) for t in VFR_TIMES]           # actual media times
    assert ts != [round(t, 4) for t in REGULAR_20FPS]       # NOT 0.00,0.05,0.10...


def test_T1b_explicit_fallback_only_without_media_time():
    class DeadCap(FakeCap):
        def get(self, prop):
            if prop == cv2.CAP_PROP_POS_MSEC:
                return -1.0  # backend reports no usable media time
            return super().get(prop)
    cap = DeadCap(VFR_TIMES, fps=20.0)
    t, fb = video_timebase.next_frame_time_seconds(cap, 20.0)
    assert fb is True                     # explicitly flagged as fallback
    assert t == 0.0
    # authoritative path is flagged False
    t2, fb2 = video_timebase.next_frame_time_seconds(FakeCap(VFR_TIMES), 20.0)
    assert fb2 is False and t2 == 0.0
    cap2 = FakeCap(VFR_TIMES)
    cap2.read()
    t3, fb3 = video_timebase.next_frame_time_seconds(cap2, 20.0)
    assert fb3 is False and abs(t3 - 0.04) < 1e-9


# ---------- T2 — canonical seek uses milliseconds, never POS_FRAMES ----------

def test_T2_seek_requests_pos_msec():
    cap = FakeCap(VFR_TIMES)
    video_timebase.seek_seconds(cap, 0.15)
    video_timebase.seek_ms(cap, 240.0)
    assert cap.seeks == [(cv2.CAP_PROP_POS_MSEC, 150.0), (cv2.CAP_PROP_POS_MSEC, 240.0)]
    assert all(p != cv2.CAP_PROP_POS_FRAMES for p, _ in cap.seeks)
    ok, frame, t = video_timebase.read_frame_at(FakeCap(VFR_TIMES), 0.12)
    assert ok and abs(t - 0.15) < 1e-9   # actual media time of the frame used


# ---------- T3 — CV-shadow tap reference seeks by media time ----------

def test_T3_cv_shadow_tap_reference_media_seek():
    import cv_shadow
    cap = FakeCap([i * 0.1 for i in range(400)], fps=10.0, w=160, h=120)
    anchors = [{"t": 36.0, "box": {"x": 0.4, "y": 0.4, "w": 0.1, "h": 0.2}}]
    cv_shadow._build_tap_references(cap, 10.0, anchors, 0.5, 160, 120, 1.0, detector=None)
    msec_seeks = [v for p, v in cap.seeks if p == cv2.CAP_PROP_POS_MSEC]
    assert 36500.0 in msec_seeks          # (36.0 + t_off 0.5) * 1000 — media time
    assert all(p == cv2.CAP_PROP_POS_MSEC for p, _ in cap.seeks)


# ---------- T4 — shadow sampling by elapsed media time ----------

def test_T4_sampling_uses_media_time_not_fidx_fps():
    cap = FakeCap(VFR_TIMES, fps=20.0)
    interval = 0.2  # 5 Hz
    sampled, prev = [], None
    while True:
        t, _fb = video_timebase.next_frame_time_seconds(cap, 20.0)
        if not cap.grab():
            break
        if not video_timebase.should_sample(t, prev, interval):
            continue
        prev = t
        sampled.append(round(t, 4))
    assert sampled == [0.00, 0.24, 0.44]      # actual VFR media instants
    for s in sampled:
        assert s in [round(t, 4) for t in VFR_TIMES]
    assert sampled != [0.0, 0.2, 0.4]         # never an fps-derived grid
    # wiring: the shadow scan consumes exactly these helpers, fidx/fps is gone
    src = (BACKEND / "cv_shadow.py").read_text()
    assert "video_timebase.next_frame_time_seconds(cap, fps)" in src
    assert "video_timebase.should_sample(" in src
    assert "t = fidx / fps" not in src
    assert "CAP_PROP_POS_FRAMES" not in src


# ---------- T5 — physics dt from real timestamp differences ----------

def test_T5_physics_dt_uses_real_media_delta():
    assert abs(video_timebase.sample_dt(0.24, 0.11, 0.2) - 0.13) < 1e-9
    assert abs(video_timebase.sample_dt(0.44, 0.24, 0.2) - 0.20) < 1e-9
    assert video_timebase.sample_dt(0.0, None, 0.2) == 0.2  # first sample only
    src = (BACKEND / "cv_shadow.py").read_text()
    assert "dt_sample = video_timebase.sample_dt(t, prev_sample_t, sample_interval)" in src
    assert "lost_since += dt_sample" in src
    assert "step / fps" not in src
    assert "dt = max(0.05, t - last_t)" in src  # physics dt now spans media ts


# ---------- T6 / T7 / T8 — tele clip renders by media time ----------

def _run_teleclip(monkeypatch, times, fps=20.0):
    import tele_clip

    fake = FakeCap(times, fps=fps, w=160, h=120)
    monkeypatch.setattr(tele_clip.cv2, "VideoCapture", lambda p: fake)
    monkeypatch.setattr(video_timebase, "media_duration_seconds",
                        lambda p: times[-1] + 0.05)

    class FakeWriter:
        def __init__(self):
            self.frames = 0
        def append_data(self, arr):
            self.frames += 1
        def close(self):
            pass

    writer = FakeWriter()

    class FakeImageio:
        @staticmethod
        def get_writer(*a, **kw):
            return writer

    monkeypatch.setitem(sys.modules, "imageio", FakeImageio)

    interp_ts, risk_ts = [], []
    orig_interp = tele_clip._interp
    orig_risk = tele_clip._risk_alpha

    def rec_interp(sm, t):
        interp_ts.append(round(t, 4))
        return orig_interp(sm, t)

    def rec_risk(t, windows, fade=tele_clip.FADE_SEC):
        risk_ts.append(round(t, 4))
        return orig_risk(t, windows, fade)

    monkeypatch.setattr(tele_clip, "_interp", rec_interp)
    monkeypatch.setattr(tele_clip, "_risk_alpha", rec_risk)

    track = [{"t": 0.2 * i, "x": 0.4, "y": 0.4, "w": 0.05, "h": 0.12}
             for i in range(0, 60)]  # dense 0..11.8s track
    res = tele_clip.generate_tracked_clip("fake.mp4", 5.0, track, "/tmp/fix03_clip.mp4")
    return fake, writer, interp_ts, risk_ts, res


def test_T6_T7_T8_teleclip_media_time(monkeypatch):
    # VFR source around the 5.0s moment: irregular gaps, extends beyond c1
    times = []
    t = 0.0
    k = 0
    while t < 14.0:
        times.append(round(t, 3))
        t += 0.04 if (k % 3) else 0.11   # irregular VFR cadence
        k += 1
    fake, writer, interp_ts, risk_ts, _res = _run_teleclip(monkeypatch, times)
    assert writer.frames > 0
    pts = {round(x, 4) for x in times}
    # T6 — interpolation main calls receive the frame's ACTUAL media timestamp
    mains = interp_ts[0::3]  # per frame: main, then velocity ta/tb
    assert len(mains) == writer.frames
    assert all(m in pts for m in mains)
    # T7 — risk-alpha windows evaluated at the actual media timestamp
    assert len(risk_ts) == writer.frames
    assert risk_ts == mains
    # T8 — render stopped by media time: nothing at/after 14s was rendered,
    # and the clip covers only the c0..c1 media window
    c1_max = max(mains)
    assert c1_max < 11.0                     # 5.0 moment + post/padding window
    assert all(m <= c1_max + 1e-6 for m in mains)
    assert mains == sorted(mains)
    # never a regular fps grid
    grid = [round(mains[0] + i * (1.0 / 20.0), 4) for i in range(len(mains))]
    assert mains != grid
    src = (BACKEND / "tele_clip.py").read_text()
    assert "idx / fps" not in src and "CAP_PROP_POS_FRAMES" not in src


# ---------- T10 / T11 — doubt tap + teleclip edge use canonical seeks ----------

def test_T10_doubt_tap_canonical_seek_wiring():
    src = (BACKEND / "server.py").read_text()
    assert "CAP_PROP_POS_FRAMES" not in src   # no frame-index seeking anywhere
    i = src.find("async def _verify_doubt_taps")
    assert i > 0
    seg = src[i:i + 4000]
    assert 'video_timebase.seek_seconds(cap, float(c["t"]))' in seg


def test_T11_teleclip_edge_crop_canonical_seek(monkeypatch):
    import server
    fake = FakeCap([i * 0.1 for i in range(200)], fps=10.0, w=160, h=120)
    monkeypatch.setattr(cv2, "VideoCapture", lambda p: fake)
    sm = [(0.2 * i, 0.4, 0.4, 0.05, 0.12) for i in range(60)]
    server._teleclip_edge_crop("fake.mp4", sm, 7.3, "/tmp/fix03_edge.jpg")
    assert (cv2.CAP_PROP_POS_MSEC, 7300.0) in fake.seeks
    assert all(p == cv2.CAP_PROP_POS_MSEC for p, _ in fake.seeks)


# ---------- T12 — duration does not depend on frame_count/fps ----------

def test_T12_primary_duration_is_media_probe(monkeypatch):
    import server
    monkeypatch.setattr(server, "get_duration_seconds", lambda p: 12.5)
    assert server._video_duration_seconds("does-not-exist.mp4") == 12.5

    import media_binaries
    monkeypatch.setattr(media_binaries, "get_duration_seconds", lambda p: 44.4)
    assert video_timebase.media_duration_seconds("x.mp4") == 44.4
    monkeypatch.setattr(media_binaries, "get_duration_seconds", lambda p: 0.0)
    assert video_timebase.media_duration_seconds("x.mp4") is None  # caller fallback
    src = (BACKEND / "server.py").read_text()
    i = src.find("def _video_duration_seconds")
    seg = src[i:i + 400]
    assert "CAP_PROP_FRAME_COUNT" not in seg and "get_duration_seconds" in seg


# ---------- T13 — production tracker timing unchanged ----------

def test_T13_production_tracker_untouched():
    import player_tracking
    src = (BACKEND / "player_tracking.py").read_text()
    assert "CAP_PROP_POS_MSEC" in src            # existing media-time timing
    assert "CAP_PROP_POS_FRAMES" not in src
    # t_off calibration mechanism retained, untouched (precision_engine)
    pe = (BACKEND / "precision_engine.py").read_text()
    assert "def estimate_time_offset" in pe
    assert "CAP_PROP_POS_MSEC" in pe
    assert player_tracking.MAX_TRACKER_SEEDS == 16
    assert "video_timebase" not in src           # tracker deliberately untouched


# ---------- T14 — authority/proof semantics unchanged ----------

def test_T14_authority_semantics_unchanged():
    from evidence_authority import (
        attach_event_evidence_authority, apply_fail_closed_proof_authority,
        compute_proof_frame_verified, ts_to_ms,
    )
    assert ts_to_ms("00:36") == 36000
    full = {"action_timeline": [{"timestamp": "00:36", "cross_verified": True}],
            "video_comments": [{"timestamp": "00:36", "comment": "x"}]}
    attach_event_evidence_authority(full)
    apply_fail_closed_proof_authority(full)
    assert full["video_comments"][0]["proof_verified"] is True
    assert compute_proof_frame_verified({
        "proof_verified": True, "frame_url": "/f/x.jpg", "identity_verified": True,
        "evidence_time_ms": 36000, "frame_time_ms": 38000}) is False


# ---------- T15 — zero new production model calls ----------

def test_T15_no_new_model_call_sites():
    src = (BACKEND / "server.py").read_text()
    assert src.count("call_gemini_with_video(") == 7
    assert src.count("call_gemini_text(") == 2
    assert src.count("verify_frame_identity(") == 5
    assert src.count("verify_ring_placement(") == 1
    assert src.count("verify_preview_summary(") == 2
    for name in ("video_timebase.py", "cv_shadow.py", "tele_clip.py"):
        low = (BACKEND / name).read_text().lower()
        for banned in ("gemini", "openai", "llmchat", "httpx"):
            assert banned not in low
