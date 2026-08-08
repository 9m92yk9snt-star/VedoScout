// SNAPSHOTS — "The moments that shaped your report."
// Pixel-match of the approved reference: 4 photo cards built from real
// analyzed-video frames (timestamp + tactical annotation), a "report at a
// glance" strip and a closing quote bar. Pure presentation — all data comes
// pre-derived from derive.js (snapshotMoments + snapshot).

import React, { useState } from "react";
import { Camera, Star, Eye, Flame, Target, Sparkles, Play, ChevronRight, Quote, Info } from "lucide-react";

export const SNAP_CARD_META = {
  strength: { label: "Biggest Strength", Icon: Star, badge: "bg-[#1E5B3C] text-white", accent: "linear-gradient(90deg,#A8E10C,#1E5B3C)", title: "text-[#12211A]", glanceIcon: "text-[#1E5B3C] border-[#1E5B3C]" },
  noticed: { label: "Scout Noticed", Icon: Eye, badge: "bg-[#12211A] text-white", accent: "linear-gradient(90deg,#1E5B3C,#12402A)", title: "text-[#1E5B3C]", glanceIcon: "text-[#1E5B3C] border-[#1E5B3C]" },
  hidden: { label: "Hidden Talent", Icon: Flame, badge: "bg-[#DD6B20] text-white", accent: "linear-gradient(90deg,#F6AD55,#DD6B20)", title: "text-[#12211A]", glanceIcon: "text-[#DD6B20] border-[#DD6B20]" },
  develop: { label: "Development Area", Icon: Target, badge: "bg-[#D9534F] text-white", accent: "linear-gradient(90deg,#F1948A,#D9534F)", title: "text-[#12211A]", glanceIcon: "text-[#D9534F] border-[#D9534F]" },
};

/* Tactical overlay drawn on top of the frame. Generic presentation marks
   (movement path, scan direction, run + target, space circle) — they never
   assert facts beyond the moment's own verified text. */
