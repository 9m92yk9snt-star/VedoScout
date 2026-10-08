/**
 * The sole player-selection workflow: up to ten visible, human-confirmed
 * moments, then three distinct extra checks. No detector guesses or hidden
 * manual editor. Every box stays bound to the exact displayed still frame.
 */
import React, { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Check, X, EyeOff, RotateCcw, ZoomIn, ZoomOut, ChevronLeft, ChevronRight, Loader2 } from "lucide-react";
import MarkedCropCanvas from "../MarkedCropCanvas";
import { detectSceneCuts, distributeHints } from "./sceneDetect";
import videoFrameAuthority from "./videoFrameAuthority.cjs";
import policy from "./scoutTapPolicy.cjs";

const { TARGET_TAPS, MIN_TAPS, VERIFY_TAPS, screenToVideo, tapBox, markingProgress,
  nearbyTime, verifyTime, distinctVerifyTime, buildPayload } = policy;
const clamp = (n, lo, hi) => Math.max(lo, Math.min(hi, n));
const fmt = t => {
  const s = Math.floor(Math.max(0, t || 0));
  return Math.floor(s / 60) + ":" + String(s % 60).padStart(2, "0");
};
const button = "min-h-[44px] rounded-xl border border-white/25 px-3 text-sm font-bold disabled:opacity-35 transition-colors hover:border-[#CCFF00]";
const primary = "min-h-[48px] rounded-xl bg-[#CCFF00] text-ink px-4 font-black disabled:opacity-35 flex items-center justify-center gap-2";

function waitForMetadata(video, signal) {
  return new Promise((resolve, reject) => {
    let timer;
    const start = Date.now();
    const stop = () => { clearTimeout(timer); signal.removeEventListener("abort", aborted); };
    const aborted = () => { stop(); reject(new Error("FRAME_SEEK_ABORTED")); };
    const tick = () => {
      if (signal.aborted) return aborted();
      if (video.readyState >= 1 && video.videoWidth > 0 && video.videoHeight > 0 &&
          Number.isFinite(video.duration) && video.duration > 0) {
        stop(); resolve(); return;
      }
      if (Date.now() - start >= 12000) {
        stop(); reject(new Error("Your video could not be opened. Retry, or choose another video.")); return;
      }
      timer = setTimeout(tick, 150);
    };
    signal.addEventListener("abort", aborted, { once: true });
    tick();
  });
}

async function capturePresented(video, target, signal) {
  const frame = await videoFrameAuthority.seekPresentedFrame(video, target, { signal });
  if (signal.aborted) throw new Error("FRAME_SEEK_ABORTED");
  if (!video.videoWidth || !video.videoHeight || video.seeking || video.readyState < 2) {
    throw new Error("Frame not ready");
  }
  const canvas = document.createElement("canvas");
  const w = Math.min(1280, video.videoWidth);
  canvas.width = w;
  canvas.height = Math.round(video.videoHeight * w / video.videoWidth);
  const context = canvas.getContext("2d");
  if (!context) throw new Error("Frame capture unavailable");
  context.drawImage(video, 0, 0, canvas.width, canvas.height);
  const jpegDataUrl = canvas.toDataURL("image/jpeg", 0.82);
  if (!jpegDataUrl.startsWith("data:image/jpeg")) throw new Error("Frame capture unavailable");
  return { t: frame.mediaTime, jpegDataUrl, width: video.videoWidth, height: video.videoHeight };
}

