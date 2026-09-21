// GrowthAdmin — discounts (auto 48h percent + manual campaigns) and the nurture sweep.
import React, { useEffect, useState } from "react";
import { Percent, Plus, Trash2, Play, Mail } from "lucide-react";
import api from "@/lib/api";
import { toast } from "sonner";

export default function GrowthAdmin() {
  const [autoPercent, setAutoPercent] = useState(25);
  const [campaigns, setCampaigns] = useState([]);
  const [form, setForm] = useState({ name: "", percent: 20, hours_valid: 72, send_email: true });
  const [busy, setBusy] = useState(false);
  const [sweepResult, setSweepResult] = useState(null);
  const [emailsOn, setEmailsOn] = useState(false);

  const load = () => {
    api.get("/admin/discounts").then(({ data }) => {
      setAutoPercent(data.auto_percent);
      setCampaigns(data.campaigns || []);
      setEmailsOn(!!data.emails_enabled);
    }).catch(() => {});
  };
  useEffect(() => { load(); }, []);

  const toggleEmails = async () => {
    try {
      const { data } = await api.put("/admin/discounts/emails-enabled", { enabled: !emailsOn });
      setEmailsOn(!!data.enabled);
      toast.success(data.enabled ? "Nurture emails are ON" : "Nurture emails are OFF");
    } catch { toast.error("Failed"); }
  };

  const saveAuto = async () => {
    try {
      await api.put("/admin/discounts/auto", { percent: Number(autoPercent) });
      toast.success("Auto 48h discount updated");
    } catch (e) { toast.error(e?.response?.data?.detail || "Failed"); }
  };

  const createCampaign = async () => {
    if (!form.name.trim()) { toast.error("Give the campaign a name"); return; }
    setBusy(true);
    try {
      const { data } = await api.post("/admin/discounts", form);
      toast.success(data?.emailed != null ? `Campaign live — email queued to ${data.emailed} users` : "Campaign live");
      setForm({ name: "", percent: 20, hours_valid: 72, send_email: true });
      load();
    } catch (e) { toast.error(e?.response?.data?.detail || "Failed"); }
    finally { setBusy(false); }
  };

  const deactivate = async (id) => {
    try { await api.delete(`/admin/discounts/${id}`); toast.success("Campaign deactivated"); load(); }
    catch { toast.error("Failed"); }
  };

  const runSweep = async (dry) => {
    setBusy(true);
    try {
      const { data } = await api.post(`/admin/conversion-sweep?dry_run=${dry}`);
      setSweepResult(data);
      toast.success(`${dry ? "Dry run" : "Sweep"}: ${data?.results?.length ?? 0} item(s)`);
    } catch (e) { toast.error(e?.response?.data?.detail || "Failed"); }
    finally { setBusy(false); }
  };

  const inp = "bg-white border border-gray-border rounded-lg px-3 py-2 text-sm text-ink focus:outline-none focus:border-forest";

  return (
    <div className="space-y-8" data-testid="growth-admin">
      <section className="bg-white border border-gray-border rounded-2xl p-5">
        <h3 className="font-barlow font-black uppercase text-ink flex items-center gap-2"><Percent className="w-4 h-4 text-forest" /> Automatic 48h offer</h3>
        <p className="text-xs text-ink/55 mt-1">Sent 48 hours after an unpaid analysis — valid 48 hours, applied automatically at checkout.</p>
        <div className="flex items-center gap-3 mt-3">
          <input type="number" min="1" max="90" value={autoPercent} data-testid="auto-percent-input"
            onChange={(e) => setAutoPercent(e.target.value)} className={`${inp} w-24`} />
          <span className="text-sm text-ink/60">% off single report</span>
          <button type="button" onClick={saveAuto} data-testid="auto-percent-save"
            className="bg-forest text-white font-barlow font-black uppercase text-[11px] tracking-widest px-5 py-2.5 rounded-full">Save</button>
        </div>
      </section>

      <section className="bg-white border border-gray-border rounded-2xl p-5">
        <h3 className="font-barlow font-black uppercase text-ink flex items-center gap-2"><Plus className="w-4 h-4 text-forest" /> Manual campaign</h3>
        <p className="text-xs text-ink/55 mt-1">Discount on the single report for ALL users — optionally emailed to everyone.</p>
        <div className="grid sm:grid-cols-4 gap-3 mt-3">
          <div className="sm:col-span-2">
            <label className="block text-[10px] font-extrabold uppercase tracking-wider text-ink/55 mb-1">Campaign name</label>
            <input placeholder="Name (e.g. Summer offer)" value={form.name} data-testid="campaign-name-input"
              onChange={(e) => setForm({ ...form, name: e.target.value })} className={`${inp} w-full`} />
          </div>
          <div>
            <label className="block text-[10px] font-extrabold uppercase tracking-wider text-ink/55 mb-1">Discount %</label>
            <input type="number" min="1" max="90" value={form.percent} data-testid="campaign-percent"
              onChange={(e) => setForm({ ...form, percent: Number(e.target.value) })} className={`${inp} w-full`} title="% off" />
          </div>
          <div>
            <label className="block text-[10px] font-extrabold uppercase tracking-wider text-ink/55 mb-1">Valid for (hours)</label>
            <input type="number" min="1" max="720" value={form.hours_valid} data-testid="campaign-hours-input"
              onChange={(e) => setForm({ ...form, hours_valid: Number(e.target.value) })} className={`${inp} w-full`} title="Hours valid" />
          </div>
        </div>
        <label className="flex items-center gap-2 mt-3 text-sm text-ink/70">
          <input type="checkbox" checked={form.send_email} data-testid="campaign-email-check"
            onChange={(e) => setForm({ ...form, send_email: e.target.checked })} />
          <Mail className="w-3.5 h-3.5" /> Email the offer to all users
        </label>
        <button type="button" onClick={createCampaign} disabled={busy} data-testid="campaign-create-btn"
          className="mt-3 bg-forest text-white font-barlow font-black uppercase text-[11px] tracking-widest px-6 py-2.5 rounded-full disabled:opacity-50">
          Launch campaign
        </button>
        <div className="mt-4 space-y-2">
          {campaigns.map((c) => (
            <div key={c.id} className="flex items-center justify-between bg-[#FBF9F3] border border-[#E5DFCE] rounded-xl px-4 py-2.5" data-testid={`campaign-row-${c.id}`}>
              <div className="text-sm">
                <b>{c.name}</b> — {c.percent}% off · until {new Date(c.expires_at).toLocaleString()}
                {!c.active && <span className="ml-2 text-[10px] uppercase font-bold text-red-600">inactive</span>}
              </div>
              {c.active && (
                <button type="button" onClick={() => deactivate(c.id)} data-testid={`campaign-delete-${c.id}`} className="text-red-600 hover:text-red-800">
                  <Trash2 className="w-4 h-4" />
                </button>
              )}
            </div>
          ))}
          {!campaigns.length && <p className="text-xs text-ink/40">No campaigns yet.</p>}
        </div>
      </section>

      <section className="bg-white border border-gray-border rounded-2xl p-5">
        <h3 className="font-barlow font-black uppercase text-ink flex items-center gap-2"><Play className="w-4 h-4 text-forest" /> Nurture sweep</h3>
        <p className="text-xs text-ink/55 mt-1">Runs automatically every 15 min when enabled: 24h numbers-mail, 48h discount, 72h discovery, 1h abandoned checkout.</p>
        <label className="flex items-center gap-2 mt-3 text-sm text-ink/70">
          <input type="checkbox" checked={emailsOn} onChange={toggleEmails} data-testid="growth-emails-toggle" />
          Automatic nurture emails {emailsOn ? "ON" : "OFF"}
        </label>
        <div className="flex gap-3 mt-3">
          <button type="button" onClick={() => runSweep(true)} disabled={busy} data-testid="sweep-dry-btn"
            className="border border-forest text-forest font-barlow font-black uppercase text-[11px] tracking-widest px-5 py-2.5 rounded-full disabled:opacity-50">Dry run</button>
          <button type="button" onClick={() => runSweep(false)} disabled={busy} data-testid="sweep-run-btn"
            className="bg-forest text-white font-barlow font-black uppercase text-[11px] tracking-widest px-5 py-2.5 rounded-full disabled:opacity-50">Run now</button>
        </div>
        {sweepResult && (
          <pre className="mt-3 bg-[#0B1F14] text-[#CCFF00] text-[11px] p-3 rounded-xl overflow-auto max-h-56" data-testid="sweep-result">
            {JSON.stringify(sweepResult, null, 2)}
          </pre>
        )}
      </section>
    </div>
  );
}
