// Movement Map — measured optical-tracking visual (ground truth, no AI estimates).
// Parent-first UX: every metric is labelled in plain language, the timeline is
// fully transparent (clip timestamps, tracking passages, the user's own taps),
// and the fastest moment carries a trust badge showing HOW it was verified.
import React, { useState } from "react";
import { Activity, Zap, Timer, Gauge, Play, ShieldCheck, Info, ChevronDown } from "lucide-react";
import { V2Card, V2Title } from "./sections";

function TrailSvg({ trail }) {
  const strokes = [];
  let cur = [];
  trail.forEach((p, i) => {
    if (i > 0 && p.t - trail[i - 1].t > 0.6) {
      if (cur.length > 1) strokes.push(cur);
      cur = [];
    }
    cur.push(p);
  });
  if (cur.length > 1) strokes.push(cur);
  const X = (p) => (p.x * 160).toFixed(1);
  const Y = (p) => (p.y * 90).toFixed(1);
  return (
    <svg viewBox="0 0 160 90" className="w-full rounded-[10px]" data-testid="v2-movement-svg" style={{ background: "#0D2818", aspectRatio: "16/9" }}>
      <defs>
        <radialGradient id="mmheat">
          <stop offset="0%" stopColor="#CCFF00" stopOpacity="0.3" />
          <stop offset="100%" stopColor="#CCFF00" stopOpacity="0" />
        </radialGradient>
      </defs>
      {[40, 80, 120].map((gx) => <line key={gx} x1={gx} y1="0" x2={gx} y2="90" stroke="#1D4230" strokeWidth="0.5" />)}
      {[30, 60].map((gy) => <line key={gy} x1="0" y1={gy} x2="160" y2={gy} stroke="#1D4230" strokeWidth="0.5" />)}
      {trail.map((p, i) => <circle key={`h${i}`} cx={X(p)} cy={Y(p)} r="10" fill="url(#mmheat)" />)}
      {strokes.map((s, i) => (
        <polyline
          key={`s${i}`}
          points={s.map((p) => `${X(p)},${Y(p)}`).join(" ")}
          fill="none" stroke="#CCFF00" strokeWidth="1.1" strokeLinecap="round" strokeLinejoin="round" opacity="0.85"
        />
      ))}
      {trail.filter((p) => p.tap).map((p, i) => (
        <g key={`t${i}`}>
          <circle cx={X(p)} cy={Y(p)} r="3" fill="none" stroke="#FFFFFF" strokeWidth="0.9" />
          <circle cx={X(p)} cy={Y(p)} r="1" fill="#FFFFFF" />
        </g>
      ))}
    </svg>
  );
}

const TRUST_LABEL = {
  tap: "Verified — this moment sits at one of your own taps",
  ai: "Identity-checked by a second AI at this exact second",
};

const HOW_WE_MEASURED = [
  ["What was measured?", "Your player's position, frame by frame, in the video you uploaded."],
  ["When?", "Only in the passages where the tracker had a secure lock on your player — shown above as timestamps from your clip."],
  ["How?", "You tapped your player; an optical tracker followed exactly that figure. Pure mathematics — no AI guessing."],
  ["Why does it matter?", "Bursts, work rate and top speed show how actively your player moves — things that are hard to see live."],
  ["Why trust it?", "Every tap was cross-checked by an independent AI, and the fastest moment is only reported from an identity-verified second. When the tracker is unsure, it stops instead of guessing."],
];

