// Cinematic report intro — a short film-style opening (dark scene → the
// player's best frame + name → score count-up) shown the first time a report
// is opened. Always skippable; sound is off by default.

import React, { useEffect, useRef, useState } from "react";
import { Volume2, VolumeX } from "lucide-react";

export function CinematicIntro({
  playerName, overall, momentTs, momentTitle, image, demo, onDone,
  scoreDecimals = 1, scoreSuffix = null, scoreLabel = "Overall score",
  endLine = "Your story starts here", endEmphasis = false,
}) {
  const [phase, setPhase] = useState(0); // 0 dark · 1 moment · 2 score · 3 fade-out
  const [score, setScore] = useState(0);
  const [soundOn, setSoundOn] = useState(false);
  const soundRef = useRef(false);
  const audioCtxRef = useRef(null);
  const doneRef = useRef(false);
  const rafRef = useRef(null);
  const timersRef = useRef([]);
  const target = typeof overall === "number" ? overall : null;

  const tickSound = (freq = 1250, dur = 0.03, gain = 0.06) => {
    const ctx = audioCtxRef.current;
    if (!ctx) return;
    try {
      const o = ctx.createOscillator();
      const g = ctx.createGain();
      o.type = "square";
      o.frequency.value = freq;
      g.gain.setValueAtTime(gain, ctx.currentTime);
      g.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + dur);
      o.connect(g);
      g.connect(ctx.destination);
      o.start();
      o.stop(ctx.currentTime + dur);
    } catch { /* noop */ }
  };

  const finish = () => {
    if (doneRef.current) return;
    doneRef.current = true;
    timersRef.current.forEach(clearTimeout);
    if (rafRef.current) cancelAnimationFrame(rafRef.current);
    onDone();
  };

  useEffect(() => {
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { document.body.style.overflow = prev; };
  }, []);

  useEffect(() => {
    const t = (fn, ms) => timersRef.current.push(setTimeout(fn, ms));
    t(() => setPhase(1), 1000);
    t(() => {
      setPhase(2);
      if (target == null) {
        t(() => setPhase(3), 1600);
        t(finish, 2300);
        return;
      }
      const dur = 1700;
      const start = performance.now();
      let lastTick = 0;
      const step = (now) => {
        const p = Math.min(1, (now - start) / dur);
        const eased = 1 - Math.pow(1 - p, 3);
        setScore(eased * target);
        if (soundRef.current && now - lastTick > 85 && p < 1) { tickSound(); lastTick = now; }
        if (p < 1) {
          rafRef.current = requestAnimationFrame(step);
        } else {
          if (soundRef.current) tickSound(330, 0.16, 0.09);
          t(() => setPhase(3), 1500);
          t(finish, 2200);
        }
      };
      rafRef.current = requestAnimationFrame(step);
    }, 3800);
    return () => {
      timersRef.current.forEach(clearTimeout);
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const toggleSound = () => {
    setSoundOn((v) => {
      const next = !v;
      soundRef.current = next;
      if (next && !audioCtxRef.current) {
        try { audioCtxRef.current = new (window.AudioContext || window.webkitAudioContext)(); } catch { /* noop */ }
      }
      return next;
    });
  };

  return (
    <div
      data-testid="cinematic-intro"
      className={`fixed inset-0 z-[100] bg-black overflow-hidden ${phase === 3 ? "smp-cine-out" : ""}`}
      style={{ fontFamily: "'DM Sans', sans-serif" }}
    >
      {image && (
        <img
          src={image}
          alt=""
          className="absolute inset-0 w-full h-full object-cover smp-cine-kenburns transition-[opacity,filter] duration-700"
          style={{
            opacity: phase >= 1 ? 1 : 0,
            filter: phase >= 2 ? "brightness(0.3) blur(3px) saturate(1.05)" : "brightness(0.55) saturate(1.05)",
          }}
        />
      )}
      <div className="absolute inset-0 bg-gradient-to-b from-black/80 via-black/20 to-black/85" />
      <div aria-hidden className="absolute top-0 left-0 right-0 h-[7vh] bg-black z-10 border-b border-white/5" />
      <div aria-hidden className="absolute bottom-0 left-0 right-0 h-[7vh] bg-black z-10 border-t border-white/5" />

      <button
        type="button"
        onClick={finish}
        data-testid="cinematic-skip-btn"
        className="absolute top-[calc(7vh+12px)] right-4 z-30 text-[10px] tracking-[0.14em] font-bold text-white/60 hover:text-white border border-white/25 rounded-full px-3.5 py-1.5 bg-black/40 uppercase transition-colors"
      >
        Skip ✕
      </button>

      {demo && (
        <div
          data-testid="cinematic-sample-badge"
          className="absolute top-[calc(7vh+12px)] left-4 z-30 text-[9px] tracking-[0.1em] font-extrabold text-[#CCFF00] bg-black/55 border border-[#CCFF00]/30 rounded-full px-3 py-1.5 uppercase max-w-[58vw] leading-tight"
        >
          Demo sample — every premium report opens like this
        </div>
      )}

      <div className="absolute inset-0 z-20 flex flex-col items-center justify-center text-center px-6">
        <div className={`text-[#CCFF00] text-[10px] md:text-[11px] tracking-[0.42em] font-bold uppercase ${phase === 0 ? "smp-cine-pulse" : "opacity-80"}`}>
          ScoutMePlay presents
        </div>

        {phase < 2 && (
          <div className={`transition-opacity duration-700 ${phase >= 1 ? "opacity-100" : "opacity-0"}`}>
            <h1
              data-testid="cinematic-player-name"
              className="font-barlow font-black text-white uppercase leading-[0.95] text-[13vw] md:text-[72px] mt-4 drop-shadow-[0_4px_30px_rgba(0,0,0,0.6)]"
            >
              {playerName}
            </h1>
            {(momentTs || momentTitle) && (
              <p className="text-white/90 text-[15px] md:text-[19px] mt-4 leading-snug max-w-[560px] mx-auto">
                {momentTs && <>Minute <span className="text-[#CCFF00] font-bold">{momentTs}</span>. </>}
                {momentTitle && <span className="font-semibold">{momentTitle}.</span>}
              </p>
            )}
          </div>
        )}

        {phase >= 2 && (
          <div className="smp-cine-fadein">
            {target != null && (
              <>
                <div
                  data-testid="cinematic-score"
                  className="font-barlow font-black text-[#CCFF00] leading-none text-[26vw] md:text-[150px] drop-shadow-[0_0_60px_rgba(204,255,0,0.3)] tabular-nums mt-3"
                >
                  {score.toFixed(scoreDecimals)}
                  {scoreSuffix && <span className="text-[7vw] md:text-[44px] text-white/50 font-bold">{scoreSuffix}</span>}
                </div>
                <div className="text-white/70 text-[10px] md:text-[12px] tracking-[0.4em] font-bold uppercase mt-2">{scoreLabel}</div>
              </>
            )}
            <div className={`text-[10px] tracking-[0.32em] font-bold uppercase mt-8 ${endEmphasis ? "text-[#CCFF00]" : "text-white/50"}`} data-testid="cinematic-end-line">{endLine}</div>
            <div className="text-[#CCFF00] text-xl mt-1 smp-cine-bounce" aria-hidden>↓</div>
          </div>
        )}
      </div>

      <button
        type="button"
        onClick={toggleSound}
        data-testid="cinematic-sound-toggle"
        className="absolute bottom-[calc(7vh+12px)] left-1/2 -translate-x-1/2 z-30 inline-flex items-center gap-1.5 text-[10px] tracking-[0.1em] font-bold text-white/50 hover:text-white border border-white/20 rounded-full px-3 py-1.5 bg-black/40 uppercase transition-colors"
      >
        {soundOn ? <Volume2 className="w-3 h-3" /> : <VolumeX className="w-3 h-3" />} {soundOn ? "Sound on" : "Sound off"}
      </button>
    </div>
  );
}
