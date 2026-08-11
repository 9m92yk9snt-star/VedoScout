// Premium mobile category layout — the approved "01–10 numbered categories"
// structure (mockup-premium-categories.html). Mobile/tablet (<lg) only; the
// desktop grid layout in PremiumReportV2 stays untouched. All values come
// from the same derive.js data — pure reorganisation, no new logic.
import React, { useEffect, useRef, useState } from "react";
import {
  Brain, Zap, Activity, Shield, BarChart3, Video, TrendingUp, Users, Trophy,
  ChevronDown, Heart, Play, Clapperboard, Loader2, Download, ShieldCheck,
  Star, Target, Sparkles, FileText,
} from "lucide-react";
import { SKILL_LABELS } from "./derive";
import {
  MatchStatsCard, AgeComparisonCard, TopStrengthsCard, DevPrioritiesCard,
  RoadmapCard, TrainingPlanCard, ParentTipsCard, VideoHighlightCard,
  CoachNotesCard, ScoutOutlookCard, ActionTimelineCard,
} from "./sections";
import { SnapshotsSection } from "./snapshots";
import { MovementMapCard } from "./movement";
import { PaceCard } from "./pace";
import { ParentValueMetricsCard } from "./parentmetrics";
import { ParentsPackageSection } from "./parents";
import { GrowYourGameSection } from "./growyourgame";
import { ParentCornerSection } from "./parentcorner";
import { DreamPathSection } from "./dreampath";
import { ProgressCard, ProgressTeaser } from "./progress";
import { MissionsCard } from "./missions";
import { ScoreGuideCard } from "./scoreguide";
import { SkillMeaningCard, PositionDiscoveryCard } from "./scoremeaning";

const IQ_TACTICAL = new Set(["scanning", "decision_making", "game_understanding"]);

const bucketOf = (category, key) => {
  if (category === "mentality") return "iq";
  if (category === "technical") return "tech";
  if (category === "physical") return "phys";
  return IQ_TACTICAL.has(key) ? "iq" : "tact";
};

function collectBuckets(full) {
  const out = { iq: [], tech: [], phys: [], tact: [] };
  for (const cat of ["technical", "tactical", "physical", "mentality"]) {
    const sec = full?.[cat] || {};
    for (const [key, sk] of Object.entries(sec)) {
      if (!sk || typeof sk !== "object" || sk.cannot_evaluate || typeof sk.score !== "number") continue;
      out[bucketOf(cat, key)].push({ key, label: SKILL_LABELS[key] || key.replace(/_/g, " "), score: sk.score });
    }
  }
  return out;
}

const avgScore = (arr) => (arr.length ? arr.reduce((s, x) => s + x.score, 0) / arr.length : null);

function SkillBarRow({ label, score }) {
  return (
    <div className="flex items-center gap-2.5 py-1.5">
      <span className="text-[13px] font-medium text-[#1C2B21] flex-1 min-w-0 truncate">{label}</span>
      <span className="w-[100px] h-[6px] rounded-full bg-[#EDF0EA] relative overflow-hidden shrink-0">
        <span
          className="absolute inset-y-0 left-0 rounded-full"
          style={{ width: `${Math.min(100, score * 10)}%`, background: "linear-gradient(90deg,#7BC96A,#2E7D32)" }}
        />
      </span>
      <b className="font-barlow font-black text-[16px] text-[#1E5B3C] w-8 text-right shrink-0">{Number(score).toFixed(1)}</b>
    </div>
  );
}

function Chip({ chip }) {
  if (!chip) return null;
  if (chip.type === "score") {
    const amber = chip.value < 7;
    return (
      <span
        className={`ml-auto shrink-0 font-barlow font-black text-[18px] rounded-[10px] px-3 py-1 ${amber ? "bg-[#FBEBC2] text-[#7A5A10]" : "bg-[#DFF3D3] text-[#12402A]"}`}
      >
        {Number(chip.value).toFixed(1)}
      </span>
    );
  }
  if (chip.type === "count") {
    const Icon = chip.icon || FileText;
    return (
      <span className="ml-auto shrink-0 inline-flex items-center gap-1.5 bg-[#EEF1EC] text-[#3C4A40] text-[11px] font-extrabold rounded-[10px] px-2.5 py-2">
        <Icon className="w-3.5 h-3.5" /> {chip.value}
      </span>
    );
  }
  if (chip.type === "heart") {
    return (
      <span className="ml-auto shrink-0 w-9 h-9 rounded-[10px] bg-[#EEF1EC] flex items-center justify-center">
        <Heart className="w-4 h-4 text-[#1E5B3C] fill-[#1E5B3C]" />
      </span>
    );
  }
  return null;
}