export default function ScoutMode({ open, videoUrl, onCancel, onConfirm }) {
  const videoRef = useRef(null);
  const overlayRef = useRef(null);
  const stageRef = useRef(null);
  const sessionRef = useRef(null);
  const frameRequestRef = useRef(null);
  const actionLock = useRef(false);
  const submitLock = useRef(false);
  const pointers = useRef(new Map());
  const gesture = useRef(null);
  const suppressClick = useRef(false);
  const [retry, setRetry] = useState(0);
  const [phase, setPhase] = useState("BOOTING");
  const [boot, setBoot] = useState({ progress: 0, label: "Preparing your video" });
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [duration, setDuration] = useState(0);
  const [cuts, setCuts] = useState([]);
  const [frames, setFrames] = useState([]);
  const [queue, setQueue] = useState([]);
  const [position, setPosition] = useState(0);
  const [marks, setMarks] = useState({});
  const [verifyMarks, setVerifyMarks] = useState([]);
  const [verifyFrame, setVerifyFrame] = useState(null);
  const [loadedImage, setLoadedImage] = useState(null);
  const [verifyTarget, setVerifyTarget] = useState(0);
  const [draft, setDraft] = useState(null);
  const [frameBusy, setFrameBusy] = useState(false);
  const [hiddenHelp, setHiddenHelp] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [rect, setRect] = useState({ w: 0, h: 0 });

  useEffect(() => {
    if (!open) return undefined;
    const activePointers = pointers.current;
    const controller = new AbortController();
    sessionRef.current = controller;
    frameRequestRef.current = null;
    actionLock.current = false;
    submitLock.current = false;
    setPhase("BOOTING");
    setError(""); setNotice(""); setFrames([]); setQueue([]); setPosition(0);
    setMarks({}); setVerifyMarks([]); setVerifyFrame(null); setLoadedImage(null); setDraft(null);
    setFrameBusy(false); setSubmitting(false); setHiddenHelp(false);
    setZoom(1); setPan({ x: 0, y: 0 });
    const video = videoRef.current;
    (async () => {
      try {
        setBoot({ progress: 0, label: "Preparing your video" });
        videoFrameAuthority.resetPresentedFrame(video);
        video.load();
        await waitForMetadata(video, controller.signal);
        video.pause();
        setDuration(video.duration);
        setBoot({ progress: 0.08, label: "Finding moments across your clip" });
        const detected = await detectSceneCuts(video, {
          samples: 12, signal: controller.signal,
          onProgress: p => { if (!controller.signal.aborted) setBoot({ progress: 0.08 + p * 0.3, label: "Finding moments across your clip" }); },
        });
        if (controller.signal.aborted) return;
        setCuts(detected.cuts);
        const hints = distributeHints(video.duration, detected.cuts, TARGET_TAPS);
        const captured = [];
        for (let i = 0; i < hints.length; i++) {
          if (controller.signal.aborted) return;
          try {
            captured.push(await capturePresented(video, hints[i], controller.signal));
          } catch (e) {
            if (controller.signal.aborted) return;
            captured.push(null); // unreadable pixels never become a tappable frame
          }
          setBoot({ progress: 0.38 + 0.62 * (i + 1) / hints.length, label: "Preparing your " + TARGET_TAPS + " tap moments" });
        }
        if (controller.signal.aborted) return;
        const usable = captured.map((f, i) => f ? i : null).filter(i => i !== null);
        if (usable.length < MIN_TAPS) throw new Error("Not enough frames could be opened. Retry preparing your video.");
        setFrames(captured); setQueue(usable); setPosition(0); setPhase("MARKING");
      } catch (e) {
        if (!controller.signal.aborted) { setError(e.message || "Video unavailable. Please retry."); setPhase("ERROR"); }
      }
    })();
    return () => {
      controller.abort();
      if (sessionRef.current === controller) sessionRef.current = null;
      frameRequestRef.current = null;
      activePointers.clear(); gesture.current = null;
    };
  }, [open, videoUrl, retry]);

  useEffect(() => {
    if (!open) return undefined;
    const previousFocus = document.activeElement;
    overlayRef.current?.querySelector('button')?.focus();
    return () => { if (previousFocus?.isConnected) previousFocus.focus(); };
  }, [open]);

  useEffect(() => {
    if (!open || !stageRef.current) return undefined;
    const el = stageRef.current;
    const measure = () => { const r = el.getBoundingClientRect(); setRect({ w: r.width, h: r.height }); };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(el);
    return () => observer.disconnect();
  }, [open]);

  const current = queue[position];
  const activeFrame = phase === "MARKING" ? frames[current] : verifyFrame;
  const confirmedCount = Object.values(marks).filter(m => policy.validBox(m.box)).length;
  const canTap = !!activeFrame && loadedImage === activeFrame.jpegDataUrl && !frameBusy && !submitting &&
    (phase === "MARKING" || (phase === "VERIFY" && verifyMarks.length < VERIFY_TAPS));
  const hasDraft = canTap && draft?.frame === activeFrame;
  const resetView = useCallback(() => { setZoom(1); setPan({ x: 0, y: 0 }); }, []);

  useEffect(() => {
    actionLock.current = false;
    setDraft(null); setHiddenHelp(false); resetView();
  }, [phase, current, resetView]);

  const handleTap = useCallback(e => {
    if (suppressClick.current) { suppressClick.current = false; return; }
    if (!canTap || hiddenHelp || e.target.closest("button, input, [data-marker-handle]")) return;
    const r = stageRef.current.getBoundingClientRect();
    const point = screenToVideo({ x: e.clientX, y: e.clientY }, r, activeFrame, zoom, pan);
    if (point) setDraft({ box: tapBox(point), frame: activeFrame });
  }, [canTap, hiddenHelp, activeFrame, zoom, pan]);

  const handlePointerDown = useCallback((e, mode = "stage") => {
    if (!canTap || hiddenHelp || (e.button != null && e.button !== 0)) return;
    if (e.target.closest("button, input")) return;
    if (mode !== "stage") e.stopPropagation();
    try { stageRef.current.setPointerCapture(e.pointerId); } catch { /* older devices */ }
    pointers.current.set(e.pointerId, { x: e.clientX, y: e.clientY });
    const values = [...pointers.current.values()];
    if (values.length === 1) {
      suppressClick.current = mode !== "stage";
      gesture.current = { mode, origin: values[0], pan: { ...pan }, zoom, box: draft?.box && { ...draft.box } };
    } else if (values.length === 2) {
      suppressClick.current = true;
      gesture.current = {
        mode: "pinch", distance: Math.hypot(values[1].x - values[0].x, values[1].y - values[0].y),
        midpoint: { x: (values[0].x + values[1].x) / 2, y: (values[0].y + values[1].y) / 2 },
        pan: { ...pan }, zoom,
      };
    }
  }, [canTap, hiddenHelp, pan, zoom, draft]);

  const handlePointerMove = useCallback(e => {
    if (!pointers.current.has(e.pointerId) || !gesture.current) return;
    e.preventDefault();
    pointers.current.set(e.pointerId, { x: e.clientX, y: e.clientY });
    const g = gesture.current;
    const r = stageRef.current.getBoundingClientRect();
    const values = [...pointers.current.values()];
    if (g.mode === "pinch" && values.length === 2 && g.distance > 0) {
      const distance = Math.hypot(values[1].x - values[0].x, values[1].y - values[0].y);
      const z = clamp(g.zoom * distance / g.distance, 1, 5);
      const mid = { x: (values[0].x + values[1].x) / 2, y: (values[0].y + values[1].y) / 2 };
      const px = mid.x - r.left - r.width / 2 - (g.midpoint.x - r.left - r.width / 2 - g.pan.x) * z / g.zoom;
      const py = mid.y - r.top - r.height / 2 - (g.midpoint.y - r.top - r.height / 2 - g.pan.y) * z / g.zoom;
      setZoom(z); setPan({ x: clamp(px, -r.width * (z - 1) / 2, r.width * (z - 1) / 2), y: clamp(py, -r.height * (z - 1) / 2, r.height * (z - 1) / 2) });
      return;
    }
    if (values.length !== 1 || g.mode === "pinch" || !activeFrame) return;
    const dx = e.clientX - g.origin.x, dy = e.clientY - g.origin.y;
    if (Math.hypot(dx, dy) > 6) suppressClick.current = true;
    if (g.mode === "stage") {
      if (zoom > 1) setPan({
        x: clamp(g.pan.x + dx, -r.width * (zoom - 1) / 2, r.width * (zoom - 1) / 2),
        y: clamp(g.pan.y + dy, -r.height * (zoom - 1) / 2, r.height * (zoom - 1) / 2),
      });
    } else if (g.box) {
      const scale = Math.min(r.width / activeFrame.width, r.height / activeFrame.height);
      const fx = dx / (activeFrame.width * scale * zoom), fy = dy / (activeFrame.height * scale * zoom);
      const b = { ...g.box };
      if (g.mode === "move") { b.x = clamp(b.x + fx, 0, 1 - b.w); b.y = clamp(b.y + fy, 0, 1 - b.h); }
      else { b.w = clamp(b.w + fx, 0.02, 1 - b.x); b.h = clamp(b.h + fy, 0.04, 1 - b.y); }
      setDraft({ box: b, frame: activeFrame });
    }
  }, [activeFrame, zoom]);

  const handlePointerUp = useCallback(e => {
    pointers.current.delete(e.pointerId);
    if (!pointers.current.size) gesture.current = null;
    try { stageRef.current.releasePointerCapture(e.pointerId); } catch { /* already released */ }
  }, []);

  const goNext = updated => {
    const progress = markingProgress(queue, current, updated);
    setDraft(null); resetView(); setHiddenHelp(false);
    if (progress.verify) setPhase("VERIFY");
    else {
      setPosition(queue.indexOf(progress.next));
      if (progress.needsVisible) setNotice("We need 3 visible moments. Choose a thumbnail, or use “Hidden” to move to a clearer frame.");
    }
  };
  const confirmMark = () => {
    if (!hasDraft || actionLock.current) return;
    actionLock.current = true;
    const updated = { ...marks, [current]: { t: activeFrame.t, box: { ...draft.box } } };
    setMarks(updated); setNotice("Selection saved."); goNext(updated);
    // A repeated edit may keep the same queue position; release on next render.
    queueMicrotask(() => { actionLock.current = false; });
  };
  const skipMark = () => {
    if (frameBusy || current == null) return;
    const updated = { ...marks, [current]: { skipped: true, t: activeFrame.t } };
    setMarks(updated); setNotice("Not visible — this frame is not an identity anchor."); goNext(updated);
  };

  const loadVerify = useCallback(async target => {
    const session = sessionRef.current;
    if (!session || session.signal.aborted) return;
    const request = {};
    frameRequestRef.current = request;
    setFrameBusy(true); setDraft(null); setVerifyFrame(null); setNotice("");
    const t = clamp(target, 0, Math.max(0, (videoRef.current.duration || 0) - 0.04));
    setVerifyTarget(t);
    try {
      const f = await capturePresented(videoRef.current, t, session.signal);
      if (frameRequestRef.current !== request || session.signal.aborted) return;
      setVerifyFrame(f); setVerifyTarget(f.t);
    } catch {
      if (frameRequestRef.current === request && !session.signal.aborted) setNotice("Frame unavailable. Move the timeline or retry this moment.");
    } finally {
      if (frameRequestRef.current === request && !session.signal.aborted) setFrameBusy(false);
    }
  }, []);

  useEffect(() => {
    if (phase !== "VERIFY") return;
    resetView(); setHiddenHelp(false);
    if (verifyMarks.length < VERIFY_TAPS) loadVerify(verifyTime(duration, verifyMarks.length));
  }, [phase, verifyMarks.length, duration, loadVerify, resetView]);

  const confirmVerify = () => {
    if (!hasDraft || actionLock.current || verifyMarks.length >= VERIFY_TAPS) return;
    if (!distinctVerifyTime(activeFrame.t, verifyMarks)) {
      setNotice("Choose a different moment for this check — at least half a second apart."); return;
    }
    actionLock.current = true;
    // Block the old check frame immediately, before the effect schedules the
    // next one. A fast second tap must not land on the previous check's pixels.
    if (verifyMarks.length + 1 < VERIFY_TAPS) { setVerifyFrame(null); setFrameBusy(true); }
    setVerifyMarks(prev => [...prev, { t: activeFrame.t, box: { ...draft.box }, jpegDataUrl: activeFrame.jpegDataUrl }]);
    setDraft(null); setHiddenHelp(false); setNotice("Extra check saved."); resetView();
    queueMicrotask(() => { actionLock.current = false; });
  };

  const moveNearby = async direction => {
    if (frameBusy || submitting) return;
    const session = sessionRef.current;
    const t = activeFrame?.t ?? verifyTarget;
    const next = nearbyTime(t, direction, duration, cuts);
    if (next === null) { setNotice("This is the edge of this scene. Choose another moment."); return; }
    if (phase === "VERIFY") { await loadVerify(next); return; }
    const index = current;
    const request = {};
    frameRequestRef.current = request;
    setFrameBusy(true); setDraft(null); setNotice("");
    try {
      const frame = await capturePresented(videoRef.current, next, session.signal);
      if (session.signal.aborted || frameRequestRef.current !== request) return;
      setFrames(prev => prev.map((f, i) => i === index ? frame : f));
      setMarks(prev => { const updated = { ...prev }; delete updated[index]; return updated; });
      resetView();
      setNotice("Check this nearby moment. Only confirm when your player is visible.");
    } catch {
      if (!session.signal.aborted) setNotice("Could not open that moment. Your other selections are kept — try the other direction.");
    } finally {
      if (!session.signal.aborted && frameRequestRef.current === request) setFrameBusy(false);
    }
  };

  const submit = async () => {
    if (submitLock.current || verifyMarks.length !== VERIFY_TAPS) return;
    const session = sessionRef.current;
    submitLock.current = true; setSubmitting(true); setNotice("");
    try {
      await onConfirm(buildPayload(frames, marks, verifyMarks, cuts));
    } catch (e) {
      if (!session.signal.aborted) setNotice(e.message || "Your selections could not be saved. Please try again.");
    } finally {
      if (!session.signal.aborted) { submitLock.current = false; setSubmitting(false); }
    }
  };

  if (!open) return null;
  const transform = "scale(" + zoom + ") translate(" + pan.x / zoom + "px," + pan.y / zoom + "px)";
  const done = phase === "VERIFY" && verifyMarks.length === VERIFY_TAPS;
  return createPortal(
    <div ref={overlayRef} role="dialog" aria-modal="true" aria-label="Select your player" data-testid="scout-mode-overlay"
      onKeyDown={e => {
        if (e.key === 'Escape') { e.preventDefault(); onCancel(); }
        if (e.key !== 'Tab') return;
        const controls = [...overlayRef.current.querySelectorAll('button:not(:disabled), input:not(:disabled)')];
        const first = controls[0], last = controls[controls.length - 1];
        if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last?.focus(); }
        if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first?.focus(); }
      }}
      className="fixed inset-0 z-[230] bg-ink text-white flex flex-col" style={{ height: "100dvh", paddingTop: "env(safe-area-inset-top, 0px)" }}>
      <header className="flex-none h-12 flex items-center justify-between px-3 border-b border-white/10">
        <button type="button" aria-label="Close player selection" data-testid="scout-close" onClick={onCancel} className="w-11 h-11 flex items-center justify-center"><X size={22} /></button>
        <span className="text-sm font-black tracking-wide">Select your player</span>
        <span className="text-xs text-white/60">{phase === "VERIFY" ? "2 / 2" : "1 / 2"}</span>
      </header>
      {(phase === "MARKING" || phase === "VERIFY") && (
        <div className="flex-none px-4 py-2.5 flex justify-between gap-2 items-center bg-white/5">
          <div>
            <p className="text-sm font-bold">{phase === "MARKING" ? "Tap your player in the clear moments" : done ? "Your selections are ready" : "3 extra checks across the clip"}</p>
            <p className="text-[11px] text-white/60">{hasDraft ? "Drag or resize the box to fit your player." : "Pinch to zoom · drag to pan · tap to select"}</p>
          </div>
          <span data-testid={phase === "MARKING" ? "scout-progress-counter" : "scout-verify-counter"} className="text-[#CCFF00] text-xl font-black tabular-nums whitespace-nowrap">
            {phase === "MARKING" ? confirmedCount + "/" + queue.length : verifyMarks.length + "/3"}
          </span>
        </div>
      )}
      <div ref={stageRef} data-testid="scout-stage" className="relative flex-1 min-h-0 overflow-hidden bg-black"
        aria-busy={frameBusy || phase === "BOOTING" || (!!activeFrame && loadedImage !== activeFrame.jpegDataUrl)} onClick={handleTap} onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove} onPointerUp={handlePointerUp} onPointerCancel={handlePointerUp}
        style={{ touchAction: "none" }}>
        <video ref={videoRef} src={videoUrl} playsInline muted crossOrigin="anonymous" preload="auto" data-testid="scout-video"
          className="absolute inset-0 w-full h-full object-contain" style={{ pointerEvents: "none" }} />
        {activeFrame && (
          <img key={activeFrame.jpegDataUrl} src={activeFrame.jpegDataUrl} alt="The exact video frame for this tap" draggable={false}
            onLoad={() => setLoadedImage(activeFrame.jpegDataUrl)}
            data-testid="scout-presented-frame" data-frame-time={activeFrame.t}
            className="absolute inset-0 w-full h-full object-contain select-none"
            style={{ transform, transformOrigin: "center center", pointerEvents: "none" }} />
        )}
        {activeFrame && !frameBusy && (
          <span className="absolute top-2 left-3 bg-black/70 px-2 py-1 rounded-lg text-xs text-white/80 pointer-events-none">{fmt(activeFrame.t)}</span>
        )}
        {hasDraft && rect.w > 0 && <DraftMarker box={draft.box} frame={activeFrame} rect={rect} zoom={zoom} pan={pan} onPointerDown={handlePointerDown} />}
        {phase === "BOOTING" && (
          <div className="absolute inset-0 bg-ink flex flex-col items-center justify-center gap-4 px-8 text-center">
            <Loader2 className="animate-spin text-[#CCFF00]" size={42} />
            <p className="text-lg font-bold" role="status">{boot.label}</p>
            <div role="progressbar" aria-label="Preparing tap moments" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(boot.progress * 100)}
              className="w-full max-w-xs h-2 rounded-full bg-white/15 overflow-hidden">
              <div className="h-full bg-[#CCFF00]" style={{ width: Math.round(boot.progress * 100) + "%" }} />
            </div>
            <p className="text-xs text-white/60">Up to 10 guided taps, then 3 extra checks. Your analysis has not started.</p>
          </div>
        )}
        {phase === "ERROR" && (
          <div className="absolute inset-0 bg-ink flex flex-col items-center justify-center gap-5 px-6 text-center">
            <p role="alert">{error}</p>
            <button type="button" data-testid="scout-retry" className={primary} onClick={() => setRetry(n => n + 1)}>Retry preparing video</button>
          </div>
        )}
        {frameBusy && <div role="status" className="absolute inset-0 flex items-center justify-center bg-black/65 pointer-events-none"><Loader2 className="animate-spin text-[#CCFF00]" size={32} /></div>}
      </div>

      {phase === "MARKING" && (
        <div data-testid="scout-frame-strip" className="flex-none flex gap-1.5 overflow-x-auto px-3 py-2 bg-ink" style={{ touchAction: "pan-x" }}>
          {queue.map((i, pos) => (
            <button key={i} type="button" disabled={frameBusy} data-testid={"scout-frame-strip-" + pos}
              aria-label={"Moment " + (pos + 1) + (marks[i]?.box ? ", selected" : marks[i]?.skipped ? ", not visible" : ", pending")}
              onClick={() => { setPosition(pos); setDraft(null); setHiddenHelp(false); resetView(); }}
              className={"relative flex-none w-12 h-12 border-2 rounded-lg overflow-hidden " + (pos === position ? "border-[#CCFF00]" : "border-white/25")}>
              {marks[i]?.box ? <MarkedCropCanvas frameDataUrl={frames[i].jpegDataUrl} box={marks[i].box} className="w-full h-full" width={96} height={96} /> :
                <img src={frames[i].jpegDataUrl} alt="" className={"w-full h-full object-cover " + (marks[i]?.skipped ? "opacity-40" : "")} />}
              <span className="absolute bottom-0 left-0 right-0 bg-black/70 text-[9px]">{marks[i]?.box ? "✓ " : ""}{pos + 1}</span>
            </button>
          ))}
        </div>
      )}
      {(phase === "MARKING" || phase === "VERIFY") && (
        <footer className="flex-none px-3 pt-2 bg-ink border-t border-white/10 space-y-2"
          style={{ paddingBottom: "max(12px, env(safe-area-inset-bottom, 0px))" }}>
          {notice && <p role="status" data-testid="scout-notice" className="text-[12px] text-white/85">{notice}</p>}
          {hasDraft && (
            <div data-testid="scout-selection-preview" className="flex items-center gap-3">
              <div className="w-16 h-20 flex-none rounded-xl border-2 border-[#CCFF00] overflow-hidden">
                <MarkedCropCanvas frameDataUrl={activeFrame.jpegDataUrl} box={draft.box} width={128} height={160} className="w-full h-full" />
              </div>
              <div className="flex-1 min-w-0">
                <p className="font-bold text-sm text-[#CCFF00]">Your selected player</p>
                <p className="text-[11px] text-white/60">Check the crop. Keep only your player inside the box.</p>
                <div className="flex gap-2 mt-2">
                  <button type="button" data-testid="scout-retap" className={button} onClick={() => setDraft(null)}><RotateCcw size={15} className="inline mr-1" />Re-tap</button>
                  <button type="button" data-testid={phase === "MARKING" ? "scout-confirm-mark" : "scout-verify-confirm"} className={primary + " flex-1"}
                    disabled={submitting || actionLock.current} onClick={phase === "MARKING" ? confirmMark : confirmVerify}><Check size={18} />Confirm</button>
                </div>
              </div>
            </div>
          )}
          {!hasDraft && phase === "VERIFY" && !done && (
            <div className="flex items-center gap-2">
              <button type="button" aria-label="Previous second" data-testid="scout-verify-back1" className={button} onClick={() => loadVerify(verifyTarget - 1)}>−1s</button>
              <input type="range" aria-label="Choose a clear check moment" data-testid="scout-verify-scrub" min={0} max={Math.max(0, duration - 0.04)} step={0.04}
                value={verifyTarget} onChange={e => loadVerify(Number(e.target.value))} className="flex-1 min-w-0 h-11" style={{ accentColor: "#CCFF00" }} />
              <button type="button" aria-label="Next second" data-testid="scout-verify-fwd1" className={button} onClick={() => loadVerify(verifyTarget + 1)}>+1s</button>
              {!verifyFrame && !frameBusy && <button type="button" className={button} onClick={() => loadVerify(verifyTarget)}>Retry</button>}
            </div>
          )}
          {!done && (
            <div className="flex justify-between items-center gap-2">
              <button type="button" data-testid="scout-hidden-player" className={button + " flex items-center gap-1.5"} disabled={frameBusy}
                aria-expanded={hiddenHelp} onClick={() => { setHiddenHelp(v => !v); setDraft(null); }}>
                <EyeOff size={16} />Hidden?
              </button>
              <div className="flex items-center gap-1">
                <button type="button" aria-label="Zoom out" data-testid="scout-zoom-out" className={button} disabled={zoom <= 1} onClick={() => { setZoom(z => Math.max(1, z / 1.4)); setPan({ x: 0, y: 0 }); }}><ZoomOut size={18} /></button>
                <button type="button" aria-label="Reset zoom" data-testid="scout-zoom-reset" className={button + " tabular-nums"} onClick={resetView}>{zoom.toFixed(1)}×</button>
                <button type="button" aria-label="Zoom in" data-testid="scout-zoom-in" className={button} disabled={zoom >= 5} onClick={() => setZoom(z => Math.min(5, z * 1.4))}><ZoomIn size={18} /></button>
              </div>
            </div>
          )}
          {hiddenHelp && !done && (
            <div data-testid="scout-hidden-help" className="rounded-xl bg-white/5 border border-white/15 p-3 space-y-2">
              <p className="text-sm font-bold">Behind another player?</p>
              <p className="text-[11px] text-white/70">Do not mark the player in front. Move to a nearby clear frame, then tap your player. If still hidden, skip this moment.</p>
              <div className="flex gap-2">
                <button type="button" data-testid="scout-nearby-earlier" disabled={frameBusy} className={button + " flex-1"} onClick={() => moveNearby(-1)}><ChevronLeft size={14} className="inline" />0.5s earlier</button>
                <button type="button" data-testid="scout-nearby-later" disabled={frameBusy} className={button + " flex-1"} onClick={() => moveNearby(1)}>0.5s later<ChevronRight size={14} className="inline" /></button>
              </div>
              {phase === "MARKING" && <button type="button" data-testid="scout-skip-frame" disabled={frameBusy} className={button + " w-full"} onClick={skipMark}>Not visible — skip this moment</button>}
              {phase === "VERIFY" && <button type="button" className={button + " w-full"} onClick={() => { setHiddenHelp(false); loadVerify(clamp(verifyTarget + 2, 0, duration - 0.04)); }}>Try another check moment</button>}
              <button type="button" className="w-full min-h-[44px] text-[#CCFF00] text-sm font-bold" onClick={() => setHiddenHelp(false)}>Player visible — tap now</button>
            </div>
          )}
          {phase === "MARKING" && !hasDraft && !hiddenHelp && confirmedCount >= MIN_TAPS && (
            <button type="button" data-testid="scout-finish-early" className={button + " w-full text-[#CCFF00]"} onClick={() => { setNotice(""); setPhase("VERIFY"); }}>Continue to 3 extra checks · {confirmedCount} selected</button>
          )}
          {done && (
            <>
              <div className="flex justify-center gap-3" data-testid="scout-verify-done">
                {verifyMarks.map((m, i) => <div key={i} className="w-14 h-16 border border-[#CCFF00] rounded-lg overflow-hidden"><MarkedCropCanvas frameDataUrl={m.jpegDataUrl} box={m.box} width={112} height={128} className="w-full h-full" /></div>)}
              </div>
              <button type="button" data-testid="scout-submit" disabled={submitting} className={primary + " w-full"} onClick={submit}>
                {submitting ? <Loader2 size={18} className="animate-spin" /> : <Check size={18} />}
                {submitting ? "Saving your selections…" : "Use " + (confirmedCount + VERIFY_TAPS) + " player selections"}
              </button>
              <button type="button" className="w-full min-h-[44px] text-xs text-white/60" disabled={submitting} onClick={() => setVerifyMarks(prev => prev.slice(0, -1))}>Redo last check</button>
            </>
          )}
        </footer>
      )}
    </div>, document.body,
  );
}

