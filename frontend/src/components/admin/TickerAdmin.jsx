// TickerAdmin — control the scrolling social-proof bar (real counts + boosts).
import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";

const ROWS = [
  { key: "players_analyzed", label: "Players Analyzed", hint: "Real = videos analyzed" },
  { key: "pro_reports", label: "ScoutMe Pro Reports Delivered", hint: "Real = full reports generated" },
  { key: "scout_reviews", label: "Professional Scout Reviews Delivered", hint: "Real = delivered scout reviews" },
  { key: "players_available", label: "Players Available to Scouts", hint: "Real = player profiles in library" },
  { key: "trial_invites", label: "Trial Invitations Earned", hint: "Manual only (no automatic count)" },
  { key: "club_opportunities", label: "Club Opportunities Created", hint: "Manual only (no automatic count)" },
];

export default function TickerAdmin() {
  const [data, setData] = useState(null);
  const [boosts, setBoosts] = useState({});
  const [enabled, setEnabled] = useState(true);
  const [saving, setSaving] = useState(false);

  const load = () =>
    api.get("/admin/ticker").then(({ data }) => {
      setData(data);
      setBoosts(data.boosts || {});
      setEnabled(data.enabled !== false);
    }).catch(() => toast.error("Could not load ticker settings"));

  useEffect(() => { load(); }, []);

  const save = async () => {
    setSaving(true);
    try {
      const clean = {};
      ROWS.forEach(({ key }) => { clean[key] = Math.max(0, parseInt(boosts[key], 10) || 0); });
      await api.put("/admin/ticker", { enabled, boosts: clean });
      toast.success("Ticker updated — live within a minute");
      load();
    } catch {
      toast.error("Could not save ticker settings");
    } finally {
      setSaving(false);
    }
  };

  if (!data) return <div className="text-ink/50 text-sm py-8">Loading ticker settings…</div>;

  return (
    <div className="space-y-6 max-w-3xl" data-testid="ticker-admin">
      <div className="flex items-center justify-between rounded-lg border border-ink/10 bg-white/5 px-4 py-3">
        <div>
          <div className="font-bold text-ink">Scrolling stats bar</div>
          <div className="text-xs text-ink/50">Shown on the landing page and free preview reports.</div>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs text-ink/60">{enabled ? "Visible" : "Hidden"}</span>
          <Switch checked={enabled} onCheckedChange={setEnabled} data-testid="ticker-enabled-switch" />
        </div>
      </div>

      <div className="rounded-lg border border-ink/10 overflow-hidden">
        <div className="grid grid-cols-[1fr_90px_110px_90px] gap-2 px-4 py-2 text-[11px] uppercase tracking-wider text-ink/40 bg-white/5">
          <span>Stat</span><span className="text-right">Real</span><span className="text-right">Extra (boost)</span><span className="text-right">Shown</span>
        </div>
        {ROWS.map(({ key, label, hint }) => {
          const real = data.real?.[key] ?? 0;
          const boost = parseInt(boosts[key], 10) || 0;
          return (
            <div key={key} className="grid grid-cols-[1fr_90px_110px_90px] gap-2 items-center px-4 py-3 border-t border-ink/5">
              <div>
                <div className="text-sm font-semibold text-ink">{label}</div>
                <div className="text-[11px] text-ink/40">{hint}</div>
              </div>
              <div className="text-right text-sm text-ink/70" data-testid={`ticker-real-${key}`}>{real.toLocaleString()}</div>
              <Input
                type="number" min="0"
                className="h-8 text-right"
                value={boosts[key] ?? 0}
                onChange={(e) => setBoosts((b) => ({ ...b, [key]: e.target.value }))}
                data-testid={`ticker-boost-${key}`}
              />
              <div className="text-right text-sm font-bold text-volt" data-testid={`ticker-total-${key}`}>
                {(real + Math.max(0, boost)).toLocaleString()}
              </div>
            </div>
          );
        })}
      </div>

      <Button onClick={save} disabled={saving} data-testid="ticker-save-btn">
        {saving ? "Saving…" : "Save ticker settings"}
      </Button>
    </div>
  );
}
