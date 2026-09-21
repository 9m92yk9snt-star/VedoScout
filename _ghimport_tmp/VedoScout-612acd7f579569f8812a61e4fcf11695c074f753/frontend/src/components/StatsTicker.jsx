// StatsTicker — slim infinite-scrolling live stats bar under the top menu.
// Real numbers from /api/stats/ticker (admin can boost + toggle). Auto-refreshes.

import React, { useEffect, useState } from "react";
import { Volleyball, FileText, UserCheck, Globe, Target, Trophy } from "lucide-react";
import api from "@/lib/api";

const LIME = "#CCFF00";

const ITEMS = [
  { key: "players_analyzed", icon: Volleyball, label: "Players Analyzed" },
  { key: "pro_reports", icon: FileText, label: "ScoutMe Pro Reports Delivered" },
  { key: "scout_reviews", icon: UserCheck, label: "Professional Scout Reviews Delivered" },
  { key: "players_available", icon: Globe, label: "Players Available to Scouts" },
  { key: "trial_invites", icon: Target, label: "Trial Invitations Earned" },
  { key: "club_opportunities", icon: Trophy, label: "Club Opportunities Created" },
];

const fmt = (n) => Number(n || 0).toLocaleString("en-US");

function TickerRun({ stats }) {
  return (
    <div className="flex items-center shrink-0" aria-hidden="true">
      {ITEMS.map(({ key, icon: Icon, label }) => (
        <span key={key} className="flex items-center gap-2 px-7 whitespace-nowrap">
          <Icon className="w-3.5 h-3.5 shrink-0" style={{ color: LIME }} />
          <span className="font-barlow font-black text-[13px] tracking-[0.02em]" style={{ color: LIME }}>
            {fmt(stats[key])}
          </span>
          <span className="text-[10.5px] font-bold uppercase tracking-[0.12em] text-white/60">{label}</span>
          <span className="ml-7 w-1 h-1 rounded-full bg-white/20" />
        </span>
      ))}
    </div>
  );
}

export default function StatsTicker() {
  const [stats, setStats] = useState(null);

  useEffect(() => {
    let alive = true;
    const load = () =>
      api.get("/stats/ticker").then(({ data }) => {
        if (alive) setStats(data?.enabled ? data.stats : null);
      }).catch(() => {});
    load();
    const iv = setInterval(load, 60000);
    return () => { alive = false; clearInterval(iv); };
  }, []);

  if (!stats) return null;
  return (
    <div
      className="relative overflow-hidden select-none"
      style={{ background: "#0B1F14", borderBottom: "1px solid rgba(204,255,0,0.18)" }}
      data-testid="stats-ticker"
    >
      <style>{`
        @keyframes smp-ticker-scroll {
          from { transform: translateX(0); }
          to { transform: translateX(-50%); }
        }
        .smp-ticker-track { animation: smp-ticker-scroll 38s linear infinite; will-change: transform; }
        .smp-ticker-track:hover { animation-play-state: paused; }
      `}</style>
      <div className="smp-ticker-track flex items-center h-9 w-max">
        <TickerRun stats={stats} />
        <TickerRun stats={stats} />
      </div>
      <div className="pointer-events-none absolute inset-y-0 left-0 w-10" style={{ background: "linear-gradient(90deg, #0B1F14, transparent)" }} />
      <div className="pointer-events-none absolute inset-y-0 right-0 w-10" style={{ background: "linear-gradient(270deg, #0B1F14, transparent)" }} />
    </div>
  );
}