function CatRow({ num, icon: Icon, title, desc, chip, open, onToggle, children, testid }) {
  return (
    <div
      className={`bg-white rounded-[14px] shadow-[0_2px_10px_rgba(16,27,18,0.06)] mb-2.5 overflow-hidden border-l-4 ${
        chip?.type === "score" && chip.value < 7 ? "border-l-[#F5B82E]" : "border-l-[#2E7D32]"
      }`}
      data-testid={testid}
    >
      <button
        type="button"
        onClick={onToggle}
        data-testid={`${testid}-toggle`}
        className="w-full flex items-center gap-3 px-3.5 py-3.5 text-left"
      >
        <span className="font-barlow font-black text-[16px] text-[#2E7D32] w-6 shrink-0">{num}</span>
        <span className="w-9 h-9 shrink-0 flex items-center justify-center text-[#101B12]">
          <Icon className="w-6 h-6" strokeWidth={1.8} />
        </span>
        <span className="min-w-0 flex-1">
          <span className="block font-extrabold text-[14px] tracking-[0.02em] text-[#101B12]">{title}</span>
          <span className="block text-[11.5px] text-[#5B6B5E] leading-[1.35] mt-0.5">{desc}</span>
        </span>
        <Chip chip={chip} />
        <ChevronDown className={`w-4 h-4 text-[#9AA99D] shrink-0 transition-transform ${open ? "rotate-180" : ""}`} />
      </button>
      {open && <div className="border-t border-[#EDF0EA] px-3 py-3.5 space-y-3.5 bg-[#FBFAF5]" data-testid={`${testid}-body`}>{children}</div>}
    </div>
  );
}

function MobileGauge({ overall, ctx }) {
  const C = 2 * Math.PI * 38;
  const offset = overall != null ? C * (1 - overall / 10) : C;
  return (
    <div className="ml-auto text-center relative w-[92px] shrink-0">
      <svg width="92" height="92" viewBox="0 0 92 92" className="-rotate-90">
        <circle cx="46" cy="46" r="38" stroke="#E8EDE6" strokeWidth="7" fill="none" />
        <circle
          cx="46" cy="46" r="38" stroke="#2E7D32" strokeWidth="7" fill="none"
          strokeLinecap="round" strokeDasharray={C} strokeDashoffset={offset}
        />
      </svg>
      <div className="absolute top-[26px] inset-x-0 font-barlow font-black text-[28px] text-[#101B12] leading-none" data-testid="pm-overall-score">
        {overall != null ? Number(overall).toFixed(1) : "—"}
      </div>
      <div className="absolute top-[56px] inset-x-0 text-[7.5px] font-extrabold tracking-[0.18em] text-[#5B6B5E]">OVERALL</div>
      {ctx?.level && (
        <div className="mt-1 text-[#2E7D32] text-[10px] font-extrabold flex items-center justify-center gap-1">
          <TrendingUp className="w-3 h-3" /> {ctx.level}
        </div>
      )}
    </div>
  );
}

