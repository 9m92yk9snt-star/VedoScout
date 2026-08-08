// SNAPSHOT — "The key moments we found in your match."
// Pixel-match of the approved reference: cream section card, 2×2 moment cards
// (colored header bar with category + timestamp, real frame with tactical
// annotation, title + description) and an OVERALL PROGRESS strip.
// Pure presentation — all data comes pre-derived from derive.js.

import React, { useState } from "react";
import { Camera, Star, Eye, Flame, Target, TrendingUp } from "lucide-react";

export const SNAP_CARD_META = {
  strength: { label: "Biggest Strength", Icon: Star, header: "linear-gradient(90deg,#1E3D25,#2E5435)" },
  noticed: { label: "Scout Noticed", Icon: Eye, header: "linear-gradient(90deg,#1E3D25,#2E5435)" },
  hidden: { label: "Hidden Talent", Icon: Flame, header: "linear-gradient(90deg,#7A4A10,#B26D1C)" },
  develop: { label: "Biggest Development Area", Icon: Target, header: "linear-gradient(90deg,#5E1D1B,#98322B)" },
};

/* Tactical overlay drawn on top of the frame. Generic presentation marks
   (movement arrow, scan direction, run + target, space circle) — they never
   assert facts beyond the moment's own verified text. */
export function SnapshotAnnot({ type }) {
  if (!type) return null;
  const t = type === "space" ? "circle" : type;
  return (
    <svg className="absolute inset-0 w-full h-full pointer-events-none" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden>
      {(t === "path" || t === "arrow") && (
        <g stroke="#7ED321" fill="none" strokeWidth="2" style={{ filter: "drop-shadow(0 1px 2px rgba(0,0,0,0.5))" }}>
          <line x1="38" y1="64" x2="58" y2="46" vectorEffect="non-scaling-stroke" strokeLinecap="round" />
          <polyline points="51,44 59,45 57,53" vectorEffect="non-scaling-stroke" strokeLinecap="round" strokeLinejoin="round" />
          {t === "path" && (
            <ellipse cx="30" cy="78" rx="16" ry="6" strokeDasharray="2.2 1.8" vectorEffect="non-scaling-stroke" />
          )}
        </g>
      )}
      {t === "scan" && (
        <g stroke="#FFFFFF" fill="none" strokeWidth="2" style={{ filter: "drop-shadow(0 1px 2px rgba(0,0,0,0.6))" }}>
          <line x1="72" y1="21" x2="46" y2="21" strokeDasharray="1.8 1.8" vectorEffect="non-scaling-stroke" strokeLinecap="round" />
          <polyline points="51,16 44,21 51,26" vectorEffect="non-scaling-stroke" strokeLinecap="round" strokeLinejoin="round" />
          <circle cx="75" cy="21" r="1.8" fill="#FFFFFF" stroke="none" />
        </g>
      )}
      {t === "run" && (
        <g stroke="#F5A623" fill="none" strokeWidth="2" style={{ filter: "drop-shadow(0 1px 2px rgba(0,0,0,0.5))" }}>
          <path d="M 20,82 Q 42,64 58,38" strokeDasharray="2.2 1.8" vectorEffect="non-scaling-stroke" strokeLinecap="round" />
          <polyline points="51,40 59,36 59,45" vectorEffect="non-scaling-stroke" strokeLinecap="round" strokeLinejoin="round" />
          <circle cx="64" cy="28" r="7" strokeDasharray="2 1.6" vectorEffect="non-scaling-stroke" />
        </g>
      )}
      {t === "circle" && (
        <g stroke="#E8442E" fill="none" strokeWidth="2" style={{ filter: "drop-shadow(0 1px 2px rgba(0,0,0,0.5))" }}>
          <ellipse cx="60" cy="78" rx="17" ry="6.5" strokeDasharray="2.2 1.8" vectorEffect="non-scaling-stroke" />
        </g>
      )}
    </svg>
  );
}

/* Frame image with graceful stylized-pitch fallback (real reports without a
   verified frame never show an invented photo). */
export function SnapFrame({ thumb, annot, Icon }) {
  const [err, setErr] = useState(false);
  const show = !!thumb && !err;
  return (
    <div className="absolute inset-0" aria-hidden>
      {show ? (
        <img src={thumb} alt="" onError={() => setErr(true)} className="absolute inset-0 w-full h-full object-cover" />
      ) : (
        <div className="absolute inset-0" style={{ background: "linear-gradient(160deg,#1B4430,#0B1F14)" }}>
          <div className="absolute left-0 right-0 top-1/2 h-px bg-white/10" />
          <div className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 w-24 h-24 rounded-full border border-white/10" />
          {Icon && <Icon className="absolute inset-0 m-auto w-12 h-12 text-white/15" />}
        </div>
      )}
      <SnapshotAnnot type={annot} />
    </div>
  );
}

