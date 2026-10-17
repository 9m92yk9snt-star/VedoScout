/**
 * sceneDetect.js — client-side highlight-reel segment detection.
 *
 * Designed for ScoutMode v3.1. When the user uploads a highlights video stitched
 * from multiple matches, this module finds the cut-points so the backend can
 * build a SEPARATE multi-pose fingerprint per segment (otherwise the kid's kit
 * change between matches breaks `verify_and_pick_thumbnail`).
 *
 * Algorithm: sample N evenly spaced frames, compute a coarse 8×8 RGB histogram
 * for each, and compare consecutive histograms with chi-squared distance. A
 * value > THRESHOLD = scene cut.
 *
 * Bounded local sampling. No model downloads. No external
 * dependencies — uses native canvas + getImageData.
 *
 * Public API:
 *   detectSceneCuts(videoEl, opts) → Promise<{ cuts: number[], samples: number[] }>
 *   distributeHints(duration, cuts, count = 10) → number[]
 */

import videoFrameAuthority from "./videoFrameAuthority.cjs";

const DEFAULT_SAMPLES = 12;
const HIST_BINS = 8; // 8×8 = 64 bins per RGB channel collapsed
const CHI_SQUARED_THRESHOLD = 0.42; // tuned for typical highlight reels

/** Build a coarse 8-bin per-channel histogram (flat 24-length vector) from a canvas. */
function frameHistogram(ctx, w, h) {
  const data = ctx.getImageData(0, 0, w, h).data;
  const hist = new Float32Array(HIST_BINS * 3);
  let n = 0;
  // Subsample every 20 pixels for speed
  for (let i = 0; i < data.length; i += 20 * 4) {
    const r = data[i], g = data[i + 1], b = data[i + 2];
    const ri = Math.min(HIST_BINS - 1, (r * HIST_BINS) >> 8);
    const gi = Math.min(HIST_BINS - 1, (g * HIST_BINS) >> 8);
    const bi = Math.min(HIST_BINS - 1, (b * HIST_BINS) >> 8);
    hist[ri] += 1;
    hist[HIST_BINS + gi] += 1;
    hist[HIST_BINS * 2 + bi] += 1;
    n++;
  }
  if (n > 0) for (let i = 0; i < hist.length; i++) hist[i] /= n;
  return hist;
}

/** Chi-squared distance between two normalised histograms (0=identical, 1=very different). */
function chiSquared(a, b) {
  let s = 0;
  for (let i = 0; i < a.length; i++) {
    const num = (a[i] - b[i]) ** 2;
    const den = (a[i] + b[i]) || 1e-6;
    s += num / den;
  }
  // Three independent normalised channels each have a maximum distance of 2.
  // Dividing by 24 bins made the maximum 0.25: the 0.42 cut threshold was
  // unreachable even when two frames had entirely different colours.
  return s / 6;
}

// Compare actual decoded clarity in the field band, rather than rewarding a
// sharp tree/sky at the top of a portrait clip. This ranks frames, not players.
function frameClarity(ctx, w, h) {
  const { data } = ctx.getImageData(0, 0, w, h);
  const gray = (x, y) => {
    const i = (y * w + x) * 4;
    return (data[i] * 0.299 + data[i + 1] * 0.587 + data[i + 2] * 0.114) / 255;
  };
  let energy = 0, usable = 0, n = 0;
  for (let y = Math.max(1, Math.floor(h * 0.35)); y < h * 0.9 - 1; y += 2) {
    for (let x = 1; x < w - 1; x += 2) {
      const value = gray(x, y);
      energy += Math.abs(gray(x - 1, y) + gray(x + 1, y) + gray(x, y - 1) + gray(x, y + 1) - 4 * value);
      usable += value > 0.04 && value < 0.96 ? 1 : 0; n++;
    }
  }
  return n ? (energy / n) * (usable / n) : 0;
}

/** Seek to a positively acknowledged presented frame. */
function seek(v, t, signal) {
  return videoFrameAuthority.seekPresentedFrame(v, t, { signal });
}

/**
 * Detect scene cuts (match boundaries) in a video.
 * Returns the cut timestamps (seconds) AND the timestamps that were actually sampled
 * (handy for the timeline-render in ScoutMode).
 *
 * @param {HTMLVideoElement} videoEl
 * @param {{ samples?: number, threshold?: number, onProgress?: (p:number)=>void, signal?: AbortSignal }} opts
 */
