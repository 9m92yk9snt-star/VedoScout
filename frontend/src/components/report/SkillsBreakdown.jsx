/**
 * SkillsBreakdown.jsx — Parent-friendly redesign of the DNA Fingerprint.
 *
 * Fixes the "wall of numbers" problem by:
 *   • Grouping skills by pillar (Technical / Tactical / Physical / Mindset)
 *   • Giving every skill a plain-language name + a one-sentence meaning
 *   • Highlighting the Top 3 standout skills in a dedicated row at the top
 *   • Auto-linking skills to matching video moments (keyword match against
 *     `video_comments`) so a parent can click "See at 0:24" and jump to
 *     the actual footage — every note anchored back to the video.
 *
 * Purely presentational — no data changes, no backend calls.
 */
import React, { useMemo, useState } from "react";
import { motion } from "framer-motion";
import { PlayCircle, Info, Sparkles, ChevronDown, ChevronUp } from "lucide-react";
import { PillarIcon, SkillMeter } from "@/components/report/FootballReport";

/* ── Parent-friendly skill dictionary ──────────────────────────────────── */
const SKILL_MEANINGS = {
  // Technical
  first_touch:          { label: "First touch",         meaning: "The very first moment when the ball arrives — does it stay under his control, or does it bounce away?" },
  ball_control:         { label: "Ball control",         meaning: "How comfortable he is with the ball at his feet in tight spaces." },
  dribbling:            { label: "Dribbling",            meaning: "His ability to beat defenders on the run — feints, changes of direction, take-ons." },
  passing:              { label: "Passing",              meaning: "How accurately and cleverly he moves the ball to a teammate." },
  shooting:             { label: "Shooting",             meaning: "Technique, power and placement when he finishes." },
  weak_foot:            { label: "Weak foot",            meaning: "How usable his non-dominant foot is under pressure." },
  one_v_one:            { label: "1v1 duels",            meaning: "What happens when it's just him against a single defender." },
  // Tactical
  positioning:          { label: "Positioning",          meaning: "Whether he's in the right spot on the pitch — with and without the ball." },
  off_ball_movement:    { label: "Off-ball movement",    meaning: "How he moves without the ball — creating space, making runs, dragging defenders." },
  scanning:             { label: "Scanning",             meaning: "How often he looks around before receiving the ball. A sign of football IQ." },
  decision_making:      { label: "Decision making",      meaning: "Does he choose the right pass, run or shot in the moment?" },
  timing_of_runs:       { label: "Timing of runs",       meaning: "When he breaks forward — early enough to hurt, late enough to stay onside." },
  game_understanding:   { label: "Game reading",         meaning: "How well he seems to understand what each moment of the game needs." },
  // Physical
  acceleration:         { label: "Acceleration",         meaning: "How quickly he gets from standing to full speed in the first 3–5 steps." },
  speed:                { label: "Top speed",            meaning: "How fast he is once he's already running." },
  balance:              { label: "Balance",              meaning: "Whether he stays on his feet when defenders challenge him." },
  agility:              { label: "Agility",              meaning: "How sharply he can change direction without losing control." },
  intensity:            { label: "Intensity",            meaning: "How much energy he brings — sprints, closing down, work rate." },
  body_control:         { label: "Body control",         meaning: "How well he uses his body to shield the ball or hold off defenders." },
  // Mindset
  confidence:           { label: "Confidence",           meaning: "Does he demand the ball and take risks — even after a mistake?" },
  work_rate:            { label: "Work rate",            meaning: "How hard he works when his team doesn't have the ball." },
  courage_in_duels:     { label: "Courage in duels",     meaning: "Does he go into tackles and headers without hesitation?" },
  response_to_mistakes: { label: "Response to mistakes", meaning: "What his body language and next action look like after a bad moment." },
  competitive_mindset:  { label: "Competitive edge",     meaning: "How badly he seems to want to win — attitude, not just skill." },
  focus:                { label: "Focus",                meaning: "Does he stay switched on for the full match — no wandering, no drifting?" },
};

