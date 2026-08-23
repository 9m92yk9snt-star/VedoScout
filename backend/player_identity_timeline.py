"""player_identity_timeline.py — FIX 09A: GLOBAL TARGET IDENTITY TIMELINE.

Scene-aware, full-video identity timeline for the tapped player (GLOBAL_TARGET).
Runs ALONGSIDE the production FIX04 tracker (gt_track) — it does not replace it
and is NOT fed into FIX08 event authority in this phase.

Architecture:
- deterministic core `assemble_timeline()` — pure logic over pre-computed
  per-frame observations (fully testable without video/model calls)
- video ingestion `build_identity_timeline()` — decodes the video ONCE at
  IDENTITY_TIMELINE_HZ, runs the local person detector once per sampled frame
  and reuses the calibrated cv_shadow/cv_detect primitives (tap references,
  zone embeddings, negative gallery, team model, camera motion). ZERO LLM or
  network calls.

Identity model:
- GLOBAL_TARGET = the exact player selected by the user's taps (FIX00A —
  absolute authority; no tracker or appearance score may override a tap pin)
- every hard scene cut restarts LOCAL multi-player tracks and terminates
  physical trajectory continuity; global identity survives via CUT_REID
- other players keep scene-local track ids as negative identity information
- occlusion keeps identity (OCCLUDED with predicted geometry, explicitly
  marked, never proof-eligible); ambiguous duels are resolved retrospectively
  with post-separation evidence (offline video: forward AND backward frames)
- C03: local tracks are continuously identity-evaluated and SPLIT when the
  appearance/negative evidence changes persistently — a silent MOT switch
  (no detector miss, no overlap) can never let a teammate tail inherit the
  target because of good earlier frames
- C04: a tap that lands on spatially ambiguous overlapping bodies is bound
  by appearance/post-separation evidence, or held as bounded competing
  hypotheses — never arbitrarily
- fail-closed: no confident identity ⇒ unresolved interval, never a guess
"""
from __future__ import annotations

import logging
import math
import os
import time

logger = logging.getLogger("elite-scout")

VERSION = 1
TIMELINE_ENABLED = os.environ.get("IDENTITY_TIMELINE_ENABLED", "1") == "1"
HZ = float(os.environ.get("IDENTITY_TIMELINE_HZ", "5"))
SMALL_W = 480

SIM_T = 0.45          # calibrated with cv_shadow on real footage
MARGIN_T = 0.10       # best must clearly beat runner-up
REACQ_BONUS = 0.05    # stricter gate after loss / for joins
CUT_REID_BONUS = 0.05 # stricter gate for tap-less scenes
MAX_SPEED = 0.28      # frame-widths / second (camera-compensated)
CUT_DIFF = 45.0       # 160w-gray global diff → hard cut (player_tracking calib)
CUT_DIFF_HARD = 75.0  # cut regardless of camera-model state

MOT_IOU_MIN = 0.10
OVERLAP_IOU = 0.10
SCALE_STEP = (0.60, 1.60)   # per-sample height ratio (zoom-plausible)
SCALE_JOIN = (0.55, 1.80)   # within-scene re-acquisition join height ratio
MAX_MISSES = 10             # samples (≈2 s @5 Hz) a track may survive unseen
PIN_WINDOW_MS = 600
PIN_APPEAR_WIN_MS = 5000    # C04 appearance-evidence window around a tap
POST_WIN_MS = 3000          # post-separation evidence window
RESUME_WIN_MS = 2000        # post-gap identity confirmation window
UNRESOLVED_GAP_MS = 1500

# C02 — detection retention is FRAME-relative, never tap-median-relative:
# a highlight cut may legitimately change the target's on-screen scale by far
# more than any global prior. Scale plausibility applies only during per-step
# track association (SCALE_STEP) and within-scene re-acquisition (SCALE_JOIN);
# cross-scene CUT_REID carries NO scale gate (scene-adaptive by construction).
PLAYER_MIN_FRAC = 0.02      # of frame height
PLAYER_MAX_FRAC = 0.90

# C03 — temporal identity segmentation (bounded multi-frame, never one frame)
SWITCH_MIN_RUN = 3          # usable samples of persistent opposite identity
SWITCH_MIN_RUN_NEG = 2      # when the negative gallery dominates every sample
SWITCH_MEAN_GAP = 0.12      # material similarity change between segments

# R01 — deterministic scene-cut stabilization
MIN_SCENE_SAMPLES = 3       # smaller scenes are transition/flash artifacts
REJOIN_SIG_DIFF = 20.0      # 8x8 pooled-gray diff below which two "scenes"
                            # MAY be the same shot (necessary, NOT sufficient)
LAYOUT_CONTINUITY_MIN = 0.5 # fraction of detections that must persist in
                            # place across a candidate rejoin boundary — two
                            # different highlights on similar green pitches
                            # share global luminance but not player layout

# R02/R03 — evidence-based identity margins (same-kit teammates make a flat
# 0.10 raw-similarity margin unreachable on real footage; the improvement is
# better reasoning, not lower thresholds: negative-relative adjustment,
# concurrent-only rivals and evidence-scaled acceptance)
NEG_REL_W = 0.5             # weight of (score - negative_gallery) evidence
ADJ_MARGIN_STRONG = 0.05    # adjusted margin with strong multi-frame evidence
STRONG_USABLE = 5           # usable samples needed for the strong margin
PIN_DOMINANT_IOU = 0.30     # tap spatial dominance: clear best overlap …
PIN_RIVAL_IOU = 0.15        # … while every rival barely grazes the tap

# FIX09A.1 — tap-independent GLOBAL_TARGET positive prototype bank
BANK_MAX = 24               # bounded, deduplicated multi-view prototype bank
BANK_PER_BUCKET = 2         # diversity: best N per (scene, scale-bucket)
BANK_SINGLE_DISCOUNT = 0.95 # one supporting prototype is weaker than two

# ── FIX09A.2 — decisive-action identity recovery ──
TAP_RECOVER_DIST_H = 1.0    # A2.1 relaxed tap binding: ≤ 1 body-height away
KIN_W = 0.3                 # A2.4 weight of kinematic continuity in path score
KIN_MIN = 0.6               # kinematic tiebreak needs strong physical continuity
REENTRY_MAX_GAP_MS = 2500   # bounded re-entry window after losing the target
OCCL_FILL_MAX_MS = 1200     # labeled predicted fill across short verified joins
FILL_STEP_MS = 200
SHAPE_MARGIN = 0.25         # A2.3 shape/motion tiebreak must CLEARLY separate
SHAPE_MIN_USABLE = 4

STATES = ("VISIBLE", "PARTIAL", "OCCLUDED", "REACQUIRED", "CUT_REID")


# ─────────────────────────────────────────────── geometry helpers
def _iou(a, b) -> float:
    ax0, ay0, ax1, ay1 = a[0], a[1], a[0] + a[2], a[1] + a[3]
    bx0, by0, bx1, by1 = b[0], b[1], b[0] + b[2], b[1] + b[3]
    ix = max(0.0, min(ax1, bx1) - max(ax0, bx0))
    iy = max(0.0, min(ay1, by1) - max(ay0, by0))
    inter = ix * iy
    return inter / max(1e-6, a[2] * a[3] + b[2] * b[3] - inter)


def _center(b):
    return (b[0] + b[2] / 2.0, b[1] + b[3] / 2.0)


class _Track:
    __slots__ = ("tid", "samples", "vel", "cam_acc", "misses", "miss_preds")

    def __init__(self, tid):
        self.tid = tid
        self.samples = []       # {"i","ms","box","emb","team","overlap","gap_before"}
        self.vel = (0.0, 0.0)   # camera-compensated px/s
        self.cam_acc = [0.0, 0.0]
        self.misses = 0
        self.miss_preds = {}    # obs_i -> (ms, predicted box) while unseen


def _usable(s) -> bool:
    """Crossover freeze + feature ownership: an overlapped or contaminated
    sample never contributes identity evidence."""
    if s["overlap"] or s["emb"] is None:
        return False
    e = s["emb"]
    if isinstance(e, dict) and e.get("owned") is False:
        return False
    return True


# ─────────────────────────────────────────────── scene segmentation + MOT
def _sig_diff(a, b):
    sa, sb = a.get("sig"), b.get("sig")
    if not sa or not sb or len(sa) != len(sb):
        return None
    return sum(abs(x - y) for x, y in zip(sa, sb)) / len(sa)


def _layout_continuity(oa, ob):
    """Structural same-shot evidence: fraction of detections in `oa` that have
    a spatial counterpart in `ob` within plausible one-step motion. Within one
    shot players barely move between samples; across two different highlights
    the layout is unrelated even when the pitch/lighting looks identical."""
    da = [d["box"] for d in (oa.get("detections") or [])]
    db_ = [d["box"] for d in (ob.get("detections") or [])]
    if not da or not db_:
        return None
    matched = 0
    for b in da:
        for c in db_:
            hr = c[3] / max(1e-6, b[3])
            if hr < SCALE_STEP[0] or hr > SCALE_STEP[1]:
                continue
            if _iou(b, c) >= 0.20:
                matched += 1
                break
            c0, c1 = _center(b), _center(c)
            if math.hypot(c1[0] - c0[0], c1[1] - c0[1]) <= 0.9 * max(b[3], c[3]):
                matched += 1
                break
    return matched / len(da)


def _same_shot(oa, ob):
    """A rejoin needs BOTH global-signature similarity AND structural layout
    continuity. Similar green pitch alone must never join two highlights."""
    d = _sig_diff(oa, ob)
    if d is None or d >= REJOIN_SIG_DIFF:
        return False
    lc = _layout_continuity(oa, ob)
    return lc is not None and lc >= LAYOUT_CONTINUITY_MIN


