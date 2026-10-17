/**
 * The sole player-selection workflow: up to ten visible, human-confirmed
 * moments in one workflow, then automatic analysis. No detector guesses or hidden
 * manual editor. Every box stays bound to the exact displayed still frame.
 */
import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Check, X, RotateCcw, ZoomIn, ZoomOut, ChevronRight, Loader2, ScanLine, SlidersHorizontal, HelpCircle, ArrowRight, CheckCircle2 } from "lucide-react";
import MarkedCropCanvas from "../MarkedCropCanvas";
import { detectSceneCuts, selectTapHints } from "./sceneDetect";
import videoFrameAuthority from "./videoFrameAuthority.cjs";
import policy from "./scoutTapPolicy.cjs";
import selection from "./selectionHints.cjs";
import "./ScoutMode.css";

const { TARGET_TAPS, MIN_TAPS, screenToVideo, tapBox, markingProgress, nearbyTime, nearbyMoments, resizeBox, buildPayload } = policy;
const clamp = (n, lo, hi) => Math.max(lo, Math.min(hi, n));
const insideBox = (point, box) => !!point && !!box && point.x >= box.x && point.x <= box.x + box.w && point.y >= box.y && point.y <= box.y + box.h;
const fmt = t => {
  const s = Math.floor(Math.max(0, t || 0));
  return Math.floor(s / 60) + ":" + String(s % 60).padStart(2, "0");
};
const button = "min-h-[44px] rounded-xl border border-white/15 bg-white/[.035] px-3 text-sm font-semibold disabled:opacity-35 transition-colors hover:border-[#CCFF00]/60 focus-visible:outline focus-visible:outline-2 focus-visible:outline-[#CCFF00]";
const primary = "min-h-[52px] rounded-2xl bg-[#CCFF00] text-[#10150a] px-4 font-bold disabled:opacity-35 flex items-center justify-center gap-2 transition-colors hover:bg-[#dcff60] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#CCFF00]";

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

