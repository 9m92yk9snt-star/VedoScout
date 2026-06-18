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
        detectorRef.current = await getDetector();
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
      setHints([]);
      setSceneCuts([]);
      setShowVerify(false);
      setBooting(true);
      setBootProgress(0);
    }
  }, [open]);

  // ── Observe stage size so chips can be positioned in render coords ──
  useEffect(() => {
    if (!stageRef.current) return;
    const el = stageRef.current;
    const ro = new ResizeObserver(() => {
      const r = el.getBoundingClientRect();
      setStageRect({ w: r.width, h: r.height });
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // ── Run MediaPipe on the current frame whenever it stabilises ──────
  const runDetectionOnCurrent = useCallback(async () => {
    const v = videoRef.current;
    const det = detectorRef.current;
    if (!v || !det || v.readyState < 2 || !v.videoWidth) return;
    setDetecting(true);
    try {
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
      const dets = (result?.detections || [])
        // Loose size floor — phone wide shots typically have players at
        // 30-100 px tall. We accept anything that's roughly the height of
        // a person (2:1 ratio give or take). Detected players that pass
        // this filter still get tappable chips below.
        .filter((d) => d.boundingBox.width >= 10 && d.boundingBox.height >= 20)
        // Largest first — likely closer to camera, easier to tap
        .sort((a, b) => b.boundingBox.width * b.boundingBox.height - a.boundingBox.width * a.boundingBox.height)
        .slice(0, 22) // up to 22 chips so a whole team fits on the field
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
  }, []);

  useEffect(() => {
    if (!open || booting || !videoReady) return;
    runDetectionOnCurrent();
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
      setTimeout(() => setTapFlash(null), 600);
      const nextHintT = nextUntappedHint(out, hints);
      if (out.length < TARGET_TAPS && nextHintT != null) {
        setTimeout(() => {
          try { v.currentTime = nextHintT; } catch { /* noop */ }
        }, 220);
      } else if (out.length === TARGET_TAPS) {
        setTimeout(() => setShowVerify(true), 350);
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
      const nextHintT = nextUntappedHint(out, hints);
      if (out.length < TARGET_TAPS && nextHintT != null) {
        setTimeout(() => {
          try { v.currentTime = nextHintT; } catch { /* noop */ }
        }, 220);
      } else if (out.length === TARGET_TAPS) {
        setTimeout(() => setShowVerify(true), 350);
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
          <div className="absolute top-3 right-3 flex items-center gap-1.5 bg-ink/85 backdrop-blur text-white text-[10px] uppercase tracking-widest font-bold px-2 py-1">
            <Loader2 className="w-3 h-3 animate-spin text-[#CCFF00]" />
            Scanning frame…
          </div>
        )}

        {/* Help banner top of stage — Hint chip when not done */}
        {!booting && !showVerify && anchors.length < TARGET_TAPS && detections.length > 0 && (
          <div
            className="absolute top-3 left-3 flex items-center gap-1.5 bg-ink/90 backdrop-blur text-white text-[11px] font-bold px-2 py-1 max-w-[60%]"
            data-testid="scout-tap-anywhere-hint"
          >
            <Hand className="w-3.5 h-3.5 text-[#CCFF00]" />
            Tap your kid — {TARGET_TAPS - anchors.length} more to go
          </div>
        )}
        {!booting && !showVerify && anchors.length < TARGET_TAPS && detections.length === 0 && !detecting && (
          <div
            className="absolute top-3 left-3 right-3 flex items-center gap-1.5 bg-ink/90 backdrop-blur text-white text-[11px] font-bold px-2 py-1.5"
            data-testid="scout-tap-anywhere-hint"
          >
            <Hand className="w-4 h-4 text-[#CCFF00] flex-shrink-0" />
            <span>
              No numbered boxes here — <span className="text-[#CCFF00]">tap directly on your kid</span> and we&apos;ll lock the anchor at that spot.
            </span>
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

// ── ChipsLayer — overlays a TAPPABLE rectangle on every detection ─────
//
// Each detection becomes a big rectangle covering the whole player. The
// numbered badge sits in the top-left corner. The whole rectangle is the
// tap target — much easier to hit than a small chip floating above the
// head, especially on small wide-shot players. Border colour = the
// player's jersey colour (sampled live) so teammates are visually
// distinguishable at a glance.

function ChipsLayer({ detections, videoEl, stageRect, tapFlashIdx, onTap }) {
  if (!videoEl || !stageRect.w) return null;
  const vw = videoEl.videoWidth || 1;
  const vh = videoEl.videoHeight || 1;
  const sw = stageRect.w, sh = stageRect.h;
  // object-contain mapping
  const scale = Math.min(sw / vw, sh / vh);
  const renderedW = vw * scale, renderedH = vh * scale;
  const offX = (sw - renderedW) / 2, offY = (sh - renderedH) / 2;
  const toScreen = (bb) => ({
    x: bb.originX * scale + offX,
    y: bb.originY * scale + offY,
    w: bb.width * scale,
    h: bb.height * scale,
  });
  // Minimum tap target — even if MediaPipe says the player is 20×40 px,
  // we render at least a 36 × 80 hit area to stay finger-friendly.
  const MIN_W = 36, MIN_H = 80;
  return (
    <div className="absolute inset-0 pointer-events-none" data-testid="scout-chips-layer">
      {detections.map((d, i) => {
        const r = toScreen(d.bbox);
        const w = Math.max(MIN_W, r.w);
        const h = Math.max(MIN_H, r.h);
        const x = r.x + r.w / 2 - w / 2;
        const y = r.y + r.h / 2 - h / 2;
        const num = i + 1;
        const flashing = tapFlashIdx === d.idx;
        const ringColor = `rgb(${d.jerseyRGB[0]}, ${d.jerseyRGB[1]}, ${d.jerseyRGB[2]})`;
        return (
          <button
            key={`chip-${i}`}
            type="button"
            data-testid={`scout-chip-${num}`}
            onClick={(e) => {
              e.preventDefault();
              e.stopPropagation();
              onTap(d);
            }}
            className="pointer-events-auto absolute transition-transform active:scale-95"
            style={{
              left: x,
              top: y,
              width: w,
              height: h,
              border: `2px solid ${flashing ? "#22C55E" : ringColor}`,
              backgroundColor: flashing
                ? "rgba(34, 197, 94, 0.25)"
                : "rgba(204, 255, 0, 0.06)",
              boxShadow: flashing
                ? "0 0 22px rgba(34,197,94,0.65), inset 0 0 18px rgba(34,197,94,0.4)"
                : "0 0 10px rgba(0,0,0,0.45)",
              transform: flashing ? "scale(1.03)" : undefined,
            }}
            aria-label={`Tap player number ${num}`}
          >
            {/* Numbered badge — top-left of the box */}
            <span
              className="absolute -top-2 -left-2 flex items-center justify-center font-black text-[15px]"
              style={{
                width: 30,
                height: 30,
                borderRadius: "50%",
                backgroundColor: flashing ? "#22C55E" : "#0A0F0D",
                color: flashing ? "#0A0F0D" : "#CCFF00",
                border: `2.5px solid ${flashing ? "#22C55E" : "#CCFF00"}`,
                boxShadow: "0 0 10px rgba(0,0,0,0.6)",
              }}
            >
              {num}
            </span>
          </button>
        );
      })}
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