def _split_scenes(obs):
    """Split at hard cuts, then stabilize deterministically (R01):
    - rejoin consecutive 'scenes' whose boundary frames are the SAME shot
      (false cut from a pan spike / decode artifact)
    - a scene shorter than MIN_SCENE_SAMPLES is a transition/flash fragment:
      if its neighbours are the same shot, the whole run is rejoined
      (flash inside one clip); otherwise it is absorbed into the next scene.
    Genuinely different highlight clips are never joined."""
    raw, cur = [], []
    for i, o in enumerate(obs):
        if o.get("cut") and cur:
            raw.append(cur)
            cur = []
        cur.append(i)
    if cur:
        raw.append(cur)

    changed = True
    while changed and len(raw) > 1:
        changed = False
        for k in range(len(raw) - 1):  # boundary rejoin: same shot continues
            if _same_shot(obs[raw[k][-1]], obs[raw[k + 1][0]]):
                raw[k] = raw[k] + raw.pop(k + 1)
                changed = True
                break
        if changed:
            continue
        for k, sc in enumerate(raw):   # minimum scene duration debounce
            if len(sc) >= MIN_SCENE_SAMPLES:
                continue
            if 0 < k < len(raw) - 1 \
                    and _same_shot(obs[raw[k - 1][-1]], obs[raw[k + 1][0]]):
                # flash/artifact INSIDE one continuous shot
                raw[k - 1] = raw[k - 1] + raw.pop(k) + raw.pop(k)
                changed = True
                break
            j = k + 1 if k + 1 < len(raw) else k - 1
            sc = raw.pop(k)
            jj = j - 1 if j > k else j
            raw[jj] = sorted(raw[jj] + sc)
            changed = True
            break
    return raw


def _scene_mot(obs, idxs):
    """Greedy camera-compensated IoU tracker, scene-local ids from 1."""
    all_tracks, live = [], []
    next_tid = 1
    crossings = []  # {"a","b","ms"} overlap events between two live tracks
    for i in idxs:
        o = obs[i]
        ms = int(o["media_ms"])
        cdx = float(o.get("cam_dx") or 0.0)
        cdy = float(o.get("cam_dy") or 0.0)
        dets = list(o.get("detections") or [])
        preds = {}
        for tr in live:
            tr.cam_acc[0] += cdx
            tr.cam_acc[1] += cdy
            last = tr.samples[-1]
            gap_s = max(0.0, (ms - last["ms"]) / 1000.0)
            preds[tr.tid] = (last["box"][0] + tr.cam_acc[0] + tr.vel[0] * gap_s,
                             last["box"][1] + tr.cam_acc[1] + tr.vel[1] * gap_s,
                             last["box"][2], last["box"][3])
        pairs = []
        for tr in live:
            p = preds[tr.tid]
            for di, d in enumerate(dets):
                b = d["box"]
                hr = b[3] / max(1e-6, p[3])
                if hr < SCALE_STEP[0] or hr > SCALE_STEP[1]:
                    continue  # zoom-implausible per step — never matched
                v = _iou(p, b)
                if v >= MOT_IOU_MIN:
                    pairs.append((v, 0.0, tr, di))
                else:
                    cx, cy = _center(p)
                    dx_, dy_ = _center(b)
                    dist = math.hypot(dx_ - cx, dy_ - cy)
                    if dist <= 0.9 * max(p[3], b[3]):
                        pairs.append((0.0, -dist, tr, di))
        pairs.sort(key=lambda q: (-q[0], q[1]))
        used_t, used_d = set(), set()
        for v, nd, tr, di in pairs:
            if tr.tid in used_t or di in used_d:
                continue
            used_t.add(tr.tid)
            used_d.add(di)
            d = dets[di]
            prev = tr.samples[-1]
            gap_s = max(1e-6, (ms - prev["ms"]) / 1000.0)
            c0, c1 = _center(prev["box"]), _center(d["box"])
            tr.vel = ((c1[0] - c0[0] - tr.cam_acc[0]) / gap_s,
                      (c1[1] - c0[1] - tr.cam_acc[1]) / gap_s)
            gap_before = tr.misses
            tr.cam_acc = [0.0, 0.0]
            tr.misses = 0
            tr.samples.append({"i": i, "ms": ms, "box": tuple(d["box"]),
                               "emb": d.get("emb"), "team": d.get("team"),
                               "overlap": False, "gap_before": gap_before})
        for tr in live:
            if tr.tid not in used_t:
                tr.misses += 1
                tr.miss_preds[i] = (ms, preds[tr.tid])
        live = [tr for tr in live if tr.misses <= MAX_MISSES]
        for di, d in enumerate(dets):
            if di in used_d:
                continue
            tr = _Track(next_tid)
            next_tid += 1
            tr.samples.append({"i": i, "ms": ms, "box": tuple(d["box"]),
                               "emb": d.get("emb"), "team": d.get("team"),
                               "overlap": False, "gap_before": 0})
            live.append(tr)
            all_tracks.append(tr)
        # crossover freeze: overlapping live detections are tagged; identity
        # is never learned or scored on those samples
        cur = [(tr, tr.samples[-1]) for tr in live
               if tr.samples and tr.samples[-1]["i"] == i]
        for a in range(len(cur)):
            for b in range(a + 1, len(cur)):
                (t1, s1), (t2, s2) = cur[a], cur[b]
                if _iou(s1["box"], s2["box"]) > OVERLAP_IOU:
                    s1["overlap"] = True
                    s2["overlap"] = True
                    crossings.append({"a": t1.tid, "b": t2.tid, "ms": ms})
    return all_tracks, crossings


# ─────────────────────────────────────────────── C03: temporal identity splits
def _split_track(tr, ident_fn, neg_fn, next_tid):
    """Continuously evaluate identity along a local track and split it where
    the evidence changes PERSISTENTLY (bounded multi-frame — a single noisy
    frame never splits). A silent MOT switch onto a same-kit teammate ends
    the target segment even without a detector miss or explicit overlap."""
    seq = []
    for k, s in enumerate(tr.samples):
        if not _usable(s):
            continue
        try:
            sim = float(ident_fn(s["emb"]))
            neg = float(neg_fn(s["emb"])) if neg_fn else 0.0
        except Exception:
            continue
        fl = neg >= sim + 0.15  # negative gallery dominates → forced low
        seq.append({"k": k, "cls": "L" if (sim < SIM_T or fl) else "H",
                    "sim": sim, "fl": fl})
    if len(seq) < SWITCH_MIN_RUN + 2:
        return [tr], next_tid
    runs = []
    for it in seq:
        if runs and runs[-1]["cls"] == it["cls"]:
            runs[-1]["items"].append(it)
        else:
            runs.append({"cls": it["cls"], "items": [it]})

    def _strong(r):
        n = len(r["items"])
        if r["cls"] == "L" and n >= SWITCH_MIN_RUN_NEG and all(i["fl"] for i in r["items"]):
            return True
        return n >= SWITCH_MIN_RUN

    def _mean(r):
        return sum(i["sim"] for i in r["items"]) / len(r["items"])

    changed = True
    while changed and len(runs) > 1:
        changed = False
        for i, r in enumerate(runs):
            if not _strong(r):  # noise run — absorb into a neighbour
                j = i - 1 if i > 0 else i + 1
                runs[j]["items"] = sorted(runs[j]["items"] + r["items"],
                                          key=lambda x: x["k"])
                runs.pop(i)
                changed = True
                break
        if changed:
            continue
        for i in range(len(runs) - 1):
            if runs[i]["cls"] == runs[i + 1]["cls"] \
                    or abs(_mean(runs[i]) - _mean(runs[i + 1])) < SWITCH_MEAN_GAP:
                runs[i]["items"] = sorted(runs[i]["items"] + runs[i + 1]["items"],
                                          key=lambda x: x["k"])
                runs.pop(i + 1)
                changed = True
                break
    if len(runs) <= 1:
        return [tr], next_tid

    parts = []
    for ri, r in enumerate(runs):
        start = 0 if ri == 0 else r["items"][0]["k"]
        end = len(tr.samples) if ri == len(runs) - 1 else r["items"][-1]["k"] + 1
        smp = tr.samples[start:end]  # ambiguous transition frames between runs
        if not smp:                  # are DISCARDED — assigned to neither side
            continue
        nt = _Track(tr.tid if not parts else next_tid)
        if parts:
            next_tid += 1
        nt.samples = smp
        nt.miss_preds = {i: (pms, pb) for i, (pms, pb) in tr.miss_preds.items()
                         if smp[0]["ms"] < pms < smp[-1]["ms"]}
        parts.append(nt)
    return (parts, next_tid) if len(parts) > 1 else ([tr], next_tid)


def _apply_identity_splits(tracks, crossings, ident_fn, neg_fn):
    out = []
    next_tid = max((t.tid for t in tracks), default=0) + 1
    seg_map = {}
    for tr in tracks:
        parts, next_tid = _split_track(tr, ident_fn, neg_fn, next_tid)
        out.extend(parts)
        seg_map[tr.tid] = [(p.samples[0]["ms"], p.samples[-1]["ms"], p.tid)
                           for p in parts]

    def _map(tid, ms):
        segs = seg_map.get(tid) or []
        best = None
        for s0, s1, nt in segs:
            d = 0 if s0 <= ms <= s1 else min(abs(ms - s0), abs(ms - s1))
            if best is None or d < best[0]:
                best = (d, nt)
        return best[1] if best else tid

    remapped = []
    for c in crossings:
        a, b = _map(c["a"], c["ms"]), _map(c["b"], c["ms"])
        if a != b:
            remapped.append({"a": a, "b": b, "ms": c["ms"]})
    return out, remapped