export default function ScoutMode({ open, videoUrl, onCancel, onConfirm, requestMask, requestTracking }) {
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
  const [loadedImage, setLoadedImage] = useState(null);
  const [draft, setDraft] = useState(null);
  const [frameBusy, setFrameBusy] = useState(false);
  const [hiddenHelp, setHiddenHelp] = useState(false);
  const [partial, setPartial] = useState(false);
  const [tapIntent, setTapIntent] = useState("target");
  const [refine, setRefine] = useState(false);
  const [advanced, setAdvanced] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [nearby, setNearby] = useState(null);
  const [link, setLink] = useState(null);
  const [maskBusy, setMaskBusy] = useState(false);
  const [preview, setPreview] = useState(null);
  const [previewIndex, setPreviewIndex] = useState(0);
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
    setMarks({}); setLoadedImage(null); setDraft(null);
    setFrameBusy(false); setSubmitting(false); setHiddenHelp(false); setPartial(false); setTapIntent("target"); setLink(null); setPreview(null);
    setZoom(1); setPan({ x: 0, y: 0 }); setRefine(false); setAdvanced(false); setNearby(null); setDragging(false);
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
          samples: Math.min(32, Math.max(12, Math.ceil(video.duration / 3))), signal: controller.signal,
          onProgress: p => { if (!controller.signal.aborted) setBoot({ progress: 0.08 + p * 0.3, label: "Finding moments across your clip" }); },
        });
        if (controller.signal.aborted) return;
        setCuts(detected.cuts);
        const hints = policy.prioritizeTapMoments(selectTapHints(video.duration, detected.cuts, detected.qualitySamples, TARGET_TAPS), video.duration);
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
  const activeFrame = preview?.frames[previewIndex] || link?.frame || frames[current];
  const confirmedCount = Object.values(marks).filter(m => policy.validBox(m.box)).length;
  const fullCount = Object.values(marks).filter(m => policy.validBox(m.box) && m.visibility !== "partial").length;
  const canTap = !!activeFrame && loadedImage === activeFrame.jpegDataUrl && !frameBusy && !submitting && !preview &&
    phase === "MARKING";
  const hasDraft = !!draft && draft.frame === activeFrame;
  const hasVisibleTarget = insideBox(draft?.target_point, draft?.box);
  const maskDataUrl = useMemo(() => selection.maskImage(draft?.visible_mask), [draft?.visible_mask]);
  const maskKey = draft ? JSON.stringify([draft.box, draft.target_point, draft.exclude_points, draft.include_points, draft.player_behind, draft.visibility, draft.manualBox]) : "";
  useEffect(() => {
    if (!requestMask || !draft?.maskRequested || !hasVisibleTarget || !canTap || dragging || draft.visible_mask || draft.maskDeclined === maskKey) { setMaskBusy(false); return undefined; }
    const controller = new AbortController();
    const captured = draft;
    setMaskBusy(true);
    const timer = setTimeout(async () => {
      try {
        const result = await requestMask(captured.frame, captured, controller.signal);
        const suggested = result?.mask || result;
        const mask = selection.validMask(suggested) && ["native_person_instance", "native_person_prompt"].includes(suggested.method) ? suggested : undefined;
        const box = mask && policy.validBox(result?.box) ? result.box : captured.box;
        if (!controller.signal.aborted) {
          setDraft(prev => prev?.frame === captured.frame && JSON.stringify([prev.box, prev.target_point, prev.exclude_points, prev.include_points, prev.player_behind, prev.visibility, prev.manualBox]) === maskKey
            ? { ...prev, box, visible_mask: mask, maskRequested: !!mask } : prev);
          if (!mask) setNotice(captured.player_behind ? "Could not isolate the player behind. Tap a visible part, mark the player in front, or choose a clearer moment." : "Player outline unclear. Adjust the box or use a clearer moment.");
        }
      } catch {
        if (!controller.signal.aborted) {
          setDraft(prev => prev?.frame === captured.frame && JSON.stringify([prev.box, prev.target_point, prev.exclude_points, prev.include_points, prev.player_behind, prev.visibility, prev.manualBox]) === maskKey
            ? { ...prev, maskRequested: false } : prev);
          setNotice("Your selection is kept. Adjust the box or choose a clearer moment.");
        }
      } finally { if (!controller.signal.aborted) setMaskBusy(false); }
    }, 250);
    return () => { clearTimeout(timer); controller.abort(); };
    // Keyed only to the frame and human inputs, never to the returned mask.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [requestMask, maskKey, activeFrame, canTap, draft?.maskRequested, hasVisibleTarget, dragging]);
  const outlinePending = !!requestMask && !!draft?.maskRequested && hasVisibleTarget && !draft?.visible_mask && draft?.maskDeclined !== maskKey;
  const outlineBusy = maskBusy || outlinePending;
  const resetView = useCallback(() => { setZoom(1); setPan({ x: 0, y: 0 }); }, []);

  useEffect(() => {
    actionLock.current = false;
    setDraft(null); setHiddenHelp(false); setPartial(false); setTapIntent("target"); setRefine(false); setAdvanced(false); setNearby(null); setLink(null); setPreview(null); resetView();
  }, [phase, current, resetView]);

  const handleTap = useCallback(e => {
    if (suppressClick.current) { suppressClick.current = false; return; }
    if (!canTap || hiddenHelp || nearby || e.target.closest("button, input, [data-marker-handle]")) return;
    const r = stageRef.current.getBoundingClientRect();
    const point = screenToVideo({ x: e.clientX, y: e.clientY }, r, activeFrame, zoom, pan);
    if (!point) return;
    if (requestMask && draft?.maskRequested && tapIntent !== "target") setMaskBusy(true);
    if ((tapIntent === "behind" || (!hasVisibleTarget && tapIntent === "target")) && hasDraft) {
      if (point.x < draft.box.x || point.x > draft.box.x + draft.box.w || point.y < draft.box.y || point.y > draft.box.y + draft.box.h) {
        setNotice("Tap a visible part inside your marked area, or enlarge the box."); return;
      }
      setDraft(prev => ({ ...prev, target_point: point, include_points: [], visible_mask: undefined, maskRequested: true, maskDeclined: undefined }));
      setTapIntent("target"); setNotice(draft.player_behind ? "Finding only the visible parts of your player behind." : "Finding your player’s outline at your new tap.");
    } else if (tapIntent === "include" && hasDraft) {
      const b = draft.box, pad = .005;
      const x = Math.max(0, Math.min(b.x, point.x - pad)), y = Math.max(0, Math.min(b.y, point.y - pad));
      const right = Math.min(1, Math.max(b.x + b.w, point.x + pad)), bottom = Math.min(1, Math.max(b.y + b.h, point.y + pad));
      setDraft(prev => ({ ...prev, box: { x, y, w: right - x, h: bottom - y }, target_point: prev.target_point || point, include_points: [...(prev.include_points || []), point].slice(-4), visible_mask: undefined, maskRequested: true, maskDeclined: undefined, continuity: undefined, tracking_check: undefined }));
      setTapIntent("target"); setNotice("Visible body part added. Check the updated cutout.");
    } else if (tapIntent === "exclude" && hasDraft) {
      const inside = point.x >= draft.box.x && point.x <= draft.box.x + draft.box.w && point.y >= draft.box.y && point.y <= draft.box.y + draft.box.h;
      setDraft(prev => ({ ...prev, exclude_points: [...(prev.exclude_points || []), point].slice(-4), visible_mask: undefined, maskRequested: true, maskDeclined: undefined, tracking_check: undefined,
        ...(inside ? { visibility: "partial", player_behind: true, continuity: undefined } : {}) }));
      if (inside) setPartial(true);
      setTapIntent("target"); setNotice("Opponent marked in red. Check that the cutout keeps only your player.");
    } else if (!hasDraft) {
      setDraft({ box: tapBox(point), frame: activeFrame, target_point: point, maskRequested: true,
        ...(partial && !link ? { visibility: "partial", player_behind: true, manualBox: true } : {}) });
    }
  }, [canTap, hiddenHelp, nearby, activeFrame, zoom, pan, tapIntent, hasDraft, hasVisibleTarget, partial, link, draft, requestMask]);

  const handlePointerDown = useCallback((e, mode = "stage") => {
    if (!canTap || hiddenHelp || nearby || (["include", "exclude"].includes(tapIntent)) || (e.button != null && e.button !== 0)) return;
    if (mode !== "stage" && !refine) return;
    if (e.target.closest("button, input")) return;
    if (mode !== "stage") e.stopPropagation();
    try { stageRef.current.setPointerCapture(e.pointerId); } catch { /* older devices */ }
    pointers.current.set(e.pointerId, { x: e.clientX, y: e.clientY });
    const values = [...pointers.current.values()];
    if (values.length === 1) {
      suppressClick.current = mode !== "stage";
      if (mode !== "stage") setDragging(true);
      gesture.current = { mode, origin: values[0], pan: { ...pan }, zoom, box: draft?.box && { ...draft.box } };
    } else if (values.length === 2) {
      suppressClick.current = true;
      gesture.current = {
        mode: "pinch", distance: Math.hypot(values[1].x - values[0].x, values[1].y - values[0].y),
        midpoint: { x: (values[0].x + values[1].x) / 2, y: (values[0].y + values[1].y) / 2 },
        pan: { ...pan }, zoom,
      };
    }
  }, [canTap, hiddenHelp, nearby, pan, zoom, draft, tapIntent, refine]);

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
      if (zoom > 1 && !draft) setPan({
        x: clamp(g.pan.x + dx, -r.width * (zoom - 1) / 2, r.width * (zoom - 1) / 2),
        y: clamp(g.pan.y + dy, -r.height * (zoom - 1) / 2, r.height * (zoom - 1) / 2),
      });
    } else if (g.box) {
      const scale = Math.min(r.width / activeFrame.width, r.height / activeFrame.height);
      const fx = dx / (activeFrame.width * scale * zoom), fy = dy / (activeFrame.height * scale * zoom);
      let b = { ...g.box };
      if (g.mode === "move") { b.x = clamp(b.x + fx, 0, 1 - b.w); b.y = clamp(b.y + fy, 0, 1 - b.h); }
      else b = resizeBox(g.box, g.mode.replace("resize-", ""), fx, fy);
      setDraft(prev => ({ ...prev, box: b, manualBox: true, frame: activeFrame, visible_mask: undefined, maskRequested: true, maskDeclined: undefined, continuity: undefined, tracking_check: undefined }));
    }
  }, [activeFrame, zoom, draft]);

  const handlePointerUp = useCallback(e => {
    pointers.current.delete(e.pointerId);
    if (!pointers.current.size) { gesture.current = null; setDragging(false); }
    try { stageRef.current.releasePointerCapture(e.pointerId); } catch { /* already released */ }
  }, []);

  const editSelection = () => {
    if (!hasDraft) return;
    setRefine(v => !v); setTapIntent("target"); setHiddenHelp(false); setAdvanced(false);
    if (!refine && rect.w && rect.h) {
      const scale = Math.min(rect.w / activeFrame.width, rect.h / activeFrame.height);
      const z = clamp(Math.min(rect.w * .6 / (draft.box.w * activeFrame.width * scale), rect.h * .65 / (draft.box.h * activeFrame.height * scale)), 1, 5);
      setZoom(z);
      setPan({ x: clamp((.5 - draft.box.x - draft.box.w / 2) * activeFrame.width * scale * z, -rect.w * (z - 1) / 2, rect.w * (z - 1) / 2),
        y: clamp((.5 - draft.box.y - draft.box.h / 2) * activeFrame.height * scale * z, -rect.h * (z - 1) / 2, rect.h * (z - 1) / 2) });
    }
  };
  const choosePartial = () => {
    setPartial(true); setHiddenHelp(false); setRefine(true); setAdvanced(true);
    setTapIntent(hasDraft ? "behind" : "target");
    if (hasDraft) setDraft(prev => ({ ...prev, player_behind: true, visibility: "partial", manualBox: true,
      target_point: undefined, include_points: [], visible_mask: undefined, maskRequested: true, maskDeclined: undefined, continuity: undefined, tracking_check: undefined }));
    setNotice("Tap a visible part of YOUR player. Do not mark the player in front.");
  };
  const chooseVisible = () => {
    setPartial(false); setHiddenHelp(false); setTapIntent("target");
    if (draft?.player_behind) setDraft(prev => ({ ...prev, player_behind: undefined, visibility: undefined,
      exclude_points: [], include_points: [], visible_mask: undefined, maskRequested: true, maskDeclined: undefined, continuity: undefined, tracking_check: undefined }));
    setNotice("");
  };
  const openNearby = async () => {
    if (frameBusy || submitting || !activeFrame || link || preview) return;
    const base = activeFrame, session = sessionRef.current, index = current;
    const request = {};
    frameRequestRef.current = request;
    setFrameBusy(true); setHiddenHelp(false);
    try {
      const candidates = [];
      const segment = t => cuts.filter(c => t >= c).length;
      for (const t of nearbyMoments(base.t, duration, cuts)) {
        let f;
        try { f = t === base.t ? base : await capturePresented(videoRef.current, t, session.signal); }
        catch (e) { if (session.signal.aborted) throw e; else continue; }
        if (session.signal.aborted || frameRequestRef.current !== request) return;
        if (segment(f.t) === segment(base.t) && !candidates.some(c => Math.abs(c.t - f.t) < .02)) candidates.push(f);
      }
      setNearby({ index, frames: candidates, base });
    } catch { if (!session.signal.aborted) setNotice("Could not open nearby moments. Your selection is kept."); }
    finally { if (!session.signal.aborted && frameRequestRef.current === request) setFrameBusy(false); }
  };
  const chooseNearby = frame => {
    if (!nearby || frameBusy || nearby.index !== current) return;
    if (frame !== activeFrame) {
      setFrames(prev => prev.map((f, i) => i === current ? frame : f));
      setMarks(prev => { const updated = { ...prev }; delete updated[current]; return updated; });
      setDraft(null); setPartial(false); setRefine(false); setAdvanced(false); setTapIntent("target"); resetView();
    }
    setNearby(null); setNotice("Tap your player in this moment.");
  };

  const goNext = updated => {
    const progress = markingProgress(queue, current, updated);
    setDraft(null); resetView(); setHiddenHelp(false); setPartial(false); setTapIntent("target"); setRefine(false); setAdvanced(false); setNearby(null);
    if (progress.ready) setPhase("READY");
    else {
      setPosition(queue.indexOf(progress.next));
      if (progress.needsVisible) setNotice("We need 3 visible moments with the full player. Use a clearer frame for the remaining selections.");
    }
  };
  const confirmMark = () => {
    if (!canTap || !hasDraft || !hasVisibleTarget || actionLock.current || link || outlineBusy || dragging || (requestMask && draft.player_behind && !draft.visible_mask)) return;
    actionLock.current = true;
    const updated = { ...marks, [current]: { t: activeFrame.t, box: { ...draft.box }, ...selection.hints(draft),
      ...(draft.continuity?.length ? { continuity: draft.continuity } : {}) } };
    setMarks(updated); setNotice("Selection saved."); goNext(updated);
    // A repeated edit may keep the same queue position; release on next render.
    queueMicrotask(() => { actionLock.current = false; });
  };
  const skipMark = () => {
    if (frameBusy || current == null) return;
    const updated = { ...marks, [current]: { skipped: true, t: activeFrame.t } };
    setMarks(updated); setNotice("Not visible — this frame is not an identity anchor."); goNext(updated);
  };


  const startLink = async direction => {
    if (!hasDraft || frameBusy || link || outlineBusy || phase !== "MARKING") return;
    const next = nearbyTime(activeFrame.t, direction, duration, cuts);
    if (next === null || Math.abs(next - activeFrame.t) < 0.02) { setNotice("No nearby frame in this scene. Try the other direction."); return; }
    const session = sessionRef.current, base = { draft, frame: activeFrame };
    setFrameBusy(true);
    try {
      const frame = await capturePresented(videoRef.current, next, session.signal);
      if (session.signal.aborted) return;
      if (cuts.filter(c => frame.t >= c).length !== cuts.filter(c => base.frame.t >= c).length) {
        setNotice("That frame is across a scene cut. Choose another direction."); return;
      }
      setLink({ ...base, frame, baseFrame: base.frame }); setDraft(null); setPartial(false); setTapIntent("target"); resetView();
      setNotice("Tap the SAME player in this nearby frame. Confirm only if he is clearly visible.");
    } catch { if (!session.signal.aborted) setNotice("Could not open the nearby frame. Your selection is kept."); }
    finally { if (!session.signal.aborted) setFrameBusy(false); }
  };
  const finishLink = accept => {
    if (!link || frameBusy || outlineBusy || (accept && (!hasDraft || !hasVisibleTarget))) return;
    if (accept && draft.visibility === "partial") { setNotice("Choose a nearby frame where the same player is fully visible."); return; }
    const linked = accept ? { t: activeFrame.t, box: { ...draft.box }, ...selection.hints(draft), same_player: true } : null;
    const restored = { ...link.draft, ...(linked ? { continuity: [...(link.draft.continuity || []).filter(c => Math.abs(c.t - linked.t) > 0.02), linked].slice(-2) } : {}) };
    setDraft(restored); setPartial(restored.visibility === "partial"); setLink(null); setTapIntent("target"); resetView();
    setNotice(accept ? "Same player confirmed at both marked moments. Hidden frames remain uncertain." : "Nearby check cancelled. Your selection is kept.");
  };

  const startPreview = async () => {
    if (!requestTracking || !hasDraft || draft.visibility === "partial" || outlineBusy || link) return;
    const session = sessionRef.current, captured = draft, base = activeFrame;
    const segment = time => cuts.filter(c => time >= c).length;
    const samples = [base];
    setFrameBusy(true); setNotice("Preparing a short tracking check…");
    try {
      for (const delta of [0.125, 0.25, 0.375, 0.5]) {
        if (base.t + delta >= duration - 0.04 || segment(base.t + delta) !== segment(base.t)) break;
        const frame = await capturePresented(videoRef.current, base.t + delta, session.signal);
        if (segment(frame.t) !== segment(base.t) || frame.t <= samples[samples.length - 1].t) break;
        samples.push(frame);
      }
      if (samples.length < 3) throw new Error("Too close to a cut or the end. Use a clearer moment.");
      const result = await requestTracking(samples, captured, session.signal);
      if (session.signal.aborted) return;
      // Dense backend cut detection can find boundaries missed by the coarse
      // initial scene samples. Never loop or link across a reported cut.
      const cutIndex = result.findIndex(r => r.status === "scene_cut");
      const end = cutIndex < 0 ? samples.length : cutIndex;
      if (end < 3) {
        setNotice("The video cuts here. Choose an earlier moment in this scene for a tracking check. Your selection is kept.");
        return;
      }
      setPreview({ frames: samples.slice(0, end), results: result.slice(0, end), draft: captured, baseFrame: base }); setPreviewIndex(0); resetView();
      setNotice(cutIndex < 0 ? "Watch the box. This is a provisional tracking check, not verified match evidence." : "This check stops before a video cut. Watch the box on your player.");
    } catch (e) { if (!session.signal.aborted) setNotice(e.message || "Tracking check unavailable. Your selection is kept."); }
    finally { if (!session.signal.aborted) setFrameBusy(false); }
  };
  useEffect(() => {
    if (!preview) return undefined;
    const timer = setInterval(() => setPreviewIndex(i => (i + 1) % preview.frames.length), 400);
    return () => clearInterval(timer);
  }, [preview]);
  const finishPreview = approve => {
    if (!preview) return;
    setDraft({ ...preview.draft, ...(approve ? { tracking_check: { status: "user_confirmed", start: preview.frames[0].t, end: preview.frames[preview.frames.length - 1].t } } : {}) });
    setPreview(null); resetView();
    setNotice(approve ? "Short tracking check approved. Confirm your selection to save it." : "Check closed. Your selection is kept.");
  };
  const correctPreview = index => {
    if (!preview || index === 0 || phase !== "MARKING") return;
    const captured = preview;
    setLink({ draft: captured.draft, frame: captured.frames[index], baseFrame: captured.baseFrame });
    setPreview(null); setDraft(null); setPartial(false); setTapIntent("target"); resetView();
    setNotice("Tap your actual player here, then confirm Same player. No suggested tracking box is saved as a human tap.");
  };

  const submit = async () => {
    if (submitLock.current || phase !== "READY" || fullCount < MIN_TAPS) return;
    const session = sessionRef.current;
    submitLock.current = true; setSubmitting(true); setNotice("");
    try {
      await onConfirm(buildPayload(frames, marks, [], cuts));
    } catch (e) {
      if (!session.signal.aborted) setNotice(e.message || "Your selections could not be saved. Please try again.");
    } finally {
      if (!session.signal.aborted) { submitLock.current = false; setSubmitting(false); }
    }
  };

  if (!open) return null;
  const transform = "scale(" + zoom + ") translate(" + pan.x / zoom + "px," + pan.y / zoom + "px)";
  const done = phase === "READY";
  return createPortal(
    <div ref={overlayRef} role="dialog" aria-modal="true" aria-label="Select your player" data-testid="scout-mode-overlay"
      onKeyDown={e => {
        if (e.key === 'Escape') { e.preventDefault(); onCancel(); }
        if (e.key !== 'Tab') return;
        const controls = [...overlayRef.current.querySelectorAll('button:not(:disabled), input:not(:disabled), [tabindex="0"]')];
        const first = controls[0], last = controls[controls.length - 1];
        if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last?.focus(); }
        if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first?.focus(); }
      }} className="scout-editor">
      <header className="scout-header">
        <button type="button" aria-label="Close player selection" data-testid="scout-close" onClick={onCancel} className="scout-icon"><X size={21} /></button>
        <span className="scout-wordmark"><ScanLine size={17} /> PLAYER SELECT</span>
        <span className="scout-step">SCOUTMEPLAY</span>
      </header>
      {(phase === "MARKING" || done) && <div className="scout-instruction">
        <div>
          <span className="scout-eyebrow">{done ? "READY TO GO" : refine ? "FINE-TUNE" : hasDraft ? "YOUR PLAYER" : "ONE PLAYER. ONE TAP."}</span>
          <h2>{done ? "Looking good." : refine ? "Make it a perfect fit." : hasDraft ? "Is this your player?" : "Select your player."}</h2>
          <p>{done ? "Your references are ready for analysis." : refine ? "Drag the corners. Keep only your player." : hasDraft ? "Check the player below, then save this moment." : partial ? "Tap the visible part of your player." : "Tap their shirt. We’ll help you frame the rest."}</p>
        </div>
        <div className="scout-count"><span data-testid="scout-progress-counter">{confirmedCount + "/" + queue.length}</span><small>saved</small></div>
      </div>}
      <div ref={stageRef} data-testid="scout-stage" className="scout-stage"
        aria-busy={frameBusy || phase === "BOOTING" || (!!activeFrame && loadedImage !== activeFrame.jpegDataUrl)}
        onClick={handleTap} onPointerDown={e => handlePointerDown(e)} onPointerMove={handlePointerMove} onPointerUp={handlePointerUp} onPointerCancel={handlePointerUp}>
        <video ref={videoRef} src={videoUrl} playsInline muted crossOrigin="anonymous" preload="auto" data-testid="scout-video" className="scout-source-video" />
        {activeFrame && <img key={activeFrame.jpegDataUrl} src={activeFrame.jpegDataUrl} alt="The exact video frame for this tap" draggable={false}
          onLoad={() => setLoadedImage(activeFrame.jpegDataUrl)} data-testid="scout-presented-frame" data-frame-time={activeFrame.t}
          className="scout-still" style={{ transform, transformOrigin: "center center" }} />}
        {activeFrame && !frameBusy && <span className="scout-time">{fmt(activeFrame.t)} <span>· paused</span></span>}
        {canTap && !hiddenHelp && <div className="scout-zoom">
          <button type="button" aria-label="Zoom out" data-testid="scout-zoom-out" className="scout-icon" disabled={zoom <= 1} onClick={() => { setZoom(z => Math.max(1, z / 1.4)); setPan({ x: 0, y: 0 }); }}><ZoomOut size={17} /></button>
          <button type="button" aria-label="Reset zoom" data-testid="scout-zoom-reset" className="scout-zoom-value" onClick={resetView}>{zoom.toFixed(1)}×</button>
          <button type="button" aria-label="Zoom in" data-testid="scout-zoom-in" className="scout-icon" disabled={zoom >= 5} onClick={() => setZoom(z => Math.min(5, z * 1.4))}><ZoomIn size={17} /></button>
        </div>}
        {hasDraft && rect.w > 0 && <DraftMarker box={draft.box} frame={activeFrame} rect={rect} zoom={zoom} pan={pan}
          onPointerDown={handlePointerDown} maskDataUrl={maskDataUrl} editable={refine} targetPoint={draft.target_point}
          excludeMode={["include", "exclude"].includes(tapIntent)} onAdjustBox={box => setDraft(prev => ({ ...prev, box, manualBox: true, visible_mask: undefined, maskRequested: true, maskDeclined: undefined, continuity: undefined, tracking_check: undefined }))} />}
        {hasDraft && rect.w > 0 && <SelectionPoints points={draft.exclude_points || []} frame={activeFrame} rect={rect} zoom={zoom} pan={pan} />}
        {preview && rect.w > 0 && policy.validBox(preview.results[previewIndex]?.box) &&
          <DraftMarker box={preview.results[previewIndex].box} frame={activeFrame} rect={rect} zoom={zoom} pan={pan} onPointerDown={() => {}} excludeMode />}
        {preview && <span role="status" className="scout-stage-tip">{preview.results[previewIndex]?.box ? "Suggested tracking · not a saved selection" : "Uncertain — no trusted box"}</span>}
        {canTap && !hasDraft && !hiddenHelp && <span className="scout-stage-tip"><ScanLine size={14} /> Pinch to zoom · tap to select</span>}
        {hasDraft && refine && !hasVisibleTarget && <span className="scout-stage-tip">Tap your player inside the box to set the selection point.</span>}
        {phase === "BOOTING" && <div className="scout-loading">
          <span className="scout-scan-orb"><ScanLine size={34} /></span>
          <h2>Finding your best moments.</h2><p role="status">{boot.label}</p>
          <div role="progressbar" aria-label="Preparing tap moments" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(boot.progress * 100)} className="scout-progress-track">
            <div style={{ width: Math.round(boot.progress * 100) + "%" }} />
          </div><small>You choose the player. We do the analysis.</small>
        </div>}
        {phase === "ERROR" && <div className="scout-loading"><p role="alert">{error}</p><button type="button" data-testid="scout-retry" className={primary} onClick={() => setRetry(n => n + 1)}>Retry preparing video</button></div>}
        {frameBusy && <div role="status" className="scout-busy"><Loader2 className="animate-spin" size={28} /><span>Opening real video frames…</span></div>}
      </div>

      {(phase === "MARKING" || done) && !link && !preview && <nav data-testid="scout-frame-strip" className="scout-moments" aria-label="Player reference moments">
        {queue.map((i, pos) => <button key={i} type="button" disabled={frameBusy} data-testid={"scout-frame-strip-" + pos}
          ref={el => { if (pos === position) el?.scrollIntoView?.({ block: "nearest", inline: "nearest" }); }}
          aria-label={"Moment " + (pos + 1) + (marks[i]?.box ? ", selected" : marks[i]?.skipped ? ", not visible" : ", pending")}
          aria-current={pos === position ? "step" : undefined}
          onClick={() => { setPosition(pos); setPhase("MARKING"); setDraft(null); setHiddenHelp(false); setNearby(null); setRefine(false); resetView(); }}
          className={"scout-moment " + (pos === position ? "is-current " : "") + (marks[i]?.box ? "is-saved" : "")}>
          {marks[i]?.box ? <MarkedCropCanvas frameDataUrl={frames[i].jpegDataUrl} box={marks[i].box} className="scout-moment-image" width={96} height={96} /> :
            <img src={frames[i].jpegDataUrl} alt="" className={"scout-moment-image " + (marks[i]?.skipped ? "is-skipped" : "")} />}
          <span>{marks[i]?.box ? <Check size={11} /> : pos + 1}</span>
        </button>)}
      </nav>}

      {(phase === "MARKING" || done) && <footer className="scout-panel">
        <div className="scout-panel-body">
          {notice && <p role="status" data-testid="scout-notice" className="scout-notice">{notice}</p>}
          {preview ? <div data-testid="scout-tracking-preview" className="scout-tool-panel">
            <strong>Does the box stay on your player?</strong>
            <div className="scout-button-row"><button type="button" data-testid="scout-preview-approve" className={primary + " flex-1"} disabled={preview.results.some(r => !policy.validBox(r.box))} onClick={() => finishPreview(true)}>Right player</button>
              <button type="button" data-testid="scout-preview-close" className={button} onClick={() => finishPreview(false)}>Close</button></div>
            <div className="scout-button-row">{preview.frames.slice(1).map((frame, i) => <button key={i} type="button" data-testid={"scout-preview-correct-" + (i + 1)} className={button} onClick={() => correctPreview(i + 1)}>Fix +{(frame.t - preview.frames[0].t).toFixed(2)}s</button>)}</div>
          </div> : nearby ? <section className="scout-tool-panel" data-testid="scout-nearby-filmstrip">
            <div className="scout-tool-heading"><div><strong>Find a clearer moment</strong><p>Swipe to look. Tap a frame to use it.</p></div><button type="button" aria-label="Close nearby moments" className="scout-icon" onClick={() => setNearby(null)}><X size={18} /></button></div>
            <div className="scout-nearby-frames">{nearby.frames.map((frame, i) => <button type="button" key={frame.t} data-testid={"scout-nearby-frame-" + i} aria-label={"Use frame at " + frame.t.toFixed(2) + " seconds"} aria-pressed={frame === activeFrame}
              className={"scout-nearby-frame " + (frame === activeFrame ? "is-current" : "")} onClick={() => chooseNearby(frame)}>
              <img src={frame.jpegDataUrl} alt="" /><span>{frame.t.toFixed(2)}s</span></button>)}</div>
            <small>Same scene only. Your selection stays until you choose a different frame.</small>
          </section> : hiddenHelp ? <section data-testid="scout-hidden-help" className="scout-tool-panel">
            <div className="scout-tool-heading"><div><strong>Can you see your player?</strong><p>Do not mark the player in front.</p></div><button type="button" className="scout-icon" aria-label="Close selection help" onClick={() => setHiddenHelp(false)}><X size={18} /></button></div>
            <button type="button" data-testid="scout-partial-player" className={button + " w-full"} onClick={choosePartial}>Partly visible — select the visible part</button>
            <button type="button" data-testid="scout-skip-frame" disabled={frameBusy} className={button + " w-full"} onClick={skipMark}>Not visible — use another moment</button>
            {partial && <button type="button" data-testid="scout-player-visible" className="scout-text-button" onClick={chooseVisible}>Player is fully visible</button>}
          </section> : <>
            {hasDraft && <div data-testid="scout-selection-preview" className="scout-selection-card">
              <div className="scout-player-crop"><MarkedCropCanvas frameDataUrl={activeFrame.jpegDataUrl} box={draft.box} mask={draft.visible_mask} width={192} height={240} className="w-full h-full" /></div>
              <div className="scout-selection-copy"><span className="scout-eyebrow">{draft.player_behind ? "PARTLY VISIBLE" : "SELECTED PLAYER"}</span><strong>{outlineBusy ? "Framing your player…" : !hasVisibleTarget ? "Set the player’s point" : "Your player. Your call."}</strong>
                <p>{!hasVisibleTarget ? "Tap their visible body inside the box." : draft.player_behind ? draft.visible_mask ? "Only the visible parts are selected." : "Use precise tools or a clearer moment." : draft.visible_mask ? "Check the head, shirt and feet." : "Check the box includes the full player."}</p>
                {draft.visible_mask && <span className="scout-outline-status"><CheckCircle2 size={12} /> Player outline ready</span>}
              </div>
            </div>}
            {hasDraft && refine && <div className="scout-edit-tools" data-testid="scout-edit-tools">
              <div className="scout-tool-heading"><span>Drag any corner · two fingers to move the view</span><button type="button" data-testid="scout-retap" className="scout-text-button" onClick={() => { setDraft(null); setRefine(false); setAdvanced(false); setNotice(""); resetView(); }}><RotateCcw size={13} /> Pick again</button></div>
              <button type="button" className="scout-text-button" data-testid="scout-advanced" aria-expanded={advanced} onClick={() => setAdvanced(v => !v)}><SlidersHorizontal size={14} />Precise tools<ChevronRight size={13} /></button>
              {advanced && <div className="scout-tool-panel">
                <div className="scout-button-row">
                  {requestMask && !draft.maskRequested && <button type="button" data-testid="scout-refine-cutout" className={button} onClick={() => setDraft(prev => ({ ...prev, maskRequested: true, maskDeclined: undefined }))}>Retry outline</button>}
                  {requestMask && <button type="button" data-testid="scout-include-player" className={button} disabled={outlineBusy} aria-pressed={tapIntent === "include"} onClick={() => { setTapIntent(t => t === "include" ? "target" : "include"); setNotice("Tap a missing visible part of YOUR player."); }}>Add body part</button>}
                  <button type="button" data-testid="scout-exclude-opponent" className={button} disabled={outlineBusy} aria-pressed={tapIntent === "exclude"} onClick={() => { setTapIntent(t => t === "exclude" ? "target" : "exclude"); setNotice("Tap the other player to exclude them."); }}>Remove other player</button>
                  {!!draft.exclude_points?.length && <button type="button" className={button} onClick={() => { setDraft(prev => ({ ...prev, exclude_points: [], visible_mask: undefined, maskRequested: true, maskDeclined: undefined, tracking_check: undefined })); setTapIntent("target"); }}>Clear red points</button>}
                  {!!draft.visible_mask && !draft.player_behind && <button type="button" className={button} onClick={() => { setMaskBusy(false); setDraft(prev => ({ ...prev, visible_mask: undefined, maskRequested: false, maskDeclined: maskKey, tracking_check: undefined })); }}>Use box instead</button>}
                  {requestTracking && draft.visibility !== "partial" && !link && <button type="button" data-testid="scout-check-tracking" className={button} disabled={outlineBusy || frameBusy} onClick={startPreview}>Preview tracking</button>}
                </div>
                {draft.visible_mask && <div data-testid="scout-cutout-context" className="scout-context-crop"><MarkedCropCanvas frameDataUrl={activeFrame.jpegDataUrl} box={draft.box} width={96} height={120} /><small>Original area for comparison. The outline keeps only visible player pixels.</small></div>}
                {draft.visibility === "partial" && !link && <div className="scout-button-row">
                  <button type="button" data-testid="scout-link-before" className={button} disabled={outlineBusy || frameBusy} onClick={() => startLink(-1)}>Link earlier reference</button>
                  <button type="button" data-testid="scout-link-after" className={button} disabled={outlineBusy || frameBusy} onClick={() => startLink(1)}>Link later reference</button>
                </div>}
                {!!draft.continuity?.length && <small>{draft.continuity.length} nearby identity check(s) saved</small>}
              </div>}
            </div>}
            {!hasDraft && !done && <div className="scout-empty-hint"><ScanLine size={22} /><div><strong>{partial ? "Select only the visible part" : "Start with one clear tap"}</strong><p>{fullCount >= MIN_TAPS ? "You can finish now, or add more references." : "Choose the same player in at least 3 clear moments."}</p></div></div>}
          </>}
        </div>

        {!preview && !nearby && !hiddenHelp && <div className="scout-actions">
          {hasDraft && <div className="scout-button-row">
            <button type="button" data-testid="scout-refine" className={button + " scout-edit-button"} aria-expanded={refine} onClick={editSelection}><SlidersHorizontal size={16} />{refine ? "Done editing" : "Adjust"}</button>
            <button type="button" data-testid="scout-confirm-mark" className={primary + " flex-1"}
              disabled={!canTap || submitting || actionLock.current || !hasVisibleTarget || outlineBusy || dragging || (!!requestMask && draft.player_behind && !draft.visible_mask)}
              onClick={link ? () => finishLink(true) : confirmMark}>{outlineBusy ? <Loader2 size={17} className="animate-spin" /> : <Check size={18} />}{link ? "Same player" : "Save player"}{!outlineBusy && <ArrowRight size={16} />}</button>
          </div>}
          {phase === "MARKING" && !hasDraft && !link && fullCount >= MIN_TAPS && <button type="button" data-testid="scout-finish-early" className={primary + " w-full"} onClick={() => { setNotice(""); setPhase("READY"); }}>Finish with {confirmedCount} selections<ArrowRight size={17} /></button>}
          {done && <>
            <div className="scout-review-crops" data-testid="scout-selection-done">{Object.entries(marks).filter(([, m]) => policy.validBox(m.box)).map(([i, m]) => <div key={i}><MarkedCropCanvas frameDataUrl={frames[Number(i)].jpegDataUrl} box={m.box} mask={m.visible_mask} width={112} height={128} className="w-full h-full" /></div>)}</div>
            <p className="scout-review-note">Identity checks run automatically. No extra player taps.</p>
            <button type="button" data-testid="scout-submit" disabled={submitting} className={primary + " w-full"} onClick={submit}>{submitting ? <Loader2 size={18} className="animate-spin" /> : <Check size={18} />}{submitting ? "Saving your selections…" : "Use " + confirmedCount + " player selections"}</button>
            <button type="button" className="scout-text-button w-full" disabled={submitting} onClick={() => setPhase("MARKING")}>Add or adjust a selection</button>
          </>}
        </div>}
        {phase === "MARKING" && !link && !preview && !nearby && <div className="scout-secondary">
          <button type="button" data-testid="scout-hidden-player" className="scout-text-button" disabled={frameBusy} aria-expanded={hiddenHelp} onClick={() => { setHiddenHelp(v => !v); setNotice(""); }}><HelpCircle size={15} />Need a clearer view?</button>
          <button type="button" data-testid="scout-open-nearby" className="scout-text-button" disabled={frameBusy} onClick={openNearby}>Find moment<ChevronRight size={14} /></button>
        </div>}
        {link && <button type="button" data-testid="scout-cancel-link" className={button + " w-full"} disabled={outlineBusy || frameBusy} onClick={() => finishLink(false)}>Cancel nearby check</button>}
      </footer>}
    </div>, document.body,
  );
}

