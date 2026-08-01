import React, { useEffect, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import Navigation from "@/components/Navigation";
import { MiniPitch } from "@/components/FootballAccents";
import ProfileVisibilityCard from "@/components/profile/ProfileVisibilityCard";
import ReportPaywallTiers from "@/components/ReportPaywallTiers";
import api from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { trackPurchase } from "@/lib/pixels";
import {
  Plus, Lock, CheckCircle2, Film, Loader2, Rocket, TrendingUp, AlertCircle,
  Activity, ArrowRight, Sparkles, Zap, Crown, Calendar, XCircle, RefreshCw,
} from "lucide-react";

const VERDICT_META = {
  ahead: { label: "Ahead", icon: Rocket, color: "bg-forest-pop text-white" },
  on_track: { label: "On track", icon: TrendingUp, color: "bg-forest text-white" },
  plateau: { label: "Plateau", icon: AlertCircle, color: "bg-amber-600 text-white" },
  first_report: { label: "Baseline", icon: Activity, color: "bg-cream-soft text-ink" },
};

export default function DashboardPage() {
  const { user } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const [reports, setReports] = useState([]);
  const [players, setPlayers] = useState([]);
  // Legacy Progress Pass status — still queried so we can show
  // remaining credits to users who bought the $399 pass before
  // subscriptions launched. New users never see the buy flow.
  const [passState, setPassState] = useState(null);
  const [loading, setLoading] = useState(true);

  // Subscription state — { subscription: {...}, tiers: {...}, usage: {...} } from /api/me/subscription
  const [subscription, setSubscription] = useState(null);
  const [tiers, setTiers] = useState({});
  // Monthly upload usage — drives the "Premium at limit → VIP only" banner variant
  const [usage, setUsage] = useState(null);

  const fetchAll = () => {
    Promise.allSettled([
      api.get("/reports/mine").then(({ data }) => setReports(data)),
      api.get("/progress/players").then(({ data }) => setPlayers(data.items || [])),
      api.get("/progress/pass/status").then(({ data }) => setPassState(data)),
      api.get("/me/subscription").then(({ data }) => {
        setSubscription(data.subscription);
        setTiers(data.tiers || {});
        setUsage(data.usage || null);
      }),
    ]).finally(() => setLoading(false));
  };

  useEffect(() => {
    // Paid scouts (Club/Business tier) don't belong on the player dashboard —
    // send them to their workspace: the Player Database search.
    if (user?.is_paid_scout) {
      navigate("/players-database", { replace: true });
      return;
    }
    fetchAll();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Subscription return handler — Stripe redirects back here after
  // checkout success with `?subscribe_session=cs_xxx`. We poll the
  // status endpoint (max ~10s) which idempotently persists the
  // subscription on the user record and surfaces a success toast.
  useEffect(() => {
    const params = new URLSearchParams(location.search);
    const subSession = params.get("subscribe_session");
    if (subSession) {
      params.delete("subscribe_session");
      const newSearch = params.toString();
      navigate({ pathname: location.pathname, search: newSearch ? `?${newSearch}` : "" }, { replace: true });

      const poll = async (attempts = 0) => {
        if (attempts > 5) {
          toast.info("Subscription confirmation taking a bit longer — refresh in a moment.", { duration: 8000 });
          return;
        }
        try {
          const { data } = await api.get(`/payments/subscribe/status/${subSession}`);
          if (data.payment_status === "paid") {
            trackPurchase();
            setSubscription(data.subscription);
            toast.success(`Welcome to ${data.tier === "vip" ? "VIP Premium" : "Premium"}! Your subscription is now active.`, { duration: 9000 });
            return;
          }
          setTimeout(() => poll(attempts + 1), 2000);
        } catch (err) {
          toast.error(err?.response?.data?.detail || "Couldn't confirm subscription.");
        }
      };
      poll();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.search]);

  // One-shot first-visit pulse on the locked Unlock pills, à la Linear /
  // Stripe Express. Reads a localStorage flag once on mount; if absent,
  // applies the pulse for ~1.6 s and then sets the flag so subsequent
  // visits stay calm. The flag is namespaced per-user so a different
  // free user on the same browser still gets their own first-touch hint.
  const [unlockPulseOn, setUnlockPulseOn] = useState(false);
  useEffect(() => {
    if (passState?.active) return; // premium user — no upgrade hint needed
    if (!players?.length) return;
    const key = "dashboard_unlock_pulse_seen_v1";
    try {
      if (window.localStorage.getItem(key)) return;
      setUnlockPulseOn(true);
      window.localStorage.setItem(key, "1");
      // turn the class off after the animation completes so the DOM stays clean
      const t = setTimeout(() => setUnlockPulseOn(false), 1900);
      return () => clearTimeout(t);
    } catch {
      // localStorage unavailable (private mode, etc.) — silently skip the hint
    }
  }, [passState?.active, players?.length]);

  // ─── derived stats for the quick-stats row ───
  const totalReports = reports.length;
  const premiumReports = reports.filter((r) => r.is_paid || r.manually_unlocked).length;
  const trackedPlayers = players.length;
  const lastReport = reports[0]; // assumed sorted desc by API
  const planLabel = subscription?.tier
    ? subscription.tier === "vip"
      ? "VIP Premium"
      : "Premium"
    : passState?.active
    ? "Progress Pass"
    : premiumReports > 0
    ? "Pay-per-report"
    : "Free";

  return (
    <div className="min-h-screen bg-cream-base text-ink">
      <Navigation />
      <div className="pt-28 pb-16 px-6">
        <div className="max-w-7xl mx-auto">
          <div className="flex flex-col md:flex-row md:items-end md:justify-between gap-6">
            <div>
              <span className="text-forest text-xs uppercase tracking-[0.25em] font-bold inline-flex items-center gap-2">
                <span className="relative flex items-center justify-center w-2 h-2 shrink-0" aria-hidden>
                  <span className="absolute inset-0 rounded-full bg-volt animate-ping opacity-75" />
                  <span className="relative rounded-full w-1.5 h-1.5 bg-volt" />
                </span>
                Your dashboard
              </span>
              <h1 className="mt-3 font-barlow font-black uppercase text-4xl md:text-5xl tracking-tighter leading-[0.95]">
                Welcome,{" "}
                <span className="text-forest">
                  {user?.full_name?.split(" ")[0] || "Player"}
                </span>
              </h1>
              <p className="mt-2 text-ink/65 text-sm">
                Track growth across reports, manage uploads, unlock premium analysis.
              </p>
            </div>
            <Link
              to="/upload"
              data-testid="dashboard-upload-btn"
              className="bg-forest hover:bg-forest-pop text-white font-barlow font-black uppercase tracking-widest text-sm px-6 py-3 transition-colors flex items-center gap-2 self-start md:self-end"
              style={{
                boxShadow:
                  "0 18px 36px -16px rgba(31, 79, 47, 0.45), 0 8px 16px -8px rgba(31, 79, 47, 0.3)",
              }}
            >
              <Plus className="w-4 h-4" />
              New upload
            </Link>
          </div>

          {/* QUICK STATS ROW — establishes hierarchy immediately. Hidden while loading. */}
          {!loading && (
            <div
              data-testid="dashboard-quick-stats"
              className="mt-6 md:mt-8 grid grid-cols-2 md:grid-cols-4 gap-3 md:gap-4"
            >
              <QuickStatTile icon={Film} label="Total uploads" value={totalReports} testid="qs-uploads" />
              <QuickStatTile icon={CheckCircle2} label="Premium reports" value={premiumReports} accent testid="qs-premium" />
              <QuickStatTile icon={Activity} label="Tracked players" value={trackedPlayers} testid="qs-players" />
              <QuickStatTile
                icon={planLabel === "VIP Premium" ? Crown : planLabel === "Premium" ? TrendingUp : Sparkles}
                label="Current plan"
                value={planLabel}
                small
                testid="qs-plan"
              />
            </div>
          )}

          {/* Last activity meta */}
          {!loading && lastReport && (
            <p className="mt-3 text-[11px] uppercase tracking-[0.2em] font-bold text-ink/50">
              Last upload ·{" "}
              <span className="text-forest">
                {lastReport.player_details?.player_name || "—"}
              </span>{" "}
              · {new Date(lastReport.created_at).toLocaleDateString()}
            </p>
          )}

          {loading ? (
            <div className="text-center py-16">
              <Loader2 className="w-6 h-6 animate-spin text-forest mx-auto" />
            </div>
          ) : (
            <>
              {/* PROGRESS PASS BANNER (legacy holders only) — new users
                 see <UpgradeBanner /> below instead. */}
              {passState?.active && (
                <LegacyPassActiveBanner passState={passState} />
              )}

              {/* SUBSCRIPTION CARD (Premium / VIP) — only when user has one */}
              <SubscriptionCard
                subscription={subscription}
                tiers={tiers}
                onChange={(s) => setSubscription(s)}
              />

              {/* UPGRADE BANNER — shown to:
                 (a) free users without any subscription, and
                 (b) Premium subscribers who have hit their monthly limit → banner
                     shows "Buy 1 extra report for $89" + VIP upgrade side by side.
                 (c) VIP subscribers who have hit their 4/month limit → banner
                     shows "Buy 1 extra report for $59" only (no further upgrade).
                 Skipped when: legacy Progress Pass is active. */}
              {(() => {
                const isPremiumAtLimit =
                  subscription?.tier === "premium" && usage?.exhausted;
                const isVipAtLimit =
                  subscription?.tier === "vip" && usage?.exhausted;
                const showBanner =
                  (!subscription?.tier && !passState?.active) ||
                  (isPremiumAtLimit && !passState?.active) ||
                  (isVipAtLimit && !passState?.active);
                if (!showBanner) return null;
                const mode = isVipAtLimit
                  ? "vip-at-limit"
                  : isPremiumAtLimit
                  ? "premium-at-limit"
                  : "free";
                return (
                  <UpgradeBanner
                    tiers={tiers}
                    mode={mode}
                    usage={usage}
                    latestLockedReportId={reports.find((r) => !(r.is_paid || r.manually_unlocked))?.id}
                  />
                );
              })()}

              {/* REPORTS (Library) — moved to top: this is the most-used
                 part of the dashboard; users want to jump to a report. */}
              <section className="mt-10">
                <SectionHeader
                  icon={Film}
                  eyebrow="Library"
                  title="Your reports"
                  countLabel={reports.length > 0 ? `${reports.length} ${reports.length === 1 ? "report" : "reports"}` : null}
                />
                {reports.length === 0 ? (
                  <div className="mt-4 border border-ink/10 bg-cream-card p-12 text-center">
                    <Film className="w-12 h-12 text-forest mx-auto mb-4" strokeWidth={1.5} />
                    <h3 className="font-barlow font-black uppercase text-2xl">No uploads yet</h3>
                    <p className="mt-2 text-ink/65 text-sm">Upload your first football video and receive an instant free scout preview.</p>
                    <Link
                      to="/upload"
                      data-testid="dashboard-empty-upload-btn"
                      className="inline-flex mt-6 bg-forest hover:bg-forest-pop text-white font-barlow font-black uppercase tracking-widest text-sm px-6 py-3 transition-colors items-center gap-2"
                    >
                      <Plus className="w-4 h-4" /> Upload video
                    </Link>
                  </div>
                ) : (
                  <div className="mt-4 grid sm:grid-cols-2 lg:grid-cols-3 gap-px bg-ink/10 border border-ink/10">
                    {reports.map((r) => {
                      const unlocked = r.is_paid || r.manually_unlocked;
                      return (
                        <Link
                          to={`/report/${r.id}`}
                          key={r.id}
                          data-testid={`dashboard-report-${r.id}`}
                          data-report-id={r.id}
                          className="group bg-cream-card hover:bg-white transition-colors flex flex-col overflow-hidden open-report-link"
                        >
                          <div className="relative aspect-video bg-ink overflow-hidden">
                            {r.poster_url ? (
                              <img
                                src={`${process.env.REACT_APP_BACKEND_URL}${r.poster_url}`}
                                alt={r.player_details?.player_name}
                                className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500"
                              />
                            ) : (
                              <div className="w-full h-full flex items-center justify-center bg-gradient-to-br from-ink to-forest/40">
                                <Film className="w-10 h-10 text-white/40" strokeWidth={1.5} />
                              </div>
                            )}
                            <div className="absolute inset-0 bg-gradient-to-t from-ink/80 via-transparent to-transparent" />
                            <div className="absolute top-3 left-3 right-3 flex items-center justify-between">
                              <span className="text-[10px] uppercase tracking-[0.18em] font-bold text-ink bg-cream-card/90 backdrop-blur px-2 py-1">
                                {new Date(r.created_at).toLocaleDateString()}
                              </span>
                              {unlocked ? (
                                <span className="flex items-center gap-1 bg-forest text-white text-[10px] uppercase tracking-widest font-black px-2 py-1">
                                  <CheckCircle2 className="w-3 h-3" /> Premium
                                </span>
                              ) : (
                                <span className="flex items-center gap-1 bg-cream-card/90 backdrop-blur border border-ink/15 text-ink/80 text-[10px] uppercase tracking-widest font-bold px-2 py-1">
                                  <Lock className="w-3 h-3" /> Preview
                                </span>
                              )}
                            </div>
                          </div>
                          <div className="px-4 pt-3 pb-3.5 flex-1 flex flex-col">
                            <div className="flex items-start justify-between gap-3">
                              <h3 className="font-barlow font-black uppercase text-lg text-ink group-hover:text-forest transition-colors leading-tight truncate">
                                {r.player_details?.player_name}
                              </h3>
                              <span className="text-forest text-[10px] uppercase tracking-widest font-black flex-shrink-0 mt-1">View →</span>
                            </div>
                            <div className="mt-1 flex items-center gap-2">
                              <MiniPitch position={r.player_details?.position} className="w-5 h-7 flex-shrink-0" />
                              <p className="text-[12px] text-ink/60 leading-snug">
                                {r.player_details?.position} · age {r.player_details?.age}
                                {r.player_details?.video_type ? <span className="text-ink/40"> · {r.player_details.video_type}</span> : null}
                              </p>
                            </div>
                          </div>
                        </Link>
                      );
                    })}
                  </div>
                )}
              </section>

              {/* PROFILE & VISIBILITY — Phase 1 of the paid Scout Database.
                 Players opt in here so scouts can find them via /players-database. */}
              <ProfileVisibilityCard latestReportId={reports[0]?.id} />

              {/* PLAYERS / TRAJECTORIES — moved BELOW reports. */}
              {players.length > 0 && (
                <section className="mt-12" data-testid="dashboard-players-section">
                  <SectionHeader
                    icon={Activity}
                    eyebrow="Track progress"
                    title="Your players"
                    countLabel={`${players.length} tracked`}
                  />
                  <ul className="mt-3 bg-cream-card border border-ink/10 divide-y divide-ink/10">
                    {players.map((p) => (
                      <PlayerRow
                        key={p.id}
                        p={p}
                        isPremium={!!subscription?.tier || !!passState?.active}
                        onUpgradeClick={() => {
                          // Scroll the user to the dashboard's upgrade banner so they
                          // see ALL plan options instead of a single modal.
                          const target = document.querySelector('[data-testid="dashboard-upgrade-banner"]');
                          if (target) target.scrollIntoView({ behavior: "smooth", block: "center" });
                        }}
                        pulse={unlockPulseOn}
                      />
                    ))}
                  </ul>
                </section>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}

/* ── Shared panel header used by both "Library · Your reports" and
 *    "Track progress · Your players" sections. Establishes a consistent,
 *    premium hierarchy: section icon · eyebrow label · vertical separator
 *    · title on the left, count chip on the right, then a 2-tone hairline
 *    rule (small forest segment + ink/15) for a subtle premium accent. */
function SectionHeader({ icon: Icon, eyebrow, title, countLabel }) {
  return (
    <header className="relative">
      <div className="flex items-end justify-between gap-3 pb-3">
        <div className="flex items-baseline gap-2.5 min-w-0">
          {Icon && (
            <Icon
              className="w-3.5 h-3.5 text-forest flex-shrink-0 self-center -mt-0.5"
              strokeWidth={2.4}
              aria-hidden="true"
            />
          )}
          <span className="text-forest text-[10px] uppercase tracking-[0.3em] font-black flex-shrink-0">
            {eyebrow}
          </span>
          <span className="h-3 w-px bg-ink/25 flex-shrink-0" aria-hidden="true" />
          <h2 className="font-barlow font-black uppercase text-xl md:text-2xl tracking-tighter leading-none truncate">
            {title}
          </h2>
        </div>
        {countLabel && (
          <span className="text-[10px] uppercase tracking-widest text-ink/55 font-bold flex-shrink-0">
            {countLabel}
          </span>
        )}
      </div>
      {/* 2-tone hairline accent rule */}
      <div className="relative h-px w-full bg-ink/15" aria-hidden="true">
        <span className="absolute left-0 top-0 h-px w-12 bg-forest" />
      </div>
    </header>
  );
}

/* ── Compact row in the "Your players" list. Replaces the previous
 *    PlayerCard grid because a divided row-list reads as a scannable
 *    register (Linear / Stripe Express pattern) and uses screen real
 *    estate efficiently — especially on mobile. The right-hand premium
 *    pill mirrors the report cards so users have a consistent visual
 *    language for "what's unlocked vs locked." */
function PlayerRow({ p, isPremium, onUpgradeClick, pulse = false }) {
  return (
    <li className="relative">
      {/* Left status stripe — forest when the user is on Premium / has the
          Progress Pass active, soft ink otherwise. Mirrors the report-card
          PREMIUM badge so users have a consistent visual cue. */}
      <span
        aria-hidden="true"
        className={`absolute left-0 top-0 bottom-0 w-[3px] ${
          isPremium ? "bg-forest" : "bg-ink/15"
        }`}
      />
      <Link
        to={`/trajectory/${p.id}`}
        data-testid={`player-card-${p.id}`}
        className="group flex items-center gap-3 sm:gap-4 pl-5 pr-4 py-3.5 hover:bg-cream-soft/60 transition-colors"
      >
        {/* Left rail: position badge */}
        <div className="flex-shrink-0 min-w-[88px] sm:min-w-[124px]">
          <span className="inline-flex bg-forest/10 text-forest font-barlow font-black uppercase text-[10px] tracking-[0.18em] px-2 py-1 leading-none">
            {p.last_position || "Player"}
          </span>
        </div>
        {/* Centre: name + meta */}
        <div className="flex-1 min-w-0">
          <h3 className="font-barlow font-black uppercase text-base sm:text-lg text-ink group-hover:text-forest transition-colors leading-tight truncate">
            {p.name}
          </h3>
          <p className="mt-0.5 text-[11px] text-ink/55 leading-tight truncate">
            {p.last_age ? `Age ${p.last_age}` : ""}
            {p.preferred_foot ? ` · ${p.preferred_foot} foot` : ""}
            {` · ${p.report_count} ${p.report_count === 1 ? "report" : "reports"}`}
          </p>
        </div>
        {/* Right: premium pill (when applicable) + spacer-reservation for
            the locked-upgrade button (which renders OUTSIDE this Link to
            keep the HTML valid — buttons must not be descendants of <a>) +
            navigation arrow. */}
        <div className="flex items-center gap-2 sm:gap-3 flex-shrink-0">
          {isPremium ? (
            <>
              <span className="hidden sm:flex items-center gap-1 bg-forest text-white text-[9px] uppercase tracking-widest font-black px-2 py-1">
                <CheckCircle2 className="w-3 h-3" strokeWidth={2.4} /> Premium
              </span>
              <CheckCircle2 className="sm:hidden w-4 h-4 text-forest" strokeWidth={2.4} aria-hidden="true" />
            </>
          ) : (
            <>
              {/* Reserved width so the arrow stays in the same column as
                  the premium rows — the upgrade button is absolutely
                  positioned over this space (see sibling block below). */}
              <span aria-hidden="true" className="hidden sm:inline-block w-[78px] h-[22px]" />
              <span aria-hidden="true" className="sm:hidden inline-block w-7 h-7" />
            </>
          )}
          <ArrowRight className="w-4 h-4 text-forest group-hover:translate-x-1 transition-transform" />
        </div>
      </Link>
      {/* Upgrade button — sibling of the Link (not nested!) so we don't
          produce <button> inside <a> which is invalid HTML. Absolutely
          positioned over the reserved space so it visually sits in the
          row. Tapping it opens the Progress Pass checkout without
          triggering the row navigation. */}
      {!isPremium && onUpgradeClick && (
        <>
          <button
            type="button"
            onClick={onUpgradeClick}
            data-testid={`player-row-upgrade-${p.id}`}
            aria-label={`Upgrade to unlock progress tracking for ${p.name}`}
            title="Upgrade to unlock"
            className={`${pulse ? "scoutme-unlock-pulse " : ""}hidden sm:flex absolute z-10 right-9 top-1/2 -translate-y-1/2 items-center gap-1 bg-cream-soft hover:bg-forest hover:text-white hover:border-forest border border-ink/15 text-ink/65 text-[9px] uppercase tracking-widest font-bold px-2 py-1 transition-colors cursor-pointer`}
          >
            <Lock className="w-3 h-3" strokeWidth={2.4} /> Unlock
          </button>
          <button
            type="button"
            onClick={onUpgradeClick}
            data-testid={`player-row-upgrade-mobile-${p.id}`}
            aria-label={`Upgrade to unlock progress tracking for ${p.name}`}
            className={`${pulse ? "scoutme-unlock-pulse " : ""}sm:hidden absolute z-10 right-8 top-1/2 -translate-y-1/2 inline-flex items-center justify-center w-7 h-7 text-ink/45 hover:text-forest active:text-forest transition-colors cursor-pointer`}
          >
            <Lock className="w-3.5 h-3.5" strokeWidth={2.4} />
          </button>
        </>
      )}
    </li>
  );
}

/* ────────────────────────────────────────────────────────────────────────
 *  QuickStatTile — small KPI tile used in the dashboard's top stats row.
 *  Cream-card body, forest icon badge, big number, uppercase label. Mirrors
 *  the visual language of the rest of the dashboard so the new row feels
 *  native, not bolted on.
 * ──────────────────────────────────────────────────────────────────────── */
function QuickStatTile({ icon: Icon, label, value, accent = false, small = false, testid }) {
  return (
    <div
      data-testid={testid}
      className={`relative bg-cream-card border ${
        accent ? "border-forest/40" : "border-gray-border"
      } p-4 md:p-5 flex items-start gap-3 md:gap-4 hover:border-forest/50 transition-colors`}
    >
      <span
        className={`shrink-0 w-9 h-9 md:w-10 md:h-10 flex items-center justify-center border ${
          accent ? "bg-forest text-white border-forest" : "bg-forest/10 text-forest border-forest/20"
        }`}
      >
        <Icon className="w-4 h-4 md:w-5 md:h-5" strokeWidth={2} />
      </span>
      <div className="min-w-0">
        <div
          className={`font-barlow font-black uppercase leading-none text-ink ${
            small ? "text-base md:text-lg tracking-tight" : "text-2xl md:text-3xl tracking-tighter"
          }`}
        >
          {value}
        </div>
        <div className="mt-1.5 text-[10px] md:text-[11px] uppercase tracking-[0.18em] font-bold text-ink/55">
          {label}
        </div>
      </div>
    </div>
  );
}

/* ────────────────────────────────────────────────────────────────────────
 *  LEGACY PROGRESS PASS BANNER — shows the remaining credits + expiry
 *  ONLY for users who already purchased the $399 12-month Progress Pass
 *  before subscriptions launched. New users no longer see this product;
 *  the marketing/buy variant has been retired in favour of Premium / VIP.
 * ──────────────────────────────────────────────────────────────────────── */
function LegacyPassActiveBanner({ passState }) {
  if (!passState?.active) return null;
  return (
    <div data-testid="progress-pass-active-banner" className="mt-10 bg-forest text-white p-5 md:p-6 grid md:grid-cols-3 gap-4 items-center border-l-8 border-forest-pop">
      <div className="md:col-span-2 flex items-center gap-3">
        <div className="w-11 h-11 bg-white/10 border border-white/30 flex items-center justify-center">
          <CheckCircle2 className="w-5 h-5" />
        </div>
        <div>
          <div className="text-[10px] uppercase tracking-[0.22em] font-bold opacity-80">Progress Pass active</div>
          <h2 className="font-barlow font-black uppercase text-xl tracking-tighter">
            {passState.credits_remaining} of {passState.credits_total} report credits remaining
          </h2>
          {passState.expires_at && (
            <p className="text-xs opacity-80 mt-1">
              Expires {new Date(passState.expires_at).toLocaleDateString()}
            </p>
          )}
        </div>
      </div>
      <div className="flex md:justify-end">
        <Link to="/upload" data-testid="progress-pass-use-credit-btn" className="inline-flex items-center gap-2 bg-white text-forest hover:bg-cream-soft font-barlow font-black uppercase tracking-widest text-xs px-5 py-3 transition-colors">
          Use a credit <ArrowRight className="w-4 h-4" />
        </Link>
      </div>
    </div>
  );
}


/* ────────────────────────────────────────────────────────────────────────
 *  UPGRADE BANNER — shown on the dashboard ONLY when the user has no
 *  active subscription and no legacy Progress Pass. Two compact cards
 *  side-by-side (Premium and VIP) reuse the same /payments/subscribe
 *  endpoint as the landing pricing section — clicking either card
 *  full-redirects to Stripe Checkout in `mode=subscription`.
 *  Once the subscription is active <SubscriptionCard /> takes over and
 *  this banner is hidden, so we never double-promote.
 * ──────────────────────────────────────────────────────────────────────── */
function UpgradeBanner({ tiers, mode = "free", usage = null, latestLockedReportId = null }) {
  const navigate = useNavigate();
  const [busy, setBusy] = useState(null); // "premium" | "vip" | "extra" | null
  const isPremiumAtLimit = mode === "premium-at-limit";
  const isVipAtLimit = mode === "vip-at-limit";
  const isAtLimit = isPremiumAtLimit || isVipAtLimit;
  const extraPrice = usage?.extra_report_price;
  const extraTierLabel = isVipAtLimit ? "VIP" : "Premium";

  const startSubscription = async (tier) => {
    if (busy) return;
    setBusy(tier);
    try {
      const { data } = await api.post("/payments/subscribe", {
        tier,
        origin_url: window.location.origin,
      });
      if (!data?.url) throw new Error("No checkout URL received");
      window.location.href = data.url;
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Could not start checkout.", { duration: 7000 });
      setBusy(null);
    }
  };

  // Buys ONE extra report at the current user's discounted subscriber rate
  // (Premium: $89 default, VIP: $59 default — admin-editable). Reuses the
  // same /payments/prepay-upload endpoint as free users; the backend now
  // switches the price to the subscriber rate automatically based on tier.
  const buyExtraReport = async () => {
    if (busy) return;
    setBusy("extra");
    try {
      const { data } = await api.post("/payments/prepay-upload", {
        origin_url: window.location.origin,
      });
      if (!data?.url) throw new Error("No checkout URL received");
      window.location.href = data.url;
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Could not start checkout.", { duration: 7000 });
      setBusy(null);
    }
  };

  const vip = tiers?.vip || { amount: 49.99 };
  const monthlyLimit = usage?.monthly_limit ?? (isVipAtLimit ? 4 : 2);
  const usedThisPeriod = usage?.used_this_period ?? monthlyLimit;

  return (
    <div
      data-testid={
        isVipAtLimit
          ? "dashboard-upgrade-banner-vip-at-limit"
          : isPremiumAtLimit
          ? "dashboard-upgrade-banner-at-limit"
          : "dashboard-upgrade-banner"
      }
      className={`mt-10 relative overflow-hidden p-5 md:p-7 ${
        isAtLimit ? "border border-[#F5C443]/25 text-white" : "bg-cream-card border border-gray-border"
      }`}
    >
      {isAtLimit && (
        <>
          <div aria-hidden className="absolute inset-0 bg-cover bg-center" style={{ backgroundImage: "url(/assets/premium-dash-gold.jpg)" }} />
          <div aria-hidden className="absolute inset-0 bg-gradient-to-r from-[#06120B]/[0.97] via-[#06120B]/90 to-[#06120B]/75" />
          <div aria-hidden className="absolute top-0 left-0 right-0 h-px bg-gradient-to-r from-transparent via-[#F5C443]/70 to-transparent" />
        </>
      )}
      <div className="relative flex items-center gap-2 mb-3">
        <span aria-hidden className="relative flex items-center justify-center w-2 h-2 shrink-0">
          <span className={`absolute inset-0 rounded-full ${isAtLimit ? "bg-[#F5C443]" : "bg-volt"} animate-ping opacity-75`} />
          <span className={`relative rounded-full w-1.5 h-1.5 ${isAtLimit ? "bg-[#F5C443]" : "bg-volt"}`} />
        </span>
        <span className={`text-[10px] uppercase tracking-[0.28em] font-bold ${isAtLimit ? "text-[#F5C443]" : "text-forest"}`}>
          {isAtLimit
            ? `${extraTierLabel} quota · ${usedThisPeriod} / ${monthlyLimit} reports used this month`
            : "Unlock your full potential"}
        </span>
      </div>
      <h2 className={`relative font-barlow font-black uppercase text-2xl md:text-3xl tracking-tighter leading-[0.95] ${isAtLimit ? "text-white" : "text-ink"}`}>
        {isAtLimit ? (
          <>Keep the momentum.<br /><span className="bg-gradient-to-r from-[#F5C443] to-[#FFE08A] bg-clip-text text-transparent">Add one extra report{extraPrice ? <> · <span className="text-[#CCFF00]">${extraPrice}</span></> : null}</span></>
        ) : (
          <>Ready for more?<br /><span className="text-forest">Upgrade your plan.</span></>
        )}
      </h2>
      <p className={`relative mt-2 text-sm max-w-xl ${isAtLimit ? "text-white/70" : "text-ink/65"}`}>
        {isVipAtLimit
          ? `All ${monthlyLimit} VIP reports used — that's elite-level commitment. Add one extra at your private VIP rate and keep the scouts watching. Quota resets next billing cycle.`
          : isPremiumAtLimit
          ? `All ${monthlyLimit} Premium reports used — proof you're putting in the work. Add one extra at your private member rate, or step up to VIP for 4 reports a month and a real scout's eyes on your game.`
          : "You're on the Free plan. Upgrade for more uploads, advanced AI analysis, and (with VIP) a real scout reviewing your video."}
      </p>

      {isAtLimit ? (
        <div className={`relative mt-5 grid gap-3 ${isPremiumAtLimit ? "grid-cols-1 sm:grid-cols-2" : "grid-cols-1"}`}>
          {/* Buy-1-extra-report card — primary action for at-limit subscribers */}
          <button
            type="button"
            data-testid="dashboard-buy-extra-report-btn"
            onClick={buyExtraReport}
            disabled={busy !== null}
            className="relative text-left bg-[#0F3A22] border border-forest p-5 hover:shadow-[0_18px_36px_-12px_rgba(15,58,34,0.55)] transition-all disabled:opacity-60 disabled:cursor-wait"
          >
            <div className="flex items-center justify-between gap-3 mb-2">
              <span className="inline-flex items-center gap-1.5 text-[#CCFF00] text-[10px] uppercase tracking-[0.18em] font-black">
                <TrendingUp className="w-3.5 h-3.5" /> Extra report
              </span>
              <span className="text-[9px] uppercase tracking-[0.16em] font-bold text-[#A5DD5F]/80 bg-[#A5DD5F]/10 px-2 py-0.5 rounded-full">
                Cheapest for you
              </span>
            </div>
            <div className="flex items-baseline gap-1.5">
              <span className="font-barlow font-black text-3xl text-[#CCFF00]">${extraPrice ?? (isVipAtLimit ? 59 : 89)}</span>
              <span className="text-[10px] uppercase tracking-[0.22em] font-bold text-white/70">/ one report</span>
            </div>
            <ul className="mt-3 space-y-1.5 text-[12px] text-white/85 leading-snug">
              <li className="flex items-center gap-1.5"><CheckCircle2 className="w-3 h-3 text-[#A5DD5F]" /> Same full 4-pillar premium report</li>
              <li className="flex items-center gap-1.5"><CheckCircle2 className="w-3 h-3 text-[#A5DD5F]" /> Cheaper than the single-report price</li>
              <li className="flex items-center gap-1.5"><CheckCircle2 className="w-3 h-3 text-[#A5DD5F]" /> Subscription stays untouched</li>
            </ul>
            <span className="mt-4 inline-flex items-center gap-1.5 bg-[#A5DD5F] text-[#0F3A22] font-barlow font-black uppercase tracking-[0.18em] text-xs px-4 py-2">
              {busy === "extra" ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <>Buy 1 report <ArrowRight className="w-3.5 h-3.5" /></>}
            </span>
          </button>

          {/* VIP upgrade — only offered to Premium-at-limit users */}
          {isPremiumAtLimit && (
            <button
              type="button"
              data-testid="dashboard-upgrade-vip-btn"
              onClick={() => startSubscription("vip")}
              disabled={busy !== null}
              className="relative text-left bg-[#0A0F0D] border border-[#1F2724] p-5 hover:shadow-[0_18px_36px_-12px_rgba(0,0,0,0.65)] transition-all disabled:opacity-60 disabled:cursor-wait"
            >
              <div className="flex items-center justify-between gap-3 mb-2">
                <span className="inline-flex items-center gap-1.5 text-[#F5C443] text-[10px] uppercase tracking-[0.18em] font-black">
                  <Crown className="w-3.5 h-3.5" fill="#F5C443" /> Upgrade to VIP
                </span>
                <span className="text-[9px] uppercase tracking-[0.16em] font-bold text-[#F5C443]/80 bg-[#F5C443]/10 px-2 py-0.5 rounded-full">
                  Best value
                </span>
              </div>
              <div className="flex items-baseline gap-1.5">
                <span className="font-barlow font-black text-3xl text-[#F5C443]">${vip.amount?.toFixed(2)}</span>
                <span className="text-[10px] uppercase tracking-[0.22em] font-bold text-white/70">/ month</span>
              </div>
              <ul className="mt-3 space-y-1.5 text-[12px] text-white/85 leading-snug">
                <li className="flex items-center gap-1.5"><CheckCircle2 className="w-3 h-3 text-[#F5C443]" /> 4 reports per month included</li>
                <li className="flex items-center gap-1.5"><CheckCircle2 className="w-3 h-3 text-[#F5C443]" /> Real scout review + direct contact</li>
                <li className="flex items-center gap-1.5"><CheckCircle2 className="w-3 h-3 text-[#F5C443]" /> Deeper per-report discount</li>
              </ul>
              <span className="mt-4 inline-flex items-center gap-1.5 bg-[#F5C443] text-[#0A0F0D] font-barlow font-black uppercase tracking-[0.18em] text-xs px-4 py-2">
                {busy === "vip" ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <>Go VIP <ArrowRight className="w-3.5 h-3.5" /></>}
              </span>
            </button>
          )}
        </div>
      ) : (
        <div className="relative mt-6">
          {/* Unified 3-tier pricing (Single / Premium / VIP) — same component
              as the report paywall and the post-analysis HeroTeaser so free
              users see ONE consistent offer everywhere. */}
          <ReportPaywallTiers
            isLoggedIn
            singleTitle="Unlock a full report"
            onUnlockSingle={() => {
              if (latestLockedReportId) navigate(`/report/${latestLockedReportId}?unlock=1`);
              else navigate("/upload");
            }}
          />
        </div>
      )}

      {isAtLimit && (
        <p className="relative mt-3 text-[10px] uppercase tracking-[0.18em] font-bold flex items-center gap-1.5 text-white/50">
          <Lock className="w-3 h-3 text-[#F5C443]" />
          Secure Stripe · Cancel anytime from your dashboard
        </p>
      )}
    </div>
  );
}


/* ────────────────────────────────────────────────────────────────────────
 *  SUBSCRIPTION CARD — surfaces the user's active monthly plan (Premium /
 *  VIP) with self-serve Cancel / Resume / Upgrade actions. Hidden entirely
 *  for users without a subscription so the dashboard stays uncluttered for
 *  one-time-purchase customers and free users.
 * ──────────────────────────────────────────────────────────────────────── */
function SubscriptionCard({ subscription, tiers, onChange }) {
  const [busy, setBusy] = useState(null); // "cancel" | "resume" | "change" | null

  if (!subscription || !subscription.tier) return null;

  const tier = subscription.tier;
  const conf = tiers[tier] || {};
  const isVip = tier === "vip";
  const otherTier = isVip ? "premium" : "vip";
  const otherConf = tiers[otherTier] || {};
  const willCancel = !!subscription.cancel_at_period_end;
  const periodEnd = subscription.current_period_end
    ? new Date(subscription.current_period_end).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" })
    : null;
  const isActive = ["active", "trialing", "past_due"].includes(subscription.status);

  const doAction = async (action) => {
    if (busy) return;
    setBusy(action);
    try {
      let res;
      if (action === "cancel") res = await api.post("/me/subscription/cancel");
      else if (action === "resume") res = await api.post("/me/subscription/resume");
      else if (action === "change") res = await api.post("/me/subscription/change-tier", { tier: otherTier, origin_url: window.location.origin });
      onChange(res.data.subscription);
      toast.success(
        action === "cancel" ? `Cancellation scheduled. Access continues until ${periodEnd}.` :
        action === "resume" ? "Subscription reactivated." :
        `Plan changed to ${otherTier === "vip" ? "VIP Premium" : "Premium"} — proration applied on next invoice.`,
        { duration: 8000 }
      );
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Action failed.", { duration: 7000 });
    } finally {
      setBusy(null);
    }
  };

  return (
    <div
      data-testid="dashboard-subscription-card"
      className="mt-10 relative overflow-hidden border border-[#F5C443]/25 text-white"
    >
      {/* Nano Banana gold pitch texture + tier-tinted overlay */}
      <div aria-hidden className="absolute inset-0 bg-cover bg-center" style={{ backgroundImage: "url(/assets/premium-dash-gold.jpg)" }} />
      <div aria-hidden className={`absolute inset-0 ${isVip ? "bg-gradient-to-r from-[#050807]/[0.97] via-[#050807]/90 to-[#050807]/70" : "bg-gradient-to-r from-[#06180E]/[0.97] via-[#06180E]/90 to-[#06180E]/70"}`} />
      <div aria-hidden className="absolute top-0 left-0 right-0 h-px bg-gradient-to-r from-transparent via-[#F5C443]/70 to-transparent" />

      <div className="relative p-6 md:p-8 grid md:grid-cols-3 gap-6 items-center">
        <div className="md:col-span-2">
          <div className="flex items-center gap-2.5 mb-2.5">
            <span className="w-8 h-8 flex items-center justify-center border border-[#F5C443]/40 bg-[#F5C443]/10">
              <Crown className="w-4 h-4 text-[#F5C443]" fill="#F5C443" />
            </span>
            <span className="text-[10px] uppercase tracking-[0.3em] font-black text-[#F5C443]">
              Active plan · {subscription.status}
            </span>
          </div>
          <h3 className="font-barlow font-black uppercase text-3xl md:text-4xl tracking-tight leading-none">
            {isVip
              ? <>VIP <span className="bg-gradient-to-r from-[#F5C443] to-[#FFE08A] bg-clip-text text-transparent">Premium</span></>
              : <>Premium <span className="text-[#CCFF00]">Member</span></>}
          </h3>
          <p className="mt-2 text-sm text-white/70">
            ${conf.amount?.toFixed(2) ?? "—"} / month — full scout-grade analysis on every upload.
          </p>
          <div className="mt-3.5 flex flex-wrap gap-2">
            {(isVip
              ? ["4 reports / month", "Real scout review", "Direct contact", "Deepest discount"]
              : [`${conf.monthly_upload_limit ?? "—"} reports / month`, "Advanced AI analysis", "Full premium dossier"]
            ).map((perk) => (
              <span key={perk} className="inline-flex items-center gap-1.5 border border-white/15 bg-white/[0.06] px-3 py-1 text-[10px] uppercase tracking-[0.18em] font-bold text-white/80">
                <CheckCircle2 className={`w-3 h-3 ${isVip ? "text-[#F5C443]" : "text-[#CCFF00]"}`} /> {perk}
              </span>
            ))}
          </div>
          {periodEnd && (
            <p className={`mt-4 inline-flex items-center gap-1.5 text-xs uppercase tracking-[0.18em] font-bold px-2.5 py-1 ${
              willCancel ? "bg-amber-500/20 text-amber-200" : "bg-white/10 text-white/85"
            }`}>
              <Calendar className="w-3 h-3" />
              {willCancel ? `Ends on ${periodEnd}` : `Next billing ${periodEnd}`}
            </p>
          )}
        </div>

      <div className="flex flex-col gap-2 md:items-end">
        {isActive && !willCancel && (
          <button
            type="button"
            disabled={busy !== null}
            onClick={() => doAction("change")}
            data-testid="subscription-change-tier-btn"
            className={`group w-full md:w-auto inline-flex items-center justify-center gap-2 px-5 py-3 font-barlow font-black uppercase tracking-[0.16em] text-xs transition-all disabled:opacity-60 disabled:cursor-wait ${
              isVip
                ? "bg-white/10 hover:bg-white/15 text-white border border-white/20"
                : "bg-[#F5C443] hover:bg-[#FFD661] text-[#0A0F0D]"
            }`}
          >
            {busy === "change" ? <Loader2 className="w-4 h-4 animate-spin" /> : (
              <>
                {isVip ? "Switch to Premium" : "Upgrade to VIP"}
                <ArrowRight className="w-4 h-4" />
              </>
            )}
          </button>
        )}
        {isActive && !willCancel && (
          <button
            type="button"
            disabled={busy !== null}
            onClick={() => doAction("cancel")}
            data-testid="subscription-cancel-btn"
            className="w-full md:w-auto inline-flex items-center justify-center gap-2 px-5 py-2.5 text-white/70 hover:text-white text-xs uppercase tracking-[0.18em] font-bold transition-colors disabled:opacity-60"
          >
            {busy === "cancel" ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : (
              <><XCircle className="w-3.5 h-3.5" /> Cancel subscription</>
            )}
          </button>
        )}
        {willCancel && isActive && (
          <button
            type="button"
            disabled={busy !== null}
            onClick={() => doAction("resume")}
            data-testid="subscription-resume-btn"
            className="w-full md:w-auto inline-flex items-center justify-center gap-2 px-5 py-3 bg-[#CCFF00] hover:bg-[#D8FF33] text-[#0F3A22] font-barlow font-black uppercase tracking-[0.16em] text-xs transition-all disabled:opacity-60 disabled:cursor-wait"
          >
            {busy === "resume" ? <Loader2 className="w-4 h-4 animate-spin" /> : (
              <><RefreshCw className="w-4 h-4" /> Reactivate</>
            )}
          </button>
        )}
        {otherConf?.amount && isActive && !willCancel && (
          <p className="text-[10px] uppercase tracking-[0.18em] text-white/45 font-bold md:text-right">
            ${otherConf.amount.toFixed(2)}/mo · proration applied
          </p>
        )}
        </div>
      </div>
    </div>
  );
}
