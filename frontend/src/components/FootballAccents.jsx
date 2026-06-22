/**
 * FootballAccents.jsx — tiny reusable SVG decorations that add football flavour
 * to the report / dashboard pages WITHOUT changing any existing layout.
 *
 * Every export is a pure SVG component (no state, no measurement) so they slot
 * into existing flex/grid rows like an emoji. Size + colour are controlled via
 * standard className props (`w-3 h-3 text-forest` etc.).
 */
import React from "react";

/* ─────────────────────────────────────────────────────────────────────────
 *  FootballIcon — a clean monoline football used in place of generic stars.
 * ────────────────────────────────────────────────────────────────────────── */
export function FootballIcon({ className = "w-3 h-3", filled = false }) {
  return (
    <svg viewBox="0 0 24 24" className={className} fill="none" stroke="currentColor" strokeWidth={1.6} aria-hidden>
      <circle cx="12" cy="12" r="9.5" fill={filled ? "currentColor" : "none"} />
      {/* Classic football pentagon — drawn lightly so it works at 12 px too. */}
      <path
        d="M12 5.5 L15.7 8.4 L14.3 12.8 L9.7 12.8 L8.3 8.4 Z"
        fill={filled ? "rgba(255,255,255,0.85)" : "none"}
        stroke="currentColor"
        strokeWidth={filled ? 0 : 1.4}
      />
      <path d="M12 5.5 L12 2.5" />
      <path d="M15.7 8.4 L18.6 6.4" />
      <path d="M14.3 12.8 L17.5 15.8" />
      <path d="M9.7 12.8 L6.5 15.8" />
      <path d="M8.3 8.4 L5.4 6.4" />
    </svg>
  );
}

/* ─────────────────────────────────────────────────────────────────────────
 *  MiniPitch — a tiny 28×40 pitch sketch with a glowing position-marker dot.
 *  Maps loose position names to normalised x/y on a portrait pitch.
 * ────────────────────────────────────────────────────────────────────────── */
const POSITION_MAP = {
  // y goes from 0 (top = attacking) to 1 (bottom = own goal)
  goalkeeper: { x: 0.5, y: 0.92 }, gk: { x: 0.5, y: 0.92 },
  "centre-back": { x: 0.5, y: 0.78 }, "center-back": { x: 0.5, y: 0.78 }, cb: { x: 0.5, y: 0.78 }, defender: { x: 0.5, y: 0.78 },
  "left-back": { x: 0.18, y: 0.78 }, lb: { x: 0.18, y: 0.78 }, "left back": { x: 0.18, y: 0.78 },
  "right-back": { x: 0.82, y: 0.78 }, rb: { x: 0.82, y: 0.78 }, "right back": { x: 0.82, y: 0.78 },
  "defensive midfielder": { x: 0.5, y: 0.62 }, cdm: { x: 0.5, y: 0.62 },
  midfielder: { x: 0.5, y: 0.5 }, "central midfielder": { x: 0.5, y: 0.5 }, cm: { x: 0.5, y: 0.5 },
  "attacking midfielder": { x: 0.5, y: 0.35 }, cam: { x: 0.5, y: 0.35 }, "no. 10": { x: 0.5, y: 0.35 },
  "left winger": { x: 0.18, y: 0.25 }, lw: { x: 0.18, y: 0.25 }, "left wing": { x: 0.18, y: 0.25 },
  "right winger": { x: 0.82, y: 0.25 }, rw: { x: 0.82, y: 0.25 }, "right wing": { x: 0.82, y: 0.25 },
  striker: { x: 0.5, y: 0.13 }, st: { x: 0.5, y: 0.13 }, forward: { x: 0.5, y: 0.13 }, "centre forward": { x: 0.5, y: 0.13 },
};

export function positionToCoord(position) {
  if (!position) return { x: 0.5, y: 0.5 };
  const key = String(position).trim().toLowerCase();
  return POSITION_MAP[key] || POSITION_MAP[key.replace(/-/g, " ")] || { x: 0.5, y: 0.5 };
}

/**
 * <MiniPitch position="Attacking Midfielder" /> renders a 28×40 pitch SVG with
 * a glowing lime dot at the matched position. Sized via `className`. Used as a
 * decoration next to position labels — purely visual, doesn't replace text.
 */
