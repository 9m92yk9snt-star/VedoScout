"""cv_shadow.py — SHADOW-MODE CV identity engine (P0-P6 of the identity brief).

Runs IN PARALLEL with the existing production tracker and ONLY observes + logs.
It never influences reports, tracking, analysis, markers or proof clips.
Production authority stays with the existing pipeline; every gate here is a
future candidate that must first prove itself on real footage.

Design rules honoured:
- identity certainty > tracking coverage (UNCERTAIN/LOST over guessing)
- taps form ONE reference identity (consistency + outlier downweighting)
- multi-scale features (never punish a far player for unreadable details)
- crossover freeze (no identity learning in ambiguous frames)
- margin rule (best candidate must CLEARLY beat the runner-up)
- safe re-acquisition (stricter gate after LOST)
- modular + feature-flagged; zero new dependencies; zero LLM cost

Calibrated on real footage (report bd972050, 11 taps, white kit + blue
opponents, sun/shade changes): appearance = component-masked, illumination-
normalized Lab moments. It separates TEAMS reliably; identical-kit teammates
stay close by design → margin rule yields UNCERTAIN there (fail-safe).
"""
from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

import cv_detect
import video_timebase

logger = logging.getLogger("elite-scout")

SHADOW_ENABLED = os.environ.get("CV_SHADOW_ENABLED", "1") == "1"
HZ = float(os.environ.get("CV_SHADOW_HZ", "5"))
SMALL_W = int(os.environ.get("CV_SHADOW_WIDTH", "480"))

SIM_T = float(os.environ.get("CV_SHADOW_SIM_T", "0.45"))
MARGIN_T = float(os.environ.get("CV_SHADOW_MARGIN_T", "0.10"))
REACQ_BONUS = 0.05   # stricter gate after LOST
MAX_SPEED = 0.28     # frame-widths per second (camera-compensated)
LOST_GRACE = 1.2     # seconds without candidates before LOST

# Lab tolerances for similarity (L, a, b, stdL, stda, stdb)
_TOL = np.array([30.0, 10.0, 10.0, 22.0, 10.0, 10.0])


# ---------------------------------------------------------------- utilities
def _green_mask(bgr):
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    return cv2.inRange(hsv, (30, 40, 40), (90, 255, 255))


def _pitch_l(small) -> float:
    """Median pitch luminance — reference for sun/shade normalisation."""
    g = _green_mask(small) > 0
    if g.sum() < 100:
        return 140.0
    lab = cv2.cvtColor(small, cv2.COLOR_BGR2LAB)
    return float(np.median(lab[:, :, 0][g]))


def _sharpness(gray) -> float:
    v = cv2.Laplacian(gray, cv2.CV_64F).var()
    return float(min(1.0, v / 250.0))


