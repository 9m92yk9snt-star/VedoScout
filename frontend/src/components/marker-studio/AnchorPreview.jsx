/**
 * AnchorPreview.jsx — Improvement #3 + #4 of the Trust Stack.
 *
 * Renders the "before you press DONE, here's what we'll analyse" preview
 * screen. The user sees every locked anchor with a coloured confidence
 * ring (green ≥90 %, yellow 80-89, red <80) and can:
 *
 *   • Tap any anchor to REPLACE — drops back into the MarkerStudio's
 *     manual mode pre-seeked to that timestamp so they can re-mark.
 *   • See a friendly "we need one more tap" prompt when the AI couldn't
 *     reach 3 green anchors (Improvement #4 — Smart second-tap fallback).
 *   • Press DONE — only enabled when ≥ 3 green anchors are locked.
 *
 * Props:
 *   open               (bool)             — toggle the overlay
 *   anchors            (array)            — [{ t, box, thumb, confidence, band, detail }]
 *   refAnchorT         (number)           — time of the user's first manual anchor (ground truth)
 *   onReplace          (idx => void)      — user wants to redo anchor #idx
 *   onSecondTap        (suggestedT => void) — user takes the hint and adds a 2nd tap
 *   onDone             () => void         — final submit
 *   onBack             () => void         — return to MANUAL studio
 *   suggestedTapTime   (number|null)      — recommended t for second-tap CTA
 *   enrolling          (bool)             — show "learning your kid…" if still running
 *   enrollProgress     (0..1)
 */

import React from "react";
import { Check, X, ArrowLeft, Sparkles, Loader2, Pencil, Hand } from "lucide-react";

const BAND_COLORS = {
  green: { ring: "#22C55E", text: "#22C55E", bg: "rgba(34,197,94,0.12)" },
  yellow: { ring: "#FACC15", text: "#FACC15", bg: "rgba(250,204,21,0.12)" },
  red: { ring: "#F87171", text: "#F87171", bg: "rgba(248,113,113,0.14)" },
};

function ConfidenceRing({ score, band, size = 64 }) {
  const c = BAND_COLORS[band] || BAND_COLORS.red;
  const stroke = 4;
  const r = (size - stroke) / 2;
  const circ = 2 * Math.PI * r;
  const pct = Math.max(0, Math.min(1, score || 0));
  const dash = circ * pct;
  return (
    <svg width={size} height={size} className="absolute -top-2 -right-2 drop-shadow-lg">
      <circle
        cx={size / 2}
        cy={size / 2}
        r={r}
        fill="rgba(10,15,13,0.85)"
        stroke="rgba(255,255,255,0.15)"
        strokeWidth={stroke}
      />
      <circle
        cx={size / 2}
        cy={size / 2}
        r={r}
        fill="none"
        stroke={c.ring}
        strokeWidth={stroke}
        strokeDasharray={`${dash} ${circ - dash}`}
        strokeLinecap="round"
        transform={`rotate(-90 ${size / 2} ${size / 2})`}
      />
      <text
        x="50%"
        y="51%"
        textAnchor="middle"
        dominantBaseline="middle"
        style={{
          fill: c.text,
          fontFamily: "'Barlow', sans-serif",
          fontWeight: 900,
          fontSize: 14,
          letterSpacing: 0.5,
        }}
      >
        {Math.round(pct * 100)}
      </text>
    </svg>
  );
}