export function MovementMapCard({ movement, pace, onPlayAt }) {
  const [showHow, setShowHow] = useState(false);
  if (!movement?.trail?.length) return null;
  const stats = [
    { icon: Zap, label: "Speed Bursts", sub: "sudden accelerations", value: movement.bursts, testid: "v2-mm-bursts" },
    { icon: Timer, label: "Secure Tracking", sub: "time locked on your player", value: `${movement.tracked_seconds}s`, testid: "v2-mm-time" },
    { icon: Gauge, label: "Work Rate", sub: "movement activity · 0–100", value: `${movement.intensity}`, testid: "v2-mm-intensity" },
  ];
  const taps = movement.tap_times_mmss || [];
  const trust = TRUST_LABEL[movement.top_trust];
  const kmh =
    movement.top_trust && pace?.top_trust &&
    Math.abs((Number(pace.top_speed_t) || -99) - (Number(movement.top_video_s) || 99)) <= 2
      ? pace.top_speed_kmh
      : null;
  const passageCount = movement.segments || (movement.passages || []).length;
  return (
    <V2Card testid="v2-movement-map-card">
      <V2Title
        icon={Activity}
        right={<span className="text-[10px] font-extrabold tracking-[0.14em] text-[#CCFF00] bg-[#12402A] px-2.5 py-1 rounded-[5px] hidden md:block">MEASURED · OPTICAL TRACKING</span>}
      >
        Movement Map
      </V2Title>
      <p className="text-[12px] text-[#5C6657] leading-[1.5] -mt-1 mb-4" data-testid="v2-mm-subtitle">
        Where your player moved while our tracker had a secure lock — built from your own taps, never guessed. Covers this clip only.
      </p>
      <div className="grid md:grid-cols-[1.3fr_1fr] gap-5 items-start">
        <div>
          <TrailSvg trail={movement.trail} />
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 mt-2.5" data-testid="v2-mm-legend">
            <span className="inline-flex items-center gap-1.5 text-[10.5px] font-bold text-[#4B5563]">
              <span className="inline-block w-4 h-[3px] rounded-full bg-[#9FC400]" /> Your player&rsquo;s route
            </span>
            <span className="inline-flex items-center gap-1.5 text-[10.5px] font-bold text-[#4B5563]">
              <span className="inline-block w-2.5 h-2.5 rounded-full border-[2px] border-[#7A8471] bg-white" /> Your taps
            </span>
            <span className="inline-flex items-center gap-1.5 text-[10.5px] font-bold text-[#4B5563]">
              <span className="inline-block w-2.5 h-2.5 rounded-full bg-[#D3E88A]" /> Time spent there
            </span>
          </div>
          <p className="text-[10.5px] text-[#8B957F] leading-[1.5] mt-1.5">
            Only moments with a secure lock on your player are drawn. When the tracker is unsure, it stops honestly — nothing is guessed.
          </p>
        </div>
        <div>
          {taps.length > 0 && (
            <div className="mb-3.5" data-testid="v2-mm-taps">
              <div className="text-[9px] font-extrabold tracking-[0.14em] uppercase text-[#75816F] mb-1.5">
                Your taps — tap to rewatch
              </div>
              <div className="flex flex-wrap gap-1.5">
                {taps.map((t, i) => (
                  <button
                    key={`${t}-${i}`}
                    type="button"
                    data-testid={`v2-mm-tap-${i}`}
                    onClick={() => onPlayAt?.(t)}
                    className="inline-flex items-center gap-1 bg-[#FBF9F3] border border-[#E5DFCE] hover:border-[#1E5B3C] rounded-full px-2.5 py-1 text-[11px] font-bold text-[#12402A] transition-colors"
                  >
                    <Play className="w-2.5 h-2.5 fill-current" /> {t}
                  </button>
                ))}
              </div>
              {movement.taps_same_player && (
                <div className="flex items-start gap-1.5 mt-2 text-[10.5px] font-semibold text-[#1E5B3C]" data-testid="v2-mm-taps-verified">
                  <ShieldCheck className="w-3.5 h-3.5 flex-shrink-0 mt-[1px]" />
                  <span>
                    Independent AI check: all {taps.length} of your taps show the same player
                    {movement.taps_confidence ? ` (${movement.taps_confidence} confidence)` : ""}.
                  </span>
                </div>
              )}
            </div>
          )}

          <div className="grid grid-cols-3 gap-2.5 mb-3.5">
            {stats.map(({ icon: Icon, label, sub, value, testid }) => (
              <div key={label} className="bg-[#FBF9F3] border border-[#E5DFCE] rounded-[11px] p-3 text-center">
                <Icon className="w-4 h-4 mx-auto text-[#1E5B3C]" />
                <div data-testid={testid} className="font-barlow font-black text-[20px] mt-1 leading-none">{value}</div>
                <div className="text-[8.5px] font-extrabold tracking-[0.08em] uppercase text-[#4B5563] mt-1 leading-[1.35]">{label}</div>
                <div className="text-[8px] text-[#8B957F] leading-tight mt-0.5">{sub}</div>
              </div>
            ))}
          </div>

          <button
            type="button"
            data-testid="v2-mm-topspeed"
            onClick={() => onPlayAt?.(movement.top_video_s ?? movement.top_speed_t)}
            className="w-full bg-[#12402A] text-white rounded-[11px] px-4 py-3.5 text-left group"
          >
            <span className="block text-[9px] font-extrabold tracking-[0.14em] text-[#A9BC9C] uppercase">
              Fastest moment · in your uploaded clip
            </span>
            <span className="flex items-center justify-between mt-1">
              <span className="font-barlow font-black text-[24px] leading-none text-[#CCFF00]">
                {movement.top_speed_t}
                {kmh ? <span className="text-[14px] ml-2">≈ {kmh} km/h</span> : null}
              </span>
              <span className="w-8 h-8 rounded-full bg-white/10 border border-white/30 flex items-center justify-center transition-transform group-hover:scale-110 flex-shrink-0">
                <Play className="w-3 h-3 text-white fill-white ml-0.5" />
              </span>
            </span>
            <span className="block mt-2 space-y-0.5">
              {movement.track_start_t && (
                <span className="block text-[10px] text-white/70" data-testid="v2-mm-track-window">
                  Tracking began at {movement.track_start_t} · covered {movement.tracked_seconds}s in {passageCount} passage{passageCount === 1 ? "" : "s"}
                </span>
              )}
              {movement.top_after_start != null && (
                <span className="block text-[10px] text-white/70" data-testid="v2-mm-after-start">
                  Fastest movement +{movement.top_after_start}s after tracking began
                  {!kmh ? ` · burst score ${movement.top_speed_idx}/100 vs. this clip's own movement` : ""}
                </span>
              )}
            </span>
            {trust && (
              <span className="mt-2 inline-flex items-center gap-1.5 text-[9.5px] font-extrabold tracking-[0.06em] uppercase text-[#CCFF00]" data-testid="v2-mm-trust">
                <ShieldCheck className="w-3 h-3" /> {trust}
              </span>
            )}
            <span className="mt-1.5 flex items-center gap-1.5 text-[10px] font-extrabold tracking-[0.1em] uppercase text-white/60 group-hover:text-white transition-colors">
              <Play className="w-2.5 h-2.5 fill-current" /> Watch this exact second
            </span>
          </button>

          <button
            type="button"
            data-testid="v2-mm-how-toggle"
            onClick={() => setShowHow((s) => !s)}
            className="mt-3 inline-flex items-center gap-1.5 text-[10.5px] font-extrabold tracking-[0.08em] uppercase text-[#1E5B3C] hover:text-[#12402A] transition-colors"
          >
            <Info className="w-3.5 h-3.5" /> How we measured this
            <ChevronDown className={`w-3.5 h-3.5 transition-transform ${showHow ? "rotate-180" : ""}`} />
          </button>
          {showHow && (
            <div className="mt-2 bg-[#FBF9F3] border border-[#E5DFCE] rounded-[11px] p-3.5 space-y-2" data-testid="v2-mm-how-panel">
              {HOW_WE_MEASURED.map(([q, a]) => (
                <div key={q}>
                  <div className="text-[10px] font-extrabold uppercase tracking-[0.06em] text-[#12402A]">{q}</div>
                  <div className="text-[11px] text-[#5C6657] leading-[1.5]">{a}</div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </V2Card>
  );
}