def _comp_mask_crop(small, box):
    """Isolate the single non-pitch component nearest the box centre.
    Excludes a second player in the same rectangle when they are separable.
    Returns (crop, mask, merged) — merged=True when nothing could be isolated."""
    x, y, w, h = box
    pad = int(h * 0.1)
    x0, y0 = max(0, x - pad), max(0, y - pad)
    x1 = min(small.shape[1], x + w + pad)
    y1 = min(small.shape[0], y + h + pad)
    roi = small[y0:y1, x0:x1]
    ng = cv2.bitwise_not(_green_mask(roi))
    ng = cv2.morphologyEx(ng, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    n, lbl, stats, cents = cv2.connectedComponentsWithStats(ng, 8)
    cx, cy = (x + w / 2) - x0, (y + h / 2) - y0
    best, bd = 0, 1e9
    for i in range(1, n):
        if stats[i, 4] < 30:
            continue
        d = abs(cents[i][0] - cx) + abs(cents[i][1] - cy)
        if d < bd:
            bd, best = d, i
    if best == 0:
        return roi, np.full(roi.shape[:2], 255, np.uint8), True, (x0, y0)
    m = (lbl == best).astype(np.uint8) * 255
    xs = np.where(m.any(0))[0]
    ys = np.where(m.any(1))[0]
    return (roi[ys[0]:ys[-1] + 1, xs[0]:xs[-1] + 1],
            m[ys[0]:ys[-1] + 1, xs[0]:xs[-1] + 1], False,
            (x0 + int(xs[0]), y0 + int(ys[0])))


def _zone_embedding(small, box, pitch_l, occluders=None):
    """Multi-scale zone embedding over the ISOLATED person component only.
    Per zone: illumination-normalized Lab mean+std. Zones adapt to pixel size —
    a far player is never compared on details the camera cannot resolve.
    Phase 4 feature ownership: pixels covered by OCCLUDING people are removed
    from the mask so the target is never matched on someone else's body; if
    too little of the target stays visible the sample is tagged owned=False
    instead of silently comparing contaminated features."""
    crop, mask, merged, (gx, gy) = _comp_mask_crop(small, box)
    h, w = crop.shape[:2]
    if h < 12 or w < 4:
        return None
    owned = None
    if occluders:
        om = mask.copy()
        for oc in occluders:
            lx0, ly0 = max(0, int(oc[0]) - gx), max(0, int(oc[1]) - gy)
            lx1 = min(w, int(oc[0] + oc[2]) - gx)
            ly1 = min(h, int(oc[1] + oc[3]) - gy)
            if lx1 > lx0 and ly1 > ly0:
                om[ly0:ly1, lx0:lx1] = 0
        kept = int((om > 0).sum())
        if kept >= 0.30 * max(1, int((mask > 0).sum())) and kept >= 30:
            mask, owned = om, True
        else:
            owned = False  # too occluded to own its features — tagged, never guessed
    lab = cv2.cvtColor(crop, cv2.COLOR_BGR2LAB).astype(np.float32)
    lab[:, :, 0] *= 140.0 / max(30.0, pitch_l)
    if h >= 90:
        cuts, scale = [0.0, 0.18, 0.55, 0.80, 1.0], "close"
    elif h >= 40:
        cuts, scale = [0.0, 0.30, 0.72, 1.0], "medium"
    else:
        cuts, scale = [0.0, 0.5, 1.0], "far"
    zones = []
    for a, b in zip(cuts, cuts[1:]):
        y0, y1 = int(a * h), max(int(b * h), int(a * h) + 1)
        z = lab[y0:y1].reshape(-1, 3)
        mm = mask[y0:y1].reshape(-1) > 0
        zs = z[mm] if mm.sum() >= 10 else z
        zones.append(np.concatenate([zs.mean(0), zs.std(0)]))
    return {"scale": scale, "zones": zones, "aspect": h / max(1, w),
            "merged": merged, "px_h": h, "owned": owned}


def _sim(a, b) -> float:
    """Similarity between two embeddings, comparable across scales by pooling
    onto the coarser zone layout. Tolerance-scaled Lab distance → [0,1]."""
    if not a or not b:
        return 0.0
    za, zb = a["zones"], b["zones"]
    n = min(len(za), len(zb))

    def pool(zs, k):
        if len(zs) == k:
            return zs
        out, step = [], len(zs) / k
        for i in range(k):
            seg = zs[int(i * step):max(int((i + 1) * step), int(i * step) + 1)]
            out.append(np.mean(seg, axis=0))
        return out

    za, zb = pool(za, n), pool(zb, n)
    ds = []
    for x, y in zip(za, zb):
        d = np.abs(x - y) / _TOL
        ds.append(float(np.clip(1.0 - d.mean(), 0.0, 1.0)))
    asp = 1.0 - min(0.5, abs(a["aspect"] - b["aspect"]) / 4.0)
    return float(np.mean(ds)) * asp


def _blobs(small, mask_roi, min_h, max_h):
    """Non-pitch blobs inside an ROI mask → candidate player boxes (px)."""
    non_green = cv2.bitwise_not(_green_mask(small))
    non_green = cv2.bitwise_and(non_green, mask_roi)
    non_green = cv2.morphologyEx(non_green, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    non_green = cv2.morphologyEx(non_green, cv2.MORPH_CLOSE, np.ones((7, 3), np.uint8))
    n, _, stats, _ = cv2.connectedComponentsWithStats(non_green, 8)
    out = []
    for i in range(1, n):
        x, y, w, h, area = stats[i]
        if h < min_h or h > max_h or w > h * 1.6 or area < 0.25 * w * h:
            continue
        out.append((x, y, w, h))
    return out[:24]


def _iou(a, b) -> float:
    ax0, ay0, ax1, ay1 = a[0], a[1], a[0] + a[2], a[1] + a[3]
    bx0, by0, bx1, by1 = b[0], b[1], b[0] + b[2], b[1] + b[3]
    ix = max(0, min(ax1, bx1) - max(ax0, bx0))
    iy = max(0, min(ay1, by1) - max(ay0, by0))
    inter = ix * iy
    return inter / max(1.0, a[2] * a[3] + b[2] * b[3] - inter)


def _cluster_windows(ts_list, join=1.0, pad=0.3):
    """Merge nearby timestamps into [t0, t1] windows."""
    ts = sorted(float(t) for t in ts_list)
    out = []
    for t in ts:
        if out and t - out[-1][1] <= join:
            out[-1][1] = t
        else:
            out.append([t, t])
    return [[round(max(0.0, a - pad), 1), round(b + pad, 1)] for a, b in out]


def bridge_track_points(points, windows, hz=5.0):
    """Phase 15 ACTIVATION: return a COPY of the production track where small,
    pre-validated safe gaps are linearly interpolated (identity verified on
    both sides, no crowding, physics-realistic — validated in shadow). The
    stored production track is NEVER mutated; this only feeds rendering."""
    if not points or not windows:
        return points
    pts = sorted((dict(p) for p in points), key=lambda p: float(p["t"]))
    added = []
    for w in windows:
        try:
            w0, w1 = float(w[0]), float(w[1])
        except Exception:
            continue
        p0 = max((p for p in pts if float(p["t"]) <= w0 + 0.05),
                 key=lambda p: float(p["t"]), default=None)
        p1 = min((p for p in pts if float(p["t"]) >= w1 - 0.05),
                 key=lambda p: float(p["t"]), default=None)
        if not p0 or not p1:
            continue
        t0, t1 = float(p0["t"]), float(p1["t"])
        if t1 - t0 <= 0:
            continue
        n = int((t1 - t0) * hz)
        for k in range(1, n):
            f = k / n
            added.append({
                "t": round(t0 + f * (t1 - t0), 3),
                "x": float(p0["x"]) + f * (float(p1["x"]) - float(p0["x"])),
                "y": float(p0["y"]) + f * (float(p1["y"]) - float(p0["y"])),
                "w": float(p0["w"]) + f * (float(p1["w"]) - float(p0["w"])),
                "h": float(p0["h"]) + f * (float(p1["h"]) - float(p0["h"])),
                "conf": round(min(float(p0.get("conf") or 0.8),
                                  float(p1.get("conf") or 0.8)) * 0.9, 3),
                "bridged": True,
            })
    if not added:
        return points
    return sorted(list(pts) + added, key=lambda p: float(p["t"]))


# ---------------------------------------------------------------- reference
def _build_tap_references(cap, fps, anchors, t_off, sw, sh, scale, detector=None):
    """P1-P4: refine each user tap to the actual person, score its quality,
    embed it, then cross-check all taps into ONE identity with outliers
    downweighted — a single bad tap can never contaminate the profile.
    Refinement prefers REAL person detections (fixes merged/contaminated
    taps); connected-component blobs remain the fallback."""
    refs, negatives = [], []
    for a in anchors:
        try:
            t = float(a["t"]) + (t_off or 0.0)
            box = a["box"]
            # FIX 03 — canonical media-time seek (VFR-safe), never t*fps
            video_timebase.seek_seconds(cap, max(0.0, t))
            ok, frame = cap.read()
            if not ok:
                continue
            small = cv2.resize(frame, (sw, sh))
            pl = _pitch_l(small)
            bx = int(box["x"] * sw)
            by = int(box["y"] * sh)
            bw = max(4, int(box["w"] * sw))
            bh = max(8, int(box["h"] * sh))
            pad_x, pad_y = int(bw * 0.15), int(bh * 0.15)
            rx0, ry0 = max(0, bx - pad_x), max(0, by - pad_y)
            rx1, ry1 = min(sw, bx + bw + pad_x), min(sh, by + bh + pad_y)
            roi_mask = np.zeros((sh, sw), np.uint8)
            roi_mask[ry0:ry1, rx0:rx1] = 255
            cand = _blobs(small, roi_mask, min_h=max(8, int(bh * 0.4)), max_h=int(bh * 1.6))
            cx0, cy0 = bx + bw / 2, by + bh / 2
            # person detections inside the padded region (preferred refinement)
            det_in = []
            if detector is not None and detector.ok:
                for (nx, ny, nw_, nh_, dc) in detector.detect(frame):
                    c = (int(nx * sw), int(ny * sh),
                         max(3, int(nw_ * sw)), max(6, int(nh_ * sh)))
                    ccx, ccy = c[0] + c[2] / 2, c[1] + c[3] / 2
                    if rx0 <= ccx <= rx1 and ry0 <= ccy <= ry1 and bh * 0.4 <= c[3] <= bh * 1.7:
                        det_in.append(c)
            if det_in:
                rb = min(det_in, key=lambda c: abs(c[0] + c[2] / 2 - cx0) + abs(c[1] + c[3] / 2 - cy0))
                refined_by = "detector"
            elif cand:
                rb = min(cand, key=lambda c: abs(c[0] + c[2] / 2 - cx0) + abs(c[1] + c[3] / 2 - cy0))
                refined_by = "blob"
            else:
                rb = (bx, by, bw, bh)  # fallback: trust the raw tap box
                refined_by = "raw"
            # visible-body awareness first: other people near the refined box —
            # they both drive the visibility score and are removed from the
            # embedding mask (Phase 4 feature ownership at tap references)
            others_near = [c for c in (det_in or cand) if c != rb]
            emb = _zone_embedding(small, rb, pl,
                                  occluders=[c for c in others_near if _iou(c, rb) > 0.05])
            if not emb:
                continue
            occ_frac = 0.0
            for c in others_near:
                ix = max(0, min(rb[0] + rb[2], c[0] + c[2]) - max(rb[0], c[0]))
                iy = max(0, min(rb[1] + rb[3], c[1] + c[3]) - max(rb[1], c[1]))
                occ_frac = max(occ_frac, (ix * iy) / max(1.0, rb[2] * rb[3]))
            visibility = round(1.0 - min(1.0, occ_frac), 3)
            overlaps = sum(1 for c in others_near if _iou(c, rb) > 0.10)
            crop = small[rb[1]:rb[1] + rb[3], rb[0]:rb[0] + rb[2]]
            gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
            quality = round(
                0.30 * min(1.0, rb[3] / 60.0)              # pixel size
                + 0.25 * _sharpness(gray)                   # blur
                + 0.30 * visibility                          # occlusion / visible body
                + 0.15 * (0.0 if emb.get("merged") else 1.0),  # isolation
                3,
            )
            refs.append({"t": round(t, 2), "emb": emb, "quality": quality,
                         "box": rb, "refined": refined_by != "raw",
                         "refined_by": refined_by, "visibility": visibility,
                         "overlaps": overlaps, "merged": bool(emb.get("merged")),
                         "chroma": cv_detect.torso_chroma(small, rb)})
            # P10 negative gallery: OTHER people at the tap moment (same scene)
            for c in others_near:
                if _iou(c, rb) > 0.3:
                    continue
                oe = _zone_embedding(small, c, pl)
                if oe:
                    _add_negative(negatives, oe)
        except Exception:
            continue
    # P4 consistency: pairwise similarity → outliers downweighted; a clearly
    # wrong tap (far below the group AND low quality) is fully REJECTED —
    # one bad tap must never contaminate the identity. Max 2 rejections,
    # never with fewer than 5 usable taps.
    for r in refs:
        sims = [_sim(r["emb"], o["emb"]) for o in refs if o is not r]
        r["consistency"] = round(float(np.mean(sims)), 3) if sims else 1.0
    med = float(np.median([r["consistency"] for r in refs])) if refs else 0.0
    rejected = 0
    for r in sorted(refs, key=lambda x: x["consistency"]):
        r["outlier"] = bool(r["consistency"] < med - 0.15)
        r["rejected"] = False
        if (len(refs) >= 5 and rejected < 2
                and r["consistency"] < med - 0.30 and r["quality"] < 0.5):
            r["rejected"] = True
            rejected += 1
    for r in refs:
        r["weight"] = 0.0 if r["rejected"] else round(
            (0.3 if r["outlier"] else 1.0)
            * (0.5 if r["merged"] else 1.0)
            * max(0.2, r["quality"]), 3)
    return refs, negatives


def _profile_sim(emb, refs) -> float:
    """Weighted mean of the 3 best tap matches — one identity, many views.
    Phase 3 multi-view: same-scale references are PREFERRED during selection
    (a far player is matched against far-view taps when available) without
    ever penalising the similarity value itself."""
    if not refs:
        return 0.0
    scale = emb.get("scale") if emb else None
    ranked = sorted(
        ((_sim(emb, r["emb"]), r) for r in refs),
        key=lambda sr: -(sr[0] + (0.05 if sr[1]["emb"].get("scale") == scale else 0.0)),
    )[:3]
    tw = sum(r["weight"] for _, r in ranked)
    return sum(s * r["weight"] for s, r in ranked) / max(1e-6, tw)


def _sim_relaxed(emb, refs) -> float:
    """Pose-tolerant similarity: whole-body pooled stats, no zone order, no
    aspect penalty. A bent/fallen target keeps its colours even when the
    vertical zone layout scrambles — used ONLY to avoid false alarms, never
    to raise confidence."""
    if not emb or not refs:
        return 0.0
    pooled = np.mean(emb["zones"], axis=0)
    best = 0.0
    for r in refs:
        rp = np.mean(r["emb"]["zones"], axis=0)
        d = np.abs(pooled - rp) / _TOL
        best = max(best, float(np.clip(1.0 - d.mean(), 0.0, 1.0)))
    return best


def _add_negative(negatives, emb, cap=30):
    """Phase 7 persistent negative gallery: keep DISTINCT teammates only —
    near-duplicates are skipped so the cap covers different players."""
    if not emb or len(negatives) >= cap:
        return False
    for n in negatives:
        if _sim(emb, n) > 0.92:
            return False
    negatives.append(emb)
    return True


# ---------------------------------------------------------------- main scan
def run_shadow(report_id: str, video_path: str, doc: dict) -> Optional[dict]:
    """Full shadow pass. Returns the metrics dict (also logged). Never raises."""
    t_start = time.time()
    cap = None
    try:
        anchors = [a for a in (doc.get("anchors") or []) if isinstance(a, dict) and a.get("box")]
        track_pts = [p for p in ((doc.get("player_track") or {}).get("points") or [])
                     if isinstance(p, dict) and isinstance(p.get("t"), (int, float))]
        if not anchors:
            return {"status": "skipped", "reason": "no_anchors"}
        t_off = float(doc.get("anchor_time_offset") or 0.0)
        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            return {"status": "skipped", "reason": "no_video"}
        fps = cap.get(cv2.CAP_PROP_FPS) or 15.0
        W = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        H = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        if W < 100 or H < 100 or total < 10:
            return {"status": "skipped", "reason": "bad_video"}
        # FIX 03 — media duration is authoritative; frame_count/fps is an
        # explicit last-resort fallback only
        dur = video_timebase.media_duration_seconds(video_path) or (total / fps)
        scale = SMALL_W / W
        sw, sh = SMALL_W, max(2, int(H * scale))

        detector = cv_detect.PersonDetector()
        refs, negatives = _build_tap_references(cap, fps, anchors, t_off, sw, sh, scale,
                                                detector=detector)
        if len(refs) < 3:
            return {"status": "skipped", "reason": "too_few_references"}

        # production track lookup (video time)
        def prod_at(t):
            near = [p for p in track_pts if abs(float(p["t"]) - t) <= 0.45]
            return min(near, key=lambda p: abs(float(p["t"]) - t)) if near else None

        med_h = float(np.median([r["box"][3] for r in refs]))
        state, last_pos, last_t, lost_since = "LOST", None, None, 0.0
        reacq_streak = 0
        reacq_pending, lost_in_crowd = False, False
        reacq_attempts = reacq_verified = reacq_team_rejected = 0
        reacq_need_max = 2
        states_count = {"VERIFIED": 0, "PROVISIONAL": 0, "UNCERTAIN": 0, "LOST": 0}
        crossovers = potential_switches = samples = 0
        margins, agreements = [], []
        # v3: direct verification of the PRODUCTION box — "does the content of
        # the current production track box still look like the tapped player?"
        prod_sims, prod_suspect, prod_crowded, switch_risk = [], 0, 0, 0
        suspect_ts, switch_ts, crowded_ts = [], [], []
        prev_prod_low = False  # pose-robustness: flags need 2 consecutive low samples
        prod_empty = 0
        prev_prod_empty = False
        empty_ts = []
        sample_log = []  # per-sample prod context for gap-bridging analysis
        own_evals = contaminated_evals = 0
        neg_match = teleport = 0
        neg_ts, teleport_ts = [], []
        prev_neg_hit = False
        prev_prod_c, prev_prod_t = None, None

        # flagged-moment gallery: small annotated frames so an admin can judge
        # every finding (true risk vs false alarm) with their own eyes
        try:
            frames_dir = Path(video_path).parent / "frames" / str(report_id)
            frames_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            frames_dir = None
        saved_imgs = 0
        _last_save = {}

        def _save_flag_frame(small_img, t, pb, other_box, ps, kind):
            nonlocal saved_imgs
            if frames_dir is None or saved_imgs >= 12:
                return None
            if kind == "SUSPECT" and saved_imgs >= 8:
                return None  # reserve slots for the rarer switch-risk frames
            if t - _last_save.get(kind, -9.0) < 1.5:
                return None  # one image per incident, not per sample
            try:
                vis = small_img.copy()
                cv2.rectangle(vis, (pb[0], pb[1]), (pb[0] + pb[2], pb[1] + pb[3]),
                              (0, 255, 255), 2)
                if other_box is not None:
                    cv2.rectangle(vis, (other_box[0], other_box[1]),
                                  (other_box[0] + other_box[2], other_box[1] + other_box[3]),
                                  (0, 0, 255), 2)
                cv2.putText(vis, f"{kind} t={t:.1f}s sim={ps:.2f}", (8, 22),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2)
                name = f"cvshadow_{int(round(t * 10))}.jpg"
                cv2.imwrite(str(frames_dir / name), vis,
                            [cv2.IMWRITE_JPEG_QUALITY, 70])
                saved_imgs += 1
                _last_save[kind] = t
                return name
            except Exception:
                return None

        # ── P3 scene awareness (detector + MOT + team classification) ──
        mot = cv_detect.MiniMOT()
        _tap_chromas = [r["chroma"] for r in refs if r.get("chroma")]
        _anchor = (float(np.median([c[0] for c in _tap_chromas])),
                   float(np.median([c[1] for c in _tap_chromas]))) if _tap_chromas else None
        team = cv_detect.TeamModel(_anchor)
        det_frames = det_persons = 0
        team_counts = {"target_team": 0, "opponent": 0, "other": 0}
        det_negatives = 0
        cam = cv_detect.CameraMotion(out_scale=sw / 160.0)  # Phase 8 full global motion
        cam_dx = cam_dy = 0.0

        cap.set(cv2.CAP_PROP_POS_MSEC, 0.0)
        # FIX 03 — sample at HZ by ELAPSED MEDIA TIME (VFR-safe); every
        # timestamp is the frame's ACTUAL media time, never fidx/fps
        sample_interval = 1.0 / HZ if HZ > 0 else 0.0
        prev_sample_t = None
        dt_sample = sample_interval
        while True:
            t, _tb_fb = video_timebase.next_frame_time_seconds(cap, fps)
            ok = cap.grab()
            if not ok:
                break
            if not video_timebase.should_sample(t, prev_sample_t, sample_interval):
                continue
            ok, frame = cap.retrieve()
            if not ok:
                break
            dt_sample = video_timebase.sample_dt(t, prev_sample_t, sample_interval)
            prev_sample_t = t
            samples += 1
            small = cv2.resize(frame, (sw, sh))
            pitch_l = _pitch_l(small)
            tiny = cv2.cvtColor(cv2.resize(small, (160, max(2, int(sh * 160 / sw)))),
                                cv2.COLOR_BGR2GRAY).astype(np.float32)
            cam.update(tiny)  # Phase 8: affine pan/zoom/rotation, translation fallback
            cam_dx, cam_dy = cam.dx, cam.dy

            # ── P3: person detection + MOT + team classification (shadow) ──
            dets = []
            if detector.ok:
                for (nx, ny, nw_, nh_, dc) in detector.detect(frame):
                    b = (int(nx * sw), int(ny * sh),
                         max(3, int(nw_ * sw)), max(6, int(nh_ * sh)))
                    if med_h * 0.35 <= b[3] <= med_h * 2.5:
                        dets.append(b)
                det_frames += 1
                det_persons += len(dets)
                mot.update(dets, cam_dx, cam_dy)
                for b in dets:
                    ch = cv_detect.torso_chroma(small, b)
                    team.add(ch)
                    cl = team.classify(ch)
                    if cl:
                        team_counts[cl] += 1

            # expected position: production track first, else own continuity
            pr = prod_at(t)
            if pr is not None:
                exp = ((float(pr["x"]) + float(pr["w"]) / 2) * sw,
                       (float(pr["y"]) + float(pr["h"]) / 2) * sh)
            elif last_pos is not None:
                exp = cam.point(last_pos[0], last_pos[1])
            else:
                exp = None

            # ── v3 PROD-BOX VERIFICATION (the key shadow signal) ──
            if pr is not None:
                pb = (int(float(pr["x"]) * sw), int(float(pr["y"]) * sh),
                      max(4, int(float(pr["w"]) * sw)), max(8, int(float(pr["h"]) * sh)))
                # apples-to-apples: tap references are tight detector boxes, so
                # evaluate the person DETECTION inside the prod box (when one
                # exists) rather than the looser prod rectangle itself
                pb_eval = pb
                if dets:
                    _ov = [c for c in dets if _iou(c, pb) > 0.2]
                    if _ov:
                        pb_eval = max(_ov, key=lambda c: _iou(c, pb))
                pe = _zone_embedding(small, pb_eval, pitch_l,
                                     occluders=[c for c in dets
                                                if c != pb_eval and _iou(c, pb_eval) > 0.05])
                # Phase 9: trajectory gate on the PRODUCTION track — a camera-
                # compensated jump faster than physically possible means the
                # box teleported (switch/drift). Scene cuts are excluded: the
                # affine estimation fails there → fallback mode skips the check.
                cur_c = (pb[0] + pb[2] / 2.0, pb[1] + pb[3] / 2.0)
                if (prev_prod_c is not None and prev_prod_t is not None
                        and cam.mode == "affine"):
                    dtp = t - prev_prod_t
                    if 0.0 < dtp <= 0.6:
                        exq = cam.point(prev_prod_c[0], prev_prod_c[1])
                        jump = float(np.hypot(cur_c[0] - exq[0], cur_c[1] - exq[1]))
                        if ((jump / max(0.05, dtp)) / sw > MAX_SPEED * 1.6
                                and jump > med_h * 0.8):
                            teleport += 1
                            if len(teleport_ts) < 40:
                                entry = {"t": round(t, 1)}
                                img = _save_flag_frame(small, t, pb, None, 0.0, "TELEPORT")
                                if img:
                                    entry["img"] = img
                                teleport_ts.append(entry)
                prev_prod_c, prev_prod_t = cur_c, t
                if pe:
                    if pe.get("owned") is True:
                        own_evals += 1
                    elif pe.get("owned") is False:
                        contaminated_evals += 1
                    ps = _profile_sim(pe, refs)
                    prod_sims.append(round(ps, 3))
                    # Phase 7: a KNOWN teammate matching the prod-box content
                    # clearly better than the tapped player = switch indicator
                    # (persistence required — 2 consecutive samples)
                    pn = max((_sim(pe, n) for n in negatives), default=0.0)
                    neg_hit = pn > ps + 0.15 and ps < SIM_T
                    if neg_hit and prev_neg_hit:
                        neg_match += 1
                        if len(neg_ts) < 40:
                            entry = {"t": round(t, 1), "sim": round(ps, 2)}
                            img = _save_flag_frame(small, t, pb, None, ps, "NEG-MATCH")
                            if img:
                                entry["img"] = img
                            neg_ts.append(entry)
                    prev_neg_hit = neg_hit
                    # pose-robust flagging: a bent/fallen target scrambles the
                    # zone layout → the pose-tolerant pooled similarity may
                    # rescue the sample, but ONLY when a detected person is
                    # actually inside the prod box (an empty box must keep
                    # flagging). All flags need 2 consecutive low samples.
                    # empty-box check: no detection overlapping AND the box
                    # content is not person-like (a far/small player can be
                    # missed by the detector — white kit against pitch gives a
                    # high non-green fraction, bushes/grass do not)
                    person_in_box = any(_iou(c, pb) > 0.2 for c in dets) if dets else True
                    if dets and not person_in_box:
                        _bx0, _by0 = max(0, pb[0]), max(0, pb[1])
                        _bx1 = min(sw, pb[0] + pb[2])
                        _by1 = min(sh, pb[1] + pb[3])
                        _roi = small[_by0:_by1, _bx0:_bx1]
                        if _roi.size >= 60:
                            _ng = cv2.bitwise_not(_green_mask(_roi))
                            # measured on real footage: bushes/goal background
                            # 0.35-0.52, real player boxes 0.65-0.86
                            if float(_ng.mean()) / 255.0 >= 0.55:
                                person_in_box = True  # person-like content present
                    ps_rel = _sim_relaxed(pe, refs)
                    low = ps < SIM_T * 0.75 and (not person_in_box or ps_rel < SIM_T)
                    if detector.ok and not person_in_box:
                        prod_empty += 1
                        if prev_prod_empty and len(empty_ts) < 60:
                            entry = {"t": round(t, 1)}
                            img = _save_flag_frame(small, t, pb, None, ps, "EMPTY-BOX")
                            if img:
                                entry["img"] = img
                            empty_ts.append(entry)
                    prev_prod_empty = detector.ok and not person_in_box
                    if low and prev_prod_low:
                        prod_suspect += 1
                        if len(suspect_ts) < 60:
                            entry = {"t": round(t, 1), "sim": round(ps, 2)}
                            img = _save_flag_frame(small, t, pb, None, ps, "SUSPECT")
                            if img:
                                entry["img"] = img
                            suspect_ts.append(entry)
                    # nearby people around the prod box → crossover pressure.
                    # Real detections when available; blob fallback otherwise.
                    if dets:
                        near_blobs = [c for c in dets
                                      if abs(c[0] + c[2] / 2 - (pb[0] + pb[2] / 2)) < pb[3] * 2.5
                                      and abs(c[1] + c[3] / 2 - (pb[1] + pb[3] / 2)) < pb[3] * 2.5]
                    else:
                        nb_roi = np.zeros((sh, sw), np.uint8)
                        rr = int(pb[3] * 1.5)
                        nb_roi[max(0, pb[1] - rr):min(sh, pb[1] + pb[3] + rr),
                               max(0, pb[0] - rr):min(sw, pb[0] + pb[2] + rr)] = 255
                        near_blobs = _blobs(small, nb_roi, min_h=max(8, int(pb[3] * 0.45)),
                                            max_h=int(pb[3] * 2.0))
                    others = [c for c in near_blobs if _iou(c, pb) < 0.35]
                    _crowd_flag = any(_iou(c, pb) > 0.10 for c in others)
                    if _crowd_flag:
                        prod_crowded += 1
                        if len(crowded_ts) < 60:
                            crowded_ts.append(round(t, 1))
                    sample_log.append({"t": t, "ps": ps, "crowded": _crowd_flag,
                                       "empty": detector.ok and not person_in_box})
                    # switch risk: a DIFFERENT nearby person matches the tapped
                    # player CLEARLY better than the prod box content does.
                    # Pose-robust: requires persistence (prev sample also low),
                    # the relaxed check to fail too, and the competitor to be
                    # SAME-KIT (opponents/spectators can't be the target).
                    if low and prev_prod_low:
                        for c in others:
                            oe = _zone_embedding(small, c, pitch_l,
                                                 occluders=[pb_eval] if _iou(c, pb_eval) > 0.05 else None)
                            if not oe:
                                continue
                            if _profile_sim(oe, refs) > ps + 0.15 and ps < SIM_T:
                                cl = team.classify(cv_detect.torso_chroma(small, c))
                                if cl in ("opponent", "other"):
                                    continue
                                switch_risk += 1
                                if len(switch_ts) < 60:
                                    entry = {"t": round(t, 1), "sim": round(ps, 2)}
                                    img = _save_flag_frame(small, t, pb, c, ps, "SWITCH-RISK")
                                    if img:
                                        entry["img"] = img
                                    switch_ts.append(entry)
                                break
                    prev_prod_low = low
                    # P10: negative teammate gallery from REAL detections —
                    # same-kit players clearly away from the production target.
                    # Never contaminates the positive profile (separate list).
                    if dets and len(negatives) < 30:
                        for c in dets:
                            if _iou(c, pb) > 0.05:
                                continue
                            d_c = np.hypot(c[0] + c[2] / 2 - (pb[0] + pb[2] / 2),
                                           c[1] + c[3] / 2 - (pb[1] + pb[3] / 2))
                            if d_c < med_h * 2.0:
                                continue  # too close — ambiguous, skip
                            if team.classify(cv_detect.torso_chroma(small, c)) == "target_team":
                                ne = _zone_embedding(small, c, pitch_l)
                                if ne and _add_negative(negatives, ne):
                                    det_negatives += 1

            # ROI: local when we have an expectation, wide when re-acquiring
            roi_mask = np.zeros((sh, sw), np.uint8)
            if exp is not None:
                r = int(med_h * (2.2 if state in ("VERIFIED", "PROVISIONAL") else 4.0))
                x0, y0 = max(0, int(exp[0] - r)), max(0, int(exp[1] - r))
                roi_mask[y0:min(sh, int(exp[1] + r)), x0:min(sw, int(exp[0] + r))] = 255
            else:
                roi_mask[:] = 255
            # candidates: REAL detections inside the ROI (P3); blob fallback
            if dets:
                cand = [c for c in dets
                        if roi_mask[min(sh - 1, max(0, c[1] + c[3] // 2)),
                                    min(sw - 1, max(0, c[0] + c[2] // 2))] > 0]
            else:
                cand = _blobs(small, roi_mask, min_h=max(8, int(med_h * 0.45)),
                              max_h=int(med_h * 2.2))

            scored = []
            for c in cand:
                emb = _zone_embedding(small, c, pitch_l,
                                      occluders=[o for o in cand
                                                 if o is not c and _iou(o, c) > 0.05])
                if not emb:
                    continue
                s = _profile_sim(emb, refs)
                sn = max((_sim(emb, n) for n in negatives), default=0.0)  # P10
                # soft spatial prior: appearance alone cannot separate identical
                # kits — expectation-distance breaks ties WITHOUT overriding gates
                if exp is not None:
                    dist = np.hypot(c[0] + c[2] / 2 - exp[0], c[1] + c[3] / 2 - exp[1])
                    prior = float(np.exp(-dist / max(1.0, med_h * 2.0)))
                else:
                    prior = 0.5
                # P9: team classification as candidate FILTER (rank penalty
                # only — never a hard identity decision)
                cl = team.classify(cv_detect.torso_chroma(small, c)) if dets else None
                team_pen = 0.6 if cl in ("opponent", "other") else 1.0
                scored.append({"box": c, "sim": s, "neg": sn, "emb": emb,
                               "rank": s * (0.6 + 0.4 * prior) * team_pen})
            scored.sort(key=lambda d: -d["rank"])

            # crossover detection (P13): candidates overlapping the best one
            crowd = False
            if scored:
                crowd = any(_iou(scored[0]["box"], d["box"]) > 0.12 for d in scored[1:])
                if crowd:
                    crossovers += 1

            new_state = "LOST"
            if scored:
                best = scored[0]
                runner = scored[1]["sim"] if len(scored) > 1 else 0.0
                margin = best["sim"] - max(runner, best["neg"])
                margins.append(round(margin, 3))
                # P12 physics gate (camera-compensated, full affine — Phase 8)
                phys_ok = True
                if last_pos is not None and last_t is not None and state != "LOST":
                    dt = max(0.05, t - last_t)
                    exp_p = cam.point(last_pos[0], last_pos[1])
                    dist = np.hypot(best["box"][0] + best["box"][2] / 2 - exp_p[0],
                                    best["box"][1] + best["box"][3] / 2 - exp_p[1])
                    phys_ok = dist <= MAX_SPEED * sw * dt + med_h * 0.6
                reacq_mode = state == "LOST" or reacq_pending
                sim_gate = SIM_T + (REACQ_BONUS if reacq_mode else 0.0)
                mar_gate = MARGIN_T + (REACQ_BONUS if reacq_mode else 0.0)
                accepted_clean = False
                if best["sim"] >= sim_gate and margin >= mar_gate and phys_ok and not crowd:
                    if reacq_mode:
                        # Phase 13 safe re-acquisition — multi-signal: a streak
                        # of CONSECUTIVE clean samples (3 when lost in a crowd),
                        # team must not contradict, pose-relaxed sim must agree.
                        if state == "LOST":
                            reacq_attempts += 1
                        need = 3 if lost_in_crowd else 2
                        reacq_need_max = max(reacq_need_max, need)
                        cl_best = (team.classify(cv_detect.torso_chroma(small, best["box"]))
                                   if dets else None)
                        if cl_best in ("opponent", "other"):
                            reacq_team_rejected += 1
                            new_state = "UNCERTAIN"
                        else:
                            accepted_clean = True
                            reacq_pending = True
                            reacq_streak += 1
                            if (reacq_streak >= need
                                    and _sim_relaxed(best.get("emb"), refs) >= SIM_T):
                                new_state = "VERIFIED"
                                reacq_pending, lost_in_crowd = False, False
                                reacq_verified += 1
                            else:
                                new_state = "PROVISIONAL"
                    else:
                        accepted_clean = True
                        new_state = "VERIFIED"
                elif best["sim"] >= SIM_T and phys_ok:
                    new_state = "PROVISIONAL" if not crowd else "UNCERTAIN"
                elif best["sim"] >= SIM_T * 0.75:
                    new_state = "UNCERTAIN"
                if reacq_pending and not accepted_clean:
                    reacq_streak = 0  # streak must be consecutive clean samples
                if new_state in ("VERIFIED", "PROVISIONAL"):
                    last_pos = (best["box"][0] + best["box"][2] / 2,
                                best["box"][1] + best["box"][3] / 2)
                    last_t = t
                    lost_since = 0.0
                if new_state != "LOST" and state != "LOST" and not reacq_pending:
                    reacq_streak = 0
            if new_state == "LOST":
                reacq_streak = 0
                reacq_pending = False
                lost_since += dt_sample
                if lost_since < LOST_GRACE and state in ("VERIFIED", "PROVISIONAL", "UNCERTAIN"):
                    new_state = "UNCERTAIN"
            if new_state == "LOST" and state != "LOST":
                lost_in_crowd = bool(crowd)  # Phase 13: remember the loss context
            state = new_state
            states_count[state] += 1

            # compare with production authority (shadow only OBSERVES)
            if pr is not None and scored and state == "VERIFIED":
                px = (float(pr["x"]) + float(pr["w"]) / 2) * sw
                py = (float(pr["y"]) + float(pr["h"])) * sh
                bx = scored[0]["box"][0] + scored[0]["box"][2] / 2
                by = scored[0]["box"][1] + scored[0]["box"][3]
                d = float(np.hypot(px - bx, py - by))
                agree = d <= med_h * 1.5
                agreements.append(agree)
                if not agree:
                    potential_switches += 1

        # ── track-end protection: cluster persistent empty-box moments into
        # unsafe windows (marker/clips fade there; evidence deprioritizes) ──
        empty_windows = _cluster_windows([e["t"] for e in empty_ts]) if empty_ts else []

        # ── PHASE 15 (SHADOW): context-aware gap bridging — observe/log only.
        # A production-track gap is "bridgeable" ONLY when identity is shadow-
        # verified on BOTH sides, nobody is crowding, and the implied movement
        # is physically realistic. No blind fixed-duration rule.
        gaps_found = bridgeable = 0
        bridge_windows = []
        spts = sorted(track_pts, key=lambda p: float(p["t"]))
        def _near_log(tq, w=0.55):
            return [s for s in sample_log if abs(s["t"] - tq) <= w]
        for i in range(1, len(spts)):
            g0, g1 = float(spts[i - 1]["t"]), float(spts[i]["t"])
            gap = g1 - g0
            if gap <= 0.7:
                continue
            gaps_found += 1
            if gap > 1.5:
                continue
            l0, l1 = _near_log(g0), _near_log(g1)
            id_ok = (bool(l0) and max(s["ps"] for s in l0) >= SIM_T
                     and bool(l1) and max(s["ps"] for s in l1) >= SIM_T)
            crowd = any(s["crowded"] or s["empty"] for s in l0 + l1)
            dxn = float(spts[i]["x"]) - float(spts[i - 1]["x"])
            dyn = float(spts[i]["y"]) - float(spts[i - 1]["y"])
            phys_ok = (float(np.hypot(dxn, dyn)) / gap) <= MAX_SPEED
            if id_ok and not crowd and phys_ok:
                bridgeable += 1
                if len(bridge_windows) < 40:
                    bridge_windows.append([round(g0, 1), round(g1, 1)])

        # false-rejection proxy: does the shadow engine re-verify the taps themselves?
        tap_self = []
        for r in refs:
            s = _profile_sim(r["emb"], [o for o in refs if o is not r])
            tap_self.append(s >= SIM_T)

        out = {
            "status": "ok",
            "engine_version": 6,
            "duration_s": round(dur, 1),
            "samples": samples,
            "taps": [{"t": r["t"], "quality": r["quality"], "consistency": r["consistency"],
                      "outlier": r["outlier"], "rejected": r["rejected"], "weight": r["weight"],
                      "refined_by": r["refined_by"], "visibility": r["visibility"],
                      "merged": r["merged"]}
                     for r in refs],
            "tap_outliers": sum(1 for r in refs if r["outlier"]),
            "tap_rejected": sum(1 for r in refs if r["rejected"]),
            "negative_gallery": len(negatives),
            "states": states_count,
            "verified_coverage": round(states_count["VERIFIED"] / max(1, samples), 3),
            "crossover_samples": crossovers,
            "margin_median": round(float(np.median(margins)), 3) if margins else None,
            "margin_p10": round(float(np.percentile(margins, 10)), 3) if margins else None,
            "prod_agreement": round(float(np.mean(agreements)), 3) if agreements else None,
            "prod_compared": len(agreements),
            "potential_switches": potential_switches,
            "tap_self_verify": round(sum(tap_self) / max(1, len(tap_self)), 3),
            # v3 — direct production-track verification (the primary signal)
            "prod_verify": {
                "checked": len(prod_sims),
                "sim_mean": round(float(np.mean(prod_sims)), 3) if prod_sims else None,
                "sim_p10": round(float(np.percentile(prod_sims, 10)), 3) if prod_sims else None,
                "suspect_frames": prod_suspect,
                "suspect_rate": round(prod_suspect / max(1, len(prod_sims)), 3),
                "crowded_frames": prod_crowded,
                "switch_risk_frames": switch_risk,
                "empty_box_frames": prod_empty,
                "neg_match_frames": neg_match,
                "teleport_frames": teleport,
                "suspect_ts": suspect_ts,
                "switch_ts": switch_ts,
                "crowded_ts": crowded_ts,
                "empty_ts": empty_ts,
                "neg_ts": neg_ts,
                "teleport_ts": teleport_ts,
                "empty_windows": empty_windows,
                "flag_frames": saved_imgs,
            },
            # Phase 8/4/13 — camera model, feature ownership, re-acquisition
            "camera": {
                "affine_frames": cam.affine_frames,
                "fallback_frames": cam.fallback_frames,
            },
            "feature_ownership": {
                "owned_evals": own_evals,
                "contaminated_evals": contaminated_evals,
            },
            "reacq": {
                "attempts": reacq_attempts,
                "verified": reacq_verified,
                "team_rejected": reacq_team_rejected,
                "max_streak_required": reacq_need_max,
            },
            # Phase 15 (shadow): production-track gaps and which are SAFELY
            # bridgeable given identity/crowd/physics context on both sides
            "gap_bridging": {
                "gaps": gaps_found,
                "bridgeable": bridgeable,
                "windows": bridge_windows,
            },
            # P3 scene awareness (detector + MOT + team classification)
            "scene": {
                "detector": bool(detector.ok),
                "det_frames": det_frames,
                "avg_persons": round(det_persons / max(1, det_frames), 2) if det_frames else None,
                "mot_tracks_created": mot.created,
                "mot_crossover_events": mot.crossover_events,
                "team_ready": bool(team.centers is not None and team.target_ci is not None),
                "team_counts": team_counts,
                "det_negatives": det_negatives,
            },
            "compute_s": round(time.time() - t_start, 1),
            "config": {"hz": HZ, "width": SMALL_W, "sim_t": SIM_T, "margin_t": MARGIN_T},
        }
        logger.info(
            f"[cv-shadow] {report_id}: coverage={out['verified_coverage']} "
            f"prod_sim={out['prod_verify']['sim_mean']} "
            f"suspect={prod_suspect}/{len(prod_sims)} switch_risk={switch_risk} "
            f"neg_match={neg_match} teleport={teleport} "
            f"cam_affine={cam.affine_frames}/{cam.affine_frames + cam.fallback_frames} "
            f"crossovers={crossovers} outliers={out['tap_outliers']} "
            f"({out['compute_s']}s for {samples} samples)"
        )
        return out
    except Exception as e:
        logger.warning(f"[cv-shadow] {report_id} failed: {e}")
        return {"status": "error", "reason": str(e)[:200]}
    finally:
        try:
            if cap is not None:
                cap.release()
        except Exception:
            pass
