/**
 * FootballReport.jsx — Reusable visual primitives that give the ReportPage a
 * cinematic, football-native feel. Purely presentational: NO data/logic
 * changes. Named exports so the ReportPage can drop them in surgically.
 *
 *  PillarIcon         — SVG football icons for the 4 pillar sections
 *                       (technical / tactical / physical / mindset).
 *                       Replaces photo thumbnails per user feedback.
 *  AnimatedScore      — Count-up animated /10 score with an optional
 *                       colored ring, uses framer-motion useMotionValue.
 *  SkillMeter         — Football-styled horizontal skill bar with tick
 *                       marks per tier (Standard / Strong / Pro / Elite),
 *                       animated fill, and a "you are here" pointer.
 *  MomentCard         — Video-timestamp-linked moment tile with a small
 *                       animated play badge (used to surface video-based
 *                       moments in a horizontal scroll strip).
 *  PitchDecoration    — Small SVG chalk pitch-line ornament that can sit
 *                       under section headings to give football rhythm.
 *  TrimmedScoreGrid   — Wraps a set of AnimatedScore items into a clean
 *                       2- or 3-column grid so the "wall of numbers" the
 *                       user complained about becomes glance-able.
 */
import React, { useEffect, useRef, useState } from "react";
import {
  motion,
  useInView,
  useMotionValue,
  useTransform,
  animate,
} from "framer-motion";
import { PlayCircle } from "lucide-react";

/* ────────────────────────────────────────────────────────────────────── */
/*  PillarIcon — 4 SVG icons for the pillar headers.                       */
/* ────────────────────────────────────────────────────────────────────── */
const PILLAR_ICONS = {
  technical: (
    <svg viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
      {/* Ball */}
      <circle cx="32" cy="32" r="18" stroke="currentColor" strokeWidth="2.5" />
      <path d="M32 14 L27 24 L20 26 M32 14 L37 24 L44 26 M20 26 L22 40 L28 44 M44 26 L42 40 L36 44 M28 44 L36 44" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" />
      {/* Motion arc */}
      <path d="M50 32 Q 58 20 46 12" stroke="currentColor" strokeWidth="2" strokeDasharray="3 3" strokeLinecap="round" fill="none" />
    </svg>
  ),
  tactical: (
    <svg viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
      {/* Pitch outline */}
      <rect x="8" y="12" width="48" height="40" rx="2" stroke="currentColor" strokeWidth="2" />
      <line x1="32" y1="12" x2="32" y2="52" stroke="currentColor" strokeWidth="1.5" />
      <circle cx="32" cy="32" r="6" stroke="currentColor" strokeWidth="1.5" fill="none" />
      {/* Xs and Os for tactics */}
      <text x="16" y="26" fontSize="8" fontFamily="monospace" fontWeight="bold" fill="currentColor">X</text>
      <text x="46" y="46" fontSize="8" fontFamily="monospace" fontWeight="bold" fill="currentColor">O</text>
      {/* Arrow */}
      <path d="M20 42 L42 22 M42 22 L37 22 M42 22 L42 27" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  ),
  physical: (
    <svg viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
      {/* Lightning bolt */}
      <path d="M34 8 L18 34 L28 34 L24 56 L46 26 L34 26 L38 8 Z" stroke="currentColor" strokeWidth="2.5" strokeLinejoin="round" fill="none" />
      {/* Speed lines */}
      <path d="M8 20 L14 20" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
      <path d="M6 32 L12 32" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
      <path d="M8 44 L14 44" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  ),
  mindset: (
    <svg viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
      {/* Shield */}
      <path d="M32 8 L52 16 V 32 Q 52 46 32 56 Q 12 46 12 32 V 16 Z" stroke="currentColor" strokeWidth="2.5" strokeLinejoin="round" fill="none" />
      {/* Heart inside */}
      <path d="M32 40 C 24 34 22 28 26 24 C 29 22 32 24 32 28 C 32 24 35 22 38 24 C 42 28 40 34 32 40 Z" fill="currentColor" opacity="0.85" />
    </svg>
  ),
};

export function PillarIcon({ kind, className = "w-8 h-8 text-forest", ...rest }) {
  const svg = PILLAR_ICONS[kind] || PILLAR_ICONS.technical;
  return (
    <span
      className={`inline-flex items-center justify-center ${className}`}
      data-testid={`pillar-icon-${kind}`}
      aria-hidden="true"
      {...rest}
    >
      {svg}
    </span>
  );
}

