import React, { useEffect, useState, useCallback, useRef } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { motion } from "framer-motion";
import {
  Radar, RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, ResponsiveContainer,
} from "recharts";
import Navigation from "@/components/Navigation";
import api, { ASSET_BASE } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import {
  Lock, Unlock, Download, Loader2, ChevronLeft, ShieldCheck, Star, AlertTriangle, Eye, Info, Check, Share2,
} from "lucide-react";
import ScoutReview from "@/components/ScoutReview";
import CheckoutTransitionModal from "@/components/CheckoutTransitionModal";
import EmbeddedCheckoutModal from "@/components/EmbeddedCheckoutModal";
import PaymentBadges from "@/components/PaymentBadges";

/* Tier visual treatment — 4 levels mapped to colour + label */
const TIER_META = {
  elite_academy:  { rank: 4, label: "Elite Academy",     dot: "bg-emerald-500", text: "text-emerald-700", border: "border-emerald-500" },
  pro_academy:    { rank: 3, label: "Pro Academy",       dot: "bg-volt",        text: "text-volt",        border: "border-volt" },
  strong_club:    { rank: 2, label: "Strong Club",       dot: "bg-amber-500",   text: "text-amber-700",   border: "border-amber-500" },
  standard_club:  { rank: 1, label: "Standard Club",     dot: "bg-stone-500",   text: "text-stone-600",   border: "border-stone-400" },
};

function TierBadge({ tier, size = "md" }) {
  const t = TIER_META[tier];
  if (!t) return null;
  const cls = size === "sm"
    ? "text-[9px] tracking-[0.18em] px-1.5 py-0.5"
    : "text-[10px] tracking-[0.22em] px-2 py-1";
  return (
    <span
      data-testid={`tier-badge-${tier}`}
      className={`inline-flex items-center gap-1.5 uppercase font-bold border ${t.border} ${t.text} bg-cream-card ${cls}`}
    >
      <span className={`w-1.5 h-1.5 rounded-full ${t.dot}`} />
      {t.label}
    </span>
  );
}

/* Visual benchmark bar — 4 segments, the one matching `tier` is highlighted.
   Each segment shows the score range expected for that tier at the player's age+position. */
