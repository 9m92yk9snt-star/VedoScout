// Dream Path — "Vejen til drømmen". A vertical, honest development roadmap.
// 100% derived from existing analysis data (tier, priorities, progression) —
// it moves with every new analysis. Never promises academies or contracts.
import React from "react";
import { Check, Lock, TrendingUp, ShieldCheck, Sparkles, Flag, ArrowRight, MapPin } from "lucide-react";

const LIME = "#CCFF00";
const INKG = "#0B1F14";

export const LADDER = [
  { key: "foundation",    title: "Enjoying the Game",   sub: "Playing, smiling, building the basics" },
  { key: "standard_club", title: "Club Player",         sub: "A solid, trusted part of the team" },
  { key: "strong_club",   title: "Strong Club Player",  sub: "Stands out in their own matches" },
  { key: "pro_academy",   title: "Academy Level",       sub: "The level where licensed academies watch" },
  { key: "elite_academy", title: "Elite Academy Level", sub: "Among the strongest in the age group" },
  { key: "horizon",       title: "Elite Youth Pathway", sub: "Where the dream becomes a plan" },
];

const TIER_INDEX = { standard_club: 1, strong_club: 2, pro_academy: 3, elite_academy: 4 };

export function deriveDreamPath(report, d) {
  const full = report?.full_report || {};
  const ob = full.overall_benchmark || {};
  const tier = String(ob.tier || "").toLowerCase();
  let cur = TIER_INDEX[tier];
  if (cur == null) {
    const dots = d?.scoutOutlook?.currentDots;
    cur = Math.min(4, Math.max(1, (typeof dots === "number" ? dots : 3) - 1));
  }
  const prog = report?.progression || null;
  const overallDelta = prog?.categories?.find?.((c) => c.key === "overall_development")?.delta ?? null;
  return {
    cur,
    currentLabel: d?.scoutOutlook?.currentLabel || LADDER[cur].title,
    percentile: ob.percentile || null,
    separates: ob.what_separates_from_next_tier || null,
    nextStep: ob.realistic_next_step || null,
    requirements: (d?.devPriorities || []).slice(0, 3),
    prog,
    overallDelta,
    improvements: Array.isArray(prog?.improvements) ? prog.improvements.slice(0, 2) : [],
  };
}

function Node({ state }) {
  if (state === "done") {
    return (
      <span className="w-8 h-8 rounded-full flex items-center justify-center shrink-0 z-10" style={{ background: "#1F4F2F", border: "1.5px solid rgba(204,255,0,0.35)" }}>
        <Check className="w-4 h-4 text-white" strokeWidth={3} />
      </span>
    );
  }
  if (state === "current") {
    return (
      <span className="relative w-9 h-9 rounded-full flex items-center justify-center shrink-0 z-10" style={{ background: LIME }}>
        <span className="absolute inset-0 rounded-full animate-ping opacity-30" style={{ background: LIME }} />
        <MapPin className="w-4.5 h-4.5 relative" style={{ color: INKG }} strokeWidth={2.5} />
      </span>
    );
  }
  if (state === "next") {
    return (
      <span className="w-8 h-8 rounded-full flex items-center justify-center shrink-0 z-10 bg-transparent" style={{ border: `2px dashed rgba(204,255,0,0.6)` }}>
        <Flag className="w-3.5 h-3.5" style={{ color: LIME }} />
      </span>
    );
  }
  return (
    <span className="w-8 h-8 rounded-full flex items-center justify-center shrink-0 z-10 border border-white/15">
      <Lock className="w-3.5 h-3.5 text-white/35" />
    </span>
  );
}

