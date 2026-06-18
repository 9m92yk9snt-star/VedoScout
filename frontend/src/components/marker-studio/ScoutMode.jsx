/**
 * ScoutMode.jsx — v4.0 "one-tap track" workflow.
 *
 * REPLACES the chip-based v3 flow entirely.
 *
 * Pipeline:
 *   1. BOOTING       — detect scene cuts, distribute 10 keyframe timestamps,
 *                      pre-capture each keyframe as a JPEG (≤1920px @0.85).
 *   2. TAP_REFERENCE — show the first keyframe full-screen.  The user taps
 *                      DIRECTLY on the player they want to identify.  An
 *                      instant lime outline locks around the tap box.  If
 *                      the player isn't in this frame, user can scrub to a
 *                      different keyframe and tap there.
 *   3. TRACKING      — POST {reference, 9 targets} to /api/scout/track-player.
 *                      Gemini ReIDs the same player in parallel.  Progress
 *                      card shows elapsed time + rotating status messages.
 *                      Client-side `spatioTemporal.filterByMotion` rejects
 *                      any match implying >8 m/s player speed.
 *   4. REVIEW        — 2×5 grid of 10 thumbnails, each with the AI-tracked
 *                      player outlined in lime + a confidence badge.  Tap
 *                      any thumbnail to re-tap manually if AI got it wrong.
 *   5. CONFIRM       — calls onConfirm({anchors, sceneCuts}).  Contract
 *                      preserved — MarkerStudio.handleScoutConfirm gets the
 *                      same payload shape as before, so the rest of the
 *                      pipeline doesn't change.
 *
 * Out of scope (per scope discipline):
 *   - Landing, pricing, payment, reports, top bar, scrubber styling,
 *     dormant Roster code, freeform tap fallback flow.
 */

import React, { useEffect, useRef, useState, useCallback } from "react";
import { createPortal } from "react-dom";
import { Loader2, X, RotateCcw, Check, Hand } from "lucide-react";
import { detectSceneCuts, distributeHints } from "./sceneDetect";
import { filterByMotion } from "./spatioTemporal";

const API_BASE = process.env.REACT_APP_BACKEND_URL || "";
const TARGET_HINTS = 10;
// Reduced from 1920/0.85 → 1280/0.78. ReID does NOT need pixel-perfect
// detail (it needs jersey colour + body shape) and smaller payloads mean
// faster Gemini round-trips. Empirically saves ~40-60 % per call.
const FRAME_MAX_W = 1280;
const FRAME_JPEG_QUALITY = 0.78;

// ── Helpers ─────────────────────────────────────────────────────────

/** Seek the video and wait for the next painted frame (iOS-safe).
 *
 *  Uses a hard outer timeout of 1500 ms so the boot loop NEVER hangs even
 *  if the seek silently fails — on iOS Safari `requestVideoFrameCallback`
 *  can fail to fire on a freshly-mounted <video> element until the first
 *  successful paint, which would otherwise stall the entire pipeline.
 */
function seekTo(videoEl, t) {
  return new Promise((resolve) => {
    if (!videoEl) return resolve();
    let done = false;
    const finish = () => {
      if (done) return;
      done = true;
      videoEl.removeEventListener("seeked", onSeeked);
      // Wait one frame so the canvas captures the new pixels.
      let painted = false;
      const paintDone = () => { if (!painted) { painted = true; resolve(); } };
      if (typeof videoEl.requestVideoFrameCallback === "function") {
        try { videoEl.requestVideoFrameCallback(paintDone); } catch { /* noop */ }
      } else {
        requestAnimationFrame(() => requestAnimationFrame(paintDone));
      }
      // Hard cap — never wait more than 400 ms for the paint callback.
      setTimeout(paintDone, 400);
    };
    const onSeeked = () => finish();
    videoEl.addEventListener("seeked", onSeeked);
    try { videoEl.currentTime = t; } catch { finish(); }
    // Outer hard cap — never wait more than 1500 ms total for any one seek.
    setTimeout(finish, 1500);
  });
}

/** Snapshot the current video frame as a JPEG data-URL. */
function captureFrame(videoEl) {
  if (!videoEl || !videoEl.videoWidth) return null;
  const vw = videoEl.videoWidth;
  const vh = videoEl.videoHeight;
  const targetW = Math.min(FRAME_MAX_W, vw);
  const targetH = Math.round(vh * (targetW / vw));
  const c = document.createElement("canvas");
  c.width = targetW;
  c.height = targetH;
  try {
    c.getContext("2d").drawImage(videoEl, 0, 0, targetW, targetH);
    return c.toDataURL("image/jpeg", FRAME_JPEG_QUALITY);
  } catch {
    return null;
  }
}

