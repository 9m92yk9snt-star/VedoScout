// Premium Building Dashboard — the clean, premium "your dossier is being built"
// experience shown to unlocked users while the full report generates.
// Replaces the old long report-style page. ReportPage's existing polling
// auto-switches to the full dossier the moment generation completes.
import React, { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import {
  Crown, Check, Clock, Play, FileText, ShieldCheck, Eye, Calendar,
  UserCheck, PenLine, Award, MessageSquare, CreditCard, Loader2, Sparkles,
} from "lucide-react";
import api, { ASSET_BASE } from "@/lib/api";

const LIME = "#CCFF00";
const INKG = "#0B1F14";

const STAGES = ["Video Uploaded", "Player Tracked", "AI Analyzing", "Writing Report", "Creating PDF", "Final Check"];
const GAUGES = [
  { label: "Technical", target: 92 },
  { label: "Tactical", target: 85 },
  { label: "Physical", target: 78 },
  { label: "Mental", target: 71 },
];
const SCOUT_STEPS = ["Scout Assigned", "Watching Match", "Writing Notes", "Quality Review", "Ready for You"];

function useBuildProgress(reportId) {
  const startRef = useRef(null);
  const [, setTick] = useState(0);
  if (startRef.current === null) {
    const key = `smp.buildstart.${reportId}`;
    let s = Number(sessionStorage.getItem(key));
    if (!s) {
      s = Date.now();
      try { sessionStorage.setItem(key, String(s)); } catch { /* ignore */ }
    }
    startRef.current = s;
  }
  useEffect(() => {
    const t = setInterval(() => setTick((x) => x + 1), 1000);
    return () => clearInterval(t);
  }, []);
  const elapsed = (Date.now() - startRef.current) / 1000;
  const pct = Math.min(98, Math.round(72 + 26 * (1 - Math.exp(-elapsed / 110))));
  const etaMin = Math.max(1, Math.ceil((99 - pct) / 10));
  return { pct, etaMin, elapsed };
}

function ProgressRing({ pct }) {
  const R = 62;
  const C = 2 * Math.PI * R;
  return (
    <div className="relative w-40 h-40 flex-shrink-0" data-testid="pbd-progress-ring">
      <svg viewBox="0 0 150 150" className="w-full h-full -rotate-90">
        <circle cx="75" cy="75" r={R} fill="none" stroke="rgba(255,255,255,0.12)" strokeWidth="13" />
        <circle
          cx="75" cy="75" r={R} fill="none" stroke={LIME} strokeWidth="13" strokeLinecap="round"
          strokeDasharray={C} strokeDashoffset={C * (1 - pct / 100)}
          style={{ transition: "stroke-dashoffset 1s ease", filter: `drop-shadow(0 0 10px ${LIME}66)` }}
        />
      </svg>
      <div className="absolute inset-0 flex items-center justify-center">
        <span className="font-barlow font-black text-white text-[38px]" data-testid="pbd-progress-pct">{pct}%</span>
      </div>
    </div>
  );
}

function Gauge({ label, value }) {
  const C = Math.PI * 42;
  return (
    <div className="bg-white rounded-2xl border border-[#E9E4D5] p-4 text-center">
      <div className="text-[9.5px] font-extrabold tracking-[0.14em] uppercase text-[#5C6657]">{label}</div>
      <svg viewBox="0 0 100 58" className="w-full mt-1.5">
        <path d="M 8 52 A 42 42 0 0 1 92 52" fill="none" stroke="#E9E4D5" strokeWidth="9" strokeLinecap="round" />
        <path
          d="M 8 52 A 42 42 0 0 1 92 52" fill="none" stroke="url(#pbdgrad)" strokeWidth="9" strokeLinecap="round"
          strokeDasharray={C} strokeDashoffset={C * (1 - value / 100)} style={{ transition: "stroke-dashoffset 1s ease" }}
        />
        <defs>
          <linearGradient id="pbdgrad" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stopColor="#2F8F4E" />
            <stop offset="100%" stopColor="#9FC400" />
          </linearGradient>
        </defs>
        <text x="50" y="50" textAnchor="middle" style={{ fontFamily: "'Barlow Condensed', sans-serif", fontWeight: 900, fontSize: "19px", fill: "#12211A" }}>{value}%</text>
      </svg>
    </div>
  );
}

export default function PremiumBuildingDashboard({ report, user }) {
  const navigate = useNavigate();
  const { pct, etaMin, elapsed } = useBuildProgress(report.id);
  const [showVideo, setShowVideo] = useState(false);
  const [review, setReview] = useState(null);
  const [cancelBusy, setCancelBusy] = useState(false);

  useEffect(() => {
    let live = true;
    api.get(`/reports/${report.id}/agent-review`)
      .then(({ data }) => { if (live) setReview(data); })
      .catch(() => {});
    return () => { live = false; };
  }, [report.id]);

  const firstName = (user?.full_name || "").split(" ")[0] || "there";
  const pd = report.player_details || {};
  const heroImg = report.display_crop_url || report.subject_crop_url || report.poster_url;
  const poster = report.poster_url || report.marker_url;
  const preview = report.preview || {};

  // Stage states derived from real signals + display progress
  const stageState = (i) => {
    if (i === 0) return "done";
    if (i === 1) return (report.fingerprint || (report.anchors || []).length) ? "done" : "active";
    if (i === 2) return report.preview ? "done" : "active";
    if (i === 3) return pct < 90 ? "active" : "done";
    if (i === 4) return pct < 90 ? "todo" : pct < 96 ? "active" : "done";
    return pct >= 96 ? "active" : "todo";
  };

  const gaugeValue = (target) => Math.min(target, Math.round(target * Math.min(1, 0.45 + elapsed / 180)));

  const scoutDone = review?.status === "delivered";
  const scoutStepState = (i) => {
    if (scoutDone) return "done";
    if (i <= 1) return "done";
    if (i === 2) return "active";
    return "todo";
  };

  const contentTypeLabel = ({
    full_match: "Full match", small_sided: "Small-sided game", training: "Training session",
    drill: "Technical drills", fitness: "Fitness work", freestyle: "Freestyle", mixed: "Mixed content",
  })[report.content_gate?.content_type] || "Highlight reel";

  const uploadedLabel = (() => {
    try {
      const d = new Date(report.created_at);
      const today = new Date();
      return d.toDateString() === today.toDateString() ? "Uploaded today" : `Uploaded ${d.toLocaleDateString()}`;
    } catch { return "Uploaded"; }
  })();

  const nextBilling = (() => {
    if (!user?.subscription_renews_at) return null;
    try { return new Date(user.subscription_renews_at).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" }); }
    catch { return null; }
  })();

  const handleCancelSub = async () => {
    if (!window.confirm("Cancel your subscription? You keep access until the end of the current billing period.")) return;
    setCancelBusy(true);
    try {
      await api.post("/me/subscription/cancel");
      toast.success("Subscription cancelled — access continues until the period ends.");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not cancel — please contact support.");
    } finally {
      setCancelBusy(false);
    }
  };

  return (
    <div className="pt-24 md:pt-28 px-4 md:px-6 pb-10" data-testid="premium-building-dashboard">
      <div className="max-w-[880px] mx-auto">
        {/* ── Welcome ── */}
        <h1 className="font-barlow font-black text-[26px] md:text-[32px] text-[#12211A] leading-tight">
          Welcome back, {firstName} <span aria-hidden>👋</span>
        </h1>
        <p className="text-[14px] text-[#5C6657] mt-0.5">Here&rsquo;s your latest report</p>

        {/* ── Building hero ── */}
        <div className="relative rounded-[24px] overflow-hidden mt-4 shadow-xl" style={{ background: `linear-gradient(120deg, #0E2A1B 0%, ${INKG} 60%, #10241A 100%)` }} data-testid="pbd-hero">
          {heroImg && (
            <div className="absolute inset-y-0 right-0 w-[46%] hidden sm:block" aria-hidden>
              <img src={`${ASSET_BASE}${heroImg}`} alt="" className="w-full h-full object-cover opacity-70" />
              <div className="absolute inset-0" style={{ background: `linear-gradient(90deg, ${INKG} 0%, rgba(11,31,20,0.45) 55%, rgba(11,31,20,0.25) 100%)` }} />
            </div>
          )}
          <div className="relative p-6 md:p-8">
            <div className="flex flex-col sm:flex-row items-center gap-6">
              <ProgressRing pct={pct} />
              <div className="text-center sm:text-left">
                <span className="inline-flex items-center gap-1.5 rounded-full px-3.5 py-1.5 text-[11px] font-extrabold tracking-[0.12em] uppercase" style={{ background: "rgba(204,255,0,0.14)", color: LIME, border: `1px solid ${LIME}44` }}>
                  <Crown className="w-3.5 h-3.5" /> Premium Report
                </span>
                <h2 className="font-barlow font-black uppercase leading-[0.98] mt-2.5 text-[30px] md:text-[36px]">
                  <span className="text-white">Building your</span><br />
                  <span style={{ color: LIME }}>Scout Dossier</span>
                </h2>
                <p className="text-white/75 text-[14px] mt-2 max-w-[300px]">
                  Our AI is analyzing every detail of your player&rsquo;s performance.
                </p>
              </div>
            </div>

            {/* stage chain */}
            <div className="mt-6 grid grid-cols-3 sm:grid-cols-6 gap-y-4" data-testid="pbd-stages">
              {STAGES.map((label, i) => {
                const st = stageState(i);
                return (
                  <div key={label} className="flex flex-col items-center text-center px-1" data-testid={`pbd-stage-${i + 1}`}>
                    <span
                      className="w-9 h-9 rounded-full flex items-center justify-center"
                      style={
                        st === "done"
                          ? { background: "rgba(204,255,0,0.15)", border: `2px solid ${LIME}` }
                          : st === "active"
                          ? { background: LIME, boxShadow: `0 0 16px ${LIME}88` }
                          : { background: "rgba(255,255,255,0.08)", border: "2px solid rgba(255,255,255,0.25)" }
                      }
                    >
                      {st === "done" ? (
                        <Check className="w-4 h-4" style={{ color: LIME }} strokeWidth={3} />
                      ) : st === "active" ? (
                        <Loader2 className="w-4 h-4 animate-spin" style={{ color: INKG }} strokeWidth={3} />
                      ) : i === 4 ? (
                        <FileText className="w-4 h-4 text-white/50" />
                      ) : (
                        <ShieldCheck className="w-4 h-4 text-white/50" />
                      )}
                    </span>
                    <span className={`mt-1.5 text-[10.5px] font-bold leading-tight ${st === "todo" ? "text-white/45" : "text-white"}`}>{label}</span>
                  </div>
                );
              })}
            </div>

            <div className="mt-5 flex justify-center">
              <span className="inline-flex items-center gap-2 rounded-full px-5 py-2.5 text-[13px] font-bold text-white" style={{ background: "rgba(255,255,255,0.08)", border: "1px solid rgba(255,255,255,0.18)" }} data-testid="pbd-eta">
                <Clock className="w-4 h-4" style={{ color: LIME }} />
                Estimated ready in <span style={{ color: LIME }}>~{etaMin} min</span>
              </span>
            </div>
          </div>
        </div>

        {/* ── Match card ── */}
        <div className="bg-white rounded-[20px] border border-[#E9E4D5] p-4 mt-4 shadow-sm" data-testid="pbd-match-card">
          <div className="flex items-center gap-4">
            <button
              type="button"
              onClick={() => setShowVideo((s) => !s)}
              className="relative w-32 h-20 rounded-xl overflow-hidden flex-shrink-0 bg-[#0E2A1B] group"
              data-testid="pbd-match-thumb"
            >
              {poster && <img src={`${ASSET_BASE}${poster}`} alt="" className="w-full h-full object-cover" />}
              <span className="absolute inset-0 flex items-center justify-center bg-black/25 group-hover:bg-black/10 transition-colors">
                <span className="w-9 h-9 rounded-full bg-white/90 flex items-center justify-center">
                  <Play className="w-4 h-4 ml-0.5 text-[#12211A] fill-current" />
                </span>
              </span>
              <span className="absolute bottom-1.5 left-1.5 bg-black/70 text-white text-[9px] font-bold px-1.5 py-0.5 rounded">CLIP</span>
            </button>
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-1.5 text-[10px] font-extrabold tracking-[0.14em] uppercase text-[#5C6657]">
                <Award className="w-3.5 h-3.5" /> Your match
              </div>
              <div className="font-barlow font-black text-[20px] text-[#12211A] leading-tight truncate">{pd.player_name || "Your player"}</div>
              <div className="flex items-center gap-2 text-[11.5px] text-[#5C6657] mt-0.5">
                <Calendar className="w-3 h-3" /> {uploadedLabel} <span className="text-[#C9C4B4]">•</span> {contentTypeLabel}
              </div>
            </div>
            <button
              type="button"
              onClick={() => setShowVideo((s) => !s)}
              data-testid="pbd-view-video"
              className="flex-shrink-0 border-2 border-[#12402A] text-[#12402A] hover:bg-[#12402A] hover:text-white transition-colors rounded-full px-5 py-2 text-[12px] font-extrabold tracking-[0.1em] uppercase"
            >
              View
            </button>
          </div>
          {showVideo && report.video_url && (
            <video
              src={`${ASSET_BASE}${report.video_url}`}
              poster={poster ? `${ASSET_BASE}${poster}` : undefined}
              controls autoPlay playsInline
              className="w-full rounded-xl mt-3 bg-black"
              data-testid="pbd-video-player"
            />
          )}
        </div>

        {/* ── Analysis in progress ── */}
        <div className="bg-white rounded-[20px] border border-[#E9E4D5] p-5 mt-4 shadow-sm" data-testid="pbd-gauges">
          <div className="flex items-center gap-2 text-[11px] font-extrabold tracking-[0.16em] uppercase text-[#12402A]">
            <Crown className="w-4 h-4" /> Analysis in progress
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mt-3">
            {GAUGES.map((g) => <Gauge key={g.label} label={g.label} value={gaugeValue(g.target)} />)}
          </div>
        </div>

        {/* ── Live preview (real preview content — numbers arrive with the dossier) ── */}
        <div className="bg-white rounded-[20px] border border-[#E9E4D5] p-5 mt-4 shadow-sm" data-testid="pbd-live-preview">
          <div className="flex items-center gap-2 text-[11px] font-extrabold tracking-[0.16em] uppercase text-[#12402A]">
            <Eye className="w-4 h-4" /> Live preview
          </div>
          {preview.player_type && (
            <span className="inline-block mt-3 bg-[#12402A] text-[#CCFF00] text-[11px] font-extrabold tracking-[0.06em] uppercase px-3 py-1.5 rounded-full">
              {preview.player_type}
            </span>
          )}
          {preview.brief_summary && (
            <p className="text-[13.5px] text-[#3A4136] leading-relaxed mt-2.5">{preview.brief_summary}</p>
          )}
          {(preview.top_strengths || []).length > 0 && (
            <div className="mt-3 space-y-1.5">
              {preview.top_strengths.slice(0, 3).map((s) => (
                <div key={s} className="flex items-start gap-2 text-[13px] font-semibold text-[#12211A]">
                  <Check className="w-4 h-4 mt-0.5 flex-shrink-0" style={{ color: "#2F8F4E" }} strokeWidth={3} />
                  {s}
                </div>
              ))}
            </div>
          )}
          <div className="grid grid-cols-3 gap-2.5 mt-4">
            {["Overall Potential", "Skill Ratings", "Benchmarks"].map((t) => (
              <div key={t} className="rounded-xl border border-[#E9E4D5] bg-[#FBF9F3] p-3 text-center overflow-hidden relative">
                <div className="text-[9px] font-extrabold tracking-[0.1em] uppercase text-[#8B957F]">{t}</div>
                <div className="mt-1.5 h-6 rounded-md bg-gradient-to-r from-[#E9E4D5] via-[#F4F0E4] to-[#E9E4D5] animate-pulse" />
                <div className="text-[9px] text-[#A29D8E] mt-1.5">calculating…</div>
              </div>
            ))}
          </div>
          <div className="flex items-center justify-center gap-1.5 text-[11px] text-[#8B957F] mt-3">
            <Sparkles className="w-3.5 h-3.5" /> Preview updates live as analysis continues
          </div>
        </div>

        {/* ── Human scout review ── */}
        {review && (
          <div className="bg-white rounded-[20px] border border-[#E9E4D5] p-5 mt-4 shadow-sm" data-testid="pbd-scout-review">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2 text-[11px] font-extrabold tracking-[0.16em] uppercase text-[#12402A]">
                <MessageSquare className="w-4 h-4" /> Scout review
              </div>
              <span className="bg-[#F0EDE5] text-[#12402A] text-[9.5px] font-extrabold tracking-[0.1em] uppercase px-3 py-1.5 rounded-full">
                Real human scout
              </span>
            </div>
            <div className="mt-4 grid grid-cols-5 gap-1" data-testid="pbd-scout-steps">
              {SCOUT_STEPS.map((label, i) => {
                const st = scoutStepState(i);
                const Icon = [UserCheck, Play, PenLine, ShieldCheck, Award][i];
                return (
                  <div key={label} className="flex flex-col items-center text-center">
                    <span
                      className="w-9 h-9 rounded-full flex items-center justify-center border-2"
                      style={
                        st === "done"
                          ? { borderColor: "#2F8F4E", background: "#EAF4EC" }
                          : st === "active"
                          ? { borderColor: "#9FC400", background: "#F6FBE4", boxShadow: "0 0 12px rgba(159,196,0,0.5)" }
                          : { borderColor: "#DDD8C8", background: "#FBF9F3" }
                      }
                    >
                      {st === "done" ? <Check className="w-4 h-4 text-[#2F8F4E]" strokeWidth={3} /> : <Icon className={`w-4 h-4 ${st === "active" ? "text-[#5C7A00]" : "text-[#B4AF9F]"}`} />}
                    </span>
                    <span className={`mt-1.5 text-[9.5px] font-bold leading-tight ${st === "todo" ? "text-[#B4AF9F]" : "text-[#12211A]"}`}>{label}</span>
                  </div>
                );
              })}
            </div>
            <div className="mt-4 bg-[#FBF9F3] border border-[#E9E4D5] rounded-xl p-3.5 flex items-center gap-3">
              <span className="w-9 h-9 rounded-full bg-[#12402A] flex items-center justify-center flex-shrink-0">
                <UserCheck className="w-4 h-4 text-[#CCFF00]" />
              </span>
              <div className="text-[12.5px] leading-snug">
                <span className="font-bold text-[#12211A]">{scoutDone ? "Your scout review is ready" : "Your personal scout is reviewing your video"}</span>
                <br />
                <span className="text-[#5C6657]">{scoutDone ? "Read it below your full report." : "You'll be able to chat with them once the report is ready."}</span>
              </div>
            </div>
          </div>
        )}

        {/* ── Premium subscription management (no sales — they already paid) ── */}
        <div className="bg-[#12211A] rounded-[20px] p-5 mt-4" data-testid="pbd-subscription">
          <div className="flex flex-wrap items-center gap-3">
            <span className="w-10 h-10 rounded-full flex items-center justify-center flex-shrink-0" style={{ background: "rgba(204,255,0,0.14)", border: `1px solid ${LIME}44` }}>
              <CreditCard className="w-4.5 h-4.5" style={{ color: LIME, width: 18, height: 18 }} />
            </span>
            <div className="flex-1 min-w-[180px]">
              <div className="flex items-center gap-2">
                <span className="font-barlow font-black uppercase text-white text-[16px]">
                  {user?.subscription_tier ? `${user.subscription_tier} active` : user?.role === "admin" ? "Elite access active" : "Report unlocked"}
                </span>
                <span className="w-2 h-2 rounded-full" style={{ background: LIME }} />
              </div>
              <div className="text-white/60 text-[12px] mt-0.5" data-testid="pbd-billing">
                {user?.subscription_tier
                  ? nextBilling ? `Next billing date: ${nextBilling}` : "Active subscription"
                  : user?.role === "admin" ? "All premium features included" : "Lifetime access to this report"}
              </div>
            </div>
            {user?.subscription_tier && (
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => navigate("/dashboard")}
                  data-testid="pbd-change-sub"
                  className="border border-white/25 text-white hover:bg-white/10 transition-colors rounded-full px-4 py-2 text-[11px] font-extrabold tracking-[0.08em] uppercase"
                >
                  Change subscription
                </button>
                <button
                  type="button"
                  onClick={handleCancelSub}
                  disabled={cancelBusy}
                  data-testid="pbd-cancel-sub"
                  className="text-white/45 hover:text-red-300 transition-colors text-[11px] font-extrabold tracking-[0.08em] uppercase disabled:opacity-50"
                >
                  {cancelBusy ? "Cancelling…" : "Cancel"}
                </button>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
