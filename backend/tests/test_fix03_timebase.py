# FIX 03 — CANONICAL TIMEBASE / VFR behavioural tests (incl. CORRECTION 01).
# Deterministic only: a pure-Python VFR VideoCapture stand-in mimics real
# OpenCV/FFmpeg semantics (POS_MSEC = picture_pts established AFTER grab).
# ZERO live LLM calls, zero real video decoding.
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
    """Mimics OpenCV/FFmpeg semantics: CAP_PROP_POS_MSEC is picture_pts —
    established only AFTER grab()/decode. Pre-grab reads return the PREVIOUS
    grab's (stale) PTS, exactly like the real backend. Every frame carries its
    source index in all pixels so frame↔timestamp pairing is provable."""

    def __init__(self, times_s, fps=20.0, w=160, h=120, keyframes=None):
        self.times = list(times_s)
        self.fps = fps
        self.w, self.h = w, h
        self.next_i = 0
        self.last_pts_ms = 0.0
        self.last_grabbed = None
        self.keyframes = sorted(keyframes) if keyframes else None
        self.seeks = []

    def get(self, prop):
        if prop == cv2.CAP_PROP_POS_MSEC:
            return self.last_pts_ms  # PTS of the LAST grabbed frame only
        if prop == cv2.CAP_PROP_POS_FRAMES:
            return float(self.next_i)
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
            target = value / 1000.0
            idx = 0
            for k, t in enumerate(self.times):
                if t <= target + 1e-9:
                    idx = k
                else:
                    break
            if self.keyframes is not None:  # ffmpeg lands on keyframe <= target
                idx = max([k for k in self.keyframes if k <= idx] or [0])
            self.next_i = idx
            self.last_pts_ms = 0.0 if idx == 0 else self.times[idx - 1] * 1000.0
        elif prop == cv2.CAP_PROP_POS_FRAMES:
            self.next_i = int(value)
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


def _decode_all(cap, fps):
    """(t, frame_id) pairs via the C01 contract: grab → PTS → retrieve."""
    out = []
    while True:
        ok, t, _fb = video_timebase.grab_frame_time_seconds(cap, fps)
        if not ok:
            break
        ok, frame = cap.retrieve()
        if not ok:
            break
        out.append((round(t, 4), int(frame[0, 0, 0])))
    return out


# ---------- T1 / T9 — VFR is never reinterpreted as frame_index/fps ----------

def test_T1_T9_vfr_sequence_not_flattened_to_fps_grid():
    pairs = _decode_all(FakeCap(VFR_TIMES, fps=20.0), 20.0)
    ts = [t for t, _ in pairs]
    assert ts == [round(t, 4) for t in VFR_TIMES]           # actual media times
    assert ts != [round(t, 4) for t in REGULAR_20FPS]       # NOT 0.00,0.05,0.10...


def test_T1b_explicit_fallback_only_without_media_time():
    class DeadCap(FakeCap):
        def get(self, prop):
            if prop == cv2.CAP_PROP_POS_MSEC:
                return -1.0  # backend reports no usable media time
            return super().get(prop)
    cap = DeadCap(VFR_TIMES, fps=20.0)
    ok, t, fb = video_timebase.grab_frame_time_seconds(cap, 20.0)
    assert ok and fb is True and t == 0.0     # explicit last resort, flagged
    ok, t2, fb2 = video_timebase.grab_frame_time_seconds(cap, 20.0)
    assert fb2 is True and abs(t2 - 0.05) < 1e-9
    # authoritative path is flagged False
    ok, t3, fb3 = video_timebase.grab_frame_time_seconds(FakeCap(VFR_TIMES), 20.0)
    assert ok and fb3 is False and t3 == 0.0


# ---------- T2 — canonical seek uses milliseconds, never POS_FRAMES ----------

def test_T2_seek_requests_pos_msec():
    cap = FakeCap(VFR_TIMES)
    video_timebase.seek_seconds(cap, 0.15)
    video_timebase.seek_ms(cap, 240.0)
    assert cap.seeks == [(cv2.CAP_PROP_POS_MSEC, 150.0), (cv2.CAP_PROP_POS_MSEC, 240.0)]
    assert all(p != cv2.CAP_PROP_POS_FRAMES for p, _ in cap.seeks)