/** Map a pointer/touch event in stage-screen coords → fractional video coords. */
function eventToVideoFrac(event, stageEl, videoEl) {
  if (!stageEl || !videoEl?.videoWidth) return null;
  const r = stageEl.getBoundingClientRect();
  const cx = event.touches?.[0]?.clientX ?? event.clientX;
  const cy = event.touches?.[0]?.clientY ?? event.clientY;
  if (cx == null || cy == null) return null;
  const sx = cx - r.left;
  const sy = cy - r.top;
  // object-contain mapping inverse
  const vw = videoEl.videoWidth, vh = videoEl.videoHeight;
  const sw = r.width, sh = r.height;
  const scale = Math.min(sw / vw, sh / vh);
  const renderedW = vw * scale, renderedH = vh * scale;
  const offX = (sw - renderedW) / 2, offY = (sh - renderedH) / 2;
  const inX = sx - offX, inY = sy - offY;
  if (inX < 0 || inY < 0 || inX > renderedW || inY > renderedH) return null;
  return { fx: inX / renderedW, fy: inY / renderedH };
}

/** Build a default reference box around the user's tap point. */
function tapToBox(fx, fy) {
  // Roughly the size of a small player at typical sideline framing
  const w = 0.06, h = 0.18;
  return {
    x: Math.max(0, Math.min(1 - w, fx - w / 2)),
    y: Math.max(0, Math.min(1 - h, fy - h * 0.42)),
    w,
    h,
  };
}

// ── Component ───────────────────────────────────────────────────────