function DraftMarker({ box, frame, rect, zoom, pan, onPointerDown, maskDataUrl, excludeMode, editable, targetPoint, onAdjustBox }) {
  const scale = Math.min(rect.w / frame.width, rect.h / frame.height);
  const rw = frame.width * scale, rh = frame.height * scale;
  const x = ((rect.w - rw) / 2 + box.x * rw - rect.w / 2) * zoom + rect.w / 2 + pan.x;
  const y = ((rect.h - rh) / 2 + box.y * rh - rect.h / 2) * zoom + rect.h / 2 + pan.y;
  const width = box.w * rw * zoom, height = box.h * rh * zoom;
  return (
    <>
      {maskDataUrl && <div data-testid="scout-player-mask" style={{ position: "absolute", left: x, top: y, width, height, background: "rgba(204,255,0,0.35)",
        maskImage: `url(${maskDataUrl})`, WebkitMaskImage: `url(${maskDataUrl})`, maskSize: "100% 100%", WebkitMaskSize: "100% 100%", pointerEvents: "none", zIndex: 9 }} />}
      <div data-testid="scout-draft-marker" data-marker-handle="move" onPointerDown={e => onPointerDown(e, "move")}
        style={{ position: "absolute", left: x, top: y, width, height, border: "3px solid #CCFF00", borderRadius: 8,
          boxShadow: "0 0 0 100vmax rgba(0,0,0,0.23)", cursor: editable ? "move" : "default", zIndex: 10, touchAction: "none", pointerEvents: excludeMode || !editable || !insideBox(targetPoint, box) ? "none" : "auto" }} />
      {targetPoint && <span data-testid="scout-target-point" style={{ position: "absolute", left: x + (targetPoint.x - box.x) * rw * zoom - 4, top: y + (targetPoint.y - box.y) * rh * zoom - 4,
        width: 8, height: 8, borderRadius: "50%", background: "#CCFF00", border: "2px solid #10170d", boxShadow: "0 0 0 2px white", pointerEvents: "none", zIndex: 12 }} />}
      {editable && ["nw", "ne", "sw", "se"].map(corner => <div key={corner} role="button" tabIndex={excludeMode ? -1 : 0} aria-label={"Resize " + ({ nw: "top left", ne: "top right", sw: "bottom left", se: "bottom right" })[corner]}
        data-testid={"scout-draft-resize-" + corner} data-marker-handle={"resize-" + corner} onPointerDown={e => onPointerDown(e, "resize-" + corner)}
        onKeyDown={e => {
          if (!onAdjustBox || !e.key.startsWith("Arrow") || excludeMode) return;
          e.preventDefault(); e.stopPropagation();
          const delta = e.shiftKey ? 10 : 1;
          onAdjustBox(resizeBox(box, corner, (e.key === "ArrowLeft" ? -delta : e.key === "ArrowRight" ? delta : 0) / frame.width, (e.key === "ArrowUp" ? -delta : e.key === "ArrowDown" ? delta : 0) / frame.height));
        }} className="scout-resize-handle"
        style={{ left: x + (corner.includes("e") ? width : 0) - 22, top: y + (corner.includes("s") ? height : 0) - 22,
          cursor: ["nw", "se"].includes(corner) ? "nwse-resize" : "nesw-resize", pointerEvents: excludeMode ? "none" : "auto" }}><span /></div>)}
    </>
  );
}

function SelectionPoints({ points, frame, rect, zoom, pan }) {
  const scale = Math.min(rect.w / frame.width, rect.h / frame.height), rw = frame.width * scale, rh = frame.height * scale;
  return points.map((p, i) => <span key={i} aria-label="Excluded opponent point" style={{ position: "absolute",
    left: ((rect.w - rw) / 2 + p.x * rw - rect.w / 2) * zoom + rect.w / 2 + pan.x - 6,
    top: ((rect.h - rh) / 2 + p.y * rh - rect.h / 2) * zoom + rect.h / 2 + pan.y - 6,
    width: 12, height: 12, borderRadius: "50%", background: "#ff6666", border: "2px solid white", pointerEvents: "none", zIndex: 12 }} />);
}
