import React, { useEffect, useState, useCallback, useRef } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { motion } from "framer-motion";
import {
  Radar, RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, ResponsiveContainer,
} from "recharts";
import Navigation from "@/components/Navigation";
import { trackPurchase, trackViewContent } from "@/lib/pixels";
import ReportChapterNav from "@/components/ReportChapterNav";
import MarkedCropCanvas from "@/components/MarkedCropCanvas";
import FullFrameWithBoxCanvas from "@/components/FullFrameWithBoxCanvas";
import { FootballIcon, MiniPitch, JerseyChip, PitchLineDivider } from "@/components/FootballAccents";
import { PillarIcon, AnimatedScore, SkillMeter, MomentCard, PitchDecoration } from "@/components/report/FootballReport";
import PerformanceRadarHero from "@/components/report/PerformanceRadarHero";
import SkillsBreakdown from "@/components/report/SkillsBreakdown";
import api, { ASSET_BASE } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { isPremiumUser } from "@/lib/premium";
import {
  Lock, Unlock, Download, Loader2, ChevronLeft, ShieldCheck, Star, AlertTriangle, Eye, Info, Check, Share2, Link2, Mail, Zap, Target, Crown, Sparkles, IdCard,
} from "lucide-react";
import ScoutReview from "@/components/ScoutReview";
import CheckoutTransitionModal from "@/components/CheckoutTransitionModal";
import EmbeddedCheckoutModal from "@/components/EmbeddedCheckoutModal";
import PaymentBadges from "@/components/PaymentBadges";
import ReportPaywallTiers from "@/components/ReportPaywallTiers";
import PremiumReadyBanner from "@/components/PremiumReadyBanner";
import PremiumReportV2 from "@/components/report-v2/PremiumReportV2";
import DoubtConfirmModal from "@/components/DoubtConfirmModal";

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

/* Map SectionGrid `title` → PillarIcon `kind`.
   Purely presentational — no data/scores change. */
const _PILLAR_KIND = {
  technical: "technical",
  tactical: "tactical",
  physical: "physical",
  mindset: "mindset",
  mentality: "mindset",
};

