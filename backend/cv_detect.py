"""Shared local person/ball detector and supporting scene primitives.

Lightweight person detection (YOLOv8n via OpenCV DNN, local, no API), a
minimal camera-compensated multi-object tracker and kit-color team
classification. Everything here is a SUPPORTING layer: it filters candidates
and provides spatial context — it never decides target identity by itself
in the production pipeline.
"""
from __future__ import annotations

import logging
import hashlib
import os
import threading
import time
from collections import OrderedDict
from contextvars import ContextVar
from pathlib import Path
from typing import NamedTuple

import cv2
import numpy as np

logger = logging.getLogger("elite-scout")

DETECTOR_ENABLED = os.environ.get("CV_SHADOW_DETECTOR", "1") == "1"
MODEL_PATH = Path(__file__).resolve().parent / "models" / "yolov8n.onnx"
CONF_T = float(os.environ.get("CV_SHADOW_DET_CONF", "0.25"))
NMS_T = 0.45
INPUT = 640
CURRENT_PREDICTIONS = ContextVar("native_detector_predictions", default=None)


class Predictions(NamedTuple):
    xywh: np.ndarray
    classes: np.ndarray
    scores: np.ndarray
    ball_scores: np.ndarray | None


def _predict(detector, frame):
    height, width = frame.shape[:2]
    scale = INPUT / max(height, width)
    nw, nh = int(width * scale), int(height * scale)
    image = np.zeros((INPUT, INPUT, 3), np.uint8)
    image[:nh, :nw] = cv2.resize(frame, (nw, nh))
    blob = cv2.dnn.blobFromImage(image, 1 / 255.0, (INPUT, INPUT), swapRB=True)
    detector.net.setInput(blob)
    raw = np.asarray(detector.net.forward())
    if raw.size == 0:
        return Predictions(np.empty((0, 4)), np.empty(0, dtype=int), np.empty(0), None)
    if raw.ndim == 3 and raw.shape[0] == 1:
        raw = raw[0]
    if raw.ndim != 2:
        raise ValueError(f"DENSE_DETECTOR_OUTPUT_SHAPE:{raw.shape}")
    if (raw.shape[0] >= 5 and raw.shape[0] < raw.shape[1]) or raw.shape[1] < 5:
        raw = raw.T
    if raw.shape[1] < 5:
        raise ValueError(f"DENSE_DETECTOR_OUTPUT_SHAPE:{raw.shape}")
    scores = raw[:, 4:]
    # Retain exact network coordinates/scores, including ball scores when a
    # different COCO class wins. No box rounding or NMS moves between callers.
    return Predictions(raw[:, :4], scores.argmax(1), scores.max(1),
                       scores[:, 32] if scores.shape[1] > 32 else None)


def predict(detector, frame, *, ball_floor=.001):
    """Stateless network candidates; callers retain their own NMS and rules."""
    cache = CURRENT_PREDICTIONS.get()
    return _predict(detector, frame) if cache is None else cache.predict(detector, frame, ball_floor)