export default function ScoutMode({ open, onCancel, onConfirm, videoUrl, duration }) {
  /* Refs */
  const videoRef = useRef(null);
  const stageRef = useRef(null);
  const cancelledRef = useRef(false);

  /* Video readiness */
  const [videoReady, setVideoReady] = useState(false);
  const [vidDur, setVidDur] = useState(duration || 0);
  const [stageRect, setStageRect] = useState({ w: 0, h: 0 });

  /* Phase machine */
  // BOOTING | TAP_REFERENCE | TRACKING | REVIEW
  const [phase, setPhase] = useState("BOOTING");

  /* Boot phase */
  const [bootProgress, setBootProgress] = useState(0);
  const [bootStage, setBootStage] = useState("scene"); // "scene" | "frames"
  const [hints, setHints] = useState([]);             // [t1, t2, ..., t10]
  const [sceneCuts, setSceneCuts] = useState([]);
  const [frameCache, setFrameCache] = useState([]);   // [{t, jpegDataUrl}]

  /* Tap reference phase */
  const [activeHintIdx, setActiveHintIdx] = useState(0);
  // refTap: { hintIdx, t, box:{x,y,w,h} } — locked once user is happy.
  const [refTap, setRefTap] = useState(null);

  /* Tracking phase */
  const [trackingStartedAt, setTrackingStartedAt] = useState(null);
  const [trackingError, setTrackingError] = useState(null);

  /* Review phase */
  // matches: [{ hintIdx, t, box, confidence, source: 'user'|'gemini', missing?: bool }]
  const [matches, setMatches] = useState([]);
  const [reviewActiveIdx, setReviewActiveIdx] = useState(null); // when user is re-tapping a missed frame

  // ── Reset on close ────────────────────────────────────────────────
  useEffect(() => {
    if (!open) {
      cancelledRef.current = false;
      setVideoReady(false);
      setPhase("BOOTING");
      setBootProgress(0);
      setBootStage("scene");
      setHints([]);
      setSceneCuts([]);
      setFrameCache([]);
      setActiveHintIdx(0);
      setRefTap(null);
      setTrackingStartedAt(null);
      setTrackingError(null);
      setMatches([]);
      setReviewActiveIdx(null);
    }
  }, [open]);

  // ── Track stage size ──────────────────────────────────────────────
  useEffect(() => {
    if (!open) return;
    if (!stageRef.current) return;
    const el = stageRef.current;
    const initial = el.getBoundingClientRect();
    setStageRect({ w: initial.width, h: initial.height });
    const ro = new ResizeObserver(() => {
      const r = el.getBoundingClientRect();
      setStageRect({ w: r.width, h: r.height });
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, [open]);

  // ── BOOT: scene-cut detect → distribute hints → pre-capture frames ─
  useEffect(() => {
    if (!open) return;
    if (!videoReady) return;
    if (phase !== "BOOTING") return;
    let cancelled = false;
    (async () => {
      const v = videoRef.current;
      if (!v) return;

      // 0. Wait until the video is TRULY playable (readyState >= 2 + frames
      //    decoded). `loadedmetadata` fires with just the header, before any
      //    pixels are available — on iOS Safari the first `seek` then hangs
      //    silently waiting for a frame that doesn't exist yet.
      //
      //    If the wait drags past 4 s we force-reload the <video> element
      //    via .load() — this "kicks" iOS Safari out of its sometimes-stuck
      //    first-load state without the user having to close + reopen.
      const waitReady = async () => {
        const start = Date.now();
        let reloaded = false;
        while (!cancelled && Date.now() - start < 12000) {
          if (v.readyState >= 2 && v.videoWidth > 0 && v.duration > 0) return;
          if (!reloaded && Date.now() - start > 4000) {
            reloaded = true;
            try {
              v.load();
              // Some iOS versions need an explicit .play() then .pause()
              // to populate the decoder.
              const pp = v.play();
              if (pp?.catch) pp.catch(() => {});
              setTimeout(() => { try { v.pause(); } catch { /* noop */ } }, 50);
            } catch { /* noop */ }
          }
          await new Promise((r) => setTimeout(r, 100));
        }
      };
      await waitReady();
      if (cancelled) return;

      // 1. Scene-cut detection (~3 s)
      setBootStage("scene");
      setBootProgress(0);
      let cuts = [];
      try {
        const result = await detectSceneCuts(v, {
          onProgress: (p) => { if (!cancelled) setBootProgress(p * 0.4); },
        });
        cuts = result.cuts || [];
      } catch (err) {
        console.warn("scene-cut detect failed:", err);
      }
      if (cancelled) return;
      setSceneCuts(cuts);

      // 2. Distribute 10 hint timestamps
      const dur = v.duration || vidDur || 0;
      const hs = distributeHints(dur, cuts, TARGET_HINTS);
      if (cancelled || !hs.length) {
        // Final safety net: if duration is unknown, just split [0..30s].
        // Better to show something than hang at 0%.
        const fallback = [];
        const fbDur = dur || 30;
        for (let i = 0; i < TARGET_HINTS; i++) {
          fallback.push((fbDur * (i + 0.5)) / TARGET_HINTS);
        }
        setHints(fallback);
      } else {
        setHints(hs);
      }
      const finalHints = hs.length ? hs : (() => {
        const fb = [];
        const fbDur = dur || 30;
        for (let i = 0; i < TARGET_HINTS; i++) fb.push((fbDur * (i + 0.5)) / TARGET_HINTS);
        return fb;
      })();

      // 3. Pre-capture all 10 keyframes as JPEGs.
      //    Each seekTo has a 1500 ms hard cap, so even if iOS Safari
      //    refuses to seek, we'll move on rather than hang.
      setBootStage("frames");
      setBootProgress(0.4);
      const captured = [];
      for (let i = 0; i < finalHints.length; i++) {
        if (cancelled) return;
        try {
          await seekTo(v, finalHints[i]);
          const dataUrl = captureFrame(v);
          captured.push({ t: finalHints[i], jpegDataUrl: dataUrl });
        } catch (err) {
          console.warn("frame capture failed at t=", finalHints[i], err);
          captured.push({ t: finalHints[i], jpegDataUrl: null });
        }
        if (!cancelled) setBootProgress(0.4 + 0.6 * ((i + 1) / finalHints.length));
      }
      if (cancelled) return;
      setFrameCache(captured);

      // 4. Seek back to first hint and move to TAP_REFERENCE
      try { await seekTo(v, finalHints[0]); } catch { /* noop */ }
      if (cancelled) return;
      setActiveHintIdx(0);
      setBootProgress(1);
      setPhase("TAP_REFERENCE");
    })();
    return () => { cancelled = true; };
  }, [open, videoReady, phase, vidDur]);

  // ── Seek video when the user navigates to a different hint frame
  useEffect(() => {
    if (phase !== "TAP_REFERENCE" && phase !== "REVIEW") return;
    const v = videoRef.current;
    if (!v) return;
    const t = hints[activeHintIdx];
    if (t == null) return;
    if (Math.abs(v.currentTime - t) > 0.15) {
      try { v.currentTime = t; } catch { /* noop */ }
    }
  }, [activeHintIdx, hints, phase]);

  // ── TAP_REFERENCE: handle tap on the video stage ──────────────────
  const handleReferenceTap = useCallback((e) => {
    if (phase !== "TAP_REFERENCE") return;
    const frac = eventToVideoFrac(e, stageRef.current, videoRef.current);
    if (!frac) return;
    const box = tapToBox(frac.fx, frac.fy);
    const t = hints[activeHintIdx];
    setRefTap({ hintIdx: activeHintIdx, t, box });
    // Auto-advance after a short beat so the user sees the lock
    setTimeout(() => {
      if (!cancelledRef.current) setPhase("TRACKING");
    }, 800);
  }, [phase, hints, activeHintIdx]);

  // ── REVIEW: tap a thumbnail to re-tap manually ────────────────────
  const handleReviewThumbTap = useCallback((idx) => {
    if (phase !== "REVIEW") return;
    setReviewActiveIdx(idx);
    setActiveHintIdx(idx);
    setPhase("TAP_REFERENCE");
  }, [phase]);

  const handleReviewTap = useCallback((e) => {
    // When the user is correcting a single frame (reviewActiveIdx !== null)
    // we DON'T re-run tracking — we just update that one match.
    if (phase !== "TAP_REFERENCE") return;
    if (reviewActiveIdx == null) {
      handleReferenceTap(e);
      return;
    }
    const frac = eventToVideoFrac(e, stageRef.current, videoRef.current);
    if (!frac) return;
    const box = tapToBox(frac.fx, frac.fy);
    setMatches((prev) => prev.map((m, i) =>
      i === reviewActiveIdx
        ? { ...m, box, confidence: 1.0, source: "user", missing: false }
        : m,
    ));
    setReviewActiveIdx(null);
    // small delay so the lime lock animation is visible
    setTimeout(() => {
      if (!cancelledRef.current) setPhase("REVIEW");
    }, 600);
  }, [phase, reviewActiveIdx, handleReferenceTap]);

  // ── TRACKING: POST to backend, then transition to REVIEW ──────────
  useEffect(() => {
    if (phase !== "TRACKING") return;
    if (!refTap) return;
    let cancelled = false;
    (async () => {
      setTrackingStartedAt(Date.now());
      setTrackingError(null);
      const refFrame = frameCache[refTap.hintIdx];
      if (!refFrame?.jpegDataUrl) {
        setTrackingError("Reference frame missing — please retry.");
        return;
      }
      // 9 target frames = every hint except the reference
      const targets = frameCache
        .map((f, i) => ({ i, t: f.t, image: f.jpegDataUrl }))
        .filter((f) => f.i !== refTap.hintIdx && f.image);

      try {
        const res = await fetch(`${API_BASE}/api/scout/track-player`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            reference: { image: refFrame.jpegDataUrl, box: refTap.box },
            targets: targets.map((f) => ({ id: `hint-${f.i}`, image: f.image })),
          }),
        });
        if (cancelled) return;
        if (!res.ok) {
          setTrackingError(`Tracking failed (${res.status}). Tap directly on each frame to continue.`);
          return;
        }
        const json = await res.json();
        const byId = new Map(
          (json.matches || []).map((m) => [m.id, m]),
        );
        // Assemble final matches[] — 10 entries in hint order
        let outMatches = frameCache.map((f, i) => {
          if (i === refTap.hintIdx) {
            return {
              hintIdx: i, t: f.t, box: refTap.box,
              confidence: 1.0, source: "user", missing: false,
            };
          }
          const m = byId.get(`hint-${i}`);
          if (m?.box) {
            return {
              hintIdx: i, t: f.t, box: m.box,
              confidence: m.confidence ?? 0.5,
              reason: m.reason || "",
              source: "gemini", missing: false,
            };
          }
          return {
            hintIdx: i, t: f.t, box: null,
            confidence: 0,
            reason: m?.reason || "not found",
            source: "gemini", missing: true,
          };
        });

        // ── Safety net: reject physically impossible jumps ─────────
        try {
          const ref = { t: refTap.t, box: refTap.box };
          const candidates = outMatches
            .filter((m) => !m.missing && m.box && m.hintIdx !== refTap.hintIdx)
            .map((m) => ({ t: m.t, box: m.box, confidence: m.confidence, _idx: m.hintIdx }));
          const { rejected } = filterByMotion(candidates, ref);
          const rejIdx = new Set(rejected.map((r) => r.anchor._idx));
          if (rejIdx.size) {
            outMatches = outMatches.map((m) =>
              rejIdx.has(m.hintIdx)
                ? { ...m, missing: true, box: null, confidence: 0, reason: "physics_reject" }
                : m,
            );
          }
        } catch (err) {
          console.warn("spatioTemporal filter skipped:", err);
        }

        if (cancelled) return;
        setMatches(outMatches);
        setPhase("REVIEW");
      } catch (err) {
        console.warn("Track-player request failed:", err);
        if (!cancelled) {
          setTrackingError("Network error — please retry.");
        }
      }
    })();
    return () => { cancelled = true; };
  }, [phase, refTap, frameCache]);

  // ── CONFIRM ───────────────────────────────────────────────────────
  const handleConfirm = useCallback(() => {
    // Build the anchors[] payload in the SHAPE the existing pipeline expects.
    // We map each "match" (whether AI-found or user-corrected) into the same
    // {t, box, segment} structure that handleScoutConfirm consumes today.
    const anchors = matches
      .filter((m) => m.box && !m.missing)
      .map((m) => {
        // Find which scene-cut segment this anchor belongs to (0-indexed)
        let seg = 0;
        for (let i = 0; i < sceneCuts.length; i++) {
          if (m.t >= sceneCuts[i]) seg = i + 1;
        }
        return { t: m.t, box: m.box, segment: seg };
      });
    if (!anchors.length) return;
    onConfirm({ anchors, sceneCuts });
  }, [matches, sceneCuts, onConfirm]);

  // ── Render ────────────────────────────────────────────────────────
  if (!open) return null;

  const lockedFrameBackground = phase === "REVIEW" && reviewActiveIdx == null;
  const showStageOverlay =
    phase === "BOOTING" || phase === "TRACKING" || (phase === "TAP_REFERENCE" && !refTap);

  return createPortal(
    <div
      className="fixed inset-0 z-[230] bg-ink text-white flex flex-col"
      data-testid="scout-mode-overlay"
    >
      {/* ── Top bar (compact, restrained) ───────────────────────── */}
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
        <span
          className="text-[11px] uppercase tracking-widest font-black text-white/85"
          data-testid="scout-mode-title"
        >
          Scout Mode
        </span>
        {phase === "REVIEW" && reviewActiveIdx == null ? (
          <button
            type="button"
            onClick={() => {
              // Re-run tracking from scratch — wipe matches, go back to TAP_REFERENCE
              setMatches([]);
              setRefTap(null);
              setActiveHintIdx(0);
              setPhase("TAP_REFERENCE");
            }}
            data-testid="scout-restart"
            className="w-9 h-9 flex items-center justify-center text-white/85 hover:text-[#CCFF00] transition-colors"
            aria-label="Start over"
            title="Start over"
          >
            <RotateCcw className="w-4 h-4" />
          </button>
        ) : (
          <span className="w-9" />
        )}
      </div>

      {/* ── Main stage ──────────────────────────────────────────── */}
      {phase === "REVIEW" && reviewActiveIdx == null ? (
        <ReviewGrid
          matches={matches}
          frameCache={frameCache}
          onTapThumb={handleReviewThumbTap}
        />
      ) : (
        <div
          ref={stageRef}
          className="relative flex-1 bg-black overflow-hidden flex items-center justify-center"
          data-testid="scout-stage"
          onClick={
            phase === "TAP_REFERENCE" && reviewActiveIdx == null
              ? handleReferenceTap
              : phase === "TAP_REFERENCE" && reviewActiveIdx != null
                ? handleReviewTap
                : undefined
          }
          style={{
            cursor:
              phase === "TAP_REFERENCE" && !refTap ? "crosshair" : "default",
          }}
        >
          <video
            ref={videoRef}
            src={videoUrl}
            className="w-full h-full object-contain"
            playsInline
            preload="auto"
            muted
            onLoadedMetadata={(e) => {
              setVidDur(e.target.duration || 0);
            }}
            onCanPlay={(e) => {
              // Wait for actual pixel data (readyState >= 3) before kicking
              // off the boot pipeline. `loadedmetadata` is too early — only
              // the header is decoded then and iOS Safari hangs on the first
              // seek.
              setVideoReady(true);
              setVidDur(e.target.duration || 0);
            }}
          />

          {/* Player-lock outline overlay — visible while the user has
              tapped (TAP_REFERENCE) or while they are correcting a single
              frame and have tapped (review-correct). */}
          {((phase === "TAP_REFERENCE" && refTap && refTap.hintIdx === activeHintIdx) ||
            (phase === "TAP_REFERENCE" && reviewActiveIdx != null && matches[reviewActiveIdx]?.box && matches[reviewActiveIdx]?.source === "user")) && (
            <LockedPlayerBox
              box={
                refTap?.box ||
                matches[reviewActiveIdx]?.box
              }
              videoEl={videoRef.current}
              stageRect={stageRect}
              accent="#22C55E"
            />
          )}

          {/* Boot overlay */}
          {phase === "BOOTING" && (
            <BootOverlay progress={bootProgress} stage={bootStage} />
          )}

          {/* Tap-to-identify overlay (only when no tap yet) */}
          {phase === "TAP_REFERENCE" && !refTap && reviewActiveIdx == null && (
            <TapHintOverlay
              hintIdx={activeHintIdx}
              total={hints.length}
              onPrev={
                activeHintIdx > 0
                  ? () => setActiveHintIdx((i) => Math.max(0, i - 1))
                  : null
              }
              onNext={
                activeHintIdx < hints.length - 1
                  ? () => setActiveHintIdx((i) => Math.min(hints.length - 1, i + 1))
                  : null
              }
            />
          )}

          {/* Manual-correct overlay (when re-tapping a single review frame) */}
          {phase === "TAP_REFERENCE" && reviewActiveIdx != null && (
            <ManualCorrectOverlay
              frameNumber={reviewActiveIdx + 1}
              onCancel={() => {
                setReviewActiveIdx(null);
                setPhase("REVIEW");
              }}
            />
          )}

          {/* Tracking overlay — shows progress, never-frozen */}
          {phase === "TRACKING" && (
            <TrackingOverlay
              startedAt={trackingStartedAt}
              expectedMs={10000}
              error={trackingError}
              onRetry={() => {
                setTrackingError(null);
                // Force re-trigger by toggling phase
                setPhase("REVIEW");
                setTimeout(() => setPhase("TRACKING"), 50);
              }}
              onSkipToReview={() => {
                // User wants to just review whatever we have; treat all 9 as missing
                const fallback = frameCache.map((f, i) => {
                  if (i === refTap.hintIdx) {
                    return { hintIdx: i, t: f.t, box: refTap.box, confidence: 1, source: "user", missing: false };
                  }
                  return { hintIdx: i, t: f.t, box: null, confidence: 0, source: "gemini", missing: true };
                });
                setMatches(fallback);
                setPhase("REVIEW");
              }}
            />
          )}
        </div>
      )}

      {/* ── Bottom action bar (only in REVIEW) ────────────────── */}
      {phase === "REVIEW" && reviewActiveIdx == null && (
        <div className="flex-shrink-0 bg-ink/95 border-t border-white/8 backdrop-blur px-4 py-3">
          <button
            type="button"
            onClick={handleConfirm}
            disabled={matches.filter((m) => !m.missing && m.box).length < 3}
            data-testid="scout-confirm"
            className="w-full h-12 flex items-center justify-center gap-2 bg-[#CCFF00] text-ink font-black text-[13px] uppercase tracking-wider transition-all disabled:opacity-40 disabled:cursor-not-allowed hover:bg-white"
            style={{ letterSpacing: "0.08em" }}
          >
            <Check className="w-5 h-5" />
            Confirm {matches.filter((m) => !m.missing && m.box).length} player{matches.filter((m) => !m.missing && m.box).length === 1 ? "" : "s"}
          </button>
          <p className="mt-2 text-[10px] text-white/45 text-center" style={{ letterSpacing: "0.04em" }}>
            Tap any frame to correct the AI{`'`}s pick.  Missing frames will be skipped.
          </p>
        </div>
      )}
    </div>,
    document.body,
  );
}