function SectionGrid({ title, section, onSeek, chapter, sub }) {
  if (!section) return null;
  const pillarKind = _PILLAR_KIND[String(title).toLowerCase()] || null;
  return (
    <div className="bg-surface border border-gray-border p-6 md:p-8 scroll-mt-20" id={`report-${title.toLowerCase().replace(/\s+/g, "-")}`}>
      {chapter && (
        <div className="flex items-center gap-2 mb-2">
          <PitchLineDivider className="w-10 h-2 text-forest/55" />
          <span className="text-[9px] uppercase tracking-[0.32em] font-black text-forest">{chapter}</span>
        </div>
      )}
      <div className="flex items-start gap-4 mb-1">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2.5">
            {pillarKind && (
              <PillarIcon kind={pillarKind} className="w-8 h-8 md:w-9 md:h-9 text-forest shrink-0" />
            )}
            <h3 className="font-barlow font-black uppercase text-2xl md:text-3xl text-ink leading-[0.95]">{title}</h3>
          </div>
          {sub && (
            <p className="mt-1 text-sm text-ink/55">{sub}</p>
          )}
          <PitchDecoration className="mt-2 w-20 h-6 text-forest/25" />
        </div>
      </div>
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
                  <AnimatedScore
                    value={val?.score ?? 0}
                    max={10}
                    ring
                    colorClass={scoreColor(val?.score)}
                    className="font-barlow font-black text-3xl leading-none"
                    testid={`attr-score-${key}`}
                  />
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
                    <div className="mt-4" data-testid="skill-meter-wrap">
                      <div className="text-[9px] uppercase tracking-[0.22em] font-bold text-ink/45 mb-1.5">
                        For his age + position
                      </div>
                      <SkillMeter
                        value={val?.score ?? 0}
                        max={10}
                        tiers={["Standard", "Strong", "Pro", "Elite"]}
                        currentTier={(TIER_META[tier]?.label || "").split(" ")[0]}
                      />
                    </div>
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

              {/* Evidence list — confidence badge removed for confident-voice UX */}
              {evidence.length > 0 && (
                <details className="mt-3 group">
                  <summary className="cursor-pointer text-[10px] uppercase tracking-widest font-bold text-ink/50 hover:text-volt transition-colors list-none">
                    Show evidence ({evidence.length})
                  </summary>
                  <ul className="mt-2 space-y-1.5">
                    {evidence.map((e, idx) => {
                      const ts = e.timestamp;
                      const tsParsed = ts && /^\s*\d{1,2}:\d{2}/.test(ts);
                      const isClickable = !!(onSeek && tsParsed);
                      return (
                        <li key={idx} className="text-[11px] text-ink/70 flex gap-2">
                          {isClickable ? (
                            <button
                              type="button"
                              onClick={() => onSeek(ts)}
                              data-testid={`evidence-seek-${key}-${idx}`}
                              aria-label={`Play this moment at ${ts}`}
                              title={`Play this moment at ${ts}`}
                              className="font-barlow font-black text-volt min-w-[42px] tabular-nums hover:text-forest-pop hover:underline underline-offset-2 transition-colors cursor-pointer text-left"
                            >
                              {ts}
                            </button>
                          ) : (
                            <span className="font-barlow font-black text-volt min-w-[42px] tabular-nums">{ts || "·"}</span>
                          )}
                          <span className="leading-snug">{e.what || e.note}</span>
                        </li>
                      );
                    })}
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
      {/* Nano Banana — dark stadium tunnel emerging into pitch (NO people) */}
      <img
        src={`${process.env.REACT_APP_BACKEND_URL}/api/static/landing/bg-benchmark-tunnel.png`}
        alt=""
        aria-hidden
        loading="lazy"
        onError={(e) => { e.currentTarget.style.display = "none"; }}
        className="absolute inset-0 w-full h-full object-cover opacity-35"
      />
      {/* Forest wash + depth overlay keeps the forest-green identity + text readable */}
      <div aria-hidden className="absolute inset-0 bg-gradient-to-br from-forest via-forest/85 to-forest/95" />
      <div aria-hidden className="absolute inset-0 bg-gradient-to-r from-forest/70 via-transparent to-forest/40" />
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
              for his age ({ob.age_bracket_used.replace(/_/g, " ").toLowerCase()})
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
        <div className="text-[9px] uppercase tracking-[0.28em] font-bold text-cream-base/65 mb-3">Where he stands on the football ladder</div>
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
      {/* Nano Banana — aerial floodlit empty pitch (NO people) */}
      <img
        src={`${process.env.REACT_APP_BACKEND_URL}/api/static/landing/bg-archetype-aerial.png`}
        alt=""
        aria-hidden
        loading="lazy"
        onError={(e) => { e.currentTarget.style.display = "none"; }}
        className="absolute inset-0 w-full h-full object-cover opacity-30"
      />
      <div aria-hidden className="absolute inset-0 bg-gradient-to-b from-forest/90 via-forest/85 to-forest/95" />
      <div aria-hidden className="absolute inset-0 bg-gradient-to-r from-forest/95 via-transparent to-forest/50" />
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

      {/* Career brief — FBref / Transfermarkt verified career stats (Step 3) */}
      {archetype.career_brief && proName && (
        <div
          data-testid="archetype-career-brief"
          className="relative mx-6 md:mx-8 mb-5 p-5 bg-cream-base/10 border border-cream-base/20"
        >
          <div className="text-[10px] uppercase tracking-[0.28em] font-bold text-cream-base/85 mb-2">
            {proName} · career snapshot (FBref · Transfermarkt verified)
          </div>
          <p className="text-sm leading-relaxed text-cream-base/95">
            {archetype.career_brief}
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
  const order = ["style", "build", "role", "path", "fifa"];
  const lenses = order
    .map((k) => archetype.lenses[k])
    .filter((l) => l && l.name);
  if (lenses.length === 0) return null;

  return (
    <div data-testid="lens-matches-strip" className="bg-surface border border-gray-border p-6 md:p-7">
      <div className="flex items-end justify-between gap-4 flex-wrap mb-5">
        <div>
          <div className="text-[10px] uppercase tracking-[0.28em] font-bold text-forest mb-2">
            The {lenses.length}-lens comparison
          </div>
          <h3 className="font-barlow font-black uppercase text-xl md:text-2xl text-ink leading-tight">
            How this player resembles {lenses.length} different pros
          </h3>
          <p className="mt-1.5 text-xs text-ink/60 max-w-xl">
            Each lens picks the closest pro on a different dimension: how he plays, his physical build, his on-pitch role, the career path he's on, and a real k-NN similarity search against 7,500+ FIFA-rated senior pros.
          </p>
        </div>
        <div className="text-[9px] uppercase tracking-[0.22em] font-bold text-ink/45 text-right">
          Style · Build · Role · Career-path · <span className="text-forest">FIFA data</span>
        </div>
      </div>

      <div className="grid sm:grid-cols-2 gap-3">
        {lenses.map((lens) => {
          const meta = TIER_PILL_META[lens.tier] || null;
          const scoreWidth = Math.min(100, Math.max(20, (lens.score || 0) * 10));
          const isFifa = lens.lens === "fifa";
          return (
            <div
              key={lens.lens}
              data-testid={`lens-match-${lens.lens}`}
              className={`relative p-4 md:p-5 ${
                isFifa
                  ? "bg-forest text-cream-base border-l-4 border-cream-base"
                  : "bg-cream-card border-l-4 border-forest"
              }`}
            >
              {isFifa && (
                <div className="absolute top-3 right-3 text-[8px] uppercase tracking-[0.22em] font-bold px-2 py-0.5 bg-cream-base text-forest">
                  Real data · k-NN
                </div>
              )}
              <div className="flex items-center gap-3 mb-3">
                <div
                  className={`w-12 h-12 shrink-0 flex items-center justify-center font-barlow font-black text-base shadow ${
                    isFifa ? "bg-cream-base text-forest" : "bg-forest text-cream-base"
                  }`}
                  style={{ clipPath: "polygon(50% 0, 100% 25%, 100% 75%, 50% 100%, 0 75%, 0 25%)" }}
                >
                  {_archetypeMonogram(lens.name)}
                </div>
                <div className="flex-1 min-w-0">
                  <div className={`text-[9px] uppercase tracking-[0.22em] font-bold ${
                    isFifa ? "text-cream-base/85" : "text-forest"
                  }`}>
                    {lens.lens_label}
                  </div>
                  <div className={`font-barlow font-black uppercase text-base md:text-lg truncate leading-tight ${
                    isFifa ? "text-white" : "text-ink"
                  }`}>
                    {lens.name}
                  </div>
                  <div className={`text-[10px] uppercase tracking-[0.18em] font-bold truncate ${
                    isFifa ? "text-cream-base/65" : "text-ink/55"
                  }`}>
                    {lens.club || "—"}
                    {lens.league && <span className="opacity-60"> · {lens.league}</span>}
                  </div>
                </div>
                {meta && !isFifa && (
                  <div className="hidden sm:inline-flex text-[8px] uppercase tracking-[0.2em] font-bold px-2 py-1 bg-cream-soft text-forest shrink-0">
                    {meta.label}
                  </div>
                )}
                {isFifa && typeof lens.overall === "number" && (
                  <div className="hidden sm:inline-flex text-[8px] uppercase tracking-[0.2em] font-bold px-2 py-1 bg-cream-base/15 text-cream-base shrink-0">
                    FIFA {lens.overall}
                  </div>
                )}
              </div>
              <p className={`text-xs md:text-sm leading-snug mb-3 ${
                isFifa ? "text-cream-base/85" : "text-ink/70"
              }`}>
                {lens.why}
              </p>
              <div className="flex items-center gap-3">
                <div className={`flex-1 h-1.5 overflow-hidden ${isFifa ? "bg-cream-base/15" : "bg-cream-soft"}`}>
                  <div className={`h-full ${isFifa ? "bg-cream-base" : "bg-forest"}`} style={{ width: `${scoreWidth}%` }} />
                </div>
                <div className={`font-barlow font-black tabular-nums text-xl leading-none ${
                  isFifa ? "text-white" : "text-forest"
                }`}>
                  {isFifa && typeof lens.similarity_pct === "number"
                    ? `${lens.similarity_pct.toFixed(1)}%`
                    : (lens.score ?? 0).toFixed(1)}
                </div>
                {!isFifa && <div className="text-[10px] font-bold text-ink/45">/10</div>}
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

/* FIFA Data Twin panel — shows the FULL top-5 nearest-neighbour result from the
   real k-NN search against the FIFA-22 dataset. This is the panel that makes
   the report feel rigorous: "we ran your scores against 7,473 senior pros and
   here are the 5 closest matches by 22-attribute Euclidean similarity." */
function FifaDataTwinPanel({ archetype }) {
  if (!archetype || !Array.isArray(archetype.fifa_neighbors) || archetype.fifa_neighbors.length === 0) {
    return null;
  }
  const neighbors = archetype.fifa_neighbors;
  const meta = archetype.fifa_db_meta || {};

  return (
    <div data-testid="fifa-data-twin-panel" className="bg-surface border border-gray-border p-6 md:p-7">
      <div className="flex items-end justify-between gap-4 flex-wrap mb-5">
        <div>
          <div className="text-[10px] uppercase tracking-[0.28em] font-bold text-forest mb-2">
            FIFA data twin · real similarity search
          </div>
          <h3 className="font-barlow font-black uppercase text-xl md:text-2xl text-ink leading-tight">
            The 5 closest senior pros by 22-attribute k-NN
          </h3>
          <p className="mt-1.5 text-xs text-ink/60 max-w-2xl">
            We ran your full scoring vector against{" "}
            <span className="font-bold text-forest">
              {meta.size ? meta.size.toLocaleString() : "7,000+"} senior pros
            </span>{" "}
            in the EA Sports FIFA dataset, computing per-attribute Euclidean similarity across 22 dimensions. Below are the 5 closest matches — and the 3 attributes where the gap is smallest in each case.
          </p>
        </div>
        <div className="text-[9px] uppercase tracking-[0.22em] font-bold text-ink/45">
          Hard-capped at 92% · honest spread
        </div>
      </div>

      <div className="space-y-2">
        {neighbors.map((n, i) => {
          const barWidth = Math.min(100, Math.max(20, n.similarity_pct || 0));
          const isTop = i === 0;
          return (
            <div
              key={`${n.name}-${i}`}
              data-testid={`fifa-neighbor-${i}`}
              className={`flex items-center gap-3 md:gap-4 p-3 md:p-4 ${
                isTop ? "bg-forest text-cream-base" : "bg-cream-card border-l-2 border-forest/30"
              }`}
            >
              {/* Rank */}
              <div className={`font-barlow font-black text-2xl shrink-0 w-8 text-center ${
                isTop ? "text-cream-base" : "text-forest/70"
              }`}>
                {i + 1}
              </div>

              {/* Crest monogram */}
              <div
                className={`w-12 h-12 shrink-0 flex items-center justify-center font-barlow font-black text-base shadow ${
                  isTop ? "bg-cream-base text-forest" : "bg-forest text-cream-base"
                }`}
                style={{ clipPath: "polygon(50% 0, 100% 25%, 100% 75%, 50% 100%, 0 75%, 0 25%)" }}
              >
                {_archetypeMonogram(n.name)}
              </div>

              {/* Name + club */}
              <div className="flex-1 min-w-0">
                <div className={`font-barlow font-black uppercase text-sm md:text-base truncate ${
                  isTop ? "text-white" : "text-ink"
                }`}>
                  {n.name}
                </div>
                <div className={`text-[10px] uppercase tracking-[0.16em] font-bold truncate ${
                  isTop ? "text-cream-base/70" : "text-ink/55"
                }`}>
                  {n.club || "—"}
                  {n.league && <span className="opacity-60"> · {n.league}</span>}
                </div>
                {Array.isArray(n.nearest_attrs) && n.nearest_attrs.length > 0 && (
                  <div className={`text-[10px] mt-1 truncate ${
                    isTop ? "text-cream-base/80" : "text-ink/50"
                  }`}>
                    closest on:{" "}
                    {n.nearest_attrs.map((a, idx) => (
                      <span key={idx} className={`inline-block px-1.5 py-0.5 mr-1 text-[9px] font-bold uppercase tracking-wide ${
                        isTop ? "bg-cream-base/15 text-white" : "bg-forest/10 text-forest"
                      }`}>
                        {a.replace(/_/g, " ")}
                      </span>
                    ))}
                  </div>
                )}
              </div>

              {/* Build + foot mini-pills */}
              <div className="hidden md:flex flex-col items-end gap-1 shrink-0">
                {n.build && (
                  <span className={`text-[8px] uppercase tracking-[0.18em] font-bold px-2 py-0.5 ${
                    isTop ? "bg-cream-base/15 text-cream-base" : "bg-cream-soft text-forest"
                  }`}>
                    {n.build.replace(/_/g, " ")}
                  </span>
                )}
                {n.preferred_foot && (
                  <span className={`text-[8px] uppercase tracking-[0.18em] font-bold px-2 py-0.5 ${
                    isTop ? "bg-cream-base/15 text-cream-base" : "bg-cream-soft text-forest"
                  }`}>
                    {n.preferred_foot}-footed
                  </span>
                )}
              </div>

              {/* Similarity bar + % */}
              <div className="flex items-center gap-2 shrink-0">
                <div className={`hidden md:block w-24 h-2 ${isTop ? "bg-cream-base/15" : "bg-cream-soft"}`}>
                  <div
                    className={`h-full ${isTop ? "bg-cream-base" : "bg-forest"}`}
                    style={{ width: `${barWidth}%` }}
                  />
                </div>
                <div className={`font-barlow font-black text-2xl tabular-nums leading-none ${
                  isTop ? "text-white" : "text-forest"
                }`}>
                  {(n.similarity_pct ?? 0).toFixed(1)}
                </div>
                <div className={`text-[10px] font-bold ${isTop ? "text-cream-base/60" : "text-ink/45"}`}>
                  %
                </div>
              </div>
            </div>
          );
        })}
      </div>

      <p className="mt-5 text-xs text-ink/50 italic">
        Similarity computed as 100 − RMSE × 18 across 22 measured attributes (FIFA-22 attribute ratings normalised to a 0-10 scale, identical to the player's). Foot/build matches add a small bonus.{" "}
        <span className="not-italic font-bold text-ink/65">Source:</span> {meta.source || "EA Sports FIFA 22"}.
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

/* StatsBomb Pro Calibration — anchors the player's scores against Euro 2024
   senior-pro per-90 distributions. This is the panel that turns "8/10
   passing" into "Top 25% of Euro 2024 starters" — verifiable, public-source. */
function StatsBombCalibrationPanel({ calibration }) {
  if (!calibration || !Array.isArray(calibration.rows) || calibration.rows.length === 0) return null;
  const { position, position_n, source, source_url, competition, matches, rows, summary } = calibration;

  const BUCKET_META = {
    p90:      { label: "Top 10%",      cls: "bg-forest text-cream-base", barCls: "bg-forest",        widthPct: 95 },
    p75:      { label: "Top 25%",      cls: "bg-forest/85 text-cream-base", barCls: "bg-forest/80",  widthPct: 78 },
    p50:      { label: "Median pro",   cls: "bg-cream-soft text-forest", barCls: "bg-forest/55",     widthPct: 50 },
    p25:      { label: "Bottom 25%",   cls: "bg-cream-soft text-ink/70", barCls: "bg-ink/30",        widthPct: 25 },
    below_p25:{ label: "Below pro",    cls: "bg-cream-soft text-ink/60", barCls: "bg-ink/20",        widthPct: 12 },
  };

  return (
    <div data-testid="statsbomb-calibration-panel" className="bg-surface border border-gray-border p-6 md:p-7">
      <div className="flex items-end justify-between gap-4 flex-wrap mb-5">
        <div>
          <div className="text-[10px] uppercase tracking-[0.28em] font-bold text-forest mb-2">
            Pro calibration · StatsBomb Euro 2024
          </div>
          <h3 className="font-barlow font-black uppercase text-xl md:text-2xl text-ink leading-tight">
            Where your scores sit vs Euro 2024 senior pros
          </h3>
          <p className="mt-1.5 text-xs text-ink/60 max-w-2xl">
            Each score is checked against what real professional players actually do per 90 minutes at{" "}
            <span className="font-bold text-forest">{position_n} {position} starters</span>{" "}
            at the European Championship 2024 — extracted from public StatsBomb event-level data across{" "}
            <span className="font-bold text-forest">{matches} matches</span>.
          </p>
        </div>
        <div className="hidden lg:flex flex-col items-end gap-1 text-[9px] uppercase tracking-[0.22em] font-bold">
          {["p90","p75","p50","p25"].map((b) => (
            <div key={b} className="flex items-center gap-2">
              <span className="text-ink/50">{BUCKET_META[b].label}</span>
              <span className={`px-2 py-0.5 ${BUCKET_META[b].cls}`}>{summary[b] ?? 0}</span>
            </div>
          ))}
        </div>
      </div>

      <div className="space-y-1.5">
        {rows.map((r, i) => {
          const meta = BUCKET_META[r.bucket] || BUCKET_META.p25;
          // Pro reference label: show the relevant p-band value the user surpassed
          let proRef = "";
          if (r.bucket === "p90") proRef = `pro p90: ${r.pro_p90}`;
          else if (r.bucket === "p75") proRef = `pro p75: ${r.pro_p75}`;
          else if (r.bucket === "p50") proRef = `pro p50: ${r.pro_p50}`;
          else proRef = `pro p25: ${r.pro_p25}`;
          return (
            <div
              key={r.attribute_key}
              data-testid={`statsbomb-row-${r.attribute_key}`}
              className="flex items-center gap-3 md:gap-4 p-3 md:p-4 bg-cream-card"
            >
              {/* Attribute label + StatsBomb metric */}
              <div className="flex-1 min-w-0 max-w-[40%]">
                <div className="font-barlow font-black uppercase text-sm text-ink truncate">
                  {r.attribute_label}
                </div>
                <div className="text-[10px] uppercase tracking-[0.18em] font-bold text-ink/50 truncate">
                  {r.statsbomb_metric_label}
                </div>
              </div>

              {/* Score */}
              <div className="shrink-0 w-16 text-right">
                <div className="font-barlow font-black text-2xl tabular-nums text-forest leading-none">
                  {r.score}
                </div>
                <div className="text-[9px] uppercase tracking-[0.2em] font-bold text-ink/45">
                  / 10
                </div>
              </div>

              {/* Bar */}
              <div className="hidden md:block flex-1 relative h-3 bg-cream-soft">
                {/* p25/p50/p75/p90 ticks */}
                <div className="absolute top-0 left-[25%] w-px h-full bg-ink/15" />
                <div className="absolute top-0 left-[50%] w-px h-full bg-ink/15" />
                <div className="absolute top-0 left-[75%] w-px h-full bg-ink/15" />
                <div className="absolute top-0 left-[90%] w-px h-full bg-ink/15" />
                <div className={`absolute inset-y-0 left-0 ${meta.barCls}`} style={{ width: `${meta.widthPct}%` }} />
              </div>

              {/* Bucket pill + pro p-value */}
              <div className="shrink-0 flex flex-col items-end gap-1">
                <span className={`text-[9px] uppercase tracking-[0.18em] font-bold px-2.5 py-1 ${meta.cls}`}>
                  {r.bucket_label}
                </span>
                <span className="text-[9px] uppercase tracking-[0.18em] font-bold text-ink/45">
                  {proRef}
                </span>
              </div>
            </div>
          );
        })}
      </div>

      <div className="mt-5 p-3 bg-cream-soft text-xs text-ink/70 leading-relaxed">
        <span className="font-bold text-forest uppercase tracking-wider text-[10px]">Methodology:</span>{" "}
        {calibration.methodology}
      </div>

      <p className="mt-3 text-xs text-ink/50 italic">
        <span className="not-italic font-bold text-ink/65">Source:</span>{" "}
        <a href={source_url} target="_blank" rel="noopener noreferrer" className="underline hover:text-forest">
          {source}
        </a>
        {calibration.license && (
          <> · <span className="not-italic">License: {calibration.license}</span></>
        )}
        . The percentile bands describe where this player would sit if measured against {competition} starters at the same position.
      </p>
    </div>
  );
}



/* Position-specific reference profile card — shows the player's actual
   scores against Pro Academy expectations for the position + age bracket.


/* ============================================================================
   AGE INTELLIGENCE SCORING SYSTEM — UI COMPONENTS
   ============================================================================ */

/* AgeStageBanner — top-of-report stage indicator + headline. */
function AgeStageBanner({ age_intelligence }) {
  if (!age_intelligence || !age_intelligence.stage) return null;
  const { age_band, label, headline } = age_intelligence.stage;
  const level = age_intelligence.level;
  return (
    <div data-testid="age-stage-banner" className="bg-forest text-cream-base p-5 md:p-6">
      <div className="flex items-center gap-4 flex-wrap">
        <div className="text-[9px] uppercase tracking-[0.28em] font-bold text-cream-base/75 px-2.5 py-1 bg-cream-base/15">
          Reviewed for his age
        </div>
        <div className="font-barlow font-black text-2xl md:text-3xl tracking-tight uppercase">
          {age_band}
        </div>
        <div className="font-barlow font-black uppercase text-base md:text-lg text-cream-base/95">
          · {label}
        </div>
        {level && level.label && (
          <div data-testid="age-stage-level-pill" className="ml-auto inline-flex items-center gap-2 px-3 py-1.5 bg-cream-base text-forest">
            <span className="text-[9px] uppercase tracking-[0.22em] font-bold">Level</span>
            <span className="font-barlow font-black text-sm uppercase">{level.label}</span>
          </div>
        )}
      </div>
      {headline && (
        <p className="mt-2 text-sm md:text-base text-cream-base/85 italic">{headline}</p>
      )}
    </div>
  );
}


/* AgeAppropriateEvaluationDisclaimer — the credibility line. */
function AgeAppropriateEvaluationDisclaimer({ age_intelligence }) {
  if (!age_intelligence) return null;
  const text = age_intelligence.disclaimer ||
    "This player has been evaluated using age-appropriate and position-specific benchmarks. Professional player data is used as a style and long-term development reference, not as a direct comparison.";
  return (
    <div data-testid="age-appropriate-disclaimer" className="bg-cream-soft border-l-4 border-forest p-4 md:p-5">
      <div className="text-[10px] uppercase tracking-[0.28em] font-bold text-forest mb-1.5">
        How this evaluation works
      </div>
      <p className="text-sm md:text-base text-ink/85 leading-relaxed">{text}</p>
    </div>
  );
}


/* WhatWeEvaluatedBlock — shows the stage's evaluation focus AND what the AI
   could/couldn't see in the actual video. */
function WhatWeEvaluatedBlock({ age_intelligence }) {
  if (!age_intelligence) return null;
  const evaluated = age_intelligence.what_we_evaluated || [];
  const not_for_stage = age_intelligence.what_we_could_not_evaluate || [];
  const ai_blind_spots = age_intelligence.what_ai_could_not_evaluate || [];

  if (evaluated.length === 0 && not_for_stage.length === 0 && ai_blind_spots.length === 0) return null;

  return (
    <div data-testid="what-we-evaluated-block" className="bg-surface border border-gray-border p-6 md:p-7">
      <div className="text-[10px] uppercase tracking-[0.28em] font-bold text-forest mb-2">
        What we looked at · What we left for later
      </div>
      <h3 className="font-barlow font-black uppercase text-xl md:text-2xl text-ink leading-tight mb-5">
        What this report covers
      </h3>

      <div className="grid md:grid-cols-2 gap-4">
        <div data-testid="what-we-evaluated-list" className="bg-cream-card border-l-4 border-forest p-5">
          <div className="text-[10px] uppercase tracking-[0.22em] font-bold text-forest mb-3">
            Reviewed for his age
          </div>
          <ul className="space-y-2">
            {evaluated.map((item, i) => (
              <li key={i} className="text-sm text-ink/85 flex gap-2">
                <span className="text-forest font-bold shrink-0">·</span>
                <span>{item}</span>
              </li>
            ))}
          </ul>
        </div>

        <div data-testid="what-we-did-not-evaluate-list" className="bg-cream-card border-l-4 border-ink/30 p-5">
          <div className="text-[10px] uppercase tracking-[0.22em] font-bold text-ink/55 mb-3">
            Saved for his next age group
          </div>
          {not_for_stage.length > 0 ? (
            <ul className="space-y-2">
              {not_for_stage.map((item, i) => (
                <li key={i} className="text-sm text-ink/75 flex gap-2">
                  <span className="text-ink/40 font-bold shrink-0">·</span>
                  <span>{item}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-ink/60 italic">For his age, we look at everything visible &mdash; nothing was held back.</p>
          )}
        </div>
      </div>

      {ai_blind_spots.length > 0 && (
        <div data-testid="ai-blind-spots" className="mt-4 p-4 bg-cream-soft">
          <div className="text-[10px] uppercase tracking-[0.22em] font-bold text-ink/55 mb-2">
            Couldn&apos;t be seen in this particular video
          </div>
          <ul className="space-y-1">
            {ai_blind_spots.slice(0, 6).map((item, i) => (
              <li key={i} className="text-xs text-ink/65">
                <span className="font-bold text-ink/80">{item.label}:</span> {item.reason}
              </li>
            ))}
          </ul>
          <p className="mt-2 text-[10px] text-ink/45 italic">
            Upload follow-up footage that includes these moments for a complete picture.
          </p>
        </div>
      )}
    </div>
  );
}


/* AgeIntelligenceScoreboard — the 9-score grid. */
function AgeIntelligenceScoreboard({ age_intelligence, position_hint }) {
  if (!age_intelligence || !age_intelligence.scores) return null;
  const s = age_intelligence.scores;
  const stage = age_intelligence.stage || {};
  const nextStage = age_intelligence.next_stage;

  const SCORES = [
    { key: "current_age_score",            label: "For his age",                hint: `vs ${stage.age_band || "peers"} peers` },
    { key: "position_specific_score",      label: "For his position",           hint: position_hint || "in his role" },
    { key: "next_level_readiness_score",   label: "Ready for next level",       hint: nextStage ? `toward ${nextStage.age_band}` : "already at top level" },
    { key: "pro_style_match_score",        label: "Pro style match",            hint: "who he reminds us of" },
    { key: "technical_score",              label: "Technical",                  hint: "ball, dribbling, passing" },
    { key: "tactical_score",               label: "Tactical",                   hint: "scanning, decision-making, positioning" },
    { key: "physical_score",               label: "Physical",                   hint: "speed, balance, agility" },
    { key: "mentality_body_language_score",label: "Mindset & body language",    hint: "confidence, courage, focus" },
    { key: "development_priority_score",   label: "Room to grow",               hint: "biggest area to work on" },
  ];

  return (
    <div data-testid="age-intelligence-scoreboard" className="bg-surface border border-gray-border p-6 md:p-7">
      <div className="flex items-end justify-between gap-4 flex-wrap mb-5">
        <div>
          <div className="text-[10px] uppercase tracking-[0.28em] font-bold text-forest mb-2">
            Age Intelligence Scoreboard
          </div>
          <h3 className="font-barlow font-black uppercase text-xl md:text-2xl text-ink leading-tight">
            9 scores · for {stage.age_band}
          </h3>
          <p className="mt-1.5 text-xs text-ink/60 max-w-2xl">
            Each score is computed deterministically against the {stage.label?.toLowerCase()} rubric.
            None of these numbers are written prose — they are math over the observed sub-skills, weighted by stage focus.
          </p>
        </div>
        <div className="text-[9px] uppercase tracking-[0.22em] font-bold text-ink/45">
          {stage.age_band} · {stage.label}
        </div>
      </div>

      <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-2">
        {SCORES.map((cfg) => {
          const v = s[cfg.key];
          const isMissing = v === null || v === undefined;
          const isHighlight = cfg.key === "current_age_score";
          const barWidth = isMissing ? 0 : Math.min(100, Math.max(8, v * 10));
          return (
            <div
              key={cfg.key}
              data-testid={`scoreboard-${cfg.key}`}
              className={`p-4 ${isHighlight ? "bg-forest text-cream-base" : "bg-cream-card"}`}
            >
              <div className={`text-[9px] uppercase tracking-[0.2em] font-bold mb-1 ${isHighlight ? "text-cream-base/75" : "text-forest"}`}>
                {cfg.label}
              </div>
              {isMissing ? (
                <div>
                  <div className={`font-barlow font-black text-2xl leading-none ${isHighlight ? "text-white" : "text-ink/30"}`}>—</div>
                  <div className={`text-[9px] uppercase tracking-[0.18em] font-bold mt-1 ${isHighlight ? "text-cream-base/55" : "text-ink/45"}`}>
                    {(stage.id === "foundation" || stage.id === "technical") ? "Unlocks at U12" : "not applicable"}
                  </div>
                </div>
              ) : (
                <>
                  <div className="flex items-baseline gap-1">
                    <span className={`font-barlow font-black text-3xl tabular-nums leading-none ${isHighlight ? "text-white" : "text-forest"}`}>
                      {Number(v).toFixed(1)}
                    </span>
                    <span className={`text-[9px] uppercase tracking-[0.2em] font-bold ${isHighlight ? "text-cream-base/55" : "text-ink/45"}`}>
                      / 10
                    </span>
                  </div>
                  <div className={`mt-2 h-1 ${isHighlight ? "bg-cream-base/15" : "bg-cream-soft"}`}>
                    <div className={`h-full ${isHighlight ? "bg-cream-base" : "bg-forest"}`} style={{ width: `${barWidth}%` }} />
                  </div>
                  <div className={`text-[10px] mt-2 ${isHighlight ? "text-cream-base/65" : "text-ink/55"}`}>
                    {cfg.hint}
                  </div>
                </>
              )}
            </div>
          );
        })}
      </div>

      {age_intelligence.level && (
        <div className="mt-5 p-3 bg-cream-soft flex items-center gap-3 flex-wrap">
          <div className="text-[10px] uppercase tracking-[0.22em] font-bold text-forest">
            Overall level
          </div>
          <div data-testid="age-intelligence-level" className="font-barlow font-black uppercase text-base text-ink">
            {age_intelligence.level.label}
          </div>
          <div className="text-xs text-ink/60 flex-1">
            {age_intelligence.level.definition}
          </div>
        </div>
      )}
    </div>
  );
}


/* StageGatedPanel — friendly replacement when a senior-pro panel is hidden
   because the player is too young (U6-U11). */
function StageGatedPanel({ title, message, testId }) {
  if (!message) return null;
  return (
    <div data-testid={testId} className="bg-cream-card border border-gray-border p-6 md:p-7 text-center">
      <div className="text-[10px] uppercase tracking-[0.28em] font-bold text-forest mb-2">
        {title}
      </div>
      <div className="inline-flex items-center justify-center w-14 h-14 rounded-full bg-forest/10 text-forest mb-3">
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
          <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"
                stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
        </svg>
      </div>
      <p className="text-sm text-ink/75 max-w-lg mx-auto leading-relaxed">
        {message}
      </p>
    </div>
  );
}


/* AgeProfileCard — European academy reference overlay.
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


function LockedOverlay({ isLoggedIn, onUnlockSingle }) {
  // Paywall mirrors the front-page tier model (Single / Premium / VIP) so the
  // offer and admin-set prices are identical on every touchpoint. "Free" is
  // omitted — the visitor is already looking at their free preview.
  return (
    <div
      className="absolute inset-0 z-20 backdrop-blur-xl bg-cream-card/95 border border-gray-border overflow-y-auto"
      data-testid="locked-overlay"
    >
      <div className="max-w-6xl mx-auto p-6 md:p-10">
        <div className="text-center mb-8 md:mb-10">
          <div className="inline-flex items-center gap-2 mb-3">
            <Lock className="w-4 h-4 text-volt" strokeWidth={1.8} />
            <span className="text-volt text-[11px] uppercase tracking-[0.35em] font-black">Unlock the full report</span>
          </div>
          <h3 className="font-barlow font-black uppercase text-3xl md:text-5xl text-ink tracking-tight leading-[0.95]">
            Choose your<br />
            <span className="text-forest">scout package</span>
          </h3>
          <p className="mt-4 text-ink/70 text-sm md:text-base max-w-xl mx-auto leading-relaxed">
            Get the complete technical, tactical, physical &amp; mental breakdown — plus a real scout&apos;s written review.
          </p>
        </div>
        <ReportPaywallTiers isLoggedIn={isLoggedIn} onUnlockSingle={onUnlockSingle} />
      </div>
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
  const [doubtInfo, setDoubtInfo] = useState(null);
  const [doubtBusy, setDoubtBusy] = useState(false);
  const [downloadingPdf, setDownloadingPdf] = useState(false);
  const [shareBusy, setShareBusy] = useState(false);
  const [shareState, setShareState] = useState(null); // null → follow report doc; {token} local override
  const [videoFailed, setVideoFailed] = useState(false);  // graceful fallback when the uploaded clip can't be decoded on this device
  const pollingRef = useRef(null);
  // ── Timestamped video evidence ────────────────────────────────────
  // Clicking any "0:23"-style timestamp in the report scrubs the player
  // to that exact second and plays. Used by PillarCard's evidence lists
  // and the inline Video Moments card.
  const videoRef = useRef(null);
  const parseTimestamp = useCallback((ts) => {
    if (!ts) return null;
    const m = String(ts).match(/^\s*(\d{1,2}):(\d{2})(?:\.\d+)?\s*$/);
    if (!m) return null;
    const seconds = parseInt(m[1], 10) * 60 + parseInt(m[2], 10);
    return Number.isFinite(seconds) ? seconds : null;
  }, []);
  const seekVideoTo = useCallback((ts) => {
    const seconds = parseTimestamp(ts);
    const v = videoRef.current;
    if (seconds == null || !v) return false;
    try {
      // Scroll the video into view first so the user sees the moment land.
      v.scrollIntoView({ behavior: "smooth", block: "center" });
      const apply = () => {
        try { v.currentTime = seconds; } catch { /* ignore */ }
        const p = v.play();
        if (p && typeof p.catch === "function") p.catch(() => { /* autoplay block — leave paused */ });
      };
      if (v.readyState >= 1) apply();
      else {
        const once = () => { v.removeEventListener("loadedmetadata", once); apply(); };
        v.addEventListener("loadedmetadata", once);
        // safety fallback if metadata never fires
        setTimeout(apply, 1200);
      }
      return true;
    } catch {
      return false;
    }
  }, [parseTimestamp]);

  const fetchReport = useCallback(async () => {
    try {
      const [r, p] = await Promise.all([
        api.get(`/reports/${id}`),
        api.get("/settings/price"),
      ]);
      setReport(r.data);
      setPrice(Number(p.data.single_price) || p.data.price);
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Failed to load report");
      navigate("/dashboard");
    } finally {
      setLoading(false);
    }
  }, [id, navigate]);

  useEffect(() => { fetchReport(); }, [fetchReport]);

  // Stage 3 — surface the doubt-confirmation prompt when the report doc says
  // the tracker is waiting for the owner's answer (also covers page reloads).
  useEffect(() => {
    if (report?.doubt_status === "awaiting" && report?.doubt_moments?.length) {
      setDoubtInfo({ moments: report.doubt_moments });
    }
  }, [report?.doubt_status]); // eslint-disable-line react-hooks/exhaustive-deps

  const submitDoubt = async (taps, skip = false) => {
    setDoubtBusy(true);
    try {
      await api.post(`/reports/${id}/doubt-confirm`, { taps, skip });
      setDoubtInfo(null);
      toast.success(skip
        ? "Okay — the tracker decides on its own. Analysis continues."
        : "Player confirmed — tracking updated. Analysis continues.");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not submit — try again.");
    } finally {
      setDoubtBusy(false);
    }
  };

  // Marketing pixels: ViewContent once per report view (the "product page")
  const viewContentTrackedRef = useRef(false);
  useEffect(() => {
    if (report?.id && !viewContentTrackedRef.current) {
      viewContentTrackedRef.current = true;
      trackViewContent("scout_report");
    }
  }, [report?.id]);

  // Session 126 — Auto-generate the full scout dossier for premium tiers
  // (admin/premium/vip/scout) OR any report that's already paid/unlocked but
  // hasn't materialised the full_report yet. Was previously a manual button-
  // click flow (line 3138 "Report unlocked · Generate full report"). Premium
  // users should never see a "click to generate" prompt — the dossier just
  // renders. Guard against re-triggering with a ref so React StrictMode's
  // double-effect doesn't fire two Gemini jobs.
  const autoGenTriggeredRef = useRef(false);
  useEffect(() => {
    if (!report || generatingFull || autoGenTriggeredRef.current) return;
    const premiumRoleNow = isPremiumUser(user);
    const alreadyUnlocked = report.is_paid || report.manually_unlocked || premiumRoleNow;
    const needsFullReport = alreadyUnlocked && !report.full_report;
    // Don't auto-fire if the backend is already generating (e.g. right after
    // a successful checkout). The Stripe success path sets generatingFull.
    if (needsFullReport) {
      autoGenTriggeredRef.current = true;
      (async () => {
        setGeneratingFull(true);
        try {
          // Don't re-fire if the backend is already generating (e.g. right after
          // a successful checkout or a doubt-confirmation wait) — just poll.
          if (report.full_report_status !== "generating" && report.full_report_status !== "awaiting_confirmation") {
            await api.post(`/reports/${id}/generate-full`);
          }
          await pollFullReportReady();
          await fetchReport();
        } catch (err) {
          // Silent fail — the "OPEN FULL SCOUT DOSSIER" button below stays
          // available for a manual retry. No toast to avoid noise on mount.
          // eslint-disable-next-line no-console
          console.warn("Auto full-report generation failed:", err?.message);
        } finally {
          setGeneratingFull(false);
        }
      })();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [report, user]);

  // Auto-open the embedded checkout when ?unlock=1 (Hero Teaser navigates here with this param)
  /* eslint-disable */
  useEffect(() => {
    if (searchParams.get("unlock") === "1" && report && !report.is_paid && !report.manually_unlocked) {
      setEmbeddedOpen(true);
      const np = new URLSearchParams(searchParams);
      np.delete("unlock");
      setSearchParams(np, { replace: true });
    }
  }, [searchParams.get("unlock"), report]);
  /* eslint-enable */

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
          trackPurchase(price, "USD");
          setCheckoutModal({ open: true, state: "success", errorMessage: null });
          const np = new URLSearchParams(searchParams);
          np.delete("session_id");
          setSearchParams(np, { replace: true });
          await fetchReport();
          // trigger full report generation (async + polled — backend returns
          // immediately so we never hit Cloudflare's 100s edge timeout).
          setGeneratingFull(true);
          try {
            await api.post(`/reports/${id}/generate-full`);
            await pollFullReportReady();
            await fetchReport();
            toast.success("Full premium report ready");
          } catch (e) {
            toast.error(e?.message || e?.response?.data?.detail || "Failed to generate full report");
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
    // Trigger full report generation — backend now returns immediately and the
    // heavy Gemini work runs in a background task. We poll until ready so the
    // request never hits the Cloudflare 100s edge timeout.
    setGeneratingFull(true);
    try {
      await api.post(`/reports/${id}/generate-full`);
      await pollFullReportReady();
      await fetchReport();
      toast.success("Full premium report unlocked");
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Couldn't auto-generate full report. Click 'Regenerate' below.");
    } finally {
      setGeneratingFull(false);
    }
  };

  // Polls the report-status endpoint until the full report finishes generating
  // (or fails). Backend caps generation at ~5 min, we wait up to 7 min just in
  // case of slow Gemini responses, then surface a friendly toast either way.
  const pollFullReportReady = async () => {
    const start = Date.now();
    const HARD_TIMEOUT_MS = 7 * 60 * 1000;
    while (Date.now() - start < HARD_TIMEOUT_MS) {
      try {
        const { data } = await api.get(`/reports/${id}/status`);
        if (data?.doubt_status === "awaiting" && data?.doubt_moments?.length) {
          setDoubtInfo({ moments: data.doubt_moments });
        } else if (data?.doubt_status && data.doubt_status !== "awaiting") {
          setDoubtInfo(null);
        }
        if (data?.full_report_status === "ready" || data?.has_full_report) return data;
        if (data?.full_report_status === "failed") {
          throw new Error(data?.full_report_error || "Full report generation failed");
        }
      } catch (e) {
        if (e?.response?.status === 404) throw e;
        // transient network blips — keep polling
      }
      await new Promise((r) => setTimeout(r, 4500));
    }
    throw new Error("Full report is taking longer than usual. Please refresh the page in a minute.");
  };

  const handleGenerateFull = async () => {
    setGeneratingFull(true);
    try {
      await api.post(`/reports/${id}/generate-full`);
      await pollFullReportReady();
      await fetchReport();
      toast.success("Full report ready");
    } catch (err) {
      toast.error(err?.message || err?.response?.data?.detail || "Failed to generate full report");
    } finally {
      setGeneratingFull(false);
    }
  };

  const shareToken = shareState ? shareState.token : (report?.share_enabled ? report?.share_token : null);

  const handleShareReport = async () => {
    setShareBusy(true);
    try {
      const { data } = await api.post(`/reports/${id}/share`);
      const url = `${ASSET_BASE}${data.share_path}`;
      setShareState({ token: data.share_token });
      try {
        await navigator.clipboard.writeText(url);
        toast.success("Share link copied — anyone with the link can download the PDF");
      } catch {
        window.prompt("Copy the share link:", url);
      }
    } catch (err) {
      toast.error(String(err?.response?.data?.detail || "Could not create share link"));
    } finally {
      setShareBusy(false);
    }
  };

  const handleRevokeShare = async () => {
    try {
      await api.delete(`/reports/${id}/share`);
      setShareState({ token: null });
      toast.success("Share link disabled — old links no longer work");
    } catch {
      toast.error("Could not disable the link");
    }
  };

  const [cardBusy, setCardBusy] = useState(false);
  const handlePlayerCard = async () => {
    setCardBusy(true);
    try {
      const resp = await api.get(`/reports/${id}/player-card.png`, { responseType: "blob" });
      const fname = `ScoutMePlay_${(report?.player_details?.player_name || "player").replace(/\s+/g, "_")}_Card.png`;
      const file = new File([resp.data], fname, { type: "image/png" });
      if (navigator.canShare && navigator.canShare({ files: [file] })) {
        try {
          await navigator.share({ files: [file], title: "ScoutMePlay Player Card" });
        } catch (err) {
          if (err?.name !== "AbortError") throw err;
        }
      } else {
        const url = URL.createObjectURL(resp.data);
        const a = document.createElement("a");
        a.href = url;
        a.download = fname;
        a.click();
        URL.revokeObjectURL(url);
        toast.success("Player card downloaded — ready to share");
      }
    } catch {
      toast.error("Could not generate the player card");
    } finally {
      setCardBusy(false);
    }
  };

  const handleDownloadPdf = async () => {
    setDownloadingPdf(true);
    try {
      const res = await api.get(`/reports/${id}/pdf`, { responseType: "blob" });
      const blob = new Blob([res.data], { type: "application/pdf" });
      const url = window.URL.createObjectURL(blob);
      // Sanitise the filename — trailing dots + spaces make Chrome/Safari
      // strip the `.pdf` extension, which is what most "download does nothing"
      // reports are actually about.
      const raw = report?.player_details?.player_name || "report";
      const safe = String(raw).replace(/[^A-Za-z0-9À-ÿ]+/g, "_").replace(/_+$/, "") || "report";
      const filename = `EliteScout_${safe}_Report.pdf`;
      const link = document.createElement("a");
      link.href = url;
      link.download = filename;
      link.rel = "noopener";
      link.style.display = "none";
      // Anchor MUST be in the DOM for the click to trigger a download in
      // Chrome ≥91 + Safari + iOS webviews. This was the bug.
      document.body.appendChild(link);
      link.click();
      // Give the browser a beat to start reading the blob before we tear it
      // down. Firefox especially throws if the URL is revoked too early.
      setTimeout(() => {
        try { document.body.removeChild(link); } catch (_) {}
        window.URL.revokeObjectURL(url);
      }, 400);
    } catch (err) {
      const detail = err?.response?.data?.detail || err?.message || "PDF download failed";
      toast.error(String(detail));
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

  const { preview, full_report, player_details, video_url, poster_url, marker_url, fingerprint, is_paid, manually_unlocked, content_gate, trial_readiness, archetype, age_profile_reference, statsbomb_calibration, age_intelligence, statsbomb_calibration_gated_message, trial_readiness_gated_message } = report;
  const premiumRole = isPremiumUser(user);
  const unlocked = is_paid || manually_unlocked || premiumRole;

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
  const evidenceQualityNote = full_report?.evidence_quality_note;
  const couldNotAssess = full_report?.scout_view?.what_we_could_not_assess;

  // ===== Premium Report V2 — the pixel-perfect report design fully REPLACES
  // the old premium layout once the full dossier exists. Locked/free-preview
  // and "generating" states keep the original flow below. =====
  if (unlocked && full_report) {
    return (
      <div className="min-h-screen bg-[#F2EDE2] pb-16">
        <Navigation />
        <div className="pt-24 md:pt-28 px-4 md:px-8">
          <div className="max-w-[1440px] mx-auto mb-4 flex flex-wrap items-center gap-3">
            <button
              onClick={() => navigate("/dashboard")}
              data-testid="back-to-dashboard"
              className="flex items-center gap-2 text-[#12402A]/70 hover:text-[#12402A] uppercase tracking-widest text-xs font-bold transition-colors"
            >
              <ChevronLeft className="w-4 h-4" />
              Dashboard
            </button>
            <div className="ml-auto flex items-center gap-3">
              <button
                onClick={handlePlayerCard}
                disabled={cardBusy}
                data-testid="player-card-btn"
                className="bg-[#E8B32C] hover:bg-[#d9a418] text-[#12402A] font-barlow font-black uppercase tracking-widest text-xs px-5 py-2.5 transition-colors disabled:opacity-50 flex items-center gap-2 rounded"
              >
                {cardBusy ? <Loader2 className="w-4 h-4 animate-spin" /> : <IdCard className="w-4 h-4" />}
                Player card
              </button>
              <button
                onClick={handleShareReport}
                disabled={shareBusy}
                data-testid="share-report-btn"
                className="bg-white border border-[#12402A]/25 text-[#12402A] hover:bg-[#12402A]/5 font-barlow font-black uppercase tracking-widest text-xs px-5 py-2.5 transition-colors disabled:opacity-50 flex items-center gap-2 rounded"
              >
                {shareBusy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Share2 className="w-4 h-4" />}
                {shareToken ? "Copy share link" : "Share report"}
              </button>
              {shareToken && (
                <button
                  onClick={handleRevokeShare}
                  data-testid="disable-share-btn"
                  className="text-[#12402A]/55 hover:text-red-700 uppercase tracking-widest text-[10px] font-bold flex items-center gap-1 transition-colors"
                >
                  <Link2 className="w-3 h-3" /> Disable link
                </button>
              )}
              <button
                onClick={handleDownloadPdf}
                disabled={downloadingPdf}
                data-testid="download-pdf-btn"
                className="bg-[#12402A] hover:bg-[#1E5B3C] text-white font-barlow font-black uppercase tracking-widest text-xs px-5 py-2.5 transition-colors disabled:opacity-50 flex items-center gap-2 rounded"
              >
                {downloadingPdf ? <Loader2 className="w-4 h-4 animate-spin" /> : <Download className="w-4 h-4" />}
                Download PDF
              </button>
            </div>
          </div>
          <PremiumReportV2 report={report} assetBase={ASSET_BASE} />
          <div className="max-w-[1440px] mx-auto mt-6">
            <ScoutReview reportId={id} />
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-deepnavy text-ink pb-20">
      <Navigation />
      {doubtInfo && (
        <DoubtConfirmModal
          moments={doubtInfo.moments}
          busy={doubtBusy}
          onConfirm={(taps) => submitDoubt(taps, false)}
          onSkip={() => submitDoubt([], true)}
        />
      )}
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

          {/* Session 130 — Dedicated Premium Ready banner. Rendered ONLY for
              unlocked/premium users (admin/premium/vip/scout OR is_paid/manually_unlocked).
              Free users never see this — they get the blur + PricingCards flow below. */}
          {unlocked && (
            <PremiumReadyBanner
              playerName={player_details?.player_name}
              onOpenReport={() => {
                const target = document.querySelector('[data-testid="report-scores-grid"]');
                if (target) {
                  target.scrollIntoView({ behavior: "smooth", block: "start" });
                } else {
                  window.scrollTo({ top: window.innerHeight * 0.5, behavior: "smooth" });
                }
              }}
            />
          )}

          {/* ===== Header ===== */}
          <div className="mt-6 grid lg:grid-cols-5 gap-px bg-cream-soft/40 border border-gray-border">
            <div className="bg-surface p-6 md:p-8 lg:col-span-2">
              {report.demo ? (
                <div className="relative w-full bg-deepnavy border border-volt/20 aspect-video flex flex-col items-center justify-center text-center p-6 overflow-hidden">
                  <div className="absolute top-3 right-3 bg-volt text-white text-[10px] uppercase tracking-widest font-black px-2 py-1">Demo</div>
                  {/* Photo-free chalk-pitch decoration — no stock player imagery */}
                  <div aria-hidden className="absolute inset-0 opacity-[0.08]" style={{
                    backgroundImage: "repeating-linear-gradient(45deg, #CCFF00 0 1px, transparent 1px 24px)",
                  }} />
                  <div aria-hidden className="absolute -bottom-16 -right-16 w-56 h-56 rounded-full bg-volt/20 blur-3xl pointer-events-none" />
                  <div className="relative">
                    <div className="font-barlow font-black uppercase text-3xl text-volt">Sample report</div>
                    <p className="mt-2 text-sm text-ink/70 max-w-sm">
                      This is a demo report so you can explore the premium experience. Upload your own video to get a real analysis.
                    </p>
                  </div>
                </div>
              ) : (
                <div className="relative" data-testid="report-video-frame">
                  {/* MATCH FOOTAGE header strip — sits flush above the clip and
                      gives the embed broadcast-style chrome instead of looking
                      like a bare HTML5 video. */}
                  <div className="flex items-center justify-between bg-forest text-cream-card px-3 py-1.5 border border-forest">
                    <div className="flex items-center gap-2">
                      <span className="relative flex w-1.5 h-1.5">
                        <span className="absolute inset-0 rounded-full bg-[#CCFF00] animate-ping opacity-75" />
                        <span className="relative rounded-full w-1.5 h-1.5 bg-[#CCFF00]" />
                      </span>
                      <span className="text-[9.5px] uppercase tracking-[0.28em] font-black">Match footage · analysed</span>
                    </div>
                    <span className="text-[9.5px] uppercase tracking-[0.2em] font-black text-cream-card/70 tabular-nums">
                      30s clip
                    </span>
                  </div>
                  <div className="relative w-full bg-black aspect-video overflow-hidden border-x border-b-2 border-forest" data-testid="report-video-shell">
                    {!videoFailed && (
                      <video
                        ref={videoRef}
                        src={`${ASSET_BASE}${video_url}`}
                        poster={poster_url ? `${ASSET_BASE}${poster_url}` : (marker_url ? `${ASSET_BASE}${marker_url}` : undefined)}
                        controls
                        playsInline
                        preload="metadata"
                        onError={() => setVideoFailed(true)}
                        data-testid="report-video"
                        className="absolute inset-0 w-full h-full object-cover"
                      />
                    )}
                    {/* Premium broadcast corner brackets — fully decorative; the
                        controls remain clickable because the corner divs are tiny. */}
                    <span aria-hidden className="absolute top-1.5 left-1.5 w-3 h-3 border-l-2 border-t-2 border-volt/80" />
                    <span aria-hidden className="absolute top-1.5 right-1.5 w-3 h-3 border-r-2 border-t-2 border-volt/80" />
                    <span aria-hidden className="absolute bottom-1.5 left-1.5 w-3 h-3 border-l-2 border-b-2 border-volt/80" />
                    <span aria-hidden className="absolute bottom-1.5 right-1.5 w-3 h-3 border-r-2 border-b-2 border-volt/80" />
                    {/* Friendly fallback if the uploaded clip can't be decoded on this device (iOS HEVC etc.) */}
                    {videoFailed && (
                      <div className="absolute inset-0 flex flex-col items-center justify-center text-center px-6" data-testid="report-video-fallback">
                        {marker_url && (
                          <img
                            src={`${ASSET_BASE}${marker_url}`}
                            alt=""
                            className="absolute inset-0 w-full h-full object-cover opacity-60"
                            aria-hidden
                          />
                        )}
                        <div className="absolute inset-0 bg-gradient-to-t from-cream-base via-cream-base/85 to-cream-base/40" />
                        <div className="relative">
                          <div className="text-forest text-[10px] uppercase tracking-[0.3em] font-black mb-1">Video preview unavailable on this device</div>
                          <p className="text-ink/65 text-xs max-w-[260px] mx-auto">
                            Your clip was analysed successfully — the locked-player frame and full report are below.
                          </p>
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              )}
              {/* ===== Match-stat scoreboard =====
                  Replaces the old flat 3-cell Type/Foot/Age strip with a TV-broadcast
                  scoreboard-style display: a dark ink banner with monospace stats and
                  vertical separators. Feels like a match-info ticker instead of a
                  generic 3-column data table. */}
              <div className="mt-4 grid grid-cols-3 bg-ink text-cream-card border border-forest/60 divide-x divide-cream-card/15 overflow-hidden">
                <div className="px-2 py-2 text-center">
                  <div className="text-[8.5px] uppercase tracking-[0.22em] text-cream-card/55 font-bold leading-tight">Type</div>
                  <div className="font-barlow font-black uppercase text-base text-volt mt-0.5 tracking-tight">{player_details.video_type}</div>
                </div>
                <div className="px-2 py-2 text-center">
                  <div className="text-[8.5px] uppercase tracking-[0.22em] text-cream-card/55 font-bold leading-tight">Foot</div>
                  <div className="font-barlow font-black uppercase text-base text-volt mt-0.5 tracking-tight">{player_details.preferred_foot}</div>
                </div>
                <div className="px-2 py-2 text-center">
                  <div className="text-[8.5px] uppercase tracking-[0.22em] text-cream-card/55 font-bold leading-tight">Age</div>
                  <div className="font-barlow font-black uppercase text-base text-volt mt-0.5 tabular-nums tracking-tight">{player_details.age}</div>
                </div>
              </div>
            </div>

            <div className="bg-surface p-6 md:p-8 lg:col-span-3 flex flex-col justify-between">
              <div>
                <div className="flex items-center gap-2.5">
                  <PitchLineDivider className="w-10 h-2 text-volt/55" />
                  <span className="text-volt text-xs uppercase tracking-[0.25em] font-bold">{unlocked ? "Premium report" : "Free preview"}</span>
                </div>
                <h1
                  data-testid="report-player-name"
                  className="mt-3 font-barlow font-black uppercase text-4xl md:text-6xl tracking-tighter leading-[0.95]"
                >
                  {player_details.player_name}
                </h1>
                <div className="mt-3 flex items-center gap-3">
                  <MiniPitch position={player_details.position} className="w-7 h-10 flex-shrink-0" />
                  <p className="text-ink/65 text-sm md:text-base">
                    {player_details.position} · {player_details.current_club || "Independent"}
                  </p>
                </div>

                {/* ===== Premium scout badges row =====
                    Compact pills that surface key player-profile facts at a glance —
                    foot, age and selected archetype. Uses existing data only. */}
                <div className="mt-5 flex flex-wrap gap-2" data-testid="report-scout-badges">
                  {player_details.preferred_foot && (
                    <span className="inline-flex items-center gap-1.5 bg-cream-card border border-forest/20 px-2.5 py-1 rounded-sm text-[10px] uppercase tracking-[0.18em] font-black text-forest">
                      <svg viewBox="0 0 24 24" className="w-3 h-3" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
                        <path d="M8 4 L12 4 L13 16 L8 16 Z M9 18 L9 22 L12 22 L12 18 Z" />
                      </svg>
                      {player_details.preferred_foot} foot
                    </span>
                  )}
                  {player_details.age && (
                    <span className="inline-flex items-center gap-1.5 bg-cream-card border border-forest/20 px-2.5 py-1 rounded-sm text-[10px] uppercase tracking-[0.18em] font-black text-forest">
                      <svg viewBox="0 0 24 24" className="w-3 h-3" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
                        <circle cx="12" cy="12" r="9" />
                        <path d="M12 7 L12 12 L15 14" />
                      </svg>
                      Age {player_details.age}
                    </span>
                  )}
                  {player_details.video_type && (
                    <span className="inline-flex items-center gap-1.5 bg-cream-card border border-forest/20 px-2.5 py-1 rounded-sm text-[10px] uppercase tracking-[0.18em] font-black text-forest">
                      <FootballIcon className="w-3 h-3" />
                      {String(player_details.video_type).replace(/^./, c => c.toUpperCase())}
                    </span>
                  )}
                  {(full_report?.player_type || preview?.player_type) && (
                    <span className="inline-flex items-center gap-1.5 bg-forest text-cream-card border border-forest px-2.5 py-1 rounded-sm text-[10px] uppercase tracking-[0.18em] font-black">
                      <FootballIcon className="w-3 h-3" />
                      Archetype
                    </span>
                  )}
                </div>

                <div className="mt-4 inline-flex items-center gap-2 bg-deepnavy border border-volt/30 px-4 py-2">
                  <FootballIcon className="w-4 h-4 text-volt" />
                  <span className="font-barlow font-bold uppercase text-sm" data-testid="report-player-type">
                    {(full_report?.player_type) || preview?.player_type || "Player Analysis"}
                  </span>
                </div>

                {marker_url && (
                  <div className="mt-5 border border-forest/30 bg-cream-card/90 p-3 max-w-md shadow-sm" data-testid="marker-card">
                    <div className="flex items-center justify-between gap-2 mb-2">
                      <div className="flex items-center gap-2">
                        <FootballIcon className="w-3.5 h-3.5 text-forest" />
                        <span className="text-[10px] uppercase tracking-[0.22em] font-black text-forest">Your player · tracked</span>
                      </div>
                      <span className="inline-flex items-center gap-1 px-1.5 py-0.5 bg-[#CCFF00] text-ink text-[8px] uppercase tracking-[0.18em] font-black rounded-sm">
                        <span className="w-1 h-1 rounded-full bg-ink" /> Auto-lock
                      </span>
                    </div>
                    <div className="relative w-full aspect-video border border-forest/25 overflow-hidden bg-ink">
                      {/* Canvas-based renderer guarantees the lime box
                          lands on the same pixels the zoomed crop below
                          already shows correctly — no CSS aspect-ratio
                          drift, no EXIF rotation surprises. */}
                      <FullFrameWithBoxCanvas
                        frameDataUrl={`${ASSET_BASE}${marker_url}`}
                        box={fingerprint?.box && typeof fingerprint.box.x === "number" ? fingerprint.box : null}
                        className="w-full h-full"
                      />
                    </div>
                    {/* Pixel-perfect cropped close-up so the user can SEE who is
                        being tracked — proves the box is on the right player. */}
                    {fingerprint?.box && typeof fingerprint.box.x === "number" && (
                      <div className="mt-2 flex items-center gap-2 bg-cream-soft/70 border border-forest/15 p-2 rounded-sm" data-testid="locked-player-zoom">
                        <div className="relative w-20 h-20 flex-shrink-0 overflow-hidden border-2 border-[#CCFF00] shadow-[0_0_8px_rgba(204,255,0,0.4)] bg-ink">
                          <MarkedCropCanvas
                            frameDataUrl={`${ASSET_BASE}${marker_url}`}
                            box={fingerprint.box}
                            className="absolute inset-0 w-full h-full"
                          />
                        </div>
                        <div className="min-w-0">
                          <div className="text-[9px] uppercase tracking-[0.22em] font-black text-forest">Zoomed crop</div>
                          <div className="text-[11px] text-ink/70 leading-snug">This is the exact pixel region every observation in this report refers to.</div>
                        </div>
                      </div>
                    )}
                    {fingerprint && (fingerprint.jersey_name || fingerprint.shorts_name) && (
                      <div className="mt-2.5 flex flex-wrap items-center gap-1.5" data-testid="player-fingerprint">
                        {fingerprint.jersey_hex && (
                          <span className="inline-flex items-center gap-1.5 border border-forest/20 bg-cream-card px-2 py-1 text-[10px] uppercase tracking-widest font-bold text-ink/75">
                            <span
                              className="w-3 h-3 inline-block border border-ink/20 rounded-sm"
                              style={{ background: fingerprint.jersey_hex }}
                            />
                            {fingerprint.jersey_name || "jersey"}
                          </span>
                        )}
                        {fingerprint.shorts_hex && (
                          <span className="inline-flex items-center gap-1.5 border border-forest/20 bg-cream-card px-2 py-1 text-[10px] uppercase tracking-widest font-bold text-ink/75">
                            <span
                              className="w-3 h-3 inline-block border border-ink/20 rounded-sm"
                              style={{ background: fingerprint.shorts_hex }}
                            />
                            {fingerprint.shorts_name || "shorts"}
                          </span>
                        )}
                      </div>
                    )}
                    <p className="mt-2.5 text-[11px] text-ink/60 leading-snug">
                      Every note in this report is about the player inside the lime box &mdash; no one else.
                    </p>
                  </div>
                )}

                {/* ===== FREE-PREVIEW content block (non-unlocked users) =====
                    The HeroTeaser overlay right after upload is the FULL reveal —
                    we don't want to duplicate the same wall of text here. Instead,
                    the dashboard view shows a TEASING short snippet + blurred /
                    locked stubs that drive the user to the unlock CTA. */}
                {!unlocked && preview && (
                  <div className="mt-6 space-y-4" data-testid="free-preview-content">
                    {(preview.brief_summary || preview.summary) && (() => {
                      const full = preview.brief_summary || preview.summary;
                      const teaser = String(full).slice(0, 90).replace(/\s+\S*$/, "");
                      const hasMore = String(full).length > teaser.length;
                      return (
                        <div className="relative bg-cream-card border border-gray-border p-4 md:p-5 rounded-sm shadow-sm overflow-hidden">
                          <p className="text-ink/45 text-[10px] uppercase tracking-[0.3em] font-bold mb-2">
                            What the scout saw — preview
                          </p>
                          <p className="text-ink text-sm md:text-base leading-relaxed">
                            {teaser}
                            {hasMore && (
                              <>
                                <span aria-hidden className="text-ink/85">…</span>
                                {/* Blurred fake continuation so the user feels the cut-off */}
                                <span
                                  aria-hidden
                                  className="ml-1 text-ink/55 select-none"
                                  style={{ filter: "blur(5px)" }}
                                >
                                  the rest of the scout&apos;s observation is unlocked in the full report
                                </span>
                              </>
                            )}
                          </p>
                          {hasMore && (
                            <div className="mt-3 inline-flex items-center gap-1.5 text-forest text-[10px] uppercase tracking-[0.25em] font-black">
                              <Lock className="w-3 h-3" />
                              Unlock to read the full breakdown
                            </div>
                          )}
                        </div>
                      );
                    })()}

                    {Array.isArray(preview.top_strengths) && preview.top_strengths.length > 0 && (
                      <div className="bg-cream-soft/70 border border-forest/15 p-4 md:p-5 rounded-sm">
                        <p className="text-forest text-[10px] uppercase tracking-[0.3em] font-black mb-3 flex items-center gap-1.5">
                          <FootballIcon className="w-3.5 h-3.5" />
                          1 of 3 top strengths revealed
                        </p>
                        <ul className="space-y-2.5">
                          {/* Only the FIRST strength is shown — the other two are
                              blurred so the user sees there's more behind the unlock. */}
                          {preview.top_strengths.slice(0, 1).map((s, i) => (
                            <li key={i} className="flex items-start gap-2.5 text-ink text-[13px] md:text-sm leading-snug">
                              <JerseyChip number={i + 1} className="w-6 h-6 flex-shrink-0" />
                              <span className="font-semibold mt-0.5">{s}</span>
                            </li>
                          ))}
                          {preview.top_strengths.slice(1, 3).map((s, i) => (
                            <li
                              key={`lock-${i}`}
                              className="flex items-start gap-2.5 text-ink/65 text-[13px] md:text-sm leading-snug select-none"
                              style={{ filter: "blur(4px)" }}
                              aria-hidden
                            >
                              <JerseyChip number={i + 2} muted className="w-6 h-6 flex-shrink-0" />
                              <span className="font-semibold mt-0.5">{s}</span>
                            </li>
                          ))}
                        </ul>
                        {preview.top_strengths.length > 1 && (
                          <p className="mt-3 inline-flex items-center gap-1.5 text-forest text-[10px] uppercase tracking-[0.25em] font-black">
                            <Lock className="w-3 h-3" />
                            Unlock to reveal {preview.top_strengths.length - 1} more
                          </p>
                        )}
                      </div>
                    )}

                    {/* "One area to improve" + evidence note moved BEHIND the paywall
                        — these are real observations and should drive the purchase. */}
                    {preview.area_for_improvement && (
                      <div className="relative bg-cream-card border border-gray-border p-3 md:p-4 rounded-sm overflow-hidden">
                        <p className="text-ink/45 text-[10px] uppercase tracking-[0.3em] font-bold mb-1 flex items-center gap-1.5">
                          <Lock className="w-3 h-3 text-forest" />
                          One area to improve · locked
                        </p>
                        <p
                          className="text-ink/85 text-[13px] leading-snug select-none"
                          style={{ filter: "blur(5px)" }}
                          aria-hidden
                        >
                          {preview.area_for_improvement}
                        </p>
                      </div>
                    )}
                  </div>
                )}
              </div>

              {unlocked && full_report && (
                <div className="mt-8 grid grid-cols-2 md:grid-cols-5 gap-px bg-cream-soft/40 border border-gray-border" data-testid="report-scores-grid">
                  {[
                    { key: "technical", label: "Technical", v: full_report.scores?.technical, pillar: "technical" },
                    { key: "tactical", label: "Tactical", v: full_report.scores?.tactical, pillar: "tactical" },
                    { key: "physical", label: "Physical", v: full_report.scores?.physical, pillar: "physical" },
                    { key: "mentality", label: "Mentality", v: full_report.scores?.mentality, pillar: "mindset" },
                    { key: "overall_development", label: "Overall", v: full_report.scores?.overall_development, pillar: null },
                  ].map((s, i) => {
                    const pct = typeof s.v === "number" ? Math.max(0, Math.min(100, (s.v / 10) * 100)) : 0;
                    const barColor = (s.v ?? 0) >= 8 ? "bg-forest-pop" : (s.v ?? 0) >= 6 ? "bg-volt" : (s.v ?? 0) >= 4 ? "bg-amber-500" : "bg-rose-500";
                    return (
                      <div key={i} className="bg-surface p-3 text-center flex flex-col items-center justify-between">
                        <div className="flex items-center gap-1.5 justify-center">
                          {s.pillar && (
                            <PillarIcon kind={s.pillar} className="w-3.5 h-3.5 text-forest/70 hidden sm:inline-flex" />
                          )}
                          <div className="text-[9.5px] md:text-[10px] uppercase tracking-[0.14em] text-ink/55 font-bold leading-tight">
                            {s.label}
                          </div>
                        </div>
                        <div className="mt-1.5">
                          <AnimatedScore
                            value={s.v ?? 0}
                            max={10}
                            colorClass={scoreColor(s.v)}
                            className="font-barlow font-black text-3xl leading-none tabular-nums"
                            testid={`overall-score-${s.key}`}
                          />
                        </div>
                        {/* Mini progress bar visualises the rating at a glance —
                            colour matches the score band (red < 4 / amber 4-5 / volt 6-7 / forest-pop 8+). */}
                        <div className="mt-2 w-full h-1 bg-ink/8 rounded-full overflow-hidden">
                          <div className={`h-full ${barColor} rounded-full transition-all duration-500`} style={{ width: `${pct}%` }} />
                        </div>
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

                  {/* ===== Social share toolbar ===== */}
                  <div className="flex items-center gap-2 ml-auto" data-testid="report-share-toolbar">
                    <span className="hidden md:inline text-[10px] uppercase tracking-[0.22em] font-bold text-ink/55 mr-1">Share</span>
                    <a
                      href={`https://wa.me/?text=${encodeURIComponent(`Check out ${player_details?.player_name || "this"} scouting report on ScoutMePlay: ${typeof window !== "undefined" ? window.location.href : ""}`)}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      data-testid="share-whatsapp-btn"
                      title="Share on WhatsApp"
                      className="w-10 h-10 flex items-center justify-center text-forest border-2 border-forest hover:bg-forest hover:text-cream-card transition-colors"
                    >
                      <svg className="w-4 h-4" viewBox="0 0 24 24" fill="currentColor"><path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51l-.57-.01c-.198 0-.52.074-.792.372s-1.04 1.016-1.04 2.479 1.065 2.876 1.213 3.074c.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.890-5.335 11.893-11.893a11.821 11.821 0 00-3.48-8.413Z"/></svg>
                    </a>
                    <a
                      href={`https://twitter.com/intent/tweet?text=${encodeURIComponent(`${player_details?.player_name || "Check out this"} scouting report — ScoutMePlay`)}&url=${encodeURIComponent(typeof window !== "undefined" ? window.location.href : "")}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      data-testid="share-twitter-btn"
                      title="Share on X (Twitter)"
                      className="w-10 h-10 flex items-center justify-center text-forest border-2 border-forest hover:bg-forest hover:text-cream-card transition-colors"
                    >
                      <svg className="w-4 h-4" viewBox="0 0 24 24" fill="currentColor"><path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z"/></svg>
                    </a>
                    <a
                      href={`mailto:?subject=${encodeURIComponent(`${player_details?.player_name || "Scouting"} report from ScoutMePlay`)}&body=${encodeURIComponent(`Take a look at this scouting report:\n\n${typeof window !== "undefined" ? window.location.href : ""}`)}`}
                      data-testid="share-email-btn"
                      title="Share by email"
                      className="w-10 h-10 flex items-center justify-center text-forest border-2 border-forest hover:bg-forest hover:text-cream-card transition-colors"
                    >
                      <Mail className="w-4 h-4" />
                    </a>
                    <button
                      type="button"
                      onClick={() => {
                        if (typeof window !== "undefined" && navigator?.clipboard) {
                          navigator.clipboard.writeText(window.location.href).then(
                            () => toast.success("Link copied"),
                            () => toast.error("Couldn't copy link")
                          );
                        }
                      }}
                      data-testid="share-copy-btn"
                      title="Copy link"
                      className="w-10 h-10 flex items-center justify-center text-forest border-2 border-forest hover:bg-forest hover:text-cream-card transition-colors"
                    >
                      <Link2 className="w-4 h-4" />
                    </button>
                  </div>
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
          {unlocked && full_report && (
            <ReportChapterNav
              chapters={[
                { id: "report-executive", num: "01", label: "Summary" },
                { id: "report-technical-analysis", num: "02", label: "Technical" },
                { id: "report-tactical-analysis", num: "03", label: "Tactical" },
                { id: "report-physical-analysis", num: "04", label: "Physical" },
                { id: "report-mindset", num: "05", label: "Mindset" },
                { id: "report-video-moments", num: "06", label: "Moments" },
                { id: "report-final-summary", num: "07", label: "Final" },
              ]}
            />
          )}
          <div className="mt-10 relative">
            {!unlocked && (
              <LockedOverlay isLoggedIn={!!user} onUnlockSingle={() => setEmbeddedOpen(true)} />
            )}

            <div className={`${!unlocked ? "blur-locked" : ""} space-y-6`} data-testid="premium-content">
              {/* Chapter opener — moody Nano Banana chalk-touchline background,
                  NO people, only objects. Ensures clarity about who the report is about. */}
              {(unlocked && full_report) && (
                <div
                  data-testid="report-hero-divider"
                  className="relative w-full overflow-hidden bg-ink border border-gray-border py-10 md:py-14"
                >
                  {/* Nano Banana — chalk touchline on wet night grass (no people) */}
                  <img
                    src={`${process.env.REACT_APP_BACKEND_URL}/api/static/landing/bg-scout-hero.png`}
                    alt=""
                    aria-hidden
                    loading="lazy"
                    onError={(e) => { e.currentTarget.style.display = "none"; }}
                    className="absolute inset-0 w-full h-full object-cover opacity-55 scale-105"
                  />
                  {/* Layered overlays — ensure text stays readable while the
                      texture shows through cinematically. */}
                  <div aria-hidden className="absolute inset-0 bg-gradient-to-r from-ink/95 via-ink/75 to-ink/30" />
                  <div aria-hidden className="absolute inset-0 bg-gradient-to-b from-ink/40 via-transparent to-ink/60" />
                  {/* Chalk pitch decorations — subtle, non-distracting */}
                  <div aria-hidden className="absolute inset-y-0 left-0 w-1 bg-volt/70" />
                  <div aria-hidden className="absolute -top-24 -right-24 w-64 h-64 rounded-full bg-forest/40 blur-3xl pointer-events-none" />
                  <div aria-hidden className="absolute bottom-0 left-1/3 right-0 h-px bg-gradient-to-r from-transparent via-volt/40 to-transparent" />
                  {/* Repeating chalk-line pattern top edge */}
                  <div aria-hidden className="absolute top-0 left-0 right-0 h-px bg-cream-base/10" />

                  <div className="relative px-6 md:px-12 max-w-4xl">
                    <div className="inline-flex items-center gap-2 mb-3">
                      <span className="w-8 h-px bg-volt" />
                      <span className="text-volt text-[10px] md:text-[11px] uppercase tracking-[0.32em] font-black">
                        Your full scout report
                      </span>
                    </div>
                    <h2 className="font-barlow font-black uppercase tracking-tighter text-4xl md:text-6xl text-cream-base leading-[0.9]">
                      Through<br />
                      <span className="text-volt">a scout&apos;s eyes.</span>
                    </h2>
                    <p className="mt-4 text-cream-base/80 text-sm md:text-base max-w-lg leading-relaxed">
                      Honest, age-appropriate notes &mdash; what stood out, what to work on, and how to grow next.
                    </p>
                    <div className="mt-5 flex items-center gap-4 text-[9px] uppercase tracking-[0.28em] font-bold text-cream-base/55">
                      <span>· Chapters 01 → 08 ·</span>
                      <span className="hidden sm:inline">Every note anchored to the video</span>
                    </div>
                  </div>
                </div>
              )}

              {/* Scout's Summary */}
              {(unlocked && full_report) && (
                <div className="bg-surface border border-gray-border p-6 md:p-8 scroll-mt-20" id="report-executive">
                  <div className="flex items-center gap-2 mb-2">
                    <PitchLineDivider className="w-10 h-2 text-forest/55" />
                    <span className="text-[9px] uppercase tracking-[0.32em] font-black text-forest">Chapter · 01</span>
                  </div>
                  <h3 className="font-barlow font-black uppercase text-2xl md:text-3xl text-ink">Scout&apos;s Summary</h3>
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
                  {/* Age Stage banner — top-of-report stage indicator */}
                  <AgeStageBanner age_intelligence={age_intelligence} />

                  {/* Age-appropriate evaluation disclaimer */}
                  <AgeAppropriateEvaluationDisclaimer age_intelligence={age_intelligence} />

                  {/* Overall benchmark hero — places the player on the age+position tier landscape */}
                  <OverallBenchmarkBanner
                    ob={full_report.overall_benchmark}
                    overallScore={full_report.scores?.overall_development}
                  />

                  {/* Age Intelligence Scoreboard — the 9 deterministic scores */}
                  <AgeIntelligenceScoreboard
                    age_intelligence={age_intelligence}
                    position_hint={player_details?.position}
                  />

                  {/* What we evaluated · what we deliberately did not */}
                  <WhatWeEvaluatedBlock age_intelligence={age_intelligence} />

                  {/* Stylistic archetype — public, style-only comparison */}
                  <ArchetypeCard archetype={archetype} />

                  {/* 5-Lens twins strip — ALWAYS renders. The FIFA lens is auto-removed
                      from archetype.lenses for U6-U11 by the backend stage-gating, so it
                      naturally falls back to a 4-lens display at those ages. */}
                  <ClosestMatchesStrip archetype={archetype} />

                  {/* FIFA Data Twin — top-5 real k-NN. Backend strips fifa_neighbors for
                      U6-U11 and attaches a friendly stage-gated message instead. */}
                  {archetype?.fifa_neighbors && archetype.fifa_neighbors.length > 0 ? (
                    <FifaDataTwinPanel archetype={archetype} />
                  ) : (
                    <StageGatedPanel
                      title="FIFA Data Twin · senior-pro reference"
                      message={archetype?.fifa_panel_gated_message}
                      testId="fifa-data-twin-gated"
                    />
                  )}

                  {/* StatsBomb Pro Calibration — gated for U6-U11. */}
                  {statsbomb_calibration ? (
                    <StatsBombCalibrationPanel calibration={statsbomb_calibration} />
                  ) : (
                    <StageGatedPanel
                      title="Pro Calibration · StatsBomb Euro 2024"
                      message={statsbomb_calibration_gated_message}
                      testId="statsbomb-calibration-gated"
                    />
                  )}

                  {/* Full skill picture — parent-friendly grouped breakdown with video links */}
                  <SkillsBreakdown
                    fullReport={full_report}
                    videoComments={full_report.video_comments || []}
                    onSeek={seekVideoTo}
                    ageProfile={age_profile_reference}
                    scoreContext={report.score_context}
                  />

                  {/* Performance Radar — cinematic dark centrepiece (custom SVG + Nano Banana bg) */}
                  {radarData && (
                    <>
                      {/* PINNED TOP-3 CARDS — Session 123 P1
                          Two compact cards immediately above the radar showing
                          the top-3 strengths (green) and top-3 development
                          priorities (amber). Full lists still shown in the
                          Scout View block further down; these cards are the
                          "at-a-glance" verdict for the parent/player. */}
                      {full_report.scout_view && (
                        (full_report.scout_view.key_strengths?.length ||
                         full_report.scout_view.development_priorities?.length ||
                         full_report.scout_view.areas_of_concern?.length) && (
                          <div
                            className="grid md:grid-cols-2 gap-4 mb-6"
                            data-testid="report-pinned-top3-cards"
                          >
                            {/* Card 1 — Top 3 Styrker */}
                            <div
                              className="relative bg-surface border-l-4 border-l-emerald-400 border border-gray-border p-5"
                              data-testid="report-pinned-strengths"
                            >
                              <div className="flex items-center gap-2 mb-3">
                                <Zap className="w-4 h-4 text-emerald-400" />
                                <div className="text-[10px] uppercase tracking-[0.24em] font-bold text-emerald-400">
                                  Top 3 Styrker
                                </div>
                              </div>
                              <ul className="space-y-2.5 text-sm text-ink/85">
                                {(full_report.scout_view.key_strengths || [])
                                  .slice(0, 3)
                                  .map((s, i) => (
                                    <li
                                      key={i}
                                      className="flex gap-2 leading-snug"
                                      data-testid={`pinned-strength-${i}`}
                                    >
                                      <span className="text-emerald-400 mt-0.5 flex-shrink-0">✓</span>
                                      <span>{s}</span>
                                    </li>
                                  ))}
                                {(!full_report.scout_view.key_strengths ||
                                  full_report.scout_view.key_strengths.length === 0) && (
                                  <li className="text-ink/40 italic">Ingen styrker registreret endnu</li>
                                )}
                              </ul>
                            </div>

                            {/* Card 2 — Top 3 Fokusområder (development priorities first, fall back to areas_of_concern) */}
                            <div
                              className="relative bg-surface border-l-4 border-l-amber-400 border border-gray-border p-5"
                              data-testid="report-pinned-focus"
                            >
                              <div className="flex items-center gap-2 mb-3">
                                <Target className="w-4 h-4 text-amber-400" />
                                <div className="text-[10px] uppercase tracking-[0.24em] font-bold text-amber-400">
                                  Top 3 Fokusområder
                                </div>
                              </div>
                              <ul className="space-y-2.5 text-sm text-ink/85">
                                {(
                                  (full_report.scout_view.development_priorities?.length
                                    ? full_report.scout_view.development_priorities
                                    : full_report.scout_view.areas_of_concern) || []
                                )
                                  .slice(0, 3)
                                  .map((s, i) => (
                                    <li
                                      key={i}
                                      className="flex gap-2 leading-snug"
                                      data-testid={`pinned-focus-${i}`}
                                    >
                                      <span className="text-amber-400 mt-0.5 flex-shrink-0">→</span>
                                      <span>{s}</span>
                                    </li>
                                  ))}
                                {!(
                                  full_report.scout_view.development_priorities?.length ||
                                  full_report.scout_view.areas_of_concern?.length
                                ) && (
                                  <li className="text-ink/40 italic">Ingen fokusområder registreret endnu</li>
                                )}
                              </ul>
                            </div>
                          </div>
                        )
                      )}

                      <PerformanceRadarHero
                        scores={full_report.scores}
                        bgSrc={`${process.env.REACT_APP_BACKEND_URL}/api/static/landing/bg-radar-tactics.png`}
                      />
                    </>
                  )}

                  <SectionGrid
                    title="Technical"
                    sub="Ball, dribbling, passing, shooting"
                    section={full_report.technical}
                    onSeek={seekVideoTo}
                    chapter="Chapter · 02 · Technical"
                  />
                  <SectionGrid
                    title="Tactical"
                    sub="Scanning, decisions, positioning"
                    section={full_report.tactical}
                    onSeek={seekVideoTo}
                    chapter="Chapter · 03 · Tactical"
                  />
                  <SectionGrid
                    title="Physical"
                    sub="Speed, balance, agility, stamina"
                    section={full_report.physical}
                    onSeek={seekVideoTo}
                    chapter="Chapter · 04 · Physical"
                  />
                  <SectionGrid
                    title="Mindset"
                    sub="Confidence, courage, focus, body language"
                    section={full_report.mentality}
                    onSeek={seekVideoTo}
                    chapter="Chapter · 05 · Mindset"
                  />

                  {/* European Academy reference profile — position priorities vs Pro Academy expectations */}
                  <AgeProfileCard ref={age_profile_reference} />

                  {/* Trial-readiness checklist — position-specific, scout-style.
                      Gated to U12+; backend nulls it for U6-U11 with a friendly message. */}
                  {trial_readiness ? (
                    <TrialReadinessCard tr={trial_readiness} />
                  ) : (
                    <StageGatedPanel
                      title="Trial readiness · scout checklist"
                      message={trial_readiness_gated_message}
                      testId="trial-readiness-gated"
                    />
                  )}

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
                    <div data-testid="video-moments-card" id="report-video-moments" className="bg-surface border border-gray-border p-6 md:p-8 scroll-mt-20">
                      <div className="flex items-center gap-2 mb-2">
                        <PitchLineDivider className="w-10 h-2 text-forest/55" />
                        <span className="text-[9px] uppercase tracking-[0.32em] font-black text-forest">Chapter · 06</span>
                      </div>
                      <div className="text-[10px] uppercase tracking-[0.28em] font-bold text-forest mb-2">Frame-stamped evidence</div>
                      <h3 className="font-barlow font-black uppercase text-2xl md:text-3xl text-ink leading-tight">Video moments</h3>
                      <p className="mt-2 text-sm text-ink/65 max-w-xl">
                        Every note is tied to the exact moment in the video &mdash; so you can rewatch it yourself.
                      </p>
                      {/* Quick-nav MomentCard strip — horizontal scrollable ribbon,
                          same click-to-seek behaviour as the full grid below.
                          Hidden on desktop where the full grid already shows all cards. */}
                      <div
                        data-testid="moment-strip"
                        className="mt-5 md:hidden -mx-6 px-6 flex gap-3 overflow-x-auto pb-2 snap-x snap-mandatory scrollbar-none"
                      >
                        {full_report.video_comments.slice(0, 8).map((c, i) => {
                          const ts = c.timestamp;
                          const tsParsed = ts && /^\s*\d{1,2}:\d{2}/.test(ts);
                          const m = ts && ts.match(/(\d{1,2}):(\d{2})/);
                          const seconds = m ? parseInt(m[1], 10) * 60 + parseInt(m[2], 10) : 0;
                          return (
                            <div key={`strip-${i}`} className="snap-start">
                              <MomentCard
                                timestamp={seconds}
                                label={`Moment ${String(i + 1).padStart(2, "0")}`}
                                description={c.comment}
                                onSeek={tsParsed ? () => seekVideoTo(ts) : undefined}
                                tone={i % 3 === 0 ? "forest" : i % 3 === 1 ? "volt" : "ink"}
                              />
                            </div>
                          );
                        })}
                      </div>
                      {/* Mini timeline ribbon — visualises WHEN in the clip each moment occurred. */}
                      <div className="mt-5 relative h-1.5 bg-cream-soft border border-forest/15 rounded-full overflow-visible" aria-hidden>
                        {full_report.video_comments.map((c, i) => {
                          const t = c.timestamp || "";
                          const m = t.match(/(\d{1,2}):(\d{2})/);
                          const seconds = m ? (parseInt(m[1], 10) * 60 + parseInt(m[2], 10)) : null;
                          const total = videoRef.current?.duration || 30;
                          const pct = seconds != null && total ? Math.max(0, Math.min(100, (seconds / total) * 100)) : ((i + 1) / (full_report.video_comments.length + 1)) * 100;
                          return (
                            <span
                              key={`tl-${i}`}
                              className="absolute top-1/2 -translate-y-1/2 -translate-x-1/2 w-3 h-3 rounded-full bg-forest border-2 border-cream-base shadow-[0_0_6px_rgba(31,79,47,0.4)]"
                              style={{ left: `${pct}%` }}
                            />
                          );
                        })}
                      </div>
                      <div className="mt-7 grid sm:grid-cols-2 gap-5">
                        {full_report.video_comments.map((c, i) => {
                          const ts = c.timestamp;
                          const tsParsed = ts && /^\s*\d{1,2}:\d{2}/.test(ts);
                          const cardOnClick = (tsParsed && ts) ? () => seekVideoTo(ts) : undefined;
                          return (
                            <div
                              key={i}
                              data-testid={`video-moment-${i}`}
                              role={cardOnClick ? "button" : undefined}
                              tabIndex={cardOnClick ? 0 : undefined}
                              onClick={cardOnClick}
                              onKeyDown={cardOnClick ? (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); cardOnClick(); } } : undefined}
                              className={`relative bg-cream-card overflow-hidden border-l-[3px] border-forest ${cardOnClick ? "cursor-pointer hover:shadow-lg hover:border-forest-pop focus:outline-none focus:ring-2 focus:ring-forest" : ""} transition-shadow shadow-sm`}
                            >
                              {/* Moment number chip — top-left corner */}
                              <span className="absolute top-2 left-2 z-20 inline-flex items-center justify-center min-w-[22px] h-[22px] px-1.5 bg-forest text-cream-card text-[10px] font-black tabular-nums rounded-sm">
                                {String(i + 1).padStart(2, "0")}
                              </span>
                              <div className="relative aspect-video bg-cream-soft group">
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
                                    <FootballIcon className="w-8 h-8 text-ink/15" />
                                  </div>
                                )}
                                {/* Film-strip top/bottom edge — pure decoration, gives a cinematic feel */}
                                <div className="absolute top-0 left-0 right-0 h-1.5 bg-ink/85 flex items-center gap-1 px-1" aria-hidden>
                                  {Array.from({ length: 14 }).map((_, k) => (
                                    <span key={k} className="w-1 h-0.5 bg-cream-base/55" />
                                  ))}
                                </div>
                                <div className="absolute bottom-0 left-0 right-0 h-1.5 bg-ink/85 flex items-center gap-1 px-1" aria-hidden>
                                  {Array.from({ length: 14 }).map((_, k) => (
                                    <span key={k} className="w-1 h-0.5 bg-cream-base/55" />
                                  ))}
                                </div>
                                {cardOnClick && (
                                  <div className="absolute inset-0 flex items-center justify-center bg-ink/0 group-hover:bg-ink/30 transition-colors">
                                    <span className="opacity-0 group-hover:opacity-100 transition-opacity inline-flex items-center gap-1.5 bg-volt text-ink px-3 py-1.5 text-[11px] uppercase tracking-widest font-black shadow-lg">
                                      ▶ Play moment
                                    </span>
                                  </div>
                                )}
                                {/* Timestamp pill — bottom-right, premium look */}
                                <div className="absolute bottom-3 right-2 bg-ink/90 backdrop-blur-sm text-volt px-2.5 py-1 text-[11px] font-barlow font-black tracking-wide rounded-sm inline-flex items-center gap-1.5 border border-volt/40">
                                  <svg viewBox="0 0 24 24" className="w-3 h-3" fill="none" stroke="currentColor" strokeWidth="2.4" aria-hidden>
                                    <circle cx="12" cy="12" r="9" />
                                    <path d="M12 7 L12 12 L15 14" />
                                  </svg>
                                  {c.timestamp || "—"}
                                </div>
                              </div>
                              <p className="p-4 text-sm text-ink/85 leading-relaxed">{c.comment}</p>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  )}

                  {/* Final summary */}
                  {full_report.final_summary && (
                  <div className="bg-surface border border-gray-border p-6 md:p-8 scroll-mt-20" id="report-final-summary">
                    <div className="flex items-center gap-2 mb-2">
                      <PitchLineDivider className="w-10 h-2 text-forest/55" />
                      <span className="text-[9px] uppercase tracking-[0.32em] font-black text-forest">Chapter · 07</span>
                    </div>
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

              {/* Session 126 — Premium tier landing card. Shown when the report
                  is unlocked (paid OR premium/vip/admin role) but the full
                  dossier hasn't been generated yet. Replaces the old plain
                  "Report unlocked · Generate full report" prompt with a high-
                  end "PREMIUM ACCESS · OPEN FULL SCOUT DOSSIER" panel that
                  matches the rest of the premium UI language. */}
              {unlocked && !full_report && !generatingFull && (
                <div
                  data-testid="premium-access-panel"
                  className="relative bg-gradient-to-br from-deepnavy via-ink to-deepnavy border-2 border-volt/50 p-8 md:p-12 text-center overflow-hidden"
                  style={{ boxShadow: "0 32px 60px -20px rgba(204,255,0,0.22), 0 0 0 1px rgba(204,255,0,0.08) inset" }}
                >
                  <div aria-hidden className="absolute -top-24 -right-24 w-64 h-64 rounded-full bg-volt/20 blur-3xl pointer-events-none" />
                  <div aria-hidden className="absolute -bottom-24 -left-24 w-64 h-64 rounded-full bg-forest/25 blur-3xl pointer-events-none" />
                  <div className="relative">
                    <div className="inline-flex items-center gap-2 mb-5">
                      <Crown className="w-4 h-4 text-volt" strokeWidth={1.8} />
                      <span className="text-volt text-[11px] uppercase tracking-[0.35em] font-black">Premium Access</span>
                      <Crown className="w-4 h-4 text-volt" strokeWidth={1.8} />
                    </div>
                    <h3 className="font-barlow font-black uppercase text-4xl md:text-5xl text-cream-base tracking-tight leading-[0.95]">
                      Your Full<br />
                      <span className="text-volt">Scout Dossier</span>
                    </h3>
                    <p className="mt-4 text-cream-base/70 text-sm md:text-base max-w-lg mx-auto leading-relaxed">
                      Technical · Tactical · Physical · Mentality — with age-calibrated benchmarks, evidence &amp; a personal scout review.
                    </p>
                    <button
                      onClick={handleGenerateFull}
                      data-testid="open-full-dossier-btn"
                      className="mt-8 inline-flex items-center justify-center gap-3 bg-volt hover:bg-forest-pop text-ink hover:text-white font-barlow font-black uppercase tracking-[0.22em] text-sm md:text-base px-8 py-4 transition-all group"
                      style={{ boxShadow: "0 12px 32px -8px rgba(204,255,0,0.5)" }}
                    >
                      <Sparkles className="w-4 h-4" />
                      Open Full Scout Dossier
                      <Sparkles className="w-4 h-4 transition-transform group-hover:rotate-12" />
                    </button>
                    <p className="mt-4 text-[10px] text-cream-base/45 uppercase tracking-[0.22em] font-bold flex items-center justify-center gap-1.5">
                      <ShieldCheck className="w-3 h-3" /> Elite-tier access · Included in your plan
                    </p>
                  </div>
                </div>
              )}
              {generatingFull && (
                <div
                  data-testid="premium-generating-panel"
                  className="relative bg-gradient-to-br from-deepnavy via-ink to-deepnavy border-2 border-volt/50 p-8 md:p-12 text-center overflow-hidden"
                  style={{ boxShadow: "0 32px 60px -20px rgba(204,255,0,0.22), 0 0 0 1px rgba(204,255,0,0.08) inset" }}
                >
                  <div aria-hidden className="absolute -top-24 -right-24 w-64 h-64 rounded-full bg-volt/20 blur-3xl pointer-events-none animate-pulse" />
                  <div className="relative">
                    <div className="inline-flex items-center gap-2 mb-5">
                      <Crown className="w-4 h-4 text-volt" strokeWidth={1.8} />
                      <span className="text-volt text-[11px] uppercase tracking-[0.35em] font-black">Premium Access</span>
                    </div>
                    <Loader2 className="w-10 h-10 animate-spin text-volt mx-auto" strokeWidth={1.5} />
                    <p className="mt-5 text-cream-base/85 font-barlow font-black uppercase tracking-[0.22em] text-base">
                      Building Your Scout Dossier
                    </p>
                    <p className="mt-2 text-cream-base/55 text-xs uppercase tracking-[0.22em] font-bold">
                      Technical · Tactical · Physical · Mentality — a few minutes
                    </p>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