/* ────────────────────────────────────────────────────────────────────── */
/*  AnimatedScore — count-up numeric score with optional decorative ring. */
/*  Fires the animation when the element enters the viewport.             */
/* ────────────────────────────────────────────────────────────────────── */
export function AnimatedScore({
  value,
  max = 10,
  duration = 1.4,
  className = "font-barlow font-black text-3xl md:text-4xl leading-none",
  suffix = null,
  colorClass = "text-forest",
  ring = false,
  testid,
}) {
  const ref = useRef(null);
  const inView = useInView(ref, { once: true, margin: "-40px" });
  const mv = useMotionValue(0);
  const rounded = useTransform(mv, (v) => (Number.isInteger(value) ? Math.round(v) : v.toFixed(1)));
  const [display, setDisplay] = useState("0");

  useEffect(() => {
    if (!inView) return undefined;
    const control = animate(mv, Number(value) || 0, { duration, ease: [0.22, 1, 0.36, 1] });
    const unsub = rounded.on("change", (v) => setDisplay(String(v)));
    return () => {
      control.stop();
      unsub();
    };
  }, [inView, value, duration, mv, rounded]);

  return (
    <span ref={ref} data-testid={testid} className={`relative inline-flex items-center ${ring ? "gap-3" : ""}`}>
      {ring && (
        <ScoreRing value={Number(value) || 0} max={max} colorClass={colorClass} />
      )}
      <span className="flex items-baseline">
        <span className={`${className} ${colorClass}`}>{display}</span>
        {suffix ?? <span className="text-ink/40 text-sm font-bold ml-0.5">/{max}</span>}
      </span>
    </span>
  );
}