# ---------- C1 — grab → timestamp → retrieve pairs the SAME frame ----------

def test_C1_grab_then_timestamp_then_retrieve_same_frame():
    pairs = _decode_all(FakeCap(VFR_TIMES, fps=20.0), 20.0)
    assert len(pairs) == len(VFR_TIMES)
    for t, fid in pairs:
        assert abs(VFR_TIMES[fid] - t) < 1e-9  # timestamp belongs to THAT frame


# ---------- C2 — the old pre-grab reading is provably wrong ----------

def test_C2_pre_grab_timestamp_fails_on_realistic_cap():
    cap = FakeCap(VFR_TIMES, fps=20.0)
    old_style = []
    while True:
        stale_ms = cap.get(cv2.CAP_PROP_POS_MSEC)   # read BEFORE grab (old bug)
        ok, frame = cap.read()
        if not ok:
            break
        old_style.append((round(stale_ms / 1000.0, 4), int(frame[0, 0, 0])))
    # every frame after the first gets the PREVIOUS frame's PTS -> mismatch
    mismatches = [1 for t, fid in old_style if abs(VFR_TIMES[fid] - t) > 1e-9]
    assert len(mismatches) == len(VFR_TIMES) - 1
    # the corrected helper has zero mismatches (C1)
    good = _decode_all(FakeCap(VFR_TIMES, fps=20.0), 20.0)
    assert all(abs(VFR_TIMES[fid] - t) < 1e-9 for t, fid in good)


# ---------- T3 — CV-shadow tap reference seeks by media time ----------

def test_T3_cv_shadow_tap_reference_media_seek():
    import cv_shadow
    cap = FakeCap([i * 0.1 for i in range(400)], fps=10.0)
    anchors = [{"t": 36.0, "box": {"x": 0.4, "y": 0.4, "w": 0.1, "h": 0.2}}]
    cv_shadow._build_tap_references(cap, 10.0, anchors, 0.5, 160, 120, 1.0, detector=None)
    msec_seeks = [v for p, v in cap.seeks if p == cv2.CAP_PROP_POS_MSEC]
    assert 36500.0 in msec_seeks          # (36.0 + t_off 0.5) * 1000 — media time
    assert all(p == cv2.CAP_PROP_POS_MSEC for p, _ in cap.seeks)


# ---------- T4 / C3 — shadow sampling: same decoded frame + media time ----------

def test_T4_C3_sampling_uses_media_time_of_the_decoded_frame():
    cap = FakeCap(VFR_TIMES, fps=20.0)
    interval = 0.2  # 5 Hz
    sampled, prev = [], None
    while True:
        ok, t, _fb = video_timebase.grab_frame_time_seconds(cap, 20.0)
        if not ok:
            break
        if not video_timebase.should_sample(t, prev, interval):
            continue
        ok, frame = cap.retrieve()
        assert ok
        prev = t
        sampled.append((round(t, 4), int(frame[0, 0, 0])))
    assert [t for t, _ in sampled] == [0.00, 0.24, 0.44]  # actual VFR instants
    for t, fid in sampled:
        assert abs(VFR_TIMES[fid] - t) < 1e-9   # C3: SAME frame as timestamp
    assert [t for t, _ in sampled] != [0.0, 0.2, 0.4]     # never an fps grid
    src = (BACKEND / "cv_shadow.py").read_text()
    assert "video_timebase.grab_frame_time_seconds(cap, fps)" in src
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
    assert "dt = max(0.05, t - last_t)" in src  # physics dt spans media ts


# ---------- tele clip: shared harness ----------

def _teleclip_times():
    # irregular VFR cadence, dense (0.04s) around the 5.0s moment
    times, t, k = [], 0.0, 0
    while t < 14.0:
        times.append(round(t, 3))
        t += 0.04 if (4.0 <= t <= 6.0 or k % 3) else 0.11
        k += 1
    return times


