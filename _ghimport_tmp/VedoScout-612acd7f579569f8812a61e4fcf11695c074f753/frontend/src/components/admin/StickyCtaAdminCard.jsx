// Admin Settings card — edit the landing sticky mobile CTA (text + on/off).
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Smartphone } from "lucide-react";
import api from "@/lib/api";

export default function StickyCtaAdminCard() {
  const [cfg, setCfg] = useState({ enabled: true, text: "Get My Report" });
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api.get("/settings/sticky-cta").then(({ data }) => setCfg(data)).catch(() => {});
  }, []);

  const save = async () => {
    setSaving(true);
    try {
      await api.put("/admin/sticky-cta", { enabled: !!cfg.enabled, text: (cfg.text || "").trim() || "Get My Report" });
      toast.success("Sticky CTA saved — live on the landing page immediately");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not save");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div data-testid="admin-sticky-cta-card" className="bg-surface border border-gray-border p-6 md:p-8">
      <div className="flex items-center gap-2 mb-1">
        <Smartphone className="w-4 h-4 text-volt" />
        <span className="text-volt text-[10px] uppercase tracking-[0.22em] font-bold">Landing page</span>
      </div>
      <h2 className="font-barlow font-black uppercase text-2xl text-ink">Sticky mobile CTA</h2>
      <p className="mt-2 text-ink/65 text-sm">
        A small fixed button at the bottom of the phone screen while visitors scroll the pricing section
        on the front page. Change the text here — it updates live.
      </p>
      <div className="mt-5 flex flex-wrap items-end gap-4">
        <label className="flex flex-col flex-1 min-w-[220px]">
          <span className="text-[11px] uppercase tracking-[0.22em] font-bold text-ink/55 mb-2">Button text</span>
          <input
            type="text"
            maxLength={40}
            value={cfg.text}
            onChange={(e) => setCfg((c) => ({ ...c, text: e.target.value }))}
            data-testid="admin-sticky-cta-text"
            className="bg-deepnavy border border-gray-border px-3 py-3 text-ink focus:outline-none focus:border-volt focus:ring-1 focus:ring-volt"
          />
        </label>
        <label className="flex items-center gap-2.5 pb-3 cursor-pointer select-none" data-testid="admin-sticky-cta-enabled">
          <input
            type="checkbox"
            checked={!!cfg.enabled}
            onChange={(e) => setCfg((c) => ({ ...c, enabled: e.target.checked }))}
            className="w-4 h-4 accent-[#1F4F2F]"
          />
          <span className="text-sm text-ink/80 font-bold">Enabled</span>
        </label>
        <button
          type="button"
          onClick={save}
          disabled={saving}
          data-testid="admin-sticky-cta-save"
          className="bg-forest hover:bg-forest-pop text-cream-card font-barlow font-black uppercase tracking-widest text-xs px-6 py-3 transition-colors disabled:opacity-50"
        >
          {saving ? "Saving…" : "Save"}
        </button>
      </div>
    </div>
  );
}
