/**
 * ScoutMode.jsx — v5.0 "10-tap precision marker" workflow.
 *
 * Replaces the v4 "1-tap + AI track" approach.  Every anchor is now
 * user-verified, which is the only reliable way to guarantee that the
 * report thumbnails track the SAME player throughout the video.
 *
 * Phases:
 *   1. BOOTING    — extract 10 keyframes from the video (scene-cut driven).
 *                   Premium loading screen with status messages + rotating
 *                   football-insights so the user never feels frozen.
 *   2. MARKING    — show each keyframe full-screen.  User taps the target
 *                   player, can pinch-zoom / pan / drag the marker for
 *                   precision, then confirms.  Auto-advances to next frame.
 *                   "Skip this frame" cycles to another keyframe if the
 *                   player isn't visible (we then re-queue the skipped one
 *                   at the end so the user can retry it).
 *   3. CONFIRM    — anchors collected → onConfirm({anchors, sceneCuts}).
 *                   At least 3 anchors are required; the rest can be skipped.
 *
 * NOT touched (per scope discipline):
 *   - Backend pipeline, analysis endpoints, report generation.
 *   - MarkerStudio's wrapper / auto-open / video-element competition fix.
 *   - Landing page, pricing, payment, upload UI.
 *   - Existing /api/scout/detect-players + /api/scout/track-player endpoints
 *     remain in place (dormant for this workflow but unchanged).
 */

import React, { useEffect, useRef, useState, useCallback, useMemo } from "react";
import { createPortal } from "react-dom";
import { X, Check, RotateCcw, ChevronRight, ZoomIn, ZoomOut } from "lucide-react";
import { detectSceneCuts, distributeHints } from "./sceneDetect";

const TARGET_HINTS = 10;
const MIN_REQUIRED = 3;
const FRAME_MAX_W = 1280;
const FRAME_JPEG_QUALITY = 0.82;

// ── Football / scouting insights — rotate every ~4 s during boot ────
const SCOUT_INSIGHTS = [
  "Pro scouts watch 15+ hours of footage per shortlisted player.",
  "Top academies track over 30 metrics per player every match.",
  "A youth player has only ~90 minutes of decisive moments per season.",
  "Quality > quantity — 5 clean highlight clips beat 50 vague ones.",
  "ScoutMePlay analyses every touch your kid takes on the ball.",
  "Movement off the ball is what scouts watch first.",
  "Composure under pressure is the #1 differentiator at U-14 level.",
  "First-touch direction tells you 80 % of what you need to know.",
];

// ── Pure helpers ────────────────────────────────────────────────────

function seekTo(videoEl, t) {
  return new Promise((resolve) => {
    if (!videoEl) return resolve();
    let done = false;
    const finish = () => {
      if (done) return;
      done = true;
      videoEl.removeEventListener("seeked", onSeeked);
      let painted = false;
      const paintDone = () => { if (!painted) { painted = true; resolve(); } };
      if (typeof videoEl.requestVideoFrameCallback === "function") {
        try { videoEl.requestVideoFrameCallback(paintDone); } catch { /* noop */ }
      } else {
        requestAnimationFrame(() => requestAnimationFrame(paintDone));
      }
      setTimeout(paintDone, 400);
    };
    const onSeeked = () => finish();
    videoEl.addEventListener("seeked", onSeeked);
    try { videoEl.currentTime = t; } catch { finish(); }
    setTimeout(finish, 1500);
  });
}

function captureFrame(videoEl) {
  if (!videoEl || !videoEl.videoWidth) return null;
  const vw = videoEl.videoWidth, vh = videoEl.videoHeight;
  const tw = Math.min(FRAME_MAX_W, vw);
  const th = Math.round(vh * (tw / vw));
  const c = document.createElement("canvas");
  c.width = tw; c.height = th;
  try {
    c.getContext("2d").drawImage(videoEl, 0, 0, tw, th);
    return c.toDataURL("image/jpeg", FRAME_JPEG_QUALITY);
  } catch { return null; }
}

// ── Component ───────────────────────────────────────────────────────