/* ────────────────────────────────────────────────────────────────────── */
/*  ScoreRing — small circular progress ring wrapping AnimatedScore.      */
/* ────────────────────────────────────────────────────────────────────── */
function ScoreRing({ value, max = 10, colorClass = "text-forest" }) {
  const ref = useRef(null);
  const inView = useInView(ref, { once: true, margin: "-40px" });
  const size = 44;
  const stroke = 4;
  const r = (size - stroke) / 2;
  const circ = 2 * Math.PI * r;
  const pct = Math.max(0, Math.min(1, value / max));

  return (
    <span ref={ref} className={`relative inline-flex ${colorClass}`} style={{ width: size, height: size }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="-rotate-90">
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke="currentColor"
          strokeOpacity="0.15"
          strokeWidth={stroke}
        />
        <motion.circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke="currentColor"
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={circ}
          initial={{ strokeDashoffset: circ }}
          animate={inView ? { strokeDashoffset: circ * (1 - pct) } : { strokeDashoffset: circ }}
          transition={{ duration: 1.4, ease: [0.22, 1, 0.36, 1] }}
        />
      </svg>
    </span>
  );
}

/* ────────────────────────────────────────────────────────────────────── */
/*  SkillMeter — animated horizontal bar with per-tier tick marks + a     */
/*  "you are here" pointer. Replaces the flat 4-column benchmark row so   */
/*  the user gets a single glance-able progress bar per skill.            */
/* ────────────────────────────────────────────────────────────────────── */
export function SkillMeter({
  value,
  max = 10,
  tiers = ["Standard", "Strong", "Pro", "Elite"],
  currentTier,
  className = "",
}) {
  const ref = useRef(null);
  const inView = useInView(ref, { once: true, margin: "-40px" });
  const pct = Math.max(0, Math.min(1, (Number(value) || 0) / max));
  const activeTierIndex = Math.max(0, Math.min(tiers.length - 1, Math.floor(pct * tiers.length - 0.001)));
  const shownTier = currentTier || tiers[activeTierIndex];

  return (
    <div ref={ref} className={`w-full ${className}`}>
      {/* Tick labels above the bar */}
      <div className="grid grid-cols-4 gap-1 mb-1.5">
        {tiers.map((t, i) => {
          const active = t === shownTier;
          return (
            <span
              key={t}
              className={`text-[9px] uppercase tracking-[0.16em] font-bold text-center ${
                active ? "text-forest" : "text-ink/35"
              }`}
            >
              {t}
            </span>
          );
        })}
      </div>
      {/* Bar */}
      <div className="relative h-2.5 w-full bg-gray-border overflow-hidden">
        <motion.div
          className="absolute top-0 left-0 h-full bg-gradient-to-r from-forest to-forest-pop"
          initial={{ width: 0 }}
          animate={inView ? { width: `${pct * 100}%` } : { width: 0 }}
          transition={{ duration: 1.2, ease: [0.22, 1, 0.36, 1] }}
        />
        {/* Tick marks at 25/50/75 % */}
        {[0.25, 0.5, 0.75].map((t) => (
          <span
            key={t}
            aria-hidden
            className="absolute top-0 h-full w-px bg-cream-base/50"
            style={{ left: `${t * 100}%` }}
          />
        ))}
        {/* "You are here" pointer */}
        <motion.span
          aria-hidden
          className="absolute top-1/2 -translate-y-1/2 flex items-center justify-center"
          initial={{ left: 0, opacity: 0 }}
          animate={inView ? { left: `${pct * 100}%`, opacity: 1 } : { left: 0, opacity: 0 }}
          transition={{ duration: 1.2, delay: 0.4, ease: [0.22, 1, 0.36, 1] }}
          style={{ transform: "translate(-50%, -50%)" }}
        >
          <span className="w-3.5 h-3.5 bg-volt border-2 border-ink rounded-full shadow-[0_2px_6px_rgba(0,0,0,0.25)]" />
        </motion.span>
      </div>
    </div>
  );
}

/* ────────────────────────────────────────────────────────────────────── */
/*  MomentCard — video-timestamp-linked observation tile.                 */
/* ────────────────────────────────────────────────────────────────────── */
export function MomentCard({ timestamp, label, description, onSeek, tone = "forest" }) {
  const toneClass = {
    forest: "bg-forest text-white",
    volt: "bg-volt text-ink",
    ink: "bg-ink text-cream-base",
  }[tone] || "bg-forest text-white";

  return (
    <motion.button
      type="button"
      onClick={() => onSeek?.(timestamp)}
      initial={{ opacity: 0, y: 8 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-40px" }}
      transition={{ duration: 0.4 }}
      whileHover={{ y: -2 }}
      className="group relative shrink-0 w-64 md:w-72 text-left bg-cream-card border border-gray-border p-4 hover:border-forest/40 transition-all"
      data-testid={`moment-${timestamp || label}`}
    >
      <div className="flex items-start gap-3">
        <span className={`shrink-0 w-9 h-9 flex items-center justify-center ${toneClass}`}>
          <PlayCircle className="w-4 h-4" />
        </span>
        <div className="min-w-0">
          <div className="text-[10px] uppercase tracking-[0.22em] font-black text-forest">
            {formatSecs(timestamp)}
          </div>
          <div className="mt-0.5 font-barlow font-black uppercase tracking-tight text-sm text-ink leading-tight line-clamp-2">
            {label}
          </div>
        </div>
      </div>
      {description && (
        <p className="mt-2.5 text-xs text-ink/65 leading-snug line-clamp-3">{description}</p>
      )}
      {/* Hover chalk-line */}
      <span
        aria-hidden
        className="absolute bottom-0 left-0 right-0 h-[2px] bg-volt origin-left scale-x-0 group-hover:scale-x-100 transition-transform duration-300"
      />
    </motion.button>
  );
}

function formatSecs(sec) {
  const n = Number(sec) || 0;
  const m = Math.floor(n / 60);
  const s = Math.floor(n % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

/* ────────────────────────────────────────────────────────────────────── */
/*  PitchDecoration — small SVG chalk pitch-line ornament.                */
/* ────────────────────────────────────────────────────────────────────── */
export function PitchDecoration({ className = "w-24 h-10 text-forest/40" }) {
  return (
    <svg
      viewBox="0 0 120 40"
      className={className}
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
    >
      <rect x="1" y="1" width="118" height="38" stroke="currentColor" strokeWidth="1" />
      <line x1="60" y1="1" x2="60" y2="39" stroke="currentColor" strokeWidth="1" />
      <circle cx="60" cy="20" r="6" stroke="currentColor" strokeWidth="1" fill="none" />
      <rect x="1" y="10" width="14" height="20" stroke="currentColor" strokeWidth="1" fill="none" />
      <rect x="105" y="10" width="14" height="20" stroke="currentColor" strokeWidth="1" fill="none" />
    </svg>
  );
}
