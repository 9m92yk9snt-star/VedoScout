import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import api from "@/lib/api";
import { SkillBars } from "./SkillBars";
import { ArrowRight, Crown, Upload } from "lucide-react";

const verdictFor = (overall) => {
  if (overall == null) return { label: "Building Up", note: "Keep working and stay consistent." };
  if (overall >= 8.5) return { label: "Elite Level", note: "Outstanding — scouts notice players like you." };
  if (overall >= 7.5) return { label: "Above Average", note: "Keep working and stay consistent." };
  if (overall >= 6.5) return { label: "On Track", note: "Solid foundation — your next report shows the growth." };
  return { label: "Building Up", note: "Every session counts. Keep grinding." };
};

/* Premium performance HQ — dark panel with the overall ring and the new
 * animated skill bars (replaces the old radar chart). */
export default function PerformancePanel() {
  const [perf, setPerf] = useState(null);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    api.get("/dashboard/performance")
      .then(({ data }) => setPerf(data))
      .catch(() => {})
      .finally(() => setLoaded(true));
  }, []);

  if (!loaded) return null;

  if (!perf?.has_report) {
    return (
      <div
        data-testid="performance-panel-empty"
        className="mt-8 relative overflow-hidden rounded-3xl p-7 md:p-9 text-white"
        style={{ background: "#0F1F14" }}
      >
        <div className="flex items-center gap-2 mb-2">
          <Crown className="w-4 h-4 text-[#CCFF00]" fill="#CCFF00" />
          <span className="text-[10px] uppercase tracking-[0.28em] font-bold text-[#CCFF00]">Performance HQ</span>
        </div>
        <h2 className="font-barlow font-black uppercase text-2xl md:text-3xl tracking-tight leading-tight">
          Your performance panel is waiting
        </h2>
        <p className="mt-2 text-sm text-white/70 max-w-md">
          Upload a match and unlock your premium report — your overall score and skill breakdown will live right here.
        </p>
        <Link
          to="/upload"
          data-testid="performance-empty-upload-btn"
          className="mt-5 inline-flex items-center gap-2 bg-forest hover:bg-forest-pop text-white font-barlow font-black uppercase tracking-widest text-xs px-5 py-3 rounded-full transition-colors"
        >
          <Upload className="w-4 h-4" /> Upload a video
        </Link>
      </div>
    );
  }

  const overall = perf.overall;
  const pct = overall != null ? Math.min(100, (overall / 10) * 100) : 0;
  const verdict = verdictFor(overall);
  const bars = [
    { label: "Technical", value: perf.scores?.technical },
    { label: "Tactical", value: perf.scores?.tactical },
    { label: "Physical", value: perf.scores?.physical },
    { label: "Mental", value: perf.scores?.mentality },
  ];

  return (
    <div
      data-testid="performance-panel"
      className="mt-8 relative overflow-hidden rounded-3xl p-6 md:p-8 text-white grid md:grid-cols-[auto_1fr_1.1fr] gap-7 items-center"
      style={{ background: "#0F1F14" }}
    >
      <div aria-hidden className="absolute -top-24 -right-24 w-72 h-72 rounded-full pointer-events-none" style={{ background: "radial-gradient(circle, rgba(204,255,0,0.09), transparent 70%)" }} />
      {/* Overall ring */}
      <div className="justify-self-center md:justify-self-start">
        <div className="relative w-[124px] h-[124px]">
          <div
            className="absolute inset-0 rounded-full"
            style={{ background: `conic-gradient(#CCFF00 0 ${pct}%, rgba(255,255,255,0.08) ${pct}% 100%)` }}
          />
          <div className="absolute inset-[10px] rounded-full flex flex-col items-center justify-center" style={{ background: "#0F1F14" }}>
            <span className="font-barlow font-black text-[34px] leading-none" data-testid="performance-overall-score">
              {overall != null ? Number(overall).toFixed(1) : "—"}
            </span>
            <span className="text-[11px] text-white/50 font-bold">/ 10</span>
          </div>
          <span className="absolute -top-2 left-1/2 -translate-x-1/2 w-7 h-7 rounded-full flex items-center justify-center" style={{ background: "#CCFF00" }}>
            <Crown className="w-3.5 h-3.5 text-[#0F1F14]" fill="#0F1F14" />
          </span>
        </div>
        <div className="mt-2.5 text-center text-[10px] uppercase tracking-[0.2em] font-bold text-white/55">Overall score</div>
      </div>
      {/* Verdict + CTA */}
      <div className="text-center md:text-left">
        <div className="text-sm text-white/60">Your performance is</div>
        <div className="mt-1 font-barlow font-black uppercase text-2xl md:text-3xl tracking-tight" style={{ color: "#8FE05A" }} data-testid="performance-verdict">
          {verdict.label}
        </div>
        <p className="mt-1.5 text-[13px] text-white/60">{verdict.note}</p>
        <Link
          to={`/report/${perf.report_id}`}
          data-testid="performance-view-report-btn"
          className="mt-4 inline-flex items-center gap-2 bg-forest hover:bg-forest-pop text-white font-barlow font-black uppercase tracking-widest text-xs px-5 py-3 rounded-full transition-colors"
        >
          View full report <ArrowRight className="w-4 h-4" />
        </Link>
        {perf.player_name && (
          <p className="mt-3 text-[10px] uppercase tracking-[0.18em] font-bold text-white/40">
            {perf.player_name} · {perf.created_at ? new Date(perf.created_at).toLocaleDateString() : ""}
          </p>
        )}
      </div>
      {/* Skill bars — the new visualization */}
      <div className="w-full">
        <SkillBars scores={bars} />
      </div>
    </div>
  );
}
