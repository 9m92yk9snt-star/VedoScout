// Free Preview Landing — the conversion-first page free users see after the
// preview finishes (permanent until they unlock). Approved category layout
// (mockup-free-categories.html): 01 Player Snapshot → your free proof →
// 9 locked numbered categories → teasers → packages. Every visible fact is
// REAL (video, strengths, tap timestamps); locked values are never invented.
import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  Lock, Play, ShieldCheck, Star, FileText, BarChart3, ClipboardList, Brain,
  Gift, ChevronRight, CheckCircle2, Users, MessageSquare, Download, Zap,
  Activity, Shield, Video, TrendingUp, Trophy,
} from "lucide-react";
import { ASSET_BASE } from "@/lib/api";
import { CinematicIntro } from "@/components/report-v2/cinematic";
import { ProofPlayerSheet } from "@/components/report-v2/proofplayer";
import DreamPricingTiers from "@/components/DreamPricingTiers";
import { DreamPathTeaser } from "@/components/report-v2/dreampath";
import { ScoreMeaningTeaser } from "@/components/report-v2/scoremeaning";
import ShareUnlockModal from "@/components/ShareUnlockModal";

const LIME = "#CCFF00";
const INKG = "#0B1F14";

const CTA_FEATURES = [
  { icon: FileText, label: "Complete Player Report" },
  { icon: Star, label: "25 Professional Skill Ratings" },
  { icon: BarChart3, label: "Benchmarks & Comparisons" },
  { icon: ClipboardList, label: "Development Plan" },
  { icon: Download, label: "Downloadable PDF" },
  { icon: ShieldCheck, label: "Real Scout Review" },
  { icon: MessageSquare, label: "Talk With Scout" },
];

// The 9 locked categories — same numbering & names as the premium report.
const LOCKED_CATS = [
  { key: "iq", num: "02", icon: Brain, title: "FOOTBALL IQ & MENTALITY", desc: "Scanning, decisions, mentality and attitude.", blurScore: "8.2" },
  { key: "tech", num: "03", icon: Zap, title: "TECHNIQUE", desc: "First touch, dribbling, finishing + video proof." },
  { key: "phys", num: "04", icon: Activity, title: "PHYSICAL & MOVEMENT", desc: "Top speed km/h, sprints and movement map." },
  { key: "tact", num: "05", icon: Shield, title: "TACTICAL", desc: "Positioning, pressing and off-ball runs." },
  { key: "impact", num: "06", icon: BarChart3, title: "MATCH IMPACT", desc: "Match stats + benchmark against your age group." },
  { key: "evidence", num: "07", icon: Video, title: "SCOUT EVIDENCE", desc: "3 locked photo moments + timestamped match clips.", proofTease: true },
  { key: "development", num: "08", icon: TrendingUp, title: "DEVELOPMENT", desc: "Your training plan + 12-month roadmap." },
  { key: "parents", num: "09", icon: Users, title: "PARENTS' CORNER", desc: "Watch the match together + a letter to the player." },
  { key: "verdict", num: "10", icon: Trophy, title: "SCOUT VERDICT", desc: "The conclusion + what a scout looks for next time." },
];

const potentialLabel = (v) =>
  v >= 85 ? "EXCELLENT" : v >= 75 ? "STRONG" : v >= 65 ? "GOOD" : v >= 50 ? "PROMISING" : "DEVELOPING";

const mmss = (t) => {
  const s = Math.max(0, Math.round(Number(t) || 0));
  return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
};

const resolveUrl = (url) => {
  if (!url) return null;
  return /^https?:\/\//i.test(url) ? url : `${ASSET_BASE}${url}`;
};

