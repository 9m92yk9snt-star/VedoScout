// Free Preview Landing — the conversion-first page free users see after the
// AI preview finishes (permanent until they unlock). Replaces the old long
// report-style preview. Every visible fact is REAL (video, strengths count,
// tap timestamps); locked values are never invented — they unlock with payment.
import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  Lock, Play, ShieldCheck, Star, TrendingUp, Zap, Target, FileText,
  BarChart3, Map, ClipboardList, Brain, Shuffle, Gift, ChevronRight,
  CheckCircle2, Users, MessageSquare, Download, Camera,
} from "lucide-react";
import { ASSET_BASE } from "@/lib/api";
import { SnapshotAnnot, SNAP_CARD_META } from "@/components/report-v2/snapshots";
import { CinematicIntro } from "@/components/report-v2/cinematic";
import { ProofPlayerSheet } from "@/components/report-v2/proofplayer";
import DreamPricingTiers from "@/components/DreamPricingTiers";
import { DreamPathTeaser } from "@/components/report-v2/dreampath";
import { ScoreMeaningTeaser } from "@/components/report-v2/scoremeaning";
import ShareUnlockModal from "@/components/ShareUnlockModal";

const LIME = "#CCFF00";
const INKG = "#0B1F14";

const MISSING = [
  { icon: Zap, label: "25 Skill Ratings" },
  { icon: Star, label: "Grow Your Game — video-proven lessons" },
  { icon: BarChart3, label: "Benchmarks & Age Comparisons" },
  { icon: Map, label: "Position Analysis" },
  { icon: ClipboardList, label: "Development Plan" },
  { icon: Brain, label: "Mental & Personality Profile" },
  { icon: Shuffle, label: "Playing Style & Comparisons" },
];

