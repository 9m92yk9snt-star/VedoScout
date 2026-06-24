import React, { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import Navigation from "@/components/Navigation";
import api from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import {
  Users, FileVideo, FileCheck2, BadgeDollarSign, Save, Unlock, Trash2, Loader2,
  ShieldCheck, UserPlus, X, Crown, UserCheck, Eye, EyeOff, Mail, MailOpen, Inbox,
  Share2, Twitter, Facebook, Linkedin, Instagram, Layout,
} from "lucide-react";
import ScoutQueue from "@/components/ScoutQueue";
import BlogAdmin from "@/components/BlogAdmin";

const ALL_TABS = [
  { id: "stats", label: "Overview", role: "admin" },
  { id: "scouts", label: "Scout Queue", role: "both" },
  { id: "reports", label: "Reports", role: "admin" },
  { id: "users", label: "Users", role: "admin" },
  { id: "messages", label: "Messages", role: "admin" },
  { id: "blog", label: "Blog", role: "admin" },
  { id: "payments", label: "Payments", role: "admin" },
  { id: "settings", label: "Settings", role: "admin" },
];

const SEGMENT_META = {
  all:     { label: "All users",  color: "text-ink" },
  free:    { label: "Free",       color: "text-ink/70" },
  premium: { label: "Premium",    color: "text-volt" },
  scout:   { label: "Scouts",     color: "text-blue-400" },
  admin:   { label: "Admins",     color: "text-pink-400" },
};

export default function AdminPage() {
  const { user: currentUser } = useAuth();
  const isScoutRole = currentUser?.role === "scout";
  const isAdminRole = currentUser?.role === "admin";

  const tabs = useMemo(
    () => ALL_TABS.filter((t) => t.role === "both" || (isAdminRole ? t.role === "admin" : false)),
    [isAdminRole],
  );

  const [activeTab, setActiveTab] = useState(isScoutRole ? "scouts" : "stats");
  const [stats, setStats] = useState(null);
  const [reports, setReports] = useState([]);
  const [users, setUsers] = useState([]);
  const [payments, setPayments] = useState([]);
  const [messages, setMessages] = useState([]);
  const [price, setPrice] = useState(1);
  const [priceInput, setPriceInput] = useState("");
  const [passPrice, setPassPrice] = useState(1);
  const [passPriceInput, setPassPriceInput] = useState("");
  const [savingPrice, setSavingPrice] = useState(false);
  const [savingPassPrice, setSavingPassPrice] = useState(false);
  const [loading, setLoading] = useState(true);

  // Social links (admin-editable)
  const DEFAULT_SOCIAL = {
    twitter_url:   "https://twitter.com/scoutmeplay",
    facebook_url:  "https://www.facebook.com/scoutmeplay",
    linkedin_url:  "https://www.linkedin.com/company/scoutmeplay",
    instagram_url: "https://www.instagram.com/scoutmeplay",
  };
  const [social, setSocial] = useState(DEFAULT_SOCIAL);
  const [socialInput, setSocialInput] = useState(DEFAULT_SOCIAL);
  const [savingSocial, setSavingSocial] = useState(false);

  // Blog draft count — surfaced as a badge on the Blog tab
  const [blogDraftCount, setBlogDraftCount] = useState(0);

  // Active landing variant — admin toggles between long-form and minimal landing pages
  const [activeLanding, setActiveLanding] = useState("full"); // "full" | "minimal"
  const [savingLanding, setSavingLanding] = useState(false);

  // Users tab — segment filter + scout creation modal
  const [userSegment, setUserSegment] = useState("all");   // all | free | premium | scout | admin
  const [showCreateScout, setShowCreateScout] = useState(false);
  const [deletingUserId, setDeletingUserId] = useState(null);

  const load = async () => {
    setLoading(true);
    try {
      if (isScoutRole) {
        // scouts only need pricing pulled (everything else they can't see)
        const [pr] = await Promise.all([api.get("/settings/price")]);
        setPrice(pr.data.price);
        setPriceInput(String(pr.data.price));
        setPassPrice(pr.data.pass_price ?? 399);
        setPassPriceInput(String(pr.data.pass_price ?? 399));
      } else {
        const [s, r, u, p, pr, m, bd] = await Promise.all([
          api.get("/admin/stats"),
          api.get("/admin/reports"),
          api.get("/admin/users"),
          api.get("/admin/payments"),
          api.get("/settings/price"),
          api.get("/admin/contact-messages"),
          api.get("/blog/admin/posts", { params: { status: "draft" } }).catch(() => ({ data: { items: [] } })),
        ]);
        setStats(s.data);
        setReports(r.data);
        setUsers(u.data);
        setPayments(p.data);
        setPrice(pr.data.price);
        setPriceInput(String(pr.data.price));
        setPassPrice(pr.data.pass_price ?? 399);
        setPassPriceInput(String(pr.data.pass_price ?? 399));
        setMessages(m.data);
        setBlogDraftCount((bd.data?.items || []).length);
        if (pr.data.social) {
          setSocial(pr.data.social);
          setSocialInput(pr.data.social);
        }
        if (pr.data.active_landing) {
          setActiveLanding(pr.data.active_landing === "minimal" ? "minimal" : "full");
        }
      }
    } catch (err) {
      toast.error("Failed to load admin data");
    } finally {
      setLoading(false);
    }
  };

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { load(); }, []);

  const handlePriceSave = async () => {
    const v = parseFloat(priceInput);
    if (!v || v <= 0) {
      toast.error("Enter a valid positive price");
      return;
    }
    setSavingPrice(true);
    try {
      await api.put("/admin/price", { price: v });
      setPrice(v);
      toast.success(`Single report price updated to $${v} USD`);
    } catch (err) {
      toast.error("Failed to update price");
    } finally {
      setSavingPrice(false);
    }
  };

  const handlePassPriceSave = async () => {
    const v = parseFloat(passPriceInput);
    if (!v || v <= 0) {
      toast.error("Enter a valid positive price");
      return;
    }
    setSavingPassPrice(true);
    try {
      await api.put("/admin/pass-price", { price: v });
      setPassPrice(v);
      toast.success(`12-month plan price updated to $${v} USD`);
    } catch (err) {
      toast.error("Failed to update 12-month plan price");
    } finally {
      setSavingPassPrice(false);
    }
  };

  const handleLandingChange = async (next) => {
    if (next !== "full" && next !== "minimal") return;
    if (next === activeLanding) return;
    const prev = activeLanding;
    setActiveLanding(next);
    setSavingLanding(true);
    try {
      await api.put("/admin/active-landing", { active_landing: next });
      // Bust the cached copy so the public landing immediately reflects the
      // new variant on the admin's next visit too.
      try { window.localStorage.setItem("scoutmeplay.active_landing", next); } catch { /* private mode */ }
      toast.success(
        next === "minimal"
          ? "Minimal landing is now live"
          : "Full landing is now live",
      );
    } catch (err) {
      setActiveLanding(prev);
      toast.error(err?.response?.data?.detail || "Failed to switch landing variant");
    } finally {
      setSavingLanding(false);
    }
  };

  const handleSocialSave = async () => {
    const payload = {};
    for (const k of Object.keys(DEFAULT_SOCIAL)) {
      const v = (socialInput[k] || "").trim();
      if (v && !(v.startsWith("https://") || v.startsWith("http://"))) {
        toast.error(`${k.replace("_url", "").toUpperCase()} link must start with https://`);
        return;
      }
      payload[k] = v;
    }
    setSavingSocial(true);
    try {
      const { data } = await api.put("/admin/social-links", payload);
      if (data.social) {
        setSocial(data.social);
        setSocialInput(data.social);
      }
      toast.success("Social links saved");
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Failed to update social links");
    } finally {
      setSavingSocial(false);
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

  const handleDeleteUser = async (u) => {
    if (u.role === "admin") {
      toast.error("Admin accounts cannot be deleted");
      return;
    }
    const label = u.segment === "scout" ? "scout" : u.segment === "premium" ? "premium user" : "user";
    if (!window.confirm(`Delete ${label} "${u.email}"? This permanently removes their account, reports, and uploads.`)) return;
    setDeletingUserId(u.id);
    try {
      const { data } = await api.delete(`/admin/users/${u.id}`);
      toast.success(`Deleted ${u.email}${data.reports_deleted ? ` + ${data.reports_deleted} report(s)` : ""}`);
      load();
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Delete failed");
    } finally {
      setDeletingUserId(null);
    }
  };

  // ====== Contact messages ======
  const updateMessageStatus = async (msgId, status) => {
    try {
      await api.put(`/admin/contact-messages/${msgId}/status`, { status });
      setMessages((prev) => prev.map((m) => (m.id === msgId ? { ...m, status } : m)));
    } catch (err) {
      toast.error("Couldn't update message status");
    }
  };

  const deleteMessage = async (msgId) => {
    if (!window.confirm("Delete this message permanently?")) return;
    try {
      await api.delete(`/admin/contact-messages/${msgId}`);
      setMessages((prev) => prev.filter((m) => m.id !== msgId));
      toast.success("Message deleted");
    } catch (err) {
      toast.error("Delete failed");
    }
  };

  return (
    <div className="min-h-screen bg-deepnavy text-ink">
      <Navigation />
      <div className="pt-28 pb-16 px-6">
        <div className="max-w-7xl mx-auto">
          <div>
            <span className="text-volt text-xs uppercase tracking-[0.25em] font-bold">
              {isScoutRole ? "Scout console" : "Control Room"}
            </span>
            <h1 data-testid="admin-title" className="mt-3 font-barlow font-black uppercase text-4xl md:text-5xl tracking-tighter leading-[0.95]">
              {isScoutRole ? "Scout dashboard" : "Admin dashboard"}
            </h1>
            {isScoutRole && (
              <p className="mt-3 text-sm text-ink/60 max-w-xl">
                Welcome back. Review unlocked reports below — deliver your written assessment and reply to player questions in the chat thread.
              </p>
            )}
          </div>

          {/* Tabs */}
          <div className="mt-8 border-b border-gray-border flex gap-1 overflow-x-auto">
            {tabs.map((t) => {
              let badgeCount = 0;
              if (t.id === "messages") badgeCount = messages.filter((m) => m.status === "new").length;
              else if (t.id === "blog")  badgeCount = blogDraftCount;
              return (
                <button
                  key={t.id}
                  onClick={() => setActiveTab(t.id)}
                  data-testid={`admin-tab-${t.id}`}
                  className={`relative px-5 py-3 uppercase tracking-widest text-xs font-bold transition-colors whitespace-nowrap ${
                    activeTab === t.id ? "text-volt border-b-2 border-volt" : "text-ink/55 hover:text-ink"
                  }`}
                >
                  {t.label}
                  {badgeCount > 0 && (
                    <span
                      data-testid={`admin-tab-${t.id}-badge`}
                      className={`ml-2 inline-flex items-center justify-center min-w-[18px] h-[18px] px-1.5 text-[10px] font-black ${
                        t.id === "blog"
                          ? "bg-ink/12 text-ink"   /* drafts pending — subtle */
                          : "bg-volt text-white"   /* new messages — vivid */
                      }`}
                    >
                      {badgeCount}
                    </span>
                  )}
                </button>
              );
            })}
          </div>

          {loading ? (
            <div className="text-center py-20">
              <Loader2 className="w-6 h-6 animate-spin text-volt mx-auto" />
            </div>
          ) : (
            <div className="mt-8">
              {activeTab === "stats" && stats && (
                <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-px bg-cream-soft/40 border border-gray-border">
                  {[
                    { icon: Users, label: "Total users", val: stats.total_users, suffix: "" },
                    { icon: FileVideo, label: "Total uploads", val: stats.total_uploads, suffix: "" },
                    { icon: FileCheck2, label: "Paid reports", val: stats.total_paid_reports, suffix: "" },
                    { icon: BadgeDollarSign, label: "Revenue", val: (stats.revenue_usd ?? stats.revenue_dkk ?? 0).toFixed(2), suffix: " USD" },
                  ].map((s, i) => (
                    <div key={i} data-testid={`admin-stat-${i}`} className="bg-surface p-6">
                      <s.icon className="w-7 h-7 text-volt mb-4" strokeWidth={1.5} />
                      <div className="text-xs uppercase tracking-[0.2em] font-bold text-ink/50">{s.label}</div>
                      <div className="mt-2 font-barlow font-black text-4xl text-ink">{s.val}{s.suffix}</div>
                    </div>
                  ))}
                </div>
              )}

              {activeTab === "scouts" && <ScoutQueue />}

              {activeTab === "blog" && <BlogAdmin />}

              {activeTab === "reports" && (
                <div className="border border-gray-border overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead className="bg-volt text-white uppercase text-xs tracking-widest font-bold">
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
                        <tr key={r.id} data-testid={`admin-report-row-${r.id}`} className="bg-surface border-t border-gray-border">
                          <td className="p-3">
                            <div className="font-bold text-ink">{r.player_details?.player_name}</div>
                            <div className="text-xs text-ink/55">{r.player_details?.position} · age {r.player_details?.age}</div>
                          </td>
                          <td className="p-3 text-ink/70 text-xs">{r.user_email}</td>
                          <td className="p-3 text-ink/65 text-xs">{new Date(r.created_at).toLocaleString()}</td>
                          <td className="p-3">
                            {r.is_paid || r.manually_unlocked ? (
                              <span className="text-volt uppercase text-xs font-bold tracking-widest">Premium</span>
                            ) : (
                              <span className="text-ink/55 uppercase text-xs font-bold tracking-widest">Preview</span>
                            )}
                          </td>
                          <td className="p-3 text-right">
                            <div className="flex gap-2 justify-end">
                              <Link
                                to={`/report/${r.id}`}
                                data-testid={`admin-view-${r.id}`}
                                title="Open report"
                                className="text-volt hover:bg-volt hover:text-white p-2 transition-colors"
                              >
                                <Eye className="w-4 h-4" />
                              </Link>
                              {!(r.is_paid || r.manually_unlocked) && (
                                <button
                                  onClick={() => handleUnlock(r.id)}
                                  data-testid={`admin-unlock-${r.id}`}
                                  title="Manually unlock"
                                  className="text-volt hover:bg-volt hover:text-white p-2 transition-colors"
                                >
                                  <Unlock className="w-4 h-4" />
                                </button>
                              )}
                              <button
                                onClick={() => handleDelete(r.id)}
                                data-testid={`admin-delete-${r.id}`}
                                title="Delete report"
                                className="text-red-400 hover:bg-red-400 hover:text-ink p-2 transition-colors"
                              >
                                <Trash2 className="w-4 h-4" />
                              </button>
                            </div>
                          </td>
                        </tr>
                      ))}
                      {reports.length === 0 && (
                        <tr><td colSpan="5" className="p-8 text-center text-ink/50 bg-surface">No reports yet</td></tr>
                      )}
                    </tbody>
                  </table>
                </div>
              )}

              {activeTab === "users" && (
                <div className="space-y-4">
                  {/* Filter pills + Add Scout button */}
                  <div className="flex flex-wrap items-center gap-3 justify-between">
                    <div className="flex flex-wrap gap-2" data-testid="admin-users-filter">
                      {["all", "free", "premium", "scout", "admin"].map((seg) => {
                        const count = seg === "all" ? users.length : users.filter((u) => u.segment === seg).length;
                        const active = userSegment === seg;
                        const m = SEGMENT_META[seg];
                        return (
                          <button
                            key={seg}
                            onClick={() => setUserSegment(seg)}
                            data-testid={`admin-users-segment-${seg}`}
                            className={`px-4 py-2 uppercase tracking-widest text-[10px] font-bold border transition-colors ${
                              active
                                ? "bg-volt text-white border-volt"
                                : "bg-surface text-white/65 border-gray-border hover:border-ink/12 hover:text-white"
                            }`}
                          >
                            {m.label} <span className={`ml-1.5 ${active ? "text-ink/70" : "text-ink/50"}`}>{count}</span>
                          </button>
                        );
                      })}
                    </div>
                    <button
                      onClick={() => setShowCreateScout(true)}
                      data-testid="admin-add-scout-btn"
                      className="inline-flex items-center gap-2 bg-volt hover:bg-forest-pop text-white font-barlow font-black uppercase tracking-widest text-xs px-5 py-2.5 transition-colors"
                    >
                      <UserPlus className="w-4 h-4" />
                      Add scout
                    </button>
                  </div>

                  <div className="border border-gray-border overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead className="bg-volt text-white uppercase text-xs tracking-widest font-bold">
                        <tr>
                          <th className="p-3 text-left">Name</th>
                          <th className="p-3 text-left">Email</th>
                          <th className="p-3 text-left">Segment</th>
                          <th className="p-3 text-left">Reports</th>
                          <th className="p-3 text-left">Joined</th>
                          <th className="p-3 text-right">Actions</th>
                        </tr>
                      </thead>
                      <tbody>
                        {users
                          .filter((u) => userSegment === "all" || u.segment === userSegment)
                          .map((u) => {
                            const isSelf = u.id === currentUser?.id;
                            const canDelete = u.role !== "admin" && !isSelf;
                            const segIcon = u.segment === "premium" ? <Crown className="w-3 h-3" /> :
                                            u.segment === "scout"   ? <UserCheck className="w-3 h-3" /> :
                                            u.segment === "admin"   ? <ShieldCheck className="w-3 h-3" /> :
                                                                       null;
                            return (
                              <tr key={u.id} data-testid={`admin-user-row-${u.id}`} className="bg-surface border-t border-gray-border">
                                <td className="p-3 text-ink">{u.full_name}</td>
                                <td className="p-3 text-ink/70 text-xs">{u.email}</td>
                                <td className="p-3">
                                  <span className={`inline-flex items-center gap-1 uppercase text-xs font-bold tracking-widest ${SEGMENT_META[u.segment]?.color || "text-ink/55"}`}>
                                    {segIcon}
                                    {u.segment}
                                  </span>
                                </td>
                                <td className="p-3 text-ink/70 text-xs">{u.report_count ?? 0}</td>
                                <td className="p-3 text-ink/65 text-xs">{new Date(u.created_at).toLocaleDateString()}</td>
                                <td className="p-3 text-right">
                                  {canDelete ? (
                                    <button
                                      onClick={() => handleDeleteUser(u)}
                                      disabled={deletingUserId === u.id}
                                      data-testid={`admin-delete-user-${u.id}`}
                                      title="Delete user"
                                      className="text-red-400 hover:bg-red-400 hover:text-ink p-2 transition-colors disabled:opacity-40"
                                    >
                                      {deletingUserId === u.id ? <Loader2 className="w-4 h-4 animate-spin" /> : <Trash2 className="w-4 h-4" />}
                                    </button>
                                  ) : (
                                    <span className="text-ink/40 text-[10px] uppercase tracking-widest">
                                      {isSelf ? "you" : "protected"}
                                    </span>
                                  )}
                                </td>
                              </tr>
                            );
                          })}
                        {users.filter((u) => userSegment === "all" || u.segment === userSegment).length === 0 && (
                          <tr><td colSpan="6" className="p-8 text-center text-ink/50 bg-surface">No users in this segment.</td></tr>
                        )}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {activeTab === "messages" && (
                <div className="space-y-4">
                  {messages.length === 0 ? (
                    <div className="border border-gray-border bg-surface p-12 text-center">
                      <Inbox className="w-10 h-10 text-ink/40 mx-auto mb-3" />
                      <p className="font-barlow font-black uppercase tracking-tight text-lg text-ink/70">No messages yet</p>
                      <p className="text-sm text-ink/50 mt-1">Contact form submissions will appear here.</p>
                    </div>
                  ) : (
                    messages.map((m) => {
                      const isNew = m.status === "new";
                      const isArchived = m.status === "archived";
                      return (
                        <div
                          key={m.id}
                          data-testid={`admin-message-${m.id}`}
                          className={`border bg-surface ${isNew ? "border-volt/40" : "border-gray-border"} ${isArchived ? "opacity-60" : ""}`}
                        >
                          <div className="px-5 py-4 flex flex-wrap items-start justify-between gap-3 border-b border-gray-border">
                            <div className="min-w-0">
                              <div className="flex items-center gap-2.5">
                                {isNew ? (
                                  <span className="inline-flex items-center gap-1 px-2 py-0.5 bg-volt text-white text-[10px] uppercase tracking-widest font-black">
                                    <Mail className="w-3 h-3" /> New
                                  </span>
                                ) : isArchived ? (
                                  <span className="inline-flex items-center gap-1 px-2 py-0.5 bg-cream-soft/30 text-ink/55 text-[10px] uppercase tracking-widest font-bold">
                                    Archived
                                  </span>
                                ) : (
                                  <span className="inline-flex items-center gap-1 px-2 py-0.5 bg-cream-soft/30 text-ink/70 text-[10px] uppercase tracking-widest font-bold">
                                    <MailOpen className="w-3 h-3" /> Read
                                  </span>
                                )}
                                <span className="font-barlow font-black uppercase text-base text-ink">{m.name}</span>
                              </div>
                              <a
                                href={`mailto:${m.email}?subject=Re: Your message to ScoutMePlay`}
                                className="mt-1 inline-block text-xs text-volt hover:underline break-all"
                              >
                                {m.email}
                              </a>
                              <p className="mt-1 text-[10px] uppercase tracking-[0.22em] font-bold text-ink/45">
                                {new Date(m.created_at).toLocaleString()}
                              </p>
                            </div>
                            <div className="flex items-center gap-2 shrink-0">
                              {isNew && (
                                <button
                                  onClick={() => updateMessageStatus(m.id, "read")}
                                  data-testid={`admin-msg-mark-read-${m.id}`}
                                  className="text-xs uppercase tracking-widest font-bold text-ink/60 hover:text-volt px-2 py-1 transition-colors"
                                >
                                  Mark read
                                </button>
                              )}
                              {!isArchived ? (
                                <button
                                  onClick={() => updateMessageStatus(m.id, "archived")}
                                  data-testid={`admin-msg-archive-${m.id}`}
                                  className="text-xs uppercase tracking-widest font-bold text-ink/60 hover:text-volt px-2 py-1 transition-colors"
                                >
                                  Archive
                                </button>
                              ) : (
                                <button
                                  onClick={() => updateMessageStatus(m.id, "read")}
                                  data-testid={`admin-msg-unarchive-${m.id}`}
                                  className="text-xs uppercase tracking-widest font-bold text-ink/60 hover:text-volt px-2 py-1 transition-colors"
                                >
                                  Unarchive
                                </button>
                              )}
                              <button
                                onClick={() => deleteMessage(m.id)}
                                data-testid={`admin-msg-delete-${m.id}`}
                                title="Delete"
                                className="text-red-400 hover:bg-red-400 hover:text-ink p-2 transition-colors"
                              >
                                <Trash2 className="w-4 h-4" />
                              </button>
                            </div>
                          </div>
                          <div className="px-5 py-4 text-sm text-ink/80 whitespace-pre-wrap leading-relaxed">
                            {m.message}
                          </div>
                        </div>
                      );
                    })
                  )}
                </div>
              )}

              {activeTab === "payments" && (
                <div className="border border-gray-border overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead className="bg-volt text-white uppercase text-xs tracking-widest font-bold">
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
                        <tr key={p.id} className="bg-surface border-t border-gray-border">
                          <td className="p-3 text-ink/65 text-xs">{new Date(p.created_at).toLocaleString()}</td>
                          <td className="p-3 text-ink/70 text-xs">{p.user_email}</td>
                          <td className="p-3 text-ink font-bold">{p.amount} {(p.currency || "").toUpperCase()}</td>
                          <td className="p-3">
                            <span className={`uppercase text-xs font-bold tracking-widest ${p.payment_status === "paid" ? "text-volt" : "text-ink/55"}`}>
                              {p.payment_status}
                            </span>
                          </td>
                          <td className="p-3 text-ink/50 text-[10px] font-mono break-all">{p.session_id}</td>
                        </tr>
                      ))}
                      {payments.length === 0 && (
                        <tr><td colSpan="5" className="p-8 text-center text-ink/50 bg-surface">No payments yet</td></tr>
                      )}
                    </tbody>
                  </table>
                </div>
              )}

              {activeTab === "settings" && (
                <div className="space-y-6 max-w-xl">
                  <div className="bg-surface border border-gray-border p-6 md:p-8">
                    <div className="flex items-center gap-2 mb-1">
                      <BadgeDollarSign className="w-4 h-4 text-volt" />
                      <span className="text-volt text-[10px] uppercase tracking-[0.22em] font-bold">One-time</span>
                    </div>
                    <h2 className="font-barlow font-black uppercase text-2xl text-ink">Single report price</h2>
                    <p className="mt-2 text-ink/65 text-sm">The one-time price a buyer pays to unlock a single full report (includes scout review).</p>

                    <div className="mt-6">
                      <label className="text-xs uppercase tracking-[0.2em] font-bold text-ink/55 block mb-2">Current price (USD)</label>
                      <div className="flex gap-2">
                        <input
                          type="number"
                          min="1"
                          step="1"
                          value={priceInput}
                          onChange={(e) => setPriceInput(e.target.value)}
                          data-testid="admin-price-input"
                          className="flex-1 bg-deepnavy border border-gray-border px-3 py-3 text-ink focus:outline-none focus:border-volt focus:ring-1 focus:ring-volt"
                        />
                        <button
                          onClick={handlePriceSave}
                          disabled={savingPrice}
                          data-testid="admin-price-save"
                          className="bg-volt hover:bg-forest-pop text-white font-barlow font-black uppercase tracking-widest text-sm px-6 transition-colors disabled:opacity-50 flex items-center gap-2"
                        >
                          {savingPrice ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
                          Save
                        </button>
                      </div>
                      <p className="mt-3 text-xs text-ink/50">Currently active: <span className="text-volt font-bold">${price} USD</span></p>
                    </div>
                  </div>

                  <div className="bg-surface border-2 border-volt/30 p-6 md:p-8 relative overflow-hidden">
                    <div className="absolute -top-12 -right-12 w-48 h-48 bg-volt/10 rounded-full blur-3xl pointer-events-none" />
                    <div className="flex items-center gap-2 mb-1 relative">
                      <Crown className="w-4 h-4 text-volt" />
                      <span className="text-volt text-[10px] uppercase tracking-[0.22em] font-bold">12 months · 3 reports</span>
                    </div>
                    <h2 className="font-barlow font-black uppercase text-2xl text-ink relative">12-month plan price</h2>
                    <p className="mt-2 text-ink/65 text-sm relative">
                      One-time price for the year-long plan — 3 reports + progress tracking + scout review on every report.
                    </p>

                    <div className="mt-6 relative">
                      <label className="text-xs uppercase tracking-[0.2em] font-bold text-ink/55 block mb-2">Current price (USD)</label>
                      <div className="flex gap-2">
                        <input
                          type="number"
                          min="1"
                          step="1"
                          value={passPriceInput}
                          onChange={(e) => setPassPriceInput(e.target.value)}
                          data-testid="admin-pass-price-input"
                          className="flex-1 bg-deepnavy border border-gray-border px-3 py-3 text-ink focus:outline-none focus:border-volt focus:ring-1 focus:ring-volt"
                        />
                        <button
                          onClick={handlePassPriceSave}
                          disabled={savingPassPrice}
                          data-testid="admin-pass-price-save"
                          className="bg-volt hover:bg-forest-pop text-white font-barlow font-black uppercase tracking-widest text-sm px-6 transition-colors disabled:opacity-50 flex items-center gap-2"
                        >
                          {savingPassPrice ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
                          Save
                        </button>
                      </div>
                      <p className="mt-3 text-xs text-ink/50">Currently active: <span className="text-volt font-bold">${passPrice} USD</span></p>
                    </div>
                  </div>

                  {/* ── Landing variant toggle ── */}
                  <div className="bg-surface border border-gray-border p-6 md:p-8" data-testid="admin-landing-card">
                    <div className="flex items-center gap-2 mb-1">
                      <Layout className="w-4 h-4 text-volt" />
                      <span className="text-volt text-[10px] uppercase tracking-[0.22em] font-bold">Public homepage</span>
                    </div>
                    <h2 className="font-barlow font-black uppercase text-2xl text-ink">Active landing variant</h2>
                    <p className="mt-2 text-ink/65 text-sm">
                      Choose which landing page non-logged-in visitors see on{" "}
                      <span className="font-bold text-ink">scoutmeplay.com</span>.
                      The Full variant is the long-form marketing page; the Minimal variant is a short conversion-focused page (Hero → Pricing → FAQ → Footer).
                    </p>

                    <div className="mt-6 grid grid-cols-1 sm:grid-cols-2 gap-3">
                      {[
                        {
                          id: "full",
                          label: "Full",
                          desc: "Long-form marketing page (Hero, Walkthrough, What you get, Sample, Pricing, FAQ, Final CTA).",
                        },
                        {
                          id: "minimal",
                          label: "Minimal",
                          desc: "Short, conversion-focused page (Hero, Pricing, FAQ, Footer).",
                        },
                      ].map(({ id, label, desc }) => {
                        const isActive = activeLanding === id;
                        return (
                          <button
                            key={id}
                            type="button"
                            disabled={savingLanding}
                            onClick={() => handleLandingChange(id)}
                            data-testid={`admin-landing-${id}-btn`}
                            className={`text-left p-4 border-2 transition-all relative ${
                              isActive
                                ? "border-volt bg-volt/10"
                                : "border-gray-border bg-deepnavy hover:border-forest/60"
                            } disabled:opacity-60 disabled:cursor-wait`}
                          >
                            <div className="flex items-center justify-between gap-3">
                              <span className="font-barlow font-black uppercase tracking-widest text-base text-ink">
                                {label}
                              </span>
                              {isActive && (
                                <span className="text-[9px] uppercase tracking-[0.22em] font-bold bg-volt text-ink px-2 py-0.5">
                                  Active
                                </span>
                              )}
                              {!isActive && savingLanding && (
                                <Loader2 className="w-4 h-4 animate-spin text-volt" />
                              )}
                            </div>
                            <p className="mt-2 text-xs text-ink/65 leading-relaxed">{desc}</p>
                          </button>
                        );
                      })}
                    </div>
                    <p className="mt-4 text-xs text-ink/50">
                      Currently live: <span className="text-volt font-bold uppercase tracking-widest">{activeLanding}</span>
                      {" · "}
                      <span className="text-ink/40">Changes apply instantly to new visitors. Existing tabs may need a refresh.</span>
                    </p>
                  </div>

                  {/* ── Social Links card ── */}
                  <div className="bg-surface border border-gray-border p-6 md:p-8">
                    <div className="flex items-center gap-2 mb-1">
                      <Share2 className="w-4 h-4 text-volt" />
                      <span className="text-volt text-[10px] uppercase tracking-[0.22em] font-bold">Footer</span>
                    </div>
                    <h2 className="font-barlow font-black uppercase text-2xl text-ink">Social links</h2>
                    <p className="mt-2 text-ink/65 text-sm">
                      The &ldquo;Follow us&rdquo; icons in the public footer link to these URLs. Leave a field empty to hide that icon.
                    </p>

                    <div className="mt-6 space-y-4">
                      {[
                        { key: "instagram_url", label: "Instagram", Icon: Instagram, placeholder: "https://www.instagram.com/yourhandle" },
                        { key: "twitter_url",   label: "X (Twitter)", Icon: Twitter,  placeholder: "https://twitter.com/yourhandle" },
                        { key: "facebook_url",  label: "Facebook",  Icon: Facebook,  placeholder: "https://www.facebook.com/yourpage" },
                        { key: "linkedin_url",  label: "LinkedIn",  Icon: Linkedin,  placeholder: "https://www.linkedin.com/company/yourcompany" },
                      ].map(({ key, label, Icon, placeholder }) => (
                        <div key={key}>
                          <label className="text-xs uppercase tracking-[0.2em] font-bold text-ink/55 flex items-center gap-2 mb-2">
                            <Icon className="w-3.5 h-3.5 text-forest" strokeWidth={1.8} />
                            {label}
                          </label>
                          <input
                            type="url"
                            value={socialInput[key] || ""}
                            onChange={(e) => setSocialInput({ ...socialInput, [key]: e.target.value })}
                            placeholder={placeholder}
                            data-testid={`admin-social-${key.replace("_url", "")}-input`}
                            className="w-full bg-deepnavy border border-gray-border px-3 py-3 text-ink text-sm focus:outline-none focus:border-volt focus:ring-1 focus:ring-volt"
                          />
                        </div>
                      ))}
                    </div>

                    <button
                      onClick={handleSocialSave}
                      disabled={savingSocial}
                      data-testid="admin-social-save"
                      className="mt-6 bg-volt hover:bg-forest-pop text-white font-barlow font-black uppercase tracking-widest text-sm px-6 py-3 transition-colors disabled:opacity-50 flex items-center gap-2"
                    >
                      {savingSocial ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
                      Save social links
                    </button>
                    <p className="mt-3 text-xs text-ink/50">
                      Currently active:&nbsp;
                      <span className="text-volt font-bold">
                        {Object.values(social).filter((v) => v).length} of 4 links live
                      </span>
                    </p>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      <CreateScoutModal
        open={showCreateScout}
        onClose={() => setShowCreateScout(false)}
        onCreated={() => {
          setShowCreateScout(false);
          setUserSegment("scout");
          load();
        }}
      />
    </div>
  );
}

// ============== Create Scout Modal ==============

function CreateScoutModal({ open, onClose, onCreated }) {
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPwd, setShowPwd] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!open) {
      setFullName("");
      setEmail("");
      setPassword("");
      setShowPwd(false);
      setSubmitting(false);
    }
  }, [open]);

  const submit = async (e) => {
    e.preventDefault();
    if (!fullName.trim() || !email.trim() || password.length < 6) {
      toast.error("Name, email and password (min 6 chars) are required.");
      return;
    }
    setSubmitting(true);
    try {
      await api.post("/admin/scouts", {
        email: email.trim().toLowerCase(),
        password,
        full_name: fullName.trim(),
      });
      toast.success(`Scout ${email} created — they can now log in and answer reports.`);
      onCreated && onCreated();
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Couldn't create scout.");
    } finally {
      setSubmitting(false);
    }
  };

  if (!open) return null;

  return (
    <div
      data-testid="create-scout-modal"
      className="fixed inset-0 z-[100] flex items-center justify-center bg-cream-card backdrop-blur-md px-4 py-6"
      onClick={onClose}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="relative w-full max-w-md border-2 border-volt/30 bg-surface/95 backdrop-blur-2xl"
        style={{ boxShadow: "0 0 80px rgba(204,255,0,0.18)" }}
      >
        <div className="flex items-center justify-between px-6 pt-5 pb-4 border-b border-gray-border">
          <div className="flex items-center gap-2.5">
            <div className="w-9 h-9 bg-volt/10 border border-volt/40 flex items-center justify-center">
              <UserCheck className="w-4 h-4 text-volt" />
            </div>
            <div>
              <div className="text-[10px] uppercase tracking-[0.22em] font-bold text-volt">Scout / Agent</div>
              <div className="font-barlow font-black uppercase text-ink text-base leading-tight mt-0.5">
                Add new scout
              </div>
            </div>
          </div>
          <button
            onClick={onClose}
            aria-label="Close"
            data-testid="create-scout-close"
            className="w-8 h-8 flex items-center justify-center text-ink/55 hover:text-volt transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <form onSubmit={submit} className="px-6 py-5 space-y-4">
          <p className="text-xs text-ink/60 leading-relaxed">
            Scouts log in and respond to unlocked reports. They can deliver the initial review and chat with the player —
            they cannot see other admin tabs, payments, or users.
          </p>

          <div>
            <label className="text-[10px] uppercase tracking-[0.22em] font-bold text-ink/55 block mb-1.5">
              Full name
            </label>
            <input
              type="text"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              placeholder="e.g. Marco Vasquez"
              data-testid="create-scout-name"
              className="w-full bg-deepnavy border border-gray-border px-3 py-2.5 text-ink text-sm focus:outline-none focus:border-volt focus:ring-1 focus:ring-volt"
              autoFocus
            />
          </div>

          <div>
            <label className="text-[10px] uppercase tracking-[0.22em] font-bold text-ink/55 block mb-1.5">
              Email
            </label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="scout@scoutmeplay.com"
              data-testid="create-scout-email"
              className="w-full bg-deepnavy border border-gray-border px-3 py-2.5 text-ink text-sm focus:outline-none focus:border-volt focus:ring-1 focus:ring-volt"
            />
          </div>

          <div>
            <label className="text-[10px] uppercase tracking-[0.22em] font-bold text-ink/55 block mb-1.5">
              Temporary password
            </label>
            <div className="relative">
              <input
                type={showPwd ? "text" : "password"}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Min 6 characters"
                data-testid="create-scout-password"
                className="w-full bg-deepnavy border border-gray-border px-3 py-2.5 pr-10 text-ink text-sm focus:outline-none focus:border-volt focus:ring-1 focus:ring-volt"
              />
              <button
                type="button"
                onClick={() => setShowPwd((v) => !v)}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-ink/50 hover:text-ink"
                tabIndex={-1}
              >
                {showPwd ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            </div>
            <p className="mt-1 text-[10px] text-ink/50">Share this with the scout securely. They can change it later via the profile settings (future feature).</p>
          </div>

          <button
            type="submit"
            disabled={submitting}
            data-testid="create-scout-submit"
            className="w-full inline-flex items-center justify-center gap-2 bg-volt hover:bg-forest-pop text-white font-barlow font-black uppercase tracking-widest text-sm px-5 py-3 transition-colors disabled:opacity-50"
          >
            {submitting ? <Loader2 className="w-4 h-4 animate-spin" /> : <UserPlus className="w-4 h-4" />}
            Create scout
          </button>
        </form>
      </div>
    </div>
  );
}