ScoutMode.displayName = "ScoutMode";

// ── Sub-components ──────────────────────────────────────────────────

/** Live lime outline locked over the user's tapped player. */
function LockedPlayerBox({ box, videoEl, stageRect, accent }) {
  if (!box || !videoEl?.videoWidth || !stageRect.w) return null;
  const vw = videoEl.videoWidth, vh = videoEl.videoHeight;
  const sw = stageRect.w, sh = stageRect.h;
  const scale = Math.min(sw / vw, sh / vh);
  const rW = vw * scale, rH = vh * scale;
  const offX = (sw - rW) / 2, offY = (sh - rH) / 2;
  const x = box.x * rW + offX;
  const y = box.y * rH + offY;
  const w = box.w * rW;
  const h = box.h * rH;
  return (
    <div
      data-testid="scout-locked-player"
      style={{
        position: "absolute",
        left: x - 2,
        top: y - 2,
        width: w + 4,
        height: h + 4,
        border: `3px solid ${accent}`,
        borderRadius: 6,
        boxShadow: `0 0 0 1px rgba(0,0,0,0.7), 0 0 28px ${accent}80`,
        pointerEvents: "none",
        zIndex: 40,
        animation: "scoutLockPop 0.55s ease-out forwards",
      }}
    >
      <style>{`
        @keyframes scoutLockPop {
          0%   { transform: scale(1.15); opacity: 0; }
          60%  { transform: scale(0.98); opacity: 1; }
          100% { transform: scale(1.00); opacity: 1; }
        }
      `}</style>
      <div
        style={{
          position: "absolute",
          bottom: -22,
          left: "50%",
          transform: "translateX(-50%)",
          padding: "2px 6px",
          background: accent,
          color: "#0A0F0D",
          fontSize: 10,
          fontWeight: 900,
          letterSpacing: "0.08em",
          textTransform: "uppercase",
          whiteSpace: "nowrap",
        }}
      >
        ✓ Player locked
      </div>
    </div>
  );
}

