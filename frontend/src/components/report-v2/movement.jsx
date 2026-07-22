// Movement Map — measured optical-tracking visual (ground truth, no AI estimates).
import React from "react";
import { Activity, Zap, Timer, Gauge, Play } from "lucide-react";
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

export function MovementMapCard({ movement, onPlayAt }) {
  if (!movement?.trail?.length) return null;
  const stats = [
    { icon: Zap, label: "Explosive Actions", value: movement.bursts, testid: "v2-mm-bursts" },
    { icon: Timer, label: "Tracked Play", value: `${movement.tracked_seconds}s`, testid: "v2-mm-time" },
    { icon: Gauge, label: "Intensity Index", value: `${movement.intensity}`, testid: "v2-mm-intensity" },
  ];
  return (
    <V2Card testid="v2-movement-map-card">
      <V2Title
        icon={Activity}
        right={<span className="text-[10px] font-extrabold tracking-[0.14em] text-[#CCFF00] bg-[#12402A] px-2.5 py-1 rounded-[5px] hidden md:block">MEASURED · OPTICAL TRACKING</span>}
      >
        Movement Map
      </V2Title>
      <div className="grid md:grid-cols-[1.3fr_1fr] gap-5 items-center">
        <TrailSvg trail={movement.trail} />
        <div>
          <div className="grid grid-cols-3 gap-2.5 mb-3.5">
            {stats.map(({ icon: Icon, label, value, testid }) => (
              <div key={label} className="bg-[#FBF9F3] border border-[#E5DFCE] rounded-[11px] p-3 text-center">
                <Icon className="w-4 h-4 mx-auto text-[#1E5B3C]" />
                <div data-testid={testid} className="font-barlow font-black text-[20px] mt-1 leading-none">{value}</div>
                <div className="text-[8.5px] font-extrabold tracking-[0.08em] uppercase text-[#75816F] mt-1 leading-[1.35]">{label}</div>
              </div>
            ))}
          </div>
          <button
            type="button"
            data-testid="v2-mm-topspeed"
            onClick={() => onPlayAt?.(movement.top_speed_t)}
            className="w-full flex items-center justify-between bg-[#12402A] text-white rounded-[11px] px-4 py-3 group"
          >
            <span className="text-left">
              <span className="block text-[9px] font-extrabold tracking-[0.14em] text-[#A9BC9C] uppercase">Fastest Measured Moment</span>
              <span className="font-barlow font-black text-[18px] text-[#CCFF00]">{movement.top_speed_t} · {movement.top_speed_idx}/100 pace</span>
            </span>
            <span className="w-8 h-8 rounded-full bg-white/10 border border-white/30 flex items-center justify-center transition-transform group-hover:scale-110">
              <Play className="w-3 h-3 text-white fill-white ml-0.5" />
            </span>
          </button>
          <p className="text-[10.5px] text-[#8B957F] leading-[1.5] mt-3">
            Measured frame-by-frame with optical tracking seeded by your own player taps — mathematical data, not AI estimates.
          </p>
        </div>
      </div>
    </V2Card>
  );
}
