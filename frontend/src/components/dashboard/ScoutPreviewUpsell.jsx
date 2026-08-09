import React from "react";
import { SkillBars } from "./SkillBars";
import { Lock, Crown, CheckCircle2 } from "lucide-react";

const DEMO_BARS = [
  { label: "Technical", value: 7.8 },
  { label: "Tactical", value: 8.4 },
  { label: "Physical", value: 7.2 },
  { label: "Mental", value: 8.6 },
];

const PERKS = [
  "Full match analysis on every upload",
  "Player benchmarks against your age group",
  "Detailed PDF scout report",
  "Visible in the Scout Library",
  "Messages from agents, scouts & clubs",
];

/* Free-user FOMO panel — shows what a premium performance panel looks like
 * (demo data, clearly tagged) and sells the dream. */
export default function ScoutPreviewUpsell({ playersCount, onSeePlans }) {
  return (
    <div
      data-testid="scout-preview-upsell"
      className="mt-8 bg-cream-card border border-gray-border rounded-3xl p-6 md:p-8 grid md:grid-cols-2 gap-7 items-center"
    >
      <div>
        <span className="inline-flex w-12 h-12 rounded-2xl bg-forest/10 text-forest items-center justify-center mb-4">
          <Lock className="w-5 h-5" />
        </span>
        <h3 className="font-barlow font-black uppercase text-2xl md:text-3xl tracking-tight leading-[1.05]">
          See what scouts see.<br /><span className="text-forest">Unlock your story.</span>
        </h3>
        <ul className="mt-4 space-y-2">
          {PERKS.map((p) => (
            <li key={p} className="flex items-center gap-2 text-sm text-ink/75">
              <CheckCircle2 className="w-4 h-4 text-forest shrink-0" /> {p}
            </li>
          ))}
        </ul>
        {playersCount ? (
          <p className="mt-4 text-[12px] font-bold text-ink/55" data-testid="upsell-fomo-line">
            <span className="text-forest">{Number(playersCount).toLocaleString()} players</span> are already visible to scouts. Don't stay unseen.
          </p>
        ) : null}
        <div
          className="mt-3 border border-amber-300/70 bg-amber-50 rounded-xl px-3.5 py-2.5 text-[12px] text-amber-900 leading-snug"
          data-testid="upsell-visibility-notice"
        >
          <b>Heads up:</b> on the Free plan your uploads are <b>not visible to scouts</b>. Upgrade to
          enter the Scout Library — or opt in to social-media featuring (below) if you'd like us to
          show off your clip.
        </div>
      </div>
      <div>
        <div className="relative rounded-2xl p-5 text-white overflow-hidden" style={{ background: "#0F1F14" }}>
          <div className="flex items-center justify-between mb-4">
            <span className="text-[12px] text-white/60">Scout Report Preview</span>
            <span className="text-[9px] uppercase tracking-[0.18em] font-black text-[#CCFF00] bg-white/5 border border-[#CCFF00]/30 px-2 py-0.5 rounded-full">
              Demo preview
            </span>
          </div>
          <div className="flex items-center gap-5">
            <div className="shrink-0">
              <div className="relative w-[92px] h-[92px]">
                <div className="absolute inset-0 rounded-full" style={{ background: "conic-gradient(#CCFF00 0 82%, rgba(255,255,255,0.08) 82% 100%)" }} />
                <div className="absolute inset-[8px] rounded-full flex flex-col items-center justify-center" style={{ background: "#0F1F14" }}>
                  <span className="font-barlow font-black text-[26px] leading-none">82</span>
                  <span className="text-[9px] text-white/50 font-bold">/ 100</span>
                </div>
              </div>
              <div className="mt-2 text-center text-[9px] uppercase tracking-[0.16em] font-bold text-white/50">Overall</div>
            </div>
            <SkillBars scores={DEMO_BARS} compact />
          </div>
        </div>
        <button
          type="button"
          onClick={onSeePlans}
          data-testid="upsell-see-plans-btn"
          className="mt-4 w-full flex items-center justify-center gap-2 bg-forest hover:bg-forest-pop text-white font-barlow font-black uppercase tracking-widest text-sm px-5 py-3.5 rounded-full transition-colors"
        >
          <Crown className="w-4 h-4" /> See plans
        </button>
      </div>
    </div>
  );
}
