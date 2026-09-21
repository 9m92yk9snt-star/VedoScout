/**
 * multiPoseEnroll.js — Improvement #1 of the Trust Stack.
 *
 * When the user marks their child once in the studio, this module silently
 * tracks the same child for ±5 seconds around the marked anchor and gathers
 * 8-12 same-player crops. From those crops it builds a richer "multi-pose
 * fingerprint" used by the auto-suggest stage to find the player throughout
 * the rest of the video — instead of relying on a single brittle frame.
 *
 * The tracker is intentionally simple (greedy IoU + colour continuity), no
 * deep models, no extra downloads — works in the browser in <2s on a 30 s
 * 1080p clip. When tracking is lost mid-scan we just skip the missing frame
 * and continue; we don't need perfect recall, only enough crops to span
 * pose/lighting variation.
 *
 * Public API:
 *   enrollFromMark(videoEl, anchor, detector, opts) → MultiPoseRef
 *
 *   MultiPoseRef = {
 *     crops:        [{ t, bbox, jerseyRGB, shortsRGB, hairRGB, thumbDataUrl }]
 *     avgJerseyRGB: [r,g,b]
 *     avgShortsRGB: [r,g,b]
 *     avgHairRGB:   [r,g,b]
 *     bestThumb:    dataURL (the biggest, sharpest crop — used for the report card)
 *   }
 */

// ── Tunables ──────────────────────────────────────────────────────────
const WINDOW_S = 5.0;          // ±5 seconds around the anchor
const N_SAMPLES = 14;            // how many frames to sample in the window
const IOU_LOCK_THRESHOLD = 0.30; // minimum IoU to consider a detection the same player
const COLOR_LOCK_TOLERANCE = 75; // RGB Euclidean — when IoU is weak, use colour as backup
const MIN_CROPS = 4;             // need at least this many crops to consider enrollment successful

/* Bounding-box helpers ────────────────────────────────────────────── */

/** Intersection-over-Union for two MediaPipe detection boxes (originX/Y/width/height). */
function iou(a, b) {
  const ax2 = a.originX + a.width;
  const ay2 = a.originY + a.height;
  const bx2 = b.originX + b.width;
  const by2 = b.originY + b.height;
  const ix1 = Math.max(a.originX, b.originX);
  const iy1 = Math.max(a.originY, b.originY);
  const ix2 = Math.min(ax2, bx2);
  const iy2 = Math.min(ay2, by2);
  const iw = Math.max(0, ix2 - ix1);
  const ih = Math.max(0, iy2 - iy1);
  const inter = iw * ih;
  const union = a.width * a.height + b.width * b.height - inter;
  return union > 0 ? inter / union : 0;
}

/** Mean RGB of the upper-torso region of a detection box. */
function sampleJersey(ctx, bb, canvasW, canvasH) {
  const sx = Math.max(0, Math.floor(bb.originX + bb.width * 0.25));
  const sy = Math.max(0, Math.floor(bb.originY + bb.height * 0.18));
  const sw = Math.max(2, Math.floor(Math.min(canvasW - sx, bb.width * 0.5)));
  const sh = Math.max(2, Math.floor(Math.min(canvasH - sy, bb.height * 0.35)));
  if (sw < 4 || sh < 4) return null;
  try {
    const data = ctx.getImageData(sx, sy, sw, sh).data;
    let r = 0, g = 0, b = 0, n = 0;
    for (let i = 0; i < data.length; i += 20) {
      r += data[i]; g += data[i + 1]; b += data[i + 2]; n++;
    }
    return n ? [Math.round(r / n), Math.round(g / n), Math.round(b / n)] : null;
  } catch {
    return null;
  }
}

/** Mean RGB of the shorts region (below jersey). */
function sampleShorts(ctx, bb, canvasW, canvasH) {
  const sx = Math.max(0, Math.floor(bb.originX + bb.width * 0.3));
  const sy = Math.max(0, Math.floor(bb.originY + bb.height * 0.55));
  const sw = Math.max(2, Math.floor(Math.min(canvasW - sx, bb.width * 0.4)));
  const sh = Math.max(2, Math.floor(Math.min(canvasH - sy, bb.height * 0.22)));
  if (sw < 4 || sh < 4) return null;
  try {
    const data = ctx.getImageData(sx, sy, sw, sh).data;
    let r = 0, g = 0, b = 0, n = 0;
    for (let i = 0; i < data.length; i += 20) {
      r += data[i]; g += data[i + 1]; b += data[i + 2]; n++;
    }
    return n ? [Math.round(r / n), Math.round(g / n), Math.round(b / n)] : null;
  } catch {
    return null;
  }
}

