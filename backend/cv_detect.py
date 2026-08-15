"""cv_detect.py — P3 scene awareness for the SHADOW identity engine.

Lightweight person detection (YOLOv8n via OpenCV DNN, local, no API), a
minimal camera-compensated multi-object tracker and kit-color team
classification. Everything here is a SUPPORTING layer: it filters candidates
and provides spatial context — it never decides target identity by itself
and never touches the production pipeline.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

import cv2
import numpy as np

logger = logging.getLogger("elite-scout")

DETECTOR_ENABLED = os.environ.get("CV_SHADOW_DETECTOR", "1") == "1"
MODEL_PATH = Path(__file__).resolve().parent / "models" / "yolov8n.onnx"
CONF_T = float(os.environ.get("CV_SHADOW_DET_CONF", "0.25"))
NMS_T = 0.45
INPUT = 640


class PersonDetector:
    """YOLOv8n person detection via cv2.dnn. Lazy-loaded; fails safe."""

    def __init__(self):
        self.net = None
        self.ok = False
        try:
            if DETECTOR_ENABLED and MODEL_PATH.exists() and MODEL_PATH.stat().st_size > 1_000_000:
                self.net = cv2.dnn.readNetFromONNX(str(MODEL_PATH))
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
        nw, nh = int(W * s), int(H * s)
        img = np.zeros((INPUT, INPUT, 3), np.uint8)
        img[:nh, :nw] = cv2.resize(frame_bgr, (nw, nh))
        blob = cv2.dnn.blobFromImage(img, 1 / 255.0, (INPUT, INPUT), swapRB=True)
        self.net.setInput(blob)
        out = self.net.forward()[0].T  # (8400, 84)
        cls = out[:, 4:].argmax(1)
        conf = out[:, 4:].max(1)
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
        _, _, centers = cv2.kmeans(
            data, 2, None,
            (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 0.5),
            5, cv2.KMEANS_PP_CENTERS)
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