function AnchorCard({ anchor, idx, onReplace, isRef }) {
  const band = anchor.band || "red";
  const score = anchor.confidence ?? 0;
  return (
    <div
      className="relative overflow-hidden border border-white/20 bg-white/8"
      style={{ minHeight: 200, boxShadow: "0 10px 24px rgba(0,0,0,0.4)" }}
      data-testid={`ms-preview-anchor-${idx}`}
    >
      {anchor.thumb && (
        <img
          src={anchor.thumb}
          alt={`Anchor ${idx + 1}`}
          className="absolute inset-0 w-full h-full object-cover"
          draggable={false}
        />
      )}
      {/* Dim overlay for readability */}
      <div className="absolute inset-0 bg-gradient-to-b from-black/10 via-transparent to-black/80 pointer-events-none" />

      {/* Anchor # + time */}
      <div className="absolute top-2 left-2 flex items-center gap-1.5">
        <span className="bg-[#CCFF00] text-ink font-black text-base leading-none px-2 py-0.5">
          #{idx + 1}
        </span>
        <span className="text-white text-[11px] font-bold tabular-nums bg-ink/85 px-1.5 py-0.5">
          {formatTime(anchor.t)}
        </span>
        {isRef && (
          <span
            className="text-[8px] uppercase tracking-widest font-black bg-[#CCFF00] text-ink px-1.5 py-0.5"
            title="Your original tap — the ground truth we matched against"
          >
            Your tap
          </span>
        )}
      </div>

      {/* Confidence ring */}
      {!isRef && <ConfidenceRing score={score} band={band} />}
      {isRef && (
        <div className="absolute -top-2 -right-2 w-14 h-14 rounded-full bg-[#CCFF00] flex items-center justify-center shadow-lg">
          <Hand className="w-6 h-6 text-ink" />
        </div>
      )}

      {/* Footer + replace */}
      <div className="absolute bottom-0 left-0 right-0 p-2">
        <div className="text-white text-[13px] font-bold leading-tight mb-1">
          {isRef
            ? "Locked from your tap"
            : band === "green"
            ? "Strong match"
            : band === "yellow"
            ? "Decent match"
            : "Weak — replace this"}
        </div>
        {!isRef && (
          <button
            type="button"
            data-testid={`ms-preview-replace-${idx}`}
            onClick={() => onReplace?.(idx)}
            className={`w-full py-1.5 px-2 text-[10px] uppercase tracking-widest font-black transition-colors ${
              band === "red"
                ? "bg-[#F87171] text-ink hover:bg-[#FCA5A5]"
                : "bg-white/15 text-white hover:bg-white/25"
            }`}
          >
            <Pencil className="w-3 h-3 inline -mt-0.5 mr-1" />
            Replace
          </button>
        )}
      </div>
    </div>
  );
}

function formatTime(s) {
  const t = Math.max(0, s | 0);
  const mm = String(Math.floor(t / 60)).padStart(2, "0");
  const ss = String(t % 60).padStart(2, "0");
  return `${mm}:${ss}`;
}