/** Boot screen — shows scene-cut detection & frame extraction progress. */
function BootOverlay({ progress, stage }) {
  const pct = Math.round(progress * 100);
  return (
    <div className="absolute inset-0 flex flex-col items-center justify-center bg-ink/95 backdrop-blur-md text-white px-6" style={{ zIndex: 50 }}>
      <div className="relative w-20 h-20 mb-4">
        <div className="absolute inset-0 rounded-full border-4 border-[#CCFF00]/15" />
        <div
          className="absolute inset-0 rounded-full border-4 border-[#CCFF00] border-t-transparent animate-spin"
          style={{ animationDuration: "1.1s" }}
        />
        <div className="absolute inset-0 flex items-center justify-center text-[#CCFF00] font-black text-base tabular-nums">
          {pct}%
        </div>
      </div>
      <div className="text-white font-black text-[15px] mb-1 tracking-wide">
        {stage === "scene" ? "Reading the match…" : "Preparing 10 keyframes…"}
      </div>
      <div className="text-white/65 text-[11px] text-center max-w-xs">
        {stage === "scene"
          ? "Finding the natural breakpoints in your video so the AI can analyse each segment correctly."
          : "Capturing 10 distinct moments to identify your player from."}
      </div>
    </div>
  );
}

/** "Tap the player you want to identify" — initial overlay. */
function TapHintOverlay({ hintIdx, total, onPrev, onNext }) {
  return (
    <>
      {/* Centred instruction */}
      <div
        className="absolute left-1/2 -translate-x-1/2 flex flex-col items-center pointer-events-none"
        style={{ top: 24, zIndex: 20 }}
      >
        <div className="flex items-center gap-2 bg-ink/92 backdrop-blur px-3 py-1.5 border border-[#CCFF00]/45">
          <Hand className="w-4 h-4 text-[#CCFF00]" />
          <span className="text-[13px] font-black text-[#CCFF00] uppercase tracking-wide leading-none">
            Tap the player you want to identify
          </span>
        </div>
      </div>

      {/* Soft pulsing crosshair near the centre — visual invitation to tap */}
      <div
        className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 pointer-events-none"
        style={{ zIndex: 15 }}
      >
        <div
          style={{
            width: 56,
            height: 56,
            borderRadius: "50%",
            border: "2px dashed rgba(204,255,0,0.55)",
            animation: "scoutPulse 1.6s ease-in-out infinite",
          }}
        />
        <style>{`
          @keyframes scoutPulse {
            0%, 100% { opacity: 0.35; transform: scale(1); }
            50%      { opacity: 0.85; transform: scale(1.15); }
          }
        `}</style>
      </div>

      {/* Frame navigation — "this frame isn't great" */}
      <div
        className="absolute left-0 right-0 flex items-center justify-between px-3"
        style={{ bottom: 16, zIndex: 20 }}
      >
        <button
          type="button"
          onClick={(e) => { e.stopPropagation(); onPrev?.(); }}
          disabled={!onPrev}
          className="text-white/65 hover:text-[#CCFF00] disabled:opacity-30 transition-colors"
          style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.06em", textTransform: "uppercase", pointerEvents: "auto", background: "transparent", border: "none" }}
          data-testid="scout-prev-frame"
        >
          ← Other frame
        </button>
        <span className="text-white/60 tabular-nums" style={{ fontSize: 10, fontWeight: 700, letterSpacing: "0.1em", pointerEvents: "none" }}>
          FRAME {hintIdx + 1} / {total}
        </span>
        <button
          type="button"
          onClick={(e) => { e.stopPropagation(); onNext?.(); }}
          disabled={!onNext}
          className="text-white/65 hover:text-[#CCFF00] disabled:opacity-30 transition-colors"
          style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.06em", textTransform: "uppercase", pointerEvents: "auto", background: "transparent", border: "none" }}
          data-testid="scout-next-frame"
        >
          Other frame →
        </button>
      </div>
    </>
  );
}

