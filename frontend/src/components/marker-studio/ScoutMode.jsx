/**
 * ScoutMode.jsx — the v3.1 "human-in-the-loop" anchor builder.
 *
 * Goal: 10 user-verified anchors, single screen, full timeline control,
 * highlight-reel-safe (scene cuts auto-detected so the backend can build
 * per-segment fingerprints).
 *
 * UX flow:
 *   1. We open as an overlay over the existing MarkerStudio (does NOT replace
 *      the Instant Roster / Manual / Preview screens — pure additive support).
 *   2. On mount: detect scene cuts (~3 s) and distribute 10 hint timestamps
 *      proportionally across the detected segments.
 *   3. The video shows the first hint frame with NUMBERED CHIPS on every
 *      MediaPipe-detected player. User taps their kid's chip → anchor locked.
 *   4. User can:
 *        - scrub the timeline to ANY moment and tap there
 *        - tap a different hint dot to jump there
 *        - press UNDO (↶) to revert the last tap
 *   5. When 10 anchors are locked → a verification grid slides up. User
 *      confirms or replaces individual taps. Then DONE.
 *
 * On confirm: calls `onConfirm({ anchors, sceneCuts })` — parent (MarkerStudio)
 * wires that into the existing handleDone() so the upload + backend pipeline
 * doesn't need any payload change at the call-site.
 */

import React, { useEffect, useRef, useState, useCallback } from "react";
import { createPortal } from "react-dom";
import {
  X,
  Check,
  Loader2,
  RotateCcw,
  Hand,
  Film,
  Sparkles,
} from "lucide-react";

import { detectSceneCuts, distributeHints } from "./sceneDetect";

/* ── Dedicated MediaPipe ObjectDetector for Scout Mode ──────────────
 *  Created in ScoutMode (NOT shared with the rest of MarkerStudio) so we
 *  can use a much more permissive scoreThreshold (0.20) and a higher
 *  maxResults (25). Real-world phone footage shows kids at 50-90 px tall;
 *  the shared detector's stricter 0.35 floor drops most of them.
 *
 *  Uses EfficientDet **Lite 2** instead of Lite 0 — 2-3× better recall on
 *  small (50-80 px) humans, which is exactly the class our wide-shot
 *  phone footage produces. One-time +5 MB model download (cached after).
 *  The other flows (Instant Roster, multi-pose enrol, etc.) keep their
 *  own Lite 0 + 0.35 shared detector — this is purely additive. */
let _scoutDetectorPromise = null;
async function getScoutDetector() {
  if (_scoutDetectorPromise) return _scoutDetectorPromise;
  _scoutDetectorPromise = (async () => {
    const { ObjectDetector, FilesetResolver } = await import(
      "@mediapipe/tasks-vision"
    );
    const fileset = await FilesetResolver.forVisionTasks(
      "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.35/wasm",
    );
    return await ObjectDetector.createFromOptions(fileset, {
      baseOptions: {
        modelAssetPath:
          "https://storage.googleapis.com/mediapipe-models/object_detector/efficientdet_lite2/float16/1/efficientdet_lite2.tflite",
      },
      scoreThreshold: 0.10, // max recall — catch small distant players & motion blur
      maxResults: 40,        // raise — we filter aggressively for tall/human-shaped below
      runningMode: "IMAGE",
      categoryAllowlist: ["person"],
    });
  })();
  return _scoutDetectorPromise;
}

const TARGET_TAPS = 10;
const MIN_BOX_FRAC = 0.02;

function clamp(v, lo, hi) {
  return Math.max(lo, Math.min(hi, v));
}
function fmtTime(s) {
  const t = Math.max(0, s | 0);
  const mm = String(Math.floor(t / 60)).padStart(2, "0");
  const ss = String(t % 60).padStart(2, "0");
  return `${mm}:${ss}`;
}

/** Build a thumb dataURL from a detection box on the given canvas. */
function cropThumb(canvas, bb, targetW = 160) {
  const pad = 0.22;
  const cx = Math.max(0, bb.originX - bb.width * pad);
  const cy = Math.max(0, bb.originY - bb.height * pad);
  const cw = Math.min(canvas.width - cx, bb.width * (1 + pad * 2));
  const ch = Math.min(canvas.height - cy, bb.height * (1 + pad * 2));
  if (cw < 8 || ch < 8) return null;
  const out = document.createElement("canvas");
  out.width = targetW;
  out.height = Math.round(targetW * (ch / cw));
  out.getContext("2d").drawImage(canvas, cx, cy, cw, ch, 0, 0, out.width, out.height);
  return out.toDataURL("image/jpeg", 0.82);
}

/** Sample mean RGB of the upper-torso region. */
function sampleJersey(ctx, bb, w, h) {
  const sx = Math.max(0, Math.floor(bb.originX + bb.width * 0.25));
  const sy = Math.max(0, Math.floor(bb.originY + bb.height * 0.18));
  const sw = Math.max(2, Math.floor(Math.min(w - sx, bb.width * 0.5)));
  const sh = Math.max(2, Math.floor(Math.min(h - sy, bb.height * 0.35)));
  if (sw < 4 || sh < 4) return [128, 128, 128];
  try {
    const data = ctx.getImageData(sx, sy, sw, sh).data;
    let r = 0, g = 0, b = 0, n = 0;
    for (let i = 0; i < data.length; i += 20) {
      r += data[i]; g += data[i + 1]; b += data[i + 2]; n++;
    }
    return n ? [Math.round(r / n), Math.round(g / n), Math.round(b / n)] : [128, 128, 128];
  } catch {
    return [128, 128, 128];
  }
}

