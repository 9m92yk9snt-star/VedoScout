/**
 * PerformanceRadarHero.jsx — Cinematic centrepiece redesign of the Performance
 * Radar. Replaces Recharts with a hand-built animated SVG diamond radar on top
 * of a dark stadium hero photograph. Purely presentational — accepts the same
 * 4 scores (technical/tactical/physical/mentality) and renders them.
 *
 *   • Dark ink centrepiece with Nano Banana stadium background + heavy overlay
 *   • Framer-motion animated player shape (draw-in + shimmer)
 *   • 4 tier reference rings (Standard/Strong/Pro/Elite) with pulsing Elite ring
 *   • Score callouts absolutely positioned at the poles of the radar
 *   • Interactive hover states on axis labels
 *   • Tactical Key floating panel (backdrop-blur)
 */
import React, { useMemo, useState } from "react";
import { motion, useInView } from "framer-motion";
import { useRef } from "react";
import { PillarIcon } from "@/components/report/FootballReport";

const CANVAS = 520; // logical SVG viewBox size
const CENTER = CANVAS / 2;
const R_MAX = 210; // max score (10) reaches this radius (in viewBox units)

/* 4-axis coordinate helpers.
   Order: 0 = Top (Technical), 1 = Right (Tactical), 2 = Bottom (Physical), 3 = Left (Mental) */
function axisPoint(index, value, max = 10) {
  const t = Math.max(0, Math.min(1, (Number(value) || 0) / max));
  const r = R_MAX * t;
  switch (index) {
    case 0: return [CENTER, CENTER - r];
    case 1: return [CENTER + r, CENTER];
    case 2: return [CENTER, CENTER + r];
    case 3: return [CENTER - r, CENTER];
    default: return [CENTER, CENTER];
  }
}

function polygonPath(scores, max = 10) {
  const pts = [0, 1, 2, 3].map((i) => axisPoint(i, scores[i], max));
  return `M ${pts[0][0]} ${pts[0][1]} L ${pts[1][0]} ${pts[1][1]} L ${pts[2][0]} ${pts[2][1]} L ${pts[3][0]} ${pts[3][1]} Z`;
}

function tierRingPath(value) {
  return polygonPath([value, value, value, value]);
}

/* Score chip — pill anchored to an axis pole */
function AxisChip({ label, score, kind, pos, active, onHoverStart, onHoverEnd, testid }) {
  const [x, y] = pos;
  return (
    <motion.div
      onMouseEnter={onHoverStart}
      onMouseLeave={onHoverEnd}
      onFocus={onHoverStart}
      onBlur={onHoverEnd}
      tabIndex={0}
      data-testid={testid}
      role="button"
      aria-label={`${label} score ${score} out of 10`}
      className="absolute -translate-x-1/2 -translate-y-1/2 select-none outline-none"
      style={{ left: `${x}%`, top: `${y}%` }}
      initial={{ opacity: 0, scale: 0.7 }}
      whileInView={{ opacity: 1, scale: 1 }}
      viewport={{ once: true, margin: "-40px" }}
      transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
      whileHover={{ scale: 1.08 }}
    >
      <div
        className={`flex items-center gap-2 px-2.5 py-1.5 md:px-3 md:py-2 border-2 backdrop-blur-md transition-all duration-300 ${
          active
            ? "bg-volt text-ink border-volt shadow-[0_0_28px_rgba(204,255,0,0.55)]"
            : "bg-ink/70 text-cream-base border-cream-base/25 hover:border-volt/70"
        }`}
      >
        <PillarIcon kind={kind} className={`w-4 h-4 md:w-5 md:h-5 ${active ? "text-ink" : "text-volt"}`} />
        <div className="flex flex-col leading-none">
          <span className={`text-[8px] md:text-[9px] uppercase tracking-[0.22em] font-bold ${active ? "text-ink/70" : "text-cream-base/60"}`}>
            {label}
          </span>
          <span className="font-barlow font-black text-lg md:text-2xl leading-none tabular-nums">
            {score ?? "—"}<span className={`text-[9px] md:text-[10px] font-bold ml-0.5 ${active ? "text-ink/50" : "text-cream-base/45"}`}>/10</span>
          </span>
        </div>
      </div>
    </motion.div>
  );
}

