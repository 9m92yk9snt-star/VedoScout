/**
 * MarkerStudio — premium fullscreen player-marking sheet.
 *
 * Goals (driven by user feedback on mobile):
 *   • The video must be HUGE (fills the screen). Small targets need pixels.
 *   • Zoom is centre-origin and pannable — no off-screen drift.
 *   • Two clear modes via a segmented toggle:
 *       NAVIGATE — single finger pans, pinch zooms.
 *       PLACE BOX — single finger draws / moves / resizes the box.
 *     Pinch zoom works in both modes.
 *   • The box is movable + resizable after it's drawn (8 handles).
 *   • A frame scrubber lives in the bottom toolbar so the user never leaves.
 *   • Optional "Auto-find" runs MediaPipe ObjectDetector on the current frame
 *     and shows tappable dots over every detected person — tap to snap the box.
 *
 * The component is presentation-only — it produces a marker JPG + normalised
 * box + timestamp via onConfirm. The parent (UploadPage) handles upload.
 */

import React, {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { createPortal } from "react-dom";
import {
  Check,
  Move,
  Square,
  Sparkles,
  X,
  ZoomIn,
  ZoomOut,
  ChevronLeft,
  ChevronRight,
  Loader2,
  Play,
  Pause,
} from "lucide-react";
import { toast } from "sonner";

/* ─────────────────────────────────────────────────────────────────────
 * Geometry helpers
 * ─────────────────────────────────────────────────────────────────── */

const MIN_BOX_FRAC = 0.04; // normalised — about 4% of the video edge
const DEFAULT_BOX_FRAC = { w: 0.10, h: 0.22 }; // sensible default tap-box

/**
 * Compute the rendered bounds of the <video> element inside its parent
 * container assuming `object-fit: contain`. Used to map video-native pixels
 * (the ObjectDetector output) into screen pixels.
 */
function renderedVideoBounds(videoEl) {
  if (!videoEl) return { x: 0, y: 0, w: 0, h: 0 };
  const vw = videoEl.videoWidth || 1;
  const vh = videoEl.videoHeight || 1;
  const ew = videoEl.clientWidth;
  const eh = videoEl.clientHeight;
  const videoRatio = vw / vh;
  const elementRatio = ew / eh;
  if (videoRatio > elementRatio) {
    const renderedH = ew / videoRatio;
    return { x: 0, y: (eh - renderedH) / 2, w: ew, h: renderedH };
  }
  const renderedW = eh * videoRatio;
  return { x: (ew - renderedW) / 2, y: 0, w: renderedW, h: eh };
}

function clamp(v, lo, hi) {
  return Math.max(lo, Math.min(hi, v));
}

function formatTime(s) {
  if (!isFinite(s) || s < 0) return "0:00";
  const m = Math.floor(s / 60);
  const r = Math.floor(s % 60);
  return `${m}:${r.toString().padStart(2, "0")}`;
}

/* ─────────────────────────────────────────────────────────────────────
 * Lazy MediaPipe loader. The 5 MB wasm + model only download when the
 * user actually taps Auto-find, so cold page-load stays light.
 * ─────────────────────────────────────────────────────────────────── */

let _detectorPromise = null;

async function getDetector() {
  if (_detectorPromise) return _detectorPromise;
  _detectorPromise = (async () => {
    const { ObjectDetector, FilesetResolver } = await import(
      "@mediapipe/tasks-vision"
    );
    const fileset = await FilesetResolver.forVisionTasks(
      "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.35/wasm",
    );
    return await ObjectDetector.createFromOptions(fileset, {
      baseOptions: {
        modelAssetPath:
          "https://storage.googleapis.com/mediapipe-models/object_detector/efficientdet_lite0/float16/1/efficientdet_lite0.tflite",
      },
      scoreThreshold: 0.35,
      maxResults: 15,
      runningMode: "IMAGE",
      categoryAllowlist: ["person"],
    });
  })();
  return _detectorPromise;
}

/* ─────────────────────────────────────────────────────────────────────
 * Component
 * ─────────────────────────────────────────────────────────────────── */

export default function MarkerStudio({
  open,
  videoUrl,
  videoFile,           // optional File — if provided we create our own blob URL
  initialTimestamp = 0,
  onConfirm,
  onCancel,
}) {
  // Layout
  const wrapperRef = useRef(null);
  const videoRef = useRef(null);
  const [wrapperRect, setWrapperRect] = useState({ w: 0, h: 0 });

  // Independent blob URL so we don't fight the inline preview for the same blob
  const [ownUrl, setOwnUrl] = useState(null);
  useEffect(() => {
    if (!open) return;
    if (videoFile) {
      const u = URL.createObjectURL(videoFile);
      setOwnUrl(u);
      return () => URL.revokeObjectURL(u);
    }
    setOwnUrl(null);
    return undefined;
  }, [open, videoFile]);
  const activeUrl = ownUrl || videoUrl;

  // Modes & transform
  const [mode, setMode] = useState("navigate"); // 'navigate' | 'box'
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const MAX_ZOOM = 5;

  // Box — normalised 0..1 of the wrapper rect
  const [box, setBox] = useState(null); // {x,y,w,h}

  // Multi-anchor strip — confirmed anchors from previous "Lock"s. Each entry is
  // {t: seconds, box: {x,y,w,h}, thumbDataUrl: string}. The current `box` becomes
  // anchor N once the user taps "Add". The final "Done" submits anchors + box-of-first.
  const [anchors, setAnchors] = useState([]);
  const MAX_ANCHORS = 5;
  const [autoSuggesting, setAutoSuggesting] = useState(false);
  const [autoSuggestError, setAutoSuggestError] = useState("");

  // Auto-find detections (normalised 0..1 of wrapper rect, in dimmed-video coords)
  const [detections, setDetections] = useState([]);
  const [detecting, setDetecting] = useState(false);
  const [detectError, setDetectError] = useState("");

  // Video playback
  const [playing, setPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(initialTimestamp || 0);
  const [duration, setDuration] = useState(0);
  const [videoReady, setVideoReady] = useState(false);

  /* ── Lifecycle: mount/unmount, body scroll lock ──────────────── */
  useEffect(() => {
    if (!open) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = prev;
    };
  }, [open]);

  /* ── Reset transient state every time we re-open ─────────────── */
  useEffect(() => {
    if (open) {
      setMode("navigate");
      setZoom(1);
      setPan({ x: 0, y: 0 });
      setBox(null);
      setDetections([]);
      setDetectError("");
      setPlaying(false);
      setVideoReady(false);
      setAnchors([]);
      setAutoSuggesting(false);
      setAutoSuggestError("");
    }
  }, [open]);

  /* ── Measure wrapper after layout ───────────────────────────── */
  useLayoutEffect(() => {
    if (!open) return;
    const el = wrapperRef.current;
    if (!el) return;
    const measure = () =>
      setWrapperRect({ w: el.clientWidth, h: el.clientHeight });
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, [open]);

  /* ── Seek video to initial timestamp on first ready ──────────── */
  useEffect(() => {
    if (!open) return;
    const v = videoRef.current;
    if (!v) return;
    const tryReady = () => {
      if (v.readyState >= 1 && v.videoWidth > 0) {
        try {
          v.currentTime = Math.max(0, Math.min(v.duration || 0, initialTimestamp || 0));
          setDuration(v.duration || 0);
          setVideoReady(true);
        } catch {/* ignore */}
      }
    };
    tryReady(); // sync check — covers the case where metadata loaded BEFORE this effect ran
    v.addEventListener("loadedmetadata", tryReady);
    v.addEventListener("loadeddata", tryReady);
    return () => {
      v.removeEventListener("loadedmetadata", tryReady);
      v.removeEventListener("loadeddata", tryReady);
    };
  }, [open, initialTimestamp, activeUrl]);

  /* ── Track current time ─────────────────────────────────────── */
  useEffect(() => {
    if (!open) return;
    const v = videoRef.current;
    if (!v) return;
    const onTime = () => setCurrentTime(v.currentTime || 0);
    const onPlay = () => setPlaying(true);
    const onPause = () => setPlaying(false);
    v.addEventListener("timeupdate", onTime);
    v.addEventListener("play", onPlay);
    v.addEventListener("pause", onPause);
    return () => {
      v.removeEventListener("timeupdate", onTime);
      v.removeEventListener("play", onPlay);
      v.removeEventListener("pause", onPause);
    };
  }, [open, activeUrl]);

  /* ── Transform helpers ──────────────────────────────────────── */

  /** Convert a wrapper-relative screen point to video-coord normalised 0..1.
   *  Accounts for current zoom + pan (centre origin). */
  const screenToNorm = useCallback(
    (sx, sy) => {
      const { w, h } = wrapperRect;
      if (!w || !h) return { x: 0, y: 0 };
      const cx = w / 2;
      const cy = h / 2;
      const vx = (sx - cx - pan.x) / zoom + cx;
      const vy = (sy - cy - pan.y) / zoom + cy;
      return { x: clamp(vx / w, 0, 1), y: clamp(vy / h, 0, 1) };
    },
    [wrapperRect, zoom, pan],
  );

  /** Convert normalised 0..1 video coord into wrapper-pixel coord
   *  AFTER current transform. Used to render handles at the correct
   *  on-screen position (since the box overlay lives inside the
   *  zoomed/panned layer, this is just nx*w / ny*h). */
  const normToVideoPx = useCallback(
    (nx, ny) => ({ x: nx * wrapperRect.w, y: ny * wrapperRect.h }),
    [wrapperRect],
  );

  /* ── Gesture state ──────────────────────────────────────────── */
  const gestureRef = useRef(null);

  /** Returns wrapper-relative {x,y} for any pointer/touch event */
  const eventPoint = (e, idx = 0) => {
    const rect = wrapperRef.current?.getBoundingClientRect();
    if (!rect) return { x: 0, y: 0 };
    if (e.touches && e.touches[idx]) {
      return { x: e.touches[idx].clientX - rect.left, y: e.touches[idx].clientY - rect.top };
    }
    return { x: (e.clientX || 0) - rect.left, y: (e.clientY || 0) - rect.top };
  };

  /** Pinch-zoom adjusts pan so the midpoint between fingers stays anchored. */
  const applyPinch = (startZ, startPan, startDist, currentDist, midPx) => {
    const ratio = currentDist / startDist;
    const nz = clamp(startZ * ratio, 1, MAX_ZOOM);
    const cx = wrapperRect.w / 2;
    const cy = wrapperRect.h / 2;
    const npx = midPx.x - cx - (midPx.x - cx - startPan.x) * (nz / startZ);
    const npy = midPx.y - cy - (midPx.y - cy - startPan.y) * (nz / startZ);
    return { z: nz, pan: { x: npx, y: npy } };
  };

  /** Hit-test handles inside the existing box. Returns 'tl'|'tr'|'bl'|'br'|null */
  const hitHandle = (p, currentBox) => {
    if (!currentBox) return null;
    // Convert handle screen coords accounting for zoom (handles render
    // inside the zoomed layer at fixed video-pixel size, so on-screen size
    // grows with zoom — use a forgiving hit radius of 28px screen).
    const hitR = 28;
    const c = (nx, ny) => {
      // Convert norm to screen px (account for transform)
      const cx = wrapperRect.w / 2;
      const cy = wrapperRect.h / 2;
      const vx = nx * wrapperRect.w;
      const vy = ny * wrapperRect.h;
      return { x: (vx - cx) * zoom + cx + pan.x, y: (vy - cy) * zoom + cy + pan.y };
    };
    const corners = [
      ["tl", currentBox.x, currentBox.y],
      ["tr", currentBox.x + currentBox.w, currentBox.y],
      ["bl", currentBox.x, currentBox.y + currentBox.h],
      ["br", currentBox.x + currentBox.w, currentBox.y + currentBox.h],
    ];
    for (const [k, nx, ny] of corners) {
      const cs = c(nx, ny);
      if (Math.hypot(p.x - cs.x, p.y - cs.y) < hitR) return k;
    }
    return null;
  };

  /** Is the point inside the box body (not on a handle)? */
  const insideBox = (p, currentBox) => {
    if (!currentBox) return false;
    const n = screenToNorm(p.x, p.y);
    return (
      n.x >= currentBox.x &&
      n.x <= currentBox.x + currentBox.w &&
      n.y >= currentBox.y &&
      n.y <= currentBox.y + currentBox.h
    );
  };

  /* ── Gesture handlers (touch + mouse via pointer events) ────── */

  const onCanvasPointerDown = (e) => {
    // Two-finger pinch always wins — handled by touchstart below.
    if (e.touches && e.touches.length === 2) return;

    const p = eventPoint(e);
    e.preventDefault?.();

    if (mode === "navigate") {
      // Single-finger pan
      gestureRef.current = {
        type: "pan",
        startPan: pan,
        startPoint: p,
      };
      try { e.currentTarget.setPointerCapture?.(e.pointerId); } catch {/* ignore */}
      return;
    }

    // mode === 'box'
    const handle = hitHandle(p, box);
    if (handle) {
      gestureRef.current = {
        type: "resize",
        handle,
        startBox: { ...box },
        startNorm: screenToNorm(p.x, p.y),
      };
      try { e.currentTarget.setPointerCapture?.(e.pointerId); } catch {/* ignore */}
      return;
    }
    if (insideBox(p, box)) {
      gestureRef.current = {
        type: "move",
        startBox: { ...box },
        startNorm: screenToNorm(p.x, p.y),
      };
      try { e.currentTarget.setPointerCapture?.(e.pointerId); } catch {/* ignore */}
      return;
    }
    // Draw a new box from scratch
    const startN = screenToNorm(p.x, p.y);
    gestureRef.current = {
      type: "draw",
      startNorm: startN,
    };
    setBox({ x: startN.x, y: startN.y, w: 0, h: 0 });
    setDetections([]); // any auto-find dots are stale now
    try { e.currentTarget.setPointerCapture?.(e.pointerId); } catch {/* ignore */}
  };

  const onCanvasPointerMove = (e) => {
    if (!gestureRef.current) return;
    if (e.touches && e.touches.length >= 2) return; // pinch handles itself
    const p = eventPoint(e);
    e.preventDefault?.();

    const g = gestureRef.current;
    if (g.type === "pan") {
      setPan({ x: g.startPan.x + (p.x - g.startPoint.x), y: g.startPan.y + (p.y - g.startPoint.y) });
      return;
    }
    if (g.type === "draw") {
      const cur = screenToNorm(p.x, p.y);
      const x = Math.min(g.startNorm.x, cur.x);
      const y = Math.min(g.startNorm.y, cur.y);
      const w = Math.abs(cur.x - g.startNorm.x);
      const h = Math.abs(cur.y - g.startNorm.y);
      setBox({ x, y, w, h });
      return;
    }
    if (g.type === "move") {
      const cur = screenToNorm(p.x, p.y);
      const dx = cur.x - g.startNorm.x;
      const dy = cur.y - g.startNorm.y;
      let nx = g.startBox.x + dx;
      let ny = g.startBox.y + dy;
      nx = clamp(nx, 0, 1 - g.startBox.w);
      ny = clamp(ny, 0, 1 - g.startBox.h);
      setBox({ x: nx, y: ny, w: g.startBox.w, h: g.startBox.h });
      return;
    }
    if (g.type === "resize") {
      const cur = screenToNorm(p.x, p.y);
      const dx = cur.x - g.startNorm.x;
      const dy = cur.y - g.startNorm.y;
      let { x, y, w, h } = g.startBox;
      switch (g.handle) {
        case "tl":
          x = clamp(x + dx, 0, x + w - MIN_BOX_FRAC);
          y = clamp(y + dy, 0, y + h - MIN_BOX_FRAC);
          w = g.startBox.x + g.startBox.w - x;
          h = g.startBox.y + g.startBox.h - y;
          break;
        case "tr":
          y = clamp(y + dy, 0, y + h - MIN_BOX_FRAC);
          w = clamp(g.startBox.w + dx, MIN_BOX_FRAC, 1 - x);
          h = g.startBox.y + g.startBox.h - y;
          break;
        case "bl":
          x = clamp(x + dx, 0, x + w - MIN_BOX_FRAC);
          w = g.startBox.x + g.startBox.w - x;
          h = clamp(g.startBox.h + dy, MIN_BOX_FRAC, 1 - y);
          break;
        case "br":
          w = clamp(g.startBox.w + dx, MIN_BOX_FRAC, 1 - x);
          h = clamp(g.startBox.h + dy, MIN_BOX_FRAC, 1 - y);
          break;
        default:
          break;
      }
      setBox({ x, y, w, h });
    }
  };

  const onCanvasPointerUp = (e) => {
    const g = gestureRef.current;
    gestureRef.current = null;
    try { e.currentTarget.releasePointerCapture?.(e.pointerId); } catch {/* ignore */}
    if (!g) return;

    // If draw produced a tiny box (user just tapped), snap to a default size
    if (g.type === "draw" && box) {
      const tooSmall = box.w < MIN_BOX_FRAC || box.h < MIN_BOX_FRAC;
      if (tooSmall) {
        const cx = g.startNorm.x;
        const cy = g.startNorm.y;
        const w = DEFAULT_BOX_FRAC.w;
        const h = DEFAULT_BOX_FRAC.h;
        setBox({
          x: clamp(cx - w / 2, 0, 1 - w),
          y: clamp(cy - h / 2, 0, 1 - h),
          w,
          h,
        });
      }
    }
  };

  /* ── Two-finger pinch (touch only) ──────────────────────────── */
  const onCanvasTouchStart = (e) => {
    if (e.touches.length === 2) {
      const t1 = e.touches[0];
      const t2 = e.touches[1];
      const rect = wrapperRef.current.getBoundingClientRect();
      const midPx = {
        x: (t1.clientX + t2.clientX) / 2 - rect.left,
        y: (t1.clientY + t2.clientY) / 2 - rect.top,
      };
      const dist = Math.hypot(t1.clientX - t2.clientX, t1.clientY - t2.clientY);
      gestureRef.current = {
        type: "pinch",
        startDist: dist,
        startZoom: zoom,
        startPan: pan,
        startMid: midPx,
      };
    }
  };
  const onCanvasTouchMove = (e) => {
    const g = gestureRef.current;
    if (g?.type === "pinch" && e.touches.length === 2) {
      e.preventDefault();
      const t1 = e.touches[0];
      const t2 = e.touches[1];
      const rect = wrapperRef.current.getBoundingClientRect();
      const midPx = {
        x: (t1.clientX + t2.clientX) / 2 - rect.left,
        y: (t1.clientY + t2.clientY) / 2 - rect.top,
      };
      const dist = Math.hypot(t1.clientX - t2.clientX, t1.clientY - t2.clientY);
      const { z, pan: np } = applyPinch(g.startZoom, g.startPan, g.startDist, dist, midPx);
      setZoom(z);
      setPan(np);
    }
  };
  const onCanvasTouchEnd = () => {
    if (gestureRef.current?.type === "pinch") gestureRef.current = null;
  };

  /* ── Zoom buttons / slider ──────────────────────────────────── */
  const stepZoom = (delta) => {
    setZoom((z) => clamp(z + delta, 1, MAX_ZOOM));
    if (zoom + delta <= 1.01) setPan({ x: 0, y: 0 });
  };

  /* ── Frame ±1 ────────────────────────────────────────────── */
  const stepFrame = (delta) => {
    const v = videoRef.current;
    if (!v) return;
    v.pause();
    const fps = 25;
    v.currentTime = clamp((v.currentTime || 0) + delta / fps, 0, v.duration || 0);
  };

  const togglePlay = () => {
    const v = videoRef.current;
    if (!v) return;
    if (v.paused) v.play().catch(() => {});
    else v.pause();
  };

  /* ── Auto-find (MediaPipe ObjectDetector) ───────────────────── */
  const runAutoFind = async () => {
    const v = videoRef.current;
    if (!v) return;
    if (v.readyState < 2) {
      toast.info("Video still loading — try again in a second.");
      return;
    }
    v.pause();
    setDetecting(true);
    setDetectError("");
    setDetections([]);
    try {
      const det = await getDetector();
      const canvas = document.createElement("canvas");
      canvas.width = v.videoWidth;
      canvas.height = v.videoHeight;
      const ctx = canvas.getContext("2d");
      ctx.drawImage(v, 0, 0, canvas.width, canvas.height);
      const result = det.detect(canvas);
      if (!result?.detections?.length) {
        setDetectError("No players detected in this frame. Try a clearer moment, then tap Auto-find again.");
        return;
      }
      // Normalise detections to 0..1 of the rendered wrapper rect, accounting
      // for letterboxing (object-fit: contain).
      const bounds = renderedVideoBounds(v);
      const wrapperW = wrapperRect.w || 1;
      const wrapperH = wrapperRect.h || 1;
      const normd = result.detections.map((d) => {
        const bb = d.boundingBox;
        // bb is in canvas (video native) px
        const px = (bb.originX / v.videoWidth) * bounds.w + bounds.x;
        const py = (bb.originY / v.videoHeight) * bounds.h + bounds.y;
        const pw = (bb.width / v.videoWidth) * bounds.w;
        const ph = (bb.height / v.videoHeight) * bounds.h;
        return {
          x: clamp(px / wrapperW, 0, 1),
          y: clamp(py / wrapperH, 0, 1),
          w: clamp(pw / wrapperW, 0, 1),
          h: clamp(ph / wrapperH, 0, 1),
          score: d.categories?.[0]?.score || 0,
        };
      });
      // Sort largest first — closer / more important players surface first
      normd.sort((a, b) => b.w * b.h - a.w * a.h);
      setDetections(normd);
      // Auto-switch to box mode so the next tap picks a detection
      setMode("box");
    } catch (err) {
      console.error("Auto-find error", err);
      setDetectError("Couldn't load the detector. Check your connection and try again.");
    } finally {
      setDetecting(false);
    }
  };

  const pickDetection = (d) => {
    // Slight padding around the detection for safety margin
    const pad = 0.012;
    setBox({
      x: clamp(d.x - pad, 0, 1),
      y: clamp(d.y - pad, 0, 1),
      w: clamp(d.w + pad * 2, MIN_BOX_FRAC, 1),
      h: clamp(d.h + pad * 2, MIN_BOX_FRAC, 1),
    });
    setDetections([]); // dismiss dots once chosen
    toast.success("Player locked. Refine with corner handles or tap Lock above.");
  };

  /* ── Build a tiny thumbnail data-URL from the current frame + box ─ */
  const buildAnchorThumb = useCallback(() => {
    const v = videoRef.current;
    if (!v || !box) return null;
    const w = v.videoWidth;
    const h = v.videoHeight;
    if (!w || !h) return null;
    // Crop a slightly padded region around the box in video native coords
    const bounds = renderedVideoBounds(v);
    const wrapperW = wrapperRect.w || 1;
    const wrapperH = wrapperRect.h || 1;
    const bxPx = box.x * wrapperW;
    const byPx = box.y * wrapperH;
    const bwPx = box.w * wrapperW;
    const bhPx = box.h * wrapperH;
    const nx = clamp((bxPx - bounds.x) / bounds.w, 0, 1);
    const ny = clamp((byPx - bounds.y) / bounds.h, 0, 1);
    const nw = clamp(bwPx / bounds.w, 0.02, 1 - nx);
    const nh = clamp(bhPx / bounds.h, 0.02, 1 - ny);
    // Pad 25% around the box for context
    const pad = 0.25;
    const px = clamp(nx - nw * pad, 0, 1);
    const py = clamp(ny - nh * pad, 0, 1);
    const pw = clamp(nw * (1 + pad * 2), 0.02, 1 - px);
    const ph = clamp(nh * (1 + pad * 2), 0.02, 1 - py);

    const sx = px * w;
    const sy = py * h;
    const sw = pw * w;
    const sh = ph * h;
    const out = document.createElement("canvas");
    const thumbW = 96;
    const thumbH = Math.round(thumbW * (sh / sw));
    out.width = thumbW;
    out.height = thumbH;
    const ctx = out.getContext("2d");
    ctx.drawImage(v, sx, sy, sw, sh, 0, 0, thumbW, thumbH);
    // Volt frame around it
    ctx.strokeStyle = "#CCFF00";
    ctx.lineWidth = 2;
    ctx.strokeRect(1, 1, thumbW - 2, thumbH - 2);
    return out.toDataURL("image/jpeg", 0.7);
  }, [box, wrapperRect]);

  /* ── Add the current box as a new anchor in the strip ─ */
  const addCurrentAsAnchor = () => {
    const v = videoRef.current;
    if (!v || !box) {
      toast.error("Place a box around your player first.");
      return;
    }
    if (anchors.length >= MAX_ANCHORS) {
      toast.info(`Maximum ${MAX_ANCHORS} anchors. Remove one to add another.`);
      return;
    }
    if (v.readyState < 1 || !v.videoWidth) {
      toast.info("Hold on — the video is still loading.");
      return;
    }
    const thumb = buildAnchorThumb();
    const newAnchor = {
      t: v.currentTime || 0,
      box: { ...box },
      thumb,
    };
    setAnchors((prev) => [...prev, newAnchor]);
    setBox(null);
    setMode("navigate");
    toast.success(`Anchor ${anchors.length + 1} locked. ${anchors.length + 1 < 3 ? "Add more for tighter precision." : ""}`);
  };

  const removeAnchor = (idx) => {
    setAnchors((prev) => prev.filter((_, i) => i !== idx));
  };

  /* ── Auto-suggest 5 anchors using MediaPipe + jersey-colour matching ─ */
  const runAutoSuggest = async () => {
    const v = videoRef.current;
    if (!v) return;
    if (v.duration < 2) {
      toast.info("Video too short for multi-anchor suggestion.");
      return;
    }
    if (!anchors.length && !box) {
      toast.error("Place a box on your player first — we need a reference to match against.");
      return;
    }
    setAutoSuggesting(true);
    setAutoSuggestError("");
    try {
      // Reference jersey colour: from the first anchor if any, otherwise from the current box
      let refRGB = null;
      const sampleColor = (b) => {
        const canvas = document.createElement("canvas");
        canvas.width = v.videoWidth;
        canvas.height = v.videoHeight;
        const ctx = canvas.getContext("2d");
        ctx.drawImage(v, 0, 0);
        const bounds = renderedVideoBounds(v);
        const wrapperW = wrapperRect.w || 1;
        const wrapperH = wrapperRect.h || 1;
        const bxPx = b.x * wrapperW;
        const byPx = b.y * wrapperH;
        const bwPx = b.w * wrapperW;
        const bhPx = b.h * wrapperH;
        const nx = (bxPx - bounds.x) / bounds.w;
        const ny = (byPx - bounds.y) / bounds.h;
        const nw = bwPx / bounds.w;
        const nh = bhPx / bounds.h;
        // upper torso ~ middle 60% width, top 18-55% of height
        const sx = Math.max(0, Math.floor((nx + nw * 0.2) * v.videoWidth));
        const sy = Math.max(0, Math.floor((ny + nh * 0.18) * v.videoHeight));
        const sw = Math.floor(nw * v.videoWidth * 0.6);
        const sh = Math.floor(nh * v.videoHeight * 0.37);
        if (sw < 4 || sh < 4) return null;
        const data = ctx.getImageData(sx, sy, sw, sh).data;
        let r = 0, g = 0, bb = 0, n = 0;
        for (let i = 0; i < data.length; i += 16) { // sample sparsely
          r += data[i]; g += data[i + 1]; bb += data[i + 2]; n++;
        }
        return n ? [Math.round(r / n), Math.round(g / n), Math.round(bb / n)] : null;
      };

      if (anchors.length) {
        // Use the first anchor: seek there, grab colour
        const wasPlaying = !v.paused;
        v.pause();
        await new Promise((res) => {
          const onSeeked = () => { v.removeEventListener("seeked", onSeeked); res(); };
          v.addEventListener("seeked", onSeeked);
          try { v.currentTime = anchors[0].t; } catch { res(); }
          setTimeout(res, 800);
        });
        refRGB = sampleColor(anchors[0].box);
        if (wasPlaying) v.play().catch(() => {});
      } else if (box) {
        refRGB = sampleColor(box);
      }
      if (!refRGB) refRGB = [128, 128, 128];

      const det = await getDetector();

      // Sample N=6 candidate timestamps across the video. Avoid the first 1s and last 1s.
      const N = 6;
      const dur = Math.max(1, v.duration - 2);
      const candidates = [];
      for (let i = 0; i < N; i++) {
        candidates.push(1 + (dur * i) / Math.max(1, N - 1));
      }
      // Drop any candidate too close to an existing anchor (within 2s)
      const filtered = candidates.filter((t) => {
        if (anchors.some((a) => Math.abs(a.t - t) < 2.0)) return false;
        return true;
      });

      const colorDist = (a, b) => Math.sqrt((a[0]-b[0])**2 + (a[1]-b[1])**2 + (a[2]-b[2])**2);
      const wrapperW = wrapperRect.w || 1;
      const wrapperH = wrapperRect.h || 1;
      const bounds = renderedVideoBounds(v);
      const newAnchors = [];

      for (const t of filtered) {
        if (anchors.length + newAnchors.length >= MAX_ANCHORS) break;
        // Seek
        await new Promise((res) => {
          const onSeeked = () => { v.removeEventListener("seeked", onSeeked); res(); };
          v.addEventListener("seeked", onSeeked);
          try { v.currentTime = t; } catch { res(); }
          setTimeout(res, 800);
        });
        // Capture frame
        const canvas = document.createElement("canvas");
        canvas.width = v.videoWidth;
        canvas.height = v.videoHeight;
        canvas.getContext("2d").drawImage(v, 0, 0);
        const result = det.detect(canvas);
        if (!result?.detections?.length) continue;

        // For each detection, sample its jersey colour and compare to refRGB
        let best = null;
        for (const d of result.detections) {
          const bb = d.boundingBox;
          const dx = bb.originX + bb.width * 0.25;
          const dy = bb.originY + bb.height * 0.20;
          const dw = bb.width * 0.5;
          const dh = bb.height * 0.35;
          if (dw < 4 || dh < 4) continue;
          try {
            const data = canvas.getContext("2d").getImageData(
              Math.max(0, Math.floor(dx)),
              Math.max(0, Math.floor(dy)),
              Math.min(canvas.width - dx, Math.floor(dw)),
              Math.min(canvas.height - dy, Math.floor(dh)),
            ).data;
            let r = 0, g = 0, bg = 0, n = 0;
            for (let i = 0; i < data.length; i += 16) {
              r += data[i]; g += data[i + 1]; bg += data[i + 2]; n++;
            }
            if (!n) continue;
            const meanRGB = [Math.round(r / n), Math.round(g / n), Math.round(bg / n)];
            const dist = colorDist(meanRGB, refRGB);
            if (!best || dist < best.dist) best = { d, dist };
          } catch { /* ignore */ }
        }
        if (!best || best.dist > 90) continue; // too different from reference
        // Convert detection to normalised wrapper coords
        const bb = best.d.boundingBox;
        const px = (bb.originX / v.videoWidth) * bounds.w + bounds.x;
        const py = (bb.originY / v.videoHeight) * bounds.h + bounds.y;
        const pw = (bb.width / v.videoWidth) * bounds.w;
        const ph = (bb.height / v.videoHeight) * bounds.h;
        const nbox = {
          x: clamp(px / wrapperW, 0, 1),
          y: clamp(py / wrapperH, 0, 1),
          w: clamp(pw / wrapperW, 0.02, 1),
          h: clamp(ph / wrapperH, 0.02, 1),
        };
        // Build thumb (we need to temporarily set state to box-mode-look; just build the canvas)
        const thumbCanvas = document.createElement("canvas");
        const thumbW = 96;
        const thumbH = Math.round(thumbW * (ph / pw));
        thumbCanvas.width = thumbW;
        thumbCanvas.height = thumbH;
        // Crop the detection region with 25% padding
        const padX = pw * 0.25;
        const padY = ph * 0.25;
        const sx = Math.max(0, px - padX) * (canvas.width / wrapperW * (wrapperW / bounds.w));
        // Simpler: crop in canvas-native pixels using detection box directly
        const cx = Math.max(0, bb.originX - bb.width * 0.25);
        const cy = Math.max(0, bb.originY - bb.height * 0.25);
        const cw = Math.min(canvas.width - cx, bb.width * 1.5);
        const ch = Math.min(canvas.height - cy, bb.height * 1.5);
        const tctx = thumbCanvas.getContext("2d");
        tctx.drawImage(canvas, cx, cy, cw, ch, 0, 0, thumbW, thumbH);
        tctx.strokeStyle = "#CCFF00";
        tctx.lineWidth = 2;
        tctx.strokeRect(1, 1, thumbW - 2, thumbH - 2);
        // unused vars to satisfy linter
        void sx; void nbox;
        newAnchors.push({
          t,
          box: nbox,
          thumb: thumbCanvas.toDataURL("image/jpeg", 0.7),
          suggested: true,
        });
      }

      if (!newAnchors.length) {
        setAutoSuggestError("Couldn't find enough matching frames. Add a few anchors manually.");
        return;
      }
      setAnchors((prev) => [...prev, ...newAnchors]);
      toast.success(`Added ${newAnchors.length} AI-suggested anchor${newAnchors.length === 1 ? "" : "s"}.`);
    } catch (err) {
      console.error("Auto-suggest error", err);
      setAutoSuggestError("Auto-suggest failed. Try adding anchors manually.");
    } finally {
      setAutoSuggesting(false);
    }
  };

  /* ── Final Done — submit all anchors plus the marker JPG ───── */
  const handleDone = () => {
    const v = videoRef.current;
    // If a box is still drawn but un-added, add it first
    const pendingBox = box;
    let allAnchors = anchors;
    if (pendingBox && allAnchors.length < MAX_ANCHORS && v && v.videoWidth) {
      const thumb = buildAnchorThumb();
      allAnchors = [
        ...anchors,
        { t: v.currentTime || 0, box: { ...pendingBox }, thumb },
      ];
    }
    if (!allAnchors.length) {
      toast.error("Lock onto your player first.");
      return;
    }
    if (v.readyState < 1 || !v.videoWidth) {
      toast.info("Hold on — the video is still loading.");
      return;
    }

    // Render the FIRST anchor as the marker JPG (uses full-quality video frame).
    const first = allAnchors[0];
    renderMarkerForAnchor(v, first, allAnchors, (blob, finalAnchors) => {
      if (!blob) {
        toast.error("Could not capture the frame — try a different moment.");
        return;
      }
      onConfirm({
        markerBlob: blob,
        markerTimestamp: first.t,
        markerBox: first.box, // legacy single-box field
        markerAnchors: finalAnchors.map((a) => ({ t: a.t, box: a.box })),
      });
    });
  };

  /** Paint the full-res marker JPG for the FIRST anchor. Identical to the old
   *  handleConfirm canvas logic but seeks the video to anchor 1's timestamp first. */
  const renderMarkerForAnchor = (v, anchor, allAnchors, cb) => {
    const finalise = () => {
      const w = v.videoWidth;
      const h = v.videoHeight;
      if (!w || !h) { cb(null, allAnchors); return; }
      const canvas = document.createElement("canvas");
      canvas.width = w;
      canvas.height = h;
      const ctx = canvas.getContext("2d");
      ctx.drawImage(v, 0, 0, w, h);

      const bounds = renderedVideoBounds(v);
      const wrapperW = wrapperRect.w || 1;
      const wrapperH = wrapperRect.h || 1;
      const bxPx = anchor.box.x * wrapperW;
      const byPx = anchor.box.y * wrapperH;
      const bwPx = anchor.box.w * wrapperW;
      const bhPx = anchor.box.h * wrapperH;
      const nx = clamp((bxPx - bounds.x) / bounds.w, 0, 1);
      const ny = clamp((byPx - bounds.y) / bounds.h, 0, 1);
      const nw = clamp(bwPx / bounds.w, MIN_BOX_FRAC, 1 - nx);
      const nh = clamp(bhPx / bounds.h, MIN_BOX_FRAC, 1 - ny);
      const bx = Math.round(nx * w);
      const by = Math.round(ny * h);
      const bw = Math.max(8, Math.round(nw * w));
      const bh = Math.max(8, Math.round(nh * h));

      // Re-emit the same anchor.box in proper rendered-video coords for backend
      const finalAnchors = allAnchors.map((a, idx) => idx === 0 ? { ...a, box: { x: nx, y: ny, w: nw, h: nh } } : a);

      ctx.save();
      ctx.fillStyle = "rgba(5, 10, 15, 0.45)";
      ctx.beginPath();
      ctx.rect(0, 0, w, h);
      ctx.rect(bx, by, bw, bh);
      ctx.closePath();
      ctx.fill("evenodd");
      ctx.restore();
      ctx.save();
      ctx.shadowColor = "#CCFF00";
      ctx.shadowBlur = Math.max(12, Math.min(w, h) * 0.012);
      ctx.strokeStyle = "rgba(204, 255, 0, 0.5)";
      ctx.lineWidth = Math.max(4, Math.min(w, h) * 0.006);
      ctx.strokeRect(bx, by, bw, bh);
      ctx.restore();
      ctx.strokeStyle = "#CCFF00";
      ctx.lineWidth = Math.max(3, Math.min(w, h) * 0.004);
      ctx.strokeRect(bx, by, bw, bh);
      const corner = Math.max(14, Math.min(bw, bh) * 0.18);
      ctx.strokeStyle = "#FFFFFF";
      ctx.lineWidth = Math.max(2, Math.min(w, h) * 0.0035);
      [
        [bx, by, 1, 1],
        [bx + bw, by, -1, 1],
        [bx, by + bh, 1, -1],
        [bx + bw, by + bh, -1, -1],
      ].forEach(([cx, cy, dx, dy]) => {
        ctx.beginPath();
        ctx.moveTo(cx, cy + dy * corner);
        ctx.lineTo(cx, cy);
        ctx.lineTo(cx + dx * corner, cy);
        ctx.stroke();
      });
      const label = `LOCKED · ${allAnchors.length}`;
      ctx.font = `bold ${Math.max(14, w * 0.018)}px Arial`;
      const tw = ctx.measureText(label).width;
      const padX = 10;
      const padY = 5;
      const lh = Math.max(20, w * 0.025);
      const lx = bx;
      const ly = by - lh - 4 < 4 ? by + bh + 4 : by - lh - 4;
      ctx.fillStyle = "#CCFF00";
      ctx.fillRect(lx, ly, tw + padX * 2, lh);
      ctx.fillStyle = "#050A0F";
      ctx.fillText(label, lx + padX, ly + lh - padY - 2);

      canvas.toBlob((blob) => cb(blob, finalAnchors), "image/jpeg", 0.92);
    };
    // Seek to anchor 1's time if not already there
    if (Math.abs(v.currentTime - anchor.t) > 0.1) {
      const onSeeked = () => { v.removeEventListener("seeked", onSeeked); finalise(); };
      v.addEventListener("seeked", onSeeked);
      try { v.currentTime = anchor.t; } catch { finalise(); }
      setTimeout(finalise, 800); // safety fallback
    } else {
      finalise();
    }
  };

  /* ── (legacy) handleConfirm now triggers Done if box drawn + no anchors yet ─ */
  const handleConfirm = () => {
    if (!anchors.length && box) {
      // first anchor — add then immediately submit
      addCurrentAsAnchor();
      // user will then tap "Done — Lock" below
      return;
    }
    handleDone();
  };

  /* ── Derived: transform CSS for the zoom+pan layer ──────────── */
  const transformStyle = useMemo(
    () => ({
      transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoom})`,
      transformOrigin: "50% 50%",
      transition: gestureRef.current ? "none" : "transform 0.18s ease-out", // eslint-disable-line
      willChange: "transform",
    }),
    [pan, zoom],
  );

  const hint = useMemo(() => {
    if (autoSuggesting) return "Scanning the whole video for your player…";
    if (detecting) return "Locating players…";
    if (detections.length && !box) return "Tap the dot on YOUR player";
    if (anchors.length >= 3) return "Strong precision lock · tap ✓ DONE to analyse, or add more anchors";
    if (anchors.length >= 1 && !box) return `Anchor ${anchors.length} set · scrub forward + place another for tighter precision, or tap ✓ DONE`;
    if (mode === "navigate") return "Pan with one finger · Pinch to zoom · Switch to MARK BOX when ready";
    if (!box) return "Drag around your player · Or tap ✨ Suggest 5";
    return "Drag corners to resize · Drag inside to move · Tap + ADD to lock this anchor";
  }, [mode, box, detections.length, detecting, anchors.length, autoSuggesting]);

  if (!open) return null;

  const portalRoot = typeof document !== "undefined" ? document.body : null;
  if (!portalRoot) return null;

  return createPortal(
    <div
      className="fixed inset-0 z-[200] bg-deepnavy text-cream-card flex flex-col"
      data-testid="marker-studio"
      style={{ touchAction: "none" }}
    >
      {/* ── Top bar ───────────────────────────────────── */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-cream-card/10">
        <button
          type="button"
          onClick={onCancel}
          data-testid="ms-cancel"
          className="w-10 h-10 flex items-center justify-center text-cream-card/80 hover:text-cream-card"
          aria-label="Cancel"
        >
          <X className="w-5 h-5" />
        </button>
        <div className="text-[10px] uppercase tracking-[0.3em] font-bold text-volt">
          {anchors.length === 0
            ? "Lock onto your player"
            : `Anchor ${anchors.length} / ${MAX_ANCHORS} locked`}
        </div>
        <div className="flex items-center gap-1.5">
          {/* ADD = lock the current box as a new anchor (stays in studio) */}
          <button
            type="button"
            onClick={addCurrentAsAnchor}
            disabled={!box || !videoReady || anchors.length >= MAX_ANCHORS}
            data-testid="ms-add-anchor"
            className={`px-2.5 h-10 flex items-center gap-1 text-[11px] uppercase tracking-widest font-black transition-colors ${
              box && videoReady && anchors.length < MAX_ANCHORS
                ? "bg-cream-card/15 text-cream-card hover:bg-cream-card/25"
                : "bg-cream-card/5 text-cream-card/30"
            }`}
            aria-label="Add this box as an anchor"
          >
            + Add
          </button>
          {/* DONE = finalise all anchors → submit */}
          <button
            type="button"
            onClick={handleDone}
            disabled={(!box && !anchors.length) || !videoReady}
            data-testid="ms-confirm"
            className={`px-3 h-10 flex items-center gap-1.5 text-[12px] uppercase tracking-widest font-black transition-colors ${
              (anchors.length || box) && videoReady
                ? "bg-volt text-deepnavy hover:bg-volt/90"
                : "bg-cream-card/10 text-cream-card/30"
            }`}
          >
            <Check className="w-4 h-4" />
            {anchors.length || box ? "Done" : "Lock"}
          </button>
        </div>
      </div>

      {/* ── Video stage ─────────────────────────────── */}
      <div
        ref={wrapperRef}
        className="relative flex-1 overflow-hidden bg-black select-none"
        onPointerDown={onCanvasPointerDown}
        onPointerMove={onCanvasPointerMove}
        onPointerUp={onCanvasPointerUp}
        onPointerCancel={onCanvasPointerUp}
        onTouchStart={onCanvasTouchStart}
        onTouchMove={onCanvasTouchMove}
        onTouchEnd={onCanvasTouchEnd}
        style={{ touchAction: "none" }}
      >
        {/* Scaled layer — video + box live here so they zoom/pan together */}
        <div className="absolute inset-0 pointer-events-none" style={transformStyle}>
          <video
            ref={videoRef}
            src={activeUrl}
            playsInline
            preload="metadata"
            className="w-full h-full object-contain bg-black"
            data-testid="ms-video"
          />
          {/* The box overlay (rendered in normalised wrapper coords) */}
          {box && (
            <div
              className="absolute"
              style={{
                left: `${box.x * 100}%`,
                top: `${box.y * 100}%`,
                width: `${box.w * 100}%`,
                height: `${box.h * 100}%`,
                boxShadow:
                  "0 0 0 9999px rgba(5,10,15,0.55), 0 0 22px rgba(204,255,0,0.45) inset, 0 0 28px rgba(204,255,0,0.45)",
                border: "2px solid #CCFF00",
              }}
            >
              {/* corner ticks (visual only — handles are in unscaled overlay below) */}
              {["tl", "tr", "bl", "br"].map((c) => {
                const base = {
                  position: "absolute",
                  width: 12,
                  height: 12,
                  borderColor: "#FFFFFF",
                  borderStyle: "solid",
                };
                const map = {
                  tl: { ...base, top: -1, left: -1, borderWidth: "2px 0 0 2px" },
                  tr: { ...base, top: -1, right: -1, borderWidth: "2px 2px 0 0" },
                  bl: { ...base, bottom: -1, left: -1, borderWidth: "0 0 2px 2px" },
                  br: { ...base, bottom: -1, right: -1, borderWidth: "0 2px 2px 0" },
                };
                return <span key={c} style={map[c]} />;
              })}
            </div>
          )}
        </div>

        {/* Unscaled overlay: big finger-friendly handle hit targets render here
            on top of the scaled box, since CSS scale would shrink them. We
            mirror the box bounds via wrapper-px coords computed from `box`. */}
        {box && (
          <BoxHandlesOverlay
            box={box}
            zoom={zoom}
            pan={pan}
            wrapperRect={wrapperRect}
          />
        )}

        {/* Auto-find dots */}
        {detections.length > 0 && !box && (
          <div className="absolute inset-0 pointer-events-none">
            {detections.map((d, i) => {
              const cx = (d.x + d.w / 2) * wrapperRect.w;
              const cy = (d.y + d.h / 2) * wrapperRect.h;
              const sx = (cx - wrapperRect.w / 2) * zoom + wrapperRect.w / 2 + pan.x;
              const sy = (cy - wrapperRect.h / 2) * zoom + wrapperRect.h / 2 + pan.y;
              return (
                <button
                  key={i}
                  type="button"
                  data-testid={`ms-detection-${i}`}
                  onPointerDown={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    pickDetection(d);
                  }}
                  className="absolute pointer-events-auto rounded-full bg-volt/95 border-2 border-white shadow-[0_0_24px_rgba(204,255,0,0.65)] flex items-center justify-center font-black text-deepnavy text-xs"
                  style={{
                    left: sx - 22,
                    top: sy - 22,
                    width: 44,
                    height: 44,
                    animation: `pulse-soft 1.6s ${i * 0.12}s infinite`,
                  }}
                >
                  {i + 1}
                </button>
              );
            })}
          </div>
        )}

        {/* Detecting overlay */}
        {detecting && (
          <div className="absolute inset-0 flex items-center justify-center bg-deepnavy/60 backdrop-blur-sm pointer-events-none">
            <div className="flex items-center gap-2 text-volt text-[11px] uppercase tracking-widest font-bold">
              <Loader2 className="w-4 h-4 animate-spin" />
              Locating players…
            </div>
          </div>
        )}

        {detectError && !detecting && (
          <div className="absolute top-3 left-3 right-3 bg-deepnavy/90 backdrop-blur border border-red-500/40 text-red-200 text-xs px-3 py-2">
            {detectError}
          </div>
        )}

        {/* Mode chip top-left */}
        <div className="pointer-events-none absolute top-3 left-3 flex items-center gap-1.5 bg-deepnavy/85 backdrop-blur text-cream-card text-[10px] uppercase tracking-widest font-bold px-2 py-1">
          {mode === "navigate" ? <Move className="w-3 h-3" /> : <Square className="w-3 h-3" />}
          {mode === "navigate" ? "Navigate" : "Mark box"}
          {zoom > 1.05 && <span className="text-volt">· {zoom.toFixed(1)}×</span>}
        </div>

        {/* Zoom buttons top-right (always visible, never overlapping content because they're at the edge) */}
        <div className="pointer-events-none absolute top-3 right-3 flex flex-col gap-1">
          <button
            type="button"
            data-testid="ms-zoom-in"
            onPointerDown={(e) => { e.preventDefault(); e.stopPropagation(); stepZoom(0.5); }}
            className="pointer-events-auto w-9 h-9 flex items-center justify-center bg-deepnavy/85 backdrop-blur border border-cream-card/15 text-cream-card hover:text-volt"
            aria-label="Zoom in"
          >
            <ZoomIn className="w-4 h-4" />
          </button>
          <button
            type="button"
            data-testid="ms-zoom-out"
            onPointerDown={(e) => { e.preventDefault(); e.stopPropagation(); stepZoom(-0.5); }}
            className="pointer-events-auto w-9 h-9 flex items-center justify-center bg-deepnavy/85 backdrop-blur border border-cream-card/15 text-cream-card hover:text-volt"
            aria-label="Zoom out"
          >
            <ZoomOut className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* ── Bottom toolbar ─────────────────────────── */}
      <div className="border-t border-cream-card/10 bg-deepnavy">
        {/* Anchor strip */}
        {(anchors.length > 0 || autoSuggesting || autoSuggestError) && (
          <div className="px-3 pt-2 pb-1">
            <div className="flex items-center gap-2 mb-1.5">
              <span className="text-[9px] uppercase tracking-[0.25em] font-bold text-cream-card/55">
                Anchors {anchors.length}/{MAX_ANCHORS}
              </span>
              {anchors.length >= 3 && (
                <span className="text-[9px] uppercase tracking-widest font-bold text-volt">
                  ✓ Strong precision
                </span>
              )}
              {anchors.length > 0 && anchors.length < 3 && (
                <span className="text-[9px] uppercase tracking-widest font-bold text-cream-card/45">
                  Add {3 - anchors.length} more for tight precision
                </span>
              )}
            </div>
            <div className="flex items-center gap-1.5 overflow-x-auto pb-1" data-testid="ms-anchor-strip">
              {anchors.map((a, i) => (
                <div
                  key={i}
                  className="relative flex-shrink-0 group"
                  style={{ width: 48, height: 64 }}
                  data-testid={`ms-anchor-${i}`}
                >
                  <img
                    src={a.thumb}
                    alt={`anchor ${i + 1}`}
                    className="w-full h-full object-cover border border-volt/60"
                  />
                  <span className="absolute top-0 left-0 bg-volt text-deepnavy text-[8px] uppercase tracking-wider font-black px-1 py-px">
                    {i + 1}
                  </span>
                  <span className="absolute bottom-0 right-0 bg-deepnavy/90 text-cream-card/85 text-[8px] tabular-nums px-1">
                    {formatTime(a.t)}
                  </span>
                  <button
                    type="button"
                    onClick={() => removeAnchor(i)}
                    data-testid={`ms-anchor-remove-${i}`}
                    className="absolute -top-1 -right-1 w-4 h-4 bg-red-500/90 text-white text-[10px] leading-none flex items-center justify-center rounded-full"
                    aria-label="Remove anchor"
                  >
                    ×
                  </button>
                </div>
              ))}
              {anchors.length < MAX_ANCHORS && (
                <button
                  type="button"
                  onClick={() => {
                    setBox(null);
                    setMode("box");
                  }}
                  data-testid="ms-anchor-add-btn"
                  className="flex-shrink-0 flex items-center justify-center bg-cream-card/8 hover:bg-cream-card/15 border border-dashed border-cream-card/30 text-cream-card/65 text-[10px] uppercase tracking-widest font-bold"
                  style={{ width: 48, height: 64 }}
                  aria-label="Add another anchor"
                >
                  +
                </button>
              )}
            </div>
            {autoSuggestError && (
              <p className="mt-1 text-[10px] text-red-300/85">{autoSuggestError}</p>
            )}
          </div>
        )}

        {/* Scrubber row */}
        <div className="flex items-center gap-2 px-3 py-2">
          <button
            type="button"
            onClick={togglePlay}
            data-testid="ms-play"
            className="w-9 h-9 flex items-center justify-center bg-cream-card/10 hover:bg-cream-card/20 text-cream-card"
            aria-label={playing ? "Pause" : "Play"}
          >
            {playing ? <Pause className="w-4 h-4" /> : <Play className="w-4 h-4" />}
          </button>
          <input
            type="range"
            min={0}
            max={duration || 0}
            step="0.05"
            value={currentTime}
            onChange={(e) => {
              const v = videoRef.current;
              if (v) v.currentTime = parseFloat(e.target.value);
            }}
            className="flex-1 h-1 accent-volt"
            data-testid="ms-scrub"
          />
          <div className="text-[10px] uppercase tracking-widest font-bold text-cream-card/60 tabular-nums min-w-[80px] text-right">
            {formatTime(currentTime)} / {formatTime(duration)}
          </div>
          <div className="flex">
            <button type="button" data-testid="ms-frame-back" onClick={() => stepFrame(-1)}
              className="w-9 h-9 flex items-center justify-center bg-cream-card/10 hover:bg-cream-card/20 text-cream-card">
              <ChevronLeft className="w-4 h-4" />
            </button>
            <button type="button" data-testid="ms-frame-fwd" onClick={() => stepFrame(1)}
              className="w-9 h-9 flex items-center justify-center bg-cream-card/10 hover:bg-cream-card/20 text-cream-card">
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Mode toggle + Auto-find */}
        <div className="flex items-center gap-2 px-3 pb-2">
          <div className="flex flex-1 border border-cream-card/15 overflow-hidden" data-testid="ms-mode-toggle">
            <button
              type="button"
              data-testid="ms-mode-navigate"
              onClick={() => setMode("navigate")}
              className={`flex-1 flex items-center justify-center gap-1.5 px-3 py-2 text-[11px] uppercase tracking-widest font-bold transition-colors ${
                mode === "navigate" ? "bg-volt text-deepnavy" : "bg-transparent text-cream-card/75"
              }`}
            >
              <Move className="w-3.5 h-3.5" /> Navigate
            </button>
            <button
              type="button"
              data-testid="ms-mode-box"
              onClick={() => setMode("box")}
              className={`flex-1 flex items-center justify-center gap-1.5 px-3 py-2 text-[11px] uppercase tracking-widest font-bold transition-colors ${
                mode === "box" ? "bg-volt text-deepnavy" : "bg-transparent text-cream-card/75"
              }`}
            >
              <Square className="w-3.5 h-3.5" /> Mark box
            </button>
          </div>
          <button
            type="button"
            data-testid="ms-autofind"
            onClick={runAutoSuggest}
            disabled={autoSuggesting || (!anchors.length && !box) || anchors.length >= MAX_ANCHORS}
            className="px-3 py-2 flex items-center gap-1.5 bg-volt/15 border border-volt/40 text-volt text-[11px] uppercase tracking-widest font-bold hover:bg-volt/25 disabled:opacity-50"
            title="AI scans the video and suggests up to 5 anchors matching your locked player"
          >
            {autoSuggesting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Sparkles className="w-3.5 h-3.5" />}
            ✨ Suggest 5
          </button>
        </div>

        {/* Hint row */}
        <div className="px-3 pb-3 text-[11px] text-cream-card/65 text-center">
          {hint}
        </div>
      </div>

      {/* Local keyframes */}
      <style>{`
        @keyframes pulse-soft {
          0%,100% { transform: scale(1); opacity: 1; }
          50% { transform: scale(1.15); opacity: 0.85; }
        }
      `}</style>
    </div>,
    portalRoot,
  );
}

/* ─────────────────────────────────────────────────────────────────────
 * BoxHandlesOverlay — renders 4 finger-friendly corner handles at the
 * box's on-screen position (accounting for zoom + pan). These have
 * pointer-events: none because gesture detection happens on the parent
 * wrapper; they're purely visual chrome.
 * ─────────────────────────────────────────────────────────────────── */

function BoxHandlesOverlay({ box, zoom, pan, wrapperRect }) {
  if (!box || !wrapperRect.w) return null;
  const cx = wrapperRect.w / 2;
  const cy = wrapperRect.h / 2;
  const toScreen = (nx, ny) => {
    const vx = nx * wrapperRect.w;
    const vy = ny * wrapperRect.h;
    return { x: (vx - cx) * zoom + cx + pan.x, y: (vy - cy) * zoom + cy + pan.y };
  };
  const corners = [
    ["tl", box.x, box.y],
    ["tr", box.x + box.w, box.y],
    ["bl", box.x, box.y + box.h],
    ["br", box.x + box.w, box.y + box.h],
  ];
  return (
    <div className="absolute inset-0 pointer-events-none">
      {corners.map(([k, nx, ny]) => {
        const s = toScreen(nx, ny);
        return (
          <span
            key={k}
            className="absolute bg-volt border-2 border-white"
            style={{
              left: s.x - 8,
              top: s.y - 8,
              width: 16,
              height: 16,
              boxShadow: "0 0 14px rgba(204,255,0,0.65)",
            }}
          />
        );
      })}
    </div>
  );
}