export default function ScoutMode({
  open,
  videoUrl,
  duration,                   // initial duration hint (may be 0 — we re-read from videoEl)
  getDetector,                // async () => MediaPipe ObjectDetector
  onConfirm,                  // ({ anchors, sceneCuts }) => void
  onCancel,                   // () => void
}) {
  // Refs
  const videoRef = useRef(null);
  const stageRef = useRef(null);
  const detectorRef = useRef(null);
  const renderCanvasRef = useRef(null);

  // State
  const [vidDur, setVidDur] = useState(duration || 0);
  const [currentTime, setCurrentTime] = useState(0);
  const [videoReady, setVideoReady] = useState(false);
  const [bootProgress, setBootProgress] = useState(0); // 0..1 — scene-detect progress
  const [booting, setBooting] = useState(true);
  const [sceneCuts, setSceneCuts] = useState([]);
  const [hints, setHints] = useState([]);
  const [anchors, setAnchors] = useState([]); // [{ t, box, thumb, jerseyRGB }]
  const [detections, setDetections] = useState([]); // current-frame chip list
  const [detecting, setDetecting] = useState(false);
  const [stageRect, setStageRect] = useState({ w: 0, h: 0 });
  const [showVerify, setShowVerify] = useState(false);
  const [tapFlash, setTapFlash] = useState(null); // detection index that just got tapped (for animation)
  // Timestamps the user has been shown but skipped — we don't surface them again
  const [skipped, setSkipped] = useState([]);
  // Debug overlay — shows ALL raw detections (red boxes) so we can verify the
  // filter logic is actually keeping the right ones. Toggle via the 🐞 pill.
  const [debugMode, setDebugMode] = useState(false);
  const [rawDetections, setRawDetections] = useState([]); // pre-filter detections, for debug
  // Detector status — tells us (and the user) if MediaPipe loaded at all.
  // 'loading' | 'ready' | 'failed'
  const [detectorStatus, setDetectorStatus] = useState("loading");
  // Visible confirmation chip rendered at the EXACT pixel where the user
  // just tapped. Independent of MediaPipe — works even when the detector
  // is silent. { x, y, num } in stage-local screen coords. Cleared ~1.4s later.
  const [tapMarker, setTapMarker] = useState(null);

  // ── Bootstrap: load detector, detect scene cuts, build hints ─────────
  useEffect(() => {
    if (!open) return;
    let aborted = false;
    setBooting(true);
    setBootProgress(0);
    setAnchors([]);
    setDetections([]);
    setShowVerify(false);
    (async () => {
      try {
        // Use our own permissive detector — see getScoutDetector at the top
        // of this file. Falls back to the shared getDetector prop if the
        // dedicated init fails for any reason (e.g. CDN hiccup).
        try {
          detectorRef.current = await getScoutDetector();
          setDetectorStatus("ready");
        } catch (innerErr) {
          console.warn("Scout detector init fallback to shared:", innerErr);
          try {
            detectorRef.current = await getDetector();
            setDetectorStatus("ready");
          } catch (fallbackErr) {
            console.warn("Shared detector init also failed:", fallbackErr);
            detectorRef.current = null;
            setDetectorStatus("failed");
          }
        }
        if (aborted) return;
        const v = videoRef.current;
        if (!v) return;
        // Wait for metadata
        if (v.readyState < 2 || !v.duration) {
          await new Promise((res) => {
            const finish = () => { v.removeEventListener("loadedmetadata", finish); res(); };
            v.addEventListener("loadedmetadata", finish);
            setTimeout(res, 1500);
          });
        }
        if (aborted) return;
        const d = v.duration || duration || 0;
        setVidDur(d);
        const { cuts } = await detectSceneCuts(v, {
          samples: 24,
          onProgress: (p) => setBootProgress(p * 0.85),
        });
        if (aborted) return;
        setSceneCuts(cuts);
        const hs = distributeHints(d, cuts, TARGET_TAPS);
        setHints(hs);
        setBootProgress(1);
        // Jump to the first hint
        if (hs.length) {
          try { v.currentTime = hs[0]; } catch { /* noop */ }
        }
      } catch (err) {
        console.warn("ScoutMode boot failed:", err);
      } finally {
        setBooting(false);
      }
    })();
    return () => { aborted = true; };
  }, [open, getDetector, duration]);

  // Reset on close
  useEffect(() => {
    if (!open) {
      setAnchors([]);
      setDetections([]);
      setRawDetections([]);
      setHints([]);
      setSceneCuts([]);
      setShowVerify(false);
      setBooting(true);
      setBootProgress(0);
      setSkipped([]);
      setTapMarker(null);
      setDetectorStatus("loading");
    }
  }, [open]);

  // ── Observe stage size so chips can be positioned in render coords ──
  //   IMPORTANT: deps must include `open` — on initial mount the component
  //   returns null (open=false), so `stageRef.current` is never attached.
  //   When `open` flips true the JSX renders the stage div, refs are set,
  //   and THIS effect MUST re-run to register the observer. Otherwise
  //   stageRect stays {0,0} forever and the ChipsLayer silently bails.
  //   We also seed the rect synchronously from getBoundingClientRect so
  //   the very first detection has correct screen coords (instead of
  //   waiting for the next paint tick).
  useEffect(() => {
    if (!open) return;
    if (!stageRef.current) return;
    const el = stageRef.current;
    // Seed immediately so chips can render on the FIRST detection.
    const initial = el.getBoundingClientRect();
    setStageRect({ w: initial.width, h: initial.height });
    const ro = new ResizeObserver(() => {
      const r = el.getBoundingClientRect();
      setStageRect({ w: r.width, h: r.height });
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, [open]);

  // ── Wait for the next painted video frame ─────────────────────────
  //   On iOS Safari (and sometimes Android Chrome), the `seeked` event
  //   fires BEFORE the new frame is actually presented to the compositor.
  //   Calling `drawImage(v, 0, 0)` immediately captures the previous frame
  //   (often black, since the video was paused mid-seek). Result: detector
  //   gets a blank canvas and returns 0 detections → no chips above kids.
  //
  //   `requestVideoFrameCallback` is the standard hook that fires right
  //   AFTER each new frame is presented. Fallback: two RAF ticks (one to
  //   schedule + one to wait for paint).
  const waitForFreshFrame = useCallback((videoEl) => {
    return new Promise((resolve) => {
      if (!videoEl) return resolve();
      if (typeof videoEl.requestVideoFrameCallback === "function") {
        let done = false;
        const t = setTimeout(() => { if (!done) { done = true; resolve(); } }, 400);
        videoEl.requestVideoFrameCallback(() => {
          if (!done) { done = true; clearTimeout(t); resolve(); }
        });
      } else {
        requestAnimationFrame(() => requestAnimationFrame(resolve));
      }
    });
  }, []);

  // ── Run MediaPipe on the current frame whenever it stabilises ──────
  const runDetectionOnCurrent = useCallback(async () => {
    const v = videoRef.current;
    const det = detectorRef.current;
    if (!v || !det || v.readyState < 2 || !v.videoWidth) return;
    setDetecting(true);
    try {
      // CRITICAL: wait for the newly-seeked frame to actually paint before
      // capturing it. Skipping this is what causes "AI sees nothing" on iOS.
      await waitForFreshFrame(v);

      let canvas = renderCanvasRef.current;
      if (!canvas) {
        canvas = document.createElement("canvas");
        renderCanvasRef.current = canvas;
      }
      canvas.width = v.videoWidth;
      canvas.height = v.videoHeight;
      const ctx = canvas.getContext("2d", { willReadFrequently: true });
      ctx.drawImage(v, 0, 0);
      const result = det.detect(canvas);
      const allRaw = result?.detections || [];

      // Diagnostic log — helps if user opens Safari Web Inspector
      if (allRaw.length === 0) {
        console.info("[ScoutMode] detector ran but found 0 boxes for t=", v.currentTime);
      } else {
        console.info(`[ScoutMode] detector found ${allRaw.length} raw boxes for t=`, v.currentTime);
      }

      // Keep the raw boxes for the debug overlay (no filtering, no sort).
      setRawDetections(
        allRaw.map((d) => ({
          bbox: d.boundingBox,
          score: d.categories?.[0]?.score ?? 0,
        })),
      );

      // Real player filter — three rules, in this order:
      //   1. Big enough to actually tap (8 × 24 px min in source pixels)
      //   2. Tall-shaped (h ≥ 1.4 × w) — humans are taller than wide,
      //      so this kicks out fences, distant cars, building fragments
      //      that occasionally get misclassified as "person"
      //   3. Not absurdly huge (height < 0.95 of frame) — a single box
      //      covering ~the whole frame is almost always a misfire
      //      (e.g. a sideline parent in foreground covering everything)
      const dets = allRaw
        .filter((d) => {
          const bb = d.boundingBox;
          if (bb.width < 8 || bb.height < 24) return false;
          if (bb.height < 1.4 * bb.width) return false;
          if (bb.height > 0.95 * canvas.height) return false;
          return true;
        })
        // Sort by CONFIDENCE — highest first. This is the key fix: the
        // previous sort-by-area kept buildings/crowd-clusters on top and
        // pushed your kid out of the top-20 slots. The model's score is
        // a much better "is this actually a human" signal.
        .sort(
          (a, b) =>
            (b.categories?.[0]?.score ?? 0) - (a.categories?.[0]?.score ?? 0),
        )
        .slice(0, 20) // full team + GKs + a couple of refs
        .map((d, idx) => ({
          idx,
          bbox: d.boundingBox,
          jerseyRGB: sampleJersey(ctx, d.boundingBox, canvas.width, canvas.height),
          score: d.categories?.[0]?.score ?? 0,
        }));
      setDetections(dets);
    } catch (err) {
      console.warn("ScoutMode detect failed:", err);
    } finally {
      setDetecting(false);
    }
  }, [waitForFreshFrame]);

  // Debounced trigger — wait 250 ms after currentTime stops changing so
  // we don't thrash the detector while the user is dragging the scrubber.
  useEffect(() => {
    if (!open || booting || !videoReady) return;
    const id = setTimeout(() => {
      runDetectionOnCurrent();
    }, 250);
    return () => clearTimeout(id);
  }, [open, booting, videoReady, currentTime, runDetectionOnCurrent]);

  // ── Tap handler — locks a detection as the next anchor ────────────
  const handleChipTap = useCallback((det) => {
    const v = videoRef.current;
    const canvas = renderCanvasRef.current;
    if (!v || !canvas) return;
    if (anchors.length >= TARGET_TAPS) return;

    const bb = det.bbox;
    // Convert detection (video-native coords) to wrapper-normalised box
    const vw = v.videoWidth, vh = v.videoHeight;
    const x = bb.originX / vw;
    const y = bb.originY / vh;
    const w = clamp(bb.width / vw, MIN_BOX_FRAC, 1);
    const h = clamp(bb.height / vh, MIN_BOX_FRAC, 1);
    const thumb = cropThumb(canvas, bb);
    const t = v.currentTime || 0;
    const newAnchor = {
      t,
      box: { x, y, w, h },
      thumb,
      jerseyRGB: det.jerseyRGB,
      // Stamp the segment index based on sceneCuts so backend can group per match
      segment: segmentIndexFor(t, sceneCuts),
    };
    setAnchors((prev) => {
      const out = [...prev, newAnchor];
      // Auto-advance to next un-tapped hint after a beat
      setTapFlash(det.idx);
      setTimeout(() => setTapFlash(null), 900);
      // Also show the BIG tap marker at the centre of the chip
      const stage = stageRef.current;
      if (stage) {
        const r = stage.getBoundingClientRect();
        const sw = r.width, sh = r.height;
        const scale = Math.min(sw / vw, sh / vh);
        const renderedW = vw * scale, renderedH = vh * scale;
        const offX = (sw - renderedW) / 2, offY = (sh - renderedH) / 2;
        const sx = (bb.originX + bb.width / 2) * scale + offX;
        const sy = (bb.originY + bb.height / 2) * scale + offY;
        setTapMarker({ x: sx, y: sy, num: out.length });
        setTimeout(() => setTapMarker(null), 1400);
      }
      const nextHintT = nextUntappedHint(out, hints);
      if (out.length < TARGET_TAPS && nextHintT != null) {
        setTimeout(() => {
          try { v.currentTime = nextHintT; } catch { /* noop */ }
        }, 900);
      } else if (out.length === TARGET_TAPS) {
        setTimeout(() => setShowVerify(true), 1100);
      }
      return out;
    });
  }, [anchors, hints, sceneCuts]);

  const handleUndo = useCallback(() => {
    setAnchors((prev) => {
      if (!prev.length) return prev;
      const last = prev[prev.length - 1];
      const v = videoRef.current;
      if (v && last) {
        try { v.currentTime = last.t; } catch { /* noop */ }
      }
      return prev.slice(0, -1);
    });
  }, []);

  /* ── Skip-frame handler — my kid isn't here, find another moment.
   *    Picks a fresh timestamp that is NOT close to any current anchor,
   *    hint, or previously-skipped moment. Strategy: find the largest
   *    empty gap in the [1, dur-1] window and seek to its midpoint. */
  const handleSkipFrame = useCallback(() => {
    const v = videoRef.current;
    if (!v || !vidDur || vidDur < 2) return;
    const MIN_GAP = 2.5; // seconds — keep new frames separated from used ones
    const current = v.currentTime || 0;
    // All timestamps we've already shown the user (don't re-show them)
    const used = [...anchors.map((a) => a.t), ...skipped, current].sort((a, b) => a - b);
    // Boundary-stuffed list including 1 and dur-1 as the playable window edges
    const stops = [1, ...used.filter((t) => t > 1 && t < vidDur - 1), vidDur - 1].sort((a, b) => a - b);
    // Find the largest gap between consecutive stops
    let bestMid = null;
    let bestGap = 0;
    for (let i = 0; i < stops.length - 1; i++) {
      const gap = stops[i + 1] - stops[i];
      if (gap > bestGap + 0.01) {
        bestGap = gap;
        bestMid = (stops[i] + stops[i + 1]) / 2;
      }
    }
    if (bestMid == null || bestGap < MIN_GAP * 2) {
      // No room left — fall back to a random spot at least MIN_GAP from used
      for (let tries = 0; tries < 20; tries++) {
        const candidate = 1 + Math.random() * Math.max(0.1, vidDur - 2);
        if (used.every((u) => Math.abs(u - candidate) >= MIN_GAP)) {
          bestMid = candidate;
          break;
        }
      }
    }
    if (bestMid == null) {
      bestMid = clamp(current + 5, 1, vidDur - 1);
    }
    // Mark the current frame as skipped so we don't bounce back to it
    setSkipped((prev) => (prev.includes(current) ? prev : [...prev, current]));
    try { v.currentTime = bestMid; } catch { /* noop */ }
  }, [vidDur, anchors, skipped]);

  /* ── Bulletproof fallback: user taps ANYWHERE on the video stage that
   *    is not already a chip. We treat that point as the player's body
   *    center and lock an anchor there. This guarantees a tap path even
   *    when MediaPipe misses small / blurry / occluded players. */
  const handleStageTap = useCallback((e) => {
    if (showVerify || booting) return;
    if (anchors.length >= TARGET_TAPS) return;
    // Skip if the tap originated on a chip — chips have their own onClick
    const targetEl = e.target;
    if (targetEl?.closest?.('[data-testid^="scout-chip-"]')) return;
    if (targetEl?.closest?.('[data-testid="scout-tap-anywhere-hint"]')) return;

    const v = videoRef.current;
    const canvas = renderCanvasRef.current;
    const stage = stageRef.current;
    if (!v || !stage || !v.videoWidth) return;
    // Ensure canvas has the freshest frame
    let workCanvas = canvas;
    if (!workCanvas) {
      workCanvas = document.createElement("canvas");
      renderCanvasRef.current = workCanvas;
    }
    workCanvas.width = v.videoWidth;
    workCanvas.height = v.videoHeight;
    workCanvas.getContext("2d").drawImage(v, 0, 0);

    // Compute tap position in stage-local pixels
    const r = stage.getBoundingClientRect();
    const tx = (e.touches?.[0]?.clientX ?? e.clientX) - r.left;
    const ty = (e.touches?.[0]?.clientY ?? e.clientY) - r.top;
    const sw = r.width, sh = r.height;
    if (tx < 0 || ty < 0 || tx > sw || ty > sh) return;

    // Convert to video-native coords using object-contain mapping
    const vw = v.videoWidth, vh = v.videoHeight;
    const scale = Math.min(sw / vw, sh / vh);
    const renderedW = vw * scale, renderedH = vh * scale;
    const offX = (sw - renderedW) / 2, offY = (sh - renderedH) / 2;
    if (tx < offX || tx > offX + renderedW || ty < offY || ty > offY + renderedH) return;

    const vx = (tx - offX) / scale;
    const vy = (ty - offY) / scale;
    // Default bounding box around the tap point — typical player silhouette
    const bw = Math.min(vw * 0.10, 90);
    const bh = bw * 2.2; // 1:2.2 player aspect
    const bb = {
      originX: clamp(vx - bw / 2, 0, vw - bw),
      // The user usually taps the body/head — extend the box mostly downward
      originY: clamp(vy - bh * 0.30, 0, vh - bh),
      width: bw,
      height: bh,
    };
    const thumb = cropThumb(workCanvas, bb);
    const jerseyRGB = sampleJersey(workCanvas.getContext("2d"), bb, vw, vh);
    const t = v.currentTime || 0;
    const newAnchor = {
      t,
      box: {
        x: bb.originX / vw,
        y: bb.originY / vh,
        w: clamp(bb.width / vw, MIN_BOX_FRAC, 1),
        h: clamp(bb.height / vh, MIN_BOX_FRAC, 1),
      },
      thumb,
      jerseyRGB,
      segment: segmentIndexFor(t, sceneCuts),
      freeform: true,
    };
    setAnchors((prev) => {
      const out = [...prev, newAnchor];
      // INSTANT visual chip at the tap location — independent of MediaPipe.
      // This is the chip the user actually sees confirming their tap landed.
      setTapMarker({ x: tx, y: ty, num: out.length });
      setTimeout(() => setTapMarker(null), 1400);
      const nextHintT = nextUntappedHint(out, hints);
      if (out.length < TARGET_TAPS && nextHintT != null) {
        setTimeout(() => {
          try { v.currentTime = nextHintT; } catch { /* noop */ }
        }, 900);
      } else if (out.length === TARGET_TAPS) {
        setTimeout(() => setShowVerify(true), 1100);
      }
      return out;
    });
  }, [showVerify, booting, anchors.length, hints, sceneCuts]);

  // ── Replace from verification grid → pop the slot, seek there, exit verify ──
  const handleReplaceFromVerify = useCallback((idx) => {
    setAnchors((prev) => {
      const target = prev[idx];
      if (!target) return prev;
      const out = prev.filter((_, i) => i !== idx);
      const v = videoRef.current;
      if (v && target) {
        try { v.currentTime = target.t; } catch { /* noop */ }
      }
      return out;
    });
    setShowVerify(false);
  }, []);

  // ── Submit ───────────────────────────────────────────────────────
  const handleSubmit = useCallback(() => {
    if (anchors.length === 0) return;
    onConfirm?.({ anchors, sceneCuts });
  }, [anchors, onConfirm, sceneCuts]);

  if (!open) return null;

  return createPortal(
    <div
      className="fixed inset-0 z-[230] flex flex-col bg-ink text-white"
      data-testid="scout-mode"
      style={{ touchAction: "none" }}
    >
      {/* ── Top bar ───────────────────────────────────── */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-white/10">
        <button
          type="button"
          onClick={onCancel}
          data-testid="scout-cancel"
          className="w-10 h-10 flex items-center justify-center text-white/85 hover:text-white"
          aria-label="Cancel Scout Mode"
        >
          <X className="w-5 h-5" />
        </button>
        <div className="text-[10px] uppercase tracking-[0.3em] font-black text-[#CCFF00] flex items-center gap-1.5">
          <Sparkles className="w-3 h-3" />
          Scout Mode · 100 % verified
        </div>
        <div className="flex items-center gap-1.5">
          <button
            type="button"
            onClick={() => setDebugMode((v) => !v)}
            data-testid="scout-debug-toggle"
            className={`h-7 px-2 flex items-center justify-center text-[9px] uppercase tracking-widest font-black transition-colors border ${
              debugMode
                ? "border-[#CCFF00] text-[#CCFF00] bg-[#CCFF00]/12"
                : "border-white/25 text-white/55 hover:text-white/85"
            }`}
            aria-label="Toggle detector debug overlay"
            title="Show raw AI detections (debug)"
          >
            🐞 {debugMode ? "ON" : "DBG"}
          </button>
          <button
            type="button"
            onClick={handleUndo}
            disabled={!anchors.length || showVerify}
            data-testid="scout-undo"
            className={`w-10 h-10 flex items-center justify-center transition-colors ${
              anchors.length && !showVerify
                ? "text-white/95 hover:text-[#CCFF00]"
                : "text-white/25"
            }`}
            aria-label="Undo last tap"
            title="Undo last tap"
          >
            <RotateCcw className="w-5 h-5" />
          </button>
          <span className="px-2 h-10 flex items-center text-[12px] uppercase tracking-widest font-black text-white/95 tabular-nums" data-testid="scout-counter">
            {anchors.length} / {TARGET_TAPS}
          </span>
        </div>
      </div>

      {/* ── Video stage with chip overlays ───────────────── */}
      <div
        ref={stageRef}
        className="relative flex-1 bg-black overflow-hidden flex items-center justify-center"
        data-testid="scout-stage"
        onClick={handleStageTap}
        style={{ cursor: !booting && !showVerify && anchors.length < TARGET_TAPS ? "crosshair" : "default" }}
      >
        <video
          ref={videoRef}
          src={videoUrl}
          className="w-full h-full object-contain"
          playsInline
          preload="auto"
          muted
          onLoadedMetadata={(e) => {
            setVideoReady(true);
            setVidDur(e.target.duration || 0);
          }}
          onTimeUpdate={(e) => setCurrentTime(e.target.currentTime)}
          onSeeked={(e) => setCurrentTime(e.target.currentTime)}
        />

        {/* Numbered chips */}
        {!booting && videoReady && !showVerify && detections.length > 0 && stageRect.w > 0 && (
          <ChipsLayer
            detections={detections}
            videoEl={videoRef.current}
            stageRect={stageRect}
            tapFlashIdx={tapFlash}
            onTap={handleChipTap}
          />
        )}

        {/* Debug overlay — raw detector boxes BEFORE filtering. Lets us
            see why the AI is/isn't seeing the players. Toggle via 🐞 pill. */}
        {debugMode && !booting && videoReady && !showVerify && rawDetections.length > 0 && stageRect.w > 0 && (
          <DebugLayer
            rawDetections={rawDetections}
            keptCount={detections.length}
            videoEl={videoRef.current}
            stageRect={stageRect}
          />
        )}

        {/* ── Instant tap confirmation chip — drawn at the exact pixel
              where the user tapped. Independent of MediaPipe. */}
        {tapMarker && (
          <div
            className="absolute pointer-events-none"
            data-testid="scout-tap-marker"
            style={{
              left: tapMarker.x - 36,
              top: Math.max(8, tapMarker.y - 96),
              zIndex: 60,
              animation: "scoutTapPop 1.4s ease-out forwards",
            }}
          >
            <div
              className="w-[72px] h-[72px] flex items-center justify-center font-black text-3xl"
              style={{
                borderRadius: "50%",
                backgroundColor: "#22C55E",
                color: "#0A0F0D",
                border: "4px solid #FFFFFF",
                boxShadow: "0 0 0 3px rgba(0,0,0,0.85), 0 0 40px rgba(34,197,94,0.95)",
              }}
            >
              {tapMarker.num}
            </div>
            <div
              className="text-center mt-1 text-[10px] uppercase tracking-widest font-black text-[#22C55E] bg-ink/90 px-1.5 py-0.5"
              style={{ textShadow: "0 0 4px rgba(0,0,0,0.9)" }}
            >
              Locked
            </div>
          </div>
        )}
        {/* Keyframes for the tap marker pulse */}
        <style>{`
          @keyframes scoutTapPop {
            0%   { transform: scale(0.4); opacity: 0; }
            18%  { transform: scale(1.25); opacity: 1; }
            35%  { transform: scale(1.0); opacity: 1; }
            85%  { transform: scale(1.0); opacity: 1; }
            100% { transform: scale(0.85); opacity: 0; }
          }
        `}</style>

        {/* Booting overlay */}
        {booting && (
          <div className="absolute inset-0 flex flex-col items-center justify-center bg-ink/95 backdrop-blur-md text-white px-6">
            <div className="relative w-20 h-20 mb-4">
              <div className="absolute inset-0 rounded-full border-4 border-[#CCFF00]/15"></div>
              <div
                className="absolute inset-0 rounded-full border-4 border-[#CCFF00] border-t-transparent animate-spin"
                style={{ animationDuration: "1.1s" }}
              />
              <div className="absolute inset-0 flex items-center justify-center text-[#CCFF00] font-black text-base tabular-nums">
                {Math.round(bootProgress * 100)}%
              </div>
            </div>
            <div className="text-white font-black text-base mb-1">
              Scanning for match boundaries…
            </div>
            <div className="text-white/70 text-xs text-center max-w-xs">
              Detecting scene cuts so your report stays correct across kit changes in highlight reels.
            </div>
          </div>
        )}

        {/* Detecting indicator */}
        {!booting && detecting && (
          <div className="absolute top-3 right-3 flex items-center gap-1.5 bg-ink/85 backdrop-blur text-white text-[10px] uppercase tracking-widest font-bold px-2 py-1" style={{ zIndex: 9 }}>
            <Loader2 className="w-3 h-3 animate-spin text-[#CCFF00]" />
            Scanning frame…
          </div>
        )}

        {/* ── Skip-this-frame floating button (top-right) ── */}
        {!booting && !showVerify && !detecting && anchors.length < TARGET_TAPS && (
          <button
            type="button"
            onClick={(e) => { e.stopPropagation(); handleSkipFrame(); }}
            data-testid="scout-skip-frame"
            className="absolute top-3 right-3 z-10 flex items-center gap-1.5 bg-ink/90 backdrop-blur border border-[#CCFF00] text-[#CCFF00] text-[11px] uppercase tracking-widest font-black px-3 py-2 hover:bg-[#CCFF00] hover:text-ink transition-colors shadow-[0_6px_18px_rgba(0,0,0,0.5)]"
            aria-label="My kid isn't in this frame — find another"
          >
            <RotateCcw className="w-3.5 h-3.5" />
            <span className="hidden sm:inline">Kid not here · find another</span>
            <span className="sm:hidden">Skip frame</span>
          </button>
        )}

        {/* ── BIG centred banner — always shown when waiting for a tap.
              Replaces the two old small hint banners. */}
        {!booting && !showVerify && anchors.length < TARGET_TAPS && (
          <div
            className="absolute left-1/2 -translate-x-1/2 flex flex-col items-center"
            data-testid="scout-tap-anywhere-hint"
            style={{ top: 12, zIndex: 15, pointerEvents: "none" }}
          >
            <div className="flex items-center gap-2 bg-ink/95 backdrop-blur border-2 border-[#CCFF00] px-3 py-1.5 shadow-[0_4px_18px_rgba(0,0,0,0.55)]">
              <Hand className="w-4 h-4 text-[#CCFF00]" />
              <span className="text-[14px] sm:text-[15px] font-black text-[#CCFF00] uppercase tracking-wide leading-none">
                Tap kid #{anchors.length + 1}
              </span>
              <span className="text-[10px] font-bold text-white/70 tabular-nums leading-none ml-1">
                · {TARGET_TAPS - anchors.length} more
              </span>
            </div>
            {/* AI status — tells user honestly how many players the AI sees */}
            <div
              className={`mt-1 text-[10px] uppercase tracking-widest font-black px-2 py-0.5 ${
                detectorStatus === "failed"
                  ? "text-white/65 bg-ink/85"
                  : detecting
                    ? "text-[#CCFF00] bg-ink/85"
                    : detections.length > 0
                      ? "text-[#22C55E] bg-ink/90 border border-[#22C55E]/40"
                      : "text-amber-300 bg-ink/85"
              }`}
              data-testid="scout-ai-status"
            >
              {detectorStatus === "failed"
                ? "AI offline · tap directly"
                : detecting
                  ? "AI scanning frame…"
                  : detections.length > 0
                    ? `AI sees ${detections.length} player${detections.length === 1 ? "" : "s"} · chips above their heads`
                    : "AI sees none here · tap directly or scrub"}
            </div>
          </div>
        )}
      </div>

      {/* ── Timeline strip ───────────────────────────────── */}
      {!showVerify && (
        <TimelineStrip
          duration={vidDur}
          currentTime={currentTime}
          hints={hints}
          anchors={anchors}
          sceneCuts={sceneCuts}
          onSeek={(t) => {
            const v = videoRef.current;
            if (v) {
              try { v.currentTime = t; } catch { /* noop */ }
            }
          }}
        />
      )}

      {/* ── Footer — submit when 10 reached ───────────────── */}
      {!showVerify && anchors.length >= TARGET_TAPS && (
        <div className="border-t border-white/10 px-4 py-3 bg-ink" data-testid="scout-ready-bar">
          <button
            type="button"
            onClick={() => setShowVerify(true)}
            data-testid="scout-open-verify"
            className="w-full h-12 flex items-center justify-center gap-2 bg-[#CCFF00] text-ink font-black text-[13px] uppercase tracking-widest shadow-[0_0_22px_rgba(204,255,0,0.45)] hover:bg-[#CCFF00]/90"
          >
            <Check className="w-5 h-5" />
            Review {TARGET_TAPS} taps → confirm
          </button>
        </div>
      )}

      {/* ── Verification grid (Scout v3.1 step 3) ────────── */}
      {showVerify && (
        <VerificationGrid
          anchors={anchors}
          sceneCuts={sceneCuts}
          onReplace={handleReplaceFromVerify}
          onBack={() => setShowVerify(false)}
          onSubmit={handleSubmit}
        />
      )}
    </div>,
    document.body,
  );
}

// ── Helpers used by component body ────────────────────────────────────

function nextUntappedHint(currentAnchors, hints) {
  const usedTimes = new Set(currentAnchors.map((a) => Math.round(a.t * 100) / 100));
  for (const h of hints) {
    if (!usedTimes.has(Math.round(h * 100) / 100)) {
      // Also require it's not within 0.6s of any anchor
      if (currentAnchors.every((a) => Math.abs(a.t - h) > 0.6)) return h;
    }
  }
  return null;
}

function segmentIndexFor(t, cuts) {
  let idx = 0;
  for (const c of cuts) {
    if (t < c) return idx;
    idx += 1;
  }
  return idx;
}

// ── ChipsLayer — numbered chip floating above each player's head ─────
//
// Designed to be BULLETPROOF on iOS Safari:
//   • Plain <div> elements only (no nested button-in-button or transforms
//     that can fail to render inside React portals on iOS).
//   • Each detected player gets a thin lime outline rectangle so the user
//     can SEE which players the AI thinks are real, plus a big numbered
//     chip just above the box.
//   • Inline styles only — no Tailwind classes that could be overridden
//     by parent stacking contexts.
//   • All elements at zIndex 50 (well above the banner + skip button).

function ChipsLayer({ detections, videoEl, stageRect, tapFlashIdx, onTap }) {
  if (!videoEl || !stageRect.w) return null;
  const vw = videoEl.videoWidth || 1;
  const vh = videoEl.videoHeight || 1;
  const sw = stageRect.w, sh = stageRect.h;
  // object-contain mapping (matches the <video> element)
  const scale = Math.min(sw / vw, sh / vh);
  const renderedW = vw * scale, renderedH = vh * scale;
  const offX = (sw - renderedW) / 2, offY = (sh - renderedH) / 2;

  const CHIP = 52; // chip diameter
  const TAP = 64;  // larger tap target for finger
  const TOP_GUARD = 56; // banner + status pill vertical extent
  const FOOTER_GUARD = 20;

  return (
    <div
      data-testid="scout-chips-layer"
      style={{
        position: "absolute",
        left: 0,
        top: 0,
        right: 0,
        bottom: 0,
        pointerEvents: "none",
        zIndex: 50,
      }}
    >
      {detections.map((d, i) => {
        const bb = d.bbox;
        const num = i + 1;
        const flashing = tapFlashIdx === d.idx;
        const accent = flashing ? "#22C55E" : "#CCFF00";

        // Screen-space rectangle for the player's bounding box
        const boxX = bb.originX * scale + offX;
        const boxY = bb.originY * scale + offY;
        const boxW = bb.width * scale;
        const boxH = bb.height * scale;

        // Chip placement — ABOVE the head by default, BELOW the feet if
        // it would land in the banner zone at the top.
        const cxRaw = boxX + boxW / 2;
        const cx = Math.max(TAP / 2 + 4, Math.min(sw - TAP / 2 - 4, cxRaw));
        const chipAboveY = boxY - CHIP - 10;
        const chipBelowY = Math.min(sh - CHIP - FOOTER_GUARD, boxY + boxH + 10);
        const useBelow = chipAboveY < TOP_GUARD;
        const cy = useBelow ? chipBelowY : chipAboveY;

        return (
          <div key={`player-${i}`} style={{ pointerEvents: "none" }}>
            {/* 1. Thin OUTLINE BOX around the player's body — proves to the
                  user that the AI sees this specific kid, not a building. */}
            <div
              style={{
                position: "absolute",
                left: boxX,
                top: boxY,
                width: boxW,
                height: boxH,
                border: `2px solid ${accent}`,
                borderRadius: 4,
                boxShadow: `0 0 0 1px rgba(0,0,0,0.65), 0 0 10px ${accent}55`,
                background: flashing ? `${accent}25` : "transparent",
                pointerEvents: "none",
              }}
            />

            {/* 2. Tap target — large invisible button covering chip+box so
                  the user has a generous hit area on small phones. */}
            <button
              type="button"
              data-testid={`scout-chip-${num}`}
              onClick={(e) => {
                e.preventDefault();
                e.stopPropagation();
                onTap(d);
              }}
              aria-label={`Tap to lock player number ${num}`}
              style={{
                position: "absolute",
                left: cx - TAP / 2,
                top: cy - (TAP - CHIP) / 2,
                width: TAP,
                height: TAP,
                padding: 0,
                margin: 0,
                background: "transparent",
                border: "none",
                outline: "none",
                cursor: "pointer",
                pointerEvents: "auto",
                WebkitTapHighlightColor: "transparent",
              }}
            />

            {/* 3. The visible CHIP itself — drawn as a plain absolutely-
                  positioned div (no nested transforms, no animations) so
                  iOS Safari renders it reliably. */}
            <div
              style={{
                position: "absolute",
                left: cx - CHIP / 2,
                top: cy,
                width: CHIP,
                height: CHIP,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                borderRadius: "50%",
                background: flashing ? "#22C55E" : "#0A0F0D",
                color: flashing ? "#0A0F0D" : "#CCFF00",
                border: `3px solid ${accent}`,
                fontWeight: 900,
                fontSize: 22,
                lineHeight: 1,
                fontFamily: "-apple-system, system-ui, sans-serif",
                boxShadow: flashing
                  ? `0 0 24px ${accent}, 0 0 0 2px #FFFFFF`
                  : `0 0 0 2px rgba(0,0,0,0.85), 0 0 18px rgba(204,255,0,0.55)`,
                pointerEvents: "none",
                zIndex: 51,
              }}
            >
              {num}
            </div>

            {/* 4. Connector line from chip → head of the player. Makes
                  it visually obvious which chip belongs to which kid. */}
            <div
              style={{
                position: "absolute",
                left: cx - 1,
                top: useBelow ? boxY + boxH : cy + CHIP,
                width: 2,
                height: useBelow
                  ? Math.max(0, cy - (boxY + boxH))
                  : Math.max(0, boxY - (cy + CHIP)),
                background: accent,
                opacity: 0.85,
                boxShadow: `0 0 4px ${accent}`,
                pointerEvents: "none",
              }}
            />
          </div>
        );
      })}
    </div>
  );
}

/** Small helper kept local — main `clamp` is for fractions, this is for px. */
function clampNum(v, lo, hi) {
  return Math.max(lo, Math.min(hi, v));
}

// ── DebugLayer — visualises raw MediaPipe detections so you can see why
// chips are/aren't appearing. Red boxes = filtered OUT. Lime boxes = kept.
function DebugLayer({ rawDetections, keptCount, videoEl, stageRect }) {
  if (!videoEl || !stageRect.w) return null;
  const vw = videoEl.videoWidth || 1;
  const vh = videoEl.videoHeight || 1;
  const sw = stageRect.w, sh = stageRect.h;
  const scale = Math.min(sw / vw, sh / vh);
  const renderedW = vw * scale, renderedH = vh * scale;
  const offX = (sw - renderedW) / 2, offY = (sh - renderedH) / 2;
  return (
    <div
      className="absolute inset-0 pointer-events-none"
      data-testid="scout-debug-layer"
      style={{ zIndex: 38 }}
    >
      {rawDetections.map((d, i) => {
        const bb = d.bbox;
        const x = bb.originX * scale + offX;
        const y = bb.originY * scale + offY;
        const w = bb.width * scale;
        const h = bb.height * scale;
        const ratio = bb.height / Math.max(1, bb.width);
        const isHuman = ratio >= 1.4 && bb.height >= 24 && bb.width >= 8;
        return (
          <div
            key={`raw-${i}`}
            className="absolute"
            style={{
              left: x,
              top: y,
              width: w,
              height: h,
              border: `2px solid ${isHuman ? "#CCFF00" : "#EF4444"}`,
              boxShadow: "0 0 0 1px rgba(0,0,0,0.6)",
            }}
          >
            <span
              className="absolute -top-3 left-0 text-[8px] font-black tabular-nums px-1 py-0.5"
              style={{
                color: isHuman ? "#0A0F0D" : "#FFFFFF",
                background: isHuman ? "#CCFF00" : "#EF4444",
              }}
            >
              {Math.round((d.score || 0) * 100)}% · {ratio.toFixed(1)}:1
            </span>
          </div>
        );
      })}
      <div
        className="absolute bottom-3 left-3 bg-ink/95 border border-[#CCFF00] text-[10px] font-black px-2 py-1 text-white"
        style={{ letterSpacing: "0.1em" }}
      >
        AI saw {rawDetections.length} · kept {keptCount} (
        <span className="text-[#CCFF00]">lime = kid</span> · <span className="text-red-400">red = rejected</span>)
      </div>
    </div>
  );
}

// ── Timeline strip — scrub + hints + anchors + segment dividers ───────

function TimelineStrip({ duration, currentTime, hints, anchors, sceneCuts, onSeek }) {
  const barRef = useRef(null);
  const handlePoint = useCallback((e) => {
    const bar = barRef.current;
    if (!bar || !duration) return;
    const r = bar.getBoundingClientRect();
    const clientX = e.touches?.[0]?.clientX ?? e.clientX;
    const frac = clamp((clientX - r.left) / r.width, 0, 1);
    onSeek(frac * duration);
  }, [duration, onSeek]);

  return (
    <div className="border-t border-white/10 bg-ink px-3 py-2.5" data-testid="scout-timeline">
      <div className="flex items-center justify-between mb-1.5 text-[10px] uppercase tracking-widest font-bold">
        <span className="text-white/65 tabular-nums">{fmtTime(currentTime)} / {fmtTime(duration)}</span>
        {sceneCuts.length > 0 && (
          <span className="flex items-center gap-1 text-[#CCFF00]">
            <Film className="w-3 h-3" />
            {sceneCuts.length + 1} segment{sceneCuts.length === 0 ? "" : "s"} detected
          </span>
        )}
      </div>
      <div
        ref={barRef}
        className="relative h-10 cursor-pointer select-none"
        onPointerDown={handlePoint}
        onPointerMove={(e) => { if (e.buttons) handlePoint(e); }}
        data-testid="scout-timeline-bar"
      >
        {/* Base track */}
        <div className="absolute top-1/2 left-0 right-0 h-1.5 -translate-y-1/2 bg-white/12" />
        {/* Filled portion based on progress */}
        <div
          className="absolute top-1/2 left-0 h-1.5 -translate-y-1/2 bg-[#CCFF00]/70"
          style={{ width: `${duration ? (anchors.length / TARGET_TAPS) * 100 : 0}%` }}
        />
        {/* Scene-cut dividers */}
        {sceneCuts.map((t, i) => (
          <div
            key={`cut-${i}`}
            className="absolute top-0 bottom-0 w-px bg-[#CCFF00]/60"
            style={{ left: `${(t / duration) * 100}%` }}
            title={`Match boundary at ${fmtTime(t)}`}
          >
            <Film
              className="w-3 h-3 text-[#CCFF00] absolute -top-2 left-1/2 -translate-x-1/2"
            />
          </div>
        ))}
        {/* Hint dots */}
        {hints.map((t, i) => {
          const tapped = anchors.some((a) => Math.abs(a.t - t) < 0.5);
          const pos = (t / duration) * 100;
          return (
            <div
              key={`hint-${i}`}
              className="absolute top-1/2 -translate-y-1/2 -translate-x-1/2 pointer-events-none"
              style={{ left: `${pos}%` }}
            >
              <div
                className={`w-3 h-3 rounded-full border-2 ${tapped ? "bg-[#22C55E] border-[#22C55E]" : "bg-ink border-white/55"}`}
              />
            </div>
          );
        })}
        {/* Anchors (taps from user-scrubbed moments not represented by hints get a separate dot) */}
        {anchors.map((a, i) => {
          const isHintAligned = hints.some((h) => Math.abs(h - a.t) < 0.5);
          if (isHintAligned) return null;
          const pos = (a.t / duration) * 100;
          return (
            <div
              key={`anc-${i}`}
              className="absolute top-1/2 -translate-y-1/2 -translate-x-1/2 pointer-events-none"
              style={{ left: `${pos}%` }}
              data-testid={`scout-anchor-marker-${i}`}
            >
              <div className="w-3 h-3 rounded-full bg-[#CCFF00] border-2 border-[#CCFF00]" />
            </div>
          );
        })}
        {/* Current playhead */}
        <div
          className="absolute top-0 bottom-0 w-0.5 bg-white pointer-events-none"
          style={{ left: `${duration ? (currentTime / duration) * 100 : 0}%` }}
        />
      </div>
      <div className="mt-1.5 flex items-center justify-between text-[10px] text-white/55">
        <span>● green = your taps</span>
        <span>○ = suggested moments — tap or scrub freely</span>
      </div>
    </div>
  );
}

// ── Verification grid (final review screen) ────────────────────────────

function VerificationGrid({ anchors, sceneCuts, onReplace, onBack, onSubmit }) {
  const sorted = [...anchors].sort((a, b) => a.t - b.t);
  return (
    <div
      className="absolute inset-0 z-[235] flex flex-col bg-ink text-white"
      style={{ paddingTop: 50 }}
      data-testid="scout-verify-grid"
    >
      <div className="px-4 pt-3 pb-3 border-b border-white/10">
        <div className="flex items-center justify-between">
          <button
            type="button"
            onClick={onBack}
            data-testid="scout-verify-back"
            className="w-9 h-9 flex items-center justify-center bg-white/12 hover:bg-white/25 text-white"
          >
            <RotateCcw className="w-4 h-4" />
          </button>
          <div className="flex-1 text-center">
            <div className="text-[10px] uppercase tracking-[0.32em] font-black text-[#CCFF00]">
              Verify your {anchors.length} taps
            </div>
            <div className="text-white font-black text-lg mt-0.5">
              All look like your kid? Press Done.
            </div>
          </div>
          <div className="w-9 h-9" />
        </div>
      </div>
      <div className="flex-1 overflow-y-auto px-3 py-3">
        <div className="grid grid-cols-3 sm:grid-cols-5 gap-2.5" data-testid="scout-verify-grid-cards">
          {sorted.map((a, i) => (
            <div
              key={`verify-${i}`}
              className="relative bg-white/8 border border-white/15 overflow-hidden"
              style={{ minHeight: 130 }}
              data-testid={`scout-verify-${i}`}
            >
              {a.thumb && (
                <img
                  src={a.thumb}
                  alt={`Tap ${i + 1}`}
                  className="absolute inset-0 w-full h-full object-cover"
                />
              )}
              <div className="absolute inset-0 bg-gradient-to-b from-transparent to-black/70 pointer-events-none" />
              <div className="absolute top-1 left-1 flex items-center gap-1">
                <span className="bg-[#CCFF00] text-ink font-black text-[11px] leading-none px-1.5 py-0.5">
                  {i + 1}
                </span>
                <span className="bg-ink/85 text-white text-[9px] tabular-nums px-1 py-0.5">
                  {fmtTime(a.t)}
                </span>
                {a.segment > 0 && (
                  <span className="bg-[#CCFF00]/90 text-ink text-[8px] uppercase tracking-widest font-black px-1 py-0.5">
                    M{a.segment + 1}
                  </span>
                )}
              </div>
              <button
                type="button"
                onClick={() => onReplace(i)}
                data-testid={`scout-verify-replace-${i}`}
                className="absolute bottom-0 left-0 right-0 py-1 text-[9px] uppercase tracking-widest font-black bg-white/15 hover:bg-red-500/60 text-white"
              >
                Replace
              </button>
            </div>
          ))}
        </div>
      </div>
      <div className="border-t border-white/10 px-4 py-3 bg-ink">
        <button
          type="button"
          onClick={onSubmit}
          data-testid="scout-verify-submit"
          className="w-full h-12 flex items-center justify-center gap-2 bg-[#CCFF00] text-ink font-black text-[13px] uppercase tracking-widest shadow-[0_0_22px_rgba(204,255,0,0.45)] hover:bg-[#CCFF00]/90"
        >
          <Check className="w-5 h-5" />
          Done — analyse {anchors.length} verified moment{anchors.length === 1 ? "" : "s"}
        </button>
        <p className="mt-2 text-[10px] text-white/45 text-center">
          {sceneCuts.length > 0
            ? `${sceneCuts.length + 1} match segments detected — backend will use per-segment fingerprints for thumbnail accuracy.`
            : "These 10 verified moments will guide the AI through your video."}
        </p>
      </div>
    </div>
  );
}

ScoutMode.displayName = "ScoutMode";