/** Overlay when user is re-tapping a single review frame to correct AI. */
function ManualCorrectOverlay({ frameNumber, onCancel }) {
  return (
    <>
      <div
        className="absolute left-1/2 -translate-x-1/2 pointer-events-none"
        style={{ top: 18, zIndex: 20 }}
      >
        <div className="flex items-center gap-2 bg-ink/95 backdrop-blur px-3 py-1.5 border border-amber-300/55">
          <Hand className="w-4 h-4 text-amber-300" />
          <span
            className="text-amber-200 font-black uppercase leading-none"
            style={{ fontSize: 13, letterSpacing: "0.04em" }}
          >
            Correct frame {frameNumber} — tap the right player
          </span>
        </div>
      </div>
      <div
        className="absolute left-0 right-0 flex items-center justify-center px-3"
        style={{ bottom: 16, zIndex: 20 }}
      >
        <button
          type="button"
          onClick={(e) => { e.stopPropagation(); onCancel?.(); }}
          className="text-white/65 hover:text-[#CCFF00] transition-colors"
          style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.06em", textTransform: "uppercase", pointerEvents: "auto", background: "transparent", border: "none" }}
          data-testid="scout-cancel-correct"
        >
          ← Back to review
        </button>
      </div>
    </>
  );
}

/** Progress card during Gemini parallel tracking call. */
function TrackingOverlay({ startedAt, expectedMs, error, onRetry, onSkipToReview }) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    if (!startedAt) return;
    const id = setInterval(() => setNow(Date.now()), 250);
    return () => clearInterval(id);
  }, [startedAt]);
  const elapsedMs = startedAt ? Math.max(0, now - startedAt) : 0;
  const sec = Math.floor(elapsedMs / 1000);
  const pct = Math.min(95, (elapsedMs / Math.max(1, expectedMs)) * 95);
  const STAGES = [
    "Reading your player's appearance…",
    "Scanning the other 9 frames in parallel…",
    "Matching jersey, shorts, body shape…",
    "Cross-checking position and movement…",
    "Almost ready…",
  ];
  const message = STAGES[Math.min(STAGES.length - 1, Math.floor(sec / 4))];
  const elapsedLabel = `${Math.floor(sec / 60)}:${String(sec % 60).padStart(2, "0")}`;
  const expectedLabel = `${Math.floor(expectedMs / 60000)}:${String(Math.round((expectedMs % 60000) / 1000)).padStart(2, "0")}`;

  return (
    <div
      className="absolute left-1/2 -translate-x-1/2"
      style={{
        top: "50%",
        transform: "translate(-50%, -50%)",
        width: "min(82vw, 340px)",
        padding: "16px 18px",
        background: "rgba(10,15,13,0.94)",
        backdropFilter: "blur(12px)",
        WebkitBackdropFilter: "blur(12px)",
        border: "1px solid rgba(204,255,0,0.45)",
        boxShadow: "0 12px 36px rgba(0,0,0,0.6)",
        zIndex: 30,
      }}
      data-testid="scout-tracking-card"
    >
      {error ? (
        <>
          <div className="flex items-center gap-2 mb-2">
            <span style={{ width: 9, height: 9, borderRadius: "50%", background: "#EF4444", boxShadow: "0 0 10px #EF4444" }} />
            <span style={{ color: "#FFFFFF", fontSize: 11, fontWeight: 800, letterSpacing: "0.08em", textTransform: "uppercase" }}>
              Tracking failed
            </span>
          </div>
          <p className="text-white/75 text-[12px] mb-3 leading-snug">{error}</p>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={onRetry}
              className="flex-1 h-9 bg-[#CCFF00] text-ink font-black text-[11px] uppercase tracking-wider hover:bg-white"
              data-testid="scout-track-retry"
            >
              Retry
            </button>
            <button
              type="button"
              onClick={onSkipToReview}
              className="flex-1 h-9 border border-white/25 text-white/85 font-black text-[11px] uppercase tracking-wider hover:text-[#CCFF00] hover:border-[#CCFF00]"
              data-testid="scout-track-skip"
            >
              Mark manually
            </button>
          </div>
        </>
      ) : (
        <>
          <div className="flex items-center justify-between gap-3 mb-2">
            <div className="flex items-center gap-2 min-w-0">
              <span
                style={{
                  width: 9, height: 9, borderRadius: "50%",
                  background: "#CCFF00",
                  boxShadow: "0 0 10px #CCFF00",
                  animation: "scoutPulse 1.1s ease-in-out infinite",
                }}
              />
              <span style={{ color: "#FFFFFF", fontSize: 11, fontWeight: 800, letterSpacing: "0.08em", textTransform: "uppercase" }}>
                Tracking your player
              </span>
            </div>
            <span className="tabular-nums" style={{ color: "rgba(255,255,255,0.55)", fontSize: 11, fontWeight: 700 }}>
              {elapsedLabel} <span style={{ color: "rgba(255,255,255,0.35)" }}>/ ~{expectedLabel}</span>
            </span>
          </div>
          <div style={{ height: 3, background: "rgba(255,255,255,0.1)", overflow: "hidden", marginBottom: 8 }}>
            <div
              style={{
                width: `${pct}%`,
                height: "100%",
                background: "linear-gradient(90deg, #CCFF00 0%, #22C55E 100%)",
                transition: "width 0.25s ease-out",
                boxShadow: "0 0 6px rgba(204,255,0,0.55)",
              }}
            />
          </div>
          <div style={{ color: "rgba(255,255,255,0.78)", fontSize: 12, fontWeight: 500 }}>
            {message}
          </div>
        </>
      )}
    </div>
  );
}

