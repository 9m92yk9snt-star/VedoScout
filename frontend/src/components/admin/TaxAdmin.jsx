import React, { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import {
  Loader2, RefreshCw, Landmark, Plus, Trash2, Paperclip, Download,
  TrendingUp, TrendingDown, Receipt, Percent, ChevronDown, FileText,
} from "lucide-react";
import api from "@/lib/api";

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "Maj", "Jun", "Jul", "Aug", "Sep", "Okt", "Nov", "Dec"];
const kr = (v) => `${Number(v || 0).toLocaleString("da-DK", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} kr.`;

const StatCard = ({ label, value, sub, icon: Icon, tone = "ink", testid }) => (
  <div data-testid={testid} className="border border-gray-border p-5">
    <div className="flex items-center gap-2 mb-2">
      <Icon className={`w-4 h-4 ${tone === "volt" ? "text-volt" : tone === "red" ? "text-red-400" : "text-ink/50"}`} />
      <p className="text-xs uppercase tracking-widest font-bold text-ink/55">{label}</p>
    </div>
    <p className={`font-barlow font-black text-2xl ${tone === "red" ? "text-red-400" : "text-ink"}`}>{value}</p>
    {sub && <p className="text-xs text-ink/45 mt-1">{sub}</p>}
  </div>
);

