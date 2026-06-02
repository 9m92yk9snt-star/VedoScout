import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import Navigation from "@/components/Navigation";
import api from "@/lib/api";
import {
  Users, FileVideo, FileCheck2, BadgeDollarSign, Save, Unlock, Trash2, Loader2,
} from "lucide-react";

const tabs = [
  { id: "stats", label: "Overview" },
  { id: "reports", label: "Reports" },
  { id: "users", label: "Users" },
  { id: "payments", label: "Payments" },
  { id: "settings", label: "Settings" },
];

export default function AdminPage() {
  const [activeTab, setActiveTab] = useState("stats");
  const [stats, setStats] = useState(null);
  const [reports, setReports] = useState([]);
  const [users, setUsers] = useState([]);
  const [payments, setPayments] = useState([]);
  const [price, setPrice] = useState(399);
  const [priceInput, setPriceInput] = useState("");
  const [savingPrice, setSavingPrice] = useState(false);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    try {
      const [s, r, u, p, pr] = await Promise.all([
        api.get("/admin/stats"),
        api.get("/admin/reports"),
        api.get("/admin/users"),
        api.get("/admin/payments"),
        api.get("/settings/price"),
      ]);
      setStats(s.data);
      setReports(r.data);
      setUsers(u.data);
      setPayments(p.data);
      setPrice(pr.data.price_dkk);
      setPriceInput(String(pr.data.price_dkk));
    } catch (err) {
      toast.error("Failed to load admin data");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const handlePriceSave = async () => {
    const v = parseFloat(priceInput);
    if (!v || v <= 0) {
      toast.error("Enter a valid positive price");
      return;
    }
    setSavingPrice(true);
    try {
      await api.put("/admin/price", { price_dkk: v });
      setPrice(v);
      toast.success(`Price updated to ${v} DKK`);
    } catch (err) {
      toast.error("Failed to update price");
    } finally {
      setSavingPrice(false);
    }
  };

  const handleUnlock = async (id) => {
    try {
      await api.post(`/admin/reports/${id}/unlock`);
      toast.success("Report manually unlocked");
      load();
    } catch (err) {
      toast.error("Unlock failed");
    }
  };

  const handleDelete = async (id) => {
    if (!window.confirm("Delete this report and video permanently?")) return;
    try {
      await api.delete(`/admin/reports/${id}`);
      toast.success("Report deleted");
      load();
    } catch (err) {
      toast.error("Delete failed");
    }
  };

  return (
    <div className="min-h-screen bg-deepnavy text-white">
      <Navigation />
      <div className="pt-28 pb-16 px-6">
        <div className="max-w-7xl mx-auto">
          <div>
            <span className="text-volt text-xs uppercase tracking-[0.25em] font-bold">Control Room</span>
            <h1 data-testid="admin-title" className="mt-3 font-barlow font-black uppercase text-4xl md:text-5xl tracking-tighter leading-[0.95]">
              Admin dashboard
            </h1>
          </div>

          {/* Tabs */}
          <div className="mt-8 border-b border-white/10 flex gap-1 overflow-x-auto">
            {tabs.map((t) => (
              <button
                key={t.id}
                onClick={() => setActiveTab(t.id)}
                data-testid={`admin-tab-${t.id}`}
                className={`px-5 py-3 uppercase tracking-widest text-xs font-bold transition-colors whitespace-nowrap ${
                  activeTab === t.id ? "text-volt border-b-2 border-volt" : "text-white/50 hover:text-white"
                }`}
              >
                {t.label}
              </button>
            ))}
          </div>

          {loading ? (
            <div className="text-center py-20">
              <Loader2 className="w-6 h-6 animate-spin text-volt mx-auto" />
            </div>
          ) : (
            <div className="mt-8">
              {activeTab === "stats" && stats && (
                <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-px bg-white/10 border border-white/10">
                  {[
                    { icon: Users, label: "Total users", val: stats.total_users, suffix: "" },
                    { icon: FileVideo, label: "Total uploads", val: stats.total_uploads, suffix: "" },
                    { icon: FileCheck2, label: "Paid reports", val: stats.total_paid_reports, suffix: "" },
                    { icon: BadgeDollarSign, label: "Revenue", val: stats.revenue_dkk.toFixed(2), suffix: " DKK" },
                  ].map((s, i) => (
                    <div key={i} data-testid={`admin-stat-${i}`} className="bg-surface p-6">
                      <s.icon className="w-7 h-7 text-volt mb-4" strokeWidth={1.5} />
                      <div className="text-xs uppercase tracking-[0.2em] font-bold text-white/40">{s.label}</div>
                      <div className="mt-2 font-barlow font-black text-4xl text-white">{s.val}{s.suffix}</div>
                    </div>
                  ))}
                </div>
              )}

              {activeTab === "reports" && (
                <div className="border border-white/10 overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead className="bg-volt text-deepnavy uppercase text-xs tracking-widest font-bold">
                      <tr>
                        <th className="p-3 text-left">Player</th>
                        <th className="p-3 text-left">User</th>
                        <th className="p-3 text-left">Created</th>
                        <th className="p-3 text-left">Status</th>
                        <th className="p-3 text-right">Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {reports.map((r) => (
                        <tr key={r.id} data-testid={`admin-report-row-${r.id}`} className="bg-surface border-t border-white/5">
                          <td className="p-3">
                            <div className="font-bold text-white">{r.player_details?.player_name}</div>
                            <div className="text-xs text-white/50">{r.player_details?.position} · age {r.player_details?.age}</div>
                          </td>
                          <td className="p-3 text-white/70 text-xs">{r.user_email}</td>
                          <td className="p-3 text-white/60 text-xs">{new Date(r.created_at).toLocaleString()}</td>
                          <td className="p-3">
                            {r.is_paid || r.manually_unlocked ? (
                              <span className="text-volt uppercase text-xs font-bold tracking-widest">Premium</span>
                            ) : (
                              <span className="text-white/50 uppercase text-xs font-bold tracking-widest">Preview</span>
                            )}
                          </td>
                          <td className="p-3 text-right">
                            <div className="flex gap-2 justify-end">
                              {!(r.is_paid || r.manually_unlocked) && (
                                <button
                                  onClick={() => handleUnlock(r.id)}
                                  data-testid={`admin-unlock-${r.id}`}
                                  title="Manually unlock"
                                  className="text-volt hover:bg-volt hover:text-deepnavy p-2 transition-colors"
                                >
                                  <Unlock className="w-4 h-4" />
                                </button>
                              )}
                              <button
                                onClick={() => handleDelete(r.id)}
                                data-testid={`admin-delete-${r.id}`}
                                title="Delete report"
                                className="text-red-400 hover:bg-red-400 hover:text-deepnavy p-2 transition-colors"
                              >
                                <Trash2 className="w-4 h-4" />
                              </button>
                            </div>
                          </td>
                        </tr>
                      ))}
                      {reports.length === 0 && (
                        <tr><td colSpan="5" className="p-8 text-center text-white/40 bg-surface">No reports yet</td></tr>
                      )}
                    </tbody>
                  </table>
                </div>
              )}

              {activeTab === "users" && (
                <div className="border border-white/10 overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead className="bg-volt text-deepnavy uppercase text-xs tracking-widest font-bold">
                      <tr>
                        <th className="p-3 text-left">Name</th>
                        <th className="p-3 text-left">Email</th>
                        <th className="p-3 text-left">Role</th>
                        <th className="p-3 text-left">Joined</th>
                      </tr>
                    </thead>
                    <tbody>
                      {users.map((u) => (
                        <tr key={u.id} className="bg-surface border-t border-white/5">
                          <td className="p-3 text-white">{u.full_name}</td>
                          <td className="p-3 text-white/70 text-xs">{u.email}</td>
                          <td className="p-3">
                            <span className={`uppercase text-xs font-bold tracking-widest ${u.role === "admin" ? "text-volt" : "text-white/50"}`}>{u.role}</span>
                          </td>
                          <td className="p-3 text-white/60 text-xs">{new Date(u.created_at).toLocaleDateString()}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              {activeTab === "payments" && (
                <div className="border border-white/10 overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead className="bg-volt text-deepnavy uppercase text-xs tracking-widest font-bold">
                      <tr>
                        <th className="p-3 text-left">Date</th>
                        <th className="p-3 text-left">User</th>
                        <th className="p-3 text-left">Amount</th>
                        <th className="p-3 text-left">Status</th>
                        <th className="p-3 text-left">Session</th>
                      </tr>
                    </thead>
                    <tbody>
                      {payments.map((p) => (
                        <tr key={p.id} className="bg-surface border-t border-white/5">
                          <td className="p-3 text-white/60 text-xs">{new Date(p.created_at).toLocaleString()}</td>
                          <td className="p-3 text-white/70 text-xs">{p.user_email}</td>
                          <td className="p-3 text-white font-bold">{p.amount} {(p.currency || "").toUpperCase()}</td>
                          <td className="p-3">
                            <span className={`uppercase text-xs font-bold tracking-widest ${p.payment_status === "paid" ? "text-volt" : "text-white/50"}`}>
                              {p.payment_status}
                            </span>
                          </td>
                          <td className="p-3 text-white/40 text-[10px] font-mono break-all">{p.session_id}</td>
                        </tr>
                      ))}
                      {payments.length === 0 && (
                        <tr><td colSpan="5" className="p-8 text-center text-white/40 bg-surface">No payments yet</td></tr>
                      )}
                    </tbody>
                  </table>
                </div>
              )}

              {activeTab === "settings" && (
                <div className="bg-surface border border-white/10 p-6 md:p-8 max-w-xl">
                  <h2 className="font-barlow font-black uppercase text-2xl text-white">Pricing</h2>
                  <p className="mt-2 text-white/60 text-sm">Modify the one-time premium report price.</p>

                  <div className="mt-6">
                    <label className="text-xs uppercase tracking-[0.2em] font-bold text-white/50 block mb-2">Current price (DKK)</label>
                    <div className="flex gap-2">
                      <input
                        type="number"
                        min="1"
                        step="1"
                        value={priceInput}
                        onChange={(e) => setPriceInput(e.target.value)}
                        data-testid="admin-price-input"
                        className="flex-1 bg-deepnavy border border-white/10 px-3 py-3 text-white focus:outline-none focus:border-volt focus:ring-1 focus:ring-volt"
                      />
                      <button
                        onClick={handlePriceSave}
                        disabled={savingPrice}
                        data-testid="admin-price-save"
                        className="bg-volt hover:bg-white text-deepnavy font-barlow font-black uppercase tracking-widest text-sm px-6 transition-colors disabled:opacity-50 flex items-center gap-2"
                      >
                        {savingPrice ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
                        Save
                      </button>
                    </div>
                    <p className="mt-3 text-xs text-white/40">Currently active: <span className="text-volt font-bold">{price} DKK</span></p>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
