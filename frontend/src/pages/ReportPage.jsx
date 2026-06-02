import React, { useEffect, useState, useCallback, useRef } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { motion } from "framer-motion";
import {
  Radar, RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, ResponsiveContainer,
} from "recharts";
import Navigation from "@/components/Navigation";
import api, { ASSET_BASE } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import {
  Lock, Unlock, Download, Loader2, ChevronLeft, ShieldCheck, Star,
} from "lucide-react";
import ScoutReview from "@/components/ScoutReview";

function scoreColor(s) {
  if (typeof s !== "number") return "text-white";
  if (s >= 8) return "text-volt";
  if (s >= 6) return "text-yellow-400";
  return "text-red-400";
}

function SectionGrid({ title, section }) {
  if (!section) return null;
  return (
    <div className="bg-surface border border-white/10 p-6 md:p-8">
      <h3 className="font-barlow font-black uppercase text-2xl md:text-3xl text-white">{title}</h3>
      <div className="mt-6 grid sm:grid-cols-2 gap-px bg-white/5">
        {Object.entries(section).map(([key, val]) => (
          <div key={key} className="bg-surface p-4">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs uppercase tracking-[0.18em] font-bold text-white/60">{key.replace(/_/g, " ")}</span>
              <span className={`font-barlow font-black text-2xl ${scoreColor(val?.score)}`}>{val?.score ?? "-"}<span className="text-white/30 text-base">/10</span></span>
            </div>
            <p className="text-sm text-white/75 leading-relaxed">{val?.notes}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

function LockedOverlay({ price, onUnlock, loading }) {
  return (
    <div className="absolute inset-0 z-20 backdrop-blur-xl bg-deepnavy/85 border border-white/10 flex flex-col items-center justify-center text-center p-6 md:p-12">
      <Lock className="w-10 h-10 text-volt mb-5" strokeWidth={1.5} />
      <span className="text-volt text-xs uppercase tracking-[0.3em] font-bold">Premium</span>
      <h3 className="mt-3 font-barlow font-black uppercase text-3xl md:text-5xl text-white tracking-tighter">
        Unlock full premium report
      </h3>
      <p className="mt-4 text-white/70 text-sm md:text-base max-w-xl">
        Full AI analysis across technical, tactical, physical & mental dimensions. Scout view, training plan & a premium PDF.
      </p>
      <div className="mt-6 flex items-baseline gap-2">
        <span className="font-barlow font-black text-6xl md:text-7xl text-volt">{price}</span>
        <span className="text-white/60 uppercase tracking-widest font-bold">DKK</span>
      </div>
      <p className="text-xs text-white/40 uppercase tracking-widest font-bold">One-time payment · No subscription</p>
      <button
        onClick={onUnlock}
        disabled={loading}
        data-testid="unlock-report-btn"
        className="mt-8 bg-volt hover:bg-white text-deepnavy font-barlow font-black uppercase tracking-widest text-base px-10 py-4 transition-colors disabled:opacity-50 flex items-center gap-3"
      >
        {loading ? (
          <>
            <Loader2 className="w-5 h-5 animate-spin" />
            Redirecting to Stripe...
          </>
        ) : (
          <>
            <Unlock className="w-5 h-5" />
            Unlock full premium report
          </>
        )}
      </button>
      <p className="mt-4 text-xs text-white/40 flex items-center gap-2">
        <ShieldCheck className="w-3.5 h-3.5" /> Secure payment via Stripe
      </p>
    </div>
  );
}

export default function ReportPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const { user } = useAuth();
  const [report, setReport] = useState(null);
  const [price, setPrice] = useState(399);
  const [loading, setLoading] = useState(true);
  const [unlocking, setUnlocking] = useState(false);
  const [generatingFull, setGeneratingFull] = useState(false);
  const [downloadingPdf, setDownloadingPdf] = useState(false);
  const pollingRef = useRef(null);

  const fetchReport = useCallback(async () => {
    try {
      const [r, p] = await Promise.all([
        api.get(`/reports/${id}`),
        api.get("/settings/price"),
      ]);
      setReport(r.data);
      setPrice(p.data.price_dkk);
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Failed to load report");
      navigate("/dashboard");
    } finally {
      setLoading(false);
    }
  }, [id, navigate]);

  useEffect(() => { fetchReport(); }, [fetchReport]);

  // Handle Stripe redirect with session_id polling
  useEffect(() => {
    const sessionId = searchParams.get("session_id");
    const canceled = searchParams.get("canceled");
    if (canceled) {
      toast.info("Payment canceled");
      const np = new URLSearchParams(searchParams);
      np.delete("canceled");
      setSearchParams(np, { replace: true });
      return;
    }
    if (!sessionId) return;

    let attempts = 0;
    const maxAttempts = 10;
    const poll = async () => {
      try {
        const { data } = await api.get(`/payments/status/${sessionId}`);
        if (data.payment_status === "paid") {
          toast.success("Payment confirmed. Generating your premium report...");
          const np = new URLSearchParams(searchParams);
          np.delete("session_id");
          setSearchParams(np, { replace: true });
          await fetchReport();
          // trigger full report generation
          setGeneratingFull(true);
          try {
            await api.post(`/reports/${id}/generate-full`);
            await fetchReport();
            toast.success("Full premium report ready");
          } catch (e) {
            toast.error(e?.response?.data?.detail || "Failed to generate full report");
          } finally {
            setGeneratingFull(false);
          }
          return;
        }
        if (data.status === "expired") {
          toast.error("Payment session expired");
          return;
        }
        if (attempts++ < maxAttempts) {
          pollingRef.current = setTimeout(poll, 2000);
        } else {
          toast.info("Still processing. Please refresh shortly.");
        }
      } catch (err) {
        toast.error("Error checking payment status");
      }
    };
    poll();
    return () => clearTimeout(pollingRef.current);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams.get("session_id"), searchParams.get("canceled")]);

  const handleUnlock = async () => {
    setUnlocking(true);
    try {
      const { data } = await api.post("/payments/checkout", {
        report_id: id,
        origin_url: window.location.origin,
      });
      window.location.href = data.url;
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Failed to start checkout");
      setUnlocking(false);
    }
  };

  const handleGenerateFull = async () => {
    setGeneratingFull(true);
    try {
      await api.post(`/reports/${id}/generate-full`);
      await fetchReport();
      toast.success("Full report ready");
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Failed to generate full report");
    } finally {
      setGeneratingFull(false);
    }
  };

  const handleDownloadPdf = async () => {
    setDownloadingPdf(true);
    try {
      const res = await api.get(`/reports/${id}/pdf`, { responseType: "blob" });
      const blob = new Blob([res.data], { type: "application/pdf" });
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `EliteScout_${report?.player_details?.player_name || "report"}.pdf`;
      link.click();
      window.URL.revokeObjectURL(url);
    } catch (err) {
      toast.error(err?.response?.data?.detail || "PDF download failed");
    } finally {
      setDownloadingPdf(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-deepnavy text-white">
        <Navigation />
        <div className="pt-40 text-center">
          <Loader2 className="w-8 h-8 animate-spin text-volt mx-auto" />
          <p className="mt-4 text-white/60 uppercase tracking-widest text-sm font-bold">Loading report...</p>
        </div>
      </div>
    );
  }
  if (!report) return null;

  const { preview, full_report, player_details, video_url, poster_url, marker_url, is_paid, manually_unlocked } = report;
  const unlocked = is_paid || manually_unlocked || user?.role === "admin";

  const radarData = full_report ? [
    { axis: "Technical", score: full_report.scores?.technical },
    { axis: "Tactical", score: full_report.scores?.tactical },
    { axis: "Physical", score: full_report.scores?.physical },
    { axis: "Mentality", score: full_report.scores?.mentality },
    { axis: "Overall", score: full_report.scores?.overall_development },
  ] : null;

  return (
    <div className="min-h-screen bg-deepnavy text-white pb-20">
      <Navigation />

      <div className="pt-28 px-6">
        <div className="max-w-7xl mx-auto">
          <button
            onClick={() => navigate("/dashboard")}
            data-testid="back-to-dashboard"
            className="flex items-center gap-2 text-white/60 hover:text-volt uppercase tracking-widest text-xs font-bold transition-colors"
          >
            <ChevronLeft className="w-4 h-4" />
            Dashboard
          </button>

          {/* ===== Header ===== */}
          <div className="mt-6 grid lg:grid-cols-5 gap-px bg-white/10 border border-white/10">
            <div className="bg-surface p-6 md:p-8 lg:col-span-2">
              {report.demo ? (
                <div className="relative w-full bg-deepnavy border border-volt/20 aspect-video flex flex-col items-center justify-center text-center p-6">
                  <div className="absolute top-3 right-3 bg-volt text-deepnavy text-[10px] uppercase tracking-widest font-black px-2 py-1">Demo</div>
                  <div
                    className="absolute inset-0 opacity-30"
                    style={{
                      backgroundImage: "url('https://images.pexels.com/photos/12616082/pexels-photo-12616082.jpeg')",
                      backgroundSize: "cover",
                      backgroundPosition: "center",
                    }}
                  />
                  <div className="absolute inset-0 bg-gradient-to-t from-deepnavy via-deepnavy/70 to-transparent" />
                  <div className="relative">
                    <div className="font-barlow font-black uppercase text-3xl text-volt">Sample report</div>
                    <p className="mt-2 text-sm text-white/70 max-w-sm">
                      This is a demo report so you can explore the premium experience. Upload your own video to get a real analysis.
                    </p>
                  </div>
                </div>
              ) : (
                <video
                  src={`${ASSET_BASE}${video_url}`}
                  poster={poster_url ? `${ASSET_BASE}${poster_url}` : undefined}
                  controls
                  playsInline
                  preload="metadata"
                  data-testid="report-video"
                  className="w-full bg-black aspect-video"
                />
              )}
              <div className="mt-4 grid grid-cols-3 gap-px bg-white/5">
                <div className="bg-surface p-3">
                  <div className="text-[10px] uppercase tracking-[0.18em] text-white/40 font-bold">Type</div>
                  <div className="text-sm text-white font-bold mt-1 capitalize">{player_details.video_type}</div>
                </div>
                <div className="bg-surface p-3">
                  <div className="text-[10px] uppercase tracking-[0.18em] text-white/40 font-bold">Foot</div>
                  <div className="text-sm text-white font-bold mt-1 capitalize">{player_details.preferred_foot}</div>
                </div>
                <div className="bg-surface p-3">
                  <div className="text-[10px] uppercase tracking-[0.18em] text-white/40 font-bold">Age</div>
                  <div className="text-sm text-white font-bold mt-1">{player_details.age}</div>
                </div>
              </div>
            </div>

            <div className="bg-surface p-6 md:p-8 lg:col-span-3 flex flex-col justify-between">
              <div>
                <span className="text-volt text-xs uppercase tracking-[0.25em] font-bold">{unlocked ? "Premium report" : "Free preview"}</span>
                <h1
                  data-testid="report-player-name"
                  className="mt-3 font-barlow font-black uppercase text-4xl md:text-6xl tracking-tighter leading-[0.95]"
                >
                  {player_details.player_name}
                </h1>
                <p className="mt-3 text-white/60 text-sm md:text-base">
                  {player_details.position} · {player_details.current_club || "Independent"}
                </p>
                <div className="mt-6 inline-flex items-center gap-2 bg-deepnavy border border-volt/30 px-4 py-2">
                  <Star className="w-4 h-4 text-volt" />
                  <span className="font-barlow font-bold uppercase text-sm" data-testid="report-player-type">
                    {(full_report?.player_type) || preview?.player_type || "Player Analysis"}
                  </span>
                </div>

                {marker_url && (
                  <div className="mt-5 border border-white/10 bg-deepnavy/60 p-3 max-w-md" data-testid="marker-card">
                    <div className="flex items-center gap-2 mb-2">
                      <Star className="w-3 h-3 text-volt" fill="currentColor" />
                      <span className="text-[10px] uppercase tracking-[0.22em] font-bold text-volt">Verified player</span>
                    </div>
                    <img
                      src={`${ASSET_BASE}${marker_url}`}
                      alt="Marked player"
                      className="w-full aspect-video object-cover border border-white/5"
                    />
                    <p className="mt-2 text-[11px] text-white/55">
                      AI analysed only the player you circled above.
                    </p>
                  </div>
                )}
              </div>

              {unlocked && full_report && (
                <div className="mt-8 grid grid-cols-5 gap-px bg-white/10 border border-white/10">
                  {[
                    { label: "Technical", v: full_report.scores?.technical },
                    { label: "Tactical", v: full_report.scores?.tactical },
                    { label: "Physical", v: full_report.scores?.physical },
                    { label: "Mentality", v: full_report.scores?.mentality },
                    { label: "Overall", v: full_report.scores?.overall_development },
                  ].map((s, i) => (
                    <div key={i} className="bg-surface p-3 text-center">
                      <div className="text-[10px] uppercase tracking-[0.18em] text-white/40 font-bold">{s.label}</div>
                      <div className={`font-barlow font-black text-3xl mt-1 ${scoreColor(s.v)}`}>{s.v ?? "-"}</div>
                    </div>
                  ))}
                </div>
              )}

              {unlocked && full_report && (
                <button
                  onClick={handleDownloadPdf}
                  disabled={downloadingPdf}
                  data-testid="download-pdf-btn"
                  className="mt-6 self-start bg-volt hover:bg-white text-deepnavy font-barlow font-black uppercase tracking-widest text-sm px-6 py-3 transition-colors disabled:opacity-50 flex items-center gap-2"
                >
                  {downloadingPdf ? <Loader2 className="w-4 h-4 animate-spin" /> : <Download className="w-4 h-4" />}
                  Download premium PDF
                </button>
              )}
            </div>
          </div>

          {/* ===== Free Preview ===== */}
          <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} className="mt-10">
            <div className="grid lg:grid-cols-3 gap-px bg-white/10 border border-white/10">
              <div className="bg-surface p-6 md:p-8 lg:col-span-2">
                <span className="text-volt text-xs uppercase tracking-[0.25em] font-bold">Brief Summary</span>
                <p
                  data-testid="report-preview-summary"
                  className="mt-3 text-white/85 text-base md:text-lg leading-relaxed"
                >
                  {preview?.brief_summary}
                </p>

                <div className="mt-8 grid sm:grid-cols-2 gap-6">
                  <div>
                    <div className="text-xs uppercase tracking-[0.2em] font-bold text-white/40 mb-3">Top strengths</div>
                    <ul className="space-y-2">
                      {(preview?.top_strengths || []).map((s, i) => (
                        <li key={i} data-testid={`preview-strength-${i}`} className="flex items-start gap-2 text-sm text-white">
                          <span className="text-volt mt-1">▶</span> {s}
                        </li>
                      ))}
                    </ul>
                  </div>
                  <div>
                    <div className="text-xs uppercase tracking-[0.2em] font-bold text-white/40 mb-3">Area for improvement</div>
                    <p data-testid="preview-improvement" className="text-sm text-white/85 leading-relaxed">
                      {preview?.area_for_improvement}
                    </p>
                  </div>
                </div>
              </div>

              <div className="bg-surface p-6 md:p-8">
                <span className="text-volt text-xs uppercase tracking-[0.25em] font-bold">{preview?.sample_section?.title || "Sample Section"}</span>
                <p className="mt-3 text-white/75 text-sm leading-relaxed">{preview?.sample_section?.content}</p>
                <div className="mt-6 border-t border-white/10 pt-6">
                  <p className="text-xs text-white/40 uppercase tracking-[0.2em] font-bold">More premium sections below</p>
                </div>
              </div>
            </div>
          </motion.div>

          {/* ===== Premium Sections ===== */}
          <div className="mt-10 relative">
            {!unlocked && (
              <LockedOverlay
                price={price}
                onUnlock={handleUnlock}
                loading={unlocking}
              />
            )}

            <div className={`${!unlocked ? "blur-locked" : ""} space-y-6`} data-testid="premium-content">
              {/* Executive Summary */}
              {(unlocked && full_report) && (
                <div className="bg-surface border border-white/10 p-6 md:p-8">
                  <h3 className="font-barlow font-black uppercase text-2xl md:text-3xl text-white">Executive Summary</h3>
                  <p className="mt-4 text-white/85 leading-relaxed">{full_report.executive_summary}</p>
                </div>
              )}

              {/* Placeholder content if locked */}
              {!unlocked && (
                <>
                  <div className="bg-surface border border-white/10 p-6 md:p-8">
                    <h3 className="font-barlow font-black uppercase text-2xl md:text-3xl text-white">Technical Analysis</h3>
                    <div className="mt-6 grid sm:grid-cols-2 gap-4">
                      {["First touch","Ball control","Dribbling","Passing","Shooting","Weak foot","1v1 actions"].map((k,i)=>(
                        <div key={i} className="flex items-center justify-between bg-deepnavy p-3 border border-white/5">
                          <span className="text-white/80 text-sm">{k}</span>
                          <span className="text-volt font-barlow font-black text-xl">8/10</span>
                        </div>
                      ))}
                    </div>
                  </div>
                  <div className="bg-surface border border-white/10 p-6 md:p-8">
                    <h3 className="font-barlow font-black uppercase text-2xl md:text-3xl text-white">Tactical Analysis</h3>
                    <div className="mt-6 grid sm:grid-cols-2 gap-4">
                      {["Positioning","Off-ball movement","Scanning","Decision making","Timing of runs","Game understanding"].map((k,i)=>(
                        <div key={i} className="flex items-center justify-between bg-deepnavy p-3 border border-white/5">
                          <span className="text-white/80 text-sm">{k}</span>
                          <span className="text-volt font-barlow font-black text-xl">7/10</span>
                        </div>
                      ))}
                    </div>
                  </div>
                  <div className="bg-surface border border-white/10 p-6 md:p-8">
                    <h3 className="font-barlow font-black uppercase text-2xl md:text-3xl text-white">Physical & Mentality</h3>
                    <p className="mt-3 text-white/60 text-sm">Acceleration · Balance · Agility · Work rate · Focus · Competitive mindset.</p>
                  </div>
                  <div className="bg-surface border border-white/10 p-6 md:p-8">
                    <h3 className="font-barlow font-black uppercase text-2xl md:text-3xl text-white">Scout View · Training Plan · Video Comments</h3>
                    <p className="mt-3 text-white/60 text-sm">Full breakdown across scout perspective, personalized training plan and timestamped video comments.</p>
                  </div>
                </>
              )}

              {/* Unlocked content */}
              {(unlocked && full_report) && (
                <>
                  {/* Radar chart */}
                  {radarData && (
                    <div className="bg-surface border border-white/10 p-6 md:p-8">
                      <h3 className="font-barlow font-black uppercase text-2xl md:text-3xl text-white">Performance Radar</h3>
                      <div className="mt-6 h-80">
                        <ResponsiveContainer width="100%" height="100%">
                          <RadarChart data={radarData}>
                            <PolarGrid stroke="rgba(255,255,255,0.12)" />
                            <PolarAngleAxis dataKey="axis" tick={{ fill: "#94A3B8", fontSize: 12 }} />
                            <PolarRadiusAxis domain={[0, 10]} tick={{ fill: "#94A3B8", fontSize: 10 }} />
                            <Radar dataKey="score" stroke="#CCFF00" fill="#CCFF00" fillOpacity={0.35} />
                          </RadarChart>
                        </ResponsiveContainer>
                      </div>
                    </div>
                  )}

                  <SectionGrid title="Technical Analysis" section={full_report.technical} />
                  <SectionGrid title="Tactical Analysis" section={full_report.tactical} />
                  <SectionGrid title="Physical Analysis" section={full_report.physical} />
                  <SectionGrid title="Mentality Analysis" section={full_report.mentality} />

                  {/* Scout View */}
                  {full_report.scout_view && (
                    <div className="bg-surface border border-white/10 p-6 md:p-8">
                      <h3 className="font-barlow font-black uppercase text-2xl md:text-3xl text-white">How a Scout Might Assess This Player</h3>
                      <div className="mt-6 grid lg:grid-cols-3 gap-px bg-white/5">
                        <div className="bg-surface p-4">
                          <div className="text-xs uppercase tracking-[0.2em] font-bold text-volt mb-3">Key strengths</div>
                          <ul className="space-y-2 text-sm text-white/85">
                            {(full_report.scout_view.key_strengths || []).map((s,i)=>(
                              <li key={i} className="flex gap-2"><span className="text-volt mt-1">▶</span><span>{s}</span></li>
                            ))}
                          </ul>
                        </div>
                        <div className="bg-surface p-4">
                          <div className="text-xs uppercase tracking-[0.2em] font-bold text-yellow-400 mb-3">Areas of concern</div>
                          <ul className="space-y-2 text-sm text-white/85">
                            {(full_report.scout_view.areas_of_concern || []).map((s,i)=>(
                              <li key={i} className="flex gap-2"><span className="text-yellow-400 mt-1">▶</span><span>{s}</span></li>
                            ))}
                          </ul>
                        </div>
                        <div className="bg-surface p-4">
                          <div className="text-xs uppercase tracking-[0.2em] font-bold text-white/60 mb-3">Development priorities</div>
                          <ul className="space-y-2 text-sm text-white/85">
                            {(full_report.scout_view.development_priorities || []).map((s,i)=>(
                              <li key={i} className="flex gap-2"><span className="text-white/60 mt-1">▶</span><span>{s}</span></li>
                            ))}
                          </ul>
                        </div>
                      </div>
                      <div className="mt-6 grid md:grid-cols-2 gap-px bg-white/5">
                        <div className="bg-surface p-4">
                          <div className="text-xs uppercase tracking-[0.2em] font-bold text-white/40 mb-2">Appropriate next competitive level</div>
                          <p className="text-sm text-white/85">{full_report.scout_view.appropriate_next_level}</p>
                        </div>
                        <div className="bg-surface p-4">
                          <div className="text-xs uppercase tracking-[0.2em] font-bold text-white/40 mb-2">Positional suitability</div>
                          <p className="text-sm text-white/85">{full_report.scout_view.positional_suitability}</p>
                        </div>
                      </div>
                      <p className="mt-6 text-xs text-white/40 italic">
                        This is an independent development analysis and does not guarantee selection or advancement opportunities.
                      </p>
                    </div>
                  )}

                  {/* Potential */}
                  {full_report.potential_assessment && (
                    <div className="bg-surface border border-white/10 p-6 md:p-8">
                      <h3 className="font-barlow font-black uppercase text-2xl md:text-3xl text-white">Potential Assessment</h3>
                      <div className="mt-6 grid md:grid-cols-2 gap-px bg-white/5">
                        {[
                          ["Current level", full_report.potential_assessment.current_level],
                          ["Development potential", full_report.potential_assessment.development_potential],
                          ["Recommended next step", full_report.potential_assessment.recommended_next_step],
                          ["3-month focus", full_report.potential_assessment.three_month_focus],
                        ].map(([k, v], i) => (
                          <div key={i} className="bg-surface p-4">
                            <div className="text-xs uppercase tracking-[0.2em] font-bold text-volt mb-2">{k}</div>
                            <p className="text-sm text-white/85">{v}</p>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Training Plan */}
                  {full_report.training_plan && (
                    <div className="bg-surface border border-white/10 p-6 md:p-8">
                      <h3 className="font-barlow font-black uppercase text-2xl md:text-3xl text-white">Personal Training Plan</h3>
                      <div className="mt-6 grid md:grid-cols-2 lg:grid-cols-3 gap-px bg-white/5">
                        {(full_report.training_plan.exercises || []).map((ex, i) => (
                          <div key={i} className="bg-surface p-4">
                            <div className="flex items-center justify-between mb-2">
                              <span className="font-barlow font-black uppercase text-white text-base">{ex.name}</span>
                              <span className="text-xs text-volt font-bold">{ex.duration}</span>
                            </div>
                            <p className="text-sm text-white/75 leading-relaxed">{ex.description}</p>
                          </div>
                        ))}
                      </div>
                      <div className="mt-6 grid md:grid-cols-3 gap-px bg-white/5">
                        <div className="bg-surface p-4">
                          <div className="text-xs uppercase tracking-[0.2em] font-bold text-volt mb-2">Weekly focus</div>
                          <p className="text-sm text-white/85">{full_report.training_plan.weekly_focus}</p>
                        </div>
                        <div className="bg-surface p-4">
                          <div className="text-xs uppercase tracking-[0.2em] font-bold text-volt mb-2">30-day plan</div>
                          <p className="text-sm text-white/85">{full_report.training_plan.thirty_day_plan}</p>
                        </div>
                        <div className="bg-surface p-4">
                          <div className="text-xs uppercase tracking-[0.2em] font-bold text-volt mb-2">90-day plan</div>
                          <p className="text-sm text-white/85">{full_report.training_plan.ninety_day_plan}</p>
                        </div>
                      </div>
                    </div>
                  )}

                  {/* Video Comments */}
                  {full_report.video_comments && full_report.video_comments.length > 0 && (
                    <div className="bg-surface border border-white/10 p-6 md:p-8">
                      <h3 className="font-barlow font-black uppercase text-2xl md:text-3xl text-white">Video Comments</h3>
                      <div className="mt-6 space-y-2">
                        {full_report.video_comments.map((c, i) => (
                          <div key={i} className="flex items-start gap-4 bg-deepnavy p-3 border border-white/5">
                            <span className="font-barlow font-black text-volt min-w-[64px]">{c.timestamp}</span>
                            <p className="text-sm text-white/85">{c.comment}</p>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Final summary */}
                  {full_report.final_summary && (
                    <div className="bg-surface border border-white/10 p-6 md:p-8">
                      <h3 className="font-barlow font-black uppercase text-2xl md:text-3xl text-white">Final Summary</h3>
                      <p className="mt-4 text-white/85 leading-relaxed">{full_report.final_summary}</p>
                      <p className="mt-6 text-xs text-white/40 italic">
                        Scores presented as developmental guidance, not definitive scouting evaluations.
                      </p>
                    </div>
                  )}
                </>
              )}

              {/* Scout Review — bonus human review on top of AI report */}
              {unlocked && (
                <ScoutReview reportId={id} />
              )}

              {/* If unlocked but report not yet generated */}
              {unlocked && !full_report && !generatingFull && (
                <div className="bg-surface border border-volt/30 p-8 text-center">
                  <Unlock className="w-10 h-10 text-volt mx-auto mb-4" strokeWidth={1.5} />
                  <h3 className="font-barlow font-black uppercase text-2xl text-white">Report unlocked</h3>
                  <p className="mt-2 text-white/60 text-sm">Generate your premium analysis now.</p>
                  <button
                    onClick={handleGenerateFull}
                    data-testid="generate-full-report-btn"
                    className="mt-6 bg-volt hover:bg-white text-deepnavy font-barlow font-black uppercase tracking-widest text-sm px-6 py-3 transition-colors"
                  >
                    Generate full report
                  </button>
                </div>
              )}
              {generatingFull && (
                <div className="bg-surface border border-volt/30 p-8 text-center">
                  <Loader2 className="w-8 h-8 animate-spin text-volt mx-auto" />
                  <p className="mt-4 text-white/70 uppercase tracking-widest font-bold text-sm">Generating full premium report... a few minutes</p>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
