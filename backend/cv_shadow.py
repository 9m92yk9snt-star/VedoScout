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
from typing import Optional

import cv2
import numpy as np

import cv_detect

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
        return roi, np.full(roi.shape[:2], 255, np.uint8), True
    m = (lbl == best).astype(np.uint8) * 255
    xs = np.where(m.any(0))[0]
    ys = np.where(m.any(1))[0]
    return (roi[ys[0]:ys[-1] + 1, xs[0]:xs[-1] + 1],
            m[ys[0]:ys[-1] + 1, xs[0]:xs[-1] + 1], False)


def _zone_embedding(small, box, pitch_l):
    """Multi-scale zone embedding over the ISOLATED person component only.
    Per zone: illumination-normalized Lab mean+std. Zones adapt to pixel size —
    a far player is never compared on details the camera cannot resolve."""
    crop, mask, merged = _comp_mask_crop(small, box)
    h, w = crop.shape[:2]
    if h < 12 or w < 4:
        return None
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
            "merged": merged, "px_h": h}


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


# ---------------------------------------------------------------- reference
def _build_tap_references(cap, fps, anchors, t_off, sw, sh, scale):
    """P1-P4: refine each user tap to the actual person, score its quality,
    embed it, then cross-check all taps into ONE identity with outliers
    downweighted — a single bad tap can never contaminate the profile."""
    refs, negatives = [], []
    for a in anchors:
        try:
            t = float(a["t"]) + (t_off or 0.0)
            box = a["box"]
            cap.set(cv2.CAP_PROP_POS_FRAMES, int(max(0.0, t) * fps))
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
            # refined person box = blob closest to the tap-box centre
            cx0, cy0 = bx + bw / 2, by + bh / 2
            if cand:
                rb = min(cand, key=lambda c: abs(c[0] + c[2] / 2 - cx0) + abs(c[1] + c[3] / 2 - cy0))
            else:
                rb = (bx, by, bw, bh)  # fallback: trust the raw tap box
            emb = _zone_embedding(small, rb, pl)
            if not emb:
                continue
            overlaps = sum(1 for c in cand if c != rb and _iou(c, rb) > 0.10)
            crop = small[rb[1]:rb[1] + rb[3], rb[0]:rb[0] + rb[2]]
            gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
            quality = round(
                0.35 * min(1.0, rb[3] / 60.0)              # pixel size
                + 0.25 * _sharpness(gray)                   # blur
                + 0.25 * (1.0 if overlaps == 0 else (0.5 if overlaps == 1 else 0.2))  # occlusion
                + 0.15 * (0.0 if emb.get("merged") else 1.0),  # isolation
                3,
            )
            refs.append({"t": round(t, 2), "emb": emb, "quality": quality,
                         "box": rb, "refined": bool(cand), "overlaps": overlaps,
                         "merged": bool(emb.get("merged")),
                         "chroma": cv_detect.torso_chroma(small, rb)})
            # P10 negative gallery: OTHER blobs at the tap moment (same scene)
            for c in cand:
                if c == rb or _iou(c, rb) > 0.3:
                    continue
                oe = _zone_embedding(small, c, pl)
                if oe:
                    negatives.append(oe)
        except Exception:
            continue
    # P4 consistency: pairwise similarity → outliers downweighted, never deleted
    for r in refs:
        sims = [_sim(r["emb"], o["emb"]) for o in refs if o is not r]
        r["consistency"] = round(float(np.mean(sims)), 3) if sims else 1.0
    med = float(np.median([r["consistency"] for r in refs])) if refs else 0.0
    for r in refs:
        r["outlier"] = bool(r["consistency"] < med - 0.15)
        r["weight"] = round((0.3 if r["outlier"] else 1.0)
                            * (0.5 if r["merged"] else 1.0)
                            * max(0.2, r["quality"]), 3)
    return refs, negatives[:30]


