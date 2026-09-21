// Proof mini-player — "See the proof" bottom sheet. Opens over the report
// without moving the reader's scroll position; auto-seeks the report video to
// a few seconds before the cited moment. Demo reports show the frame + a
// premium-availability note instead of video.

import React, { useEffect, useRef, useState } from "react";
import { X, Play, ShieldCheck, Lock, ChevronRight } from "lucide-react";
import { tsToSeconds } from "./derive";

const fmt = (s) => `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(Math.floor(s % 60)).padStart(2, "0")}`;

export function ProofPlayerSheet({ proof, videoUrl, posterUrl, frames, demo, onClose, onUnlock }) {
  const vidRef = useRef(null);
  const clipRef = useRef(null);
  const [atMoment, setAtMoment] = useState(false);
  const [atClipMoment, setAtClipMoment] = useState(false);
  const [clipFailed, setClipFailed] = useState(false);
  const sec = tsToSeconds(proof?.ts);
  const startAt = sec != null ? Math.max(0, sec - 4) : 0;
  const locked = !!proof?.locked;
  const useClip = !!proof?.clip && !clipFailed && !demo && !locked;
  const clipStart = typeof proof?.clipStart === "number" ? proof.clipStart : null;
  // THE MOMENT activation inside a proof clip = event_start - clip_start
  const clipMomentAt = useClip && clipStart != null && sec != null ? Math.max(0, sec - clipStart) : null;

  useEffect(() => { setClipFailed(false); }, [proof?.key]);

  useEffect(() => {
    setAtClipMoment(false);
    if (!useClip || clipMomentAt == null) return undefined;
    const v = clipRef.current;
    if (!v) return undefined;
    const onTime = () => setAtClipMoment(v.currentTime >= clipMomentAt - 0.15 && v.currentTime <= clipMomentAt + 2.0);
    v.addEventListener("timeupdate", onTime);
    return () => v.removeEventListener("timeupdate", onTime);
  }, [proof, useClip, clipMomentAt]);

  useEffect(() => {
    if (!proof) return undefined;
    const onKey = (e) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [proof, onClose]);

  useEffect(() => {
    setAtMoment(false);
    if (!proof || demo || locked || useClip || !videoUrl || sec == null) return undefined;
    const v = vidRef.current;
    if (!v) return undefined;
    const onTime = () => setAtMoment(v.currentTime >= sec - 0.3 && v.currentTime <= sec + 2.5);
    v.addEventListener("timeupdate", onTime);
    return () => v.removeEventListener("timeupdate", onTime);
  }, [proof, demo, locked, videoUrl, sec]);

  useEffect(() => {
    if (!proof || demo || locked || useClip || !videoUrl) return;
    const v = vidRef.current;
    if (!v) return;
    const seekPlay = () => {
      try { v.currentTime = startAt; } catch { /* noop */ }
      const p = v.play();
      if (p?.catch) p.catch(() => { v.muted = true; v.play().catch(() => {}); });
    };
    if (v.readyState >= 1) seekPlay();
    else {
      v.addEventListener("loadedmetadata", seekPlay, { once: true });
      try { v.load(); } catch { /* noop */ }
    }
  }, [proof, demo, locked, videoUrl, startAt]);

  if (!proof) return null;

  let demoFrame = posterUrl;
  if (demo && frames?.length) {
    let best = null;
    for (const f of frames) {
      if (!f.url) continue;
      if (sec != null && f.sec != null) {
        const d = Math.abs(f.sec - sec);
        if (!best || d < best.d) best = { url: f.url, d };
      }
    }
    demoFrame = best?.url || frames[0]?.url || posterUrl;
  }

  return (
    <div
      key={proof.key}
      data-testid="proof-player-sheet"
      className="fixed left-0 right-0 bottom-[62px] md:bottom-6 md:left-auto md:right-6 md:w-[430px] z-[85] px-2 md:px-0 smp-proof-slide"
    >
      <div className="bg-[#0D1A0F] rounded-t-[18px] md:rounded-[18px] shadow-[0_-8px_40px_rgba(0,0,0,0.45)] md:shadow-[0_18px_50px_rgba(0,0,0,0.5)] overflow-hidden border border-white/10">
        <div className="w-9 h-1 rounded-full bg-white/20 mx-auto mt-2 md:hidden" aria-hidden />
        <div className="flex items-center justify-between px-4 pt-2 pb-2.5">
          <div className="flex items-center gap-1.5 text-[#CCFF00] text-[11px] font-extrabold tracking-[0.08em] uppercase">
            {locked ? <Lock className="w-3 h-3" /> : <Play className="w-3 h-3 fill-[#CCFF00]" />} Proof{proof.ts ? ` · ${proof.ts}` : ""}
          </div>
          <button
            type="button"
            onClick={onClose}
            data-testid="proof-player-close"
            aria-label="Close proof player"
            className="w-7 h-7 rounded-full border border-white/20 text-white/70 hover:text-white flex items-center justify-center transition-colors"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
        <div className="px-2.5 pb-2.5">
          <div className="relative rounded-[12px] overflow-hidden bg-black aspect-video">
            {locked ? (
              <>
                {posterUrl && <img src={posterUrl} alt="" className="absolute inset-0 w-full h-full object-cover blur-[9px] scale-110 opacity-60" />}                <span className="absolute inset-0 flex items-center justify-center">
                  <span className="w-12 h-12 rounded-full bg-black/70 border border-white/25 flex items-center justify-center">
                    <Lock className="w-5 h-5 text-white" />
                  </span>
                </span>
              </>
            ) : demo ? (
              <>
                {demoFrame && <img src={demoFrame} alt="" className="absolute inset-0 w-full h-full object-cover" />}
                <span className="absolute top-2 left-2 bg-black/70 text-[#CCFF00] text-[9px] font-extrabold tracking-[0.12em] px-2 py-0.5 rounded">DEMO SAMPLE</span>
                {proof.ts && (
                  <span className="absolute bottom-2 left-2 bg-black/70 text-white font-barlow font-extrabold text-[12px] px-2 py-0.5 rounded tabular-nums">{proof.ts}</span>
                )}
              </>
            ) : useClip ? (
              <>
                <video
                  key={proof.clip}
                  ref={clipRef}
                  src={proof.clip}
                  poster={posterUrl || undefined}
                  autoPlay
                  loop
                  muted
                  controls
                  playsInline
                  preload="auto"
                  onError={() => setClipFailed(true)}
                  data-testid="proof-clip-video"
                  className="absolute inset-0 w-full h-full object-contain bg-black"
                />
                <span
                  data-testid="proof-clip-badge"
                  className={`absolute top-2 right-2 z-10 px-2.5 py-1 rounded-full text-[10px] font-extrabold tracking-[0.08em] uppercase pointer-events-none transition-colors duration-300 ${
                    atClipMoment ? "bg-[#CCFF00] text-[#12211A] animate-pulse" : "bg-black/70 text-white/85"
                  }`}
                >
                  {atClipMoment ? "The moment" : "Moment at"} · {proof.ts}
                </span>
                <button
                  data-testid="proof-clip-fullvideo-btn"
                  onClick={() => setClipFailed(true)}
                  className="absolute bottom-2 right-2 z-10 px-2 py-1 rounded bg-black/70 text-white/85 text-[10px] font-bold uppercase tracking-[0.08em] hover:bg-black/90"
                >
                  Full video
                </button>
              </>
            ) : (
              <>
                <video
                  ref={vidRef}
                  src={videoUrl || undefined}
                  poster={posterUrl || undefined}
                  controls
                  playsInline
                  preload="metadata"
                  data-testid="proof-player-video"
                  className="absolute inset-0 w-full h-full object-contain bg-black"
                />
                {sec != null && proof.ts && (
                  <span
                    data-testid="proof-moment-chip"
                    className={`absolute top-2 right-2 z-10 px-2.5 py-1 rounded-full text-[10px] font-extrabold tracking-[0.08em] uppercase pointer-events-none transition-colors duration-300 ${
                      atMoment ? "bg-[#CCFF00] text-[#12211A] animate-pulse" : "bg-black/70 text-white/85"
                    }`}
                  >
                    {atMoment ? "The moment" : "Moment at"} · {proof.ts}
                  </span>
                )}
              </>
            )}
          </div>
          {locked ? (
            <>
              <p data-testid="proof-player-locked-note" className="text-white/65 text-[11px] leading-[1.5] px-1.5 pt-2">
                <span className="text-[#CCFF00] font-bold">Unlocks with the full report</span> — the video jumps straight to the exact second and plays this moment as proof.
              </p>
              <button
                type="button"
                onClick={() => { onClose(); onUnlock?.(); }}
                data-testid="proof-player-unlock-btn"
                className="mt-2.5 mb-1 mx-1.5 w-[calc(100%-12px)] inline-flex items-center justify-center gap-1.5 bg-[#CCFF00] text-[#12211A] font-barlow font-black uppercase tracking-[0.05em] text-[13px] px-5 py-2.5 rounded-full hover:brightness-95 transition-[filter] active:scale-[0.98]"
              >
                Unlock the full report <ChevronRight className="w-4 h-4" />
              </button>
            </>
          ) : demo ? (
            <p data-testid="proof-player-demo-note" className="text-white/65 text-[11px] leading-[1.5] px-1.5 pt-2 pb-1">
              <span className="text-[#CCFF00] font-bold">Demo sample</span> — available in the premium report: your own match video jumps straight to {proof.ts || "the exact second"} and plays the proof.
            </p>
          ) : (
            <p className="text-white/45 text-[10.5px] leading-[1.4] px-1.5 pt-2 pb-1 flex items-center gap-1.5">
              <ShieldCheck className="w-3 h-3 text-[#CCFF00] shrink-0" />
            {sec != null && proof.ts
                ? (useClip
                    ? (clipStart != null
                        ? <>Playing from {fmt(clipStart)} so you see the build-up — the moment hits at <span className="text-[#CCFF00] font-bold">{proof.ts}</span>.</>
                        : <>Verified tracked clip of the moment at <span className="text-[#CCFF00] font-bold">{proof.ts}</span>.</>)
                    : <>Playing from {fmt(startAt)} so you see the build-up — the moment hits at <span className="text-[#CCFF00] font-bold">{proof.ts}</span>.</>)
                : <>Playing the uploaded match video.</>}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
