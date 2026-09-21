// Development Curve — automatic progress comparison across a player's reports.
// Pure math on existing scores (computed backend-side in progression.py).
import React from "react";
import { TrendingUp, ArrowUpRight, ArrowRight, ArrowDownRight, Trophy, Eye } from "lucide-react";
import { V2Card, V2Title } from "./sections";

const DIR = {
  up: { Icon: ArrowUpRight, color: "#1E5B3C", bg: "#E9F1E6" },
  flat: { Icon: ArrowRight, color: "#5B695E", bg: "#F1EFE6" },
  down: { Icon: ArrowDownRight, color: "#DD6B20", bg: "#FDF3EA" },
};

const CURVE_KEYS = [
  { key: "overall", label: "Overall", color: "#CCFF00", width: 2.4 },
  { key: "technical", label: "Technical", color: "#7BA05B", width: 1.1 },
  { key: "tactical", label: "Tactical", color: "#E8B32C", width: 1.1 },
  { key: "physical", label: "Physical", color: "#7FB6C9", width: 1.1 },
  { key: "mentality", label: "Mentality", color: "#DE8A5A", width: 1.1 },
];

function DeltaChip({ c }) {
  const isOverall = c.key === "overall_development";
  const { Icon, color } = DIR[c.dir] || DIR.flat;
  return (
    <div
      data-testid={`v2-prog-cat-${c.key}`}
      className={`rounded-[11px] border p-3 text-center ${isOverall ? "bg-[#12402A] border-[#12402A]" : "bg-[#FBF9F3] border-[#E5DFCE]"}`}
    >
      <div className={`text-[9px] font-extrabold tracking-[0.12em] uppercase ${isOverall ? "text-[#A9BC9C]" : "text-[#75816F]"}`}>{c.label}</div>
      <div className={`font-barlow font-black text-[19px] mt-1 leading-none tabular-nums ${isOverall ? "text-white" : "text-[#101B12]"}`}>
        {c.prev.toFixed(1)} <span className={isOverall ? "text-[#A9BC9C]" : "text-[#C4BFA8]"}>→</span> {c.cur.toFixed(1)}
      </div>
      <div className="flex items-center justify-center gap-1 mt-1.5" style={{ color: isOverall ? "#CCFF00" : color }}>
        <Icon className="w-3.5 h-3.5" />
        <span className="text-[11px] font-extrabold tabular-nums">
          {c.dir === "flat" ? "stable" : `${c.delta > 0 ? "+" : ""}${c.delta.toFixed(1)}`}
        </span>
      </div>
    </div>
  );
}

function ProgressCurve({ series }) {
  const W2 = 640, H2 = 190, L = 34, R = 12, T = 12, B = 30;
  const n = series.length;
  const vals = series.flatMap((s) => ["technical", "tactical", "physical", "mentality", "overall"].map((k) => s[k]).filter((v) => v != null));
  let lo = Math.max(0, Math.floor(Math.min(...vals) - 1));
  let hi = Math.min(10, Math.ceil(Math.max(...vals) + 1));
  if (hi - lo < 3) lo = Math.max(0, hi - 3);
  const grid = [];
  for (let g = lo; g <= hi; g++) grid.push(g);
  const X = (i) => L + (i * (W2 - L - R)) / Math.max(1, n - 1);
  const Y = (v) => T + ((hi - Math.max(lo, Math.min(hi, v))) * (H2 - T - B)) / (hi - lo);
  return (
    <div>
      <svg viewBox={`0 0 ${W2} ${H2}`} className="w-full rounded-[10px]" data-testid="v2-prog-curve" style={{ background: "#0D2818" }}>
        {grid.map((g) => (
          <g key={g}>
            <line x1={L} y1={Y(g)} x2={W2 - R} y2={Y(g)} stroke="#1D4230" strokeWidth="0.7" />
            <text x={L - 6} y={Y(g) + 3} fill="#5F7A66" fontSize="8" textAnchor="end" fontWeight="700">{g}</text>
          </g>
        ))}
        {CURVE_KEYS.map(({ key, color, width }) => {
          const pts = series.map((s, i) => (s[key] != null ? `${X(i)},${Y(s[key])}` : null)).filter(Boolean);
          if (pts.length < 2) return null;
          return <polyline key={key} points={pts.join(" ")} fill="none" stroke={color} strokeWidth={width} strokeLinecap="round" strokeLinejoin="round" />;
        })}
        {series.map((s, i) => (s.overall != null ? (
          <circle key={i} cx={X(i)} cy={Y(s.overall)} r="3" fill="#CCFF00" stroke="#0D2818" strokeWidth="1.2" />
        ) : null))}
        {series.map((s, i) => (
          <text key={`l${i}`} x={X(i)} y={H2 - 10} fill="#8FA896" fontSize="8.5" textAnchor="middle" fontWeight="700">{s.label}</text>
        ))}
      </svg>
      <div className="flex flex-wrap gap-x-4 gap-y-1 mt-2">
        {CURVE_KEYS.map(({ key, label, color }) => (
          <span key={key} className="flex items-center gap-1.5 text-[10px] font-extrabold tracking-[0.06em] uppercase text-[#75816F]">
            <span className="w-2.5 h-2.5 rounded-full" style={{ background: color, border: key === "overall" ? "1px solid #9CB89A" : "none" }} />
            {label}
          </span>
        ))}
      </div>
    </div>
  );
}

