import React, { useEffect, useState, useMemo } from "react";
import { useParams, Link } from "react-router-dom";
import { motion } from "framer-motion";
import {
  Loader2, Rocket, TrendingUp, AlertCircle, Award, Target,
  ArrowRight, Download, Lock, Sparkles, Flame, Activity, Trophy,
  ArrowLeftRight, Zap, ChevronDown,
} from "lucide-react";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend,
  RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, Radar,
} from "recharts";

import Navigation from "@/components/Navigation";
import api, { API_BASE } from "@/lib/api";
import EmbeddedCheckoutModal from "@/components/EmbeddedCheckoutModal";

const VERDICT_META = {
  ahead: { label: "Ahead of curve", icon: Rocket, color: "text-white", bg: "bg-forest-pop" },
  on_track: { label: "On track", icon: TrendingUp, color: "text-white", bg: "bg-forest" },
  plateau: { label: "Plateau watch", icon: AlertCircle, color: "text-white", bg: "bg-amber-600" },
  first_report: { label: "Baseline set", icon: Activity, color: "text-ink", bg: "bg-cream-soft" },
};

const PILLAR_LABEL = {
  technical: "Technical",
  tactical: "Tactical",
  physical: "Physical",
  mental: "Mental",
  decision_making: "Decision Making",
};

