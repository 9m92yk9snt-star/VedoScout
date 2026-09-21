import React from "react";
import { Users, Shield, Search, Briefcase, Trophy, TrendingUp } from "lucide-react";

const STATS = [
  { key: "players_in_library", wk: "players_wk", label: "Players in the Scout Library", Icon: Users, cls: "bg-forest/10 text-forest" },
  { key: "clubs_looking", wk: "clubs_wk", label: "Clubs looking for players", Icon: Shield, cls: "bg-amber-100 text-amber-600" },
  { key: "scouts_searching", wk: "scouts_wk", label: "Scouts searching players", Icon: Search, cls: "bg-blue-100 text-blue-600" },
  { key: "active_agents", wk: "agents_wk", label: "Active agents", Icon: Briefcase, cls: "bg-purple-100 text-purple-600" },
  { key: "trial_invites", wk: "trials_wk", label: "Players invited to trials", Icon: Trophy, cls: "bg-yellow-100 text-yellow-700" },
];

/* Admin-controlled ScoutMePlay Network numbers — keeps the dashboard alive
 * and sells the ecosystem. Hidden entirely when admin disables it. */
export default function CommunityPulse({ data }) {
  if (!data || data.enabled === false) return null;
  const items = STATS.filter((s) => Number(data[s.key]) > 0);
  if (items.length === 0) return null;

  return (
    <div className="mt-8 bg-cream-card border border-gray-border rounded-3xl p-6" data-testid="community-pulse">
      <div className="flex items-center gap-2 mb-5">
        <TrendingUp className="w-4 h-4 text-forest" />
        <h3 className="font-barlow font-black uppercase text-lg tracking-tight">ScoutMePlay Network</h3>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-5">
        {items.map(({ key, wk, label, Icon, cls }) => (
          <div key={key} data-testid={`community-stat-${key}`}>
            <div className="flex items-center gap-2.5">
              <span className={`w-9 h-9 rounded-xl flex items-center justify-center ${cls}`}>
                <Icon className="w-[18px] h-[18px]" />
              </span>
              <span className="font-barlow font-black text-2xl text-ink">{Number(data[key]).toLocaleString()}</span>
            </div>
            <p className="text-[12px] text-ink/65 mt-2 leading-snug font-medium">{label}</p>
            {Number(data[wk]) > 0 && (
              <p className="text-[11px] font-black text-forest mt-1">↗ +{Number(data[wk]).toLocaleString()} this week</p>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
