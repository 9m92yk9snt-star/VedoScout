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
import GrowthAdmin from "@/components/admin/GrowthAdmin";
import PromoEmailsAdmin from "@/components/admin/PromoEmailsAdmin";
import ExitOfferAdmin from "@/components/admin/ExitOfferAdmin";
import ReferralAdmin from "@/components/admin/ReferralAdmin";
import FeaturedClipsAdmin from "@/components/admin/FeaturedClipsAdmin";
import ReviewsAdmin from "@/components/admin/ReviewsAdmin";
import FAQAdmin from "@/components/admin/FAQAdmin";
import EmailAdmin from "@/components/admin/EmailAdmin";
import SeoInsightsPanel from "@/components/admin/SeoInsightsPanel";
import StickyCtaAdminCard from "@/components/admin/StickyCtaAdminCard";
import ScoutVerificationAdmin from "@/components/admin/ScoutVerificationAdmin";
import DemoVideosAdmin from "@/components/admin/DemoVideosAdmin";
import GrantAccessAdmin from "@/components/admin/GrantAccessAdmin";
import DiagnosticsAdmin from "@/components/admin/DiagnosticsAdmin";
import TaxAdmin from "@/components/admin/TaxAdmin";
import TickerAdmin from "@/components/admin/TickerAdmin";
import SeoAdmin from "@/components/admin/SeoAdmin";
import SocialFollowAdmin from "@/components/admin/SocialFollowAdmin";
import { MarketingAdmin } from "@/components/admin/MarketingAdmin";
import AnalyticsDashboard from "@/components/admin/AnalyticsDashboard";

const ALL_TABS = [
  { id: "stats", label: "Overview", role: "admin" },
  { id: "analytics", label: "Analytics", role: "admin" },
  { id: "growth", label: "Growth", role: "admin" },
  { id: "marketing", label: "Marketing", role: "admin" },
  { id: "ticker", label: "Ticker", role: "admin" },
  { id: "seo", label: "SEO & Social", role: "admin" },
  { id: "reviews", label: "Reviews", role: "admin" },
  { id: "scouts", label: "Scout Queue", role: "both" },
  { id: "scout-db", label: "Scout DB Verify", role: "admin" },
  { id: "grant-access", label: "Grant Access", role: "admin" },
  { id: "demo-videos", label: "Demo Videos", role: "admin" },
  { id: "reports", label: "Reports", role: "admin" },
  { id: "users", label: "Users", role: "admin" },
  { id: "messages", label: "Messages", role: "admin" },
  { id: "email", label: "Email", role: "admin" },
  { id: "faq", label: "FAQ", role: "admin" },
  { id: "blog", label: "Blog", role: "admin" },
  { id: "payments", label: "Payments", role: "admin" },
  { id: "tax", label: "Skat", role: "admin" },
  { id: "diagnostics", label: "Diagnostics", role: "admin" },
  { id: "settings", label: "Settings", role: "admin" },
];

