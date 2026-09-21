// Next Match Missions — 3 countable process goals for the child's next match.
import React from "react";
import { Target, Square } from "lucide-react";
import { V2Card, V2Title } from "./sections";

export function MissionsCard({ missions }) {
  if (!missions?.length) return null;
  return (
    <V2Card testid="v2-missions-card">
      <V2Title
        icon={Target}
        right={<span className="text-[11px] font-extrabold tracking-[0.14em] text-[#1E5B3C] hidden md:block">PRINTABLE CARD IN YOUR PDF · TICK THEM OFF AFTER THE MATCH</span>}
      >
        Next Match Missions
      </V2Title>
      <div className="grid md:grid-cols-3 gap-4">
        {missions.slice(0, 3).map((m, i) => (
          <div key={i} data-testid={`v2-mission-${i}`} className="bg-[#FBF9F3] border border-[#E5DFCE] rounded-[12px] p-4 flex flex-col">
            <div className="flex items-start justify-between gap-2 mb-2">
              <span className="w-7 h-7 rounded-full bg-[#12402A] text-[#CCFF00] font-barlow font-black text-[14px] flex items-center justify-center shrink-0">{i + 1}</span>
              {m.target && <span className="bg-[#CCFF00] text-[#101B12] font-barlow font-extrabold text-[11px] px-2.5 py-1 rounded-[6px] uppercase shrink-0">{m.target}</span>}
            </div>
            <div className="flex gap-2 items-start">
              <Square className="w-4 h-4 text-[#9CB89A] shrink-0 mt-0.5" />
              <span className="text-[13px] font-extrabold leading-snug">{m.mission}</span>
            </div>
            {m.why && <p className="text-[11px] text-[#8B957F] leading-[1.5] mt-2">{m.why}</p>}
          </div>
        ))}
      </div>
    </V2Card>
  );
}