function DraftMarker({ box, frame, rect, zoom, pan, onPointerDown }) {
  const scale = Math.min(rect.w / frame.width, rect.h / frame.height);
  const rw = frame.width * scale, rh = frame.height * scale;
  const x = ((rect.w - rw) / 2 + box.x * rw - rect.w / 2) * zoom + rect.w / 2 + pan.x;
  const y = ((rect.h - rh) / 2 + box.y * rh - rect.h / 2) * zoom + rect.h / 2 + pan.y;
  const width = box.w * rw * zoom, height = box.h * rh * zoom;
  return (
    <>
      <div data-testid="scout-draft-marker" data-marker-handle="move" onPointerDown={e => onPointerDown(e, "move")}
        style={{ position: "absolute", left: x, top: y, width, height, border: "3px solid #CCFF00", borderRadius: 8,
          boxShadow: "0 0 0 100vmax rgba(0,0,0,0.32), 0 0 18px rgba(204,255,0,0.7)", cursor: "move", zIndex: 10, touchAction: "none" }} />
      <div role="presentation" data-testid="scout-draft-resize" data-marker-handle="resize" onPointerDown={e => onPointerDown(e, "resize")}
        style={{ position: "absolute", left: x + width - 22, top: y + height - 22, width: 44, height: 44, zIndex: 11, cursor: "nwse-resize", touchAction: "none", display: "grid", placeItems: "center" }}>
        <span style={{ width: 18, height: 18, borderRadius: 5, background: "#CCFF00", border: "2px solid #0A0F0D" }} />
      </div>
    </>
  );
}