# ─────────────────────────────────────────────── identity scoring
def _track_ident(tr, ident_fn, neg_fn):
    """Aggregate identity of an identity-HOMOGENEOUS segment (tracks are
    pre-split at persistent identity changes by _apply_identity_splits, so a
    top-k aggregate can no longer be carried by stale early frames)."""
    sims, negs = [], []
    for s in tr.samples:
        if not _usable(s):
            continue
        try:
            sims.append(float(ident_fn(s["emb"])))
            negs.append(float(neg_fn(s["emb"])) if neg_fn else 0.0)
        except Exception:
            continue
    sims_sorted = sorted(sims, reverse=True)
    negs_sorted = sorted(negs, reverse=True)
    score = (sum(sims_sorted[:3]) / min(3, len(sims_sorted))) if sims_sorted else 0.0
    neg = (sum(negs_sorted[:3]) / min(3, len(negs_sorted))) if negs_sorted else 0.0
    teams = [s["team"] for s in tr.samples if s.get("team")]
    team_conflict = (len(teams) >= 3
                     and sum(1 for t in teams if t in ("opponent", "other")) > len(teams) / 2.0)
    return {"score": round(score, 4), "neg": round(neg, 4), "usable": len(sims),
            "team_conflict": team_conflict,
            "neg_conflict": bool(negs_sorted) and neg >= score + 0.10}


def _post_window_sim(samples, after_ms, ident_fn):
    best = None
    for s in samples:
        if s["ms"] <= after_ms or s["ms"] > after_ms + POST_WIN_MS:
            continue
        if not _usable(s):
            continue
        try:
            v = float(ident_fn(s["emb"]))
        except Exception:
            continue
        best = v if best is None else max(best, v)
    return best


# ─────────────────────────────────────────────── R02/R03 evidence reasoning
def _adj_ident(ii):
    """Negative-relative identity: matching the tap profile matters only to
    the degree the body matches it BETTER than the negative teammate gallery.
    Same-kit teammates score high raw similarity but low relative evidence."""
    return ii["score"] + NEG_REL_W * (ii["score"] - ii["neg"])


def _concurrent_best_adj(tracks, idents, tr, used=()):
    """Best rival evidence among tracks visible AT THE SAME TIME as `tr`.
    Non-concurrent tracks may be the SAME player (fragments) and must never
    block selection — they are chained via re-acquisition instead."""
    s0, s1 = tr.samples[0]["ms"], tr.samples[-1]["ms"]
    best = None
    for o in tracks:
        if o.tid == tr.tid or o.tid in used or not o.samples:
            continue
        if o.samples[0]["ms"] <= s1 and o.samples[-1]["ms"] >= s0:
            a = _adj_ident(idents[o.tid])
            best = a if best is None else max(best, a)
    return best


def _affirmative(ii):
    """Positive identity evidence in its own right (S02–S04): the fragment
    must clearly match the tap profile AND beat the negative teammate gallery.
    The mere absence of a concurrent rival is NOT identity evidence.
    The neg separation always needs the FULL margin — a same-kit teammate
    matches the gallery systematically, so extra frames reduce variance but
    never that bias (strong-evidence relaxation applies to rival margins only)."""
    if ii["score"] < SIM_T + REACQ_BONUS:
        return False
    return ii["score"] >= ii["neg"] + MARGIN_T


def _wins_margin(ii, best_other_adj):
    """Evidence-scaled acceptance: rich multi-frame evidence may win with a
    smaller adjusted margin; thin evidence still needs the full margin.
    With NO concurrent rival the candidate must stand on affirmative
    evidence — a sequential same-kit teammate never wins by walkover."""
    a = _adj_ident(ii)
    if best_other_adj is None:
        return _affirmative(ii)
    if ii["usable"] >= STRONG_USABLE and a >= best_other_adj + ADJ_MARGIN_STRONG:
        return True
    return a >= best_other_adj + MARGIN_T


# ─────────────────────────────────────── FIX09A.1 — global prototype bank
def _harvest_bank(results, ident_fn):
    """A1 — bounded, diverse GLOBAL_TARGET positive prototype bank harvested
    ONLY from pass-1 identity-safe observations:
    - TAP_PINNED scenes only
    - directly tap-pinned segments (profile-consistent samples), and
      gate-confirmed fragments only after conservative verification
      (sample itself must clearly match the tap profile)
    - never from occluded/predicted geometry (segments hold detections only),
      overlap/contaminated crops (_usable), duel frames, unresolved
      candidates or teammate tracks.
    Diversity is preserved per (scene, scale-bucket) instead of collapsing
    everything into one averaged appearance."""
    rows = []
    for r in results:
        if r["reid_state"] != "TAP_PINNED":
            continue
        duels = r["duel_spans"]
        for seg in r["segments"]:
            floor = SIM_T if seg["join"] == "PIN" else SIM_T + REACQ_BONUS
            for s in seg["samples"]:
                if not _usable(s):
                    continue
                if any(d0 <= s["ms"] <= d1 for d0, d1 in duels):
                    continue
                try:
                    v = float(ident_fn(s["emb"]))
                except Exception:
                    continue
                if v < floor:
                    continue
                rows.append({"emb": s["emb"], "score": v, "h": s["box"][3],
                             "scene": r["sd"]["no"]})
    buckets = {}
    for row in rows:
        h, hb = max(6.0, row["h"]), 0
        while h > 12.0:
            h /= 2.0
            hb += 1
        buckets.setdefault((row["scene"], hb), []).append(row)
    bank = []
    for key in sorted(buckets):
        items = sorted(buckets[key], key=lambda x: -x["score"])
        bank.extend(items[:BANK_PER_BUCKET])
    bank.sort(key=lambda x: -x["score"])
    return bank[:BANK_MAX]


def _bank_sim(emb, bank, pair_sim):
    """A4 — multi-prototype scoring: a candidate may strongly match one valid
    target VIEW (far/close/orientation) while differing from others. Robust
    aggregation: mean of the two strongest prototype matches — acceptance
    needs two independent supporting views, one lucky match is discounted."""
    sims = []
    for p in bank:
        try:
            sims.append(float(pair_sim(emb, p["emb"])))
        except Exception:
            continue
    if not sims:
        return 0.0
    sims.sort(reverse=True)
    if len(sims) == 1:
        return sims[0] * BANK_SINGLE_DISCOUNT
    return (sims[0] + sims[1]) / 2.0


# ─────────────────────────────────────────────── target chain per scene
def _resume_trim(samples, ident_fn, pin_ms_list, neg_fn=None):
    """MOT re-match after a real gap must be identity-confirmed — a nearby
    teammate walking into the stale prediction region must not inherit the
    track. A tap pin inside the resumed portion overrides (tap authority).
    A2.5/S02 — a non-pinned resume is a re-acquisition in disguise: the
    resumed content must also BEAT the negative teammate gallery, not merely
    look vaguely target-like."""
    if not samples:
        return samples
    out = [samples[0]]
    for k in range(1, len(samples)):
        s = samples[k]
        gap_ms = s["ms"] - samples[k - 1]["ms"]
        if s["gap_before"] >= 2 or gap_ms > 500:
            if any(p >= s["ms"] - PIN_WINDOW_MS for p in pin_ms_list):
                out.append(s)
                continue
            sims, seps = [], []
            for q in samples[k:]:
                if q["ms"] - s["ms"] > RESUME_WIN_MS:
                    break
                if _usable(q):
                    try:
                        v = float(ident_fn(q["emb"]))
                        sims.append(v)
                        seps.append(v - (float(neg_fn(q["emb"])) if neg_fn else 0.0))
                    except Exception:
                        pass
            best = max(sims) if sims else None
            if best is not None and best < SIM_T * 0.75:
                break  # resumed content is NOT the target — cut honestly
            if best is not None and neg_fn is not None and seps \
                    and max(seps) < MARGIN_T:
                break  # no resumed sample separates the target from a known
                       # teammate — a glued-on same-kit body, cut honestly
            if best is None and gap_ms > 700:
                break  # long blind gap with zero identity evidence — cut
        out.append(s)
    return out


def _edge_ref_box(samples_edge_last, width):
    """Scale reference at a chain edge: a frame-edge box under-measures the
    body — use the nearest sample fully inside the frame when available."""
    m = max(4.0, 0.04 * width)
    for s in reversed(samples_edge_last):
        b = s["box"]
        if b[0] >= m and (b[0] + b[2]) <= width - m:
            return b
    return samples_edge_last[-1]["box"]


def _kin_score(edge_box, edge_ms, cand, width):
    """A2.4 — kinematic continuity of a candidate continuation with the chain
    edge: 1.0 = re-appears where the target was lost, 0.0 = at the physical
    speed-limit boundary. Within-scene physics only — never across cuts."""
    edge_s = cand.samples[0] if cand.samples[0]["ms"] > edge_ms else cand.samples[-1]
    gap_s = abs(edge_s["ms"] - edge_ms) / 1000.0
    c0, c1 = _center(edge_box), _center(edge_s["box"])
    allow = MAX_SPEED * width * max(0.2, gap_s) + 1.2 * max(edge_box[3], edge_s["box"][3])
    return max(0.0, 1.0 - math.hypot(c1[0] - c0[0], c1[1] - c0[1]) / max(1e-6, allow))