class PredictionCache:
    """Bounded, exact-pixel reuse across one report's native detector readers.

    Cache only the head values used by person/ball readers, with no precision
    conversion. All other class scores have already contributed to argmax/max.
    Source coverage, tracks, kit measurements and decisions remain caller-owned.
    """
    def __init__(self, max_bytes=64 * 1024 * 1024, max_entries=8192):
        self.max_bytes, self.max_entries = max(0, int(max_bytes)), max(0, int(max_entries))
        self._cache, self._bytes = OrderedDict(), 0
        self._lock = threading.RLock()
        self.hits = self.misses = self.evictions = self.forwards = 0
        self.forward_seconds = 0.

    def predict(self, detector, frame, ball_floor):
        model_sha = getattr(detector, "model_sha256", None)
        key = None
        if (self.max_bytes and self.max_entries and isinstance(model_sha, str) and len(model_sha) == 64):
            settings = (model_sha, type(detector.net).__module__, type(detector.net).__qualname__,
                        INPUT, CONF_T, float(ball_floor), frame.shape, frame.dtype.str)
            digest = hashlib.sha256(repr(settings).encode())
            digest.update(frame.tobytes(order="C"))
            key = digest.digest()
        with self._lock:
            if key in self._cache:
                self.hits += 1
                saved = self._cache[key]
                self._cache.move_to_end(key)
                return Predictions(*(a.copy() if a is not None else None for a in saved))
            self.misses += 1
            started = time.monotonic()
            try:
                result = _predict(detector, frame)
            finally:
                self.forwards += 1
                self.forward_seconds += time.monotonic() - started
            if key is not None and len(result.scores):
                keep = (result.classes == 0) & (result.scores > CONF_T)
                if result.ball_scores is not None:
                    keep |= result.ball_scores > float(ball_floor)
                saved = Predictions(*(a[keep].copy() if a is not None else None for a in result))
                size = sum(a.nbytes for a in saved if a is not None)
                if size <= self.max_bytes:
                    while self._cache and (len(self._cache) >= self.max_entries or self._bytes + size > self.max_bytes):
                        _, old = self._cache.popitem(last=False)
                        self._bytes -= sum(a.nbytes for a in old if a is not None)
                        self.evictions += 1
                    for array in saved:
                        if array is not None:
                            array.flags.writeable = False
                    self._cache[key] = saved
                    self._bytes += size
            return result

    def metrics(self):
        with self._lock:
            return {"hits": self.hits, "misses": self.misses, "detector_forwards": self.forwards,
                    "forward_seconds": round(self.forward_seconds, 3), "evictions": self.evictions,
                    "entries": len(self._cache), "payload_bytes": self._bytes,
                    "max_payload_bytes": self.max_bytes, "max_entries": self.max_entries,
                    "scope": "RUN_LOCAL_EXACT_NATIVE_PREDICTIONS_NO_DECISIONS"}


class PersonDetector:
    """YOLOv8n person detection via cv2.dnn. Lazy-loaded; fails safe."""

    def __init__(self, *, enabled=None):
        """Load the shared local detector.

        ``enabled=None`` preserves the legacy shadow-mode feature flag.  A
        production caller must pass its own explicit boolean so disabling the
        old shadow diagnostics cannot silently disable FIX09A/FIX09B.
        """
        self.net = None
        self.ok = False
        self.model_sha256 = None
        self.enabled = DETECTOR_ENABLED if enabled is None else bool(enabled)
        try:
            if self.enabled and MODEL_PATH.exists() and MODEL_PATH.stat().st_size > 1_000_000:
                self.net = cv2.dnn.readNetFromONNX(str(MODEL_PATH))
                self.model_sha256 = hashlib.sha256(MODEL_PATH.read_bytes()).hexdigest()
                self.ok = True
        except Exception as e:
            logger.warning(f"[cv-detect] model load failed: {e}")
            self.ok = False

    def detect(self, frame_bgr):
        """→ list of (x, y, w, h, conf) normalized to the input frame."""
        if not self.ok:
            return []
        H, W = frame_bgr.shape[:2]
        s = INPUT / max(H, W)
        out, cls, conf, _ball_scores = predict(self, frame_bgr)
        keep = (cls == 0) & (conf > CONF_T)
        boxes, scores = [], []
        for r, c in zip(out[keep], conf[keep]):
            cx, cy, w, h = r[:4]
            boxes.append([int(cx - w / 2), int(cy - h / 2), int(w), int(h)])
            scores.append(float(c))
        idx = cv2.dnn.NMSBoxes(boxes, scores, CONF_T, NMS_T)
        dets = []
        for i in np.array(idx).flatten() if len(idx) else []:
            x, y, w, h = boxes[i]
            dets.append((x / (W * s), y / (H * s), w / (W * s), h / (H * s), scores[i]))
        return dets


def _iou(a, b):
    ax0, ay0, ax1, ay1 = a[0], a[1], a[0] + a[2], a[1] + a[3]
    bx0, by0, bx1, by1 = b[0], b[1], b[0] + b[2], b[1] + b[3]
    ix = max(0.0, min(ax1, bx1) - max(ax0, bx0))
    iy = max(0.0, min(ay1, by1) - max(ay0, by0))
    inter = ix * iy
    return inter / max(1e-6, a[2] * a[3] + b[2] * b[3] - inter)