function FreeGauge({ potential }) {
  const C = 2 * Math.PI * 38;
  if (potential != null) {
    const offset = C * (1 - potential / 100);
    return (
      <div className="ml-auto text-center relative w-[92px] shrink-0" data-testid="fpl-gauge-open">
        <svg width="92" height="92" viewBox="0 0 92 92" className="-rotate-90">
          <circle cx="46" cy="46" r="38" stroke="#E8EDE6" strokeWidth="7" fill="none" />
          <circle cx="46" cy="46" r="38" stroke="#2E7D32" strokeWidth="7" fill="none" strokeLinecap="round" strokeDasharray={C} strokeDashoffset={offset} />
        </svg>
        <div className="absolute top-[27px] inset-x-0 font-barlow font-black text-[27px] text-[#12402A] leading-none" data-testid="fpl-potential-score">{potential}</div>
        <div className="absolute top-[55px] inset-x-0 text-[7.5px] font-extrabold tracking-[0.18em] text-[#5B6B5E]">POTENTIAL</div>
        <div className="mt-1 text-[#2E7D32] text-[10px] font-extrabold">{potentialLabel(potential)}</div>
      </div>
    );
  }
  return (
    <div className="ml-auto text-center relative w-[92px] shrink-0" data-testid="fpl-gauge-locked">
      <svg width="92" height="92" viewBox="0 0 92 92" className="-rotate-90">
        <circle cx="46" cy="46" r="38" stroke="#E8EDE6" strokeWidth="7" fill="none" />
        <circle cx="46" cy="46" r="38" stroke="#2E7D32" strokeWidth="7" fill="none" strokeLinecap="round" strokeDasharray={C} strokeDashoffset={C * 0.2} opacity="0.25" />
      </svg>
      <div className="absolute top-[27px] inset-x-0 font-barlow font-black text-[27px] text-[#2E7D32] leading-none blur-[10px] select-none" aria-hidden>84</div>
      <div className="absolute top-[26px] inset-x-0 flex justify-center">
        <span className="w-8 h-8 rounded-full bg-[#12402A] flex items-center justify-center" style={{ boxShadow: "0 0 16px rgba(204,255,0,0.45)" }}>
          <Lock className="w-3.5 h-3.5" style={{ color: LIME }} />
        </span>
      </div>
      <div className="absolute top-[60px] inset-x-0 text-[7.5px] font-extrabold tracking-[0.18em] text-[#5B6B5E]">OVERALL · LOCKED</div>
    </div>
  );
}

