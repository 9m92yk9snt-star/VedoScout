// Free Preview Landing — the conversion-first page free users see after the
// AI preview finishes (permanent until they unlock). Replaces the old long
// report-style preview. Every visible fact is REAL (video, strengths count,
// tap timestamps); locked values are never invented — they unlock with payment.
import React, { useMemo, useRef, useState } from "react";
import {
  Lock, Play, ShieldCheck, Star, TrendingUp, Zap, Target, FileText,
  BarChart3, Map, ClipboardList, Brain, Shuffle, Gift, ChevronRight,
  CheckCircle2, Users, MessageSquare, Download,
} from "lucide-react";
import { ASSET_BASE } from "@/lib/api";
import ReportPaywallTiers from "@/components/ReportPaywallTiers";

const LIME = "#CCFF00";
const INKG = "#0B1F14";

const MISSING = [
  { icon: Zap, label: "25 Skill Ratings" },
  { icon: BarChart3, label: "Benchmarks & Percentiles" },
  { icon: Map, label: "Position Analysis" },
  { icon: ClipboardList, label: "Development Plan" },
  { icon: Brain, label: "Mental & Personality Profile" },
  { icon: Shuffle, label: "Playing Style & Comparisons" },
];

const CTA_FEATURES = [
  { icon: FileText, label: "Complete AI Scout Report" },
  { icon: Star, label: "25 Professional Skill Ratings" },
  { icon: BarChart3, label: "Benchmarks & Comparisons" },
  { icon: ClipboardList, label: "Development Plan" },
  { icon: Download, label: "Downloadable PDF" },
  { icon: ShieldCheck, label: "Real Scout Review" },
  { icon: MessageSquare, label: "Talk With Scout" },
];

const potentialLabel = (v) =>
  v >= 85 ? "EXCELLENT" : v >= 75 ? "STRONG" : v >= 65 ? "GOOD" : v >= 50 ? "PROMISING" : "DEVELOPING";

const mmss = (t) => {
  const s = Math.max(0, Math.round(Number(t) || 0));
  return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
};

function LockedBlur({ children, testid }) {
  return (
    <div className="relative overflow-hidden rounded-xl" data-testid={testid}>
      <div className="blur-[7px] select-none pointer-events-none" aria-hidden>{children}</div>
      <div className="absolute inset-0 flex items-center justify-center">
        <span className="w-10 h-10 rounded-full bg-[#12211A] flex items-center justify-center shadow-lg">
          <Lock className="w-4 h-4 text-white" />
        </span>
      </div>
    </div>
  );
}