function SnapshotHero({ report, d, pd, photoCandidates, reportDate, onReplayIntro, onShareClip, clipBusy }) {
  const [imgIdx, setImgIdx] = useState(0);
  const [summaryOpen, setSummaryOpen] = useState(false);
  const photo = photoCandidates[imgIdx];
  const ps = d.parentSummary || {};
  const quad = [
    { icon: Star, k: "TOP STRENGTH", v: d.snapshot?.biggestStrength },
    { icon: TrendingUp, k: "GROWTH AREA", v: d.snapshot?.developmentArea },
    { icon: Target, k: "PLAYER TYPE", v: d.playerType },
    { icon: Sparkles, k: "HIDDEN TALENT", v: d.snapshot?.hiddenTalent },
  ].filter((q) => q.v && q.v !== "—");
  const cv = d.crossVerification;
  const showVerified = (report.verification?.anchors || 0) > 0 || cv;
  return (
    <div className="bg-white rounded-[16px] shadow-[0_2px_12px_rgba(16,27,18,0.07)] overflow-hidden p-4" data-testid="pm-snapshot-card">
      <div className="flex items-center justify-between">
        <span className="inline-flex items-center gap-2 font-extrabold text-[12.5px] tracking-[0.12em] text-[#101B12]">
          <span className="bg-[#E7F3E4] text-[#2E7D32] font-barlow font-black rounded-full px-2.5 py-0.5 text-[13px]">01</span>
          PLAYER SNAPSHOT
        </span>
        {reportDate && <span className="text-[9.5px] font-bold tracking-[0.1em] text-[#8B957F]">{reportDate}</span>}
      </div>
      <div className="flex gap-3.5 mt-3.5">
        {photo && (
          <img
            src={photo}
            alt={pd.player_name}
            data-testid="pm-player-photo"
            className="w-[100px] h-[116px] object-cover rounded-[12px] shrink-0"
            onError={() => setImgIdx((i) => i + 1)}
          />
        )}
        <div className="min-w-0">
          <h1 className="font-barlow font-black text-[28px] leading-[0.95] uppercase text-[#101B12]" data-testid="pm-player-name">
            {pd.player_name}
          </h1>
          <div className="text-[#2E7D32] font-extrabold text-[13px] mt-1">{pd.position}</div>
          <div className="text-[#5B6B5E] text-[12px] mt-1 leading-[1.55]">
            {[pd.age ? `${pd.age}` : null, pd.preferred_foot ? `${pd.preferred_foot} foot` : null].filter(Boolean).join(" · ")}
            {pd.current_club ? <><br />{pd.current_club}</> : null}
          </div>
        </div>
        <MobileGauge overall={d.overall} ctx={report.score_context?.overall} />
      </div>
      {quad.length > 0 && (
        <div className="grid grid-cols-2 border-t border-[#EDF0EA] mt-4">
          {quad.map((q, i) => (
            <div key={q.k} className={`px-2.5 py-3 text-center border-b border-[#EDF0EA] ${i % 2 === 0 ? "border-r" : ""}`}>
              <div className="flex items-center justify-center gap-1 text-[8.5px] font-extrabold tracking-[0.12em] text-[#5B6B5E]">
                <q.icon className="w-3 h-3" /> {q.k}
              </div>
              <div className="font-bold text-[13px] text-[#101B12] mt-1 leading-snug">{q.v}</div>
            </div>
          ))}
        </div>
      )}
      {ps.headline && (
        <div className="bg-[#F0F7EE] rounded-[12px] mt-3.5 px-3.5 py-3 text-[13px] leading-[1.55] text-[#25402C]">
          <span className="text-[#2E7D32] text-[26px] leading-[0.6] mr-1.5" style={{ fontFamily: "Georgia, serif" }}>&ldquo;</span>
          {ps.headline}
          <button
            type="button"
            onClick={() => setSummaryOpen((o) => !o)}
            data-testid="pm-summary-toggle"
            className="block mt-1.5 text-[#1E5B3C] font-extrabold text-[12px]"
          >
            {summaryOpen ? "Hide the scout's first impression ↑" : "Read the scout's first impression →"}
          </button>
          {summaryOpen && (
            <div className="mt-2 space-y-2" data-testid="pm-summary-body">
              {(ps.paragraphs || []).map((p, i) => (
                <p key={i} className="text-[12.5px] leading-[1.6] text-[#3C4A40]">{p}</p>
              ))}
              {ps.goodNews && (
                <p className="text-[12.5px] leading-[1.55] text-[#12402A] font-semibold">
                  The good news: {ps.goodNews}
                </p>
              )}
            </div>
          )}
        </div>
      )}
      {showVerified && (
        <div className="flex items-center justify-center gap-1.5 text-[9.5px] font-extrabold tracking-[0.13em] text-[#2E7D32] mt-3" data-testid="pm-verified-line">
          <ShieldCheck className="w-3.5 h-3.5" />
          SCOUT CERTIFIED · IDENTITY VERIFIED{cv ? ` · ${cv.checked} MOMENTS RE-CHECKED` : ""}
        </div>
      )}
      <div className="flex items-center justify-center gap-5 mt-3 pt-3 border-t border-[#EDF0EA]">
        {onReplayIntro && (
          <button
            type="button"
            onClick={onReplayIntro}
            data-testid="pm-replay-intro-btn"
            className="inline-flex items-center gap-1.5 text-[10px] font-extrabold tracking-[0.1em] uppercase text-[#1E5B3C]"
          >
            <Play className="w-3 h-3 fill-current" /> Play intro
          </button>
        )}
        {onShareClip && (
          <button
            type="button"
            onClick={onShareClip}
            disabled={clipBusy}
            data-testid="pm-share-clip-btn"
            className="inline-flex items-center gap-1.5 text-[10px] font-extrabold tracking-[0.1em] uppercase text-[#1E5B3C] disabled:opacity-60"
          >
            {clipBusy ? <Loader2 className="w-3 h-3 animate-spin" /> : <Clapperboard className="w-3 h-3" />}
            {clipBusy ? "Creating clip…" : "Share intro clip"}
          </button>
        )}
      </div>
    </div>
  );
}

