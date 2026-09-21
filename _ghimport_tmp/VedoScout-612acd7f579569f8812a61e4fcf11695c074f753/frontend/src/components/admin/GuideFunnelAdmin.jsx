// GuideFunnelAdmin — leads + follow-up offer email sequence (admin-controlled).
import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import { Send, Users, Save, Loader2, Trash2, BookOpen } from "lucide-react";
import api from "@/lib/api";

const BACKEND = process.env.REACT_APP_BACKEND_URL;

const STEP_META = {
  report_offer: { label: "Report discount", desc: "Discount code for a first scout report" },
  membership_offer: { label: "Membership discount", desc: "New-member code for Premium/VIP first month" },
  paid_guide: { label: "Paid playbook", desc: "The extended paid guide (add a purchase link to enable)" },
};

function Toggle({ on, onClick, testid }) {
  return (
    <button type="button" role="switch" aria-checked={on} onClick={onClick} data-testid={testid}
      className={`relative w-11 h-6 rounded-full transition-colors shrink-0 ${on ? "bg-forest" : "bg-ink/20"}`}>
      <span className={`absolute top-0.5 w-5 h-5 rounded-full bg-white shadow transition-all ${on ? "left-[22px]" : "left-0.5"}`} />
    </button>
  );
}

export const GuideFunnelAdmin = () => {
  const [cfg, setCfg] = useState(null);
  const [leads, setLeads] = useState({ total: 0, items: [] });
  const [saving, setSaving] = useState(false);
  const [showLeads, setShowLeads] = useState(false);

  const load = async () => {
    try {
      const [c, l] = await Promise.all([api.get("/admin/guide/funnel"), api.get("/admin/guide/leads")]);
      setCfg(c.data);
      setLeads(l.data);
    } catch { toast.error("Failed to load funnel"); }
  };
  useEffect(() => { load(); }, []);

  const save = async () => {
    setSaving(true);
    try {
      await api.put("/admin/guide/funnel", cfg);
      toast.success("Funnel saved");
    } catch (e) {
      toast.error(e?.response?.data?.detail || e.message);
    } finally { setSaving(false); }
  };

  const setStep = (sid, patch) => setCfg((c) => ({ ...c, steps: { ...c.steps, [sid]: { ...c.steps[sid], ...patch } } }));

  const deleteLead = async (id) => {
    if (!window.confirm("Delete this lead?")) return;
    await api.delete(`/admin/guide/leads/${id}`);
    load();
  };

  if (!cfg) return <div className="text-ink/50 text-sm py-4">Loading funnel…</div>;

  return (
    <div className="border border-gray-border bg-surface p-5 md:p-6" data-testid="guide-funnel-admin">
      <div className="flex items-center justify-between flex-wrap gap-3 mb-2">
        <div className="flex items-center gap-2">
          <Send className="w-5 h-5 text-forest" />
          <h3 className="font-barlow font-black uppercase text-xl tracking-tight">Guide funnel</h3>
          <button onClick={() => setShowLeads((v) => !v)} data-testid="funnel-leads-btn"
            className="ml-2 text-[11px] font-bold bg-forest/10 text-forest px-2.5 py-1 flex items-center gap-1.5 hover:bg-forest/20">
            <Users className="w-3.5 h-3.5" /> {leads.total} leads
          </button>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-[11px] uppercase tracking-[0.18em] font-bold text-ink/55">Funnel active</span>
          <Toggle on={!!cfg.enabled} onClick={() => setCfg((c) => ({ ...c, enabled: !c.enabled }))} testid="funnel-master-toggle" />
        </div>
      </div>
      <p className="text-sm text-ink/60 mb-1">
        Everyone who grabs the free guide on <a className="text-forest font-bold" href="/guide" target="_blank" rel="noreferrer">/guide</a> gets
        it by email instantly — then these follow-up offers, spaced out and honest. You control everything here.
      </p>
      <a href={`${BACKEND}/api/guide/pdf`} target="_blank" rel="noopener noreferrer" data-testid="funnel-preview-pdf"
        className="inline-flex items-center gap-1.5 text-[11px] uppercase tracking-[0.18em] font-bold text-forest hover:underline mb-4">
        <BookOpen className="w-3.5 h-3.5" /> Preview the free guide PDF
      </a>

      {showLeads && (
        <div className="border border-gray-border bg-cream-soft/30 p-4 mb-4 max-h-64 overflow-y-auto" data-testid="funnel-leads-list">
          {leads.items.length === 0 ? (
            <div className="text-sm text-ink/50">No leads yet.</div>
          ) : leads.items.map((l) => (
            <div key={l.id} className="flex items-center justify-between py-1.5 text-sm">
              <div>
                <span className="font-bold text-ink">{l.email}</span>
                {l.name && <span className="text-ink/55 ml-2">({l.name})</span>}
                <span className="text-[11px] text-ink/45 ml-2">{(l.created_at || "").split("T")[0]}</span>
                {l.unsubscribed && <span className="text-[10px] uppercase font-bold text-amber-600 ml-2">unsubscribed</span>}
              </div>
              <button onClick={() => deleteLead(l.id)} className="text-red-400 hover:text-red-600 p-1"><Trash2 className="w-3.5 h-3.5" /></button>
            </div>
          ))}
        </div>
      )}

      <div className="space-y-3">
        {Object.entries(STEP_META).map(([sid, meta]) => {
          const s = cfg.steps[sid] || {};
          return (
            <div key={sid} className="border border-gray-border p-4" data-testid={`funnel-step-${sid}`}>
              <div className="flex items-center justify-between flex-wrap gap-2">
                <div>
                  <div className="font-bold text-ink text-sm">{meta.label}</div>
                  <div className="text-[11px] text-ink/50">{meta.desc}</div>
                </div>
                <Toggle on={!!s.enabled} onClick={() => setStep(sid, { enabled: !s.enabled })} testid={`funnel-toggle-${sid}`} />
              </div>
              <div className="mt-3 grid grid-cols-2 md:grid-cols-4 gap-2">
                <div>
                  <label className="block text-[10px] uppercase tracking-[0.18em] font-bold text-ink/55 mb-1">Days after signup</label>
                  <input type="number" min={0} max={60} value={s.delay_days ?? 2}
                    onChange={(e) => setStep(sid, { delay_days: Number(e.target.value) })}
                    data-testid={`funnel-delay-${sid}`}
                    className="w-full px-3 py-2 bg-cream-soft/40 border border-gray-border focus:border-forest outline-none text-sm" />
                </div>
                {sid !== "paid_guide" ? (
                  <>
                    <div>
                      <label className="block text-[10px] uppercase tracking-[0.18em] font-bold text-ink/55 mb-1">Discount code</label>
                      <input value={s.code || ""} onChange={(e) => setStep(sid, { code: e.target.value.toUpperCase() })}
                        placeholder="Create one under Discount codes"
                        data-testid={`funnel-code-${sid}`}
                        className="w-full px-3 py-2 bg-cream-soft/40 border border-gray-border focus:border-forest outline-none text-sm font-bold" />
                    </div>
                    <div>
                      <label className="block text-[10px] uppercase tracking-[0.18em] font-bold text-ink/55 mb-1">% shown in email</label>
                      <input type="number" min={1} max={90} value={s.percent ?? 20}
                        onChange={(e) => setStep(sid, { percent: Number(e.target.value) })}
                        data-testid={`funnel-percent-${sid}`}
                        className="w-full px-3 py-2 bg-cream-soft/40 border border-gray-border focus:border-forest outline-none text-sm" />
                    </div>
                  </>
                ) : (
                  <>
                    <div>
                      <label className="block text-[10px] uppercase tracking-[0.18em] font-bold text-ink/55 mb-1">Price ($)</label>
                      <input type="number" min={1} value={s.price ?? 19}
                        onChange={(e) => setStep(sid, { price: Number(e.target.value) })}
                        data-testid="funnel-price-paid_guide"
                        className="w-full px-3 py-2 bg-cream-soft/40 border border-gray-border focus:border-forest outline-none text-sm" />
                    </div>
                    <div className="col-span-2 md:col-span-1">
                      <label className="block text-[10px] uppercase tracking-[0.18em] font-bold text-ink/55 mb-1">Purchase link</label>
                      <input value={s.link || ""} onChange={(e) => setStep(sid, { link: e.target.value })}
                        placeholder="https://…"
                        data-testid="funnel-link-paid_guide"
                        className="w-full px-3 py-2 bg-cream-soft/40 border border-gray-border focus:border-forest outline-none text-sm font-mono" />
                    </div>
                  </>
                )}
              </div>
              {sid !== "paid_guide" && s.enabled && !s.code && (
                <div className="mt-2 text-[11px] text-amber-600 font-bold">Add a discount code — this step won&apos;t send without one.</div>
              )}
              {sid === "paid_guide" && s.enabled && !s.link && (
                <div className="mt-2 text-[11px] text-amber-600 font-bold">Add a purchase link — this step won&apos;t send without one.</div>
              )}
            </div>
          );
        })}
      </div>

      <div className="mt-4 flex justify-end">
        <button onClick={save} disabled={saving} data-testid="funnel-save-btn"
          className="bg-forest hover:bg-forest-pop text-cream-card font-barlow font-black uppercase tracking-widest text-xs px-6 py-2.5 flex items-center gap-2 disabled:opacity-50">
          {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />} Save funnel
        </button>
      </div>
    </div>
  );
};
