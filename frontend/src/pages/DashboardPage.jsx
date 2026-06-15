import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import Navigation from "@/components/Navigation";
import EmbeddedCheckoutModal from "@/components/EmbeddedCheckoutModal";
import api from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import {
  Plus, Lock, CheckCircle2, Film, Loader2, Rocket, TrendingUp, AlertCircle,
  Users, Activity, ArrowRight, Sparkles, Zap,
} from "lucide-react";

const VERDICT_META = {
  ahead: { label: "Ahead", icon: Rocket, color: "bg-forest-pop text-white" },
  on_track: { label: "On track", icon: TrendingUp, color: "bg-forest text-white" },
  plateau: { label: "Plateau", icon: AlertCircle, color: "bg-amber-600 text-white" },
  first_report: { label: "Baseline", icon: Activity, color: "bg-cream-soft text-ink" },
};

export default function DashboardPage() {
  const { user } = useAuth();
  const [reports, setReports] = useState([]);
  const [players, setPlayers] = useState([]);
  const [passState, setPassState] = useState(null);
  const [loading, setLoading] = useState(true);
  const [passModalOpen, setPassModalOpen] = useState(false);

  const fetchAll = () => {
    Promise.allSettled([
      api.get("/reports/mine").then(({ data }) => setReports(data)),
      api.get("/progress/players").then(({ data }) => setPlayers(data.items || [])),
      api.get("/progress/pass/status").then(({ data }) => setPassState(data)),
    ]).finally(() => setLoading(false));
  };

  useEffect(() => {
    fetchAll();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

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
                onBuyClick={() => setPassModalOpen(true)}
              />

              {/* PLAYERS / TRAJECTORIES */}
              {players.length > 0 && (
                <div className="mt-10" data-testid="dashboard-players-section">
                  <div className="flex items-baseline justify-between">
                    <div>
                      <span className="text-forest text-xs uppercase tracking-[0.25em] font-bold">Track progress</span>
                      <h2 className="mt-1 font-barlow font-black uppercase text-2xl md:text-3xl tracking-tighter">Your players</h2>
                    </div>
                    <span className="text-xs text-ink/55">{players.length} tracked</span>
                  </div>
                  <div className="mt-5 grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
                    {players.map((p) => (
                      <PlayerCard key={p.id} p={p} />
                    ))}
                  </div>
                </div>
              )}

              {/* REPORTS */}
              <div className="mt-12">
                <div className="flex items-baseline justify-between">
                  <div>
                    <span className="text-forest text-xs uppercase tracking-[0.25em] font-bold">Library</span>
                    <h2 className="mt-1 font-barlow font-black uppercase text-2xl md:text-3xl tracking-tighter">Your reports</h2>
                  </div>
                </div>
                {reports.length === 0 ? (
                  <div className="mt-5 border border-gray-border bg-cream-card p-12 text-center">
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
                  <div className="mt-5 grid sm:grid-cols-2 lg:grid-cols-3 gap-px bg-cream-soft/40 border border-gray-border">
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
                                <span className="flex items-center gap-1 bg-cream-card/90 backdrop-blur border border-gray-border text-ink/80 text-[10px] uppercase tracking-widest font-bold px-2 py-1">
                                  <Lock className="w-3 h-3" /> Preview
                                </span>
                              )}
                            </div>
                          </div>
                          <div className="p-5 flex-1 flex flex-col">
                            <h3 className="font-barlow font-black uppercase text-xl text-ink group-hover:text-forest transition-colors leading-tight">
                              {r.player_details?.player_name}
                            </h3>
                            <p className="mt-1 text-sm text-ink/65">
                              {r.player_details?.position} · age {r.player_details?.age}
                            </p>
                            <div className="mt-auto pt-4 flex items-center justify-between">
                              <span className="text-[10px] uppercase tracking-widest text-ink/50 font-bold">{r.player_details?.video_type}</span>
                              <span className="text-forest text-[10px] uppercase tracking-widest font-bold">View →</span>
                            </div>
                          </div>
                        </Link>
                      );
                    })}
                  </div>
                )}
              </div>
            </>
          )}
        </div>
      </div>

      <EmbeddedCheckoutModal
        open={passModalOpen}
        onClose={() => setPassModalOpen(false)}
        sessionInit={startPassCheckout}
        amount={599}
        currency="USD"
        product="Progress Pass — 3 reports / 12 months"
        onSuccess={onPassSuccess}
      />
    </div>
  );
}

function PlayerCard({ p }) {
  const Icon = Users;
  return (
    <Link
      to={`/trajectory/${p.id}`}
      data-testid={`player-card-${p.id}`}
      className="group bg-cream-card border border-gray-border hover:border-forest p-5 flex flex-col transition-colors"
    >
      <div className="flex items-center justify-between">
        <span className="bg-forest/10 text-forest font-barlow font-black uppercase text-[10px] tracking-widest px-2 py-1">
          {p.last_position || "Player"}
        </span>
        <span className="text-xs text-ink/55">{p.report_count} {p.report_count === 1 ? "report" : "reports"}</span>
      </div>
      <h3 className="mt-4 font-barlow font-black uppercase text-2xl text-ink group-hover:text-forest transition-colors leading-tight">
        {p.name}
      </h3>
      <p className="mt-1 text-xs text-ink/55">
        {p.last_age ? `Age ${p.last_age}` : ""} {p.preferred_foot ? `· ${p.preferred_foot} foot` : ""}
      </p>
      <div className="mt-4 pt-4 border-t border-gray-border flex items-center justify-between">
        <span className="text-[10px] uppercase tracking-widest text-ink/50 font-bold">View trajectory</span>
        <ArrowRight className="w-4 h-4 text-forest group-hover:translate-x-1 transition-transform" />
      </div>
    </Link>
  );
}

function ProgressPassBanner({ passState, onBuyClick }) {
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
          One purchase. Three premium reports for the same player. Age-adjusted percentile tracking, archetype overlay, AI delta narrative — every 3–6 months.
        </p>
        <ul className="mt-4 space-y-1.5 text-sm text-white/85">
          <li className="flex items-center gap-2"><Zap className="w-3.5 h-3.5 text-forest" /> Age-adjusted percentile shift (honest)</li>
          <li className="flex items-center gap-2"><Zap className="w-3.5 h-3.5 text-forest" /> Trajectory vs archetype path</li>
          <li className="flex items-center gap-2"><Zap className="w-3.5 h-3.5 text-forest" /> AI between-the-lines narrative</li>
          <li className="flex items-center gap-2"><Zap className="w-3.5 h-3.5 text-forest" /> Watch yourself improve (video diff)</li>
        </ul>
      </div>
      <div className="md:col-span-2 relative">
        <div className="bg-white/5 border border-white/15 p-5 backdrop-blur-sm">
          <div className="text-[10px] uppercase tracking-[0.22em] font-bold text-white/60">One-time</div>
          <div className="mt-1 flex items-baseline gap-2">
            <span className="font-barlow font-black text-5xl tracking-tighter">$599</span>
            <span className="text-xs text-white/55">USD</span>
          </div>
          <div className="mt-1 text-xs text-white/55">≈ $199 per report · 3 reports / 12 mo</div>
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