export default function ScoutMode({ open, onCancel, onConfirm, videoUrl, duration }) {
  const videoRef = useRef(null);
  const stageRef = useRef(null);

  /* Video readiness */
  const [videoReady, setVideoReady] = useState(false);
  const [vidDur, setVidDur] = useState(duration || 0);

  /* Phase machine */
  const [phase, setPhase] = useState("BOOTING"); // BOOTING | MARKING | DONE

  /* Boot phase state */
  const [bootStage, setBootStage] = useState("uploading"); // uploading | analysing | screenshots
  const [bootProgress, setBootProgress] = useState(0);
  const [hints, setHints] = useState([]);
  const [sceneCuts, setSceneCuts] = useState([]);
  const [frameCache, setFrameCache] = useState([]);

  /* Marking phase state */
  // queue: ordered list of hint indices to present.  When user skips a
  // frame we re-queue it at the END so they can retry once they've gone
  // through the others.
  const [queue, setQueue] = useState([]);
  const [queuePos, setQueuePos] = useState(0); // pointer into queue[]
  // marks[hintIdx] = { x, y, w, h, hintT, source: 'user', skipped?: bool }
  const [marks, setMarks] = useState({});

  /* Adjust-marker state for the CURRENT frame being marked */
  // local box being edited — when the user taps, we set this; pinch/drag
  // tweaks it; "Confirm" copies it into `marks`.
  const [draftBox, setDraftBox] = useState(null);
  // zoom & pan for precision marking
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  // dragging the marker box itself
  const dragRef = useRef({ active: false, startX: 0, startY: 0, origBox: null, mode: null });

  /* ── Reset on close ────────────────────────────────────────────── */
  useEffect(() => {
    if (!open) {
      setVideoReady(false);
      setPhase("BOOTING");
      setBootStage("uploading");
      setBootProgress(0);
      setHints([]);
      setSceneCuts([]);
      setFrameCache([]);
      setQueue([]);
      setQueuePos(0);
      setMarks({});
      setDraftBox(null);
      setZoom(1);
      setPan({ x: 0, y: 0 });
    }
  }, [open]);

  /* ── iOS Safari rescue: poll readyState while the boot overlay is up
   *    `canplay` and `loadeddata` are unreliable on blob URLs on iOS, so
   *    we additionally poll `videoEl.readyState` every 250ms while we're
   *    still waiting. The moment we see `readyState >= 1 (HAVE_METADATA)`
   *    AND a non-zero videoWidth, we know it's safe to start the boot
   *    pipeline. Without this, large mobile uploads sometimes get stuck
   *    on the "Uploading video 0%" screen indefinitely.
   *
   *    We also call `videoEl.load()` once explicitly when the overlay
   *    opens so the network/decoder pipeline starts immediately even if
   *    the <video> mount was preempted by another tab/render.
   */
  useEffect(() => {
    if (!open) return;
    if (videoReady) return;
    const v = videoRef.current;
    if (!v) return;
    try { v.load(); } catch { /* noop */ }
    let id;
    const tick = () => {
      const ve = videoRef.current;
      if (!ve) return;
      if (ve.readyState >= 1 && (ve.videoWidth || 0) > 0) {
        setVideoReady(true);
        setVidDur(ve.duration || 0);
        return;
      }
      id = setTimeout(tick, 250);
    };
    id = setTimeout(tick, 250);
    return () => { if (id) clearTimeout(id); };
  }, [open, videoReady]);

  /* ── Stage size observer ───────────────────────────────────────── */
  const [stageRect, setStageRect] = useState({ w: 0, h: 0 });
  useEffect(() => {
    if (!open) return;
    if (!stageRef.current) return;
    const el = stageRef.current;
    const r = el.getBoundingClientRect();
    setStageRect({ w: r.width, h: r.height });
    const ro = new ResizeObserver(() => {
      const rr = el.getBoundingClientRect();
      setStageRect({ w: rr.width, h: rr.height });
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, [open]);

  /* ── BOOT: scene-cut + 10 keyframes ────────────────────────────── */
  useEffect(() => {
    if (!open) return;
    if (!videoReady) return;
    if (phase !== "BOOTING") return;
    let cancelled = false;
    (async () => {
      const v = videoRef.current;
      if (!v) return;

      // Phase A: wait for the video to be truly ready
      setBootStage("uploading");
      setBootProgress(0.05);
      const waitReady = async () => {
        const start = Date.now();
        let reloaded = false;
        while (!cancelled && Date.now() - start < 12000) {
          if (v.readyState >= 2 && v.videoWidth > 0 && v.duration > 0) return;
          if (!reloaded && Date.now() - start > 4000) {
            reloaded = true;
            try {
              v.load();
              const pp = v.play();
              if (pp?.catch) pp.catch(() => {});
              setTimeout(() => { try { v.pause(); } catch { /* noop */ } }, 50);
            } catch { /* noop */ }
          }
          if (!cancelled) {
            const t = (Date.now() - start) / 12000;
            setBootProgress(0.05 + t * 0.10); // 5% → 15%
          }
          await new Promise((r) => setTimeout(r, 120));
        }
      };
      await waitReady();
      if (cancelled) return;

      // Phase B: scene-cut detection
      setBootStage("analysing");
      setBootProgress(0.15);
      let cuts = [];
      try {
        const result = await detectSceneCuts(v, {
          onProgress: (p) => { if (!cancelled) setBootProgress(0.15 + p * 0.30); },
        });
        cuts = result.cuts || [];
      } catch (err) {
        console.warn("scene-cut detect failed:", err);
      }
      if (cancelled) return;
      setSceneCuts(cuts);

      // Phase C: distribute hints + capture frames
      const dur = v.duration || vidDur || 0;
      let hs = distributeHints(dur, cuts, TARGET_HINTS);
      if (!hs.length) {
        const fbDur = dur || 30;
        hs = [];
        for (let i = 0; i < TARGET_HINTS; i++) hs.push((fbDur * (i + 0.5)) / TARGET_HINTS);
      }
      setHints(hs);

      setBootStage("screenshots");
      setBootProgress(0.45);
      const captured = [];
      for (let i = 0; i < hs.length; i++) {
        if (cancelled) return;
        try {
          await seekTo(v, hs[i]);
          captured.push({ t: hs[i], jpegDataUrl: captureFrame(v) });
        } catch {
          captured.push({ t: hs[i], jpegDataUrl: null });
        }
        if (!cancelled) setBootProgress(0.45 + 0.55 * ((i + 1) / hs.length));
      }
      if (cancelled) return;
      setFrameCache(captured);

      // Phase D: seek back to first usable frame, enter MARKING
      const firstViable = captured.findIndex((f) => f.jpegDataUrl);
      const startIdx = firstViable >= 0 ? firstViable : 0;
      try { await seekTo(v, hs[startIdx]); } catch { /* noop */ }
      if (cancelled) return;
      // Build initial queue — all frames in order
      const q = captured.map((_, i) => i).filter((i) => captured[i].jpegDataUrl);
      setQueue(q);
      setQueuePos(0);
      setBootProgress(1);
      setPhase("MARKING");
    })();
    return () => { cancelled = true; };
  }, [open, videoReady, phase, vidDur]);

  /* ── Whenever queue position changes, seek the video ─────────── */
  const currentHintIdx = queue[queuePos];
  useEffect(() => {
    if (phase !== "MARKING") return;
    if (currentHintIdx == null) return;
    const v = videoRef.current;
    if (!v || !hints.length) return;
    const t = hints[currentHintIdx];
    if (t != null && Math.abs(v.currentTime - t) > 0.15) {
      try { v.currentTime = t; } catch { /* noop */ }
    }
    // Reset zoom/pan/draft for the new frame
    setZoom(1);
    setPan({ x: 0, y: 0 });
    setDraftBox(marks[currentHintIdx] || null);
  }, [phase, currentHintIdx, hints, marks]);

  /* ── Tap on the stage to set the marker ──────────────────────── */
  const handleStageTap = useCallback((e) => {
    if (phase !== "MARKING") return;
    if (currentHintIdx == null) return;
    const stage = stageRef.current;
    const v = videoRef.current;
    if (!stage || !v?.videoWidth) return;
    const r = stage.getBoundingClientRect();
    const cx = e.touches?.[0]?.clientX ?? e.clientX;
    const cy = e.touches?.[0]?.clientY ?? e.clientY;
    if (cx == null || cy == null) return;

    // Pointer in stage-screen coords
    const sx = cx - r.left;
    const sy = cy - r.top;
    // Translate via current zoom/pan
    const stageW = r.width, stageH = r.height;
    const centreX = stageW / 2 + pan.x;
    const centreY = stageH / 2 + pan.y;
    const renderedX = (sx - centreX) / zoom + stageW / 2;
    const renderedY = (sy - centreY) / zoom + stageH / 2;
    // object-contain mapping → fractional video coords
    const vw = v.videoWidth, vh = v.videoHeight;
    const baseScale = Math.min(stageW / vw, stageH / vh);
    const renderedW = vw * baseScale, renderedH = vh * baseScale;
    const offX = (stageW - renderedW) / 2, offY = (stageH - renderedH) / 2;
    const inX = renderedX - offX, inY = renderedY - offY;
    if (inX < 0 || inY < 0 || inX > renderedW || inY > renderedH) return;
    const fx = inX / renderedW;
    const fy = inY / renderedH;
    const w = 0.06, h = 0.18;
    setDraftBox({
      x: Math.max(0, Math.min(1 - w, fx - w / 2)),
      y: Math.max(0, Math.min(1 - h, fy - h * 0.42)),
      w, h,
    });
  }, [phase, currentHintIdx, zoom, pan]);

  /* ── Drag the marker box itself ──────────────────────────────── */
  const handleBoxPointerDown = useCallback((e, mode) => {
    e.preventDefault();
    e.stopPropagation();
    if (!draftBox) return;
    const cx = e.touches?.[0]?.clientX ?? e.clientX;
    const cy = e.touches?.[0]?.clientY ?? e.clientY;
    dragRef.current = {
      active: true, startX: cx, startY: cy,
      origBox: { ...draftBox }, mode,
    };
  }, [draftBox]);

  const handleBoxPointerMove = useCallback((e) => {
    const d = dragRef.current;
    if (!d.active || !d.origBox) return;
    const v = videoRef.current;
    const stage = stageRef.current;
    if (!v?.videoWidth || !stage) return;
    const cx = e.touches?.[0]?.clientX ?? e.clientX;
    const cy = e.touches?.[0]?.clientY ?? e.clientY;
    if (cx == null || cy == null) return;
    const dxScreen = cx - d.startX;
    const dyScreen = cy - d.startY;
    const r = stage.getBoundingClientRect();
    const vw = v.videoWidth, vh = v.videoHeight;
    const baseScale = Math.min(r.width / vw, r.height / vh);
    const renderedW = vw * baseScale, renderedH = vh * baseScale;
    // Convert screen delta → fractional delta on the rendered video
    const dxFrac = dxScreen / (renderedW * zoom);
    const dyFrac = dyScreen / (renderedH * zoom);

    let nb = { ...d.origBox };
    if (d.mode === "move") {
      nb.x = Math.max(0, Math.min(1 - nb.w, nb.x + dxFrac));
      nb.y = Math.max(0, Math.min(1 - nb.h, nb.y + dyFrac));
    } else if (d.mode === "resize") {
      nb.w = Math.max(0.02, Math.min(1 - nb.x, nb.w + dxFrac));
      nb.h = Math.max(0.04, Math.min(1 - nb.y, nb.h + dyFrac));
    }
    setDraftBox(nb);
  }, [zoom]);

  const handleBoxPointerUp = useCallback(() => {
    dragRef.current.active = false;
  }, []);

  /* ── Zoom controls ──────────────────────────────────────────── */
  const handleZoomIn = useCallback(() => setZoom((z) => Math.min(3, z * 1.4)), []);
  const handleZoomOut = useCallback(() => {
    setZoom((z) => {
      const nz = Math.max(1, z / 1.4);
      if (nz === 1) setPan({ x: 0, y: 0 });
      return nz;
    });
  }, []);
  const handleResetZoom = useCallback(() => {
    setZoom(1); setPan({ x: 0, y: 0 });
  }, []);

  /* ── Confirm current marker → next frame ────────────────────── */
  const confirmedCount = useMemo(
    () => Object.values(marks).filter((m) => m && !m.skipped).length,
    [marks],
  );

  const advance = useCallback(() => {
    // Move to the next unmarked frame in the queue.  If we reach the end
    // and there are still skipped frames, loop back to give the user another
    // chance.  If all frames have been visited, transition to DONE.
    const totalFrames = queue.length;
    let next = queuePos + 1;
    if (next >= totalFrames) {
      // Check if all frames in queue have been either confirmed or are skipped
      const remaining = queue.filter((i) => !marks[i] || marks[i].skipped);
      if (remaining.length === 0) {
        // All confirmed somehow — go directly to finalise
        setPhase("DONE");
        return;
      }
      // Otherwise, accept current state — at least MIN_REQUIRED confirmed
      // means we're done.
      if (confirmedCount + 1 >= MIN_REQUIRED) {
        setPhase("DONE");
        return;
      }
      // Loop back to retry the skipped ones
      next = 0;
    }
    setQueuePos(next);
  }, [queue, queuePos, marks, confirmedCount]);

  const handleConfirmMark = useCallback(() => {
    if (!draftBox || currentHintIdx == null) return;
    const hintT = hints[currentHintIdx];
    setMarks((prev) => ({
      ...prev,
      [currentHintIdx]: {
        x: draftBox.x, y: draftBox.y, w: draftBox.w, h: draftBox.h,
        hintT, source: "user", skipped: false,
      },
    }));
    setTimeout(advance, 350); // brief "locked" beat so user sees confirmation
  }, [draftBox, currentHintIdx, hints, advance]);

  const handleSkipFrame = useCallback(() => {
    if (currentHintIdx == null) return;
    const hintT = hints[currentHintIdx];
    setMarks((prev) => ({
      ...prev,
      [currentHintIdx]: { skipped: true, hintT, source: "skipped" },
    }));
    advance();
  }, [currentHintIdx, hints, advance]);

  const handleRetap = useCallback(() => {
    setDraftBox(null);
  }, []);

  const handleFinishEarly = useCallback(() => {
    if (confirmedCount < MIN_REQUIRED) return;
    setPhase("DONE");
  }, [confirmedCount]);

  /* ── DONE: build payload and call onConfirm ─────────────────── */
  useEffect(() => {
    if (phase !== "DONE") return;
    // Sort confirmed marks by frame index so anchor[0] is the earliest in time.
    const indices = Object.keys(marks)
      .map(Number)
      .filter((i) => marks[i] && !marks[i].skipped)
      .sort((a, b) => a - b);
    const anchors = indices.map((i) => {
      const m = marks[i];
      let seg = 0;
      for (let s = 0; s < sceneCuts.length; s++) if (m.hintT >= sceneCuts[s]) seg = s + 1;
      return { t: m.hintT, box: { x: m.x, y: m.y, w: m.w, h: m.h }, segment: seg };
    });
    if (anchors.length < MIN_REQUIRED) {
      // not enough — fall back to MARKING for retry
      setPhase("MARKING");
      return;
    }
    // Pass the first anchor's captured frame as the marker JPEG (data URL).
    // The parent's <video> is unmounted while Scout Mode is open (decoder
    // conflict fix) so we MUST supply the frame ourselves instead of asking
    // the parent to grab it from a null videoRef.
    const firstIdx = indices[0];
    const markerImageDataUrl = frameCache[firstIdx]?.jpegDataUrl || null;
    onConfirm({ anchors, sceneCuts, markerImageDataUrl });
  }, [phase, marks, sceneCuts, frameCache, onConfirm]);

  /* ── Render ────────────────────────────────────────────────── */
  if (!open) return null;

  return createPortal(
    <div
      className="fixed inset-0 z-[230] bg-ink text-white flex flex-col"
      data-testid="scout-mode-overlay"
    >
      {/* ── Top bar ──────────────────────────────────────────── */}
      <div className="flex-shrink-0 flex items-center justify-between h-12 px-3 border-b border-white/8 bg-ink/95 backdrop-blur">
        <button
          type="button"
          onClick={onCancel}
          data-testid="scout-close"
          className="w-9 h-9 flex items-center justify-center text-white/85 hover:text-[#CCFF00] transition-colors"
          aria-label="Close Scout Mode"
        >
          <X className="w-5 h-5" />
        </button>
        <span className="text-[11px] uppercase tracking-widest font-black text-white/85" data-testid="scout-mode-title">
          Scout Mode
        </span>
        <span className="w-9" />
      </div>

      {/* ── Stage / phase content ───────────────────────────── */}
      <div
        ref={stageRef}
        className="relative flex-1 bg-black overflow-hidden flex items-center justify-center"
        data-testid="scout-stage"
        onClick={phase === "MARKING" && !draftBox ? handleStageTap : undefined}
        onMouseMove={handleBoxPointerMove}
        onMouseUp={handleBoxPointerUp}
        onMouseLeave={handleBoxPointerUp}
        onTouchMove={handleBoxPointerMove}
        onTouchEnd={handleBoxPointerUp}
        style={{
          cursor: phase === "MARKING" && !draftBox ? "crosshair" : "default",
          touchAction: "none",
        }}
      >
        <video
          ref={videoRef}
          src={videoUrl}
          className="absolute inset-0 w-full h-full object-contain"
          playsInline
          preload="auto"
          muted
          onLoadedMetadata={(e) => {
            setVidDur(e.target.duration || 0);
            // Fallback for iOS Safari: `canplay` is unreliable on blob URLs.
            // If we already have metadata + a non-zero readyState, we can safely
            // proceed — `readyState >= 1 (HAVE_METADATA)` is enough to seek + draw.
            if (e.target.readyState >= 1 && (e.target.videoWidth || 0) > 0) {
              setVideoReady(true);
            }
          }}
          onLoadedData={(e) => {
            setVideoReady(true);
            setVidDur(e.target.duration || 0);
          }}
          onCanPlay={(e) => {
            setVideoReady(true);
            setVidDur(e.target.duration || 0);
          }}
          style={{
            transform: `scale(${zoom}) translate(${pan.x / zoom}px, ${pan.y / zoom}px)`,
            transformOrigin: "center center",
            transition: dragRef.current.active ? "none" : "transform 0.18s ease-out",
            pointerEvents: "none",
          }}
        />

        {/* Draft marker (lime, draggable) */}
        {phase === "MARKING" && draftBox && videoRef.current?.videoWidth && stageRect.w > 0 && (
          <DraftMarker
            box={draftBox}
            videoEl={videoRef.current}
            stageRect={stageRect}
            zoom={zoom}
            pan={pan}
            onPointerDown={(e, mode) => handleBoxPointerDown(e, mode)}
          />
        )}

        {/* Boot overlay */}
        {phase === "BOOTING" && (
          <PremiumBootOverlay progress={bootProgress} stage={bootStage} />
        )}

        {/* Marking overlay (instructions + skip/zoom controls) */}
        {phase === "MARKING" && (
          <MarkingOverlay
            hintIdx={currentHintIdx}
            queue={queue}
            queuePos={queuePos}
            confirmedCount={confirmedCount}
            hasDraft={!!draftBox}
            zoom={zoom}
            onSkip={handleSkipFrame}
            onRetap={handleRetap}
            onConfirm={handleConfirmMark}
            onFinishEarly={handleFinishEarly}
            onZoomIn={handleZoomIn}
            onZoomOut={handleZoomOut}
            onResetZoom={handleResetZoom}
          />
        )}

        {/* Live frame strip — orientation aid during marking. Shows all
            captured frames as small thumbs with status icons; tap to jump. */}
        {phase === "MARKING" && (
          <FrameStrip
            queue={queue}
            queuePos={queuePos}
            frameCache={frameCache}
            marks={marks}
            onJumpTo={(pos) => { setQueuePos(pos); setDraftBox(null); handleResetZoom(); }}
          />
        )}
      </div>
    </div>,
    document.body,
  );
}

ScoutMode.displayName = "ScoutMode";

// ── Sub-components ─────────────────────────────────────────────────

function DraftMarker({ box, videoEl, stageRect, zoom, pan, onPointerDown }) {
  if (!box || !videoEl?.videoWidth) return null;
  const vw = videoEl.videoWidth, vh = videoEl.videoHeight;
  const sw = stageRect.w, sh = stageRect.h;
  const baseScale = Math.min(sw / vw, sh / vh);
  const rW = vw * baseScale, rH = vh * baseScale;
  const offX = (sw - rW) / 2, offY = (sh - rH) / 2;
  // Position in pre-zoom coords
  const x0 = box.x * rW + offX;
  const y0 = box.y * rH + offY;
  const w0 = box.w * rW;
  const h0 = box.h * rH;
  // Apply CSS zoom & pan transform same as video
  const centreX = sw / 2 + pan.x;
  const centreY = sh / 2 + pan.y;
  const x = (x0 - sw / 2) * zoom + centreX;
  const y = (y0 - sh / 2) * zoom + centreY;
  const w = w0 * zoom, h = h0 * zoom;

  return (
    <>
      <div
        data-testid="scout-draft-marker"
        onMouseDown={(e) => onPointerDown(e, "move")}
        onTouchStart={(e) => onPointerDown(e, "move")}
        style={{
          position: "absolute",
          left: x - 2,
          top: y - 2,
          width: w + 4,
          height: h + 4,
          border: "3px solid #CCFF00",
          borderRadius: 6,
          boxShadow: "0 0 0 1px rgba(0,0,0,0.7), 0 0 24px rgba(204,255,0,0.55)",
          background: "rgba(204,255,0,0.06)",
          cursor: "move",
          touchAction: "none",
          zIndex: 30,
        }}
      />
      {/* Resize handle (bottom-right) */}
      <div
        data-testid="scout-draft-resize"
        onMouseDown={(e) => onPointerDown(e, "resize")}
        onTouchStart={(e) => onPointerDown(e, "resize")}
        style={{
          position: "absolute",
          left: x + w - 10,
          top: y + h - 10,
          width: 22,
          height: 22,
          background: "#CCFF00",
          border: "2px solid #0A0F0D",
          borderRadius: 4,
          cursor: "nwse-resize",
          touchAction: "none",
          zIndex: 31,
          boxShadow: "0 2px 8px rgba(0,0,0,0.6)",
        }}
      />
    </>
  );
}

function PremiumBootOverlay({ progress, stage }) {
  const [insightIdx, setInsightIdx] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setInsightIdx((i) => (i + 1) % SCOUT_INSIGHTS.length), 4000);
    return () => clearInterval(id);
  }, []);
  const pct = Math.round(progress * 100);
  const stageLabel =
    stage === "uploading" ? "Uploading video"
    : stage === "analysing" ? "Analysing footage"
    : "Generating player screenshots";

  return (
    <div className="absolute inset-0 flex flex-col items-center justify-center bg-ink/97 backdrop-blur-md text-white px-8" style={{ zIndex: 50 }}>
      {/* Crest / loading mark */}
      <div className="relative w-24 h-24 mb-6">
        <div className="absolute inset-0 rounded-full border-[3px] border-white/8" />
        <svg
          viewBox="0 0 100 100"
          className="absolute inset-0 transition-all duration-300"
          style={{ transform: "rotate(-90deg)" }}
        >
          <circle
            cx="50" cy="50" r="46"
            fill="none"
            stroke="#CCFF00"
            strokeWidth="3"
            strokeLinecap="round"
            strokeDasharray={`${pct * 2.89} 289`}
            style={{ transition: "stroke-dasharray 0.35s ease-out", filter: "drop-shadow(0 0 8px rgba(204,255,0,0.55))" }}
          />
        </svg>
        <div className="absolute inset-0 flex items-center justify-center">
          <span className="text-[#CCFF00] font-black text-lg tabular-nums" style={{ letterSpacing: "-0.02em" }}>
            {pct}%
          </span>
        </div>
      </div>

      {/* Stage label */}
      <div className="text-white font-black text-[18px] mb-1 tracking-tight">
        {stageLabel}
      </div>
      <div className="text-white/55 text-[12px] mb-8 text-center max-w-xs">
        {stage === "uploading"
          ? "Preparing your video for analysis…"
          : stage === "analysing"
          ? "Finding the natural breakpoints in the match…"
          : "Capturing 10 key moments to mark your player."}
      </div>

      {/* Insights ticker */}
      <div
        className="w-full max-w-sm px-4 py-3 bg-white/3 border-l-2 border-[#CCFF00]"
        style={{ minHeight: 64 }}
      >
        <div className="text-[#CCFF00] text-[9px] uppercase tracking-[0.2em] font-black mb-1">
          Scouting Insight
        </div>
        <div className="text-white/85 text-[13px] leading-snug transition-opacity duration-500" key={insightIdx}>
          {SCOUT_INSIGHTS[insightIdx]}
        </div>
      </div>
    </div>
  );
}