export default function FreePreviewLanding({ report, user, onUnlockSingle, unlocking }) {
  const videoRef = useRef(null);
  const [playing, setPlaying] = useState(false);
  const pd = report.player_details || {};
  const preview = report.preview || {};
  const teaser = report.teaser || {};
  const poster = report.poster_url || report.marker_url;
  const firstName = (user?.full_name || "").split(" ")[0] || "there";
  const strengths = preview.top_strengths || [];
  const potential = teaser.overall_potential;

  const keyMomentT = useMemo(() => {
    const anchors = report.anchors || [];
    if (!anchors.length) return null;
    const mid = anchors[Math.floor(anchors.length / 2)];
    return mid?.t != null ? mmss(mid.t) : null;
  }, [report.anchors]);

  const startVideo = () => {
    setPlaying(true);
    setTimeout(() => {
      const v = videoRef.current;
      if (v) { const p = v.play(); if (p?.catch) p.catch(() => {}); }
    }, 60);
  };

  const scrollToPackages = () => {
    document.getElementById("scout-packages")?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  const stars = potential ? Math.round(potential / 20) : 0;

  return (
    <div className="pt-24 md:pt-28 px-4 md:px-6 pb-10" data-testid="free-preview-landing">
      <div className="max-w-[880px] mx-auto">
        {/* ── Header ── */}
        <div className="flex flex-wrap items-start justify-between gap-3" data-testid="fpl-header">
          <div>
            <h1 className="font-barlow font-black text-[26px] md:text-[30px] text-[#12211A] leading-tight">
              Hi {firstName}! <span aria-hidden>👋</span>
            </h1>
            <div className="text-[10.5px] font-extrabold tracking-[0.18em] uppercase text-[#12402A] mt-0.5">
              ScoutMe Pro Benchmarked Analysis
            </div>
            <p className="text-[13px] text-[#5C6657] mt-0.5">Here&rsquo;s your free preview</p>
          </div>
          <div className="flex items-center gap-2.5">
            <div className="flex items-center gap-2">
              <span className="w-8 h-8 rounded-full bg-[#12211A] flex items-center justify-center">
                <Lock className="w-3.5 h-3.5" style={{ color: LIME }} />
              </span>
              <div className="text-[10px] leading-tight">
                <div className="font-extrabold text-[#12211A]">100% PRIVATE &amp; SECURE</div>
                <div className="text-[#5C6657]">Only you can see this preview</div>
              </div>
            </div>
            <span className="inline-flex items-center gap-1.5 bg-white border border-[#E5DFCE] rounded-full px-3.5 py-2 text-[10px] font-extrabold tracking-[0.08em] uppercase text-[#12211A]">
              Preview complete <CheckCircle2 className="w-3.5 h-3.5 text-[#2F8F4E]" />
            </span>
          </div>
        </div>

        {/* ── Hero: video + overall potential ── */}
        <div className="rounded-[22px] overflow-hidden mt-4 grid md:grid-cols-[1.5fr_1fr]" style={{ background: INKG }} data-testid="fpl-hero">
          <div className="relative aspect-video md:aspect-auto md:min-h-[280px] bg-black">
            {playing && report.video_url ? (
              <video
                ref={videoRef}
                src={`${ASSET_BASE}${report.video_url}`}
                poster={poster ? `${ASSET_BASE}${poster}` : undefined}
                controls playsInline
                className="absolute inset-0 w-full h-full object-contain bg-black"
                data-testid="fpl-video-player"
              />
            ) : (
              <button type="button" onClick={startVideo} className="absolute inset-0 w-full group" data-testid="fpl-video">
                {poster && <img src={`${ASSET_BASE}${poster}`} alt="" className="absolute inset-0 w-full h-full object-cover" />}
                <span className="absolute inset-0 bg-black/20 group-hover:bg-black/5 transition-colors" />
                <span className="absolute inset-0 flex items-center justify-center">
                  <span className="w-16 h-16 rounded-full bg-white/85 backdrop-blur flex items-center justify-center transition-transform group-hover:scale-110">
                    <Play className="w-6 h-6 ml-1 text-[#12211A] fill-current" />
                  </span>
                </span>
                <span className="absolute bottom-3 left-3 bg-black/70 text-white text-[10px] font-extrabold tracking-[0.08em] px-2.5 py-1 rounded">
                  PREVIEW CLIP
                </span>
              </button>
            )}
          </div>
          <div className="p-6 flex flex-col justify-center" data-testid="fpl-potential">
            <div className="text-[10.5px] font-extrabold tracking-[0.18em] uppercase text-white/70">Overall potential</div>
            {potential ? (
              <>
                <div className="flex items-baseline gap-1.5 mt-1">
                  <span className="font-barlow font-black text-[58px] leading-none" style={{ color: LIME }} data-testid="fpl-potential-score">{potential}</span>
                  <span className="text-white/60 font-bold text-[16px]">/100</span>
                </div>
                <div className="flex items-center gap-1 mt-2">
                  {[1, 2, 3, 4, 5].map((i) => (
                    <Star key={i} className="w-5 h-5" style={{ color: i <= stars ? LIME : "rgba(255,255,255,0.25)", fill: i <= stars ? LIME : "none" }} />
                  ))}
                </div>
                <div className="font-barlow font-black text-[20px] mt-2" style={{ color: LIME }}>{potentialLabel(potential)}</div>
                <p className="text-white/75 text-[13px] leading-relaxed mt-2">
                  Your player shows real potential. The complete scout evaluation is ready to unlock.
                </p>
              </>
            ) : (
              <>
                <div className="flex items-center gap-3 mt-2">
                  <span className="font-barlow font-black text-[52px] leading-none blur-[9px] select-none" style={{ color: LIME }} aria-hidden>84</span>
                  <span className="w-11 h-11 rounded-full bg-white/10 border border-white/25 flex items-center justify-center">
                    <Lock className="w-4.5 h-4.5 text-white" style={{ width: 18, height: 18 }} />
                  </span>
                </div>
                <div className="font-barlow font-black text-[17px] mt-2 text-white/90">SCORE CALCULATED</div>
                <p className="text-white/70 text-[13px] leading-relaxed mt-1.5">
                  Your player&rsquo;s full 0-100 potential score is computed with the complete scout evaluation — unlock to reveal it.
                </p>
              </>
            )}
          </div>
        </div>

        {/* ── What we discovered ── */}
        <div className="rounded-[22px] mt-4 p-6 grid sm:grid-cols-[auto_1fr_auto] items-center gap-5" style={{ background: INKG }} data-testid="fpl-discovered">
          <span className="w-16 h-16 rounded-full border-[5px] flex items-center justify-center font-barlow font-black text-[28px] mx-auto sm:mx-0" style={{ borderColor: LIME, color: LIME }}>?</span>
          <div className="text-center sm:text-left">
            <div className="text-[10.5px] font-extrabold tracking-[0.2em] uppercase" style={{ color: LIME }}>What we discovered…</div>
            <div className="font-barlow font-black text-white text-[20px] md:text-[22px] leading-tight mt-1">
              There&rsquo;s something special in your player&rsquo;s game that most parents miss.
            </div>
            <p className="text-white/70 text-[13px] mt-1.5">
              Our scout found {strengths.length || "several"} strengths in this clip — one could be a game-changer. Unlock the full report to see what it is.
            </p>
          </div>
          <div className="flex flex-col items-center gap-1.5 mx-auto sm:mx-0">
            <span className="w-14 h-14 rounded-full bg-[#12211A] border border-white/15 flex items-center justify-center animate-pulse">
              <Lock className="w-5 h-5 text-white" />
            </span>
            <span className="text-white/70 text-[9.5px] font-extrabold tracking-[0.08em] uppercase text-center leading-tight">Hidden strength<br />locked</span>
          </div>
        </div>

        {/* ── Preview insights ── */}
        <div className="mt-5" data-testid="fpl-insights">
          <div className="flex items-center gap-2 text-[11px] font-extrabold tracking-[0.16em] uppercase text-[#12402A]">
            <TrendingUp className="w-4 h-4" /> Preview insights
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mt-2.5">
            <div className="bg-white rounded-2xl border border-[#E9E4D5] p-4 text-center shadow-sm" data-testid="fpl-strongest">
              <div className="text-[9.5px] font-extrabold tracking-[0.12em] uppercase text-[#5C6657]">Strongest area</div>
              <span className="w-12 h-12 rounded-full bg-[#F3F8E1] flex items-center justify-center mx-auto mt-3">
                <Zap className="w-5 h-5 text-[#5C7A00]" />
              </span>
              <div className="font-barlow font-black text-[15px] text-[#12211A] mt-2.5 leading-tight">
                {(strengths[0] || "Movement").toUpperCase()}
              </div>
              <div className="text-[11.5px] text-[#5C6657] mt-0.5">Above Average</div>
              <div className="h-1.5 rounded-full bg-[#EDE9DB] mt-3 overflow-hidden">
                <div className="h-full w-[72%] rounded-full" style={{ background: "linear-gradient(90deg,#2F8F4E,#9FC400)" }} />
              </div>
            </div>
            <div className="bg-white rounded-2xl border border-[#E9E4D5] p-4 text-center shadow-sm">
              <div className="text-[9.5px] font-extrabold tracking-[0.12em] uppercase text-[#5C6657]">Top strength</div>
              <LockedBlur testid="fpl-top-strength-locked">
                <div className="py-5">
                  <div className="mx-auto w-24 h-4 rounded bg-[#9FC400]/60" />
                  <div className="mx-auto w-32 h-3 rounded bg-[#C9C4B4] mt-2" />
                </div>
              </LockedBlur>
              <div className="text-[11.5px] font-semibold text-[#12211A] mt-2 leading-snug">Unlock to reveal your biggest strength</div>
            </div>
            <div className="bg-white rounded-2xl border border-[#E9E4D5] p-4 text-center shadow-sm">
              <div className="text-[9.5px] font-extrabold tracking-[0.12em] uppercase text-[#5C6657]">Needs to improve</div>
              <LockedBlur testid="fpl-improve-locked">
                <div className="py-5">
                  <div className="mx-auto w-24 h-4 rounded bg-[#8FA0C9]/60" />
                  <div className="mx-auto w-32 h-3 rounded bg-[#C9C4B4] mt-2" />
                </div>
              </LockedBlur>
              <div className="text-[11.5px] font-semibold text-[#12211A] mt-2 leading-snug">Unlock to see where you can improve most</div>
            </div>
          </div>
        </div>

        {/* ── Key moment + what you're missing ── */}
        <div className="grid md:grid-cols-[1fr_1.15fr] gap-4 mt-5">
          <div data-testid="fpl-key-moment">
            <div className="flex items-center gap-2 text-[11px] font-extrabold tracking-[0.16em] uppercase text-[#12402A]">
              <Star className="w-4 h-4" /> Key moment <span className="text-[#8B957F] normal-case tracking-normal font-bold">(preview)</span>
            </div>
            <div className="bg-white rounded-2xl border border-[#E9E4D5] p-4 mt-2.5 flex gap-4 shadow-sm">
              <div className="relative w-28 h-28 rounded-xl overflow-hidden flex-shrink-0 bg-[#0E2A1B]">
                {poster && <img src={`${ASSET_BASE}${poster}`} alt="" className="w-full h-full object-cover blur-[8px] scale-110" aria-hidden />}
                <span className="absolute inset-0 flex items-center justify-center">
                  <span className="w-10 h-10 rounded-full bg-[#12211A] flex items-center justify-center">
                    <Lock className="w-4 h-4 text-white" />
                  </span>
                </span>
              </div>
              <div className="min-w-0">
                <div className="font-barlow font-black text-[16px] text-[#12211A]">Scout Insight Hidden</div>
                <p className="text-[12px] text-[#5C6657] leading-snug mt-1">
                  Unlock the full report to see what our scouts noticed in this moment.
                </p>
                {keyMomentT && (
                  <span className="inline-block bg-[#F0EDE5] text-[#12211A] text-[11px] font-extrabold px-2.5 py-1 rounded-md mt-2.5" data-testid="fpl-key-moment-t">
                    {keyMomentT}
                  </span>
                )}
              </div>
            </div>
          </div>
          <div className="bg-white rounded-2xl border border-[#E9E4D5] p-4 shadow-sm" data-testid="fpl-missing-list">
            <div className="flex items-center justify-between">
              <div className="font-barlow font-black text-[15px] text-[#12211A] uppercase">What you&rsquo;re missing</div>
              <span className="text-[9px] font-extrabold tracking-[0.06em] uppercase px-2 py-1 rounded-md" style={{ background: LIME, color: "#12211A" }}>+ much more</span>
            </div>
            <div className="mt-2.5 space-y-2.5">
              {MISSING.map(({ icon: Icon, label }) => (
                <div key={label} className="flex items-center gap-2.5">
                  <Icon className="w-4 h-4 text-[#12402A] flex-shrink-0" />
                  <span className="text-[12.5px] font-bold text-[#12211A] whitespace-nowrap">{label}</span>
                  <span className="flex-1 h-2 rounded bg-gradient-to-r from-[#EDE9DB] to-[#F6F2E6]" />
                  <Lock className="w-3.5 h-3.5 text-[#8B957F] flex-shrink-0" />
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* ── You've only seen 10% ── */}
        <div className="bg-white rounded-2xl border border-[#E9E4D5] p-5 mt-4 flex flex-col sm:flex-row items-center gap-5 shadow-sm" data-testid="fpl-seen-ring">
          <div className="relative w-24 h-24 flex-shrink-0">
            <svg viewBox="0 0 100 100" className="w-full h-full -rotate-90">
              <circle cx="50" cy="50" r="40" fill="none" stroke="#EDE9DB" strokeWidth="9" />
              <circle cx="50" cy="50" r="40" fill="none" stroke="#12211A" strokeWidth="9" strokeLinecap="round" strokeDasharray={`${Math.PI * 80 * 0.1} ${Math.PI * 80}`} />
            </svg>
            <div className="absolute inset-0 flex items-center justify-center font-barlow font-black text-[20px] text-[#12211A]">10%</div>
          </div>
          <div className="text-center sm:text-left flex-1">
            <div className="font-barlow font-black text-[18px] text-[#12211A] uppercase">
              You&rsquo;ve only seen <span className="text-[#5C7A00]">10%</span>
            </div>
            <p className="text-[12.5px] text-[#5C6657] mt-0.5">90% of your professional scout analysis is still locked and waiting for you.</p>
          </div>
          <div className="flex gap-2">
            {["SKILLS", "BENCHMARKS", "REPORT", "PLAN"].map((t) => (
              <div key={t} className="flex flex-col items-center gap-1">
                <div className="relative w-12 h-14 rounded-lg overflow-hidden bg-[#0E2A1B]">
                  {poster && <img src={`${ASSET_BASE}${poster}`} alt="" className="w-full h-full object-cover blur-[6px] opacity-60" aria-hidden />}
                  <span className="absolute inset-0 flex items-center justify-center">
                    <span className="w-6 h-6 rounded-full bg-[#12211A] flex items-center justify-center"><Lock className="w-3 h-3 text-white" /></span>
                  </span>
                </div>
                <span className="text-[7.5px] font-extrabold tracking-[0.06em] text-[#8B957F]">{t}</span>
              </div>
            ))}
          </div>
        </div>

        {/* ── Unlock CTA ── */}
        <div className="rounded-[22px] mt-4 p-6 text-center" style={{ background: INKG }} data-testid="fpl-unlock-cta">
          <span className="w-14 h-14 rounded-2xl mx-auto flex items-center justify-center" style={{ background: "rgba(204,255,0,0.12)", border: `1px solid ${LIME}44` }}>
            <Gift className="w-6 h-6" style={{ color: LIME }} />
          </span>
          <h2 className="font-barlow font-black uppercase text-white text-[24px] md:text-[28px] leading-tight mt-3">
            Unlock your <span style={{ color: LIME }}>complete scout report</span> now
          </h2>
          <div className="flex flex-wrap justify-center gap-x-5 gap-y-3 mt-4 max-w-[560px] mx-auto">
            {CTA_FEATURES.map(({ icon: Icon, label }) => (
              <div key={label} className="flex flex-col items-center gap-1 w-[68px]">
                <Icon className="w-4.5 h-4.5 text-white/85" style={{ width: 18, height: 18 }} />
                <span className="text-white/65 text-[8.5px] font-bold leading-tight text-center">{label}</span>
              </div>
            ))}
          </div>
          <button
            type="button"
            onClick={scrollToPackages}
            data-testid="fpl-unlock-btn"
            className="mt-5 inline-flex items-center justify-center gap-2 rounded-full px-10 py-4 font-barlow font-black uppercase tracking-[0.05em] text-[16px] w-full sm:w-auto transition-transform active:scale-[0.98] hover:brightness-95"
            style={{ background: LIME, color: "#12211A", boxShadow: `0 14px 34px -12px ${LIME}66` }}
          >
            <Lock className="w-4 h-4" /> Unlock full report now <ChevronRight className="w-4 h-4" />
          </button>
          <div className="text-[11px] font-bold mt-2.5" style={{ color: LIME }}>
            One-time access · Instant unlock · Secure payment
          </div>
        </div>

        {/* ── Packages (existing tier chooser) ── */}
        <div id="scout-packages" className="mt-6" data-testid="fpl-packages">
          <ReportPaywallTiers isLoggedIn={!!user} onUnlockSingle={onUnlockSingle} />
        </div>

        {/* ── Trust bar ── */}
        <div className="bg-white rounded-2xl border border-[#E9E4D5] px-5 py-4 mt-5 flex flex-wrap items-center justify-center gap-x-6 gap-y-3" data-testid="fpl-trust-bar">
          <span className="flex items-center gap-2 text-[11.5px] font-bold text-[#12211A]">
            <ShieldCheck className="w-4 h-4 text-[#12402A]" /> Secure Stripe Payment
          </span>
          <span className="flex items-center gap-2.5" aria-label="Accepted payment methods">
            <span className="text-[13px] font-black italic text-[#1A1F71] tracking-tight">VISA</span>
            <span className="flex items-center -space-x-1.5" aria-hidden>
              <span className="w-4 h-4 rounded-full bg-[#EB001B]" />
              <span className="w-4 h-4 rounded-full bg-[#F79E1B] opacity-90" />
            </span>
            <span className="text-[12.5px] font-bold text-[#12211A]"> Pay</span>
            <span className="text-[12.5px] font-bold text-[#5C6657]"><span className="text-[#4285F4]">G</span> Pay</span>
          </span>
          <span className="flex items-center gap-2 text-[11.5px] text-[#5C6657]">
            <Users className="w-4 h-4" /> Hundreds of players already improving
          </span>
        </div>
      </div>
    </div>
  );
}