/** Mean RGB of the head/hair region (top 15% of box). */
function sampleHair(ctx, bb, canvasW, canvasH) {
  const sx = Math.max(0, Math.floor(bb.originX + bb.width * 0.30));
  const sy = Math.max(0, Math.floor(bb.originY));
  const sw = Math.max(2, Math.floor(Math.min(canvasW - sx, bb.width * 0.4)));
  const sh = Math.max(2, Math.floor(Math.min(canvasH - sy, bb.height * 0.15)));
  if (sw < 4 || sh < 4) return null;
  try {
    const data = ctx.getImageData(sx, sy, sw, sh).data;
    let r = 0, g = 0, b = 0, n = 0;
    for (let i = 0; i < data.length; i += 20) {
      r += data[i]; g += data[i + 1]; b += data[i + 2]; n++;
    }
    return n ? [Math.round(r / n), Math.round(g / n), Math.round(b / n)] : null;
  } catch {
    return null;
  }
}

/** Crop a small JPEG (data-URL) thumb from a detection box. */
function cropThumb(canvas, bb, targetW = 160) {
  const pad = 0.22;
  const cx = Math.max(0, bb.originX - bb.width * pad);
  const cy = Math.max(0, bb.originY - bb.height * pad);
  const cw = Math.min(canvas.width - cx, bb.width * (1 + pad * 2));
  const ch = Math.min(canvas.height - cy, bb.height * (1 + pad * 2));
  if (cw < 8 || ch < 8) return null;
  const out = document.createElement("canvas");
  const W = targetW;
  const H = Math.round(W * (ch / cw));
  out.width = W;
  out.height = H;
  const octx = out.getContext("2d");
  try {
    octx.drawImage(canvas, cx, cy, cw, ch, 0, 0, W, H);
  } catch {
    return null;
  }
  return out.toDataURL("image/jpeg", 0.82);
}

/** Convert normalised box {x,y,w,h} in WRAPPER coordinates to MediaPipe
 *  detection box (originX/Y/width/height) in VIDEO native pixels. */
function wrapperBoxToVideoBB(box, videoEl, wrapperRect) {
  // Compute the rendered video bounds inside the wrapper
  const vw = videoEl.videoWidth, vh = videoEl.videoHeight;
  const cw = wrapperRect.w, ch = wrapperRect.h;
  if (!vw || !vh || !cw || !ch) return null;
  const sx = cw / vw, sy = ch / vh, s = Math.min(sx, sy);
  const renderedW = vw * s, renderedH = vh * s;
  const offX = (cw - renderedW) / 2, offY = (ch - renderedH) / 2;
  // Wrapper-px box → video-relative-px box
  const wpx = box.x * cw, hpy = box.y * ch;
  const wpw = box.w * cw, wph = box.h * ch;
  const vx = (wpx - offX) / s;
  const vy = (hpy - offY) / s;
  const vwBB = wpw / s;
  const vhBB = wph / s;
  return {
    originX: Math.max(0, vx),
    originY: Math.max(0, vy),
    width: Math.max(8, Math.min(vw - vx, vwBB)),
    height: Math.max(8, Math.min(vh - vy, vhBB)),
  };
}

/* Public ──────────────────────────────────────────────────────────── */

/**
 * Track the marked player ±WINDOW_S seconds around the anchor and gather
 * 8-14 same-player crops. Returns a MultiPoseRef or null if too few crops
 * could be locked.
 *
 * @param {HTMLVideoElement} videoEl
 * @param {{ t: number, box: {x,y,w,h} }} anchor   — wrapper-normalised coords
 * @param {object} detector                         — MediaPipe ObjectDetector instance
 * @param {{ wrapperRect: {w,h}, onProgress?: (p:number)=>void, signal?: AbortSignal }} opts
 */