export default function TrajectoryPage() {
  const { id } = useParams();
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [passState, setPassState] = useState(null);
  const [passModalOpen, setPassModalOpen] = useState(false);
  // Same dynamic-pricing pattern used by DashboardPage / PricingCards /
  // Landing — read pass price from /settings/price so admin updates flow
  // through automatically.
  const [passPrice, setPassPrice] = useState(null);

  useEffect(() => {
    let mounted = true;
    setLoading(true);
    Promise.all([
      api.get(`/progress/players/${id}/trajectory`).then(({ data }) => { if (mounted) setData(data); }),
      api.get("/progress/pass/status").then(({ data }) => { if (mounted) setPassState(data); }).catch(() => {}),
      api.get("/settings/price").then(({ data }) => { if (mounted) setPassPrice(data.pass_price); }).catch(() => {}),
    ])
      .catch((e) => { if (mounted) setError(e?.response?.data?.detail || "Failed to load trajectory"); })
      .finally(() => { if (mounted) setLoading(false); });
    return () => { mounted = false; };
  }, [id]);

  const startPassCheckout = async () => ({
    ...(await api.post("/progress/pass/checkout", {
      origin_url: window.location.origin,
    })).data,
  });

  const onPassSuccess = async ({ session_id }) => {
    try {
      await api.post(`/progress/pass/activate/${session_id}`);
      setPassModalOpen(false);
      // re-fetch pass state so Compare Mode unlocks in-place
      const { data: ps } = await api.get("/progress/pass/status");
      setPassState(ps);
    } catch {
      setPassModalOpen(false);
    }
  };

  const traj = data?.trajectory || {};
  const profile = data?.profile || {};
  const verdict = traj.verdict || "first_report";
  const vmeta = VERDICT_META[verdict] || VERDICT_META.first_report;
  const VerdictIcon = vmeta.icon;

  // Build chart series: combine player & archetype overlay points by date
  const chartData = useMemo(() => {
    const overlay = traj.archetype_overlay?.points || [];
    return (traj.timeline || []).map((t, i) => ({
      date: new Date(t.date).toLocaleDateString("en-US", { month: "short", year: "2-digit" }),
      age: t.age,
      player: t.overall,
      archetype: overlay[i]?.archetype_overall ?? null,
      adjusted: t.age_adjusted_pct,
    }));
  }, [traj]);

  const reportCount = traj.report_count || 0;
  const oneReport = reportCount < 2;

  if (loading) {
    return (
      <div className="min-h-screen bg-cream-base">
        <Navigation />
        <div className="pt-32 flex justify-center">
          <Loader2 className="w-7 h-7 animate-spin text-forest" />
        </div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="min-h-screen bg-cream-base">
        <Navigation />
        <div className="pt-32 max-w-xl mx-auto text-center px-6">
          <AlertCircle className="w-10 h-10 text-amber-600 mx-auto mb-3" />
          <h1 className="font-barlow font-black uppercase text-3xl text-ink">Trajectory unavailable</h1>
          <p className="mt-2 text-ink/70 text-sm">{error || "Player profile not found."}</p>
          <Link to="/dashboard" className="mt-6 inline-block bg-forest hover:bg-forest-pop text-white font-barlow font-black uppercase tracking-widest text-sm px-6 py-3 transition-colors">
            Back to dashboard
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-cream-base text-ink" data-testid="trajectory-page">
      <Navigation />

      <div className="pt-28 pb-20 px-4 md:px-8">
        <div className="max-w-6xl mx-auto">
          {/* HEADER */}
          <div className="flex flex-col md:flex-row md:items-end md:justify-between gap-4">
            <div>
              <Link to="/dashboard" className="text-xs uppercase tracking-[0.22em] font-bold text-forest hover:text-forest-pop">
                ← Dashboard
              </Link>
              <h1 data-testid="trajectory-player-name" className="mt-2 font-barlow font-black uppercase text-4xl md:text-5xl tracking-tighter leading-[0.95]">
                {profile.name}
              </h1>
              <p className="mt-1 text-ink/65 text-sm">
                {profile.last_position} · {reportCount} {reportCount === 1 ? "report" : "reports"}
                {profile.last_age ? ` · age ${profile.last_age}` : ""}
              </p>
            </div>

            <div className="flex flex-wrap items-center gap-3">
              <a
                data-testid="trajectory-growth-card-btn"
                href={`${API_BASE}/progress/players/${profile.id}/growth-card.png`}
                target="_blank" rel="noreferrer"
                className="inline-flex items-center gap-2 border-2 border-forest text-forest hover:bg-forest hover:text-white font-barlow font-black uppercase tracking-widest text-xs px-5 py-3 transition-colors"
              >
                <Download className="w-4 h-4" /> Growth card
              </a>
              <Link
                to="/upload"
                data-testid="trajectory-upload-next-btn"
                className="inline-flex items-center gap-2 bg-forest hover:bg-forest-pop text-white font-barlow font-black uppercase tracking-widest text-xs px-5 py-3 transition-colors"
              >
                Upload next report <ArrowRight className="w-4 h-4" />
              </Link>
            </div>
          </div>

          {/* ── WHAT CHANGED banner — top-of-page sticky moment. Auto-computed
             from traj.deltas.pillars (first vs latest, already there). Sorted
             by absolute delta DESC, capped at the 4 biggest movers, colour-
             coded so positives feel like wins and negatives stay honest. */}
          {!oneReport && (
            <WhatChangedBanner
              deltas={traj?.deltas?.pillars}
              firstDate={traj?.timeline?.[0]?.date}
              lastDate={traj?.timeline?.[traj.timeline.length - 1]?.date}
              monthsBetween={(() => {
                const tl = traj?.timeline;
                if (!tl || tl.length < 2) return null;
                const a = new Date(tl[0].date);
                const b = new Date(tl[tl.length - 1].date);
                if (isNaN(a) || isNaN(b)) return null;
                return Math.round(((b - a) / (1000 * 60 * 60 * 24 * 30.5)) * 10) / 10;
              })()}
            />
          )}

          {/* VERDICT HERO */}
          <motion.div
            initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4 }}
            data-testid="trajectory-verdict-card"
            className={`mt-8 border-2 border-forest/30 ${vmeta.bg} ${vmeta.color} p-6 md:p-8 grid md:grid-cols-3 gap-6`}
          >
            <div className="md:col-span-2 flex items-start gap-4">
              <div className="w-12 h-12 bg-white/10 border border-white/30 flex items-center justify-center shrink-0">
                <VerdictIcon className="w-6 h-6" />
              </div>
              <div>
                <div className="text-[10px] uppercase tracking-[0.22em] font-bold opacity-80">Trajectory verdict</div>
                <h2 data-testid="trajectory-verdict-label" className="mt-1 font-barlow font-black uppercase text-3xl md:text-4xl tracking-tighter">
                  {vmeta.label}
                </h2>
                {oneReport ? (
                  <p className="mt-2 text-sm opacity-90 max-w-xl">
                    First report locked in. Upload the next video in 3–6 months to see how {profile.name?.split(" ")[0] || "your player"} actually progresses against age-typical pace and the matched archetype.
                  </p>
                ) : (
                  <p className="mt-2 text-sm opacity-90 max-w-xl">
                    {verdict === "ahead" && "Improving faster than age-typical pace. This is the curve every academy wants to see."}
                    {verdict === "on_track" && "Improving at age-typical pace. Steady, consistent development."}
                    {verdict === "plateau" && "Growth has slowed across reports. Time to check focus & repetition load."}
                  </p>
                )}
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <DeltaPill label="Raw score" value={fmtDelta(traj?.deltas?.overall_raw)} suffix="pts" />
              <DeltaPill label="Age-adjusted" value={fmtDelta(traj?.deltas?.overall_age_adjusted_pct)} suffix="pct" />
            </div>
          </motion.div>

          {/* HONESTY CALLOUT — when raw rose but age-adjusted dropped */}
          {!oneReport && traj?.deltas?.overall_raw > 0 && traj?.deltas?.overall_age_adjusted_pct < 0 && (
            <div data-testid="trajectory-honesty-callout" className="mt-4 border-l-4 border-amber-600 bg-amber-50 px-5 py-4 text-sm text-ink">
              <strong className="font-barlow font-black uppercase tracking-widest text-amber-700">Honesty check —</strong>{" "}
              the raw score went up <strong>+{traj.deltas.overall_raw}</strong>, but the age-adjusted percentile{" "}
              <strong>dropped {Math.abs(traj.deltas.overall_age_adjusted_pct)} points</strong>. The bar moved up faster than the score. Most competitors hide this; we don&apos;t.
            </div>
          )}

          {/* TRAJECTORY CHART */}
          <div data-testid="trajectory-chart-card" className="mt-6 bg-cream-card border border-gray-border p-5 md:p-8">
            <div className="flex items-baseline justify-between flex-wrap gap-2">
              <h3 className="font-barlow font-black uppercase text-2xl tracking-tighter">Growth chart</h3>
              <p className="text-xs text-ink/55">
                vs <span className="text-forest font-bold">{traj.archetype_overlay?.archetype_name || "archetype path"}</span> typical curve
              </p>
            </div>
            <div className="mt-5 h-72 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={chartData} margin={{ top: 10, right: 18, bottom: 8, left: -10 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#E5E7EB" />
                  <XAxis dataKey="date" tick={{ fill: "#0A0F0D", fontSize: 11 }} />
                  <YAxis domain={[0, 10]} tick={{ fill: "#0A0F0D", fontSize: 11 }} />
                  <Tooltip
                    contentStyle={{ background: "#fff", border: "1px solid #E5E7EB", borderRadius: 0, fontSize: 12 }}
                  />
                  <Legend wrapperStyle={{ fontSize: 12 }} />
                  <Line type="monotone" dataKey="player" name="Player" stroke="#1F4F2F" strokeWidth={3} dot={{ r: 5, fill: "#1F4F2F" }} />
                  <Line type="monotone" dataKey="archetype" name="Archetype path" stroke="#2D6B3D" strokeWidth={2} strokeDasharray="5 5" dot={{ r: 4, fill: "#2D6B3D" }} />
                </LineChart>
              </ResponsiveContainer>
            </div>
            <p className="mt-3 text-[11px] text-ink/55">
              Archetype curve is a senior-pro reference projection per age band — not invented data. Solid line = your player&apos;s overall development across reports.
            </p>
          </div>

          {/* GEMINI NARRATIVE */}
          {traj.narrative && (
            <div data-testid="trajectory-narrative-card" className="mt-6 bg-forest text-white p-6 md:p-8 border-l-8 border-forest-pop">
              <div className="flex items-center gap-2 text-[10px] uppercase tracking-[0.22em] font-bold opacity-80">
                <Sparkles className="w-3.5 h-3.5" /> Between-the-lines narrative
              </div>
              <p className="mt-4 text-base md:text-lg leading-relaxed whitespace-pre-wrap font-light">
                {traj.narrative}
              </p>
            </div>
          )}

          {/* ── COMPARE MOMENTS — Progress-Pass killer feature ────────── */}
          {!oneReport && (
            <CompareMode
              timeline={traj.timeline || []}
              isPremium={!!passState?.active}
              onUnlock={() => setPassModalOpen(true)}
            />
          )}

          {/* PILLAR DELTAS */}
          {!oneReport && traj?.deltas?.pillars && Object.keys(traj.deltas.pillars).length > 0 && (
            <div data-testid="trajectory-pillars-card" className="mt-6 bg-cream-card border border-gray-border p-5 md:p-8">
              <h3 className="font-barlow font-black uppercase text-2xl tracking-tighter">Pillar deltas</h3>
              <div className="mt-5 grid sm:grid-cols-2 gap-3">
                {Object.entries(traj.deltas.pillars).map(([pillar, info]) => (
                  <PillarDelta key={pillar} pillar={pillar} info={info} />
                ))}
              </div>
            </div>
          )}

          {/* MISSION STATUS */}
          {traj.mission && (
            <div data-testid="trajectory-mission-card" className="mt-6 bg-cream-card border border-gray-border p-5 md:p-8">
              <div className="flex items-center gap-2 text-[10px] uppercase tracking-[0.22em] font-bold text-forest">
                <Target className="w-3.5 h-3.5" /> Mission status
              </div>
              <h3 className="mt-2 font-barlow font-black uppercase text-2xl tracking-tighter">Closing the coaching loop</h3>

              {traj.mission.previous_results?.length > 0 ? (
                <div className="mt-4 space-y-3">
                  <p className="text-sm text-ink/70">Last report&apos;s focus pillars:</p>
                  {traj.mission.previous_results.map((r) => (
                    <div key={r.pillar} className="flex items-center justify-between border-l-4 border-forest pl-4 py-2 bg-cream-soft/40">
                      <div>
                        <div className="font-bold text-ink">{PILLAR_LABEL[r.pillar] || r.pillar}</div>
                        <div className="text-xs text-ink/60">{r.before} → {r.after}</div>
                      </div>
                      <span className={`text-xs uppercase tracking-widest font-black px-3 py-1 ${r.improved ? "bg-forest text-white" : "bg-amber-600 text-white"}`}>
                        {r.improved ? `+${r.delta} · Hit` : `${r.delta} · Missed`}
                      </span>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="mt-3 text-sm text-ink/65">
                  No declared focus from the previous report. Each new upload will be auto-evaluated against the weakest pillar.
                </p>
              )}

              {traj.mission.next_mission?.length > 0 && (
                <div className="mt-5 border-t border-gray-border pt-4">
                  <p className="text-[10px] uppercase tracking-[0.22em] font-bold text-forest">Recommended next focus</p>
                  <div className="mt-2 flex flex-wrap gap-2">
                    {traj.mission.next_mission.map((m) => (
                      <span key={m.pillar} className="bg-forest text-white text-xs uppercase tracking-widest font-black px-3 py-1.5">
                        {PILLAR_LABEL[m.pillar] || m.pillar} · current {m.current}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* VIDEO DIFF */}
          {traj.video_diff?.pairs?.length > 0 && (
            <div data-testid="trajectory-video-diff-card" className="mt-6 bg-cream-card border border-gray-border p-5 md:p-8">
              <div className="flex items-center gap-2 text-[10px] uppercase tracking-[0.22em] font-bold text-forest">
                <Flame className="w-3.5 h-3.5" /> Watch yourself improve
              </div>
              <h3 className="mt-2 font-barlow font-black uppercase text-2xl tracking-tighter">Video evidence: before & after</h3>
              <p className="text-xs text-ink/55 mt-1">
                Age {traj.video_diff.first_age} vs Age {traj.video_diff.last_age} — same player, real frames.
              </p>
              <div className="mt-5 space-y-5">
                {traj.video_diff.pairs.map((p, i) => (
                  <div key={i} className="grid sm:grid-cols-2 gap-4">
                    <DiffFrame frame={p.before} label="Before" />
                    <DiffFrame frame={p.after} label="After" />
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* BADGES */}
          {traj.badges?.length > 0 && (
            <div data-testid="trajectory-badges-card" className="mt-6 bg-cream-card border border-gray-border p-5 md:p-8">
              <div className="flex items-center gap-2 text-[10px] uppercase tracking-[0.22em] font-bold text-forest">
                <Trophy className="w-3.5 h-3.5" /> Growth badges
              </div>
              <h3 className="mt-2 font-barlow font-black uppercase text-2xl tracking-tighter">Earned milestones</h3>
              <div className="mt-5 grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
                {traj.badges.map((b) => (
                  <div key={b.id} data-testid={`badge-${b.id}`} className="border border-forest/30 bg-cream-soft p-4">
                    <div className="flex items-center gap-2 text-forest">
                      <Award className="w-4 h-4" />
                      <span className="font-barlow font-black uppercase text-sm tracking-wide">{b.label}</span>
                    </div>
                    <p className="mt-1 text-xs text-ink/65">{b.detail}</p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* TIMELINE TABLE */}
          {!oneReport && (
            <div data-testid="trajectory-reports-table" className="mt-6 bg-cream-card border border-gray-border">
              <h3 className="px-5 md:px-8 pt-5 md:pt-6 font-barlow font-black uppercase text-2xl tracking-tighter">All reports</h3>
              <div className="mt-3 divide-y divide-gray-border">
                {[...(traj.timeline || [])].reverse().map((t) => (
                  <Link
                    key={t.report_id}
                    to={`/report/${t.report_id}`}
                    className="px-5 md:px-8 py-4 hover:bg-cream-soft/60 transition-colors flex flex-wrap items-center justify-between gap-3"
                  >
                    <div>
                      <div className="font-barlow font-black uppercase text-ink">
                        {new Date(t.date).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })}
                      </div>
                      <div className="text-xs text-ink/55">Age {t.age} · overall {t.overall ?? "—"}/10</div>
                    </div>
                    <div className="text-forest text-xs uppercase tracking-widest font-bold">View report →</div>
                  </Link>
                ))}
              </div>
            </div>
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

function fmtDelta(v) {
  if (v === null || v === undefined) return "—";
  const prefix = v > 0 ? "+" : "";
  return `${prefix}${v}`;
}

function DeltaPill({ label, value, suffix }) {
  const positive = typeof value === "string" && value.startsWith("+");
  const negative = typeof value === "string" && value.startsWith("-");
  return (
    <div className="bg-white/10 border border-white/20 p-3">
      <div className="text-[9px] uppercase tracking-[0.22em] font-bold opacity-80">{label}</div>
      <div className={`mt-0.5 font-barlow font-black text-2xl ${positive ? "text-white" : negative ? "text-amber-200" : "text-white/80"}`}>
        {value}
        <span className="text-xs opacity-70 ml-1">{suffix}</span>
      </div>
    </div>
  );
}

function PillarDelta({ pillar, info }) {
  const delta = info.delta;
  const positive = delta > 0;
  const negative = delta < 0;
  return (
    <div data-testid={`pillar-delta-${pillar}`} className="border border-gray-border p-4 bg-white">
      <div className="flex items-center justify-between">
        <span className="font-barlow font-black uppercase text-sm tracking-wide text-ink">{PILLAR_LABEL[pillar] || pillar}</span>
        <span className={`text-sm font-black ${positive ? "text-forest" : negative ? "text-amber-700" : "text-ink/60"}`}>
          {positive ? "+" : ""}{delta}
        </span>
      </div>
      <div className="mt-2 h-2 bg-gray-border relative overflow-hidden">
        <div
          className={`h-full ${positive ? "bg-forest" : "bg-amber-600"}`}
          style={{ width: `${Math.min(100, Math.abs(delta) * 30)}%` }}
        />
      </div>
      <div className="mt-2 text-xs text-ink/60">{info.from} → {info.to}</div>
    </div>
  );
}

/* ──────────────────────────────────────────────────────────────────────
 * What Changed Banner — top-of-trajectory "sticky moment"
 *
 *   Auto-computed from `traj.deltas.pillars` (already returned by the
 *   backend — first vs latest report). Sorted by absolute delta DESC so
 *   the biggest movers come first; capped at 4 chips to keep the line
 *   punchy. Green for positive, amber for negative — honest, no spin.
 *
 *   Hidden when there's <2 reports or the pillars deltas map is empty
 *   (defensive — if a snapshot is missing pillar scores).
 * ─────────────────────────────────────────────────────────────────── */
function WhatChangedBanner({ deltas, firstDate, lastDate, monthsBetween }) {
  if (!deltas) return null;
  const entries = Object.entries(deltas)
    .filter(([, info]) => info && typeof info.delta === "number" && info.delta !== 0)
    .sort((a, b) => Math.abs(b[1].delta) - Math.abs(a[1].delta))
    .slice(0, 4);
  if (entries.length === 0) return null;

  const fmtShort = (s) => {
    try {
      return new Date(s).toLocaleDateString("en-US", { month: "short", day: "numeric" });
    } catch {
      return null;
    }
  };
  const firstLabel = fmtShort(firstDate);
  const lastLabel = fmtShort(lastDate);
  const since = firstLabel
    ? (lastLabel ? `${firstLabel} → ${lastLabel}` : `since ${firstLabel}`)
    : "across reports";

  return (
    <motion.div
      initial={{ opacity: 0, y: -6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, delay: 0.05 }}
      data-testid="trajectory-what-changed-banner"
      className="mt-6 relative bg-cream-card border border-ink/10 pl-4 pr-4 md:pl-6 md:pr-6 py-4 flex flex-col md:flex-row md:items-center gap-3 md:gap-5"
    >
      {/* Forest accent stripe on the left */}
      <span aria-hidden="true" className="absolute left-0 top-0 bottom-0 w-[3px] bg-forest" />
      <div className="flex items-center gap-2 flex-shrink-0">
        <Sparkles className="w-3.5 h-3.5 text-forest" strokeWidth={2.4} />
        <div className="text-[10px] uppercase tracking-[0.22em] font-black text-forest leading-tight">
          What changed
          <span className="block text-ink/55 font-bold tracking-widest mt-0.5">
            {since}{monthsBetween ? ` · ${monthsBetween} mo` : ""}
          </span>
        </div>
      </div>
      <div className="flex-1 flex flex-wrap items-center gap-2">
        {entries.map(([pillar, info]) => {
          const d = info.delta;
          const positive = d > 0;
          return (
            <span
              key={pillar}
              data-testid={`what-changed-${pillar}`}
              className={`inline-flex items-center gap-1.5 px-2.5 py-1 text-[11px] uppercase tracking-widest font-black ${
                positive
                  ? "bg-forest/10 text-forest"
                  : "bg-amber-600/10 text-amber-700"
              }`}
            >
              <span className="font-barlow font-black text-sm tabular-nums">
                {positive ? "+" : ""}{Math.round(d * 10) / 10}
              </span>
              <span>{PILLAR_LABEL[pillar] || pillar}</span>
            </span>
          );
        })}
      </div>
    </motion.div>
  );
}

function DiffFrame({ frame, label }) {
  if (!frame) {
    return (
      <div className="border border-dashed border-gray-border bg-cream-soft p-6 text-center">
        <Lock className="w-5 h-5 text-ink/40 mx-auto" />
        <p className="mt-2 text-xs text-ink/50 uppercase tracking-widest font-bold">{label} — pending</p>
      </div>
    );
  }
  const src = frame.frame_url ? `${process.env.REACT_APP_BACKEND_URL}${frame.frame_url}` : null;
  return (
    <div className="border border-gray-border bg-white">
      {src && (
        <div className="aspect-video bg-ink overflow-hidden relative">
          <img src={src} alt={label} className="w-full h-full object-cover" />
          <span className="absolute top-2 left-2 bg-forest text-white text-[10px] uppercase tracking-widest font-black px-2 py-1">
            {label}
          </span>
          {frame.timestamp && (
            <span className="absolute bottom-2 right-2 bg-ink/80 text-white text-[10px] font-bold px-2 py-1">
              {frame.timestamp}
            </span>
          )}
        </div>
      )}
      <div className="p-3 text-xs text-ink/70 leading-relaxed">
        {frame.comment || "—"}
      </div>
    </div>
  );
}

/* ──────────────────────────────────────────────────────────────────────
 * Compare Mode — Progress Pass killer feature
 *
 *   Renders two synced radar charts of the same player's pillar scores at
 *   two different report dates, with a scrub slider that animates between
 *   them, per-pillar delta strip, side-by-side posters. Source data is the
 *   ALREADY-FETCHED `traj.timeline` — no new backend calls.
 *
 *   Gating (per product decision):
 *     • Default pair "First ↔ Latest" works for everyone with 2+ reports.
 *     • "Biggest jump" preset + custom dropdowns are PASS-locked.
 *
 *   Hidden entirely when there are <2 reports (matches the existing
 *   one-report behaviour of the Pillar Deltas card).
 * ───────────────────────────────────────────────────────────────────── */
const PILLAR_KEYS = ["technical", "tactical", "physical", "mental", "decision_making"];

function CompareMode({ timeline, isPremium, onUnlock }) {
  // Sort chronologically (defensive — the API returns oldest→newest already).
  const sorted = useMemo(
    () => [...timeline].sort((a, b) => new Date(a.date) - new Date(b.date)),
    [timeline],
  );

  // Auto-find the consecutive pair with the largest positive overall delta.
  const biggestJump = useMemo(() => {
    if (sorted.length < 2) return null;
    let best = null;
    for (let i = 0; i < sorted.length - 1; i++) {
      const a = sorted[i];
      const b = sorted[i + 1];
      if (a.overall == null || b.overall == null) continue;
      const d = b.overall - a.overall;
      if (best == null || d > best.delta) best = { fromIdx: i, toIdx: i + 1, delta: d };
    }
    return best;
  }, [sorted]);

  // Default selection: first ↔ latest.
  const [fromIdx, setFromIdx] = useState(0);
  const [toIdx, setToIdx] = useState(sorted.length - 1);
  // Scrub: 0 = full A, 1 = full B. Animates the radar polygon between states.
  const [scrub, setScrub] = useState(1);

  // Keep fromIdx < toIdx (chronological) regardless of selection order so
  // deltas always read "earlier → later". A swap also resets the scrub.
  const [aIdx, bIdx] = fromIdx <= toIdx ? [fromIdx, toIdx] : [toIdx, fromIdx];
  const A = sorted[aIdx];
  const B = sorted[bIdx];

  // Radar series. Each axis is a pillar, value is 0..10. Interpolated by
  // the scrub slider so the polygon morphs between A and B.
  const radarData = useMemo(() => {
    if (!A || !B) return [];
    return PILLAR_KEYS.map((k) => {
      const a = A.pillars?.[k];
      const b = B.pillars?.[k];
      const aVal = a == null ? 0 : a;
      const bVal = b == null ? 0 : b;
      const live = aVal + (bVal - aVal) * scrub;
      return {
        pillar: PILLAR_LABEL[k] || k,
        a: aVal,
        b: bVal,
        live: Math.round(live * 10) / 10,
      };
    });
  }, [A, B, scrub]);

  // Per-pillar deltas (b − a). Pure client-side math, same as the backend's
  // first-vs-last delta logic but on the user-picked pair.
  const deltas = useMemo(() => {
    const out = {};
    if (!A || !B) return out;
    for (const k of PILLAR_KEYS) {
      const a = A.pillars?.[k];
      const b = B.pillars?.[k];
      if (a == null || b == null) continue;
      out[k] = Math.round((b - a) * 10) / 10;
    }
    return out;
  }, [A, B]);

  // Defensive: if for some reason A or B is missing, render nothing.
  if (!A || !B) return null;

  const fmtDate = (s) => new Date(s).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });

  const applyPreset = (preset) => {
    if (preset === "first_latest") {
      setFromIdx(0); setToIdx(sorted.length - 1); setScrub(1);
    } else if (preset === "biggest" && biggestJump && isPremium) {
      setFromIdx(biggestJump.fromIdx); setToIdx(biggestJump.toIdx); setScrub(1);
    }
  };

  const onLockedClick = (e) => {
    e.preventDefault();
    if (onUnlock) onUnlock();
  };

  return (
    <div data-testid="trajectory-compare-card" className="mt-6 bg-cream-card border border-gray-border p-5 md:p-8">
      {/* Header */}
      <div className="flex items-start justify-between flex-wrap gap-3">
        <div>
          <div className="flex items-center gap-2 text-[10px] uppercase tracking-[0.22em] font-bold text-forest">
            <ArrowLeftRight className="w-3.5 h-3.5" /> Compare moments
          </div>
          <h3 className="mt-2 font-barlow font-black uppercase text-2xl tracking-tighter">
            Watch yourself improve
          </h3>
          <p className="mt-1 text-xs text-ink/55">
            Two reports, side-by-side. Drag the slider to morph one into the other.
          </p>
        </div>
        {!isPremium && (
          <span className="bg-cream-soft border border-ink/15 text-ink/65 text-[10px] uppercase tracking-widest font-bold px-2 py-1 flex items-center gap-1">
            <Lock className="w-3 h-3" /> Free preview — first ↔ latest only
          </span>
        )}
      </div>

      {/* Preset chips */}
      <div className="mt-4 flex flex-wrap gap-2">
        <button
          type="button"
          onClick={() => applyPreset("first_latest")}
          data-testid="compare-preset-first-latest"
          className={`text-[10px] uppercase tracking-widest font-black px-3 py-1.5 transition-colors ${
            aIdx === 0 && bIdx === sorted.length - 1
              ? "bg-forest text-white"
              : "bg-cream-soft text-ink/70 hover:bg-forest hover:text-white"
          }`}
        >
          First ↔ Latest
        </button>
        <button
          type="button"
          onClick={(e) => { if (!isPremium) return onLockedClick(e); applyPreset("biggest"); }}
          disabled={!biggestJump}
          data-testid="compare-preset-biggest"
          aria-label={isPremium ? "Compare the biggest jump in scores" : "Unlock Progress Pass to use Biggest jump"}
          className={`text-[10px] uppercase tracking-widest font-black px-3 py-1.5 transition-colors flex items-center gap-1.5 ${
            !isPremium
              ? "bg-cream-soft text-ink/55 hover:bg-forest hover:text-white border border-ink/15 cursor-pointer"
              : biggestJump && aIdx === biggestJump.fromIdx && bIdx === biggestJump.toIdx
              ? "bg-forest text-white"
              : "bg-cream-soft text-ink/70 hover:bg-forest hover:text-white"
          }`}
        >
          {!isPremium && <Lock className="w-3 h-3" />}
          <Zap className="w-3 h-3" /> Biggest jump
        </button>
      </div>

      {/* Date pickers */}
      <div className="mt-4 grid grid-cols-1 md:grid-cols-[1fr_auto_1fr] gap-3 items-center">
        <DatePicker
          label="From"
          value={aIdx}
          options={sorted}
          onChange={(i) => { setFromIdx(i); setScrub(1); }}
          locked={!isPremium}
          onLockedClick={onLockedClick}
          testid="compare-from-select"
        />
        <ArrowRight className="hidden md:block w-5 h-5 text-forest mx-auto" />
        <DatePicker
          label="To"
          value={bIdx}
          options={sorted}
          onChange={(i) => { setToIdx(i); setScrub(1); }}
          locked={!isPremium}
          onLockedClick={onLockedClick}
          testid="compare-to-select"
        />
      </div>

      {/* Radar pair + scrub slider */}
      <div className="mt-6 grid grid-cols-1 md:grid-cols-[1fr_auto_1fr] gap-4 md:gap-6 items-center">
        <RadarPanel
          snapshot={A}
          radarData={radarData}
          which="a"
          accent="#2D6B3D"
          fmtDate={fmtDate}
          testid="compare-radar-a"
        />
        <div className="hidden md:flex flex-col items-center gap-3 px-2">
          <ArrowLeftRight className="w-5 h-5 text-forest" />
        </div>
        <RadarPanel
          snapshot={B}
          radarData={radarData}
          which="b"
          accent="#1F4F2F"
          fmtDate={fmtDate}
          testid="compare-radar-b"
        />
      </div>

      {/* Scrub slider (single shared control) */}
      <div className="mt-5">
        <div className="flex items-baseline justify-between mb-2">
          <span className="text-[10px] uppercase tracking-[0.22em] font-bold text-forest">Morph slider</span>
          <span className="text-[10px] uppercase tracking-widest text-ink/55 font-bold">
            {scrub <= 0.05 ? `Showing ${fmtDate(A.date)}` : scrub >= 0.95 ? `Showing ${fmtDate(B.date)}` : `In-between ${Math.round(scrub * 100)}%`}
          </span>
        </div>
        <input
          type="range"
          min={0}
          max={1}
          step={0.01}
          value={scrub}
          onChange={(e) => setScrub(Number(e.target.value))}
          data-testid="compare-scrub"
          aria-label="Morph between the two snapshots"
          className="w-full accent-forest h-1.5 cursor-pointer"
        />
      </div>

      {/* Pillar delta strip */}
      <div className="mt-6 grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-2">
        {PILLAR_KEYS.map((k) => {
          const d = deltas[k];
          if (d === undefined) return null;
          const positive = d > 0;
          const negative = d < 0;
          const A_v = A.pillars?.[k];
          const B_v = B.pillars?.[k];
          return (
            <div
              key={k}
              data-testid={`compare-pillar-${k}`}
              className="border border-gray-border p-3 bg-white"
            >
              <div className="text-[10px] uppercase tracking-widest font-bold text-ink/65 truncate">
                {PILLAR_LABEL[k] || k}
              </div>
              <div className={`mt-1 font-barlow font-black text-xl ${positive ? "text-forest" : negative ? "text-amber-700" : "text-ink/60"}`}>
                {positive ? "+" : ""}{d}
              </div>
              <div className="mt-0.5 text-[10px] text-ink/55">
                {A_v} → {B_v}
              </div>
            </div>
          );
        })}
      </div>

      {/* Side-by-side posters (if available on the timeline snapshots) */}
      {(A.poster_url || B.poster_url) && (
        <div className="mt-6 grid grid-cols-2 gap-3">
          <ComparePoster snapshot={A} label="Before" fmtDate={fmtDate} />
          <ComparePoster snapshot={B} label="After" fmtDate={fmtDate} />
        </div>
      )}

      {/* Pass nudge for free users — single non-pushy line below the card */}
      {!isPremium && (
        <button
          type="button"
          onClick={onUnlock}
          data-testid="compare-unlock-cta"
          className="mt-6 w-full bg-forest hover:bg-forest-pop text-white font-barlow font-black uppercase tracking-widest text-xs px-5 py-3 transition-colors flex items-center justify-center gap-2"
        >
          <Sparkles className="w-3.5 h-3.5" />
          Unlock to compare any two moments
          <ArrowRight className="w-4 h-4" />
        </button>
      )}
    </div>
  );
}

function DatePicker({ label, value, options, onChange, locked, onLockedClick, testid }) {
  // For locked users we still let them USE the picker — the locking applies
  // only to picking non-first / non-latest indexes. So both ends remain free.
  // Concretely: locked users can pick "First" or "Latest" in either box. If
  // they pick any other index, we route through onLockedClick.
  const firstIdx = 0;
  const lastIdx = options.length - 1;
  const handleChange = (e) => {
    const i = Number(e.target.value);
    if (locked && i !== firstIdx && i !== lastIdx) {
      onLockedClick(e);
      return;
    }
    onChange(i);
  };
  return (
    <div>
      <label className="block text-[10px] uppercase tracking-[0.22em] font-bold text-forest mb-1">
        {label}
      </label>
      <div className="relative">
        <select
          value={value}
          onChange={handleChange}
          data-testid={testid}
          className="w-full appearance-none bg-white border border-gray-border text-ink font-bold text-sm px-3 py-2.5 pr-9 cursor-pointer hover:border-forest transition-colors"
        >
          {options.map((s, i) => {
            const isLocked = locked && i !== firstIdx && i !== lastIdx;
            const labelTxt = `${new Date(s.date).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "2-digit" })} · age ${s.age ?? "—"} · ovr ${s.overall ?? "—"}`;
            return (
              <option key={s.report_id || i} value={i}>
                {isLocked ? "🔒 " : ""}{labelTxt}
              </option>
            );
          })}
        </select>
        <ChevronDown className="w-4 h-4 text-forest absolute right-3 top-1/2 -translate-y-1/2 pointer-events-none" />
      </div>
    </div>
  );
}

function RadarPanel({ snapshot, radarData, which, accent, fmtDate, testid }) {
  const dataKey = "live"; // the interpolated value driven by the scrub slider
  return (
    <div data-testid={testid} className="border border-gray-border bg-white p-3">
      <div className="flex items-baseline justify-between mb-1">
        <span className="text-[10px] uppercase tracking-widest font-black text-forest">
          {which === "a" ? "Before" : "After"}
        </span>
        <span className="text-[10px] uppercase tracking-widest text-ink/55 font-bold">
          age {snapshot.age ?? "—"} · ovr {snapshot.overall ?? "—"}
        </span>
      </div>
      <div className="text-[10px] text-ink/70 font-bold mb-1">{fmtDate(snapshot.date)}</div>
      <div className="aspect-square w-full">
        <ResponsiveContainer width="100%" height="100%">
          <RadarChart data={radarData} margin={{ top: 6, right: 12, bottom: 6, left: 12 }}>
            <PolarGrid stroke="#E5E7EB" />
            <PolarAngleAxis dataKey="pillar" tick={{ fill: "#0A0F0D", fontSize: 9 }} />
            <PolarRadiusAxis angle={90} domain={[0, 10]} tick={{ fill: "#0A0F0D", fontSize: 8 }} />
            <Radar
              name={which === "a" ? "Before" : "After"}
              dataKey={dataKey}
              stroke={accent}
              fill={accent}
              fillOpacity={0.28}
              strokeWidth={2}
              isAnimationActive={false}
            />
          </RadarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

function ComparePoster({ snapshot, label, fmtDate }) {
  const src = snapshot.poster_url ? `${process.env.REACT_APP_BACKEND_URL}${snapshot.poster_url}` : null;
  return (
    <div className="relative border border-gray-border bg-ink/90 aspect-video overflow-hidden">
      {src ? (
        <img
          src={src}
          alt={label}
          className="w-full h-full object-cover"
          onError={(e) => { e.currentTarget.style.display = "none"; }}
        />
      ) : (
        <div className="w-full h-full flex items-center justify-center bg-gradient-to-br from-ink to-forest/40">
          <Flame className="w-7 h-7 text-white/40" strokeWidth={1.5} />
        </div>
      )}
      <div className="absolute inset-0 bg-gradient-to-t from-ink/80 via-transparent to-transparent" />
      <span className="absolute top-2 left-2 bg-forest text-white text-[10px] uppercase tracking-widest font-black px-2 py-1">
        {label}
      </span>
      <span className="absolute bottom-2 right-2 bg-ink/80 text-white text-[10px] font-bold px-2 py-1">
        {fmtDate(snapshot.date)}
      </span>
    </div>
  );
}
