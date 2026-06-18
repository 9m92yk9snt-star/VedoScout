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
 * Cheap (~2-4 s on a 5-min 1080p clip). No model downloads. No external
 * dependencies — uses native canvas + getImageData.
 *
 * Public API:
 *   detectSceneCuts(videoEl, opts) → Promise<{ cuts: number[], samples: number[] }>
 *   distributeHints(duration, cuts, count = 10) → number[]
 */

const DEFAULT_SAMPLES = 28;
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
  return s / a.length;
}

/** Seek and wait for `seeked`. */
function seek(v, t) {
  return new Promise((res) => {
    let done = false;
    const finish = () => {
      if (done) return;
      done = true;
      v.removeEventListener("seeked", finish);
      res();
    };
    v.addEventListener("seeked", finish);
    try { v.currentTime = t; } catch { finish(); }
    setTimeout(finish, 700);
  });
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
  if (!v || v.readyState < 2 || !v.duration) return { cuts: [], samples: [] };
  const samples = opts.samples ?? DEFAULT_SAMPLES;
  const threshold = opts.threshold ?? CHI_SQUARED_THRESHOLD;
  const onProgress = opts.onProgress;
  const signal = opts.signal;

  const N = Math.max(6, Math.min(60, samples));
  const dur = v.duration;
  const ts = [];
  for (let i = 0; i < N; i++) ts.push((dur * i) / (N - 1));

  const w = 160, h = 90; // tiny downsample for speed
  const canvas = document.createElement("canvas");
  canvas.width = w; canvas.height = h;
  const ctx = canvas.getContext("2d", { willReadFrequently: true });

  let prevHist = null;
  const cuts = [];
  const wasPlaying = !v.paused;
  v.pause();
  for (let i = 0; i < ts.length; i++) {
    if (signal?.aborted) break;
    try { await seek(v, ts[i]); } catch { continue; }
    try {
      ctx.drawImage(v, 0, 0, w, h);
    } catch { continue; }
    const h1 = frameHistogram(ctx, w, h);
    if (prevHist) {
      const d = chiSquared(prevHist, h1);
      if (d > threshold && ts[i] > 1.0) {
        // Place the cut at the midpoint between the prev and current sample,
        // since the real cut is between them.
        const midpoint = (ts[i - 1] + ts[i]) / 2;
        // Avoid clustering — at least 3 s apart
        if (!cuts.length || midpoint - cuts[cuts.length - 1] > 3.0) {
          cuts.push(Math.round(midpoint * 100) / 100);
        }
      }
    }
    prevHist = h1;
    onProgress?.((i + 1) / ts.length);
  }
  if (wasPlaying) v.play().catch(() => {});
  return { cuts, samples: ts };
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
  if (!duration || duration <= 0 || !count) return [];
  const safeCuts = (cuts || []).filter((c) => c > 1 && c < duration - 1).sort((a, b) => a - b);
  const boundaries = [0, ...safeCuts, duration];
  const segs = [];
  for (let i = 0; i < boundaries.length - 1; i++) {
    segs.push([boundaries[i], boundaries[i + 1]]);
  }
  // Allocate hints proportional to segment duration, with a min-1 floor per segment
  const totalDur = duration;
  const allocs = segs.map(([a, b]) => Math.max(1, Math.round(((b - a) / totalDur) * count)));
  // Adjust to exactly `count`
  let sumAlloc = allocs.reduce((s, n) => s + n, 0);
  while (sumAlloc > count) {
    // remove from the largest segment first
    let idx = 0;
    for (let i = 1; i < allocs.length; i++) if (allocs[i] > allocs[idx]) idx = i;
    if (allocs[idx] > 1) { allocs[idx] -= 1; sumAlloc -= 1; }
    else break;
  }
  while (sumAlloc < count) {
    let idx = 0;
    for (let i = 1; i < allocs.length; i++) if ((segs[i][1] - segs[i][0]) > (segs[idx][1] - segs[idx][0])) idx = i;
    allocs[idx] += 1; sumAlloc += 1;
  }
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

export const __testing__ = { frameHistogram, chiSquared, seek };
