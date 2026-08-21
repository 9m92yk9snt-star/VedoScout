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
def _split_scenes(obs):
    scenes, cur = [], []
    for i, o in enumerate(obs):
        if o.get("cut") and cur:
            scenes.append(cur)
            cur = []
        cur.append(i)
    if cur:
        scenes.append(cur)
    return scenes


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


# ─────────────────────────────────────────────── target chain per scene
def _resume_trim(samples, ident_fn, pin_ms_list):
    """MOT re-match after a real gap must be identity-confirmed — a nearby
    teammate walking into the stale prediction region must not inherit the
    track. A tap pin inside the resumed portion overrides (tap authority)."""
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
            sims = []
            for q in samples[k:]:
                if q["ms"] - s["ms"] > RESUME_WIN_MS:
                    break
                if _usable(q):
                    try:
                        sims.append(float(ident_fn(q["emb"])))
                    except Exception:
                        pass
            best = max(sims) if sims else None
            if best is not None and best < SIM_T * 0.75:
                break  # resumed content is NOT the target — cut honestly
            if best is None and gap_ms > 700:
                break  # long blind gap with zero identity evidence — cut
        out.append(s)
    return out


def _reacq_ok(cand, cand_ident, last_box, last_ms, best_other_score, width):
    if cand_ident["usable"] < 1 or cand_ident["team_conflict"] or cand_ident["neg_conflict"]:
        return False
    if cand_ident["score"] < SIM_T + REACQ_BONUS:
        return False
    if best_other_score is not None and cand_ident["score"] < best_other_score + MARGIN_T:
        return False
    first = cand.samples[0]
    if last_box is not None:
        hr = first["box"][3] / max(1e-6, last_box[3])
        if hr < SCALE_JOIN[0] or hr > SCALE_JOIN[1]:
            return False  # physically implausible scale jump
        gap_s = max(0.0, (first["ms"] - last_ms) / 1000.0)
        if 0.0 < gap_s <= 1.0:
            c0, c1 = _center(last_box), _center(first["box"])
            if math.hypot(c1[0] - c0[0], c1[1] - c0[1]) > (
                    MAX_SPEED * width * gap_s + 1.2 * max(last_box[3], first["box"][3])):
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
                       ident_fn, neg_fn, width):
    """Returns (segments, reid_state, duel_spans, idents).
    segment = {"track", "samples", "join"}  join ∈ PIN | CUT_REID | REACQ."""
    idents = {tr.tid: _track_ident(tr, ident_fn, neg_fn) for tr in tracks}
    by_tid = {tr.tid: tr for tr in tracks}
    pin_list = sorted(pins or [])                      # [(ms, tid)]
    pin_ms_by_tid = {}
    for pms, ptid in pin_list:
        pin_ms_by_tid.setdefault(ptid, []).append(pms)

    segments, duel_spans = [], []
    used = set()

    def _add_segment(tr, join, samples=None):
        smp = _resume_trim(samples if samples is not None else list(tr.samples),
                           ident_fn, pin_ms_by_tid.get(tr.tid, []))
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
    else:
        # tap-less scene (highlight cut) or C04 bounded tap hypotheses —
        # appearance re-identification with strict gates and a clear margin.
        pool = tracks if not pin_restrict else [tr for tr in tracks
                                                if tr.tid in pin_restrict]
        cands = []
        for tr in pool:
            ii = idents[tr.tid]
            if ii["usable"] >= 2 and not ii["team_conflict"] and not ii["neg_conflict"] \
                    and ii["score"] >= SIM_T + CUT_REID_BONUS:
                cands.append(tr)
        cands.sort(key=lambda tr: -idents[tr.tid]["score"])
        if cands:
            best = cands[0]
            runner = max((idents[tr.tid]["score"] for tr in tracks if tr.tid != best.tid),
                         default=0.0)
            if idents[best.tid]["score"] >= runner + MARGIN_T:
                _add_segment(best, "CUT_REID")
                reid_state = ("TAP_PINNED" if pin_restrict
                              else ("CUT_REID" if scene_no > 0 else "APPEARANCE_REID"))
            else:
                reid_state = "UNRESOLVED"  # near-equal candidates — never guess
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
                    and b_post >= (a_post or 0.0) + MARGIN_T):
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

    # ── re-acquisition extension: later identity-verified tracks may join ──
    changed = True
    while changed:
        changed = False
        segments.sort(key=lambda g: g["samples"][0]["ms"])
        if not segments:
            break
        last = segments[-1]
        last_ms = last["samples"][-1]["ms"]
        last_box = last["samples"][-1]["box"]
        cands = [tr for tr in tracks if tr.tid not in used
                 and tr.samples and tr.samples[0]["ms"] > last_ms]
        cands.sort(key=lambda tr: tr.samples[0]["ms"])
        for tr in cands:
            span = (tr.samples[0]["ms"], tr.samples[-1]["ms"])
            best_other = max((idents[o.tid]["score"] for o in tracks
                              if o.tid != tr.tid and o.tid not in used
                              and o.samples and o.samples[0]["ms"] <= span[1]
                              and o.samples[-1]["ms"] >= span[0]), default=None)
            if _reacq_ok(tr, idents[tr.tid], last_box, last_ms, best_other, width):
                seg = _add_segment(tr, "REACQ")
                if seg:
                    _resolve(seg)
                    changed = True
                break
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