function BenchmarkBar({ tier, benchmarks }) {
  if (!benchmarks || typeof benchmarks !== "object") return null;
  const order = ["standard_club", "strong_club", "pro_academy", "elite_academy"];
  return (
    <div className="mt-3" data-testid="benchmark-bar">
      <div className="text-[9px] uppercase tracking-[0.22em] font-bold text-ink/45 mb-1.5">
        Age + position benchmark
      </div>
      <div className="grid grid-cols-4 gap-0.5">
        {order.map((k) => {
          const t = TIER_META[k];
          const active = k === tier;
          return (
            <div
              key={k}
              data-testid={`benchmark-seg-${k}`}
              className={`px-2 py-2 border ${active ? `${t.border} bg-cream-soft/40` : "border-gray-border bg-cream-card"} ${active ? "" : "opacity-65"}`}
            >
              <div className="flex items-center gap-1">
                <span className={`w-1 h-1 rounded-full ${t.dot}`} />
                <span className={`text-[8.5px] uppercase tracking-[0.16em] font-bold ${active ? t.text : "text-ink/45"}`}>
                  {t.label}
                </span>
              </div>
              <div className={`mt-0.5 font-barlow font-black ${active ? `${t.text} text-base` : "text-ink/55 text-sm"}`}>
                {benchmarks[k] || "—"}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

/* Visual treatment for confidence badges (high / medium / low). */
const CONFIDENCE_STYLES = {
  high: { color: "text-volt", border: "border-volt/40", bg: "bg-volt/10", label: "High confidence" },
  medium: { color: "text-yellow-300", border: "border-yellow-300/40", bg: "bg-yellow-300/10", label: "Medium confidence" },
  low: { color: "text-orange-300", border: "border-orange-300/40", bg: "bg-orange-300/10", label: "Low confidence" },
};
function ConfidenceBadge({ level, reason }) {
  const c = CONFIDENCE_STYLES[level];
  if (!c) return null;
  return (
    <span
      title={reason || c.label}
      className={`inline-flex items-center gap-1 text-[9px] uppercase tracking-[0.18em] font-bold border ${c.border} ${c.bg} ${c.color} px-1.5 py-0.5`}
    >
      <ShieldCheck className="w-3 h-3" strokeWidth={2} />
      {c.label.replace(" confidence", "")}
    </span>
  );
}

function scoreColor(s) {
  if (typeof s !== "number") return "text-ink";
  if (s >= 8) return "text-volt";
  if (s >= 6) return "text-yellow-400";
  return "text-red-400";
}

function SectionGrid({ title, section }) {
  if (!section) return null;
  return (
    <div className="bg-surface border border-gray-border p-6 md:p-8">
      <h3 className="font-barlow font-black uppercase text-2xl md:text-3xl text-ink">{title}</h3>
      <div className="mt-6 grid sm:grid-cols-2 gap-4">
        {Object.entries(section).map(([key, val]) => {
          const cannotEval = val?.cannot_evaluate === true;
          const confidence = val?.confidence;
          const evidence = Array.isArray(val?.evidence) ? val.evidence : [];
          const tier = val?.tier_for_age;
          const benchmarks = val?.benchmarks;
          const whyScore = val?.why_this_score;
          const verdict = val?.verdict;
          return (
            <div
              key={key}
              data-testid={`attr-card-${key}`}
              className="bg-cream-card border border-gray-border p-5"
            >
              <div className="flex items-start justify-between gap-2 mb-2">
                <div className="min-w-0">
                  <span className="text-xs uppercase tracking-[0.18em] font-bold text-ink/65">{key.replace(/_/g, " ")}</span>
                  {tier && !cannotEval && (
                    <div className="mt-1.5">
                      <TierBadge tier={tier} size="sm" />
                    </div>
                  )}
                </div>
                {cannotEval ? (
                  <span className="text-[10px] uppercase tracking-widest font-bold text-orange-300 border border-orange-300/40 bg-orange-300/10 px-2 py-0.5 whitespace-nowrap">
                    Need more footage
                  </span>
                ) : (
                  <span className={`font-barlow font-black text-3xl shrink-0 ${scoreColor(val?.score)}`}>
                    {val?.score ?? "-"}
                    <span className="text-ink/40 text-base">/10</span>
                  </span>
                )}
              </div>

              {cannotEval ? (
                <p className="text-xs text-ink/55 leading-relaxed italic">
                  {val?.evaluable_reason || val?.notes || "Not observable from this footage."}
                </p>
              ) : (
                <>
                  <p className="text-sm text-ink/75 leading-relaxed">{val?.notes}</p>

                  {whyScore && (
                    <div className="mt-3 pt-3 border-t border-gray-border">
                      <div className="text-[9px] uppercase tracking-[0.22em] font-bold text-volt mb-1">Why this score</div>
                      <p className="text-[13px] text-ink/80 leading-relaxed">{whyScore}</p>
                    </div>
                  )}

                  {benchmarks && tier && (
                    <BenchmarkBar tier={tier} benchmarks={benchmarks} />
                  )}

                  {verdict && (
                    <div className="mt-3 pt-3 border-t border-gray-border">
                      <p className="text-[12px] text-ink/70 leading-relaxed italic">
                        <span className="text-volt font-bold not-italic">›</span> {verdict}
                      </p>
                    </div>
                  )}
                </>
              )}

              {/* Confidence + evidence */}
              {confidence && !cannotEval && (
                <div className="mt-3 flex flex-wrap items-center gap-2">
                  <ConfidenceBadge level={confidence} reason={val?.confidence_reason} />
                  {typeof val?.observations_used === "number" && val.observations_used > 0 && (
                    <span className="text-[9px] uppercase tracking-widest font-bold text-ink/50">
                      · {val.observations_used} obs
                    </span>
                  )}
                </div>
              )}
              {evidence.length > 0 && (
                <details className="mt-2 group">
                  <summary className="cursor-pointer text-[10px] uppercase tracking-widest font-bold text-ink/50 hover:text-volt transition-colors list-none">
                    Show evidence ({evidence.length})
                  </summary>
                  <ul className="mt-2 space-y-1.5">
                    {evidence.map((e, idx) => (
                      <li key={idx} className="text-[11px] text-ink/70 flex gap-2">
                        <span className="font-barlow font-black text-volt min-w-[42px] tabular-nums">{e.timestamp || "·"}</span>
                        <span className="leading-snug">{e.what || e.note}</span>
                      </li>
                    ))}
                  </ul>
                </details>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

/* Hero banner shown above the full report — places overall_development in
   the calibrated age+position tier landscape so the customer instantly
   understands what the overall score MEANS. Styled as a forest hero panel
   (ink-on-forest) to stand out as the report's signature insight. */
function OverallBenchmarkBanner({ ob, overallScore }) {
  if (!ob) return null;
  const tier = ob.tier;
  const t = TIER_META[tier];
  if (!t) return null;
  return (
    <div
      data-testid="overall-benchmark-banner"
      className="relative overflow-hidden bg-forest p-6 md:p-10"
    >
      {/* Decorative diagonal accent stripe */}
      <div className="absolute top-0 right-0 h-full w-1 bg-forest-pop" />
      <div className="absolute -top-16 -right-16 w-56 h-56 bg-forest-pop/40 blur-3xl rounded-full pointer-events-none" />

      <div className="relative flex flex-col md:flex-row gap-8 md:items-start">
        {/* Big score + tier */}
        <div className="md:w-1/3 shrink-0">
          <div className="text-[10px] uppercase tracking-[0.28em] font-bold text-cream-base/80">How you compare</div>
          <div className="mt-3 flex items-baseline gap-2">
            <span className="font-barlow font-black text-7xl md:text-8xl text-white leading-[0.85]">
              {overallScore ?? "-"}
            </span>
            <span className="text-white/45 font-barlow font-black text-2xl">/10</span>
          </div>
          <div className="mt-4">
            <span
              data-testid={`overall-tier-${tier}`}
              className="inline-flex items-center gap-2 uppercase font-bold text-[11px] tracking-[0.22em] bg-cream-card text-forest border border-cream-card px-3 py-1.5"
            >
              <span className={`w-1.5 h-1.5 rounded-full ${t.dot}`} />
              {t.label}
            </span>
          </div>
          {ob.age_bracket_used && (
            <div className="mt-3 text-[10px] uppercase tracking-[0.22em] font-bold text-cream-base/65">
              calibrated for {ob.age_bracket_used.replace(/_/g, " ").toLowerCase()}
            </div>
          )}
        </div>

        {/* Narrative + next step */}
        <div className="flex-1 space-y-5">
          {ob.percentile && (
            <p
              data-testid="overall-percentile"
              className="text-lg md:text-xl text-white leading-snug font-medium"
            >
              {ob.percentile}
            </p>
          )}
          {ob.realistic_next_step && (
            <div>
              <div className="text-[9px] uppercase tracking-[0.28em] font-bold text-cream-base/80 mb-1.5">Realistic next step</div>
              <p data-testid="overall-next-step" className="text-sm md:text-base text-cream-base/90 leading-relaxed">{ob.realistic_next_step}</p>
            </div>
          )}
          {ob.what_separates_from_next_tier && (
            <div>
              <div className="text-[9px] uppercase tracking-[0.28em] font-bold text-cream-base/80 mb-1.5">To reach the next tier</div>
              <p data-testid="overall-next-tier-gap" className="text-sm md:text-base text-cream-base/90 leading-relaxed">{ob.what_separates_from_next_tier}</p>
            </div>
          )}
        </div>
      </div>

      {/* Tier landscape — horizontal scale showing player position */}
      <div className="relative mt-8 pt-6 border-t border-cream-base/15">
        <div className="text-[9px] uppercase tracking-[0.28em] font-bold text-cream-base/65 mb-3">Tier landscape</div>
        <div className="grid grid-cols-4 gap-0.5">
          {["standard_club", "strong_club", "pro_academy", "elite_academy"].map((k) => {
            const m = TIER_META[k];
            const active = k === tier;
            return (
              <div
                key={k}
                data-testid={`tier-landscape-${k}`}
                className={`px-3 py-3 ${active ? "bg-cream-card" : "bg-cream-base/5 border border-cream-base/10"}`}
              >
                <div className="flex items-center gap-1.5">
                  <span className={`w-1.5 h-1.5 rounded-full ${m.dot}`} />
                  <span className={`text-[9px] uppercase tracking-[0.18em] font-bold ${active ? "text-forest" : "text-cream-base/55"}`}>
                    {m.label}
                  </span>
                </div>
                {active && (
                  <div className="mt-1.5 text-[10px] uppercase tracking-[0.22em] font-bold text-forest-pop">You are here</div>
                )}
              </div>
            );
          })}
        </div>
        <a
          href="/methodology"
          target="_blank"
          rel="noopener noreferrer"
          data-testid="overall-methodology-link"
          className="mt-4 inline-block text-[10px] uppercase tracking-[0.22em] font-bold text-cream-base/70 hover:text-cream-base underline-offset-4 hover:underline transition-colors"
        >
          How we score · methodology →
        </a>
      </div>
    </div>
  );
}

/* Position-specific trial-readiness checklist — auto-evaluated against
   strong-club / pro-academy score thresholds. Renders as the page
   the player would actually hand a coach: yes/no items with reasons. */
function TrialReadinessCard({ tr }) {
  if (!tr || !Array.isArray(tr.items) || tr.items.length === 0) return null;

  const headlineMeta = {
    pro_academy:           { tone: "bg-forest text-cream-base",                eyebrow: "Today, this player is" },
    strong_club:           { tone: "bg-forest-pop text-cream-base",            eyebrow: "Today, this player is" },
    building_strong_club:  { tone: "bg-cream-card text-forest border-2 border-forest", eyebrow: "On track — building towards" },
    foundation:            { tone: "bg-cream-card text-ink border-2 border-stone-400", eyebrow: "Foundation phase" },
  }[tr.readiness_tier] || { tone: "bg-cream-card text-ink border", eyebrow: "Status" };

  return (
    <div data-testid="trial-readiness-card" className="bg-surface border border-gray-border p-6 md:p-8">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <div className="text-[10px] uppercase tracking-[0.28em] font-bold text-forest mb-2">Trial readiness</div>
          <h3 className="font-barlow font-black uppercase text-2xl md:text-3xl text-ink leading-tight">
            What this player is ready for, today
          </h3>
          <p className="mt-2 text-sm text-ink/65 max-w-xl">
            Position-specific checklist — each item below is auto-evaluated against the strong-club and pro-academy
            score thresholds for a {tr.position_key}.
          </p>
        </div>
        <div data-testid="trial-readiness-headline" className={`px-5 py-4 ${headlineMeta.tone}`}>
          <div className="text-[9px] uppercase tracking-[0.25em] font-bold opacity-80">{headlineMeta.eyebrow}</div>
          <div className="text-lg md:text-xl font-barlow font-black uppercase leading-tight mt-0.5">
            {tr.headline}
          </div>
          <div className="mt-2 flex items-center gap-3 text-[10px] uppercase tracking-[0.18em] font-bold opacity-90">
            <span data-testid="tr-strong-score">Strong club {tr.strong_club_score}</span>
            <span className="opacity-50">·</span>
            <span data-testid="tr-pro-score">Pro academy {tr.pro_academy_score}</span>
          </div>
        </div>
      </div>

      <div className="mt-6 grid sm:grid-cols-2 gap-px bg-cream-soft/20">
        {tr.items.map((it) => {
          const proMet  = it.pro_academy_met;
          const strongMet = it.strong_club_met;
          let mark, markCls, eyebrowLabel, eyebrowCls;
          if (it.no_data) {
            mark = "—"; markCls = "bg-stone-200 text-stone-500";
            eyebrowLabel = "no data"; eyebrowCls = "text-stone-500";
          } else if (proMet) {
            mark = "✓"; markCls = "bg-forest text-cream-base";
            eyebrowLabel = "pro academy ready"; eyebrowCls = "text-forest";
          } else if (strongMet) {
            mark = "✓"; markCls = "bg-forest-pop/15 text-forest";
            eyebrowLabel = "strong club ready"; eyebrowCls = "text-forest-pop";
          } else {
            mark = "○"; markCls = "bg-cream-soft text-ink/45";
            eyebrowLabel = "needs work"; eyebrowCls = "text-ink/45";
          }
          return (
            <div
              key={it.id}
              data-testid={`tr-item-${it.id}`}
              className="bg-surface p-4 flex items-start gap-3"
            >
              <div className={`w-8 h-8 shrink-0 flex items-center justify-center font-barlow font-black text-base ${markCls}`}>
                {mark}
              </div>
              <div className="flex-1 min-w-0">
                <div className="text-sm font-semibold text-ink leading-snug">{it.label}</div>
                <div className="mt-1 flex items-center gap-2 text-[10px] uppercase tracking-[0.18em] font-bold">
                  <span className={eyebrowCls}>{eyebrowLabel}</span>
                  {!it.no_data && (
                    <span className="text-ink/40">
                      score {it.value} <span className="opacity-50">· need {it.strong_club_min}/{it.pro_academy_min}</span>
                    </span>
                  )}
                </div>
              </div>
            </div>
          );
        })}
      </div>

      <p className="mt-5 text-xs text-ink/50 italic">
        Trial readiness is computed from the scores above. It's a scout-style guide, not a guarantee of selection.
      </p>
    </div>
  );
}

/* DNA Fingerprint — horizontal bar visualisation of ALL ~24 sub-attributes
   the AI evaluated. Each attribute is shown as a vertical bar scaled to its
   score (1-10). Attributes are ordered by position priority weight when
   available, so every player's DNA bar looks unique — a "fingerprint" you
   can recognise at a glance. */

const PILLAR_ATTRS = {
  technical: ["first_touch", "ball_control", "dribbling", "passing", "shooting", "weak_foot", "one_v_one"],
  tactical:  ["positioning", "off_ball_movement", "scanning", "decision_making", "timing_of_runs", "game_understanding"],
  physical:  ["acceleration", "speed", "balance", "agility", "intensity", "body_control"],
  mentality: ["confidence", "work_rate", "courage_in_duels", "response_to_mistakes", "competitive_mindset", "focus"],
};
const PILLAR_COLOR = {
  technical: "bg-forest",
  tactical:  "bg-forest-pop",
  physical:  "bg-amber-700",
  mentality: "bg-ink",
};
const PILLAR_LABEL = {
  technical: "Technical",
  tactical:  "Tactical",
  physical:  "Physical",
  mentality: "Mental",
};

function _attrPillar(key) {
  for (const [pillar, keys] of Object.entries(PILLAR_ATTRS)) {
    if (keys.includes(key)) return pillar;
  }
  return null;
}

function DnaFingerprint({ fullReport, ageProfile }) {
  if (!fullReport) return null;

  const bars = [];
  for (const pillar of ["technical", "tactical", "physical", "mentality"]) {
    const sec = fullReport[pillar] || {};
    for (const [key, value] of Object.entries(sec)) {
      if (value && typeof value === "object" && typeof value.score === "number") {
        bars.push({ key, pillar, score: value.score, label: key.replace(/_/g, " ") });
      }
    }
  }
  if (bars.length === 0) return null;

  const priorityWeights = {};
  if (ageProfile && Array.isArray(ageProfile.items)) {
    for (const it of ageProfile.items) {
      priorityWeights[it.key] = it.weight || 3;
    }
  }
  bars.sort((a, b) => {
    const wa = priorityWeights[a.key] ?? 0;
    const wb = priorityWeights[b.key] ?? 0;
    if (wb !== wa) return wb - wa;
    return b.score - a.score;
  });

  return (
    <div data-testid="dna-fingerprint" className="bg-surface border border-gray-border p-6 md:p-8">
      <div className="flex items-start justify-between gap-4 flex-wrap mb-6">
        <div>
          <div className="text-[10px] uppercase tracking-[0.28em] font-bold text-forest mb-2">Player DNA</div>
          <h3 className="font-barlow font-black uppercase text-2xl md:text-3xl text-ink leading-tight">
            Attribute fingerprint
          </h3>
          <p className="mt-2 text-sm text-ink/65 max-w-xl">
            Every scored attribute, ranked by what matters most for the position.
            Hover any row to see the exact score — every player's fingerprint is unique.
          </p>
        </div>
        <div className="flex items-center gap-3 flex-wrap">
          {Object.entries(PILLAR_LABEL).map(([p, label]) => (
            <div key={p} className="flex items-center gap-1.5">
              <span className={`w-2.5 h-2.5 ${PILLAR_COLOR[p]}`} />
              <span className="text-[9px] uppercase tracking-[0.18em] font-bold text-ink/65">{label}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Horizontal-row layout — fully readable labels + visible scores */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-x-8 gap-y-1.5">
        {bars.map((b) => {
          const pct = (b.score / 10) * 100;
          const tone =
            b.score >= 8 ? "text-forest" :
            b.score >= 7 ? "text-forest-pop" :
            b.score >= 5.5 ? "text-amber-700" : "text-ink/50";
          return (
            <div
              key={b.key}
              data-testid={`dna-seg-${b.key}`}
              className="group flex items-center gap-3 py-1.5"
            >
              {/* Pillar pip */}
              <span className={`w-1.5 h-6 ${PILLAR_COLOR[b.pillar]} shrink-0`} />
              {/* Label */}
              <span className="text-[11px] uppercase tracking-[0.12em] font-bold text-ink/85 w-[140px] md:w-[150px] shrink-0 capitalize">
                {b.label}
              </span>
              {/* Bar */}
              <div className="flex-1 h-3 bg-cream-soft/40 relative">
                <div
                  className={`absolute inset-y-0 left-0 ${PILLAR_COLOR[b.pillar]} group-hover:opacity-90 transition-opacity`}
                  style={{ width: `${pct}%` }}
                />
              </div>
              {/* Score */}
              <span className={`font-barlow font-black text-base ${tone} w-9 text-right shrink-0`}>
                {b.score}
              </span>
            </div>
          );
        })}
      </div>

      <p className="mt-6 text-xs text-ink/50 italic">
        Ordered by position priority — the attributes that matter most for this player's role appear first.
      </p>
    </div>
  );
}



/* Stylistic archetype card — small, premium, sits inline with the report.
   The named pros are public stylistic references only. We never publish
   their childhood scores. */
/* Build a 2-3 letter monogram badge from a player/archetype name.
   Strips the "-type" suffix and any non-letter words. */
function _archetypeMonogram(name) {
  if (!name) return "—";
  // Strip everything after "-type" and any common suffix words
  const clean = String(name)
    .replace(/-type.*$/i, "")
    .replace(/[^a-zA-ZÀ-ÿ\s]/g, "")
    .trim();
  const words = clean.split(/\s+/).filter(Boolean);
  if (words.length === 0) return "—";
  if (words.length === 1) return words[0].slice(0, 2).toUpperCase();
  return (words[0][0] + words[words.length - 1][0]).toUpperCase();
}

const TIER_PILL_META = {
  elite:       { label: "Generational",    cls: "bg-cream-base text-forest" },
  world_class: { label: "World-class",     cls: "bg-cream-base/85 text-forest" },
  established: { label: "Established pro", cls: "bg-cream-base/70 text-forest" },
};

function ArchetypeCard({ archetype }) {
  if (!archetype) return null;
  const developing = archetype.developing;
  if (developing) {
    return (
      <div data-testid="archetype-card" className="p-6 md:p-7 bg-cream-card border border-gray-border">
        <div className="text-[10px] uppercase tracking-[0.28em] font-bold mb-2 text-forest">
          Stylistic archetype
        </div>
        <h3 className="font-barlow font-black uppercase text-2xl md:text-3xl text-ink leading-tight">
          <span data-testid="archetype-name">{archetype.name}</span>
        </h3>
        <p className="mt-3 text-sm md:text-base text-ink/75 max-w-2xl leading-relaxed">{archetype.summary}</p>
        <p className="mt-5 text-xs text-ink/50 italic">
          Stylistic comparisons describe how this player plays today — not their ceiling, and not the named professional's youth data.
        </p>
      </div>
    );
  }
  const tierMeta = TIER_PILL_META[archetype.tier] || null;
  // Strip the "-type ..." suffix from the archetype name to get the pro's name
  const proName = (archetype.name || "").replace(/-type.*$/i, "").trim();
  const bracket = archetype.age_bracket_used;
  const bioChunk = archetype.academy_bio_chunk;
  const narrative = archetype.narrative;
  return (
    <div
      data-testid="archetype-card"
      className="relative overflow-hidden bg-forest text-cream-base"
    >
      {/* Decorative diagonal accent */}
      <div className="absolute -top-24 -right-24 w-72 h-72 bg-forest-pop/30 blur-3xl rounded-full pointer-events-none" />

      <div className="relative p-6 md:p-8 flex flex-col lg:flex-row gap-8">
        {/* Left: Crest monogram + identity */}
        <div className="lg:w-1/3 shrink-0 flex flex-col gap-4">
          {/* Crest */}
          <div className="flex items-center gap-4">
            <div
              data-testid="archetype-crest"
              className="w-20 h-20 shrink-0 bg-cream-base text-forest flex items-center justify-center font-barlow font-black text-2xl border-4 border-cream-base shadow-xl"
              style={{ clipPath: "polygon(50% 0, 100% 25%, 100% 75%, 50% 100%, 0 75%, 0 25%)" }}
            >
              {_archetypeMonogram(archetype.name)}
            </div>
            <div className="min-w-0">
              <div className="text-[9px] uppercase tracking-[0.28em] font-bold text-cream-base/70">Plays in the mould of</div>
              <div className="font-barlow font-black uppercase text-lg md:text-xl text-white leading-tight">
                {archetype.club || "—"}
              </div>
              {archetype.league && (
                <div className="text-[10px] uppercase tracking-[0.2em] font-bold text-cream-base/65 mt-0.5">
                  {archetype.league}
                </div>
              )}
            </div>
          </div>

          {/* Tier pill + match strength */}
          <div className="flex items-center gap-2 flex-wrap">
            {tierMeta && (
              <span
                data-testid="archetype-tier-pill"
                className={`text-[10px] uppercase tracking-[0.2em] font-bold px-3 py-1.5 ${tierMeta.cls}`}
              >
                {tierMeta.label}
              </span>
            )}
            {typeof archetype.match_strength === "number" && (
              <span className="inline-flex items-center gap-1.5 text-[10px] uppercase tracking-[0.2em] font-bold px-3 py-1.5 bg-cream-base/15 text-cream-base">
                <span className="text-cream-base/70">match</span>
                <span className="text-white font-barlow font-black text-sm">{archetype.match_strength.toFixed(1)}</span>
                <span className="text-cream-base/70">/10</span>
              </span>
            )}
          </div>
        </div>

        {/* Right: Headline + summary + traits */}
        <div className="flex-1 min-w-0">
          <div className="text-[10px] uppercase tracking-[0.28em] font-bold text-cream-base/70 mb-2">
            Stylistic archetype
          </div>
          <h3
            data-testid="archetype-name"
            className="font-barlow font-black uppercase text-3xl md:text-4xl leading-[0.95] text-white"
          >
            {archetype.name}
          </h3>
          <p className="mt-4 text-sm md:text-base leading-relaxed text-cream-base/90 max-w-2xl">
            {archetype.summary}
          </p>
          {Array.isArray(archetype.traits) && archetype.traits.length > 0 && (
            <ul className="mt-5 flex flex-wrap gap-2">
              {archetype.traits.map((t, i) => (
                <li
                  key={i}
                  data-testid={`archetype-trait-${i}`}
                  className="text-[10px] uppercase tracking-[0.18em] font-bold px-3 py-1.5 bg-cream-base/15 text-cream-base"
                >
                  {t}
                </li>
              ))}
            </ul>
          )}

          {/* Evidence — which player attrs drove this match */}
          {Array.isArray(archetype.evidence) && archetype.evidence.length > 0 && (
            <div data-testid="archetype-evidence" className="mt-6 pt-5 border-t border-cream-base/15">
              <div className="text-[10px] uppercase tracking-[0.28em] font-bold text-cream-base/65 mb-3">
                Why this match
              </div>
              <div className="flex flex-wrap gap-2">
                {archetype.evidence.map((e, i) => (
                  <div
                    key={i}
                    data-testid={`archetype-evidence-${e.key}`}
                    className="inline-flex items-center gap-2 px-3 py-2 bg-cream-base/10 border-l-2 border-cream-base"
                  >
                    <span className="font-barlow font-black text-2xl text-white leading-none">{e.score}</span>
                    <div className="flex flex-col">
                      <span className="text-[10px] uppercase tracking-[0.18em] font-bold text-white leading-tight">
                        {e.label}
                      </span>
                      <span className="text-[8px] uppercase tracking-[0.18em] font-bold text-cream-base/55">
                        signature trait
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Personalized Gemini narrative (Layer 3) — age-anchored comparison */}
      {narrative && (
        <div
          data-testid="archetype-narrative"
          className="relative mx-6 md:mx-8 mb-5 p-5 bg-cream-base text-ink border-l-4 border-cream-base/0"
          style={{ borderLeftColor: "#FFFFFF" }}
        >
          <div className="text-[10px] uppercase tracking-[0.28em] font-bold text-forest mb-2">
            Personalized comparison · age-anchored
          </div>
          <p className="text-sm md:text-base leading-relaxed text-ink/85">
            {narrative}
          </p>
        </div>
      )}

      {/* Age-bracketed bio chunk (Layer 1 — verbatim from catalog, no AI invention) */}
      {bioChunk && bracket && proName && (
        <div
          data-testid="archetype-academy-bio"
          className="relative mx-6 md:mx-8 mb-5 p-5 bg-cream-base/10 border border-cream-base/20"
        >
          <div className="text-[10px] uppercase tracking-[0.28em] font-bold text-cream-base/85 mb-2">
            What {proName} was doing at age {bracket}
          </div>
          <p className="text-sm leading-relaxed text-cream-base/95 italic">
            "{bioChunk}"
          </p>
          <p className="mt-3 text-[10px] uppercase tracking-[0.18em] font-bold text-cream-base/55">
            Source · public biographical record (Wikipedia / Transfermarkt / club academy pages)
          </p>
        </div>
      )}

      {/* Footer disclaimer */}
      <div className="relative px-6 md:px-8 pb-5 -mt-2">
        <p className="text-xs italic text-cream-base/55 max-w-3xl">
          Stylistic comparisons describe how this player plays <strong>today</strong> — not their ceiling, and not the named professional's youth data.
        </p>
      </div>
    </div>
  );
}

/* 4-Lens Twins Strip — replaces the legacy ClosestMatchesStrip with a richer
   layout that shows ONE matched pro per lens (Style / Build / Role / Career-path).
   Each lens picks the closest archetype on a different dimension. */
function LensMatchesStrip({ archetype }) {
  if (!archetype || !archetype.lenses) return null;
  const order = ["style", "build", "role", "path"];
  const lenses = order
    .map((k) => archetype.lenses[k])
    .filter((l) => l && l.name);
  if (lenses.length === 0) return null;

  return (
    <div data-testid="lens-matches-strip" className="bg-surface border border-gray-border p-6 md:p-7">
      <div className="flex items-end justify-between gap-4 flex-wrap mb-5">
        <div>
          <div className="text-[10px] uppercase tracking-[0.28em] font-bold text-forest mb-2">The 4-lens comparison</div>
          <h3 className="font-barlow font-black uppercase text-xl md:text-2xl text-ink leading-tight">
            How this player resembles four different pros
          </h3>
          <p className="mt-1.5 text-xs text-ink/60 max-w-xl">
            Each lens picks the closest pro on a different dimension: how he plays, his physical build, his on-pitch role, and the career path he's on.
          </p>
        </div>
        <div className="text-[9px] uppercase tracking-[0.22em] font-bold text-ink/45">
          Style · Build · Role · Career-path
        </div>
      </div>

      <div className="grid sm:grid-cols-2 gap-3">
        {lenses.map((lens) => {
          const meta = TIER_PILL_META[lens.tier] || null;
          const scoreWidth = Math.min(100, Math.max(20, (lens.score || 0) * 8));
          return (
            <div
              key={lens.lens}
              data-testid={`lens-match-${lens.lens}`}
              className="relative p-4 md:p-5 bg-cream-card border-l-4 border-forest"
            >
              <div className="flex items-center gap-3 mb-3">
                <div
                  className="w-12 h-12 shrink-0 bg-forest text-cream-base flex items-center justify-center font-barlow font-black text-base shadow"
                  style={{ clipPath: "polygon(50% 0, 100% 25%, 100% 75%, 50% 100%, 0 75%, 0 25%)" }}
                >
                  {_archetypeMonogram(lens.name)}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="text-[9px] uppercase tracking-[0.22em] font-bold text-forest">
                    {lens.lens_label}
                  </div>
                  <div className="font-barlow font-black uppercase text-base md:text-lg text-ink truncate leading-tight">
                    {lens.name}
                  </div>
                  <div className="text-[10px] uppercase tracking-[0.18em] font-bold text-ink/55 truncate">
                    {lens.club || "—"}
                    {lens.league && <span className="opacity-60"> · {lens.league}</span>}
                  </div>
                </div>
                {meta && (
                  <div className="hidden sm:inline-flex text-[8px] uppercase tracking-[0.2em] font-bold px-2 py-1 bg-cream-soft text-forest shrink-0">
                    {meta.label}
                  </div>
                )}
              </div>
              <p className="text-xs md:text-sm text-ink/70 leading-snug mb-3">
                {lens.why}
              </p>
              <div className="flex items-center gap-3">
                <div className="flex-1 h-1.5 bg-cream-soft overflow-hidden">
                  <div className="h-full bg-forest" style={{ width: `${scoreWidth}%` }} />
                </div>
                <div className="font-barlow font-black tabular-nums text-xl text-forest leading-none">
                  {(lens.score ?? 0).toFixed(1)}
                </div>
                <div className="text-[10px] font-bold text-ink/45">/10</div>
              </div>
            </div>
          );
        })}
      </div>

      <p className="mt-5 text-xs text-ink/50 italic">
        Match score reflects similarity on that lens only — not overall player quality. A high Build twin score means the same physical frame, not the same career ceiling.
      </p>
    </div>
  );
}

/* Legacy alias kept for backward compatibility — the four lenses replace the
   old "top 3 closest matches" strip. ClosestMatchesStrip now simply renders
   the new LensMatchesStrip. */
function ClosestMatchesStrip({ archetype }) {
  return <LensMatchesStrip archetype={archetype} />;
}

/* Position-specific reference profile card — shows the player's actual
   scores against Pro Academy expectations for the position + age bracket.
   Pure server-side enrichment, no AI involved. */
function AgeProfileCard({ ref: profile }) {
  if (!profile || !Array.isArray(profile.items) || profile.items.length === 0) return null;
  const positionLabel = (profile.position_key || "").toUpperCase();
  const ageLabel = (profile.age_bracket || "").toUpperCase();
  return (
    <div data-testid="age-profile-card" className="bg-surface border border-gray-border p-6 md:p-8">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <div className="text-[10px] uppercase tracking-[0.28em] font-bold text-forest mb-2">European academy reference profile</div>
          <h3 className="font-barlow font-black uppercase text-2xl md:text-3xl text-ink leading-tight">
            How the player overlays
          </h3>
          <p className="mt-2 text-sm text-ink/65 max-w-xl">
            The attributes that matter most for a {profile.position_key} — measured against the Pro Academy expectation
            for {profile.age_bracket || "the player's age bracket"}.
          </p>
        </div>
        <div className="px-4 py-3 bg-cream-card border-l-4 border-forest">
          <div className="text-[9px] uppercase tracking-[0.22em] font-bold text-forest">Position · Age</div>
          <div className="mt-0.5 font-barlow font-black text-base text-ink leading-tight">
            <span data-testid="age-profile-position">{positionLabel}</span>
            {ageLabel && <span className="text-ink/40"> · </span>}
            <span data-testid="age-profile-age">{ageLabel}</span>
          </div>
          <div
            className="mt-2 text-[10px] uppercase tracking-[0.18em] font-bold text-ink/70"
            data-testid="age-profile-summary"
            dangerouslySetInnerHTML={{ __html: profile.summary || "" }}
          />
        </div>
      </div>

      {/* Priority attributes table */}
      <div className="mt-6 space-y-px bg-gray-border">
        {profile.items.map((it) => {
          const delta = it.delta;
          let stateLabel, stateCls, deltaIcon;
          if (delta === "at_or_above") {
            stateLabel = "At or above"; stateCls = "text-forest"; deltaIcon = "▲";
          } else if (delta === "below") {
            stateLabel = "Below";        stateCls = "text-amber-700"; deltaIcon = "▼";
          } else {
            stateLabel = "—";             stateCls = "text-ink/45"; deltaIcon = "·";
          }
          // Weight visual — solid dots
          const dots = [];
          for (let i = 0; i < 5; i++) {
            dots.push(
              <span
                key={i}
                className={`w-1.5 h-1.5 rounded-full ${i < (it.weight || 3) ? "bg-forest" : "bg-cream-soft"}`}
              />
            );
          }
          return (
            <div
              key={it.key}
              data-testid={`age-profile-row-${it.key}`}
              className="bg-surface p-4 grid grid-cols-12 gap-3 items-center"
            >
              <div className="col-span-12 md:col-span-4">
                <div className="text-sm font-semibold text-ink leading-tight">{it.label}</div>
                <div className="mt-0.5 text-xs text-ink/55 leading-snug">{it.why_matters}</div>
              </div>
              <div className="col-span-3 md:col-span-2 flex items-center gap-1">
                {dots}
              </div>
              <div className="col-span-3 md:col-span-2 text-center">
                <div className="text-[9px] uppercase tracking-[0.18em] font-bold text-ink/50">Pro range</div>
                <div className="font-barlow font-black text-sm text-ink">{it.pro_academy_range}</div>
              </div>
              <div className="col-span-3 md:col-span-2 text-center">
                <div className="text-[9px] uppercase tracking-[0.18em] font-bold text-ink/50">Player</div>
                <div className="font-barlow font-black text-2xl text-forest leading-none">
                  {it.player_score ?? "—"}
                </div>
              </div>
              <div className="col-span-3 md:col-span-2 text-right">
                <div className={`inline-flex items-center gap-1.5 text-[10px] uppercase tracking-[0.18em] font-bold ${stateCls}`}>
                  <span>{deltaIcon}</span>
                  <span>{stateLabel}</span>
                </div>
              </div>
            </div>
          );
        })}
      </div>

      <p className="mt-5 text-xs text-ink/50 italic">
        Reference profile is curated from European youth-academy development frameworks. It compares the player's actual
        scores against what scouts at Pro Academy level typically look for.
      </p>
    </div>
  );
}


function LockedOverlay({ price, onUnlock, loading }) {
  return (
    <div className="absolute inset-0 z-20 backdrop-blur-xl bg-cream-card border border-gray-border flex flex-col items-center justify-center text-center p-6 md:p-12">
      <Lock className="w-10 h-10 text-volt mb-5" strokeWidth={1.5} />
      <span className="text-volt text-xs uppercase tracking-[0.3em] font-bold">Premium</span>
      <h3 className="mt-3 font-barlow font-black uppercase text-3xl md:text-5xl text-ink tracking-tighter">
        Unlock full premium report
      </h3>
      <p className="mt-4 text-ink/70 text-sm md:text-base max-w-xl">
        Full scout analysis across technical, tactical, physical & mental dimensions. Scout view, training plan & a premium PDF.
      </p>
      <div className="mt-6 flex items-baseline gap-2">
        <span className="font-barlow font-black text-6xl md:text-7xl text-volt">${price}</span>
        <span className="text-ink/65 uppercase tracking-widest font-bold">USD</span>
      </div>
      <p className="text-xs text-ink/50 uppercase tracking-widest font-bold">One-time payment · No subscription</p>
      <button
        onClick={onUnlock}
        disabled={loading}
        data-testid="unlock-report-btn"
        className="mt-8 bg-volt hover:bg-forest-pop text-white font-barlow font-black uppercase tracking-widest text-base px-10 py-4 transition-colors disabled:opacity-50 flex items-center gap-3"
      >
        {loading ? (
          <>
            <Loader2 className="w-5 h-5 animate-spin" />
            Redirecting to Stripe...
          </>
        ) : (
          <>
            <Unlock className="w-5 h-5" />
            Unlock full premium report
          </>
        )}
      </button>
      <p className="mt-4 text-xs text-ink/50 flex items-center gap-2">
        <ShieldCheck className="w-3.5 h-3.5" /> Secure payment via Stripe
      </p>
    </div>
  );
}

export default function ReportPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const { user } = useAuth();
  const [report, setReport] = useState(null);
  const [price, setPrice] = useState(1);
  const [loading, setLoading] = useState(true);
  const [unlocking, setUnlocking] = useState(false);
  const [checkoutModal, setCheckoutModal] = useState({ open: false, state: "preparing", errorMessage: null });
  const [embeddedOpen, setEmbeddedOpen] = useState(false);
  const [generatingFull, setGeneratingFull] = useState(false);
  const [downloadingPdf, setDownloadingPdf] = useState(false);
  const pollingRef = useRef(null);

  const fetchReport = useCallback(async () => {
    try {
      const [r, p] = await Promise.all([
        api.get(`/reports/${id}`),
        api.get("/settings/price"),
      ]);
      setReport(r.data);
      setPrice(p.data.price);
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Failed to load report");
      navigate("/dashboard");
    } finally {
      setLoading(false);
    }
  }, [id, navigate]);

  useEffect(() => { fetchReport(); }, [fetchReport]);

  // Handle Stripe redirect with session_id polling
  useEffect(() => {
    const sessionId = searchParams.get("session_id");
    const canceled = searchParams.get("canceled");
    if (canceled) {
      toast.info("Payment canceled");
      const np = new URLSearchParams(searchParams);
      np.delete("canceled");
      setSearchParams(np, { replace: true });
      return;
    }
    if (!sessionId) return;

    // Show "preparing" modal while we poll for confirmation
    setCheckoutModal({ open: true, state: "preparing", errorMessage: null });

    let attempts = 0;
    const maxAttempts = 10;
    const poll = async () => {
      try {
        const { data } = await api.get(`/payments/status/${sessionId}`);
        if (data.payment_status === "paid") {
          setCheckoutModal({ open: true, state: "success", errorMessage: null });
          const np = new URLSearchParams(searchParams);
          np.delete("session_id");
          setSearchParams(np, { replace: true });
          await fetchReport();
          // trigger full report generation
          setGeneratingFull(true);
          try {
            await api.post(`/reports/${id}/generate-full`);
            await fetchReport();
            toast.success("Full premium report ready");
          } catch (e) {
            toast.error(e?.response?.data?.detail || "Failed to generate full report");
          } finally {
            setGeneratingFull(false);
          }
          return;
        }
        if (data.status === "expired") {
          setCheckoutModal({ open: true, state: "error", errorMessage: "Payment session expired" });
          return;
        }
        if (attempts++ < maxAttempts) {
          pollingRef.current = setTimeout(poll, 2000);
        } else {
          setCheckoutModal({ open: false, state: "preparing", errorMessage: null });
          toast.info("Still processing. Please refresh shortly.");
        }
      } catch (err) {
        setCheckoutModal({ open: true, state: "error", errorMessage: "Error checking payment status" });
      }
    };
    poll();
    return () => clearTimeout(pollingRef.current);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams.get("session_id"), searchParams.get("canceled")]);

  const handleUnlock = async () => {
    setUnlocking(true);
    // Prefer embedded checkout when configured
    try {
      const { data: cfg } = await api.get("/config/stripe");
      if (cfg.embedded_available) {
        setUnlocking(false);
        setEmbeddedOpen(true);
        return;
      }
    } catch (_) {
      // ignore — fall through to redirect mode
    }

    setCheckoutModal({ open: true, state: "preparing", errorMessage: null });
    try {
      const { data } = await api.post("/payments/checkout", {
        report_id: id,
        origin_url: window.location.origin,
      });
      setCheckoutModal((m) => ({ ...m, state: "redirecting" }));
      setTimeout(() => {
        window.location.href = data.url;
      }, 700);
    } catch (err) {
      setCheckoutModal({
        open: true,
        state: "error",
        errorMessage: err?.response?.data?.detail || "Failed to start checkout",
      });
      setUnlocking(false);
    }
  };

  // Embedded checkout: backend session creator
  const embeddedUnlockInit = async () => {
    const { data } = await api.post("/payments/embedded/unlock", {
      report_id: id,
      origin_url: window.location.origin,
    });
    return data;
  };

  const handleEmbeddedSuccess = async () => {
    await fetchReport();
    // Trigger full report generation
    setGeneratingFull(true);
    try {
      await api.post(`/reports/${id}/generate-full`);
      await fetchReport();
      toast.success("Full premium report unlocked");
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Couldn't auto-generate full report. Click 'Regenerate' below.");
    } finally {
      setGeneratingFull(false);
    }
  };

  const handleGenerateFull = async () => {
    setGeneratingFull(true);
    try {
      await api.post(`/reports/${id}/generate-full`);
      await fetchReport();
      toast.success("Full report ready");
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Failed to generate full report");
    } finally {
      setGeneratingFull(false);
    }
  };

  const handleDownloadPdf = async () => {
    setDownloadingPdf(true);
    try {
      const res = await api.get(`/reports/${id}/pdf`, { responseType: "blob" });
      const blob = new Blob([res.data], { type: "application/pdf" });
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `EliteScout_${report?.player_details?.player_name || "report"}.pdf`;
      link.click();
      window.URL.revokeObjectURL(url);
    } catch (err) {
      toast.error(err?.response?.data?.detail || "PDF download failed");
    } finally {
      setDownloadingPdf(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-deepnavy text-ink">
        <Navigation />
        <div className="pt-40 text-center">
          <Loader2 className="w-8 h-8 animate-spin text-volt mx-auto" />
          <p className="mt-4 text-ink/65 uppercase tracking-widest text-sm font-bold">Loading report...</p>
        </div>
      </div>
    );
  }
  if (!report) return null;

  const { preview, full_report, player_details, video_url, poster_url, marker_url, is_paid, manually_unlocked, content_gate, trial_readiness, archetype, age_profile_reference } = report;
  const unlocked = is_paid || manually_unlocked || user?.role === "admin";

  const radarData = full_report ? [
    { axis: "Technical", score: full_report.scores?.technical },
    { axis: "Tactical", score: full_report.scores?.tactical },
    { axis: "Physical", score: full_report.scores?.physical },
    { axis: "Mentality", score: full_report.scores?.mentality },
  ] : null;

  // Pretty content-type label for the awareness banner
  const contentTypeLabel = (() => {
    const t = content_gate?.content_type;
    if (!t) return null;
    const map = {
      full_match: "Full Match",
      small_sided: "Small-Sided Game",
      training: "Training Session",
      drill: "Technical Drills",
      fitness: "Fitness Work",
      freestyle: "Freestyle / Ball Mastery",
      mixed: "Mixed Content",
      other: "General Football",
    };
    return map[t] || t;
  })();
  const scoresConfidence = full_report?.scores_confidence;
  const evidenceQualityNote = full_report?.evidence_quality_note;
  const couldNotAssess = full_report?.scout_view?.what_we_could_not_assess;

  return (
    <div className="min-h-screen bg-deepnavy text-ink pb-20">
      <Navigation />
      <CheckoutTransitionModal
        open={checkoutModal.open}
        state={checkoutModal.state}
        errorMessage={checkoutModal.errorMessage}
        amount={price}
        currency="USD"
        product="ScoutMePlay – Football Video Analysis"
        onClose={() => setCheckoutModal({ open: false, state: "preparing", errorMessage: null })}
      />
      <EmbeddedCheckoutModal
        open={embeddedOpen}
        sessionInit={embeddedUnlockInit}
        amount={price}
        currency="USD"
        product="ScoutMePlay – Premium Report Unlock"
        onSuccess={handleEmbeddedSuccess}
        onClose={() => setEmbeddedOpen(false)}
      />

      <div className="pt-28 px-6">
        <div className="max-w-7xl mx-auto">
          <button
            onClick={() => navigate("/dashboard")}
            data-testid="back-to-dashboard"
            className="flex items-center gap-2 text-ink/65 hover:text-volt uppercase tracking-widest text-xs font-bold transition-colors"
          >
            <ChevronLeft className="w-4 h-4" />
            Dashboard
          </button>

          {/* ===== Header ===== */}
          <div className="mt-6 grid lg:grid-cols-5 gap-px bg-cream-soft/40 border border-gray-border">
            <div className="bg-surface p-6 md:p-8 lg:col-span-2">
              {report.demo ? (
                <div className="relative w-full bg-deepnavy border border-volt/20 aspect-video flex flex-col items-center justify-center text-center p-6">
                  <div className="absolute top-3 right-3 bg-volt text-white text-[10px] uppercase tracking-widest font-black px-2 py-1">Demo</div>
                  <div
                    className="absolute inset-0 opacity-30"
                    style={{
                      backgroundImage: "url('https://images.pexels.com/photos/12616082/pexels-photo-12616082.jpeg')",
                      backgroundSize: "cover",
                      backgroundPosition: "center",
                    }}
                  />
                  <div className="absolute inset-0 bg-gradient-to-t from-deepnavy via-deepnavy/70 to-transparent" />
                  <div className="relative">
                    <div className="font-barlow font-black uppercase text-3xl text-volt">Sample report</div>
                    <p className="mt-2 text-sm text-ink/70 max-w-sm">
                      This is a demo report so you can explore the premium experience. Upload your own video to get a real analysis.
                    </p>
                  </div>
                </div>
              ) : (
                <video
                  src={`${ASSET_BASE}${video_url}`}
                  poster={poster_url ? `${ASSET_BASE}${poster_url}` : undefined}
                  controls
                  playsInline
                  preload="metadata"
                  data-testid="report-video"
                  className="w-full bg-black aspect-video"
                />
              )}
              <div className="mt-4 grid grid-cols-3 gap-px bg-cream-soft/20">
                <div className="bg-surface p-3">
                  <div className="text-[10px] uppercase tracking-[0.18em] text-ink/50 font-bold">Type</div>
                  <div className="text-sm text-ink font-bold mt-1 capitalize">{player_details.video_type}</div>
                </div>
                <div className="bg-surface p-3">
                  <div className="text-[10px] uppercase tracking-[0.18em] text-ink/50 font-bold">Foot</div>
                  <div className="text-sm text-ink font-bold mt-1 capitalize">{player_details.preferred_foot}</div>
                </div>
                <div className="bg-surface p-3">
                  <div className="text-[10px] uppercase tracking-[0.18em] text-ink/50 font-bold">Age</div>
                  <div className="text-sm text-ink font-bold mt-1">{player_details.age}</div>
                </div>
              </div>
            </div>

            <div className="bg-surface p-6 md:p-8 lg:col-span-3 flex flex-col justify-between">
              <div>
                <span className="text-volt text-xs uppercase tracking-[0.25em] font-bold">{unlocked ? "Premium report" : "Free preview"}</span>
                <h1
                  data-testid="report-player-name"
                  className="mt-3 font-barlow font-black uppercase text-4xl md:text-6xl tracking-tighter leading-[0.95]"
                >
                  {player_details.player_name}
                </h1>
                <p className="mt-3 text-ink/65 text-sm md:text-base">
                  {player_details.position} · {player_details.current_club || "Independent"}
                </p>
                <div className="mt-6 inline-flex items-center gap-2 bg-deepnavy border border-volt/30 px-4 py-2">
                  <Star className="w-4 h-4 text-volt" />
                  <span className="font-barlow font-bold uppercase text-sm" data-testid="report-player-type">
                    {(full_report?.player_type) || preview?.player_type || "Player Analysis"}
                  </span>
                </div>

                {marker_url && (
                  <div className="mt-5 border border-gray-border bg-cream-card/90 p-3 max-w-md" data-testid="marker-card">
                    <div className="flex items-center gap-2 mb-2">
                      <Star className="w-3 h-3 text-volt" fill="currentColor" />
                      <span className="text-[10px] uppercase tracking-[0.22em] font-bold text-volt">Verified player</span>
                    </div>
                    <img
                      src={`${ASSET_BASE}${marker_url}`}
                      alt="Marked player"
                      className="w-full aspect-video object-cover border border-gray-border"
                    />
                    <p className="mt-2 text-[11px] text-ink/60">
                      We analysed only the player you circled above.
                    </p>
                  </div>
                )}
              </div>

              {unlocked && full_report && (
                <div className="mt-8 grid grid-cols-5 gap-px bg-cream-soft/40 border border-gray-border">
                  {[
                    { key: "technical", label: "Technical", v: full_report.scores?.technical },
                    { key: "tactical", label: "Tactical", v: full_report.scores?.tactical },
                    { key: "physical", label: "Physical", v: full_report.scores?.physical },
                    { key: "mentality", label: "Mentality", v: full_report.scores?.mentality },
                    { key: "overall_development", label: "Overall", v: full_report.scores?.overall_development },
                  ].map((s, i) => {
                    const conf = scoresConfidence?.[s.key];
                    const c = conf ? CONFIDENCE_STYLES[conf] : null;
                    return (
                      <div key={i} className="bg-surface p-3 text-center">
                        <div className="text-[10px] uppercase tracking-[0.18em] text-ink/50 font-bold">{s.label}</div>
                        <div className={`font-barlow font-black text-3xl mt-1 ${scoreColor(s.v)}`}>{s.v ?? "-"}</div>
                        {c && (
                          <div className={`mt-1.5 text-[8px] uppercase tracking-widest font-bold ${c.color}`} title={`Confidence: ${conf}`}>
                            {conf}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}

              {unlocked && full_report && (
                <div className="mt-6 flex flex-wrap gap-3 items-center">
                  <button
                    onClick={handleDownloadPdf}
                    disabled={downloadingPdf}
                    data-testid="download-pdf-btn"
                    className="bg-volt hover:bg-forest-pop text-white font-barlow font-black uppercase tracking-widest text-sm px-6 py-3 transition-colors disabled:opacity-50 flex items-center gap-2"
                  >
                    {downloadingPdf ? <Loader2 className="w-4 h-4 animate-spin" /> : <Download className="w-4 h-4" />}
                    Download premium PDF
                  </button>
                  {report.share_card_url && (
                    <a
                      href={`${ASSET_BASE}${report.share_card_url}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      download={`scoutmeplay-${(player_details?.player_name || "player").replace(/\s+/g, "-").toLowerCase()}.png`}
                      data-testid="download-share-card-btn"
                      className="bg-cream-card hover:bg-cream-soft text-forest border-2 border-forest font-barlow font-black uppercase tracking-widest text-sm px-6 py-3 transition-colors flex items-center gap-2"
                    >
                      <Share2 className="w-4 h-4" />
                      Get share card
                    </a>
                  )}
                </div>
              )}
            </div>
          </div>

          {/* ===== Content-awareness banner ===== */}
          {content_gate && contentTypeLabel && (
            <div
              data-testid="content-awareness-banner"
              className="mt-6 flex flex-col sm:flex-row sm:items-center gap-3 sm:gap-5 border border-volt/20 bg-volt/5 px-5 py-4"
            >
              <div className="flex items-center gap-3 shrink-0">
                <Eye className="w-5 h-5 text-volt" strokeWidth={1.7} />
                <div className="flex flex-col leading-tight">
                  <span className="text-[10px] uppercase tracking-[0.22em] font-bold text-volt">Detected content</span>
                  <span className="font-barlow font-black uppercase text-ink text-lg">{contentTypeLabel}</span>
                </div>
              </div>
              <div className="flex flex-wrap items-center gap-2 sm:ml-auto">
                {content_gate.quality && (
                  <span className="text-[10px] uppercase tracking-widest font-bold text-ink/75 border border-gray-border px-2 py-1">
                    Quality · {content_gate.quality}
                  </span>
                )}
                {content_gate.player_visible && (
                  <span className="text-[10px] uppercase tracking-widest font-bold text-ink/75 border border-gray-border px-2 py-1">
                    Player · {String(content_gate.player_visible).replace(/_/g, " ")}
                  </span>
                )}
                {typeof content_gate.games_detected === "number" && content_gate.games_detected > 1 && (
                  <span className="text-[10px] uppercase tracking-widest font-bold text-yellow-300 border border-yellow-300/30 bg-yellow-300/5 px-2 py-1">
                    {content_gate.games_detected} games
                  </span>
                )}
                {content_gate.camera_distance && (
                  <span className="text-[10px] uppercase tracking-widest font-bold text-ink/60 border border-gray-border px-2 py-1">
                    Camera · {content_gate.camera_distance}
                  </span>
                )}
              </div>
            </div>
          )}

          {/* ===== Free Preview ===== TWO sections only: Summary + Top Strengths + locked teaser */}
          <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} className="mt-10">
            <div className="grid lg:grid-cols-3 gap-px bg-cream-soft/40 border border-gray-border">
              {/* SECTION 1 — Summary + Top strengths */}
              <div className="bg-surface p-6 md:p-8 lg:col-span-2">
                <span className="text-volt text-xs uppercase tracking-[0.25em] font-bold">Brief Summary</span>
                <p
                  data-testid="report-preview-summary"
                  className="mt-3 text-ink/85 text-base md:text-lg leading-relaxed"
                >
                  {preview?.brief_summary}
                </p>

                <div className="mt-8">
                  <div className="text-xs uppercase tracking-[0.2em] font-bold text-ink/50 mb-3">Top strengths</div>
                  <ul className="space-y-2">
                    {(preview?.top_strengths || []).slice(0, 3).map((s, i) => (
                      <li key={i} data-testid={`preview-strength-${i}`} className="flex items-start gap-2 text-sm text-ink">
                        <span className="text-volt mt-1">▶</span> {s}
                      </li>
                    ))}
                  </ul>
                </div>

                {/* Confidence note (new format only) */}
                {preview?.confidence && (
                  <div className="mt-6 inline-flex items-center gap-2 text-[10px] uppercase tracking-[0.18em] font-bold text-ink/65 border border-gray-border px-2.5 py-1">
                    <ShieldCheck className="w-3 h-3 text-volt" />
                    Preview confidence · {preview.confidence}
                  </div>
                )}
              </div>

              {/* SECTION 2 — LOCKED TEASER: Unlock 9 more sections */}
              {!unlocked ? (
                <div
                  data-testid="preview-locked-teaser"
                  className="relative bg-gradient-to-br from-volt/10 via-deepnavy/30 to-deepnavy/30 p-6 md:p-8 border-l border-volt/30 overflow-hidden"
                >
                  <div className="absolute -top-10 -right-10 w-40 h-40 bg-volt/15 blur-3xl rounded-full pointer-events-none" />
                  <div className="relative">
                    <div className="inline-flex items-center gap-2 text-[10px] uppercase tracking-[0.22em] font-bold text-volt border border-volt/40 bg-volt/10 px-2.5 py-1.5">
                      <Lock className="w-3 h-3" /> Locked
                    </div>
                    <div className="mt-5 font-barlow font-black uppercase text-3xl md:text-4xl text-ink leading-[0.95] tracking-tight">
                      Unlock <span className="text-volt">9 more</span><br />sections
                    </div>
                    <p className="mt-4 text-sm text-ink/70 leading-relaxed">
                      Technical · Tactical · Physical · Mentality · Scout view · Training plan · Potential · Premium PDF · Scout chat.
                    </p>
                    <ul className="mt-5 space-y-1.5 text-[12px] text-ink/60">
                      {["Confidence + evidence per category", "Personalised 90-day plan", "Premium downloadable PDF"].map((t, i) => (
                        <li key={i} className="flex items-start gap-2"><span className="text-volt mt-0.5">·</span><span>{t}</span></li>
                      ))}
                    </ul>
                    <button
                      onClick={handleUnlock}
                      disabled={unlocking}
                      data-testid="preview-locked-cta"
                      className="mt-6 inline-flex items-center justify-center gap-2 bg-volt hover:bg-forest-pop text-white font-barlow font-black uppercase tracking-widest text-xs px-4 py-3 transition-colors disabled:opacity-60"
                    >
                      {unlocking ? <Loader2 className="w-4 h-4 animate-spin" /> : <Unlock className="w-4 h-4" />}
                      Unlock for ${price} USD
                    </button>
                    <div className="mt-3">
                      <PaymentBadges variant="compact" />
                    </div>
                  </div>
                </div>
              ) : (
                <div className="bg-surface p-6 md:p-8 border-l border-gray-border">
                  <span className="text-volt text-xs uppercase tracking-[0.25em] font-bold">Premium unlocked</span>
                  <p className="mt-3 text-ink/75 text-sm leading-relaxed">All 11 sections, evidence + confidence, scout review chat, and the premium PDF are now available below.</p>
                  <div className="mt-6 inline-flex items-center gap-2 text-[10px] uppercase tracking-widest font-bold text-volt border border-volt/40 bg-volt/10 px-2.5 py-1.5">
                    <Check className="w-3 h-3" /> Full report active
                  </div>
                </div>
              )}
            </div>
          </motion.div>

          {/* ===== Premium Sections ===== */}
          <div className="mt-10 relative">
            {!unlocked && (
              <LockedOverlay
                price={price}
                onUnlock={handleUnlock}
                loading={unlocking}
              />
            )}

            <div className={`${!unlocked ? "blur-locked" : ""} space-y-6`} data-testid="premium-content">
              {/* Executive Summary */}
              {(unlocked && full_report) && (
                <div className="bg-surface border border-gray-border p-6 md:p-8">
                  <h3 className="font-barlow font-black uppercase text-2xl md:text-3xl text-ink">Executive Summary</h3>
                  <p className="mt-4 text-ink/85 leading-relaxed">{full_report.executive_summary}</p>
                </div>
              )}

              {/* Placeholder content if locked */}
              {!unlocked && (
                <>
                  <div className="bg-surface border border-gray-border p-6 md:p-8">
                    <h3 className="font-barlow font-black uppercase text-2xl md:text-3xl text-ink">Technical Analysis</h3>
                    <div className="mt-6 grid sm:grid-cols-2 gap-4">
                      {["First touch","Ball control","Dribbling","Passing","Shooting","Weak foot","1v1 actions"].map((k,i)=>(
                        <div key={i} className="flex items-center justify-between bg-deepnavy p-3 border border-gray-border">
                          <span className="text-ink/80 text-sm">{k}</span>
                          <span className="text-volt font-barlow font-black text-xl">8/10</span>
                        </div>
                      ))}
                    </div>
                  </div>
                  <div className="bg-surface border border-gray-border p-6 md:p-8">
                    <h3 className="font-barlow font-black uppercase text-2xl md:text-3xl text-ink">Tactical Analysis</h3>
                    <div className="mt-6 grid sm:grid-cols-2 gap-4">
                      {["Positioning","Off-ball movement","Scanning","Decision making","Timing of runs","Game understanding"].map((k,i)=>(
                        <div key={i} className="flex items-center justify-between bg-deepnavy p-3 border border-gray-border">
                          <span className="text-ink/80 text-sm">{k}</span>
                          <span className="text-volt font-barlow font-black text-xl">7/10</span>
                        </div>
                      ))}
                    </div>
                  </div>
                  <div className="bg-surface border border-gray-border p-6 md:p-8">
                    <h3 className="font-barlow font-black uppercase text-2xl md:text-3xl text-ink">Physical & Mentality</h3>
                    <p className="mt-3 text-ink/65 text-sm">Acceleration · Balance · Agility · Work rate · Focus · Competitive mindset.</p>
                  </div>
                  <div className="bg-surface border border-gray-border p-6 md:p-8">
                    <h3 className="font-barlow font-black uppercase text-2xl md:text-3xl text-ink">Scout View · Training Plan · Video Comments</h3>
                    <p className="mt-3 text-ink/65 text-sm">Full breakdown across scout perspective, personalized training plan and timestamped video comments.</p>
                  </div>
                </>
              )}

              {/* Unlocked content */}
              {(unlocked && full_report) && (
                <>
                  {/* Overall benchmark hero — places the player on the age+position tier landscape */}
                  <OverallBenchmarkBanner
                    ob={full_report.overall_benchmark}
                    overallScore={full_report.scores?.overall_development}
                  />

                  {/* Stylistic archetype — public, style-only comparison */}
                  <ArchetypeCard archetype={archetype} />

                  {/* Top 3 closest archetype matches */}
                  <ClosestMatchesStrip archetype={archetype} />

                  {/* Player DNA — unique attribute fingerprint */}
                  <DnaFingerprint fullReport={full_report} ageProfile={age_profile_reference} />

                  {/* Performance Radar — 4-pillar visualisation with tier reference rings */}
                  {radarData && (
                    <div data-testid="performance-radar-card" className="bg-surface border border-gray-border p-6 md:p-8">
                      <div className="flex items-start justify-between gap-4 flex-wrap mb-2">
                        <div>
                          <div className="text-[10px] uppercase tracking-[0.28em] font-bold text-forest mb-2">Pillar overview</div>
                          <h3 className="font-barlow font-black uppercase text-2xl md:text-3xl text-ink leading-tight">
                            Performance radar
                          </h3>
                          <p className="mt-2 text-sm text-ink/65 max-w-md">
                            One shape per pillar — Technical, Tactical, Physical, Mental. The further the shape reaches an axis, the stronger the player is in that area.
                          </p>
                        </div>
                        <div className="flex flex-col gap-1 items-start">
                          <div className="text-[9px] uppercase tracking-[0.22em] font-bold text-ink/55">Reference rings</div>
                          <div className="flex items-center gap-2 text-[10px] uppercase tracking-[0.14em] font-bold">
                            <span className="w-3 h-1 bg-stone-400" /> <span className="text-ink/70">Standard 4</span>
                          </div>
                          <div className="flex items-center gap-2 text-[10px] uppercase tracking-[0.14em] font-bold">
                            <span className="w-3 h-1 bg-amber-700" /> <span className="text-ink/70">Strong 6</span>
                          </div>
                          <div className="flex items-center gap-2 text-[10px] uppercase tracking-[0.14em] font-bold">
                            <span className="w-3 h-1 bg-forest-pop" /> <span className="text-ink/70">Pro 8</span>
                          </div>
                          <div className="flex items-center gap-2 text-[10px] uppercase tracking-[0.14em] font-bold">
                            <span className="w-3 h-1 bg-forest" /> <span className="text-ink/70">Elite 9.5</span>
                          </div>
                        </div>
                      </div>
                      <div className="mt-4 h-[420px]">
                        <ResponsiveContainer width="100%" height="100%">
                          <RadarChart data={radarData} margin={{ top: 24, right: 56, bottom: 24, left: 56 }} outerRadius="78%">
                            <PolarGrid stroke="#D4CFC1" strokeDasharray="2 3" />
                            <PolarAngleAxis
                              dataKey="axis"
                              tick={{ fill: "#0A0F0D", fontSize: 13, fontWeight: 800, letterSpacing: 1 }}
                            />
                            <PolarRadiusAxis
                              angle={90}
                              domain={[0, 10]}
                              tickCount={6}
                              tick={{ fill: "#9CA3AF", fontSize: 10 }}
                              axisLine={false}
                              tickFormatter={(v) => (v === 0 ? "" : String(v))}
                            />
                            {/* Tier reference rings — drawn as faint radars behind the player shape */}
                            <Radar
                              name="Elite"
                              dataKey={() => 9.5}
                              data={radarData}
                              stroke="#1F4F2F"
                              strokeWidth={1}
                              strokeDasharray="3 3"
                              fill="transparent"
                              isAnimationActive={false}
                            />
                            <Radar
                              name="Pro"
                              dataKey={() => 8}
                              data={radarData}
                              stroke="#2D6B3D"
                              strokeWidth={1}
                              strokeDasharray="3 3"
                              fill="transparent"
                              isAnimationActive={false}
                            />
                            <Radar
                              name="Strong"
                              dataKey={() => 6}
                              data={radarData}
                              stroke="#B45309"
                              strokeWidth={1}
                              strokeDasharray="3 3"
                              fill="transparent"
                              isAnimationActive={false}
                            />
                            {/* Player shape */}
                            <Radar
                              name="Player"
                              dataKey="score"
                              stroke="#1F4F2F"
                              strokeWidth={2.5}
                              fill="#1F4F2F"
                              fillOpacity={0.28}
                            />
                          </RadarChart>
                        </ResponsiveContainer>
                      </div>
                      <p className="mt-2 text-xs text-ink/50 italic">
                        Dashed rings = reference levels for Strong Club, Pro Academy, and Elite Academy. The solid forest shape is the player's profile.
                      </p>
                    </div>
                  )}

                  <SectionGrid title="Technical Analysis" section={full_report.technical} />
                  <SectionGrid title="Tactical Analysis" section={full_report.tactical} />
                  <SectionGrid title="Physical Analysis" section={full_report.physical} />
                  <SectionGrid title="Mentality Analysis" section={full_report.mentality} />

                  {/* European Academy reference profile — position priorities vs Pro Academy expectations */}
                  <AgeProfileCard ref={age_profile_reference} />

                  {/* Trial-readiness checklist — position-specific, scout-style */}
                  <TrialReadinessCard tr={trial_readiness} />

                  {/* Scout View */}
                  {full_report.scout_view && (
                    <div className="bg-surface border border-gray-border p-6 md:p-8">
                      <h3 className="font-barlow font-black uppercase text-2xl md:text-3xl text-ink">How a Scout Might Assess This Player</h3>
                      <div className="mt-6 grid lg:grid-cols-3 gap-px bg-cream-soft/20">
                        <div className="bg-surface p-4">
                          <div className="text-xs uppercase tracking-[0.2em] font-bold text-volt mb-3">Key strengths</div>
                          <ul className="space-y-2 text-sm text-ink/85">
                            {(full_report.scout_view.key_strengths || []).map((s,i)=>(
                              <li key={i} className="flex gap-2"><span className="text-volt mt-1">▶</span><span>{s}</span></li>
                            ))}
                          </ul>
                        </div>
                        <div className="bg-surface p-4">
                          <div className="text-xs uppercase tracking-[0.2em] font-bold text-yellow-400 mb-3">Areas of concern</div>
                          <ul className="space-y-2 text-sm text-ink/85">
                            {(full_report.scout_view.areas_of_concern || []).map((s,i)=>(
                              <li key={i} className="flex gap-2"><span className="text-yellow-400 mt-1">▶</span><span>{s}</span></li>
                            ))}
                          </ul>
                        </div>
                        <div className="bg-surface p-4">
                          <div className="text-xs uppercase tracking-[0.2em] font-bold text-ink/65 mb-3">Development priorities</div>
                          <ul className="space-y-2 text-sm text-ink/85">
                            {(full_report.scout_view.development_priorities || []).map((s,i)=>(
                              <li key={i} className="flex gap-2"><span className="text-ink/65 mt-1">▶</span><span>{s}</span></li>
                            ))}
                          </ul>
                        </div>
                      </div>
                      <div className="mt-6 grid md:grid-cols-2 gap-px bg-cream-soft/20">
                        <div className="bg-surface p-4">
                          <div className="text-xs uppercase tracking-[0.2em] font-bold text-ink/50 mb-2">Appropriate next competitive level</div>
                          <p className="text-sm text-ink/85">{full_report.scout_view.appropriate_next_level}</p>
                        </div>
                        <div className="bg-surface p-4">
                          <div className="text-xs uppercase tracking-[0.2em] font-bold text-ink/50 mb-2">Positional suitability</div>
                          <p className="text-sm text-ink/85">{full_report.scout_view.positional_suitability}</p>
                        </div>
                      </div>
                      <p className="mt-6 text-xs text-ink/50 italic">
                        This is an independent development analysis and does not guarantee selection or advancement opportunities.
                      </p>

                      {/* What we couldn't assess — only on new evidence-based reports */}
                      {Array.isArray(couldNotAssess) && couldNotAssess.length > 0 && (
                        <div className="mt-6 border border-orange-300/30 bg-orange-300/5 p-4">
                          <div className="flex items-center gap-2 mb-2">
                            <AlertTriangle className="w-4 h-4 text-orange-300" />
                            <span className="text-[10px] uppercase tracking-[0.22em] font-bold text-orange-300">
                              What we couldn't assess from this video
                            </span>
                          </div>
                          <ul className="space-y-1.5">
                            {couldNotAssess.map((item, i) => (
                              <li key={i} className="text-sm text-orange-200/85 flex gap-2">
                                <span className="text-orange-300/60 mt-1">·</span>
                                <span>{item}</span>
                              </li>
                            ))}
                          </ul>
                          <p className="mt-3 text-[11px] text-orange-200/55 italic">
                            Upload different footage (match play, drills, etc.) to assess these areas.
                          </p>
                        </div>
                      )}
                    </div>
                  )}

                  {/* Evidence Quality Note — explains overall video evidence */}
                  {evidenceQualityNote && (
                    <div
                      data-testid="evidence-quality-note"
                      className="bg-surface border border-volt/20 p-6 md:p-8"
                    >
                      <div className="flex items-center gap-2 mb-3">
                        <Info className="w-4 h-4 text-volt" strokeWidth={2} />
                        <h3 className="font-barlow font-black uppercase text-lg md:text-xl text-ink">Evidence Quality</h3>
                      </div>
                      <p className="text-sm text-ink/75 leading-relaxed">{evidenceQualityNote}</p>
                    </div>
                  )}

                  {/* Potential */}
                  {full_report.potential_assessment && (
                    <div className="bg-surface border border-gray-border p-6 md:p-8">
                      <h3 className="font-barlow font-black uppercase text-2xl md:text-3xl text-ink">Potential Assessment</h3>
                      <div className="mt-6 grid md:grid-cols-2 gap-px bg-cream-soft/20">
                        {[
                          ["Current level", full_report.potential_assessment.current_level],
                          ["Development potential", full_report.potential_assessment.development_potential],
                          ["Recommended next step", full_report.potential_assessment.recommended_next_step],
                          ["3-month focus", full_report.potential_assessment.three_month_focus],
                        ].map(([k, v], i) => (
                          <div key={i} className="bg-surface p-4">
                            <div className="text-xs uppercase tracking-[0.2em] font-bold text-volt mb-2">{k}</div>
                            <p className="text-sm text-ink/85">{v}</p>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Training Plan */}
                  {full_report.training_plan && (
                    <div className="bg-surface border border-gray-border p-6 md:p-8">
                      <h3 className="font-barlow font-black uppercase text-2xl md:text-3xl text-ink">Personal Training Plan</h3>
                      <div className="mt-6 grid md:grid-cols-2 lg:grid-cols-3 gap-px bg-cream-soft/20">
                        {(full_report.training_plan.exercises || []).map((ex, i) => (
                          <div key={i} className="bg-surface p-4">
                            <div className="flex items-center justify-between mb-2">
                              <span className="font-barlow font-black uppercase text-ink text-base">{ex.name}</span>
                              <span className="text-xs text-volt font-bold">{ex.duration}</span>
                            </div>
                            <p className="text-sm text-ink/75 leading-relaxed">{ex.description}</p>
                          </div>
                        ))}
                      </div>
                      <div className="mt-6 grid md:grid-cols-3 gap-px bg-cream-soft/20">
                        <div className="bg-surface p-4">
                          <div className="text-xs uppercase tracking-[0.2em] font-bold text-volt mb-2">Weekly focus</div>
                          <p className="text-sm text-ink/85">{full_report.training_plan.weekly_focus}</p>
                        </div>
                        <div className="bg-surface p-4">
                          <div className="text-xs uppercase tracking-[0.2em] font-bold text-volt mb-2">30-day plan</div>
                          <p className="text-sm text-ink/85">{full_report.training_plan.thirty_day_plan}</p>
                        </div>
                        <div className="bg-surface p-4">
                          <div className="text-xs uppercase tracking-[0.2em] font-bold text-volt mb-2">90-day plan</div>
                          <p className="text-sm text-ink/85">{full_report.training_plan.ninety_day_plan}</p>
                        </div>
                      </div>
                    </div>
                  )}

                  {/* Video Moments — frame-stamped evidence */}
                  {full_report.video_comments && full_report.video_comments.length > 0 && (
                    <div data-testid="video-moments-card" className="bg-surface border border-gray-border p-6 md:p-8">
                      <div className="text-[10px] uppercase tracking-[0.28em] font-bold text-forest mb-2">Frame-stamped evidence</div>
                      <h3 className="font-barlow font-black uppercase text-2xl md:text-3xl text-ink leading-tight">Video moments</h3>
                      <p className="mt-2 text-sm text-ink/65 max-w-xl">
                        Every observation is anchored to the exact frame it was seen at — so you can verify each note in the original clip.
                      </p>
                      <div className="mt-6 grid sm:grid-cols-2 gap-4">
                        {full_report.video_comments.map((c, i) => (
                          <div
                            key={i}
                            data-testid={`video-moment-${i}`}
                            className="bg-cream-card overflow-hidden border-l-2 border-forest"
                          >
                            <div className="relative aspect-video bg-cream-soft">
                              {c.frame_url ? (
                                <img
                                  data-testid={`video-moment-frame-${i}`}
                                  src={`${ASSET_BASE}${c.frame_url}`}
                                  alt={`Moment at ${c.timestamp}`}
                                  className="absolute inset-0 w-full h-full object-cover"
                                  loading="lazy"
                                />
                              ) : (
                                <div className="absolute inset-0 flex items-center justify-center">
                                  <span className="text-ink/30 text-xs uppercase tracking-wider">no frame</span>
                                </div>
                              )}
                              <div className="absolute bottom-2 left-2 bg-ink text-cream-base px-2 py-1 text-xs font-barlow font-black tracking-wide">
                                {c.timestamp || "—"}
                              </div>
                            </div>
                            <p className="p-4 text-sm text-ink/85 leading-relaxed">{c.comment}</p>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Final summary */}
                  {full_report.final_summary && (
                    <div className="bg-surface border border-gray-border p-6 md:p-8">
                      <h3 className="font-barlow font-black uppercase text-2xl md:text-3xl text-ink">Final Summary</h3>
                      <p className="mt-4 text-ink/85 leading-relaxed">{full_report.final_summary}</p>
                      <p className="mt-6 text-xs text-ink/50 italic">
                        Scores presented as developmental guidance, not definitive scouting evaluations.
                      </p>
                    </div>
                  )}
                </>
              )}

              {/* Scout Review — bonus human review on top of AI report */}
              {unlocked && (
                <ScoutReview reportId={id} />
              )}

              {/* If unlocked but report not yet generated */}
              {unlocked && !full_report && !generatingFull && (
                <div className="bg-surface border border-volt/30 p-8 text-center">
                  <Unlock className="w-10 h-10 text-volt mx-auto mb-4" strokeWidth={1.5} />
                  <h3 className="font-barlow font-black uppercase text-2xl text-ink">Report unlocked</h3>
                  <p className="mt-2 text-ink/65 text-sm">Generate your premium analysis now.</p>
                  <button
                    onClick={handleGenerateFull}
                    data-testid="generate-full-report-btn"
                    className="mt-6 bg-volt hover:bg-forest-pop text-white font-barlow font-black uppercase tracking-widest text-sm px-6 py-3 transition-colors"
                  >
                    Generate full report
                  </button>
                </div>
              )}
              {generatingFull && (
                <div className="bg-surface border border-volt/30 p-8 text-center">
                  <Loader2 className="w-8 h-8 animate-spin text-volt mx-auto" />
                  <p className="mt-4 text-ink/70 uppercase tracking-widest font-bold text-sm">Generating full premium report... a few minutes</p>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