export default function AnchorPreview({
  open,
  anchors,
  refAnchorT,
  onReplace,
  onSecondTap,
  onDone,
  onBack,
  suggestedTapTime,
  enrolling,
  enrollProgress,
}) {
  if (!open) return null;

  // Sort by time ascending for display, but mark which one was the user's
  // original tap so we never let them "replace" the ground-truth anchor.
  const sorted = [...anchors].sort((a, b) => a.t - b.t);
  const refIdx = sorted.findIndex(
    (a) => Math.abs(a.t - (refAnchorT ?? -999)) < 0.05,
  );

  const greenCount = sorted.filter((a) => (a.confidence ?? 0) >= 0.90).length;
  const yellowCount = sorted.filter(
    (a) => (a.confidence ?? 0) >= 0.80 && (a.confidence ?? 0) < 0.90,
  ).length;
  const doneAllowed = greenCount >= 3;
  const needsSecondTap = !doneAllowed && !enrolling && suggestedTapTime != null;

  return (
    <div
      className="absolute inset-0 z-[220] flex flex-col bg-ink/97 backdrop-blur-md text-white"
      data-testid="ms-preview-overlay"
      style={{ paddingTop: 50 /* leave space for the top bar */ }}
    >
      {/* Header */}
      <div className="px-4 pt-3 pb-3 border-b border-white/10">
        <div className="flex items-center justify-between gap-2">
          <button
            type="button"
            onClick={onBack}
            data-testid="ms-preview-back"
            className="w-9 h-9 flex items-center justify-center bg-white/10 hover:bg-white/20"
            aria-label="Back to studio"
          >
            <ArrowLeft className="w-4 h-4" />
          </button>
          <div className="flex-1 text-center">
            <div className="text-[10px] uppercase tracking-[0.32em] font-black text-[#CCFF00]">
              Preview before analysis
            </div>
            <div className="text-white font-black text-lg mt-0.5 leading-tight">
              {doneAllowed
                ? "All set — ready to analyse"
                : enrolling
                ? "Learning your kid…"
                : "Almost there — review your anchors"}
            </div>
          </div>
          <div className="w-9 h-9" />
        </div>
        {/* Trust strip */}
        <div className="mt-2 flex items-center justify-center gap-3 text-[11px] font-bold tabular-nums">
          <span className="flex items-center gap-1 text-[#22C55E]">
            <span className="inline-block w-2 h-2 rounded-full bg-[#22C55E]" />
            {greenCount} green
          </span>
          <span className="flex items-center gap-1 text-[#FACC15]">
            <span className="inline-block w-2 h-2 rounded-full bg-[#FACC15]" />
            {yellowCount} yellow
          </span>
          <span className="flex items-center gap-1 text-[#F87171]">
            <span className="inline-block w-2 h-2 rounded-full bg-[#F87171]" />
            {sorted.length - greenCount - yellowCount} red
          </span>
        </div>
      </div>

      {/* Enrollment progress (Improvement #1 finishing) */}
      {enrolling && (
        <div className="px-4 pt-3" data-testid="ms-preview-enrolling">
          <div className="text-[12px] text-white/80 mb-2">
            Tracking your kid across {Math.round((enrollProgress || 0) * 100)} %
            of the surrounding seconds…
          </div>
          <div className="h-1 bg-white/12 overflow-hidden">
            <div
              className="h-full bg-[#CCFF00] transition-all"
              style={{ width: `${(enrollProgress || 0) * 100}%` }}
            />
          </div>
        </div>
      )}

      {/* Anchor grid */}
      <div className="flex-1 overflow-y-auto px-4 py-3">
        <div
          className="grid grid-cols-2 sm:grid-cols-3 gap-3"
          data-testid="ms-preview-grid"
        >
          {sorted.map((a, i) => (
            <AnchorCard
              key={`${a.t}-${i}`}
              anchor={a}
              idx={i}
              onReplace={onReplace}
              isRef={i === refIdx}
            />
          ))}
        </div>

        {/* Empty state */}
        {!sorted.length && !enrolling && (
          <div className="py-10 text-center text-white/65 text-sm">
            No anchors yet. Go back and mark your kid first.
          </div>
        )}
      </div>

      {/* Second-tap CTA (Improvement #4) */}
      {needsSecondTap && (
        <div
          className="border-t border-white/10 bg-[#1A1F1C] px-4 py-3"
          data-testid="ms-preview-second-tap"
        >
          <div className="flex items-start gap-3">
            <div className="flex-shrink-0 w-10 h-10 rounded-full bg-[#CCFF00] flex items-center justify-center">
              <Hand className="w-5 h-5 text-ink" />
            </div>
            <div className="flex-1">
              <div className="text-white font-black text-[14px]">
                One more tap will lock it in
              </div>
              <p className="text-white/70 text-[12px] mt-0.5 leading-snug">
                We&apos;re not 100&nbsp;% sure on{" "}
                {sorted.length - greenCount - yellowCount + yellowCount} of the
                anchors. Try tapping your kid around{" "}
                <span className="font-bold text-[#CCFF00]">
                  {formatTime(suggestedTapTime)}
                </span>{" "}
                — we&apos;ll re-run with double the reference data.
              </p>
              <button
                type="button"
                onClick={() => onSecondTap?.(suggestedTapTime)}
                data-testid="ms-preview-take-second-tap"
                className="mt-2 w-full py-2.5 bg-[#CCFF00] text-ink font-black text-[12px] uppercase tracking-widest hover:bg-[#CCFF00]/90 transition-colors"
              >
                <Sparkles className="w-3.5 h-3.5 inline -mt-0.5 mr-1" />
                Take me to {formatTime(suggestedTapTime)}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Footer — DONE only when ≥3 green */}
      <div className="border-t border-white/10 px-4 py-3 bg-ink space-y-2">
        <button
          type="button"
          onClick={onDone}
          disabled={!doneAllowed || enrolling}
          data-testid="ms-preview-done"
          className={`w-full h-12 flex items-center justify-center gap-2 text-[13px] uppercase tracking-widest font-black transition-all ${
            doneAllowed && !enrolling
              ? "bg-[#CCFF00] text-ink hover:bg-[#CCFF00]/90 shadow-[0_0_22px_rgba(204,255,0,0.45)]"
              : "bg-white/8 text-white/40 cursor-not-allowed"
          }`}
        >
          {enrolling ? (
            <>
              <Loader2 className="w-5 h-5 animate-spin" />
              Learning your kid…
            </>
          ) : doneAllowed ? (
            <>
              <Check className="w-5 h-5" />
              Done · analyse {sorted.length} moments
            </>
          ) : (
            <>
              <X className="w-4 h-4" />
              Need ≥ 3 strong anchors ({greenCount}/3)
            </>
          )}
        </button>
        <p className="text-[10px] text-white/45 text-center">
          {doneAllowed
            ? "You can still replace any anchor before pressing Done."
            : "Replace red anchors with your own tap to lock them in."}
        </p>
      </div>
    </div>
  );
}