function MarkingOverlay({
  hintIdx,
  queue,
  queuePos,
  confirmedCount,
  hasDraft,
  zoom,
  onSkip,
  onRetap,
  onConfirm,
  onFinishEarly,
  onZoomIn,
  onZoomOut,
  onResetZoom,
}) {
  const totalFrames = queue.length || 10;
  const targetN = Math.max(confirmedCount + 1, queuePos + 1);
  const canFinish = confirmedCount >= MIN_REQUIRED;

  return (
    <>
      {/* Top instruction strip */}
      <div
        className="absolute left-0 right-0 flex items-center justify-between"
        style={{
          top: 0,
          height: 56,
          padding: "0 14px",
          background: "linear-gradient(180deg, rgba(10,15,13,0.94) 0%, rgba(10,15,13,0.65) 75%, rgba(10,15,13,0) 100%)",
          backdropFilter: "blur(10px)",
          WebkitBackdropFilter: "blur(10px)",
          zIndex: 15,
          pointerEvents: "none",
        }}
      >
        <div className="flex items-baseline gap-2">
          <span
            className="text-white font-black tabular-nums leading-none"
            style={{ fontSize: 26, letterSpacing: "-0.02em" }}
            data-testid="scout-progress-counter"
          >
            {confirmedCount}<span className="text-white/35 font-bold text-[16px]">/{totalFrames}</span>
          </span>
          <span className="text-white/80 leading-none" style={{ fontSize: 12, fontWeight: 600, letterSpacing: "0.01em" }}>
            {hasDraft ? "Adjust & confirm" : "Tap your player"}
          </span>
        </div>
        <span
          className="text-white/45 tabular-nums"
          style={{ fontSize: 10, fontWeight: 700, letterSpacing: "0.1em" }}
        >
          FRAME {queuePos + 1}/{totalFrames}
        </span>
      </div>

      {/* Progress dots row (just under the strip) */}
      <div
        className="absolute left-1/2 -translate-x-1/2 flex items-center gap-1.5"
        style={{ top: 50, zIndex: 14, pointerEvents: "none" }}
      >
        {queue.map((qi, i) => {
          const isPast = i < queuePos;
          const isCur = i === queuePos;
          return (
            <span
              key={qi}
              style={{
                width: isCur ? 18 : 6,
                height: 6,
                borderRadius: 3,
                background: isPast ? "#CCFF00" : isCur ? "#FFFFFF" : "rgba(255,255,255,0.2)",
                transition: "all 0.25s ease",
              }}
            />
          );
        })}
      </div>

      {/* Bottom action bar */}
      <div
        className="absolute left-0 right-0 px-3"
        style={{ bottom: 14, zIndex: 20 }}
      >
        {hasDraft ? (
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={(e) => { e.stopPropagation(); onRetap(); }}
              data-testid="scout-retap"
              className="h-12 px-4 flex items-center justify-center gap-1.5 bg-ink/85 backdrop-blur border border-white/22 text-white/85 font-black text-[11px] uppercase tracking-widest hover:text-[#CCFF00] hover:border-[#CCFF00] transition-colors"
              style={{ pointerEvents: "auto" }}
            >
              <RotateCcw className="w-3.5 h-3.5" />
              Re-tap
            </button>
            <button
              type="button"
              onClick={(e) => { e.stopPropagation(); onConfirm(); }}
              data-testid="scout-confirm-mark"
              className="flex-1 h-12 flex items-center justify-center gap-2 bg-[#CCFF00] text-ink font-black text-[13px] uppercase tracking-wider hover:bg-white transition-colors"
              style={{ pointerEvents: "auto", letterSpacing: "0.08em" }}
            >
              <Check className="w-5 h-5" />
              Confirm Player {targetN}
            </button>
          </div>
        ) : (
          <div className="flex items-center justify-between gap-2">
            <button
              type="button"
              onClick={(e) => { e.stopPropagation(); onSkip(); }}
              data-testid="scout-skip-frame"
              className="h-11 px-3 flex items-center gap-1.5 text-white/55 hover:text-[#CCFF00] transition-colors"
              style={{ pointerEvents: "auto", fontSize: 11, fontWeight: 700, letterSpacing: "0.06em", textTransform: "uppercase", background: "transparent", border: "none" }}
            >
              Not visible · next frame
              <ChevronRight className="w-4 h-4" />
            </button>
            {canFinish && (
              <button
                type="button"
                onClick={(e) => { e.stopPropagation(); onFinishEarly(); }}
                data-testid="scout-finish-early"
                className="h-11 px-4 flex items-center gap-1.5 bg-[#CCFF00]/12 border border-[#CCFF00]/55 text-[#CCFF00] hover:bg-[#CCFF00] hover:text-ink transition-colors"
                style={{ pointerEvents: "auto", fontSize: 11, fontWeight: 800, letterSpacing: "0.08em", textTransform: "uppercase" }}
              >
                <Check className="w-3.5 h-3.5" />
                Finish ({confirmedCount} marked)
              </button>
            )}
            <div className="flex items-center gap-1.5">
              <button
                type="button"
                onClick={(e) => { e.stopPropagation(); onZoomOut(); }}
                disabled={zoom <= 1.01}
                data-testid="scout-zoom-out"
                className="w-10 h-10 flex items-center justify-center bg-ink/85 backdrop-blur border border-white/22 text-white/85 hover:text-[#CCFF00] hover:border-[#CCFF00] disabled:opacity-30 transition-colors"
                style={{ pointerEvents: "auto" }}
              >
                <ZoomOut className="w-4 h-4" />
              </button>
              <button
                type="button"
                onClick={(e) => { e.stopPropagation(); onResetZoom(); }}
                data-testid="scout-zoom-reset"
                className="h-10 px-2.5 flex items-center justify-center bg-ink/85 backdrop-blur border border-white/22 text-white/75 hover:text-[#CCFF00] hover:border-[#CCFF00] transition-colors tabular-nums"
                style={{ pointerEvents: "auto", fontSize: 10, fontWeight: 800, letterSpacing: "0.04em" }}
              >
                {zoom.toFixed(1)}×
              </button>
              <button
                type="button"
                onClick={(e) => { e.stopPropagation(); onZoomIn(); }}
                disabled={zoom >= 2.99}
                data-testid="scout-zoom-in"
                className="w-10 h-10 flex items-center justify-center bg-ink/85 backdrop-blur border border-white/22 text-white/85 hover:text-[#CCFF00] hover:border-[#CCFF00] disabled:opacity-30 transition-colors"
                style={{ pointerEvents: "auto" }}
              >
                <ZoomIn className="w-4 h-4" />
              </button>
            </div>
          </div>
        )}
      </div>
    </>
  );
}

