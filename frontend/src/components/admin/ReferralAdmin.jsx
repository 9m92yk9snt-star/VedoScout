// ReferralAdmin — teammate referral program controls (enable, %, validity)
// plus a full "who invited whom" table.
import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import { Users2, Loader2 } from "lucide-react";
import api from "@/lib/api";

const inp = "bg-white border border-gray-border rounded-lg px-3 py-2 text-sm text-ink focus:outline-none focus:border-forest w-full";
const lbl = "block text-[10px] font-extrabold uppercase tracking-wider text-ink/55 mb-1";

export default function ReferralAdmin() {
  const [cfg, setCfg] = useState(null);
  const [rows, setRows] = useState([]);
  const [total, setTotal] = useState(0);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.get("/admin/referrals")
      .then(({ data }) => { setCfg(data.config); setRows(data.referrals || []); setTotal(data.total || 0); })
      .catch(() => toast.error("Could not load referral data"));
  }, []);

  const save = async () => {
    setBusy(true);
    try {
      await api.post("/admin/referral-settings", {
        enabled: !!cfg.enabled,
        percent: Number(cfg.percent),
        valid_days: Number(cfg.valid_days),
      });
      toast.success("Referral settings saved");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Save failed");
    } finally {
      setBusy(false);
    }
  };

  if (!cfg) return null;

  return (
    <section className="bg-white border border-gray-border rounded-2xl p-5 mt-8" data-testid="referral-admin">
      <h3 className="font-barlow font-black uppercase text-ink flex items-center gap-2">
        <Users2 className="w-4 h-4 text-forest" /> Teammate referral program
      </h3>
      <p className="text-xs text-ink/55 mt-1">
        Players share a personal link — when a teammate signs up through it, BOTH get a discount on their next report.
        The discount applies automatically at checkout.
      </p>
      <label className="flex items-center gap-2 mt-4 text-sm text-ink/80 font-semibold">
        <input type="checkbox" checked={!!cfg.enabled} data-testid="referral-enabled"
          onChange={(e) => setCfg({ ...cfg, enabled: e.target.checked })} />
        Referral program active
      </label>
      <div className="grid sm:grid-cols-3 gap-3 mt-3">
        <div>
          <label className={lbl}>Discount % (both sides)</label>
          <input type="number" min="1" max="90" value={cfg.percent} data-testid="referral-percent"
            onChange={(e) => setCfg({ ...cfg, percent: e.target.value })} className={inp} />
        </div>
        <div>
          <label className={lbl}>Discount valid (days)</label>
          <input type="number" min="1" max="365" value={cfg.valid_days} data-testid="referral-valid-days"
            onChange={(e) => setCfg({ ...cfg, valid_days: e.target.value })} className={inp} />
        </div>
        <div className="flex items-end">
          <button type="button" onClick={save} disabled={busy} data-testid="referral-save"
            className="bg-forest text-white font-barlow font-black uppercase text-[11px] tracking-widest px-6 py-2.5 rounded-full disabled:opacity-50">
            {busy ? <Loader2 className="w-4 h-4 animate-spin inline" /> : "Save"}
          </button>
        </div>
      </div>

      <h4 className="text-[11px] font-extrabold uppercase tracking-wider text-ink/60 mt-6">
        Who invited whom <span className="text-ink/35">({total} total)</span>
      </h4>
      <div className="mt-2 overflow-x-auto">
        <table className="w-full text-[12.5px]" data-testid="referral-table">
          <thead>
            <tr className="text-left text-[10px] uppercase tracking-wider text-ink/45 border-b border-[#EFEADB]">
              <th className="py-2 pr-3">Referrer</th>
              <th className="py-2 pr-3">Invited</th>
              <th className="py-2 pr-3">Discount</th>
              <th className="py-2 pr-3">Date</th>
              <th className="py-2">Status</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id} className="border-b border-[#F5F1E6]" data-testid={`referral-row-${r.id}`}>
                <td className="py-2 pr-3">
                  <div className="font-bold text-ink">{r.referrer_name || "—"}</div>
                  <div className="text-[11px] text-ink/50">{r.referrer_email}</div>
                </td>
                <td className="py-2 pr-3">
                  <div className="font-bold text-ink">{r.referred_name || "—"}</div>
                  <div className="text-[11px] text-ink/50">{r.referred_email}</div>
                </td>
                <td className="py-2 pr-3 font-bold text-forest">{Math.round(r.percent)}%</td>
                <td className="py-2 pr-3 text-ink/60">{r.created_at ? new Date(r.created_at).toLocaleDateString() : "—"}</td>
                <td className="py-2">
                  <span className="text-[9.5px] font-extrabold uppercase tracking-wider bg-forest/10 text-forest border border-forest/30 px-2 py-0.5 rounded-full">
                    {r.status}
                  </span>
                </td>
              </tr>
            ))}
            {!rows.length && (
              <tr><td colSpan={5} className="py-4 text-center text-ink/40 text-xs">No referrals yet.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}
