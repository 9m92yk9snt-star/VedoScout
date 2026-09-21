// DiscountCodesAdmin — create & manage discount codes (redeemed natively in Stripe checkout).
import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import { TicketPercent, Loader2, Plus, Power, Trash2 } from "lucide-react";
import api from "@/lib/api";

export const DiscountCodesAdmin = () => {
  const [items, setItems] = useState([]);
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState({ code: "", percent: 20, applies_to: "both", expires_at: "", max_uses: "" });

  const load = async () => {
    try {
      const { data } = await api.get("/admin/discount-codes");
      setItems(data.items || []);
    } catch { /* noop */ }
  };
  useEffect(() => { load(); }, []);

  const create = async () => {
    if (!form.code.trim()) { toast.error("Type a code first"); return; }
    setBusy(true);
    try {
      const payload = {
        code: form.code.trim(),
        percent: Number(form.percent),
        applies_to: form.applies_to,
        expires_at: form.expires_at ? `${form.expires_at}T23:59:59` : null,
        max_uses: form.max_uses ? Number(form.max_uses) : null,
      };
      const { data } = await api.post("/admin/discount-codes", payload);
      if (data.warning) toast.warning(data.warning);
      else toast.success(`Code ${data.code} is live — works at checkout right away`);
      setForm({ code: "", percent: 20, applies_to: "both", expires_at: "", max_uses: "" });
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || e.message);
    } finally {
      setBusy(false);
    }
  };

  const toggle = async (c) => {
    await api.patch(`/admin/discount-codes/${c.id}`);
    toast.success(c.active ? "Code deactivated" : "Code reactivated");
    load();
  };

  const remove = async (c) => {
    if (!window.confirm(`Delete code ${c.code}?`)) return;
    await api.delete(`/admin/discount-codes/${c.id}`);
    load();
  };

  return (
    <div className="border border-gray-border bg-surface p-5 md:p-6" data-testid="discount-codes-admin">
      <div className="flex items-center gap-2 mb-2">
        <TicketPercent className="w-5 h-5 text-forest" />
        <h3 className="font-barlow font-black uppercase text-xl tracking-tight">Discount codes</h3>
      </div>
      <p className="text-sm text-ink/60 mb-4">
        Codes are entered directly on the payment page (single reports and memberships).
        &quot;Applies to&quot; tells you where to advertise the code — expiry and max uses are enforced automatically.
      </p>

      <div className="grid md:grid-cols-[1fr_100px_170px_150px_110px_auto] gap-2 items-end">
        <div>
          <label className="block text-[10px] uppercase tracking-[0.2em] font-bold text-ink/55 mb-1">Code</label>
          <input data-testid="code-input" value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value.toUpperCase() })} placeholder="NEWPLAYER20"
            className="w-full px-3 py-2.5 bg-cream-soft/40 border border-gray-border focus:border-forest outline-none text-sm font-bold" />
        </div>
        <div>
          <label className="block text-[10px] uppercase tracking-[0.2em] font-bold text-ink/55 mb-1">% off</label>
          <input data-testid="code-percent" type="number" min={1} max={90} value={form.percent} onChange={(e) => setForm({ ...form, percent: e.target.value })}
            className="w-full px-3 py-2.5 bg-cream-soft/40 border border-gray-border focus:border-forest outline-none text-sm" />
        </div>
        <div>
          <label className="block text-[10px] uppercase tracking-[0.2em] font-bold text-ink/55 mb-1">Applies to</label>
          <select data-testid="code-applies" value={form.applies_to} onChange={(e) => setForm({ ...form, applies_to: e.target.value })}
            className="w-full px-3 py-2.5 bg-cream-soft/40 border border-gray-border focus:border-forest outline-none text-sm">
            <option value="both">Reports + memberships</option>
            <option value="report">Single report</option>
            <option value="subscription">Membership</option>
          </select>
        </div>
        <div>
          <label className="block text-[10px] uppercase tracking-[0.2em] font-bold text-ink/55 mb-1">Expires</label>
          <input data-testid="code-expires" type="date" value={form.expires_at} onChange={(e) => setForm({ ...form, expires_at: e.target.value })}
            className="w-full px-3 py-2.5 bg-cream-soft/40 border border-gray-border focus:border-forest outline-none text-sm" />
        </div>
        <div>
          <label className="block text-[10px] uppercase tracking-[0.2em] font-bold text-ink/55 mb-1">Max uses</label>
          <input data-testid="code-max-uses" type="number" min={1} value={form.max_uses} onChange={(e) => setForm({ ...form, max_uses: e.target.value })} placeholder="∞"
            className="w-full px-3 py-2.5 bg-cream-soft/40 border border-gray-border focus:border-forest outline-none text-sm" />
        </div>
        <button onClick={create} disabled={busy} data-testid="code-create-btn"
          className="bg-forest hover:bg-forest-pop text-cream-card font-barlow font-black uppercase tracking-widest text-xs px-5 py-2.5 flex items-center gap-2 disabled:opacity-50">
          {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />} Create
        </button>
      </div>

      <div className="mt-5 divide-y divide-gray-border" data-testid="code-list">
        {items.map((c) => (
          <div key={c.id} className="flex items-center justify-between py-3 flex-wrap gap-2" data-testid={`code-row-${c.code}`}>
            <div>
              <span className={`font-barlow font-black tracking-[0.15em] text-base ${c.active ? "text-ink" : "text-ink/35 line-through"}`}>{c.code}</span>
              <span className="ml-3 text-xs font-bold text-forest">{c.percent}% off</span>
              <div className="text-[11px] text-ink/50 mt-0.5">
                {c.applies_to === "both" ? "Reports + memberships" : c.applies_to === "report" ? "Single report" : "Membership"}
                {c.expires_at && <> · expires {c.expires_at.split("T")[0]}</>}
                {c.max_uses && <> · max {c.max_uses} uses</>}
                {typeof c.times_redeemed === "number" && <> · redeemed {c.times_redeemed}×</>}
                {!c.stripe_promo_id && <span className="text-amber-600"> · not connected to checkout (Stripe)</span>}
              </div>
            </div>
            <div className="flex items-center gap-1.5">
              <button onClick={() => toggle(c)} title={c.active ? "Deactivate" : "Activate"} data-testid={`code-toggle-${c.code}`}
                className={`p-2 transition-colors ${c.active ? "text-forest hover:bg-forest hover:text-white" : "text-ink/40 hover:bg-ink/10"}`}>
                <Power className="w-4 h-4" />
              </button>
              <button onClick={() => remove(c)} data-testid={`code-delete-${c.code}`} className="text-red-400 hover:bg-red-400 hover:text-white p-2">
                <Trash2 className="w-4 h-4" />
              </button>
            </div>
          </div>
        ))}
        {items.length === 0 && <div className="py-4 text-sm text-ink/50">No codes yet.</div>}
      </div>
    </div>
  );
};