const CTA_FEATURES = [
  { icon: FileText, label: "Complete Player Report" },
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

  // The SNAPSHOT card shows the poster frame — captured at the FIRST (marker)
  // anchor's exact second, so image + timestamp + proof video always match.
  const snapMomentT = useMemo(() => {
    const anchors = report.anchors || [];
    const first = anchors[0];
    return first?.t != null ? mmss(first.t) : null;
  }, [report.anchors]);

  // A different real tapped moment for the "Key moment" teaser (variety) —
  // falls back to the snapshot moment when only one anchor exists.
  const keyMomentT = useMemo(() => {
    const anchors = report.anchors || [];
    if (!anchors.length) return null;
    const later = anchors.slice(1);
    const mid = later.length ? later[Math.floor(later.length / 2)] : anchors[0];
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

  // ── Proof mini-player: real video proof for the open moment + key moment,
  //    locked teaser for the 3 locked snapshot cards ──
  const [proof, setProof] = useState(null);
  const openProof = (ts) => {
    try { videoRef.current?.pause(); } catch { /* noop */ }
    setProof({ ts: ts || null, key: Date.now() });
  };
  const openLockedProof = () => setProof({ ts: null, locked: true, key: Date.now() });

  // ── Cinematic intro (free preview variant): potential counts up, ends on
  //    "Unlock the full story". Separate seen-key so the premium intro still
  //    plays after purchase. ──
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
          momentTs={snapMomentT || keyMomentT}
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
            <button
              type="button"
              onClick={() => setShowCine(true)}
              data-testid="cinematic-replay-btn"
              className="inline-flex items-center gap-1.5 bg-[#12211A] rounded-full px-3.5 py-2 text-[10px] font-extrabold tracking-[0.08em] uppercase hover:bg-[#1F4F2F] transition-colors"
              style={{ color: LIME }}
            >
              <Play className="w-3 h-3 fill-current" /> Play intro
            </button>
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
                  {selfPlayer ? "You show real potential — everything you could become is ready to open." : pFirst ? `${pFirst} shows real potential — everything he could become is ready to open.` : "The player shows real potential. The complete evaluation is ready to unlock."}
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
                  {selfPlayer ? "Your full 0-100 potential score is written into your complete evaluation — see what the match says you can become." : pFirst ? `${pFirst}'s full 0-100 potential score is written into his complete evaluation — see what the match says he can become.` : "The full 0-100 potential score is computed with the complete evaluation — unlock to reveal it."}
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
              {selfPlayer ? "There's something special in your game that most players never get to see." : pFirst ? `There's something special in ${pFirst}'s game that most parents never get to see.` : "There's something special in this game that most people miss."}
            </div>
            <p className="text-white/70 text-[13px] mt-1.5">
              ScoutMe Pro Intelligence found {strengths.length || "several"} strengths in {selfPlayer ? "your game" : pFirst ? `${pFirst}'s game` : "this clip"} — one could change everything{selfPlayer ? " for you" : pFirst ? " for him" : ""}. Unlock the full report to see what it is.
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
              <div className="text-[11.5px] font-semibold text-[#12211A] mt-2 leading-snug">{selfPlayer ? "Reveal your biggest strength — the thing you do best" : pFirst ? `Reveal ${pFirst}'s biggest strength — the thing he does best` : "Unlock to reveal your biggest strength"}</div>
            </div>
            <div className="bg-white rounded-2xl border border-[#E9E4D5] p-4 text-center shadow-sm">
              <div className="text-[9.5px] font-extrabold tracking-[0.12em] uppercase text-[#5C6657]">Needs to improve</div>
              <LockedBlur testid="fpl-improve-locked">
                <div className="py-5">
                  <div className="mx-auto w-24 h-4 rounded bg-[#8FA0C9]/60" />
                  <div className="mx-auto w-32 h-3 rounded bg-[#C9C4B4] mt-2" />
                </div>
              </LockedBlur>
              <div className="text-[11.5px] font-semibold text-[#12211A] mt-2 leading-snug">{selfPlayer ? "See where you can grow fastest" : pFirst ? `See where ${pFirst} can grow fastest` : "Unlock to see where you can improve most"}</div>
            </div>
          </div>
        </div>

        {/* ── Snapshot teaser: 1 real moment unlocked, 3 locked (same design as premium) ── */}
        <div className="mt-5 bg-[#F6F3E8] border border-[#E5DFCE] rounded-[22px] p-4 md:p-5" data-testid="fpl-snapshots">
          <div className="flex items-start justify-between flex-wrap gap-3">
            <div className="flex items-start gap-3">
              <span className="w-[44px] h-[44px] rounded-[13px] bg-[#E9F1E6] flex items-center justify-center shrink-0">
                <Camera className="w-5 h-5 text-[#1E5B3C]" />
              </span>
              <div>
                <div className="font-barlow font-black text-[22px] md:text-[26px] leading-none tracking-[0.01em] text-[#101B12] uppercase">Snapshot</div>
                <p className="text-[12.5px] text-[#3C4A40] mt-1">
                  The key moments we found in <span className="text-[#1E5B3C] font-semibold">{selfPlayer ? "your" : pFirst ? `${pFirst}'s` : "the"}</span> match.
                </p>
              </div>
            </div>
            <span className="inline-flex items-center gap-1.5 bg-[#12211A] text-white text-[9.5px] font-extrabold tracking-[0.08em] uppercase px-2.5 py-1 rounded-full" data-testid="fpl-snapshots-count">
              1 of 4 unlocked
            </span>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-4">
            {/* Unlocked card — 100% real: the user's own frame + confirmed strength */}
            <div data-testid="fpl-snapshot-open" className="rounded-[16px] overflow-hidden border border-[#E5DFCE] bg-[#FBFAF2] shadow-[0_3px_14px_rgba(30,50,35,0.08)] flex flex-col">
              <div className="flex items-center gap-2.5 px-4 h-[42px] text-white shrink-0" style={{ background: SNAP_CARD_META.strength.header }}>
                <Star className="w-4 h-4 shrink-0" />
                <span className="text-[11.5px] font-extrabold tracking-[0.07em] uppercase truncate">{SNAP_CARD_META.strength.label}</span>
                {snapMomentT && (
                  <>
                    <span className="ml-auto w-px h-5 bg-white/25 shrink-0" />
                    <span className="font-barlow font-black text-[14px] tabular-nums shrink-0">{snapMomentT}</span>
                  </>
                )}
              </div>
              <div className="relative h-[180px] md:h-[200px] bg-[#0B1F14] shrink-0">
                {poster ? (
                  <img src={`${ASSET_BASE}${poster}`} alt="" className="absolute inset-0 w-full h-full object-cover" aria-hidden />
                ) : (
                  <div className="absolute inset-0" style={{ background: "linear-gradient(160deg,#1B4430,#0B1F14)" }} />
                )}
                <SnapshotAnnot type="path" />
              </div>
              <div className="px-4 py-3.5 flex-1">
                <div className="text-[16px] font-extrabold text-[#12211A] leading-snug" data-testid="fpl-snapshot-open-title">
                  {strengths[0] || "Strongest area of the match"}
                </div>
                <p className="text-[12px] text-[#5C6657] leading-snug mt-1">
                  {selfPlayer ? "A real moment from your match — confirmed by our analysis." : pFirst ? `A real moment from ${pFirst}'s match — confirmed by our analysis.` : "A real moment from the uploaded match — confirmed by our analysis."}
                </p>
                {snapMomentT && (
                  <button
                    type="button"
                    onClick={() => openProof(snapMomentT)}
                    data-testid="fpl-proof-open"
                    className="mt-2.5 inline-flex items-center gap-1.5 bg-[#12402A] text-[#CCFF00] text-[10px] font-extrabold tracking-[0.07em] uppercase px-2.5 py-1 rounded-full active:scale-95 transition-transform"
                  >
                    <Play className="w-2.5 h-2.5 fill-[#CCFF00]" /> See the proof · {snapMomentT}
                  </button>
                )}
              </div>
            </div>
            {/* Locked cards */}
            {[
              { key: "noticed", tease: "What our analysis noticed in one exact moment" },
              { key: "hidden", tease: "A talent most people watching would miss" },
              { key: "develop", tease: "The fastest way to improve — shown on video" },
            ].map(({ key, tease }, i) => {
              const meta = SNAP_CARD_META[key];
              return (
                <div key={key} data-testid={`fpl-snapshot-locked-${i}`} className="rounded-[16px] overflow-hidden border border-[#E5DFCE] bg-[#FBFAF2] shadow-[0_3px_14px_rgba(30,50,35,0.08)] flex flex-col">
                  <div className="flex items-center gap-2.5 px-4 h-[42px] text-white shrink-0" style={{ background: meta.header }}>
                    <meta.Icon className="w-4 h-4 shrink-0" />
                    <span className="text-[11.5px] font-extrabold tracking-[0.07em] uppercase truncate">{meta.label}</span>
                    <span className="ml-auto w-px h-5 bg-white/25 shrink-0" />
                    <Lock className="w-3.5 h-3.5 shrink-0" />
                  </div>
                  <div className="relative h-[180px] md:h-[200px] bg-[#0B1F14] shrink-0">
                    {poster && <img src={`${ASSET_BASE}${poster}`} alt="" className="absolute inset-0 w-full h-full object-cover blur-[9px] scale-110 opacity-60" aria-hidden />}
                    <span className="absolute inset-0 flex items-center justify-center">
                      <span className="w-11 h-11 rounded-full bg-[#12211A] border border-white/20 flex items-center justify-center shadow-lg">
                        <Lock className="w-4 h-4 text-white" />
                      </span>
                    </span>
                  </div>
                  <div className="px-4 py-3.5 flex-1">
                    <div className="text-[14px] font-extrabold text-[#12211A] leading-snug">{tease}</div>
                    <p className="text-[11px] text-[#8B957F] font-extrabold uppercase tracking-[0.08em] mt-1">Unlocks with the full report</p>
                    <button
                      type="button"
                      onClick={openLockedProof}
                      data-testid={`fpl-proof-locked-${i}`}
                      className="mt-2.5 inline-flex items-center gap-1.5 bg-[#EDE9DB] text-[#5C6657] text-[10px] font-extrabold tracking-[0.07em] uppercase px-2.5 py-1 rounded-full active:scale-95 transition-transform hover:bg-[#E3DECB]"
                    >
                      <Lock className="w-2.5 h-2.5" /> See the proof
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
          <button
            type="button"
            onClick={scrollToPackages}
            data-testid="fpl-snapshots-unlock"
            className="mt-4 w-full sm:w-auto inline-flex items-center justify-center gap-2 bg-ink text-white font-black text-[12px] uppercase tracking-wider px-6 py-3 rounded-xl hover:bg-[#1F4F2F] transition-colors"
          >
            Unlock all 4 moments <ChevronRight className="w-4 h-4" />
          </button>
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
                <div className="font-barlow font-black text-[16px] text-[#12211A]">Match Insight Hidden</div>
                <p className="text-[12px] text-[#5C6657] leading-snug mt-1">
                  {selfPlayer ? "See what ScoutMe Pro Intelligence noticed about you in this exact moment." : pFirst ? `See what ScoutMe Pro Intelligence noticed about ${pFirst} in this exact moment.` : "Unlock the full report to see what ScoutMe Pro Intelligence noticed in this moment."}
                </p>
                {keyMomentT && (
                  <div className="flex items-center gap-2 mt-2.5">
                    <span className="inline-block bg-[#F0EDE5] text-[#12211A] text-[11px] font-extrabold px-2.5 py-1 rounded-md" data-testid="fpl-key-moment-t">
                      {keyMomentT}
                    </span>
                    <button
                      type="button"
                      onClick={() => openProof(keyMomentT)}
                      data-testid="fpl-proof-keymoment"
                      className="inline-flex items-center gap-1.5 bg-[#12402A] text-[#CCFF00] text-[10px] font-extrabold tracking-[0.07em] uppercase px-2.5 py-1 rounded-full active:scale-95 transition-transform"
                    >
                      <Play className="w-2.5 h-2.5 fill-[#CCFF00]" /> See the proof
                    </button>
                  </div>
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

        {/* ── Limited discount banner (real, server-enforced deadline) ── */}
        {discount && <DiscountBanner discount={discount} pFirst={pFirst} onCta={scrollToPackages} />}

        {/* ── What the numbers really mean — one open score story (1 of 25) ── */}
        <ScoreMeaningTeaser teaser={report.score_meaning_teaser} playerName={pd.player_name} onUnlock={scrollToPackages} bonusOverride={bonusStory} />

        {/* ── The Path — dream roadmap teaser ── */}
        <DreamPathTeaser playerName={pd.player_name} onUnlock={scrollToPackages} />

        {/* ── The full report, section by section (locked) ── */}
        <div className="bg-white rounded-2xl border border-[#E9E4D5] p-5 mt-4 shadow-sm" data-testid="fpl-locked-sections">
          <p className="text-[10px] font-black uppercase tracking-[0.24em] text-[#5C7A00] mb-1">Locked in {selfPlayer ? "your" : pFirst ? `${pFirst}'s` : "the"} full report</p>
          <h3 className="font-black text-ink text-lg uppercase tracking-tight mb-4">Everything waiting inside — section by section</h3>
          <div className="grid sm:grid-cols-2 gap-x-6 gap-y-2.5">
            {[
              [Zap, "Action timeline — every involvement, timestamped"],
              [Star, "25 skill ratings across 4 categories"],
              [BarChart3, "Level benchmark + realistic next step"],
              [Map, "12-month development roadmap"],
              [ClipboardList, "Weekly training plan with 5 drills"],
              [Brain, "Grow Your Game — video-proven lessons"],
              [Users, "Parents' package: watch-together guide + car-ride tips"],
              [MessageSquare, selfPlayer ? "Personal letter written to you" : "Personal letter written to the player"],
              [Target, "3 printable next-match missions"],
              [FileText, "Coach notes for their trainer"],
            ].map(([Icon, label], i) => (
              <div key={i} className="flex items-center gap-3" data-testid={`fpl-locked-section-${i}`}>
                <span className="w-7 h-7 rounded-lg bg-[#F4F1E8] border border-[#E9E4D5] flex items-center justify-center shrink-0">
                  <Icon className="w-3.5 h-3.5 text-[#5C7A00]" />
                </span>
                <div className="min-w-0 flex-1">
                  <p className="text-[12.5px] font-bold text-ink/85 leading-tight truncate">{label}</p>
                  <div className="mt-1 h-2 rounded bg-gradient-to-r from-ink/15 to-ink/5 blur-[2.5px] select-none" aria-hidden />
                </div>
                <Lock className="w-3.5 h-3.5 text-ink/30 shrink-0" />
              </div>
            ))}
          </div>
          <div className="mt-5 flex flex-col sm:flex-row items-center gap-3">
            <button
              type="button"
              onClick={scrollToPackages}
              data-testid="fpl-locked-sections-unlock"
              className="w-full sm:w-auto inline-flex items-center justify-center gap-2 bg-ink text-white font-black text-[12px] uppercase tracking-wider px-6 py-3.5 rounded-xl hover:bg-[#1F4F2F] transition-colors"
            >
              Unlock the full report <ChevronRight className="w-4 h-4" />
            </button>
            <a
              href="/sample-report"
              target="_blank"
              rel="noopener noreferrer"
              data-testid="fpl-locked-sections-sample"
              className="text-[12px] font-bold text-[#1F4F2F] underline underline-offset-2 hover:text-ink"
            >
              Curious? See a full sample report first
            </a>
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
            <p className="text-[12.5px] text-[#5C6657] mt-0.5">{selfPlayer ? "90% of your story is still locked and waiting for you." : pFirst ? `90% of ${pFirst}'s story is still locked and waiting for you.` : "90% of your ScoutMe Pro analysis is still locked and waiting for you."}</p>
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
            {pFirst ? (
              <>See everything the match revealed about <span style={{ color: LIME }}>{pFirst}</span></>
            ) : (
              <>Unlock your <span style={{ color: LIME }}>complete player report</span> now</>
            )}
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
      {!hasBonus && (
        <button
          type="button"
          onClick={() => setShareOpen(true)}
          data-testid="share-gift-pill"
          className="fixed bottom-4 left-4 z-40 inline-flex items-center gap-2 rounded-full pl-3 pr-4 py-2.5 shadow-xl active:scale-[0.97] transition-transform"
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