const PILLAR_META = {
  technical: { label: "Technical", kind: "technical", desc: "What he does with the ball at his feet.", accent: "text-forest",       bar: "bg-forest",     bg: "bg-forest/6" },
  tactical:  { label: "Tactical",  kind: "tactical",  desc: "How he reads the game and picks his moments.", accent: "text-forest-pop", bar: "bg-forest-pop", bg: "bg-forest-pop/8" },
  physical:  { label: "Physical",  kind: "physical",  desc: "The engine — speed, balance, agility.",       accent: "text-amber-700",  bar: "bg-amber-600",  bg: "bg-amber-100/40" },
  mentality: { label: "Mindset",   kind: "mindset",   desc: "The mental side — courage, focus, work rate.",accent: "text-ink",        bar: "bg-ink",        bg: "bg-ink/5" },
};

const PILLAR_ATTRS = {
  technical: ["first_touch", "ball_control", "dribbling", "passing", "shooting", "weak_foot", "one_v_one"],
  tactical:  ["positioning", "off_ball_movement", "scanning", "decision_making", "timing_of_runs", "game_understanding"],
  physical:  ["acceleration", "speed", "balance", "agility", "intensity", "body_control"],
  mentality: ["confidence", "work_rate", "courage_in_duels", "response_to_mistakes", "competitive_mindset", "focus"],
};

/* ── Video-timestamp matcher ───────────────────────────────────────────── */
function _timestampFor(skillKey, videoComments) {
  if (!Array.isArray(videoComments) || videoComments.length === 0) return null;
  const meaning = SKILL_MEANINGS[skillKey];
  if (!meaning) return null;
  const label = meaning.label.toLowerCase();
  // Build a keyword list from the label (e.g. "first touch" → ["first touch", "touch"])
  const wordsFromLabel = label.split(/\s+/).filter((w) => w.length >= 4);
  const keywords = new Set([label, ...wordsFromLabel, skillKey.replace(/_/g, " ")]);
  if (skillKey === "dribbling")          { keywords.add("dribble"); keywords.add("beats"); }
  if (skillKey === "shooting")           { keywords.add("shot"); keywords.add("finish"); keywords.add("goal"); }
  if (skillKey === "passing")            { keywords.add("pass"); keywords.add("cross"); }
  if (skillKey === "one_v_one")          { keywords.add("1v1"); keywords.add("beat"); }
  if (skillKey === "scanning")           { keywords.add("look"); keywords.add("checks"); keywords.add("shoulder"); }
  if (skillKey === "off_ball_movement")  { keywords.add("run"); keywords.add("movement"); }
  if (skillKey === "positioning")        { keywords.add("position"); }
  if (skillKey === "courage_in_duels")   { keywords.add("tackle"); keywords.add("duel"); keywords.add("header"); }
  if (skillKey === "speed" || skillKey === "acceleration") { keywords.add("sprint"); keywords.add("pace"); }
  if (skillKey === "confidence")         { keywords.add("demand"); }
  if (skillKey === "response_to_mistakes") { keywords.add("mistake"); keywords.add("react"); }
  for (const c of videoComments) {
    const txt = String(c.comment || "").toLowerCase();
    for (const kw of keywords) {
      if (kw && txt.includes(kw)) return c.timestamp || null;
    }
  }
  return null;
}

