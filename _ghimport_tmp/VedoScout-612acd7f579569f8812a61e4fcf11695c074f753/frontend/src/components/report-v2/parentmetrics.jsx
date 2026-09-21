// Parent Value Metrics — the questions families actually ask, answered from evidence.
import React from "react";
import { HeartHandshake, Activity, Swords, RefreshCcw, Footprints, Play } from "lucide-react";
import { V2Card, V2Title } from "./sections";
import { canUseAuthorityProof } from "@/lib/authorityJoin.mjs";

const REACTION_META = {
  strong: { label: "Strong response", cls: "bg-[#12402A] text-[#CCFF00]" },
  neutral: { label: "Neutral response", cls: "bg-[#E5DFCE] text-[#5C6657]" },
  concerning: { label: "Needs support", cls: "bg-[#FFF1E0] text-[#A05A1C]" },
};

function MetricTile({ icon: Icon, label, value, note, testid }) {
  return (
    <div className="bg-[#FBF9F3] border border-[#E5DFCE] rounded-[11px] p-3.5" data-testid={testid}>
      <div className="flex items-center gap-2">
        <Icon className="w-4 h-4 text-[#1E5B3C]" />
        <span className="text-[9px] font-extrabold tracking-[0.12em] uppercase text-[#75816F]">{label}</span>
      </div>
      <div className="font-barlow font-black text-[22px] leading-none mt-2">{value}</div>
      {note && <p className="text-[10.5px] text-[#6B755F] leading-[1.45] mt-1.5">{note}</p>}
    </div>
  );
}

export function ParentValueMetricsCard({ metrics, onPlayAt }) {
  const m = metrics || {};
  // FIX 02 — authority: LLM point moments open proof only when ID + fail-closed
  // proof state exist; broad "top minute" ranges stay informational text.
  const authority = !!m.authority;
  if (!m.involvement && !m.bravery && !m.reaction && !m.offBall && !m.topMinutes?.length) return null;
  const inv = m.involvement;
  const reaction = m.reaction;
  const rMeta = REACTION_META[String(reaction?.rating || "").toLowerCase()];
  return (
    <V2Card testid="v2-parent-metrics-card">
      <V2Title
        icon={HeartHandshake}
        right={<span className="text-[10px] font-extrabold tracking-[0.14em] text-[#CCFF00] bg-[#12402A] px-2.5 py-1 rounded-[5px] hidden md:block">EVIDENCE ONLY · NEVER GUESSED</span>}
      >
        What Parents Ask
      </V2Title>
      <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-3">
        {inv && (
          <MetricTile
            icon={Activity}
            label="Involvement"
            value={inv.touches_observed != null ? `${inv.touches_observed} touches` : "—"}
            note={[inv.touches_per_minute != null ? `≈ ${inv.touches_per_minute}/min.` : null, inv.note].filter(Boolean).join(" ")}
            testid="v2-pm-involvement"
          />
        )}
        {m.bravery && (
          <MetricTile
            icon={Swords}
            label="Bravery"
            value={m.bravery.score != null ? `${m.bravery.score}/10` : "Not testable"}
            note={m.bravery.note}
            testid="v2-pm-bravery"
          />
        )}
        {reaction && (
          <div className="bg-[#FBF9F3] border border-[#E5DFCE] rounded-[11px] p-3.5" data-testid="v2-pm-reaction">
            <div className="flex items-center gap-2">
              <RefreshCcw className="w-4 h-4 text-[#1E5B3C]" />
              <span className="text-[9px] font-extrabold tracking-[0.12em] uppercase text-[#75816F]">Reaction after mistake</span>
            </div>
            {reaction.observed && rMeta ? (
              <div className="mt-2 flex items-center gap-2 flex-wrap">
                <span className={`text-[10px] font-extrabold tracking-[0.08em] uppercase px-2 py-1 rounded-[5px] ${rMeta.cls}`}>{rMeta.label}</span>
                {reaction.timestamp && (
                  canUseAuthorityProof(authority, reaction) ? (
                    <button
                      type="button"
                      onClick={() => onPlayAt?.(reaction.timestamp, { evidenceId: reaction.evidence_id, eventId: reaction.event_id })}
                      className="inline-flex items-center gap-1 text-[10px] font-bold text-[#1E5B3C] hover:text-[#12402A]"
                      data-testid="v2-pm-reaction-ts"
                    >
                      <Play className="w-2.5 h-2.5 fill-current" /> {reaction.timestamp}
                    </button>
                  ) : (
                    <span className="inline-flex items-center gap-1 text-[10px] font-bold text-[#75816F]" data-testid="v2-pm-reaction-ts">
                      {reaction.timestamp}
                    </span>
                  )
                )}
              </div>
            ) : (
              <div className="font-barlow font-black text-[15px] leading-tight mt-2 text-[#75816F]">No clear mistake in this footage</div>
            )}
            {reaction.note && <p className="text-[10.5px] text-[#6B755F] leading-[1.45] mt-1.5">{reaction.note}</p>}
          </div>
        )}
        {m.offBall && (
          <MetricTile
            icon={Footprints}
            label="Off-ball work"
            value={m.offBall.score != null ? `${m.offBall.score}/10` : "Not visible"}
            note={m.offBall.note}
            testid="v2-pm-offball"
          />
        )}
      </div>
      {m.topMinutes?.length > 0 && (
        <div className="mt-4 bg-[#12402A] rounded-[11px] p-4" data-testid="v2-pm-topminutes">
          <span className="text-[9.5px] font-extrabold tracking-[0.16em] uppercase text-[#A9BC9C]">
            Top {m.topMinutes.length === 1 ? "minute" : `${m.topMinutes.length} minutes`} — watch these first
          </span>
          <div className="mt-2.5 space-y-2">
            {m.topMinutes.map((t, i) => (
              authority ? (
                <div
                  key={i}
                  data-testid={`v2-pm-topmin-${i}`}
                  className="w-full text-left flex items-start gap-2.5"
                >
                  <span className="shrink-0 inline-flex items-center gap-1 bg-[#CCFF00] text-[#0D2818] text-[10px] font-black px-2 py-0.5 rounded-[4px]">
                    {t.from}{t.to ? `–${t.to}` : ""}
                  </span>
                  <span className="text-[11.5px] text-white/80 leading-[1.45]">{t.why}</span>
                </div>
              ) : (
                <button
                  key={i}
                  type="button"
                  data-testid={`v2-pm-topmin-${i}`}
                  onClick={() => onPlayAt?.(t.from)}
                  className="w-full text-left flex items-start gap-2.5 group"
                >
                  <span className="shrink-0 inline-flex items-center gap-1 bg-[#CCFF00] text-[#0D2818] text-[10px] font-black px-2 py-0.5 rounded-[4px]">
                    <Play className="w-2.5 h-2.5 fill-current" /> {t.from}{t.to ? `–${t.to}` : ""}
                  </span>
                  <span className="text-[11.5px] text-white/80 leading-[1.45] group-hover:text-white transition-colors">{t.why}</span>
                </button>
              )
            ))}
          </div>
        </div>
      )}
    </V2Card>
  );
}