export function DreamPathSection({ report, d, playerName }) {
  const dp = deriveDreamPath(report, d);
  const first = (playerName || "").split(" ")[0] || "Player";
  const stepsLeft = LADDER.length - 1 - dp.cur;

  return (
    <section className="rounded-[22px] p-5 sm:p-8 overflow-hidden relative" style={{ background: INKG }} data-testid="dream-path-section">
      {/* header */}
      <div className="relative">
        <span className="inline-flex items-center gap-1.5 rounded-full px-3.5 py-1.5 font-barlow font-black text-[11px] tracking-[0.18em]" style={{ background: LIME, color: INKG }}>
          <Sparkles className="w-3.5 h-3.5" /> THE PATH
        </span>
        <h2 className="mt-3 font-barlow font-black uppercase text-white text-2xl sm:text-4xl tracking-tighter leading-[0.95]">
          {first}&rsquo;s road to the dream
        </h2>
        <p className="mt-2 text-white/65 text-[13.5px] sm:text-[15px] max-w-2xl leading-relaxed">
          You&rsquo;re not just dreaming, {first} — you&rsquo;re standing on step {dp.cur + 1} of {LADDER.length}.
          {stepsLeft > 0 ? " Here's exactly what moves you to the next one." : " Keep protecting the level you've reached."}
        </p>
      </div>

      {/* momentum banner */}
      <div className="mt-4" data-testid="dp-momentum">
        {dp.prog ? (
          <div className="rounded-xl px-4 py-3 flex flex-wrap items-center gap-x-4 gap-y-1.5 bg-white/5 border border-white/10">
            <span className="flex items-center gap-1.5 text-[12px] font-black uppercase tracking-[0.1em]" style={{ color: LIME }}>
              <TrendingUp className="w-4 h-4" /> Since your last analysis
            </span>
            {typeof dp.overallDelta === "number" && (
              <span className={`text-[12.5px] font-bold ${dp.overallDelta >= 0 ? "text-white" : "text-white/70"}`}>
                Overall {dp.overallDelta > 0 ? `+${dp.overallDelta}` : dp.overallDelta === 0 ? "steady" : dp.overallDelta}
              </span>
            )}
            {dp.improvements.map((im) => (
              <span key={im.key} className="text-[12.5px] font-bold text-white">{im.label} +{im.delta}</span>
            ))}
            {!dp.improvements.length && typeof dp.overallDelta !== "number" && (
              <span className="text-[12.5px] text-white/70">Movement is measured on every upload.</span>
            )}
          </div>
        ) : (
          <div className="rounded-xl px-4 py-3 flex items-center gap-2.5 bg-white/5 border border-white/10">
            <Flag className="w-4 h-4 shrink-0" style={{ color: LIME }} />
            <span className="text-[12.5px] text-white/80">
              <span className="font-black uppercase tracking-[0.08em]" style={{ color: LIME }}>Starting point locked in.</span>{" "}
              Your next analysis measures the first movement on this path.
            </span>
          </div>
        )}
      </div>

      {/* vertical roadmap */}
      <div className="relative mt-6">
        <span className="absolute left-[15px] top-2 bottom-2 w-[2px]" style={{ background: "linear-gradient(180deg, rgba(204,255,0,0.55) 0%, rgba(204,255,0,0.25) 45%, rgba(255,255,255,0.08) 100%)" }} />
        <div className="space-y-5">
          {LADDER.map((lv, i) => {
            const state = i < dp.cur ? "done" : i === dp.cur ? "current" : i === dp.cur + 1 ? "next" : "future";
            return (
              <div key={lv.key} className="relative flex gap-4 items-start" data-testid={`dp-step-${lv.key}`}>
                <Node state={state} />
                <div className="flex-1 min-w-0 pt-0.5">
                  {state === "done" && (
                    <div>
                      <p className="font-barlow font-black uppercase text-white/85 text-[15px] tracking-tight">{lv.title}</p>
                      <p className="text-[11.5px] text-white/40 flex items-center gap-1.5 mt-0.5">
                        <Check className="w-3 h-3" style={{ color: LIME }} /> Already part of {first}&rsquo;s story
                      </p>
                    </div>
                  )}

                  {state === "current" && (
                    <div className="rounded-2xl p-4 bg-white/[0.07]" style={{ border: `1.5px solid rgba(204,255,0,0.55)` }} data-testid="dp-you-are-here">
                      <span className="inline-block rounded-md px-2.5 py-1 font-barlow font-black text-[10px] tracking-[0.18em]" style={{ background: LIME, color: INKG }}>
                        YOU ARE HERE
                      </span>
                      <p className="mt-2 font-barlow font-black uppercase text-white text-xl tracking-tight">{dp.currentLabel}</p>
                      <p className="text-[12px] text-white/55 mt-0.5">{lv.sub}</p>
                      {dp.percentile && (
                        <p className="mt-2 text-[12.5px] font-bold" style={{ color: LIME }}>{dp.percentile}</p>
                      )}
                      <p className="mt-1.5 text-[11px] text-white/45 uppercase tracking-[0.12em] font-bold">Placed by this analysis — every upload re-measures it</p>
                    </div>
                  )}

                  {state === "next" && (
                    <div className="rounded-2xl p-4 bg-white/[0.04]" style={{ border: "1.5px dashed rgba(204,255,0,0.45)" }} data-testid="dp-next-step">
                      <span className="inline-flex items-center gap-1.5 text-[10px] font-black uppercase tracking-[0.18em]" style={{ color: LIME }}>
                        <Flag className="w-3.5 h-3.5" /> Next step
                      </span>
                      <p className="mt-1.5 font-barlow font-black uppercase text-white text-lg tracking-tight">{lv.title}</p>
                      {dp.nextStep && <p className="text-[12.5px] text-white/70 mt-1 leading-snug">{dp.nextStep}</p>}
                      {dp.separates && (
                        <p className="text-[12px] text-white/50 mt-1.5 leading-snug">
                          <span className="font-bold text-white/70">What separates {first} from this level:</span> {dp.separates}
                        </p>
                      )}
                      {dp.requirements.length > 0 && (
                        <div className="mt-3 space-y-2">
                          {dp.requirements.map((r) => (
                            <div key={r.name} className="rounded-xl bg-black/25 px-3 py-2.5">
                              <div className="flex items-center justify-between gap-2">
                                <span className="text-[12.5px] font-black text-white uppercase tracking-wide">{r.name}</span>
                                {typeof r.score === "number" && (
                                  <span className="flex items-center gap-1 text-[12px] font-black shrink-0">
                                    <span className="text-white/60">{r.score}</span>
                                    <ArrowRight className="w-3 h-3" style={{ color: LIME }} />
                                    <span style={{ color: LIME }}>{Math.min(10, Math.round(r.score) + 1)}</span>
                                  </span>
                                )}
                              </div>
                              {r.howTo && <p className="text-[11.5px] text-white/55 mt-1 leading-snug">{r.howTo}</p>}
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  )}

                  {state === "future" && (
                    <div className="opacity-55">
                      <p className="font-barlow font-black uppercase text-white/70 text-[15px] tracking-tight">{lv.title}</p>
                      <p className="text-[11.5px] text-white/35 mt-0.5">{lv.sub}</p>
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* honest note */}
      <div className="mt-6 rounded-xl bg-white/[0.04] border border-white/10 px-4 py-3 flex items-start gap-2.5">
        <ShieldCheck className="w-4 h-4 shrink-0 mt-0.5" style={{ color: LIME }} />
        <p className="text-[11.5px] text-white/55 leading-relaxed">
          No one can promise the path — not us, not anyone. What we do is show the realistic next step
          and measure it honestly, analysis after analysis. That&rsquo;s how dreams become plans.
        </p>
      </div>
    </section>
  );
}

// ── Free-preview teaser: first steps visible, the journey locked ──
export function DreamPathTeaser({ playerName, onUnlock }) {
  const first = (playerName || "").split(" ")[0] || "your player";
  const lockedTitles = ["Your current level", "Next step + what it takes", "Academy level", "Elite youth pathway"];
  return (
    <div className="rounded-[22px] p-5 sm:p-6 mt-4 relative overflow-hidden" style={{ background: INKG }} data-testid="dream-path-teaser">
      <span className="inline-flex items-center gap-1.5 rounded-full px-3 py-1 font-barlow font-black text-[10px] tracking-[0.18em]" style={{ background: LIME, color: INKG }}>
        <Sparkles className="w-3 h-3" /> THE PATH
      </span>
      <h3 className="mt-2.5 font-barlow font-black uppercase text-white text-xl sm:text-2xl tracking-tighter leading-[0.95]">
        The road to {first}&rsquo;s dream
      </h3>
      <p className="mt-1.5 text-white/60 text-[12.5px] leading-snug max-w-md">
        A step-by-step development roadmap — where {first} is now, and exactly what moves them to the next level.
      </p>

      <div className="relative mt-4">
        <span className="absolute left-[13px] top-2 bottom-2 w-[2px]" style={{ background: "linear-gradient(180deg, rgba(204,255,0,0.5), rgba(255,255,255,0.06))" }} />
        <div className="space-y-3.5">
          <div className="relative flex gap-3.5 items-center">
            <span className="w-7 h-7 rounded-full flex items-center justify-center shrink-0 z-10" style={{ background: "#1F4F2F", border: "1.5px solid rgba(204,255,0,0.35)" }}>
              <Check className="w-3.5 h-3.5 text-white" strokeWidth={3} />
            </span>
            <p className="text-[13px] font-bold text-white/85">Video analysed — level placed</p>
          </div>
          {lockedTitles.map((t, i) => (
            <div key={t} className="relative flex gap-3.5 items-center">
              <span className="relative w-7 h-7 rounded-full flex items-center justify-center shrink-0 z-10 border border-white/15">
                {i === 0 ? (
                  <span className="w-7 h-7 rounded-full flex items-center justify-center" style={{ background: LIME }}>
                    <MapPin className="w-3.5 h-3.5" style={{ color: INKG }} />
                  </span>
                ) : (
                  <Lock className="w-3 h-3 text-white/35" />
                )}
              </span>
              <div className="flex items-center gap-2 min-w-0">
                {i === 0 && (
                  <span className="rounded px-1.5 py-0.5 font-barlow font-black text-[9px] tracking-[0.14em] shrink-0" style={{ background: LIME, color: INKG }}>YOU ARE HERE</span>
                )}
                <p className={`text-[13px] font-bold text-white/80 select-none ${i === 0 ? "blur-[5px]" : "blur-[4px] opacity-60"}`} aria-hidden>
                  {t}
                </p>
                <Lock className="w-3 h-3 text-white/40 shrink-0" />
              </div>
            </div>
          ))}
        </div>
      </div>

      <button
        type="button"
        onClick={onUnlock}
        data-testid="dp-unlock"
        className="mt-5 w-full rounded-xl py-3.5 font-barlow font-black uppercase tracking-[0.14em] text-[13px] flex items-center justify-center gap-2 active:scale-[0.98] transition-transform"
        style={{ background: LIME, color: INKG }}
      >
        Walk {first}&rsquo;s road to the dream <ArrowRight className="w-4 h-4" />
      </button>
      <p className="mt-2 text-center text-[10.5px] text-white/40">
        Updated with every new analysis — see {first} move step by step.
      </p>
    </div>
  );
}