export default function TaxAdmin() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [year] = useState(2026);
  const [saving, setSaving] = useState(false);
  const [deletingId, setDeletingId] = useState(null);
  const [openGuide, setOpenGuide] = useState(null);
  const fileRef = useRef(null);

  const [form, setForm] = useState({
    amount: "", date: new Date().toISOString().slice(0, 10),
    category: "hosting", note: "", vat: false,
  });

  const load = async () => {
    setLoading(true);
    try {
      const r = await api.get(`/admin/tax/summary?year=${year}`);
      setData(r.data);
    } catch {
      toast.error("Kunne ikke hente skatte-overblik");
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => { load(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const addExpense = async (e) => {
    e.preventDefault();
    const amount = parseFloat(String(form.amount).replace(",", "."));
    if (!amount || amount <= 0) { toast.error("Indtast et beløb i kroner"); return; }
    setSaving(true);
    try {
      const fd = new FormData();
      fd.append("amount_dkk", amount);
      fd.append("date", form.date);
      fd.append("category", form.category);
      fd.append("note", form.note);
      fd.append("vat_included", form.vat);
      const file = fileRef.current?.files?.[0];
      if (file) fd.append("receipt", file);
      await api.post("/admin/tax/expenses", fd, { headers: { "Content-Type": "multipart/form-data" } });
      toast.success("Udgift gemt");
      setForm({ amount: "", date: form.date, category: form.category, note: "", vat: false });
      if (fileRef.current) fileRef.current.value = "";
      load();
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Kunne ikke gemme udgiften");
    } finally {
      setSaving(false);
    }
  };

  const removeExpense = async (id) => {
    setDeletingId(id);
    try {
      await api.delete(`/admin/tax/expenses/${id}`);
      toast.success("Udgift slettet");
      load();
    } catch {
      toast.error("Kunne ikke slette udgiften");
    } finally {
      setDeletingId(null);
    }
  };

  const download = async (fmt) => {
    try {
      const r = await api.get(`/admin/tax/export.${fmt}?year=${year}`, { responseType: "blob" });
      const url = URL.createObjectURL(r.data);
      const a = document.createElement("a");
      a.href = url;
      a.download = `scoutmeplay-skat-${year}.${fmt}`;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      toast.error("Eksport fejlede");
    }
  };

  if (loading && !data) return <div className="py-16 text-center"><Loader2 className="w-6 h-6 animate-spin text-volt mx-auto" /></div>;
  if (!data) return null;

  const { income, expenses, vat } = data;
  const result = data.result_dkk;

  return (
    <div data-testid="admin-tax" className="space-y-10">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="font-barlow font-black uppercase text-2xl tracking-tight flex items-center gap-2">
          <Landmark className="w-5 h-5 text-volt" /> Skat-hjælper · {data.year}
        </h2>
        <div className="flex items-center gap-2">
          <button data-testid="tax-export-csv" onClick={() => download("csv")}
            className="flex items-center gap-2 px-4 py-2 border border-gray-border text-xs uppercase tracking-widest font-bold hover:border-volt hover:text-volt transition-colors">
            <Download className="w-3.5 h-3.5" /> CSV
          </button>
          <button data-testid="tax-export-pdf" onClick={() => download("pdf")}
            className="flex items-center gap-2 px-4 py-2 border border-gray-border text-xs uppercase tracking-widest font-bold hover:border-volt hover:text-volt transition-colors">
            <FileText className="w-3.5 h-3.5" /> PDF
          </button>
          <button data-testid="tax-refresh" onClick={load}
            className="flex items-center gap-2 px-4 py-2 border border-gray-border text-xs uppercase tracking-widest font-bold hover:border-volt hover:text-volt transition-colors">
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} /> Opdater
          </button>
        </div>
      </div>

      {/* ===== Summary cards ===== */}
      <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard testid="tax-card-income" label="Indtægter" icon={TrendingUp} tone="volt"
          value={kr(income.total_dkk)} sub={`${income.count} betalinger · ${income.total_usd.toLocaleString("da-DK")} USD${income.fx_approximate ? " · kurs delvist estimeret" : ""}`} />
        <StatCard testid="tax-card-expenses" label="Udgifter" icon={TrendingDown}
          value={kr(expenses.total_dkk)} sub={`${expenses.expenses.length} poster`} />
        <StatCard testid="tax-card-result" label="Årets resultat" icon={Receipt} tone={result < 0 ? "red" : "volt"}
          value={kr(result)} sub={`→ oplysningsskema rubrik ${data.rubrik}`} />
        <StatCard testid="tax-card-vat" label="Moms (vejledende)" icon={Percent}
          value={kr(vat.salgsmoms_if_all_dk)} sub="Salgsmoms hvis alle kunder er danske" />
      </div>

      {/* ===== Add expense ===== */}
      <div className="border border-gray-border p-5">
        <p className="text-xs uppercase tracking-widest font-bold text-volt mb-4">Tilføj udgift</p>
        <form onSubmit={addExpense} className="grid sm:grid-cols-2 lg:grid-cols-6 gap-3 items-end">
          <div className="lg:col-span-1">
            <label className="block text-[10px] uppercase tracking-widest font-bold text-ink/50 mb-1">Beløb (kr.)</label>
            <input data-testid="tax-expense-amount" type="text" inputMode="decimal" value={form.amount}
              onChange={(e) => setForm({ ...form, amount: e.target.value })} placeholder="0,00"
              className="w-full border border-gray-border bg-transparent px-3 py-2 text-sm focus:border-volt outline-none" />
          </div>
          <div className="lg:col-span-1">
            <label className="block text-[10px] uppercase tracking-widest font-bold text-ink/50 mb-1">Dato</label>
            <input data-testid="tax-expense-date" type="date" value={form.date} min="2026-01-01" max="2026-12-31"
              onChange={(e) => setForm({ ...form, date: e.target.value })}
              className="w-full border border-gray-border bg-transparent px-3 py-2 text-sm focus:border-volt outline-none" />
          </div>
          <div className="lg:col-span-1">
            <label className="block text-[10px] uppercase tracking-widest font-bold text-ink/50 mb-1">Kategori</label>
            <select data-testid="tax-expense-category" value={form.category}
              onChange={(e) => setForm({ ...form, category: e.target.value })}
              className="w-full border border-gray-border bg-transparent px-3 py-2 text-sm focus:border-volt outline-none">
              {Object.entries(data.categories).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          </div>
          <div className="lg:col-span-2">
            <label className="block text-[10px] uppercase tracking-widest font-bold text-ink/50 mb-1">Note</label>
            <input data-testid="tax-expense-note" type="text" value={form.note} maxLength={300}
              onChange={(e) => setForm({ ...form, note: e.target.value })} placeholder="fx Emergent-abonnement juni"
              className="w-full border border-gray-border bg-transparent px-3 py-2 text-sm focus:border-volt outline-none" />
          </div>
          <div className="lg:col-span-1 flex flex-col gap-2">
            <label className="flex items-center gap-2 text-xs text-ink/70 cursor-pointer select-none">
              <input data-testid="tax-expense-vat" type="checkbox" checked={form.vat}
                onChange={(e) => setForm({ ...form, vat: e.target.checked })} className="accent-[#ccff00]" />
              Dansk køb m. moms
            </label>
            <button data-testid="tax-expense-submit" type="submit" disabled={saving}
              className="flex items-center justify-center gap-2 bg-forest hover:bg-forest-pop text-white text-xs uppercase tracking-widest font-black px-4 py-2.5 transition-colors disabled:opacity-50">
              {saving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Plus className="w-3.5 h-3.5" />} Gem
            </button>
          </div>
          <div className="sm:col-span-2 lg:col-span-6">
            <label className="flex items-center gap-2 text-xs text-ink/55 cursor-pointer">
              <Paperclip className="w-3.5 h-3.5" />
              <span>Kvittering (valgfri — jpg/png/pdf, max 15 MB):</span>
              <input data-testid="tax-expense-receipt" ref={fileRef} type="file" accept=".jpg,.jpeg,.png,.webp,.pdf,.heic" className="text-xs" />
            </label>
          </div>
        </form>
      </div>

      {/* ===== Two-column: monthly income + expense list ===== */}
      <div className="grid lg:grid-cols-2 gap-6">
        <div className="border border-gray-border p-5">
          <p className="text-xs uppercase tracking-widest font-bold text-volt mb-3">Indtægter pr. måned (auto fra Stripe)</p>
          <table className="w-full text-sm" data-testid="tax-income-table">
            <tbody>
              {income.monthly.map((m) => (
                <tr key={m.month} className={`border-b border-gray-border/40 ${m.count === 0 ? "text-ink/30" : ""}`}>
                  <td className="py-1.5 font-bold uppercase text-xs tracking-wider">{MONTHS[m.month - 1]}</td>
                  <td className="py-1.5 text-right font-mono text-xs">{m.count} stk.</td>
                  <td className="py-1.5 text-right font-mono">{kr(m.gross_dkk)}</td>
                </tr>
              ))}
              <tr>
                <td className="py-2 font-black uppercase text-xs tracking-wider">I alt</td>
                <td className="py-2 text-right font-mono text-xs">{income.count} stk.</td>
                <td className="py-2 text-right font-mono font-bold">{kr(income.total_dkk)}</td>
              </tr>
            </tbody>
          </table>
          <p className="mt-2 text-[10px] text-ink/40">USD omregnet til DKK med ECB-dagskursen på betalingsdagen.</p>
        </div>

        <div className="border border-gray-border p-5">
          <p className="text-xs uppercase tracking-widest font-bold text-volt mb-3">Udgifter ({expenses.expenses.length})</p>
          {expenses.by_category.length > 0 && (
            <div className="flex flex-wrap gap-2 mb-4">
              {expenses.by_category.map((c) => (
                <span key={c.category} className="px-2 py-1 bg-ink/5 text-xs font-bold">{c.label}: {kr(c.total_dkk)}</span>
              ))}
            </div>
          )}
          <div className="divide-y divide-gray-border/40 max-h-[420px] overflow-y-auto" data-testid="tax-expense-list">
            {expenses.expenses.length === 0 && <p className="text-sm text-ink/40 py-4">Ingen udgifter endnu — tilføj din første ovenfor.</p>}
            {expenses.expenses.map((e) => (
              <div key={e.id} data-testid={`tax-expense-row-${e.id}`} className="py-2.5 flex items-center gap-3 text-sm">
                <span className="font-mono text-xs text-ink/50 shrink-0">{e.date}</span>
                <span className="font-bold shrink-0">{data.categories[e.category] || e.category}</span>
                <span className="text-ink/60 truncate">{e.note}</span>
                {e.receipt_url && (
                  <a href={`${process.env.REACT_APP_BACKEND_URL}${e.receipt_url}`} target="_blank" rel="noreferrer"
                    className="text-volt shrink-0" title="Se kvittering"><Paperclip className="w-3.5 h-3.5" /></a>
                )}
                <span className="ml-auto font-mono shrink-0">{kr(e.amount_dkk)}</span>
                <button data-testid={`tax-expense-delete-${e.id}`} onClick={() => removeExpense(e.id)} disabled={deletingId === e.id}
                  className="text-ink/30 hover:text-red-400 transition-colors shrink-0" title="Slet">
                  {deletingId === e.id ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Trash2 className="w-3.5 h-3.5" />}
                </button>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* ===== VAT ===== */}
      <div className="border border-gray-border p-5" data-testid="tax-vat-section">
        <p className="text-xs uppercase tracking-widest font-bold text-volt mb-3">Moms-overblik</p>
        <div className="grid sm:grid-cols-2 gap-4 mb-3">
          {vat.half_year.map((h) => (
            <div key={h.label} className="bg-ink/5 p-4">
              <p className="text-xs font-bold uppercase tracking-wider text-ink/60">{h.label}</p>
              <p className="font-barlow font-black text-xl mt-1">{kr(h.revenue_dkk)}</p>
              <p className="text-xs text-ink/45 mt-1">Indberetningsfrist: {h.deadline}</p>
            </div>
          ))}
        </div>
        <p className="text-xs text-ink/60">Fradragsberettiget købsmoms (danske køb markeret med moms): <b>{kr(vat.koebsmoms_deductible)}</b></p>
        <p className="text-xs text-ink/45 mt-2">{vat.note}</p>
      </div>

      {/* ===== Guide ===== */}
      <div className="border border-gray-border p-5" data-testid="tax-guide-section">
        <p className="text-xs uppercase tracking-widest font-bold text-volt mb-3">Sådan indberetter du — trin for trin</p>
        <div className="divide-y divide-gray-border/40">
          {data.guide.map((g, i) => (
            <div key={i}>
              <button data-testid={`tax-guide-step-${i}`} type="button" onClick={() => setOpenGuide(openGuide === i ? null : i)}
                className="w-full flex items-center justify-between py-3 text-left text-sm font-bold hover:text-forest transition-colors">
                {g.title}
                <ChevronDown className={`w-4 h-4 transition-transform ${openGuide === i ? "rotate-180" : ""}`} />
              </button>
              {openGuide === i && <p className="pb-4 text-sm text-ink/65 leading-relaxed">{g.body}</p>}
            </div>
          ))}
        </div>
        <p className="mt-4 text-[10px] text-ink/40">{data.disclaimer}</p>
      </div>
    </div>
  );
}