export function SnapshotAnnot({ type }) {
  if (!type) return null;
  const t = type === "space" ? "circle" : type;
  return (
    <svg className="absolute inset-0 w-full h-full pointer-events-none" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden>
      {t === "path" && (
        <g stroke="#A8E10C" fill="none" strokeWidth="2" style={{ filter: "drop-shadow(0 1px 2px rgba(0,0,0,0.5))" }}>
          <polyline points="20,74 33,59 29,48 44,40" vectorEffect="non-scaling-stroke" strokeLinecap="round" strokeLinejoin="round" />
          {[[20, 74], [33, 59], [29, 48], [44, 40]].map(([x, y], i) => (
            <circle key={i} cx={x} cy={y} r="1.6" fill="#A8E10C" stroke="none" />
          ))}
          <ellipse cx="30" cy="82" rx="12" ry="4" vectorEffect="non-scaling-stroke" />
        </g>
      )}
      {t === "arrow" && (
        <g stroke="#A8E10C" fill="none" strokeWidth="2" style={{ filter: "drop-shadow(0 1px 2px rgba(0,0,0,0.5))" }}>
          <line x1="32" y1="70" x2="60" y2="46" vectorEffect="non-scaling-stroke" strokeLinecap="round" />
          <polyline points="53,44 61,45 60,53" vectorEffect="non-scaling-stroke" strokeLinecap="round" strokeLinejoin="round" />
          <circle cx="30" cy="72" r="1.6" fill="#A8E10C" stroke="none" />
        </g>
      )}
      {t === "scan" && (
        <g stroke="#FFFFFF" fill="none" strokeWidth="2" style={{ filter: "drop-shadow(0 1px 2px rgba(0,0,0,0.6))" }}>
          <line x1="56" y1="19" x2="28" y2="19" strokeDasharray="4 4" vectorEffect="non-scaling-stroke" strokeLinecap="round" />
          <polyline points="33,14 26,19 33,24" vectorEffect="non-scaling-stroke" strokeLinecap="round" strokeLinejoin="round" />
          <circle cx="59" cy="19" r="1.8" fill="#FFFFFF" stroke="none" />
        </g>
      )}
      {t === "run" && (
        <g stroke="#F6AD55" fill="none" strokeWidth="2" style={{ filter: "drop-shadow(0 1px 2px rgba(0,0,0,0.5))" }}>
          <path d="M 30,88 Q 50,62 63,36" strokeDasharray="5 4" vectorEffect="non-scaling-stroke" strokeLinecap="round" />
          <polyline points="56,38 64,34 64,43" vectorEffect="non-scaling-stroke" strokeLinecap="round" strokeLinejoin="round" />
          <circle cx="68" cy="26" r="7" strokeDasharray="4 3" vectorEffect="non-scaling-stroke" />
          <circle cx="68" cy="26" r="1.6" fill="#F6AD55" stroke="none" />
        </g>
      )}
      {t === "circle" && (
        <g stroke="#EF4444" fill="none" strokeWidth="2" style={{ filter: "drop-shadow(0 1px 2px rgba(0,0,0,0.5))" }}>
          <ellipse cx="62" cy="75" rx="15" ry="6" strokeDasharray="5 4" vectorEffect="non-scaling-stroke" />
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

const Badge = ({ meta, testid }) => (
  <span data-testid={testid} className={`absolute top-3 left-3 z-10 inline-flex items-center gap-1.5 rounded-[8px] px-2.5 py-1.5 text-[9.5px] font-extrabold tracking-[0.09em] uppercase shadow-md ${meta.badge}`}>
    <meta.Icon className="w-3 h-3" /> {meta.label}
  </span>
);

const TsPill = ({ ts }) => (
  ts ? (
    <span className="absolute top-3 right-3 z-10 bg-[#0B1F14]/85 text-white font-barlow font-black text-[12.5px] tabular-nums px-2.5 py-1 rounded-[8px]">
      {ts}
    </span>
  ) : null
);

function FeaturedCard({ moment }) {
  const meta = SNAP_CARD_META.strength;
  return (
    <div data-testid="snapshot-card-strength" className="relative rounded-[18px] overflow-hidden border border-[#E5DFCE] shadow-[0_2px_10px_rgba(30,50,35,0.08)] min-h-[320px] sm:min-h-[380px] sm:col-span-2 xl:col-span-1 flex flex-col justify-end">
      <SnapFrame thumb={moment.thumb} annot={moment.annot} Icon={meta.Icon} />
      <Badge meta={meta} testid="snapshot-badge-strength" />
      <TsPill ts={moment.timestamp} />
      <div className="relative z-10 p-5 pt-16 bg-gradient-to-t from-[#0B1F14]/95 via-[#0B1F14]/55 to-transparent">
        <div className="font-barlow font-black text-white text-[20px] md:text-[23px] leading-tight" data-testid="snapshot-title-strength">{moment.title}</div>
        <p className="text-white/85 text-[12.5px] leading-snug mt-1.5 max-w-[420px]">{moment.desc}</p>
      </div>
      <div className="relative z-10 h-[6px] w-full" style={{ background: meta.accent }} />
    </div>
  );
}

function MomentCard({ moment }) {
  const meta = SNAP_CARD_META[moment.key] || SNAP_CARD_META.noticed;
  return (
    <div data-testid={`snapshot-card-${moment.key}`} className="bg-white rounded-[18px] overflow-hidden border border-[#E5DFCE] shadow-[0_2px_10px_rgba(30,50,35,0.08)] flex flex-col">
      <div className="relative h-[210px] xl:h-[235px] shrink-0 bg-[#0B1F14]">
        <SnapFrame thumb={moment.thumb} annot={moment.annot} Icon={meta.Icon} />
        <Badge meta={meta} testid={`snapshot-badge-${moment.key}`} />
        <TsPill ts={moment.timestamp} />
      </div>
      <div className="p-4 flex-1">
        <div className={`font-barlow font-black text-[17px] leading-tight ${meta.title}`} data-testid={`snapshot-title-${moment.key}`}>{moment.title}</div>
        <p className="text-[12px] text-[#5C6657] leading-snug mt-1.5">{moment.desc}</p>
      </div>
      <div className="h-[5px] w-full" style={{ background: meta.accent }} />
    </div>
  );
}

const GLANCE_ORDER = [
  { key: "strength", label: "Biggest Strength" },
  { key: "hidden", label: "Hidden Talent" },
  { key: "develop", label: "Development Area" },
  { key: "noticed", label: "Standout Trait" },
];

export function SnapshotsSection({ snapshot, moments, demo = false, onPlayAt = null, playerName = "" }) {
  const byKey = Object.fromEntries((moments || []).map((m) => [m.key, m]));
  const order = ["strength", "noticed", "hidden", "develop"];
  const pFirst = String(playerName || "").trim().split(" ")[0];
  const your = demo ? (pFirst ? `${pFirst}'s` : "this") : "your";
  const glanceText = {
    strength: byKey.strength?.glance || snapshot?.biggestStrength,
    hidden: byKey.hidden?.glance || snapshot?.hiddenTalent,
    develop: byKey.develop?.glance || snapshot?.developmentArea,
    noticed: byKey.noticed?.glance || byKey.noticed?.title,
  };

  return (
    <div data-testid="v2-snapshots-section">
      {/* ── Header ── */}
      <div className="flex flex-col lg:flex-row lg:items-start justify-between gap-4 mb-4">
        <div className="flex items-start gap-3.5">
          <span className="w-[52px] h-[52px] rounded-[14px] bg-white border border-[#DCE8D6] flex items-center justify-center shrink-0 shadow-sm">
            <Camera className="w-6 h-6 text-[#1E5B3C]" />
          </span>
          <div>
            <h2 className="font-barlow font-black text-[30px] md:text-[38px] leading-none tracking-[0.01em] text-[#101B12] uppercase">Snapshots</h2>
            <div className="text-[14.5px] md:text-[16px] font-bold text-[#101B12] mt-1">
              The moments that shaped <span className="text-[#1E5B3C]">{your}</span> report.
            </div>
            <p className="text-[12px] text-[#5C6657] mt-0.5">We analyzed {your === "your" ? "your" : "the"} match and found 4 key moments that define {your === "your" ? "your" : "the"} game.</p>
          </div>
        </div>
        <div className="lg:max-w-[340px]">
          {demo ? (
            <div data-testid="snapshot-demo-note" className="bg-[#FFF8E9] border border-[#F0E3C4] rounded-[14px] px-4 py-3 flex gap-2.5">
              <Info className="w-4 h-4 text-[#B7791F] mt-0.5 shrink-0" />
              <div>
                <div className="text-[12px] font-extrabold text-[#8A6D3B]">Sample visuals</div>
                <p className="text-[11.5px] text-[#8A6D3B]/90 leading-snug mt-0.5">Screenshots and timestamps in this demo are example placements. In your premium report, every frame is a real moment from your own match.</p>
              </div>
            </div>
          ) : (
            <div className="relative">
              <div data-testid="snapshot-real-note" className="bg-white border border-[#E5DFCE] rounded-[14px] px-4 py-3 flex gap-2.5 shadow-sm">
                <Sparkles className="w-4 h-4 text-[#1E5B3C] mt-0.5 shrink-0" />
                <div>
                  <div className="text-[12px] font-extrabold text-[#12211A]">Real moments from your match</div>
                  <p className="text-[11.5px] text-[#5C6657] leading-snug mt-0.5">Timestamps show exact moments we found during analysis.</p>
                </div>
              </div>
              <svg width="42" height="36" viewBox="0 0 42 36" fill="none" className="hidden lg:block absolute -bottom-8 right-3" aria-hidden>
                <path d="M6 3 C 24 8, 36 16, 34 30" stroke="#1E5B3C" strokeWidth="2.4" strokeLinecap="round" fill="none" />
                <path d="M27 25 L 34 31 L 38 22" stroke="#1E5B3C" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" fill="none" />
              </svg>
            </div>
          )}
        </div>
      </div>

      {/* ── Photo cards ── */}
      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-[1.85fr_1fr_1fr_1fr] gap-4">
        {order.map((k) => {
          const m = byKey[k];
          if (!m) return null;
          return k === "strength" ? <FeaturedCard key={k} moment={m} /> : <MomentCard key={k} moment={m} />;
        })}
      </div>

      {/* ── Your report at a glance ── */}
      <div data-testid="snapshot-glance" className="mt-4 bg-[#FBF9F3] border border-[#E5DFCE] rounded-[18px] shadow-[0_2px_10px_rgba(30,50,35,0.06)] grid md:grid-cols-[190px_1fr]">
        <div className="p-5 flex items-center gap-2 border-b md:border-b-0 md:border-r border-[#EFEADB]">
          <div>
            <div className="font-barlow font-black text-[19px] leading-[1.05] text-[#12402A] uppercase">Your Report<br />At A Glance</div>
            <p className="text-[11px] text-[#5C6657] mt-1.5 leading-snug">Here&rsquo;s what our analysis discovered.</p>
          </div>
          <ChevronRight className="w-6 h-6 text-[#C9C4B4] shrink-0 hidden md:block" />
        </div>
        <div className="grid grid-cols-2 lg:grid-cols-4">
          {GLANCE_ORDER.map(({ key, label }, i) => {
            const meta = SNAP_CARD_META[key];
            const ts = byKey[key]?.timestamp;
            return (
              <div key={key} className={`px-4 py-5 text-center flex flex-col items-center ${i > 0 ? "border-l border-[#EFEADB]" : ""} ${i >= 2 ? "border-t lg:border-t-0" : ""} ${i === 2 ? "border-l-0 lg:border-l" : ""}`}>
                <span className={`w-11 h-11 rounded-full border-2 flex items-center justify-center ${meta.glanceIcon}`}>
                  <meta.Icon className="w-4.5 h-4.5" style={{ width: 18, height: 18 }} />
                </span>
                <div className={`text-[9.5px] font-extrabold tracking-[0.14em] uppercase mt-2.5 ${key === "develop" ? "text-[#D9534F]" : key === "hidden" ? "text-[#DD6B20]" : "text-[#1E5B3C]"}`}>{label}</div>
                <div className="text-[13px] font-bold text-[#12211A] leading-snug mt-1 line-clamp-2" data-testid={`snapshot-glance-text-${key}`}>{glanceText[key] || "—"}</div>
                {ts && (
                  onPlayAt ? (
                    <button
                      type="button"
                      onClick={() => onPlayAt(ts)}
                      data-testid={`snapshot-glance-see-${key}`}
                      className="mt-2 inline-flex items-center gap-1.5 text-[11px] font-extrabold text-[#12211A] hover:text-[#1E5B3C] transition-colors"
                    >
                      See moment {ts} <Play className="w-3 h-3 fill-[#1E5B3C] text-[#1E5B3C]" />
                    </button>
                  ) : (
                    <span data-testid={`snapshot-glance-see-${key}`} className="mt-2 inline-flex items-center gap-1.5 text-[11px] font-extrabold text-[#12211A]">
                      See moment {ts} <Play className="w-3 h-3 fill-[#1E5B3C] text-[#1E5B3C]" />
                    </span>
                  )
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* ── Quote bar ── */}
      <div data-testid="snapshot-quote" className="mt-4 bg-[#FBF9F3] border border-[#E5DFCE] rounded-full px-5 py-3 flex items-center gap-3 shadow-[0_2px_10px_rgba(30,50,35,0.05)]">
        <span className="w-8 h-8 rounded-full bg-[#1E5B3C] flex items-center justify-center shrink-0">
          <Quote className="w-3.5 h-3.5 text-white fill-white" />
        </span>
        <span className="text-[13px] font-semibold text-[#3C4A40]">Every moment tells a story. These are the moments that matter.</span>
      </div>
    </div>
  );
}