const SEGMENT_META = {
  all:     { label: "All users",  color: "text-ink" },
  free:    { label: "Free",       color: "text-ink/70" },
  premium: { label: "Premium",    color: "text-volt" },
  granted: { label: "Granted",    color: "text-amber-400" },
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
  const [savingPrice, setSavingPrice] = useState(false);

  // ── NEW: admin-controlled 5-tier display pricing ───────────────────
  // Drives the public Pricing Tiers component (Single one-time / Premium / VIP)
  // + the per-report extra-purchase prices shown to subscribers who exhaust
  // their monthly quota. Saved via PUT /api/admin/pricing.
  const [tierPrices, setTierPrices] = useState({ single: 129, premium: 29.99, vip: 49.99, premiumExtra: 89, vipExtra: 59 });
  const [tierInputs, setTierInputs] = useState({ single: "129", premium: "29.99", vip: "49.99", premiumExtra: "89", vipExtra: "59" });
  const [savingTierPrices, setSavingTierPrices] = useState(false);
  const [stripeSyncWarning, setStripeSyncWarning] = useState(null);

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
  const [pixels, setPixels] = useState({ meta_pixel_id: "", tiktok_pixel_id: "" });
  const [savingPixels, setSavingPixels] = useState(false);

  useEffect(() => {
    api.get("/settings/pixels")
      .then((r) => setPixels({ meta_pixel_id: r.data.meta_pixel_id || "", tiktok_pixel_id: r.data.tiktok_pixel_id || "" }))
      .catch(() => {});
  }, []);

  const savePixels = async () => {
    setSavingPixels(true);
    try {
      await api.put("/admin/pixels", pixels);
      toast.success("Marketing pixels saved");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not save pixels");
    } finally {
      setSavingPixels(false);
    }
  };

  // Blog draft count — surfaced as a badge on the Blog tab
  const [blogDraftCount, setBlogDraftCount] = useState(0);

  // Active landing variant — admin toggles between long-form and minimal landing pages
  const [activeLanding, setActiveLanding] = useState("full"); // "full" | "minimal"
  const [savingLanding, setSavingLanding] = useState(false);

  // Users tab — segment filter + scout creation modal
  const [userSegment, setUserSegment] = useState("all");   // all | free | premium | granted | scout | admin
  const [showCreateScout, setShowCreateScout] = useState(false);
  const [deletingUserId, setDeletingUserId] = useState(null);
  // Reports tab — failed/empty uploads are hidden by default (list hygiene)
  const [showFailedReports, setShowFailedReports] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      if (isScoutRole) {
        // scouts only need pricing pulled (everything else they can't see)
        const [pr] = await Promise.all([api.get("/settings/price")]);
        setPrice(pr.data.price);
        setPriceInput(String(pr.data.price));
        // Reflect tier prices even for scouts (read-only — they can't save)
        const sp = Number(pr.data.single_price) || 129;
        const pp = Number(pr.data.premium_price) || 29.99;
        const vp = Number(pr.data.vip_price) || 49.99;
        const pe = Number(pr.data.premium_extra_price) || 89;
        const ve = Number(pr.data.vip_extra_price) || 59;
        setTierPrices({ single: sp, premium: pp, vip: vp, premiumExtra: pe, vipExtra: ve });
        setTierInputs({ single: String(sp), premium: String(pp), vip: String(vp), premiumExtra: String(pe), vipExtra: String(ve) });
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
        const sp = Number(pr.data.single_price) || 129;
        const pp = Number(pr.data.premium_price) || 29.99;
        const vp = Number(pr.data.vip_price) || 49.99;
        const pe = Number(pr.data.premium_extra_price) || 89;
        const ve = Number(pr.data.vip_extra_price) || 59;
        setTierPrices({ single: sp, premium: pp, vip: vp, premiumExtra: pe, vipExtra: ve });
        setTierInputs({ single: String(sp), premium: String(pp), vip: String(vp), premiumExtra: String(pe), vipExtra: String(ve) });
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

  /**
   * Save the 3 admin-controlled DISPLAY prices in one shot.
   *
   * - `single_price` is wired directly to the one-time Single Report
   *   checkout — the saved value is what the buyer pays.
   * - `premium_price` / `vip_price` are DISPLAY values used across the
   *   public Pricing Tiers UI. Stripe Price IDs for the recurring
   *   subscriptions are immutable; the backend returns
   *   `stripe_sync_required: true` so we can surface a small note
   *   without blocking the admin save.
   */
  const handleTierPricesSave = async () => {
    const s = parseFloat(tierInputs.single);
    const p = parseFloat(tierInputs.premium);
    const v = parseFloat(tierInputs.vip);
    const pe = parseFloat(tierInputs.premiumExtra);
    const ve = parseFloat(tierInputs.vipExtra);
    if (!s || s <= 0 || !p || p <= 0 || !v || v <= 0 || !pe || pe <= 0 || !ve || ve <= 0) {
      toast.error("All prices must be positive numbers");
      return;
    }
    setSavingTierPrices(true);
    try {
      const { data } = await api.put("/admin/pricing", {
        single_price: s,
        premium_price: p,
        vip_price: v,
        premium_extra_price: pe,
        vip_extra_price: ve,
      });
      setTierPrices({
        single:       Number(data.single_price)        || s,
        premium:      Number(data.premium_price)       || p,
        vip:          Number(data.vip_price)           || v,
        premiumExtra: Number(data.premium_extra_price) || pe,
        vipExtra:     Number(data.vip_extra_price)     || ve,
      });
      setStripeSyncWarning(data.stripe_sync_error || null);
      if (data.stripe_synced?.length) {
        toast.success(`Prices saved — Stripe updated for ${data.stripe_synced.join(" + ")}. New subscribers pay the new amount.`);
      } else {
        toast.success("Plan pricing saved — site updates immediately");
      }
    } catch (err) {
      const detail = err?.response?.data?.detail || "Failed to save pricing";
      toast.error(detail);
    } finally {
      setSavingTierPrices(false);
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
    if (!window.confirm("This grants FREE premium access to this report — no payment will ever be collected, and the user will appear as GRANTED. Are you sure?")) return;
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

  const handleDeletePayment = async (id) => {
    if (!window.confirm("Delete this payment row from the list? (Does not affect unlocks or credits.)")) return;
    try {
      await api.delete(`/admin/payments/${id}`);
      toast.success("Payment row deleted");
      setPayments((prev) => prev.filter((p) => p.id !== id));
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

              {activeTab === "analytics" && <AnalyticsDashboard />}

              {activeTab === "growth" && (
                <>
                  <GrowthAdmin />
                  <ExitOfferAdmin />
                  <ReferralAdmin />
                </>
              )}

              {activeTab === "marketing" && (
                <>
                  <FeaturedClipsAdmin />
                  <MarketingAdmin />
                </>
              )}

              {activeTab === "ticker" && <TickerAdmin />}

              {activeTab === "seo" && (
                <div className="space-y-8">
                  <SeoInsightsPanel />
                  <SocialFollowAdmin />
                  <SeoAdmin />
                </div>
              )}

              {activeTab === "reviews" && <ReviewsAdmin />}

              {activeTab === "scouts" && <ScoutQueue />}

              {activeTab === "scout-db" && <ScoutVerificationAdmin />}

              {activeTab === "grant-access" && <GrantAccessAdmin />}
              {activeTab === "diagnostics" && <DiagnosticsAdmin />}
              {activeTab === "tax" && <TaxAdmin />}
              {activeTab === "demo-videos" && <DemoVideosAdmin />}

              {activeTab === "blog" && <BlogAdmin />}

              {activeTab === "faq" && <FAQAdmin />}

              {activeTab === "email" && (
                <>
                  <PromoEmailsAdmin />
                  <EmailAdmin />
                </>
              )}

              {activeTab === "reports" && (() => {
                const isFailedOrEmpty = (r) =>
                  r.analysis_status === "failed" || (!r.preview && r.analysis_status !== "analyzing");
                const okReports = reports.filter((r) => !isFailedOrEmpty(r));
                const failedReports = reports.filter(isFailedOrEmpty);
                const visible = showFailedReports ? failedReports : okReports;
                return (
                <div className="space-y-3">
                  <div className="flex items-center justify-between flex-wrap gap-2">
                    <span className="text-xs uppercase tracking-widest font-bold text-white/60">
                      {showFailedReports ? `Failed / empty uploads (${failedReports.length})` : `Analyses (${okReports.length})`}
                    </span>
                    {failedReports.length > 0 && (
                      <button
                        onClick={() => setShowFailedReports((v) => !v)}
                        data-testid="admin-toggle-failed-reports"
                        className="px-4 py-2 uppercase tracking-widest text-[10px] font-bold border border-gray-border text-white/65 hover:text-white hover:border-ink/12 transition-colors"
                      >
                        {showFailedReports ? "← Back to analyses" : `Show failed / empty (${failedReports.length})`}
                      </button>
                    )}
                  </div>
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
                      {visible.map((r) => (
                        <tr key={r.id} data-testid={`admin-report-row-${r.id}`} className="bg-surface border-t border-gray-border">
                          <td className="p-3">
                            <div className="font-bold text-ink">{r.player_details?.player_name}</div>
                            <div className="text-xs text-ink/55">{r.player_details?.position} · age {r.player_details?.age}</div>
                          </td>
                          <td className="p-3 text-ink/70 text-xs">{r.user_email}</td>
                          <td className="p-3 text-ink/65 text-xs">{new Date(r.created_at).toLocaleString()}</td>
                          <td className="p-3">
                            {isFailedOrEmpty(r) ? (
                              <span className="text-red-400 uppercase text-xs font-bold tracking-widest">Failed</span>
                            ) : r.is_paid || r.manually_unlocked ? (
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
                      {visible.length === 0 && (
                        <tr><td colSpan="5" className="p-8 text-center text-ink/50 bg-surface">{showFailedReports ? "No failed uploads" : "No reports yet"}</td></tr>
                      )}
                    </tbody>
                  </table>
                </div>
                </div>
                );
              })()}

              {activeTab === "users" && (
                <div className="space-y-4">
                  {/* Filter pills + Add Scout button */}
                  <div className="flex flex-wrap items-center gap-3 justify-between">
                    <div className="flex flex-wrap gap-2" data-testid="admin-users-filter">
                      {["all", "free", "premium", "granted", "scout", "admin"].map((seg) => {
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
                                            u.segment === "granted" ? <Unlock className="w-3 h-3" /> :
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
                        <th className="p-3 text-right">Actions</th>
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
                          <td className="p-3 text-right">
                            <button
                              onClick={() => handleDeletePayment(p.id)}
                              data-testid={`admin-delete-payment-${p.id}`}
                              title="Delete payment row"
                              className="text-red-400 hover:bg-red-400 hover:text-ink p-2 transition-colors"
                            >
                              <Trash2 className="w-4 h-4" />
                            </button>
                          </td>
                        </tr>
                      ))}
                      {payments.length === 0 && (
                        <tr><td colSpan="6" className="p-8 text-center text-ink/50 bg-surface">No payments yet</td></tr>
                      )}
                    </tbody>
                  </table>
                </div>
              )}

              {activeTab === "settings" && (
                <div className="space-y-6 max-w-3xl">
                  <StickyCtaAdminCard />
                  {/* ── Marketing pixels (Meta + TikTok) ── */}
                  <div data-testid="admin-pixels-card" className="bg-surface border border-gray-border p-6 md:p-8">
                    <div className="flex items-center gap-2 mb-1">
                      <BadgeDollarSign className="w-4 h-4 text-volt" />
                      <span className="text-volt text-[10px] uppercase tracking-[0.22em] font-bold">Ad tracking</span>
                    </div>
                    <h2 className="font-barlow font-black uppercase text-2xl text-ink">Marketing pixels</h2>
                    <p className="mt-2 text-ink/65 text-sm">
                      Paste your Pixel IDs and the site automatically reports <b>PageView → SignUp → InitiateCheckout → Purchase</b> to
                      Facebook/Instagram and TikTok, so your ads can optimise for buyers and retarget visitors.
                      Pixels only fire for visitors who accept marketing cookies. Leave a field empty to disable that pixel.
                    </p>
                    <div className="mt-6 grid grid-cols-1 sm:grid-cols-2 gap-4">
                      <label className="flex flex-col">
                        <span className="text-[11px] uppercase tracking-[0.22em] font-bold text-ink/55 mb-2">Meta Pixel ID</span>
                        <input
                          type="text"
                          inputMode="numeric"
                          placeholder="e.g. 1234567890123"
                          value={pixels.meta_pixel_id}
                          onChange={(e) => setPixels((p) => ({ ...p, meta_pixel_id: e.target.value }))}
                          data-testid="admin-pixel-meta-input"
                          className="bg-deepnavy border border-gray-border px-3 py-3 text-ink focus:outline-none focus:border-volt focus:ring-1 focus:ring-volt"
                        />
                        <span className="mt-1.5 text-[11px] text-ink/45">business.facebook.com → Events Manager</span>
                      </label>
                      <label className="flex flex-col">
                        <span className="text-[11px] uppercase tracking-[0.22em] font-bold text-ink/55 mb-2">TikTok Pixel ID</span>
                        <input
                          type="text"
                          placeholder="e.g. C1A2B3C4D5E6F7"
                          value={pixels.tiktok_pixel_id}
                          onChange={(e) => setPixels((p) => ({ ...p, tiktok_pixel_id: e.target.value }))}
                          data-testid="admin-pixel-tiktok-input"
                          className="bg-deepnavy border border-gray-border px-3 py-3 text-ink focus:outline-none focus:border-volt focus:ring-1 focus:ring-volt"
                        />
                        <span className="mt-1.5 text-[11px] text-ink/45">ads.tiktok.com → Assets → Events</span>
                      </label>
                    </div>
                    <button
                      type="button"
                      onClick={savePixels}
                      disabled={savingPixels}
                      data-testid="admin-pixel-save-btn"
                      className="mt-5 flex items-center gap-2 bg-forest hover:bg-forest-pop text-white text-[11px] uppercase tracking-[0.18em] font-black px-6 py-3 transition-colors disabled:opacity-50"
                    >
                      {savingPixels ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : null} Save pixels
                    </button>
                  </div>

                  {/* ── NEW: 3-tier display pricing card ── */}
                  <div
                    data-testid="admin-tier-pricing-card"
                    className="bg-surface border border-gray-border p-6 md:p-8"
                  >
                    <div className="flex items-center gap-2 mb-1">
                      <BadgeDollarSign className="w-4 h-4 text-volt" />
                      <span className="text-volt text-[10px] uppercase tracking-[0.22em] font-bold">Plan pricing</span>
                    </div>
                    <h2 className="font-barlow font-black uppercase text-2xl text-ink">Public tier prices</h2>
                    <p className="mt-2 text-ink/65 text-sm">
                      These three values drive every Pricing card across the site (landing page, dashboard
                      upgrade banner, FAQ). Saved instantly &mdash; the public site refreshes on next load.
                    </p>

                    <div className="mt-6 grid grid-cols-1 sm:grid-cols-3 gap-4">
                      {/* Single one-time */}
                      <label className="flex flex-col">
                        <span className="text-[11px] uppercase tracking-[0.22em] font-bold text-ink/55 mb-2">
                          Single Report · one-time
                        </span>
                        <div className="flex">
                          <span className="bg-deepnavy border border-r-0 border-gray-border px-3 py-3 text-ink/55 font-bold">$</span>
                          <input
                            type="number"
                            min="1"
                            step="1"
                            value={tierInputs.single}
                            onChange={(e) => setTierInputs((s) => ({ ...s, single: e.target.value }))}
                            data-testid="admin-tier-single-input"
                            className="flex-1 min-w-0 bg-deepnavy border border-gray-border px-3 py-3 text-ink focus:outline-none focus:border-volt focus:ring-1 focus:ring-volt"
                          />
                        </div>
                        <span className="mt-1.5 text-[11px] text-ink/45">Current: <span className="text-volt font-bold">${tierPrices.single}</span></span>
                      </label>

                      {/* Premium /mo */}
                      <label className="flex flex-col">
                        <span className="text-[11px] uppercase tracking-[0.22em] font-bold text-ink/55 mb-2">
                          Premium · per month
                        </span>
                        <div className="flex">
                          <span className="bg-deepnavy border border-r-0 border-gray-border px-3 py-3 text-ink/55 font-bold">$</span>
                          <input
                            type="number"
                            min="0.01"
                            step="0.01"
                            value={tierInputs.premium}
                            onChange={(e) => setTierInputs((s) => ({ ...s, premium: e.target.value }))}
                            data-testid="admin-tier-premium-input"
                            className="flex-1 min-w-0 bg-deepnavy border border-gray-border px-3 py-3 text-ink focus:outline-none focus:border-volt focus:ring-1 focus:ring-volt"
                          />
                        </div>
                        <span className="mt-1.5 text-[11px] text-ink/45">Current: <span className="text-volt font-bold">${tierPrices.premium}</span></span>
                      </label>

                      {/* VIP /mo */}
                      <label className="flex flex-col">
                        <span className="text-[11px] uppercase tracking-[0.22em] font-bold text-ink/55 mb-2">
                          VIP · per month
                        </span>
                        <div className="flex">
                          <span className="bg-deepnavy border border-r-0 border-gray-border px-3 py-3 text-ink/55 font-bold">$</span>
                          <input
                            type="number"
                            min="0.01"
                            step="0.01"
                            value={tierInputs.vip}
                            onChange={(e) => setTierInputs((s) => ({ ...s, vip: e.target.value }))}
                            data-testid="admin-tier-vip-input"
                            className="flex-1 min-w-0 bg-deepnavy border border-gray-border px-3 py-3 text-ink focus:outline-none focus:border-volt focus:ring-1 focus:ring-volt"
                          />
                        </div>
                        <span className="mt-1.5 text-[11px] text-ink/45">Current: <span className="text-volt font-bold">${tierPrices.vip}</span></span>
                      </label>
                    </div>

                    {/* ── NEW: per-report extra-purchase prices for subscribers ── */}
                    <div className="mt-6 border-t border-gray-border pt-6">
                      <div className="text-[10px] uppercase tracking-[0.22em] font-black text-volt mb-1">
                        Subscriber extra-report rates
                      </div>
                      <p className="text-[11px] text-ink/55 leading-relaxed mb-4 max-w-3xl">
                        When a Premium or VIP subscriber has used their monthly quota, they can buy additional reports at these discounted rates &mdash; cheaper than the ${tierPrices.single} single-report price. Rate charged is automatically picked based on the buyer&apos;s active tier.
                      </p>
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        {/* Premium extra */}
                        <label className="flex flex-col">
                          <span className="text-[10px] uppercase tracking-widest font-bold text-ink/55 mb-1.5">
                            Premium extra report
                          </span>
                          <div className="flex">
                            <span className="bg-deepnavy border border-r-0 border-gray-border px-3 py-3 text-ink/55 font-bold">$</span>
                            <input
                              type="number"
                              min="1"
                              step="1"
                              value={tierInputs.premiumExtra}
                              onChange={(e) => setTierInputs((s) => ({ ...s, premiumExtra: e.target.value }))}
                              data-testid="admin-tier-premium-extra-input"
                              className="flex-1 min-w-0 bg-deepnavy border border-gray-border px-3 py-3 text-ink focus:outline-none focus:border-volt focus:ring-1 focus:ring-volt"
                            />
                          </div>
                          <span className="mt-1.5 text-[11px] text-ink/45">
                            Current: <span className="text-volt font-bold">${tierPrices.premiumExtra}</span>
                            <span className="ml-1 text-ink/35">/ report</span>
                          </span>
                        </label>

                        {/* VIP extra */}
                        <label className="flex flex-col">
                          <span className="text-[10px] uppercase tracking-widest font-bold text-ink/55 mb-1.5">
                            VIP extra report
                          </span>
                          <div className="flex">
                            <span className="bg-deepnavy border border-r-0 border-gray-border px-3 py-3 text-ink/55 font-bold">$</span>
                            <input
                              type="number"
                              min="1"
                              step="1"
                              value={tierInputs.vipExtra}
                              onChange={(e) => setTierInputs((s) => ({ ...s, vipExtra: e.target.value }))}
                              data-testid="admin-tier-vip-extra-input"
                              className="flex-1 min-w-0 bg-deepnavy border border-gray-border px-3 py-3 text-ink focus:outline-none focus:border-volt focus:ring-1 focus:ring-volt"
                            />
                          </div>
                          <span className="mt-1.5 text-[11px] text-ink/45">
                            Current: <span className="text-volt font-bold">${tierPrices.vipExtra}</span>
                            <span className="ml-1 text-ink/35">/ report</span>
                          </span>
                        </label>
                      </div>
                    </div>

                    <div className="mt-5 flex items-center justify-between gap-3 flex-wrap">
                      <p className="text-[11px] text-ink/45 max-w-xl leading-relaxed">
                        Single Report is a real one-time checkout &mdash; the saved value is what the buyer pays.
                        Premium / VIP saves also update Stripe automatically: a new monthly price is created and used
                        for all new subscriptions. Existing subscribers keep the price they signed up at.
                      </p>
                      <button
                        type="button"
                        onClick={handleTierPricesSave}
                        disabled={savingTierPrices}
                        data-testid="admin-tier-save"
                        className="bg-volt hover:bg-forest-pop text-white font-barlow font-black uppercase tracking-widest text-sm px-6 py-3 transition-colors disabled:opacity-50 flex items-center gap-2"
                      >
                        {savingTierPrices ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
                        Save plan prices
                      </button>
                    </div>

                    {stripeSyncWarning && (
                      <p
                        data-testid="admin-stripe-sync-warning"
                        className="mt-3 text-[11px] text-amber-500 leading-relaxed"
                      >
                        Stripe sync problem: {stripeSyncWarning}. The site shows the new price, but checkout may
                        still charge the previous amount &mdash; try saving again.
                      </p>
                    )}
                  </div>

                  {/* ── Legacy: report_price single price card (left for backward compat) ── */}
                  <div className="bg-surface border border-gray-border p-6 md:p-8">
                    <div className="flex items-center gap-2 mb-1">
                      <BadgeDollarSign className="w-4 h-4 text-volt" />
                      <span className="text-volt text-[10px] uppercase tracking-[0.22em] font-bold">Legacy</span>
                    </div>
                    <h2 className="font-barlow font-black uppercase text-2xl text-ink">Legacy report price</h2>
                    <p className="mt-2 text-ink/65 text-sm">Older one-time-purchase value used by legacy flows. New checkouts use <span className="text-volt font-bold">Single Report</span> price above.</p>

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