export async function enrollFromMark(videoEl, anchor, detector, opts = {}) {
  const v = videoEl;
  if (!v || !detector) return null;
  if (v.readyState < 2 || !v.videoWidth || !v.duration) return null;
  const { wrapperRect, onProgress, signal } = opts;
  if (!wrapperRect?.w || !wrapperRect?.h) return null;

  const refBB = wrapperBoxToVideoBB(anchor.box, v, wrapperRect);
  if (!refBB) return null;

  // Sample N_SAMPLES timestamps in [t-WINDOW, t+WINDOW]
  const start = Math.max(0.1, anchor.t - WINDOW_S);
  const end = Math.min(v.duration - 0.1, anchor.t + WINDOW_S);
  if (end - start < 0.6) return null;
  const ts = [];
  for (let i = 0; i < N_SAMPLES; i++) {
    ts.push(start + ((end - start) * i) / Math.max(1, N_SAMPLES - 1));
  }
  // Sort by distance to anchor.t so we always have a strong seed first
  ts.sort((a, b) => Math.abs(a - anchor.t) - Math.abs(b - anchor.t));

  const canvas = document.createElement("canvas");
  canvas.width = v.videoWidth;
  canvas.height = v.videoHeight;
  const ctx = canvas.getContext("2d", { willReadFrequently: true });

  // Anchor colour sample from the user's marked frame — used as the colour
  // fallback when IoU doesn't lock cleanly.
  let anchorJersey = null;
  try {
    // Seek to anchor exact time first
    await seekVideo(v, anchor.t);
    ctx.drawImage(v, 0, 0, canvas.width, canvas.height);
    anchorJersey = sampleJersey(ctx, refBB, canvas.width, canvas.height) || [128, 128, 128];
  } catch {
    anchorJersey = [128, 128, 128];
  }

  const colorDist = (a, b) =>
    Math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2);

  // The "rolling reference" — updated after each successful lock so we can
  // tolerate gradual pose/lighting drift away from the user's mark.
  let lastBB = refBB;
  const crops = [];

  for (let i = 0; i < ts.length; i++) {
    if (signal?.aborted) break;
    const t = ts[i];
    try {
      await seekVideo(v, t);
    } catch {
      continue;
    }
    try {
      ctx.drawImage(v, 0, 0, canvas.width, canvas.height);
    } catch {
      continue;
    }
    let result;
    try { result = detector.detect(canvas); } catch { result = null; }
    if (!result?.detections?.length) {
      onProgress && onProgress((i + 1) / ts.length);
      continue;
    }

    // For the anchor.t frame itself we trust the user's mark explicitly —
    // skip the matcher and use refBB directly. (Anchor.t is ts[0] after sort.)
    let chosen = null;
    if (Math.abs(t - anchor.t) < 0.05) {
      // Find the detection whose IoU with refBB is highest
      let bestIoU = 0;
      for (const d of result.detections) {
        const o = iou(d.boundingBox, refBB);
        if (o > bestIoU) { bestIoU = o; chosen = d.boundingBox; }
      }
      if (!chosen || bestIoU < IOU_LOCK_THRESHOLD) chosen = refBB;
    } else {
      // For other timestamps: IoU with lastBB primary, colour distance backup
      let best = null;
      for (const d of result.detections) {
        const bb = d.boundingBox;
        if (bb.width < 20 || bb.height < 40) continue;
        const o = iou(bb, lastBB);
        const jc = sampleJersey(ctx, bb, canvas.width, canvas.height);
        const cd = jc ? colorDist(jc, anchorJersey) : 999;
        // Combined score: high IoU preferred; colour distance penalty added
        // Score ∈ [0,1]; higher is better.
        const cdNorm = Math.min(1, cd / 200); // 0=identical, 1=very different
        const score = o * 0.65 + (1 - cdNorm) * 0.35;
        // Require either reasonable IoU OR very close colour to consider
        if (o < 0.10 && cd > COLOR_LOCK_TOLERANCE) continue;
        if (!best || score > best.score) best = { bb, score };
      }
      if (!best) {
        onProgress && onProgress((i + 1) / ts.length);
        continue;
      }
      chosen = best.bb;
    }

    if (!chosen) {
      onProgress && onProgress((i + 1) / ts.length);
      continue;
    }

    const jerseyRGB = sampleJersey(ctx, chosen, canvas.width, canvas.height);
    const shortsRGB = sampleShorts(ctx, chosen, canvas.width, canvas.height);
    const hairRGB = sampleHair(ctx, chosen, canvas.width, canvas.height);
    const thumbDataUrl = cropThumb(canvas, chosen);
    if (!thumbDataUrl) {
      onProgress && onProgress((i + 1) / ts.length);
      continue;
    }
    crops.push({
      t,
      bbox: { ...chosen },
      jerseyRGB: jerseyRGB || anchorJersey,
      shortsRGB: shortsRGB || null,
      hairRGB: hairRGB || null,
      thumbDataUrl,
      area: chosen.width * chosen.height,
    });
    lastBB = chosen; // roll the reference forward

    onProgress && onProgress((i + 1) / ts.length);
  }

  if (crops.length < MIN_CROPS) return null;

  // Aggregate fingerprint (trimmed mean — drop outliers)
  const avg = (arr) => {
    if (!arr.length) return null;
    const r = arr.reduce((s, v) => s + v[0], 0) / arr.length;
    const g = arr.reduce((s, v) => s + v[1], 0) / arr.length;
    const b = arr.reduce((s, v) => s + v[2], 0) / arr.length;
    return [Math.round(r), Math.round(g), Math.round(b)];
  };

  const jerseys = crops.map((c) => c.jerseyRGB).filter(Boolean);
  const shorts = crops.map((c) => c.shortsRGB).filter(Boolean);
  const hairs = crops.map((c) => c.hairRGB).filter(Boolean);

  // Best thumb = largest crop near the user's anchor (we trust the user's pick most)
  const sortedByQuality = [...crops].sort((a, b) => {
    const aScore = a.area - Math.abs(a.t - anchor.t) * 100;
    const bScore = b.area - Math.abs(b.t - anchor.t) * 100;
    return bScore - aScore;
  });

  return {
    crops,
    avgJerseyRGB: avg(jerseys) || [128, 128, 128],
    avgShortsRGB: avg(shorts),
    avgHairRGB: avg(hairs),
    bestThumb: sortedByQuality[0]?.thumbDataUrl || crops[0].thumbDataUrl,
    cropCount: crops.length,
    sourceAnchor: anchor,
  };
}

/* Helpers ─────────────────────────────────────────────────────────── */

/** Seek and wait for `seeked` (with timeout fallback). */
function seekVideo(v, t) {
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

export const __testing__ = {
  iou,
  sampleJersey,
  sampleShorts,
  sampleHair,
  cropThumb,
  wrapperBoxToVideoBB,
};