/* ── Compact skill row ─────────────────────────────────────────────────── */
function SkillRow({ skillKey, score, pillar, videoComments, onSeek, expanded, onToggle, index }) {
  const meta = SKILL_MEANINGS[skillKey];
  if (!meta) return null;
  const pMeta = PILLAR_META[pillar];
  const pct = Math.max(0, Math.min(100, (Number(score) || 0) * 10));
  const ts = _timestampFor(skillKey, videoComments);
  const tsParsed = ts && /^\s*\d{1,2}:\d{2}/.test(ts);

  const tone =
    score >= 8   ? "text-forest"      :
    score >= 6.5 ? "text-forest-pop"  :
    score >= 5   ? "text-amber-700"   :
                   "text-ink/55";

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 6 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-40px" }}
      transition={{ duration: 0.35, delay: index * 0.03 }}
      className="border border-gray-border bg-cream-card"
      data-testid={`skill-row-${skillKey}`}
    >
      <button
        type="button"
        onClick={onToggle}
        className="w-full text-left px-3.5 py-3 flex items-center gap-3 hover:bg-cream-soft/40 transition-colors group"
        aria-expanded={expanded}
        data-testid={`skill-row-toggle-${skillKey}`}
      >
        <span className={`w-1 h-8 shrink-0 ${pMeta.bar}`} />
        <div className="flex-1 min-w-0">
          <div className="flex items-baseline gap-2 flex-wrap">
            <span className="text-sm font-semibold text-ink leading-tight">{meta.label}</span>
            {tsParsed && (
              <span
                className="inline-flex items-center gap-1 text-[9px] uppercase tracking-[0.18em] font-black text-forest border border-forest/25 bg-forest/8 px-1.5 py-0.5"
                data-testid={`skill-video-chip-${skillKey}`}
              >
                <PlayCircle className="w-2.5 h-2.5" />
                See at {ts}
              </span>
            )}
          </div>
          {/* animated bar */}
          <div className="mt-2 h-1.5 w-full bg-cream-soft/70 relative overflow-hidden">
            <motion.div
              initial={{ width: 0 }}
              whileInView={{ width: `${pct}%` }}
              viewport={{ once: true, margin: "-40px" }}
              transition={{ duration: 1, delay: 0.2 + index * 0.02, ease: [0.22, 1, 0.36, 1] }}
              className={`absolute inset-y-0 left-0 ${pMeta.bar}`}
            />
          </div>
        </div>
        <div className="flex items-center gap-1.5 shrink-0">
          <span className={`font-barlow font-black text-xl tabular-nums leading-none ${tone}`}>
            {score}
            <span className="text-[9px] text-ink/40 font-bold ml-0.5">/10</span>
          </span>
          {expanded ? (
            <ChevronUp className="w-4 h-4 text-ink/40 group-hover:text-forest transition-colors" />
          ) : (
            <ChevronDown className="w-4 h-4 text-ink/40 group-hover:text-forest transition-colors" />
          )}
        </div>
      </button>
      {expanded && (
        <motion.div
          initial={{ opacity: 0, height: 0 }}
          animate={{ opacity: 1, height: "auto" }}
          exit={{ opacity: 0, height: 0 }}
          transition={{ duration: 0.25 }}
          className="px-3.5 pb-3 pt-1 border-t border-gray-border bg-cream-soft/25"
          data-testid={`skill-row-expanded-${skillKey}`}
        >
          <div className="flex items-start gap-2 text-[12px] text-ink/75 leading-relaxed">
            <Info className="w-3 h-3 mt-0.5 text-forest shrink-0" />
            <p><span className="font-bold text-ink/85">What we&apos;re looking at:</span> {meta.meaning}</p>
          </div>
          {tsParsed && (
            <button
              type="button"
              onClick={(e) => { e.stopPropagation(); onSeek && onSeek(ts); }}
              className="mt-2 inline-flex items-center gap-1.5 text-[10px] uppercase tracking-[0.22em] font-black text-forest hover:text-forest-pop transition-colors"
              data-testid={`skill-video-cta-${skillKey}`}
            >
              <PlayCircle className="w-3.5 h-3.5" />
              Watch this moment · {ts}
            </button>
          )}
        </motion.div>
      )}
    </motion.div>
  );
}

/* ── Standout-skill hero card ──────────────────────────────────────────── */
function StandoutCard({ skillKey, score, pillar, rank, videoComments, onSeek }) {
  const meta = SKILL_MEANINGS[skillKey];
  if (!meta) return null;
  const pMeta = PILLAR_META[pillar];
  const ts = _timestampFor(skillKey, videoComments);
  const tsParsed = ts && /^\s*\d{1,2}:\d{2}/.test(ts);

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-40px" }}
      transition={{ duration: 0.45, delay: rank * 0.08 }}
      className="relative bg-ink text-cream-base p-4 md:p-5 overflow-hidden"
      data-testid={`standout-card-${skillKey}`}
    >
      {/* Volt corner accent */}
      <div className="absolute top-0 right-0 w-0 h-0 border-t-[28px] border-l-[28px] border-t-volt border-l-transparent pointer-events-none" />
      <div className="absolute top-1 right-1.5 text-[9px] font-barlow font-black text-ink z-10 leading-none">
        #{rank + 1}
      </div>

      <div className="flex items-center gap-2 mb-2">
        <PillarIcon kind={pMeta.kind} className="w-4 h-4 text-volt" />
        <span className="text-[9px] uppercase tracking-[0.28em] font-black text-volt">Standout skill</span>
      </div>

      <div className="font-barlow font-black uppercase text-xl md:text-2xl leading-tight text-cream-base">
        {meta.label}
      </div>
      <div className="mt-1 text-[10px] uppercase tracking-[0.22em] font-bold text-cream-base/55">
        {pMeta.label}
      </div>

      <div className="mt-3 flex items-baseline gap-2">
        <span className="font-barlow font-black text-4xl md:text-5xl text-volt leading-none tabular-nums">
          {score}
        </span>
        <span className="text-cream-base/40 font-barlow font-black text-lg">/10</span>
      </div>

      <p className="mt-3 text-[12px] text-cream-base/75 leading-snug">{meta.meaning}</p>

      {tsParsed && (
        <button
          type="button"
          onClick={() => onSeek && onSeek(ts)}
          className="mt-3 inline-flex items-center gap-1.5 text-[10px] uppercase tracking-[0.22em] font-black text-volt hover:text-cream-base transition-colors border-b border-volt/40 pb-0.5"
          data-testid={`standout-video-cta-${skillKey}`}
        >
          <PlayCircle className="w-3.5 h-3.5" />
          See it at {ts}
        </button>
      )}
    </motion.div>
  );
}