class MiniMOT:
    """Minimal greedy IoU tracker with camera compensation. Supporting layer
    only — internal track IDs give spatial context (crossover/separation);
    they NEVER decide target identity."""

    def __init__(self, max_misses=6):
        self.tracks = []
        self.next_id = 1
        self.max_misses = max_misses
        self.created = 0
        self.crossover_events = 0

    def update(self, dets, cam_dx=0.0, cam_dy=0.0):
        """dets: list of (x,y,w,h) px boxes. Returns active track list."""
        for tr in self.tracks:
            tr["pred"] = (tr["box"][0] + cam_dx, tr["box"][1] + cam_dy,
                          tr["box"][2], tr["box"][3])
        pairs = []
        for ti, tr in enumerate(self.tracks):
            for di, d in enumerate(dets):
                v = _iou(tr["pred"], d)
                if v > 0.10:
                    pairs.append((v, ti, di))
        pairs.sort(reverse=True)
        used_t, used_d = set(), set()
        for v, ti, di in pairs:
            if ti in used_t or di in used_d:
                continue
            used_t.add(ti)
            used_d.add(di)
            self.tracks[ti]["box"] = dets[di]
            self.tracks[ti]["hits"] += 1
            self.tracks[ti]["misses"] = 0
        for ti, tr in enumerate(self.tracks):
            if ti not in used_t:
                tr["misses"] += 1
        for di, d in enumerate(dets):
            if di not in used_d:
                self.tracks.append({"id": self.next_id, "box": d, "hits": 1, "misses": 0})
                self.next_id += 1
                self.created += 1
        self.tracks = [t for t in self.tracks if t["misses"] <= self.max_misses]
        # crossover pressure: two live tracks overlapping
        live = [t for t in self.tracks if t["misses"] == 0]
        for i in range(len(live)):
            for j in range(i + 1, len(live)):
                if _iou(live[i]["box"], live[j]["box"]) > 0.15:
                    self.crossover_events += 1
        return live


class CameraMotion:
    """Phase 8 — full global camera motion (pan/zoom/rotation) via sparse
    optical flow + RANSAC similarity transform on a tiny gray frame.
    Falls back to phase-correlation translation; fails safe to no motion.
    Supporting layer only — never decides identity."""

    def __init__(self, out_scale=1.0):
        self.prev = None
        self.M = None
        self.mode = "none"
        self.affine_frames = 0
        self.fallback_frames = 0
        self.out_scale = float(out_scale)
        self.dx = 0.0
        self.dy = 0.0

    def update(self, tiny_gray_f32):
        prev, self.prev = self.prev, tiny_gray_f32
        self.M, self.mode = None, "none"
        self.dx = self.dy = 0.0
        if prev is None:
            return
        p8 = prev.astype(np.uint8)
        c8 = tiny_gray_f32.astype(np.uint8)
        try:
            pts = cv2.goodFeaturesToTrack(p8, maxCorners=120, qualityLevel=0.01,
                                          minDistance=6)
            if pts is not None and len(pts) >= 20:
                nxt, st, _ = cv2.calcOpticalFlowPyrLK(p8, c8, pts, None,
                                                      winSize=(15, 15), maxLevel=2)
                good = st.reshape(-1) == 1
                if good.sum() >= 12:
                    M, inl = cv2.estimateAffinePartial2D(
                        pts[good], nxt[good], method=cv2.RANSAC,
                        ransacReprojThreshold=2.0)
                    if M is not None and inl is not None and int(inl.sum()) >= 10:
                        self.M = M
                        self.mode = "affine"
                        self.affine_frames += 1
                        h, w = p8.shape[:2]
                        cx, cy = w / 2.0, h / 2.0
                        nx = M[0, 0] * cx + M[0, 1] * cy + M[0, 2]
                        ny = M[1, 0] * cx + M[1, 1] * cy + M[1, 2]
                        self.dx = (nx - cx) * self.out_scale
                        self.dy = (ny - cy) * self.out_scale
                        return
        except Exception:
            pass
        try:
            (dx, dy), _ = cv2.phaseCorrelate(prev, tiny_gray_f32)
            self.dx, self.dy = dx * self.out_scale, dy * self.out_scale
            self.mode = "translation"
            self.fallback_frames += 1
        except Exception:
            self.mode = "none"

    def point(self, x, y):
        """Transform a point (in output/small coords) through the last motion."""
        if self.M is None:
            return (x + self.dx, y + self.dy)
        tx, ty = x / self.out_scale, y / self.out_scale
        nx = self.M[0, 0] * tx + self.M[0, 1] * ty + self.M[0, 2]
        ny = self.M[1, 0] * tx + self.M[1, 1] * ty + self.M[1, 2]
        return (nx * self.out_scale, ny * self.out_scale)