def _profile_sim(emb, refs) -> float:
    """Weighted mean of the 3 best tap matches — one identity, many views."""
    if not refs:
        return 0.0
    scored = sorted(((_sim(emb, r["emb"]), r["weight"]) for r in refs), reverse=True)[:3]
    tw = sum(w for _, w in scored)
    return sum(s * w for s, w in scored) / max(1e-6, tw)


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
        dur = total / fps
        scale = SMALL_W / W
        sw, sh = SMALL_W, max(2, int(H * scale))

        refs, negatives = _build_tap_references(cap, fps, anchors, t_off, sw, sh, scale)
        if len(refs) < 3:
            return {"status": "skipped", "reason": "too_few_references"}

        # production track lookup (video time)
        def prod_at(t):
            near = [p for p in track_pts if abs(float(p["t"]) - t) <= 0.45]
            return min(near, key=lambda p: abs(float(p["t"]) - t)) if near else None

        med_h = float(np.median([r["box"][3] for r in refs]))
        step = max(1, int(round(fps / HZ)))
        state, last_pos, last_t, lost_since = "LOST", None, None, 0.0
        reacq_streak = 0
        states_count = {"VERIFIED": 0, "PROVISIONAL": 0, "UNCERTAIN": 0, "LOST": 0}
        crossovers = potential_switches = samples = 0
        margins, agreements = [], []
        # v3: direct verification of the PRODUCTION box — "does the content of
        # the current production track box still look like the tapped player?"
        prod_sims, prod_suspect, prod_crowded, switch_risk = [], 0, 0, 0
        suspect_ts, switch_ts, crowded_ts = [], [], []

        # ── P3 scene awareness (detector + MOT + team classification) ──
        detector = cv_detect.PersonDetector()
        mot = cv_detect.MiniMOT()
        _tap_chromas = [r["chroma"] for r in refs if r.get("chroma")]
        _anchor = (float(np.median([c[0] for c in _tap_chromas])),
                   float(np.median([c[1] for c in _tap_chromas]))) if _tap_chromas else None
        team = cv_detect.TeamModel(_anchor)
        det_frames = det_persons = 0
        team_counts = {"target_team": 0, "opponent": 0, "other": 0}
        det_negatives = 0
        prev_tiny = None
        cam_dx = cam_dy = 0.0

        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        fidx = 0
        while True:
            ok = cap.grab()
            if not ok:
                break
            if fidx % step != 0:
                fidx += 1
                continue
            ok, frame = cap.retrieve()
            if not ok:
                break
            t = fidx / fps
            fidx += 1
            samples += 1
            small = cv2.resize(frame, (sw, sh))
            pitch_l = _pitch_l(small)
            tiny = cv2.cvtColor(cv2.resize(small, (160, max(2, int(sh * 160 / sw)))),
                                cv2.COLOR_BGR2GRAY).astype(np.float32)
            if prev_tiny is not None:
                (dx, dy), _ = cv2.phaseCorrelate(prev_tiny, tiny)  # P11 camera comp
                cam_dx, cam_dy = dx * sw / 160, dy * sw / 160
            prev_tiny = tiny

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
                exp = (last_pos[0] + cam_dx, last_pos[1] + cam_dy)
            else:
                exp = None

            # ── v3 PROD-BOX VERIFICATION (the key shadow signal) ──
            if pr is not None:
                pb = (int(float(pr["x"]) * sw), int(float(pr["y"]) * sh),
                      max(4, int(float(pr["w"]) * sw)), max(8, int(float(pr["h"]) * sh)))
                pe = _zone_embedding(small, pb, pitch_l)
                if pe:
                    ps = _profile_sim(pe, refs)
                    prod_sims.append(round(ps, 3))
                    if ps < SIM_T * 0.75:
                        prod_suspect += 1
                        if len(suspect_ts) < 60:
                            suspect_ts.append({"t": round(t, 1), "sim": round(ps, 2)})
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
                    if any(_iou(c, pb) > 0.10 for c in others):
                        prod_crowded += 1
                        if len(crowded_ts) < 60:
                            crowded_ts.append(round(t, 1))
                    # switch risk: a DIFFERENT nearby person matches the tapped
                    # player CLEARLY better than the prod box content does
                    for c in others:
                        oe = _zone_embedding(small, c, pitch_l)
                        if oe and _profile_sim(oe, refs) > ps + 0.15 and ps < SIM_T:
                            switch_risk += 1
                            if len(switch_ts) < 60:
                                switch_ts.append(round(t, 1))
                            break
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
                                if ne:
                                    negatives.append(ne)
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
                emb = _zone_embedding(small, c, pitch_l)
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
                scored.append({"box": c, "sim": s, "neg": sn,
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
                # P12 physics gate (camera-compensated)
                phys_ok = True
                if last_pos is not None and last_t is not None and state != "LOST":
                    dt = max(0.05, t - last_t)
                    dist = np.hypot(best["box"][0] + best["box"][2] / 2 - (last_pos[0] + cam_dx),
                                    best["box"][1] + best["box"][3] / 2 - (last_pos[1] + cam_dy))
                    phys_ok = dist <= MAX_SPEED * sw * dt + med_h * 0.6
                sim_gate = SIM_T + (REACQ_BONUS if state == "LOST" else 0.0)
                mar_gate = MARGIN_T + (REACQ_BONUS if state == "LOST" else 0.0)
                if best["sim"] >= sim_gate and margin >= mar_gate and phys_ok and not crowd:
                    if state == "LOST":  # P16 safe re-acquisition: 2 clean samples
                        reacq_streak += 1
                        new_state = "PROVISIONAL" if reacq_streak < 2 else "VERIFIED"
                    else:
                        new_state = "VERIFIED"
                elif best["sim"] >= SIM_T and phys_ok:
                    new_state = "PROVISIONAL" if not crowd else "UNCERTAIN"
                elif best["sim"] >= SIM_T * 0.75:
                    new_state = "UNCERTAIN"
                if new_state in ("VERIFIED", "PROVISIONAL"):
                    last_pos = (best["box"][0] + best["box"][2] / 2,
                                best["box"][1] + best["box"][3] / 2)
                    last_t = t
                    lost_since = 0.0
                if new_state != "LOST" and state != "LOST":
                    reacq_streak = 0
            if new_state == "LOST":
                reacq_streak = 0
                lost_since += step / fps
                if lost_since < LOST_GRACE and state in ("VERIFIED", "PROVISIONAL", "UNCERTAIN"):
                    new_state = "UNCERTAIN"
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

        # false-rejection proxy: does the shadow engine re-verify the taps themselves?
        tap_self = []
        for r in refs:
            s = _profile_sim(r["emb"], [o for o in refs if o is not r])
            tap_self.append(s >= SIM_T)

        out = {
            "status": "ok",
            "engine_version": 4,
            "duration_s": round(dur, 1),
            "samples": samples,
            "taps": [{"t": r["t"], "quality": r["quality"], "consistency": r["consistency"],
                      "outlier": r["outlier"], "weight": r["weight"], "refined": r["refined"],
                      "merged": r["merged"]}
                     for r in refs],
            "tap_outliers": sum(1 for r in refs if r["outlier"]),
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
                "suspect_ts": suspect_ts,
                "switch_ts": switch_ts,
                "crowded_ts": crowded_ts,
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