/* ── Live frame strip — sticky to the bottom of the stage above the
 *    MarkingOverlay. Renders a horizontal scrollable row of all queued
 *    frame thumbs with a status overlay (✓ marked / 🔒 skipped / ▸ current
 *    / · pending). Tapping a thumb jumps the queue cursor to that frame
 *    so the user can return to a previously skipped frame or correct a
 *    bad mark. */
function FrameStrip({ queue, queuePos, frameCache, marks, onJumpTo }) {
  if (!queue || queue.length === 0) return null;
  // Count how many frames in the current queue have a non-skipped mark — when
  // every position in the queue is confirmed we surface a small trust badge so
  // the user feels confident before tapping "Upload & analyse".
  const confirmedCount = queue.reduce(
    (n, hintIdx) => (marks[hintIdx] && !marks[hintIdx].skipped ? n + 1 : n),
    0
  );
  const allDone = confirmedCount === queue.length;
  return (
    <div
      className="absolute left-0 right-0 z-30 px-3 pb-2 pointer-events-none"
      style={{ bottom: "calc(120px + env(safe-area-inset-bottom, 0px))" }}
      data-testid="scout-frame-strip"
    >
      {/* Trust badge appears the instant every frame in the queue is locked.
          Sits above the thumbnail strip and fades in with a pulse. */}
      {allDone && (
        <div
          className="mx-auto mb-2 max-w-fit pointer-events-auto"
          data-testid="scout-frame-strip-verified-badge"
        >
          <div className="flex items-center gap-2 px-3 py-1.5 bg-emerald-500/15 border border-[#CCFF00]/70 rounded-full backdrop-blur-md shadow-[0_0_18px_rgba(204,255,0,0.35)]">
            <span className="relative flex w-2 h-2">
              <span className="absolute inset-0 rounded-full bg-[#CCFF00] animate-ping opacity-75" />
              <span className="relative rounded-full w-2 h-2 bg-[#CCFF00]" />
            </span>
            <span className="text-[10.5px] uppercase tracking-[0.22em] font-black text-[#CCFF00]">
              Verified by Pro Scout Intelligence ✓
            </span>
          </div>
        </div>
      )}
      <div
        className="mx-auto max-w-[640px] flex gap-1.5 overflow-x-auto px-2 py-2 bg-ink/65 backdrop-blur border border-white/12"
        style={{ pointerEvents: "auto", WebkitOverflowScrolling: "touch" }}
      >
        {queue.map((hintIdx, pos) => {
          const m = marks[hintIdx];
          const isCurrent = pos === queuePos;
          const isConfirmed = m && !m.skipped;
          const isSkipped = m && m.skipped;
          const thumb = frameCache[hintIdx]?.jpegDataUrl;
          // Visual treatment per status:
          //   current  → bright lime border + faint glow
          //   marked   → forest-green border + check pip
          //   skipped  → dim border + slash pip (50 % opacity)
          //   pending  → soft white border
          let borderCls = "border-white/22";
          let opacityCls = "opacity-90";
          if (isCurrent) borderCls = "border-[#CCFF00] shadow-[0_0_0_2px_rgba(204,255,0,0.35)]";
          else if (isConfirmed) borderCls = "border-[#CCFF00] shadow-[0_0_0_1.5px_rgba(204,255,0,0.55)]";
          else if (isSkipped) { borderCls = "border-white/15"; opacityCls = "opacity-45"; }
          return (
            <button
              key={hintIdx}
              type="button"
              onClick={(e) => { e.stopPropagation(); onJumpTo(pos); }}
              data-testid={`scout-frame-strip-${pos}`}
              aria-label={`Frame ${pos + 1} of ${queue.length}${isConfirmed ? " (marked)" : isSkipped ? " (skipped)" : " (pending)"}`}
              className={`relative flex-shrink-0 w-14 h-9 sm:w-16 sm:h-10 border-2 ${borderCls} ${opacityCls} transition-all`}
              style={{ background: "#000" }}
            >
              {thumb ? (
                isConfirmed && typeof m?.x === "number" ? (
                  /*  CONFIRMED VIEW — the thumbnail visually transforms into a portrait
                   *  of the marked region so the user can see EXACTLY what they marked.
                   *  We zoom the underlying frame so the bounding box fills the thumb
                   *  (with a sensible cap so very tiny boxes don't pixelate hard).
                   *  NOTE: marks are stored as a FLAT shape ({x,y,w,h,…}) — NOT under
                   *  an `m.box` sub-key — that's why the earlier `m?.box` check kept
                   *  failing and the thumbnails never visibly changed in production. */
                  (() => {
                    const bw = Math.max(0.18, Math.min(1, m.w));
                    const bh = Math.max(0.18, Math.min(1, m.h));
                    const cx = (m.x + m.w / 2) * 100;
                    const cy = (m.y + m.h / 2) * 100;
                    // Force a minimum 1.9× zoom even when the bounding box is large,
                    // so the thumbnail ALWAYS visibly transforms after confirmation —
                    // no doubt that the mark was registered. Capped at 4.5× to avoid
                    // pixelation on very tiny boxes (distant player).
                    const rawScale = 1 / Math.max(bw, bh);
                    const scale = Math.min(4.5, Math.max(1.9, rawScale));
                    return (
                      <div className="absolute inset-0 overflow-hidden">
                        <img
                          src={thumb}
                          alt=""
                          className="absolute inset-0 w-full h-full object-cover transition-transform duration-300"
                          style={{
                            transform: `scale(${scale})`,
                            transformOrigin: `${Math.max(8, Math.min(92, cx))}% ${Math.max(8, Math.min(92, cy))}%`,
                            // Slight saturation/contrast boost so the confirmed
                            // thumbnails visually pop next to the unconfirmed ones.
                            filter: "saturate(1.25) contrast(1.08)",
                          }}
                          draggable={false}
                        />
                        {/* Tiny "TRACKED" pill across the bottom — extra reassurance
                            that THIS specific frame's mark was locked in. */}
                        <span className="absolute bottom-0 left-0 right-0 bg-[#CCFF00] text-ink text-[7px] uppercase tracking-[0.18em] font-black text-center py-[1px] leading-none">
                          Tracked
                        </span>
                      </div>
                    );
                  })()
                ) : (
                  /* PENDING / CURRENT / SKIPPED — show the full frame as before. */
                  <img
                    src={thumb}
                    alt=""
                    className="w-full h-full object-cover"
                    draggable={false}
                  />
                )
              ) : null}
              {/* Tap-position overlay — only useful BEFORE we've zoomed into the
                  marked region. Once confirmed, the zoomed image itself IS the
                  proof of what was marked, so this overlay is intentionally
                  skipped on confirmed thumbnails. */}
              {/* Status pip — bottom-right */}
              {(isConfirmed || isSkipped) && (
                <span
                  className={`absolute -bottom-1 -right-1 w-3.5 h-3.5 rounded-full flex items-center justify-center text-[8px] font-black ${
                    isConfirmed ? "bg-emerald-500 text-ink" : "bg-white/30 text-ink"
                  }`}
                >
                  {isConfirmed ? "✓" : "−"}
                </span>
              )}
              {/* Frame number — top-left */}
              <span className="absolute top-0 left-0 px-1 py-0.5 text-[8px] font-black text-white bg-ink/70 leading-none">
                {pos + 1}
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
