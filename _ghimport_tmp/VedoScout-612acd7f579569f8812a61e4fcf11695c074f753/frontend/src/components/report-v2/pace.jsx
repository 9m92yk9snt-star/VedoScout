// Pace & Sprints — estimates derived from the same optical tracking as the Movement Map.
// Parent-first: clip timestamps in mm:ss, plain-language labels, and a trust
// badge showing that the headline speed comes from an identity-verified moment.
import React from "react";
import { Gauge, Zap, Route, Timer, Play, ShieldCheck } from "lucide-react";
import { V2Card, V2Title } from "./sections";

const mmss = (t) => {
  const s = Math.max(0, Math.round(Number(t) || 0));
  return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
};

const TRUST_LABEL = {
  tap: "Verified moment — at your own tap",
  ai: "Identity-checked at this exact second",
};

export function PaceCard({ pace, onPlayAt }) {
  if (!pace?.top_speed_kmh) return null;
  const stats = [
    { icon: Zap, label: "Sprints", sub: `runs above ${pace.sprint_threshold_kmh} km/h`, value: pace.sprint_count, testid: "v2-pace-sprints" },
    { icon: Route, label: "Distance covered", sub: "while securely tracked", value: `${pace.distance_tracked_m} m`, testid: "v2-pace-distance" },
    { icon: Timer, label: "Average speed", sub: "while moving", value: pace.avg_moving_kmh ? `${pace.avg_moving_kmh} km/h` : "—", testid: "v2-pace-avg" },
  ];
  const trust = TRUST_LABEL[pace.top_trust];
  return (
    <V2Card testid="v2-pace-card">
      <V2Title
        icon={Gauge}
        right={<span className="text-[10px] font-extrabold tracking-[0.14em] text-[#CCFF00] bg-[#12402A] px-2.5 py-1 rounded-[5px] hidden md:block">ESTIMATED · OPTICAL TRACKING</span>}
      >
        Pace &amp; Sprints
      </V2Title>
      <div className="grid md:grid-cols-[1fr_1.4fr] gap-5 items-center">
        <button
          type="button"
          data-testid="v2-pace-top"
          onClick={() => onPlayAt?.(pace.top_speed_t)}
          className="bg-[#12402A] rounded-[14px] px-5 py-6 text-center group w-full"
        >
          <span className="block text-[9.5px] font-extrabold tracking-[0.16em] text-[#A9BC9C] uppercase">Top speed (est.)</span>
          <span className="block font-barlow font-black text-[44px] leading-none text-[#CCFF00] mt-2">
            {pace.top_speed_kmh}
            <span className="text-[16px] ml-1">km/h</span>
          </span>
          <span className="block mt-1.5 text-[11px] font-bold text-white/80" data-testid="v2-pace-top-at">
            at {mmss(pace.top_speed_t)} in your clip
          </span>
          {trust && (
            <span className="mt-2 inline-flex items-center gap-1.5 text-[9px] font-extrabold tracking-[0.06em] uppercase text-[#CCFF00]" data-testid="v2-pace-trust">
              <ShieldCheck className="w-3 h-3" /> {trust}
            </span>
          )}
          <span className="mt-2.5 flex items-center justify-center gap-1.5 text-[10px] font-extrabold tracking-[0.1em] text-white/70 uppercase group-hover:text-white transition-colors">
            <Play className="w-3 h-3 fill-current" /> Watch the moment
          </span>
        </button>
        <div>
          <div className="grid grid-cols-3 gap-2.5">
            {stats.map(({ icon: Icon, label, sub, value, testid }) => (
              <div key={label} className="bg-[#FBF9F3] border border-[#E5DFCE] rounded-[11px] p-3 text-center">
                <Icon className="w-4 h-4 mx-auto text-[#1E5B3C]" />
                <div data-testid={testid} className="font-barlow font-black text-[20px] mt-1 leading-none">{value}</div>
                <div className="text-[8.5px] font-extrabold tracking-[0.08em] uppercase text-[#4B5563] mt-1 leading-[1.35]">{label}</div>
                <div className="text-[8px] text-[#8B957F] leading-tight">{sub}</div>
              </div>
            ))}
          </div>
          <p className="text-[10.5px] text-[#8B957F] leading-[1.5] mt-3" data-testid="v2-pace-note">
            Estimated from frame-by-frame optical tracking, scaled by age-typical body height (±10-15%).
            Measured only in the {pace.tracked_seconds}s where your player was securely tracked — never guessed.
            {pace.top_trust ? " The top speed is only reported from an identity-verified moment." : ""}
          </p>
        </div>
      </div>
    </V2Card>
  );
}