def _run_teleclip(monkeypatch, times, fps=20.0):
    import tele_clip

    fake = FakeCap(times, fps=fps)
    monkeypatch.setattr(tele_clip.cv2, "VideoCapture", lambda p: fake)
    monkeypatch.setattr(video_timebase, "media_duration_seconds",
                        lambda p: times[-1] + 0.05)

    class FakeWriter:
        def __init__(self):
            self.ids = []
        def append_data(self, arr):
            self.ids.append(int(arr[0, 0, 0]))
        def close(self):
            pass

    writer = FakeWriter()

    class FakeImageio:
        @staticmethod
        def get_writer(*a, **kw):
            return writer

    monkeypatch.setitem(sys.modules, "imageio", FakeImageio)

    risk_ts, draw_ids = [], []
    orig_risk = tele_clip._risk_alpha
    orig_draw = tele_clip._draw_ring

    def rec_risk(t, windows, fade=tele_clip.FADE_SEC):
        risk_ts.append(round(t, 4))
        return orig_risk(t, windows, fade)

    def rec_draw(frame, *a, **kw):
        draw_ids.append(int(frame[0, 0, 0]))
        return orig_draw(frame, *a, **kw)

    monkeypatch.setattr(tele_clip, "_risk_alpha", rec_risk)
    monkeypatch.setattr(tele_clip, "_draw_ring", rec_draw)

    track = [{"t": 0.2 * i, "x": 0.4, "y": 0.4, "w": 0.05, "h": 0.12}
             for i in range(0, 60)]  # dense 0..11.8s track
    tele_clip.generate_tracked_clip("fake.mp4", 5.0, track, "/tmp/fix03_clip.mp4")
    c0 = next(v for p, v in fake.seeks if p == cv2.CAP_PROP_POS_MSEC) / 1000.0
    return fake, writer, risk_ts, draw_ids, c0


# ---------- C4 / T7 — ring/risk time belongs to the SAME decoded frame ----------

def test_C4_T7_teleclip_overlays_use_same_decoded_frame_time(monkeypatch):
    times = _teleclip_times()
    fake, writer, risk_ts, draw_ids, c0 = _run_teleclip(monkeypatch, times)
    assert len(draw_ids) == len(risk_ts) > 0
    for t, fid in zip(risk_ts, draw_ids):
        assert abs(times[fid] - t) < 1e-6   # timestamp of THAT decoded frame
    assert risk_ts == sorted(risk_ts)
    # never a regular fps grid
    grid = [round(risk_ts[0] + i * 0.05, 4) for i in range(len(risk_ts))]
    assert risk_ts != grid
    src = (BACKEND / "tele_clip.py").read_text()
    assert "video_timebase.grab_frame_time_seconds(cap, fps)" in src
    assert "idx / fps" not in src and "CAP_PROP_POS_FRAMES" not in src


# ---------- T8 — render window bounded by media time ----------

def test_T8_render_stops_on_media_time(monkeypatch):
    times = _teleclip_times()
    fake, writer, risk_ts, draw_ids, c0 = _run_teleclip(monkeypatch, times)
    c1_max = max(risk_ts)
    assert c1_max < 11.0                     # moment 5.0 + padded window only
    # consumption stopped right after media time passed c1 (one look-ahead grab)
    assert times[fake.last_grabbed] <= c1_max + 0.2
    assert all(t <= c1_max + 1e-6 for t in risk_ts)


# ---------- C8 — CFR output is PTS-resampled, preserving elapsed time ----------