/* ── Score-band legend chip ────────────────────────────────────────────── */
function BandChip({ tone, range, label }) {
  return (
    <div className="flex items-center gap-1.5">
      <span className={`w-3 h-3 ${tone}`} />
      <span className="text-[9.5px] uppercase tracking-[0.18em] font-bold text-ink/75">
        {range} <span className="text-ink/50 normal-case tracking-normal font-medium">{label}</span>
      </span>
    </div>
  );
}

/* ── Main export ───────────────────────────────────────────────────────── */
export default function SkillsBreakdown({ fullReport, videoComments, onSeek, ageProfile }) {
  const [expandedKey, setExpandedKey] = useState(null);

  // Collect every scored skill across all 4 pillars.
  const allSkills = useMemo(() => {
    if (!fullReport) return [];
    const out = [];
    for (const pillar of ["technical", "tactical", "physical", "mentality"]) {
      const sec = fullReport[pillar] || {};
      for (const [key, value] of Object.entries(sec)) {
        if (value && typeof value === "object" && typeof value.score === "number") {
          out.push({ key, pillar, score: value.score });
        }
      }
    }
    return out;
  }, [fullReport]);

  // Priority weights (for stable ordering inside each pillar column).
  const priorityWeights = useMemo(() => {
    const w = {};
    if (ageProfile && Array.isArray(ageProfile.items)) {
      for (const it of ageProfile.items) w[it.key] = it.weight || 3;
    }
    return w;
  }, [ageProfile]);

  // Top 3 standout skills (across all pillars).
  const standouts = useMemo(() => {
    return [...allSkills].sort((a, b) => b.score - a.score).slice(0, 3);
  }, [allSkills]);

  // Skills grouped by pillar, sorted by priority then score.
  const grouped = useMemo(() => {
    const buckets = { technical: [], tactical: [], physical: [], mentality: [] };
    for (const s of allSkills) buckets[s.pillar]?.push(s);
    for (const p of Object.keys(buckets)) {
      buckets[p].sort((a, b) => {
        const wa = priorityWeights[a.key] ?? 0;
        const wb = priorityWeights[b.key] ?? 0;
        if (wb !== wa) return wb - wa;
        return b.score - a.score;
      });
    }
    return buckets;
  }, [allSkills, priorityWeights]);

  if (allSkills.length === 0) return null;

  const toggle = (k) => setExpandedKey((cur) => (cur === k ? null : k));
  const linkedCount = allSkills.filter((s) => _timestampFor(s.key, videoComments)).length;

  return (
    <div data-testid="skills-breakdown" className="bg-surface border border-gray-border p-6 md:p-8">
      {/* Header + guide */}
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div className="max-w-2xl">
          <div className="inline-flex items-center gap-2 mb-2">
            <span className="w-6 h-px bg-forest" />
            <span className="text-[10px] uppercase tracking-[0.32em] font-black text-forest">
              Full skill picture
            </span>
          </div>
          <h3 className="font-barlow font-black uppercase text-2xl md:text-3xl text-ink leading-tight">
            The full picture — every skill we scored.
          </h3>
          <p className="mt-3 text-sm text-ink/70 leading-relaxed">
            Below is every skill we looked at, grouped into <strong>Technical</strong>, <strong>Tactical</strong>, <strong>Physical</strong> and <strong>Mindset</strong>. Tap any skill row to see <em>what we&apos;re actually looking for</em>{linkedCount > 0 && (
              <> — and <span className="text-forest font-semibold">{linkedCount} of them link straight to the exact moment in the video</span></>
            )}.
          </p>
        </div>

        {/* Score band legend */}
        <div className="border border-gray-border bg-cream-card p-3 min-w-[210px]" data-testid="skills-legend">
          <div className="text-[9px] uppercase tracking-[0.28em] font-black text-ink/50 mb-2">Score bands</div>
          <div className="space-y-1.5">
            <BandChip tone="bg-forest"      range="8–10" label="Elite / Pro" />
            <BandChip tone="bg-forest-pop"  range="6.5–8" label="Strong club" />
            <BandChip tone="bg-amber-600"   range="5–6.5" label="Standard club" />
            <BandChip tone="bg-ink/40"      range="< 5"  label="Foundation" />
          </div>
        </div>
      </div>

      {/* TOP 3 standouts */}
      {standouts.length > 0 && (
        <div className="mt-8">
          <div className="flex items-center gap-2 mb-3">
            <Sparkles className="w-4 h-4 text-volt fill-volt/30" strokeWidth={2} />
            <span className="text-[10px] uppercase tracking-[0.28em] font-black text-forest">
              His top 3 — what stands out most
            </span>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3" data-testid="standout-grid">
            {standouts.map((s, i) => (
              <StandoutCard
                key={s.key}
                skillKey={s.key}
                score={s.score}
                pillar={s.pillar}
                rank={i}
                videoComments={videoComments}
                onSeek={onSeek}
              />
            ))}
          </div>
        </div>
      )}

      {/* Grouped by pillar */}
      <div className="mt-10 grid grid-cols-1 lg:grid-cols-2 gap-5" data-testid="skills-grouped-grid">
        {["technical", "tactical", "physical", "mentality"].map((p) => {
          const items = grouped[p];
          if (!items || items.length === 0) return null;
          const meta = PILLAR_META[p];
          const avg = (items.reduce((a, b) => a + b.score, 0) / items.length).toFixed(1);
          return (
            <div
              key={p}
              className={`border border-gray-border ${meta.bg} p-4 md:p-5`}
              data-testid={`skills-group-${p}`}
            >
              {/* Pillar header */}
              <div className="flex items-start justify-between gap-3 mb-4">
                <div className="flex items-start gap-3 min-w-0">
                  <span className={`shrink-0 w-9 h-9 flex items-center justify-center border border-gray-border bg-cream-card ${meta.accent}`}>
                    <PillarIcon kind={meta.kind} className="w-5 h-5" />
                  </span>
                  <div className="min-w-0">
                    <div className={`text-[9px] uppercase tracking-[0.28em] font-black ${meta.accent}`}>{p === "mentality" ? "Mindset · pillar" : `${meta.label} · pillar`}</div>
                    <h4 className="font-barlow font-black uppercase text-lg md:text-xl text-ink leading-tight mt-0.5">
                      {meta.label}
                    </h4>
                    <p className="mt-1 text-[11px] text-ink/60 leading-snug">{meta.desc}</p>
                  </div>
                </div>
                <div className="text-right shrink-0">
                  <div className={`font-barlow font-black text-2xl leading-none tabular-nums ${meta.accent}`}>{avg}</div>
                  <div className="text-[9px] uppercase tracking-[0.22em] font-bold text-ink/45 mt-0.5">Pillar avg</div>
                </div>
              </div>

              {/* Skill rows */}
              <div className="space-y-2">
                {items.map((s, idx) => (
                  <SkillRow
                    key={s.key}
                    skillKey={s.key}
                    score={s.score}
                    pillar={s.pillar}
                    videoComments={videoComments}
                    onSeek={onSeek}
                    expanded={expandedKey === s.key}
                    onToggle={() => toggle(s.key)}
                    index={idx}
                  />
                ))}
              </div>
            </div>
          );
        })}
      </div>

      {/* Guide footer */}
      <div className="mt-6 flex items-start gap-2 text-[11.5px] text-ink/55 leading-relaxed italic">
        <Info className="w-3.5 h-3.5 mt-0.5 text-forest shrink-0 not-italic" />
        <span>
          Tap any skill row to reveal what we actually looked for. Where you see a{" "}
          <span className="inline-flex items-center gap-1 not-italic text-forest font-black text-[10px] uppercase tracking-[0.16em]">
            <PlayCircle className="w-3 h-3" /> See at 0:XX
          </span>{" "}
          chip, we found a matching moment in the video — click it to jump straight to that clip.
        </span>
      </div>
    </div>
  );
}