def _emit_scene_points(scene_id, scene_after_cut, segments, ident_fn, width, height, points):
    last_ms = -1
    for seg in segments:
        tr = seg["track"]
        first = True
        prev_s = None
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


# ─────────────────────────────────────────────── deterministic core
def assemble_timeline(observations, taps=None, identity_sim=None,
                      negative_sim=None):
    """Pure deterministic assembly. `observations` = per sampled frame:
    {media_ms:int, cut:bool, cam_dx, cam_dy, width, height,
     detections:[{box:(x,y,w,h) px, emb, team}]}. `taps` = [{media_ms, box(px)}].
    identity_sim(emb)→[0,1] similarity to the tap identity profile;
    negative_sim(emb)→[0,1] similarity to the negative teammate gallery."""
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
    for tap in (taps or []):
        tms = tap.get("media_ms")
        tbox = tap.get("box")
        if not isinstance(tms, (int, float)) or not tbox:
            continue
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
        if not cands:
            continue
        if len(cands) == 1:
            pins_by_scene.setdefault(sd["no"], []).append((int(tms), next(iter(cands))))
            continue
        # multiple bodies overlap the tap — resolve by identity evidence:
        # 1) appearance around the tap (owned, non-overlapped samples only,
        #    matched against the OTHER tap references / negative gallery)
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

    points, scenes_out, other_tracks, unresolved = [], [], [], []
    counts = {s: 0 for s in STATES}
    for sd in scene_data:
        sn = sd["no"]
        scene_id = f"scene_{sn + 1:03d}"
        segments, reid_state, duel_spans, idents = _build_scene_chain(
            sn, sd["tracks"], sd["crossings"], pins_by_scene.get(sn),
            restrict_by_scene.get(sn), ident_fn, neg_fn, width)
        before = len(points)
        _emit_scene_points(scene_id, sn > 0, segments, ident_fn, width, height, points)
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

    return {
        "version": VERSION,
        "status": "ok",
        "global_target_id": "GLOBAL_TARGET",
        "scenes": scenes_out,
        "target_points": points,
        "other_tracks": other_tracks[:300],
        "unresolved_intervals": unresolved,
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

        detector = cv_detect.PersonDetector()
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
                "cam_dx": cam_dx, "cam_dy": cam_dy,
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

        tl = assemble_timeline(observations, taps, _ident, _neg if negatives else None)
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