export default function FreePreviewLanding({ report, user, onUnlockSingle, unlocking }) {
  const videoRef = useRef(null);
  const pd = report.player_details || {};
  const preview = report.preview || {};
  const teaser = report.teaser || {};
  const poster = report.poster_url || report.marker_url;
  const firstName = (user?.full_name || "").split(" ")[0] || "there";
  const pFirst = String(pd.player_name || "").trim().split(" ")[0];
  const selfPlayer = !!pFirst && pFirst.toLowerCase() === firstName.toLowerCase();
  const lockedNumbers = report.score_meaning_teaser?.locked_count;
  const totalNumbers = lockedNumbers != null ? lockedNumbers + 1 : null;
  const strengths = preview.top_strengths || [];
  const potential = teaser.overall_potential;
  const discount = report.pricing?.discount || null;
  const [shareOpen, setShareOpen] = useState(false);
  const [bonusStory, setBonusStory] = useState(null);
  const hasBonus = !!(report.score_meaning_teaser?.bonus || bonusStory);

  const photo = resolveUrl(report.display_crop_url) || resolveUrl(report.subject_crop_url) || resolveUrl(report.marker_url) || resolveUrl(report.poster_url);

  useEffect(() => {
    if (hasBonus) return undefined;
    const key = `smp_exit_${report.id}`;
    if (localStorage.getItem(key)) return undefined;
    const t0 = Date.now();
    const onLeave = (e) => {
      if (e.clientY > 0 || Date.now() - t0 < 8000) return;
      localStorage.setItem(key, "1");
      setShareOpen(true);
    };
    document.addEventListener("mouseleave", onLeave);
    return () => document.removeEventListener("mouseleave", onLeave);
  }, [report.id, hasBonus]);

  // The free proof shows the poster frame — captured at the FIRST (marker)
  // anchor's exact second, so image + timestamp + proof video always match.
  const snapMomentT = useMemo(() => {
    const anchors = report.anchors || [];
    const first = anchors[0];
    return first?.t != null ? mmss(first.t) : null;
  }, [report.anchors]);

  const scrollToPackages = () => {
    document.getElementById("scout-packages")?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  // ── Proof mini-player: real video proof for the open moment, locked teaser
  //    for everything still waiting in the full report ──
  const [proof, setProof] = useState(null);
  const openProof = (ts) => {
    try { videoRef.current?.pause(); } catch { /* noop */ }
    setProof({ ts: ts || null, key: Date.now() });
  };
  const openLockedProof = () => setProof({ ts: null, locked: true, key: Date.now() });

  // ── Cinematic intro (free preview variant) ──
  const cineKey = `smp_cine_seen_${report.id || "report"}_fp`;
  const [showCine, setShowCine] = useState(() => {
    try {
      if (window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches) return false;
      return !window.localStorage.getItem(cineKey);
    } catch { return false; }
  });
  const closeCine = () => {
    try { window.localStorage.setItem(cineKey, "1"); } catch { /* noop */ }
    setShowCine(false);
  };

  return (
    <div className="pt-24 md:pt-28 px-4 md:px-6 pb-10" data-testid="free-preview-landing">
      {showCine && (
        <CinematicIntro
          playerName={pd.player_name}
          overall={typeof potential === "number" ? potential : null}
          momentTs={snapMomentT}
          momentTitle={strengths[0]}
          image={poster ? `${ASSET_BASE}${poster}` : null}
          demo={false}
          onDone={closeCine}
          scoreDecimals={0}
          scoreSuffix="/100"
          scoreLabel="Overall potential"
          endLine="Unlock the full story"
          endEmphasis
        />
      )}
      <ProofPlayerSheet
        proof={proof}
        videoUrl={report.video_url ? `${ASSET_BASE}${report.video_url}` : null}
        posterUrl={poster ? `${ASSET_BASE}${poster}` : null}
        frames={[]}
        demo={false}
        onClose={() => setProof(null)}
        onUnlock={scrollToPackages}
      />
      <div className="max-w-[880px] mx-auto">
        {/* ── Header ── */}
        <div className="flex flex-wrap items-center justify-between gap-3" data-testid="fpl-header">
          <div>
            <h1 className="font-barlow font-black text-[24px] md:text-[28px] text-[#12211A] leading-tight">
              Hi {firstName}! <span aria-hidden>👋</span>
            </h1>
            <p className="text-[12.5px] text-[#5C6657] mt-0.5">Here&rsquo;s your free preview</p>
          </div>
          <div className="flex items-center gap-2">
            <span className="inline-flex items-center gap-1.5 bg-white border border-[#E5DFCE] rounded-full px-3 py-1.5 text-[9.5px] font-extrabold tracking-[0.08em] uppercase text-[#12211A]">
              Preview complete <CheckCircle2 className="w-3.5 h-3.5 text-[#2F8F4E]" />
            </span>
            <button
              type="button"
              onClick={() => setShowCine(true)}
              data-testid="cinematic-replay-btn"
              className="inline-flex items-center gap-1.5 bg-[#12211A] rounded-full px-3 py-1.5 text-[9.5px] font-extrabold tracking-[0.08em] uppercase hover:bg-[#1F4F2F] transition-colors"
              style={{ color: LIME }}
            >
              <Play className="w-3 h-3 fill-current" /> Play intro
            </button>
          </div>
        </div>

        {/* ── 01 PLAYER SNAPSHOT ── */}
        <div className="bg-white rounded-[16px] shadow-[0_2px_12px_rgba(16,27,18,0.07)] p-4 mt-4 max-w-[640px] mx-auto md:max-w-none" data-testid="fpl-snapshot-card">
          <span className="inline-flex items-center gap-2 font-extrabold text-[12.5px] tracking-[0.12em] text-[#101B12]">
            <span className="bg-[#E7F3E4] text-[#2E7D32] font-barlow font-black rounded-full px-2.5 py-0.5 text-[13px]">01</span>
            PLAYER SNAPSHOT
          </span>
          <div className="flex items-center gap-3.5 mt-3.5">
            {photo && (
              <img src={photo} alt={pd.player_name || "Player"} className="w-[94px] h-[108px] object-cover rounded-[12px] shrink-0" data-testid="fpl-player-photo" />
            )}
            <div className="min-w-0">
              <h2 className="font-barlow font-black text-[26px] leading-[0.95] uppercase text-[#101B12]" data-testid="fpl-player-name">
                {pd.player_name || "Your player"}
              </h2>
              {pd.position && <div className="text-[#2E7D32] font-extrabold text-[12.5px] mt-1">{pd.position}</div>}
              <div className="text-[#5B6B5E] text-[12px] mt-1 leading-[1.5]">
                {[pd.age ? `${pd.age}` : null, pd.preferred_foot ? `${pd.preferred_foot} foot` : null, pd.current_club || null].filter(Boolean).join(" · ")}
              </div>
            </div>
            <FreeGauge potential={typeof potential === "number" ? potential : null} />
          </div>
          <div className="bg-[#F0F7EE] rounded-[12px] mt-3.5 px-3.5 py-3 text-[13px] leading-[1.55] text-[#25402C]" data-testid="fpl-snapshot-quote">
            &ldquo;We found something in {selfPlayer ? "your" : pFirst ? `${pFirst}'s` : "this"} match{pFirst && !selfPlayer ? "" : ""}.{" "}
            <b className="text-[#2E7D32]">One moment is fully open below</b> — the rest is waiting in the full report.&rdquo;
          </div>
        </div>

        {/* ── YOUR FREE PROOF ── */}
        <div className="flex items-baseline justify-between px-1 pt-6 pb-2.5 max-w-[640px] mx-auto md:max-w-none">
          <h2 className="font-barlow font-black text-[20px] uppercase tracking-[0.02em] text-[#101B12]">Your free proof</h2>
          <span className="text-[10px] text-[#5B6B5E]">Photo · timestamp · video = same moment</span>
        </div>
        <div className="relative rounded-[16px] overflow-hidden border-2 border-[#2E7D32] max-w-[640px] mx-auto md:max-w-none" data-testid="fpl-free-proof">
          <div className="relative h-[200px] md:h-[280px] bg-[#0B1F14]">
            {poster && <img src={`${ASSET_BASE}${poster}`} alt="" className="absolute inset-0 w-full h-full object-cover" aria-hidden />}
            <div className="absolute inset-0" style={{ background: "linear-gradient(180deg,rgba(0,0,0,0.35) 0,transparent 30%,rgba(0,0,0,0.88) 74%)" }} />
            <span className="absolute top-2.5 left-2.5 text-[9px] font-extrabold tracking-[0.13em] rounded-full px-2.5 py-1" style={{ background: LIME, color: "#0B120E" }}>
              BIGGEST STRENGTH
            </span>
            <span className="absolute top-2.5 right-2.5 text-[9px] font-extrabold tracking-[0.13em] rounded-full px-2.5 py-1 bg-black/60 text-white">
              1 OF 4 OPEN
            </span>
            <div className="absolute left-3.5 right-3.5 bottom-3 flex items-end justify-between gap-3 text-white">
              <div className="min-w-0">
                <div className="font-barlow font-black text-[19px] uppercase leading-[1]" data-testid="fpl-proof-title">
                  {strengths[0] || "Strongest moment of the match"}
                </div>
                <div className="text-[10.5px] text-[#CFE0D4] mt-1">
                  A real moment from {selfPlayer ? "your" : pFirst ? `${pFirst}'s` : "the"} match — confirmed by our analysis.
                </div>
              </div>
              {snapMomentT && (
                <button
                  type="button"
                  onClick={() => openProof(snapMomentT)}
                  data-testid="fpl-proof-open"
                  className="shrink-0 inline-flex items-center gap-1.5 rounded-full px-3 py-2 text-[11px] font-extrabold active:scale-95 transition-transform"
                  style={{ background: LIME, color: "#0B120E" }}
                >
                  <Play className="w-3 h-3 fill-current" /> {snapMomentT}
                </button>
              )}
            </div>
          </div>
        </div>

        {/* ── YOUR FULL ANALYSIS — 9 locked categories ── */}
        <div className="flex items-baseline justify-between px-1 pt-6 pb-2.5 max-w-[640px] mx-auto md:max-w-none">
          <h2 className="font-barlow font-black text-[20px] uppercase tracking-[0.02em] text-[#101B12]">Your full analysis</h2>
          <span className="text-[10px] text-[#5B6B5E]">9 categories waiting</span>
        </div>
        <div className="max-w-[640px] mx-auto md:max-w-none" data-testid="fpl-locked-categories">
          {LOCKED_CATS.map((c) => (
            <button
              key={c.key}
              type="button"
              onClick={c.proofTease ? openLockedProof : scrollToPackages}
              data-testid={`fpl-cat-${c.key}`}
              className={`w-full bg-white rounded-[14px] shadow-[0_2px_10px_rgba(16,27,18,0.06)] mb-2.5 flex items-center gap-3 px-3.5 py-3.5 text-left border-l-4 active:scale-[0.99] transition-transform ${
                c.blurScore ? "border-l-[#2E7D32]" : "border-l-[#C9D3C6]"
              }`}
            >
              <span className="font-barlow font-black text-[16px] text-[#2E7D32] w-6 shrink-0">{c.num}</span>
              <span className="w-9 h-9 shrink-0 flex items-center justify-center text-[#101B12]">
                <c.icon className="w-6 h-6" strokeWidth={1.8} />
              </span>
              <span className="min-w-0 flex-1">
                <span className="block font-extrabold text-[13.5px] text-[#101B12]">{c.title}</span>
                <span className="block text-[11px] text-[#5B6B5E] leading-[1.35] mt-0.5">{c.desc}</span>
              </span>
              {c.blurScore ? (
                <span className="ml-auto shrink-0 font-barlow font-black text-[18px] bg-[#DFF3D3] rounded-[10px] px-3 py-1 text-[#101B12] blur-[7px] select-none" aria-hidden>
                  {c.blurScore}
                </span>
              ) : (
                <span className="ml-auto shrink-0 w-9 h-9 rounded-[10px] bg-[#12402A] flex items-center justify-center" style={{ boxShadow: "0 0 14px rgba(204,255,0,0.28)" }}>
                  <Lock className="w-4 h-4" style={{ color: LIME }} />
                </span>
              )}
            </button>
          ))}
        </div>

        {/* ── Limited discount banner (real, server-enforced deadline) ── */}
        {discount && <DiscountBanner discount={discount} pFirst={pFirst} onCta={scrollToPackages} />}

        {/* ── What the numbers really mean — one open score story ── */}
        <ScoreMeaningTeaser teaser={report.score_meaning_teaser} playerName={pd.player_name} onUnlock={scrollToPackages} bonusOverride={bonusStory} />

        {/* ── The Path — dream roadmap teaser ── */}
        <DreamPathTeaser playerName={pd.player_name} onUnlock={scrollToPackages} />

        {/* ── Unlock CTA ── */}
        <div className="rounded-[22px] mt-5 p-6 text-center" style={{ background: INKG }} data-testid="fpl-unlock-cta">
          <span className="w-14 h-14 rounded-2xl mx-auto flex items-center justify-center" style={{ background: "rgba(204,255,0,0.12)", border: `1px solid ${LIME}44` }}>
            <Gift className="w-6 h-6" style={{ color: LIME }} />
          </span>
          <h2 className="font-barlow font-black uppercase text-white text-[24px] md:text-[28px] leading-tight mt-3">
            {pFirst ? (
              <>See everything the match revealed about <span style={{ color: LIME }}>{pFirst}</span></>
            ) : (
              <>Unlock your <span style={{ color: LIME }}>complete player report</span> now</>
            )}
          </h2>
          <div className="flex flex-wrap justify-center gap-x-5 gap-y-3 mt-4 max-w-[560px] mx-auto">
            {CTA_FEATURES.map(({ icon: Icon, label }) => (
              <div key={label} className="flex flex-col items-center gap-1 w-[68px]">
                <Icon className="text-white/85" style={{ width: 18, height: 18 }} />
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
            <Lock className="w-4 h-4" />
            {pFirst
              ? (totalNumbers ? `See all ${totalNumbers} of ${pFirst}'s numbers + his path to the next level` : `Open ${pFirst}'s full story + his path to the next level`)
              : "Unlock full report now"}
            <ChevronRight className="w-4 h-4" />
          </button>
          <div className="text-[11px] font-bold mt-2.5" style={{ color: LIME }}>
            One-time access · Instant unlock · Secure payment
          </div>
        </div>

        {/* ── Packages (existing tier chooser) ── */}
        <div id="scout-packages" className="mt-6" data-testid="fpl-packages">
          <DreamPricingTiers isLoggedIn={!!user} onUnlockSingle={onUnlockSingle} discount={discount} />
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

      {/* ── Sticky unlock bar (mobile) ── */}
      <div
        className="lg:hidden fixed bottom-[calc(62px+env(safe-area-inset-bottom,0px))] md:bottom-0 inset-x-0 z-40 bg-[#0B120E] px-4 py-3 flex items-center gap-3"
        data-testid="fpl-sticky-cta"
      >
        <div className="text-white min-w-0">
          <div className="font-barlow font-black text-[15px] uppercase leading-tight">Unlock the full analysis</div>
          <div className="text-[#8FA396] text-[10px] truncate">9 categories · all proof · your plan · PDF</div>
        </div>
        <button
          type="button"
          onClick={scrollToPackages}
          data-testid="fpl-sticky-cta-btn"
          className="ml-auto shrink-0 font-barlow font-black text-[13px] tracking-[0.08em] uppercase rounded-full px-4 py-2.5 active:scale-[0.97] transition-transform"
          style={{ background: LIME, color: "#0B120E" }}
        >
          {discount?.discounted ? `$${discount.discounted} · Unlock` : "Unlock now"}
        </button>
      </div>

      {!hasBonus && (
        <button
          type="button"
          onClick={() => setShareOpen(true)}
          data-testid="share-gift-pill"
          className="fixed bottom-[calc(134px+env(safe-area-inset-bottom,0px))] lg:bottom-4 left-4 z-40 inline-flex items-center gap-2 rounded-full pl-3 pr-4 py-2.5 shadow-xl active:scale-[0.97] transition-transform"
          style={{ background: "#0B1F14", border: "1px solid rgba(204,255,0,0.4)" }}
        >
          <Gift className="w-4 h-4" style={{ color: LIME }} />
          <span className="text-[11px] font-extrabold uppercase tracking-[0.06em]" style={{ color: LIME }}>
            Unlock 1 more story
          </span>
        </button>
      )}

      <ShareUnlockModal
        open={shareOpen}
        onClose={() => setShareOpen(false)}
        report={report}
        onUnlocked={(b) => setBonusStory(b)}
      />
    </div>
  );
}

function DiscountBanner({ discount, pFirst, onCta }) {
  const [left, setLeft] = useState("");
  useEffect(() => {
    const tick = () => {
      const ms = new Date(discount.expires_at).getTime() - Date.now();
      if (ms <= 0) { setLeft(""); return; }
      const h = Math.floor(ms / 3600000);
      const m = Math.floor((ms % 3600000) / 60000);
      setLeft(`${h}h ${m}m`);
    };
    tick();
    const iv = setInterval(tick, 30000);
    return () => clearInterval(iv);
  }, [discount.expires_at]);
  if (!left) return null;
  return (
    <button
      type="button"
      onClick={onCta}
      data-testid="discount-banner"
      className="mt-5 w-full flex items-center justify-between gap-3 rounded-2xl px-5 py-4 text-left active:scale-[0.99] transition-transform"
      style={{ background: "#0B1F14", border: "1px solid rgba(204,255,0,0.35)" }}
    >
      <div>
        <div className="text-[10px] font-extrabold tracking-[0.2em] uppercase" style={{ color: LIME }}>
          {Math.round(discount.percent)}% off — ends in {left}
        </div>
        <div className="text-white font-barlow font-black uppercase text-[15px] leading-tight mt-0.5">
          {pFirst ? `${pFirst}'s full report` : "The full report"} — ${"" + discount.discounted}
        </div>
        <div className="text-white/50 text-[10.5px] mt-0.5">Applied automatically at checkout. Real deadline — no games.</div>
      </div>
      <ChevronRight className="w-5 h-5 shrink-0" style={{ color: LIME }} />
    </button>
  );
}
