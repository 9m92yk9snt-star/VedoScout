import React, { useEffect, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import Navigation from "@/components/Navigation";
import EmbeddedCheckoutModal from "@/components/EmbeddedCheckoutModal";
import { MiniPitch } from "@/components/FootballAccents";
import api from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import {
  Plus, Lock, CheckCircle2, Film, Loader2, Rocket, TrendingUp, AlertCircle,
  Activity, ArrowRight, Sparkles, Zap,
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
  const [passState, setPassState] = useState(null);
  const [loading, setLoading] = useState(true);
  const [passModalOpen, setPassModalOpen] = useState(false);
  // Pass price loaded from /settings/price so it reflects whatever the
  // admin has currently set (single source of truth — same endpoint
  // PricingCards / Landing already use).
  const [passPrice, setPassPrice] = useState(null);

  const fetchAll = () => {
    Promise.allSettled([
      api.get("/reports/mine").then(({ data }) => setReports(data)),
      api.get("/progress/players").then(({ data }) => setPlayers(data.items || [])),
      api.get("/progress/pass/status").then(({ data }) => setPassState(data)),
      api.get("/settings/price").then(({ data }) => setPassPrice(data.pass_price)),
    ]).finally(() => setLoading(false));
  };

  useEffect(() => {
    fetchAll();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Auto-open the Progress Pass modal when user lands here with ?open_pass=1
  // (e.g. after logging-in from the pricing page's "Start the 12-Month Plan" CTA).
  useEffect(() => {
    const params = new URLSearchParams(location.search);
    if (params.get("open_pass") === "1") {
      setPassModalOpen(true);
      // strip the query so a refresh doesn't keep reopening
      params.delete("open_pass");
      const newSearch = params.toString();
      navigate({ pathname: location.pathname, search: newSearch ? `?${newSearch}` : "" }, { replace: true });
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

  const startPassCheckout = async () => ({
    ...(await api.post("/progress/pass/checkout", {
      origin_url: window.location.origin,
    })).data,
  });

  const onPassSuccess = async ({ session_id }) => {
    try {
      await api.post(`/progress/pass/activate/${session_id}`);
      toast.success("Progress Pass activated — 3 reports unlocked for 12 months");
      fetchAll();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Activation failed");
    } finally {
      setPassModalOpen(false);
    }
  };

  return (
    <div className="min-h-screen bg-cream-base text-ink">
      <Navigation />
      <div className="pt-28 pb-16 px-6">
        <div className="max-w-7xl mx-auto">
          <div className="flex flex-col md:flex-row md:items-end md:justify-between gap-6">
            <div>
              <span className="text-forest text-xs uppercase tracking-[0.25em] font-bold">Your dashboard</span>
              <h1 className="mt-3 font-barlow font-black uppercase text-4xl md:text-5xl tracking-tighter leading-[0.95]">
                Welcome, {user?.full_name?.split(" ")[0] || "Player"}
              </h1>
              <p className="mt-2 text-ink/65 text-sm">Track growth across reports, manage uploads, unlock premium analysis.</p>
            </div>
            <Link
              to="/upload"
              data-testid="dashboard-upload-btn"
              className="bg-forest hover:bg-forest-pop text-white font-barlow font-black uppercase tracking-widest text-sm px-6 py-3 transition-colors flex items-center gap-2 self-start md:self-end"
            >
              <Plus className="w-4 h-4" />
              New upload
            </Link>
          </div>

          {loading ? (
            <div className="text-center py-16">
              <Loader2 className="w-6 h-6 animate-spin text-forest mx-auto" />
            </div>
          ) : (
            <>
              {/* PROGRESS PASS BANNER */}
              <ProgressPassBanner
                passState={passState}
                passPrice={passPrice}
                onBuyClick={() => setPassModalOpen(true)}
              />

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
                        isPremium={!!passState?.active}
                        onUpgradeClick={() => setPassModalOpen(true)}
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

      <EmbeddedCheckoutModal
        open={passModalOpen}
        onClose={() => setPassModalOpen(false)}
        sessionInit={startPassCheckout}
        amount={passPrice ?? 0}
        currency="USD"
        product="Progress Pass — 3 reports / 12 months"
        onSuccess={onPassSuccess}
      />
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
            aria-label={`Unlock Progress Pass to track ${p.name}`}
            title="Unlock Progress Pass"
            className={`${pulse ? "scoutme-unlock-pulse " : ""}hidden sm:flex absolute z-10 right-9 top-1/2 -translate-y-1/2 items-center gap-1 bg-cream-soft hover:bg-forest hover:text-white hover:border-forest border border-ink/15 text-ink/65 text-[9px] uppercase tracking-widest font-bold px-2 py-1 transition-colors cursor-pointer`}
          >
            <Lock className="w-3 h-3" strokeWidth={2.4} /> Unlock
          </button>
          <button
            type="button"
            onClick={onUpgradeClick}
            data-testid={`player-row-upgrade-mobile-${p.id}`}
            aria-label={`Unlock Progress Pass to track ${p.name}`}
            className={`${pulse ? "scoutme-unlock-pulse " : ""}sm:hidden absolute z-10 right-8 top-1/2 -translate-y-1/2 inline-flex items-center justify-center w-7 h-7 text-ink/45 hover:text-forest active:text-forest transition-colors cursor-pointer`}
          >
            <Lock className="w-3.5 h-3.5" strokeWidth={2.4} />
          </button>
        </>
      )}
    </li>
  );
}

function ProgressPassBanner({ passState, passPrice, onBuyClick }) {
  if (passState?.active) {
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
  return (
    <div data-testid="progress-pass-promo-banner" className="mt-10 relative overflow-hidden bg-ink text-white p-6 md:p-8 grid md:grid-cols-5 gap-6 items-center">
      <div className="absolute -top-12 -right-12 w-64 h-64 bg-forest-pop/30 rounded-full blur-3xl pointer-events-none" />
      <div className="md:col-span-3 relative">
        <div className="flex items-center gap-2 text-[10px] uppercase tracking-[0.22em] font-bold text-forest">
          <Sparkles className="w-3.5 h-3.5" /> New · Progress Pass
        </div>
        <h2 className="mt-2 font-barlow font-black uppercase text-3xl md:text-4xl tracking-tighter leading-[0.95]">
          Track real growth.<br />
          <span className="text-forest">3 reports / 12 months.</span>
        </h2>
        <p className="mt-3 text-sm text-white/75 max-w-md">
          One purchase. Three premium reports for the same player. Age-adjusted percentile tracking, archetype overlay, growth narrative — every 3–6 months.
        </p>
        <ul className="mt-4 space-y-1.5 text-sm text-white/85">
          <li className="flex items-center gap-2"><Zap className="w-3.5 h-3.5 text-forest" /> Age-adjusted percentile shift (honest)</li>
          <li className="flex items-center gap-2"><Zap className="w-3.5 h-3.5 text-forest" /> Trajectory vs archetype path</li>
          <li className="flex items-center gap-2"><Zap className="w-3.5 h-3.5 text-forest" /> Between-the-lines narrative</li>
          <li className="flex items-center gap-2"><Zap className="w-3.5 h-3.5 text-forest" /> Watch yourself improve (video diff)</li>
        </ul>
      </div>
      <div className="md:col-span-2 relative">
        <div className="bg-white/5 border border-white/15 p-5 backdrop-blur-sm">
          <div className="text-[10px] uppercase tracking-[0.22em] font-bold text-white/60">One-time</div>
          <div className="mt-1 flex items-baseline gap-2">
            <span data-testid="progress-pass-price" className="font-barlow font-black text-5xl tracking-tighter">
              ${passPrice ?? "—"}
            </span>
            <span className="text-xs text-white/55">USD</span>
          </div>
          <div className="mt-1 text-xs text-white/55">
            {passPrice ? `≈ $${Math.round(passPrice / 3)} per report` : "≈ per-report cost"} · 3 reports / 12 mo
          </div>
          <button
            data-testid="buy-progress-pass-btn"
            onClick={onBuyClick}
            className="mt-4 w-full bg-forest hover:bg-forest-pop text-white font-barlow font-black uppercase tracking-widest text-xs px-5 py-3 transition-colors"
          >
            Unlock Progress Pass
          </button>
          <p className="mt-2 text-[10px] uppercase tracking-[0.18em] text-white/50 text-center">Secure · Stripe · No subscription</p>
        </div>
      </div>
    </div>
  );
}