def torso_chroma(small, box):
    """Median Lab (a, b) chroma of the non-pitch torso zone → kit signature.
    Chroma is far more lighting-stable than hue/brightness."""
    x, y, w, h = [int(v) for v in box]
    y0, y1 = y + int(h * 0.2), y + int(h * 0.55)
    x0, x1 = max(0, x), min(small.shape[1], x + w)
    y0, y1 = max(0, y0), min(small.shape[0], max(y1, y0 + 2))
    roi = small[y0:y1, x0:x1]
    if roi.size < 60:
        return None
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    ng = cv2.inRange(hsv, (30, 40, 40), (90, 255, 255)) == 0
    lab = cv2.cvtColor(roi, cv2.COLOR_BGR2LAB)
    a = lab[:, :, 1][ng]
    b = lab[:, :, 2][ng]
    if a.size < 30:
        a, b = lab[:, :, 1].reshape(-1), lab[:, :, 2].reshape(-1)
    return (float(np.median(a)), float(np.median(b)))


class TeamModel:
    """K-means (k=2) over detection kit chromas. Classifies detections into
    target_team / opponent / other (referee, GK — far from both kits).
    A candidate FILTER only — never treated as target identity."""

    def __init__(self, target_anchor):
        self.samples = []
        self.centers = None
        self.target_ci = None
        self.anchor = target_anchor  # chroma of the tapped player's kit

    def add(self, ch):
        if ch and len(self.samples) < 400:
            self.samples.append(ch)
            # early fit for availability, refits as scenes accumulate
            if len(self.samples) in (30, 150, 400):
                self._fit()

    def _fit(self):
        data = np.float32(self.samples)
        if len(data) < 2:
            return
        # Random k-means starts made identical windows lose or regain team
        # authority depending on other jobs' RNG use. Use deterministic starts
        # on both chroma axes and the principal axis, retaining the best fit.
        _, _, axes = np.linalg.svd(data - data.mean(axis=0), full_matrices=False)
        starts = [np.array([1.0, 0.0]), np.array([0.0, 1.0]), axes[0]]
        fits = []
        for axis in starts:
            projection = data @ axis
            seeds = data[[int(np.argmin(projection)), int(np.argmax(projection))]]
            labels = np.argmin(((data[:, None] - seeds) ** 2).sum(axis=2), axis=1)
            if len(np.unique(labels)) < 2:
                continue
            compactness, _, fitted = cv2.kmeans(
                data, 2, labels.astype(np.int32).reshape(-1, 1),
                (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 0.5),
                1, cv2.KMEANS_USE_INITIAL_LABELS)
            ordered = np.array(sorted(tuple(float(v) for v in c) for c in fitted), dtype=np.float32)
            fits.append((float(compactness), ordered))
        centers = min(fits, key=lambda fit: fit[0])[1] if fits else np.stack((data[0], data[0]))
        self.centers = centers
        if self.anchor is not None:
            d = [np.hypot(c[0] - self.anchor[0], c[1] - self.anchor[1]) for c in centers]
            self.target_ci = int(np.argmin(d))

    def classify(self, ch):
        """→ 'target_team' | 'opponent' | 'other' | None (not ready)."""
        if ch is None or self.centers is None or self.target_ci is None:
            return None
        d = [np.hypot(c[0] - ch[0], c[1] - ch[1]) for c in self.centers]
        ci = int(np.argmin(d))
        if d[ci] > 18.0:
            return "other"  # referee / GK / spectator kit
        return "target_team" if ci == self.target_ci else "opponent"
