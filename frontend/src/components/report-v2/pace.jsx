// Pace & Sprints — estimates derived from the same optical tracking as the Movement Map.
import React from "react";
import { Gauge, Zap, Route, Timer, Play } from "lucide-react";
import { V2Card, V2Title } from "./sections";

export function PaceCard({ pace, onPlayAt }) {
  if (!pace?.top_speed_kmh) return null;
  const stats = [
    { icon: Zap, label: "Sprints", sub: `above ${pace.sprint_threshold_kmh} km/h`, value: pace.sprint_count, testid: "v2-pace-sprints" },
    { icon: Route, label: "Distance covered", sub: "while tracked", value: `${pace.distance_tracked_m} m`, testid: "v2-pace-distance" },
    { icon: Timer, label: "Moving pace", sub: "median while moving", value: pace.avg_moving_kmh ? `${pace.avg_moving_kmh} km/h` : "—", testid: "v2-pace-avg" },
  ];
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
          <span className="mt-3 inline-flex items-center gap-1.5 text-[10px] font-extrabold tracking-[0.1em] text-white/70 uppercase group-hover:text-white transition-colors">
            <Play className="w-3 h-3 fill-current" /> Watch the moment · {pace.top_speed_t}s
          </span>
        </button>
        <div>
          <div className="grid grid-cols-3 gap-2.5">
            {stats.map(({ icon: Icon, label, sub, value, testid }) => (
              <div key={label} className="bg-[#FBF9F3] border border-[#E5DFCE] rounded-[11px] p-3 text-center">
                <Icon className="w-4 h-4 mx-auto text-[#1E5B3C]" />
                <div data-testid={testid} className="font-barlow font-black text-[20px] mt-1 leading-none">{value}</div>
                <div className="text-[8.5px] font-extrabold tracking-[0.08em] uppercase text-[#75816F] mt-1 leading-[1.35]">{label}</div>
                <div className="text-[8px] text-[#8B957F] leading-tight">{sub}</div>
              </div>
            ))}
          </div>
          <p className="text-[10.5px] text-[#8B957F] leading-[1.5] mt-3" data-testid="v2-pace-note">
            Estimated from frame-by-frame optical tracking, scaled by age-typical body height (±10-15%).
            Measured only in the {pace.tracked_seconds}s where your player was securely tracked — never guessed.
          </p>
        </div>
      </div>
    </V2Card>
  );
}