def _shape_sig(samples):
    """A2.3 — deterministic body/motion signature beyond kit colour:
    scale-normalized aspect ratio + body-height-normalized speed."""
    us = [s for s in samples if _usable(s)]
    if len(us) < SHAPE_MIN_USABLE:
        return None
    asp = sorted(s["box"][2] / max(1e-6, s["box"][3]) for s in us)
    spd = []
    for a, b in zip(samples, samples[1:]):
        dt = (b["ms"] - a["ms"]) / 1000.0
        if not 0.0 < dt <= 0.5:
            continue
        ca, cb = _center(a["box"]), _center(b["box"])
        spd.append(math.hypot(cb[0] - ca[0], cb[1] - ca[1]) / dt / max(1.0, a["box"][3]))
    spd.sort()
    if not spd:
        return None
    return {"aspect": asp[len(asp) // 2], "speed": spd[len(spd) // 2]}


def _shape_dist(a, b):
    if a is None or b is None:
        return None
    return 0.5 * abs(a["aspect"] - b["aspect"]) / 0.25 \
        + 0.5 * abs(a["speed"] - b["speed"]) / 1.5


def _reacq_base_ok(cand, cand_ident, edge_box, edge_ms, width, scale_ref):
    if cand_ident["usable"] < 1 or cand_ident["team_conflict"] or cand_ident["neg_conflict"]:
        return False
    if cand_ident["score"] < SIM_T + REACQ_BONUS:
        return False
    edge_s = cand.samples[0] if cand.samples[0]["ms"] > edge_ms else cand.samples[-1]
    if edge_box is not None:
        cand_ordered = (list(reversed(cand.samples))
                        if cand.samples[0]["ms"] > edge_ms else list(cand.samples))
        cand_ref = _edge_ref_box(cand_ordered, width)
        hr = cand_ref[3] / max(1e-6, scale_ref[3])
        if hr < SCALE_JOIN[0] or hr > SCALE_JOIN[1]:
            return False  # physically implausible scale jump (within scene)
        gap_s = abs(edge_s["ms"] - edge_ms) / 1000.0
        if 0.0 < gap_s <= 1.0:
            c0, c1 = _center(edge_box), _center(edge_s["box"])
            if math.hypot(c1[0] - c0[0], c1[1] - c0[1]) > (
                    MAX_SPEED * width * gap_s + 1.2 * max(edge_box[3], edge_s["box"][3])):
                return False  # teleport — a nearby body is not the target
    return True


def _crossing_intervals(crossings, tid, span0, span1):
    per = {}
    for c in crossings:
        if tid not in (c["a"], c["b"]):
            continue
        other = c["b"] if c["a"] == tid else c["a"]
        if c["ms"] < span0 or c["ms"] > span1:
            continue
        per.setdefault(other, []).append(c["ms"])
    out = []
    for other, mss in per.items():
        mss.sort()
        s0 = prev = mss[0]
        for m in mss[1:]:
            if m - prev > 900:
                out.append((other, s0, prev))
                s0 = m
            prev = m
        out.append((other, s0, prev))
    out.sort(key=lambda x: x[1])
    return out


def _build_scene_chain(scene_no, tracks, crossings, pins, pin_restrict,
                       ident_fn, neg_fn, width, guard_fn=None,
                       shape_sig=None, stats=None, tap_hyps=None):
    """Returns (segments, reid_state, duel_spans, idents).
    segment = {"track", "samples", "join"}  join ∈ PIN | CUT_REID | REACQ."""
    idents = {tr.tid: _track_ident(tr, ident_fn, neg_fn) for tr in tracks}
    by_tid = {tr.tid: tr for tr in tracks}

    # A5 flip-guard — in pass 2 the prototype bank may RAISE recall but must
    # never FLIP which concurrent body the tap-time profile prefers. If the
    # candidate loses the base-profile ordering to a concurrent rival, the two
    # evidence sources disagree on identity → ambiguity → fail closed.
    guard_idents = None
    if guard_fn is not None:
        guard_idents = {tr.tid: _track_ident(tr, guard_fn, neg_fn) for tr in tracks}

    def _guard_ok(tr, pool_g, used_g=()):
        if guard_idents is None:
            return True
        gi = guard_idents[tr.tid]
        s0, s1 = tr.samples[0]["ms"], tr.samples[-1]["ms"]
        for o in pool_g:
            if o.tid == tr.tid or o.tid in used_g or not o.samples:
                continue
            if o.samples[0]["ms"] > s1 or o.samples[-1]["ms"] < s0:
                continue
            go = guard_idents[o.tid]
            # only rivals the base profile GENUINELY recognizes can veto —
            # ordering among sub-threshold noise scores is meaningless
            if go["score"] >= SIM_T and go["usable"] >= 3 \
                    and _adj_ident(go) >= _adj_ident(gi) + MARGIN_T:
                return False
        return True

    def _guard_swap_ok(a_samples, b_samples, ov1):
        if guard_fn is None:
            return True
        ag = _post_window_sim(a_samples, ov1, guard_fn)
        bg = _post_window_sim(b_samples, ov1, guard_fn)
        return not (ag is not None and bg is not None and ag >= bg + MARGIN_T)
    pin_list = sorted(pins or [])                      # [(ms, tid)]
    pin_ms_by_tid = {}
    for pms, ptid in pin_list:
        pin_ms_by_tid.setdefault(ptid, []).append(pms)

    segments, duel_spans = [], []
    used = set()

    def _add_segment(tr, join, samples=None):
        smp = _resume_trim(samples if samples is not None else list(tr.samples),
                           ident_fn, pin_ms_by_tid.get(tr.tid, []), neg_fn)
        if not smp:
            return None
        seg = {"track": tr, "samples": smp, "join": join}
        segments.append(seg)
        used.add(tr.tid)
        return seg

    reid_state = None
    if pin_list:
        reid_state = "TAP_PINNED"
        seen = set()
        for _pms, ptid in pin_list:
            if ptid in seen or ptid not in by_tid:
                continue
            seen.add(ptid)
            _add_segment(by_tid[ptid], "PIN")
        segments.sort(key=lambda g: g["samples"][0]["ms"])
        # A2.1 — an unbound (recovered) tap left a bounded hypothesis set in a
        # pinned scene: tap authority says the target IS one of those bodies
        # at the tap instant. Select within the set under the full identity
        # gates — never against it. Skipped when the hypotheses involve the
        # already-pinned chain (that ambiguity belongs to duel resolution).
        if pin_restrict and not (set(pin_restrict) & used):
            spans0 = [(g["samples"][0]["ms"], g["samples"][-1]["ms"])
                      for g in segments if g["samples"]]

            def _conc_chain(tr):
                t0, t1 = tr.samples[0]["ms"], tr.samples[-1]["ms"]
                return any(t0 <= b and t1 >= a for a, b in spans0)

            # physical exclusion: a body concurrent with tap-pinned target
            # geometry is a confirmed non-target for its whole track
            rem = [tr for tr in tracks if tr.tid in pin_restrict
                   and tr.samples and not _conc_chain(tr)]
            sane = [tr for tr in rem
                    if idents[tr.tid]["usable"] >= 3
                    and not idents[tr.tid]["team_conflict"]
                    and not idents[tr.tid]["neg_conflict"]]
            if len(sane) == 1 and idents[sane[0].tid]["score"] >= SIM_T * 0.75:
                # tap-authority ELIMINATION: the tap bound the target to this
                # hypothesis set and every alternative is physically excluded
                # (concurrent with pinned target geometry) — the survivor IS
                # the tapped body. The human tap is the identity authority;
                # kit-level appearance need not be affirmative here.
                _add_segment(sane[0], "CUT_REID")
                if stats is not None:
                    stats["tap_restricted_joins"] = stats.get("tap_restricted_joins", 0) + 1
                segments = [s for s in segments if s["samples"]]
                segments.sort(key=lambda g: g["samples"][0]["ms"])
            else:
                rcands = [tr for tr in sane
                          if idents[tr.tid]["score"] >= SIM_T + CUT_REID_BONUS]
                rcands.sort(key=lambda tr: -_adj_ident(idents[tr.tid]))
                if rcands and _wins_margin(idents[rcands[0].tid],
                                           _concurrent_best_adj(rem, idents, rcands[0])) \
                        and _guard_ok(rcands[0], rem):
                    _add_segment(rcands[0], "CUT_REID")
                    if stats is not None:
                        stats["tap_restricted_joins"] = stats.get("tap_restricted_joins", 0) + 1
                    segments = [s for s in segments if s["samples"]]
                    segments.sort(key=lambda g: g["samples"][0]["ms"])
    else:
        # R02/R03 — whole-scene offline re-identification for tap-less scenes
        # (or C04 bounded tap hypotheses): rank ALL local tracks by
        # multi-frame negative-relative evidence, drop candidates contradicted
        # by team/negative identity, and accept the winner only if it clearly
        # beats every CONCURRENT rival (fragments of the target itself are
        # chained later, never counted as rivals).
        pool = tracks if not pin_restrict else [tr for tr in tracks
                                                if tr.tid in pin_restrict]
        cands = []
        for tr in pool:
            ii = idents[tr.tid]
            if ii["usable"] >= 3 and not ii["team_conflict"] and not ii["neg_conflict"] \
                    and ii["score"] >= SIM_T + CUT_REID_BONUS:
                cands.append(tr)
        cands.sort(key=lambda tr: -_adj_ident(idents[tr.tid]))
        if cands:
            best = cands[0]
            # tap authority constrains the hypothesis space: in restricted
            # mode the target IS one of the tapped candidates, so only those
            # candidates are rivals — an untapped body cannot outrank them.
            rival_pool = pool if pin_restrict else tracks
            ok = (_wins_margin(idents[best.tid],
                               _concurrent_best_adj(rival_pool, idents, best))
                  and _guard_ok(best, rival_pool))
            if not ok and shape_sig is not None and _guard_ok(best, rival_pool):
                # A2.3 — same-kit near-tie: the body/motion signature must
                # CLEARLY favour the appearance leader over EVERY blocking
                # rival; colour-equal AND shape-equal pairs stay unresolved.
                ba = _adj_ident(idents[best.tid])
                bs = _shape_dist(_shape_sig(best.samples), shape_sig)
                blockers = [o for o in rival_pool
                            if o.tid != best.tid and o.samples
                            and o.samples[0]["ms"] <= best.samples[-1]["ms"]
                            and o.samples[-1]["ms"] >= best.samples[0]["ms"]
                            and _adj_ident(idents[o.tid]) + MARGIN_T > ba]
                if bs is not None and blockers \
                        and idents[best.tid]["score"] >= SIM_T + CUT_REID_BONUS:
                    seps = [_shape_dist(_shape_sig(o.samples), shape_sig)
                            for o in blockers]
                    if all(od is not None and od >= bs + SHAPE_MARGIN for od in seps):
                        ok = True
                        if stats is not None:
                            stats["shape_tiebreaks"] = stats.get("shape_tiebreaks", 0) + 1
            if ok:
                _add_segment(best, "CUT_REID")
                reid_state = ("TAP_PINNED" if pin_restrict
                              else ("CUT_REID" if scene_no > 0 else "APPEARANCE_REID"))
            else:
                reid_state = "UNRESOLVED"  # concurrent near-equal rivals — never guess
        else:
            reid_state = "NO_TARGET" if not tracks else "UNRESOLVED"

    # ── retrospective duel resolution on every selected segment ──
    def _resolve(seg, depth=0):
        tr = seg["track"]
        if not seg["samples"] or depth > 4:
            return
        span0, span1 = seg["samples"][0]["ms"], seg["samples"][-1]["ms"]
        for other_tid, ov0, ov1 in _crossing_intervals(crossings, tr.tid, span0, span1):
            other = by_tid.get(other_tid)
            if other is None:
                continue
            a_post = _post_window_sim(seg["samples"], ov1, ident_fn)
            b_post = _post_window_sim(other.samples, ov1, ident_fn)
            pin_after = any(p >= ov0 for p in pin_ms_by_tid.get(tr.tid, []))
            if (not pin_after and other_tid not in used
                    and b_post is not None and b_post >= SIM_T
                    and b_post >= (a_post or 0.0) + MARGIN_T
                    and _guard_swap_ok(seg["samples"], other.samples, ov1)
                    and _guard_ok(other, tracks, used)):
                # SWAP: MOT followed the wrong body through the duel — the
                # post-separation evidence says the target continued on the
                # OTHER local track. Ambiguous middle stays unresolved.
                seg["samples"] = [s for s in seg["samples"] if s["ms"] < ov0]
                cont = [s for s in other.samples if s["ms"] > ov1]
                new = _add_segment(other, "REACQ", cont)
                first_ms = new["samples"][0]["ms"] if new else ov1
                duel_spans.append((ov0, first_ms))
                if new:
                    new["_partial"] = True
                    _resolve(new, depth + 1)
                return
            if a_post is not None and a_post >= SIM_T * 0.8:
                continue  # identity confirmed on our side after separation
            if a_post is None and b_post is None:
                continue  # no post evidence either way — overlap stays PARTIAL
            # our own side failed identity after the duel — fail closed
            seg["samples"] = [s for s in seg["samples"] if s["ms"] < ov0]
            duel_spans.append((ov0, span1))
            return

    for seg in list(segments):
        _resolve(seg)
    segments = [s for s in segments if s["samples"]]
    segments.sort(key=lambda g: g["samples"][0]["ms"] if g["samples"] else 0)

    # ── R02.5 — bidirectional in-scene reconciliation: once ANY part of the
    # scene is confidently identified, chain identity-verified fragments both
    # FORWARD and BACKWARD through the scene (offline video — future frames
    # legitimately resolve earlier ones). No fragment may overlap the chain
    # in time (a concurrent body is a different player).
    changed = True
    while changed:
        changed = False
        segments = [s for s in segments if s["samples"]]
        segments.sort(key=lambda g: g["samples"][0]["ms"])
        if not segments:
            break
        chain0 = segments[0]["samples"][0]
        chain1 = segments[-1]["samples"][-1]
        spans = [(g["samples"][0]["ms"], g["samples"][-1]["ms"]) for g in segments]

        def _overlaps_chain(tr):
            t0, t1 = tr.samples[0]["ms"], tr.samples[-1]["ms"]
            return any(t0 <= b and t1 >= a for a, b in spans)

        # A2.2 physical exclusion — a body concurrent with ACCEPTED target
        # geometry is a confirmed non-target: it remains negative evidence
        # but is no identity rival for the continuation choice.
        excl = {o.tid for o in tracks
                if o.samples and o.tid not in used and _overlaps_chain(o)}
        fwd_ref = _edge_ref_box(segments[-1]["samples"], width)
        bwd_ref = _edge_ref_box(list(reversed(segments[0]["samples"])), width)

        hyps = []
        for tr in tracks:
            if tr.tid in used or not tr.samples or _overlaps_chain(tr):
                continue
            if tr.samples[0]["ms"] > chain1["ms"]:
                edge, sref = chain1, fwd_ref
            elif tr.samples[-1]["ms"] < chain0["ms"]:
                edge, sref = chain0, bwd_ref
            else:
                continue
            # tap authority veto — a trusted (recovered) tap placed the target
            # among specific bodies at its instant; a track alive at that
            # instant but outside the hypothesis set cannot be the target.
            if any(tr.samples[0]["ms"] <= h_ms <= tr.samples[-1]["ms"]
                   and tr.tid not in h_set for h_ms, h_set in (tap_hyps or [])):
                continue
            ii = idents[tr.tid]
            if not _reacq_base_ok(tr, ii, edge["box"], edge["ms"], width, sref):
                continue
            if not _guard_ok(tr, tracks, used | excl):
                continue
            gap = (tr.samples[0]["ms"] - edge["ms"] if tr.samples[0]["ms"] > edge["ms"]
                   else edge["ms"] - tr.samples[-1]["ms"])
            hyps.append({"tr": tr, "ii": ii, "adj": _adj_ident(ii), "gap": gap,
                         "kin": _kin_score(edge["box"], edge["ms"], tr, width),
                         "other": _concurrent_best_adj(tracks, idents, tr, used | excl)})
        if not hyps:
            break
        hyps.sort(key=lambda h: -(h["adj"] + KIN_W * h["kin"]))
        pick = next((h for h in hyps if _wins_margin(h["ii"], h["other"])), None)
        if pick is None:
            # A2.4 kinematic path tiebreak — ONLY when concurrent rivals exist
            # and appearance is a statistical tie; strong physical continuity
            # with the point of loss then separates the hypotheses. A lone
            # walk-in body still needs affirmative evidence (S02).
            h = hyps[0]
            path = h["adj"] + KIN_W * h["kin"]
            second = max((g["adj"] + KIN_W * g["kin"] for g in hyps[1:]), default=None)
            if (h["other"] is not None and h["kin"] >= KIN_MIN
                    and h["other"] - h["adj"] < MARGIN_T
                    and h["gap"] <= REENTRY_MAX_GAP_MS
                    and (second is None or path >= second + MARGIN_T)):
                pick = h
                if stats is not None:
                    stats["kinematic_reacq"] = stats.get("kinematic_reacq", 0) + 1
        if pick is not None:
            seg = _add_segment(pick["tr"], "REACQ")
            if seg:
                _resolve(seg)
                changed = True
    segments = [s for s in segments if s["samples"]]
    segments.sort(key=lambda g: g["samples"][0]["ms"])
    # a target handoff across a duel (identity split or swap) is an explicit
    # ambiguous interval, even when the handoff gap itself is short
    for i in range(1, len(segments)):
        g0 = segments[i - 1]["samples"][-1]["ms"]
        g1 = segments[i]["samples"][0]["ms"]
        if g1 > g0 and any(g0 <= c["ms"] <= g1 for c in crossings):
            duel_spans.append((g0, g1))
    if segments and reid_state in ("UNRESOLVED", "NO_TARGET"):
        reid_state = "REACQ"
    return segments, reid_state, duel_spans, idents


# ─────────────────────────────────────────────── emission
def _norm_box(b, w, h):
    return {"x": round(max(0.0, b[0]) / w, 4), "y": round(max(0.0, b[1]) / h, 4),
            "w": round(b[2] / w, 4), "h": round(b[3] / h, 4)}


def _emit_scene_points(scene_id, scene_after_cut, segments, ident_fn, width, height,
                       points, duel_spans=(), stats=None):
    last_ms = -1
    prev_det = None
    for seg in segments:
        tr = seg["track"]
        first = True
        prev_s = None
        if prev_det is not None and seg["samples"]:
            # A2.2 — labeled continuity fill across a short, gate-verified
            # join (never across an ambiguous duel): predicted-only geometry,
            # NEVER proof-grade.
            s0 = seg["samples"][0]
            gap = s0["ms"] - prev_det["ms"]
            if 0 < gap <= OCCL_FILL_MAX_MS and not any(
                    d0 < s0["ms"] and d1 > prev_det["ms"] for d0, d1 in duel_spans):
                t = prev_det["ms"] + FILL_STEP_MS
                while t < s0["ms"]:
                    f = (t - prev_det["ms"]) / gap
                    fb = tuple(prev_det["box"][i] + f * (s0["box"][i] - prev_det["box"][i])
                               for i in range(4))
                    points.append({
                        "media_ms": int(t), "scene_id": scene_id,
                        "local_track_id": f"p{tr.tid:02d}",
                        "box": _norm_box(fb, width, height),
                        "state": "OCCLUDED", "identity_score": None,
                        "geometry_source": "interpolated", "predicted": True,
                        "proof_eligible": False,
                    })
                    if stats is not None:
                        stats["occlusion_fill_points"] = stats.get("occlusion_fill_points", 0) + 1
                    t += FILL_STEP_MS
        for s in seg["samples"]:
            if s["ms"] <= last_ms:
                continue
            if prev_s is not None and s["gap_before"] >= 1:
                # OCCLUDED fill — ONLY between two accepted samples (the track
                # resumed, so the occlusion is retrospectively confirmed).
                for _i, (pms, pbox) in sorted(tr.miss_preds.items()):
                    if prev_s["ms"] < pms < s["ms"] and pms > last_ms:
                        points.append({
                            "media_ms": int(pms), "scene_id": scene_id,
                            "local_track_id": f"p{tr.tid:02d}",
                            "box": _norm_box(pbox, width, height),
                            "state": "OCCLUDED", "identity_score": None,
                            "geometry_source": "predicted", "predicted": True,
                            "proof_eligible": False,
                        })
            if first:
                if seg["join"] == "CUT_REID" and scene_after_cut:
                    state = "CUT_REID"
                elif seg["join"] == "REACQ":
                    state = "REACQUIRED"
                else:
                    state = None
            else:
                state = None
            if state is None:
                if s["gap_before"] >= 2:
                    state = "REACQUIRED"
                elif s["overlap"] or (isinstance(s["emb"], dict) and s["emb"].get("owned") is False):
                    state = "PARTIAL"
                else:
                    state = "VISIBLE"
            score = None
            if _usable(s):
                try:
                    score = round(float(ident_fn(s["emb"])), 3)
                except Exception:
                    score = None
            points.append({
                "media_ms": int(s["ms"]), "scene_id": scene_id,
                "local_track_id": f"p{tr.tid:02d}",
                "box": _norm_box(s["box"], width, height),
                "state": state, "identity_score": score,
                "geometry_source": "detection", "predicted": False,
                "proof_eligible": True,
            })
            last_ms = s["ms"]
            first = False
            prev_s = s
            prev_det = {"ms": s["ms"], "box": s["box"]}


# ─────────────────────────────────────────────── deterministic core
def assemble_timeline(observations, taps=None, identity_sim=None,
                      negative_sim=None, pair_sim=None):
    """Pure deterministic assembly. `observations` = per sampled frame:
    {media_ms:int, cut:bool, cam_dx, cam_dy, width, height, sig,
     detections:[{box:(x,y,w,h) px, emb, team}]}. `taps` = [{media_ms, box(px)}].
    identity_sim(emb)→[0,1] similarity to the tap identity profile;
    negative_sim(emb)→[0,1] similarity to the negative teammate gallery;
    pair_sim(emb_a, emb_b)→[0,1] appearance similarity between two
    observations — enables the FIX09A.1 tap-independent prototype bank."""
    ident_fn = identity_sim or (lambda e: 0.0)
    neg_fn = negative_sim
    obs = sorted((o for o in (observations or []) if isinstance(o.get("media_ms"), (int, float))),
                 key=lambda o: o["media_ms"])
    if not obs:
        return {"version": VERSION, "status": "empty", "global_target_id": "GLOBAL_TARGET",
                "scenes": [], "target_points": [], "other_tracks": [],
                "unresolved_intervals": [], "counts": {s: 0 for s in STATES}}
    width = float(obs[0].get("width") or SMALL_W)
    height = float(obs[0].get("height") or SMALL_W * 9 / 16)

    scene_idx = _split_scenes(obs)
    scene_data = []
    for sn, idxs in enumerate(scene_idx):
        tracks, crossings = _scene_mot(obs, idxs)
        # C03 — split local tracks at persistent identity changes BEFORE any
        # pinning/selection: a silent MOT switch becomes a segment boundary.
        tracks, crossings = _apply_identity_splits(tracks, crossings, ident_fn, neg_fn)
        scene_data.append({
            "no": sn, "idxs": idxs, "tracks": tracks, "crossings": crossings,
            "start_ms": int(obs[idxs[0]]["media_ms"]),
            "end_ms": int(obs[idxs[-1]]["media_ms"]),
        })

    # ── tap pinning: FIX00A absolute authority (C04: never bound arbitrarily
    # when the tap lands on spatially ambiguous overlapping bodies) ──
    pins_by_scene = {}
    restrict_by_scene = {}
    tap_hyps_by_scene = {}
    recovery = {"tap_recovered_pins": 0, "tap_restricted": 0}
    for tap in (taps or []):
        tms = tap.get("media_ms")
        tbox = tap.get("box")
        if not isinstance(tms, (int, float)) or not tbox:
            continue
        # R01/F5 — a tap binds to the scene that TRULY contains its timestamp;
        # the ±window fallback applies only when no scene contains it (a tap
        # 0.3 s before a cut must not pin a body in the previous clip).
        sd = next((d for d in scene_data if d["start_ms"] <= tms <= d["end_ms"]), None)
        if sd is None:
            sd = next((d for d in scene_data
                       if d["start_ms"] - PIN_WINDOW_MS <= tms <= d["end_ms"] + PIN_WINDOW_MS), None)
        if sd is None:
            continue
        by_tid = {tr.tid: tr for tr in sd["tracks"]}
        cands = {}
        for tr in sd["tracks"]:
            for s in tr.samples:
                if abs(s["ms"] - tms) > PIN_WINDOW_MS:
                    continue
                v = _iou(s["box"], tbox)
                tc = _center(tbox)
                inside = (s["box"][0] <= tc[0] <= s["box"][0] + s["box"][2]
                          and s["box"][1] <= tc[1] <= s["box"][1] + s["box"][3])
                if v < 0.15 and not inside:
                    continue
                key = (abs(s["ms"] - tms), -v)
                if tr.tid not in cands or key < cands[tr.tid]:
                    cands[tr.tid] = key

        def _near_sim(tid):
            best = None
            for s in by_tid[tid].samples:
                if abs(s["ms"] - tms) > PIN_APPEAR_WIN_MS or not _usable(s):
                    continue
                try:
                    v = float(ident_fn(s["emb"]))
                except Exception:
                    continue
                best = v if best is None else max(best, v)
            return best

        if not cands:
            # A2.1 — TAP-INSTANT LOCAL RECOVERY: the trusted tap has no
            # containing detection (detector miss / box misalignment). Bind
            # to NEARBY visible body evidence within one body-height — never
            # invent geometry where no detection exists at all.
            tc = _center(tbox)
            relaxed = {}
            for tr in sd["tracks"]:
                for s in tr.samples:
                    if abs(s["ms"] - tms) > PIN_WINDOW_MS:
                        continue
                    c = _center(s["box"])
                    dd = math.hypot(c[0] - tc[0], c[1] - tc[1])
                    if dd > TAP_RECOVER_DIST_H * max(s["box"][3], tbox[3]):
                        continue
                    key = (abs(s["ms"] - tms), dd)
                    if tr.tid not in relaxed or key < relaxed[tr.tid]:
                        relaxed[tr.tid] = key
            if not relaxed:
                continue          # no visible body evidence — fail closed
            if len(relaxed) == 1:
                pins_by_scene.setdefault(sd["no"], []).append((int(tms), next(iter(relaxed))))
                recovery["tap_recovered_pins"] += 1
                continue
            near_r = sorted(((k[0], k[1], tid) for tid, k in relaxed.items()),
                            key=lambda x: x[1])
            (rdt1, rd1, rtid1), rd2 = near_r[0], near_r[1][1]
            if rdt1 <= 400 and rd1 <= 0.5 * rd2:
                # one body clearly closest to the tapped spot at the moment
                pins_by_scene.setdefault(sd["no"], []).append((int(tms), rtid1))
                recovery["tap_recovered_pins"] += 1
                continue
            r_ranked = sorted(((_near_sim(t), t) for t in relaxed),
                              key=lambda x: -(x[0] if x[0] is not None else -1.0))
            r_top, r_tid = r_ranked[0]
            r_2nd = r_ranked[1][0] if len(r_ranked) > 1 and r_ranked[1][0] is not None else 0.0
            if r_top is not None and r_top >= SIM_T and r_top >= r_2nd + MARGIN_T:
                pins_by_scene.setdefault(sd["no"], []).append((int(tms), r_tid))
                recovery["tap_recovered_pins"] += 1
            else:
                # bounded hypotheses — the tap roots identity to this SET;
                # selection happens later under the full identity gates
                restrict_by_scene.setdefault(sd["no"], set()).update(relaxed.keys())
                tap_hyps_by_scene.setdefault(sd["no"], []).append(
                    (int(tms), frozenset(relaxed.keys())))
                recovery["tap_restricted"] += 1
            continue
        if len(cands) == 1:
            pins_by_scene.setdefault(sd["no"], []).append((int(tms), next(iter(cands))))
            continue
        # C04a — SPATIAL DOMINANCE at the tap MOMENT: the tap box is the
        # user's statement of WHERE the player is. Judged on each track's
        # temporally-nearest sample (a box 0.5 s away may belong to a body
        # that moved into the tapped spot). If one body clearly occupies the
        # tap while every rival barely grazes it, the tap is not ambiguous.
        near = sorted(((k[0], -k[1], tid) for tid, k in cands.items()),
                      key=lambda x: -x[1])          # by nearest-sample IoU
        (dt1, sp1, sp1_tid), sp2 = near[0], (near[1][1] if len(near) > 1 else 0.0)
        if dt1 <= 400 and sp1 >= PIN_DOMINANT_IOU \
                and (sp2 < PIN_RIVAL_IOU or sp1 >= 2.0 * sp2):
            pins_by_scene.setdefault(sd["no"], []).append((int(tms), sp1_tid))
            continue
        # multiple bodies genuinely overlap the tap — resolve by identity
        # evidence:
        # 1) appearance around the tap (owned, non-overlapped samples only,
        #    matched against the OTHER tap references / negative gallery)
        ranked = sorted(((_near_sim(t), t) for t in cands),
                        key=lambda x: -(x[0] if x[0] is not None else -1.0))
        top_sim, top_tid = ranked[0]
        second = ranked[1][0] if len(ranked) > 1 and ranked[1][0] is not None else 0.0
        if top_sim is not None and top_sim >= SIM_T and top_sim >= second + MARGIN_T:
            pins_by_scene.setdefault(sd["no"], []).append((int(tms), top_tid))
            continue
        # 2) post-separation frames between the two spatially closest bodies
        pair = sorted(cands, key=lambda t: cands[t])[:2]
        sep = None
        for c in sd["crossings"]:
            if {c["a"], c["b"]} == set(pair) and abs(c["ms"] - tms) <= 4000:
                sep = c["ms"] if sep is None else max(sep, c["ms"])
        if sep is not None:
            pa = _post_window_sim(by_tid[pair[0]].samples, sep, ident_fn)
            pb = _post_window_sim(by_tid[pair[1]].samples, sep, ident_fn)
            aa, bb = (pa if pa is not None else -1.0), (pb if pb is not None else -1.0)
            win, win_sim, lose_sim = (pair[0], aa, bb) if aa >= bb else (pair[1], bb, aa)
            if win_sim >= SIM_T and win_sim >= max(0.0, lose_sim) + MARGIN_T:
                pins_by_scene.setdefault(sd["no"], []).append((int(tms), win))
                continue
        # 3) bounded competing hypotheses — selection stays restricted to the
        # tapped candidates and must pass the strict identity gates later
        restrict_by_scene.setdefault(sd["no"], set()).update(cands.keys())
        tap_hyps_by_scene.setdefault(sd["no"], []).append(
            (int(tms), frozenset(cands.keys())))

    # ── two-pass offline reasoning (A2) ──
    def _chain_all(fn, guard=None, shape_sig=None, stats=None):
        out = []
        for sd in scene_data:
            segments, reid_state, duel_spans, idents = _build_scene_chain(
                sd["no"], sd["tracks"], sd["crossings"], pins_by_scene.get(sd["no"]),
                restrict_by_scene.get(sd["no"]), fn, neg_fn, width, guard_fn=guard,
                shape_sig=shape_sig, stats=stats,
                tap_hyps=tap_hyps_by_scene.get(sd["no"]))
            out.append({"sd": sd, "segments": segments, "reid_state": reid_state,
                        "duel_spans": duel_spans, "idents": idents})
        return out

    ident_used = ident_fn
    stats = {}
    results = _chain_all(ident_fn, stats=stats)          # PASS 1 — tap authority + safe tracks
    bank = []
    if pair_sim is not None:
        bank = _harvest_bank(results, ident_fn)
        if bank:
            # A2.3 — global target body/motion signature from directly
            # tap-pinned pass-1 geometry only (identity-safe by construction)
            pin_samples = []
            for r in results:
                if r["reid_state"] == "TAP_PINNED":
                    for seg in r["segments"]:
                        if seg["join"] == "PIN":
                            pin_samples.extend(seg["samples"])
            pin_samples.sort(key=lambda s: s["ms"])
            target_shape = _shape_sig(pin_samples)
            # PASS 2 — revisit every scene with the tap-independent multi-view
            # profile. The bank is FROZEN from pass-1 safe evidence: pass-2
            # acceptances are never harvested back (no recursive
            # self-training / contamination). Positive bank evidence only
            # RAISES a candidate's identity — every acceptance still passes
            # the full margin/affirmative/scale/duel gates.
            def _ident2(e):
                try:
                    base = float(ident_fn(e))
                except Exception:
                    base = 0.0
                return max(base, _bank_sim(e, bank, pair_sim))
            ident_used = _ident2
            stats = {}
            results = _chain_all(_ident2, guard=ident_fn,
                                 shape_sig=target_shape, stats=stats)

    points, scenes_out, other_tracks, unresolved = [], [], [], []
    counts = {s: 0 for s in STATES}
    for r in results:
        sd = r["sd"]
        segments, reid_state = r["segments"], r["reid_state"]
        duel_spans, idents = r["duel_spans"], r["idents"]
        sn = sd["no"]
        scene_id = f"scene_{sn + 1:03d}"
        before = len(points)
        _emit_scene_points(scene_id, sn > 0, segments, ident_used, width, height,
                           points, duel_spans, stats)
        scene_pts = points[before:]
        target_tids = {seg["track"].tid for seg in segments}
        fully_used = {seg["track"].tid for seg in segments
                      if not seg.get("_partial") and len(seg["samples"]) == len(seg["track"].samples)}
        for tr in sd["tracks"]:
            if tr.tid in fully_used or not tr.samples:
                continue
            teams = [s["team"] for s in tr.samples if s.get("team")]
            other_tracks.append({
                "scene_id": scene_id, "local_track_id": f"p{tr.tid:02d}",
                "start_ms": int(tr.samples[0]["ms"]), "end_ms": int(tr.samples[-1]["ms"]),
                "samples": len(tr.samples),
                "team": max(set(teams), key=teams.count) if teams else None,
                "partial_target": tr.tid in target_tids,
                "identity_score": idents[tr.tid]["score"],
            })
        for d0, d1 in duel_spans:
            if d1 > d0:
                unresolved.append({"scene_id": scene_id, "start_ms": int(d0),
                                   "end_ms": int(d1), "reason": "ambiguous_duel"})
        if not scene_pts:
            unresolved.append({
                "scene_id": scene_id, "start_ms": sd["start_ms"], "end_ms": sd["end_ms"],
                "reason": "no_target" if reid_state == "NO_TARGET" else "reid_failed"})
        else:
            def _covered_by_duel(a, b):
                return any(d0 <= a and b <= d1 for d0, d1 in duel_spans)
            if scene_pts[0]["media_ms"] - sd["start_ms"] > UNRESOLVED_GAP_MS \
                    and not _covered_by_duel(sd["start_ms"], scene_pts[0]["media_ms"]):
                unresolved.append({"scene_id": scene_id, "start_ms": sd["start_ms"],
                                   "end_ms": scene_pts[0]["media_ms"], "reason": "target_absent"})
            for a, b in zip(scene_pts, scene_pts[1:]):
                if b["media_ms"] - a["media_ms"] > UNRESOLVED_GAP_MS \
                        and not _covered_by_duel(a["media_ms"], b["media_ms"]):
                    unresolved.append({"scene_id": scene_id, "start_ms": a["media_ms"],
                                       "end_ms": b["media_ms"], "reason": "target_absent"})
            if sd["end_ms"] - scene_pts[-1]["media_ms"] > UNRESOLVED_GAP_MS \
                    and not _covered_by_duel(scene_pts[-1]["media_ms"], sd["end_ms"]):
                unresolved.append({"scene_id": scene_id, "start_ms": scene_pts[-1]["media_ms"],
                                   "end_ms": sd["end_ms"], "reason": "target_absent"})
        for p in scene_pts:
            counts[p["state"]] += 1
        scenes_out.append({
            "scene_id": scene_id, "start_ms": sd["start_ms"], "end_ms": sd["end_ms"],
            "target_local_track_id": (f"p{segments[0]['track'].tid:02d}" if segments else None),
            "reid_state": reid_state,
        })

    # merge overlapping/duplicate unresolved intervals (same scene + reason)
    merged_unresolved = []
    for key in sorted({(u["scene_id"], u["reason"]) for u in unresolved}):
        rows = sorted((u for u in unresolved
                       if (u["scene_id"], u["reason"]) == key),
                      key=lambda u: u["start_ms"])
        for u in rows:
            last = merged_unresolved[-1] if merged_unresolved else None
            if (last and last["scene_id"] == u["scene_id"]
                    and last["reason"] == u["reason"]
                    and u["start_ms"] <= last["end_ms"]):
                last["end_ms"] = max(last["end_ms"], u["end_ms"])
            else:
                merged_unresolved.append(dict(u))
    merged_unresolved.sort(key=lambda u: (u["start_ms"], u["scene_id"]))

    return {
        "version": VERSION,
        "status": "ok",
        "global_target_id": "GLOBAL_TARGET",
        "scenes": scenes_out,
        "target_points": points,
        "other_tracks": other_tracks[:300],
        "unresolved_intervals": merged_unresolved,
        "profile_bank": {"size": len(bank),
                         "scenes": sorted({p["scene"] + 1 for p in bank})},
        "recovery": {
            "tap_recovered_pins": recovery["tap_recovered_pins"],
            "tap_restricted": recovery["tap_restricted"],
            "tap_restricted_joins": stats.get("tap_restricted_joins", 0),
            "kinematic_reacq": stats.get("kinematic_reacq", 0),
            "shape_tiebreaks": stats.get("shape_tiebreaks", 0),
            "occlusion_fill_points": stats.get("occlusion_fill_points", 0),
        },
        "counts": counts,
        "config": {"sim_t": SIM_T, "margin_t": MARGIN_T, "reacq_bonus": REACQ_BONUS,
                   "max_speed": MAX_SPEED, "overlap_iou": OVERLAP_IOU,
                   "switch_min_run": SWITCH_MIN_RUN},
    }


# ─────────────────────────────────────────────── video ingestion (production)
def build_identity_timeline(video_path: str, doc: dict):
    """Decode the video ONCE at HZ, detect ALL players per sampled frame,
    embed them with the calibrated cv_shadow primitives and assemble the
    global identity timeline. Zero LLM/network calls. Never raises."""
    import cv2
    import numpy as np
    import cv_detect
    import cv_shadow
    import video_timebase

    t_start = time.time()
    cap = None
    try:
        anchors = [a for a in (doc.get("anchors") or []) if isinstance(a, dict) and a.get("box")]
        if not anchors:
            return {"version": VERSION, "status": "skipped", "reason": "no_anchors"}
        t_off = float(doc.get("anchor_time_offset") or 0.0)
        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            return {"version": VERSION, "status": "skipped", "reason": "no_video"}
        fps = cap.get(cv2.CAP_PROP_FPS) or 15.0
        W = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        H = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        if W < 100 or H < 100:
            return {"version": VERSION, "status": "skipped", "reason": "bad_video"}
        scale = SMALL_W / W
        sw, sh = SMALL_W, max(2, int(H * scale))

        # FIX09A has its own production gate (IDENTITY_TIMELINE_ENABLED).
        # Never inherit CV_SHADOW_DETECTOR: that legacy switch controls only
        # optional shadow diagnostics and must not disable GLOBAL_TARGET.
        detector = cv_detect.PersonDetector(enabled=True)
        if not detector.ok:
            return {"version": VERSION, "status": "skipped",
                    "reason": "detector_unavailable"}
        refs, negatives = cv_shadow._build_tap_references(
            cap, fps, anchors, t_off, sw, sh, scale, detector=detector)
        if len(refs) < 2:
            return {"version": VERSION, "status": "skipped", "reason": "too_few_references"}
        _chromas = [r["chroma"] for r in refs if r.get("chroma")]
        _anchor = (float(np.median([c[0] for c in _chromas])),
                   float(np.median([c[1] for c in _chromas]))) if _chromas else None
        team = cv_detect.TeamModel(_anchor)
        cam = cv_detect.CameraMotion(out_scale=sw / 160.0)

        # C02 — frame-relative retention band: keep every plausible football
        # player regardless of how the tap-time camera scale compared to the
        # current scene (wide/close/zoomed). Scale plausibility is enforced
        # later, scene-adaptively, during association and re-acquisition.
        min_h = max(6.0, PLAYER_MIN_FRAC * sh)
        max_h = PLAYER_MAX_FRAC * sh

        observations = []
        cap.set(cv2.CAP_PROP_POS_MSEC, 0.0)
        interval = 1.0 / HZ if HZ > 0 else 0.0
        prev_sample_t = None
        prev_tiny = None
        while True:
            ok, t, _fb = video_timebase.grab_frame_time_seconds(cap, fps)
            if not ok:
                break
            if not video_timebase.should_sample(t, prev_sample_t, interval):
                continue
            ok, frame = cap.retrieve()
            if not ok:
                break
            prev_sample_t = t
            small = cv2.resize(frame, (sw, sh))
            pitch_l = cv_shadow._pitch_l(small)
            tiny = cv2.cvtColor(cv2.resize(small, (160, max(2, int(sh * 160 / sw)))),
                                cv2.COLOR_BGR2GRAY).astype(np.float32)
            diff = (float(cv2.absdiff(prev_tiny, tiny).mean())
                    if prev_tiny is not None and prev_tiny.shape == tiny.shape else 0.0)
            cam.update(tiny)
            prev_tiny = tiny
            # hard cut: big global diff the camera model cannot explain
            cut = (diff > CUT_DIFF and cam.mode != "affine") or diff > CUT_DIFF_HARD
            cam_dx, cam_dy = (0.0, 0.0) if cut else (cam.dx, cam.dy)
            sig = cv2.resize(tiny, (8, 8), interpolation=cv2.INTER_AREA).flatten().tolist()

            boxes = []
            if detector.ok:
                for (nx, ny, nw_, nh_, _dc) in detector.detect(frame):
                    b = (float(int(nx * sw)), float(int(ny * sh)),
                         float(max(3, int(nw_ * sw))), float(max(6, int(nh_ * sh))))
                    if min_h <= b[3] <= max_h:
                        boxes.append(b)
            else:
                roi = np.full((sh, sw), 255, np.uint8)
                boxes = [tuple(float(v) for v in bb) for bb in cv_shadow._blobs(
                    small, roi, min_h=int(min_h), max_h=int(max_h))]
            dets = []
            for b in boxes:
                occ = [o for o in boxes if o is not b and _iou(o, b) > 0.05]
                emb = cv_shadow._zone_embedding(
                    small, tuple(int(v) for v in b), pitch_l, occluders=occ or None)
                ch = cv_detect.torso_chroma(small, b)
                team.add(ch)
                dets.append({"box": b, "emb": emb, "team": team.classify(ch)})
            observations.append({
                "media_ms": int(round(t * 1000)), "cut": cut,
                "cam_dx": cam_dx, "cam_dy": cam_dy, "sig": sig,
                "width": sw, "height": sh, "detections": dets,
            })

        taps = []
        for a in anchors:
            try:
                taps.append({
                    "media_ms": int(round((float(a["t"]) + t_off) * 1000)),
                    "box": (float(a["box"]["x"]) * sw, float(a["box"]["y"]) * sh,
                            max(4.0, float(a["box"]["w"]) * sw),
                            max(8.0, float(a["box"]["h"]) * sh)),
                })
            except Exception:
                continue

        def _ident(emb):
            return cv_shadow._profile_sim(emb, refs)

        def _neg(emb):
            return max((cv_shadow._sim(emb, n) for n in negatives), default=0.0)

        def _pair(a, b):
            return cv_shadow._sim(a, b)

        tl = assemble_timeline(observations, taps, _ident,
                               _neg if negatives else None, pair_sim=_pair)
        tl.update({
            "hz": HZ,
            "samples": len(observations),
            "duration_ms": int(observations[-1]["media_ms"]) if observations else 0,
            "tap_references": len(refs),
            "negative_gallery": len(negatives),
            "detector": bool(detector.ok),
            "compute_s": round(time.time() - t_start, 1),
        })
        logger.info(
            f"[fix09a] timeline: scenes={len(tl['scenes'])} points={len(tl['target_points'])} "
            f"counts={tl['counts']} unresolved={len(tl['unresolved_intervals'])} "
            f"({tl['compute_s']}s for {tl['samples']} samples)"
        )
        return tl
    except Exception as e:
        logger.exception("[fix09a] identity timeline failed")
        return {"version": VERSION, "status": "error", "reason": str(e)[:200]}
    finally:
        try:
            if cap is not None:
                cap.release()
        except Exception:
            pass


# ─────────────────────────────────────────────── production comparison
def compare_with_production(timeline: dict, gt_track: dict) -> dict:
    """Observe-only comparison of the new global timeline vs the FIX04
    production track. Feeds the migration decision — changes nothing."""
    try:
        tl_pts = [p for p in (timeline or {}).get("target_points") or []
                  if not p.get("predicted")]
        gt_pts = [p for p in (gt_track or {}).get("points") or []
                  if isinstance(p.get("t"), (int, float))]
        hz = float((timeline or {}).get("hz") or HZ)
        by_ms = sorted(tl_pts, key=lambda p: p["media_ms"])
        compared = agree = 0
        for g in gt_pts:
            gms = float(g["t"]) * 1000.0
            near = None
            for p in by_ms:
                d = abs(p["media_ms"] - gms)
                if d <= 400 and (near is None or d < abs(near["media_ms"] - gms)):
                    near = p
            if near is None:
                continue
            compared += 1
            gcx = float(g["x"]) + float(g["w"]) / 2.0
            gcy = float(g["y"]) + float(g["h"]) / 2.0
            b = near["box"]
            tcx, tcy = b["x"] + b["w"] / 2.0, b["y"] + b["h"] / 2.0
            tol = 1.2 * max(float(g["h"]), b["h"])
            if math.hypot(gcx - tcx, gcy - tcy) <= tol:
                agree += 1
        gt_ms = {int(round(float(g["t"]) * 1000 / 500)) for g in gt_pts}
        tl_only = sum(1 for p in tl_pts if int(round(p["media_ms"] / 500)) not in gt_ms)
        return {
            "gt_points": len(gt_pts),
            "timeline_points": len(tl_pts),
            "timeline_predicted_points": sum(
                1 for p in (timeline or {}).get("target_points") or [] if p.get("predicted")),
            "gt_coverage_s": round(len(gt_pts) / 12.5, 1),
            "timeline_coverage_s": round(len(tl_pts) / max(0.1, hz), 1),
            "compared": compared,
            "agreement_rate": round(agree / compared, 3) if compared else None,
            "timeline_only_points": tl_only,
            "timeline_only_s": round(tl_only / max(0.1, hz), 1),
            "scenes": len((timeline or {}).get("scenes") or []),
            "unresolved_intervals": len((timeline or {}).get("unresolved_intervals") or []),
        }
    except Exception as e:
        return {"error": str(e)[:200]}