export async function detectSceneCuts(videoEl, opts = {}) {
  const v = videoEl;
  if (!v || v.readyState < 1 || !Number.isFinite(v.duration) || v.duration <= 0) return { cuts: [], samples: [] };
  const samples = opts.samples ?? DEFAULT_SAMPLES;
  const threshold = opts.threshold ?? CHI_SQUARED_THRESHOLD;
  const onProgress = opts.onProgress;
  const signal = opts.signal;

  const N = Math.max(6, Math.min(60, samples));
  const dur = v.duration;
  const ts = [];
  for (let i = 0; i < N; i++) ts.push(Math.min(dur - 0.04, (dur * i) / (N - 1)));

  const w = 160, h = Math.max(32, Math.round(w * (v.videoHeight || 9) / (v.videoWidth || 16)));
  const canvas = document.createElement("canvas");
  canvas.width = w; canvas.height = h;
  const ctx = canvas.getContext("2d", { willReadFrequently: true });
  if (!ctx) return { cuts: [], samples: [] };

  let prevHist = null;
  let prevTime = null;
  const sampled = [];
  const qualitySamples = [];
  const cuts = [];
  const wasPlaying = !v.paused;
  v.pause();
  for (let i = 0; i < ts.length; i++) {
    if (signal?.aborted) break;
    let frame;
    try { frame = await seek(v, ts[i], signal); } catch {
      prevHist = null;
      onProgress?.((i + 1) / ts.length);
      continue;
    }
    try {
      ctx.drawImage(v, 0, 0, w, h);
    } catch { continue; }
    let h1;
    try { h1 = frameHistogram(ctx, w, h); } catch { prevHist = null; continue; }
    sampled.push(frame.mediaTime);
    qualitySamples.push({ t: frame.mediaTime, clarity: frameClarity(ctx, w, h) });
    if (prevHist) {
      const d = chiSquared(prevHist, h1);
      if (d > threshold && ts[i] > 1.0) {
        // Place the cut at the midpoint between the prev and current sample,
        // since the real cut is between them.
        const midpoint = (prevTime + frame.mediaTime) / 2;
        // Avoid clustering — at least 3 s apart
        if (!cuts.length || midpoint - cuts[cuts.length - 1] > 3.0) {
          cuts.push(Math.round(midpoint * 100) / 100);
        }
      }
    }
    prevHist = h1;
    prevTime = frame.mediaTime;
    onProgress?.((i + 1) / ts.length);
  }
  if (wasPlaying && !signal?.aborted) v.play().catch(() => {});
  return { cuts, samples: sampled, qualitySamples };
}

/** Reuse sampled source pixels to choose clear moments in each coverage slot. */
export function selectTapHints(duration, cuts, samples, count = 10) {
  const baseline = distributeHints(duration, cuts, count);
  const safeCuts = (cuts || []).filter(t => Number.isFinite(t) && t > 0 && t < duration);
  const segment = t => safeCuts.filter(c => c <= t).length;
  const used = new Set();
  return baseline.map((t, i) => {
    const lo = i ? (baseline[i - 1] + t) / 2 : 0;
    const hi = i + 1 < baseline.length ? (t + baseline[i + 1]) / 2 : duration;
    const candidates = (samples || []).filter(s => Number.isFinite(s.t) && Number.isFinite(s.clarity)
      && s.clarity > 0 && s.t > lo && s.t < hi && !used.has(s.t)
      && segment(s.t) === segment(t) && safeCuts.every(c => Math.abs(c - s.t) > 0.35));
    candidates.sort((a, b) => b.clarity - a.clarity || Math.abs(a.t - t) - Math.abs(b.t - t));
    const chosen = candidates[0]?.t ?? t;
    used.add(chosen);
    return chosen;
  });
}

/**
 * Pure utility — given a video duration and detected scene cuts, return
 * `count` evenly-distributed hint timestamps balanced ACROSS segments.
 *
 * 0 cuts (1 segment) →  count hints spread evenly across [0, dur]
 * N cuts (N+1 segments) → ~count/(N+1) hints per segment, evenly spread within each
 * Always avoids the first/last 5 % of any segment (more likely to be transitions).
 */
export function distributeHints(duration, cuts, count = 10) {
  if (!Number.isFinite(duration) || duration <= 0 || !Number.isInteger(count) || count <= 0) return [];
  const safeCuts = [...new Set((cuts || []).filter((c) => Number.isFinite(c) && c > 1 && c < duration - 1))].sort((a, b) => a - b);
  const boundaries = [0, ...safeCuts, duration];
  const segs = [];
  for (let i = 0; i < boundaries.length - 1; i++) {
    segs.push([boundaries[i], boundaries[i + 1]]);
  }
  // More scenes than slots must still sample the WHOLE clip, not the first ten.
  if (segs.length > count) {
    if (count === 1) return [duration / 2];
    return Array.from({ length: count }, (_, i) => {
      const [a, b] = segs[Math.round(i * (segs.length - 1) / (count - 1))];
      return Number(((a + b) / 2).toFixed(2));
    });
  }
  // One slot per scene, then largest-remainder allocation by scene duration.
  const remaining = count - segs.length;
  const shares = segs.map(([a, b]) => (b - a) / duration * remaining);
  const allocs = shares.map(s => 1 + Math.floor(s));
  const order = shares.map((s, i) => ({ i, remainder: s - Math.floor(s) })).sort((a, b) => b.remainder - a.remainder);
  const spare = count - allocs.reduce((sum, n) => sum + n, 0);
  for (let i = 0; i < spare; i++) allocs[order[i].i] += 1;
  // Distribute timestamps within each segment with 5 % inset on each side
  const out = [];
  segs.forEach(([a, b], i) => {
    const n = allocs[i];
    const inset = (b - a) * 0.05;
    const lo = a + inset;
    const hi = b - inset;
    for (let k = 0; k < n; k++) {
      const frac = n === 1 ? 0.5 : k / (n - 1);
      out.push(Math.round((lo + (hi - lo) * frac) * 100) / 100);
    }
  });
  return out.slice(0, count);
}

export const __testing__ = { frameHistogram, chiSquared, frameClarity, seek };