export function MiniPitch({ position, className = "w-7 h-10" }) {
  const { x, y } = positionToCoord(position);
  return (
    <svg viewBox="0 0 28 40" className={className} aria-hidden>
      {/* Pitch background — soft forest fill so it matches cream theme. */}
      <rect x="1" y="1" width="26" height="38" rx="1.5" fill="#1F4F2F" opacity="0.92" />
      {/* Outer line */}
      <rect x="1.5" y="1.5" width="25" height="37" rx="1.5" fill="none" stroke="rgba(255,255,255,0.55)" strokeWidth="0.6" />
      {/* Halfway line */}
      <line x1="1.5" y1="20" x2="26.5" y2="20" stroke="rgba(255,255,255,0.45)" strokeWidth="0.5" />
      {/* Centre circle */}
      <circle cx="14" cy="20" r="3" fill="none" stroke="rgba(255,255,255,0.4)" strokeWidth="0.5" />
      <circle cx="14" cy="20" r="0.6" fill="rgba(255,255,255,0.55)" />
      {/* Top penalty box (attack) */}
      <rect x="8.5" y="1.5" width="11" height="4" fill="none" stroke="rgba(255,255,255,0.4)" strokeWidth="0.5" />
      <rect x="11" y="1.5" width="6" height="1.5" fill="none" stroke="rgba(255,255,255,0.4)" strokeWidth="0.5" />
      {/* Bottom penalty box (own goal) */}
      <rect x="8.5" y="34.5" width="11" height="4" fill="none" stroke="rgba(255,255,255,0.4)" strokeWidth="0.5" />
      <rect x="11" y="37" width="6" height="1.5" fill="none" stroke="rgba(255,255,255,0.4)" strokeWidth="0.5" />
      {/* Glowing position dot */}
      <circle cx={2 + x * 24} cy={2 + y * 36} r="2.4" fill="#CCFF00" opacity="0.25" />
      <circle cx={2 + x * 24} cy={2 + y * 36} r="1.5" fill="#CCFF00" stroke="#0A0F0D" strokeWidth="0.4" />
    </svg>
  );
}

/* ─────────────────────────────────────────────────────────────────────────
 *  PitchLineDivider — three short white "chalk" lines used as a decorative
 *  divider above section headers. Renders inline like a tiny SVG separator.
 * ────────────────────────────────────────────────────────────────────────── */
export function PitchLineDivider({ className = "w-12 h-2" }) {
  return (
    <svg viewBox="0 0 60 8" className={className} aria-hidden>
      <line x1="0" y1="4" x2="20" y2="4" stroke="currentColor" strokeWidth="1.2" />
      <circle cx="26" cy="4" r="2" fill="none" stroke="currentColor" strokeWidth="1.2" />
      <line x1="32" y1="4" x2="60" y2="4" stroke="currentColor" strokeWidth="1.2" />
    </svg>
  );
}

/* ─────────────────────────────────────────────────────────────────────────
 *  JerseyChip — a numbered shirt-style chip used to brand strength bullets.
 *  Replaces the plain numbered circle without changing existing JSX shape.
 * ────────────────────────────────────────────────────────────────────────── */
export function JerseyChip({ number, className = "", muted = false }) {
  return (
    <span
      className={
        "relative inline-flex items-center justify-center font-barlow font-black tabular-nums " +
        className
      }
    >
      {/* The jersey silhouette behind the number. */}
      <svg viewBox="0 0 32 32" className="absolute inset-0 w-full h-full" aria-hidden>
        <path
          d="M5 8 L11 4 L13 6 L19 6 L21 4 L27 8 L25 14 L21 13 L21 28 L11 28 L11 13 L7 14 Z"
          fill={muted ? "rgba(31,79,47,0.4)" : "#1F4F2F"}
          stroke={muted ? "rgba(31,79,47,0.5)" : "#0A2A18"}
          strokeWidth="0.8"
        />
      </svg>
      <span className={muted ? "relative text-cream-card/85 text-[11px]" : "relative text-cream-card text-[11px]"}>
        {number}
      </span>
    </span>
  );
}

/* ─────────────────────────────────────────────────────────────────────────
 *  GrassTexture — a subtle horizontal grass-stripe pattern used as a
 *  background accent on certain cards (kept very faint to remain premium).
 * ────────────────────────────────────────────────────────────────────────── */
export function GrassStripes({ className = "absolute inset-0 pointer-events-none opacity-[0.06]" }) {
  return (
    <div
      className={className}
      style={{
        backgroundImage:
          "repeating-linear-gradient(180deg, #1F4F2F 0px, #1F4F2F 14px, transparent 14px, transparent 28px)",
      }}
      aria-hidden
    />
  );
}