def test_C8_cfr_output_preserves_canonical_elapsed_time(monkeypatch):
    times = _teleclip_times()
    fake, writer, risk_ts, draw_ids, c0 = _run_teleclip(monkeypatch, times)
    out_dt = 1.0 / 20.0
    assert writer.ids, "no output frames"
    rendered_locals = {fid: round(times[fid] - c0, 6) for fid in draw_ids}
    rendered_sorted = sorted(rendered_locals.items(), key=lambda kv: kv[1])
    assert writer.ids == sorted(writer.ids)  # time-monotonic output
    first_fid = draw_ids[0]
    first_local = rendered_locals[first_fid]
    for k, fid in enumerate(writer.ids):
        slot = k * out_dt
        local = rendered_locals[fid]
        if fid == first_fid and slot < first_local - 1e-9:
            continue  # head padding duplicates the first available frame
        assert local <= slot + 1e-6          # never a frame from the future
        # sample-and-hold: no LATER rendered frame existed at/before this slot
        nxt = next((lv for f, lv in rendered_sorted if lv > local), None)
        assert nxt is None or nxt > slot - 1e-9
    # VFR proves drop/duplicate happened: dense 0.04s region -> drops,
    # sparse 0.11s region -> duplicates
    assert len(set(writer.ids)) < len(writer.ids)          # duplicates exist
    assert len(set(draw_ids) - set(writer.ids)) > 0        # drops exist
    # naive sequential append would emit every decoded frame exactly once
    assert writer.ids != draw_ids


# ---------- C9 — moment_local_ms points at the right output frame ----------

def test_C9_moment_maps_to_intended_source_frame(monkeypatch):
    times = _teleclip_times()
    fake, writer, risk_ts, draw_ids, c0 = _run_teleclip(monkeypatch, times)
    out_dt = 1.0 / 20.0
    moment_local = 5.0 - c0                  # == moment_local_ms / 1000
    k = round(moment_local / out_dt)
    assert 0 <= k < len(writer.ids)
    fid = writer.ids[k]
    # the frame shown at the moment slot IS the source moment (dense region:
    # within one output frame interval)
    assert abs((times[fid] - c0) - moment_local) <= out_dt + 1e-6


# ---------- C5 — early keyframe landing decodes forward to actual T ----------

def test_C5_seek_lands_early_then_decodes_forward():
    times = [round(i * 0.1, 4) for i in range(200)]
    cap = FakeCap(times, fps=10.0, keyframes=[0, 30, 60, 90, 120])
    ok, frame, t = video_timebase.read_frame_at(cap, 7.3, fps=10.0)
    assert ok
    assert abs(t - 7.3) < 1e-9               # ACTUAL frame media time returned
    assert int(frame[0, 0, 0]) == 73          # the frame AT 7.3s, not the keyframe
    assert cap.last_grabbed == 73             # decoded forward from keyframe 60
    assert (cv2.CAP_PROP_POS_MSEC, 7300.0) in cap.seeks


# ---------- C6 / T10 — doubt tap uses canonical random access ----------

def test_C6_T10_doubt_tap_canonical_wiring():
    src = (BACKEND / "server.py").read_text()
    assert "CAP_PROP_POS_FRAMES" not in src
    i = src.find("async def _verify_doubt_taps")
    assert i > 0
    seg = src[i:i + 4000]
    assert 'video_timebase.read_frame_at(cap, float(c["t"]))' in seg
    # behaviour of read_frame_at itself is proven in C5


# ---------- C7 / T11 — teleclip edge crop uses actual decoded frame ----------

def test_C7_T11_teleclip_edge_crop_actual_frame(monkeypatch):
    import server
    times = [round(i * 0.1, 4) for i in range(200)]
    fake = FakeCap(times, fps=10.0, keyframes=[0, 30, 60, 90, 120])
    monkeypatch.setattr(cv2, "VideoCapture", lambda p: fake)
    sm = [(0.2 * i, 0.4, 0.4, 0.05, 0.12) for i in range(60)]
    server._teleclip_edge_crop("fake.mp4", sm, 7.3, "/tmp/fix03_edge.jpg")
    assert (cv2.CAP_PROP_POS_MSEC, 7300.0) in fake.seeks
    assert all(p == cv2.CAP_PROP_POS_MSEC for p, _ in fake.seeks)
    assert fake.last_grabbed == 73            # decoded forward to the REAL 7.3s frame
    assert abs(times[fake.last_grabbed] - 7.3) < 1e-9


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