const TABS = [
  { key: "analysis", label: "ANALYSIS", icon: BarChart3 },
  { key: "evidence", label: "EVIDENCE", icon: Video },
  { key: "development", label: "DEVELOPMENT", icon: TrendingUp },
  { key: "parents", label: "PARENTS", icon: Users },
  { key: "verdict", label: "VERDICT", icon: Trophy },
];

export function PremiumMobileCategories({
  report, d, pd, photoCandidates, topStrengths, snapshotMoments, videoHighlight,
  videoUrl, posterUrl, videoRef, playAt, reportDate, onReplayIntro, onShareClip,
  clipBusy, onDownloadPdf, downloadingPdf, fallbackThumb,
}) {
  const full = report.full_report || {};
  const buckets = collectBuckets(full);
  const smSkills = report.score_meaning?.skills || [];
  const smFor = (bucket) => smSkills.filter((s) => bucketOf(s.category, s.key) === bucket);
  const [openKey, setOpenKey] = useState(null);
  const rowRefs = useRef({});

  // The tabs stick right below whatever top bar the page has (main nav on the
  // report page, sample banner on /sample-report). Measured live because the
  // nav shrinks slightly on scroll.
  const [stickyTop, setStickyTop] = useState(56);
  useEffect(() => {
    const measure = () => {
      const bar = document.querySelector('[data-testid="demo-report-banner"]')
        || document.querySelector('[data-testid="main-nav"]');
      if (bar) setStickyTop(Math.round(bar.getBoundingClientRect().height));
    };
    measure();
    window.addEventListener("scroll", measure, { passive: true });
    window.addEventListener("resize", measure);
    return () => {
      window.removeEventListener("scroll", measure);
      window.removeEventListener("resize", measure);
    };
  }, []);

  const skillBody = (bucket) => {
    const rich = smFor(bucket);
    if (rich.length) {
      return rich.map((s) => (
        <SkillMeaningCard key={s.key} s={s} position={pd.position} onPlayAt={playAt} />
      ));
    }
    return (
      <div className="bg-white rounded-[12px] px-3.5 py-2 border border-[#EDF0EA]">
        {buckets[bucket].map((s) => <SkillBarRow key={s.key} label={s.label} score={s.score} />)}
      </div>
    );
  };

  const evidenceCount =
    snapshotMoments.filter((m) => m.thumb).length + (d.actionTimeline?.length || 0) + (videoHighlight ? 1 : 0);

  const cats = [
    {
      key: "iq", icon: Brain, title: "FOOTBALL IQ & MENTALITY",
      desc: "Scanning, decisions, mentality and attitude.",
      chip: avgScore(buckets.iq) != null ? { type: "score", value: avgScore(buckets.iq) } : null,
      has: buckets.iq.length > 0 || smFor("iq").length > 0,
      body: () => skillBody("iq"),
    },
    {
      key: "tech", icon: Zap, title: "TECHNIQUE",
      desc: "First touch, passing, dribbling, finishing.",
      chip: avgScore(buckets.tech) != null ? { type: "score", value: avgScore(buckets.tech) } : null,
      has: buckets.tech.length > 0 || smFor("tech").length > 0,
      body: () => skillBody("tech"),
    },
    {
      key: "phys", icon: Activity, title: "PHYSICAL & MOVEMENT",
      desc: "Top speed, sprints, movement map and running patterns.",
      chip: avgScore(buckets.phys) != null ? { type: "score", value: avgScore(buckets.phys) } : null,
      has: buckets.phys.length > 0 || report.movement_map?.trail?.length > 0 || !!report.pace_metrics?.top_speed_kmh,
      body: () => (
        <>
          {(smFor("phys").length > 0 || buckets.phys.length > 0) && skillBody("phys")}
          {report.movement_map?.trail?.length > 0 && (
            <MovementMapCard movement={report.movement_map} pace={report.pace_metrics} onPlayAt={playAt} />
          )}
          {report.pace_metrics?.top_speed_kmh && <PaceCard pace={report.pace_metrics} onPlayAt={playAt} />}
        </>
      ),
    },
    {
      key: "tact", icon: Shield, title: "TACTICAL",
      desc: "Positioning, pressing and off-ball runs.",
      chip: avgScore(buckets.tact) != null ? { type: "score", value: avgScore(buckets.tact) } : null,
      has: buckets.tact.length > 0 || smFor("tact").length > 0,
      body: () => skillBody("tact"),
    },
    {
      key: "impact", icon: BarChart3, title: "MATCH IMPACT",
      desc: "Match statistics, influence and age benchmark.",
      chip: d.matchStats?.length ? { type: "count", value: d.matchStats.length, icon: BarChart3 } : null,
      has: !!d.matchStats || d.ageComparison?.length > 0 || report.progression?.categories?.length > 0,
      body: () => (
        <>
          <MatchStatsCard matchStats={d.matchStats} />
          <AgeComparisonCard ageComparison={d.ageComparison} ageBracket={d.ageBracket} />
          {report.progression?.categories?.length > 0 ? (
            <ProgressCard prog={report.progression} />
          ) : (
            !report.demo && <ProgressTeaser playerName={pd.player_name} />
          )}
        </>
      ),
    },
    {
      key: "evidence", icon: Video, title: "SCOUT EVIDENCE",
      desc: "Every photo moment and video clip behind the ratings.",
      chip: evidenceCount > 0 ? { type: "count", value: evidenceCount, icon: Video } : null,
      has: true,
      body: () => (
        <>
          {d.identityNote && (
            <div className="flex items-start gap-2 text-[11.5px] text-[#8A6D3B] bg-[#FFF8E9] border border-[#F0E3C4] rounded-[10px] px-3.5 py-2.5 leading-[1.5]">
              <ShieldCheck className="w-3.5 h-3.5 mt-0.5 shrink-0" />
              <span>{d.identityNote}</span>
            </div>
          )}
          <SnapshotsSection
            snapshot={d.snapshot}
            moments={snapshotMoments}
            demo={!!report.demo}
            playerName={pd.player_name}
            reportId={report.id}
          />
          <TopStrengthsCard topStrengths={topStrengths} onPlayAt={playAt} fallbackThumb={fallbackThumb} />
          {d.actionTimeline?.length > 0 && <ActionTimelineCard actions={d.actionTimeline} onPlayAt={playAt} />}
          <VideoHighlightCard videoHighlight={videoHighlight} videoUrl={videoUrl} posterUrl={posterUrl} videoRef={videoRef} />
        </>
      ),
    },
    {
      key: "development", icon: TrendingUp, title: "DEVELOPMENT",
      desc: "Your plan: priorities, weekly plan, 12-month roadmap, missions.",
      chip: { type: "count", value: 4, icon: FileText },
      has: true,
      body: () => (
        <>
          <DevPrioritiesCard devPriorities={d.devPriorities} />
          <RoadmapCard roadmap={d.roadmap} />
          <TrainingPlanCard trainingWeek={d.trainingWeek} />
          {d.missions?.length > 0 && <MissionsCard missions={d.missions} />}
          {d.growYourGame && <GrowYourGameSection gyg={d.growYourGame} playerName={pd.player_name} onPlayAt={playAt} />}
          <DreamPathSection report={report} d={d} playerName={pd.player_name} />
        </>
      ),
    },
    {
      key: "parents", icon: Users, title: "PARENTS' CORNER",
      desc: "Watch the match together, letter to the player, home drills.",
      chip: { type: "heart" },
      has: true,
      body: () => (
        <>
          <ParentTipsCard parentTips={d.parentTips} />
          {d.parentMetrics && <ParentValueMetricsCard metrics={d.parentMetrics} onPlayAt={playAt} />}
          {(d.parentCorner || pd.age) && (
            <ParentCornerSection parentCorner={d.parentCorner} playerName={pd.player_name} playerAge={pd.age} />
          )}
          {d.parentsPackage && (
            <ParentsPackageSection pack={d.parentsPackage} playerName={pd.player_name} onPlayAt={playAt} />
          )}
        </>
      ),
    },
    {
      key: "verdict", icon: Trophy, title: "SCOUT VERDICT",
      desc: "The conclusion, coach notes and what a scout looks for next.",
      chip: null,
      has: true,
      body: () => (
        <>
          <CoachNotesCard coachNotes={d.coachNotes} />
          <ScoutOutlookCard scoutOutlook={d.scoutOutlook} />
          {report.score_meaning?.discovery && (
            <PositionDiscoveryCard
              discovery={report.score_meaning.discovery}
              playerName={pd.player_name}
              currentPosition={report.score_meaning.position}
            />
          )}
          {!smSkills.length && report.score_context?.overall && <ScoreGuideCard sctx={report.score_context} />}
        </>
      ),
    },
  ].filter((c) => c.has);

  const firstSkillCat = cats.find((c) => ["iq", "tech", "phys", "tact"].includes(c.key))?.key || cats[0]?.key;
  const tabTarget = { analysis: firstSkillCat, evidence: "evidence", development: "development", parents: "parents", verdict: "verdict" };

  const jumpTo = (tabKey) => {
    const target = tabTarget[tabKey];
    if (!target) return;
    setOpenKey(target);
    setTimeout(() => rowRefs.current[target]?.scrollIntoView({ behavior: "smooth", block: "start" }), 60);
  };

  const activeTab = TABS.find((t) => tabTarget[t.key] === openKey)?.key
    || (["iq", "tech", "phys", "tact", "impact"].includes(openKey) ? "analysis" : null);

  return (
    <div data-testid="premium-mobile-categories">
      {/* sticky category tabs */}
      <div
        className="sticky z-30 -mx-4 px-2 bg-[#0B120E] flex gap-1 overflow-x-auto pt-1.5"
        style={{ scrollbarWidth: "none", top: stickyTop }}
        data-testid="pm-tabs"
      >
        {TABS.map((t) => {
          const on = activeTab === t.key;
          return (
            <button
              key={t.key}
              type="button"
              onClick={() => jumpTo(t.key)}
              data-testid={`pm-tab-${t.key}`}
              className={`shrink-0 flex flex-col items-center gap-1 text-[9.5px] font-extrabold tracking-[0.1em] px-3 pt-2 pb-2.5 rounded-t-[10px] transition-colors ${
                on ? "text-[#CCFF00] bg-[#1C2B20] border border-b-0 border-[#CCFF00]/25" : "text-[#9FB2A4]"
              }`}
            >
              <t.icon className="w-[15px] h-[15px]" />
              {t.label}
            </button>
          );
        })}
      </div>

      <div className="pt-3">
        <SnapshotHero
          report={report} d={d} pd={pd}
          photoCandidates={photoCandidates}
          reportDate={reportDate}
          onReplayIntro={onReplayIntro}
          onShareClip={onShareClip}
          clipBusy={clipBusy}
        />

        <div className="flex items-baseline justify-between px-1 pt-5 pb-2.5">
          <h2 className="font-barlow font-black text-[20px] uppercase tracking-[0.02em] text-[#101B12]">Analysis categories</h2>
          <span className="text-[10px] text-[#5B6B5E]">Open one section at a time</span>
        </div>

        {cats.map((c, i) => (
          <div key={c.key} ref={(el) => { rowRefs.current[c.key] = el; }} style={{ scrollMarginTop: stickyTop + 58 }}>
            <CatRow
              num={String(i + 2).padStart(2, "0")}
              icon={c.icon}
              title={c.title}
              desc={c.desc}
              chip={c.chip}
              open={openKey === c.key}
              onToggle={() => setOpenKey(openKey === c.key ? null : c.key)}
              testid={`pm-cat-${c.key}`}
            >
              {openKey === c.key && c.body()}
            </CatRow>
          </div>
        ))}
      </div>

      {onDownloadPdf && (
        <div
          className="sticky bottom-[calc(62px+env(safe-area-inset-bottom,0px))] md:bottom-0 z-30 -mx-4 mt-4 bg-[#0B120E] px-4 py-3 flex items-center gap-3"
          data-testid="pm-pdf-bar"
        >
          <div className="text-white min-w-0">
            <div className="font-barlow font-black text-[15px] uppercase leading-tight">Download full scout report</div>
            <div className="text-[#8FA396] text-[10px]">PDF · analysis · proof · development plan</div>
          </div>
          <button
            type="button"
            onClick={onDownloadPdf}
            disabled={downloadingPdf}
            data-testid="pm-pdf-btn"
            className="ml-auto shrink-0 inline-flex items-center gap-1.5 bg-[#CCFF00] text-[#0B120E] font-barlow font-black text-[13px] tracking-[0.08em] uppercase rounded-full px-4 py-2.5 disabled:opacity-60 active:scale-[0.97] transition-transform"
          >
            {downloadingPdf ? <Loader2 className="w-4 h-4 animate-spin" /> : <Download className="w-4 h-4" />}
            PDF
          </button>
        </div>
      )}
    </div>
  );
}