/** Final 10-thumbnail review grid. */
function ReviewGrid({ matches, frameCache, onTapThumb }) {
  return (
    <div
      className="flex-1 bg-ink overflow-y-auto"
      data-testid="scout-review-grid"
    >
      <div className="px-3 pt-3 pb-2">
        <h2
          className="text-white font-black tracking-wide leading-tight"
          style={{ fontSize: 17, letterSpacing: "-0.005em" }}
        >
          Review your player
        </h2>
        <p className="mt-1 text-white/55 text-[11px] leading-snug">
          The AI marked the same player across all 10 moments.  Tap any frame to correct it.
        </p>
      </div>
      <div className="grid grid-cols-2 gap-1.5 px-2 pb-3">
        {matches.map((m, i) => {
          const frame = frameCache[i];
          return (
            <ReviewThumb
              key={i}
              index={i}
              imageUrl={frame?.jpegDataUrl}
              box={m.box}
              source={m.source}
              missing={m.missing}
              confidence={m.confidence}
              onTap={() => onTapThumb(i)}
            />
          );
        })}
      </div>
    </div>
  );
}

/** One thumbnail in the review grid. */
function ReviewThumb({ index, imageUrl, box, source, missing, confidence, onTap }) {
  const accent = missing
    ? "#EF4444"
    : source === "user"
      ? "#22C55E"
      : confidence >= 0.7
        ? "#CCFF00"
        : "#FBBF24";
  const label = missing
    ? "Missing — tap to add"
    : source === "user"
      ? "You marked"
      : confidence >= 0.7
        ? "AI confident"
        : "Low confidence";

  return (
    <button
      type="button"
      onClick={onTap}
      data-testid={`scout-review-thumb-${index + 1}`}
      className="relative bg-black overflow-hidden transition-transform active:scale-[0.98]"
      style={{ aspectRatio: "16 / 9", border: "1px solid rgba(255,255,255,0.1)", padding: 0 }}
      aria-label={`Frame ${index + 1} — ${label}`}
    >
      {imageUrl ? (
        <img
          src={imageUrl}
          alt={`Frame ${index + 1}`}
          className="absolute inset-0 w-full h-full object-cover"
          draggable={false}
        />
      ) : (
        <div className="absolute inset-0 flex items-center justify-center text-white/40 text-[10px]">no frame</div>
      )}
      {box && !missing && (
        <div
          style={{
            position: "absolute",
            left: `${box.x * 100}%`,
            top: `${box.y * 100}%`,
            width: `${box.w * 100}%`,
            height: `${box.h * 100}%`,
            border: `2px solid ${accent}`,
            borderRadius: 3,
            boxShadow: `0 0 0 1px rgba(0,0,0,0.7), 0 0 10px ${accent}88`,
            pointerEvents: "none",
          }}
        />
      )}
      {/* Top-left frame number */}
      <span
        className="absolute top-1.5 left-1.5 px-1.5 py-0.5 bg-ink/85 backdrop-blur text-white text-[9px] font-black tabular-nums tracking-widest"
        style={{ letterSpacing: "0.1em" }}
      >
        {String(index + 1).padStart(2, "0")}
      </span>
      {/* Bottom-right status pill */}
      <span
        className="absolute bottom-1.5 right-1.5 flex items-center gap-1 px-1.5 py-0.5 backdrop-blur text-[9px] font-black uppercase"
        style={{
          background: missing ? "rgba(239,68,68,0.92)" : "rgba(10,15,13,0.85)",
          color: missing ? "#FFFFFF" : accent,
          letterSpacing: "0.08em",
        }}
      >
        {missing ? "Add" : label}
      </span>
    </button>
  );
}