/* Small dashed swatch used inside the Tactical Key */
function KeySwatch({ dash, tone, label, value }) {
  return (
    <div className="flex items-center gap-2.5">
      <svg viewBox="0 0 36 6" className="w-9 h-1.5 shrink-0" aria-hidden>
        <line x1="0" y1="3" x2="36" y2="3" stroke="currentColor" strokeWidth="2" strokeDasharray={dash} className={tone} />
      </svg>
      <div className="flex items-center gap-1.5">
        <span className="text-[9px] uppercase tracking-[0.22em] font-bold text-cream-base/85">{label}</span>
        <span className="text-[9px] font-bold text-volt tabular-nums">{value}</span>
      </div>
    </div>
  );
}

export default function PerformanceRadarHero({
  scores, // { technical, tactical, physical, mentality }
  bgSrc,  // /api/static/landing/radar-hero-stadium.png
}) {
  const wrapRef = useRef(null);
  const inView = useInView(wrapRef, { once: true, margin: "-80px" });
  const [hover, setHover] = useState(null); // 0/1/2/3

  const values = useMemo(() => ([
    Number(scores?.technical) || 0,
    Number(scores?.tactical) || 0,
    Number(scores?.physical) || 0,
    Number(scores?.mentality) || 0,
  ]), [scores]);

  const playerPath = useMemo(() => polygonPath(values), [values]);
  const vertexPts = useMemo(() => [0, 1, 2, 3].map((i) => axisPoint(i, values[i])), [values]);

  const chips = [
    { i: 0, kind: "technical", label: "Technical", value: values[0], pos: [50, 8],  testid: "radar-chip-technical" },
    { i: 1, kind: "tactical",  label: "Tactical",  value: values[1], pos: [92, 50], testid: "radar-chip-tactical" },
    { i: 2, kind: "physical",  label: "Physical",  value: values[2], pos: [50, 92], testid: "radar-chip-physical" },
    { i: 3, kind: "mindset",   label: "Mindset",   value: values[3], pos: [8, 50],  testid: "radar-chip-mindset" },
  ];

  return (
    <div
      ref={wrapRef}
      data-testid="performance-radar-hero"
      className="relative w-full overflow-hidden bg-ink text-cream-base"
    >
      {/* Background — cinematic Nano Banana stadium */}
      {bgSrc && (
        <img
          src={bgSrc}
          alt=""
          aria-hidden
          loading="lazy"
          onError={(e) => { e.currentTarget.style.display = "none"; }}
          className="absolute inset-0 w-full h-full object-cover opacity-45"
        />
      )}
      {/* Heavy overlays — depth + focus on radar */}
      <div aria-hidden className="absolute inset-0 bg-gradient-to-b from-ink/60 via-ink/85 to-ink" />
      <div aria-hidden className="absolute inset-0 bg-gradient-to-r from-ink via-ink/40 to-transparent" />
      {/* Volt glow behind the radar */}
      <div aria-hidden className="hidden lg:block absolute right-[6%] top-1/2 -translate-y-1/2 w-[520px] h-[520px] rounded-full bg-forest/25 blur-[110px] pointer-events-none" />
      <div aria-hidden className="absolute right-[15%] top-1/2 -translate-y-1/2 w-[300px] h-[300px] rounded-full bg-volt/8 blur-[80px] pointer-events-none" />

      {/* Grid content */}
      <div className="relative z-10 grid grid-cols-1 lg:grid-cols-12 gap-8 lg:gap-6 items-center px-6 md:px-10 py-14 md:py-20">
        {/* LEFT — copy + tactical key */}
        <div className="lg:col-span-4 space-y-6">
          <div>
            <div className="inline-flex items-center gap-2 mb-4">
              <span className="w-8 h-px bg-volt" />
              <span className="text-volt text-[10px] uppercase tracking-[0.32em] font-bold">
                Chapter · Performance
              </span>
            </div>
            <h2 className="font-barlow font-black uppercase tracking-tighter text-4xl md:text-5xl lg:text-6xl leading-[0.9] text-cream-base">
              His game at<br />
              <span className="text-volt">a glance.</span>
            </h2>
            <p className="mt-4 text-sm md:text-base text-cream-base/70 max-w-md leading-relaxed">
              One shape per area — the further the shape reaches out toward an axis, the stronger he is in that part of his game.
            </p>
          </div>

          {/* Overall score badge */}
          <div className="inline-flex items-baseline gap-3 border-l-2 border-volt pl-4">
            <div className="text-[10px] uppercase tracking-[0.28em] font-bold text-cream-base/60 leading-none">
              Overall shape reaches
            </div>
          </div>
          <div className="flex items-baseline gap-4">
            <div className="font-barlow font-black text-6xl md:text-7xl text-volt leading-none tabular-nums">
              {(values.reduce((a, b) => a + b, 0) / 4).toFixed(1)}
            </div>
            <div className="text-cream-base/40 font-barlow font-black text-2xl">/10</div>
            <div className="text-[10px] uppercase tracking-[0.24em] font-bold text-cream-base/55 max-w-[130px]">
              Average of the 4 pillars
            </div>
          </div>

          {/* Tactical Key */}
          <div
            data-testid="radar-tactical-key"
            className="mt-2 bg-ink/55 backdrop-blur-md border border-cream-base/12 p-4 md:p-5"
          >
            <div className="text-[10px] uppercase tracking-[0.28em] font-black text-volt mb-3">
              Tactical Key · Reference tiers
            </div>
            <div className="grid grid-cols-2 gap-x-4 gap-y-2.5">
              <KeySwatch dash="2 3"  tone="text-cream-base/25" label="Standard" value="4.0" />
              <KeySwatch dash="4 3"  tone="text-amber-400/70" label="Strong"   value="6.0" />
              <KeySwatch dash="6 3"  tone="text-forest-pop"   label="Pro"      value="8.0" />
              <KeySwatch dash="8 2"  tone="text-volt"          label="Elite"    value="9.5" />
            </div>
            <div className="mt-3 pt-3 border-t border-cream-base/10 flex items-center gap-2 text-[10px] uppercase tracking-[0.22em] font-bold text-cream-base/70">
              <span className="inline-block w-3 h-3 bg-volt rounded-full shadow-[0_0_10px_rgba(204,255,0,0.7)]" />
              His shape (solid volt)
            </div>
          </div>
        </div>

        {/* RIGHT — the radar */}
        <div className="lg:col-span-8 relative flex items-center justify-center">
          <div className="relative w-full max-w-[560px] aspect-square mx-auto">

            {/* Compass ticks — N/E/S/W */}
            {["N", "E", "S", "W"].map((c, i) => (
              <span
                key={c}
                aria-hidden
                className="absolute text-[9px] uppercase tracking-[0.32em] font-bold text-cream-base/25"
                style={{
                  ...(i === 0 && { top: 4, left: "50%", transform: "translateX(-50%)" }),
                  ...(i === 1 && { right: 4, top: "50%", transform: "translateY(-50%)" }),
                  ...(i === 2 && { bottom: 4, left: "50%", transform: "translateX(-50%)" }),
                  ...(i === 3 && { left: 4, top: "50%", transform: "translateY(-50%)" }),
                }}
              >
                {c}
              </span>
            ))}

            {/* SVG radar */}
            <svg
              viewBox={`0 0 ${CANVAS} ${CANVAS}`}
              className="absolute inset-0 w-full h-full"
              role="img"
              aria-label="Performance radar showing 4 pillar scores"
              data-testid="radar-svg"
            >
              <defs>
                {/* Gradient for player fill */}
                <radialGradient id="playerFill" cx="50%" cy="50%" r="60%">
                  <stop offset="0%" stopColor="#CCFF00" stopOpacity="0.55" />
                  <stop offset="55%" stopColor="#CCFF00" stopOpacity="0.30" />
                  <stop offset="100%" stopColor="#CCFF00" stopOpacity="0.10" />
                </radialGradient>
                {/* Soft glow filter */}
                <filter id="voltGlow" x="-20%" y="-20%" width="140%" height="140%">
                  <feGaussianBlur stdDeviation="4" result="blur" />
                  <feMerge>
                    <feMergeNode in="blur" />
                    <feMergeNode in="SourceGraphic" />
                  </feMerge>
                </filter>
              </defs>

              {/* Chalk background rings (concentric diamonds every 2 points) */}
              {[2, 4, 6, 8, 10].map((v) => (
                <path
                  key={`bg-${v}`}
                  d={tierRingPath(v)}
                  fill="none"
                  stroke="#F5F1E8"
                  strokeOpacity={v === 10 ? 0.14 : 0.06}
                  strokeWidth={v === 10 ? 1.2 : 0.9}
                />
              ))}
              {/* Cardinal axes */}
              {[[CENTER, CENTER - R_MAX], [CENTER + R_MAX, CENTER], [CENTER, CENTER + R_MAX], [CENTER - R_MAX, CENTER]].map(([x, y], i) => (
                <line
                  key={`ax-${i}`}
                  x1={CENTER} y1={CENTER} x2={x} y2={y}
                  stroke="#F5F1E8"
                  strokeOpacity={hover === i ? 0.55 : 0.14}
                  strokeWidth={hover === i ? 1.4 : 1}
                  strokeDasharray="2 4"
                  style={{ transition: "stroke-opacity 250ms, stroke-width 250ms" }}
                />
              ))}

              {/* Tier reference rings — dashed diamonds */}
              {[
                { v: 4,   stroke: "rgba(245,241,232,0.28)", dash: "2 3",  key: "standard" },
                { v: 6,   stroke: "rgba(251,191,36,0.55)",  dash: "4 3",  key: "strong" },
                { v: 8,   stroke: "rgba(45,107,61,0.9)",    dash: "6 3",  key: "pro" },
                { v: 9.5, stroke: "rgba(204,255,0,0.7)",    dash: "8 2",  key: "elite" },
              ].map((r) => (
                <motion.path
                  key={`tier-${r.key}`}
                  d={tierRingPath(r.v)}
                  fill="none"
                  stroke={r.stroke}
                  strokeWidth={r.key === "elite" ? 2 : 1.5}
                  strokeDasharray={r.dash}
                  initial={{ opacity: 0 }}
                  animate={inView ? {
                    opacity: r.key === "elite" ? [0.55, 0.95, 0.55] : 1,
                  } : { opacity: 0 }}
                  transition={{
                    delay: 0.15 + ({ standard: 0, strong: 0.1, pro: 0.2, elite: 0.3 })[r.key],
                    duration: r.key === "elite" ? 3.6 : 0.7,
                    repeat: r.key === "elite" ? Infinity : 0,
                    ease: "easeInOut",
                  }}
                  data-testid={`radar-ring-${r.key}`}
                />
              ))}

              {/* Player shape — fill + stroke draw-in */}
              <motion.path
                d={playerPath}
                fill="url(#playerFill)"
                initial={{ fillOpacity: 0 }}
                animate={inView ? { fillOpacity: 1 } : { fillOpacity: 0 }}
                transition={{ delay: 0.9, duration: 1.1, ease: "easeOut" }}
                data-testid="radar-player-fill"
              />
              <motion.path
                d={playerPath}
                fill="none"
                stroke="#CCFF00"
                strokeWidth={3}
                strokeLinejoin="round"
                filter="url(#voltGlow)"
                initial={{ pathLength: 0 }}
                animate={inView ? { pathLength: 1 } : { pathLength: 0 }}
                transition={{ delay: 0.55, duration: 1.4, ease: [0.22, 1, 0.36, 1] }}
                data-testid="radar-player-stroke"
              />

              {/* Vertex dots — highlighted when the axis label is hovered */}
              {vertexPts.map(([x, y], i) => (
                <motion.circle
                  key={`vx-${i}`}
                  cx={x} cy={y}
                  r={hover === i ? 9 : 6}
                  fill="#CCFF00"
                  stroke="#0A0F0D"
                  strokeWidth="2"
                  filter="url(#voltGlow)"
                  initial={{ scale: 0, opacity: 0 }}
                  animate={inView ? { scale: 1, opacity: 1 } : { scale: 0, opacity: 0 }}
                  transition={{ delay: 1.4 + i * 0.08, duration: 0.4, type: "spring", stiffness: 180 }}
                  style={{ transition: "r 250ms" }}
                  data-testid={`radar-vertex-${i}`}
                />
              ))}

              {/* Centre bullseye */}
              <circle cx={CENTER} cy={CENTER} r="3" fill="#F5F1E8" opacity="0.25" />
              <circle cx={CENTER} cy={CENTER} r="1.4" fill="#CCFF00" />
            </svg>

            {/* Axis chips — anchored to the outer poles */}
            {chips.map((c) => (
              <AxisChip
                key={c.i}
                label={c.label}
                score={c.value}
                kind={c.kind}
                pos={c.pos}
                active={hover === c.i}
                onHoverStart={() => setHover(c.i)}
                onHoverEnd={() => setHover(null)}
                testid={c.testid}
              />
            ))}

            {/* Corner tick label — subtle scan-line eyebrow */}
            <div className="pointer-events-none absolute -top-2 left-0 flex items-center gap-2">
              <span className="w-4 h-px bg-volt" />
              <span className="text-[9px] uppercase tracking-[0.32em] font-bold text-cream-base/50">
                LIVE ANALYSIS · 04 PILLARS
              </span>
            </div>
            <div className="pointer-events-none absolute -bottom-2 right-0 flex items-center gap-2">
              <span className="text-[9px] uppercase tracking-[0.32em] font-bold text-cream-base/40">
                0 ─ 10 scale
              </span>
              <span className="w-4 h-px bg-cream-base/30" />
            </div>
          </div>
        </div>
      </div>

      {/* Bottom scan-line accent */}
      <div aria-hidden className="absolute bottom-0 left-0 right-0 h-px bg-gradient-to-r from-transparent via-volt/50 to-transparent" />
    </div>
  );
}
