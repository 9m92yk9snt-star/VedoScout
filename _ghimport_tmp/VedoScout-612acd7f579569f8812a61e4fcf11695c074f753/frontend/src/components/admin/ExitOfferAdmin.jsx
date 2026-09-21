// ExitOfferAdmin — admin controls for the exit-intent discount popup:
// enable/disable, %, countdown, validity, headline + live preview + stats.
import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import { DoorOpen, Eye, Loader2 } from "lucide-react";
import api from "@/lib/api";
import { ExitIntentPopup } from "@/components/ExitIntentOffer";

const inp = "bg-white border border-gray-border rounded-lg px-3 py-2 text-sm text-ink focus:outline-none focus:border-forest w-full";
const lbl = "block text-[10px] font-extrabold uppercase tracking-wider text-ink/55 mb-1";

export default function ExitOfferAdmin() {
  const [cfg, setCfg] = useState(null);
  const [stats, setStats] = useState(null);
  const [busy, setBusy] = useState(false);
  const [preview, setPreview] = useState(false);

  useEffect(() => {
    api.get("/admin/exit-offer")
      .then(({ data }) => { setCfg(data.config); setStats(data.stats); })
      .catch(() => toast.error("Could not load exit-offer settings"));
  }, []);

  const save = async () => {
    setBusy(true);
    try {
      await api.post("/admin/exit-offer", {
        enabled: !!cfg.enabled,
        percent: Number(cfg.percent),
        countdown_minutes: Number(cfg.countdown_minutes),
        valid_hours: Number(cfg.valid_hours),
        headline: cfg.headline || "",
      });
      toast.success("Exit-intent offer saved");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Save failed");
    } finally {
      setBusy(false);
    }
  };

  if (!cfg) return null;

  return (
    <section className="bg-white border border-gray-border rounded-2xl p-5 mt-8" data-testid="exit-offer-admin">
      <h3 className="font-barlow font-black uppercase text-ink flex items-center gap-2">
        <DoorOpen className="w-4 h-4 text-forest" /> Exit-intent offer
      </h3>
      <p className="text-xs text-ink/55 mt-1">
        Time-limited discount popup shown ONCE when a visitor who has seen the pricing section is about to leave.
        The claimed discount attaches to their account and applies automatically at checkout.
      </p>
      {stats && (
        <p className="text-[11px] text-ink/45 mt-1" data-testid="exit-offer-stats">
          {stats.claims} claim(s) · {stats.attached} attached to accounts
        </p>
      )}
      <label className="flex items-center gap-2 mt-4 text-sm text-ink/80 font-semibold">
        <input type="checkbox" checked={!!cfg.enabled} data-testid="exit-offer-enabled"
          onChange={(e) => setCfg({ ...cfg, enabled: e.target.checked })} />
        Popup enabled on the landing page
      </label>
      <div className="grid sm:grid-cols-3 gap-3 mt-3">
        <div>
          <label className={lbl}>Discount %</label>
          <input type="number" min="1" max="90" value={cfg.percent} data-testid="exit-offer-percent"
            onChange={(e) => setCfg({ ...cfg, percent: e.target.value })} className={inp} />
        </div>
        <div>
          <label className={lbl}>Countdown (minutes)</label>
          <input type="number" min="1" max="120" value={cfg.countdown_minutes} data-testid="exit-offer-countdown-input"
            onChange={(e) => setCfg({ ...cfg, countdown_minutes: e.target.value })} className={inp} />
        </div>
        <div>
          <label className={lbl}>Discount valid (hours after claim)</label>
          <input type="number" min="1" max="168" value={cfg.valid_hours} data-testid="exit-offer-valid-hours"
            onChange={(e) => setCfg({ ...cfg, valid_hours: e.target.value })} className={inp} />
        </div>
      </div>
      <div className="mt-3">
        <label className={lbl}>Headline</label>
        <input value={cfg.headline} data-testid="exit-offer-headline-input"
          onChange={(e) => setCfg({ ...cfg, headline: e.target.value })} className={inp} />
      </div>
      <div className="flex items-center gap-3 mt-4">
        <button type="button" onClick={save} disabled={busy} data-testid="exit-offer-save"
          className="bg-forest text-white font-barlow font-black uppercase text-[11px] tracking-widest px-6 py-2.5 rounded-full disabled:opacity-50">
          {busy ? <Loader2 className="w-4 h-4 animate-spin inline" /> : "Save"}
        </button>
        <button type="button" onClick={() => setPreview(true)} data-testid="exit-offer-preview-btn"
          className="inline-flex items-center gap-1.5 border border-forest text-forest font-barlow font-black uppercase text-[11px] tracking-widest px-5 py-2.5 rounded-full hover:bg-forest/5 transition-colors">
          <Eye className="w-3.5 h-3.5" /> Preview popup
        </button>
      </div>
      {preview && (
        <ExitIntentPopup
          preview
          config={{ ...cfg, percent: Number(cfg.percent), countdown_minutes: Number(cfg.countdown_minutes) }}
          onClose={() => setPreview(false)}
        />
      )}
    </section>
  );
}