export function ProgressCard({ prog }) {
  if (!prog?.categories?.length) return null;
  const showCurve = (prog.series || []).filter((s) => s.overall != null).length >= 3;
  const rightChip = `ANALYSIS #${prog.analysis_number}${prog.prev_date_label ? ` · SINCE ${prog.prev_date_label}` : ""}${prog.days_since != null ? ` (${prog.days_since} DAYS)` : ""}`;
  return (
    <V2Card testid="v2-progress-card">
      <V2Title icon={TrendingUp} right={<span className="text-[10px] font-extrabold tracking-[0.14em] text-[#CCFF00] bg-[#12402A] px-2.5 py-1 rounded-[5px] hidden md:block">{rightChip}</span>}>
        Development Curve
      </V2Title>
      <div className="grid grid-cols-2 sm:grid-cols-5 gap-2.5 mb-4">
        {prog.categories.map((c) => <DeltaChip key={c.key} c={c} />)}
      </div>
      <div className={`grid gap-4 ${prog.watch?.length ? "md:grid-cols-[1.15fr_1fr]" : ""} mb-1`}>
        {prog.improvements?.length > 0 && (
          <div className="bg-[#F0F5EC] border border-[#DCE8D6] rounded-[12px] p-4">
            <div className="flex items-center gap-1.5 text-[11px] font-extrabold tracking-[0.12em] text-[#12402A] mb-2.5">
              <Trophy className="w-3.5 h-3.5 text-[#E8B32C]" /> BIGGEST IMPROVEMENTS
            </div>
            {prog.improvements.map((im, i) => (
              <div key={im.key} data-testid={`v2-prog-improve-${i}`} className={`py-2 ${i > 0 ? "border-t border-[#DCE8D6]" : ""}`}>
                <div className="flex items-center justify-between gap-2">
                  <span className="text-[12.5px] font-extrabold uppercase tracking-[0.03em]">{im.label}</span>
                  <span className="flex items-center gap-2 shrink-0">
                    <span className="font-barlow font-bold text-[14px] tabular-nums text-[#68766B]">{im.prev.toFixed(1)} → {im.cur.toFixed(1)}</span>
                    <span className="bg-[#1E5B3C] text-white font-barlow font-black text-[11.5px] px-2 py-0.5 rounded-full tabular-nums">+{im.delta.toFixed(1)}</span>
                  </span>
                </div>
                {im.trained && i === prog.improvements.findIndex((x) => x.trained) && (
                  <div className="text-[11px] text-[#1E5B3C] italic mt-0.5">Exactly what your last report asked you to train — and it shows.</div>
                )}
              </div>
            ))}
          </div>
        )}
        {prog.watch?.length > 0 && (
          <div className="bg-[#FFF8E9] border border-[#F0E3C4] rounded-[12px] p-4">
            <div className="flex items-center gap-1.5 text-[11px] font-extrabold tracking-[0.12em] text-[#8A6D3B] mb-2.5">
              <Eye className="w-3.5 h-3.5" /> KEEP AN EYE ON
            </div>
            {prog.watch.map((wd, i) => (
              <div key={wd.key} data-testid={`v2-prog-watch-${i}`} className="flex items-center justify-between gap-2 py-1.5">
                <span className="text-[12.5px] font-extrabold uppercase tracking-[0.03em] text-[#6B5A35]">{wd.label}</span>
                <span className="font-barlow font-bold text-[14px] tabular-nums text-[#8A6D3B]">{wd.prev.toFixed(1)} → {wd.cur.toFixed(1)}</span>
              </div>
            ))}
            <p className="text-[10.5px] text-[#8A6D3B] leading-[1.5] mt-1.5">
              Normal fluctuation — often there were simply fewer situations of this type in the new footage. Keep an eye on it next time.
            </p>
          </div>
        )}
      </div>
      {showCurve && <div className="mt-3"><ProgressCurve series={prog.series} /></div>}
      <p className="text-[10.5px] text-[#8B957F] leading-[1.5] mt-3" data-testid="v2-prog-note">
        Compared: {prog.compared_skills} skills observed in BOTH videos · {prog.not_comparable} not comparable (not visible in both) · changes under ±0.3 shown as stable.
      </p>
    </V2Card>
  );
}

export function ProgressTeaser({ playerName }) {
  const first = String(playerName || "").split(" ")[0];
  return (
    <div data-testid="v2-progress-teaser" className="mb-4 flex items-center gap-3 bg-[#F0F5EC] border border-dashed border-[#9CB89A] rounded-[12px] px-4 py-3">
      <span className="w-9 h-9 rounded-full bg-[#12402A] text-[#CCFF00] flex items-center justify-center shrink-0">
        <TrendingUp className="w-4 h-4" />
      </span>
      <span className="text-[12.5px] leading-[1.5] text-[#3C4A40]">
        <b className="text-[#12402A]">{first ? `${first}'s development curve starts here.` : "The development curve starts here."}</b>{" "}
        Upload a new video in 4–6 weeks — we automatically chart the progress, skill by skill, right here.
      </span>
    </div>
  );
}
