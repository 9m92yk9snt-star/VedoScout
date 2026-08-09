import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import api from "@/lib/api";
import { Shield, Trophy, ArrowUpRight, Check, Loader2 } from "lucide-react";

const daysLeft = (deadline) => {
  if (!deadline) return null;
  const diff = Math.ceil((new Date(deadline).getTime() - Date.now()) / 86400000);
  if (Number.isNaN(diff)) return null;
  return diff;
};

/* Trials & Opportunities — PREMIUM ONLY. Free users never see this section
 * (the API returns a locked payload and we render nothing). Premium players
 * can raise their hand with "I'm interested" — admin sees the applicant list. */
export default function OpportunitiesPanel() {
  const [data, setData] = useState(null);
  const [busyId, setBusyId] = useState(null);

  useEffect(() => {
    api.get("/dashboard/opportunities").then(({ data }) => setData(data)).catch(() => {});
  }, []);

  const toggleInterest = async (o) => {
    if (busyId) return;
    setBusyId(o.id);
    try {
      if (o.interested) {
        await api.delete(`/dashboard/opportunities/${o.id}/interest`);
        toast.success("Interest withdrawn.");
      } else {
        await api.post(`/dashboard/opportunities/${o.id}/interest`);
        toast.success("Interest registered — we'll pass your profile on!");
      }
      setData((prev) => ({
        ...prev,
        items: prev.items.map((x) => (x.id === o.id ? { ...x, interested: !o.interested } : x)),
      }));
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not update interest");
    } finally {
      setBusyId(null);
    }
  };

  if (!data || data.locked || !data.items?.length) return null;

  return (
    <div className="mt-8 bg-cream-card border border-gray-border rounded-3xl p-6" data-testid="opportunities-panel">
      <div className="flex items-center gap-2 mb-4">
        <Trophy className="w-4 h-4 text-forest" />
        <h3 className="font-barlow font-black uppercase text-lg tracking-tight">Trials &amp; Opportunities</h3>
        <span className="ml-auto text-[10px] uppercase tracking-[0.16em] font-black text-[#CCFF00] bg-[#0F1F14] px-2.5 py-1 rounded-full">
          Premium
        </span>
      </div>
      <ul className="divide-y divide-ink/10">
        {data.items.map((o) => {
          const dl = daysLeft(o.deadline);
          const closed = dl != null && dl < 0;
          return (
            <li key={o.id} className="flex flex-wrap items-center gap-3.5 py-3.5" data-testid={`opportunity-row-${o.id}`}>
              <span className="w-11 h-11 rounded-xl flex items-center justify-center shrink-0" style={{ background: "#13253F", color: "#F2C94C" }}>
                <Shield className="w-5 h-5" />
              </span>
              <div className="min-w-0 flex-1">
                <b className="block text-sm text-ink truncate">{o.title}</b>
                <span className="block text-[12px] text-ink/55 mt-0.5 truncate">
                  {[o.club_name, o.age_band, o.location].filter(Boolean).join(" • ")}
                </span>
              </div>
              {o.is_new && !o.interested && (
                <span className="bg-forest text-white text-[10px] font-black uppercase tracking-wider px-2.5 py-1 rounded-lg shrink-0">New</span>
              )}
              {dl != null && (
                <span className={`text-[11px] font-bold shrink-0 ${closed ? "text-ink/40" : dl <= 3 ? "text-amber-600" : "text-ink/55"}`}>
                  {closed ? "Closed" : dl === 0 ? "Today" : `${dl}d left`}
                </span>
              )}
              {!closed && (
                <button
                  type="button"
                  onClick={() => toggleInterest(o)}
                  disabled={busyId === o.id}
                  data-testid={`opportunity-interest-${o.id}`}
                  className={`shrink-0 inline-flex items-center gap-1.5 font-barlow font-black uppercase tracking-[0.12em] text-[11px] px-3.5 py-2 rounded-full transition-colors disabled:opacity-50 ${
                    o.interested
                      ? "bg-forest/10 text-forest border border-forest/40 hover:bg-forest/20"
                      : "bg-forest hover:bg-forest-pop text-white"
                  }`}
                  title={o.interested ? "Click to withdraw your interest" : "Tell us you want this trial"}
                >
                  {busyId === o.id ? (
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  ) : o.interested ? (
                    <><Check className="w-3.5 h-3.5" /> Interested</>
                  ) : (
                    "I'm interested"
                  )}
                </button>
              )}
              {o.cta_url && (
                <a
                  href={o.cta_url}
                  target="_blank"
                  rel="noreferrer"
                  data-testid={`opportunity-cta-${o.id}`}
                  className="shrink-0 text-forest hover:text-forest-pop"
                  aria-label={`Open ${o.title}`}
                >
                  <ArrowUpRight className="w-[18px] h-[18px]" />
                </a>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