function SnapCard({ moment }) {
  const meta = SNAP_CARD_META[moment.key] || SNAP_CARD_META.noticed;
  return (
    <div data-testid={`snapshot-card-${moment.key}`} className="rounded-[16px] overflow-hidden border border-[#E5DFCE] bg-[#FBFAF2] shadow-[0_3px_14px_rgba(30,50,35,0.08)] flex flex-col">
      <div className="flex items-center gap-2.5 px-4 h-[44px] text-white shrink-0" style={{ background: meta.header }}>
        <meta.Icon className="w-4 h-4 shrink-0" />
        <span className="text-[11.5px] md:text-[12px] font-extrabold tracking-[0.07em] uppercase truncate" data-testid={`snapshot-badge-${moment.key}`}>{meta.label}</span>
        {moment.timestamp && (
          <>
            <span className="ml-auto w-px h-5 bg-white/25 shrink-0" />
            <span className="font-barlow font-black text-[15px] tabular-nums shrink-0" data-testid={`snapshot-ts-${moment.key}`}>{moment.timestamp}</span>
          </>
        )}
      </div>
      <div className="relative h-[200px] md:h-[245px] bg-[#0B1F14] shrink-0">
        <SnapFrame thumb={moment.thumb} annot={moment.annot} Icon={meta.Icon} />
      </div>
      <div className="px-5 py-4 flex-1">
        <div className="text-[18px] md:text-[20px] font-extrabold text-[#12211A] leading-snug" data-testid={`snapshot-title-${moment.key}`}>{moment.title}</div>
        <p className="text-[13px] text-[#5C6657] leading-relaxed mt-1.5">{moment.desc}</p>
      </div>
    </div>
  );
}

const ORDER = ["strength", "noticed", "hidden", "develop"];

export function SnapshotsSection({ snapshot, moments, demo = false, playerName = "" }) {
  const byKey = Object.fromEntries((moments || []).map((m) => [m.key, m]));
  const pFirst = String(playerName || "").trim().split(" ")[0];
  const who = demo ? (pFirst ? `${pFirst}'s` : "this") : "your";

  return (
    <div data-testid="v2-snapshots-section" className="bg-[#F6F3E8] border border-[#E5DFCE] rounded-[22px] p-4 md:p-6 shadow-[0_2px_10px_rgba(30,50,35,0.05)]">
      {/* ── Header ── */}
      <div className="flex items-start gap-4 mb-5">
        <span className="w-[52px] h-[52px] rounded-[15px] bg-[#E9F1E6] flex items-center justify-center shrink-0">
          <Camera className="w-6 h-6 text-[#1E5B3C]" />
        </span>
        <div className="min-w-0">
          <h2 className="font-barlow font-black text-[28px] md:text-[34px] leading-none tracking-[0.01em] text-[#101B12] uppercase">Snapshot</h2>
          <p className="text-[14px] md:text-[15.5px] text-[#3C4A40] mt-1">
            The key moments we found in <span className="text-[#1E5B3C] font-semibold">{who}</span> match.
          </p>
          {demo && (
            <p data-testid="snapshot-demo-note" className="text-[11.5px] text-[#8A6D3B] mt-1 leading-snug">
              Sample visuals — screenshots and timestamps in this demo are example placements. In your premium report, every frame is a real moment from your own match.
            </p>
          )}
        </div>
      </div>

      {/* ── 2×2 moment cards ── */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 md:gap-5">
        {ORDER.map((k) => (byKey[k] ? <SnapCard key={k} moment={byKey[k]} /> : null))}
      </div>

      {/* ── Overall progress ── */}
      <div data-testid="snapshot-progress" className="mt-4 md:mt-5 bg-[#EAF2E3] border border-[#D8E6D2] rounded-[16px] px-5 py-4 flex flex-col sm:flex-row sm:items-center gap-3 sm:gap-5">
        <div className="flex items-center gap-3 shrink-0">
          <span className="font-barlow font-black text-[17px] leading-[1.1] text-[#1E5B3C] uppercase">Overall<br />Progress</span>
          <TrendingUp className="w-6 h-6 text-[#1E5B3C] shrink-0" />
        </div>
        <span className="hidden sm:block w-px self-stretch bg-[#C9DBC0]" aria-hidden />
        <div className="min-w-0">
          <div className="text-[16px] md:text-[17px] font-extrabold text-[#12211A] leading-snug" data-testid="snapshot-progress-note">{snapshot?.progressNote}</div>
          <p className="text-[12.5px] text-[#5C6657] mt-0.5">Keep working and enjoying the game.</p>
        </div>
      </div>
    </div>
  );
}
