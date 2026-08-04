// Premium Report V2 — pixel-perfect implementation of the approved reference
// design (see /public/mockup-report.html for the spec mockup). Pure presentation:
// all values come from the existing full_report analysis via derive.js.

import React, { useRef, useState, useCallback } from "react";
import { Star, Users, ShieldCheck } from "lucide-react";
import { deriveV2, tsToSeconds } from "./derive";
import {
  V2Card, V2Title, SnapshotCard, MatchStatsCard, AgeComparisonCard,
  TopStrengthsCard, DevPrioritiesCard, RoadmapCard, TrainingPlanCard,
  ParentTipsCard, VideoHighlightCard, CoachNotesCard, ScoutOutlookCard,
  ActionTimelineCard,
} from "./sections";
import { MovementMapCard } from "./movement";
import { PaceCard } from "./pace";
import { VerifiedIdentityStrip } from "./verification";
import { ParentValueMetricsCard } from "./parentmetrics";
import { ParentsPackageSection } from "./parents";
import { GrowYourGameSection } from "./growyourgame";
import { ParentCornerSection } from "./parentcorner";
import { DreamPathSection } from "./dreampath";
import { ProgressCard, ProgressTeaser } from "./progress";
import { MissionsCard } from "./missions";
import { ScoreGuideCard } from "./scoreguide";
import { ScoreMeaningSection } from "./scoremeaning";

const resolveUrl = (url, base) => {
  if (!url) return null;
  return /^https?:\/\//i.test(url) ? url : `${base || ""}${url}`;
};

const fmtDate = (iso) => {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleDateString("en-GB", { day: "2-digit", month: "long", year: "numeric" }).toUpperCase();
  } catch { return ""; }
};

function V2PageHeader({ reportDate }) {
  return (
    <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 mb-5">
      {/* Wordmark only — no logo mark per spec */}
      <div>
        <div className="font-barlow font-black text-[26px] tracking-[0.03em] text-[#12402A] leading-none">
          SCOUT<span className="text-[#7BA05B]">ME</span>PLAY
        </div>
        <div className="text-[10px] tracking-[0.24em] font-bold text-[#8B957F] uppercase mt-1">ScoutMe Pro Intelligence</div>
      </div>
      <div className="text-center">
        <h1 className="font-barlow font-black text-[26px] md:text-[30px] tracking-[0.04em] text-[#101B12] leading-none">PREMIUM PLAYER REPORT</h1>
        <div className="inline-block bg-[#12402A] text-[#F0EAD8] text-[10px] font-bold tracking-[0.22em] px-4 py-1 rounded mt-1.5">
          INDEPENDENT&nbsp;&nbsp;·&nbsp;&nbsp;EVIDENCE-BASED
        </div>
      </div>
      <div className="md:text-right">
        <div className="text-[11px] tracking-[0.14em] font-bold text-[#8B957F] uppercase">Report Date</div>
        <div className="text-[14px] font-extrabold mt-0.5" data-testid="v2-report-date">{reportDate}</div>
      </div>
    </div>
  );
}

function HeroPhoto({ candidates, alt }) {
  const [idx, setIdx] = useState(0);
  const src = candidates[idx];
  if (!src) return null;
  return (
    <img
      src={src}
      alt={alt}
      data-testid="v2-player-photo"
      className="w-full h-full object-cover"
      onError={() => setIdx((i) => i + 1)}
      onLoad={(e) => {
        const im = e.currentTarget;
        // Degenerate crops (tiny or extreme slivers) can't carry the hero —
        // step to the next candidate (marker frame, then poster).
        const w = im.naturalWidth, h = im.naturalHeight;
        if (w < 120 || h < 120 || w / h < 0.45) setIdx((i) => i + 1);
      }}
    />
  );
}

function PlayerHeroCard({ playerDetails, photoCandidates, positionAbbr }) {
  return (
    <div className="bg-white border border-[#E5DFCE] rounded-[14px] shadow-[0_2px_10px_rgba(30,50,35,0.06)] overflow-hidden flex flex-col" data-testid="v2-player-hero-card">
      <div className="relative h-[260px] md:h-[280px] bg-[#0F2A1A]">
        <HeroPhoto candidates={photoCandidates} alt={playerDetails.player_name} />
        <div aria-hidden className="absolute inset-0 bg-gradient-to-tr from-[#12402A]/25 to-transparent" />
        <div className="absolute top-4 right-4 bg-white/95 rounded-[12px] px-4 py-2.5 text-center">
          <div className="font-barlow font-black text-[30px] leading-[0.9] text-[#12402A]">{positionAbbr}</div>
          <div className="text-[8.5px] tracking-[0.14em] font-bold text-[#8B957F] uppercase mt-1">Preferred Position</div>
        </div>
      </div>
      <div className="p-5 md:px-6 md:pb-6">
        <h2 className="font-barlow font-black text-[32px] tracking-[0.02em] leading-[0.95] uppercase" data-testid="v2-player-name">{playerDetails.player_name}</h2>
        <div className="text-[12px] font-bold tracking-[0.18em] uppercase text-[#1E5B3C] mt-1">{playerDetails.position}</div>
        <div className="flex mt-3.5 border-t border-[#E5DFCE] pt-3">
          {[
            ["Age", playerDetails.age],
            ["Foot", playerDetails.preferred_foot],
            ["Club", playerDetails.current_club || "Independent"],
            ["Type", playerDetails.video_type],
          ].map(([k, v], i) => (
            <div key={k} className={`flex-1 min-w-0 ${i > 0 ? "border-l border-[#E5DFCE] pl-3" : ""} pr-2`}>
              <div className="text-[9px] tracking-[0.14em] font-bold text-[#8B957F] uppercase">{k}</div>
              <div className="text-[13px] font-bold mt-0.5 capitalize truncate">{v}</div>
            </div>
          ))}
        </div>
        <div className="mt-3.5 text-[#1E5B3C] text-[21px]" style={{ fontFamily: "'Caveat', cursive", fontWeight: 600 }}>
          Keep inspiring.
        </div>
      </div>
    </div>
  );
}

function ParentSummaryCard({ parentSummary }) {
  return (
    <V2Card testid="v2-parent-summary-card">
      <V2Title icon={Users}>Parent Summary</V2Title>
      <div className="text-[16.5px] font-extrabold text-[#174A30] leading-[1.35] mb-3" data-testid="v2-parent-headline">
        {parentSummary.headline}
      </div>
      {parentSummary.paragraphs.map((p, i) => (
        <p key={i} className="text-[13px] leading-[1.62] text-[#3C4A40] mb-2.5">{p}</p>
      ))}
      {parentSummary.goodNews && (
        <div className="bg-[#F0F5EC] border border-[#DCE8D6] rounded-[11px] px-4 py-3.5 flex gap-3 mt-1">
          <div className="w-[34px] h-[34px] rounded-[9px] bg-[#1E5B3C] text-white flex items-center justify-center shrink-0">
            <Star className="w-3.5 h-3.5 fill-white" />
          </div>
          <div>
            <b className="text-[11.5px] tracking-[0.14em] text-[#12402A] block mb-1">THE GOOD NEWS</b>
            <span className="text-[12.5px] leading-[1.55] text-[#3C4A40]">{parentSummary.goodNews}</span>
          </div>
        </div>
      )}
    </V2Card>
  );
}

function OverallScoreCard({ overall, playerType, stars, ctx, bracket }) {
  const pct = overall != null ? (overall / 10) * 100 : 0;
  return (
    <V2Card testid="v2-overall-score-card" className="flex flex-col items-center justify-center text-center">
      <h3 className="text-[13.5px] font-extrabold tracking-[0.1em] uppercase text-[#12402A] mb-4">Overall Development Score</h3>
      <div
        className="relative w-[180px] h-[180px] rounded-full flex items-center justify-center mb-4"
        style={{ background: `conic-gradient(#12402A 0 ${pct * 0.68}%, #6E9E63 ${pct * 0.68}% ${pct}%, #C9D8C0 ${pct}% 100%)` }}
      >
        <div className="absolute inset-[15px] bg-white rounded-full" />
        <span className="relative font-barlow font-black text-[54px] text-[#101B12] leading-none" data-testid="v2-overall-score">
          {overall != null ? Number(overall).toFixed(1) : "—"}
        </span>
        <span className="relative text-[14px] text-[#8B957F] font-bold">/10</span>
      </div>
      {ctx?.level && (
        <div data-testid="v2-overall-level" className="bg-[#12402A] text-[#CCFF00] font-barlow font-extrabold text-[13px] tracking-[0.1em] uppercase px-4 py-1.5 rounded-full mb-2.5">
          {ctx.level} level{bracket ? ` · ${bracket}` : ""}
        </div>
      )}
      <div className="text-[13px] font-extrabold tracking-[0.09em] uppercase text-[#101B12]">{playerType}</div>
      <div className="flex gap-1 my-2.5">
        {[1, 2, 3, 4, 5].map((i) => (
          <Star key={i} className={`w-[18px] h-[18px] ${i <= stars ? "text-[#E8B32C] fill-[#E8B32C]" : "text-[#DCE3D2]"}`} />
        ))}
      </div>
      <p className="text-[12px] text-[#68766B] leading-[1.55] max-w-[290px]">
        {ctx?.line || "This score reflects the current level compared to other players of the same age in this position."}
      </p>
    </V2Card>
  );
}

function V2Footer() {
  return (
    <div className="bg-[#12402A] rounded-t-[14px] text-[#E9EFE2] flex flex-col md:flex-row items-center justify-between gap-3 px-6 md:px-8 py-5 mt-4" data-testid="v2-report-footer">
      <div className="text-[12.5px] leading-[1.5] max-w-[280px] text-center md:text-left">
        <span className="text-[#7BA05B] mr-2">❝</span>Talent gets you noticed. Character makes you unforgettable.
      </div>
      <div className="text-center">
        <div className="font-barlow font-black text-[19px] tracking-[0.06em]">SCOUTMEPLAY</div>
        <div className="text-[9px] tracking-[0.24em] text-[#A9BC9C] mt-0.5">YOUR JOURNEY. OUR ANALYSIS. YOUR FUTURE.</div>
      </div>
      <div className="text-[12px] leading-[1.55] max-w-[270px] text-center md:text-right">
        Thank you for trusting ScoutMePlay. We are excited to be part of your journey!
      </div>
    </div>
  );
}

export default function PremiumReportV2({ report, assetBase }) {
  const d = deriveV2(report);
  const pd = report.player_details || {};
  const videoRef = useRef(null);

  const photoCandidates = [
    resolveUrl(report.display_crop_url, assetBase),
    resolveUrl(report.subject_crop_url, assetBase),
    resolveUrl(report.marker_url, assetBase),
    resolveUrl(report.poster_url, assetBase),
  ].filter(Boolean);
  const videoUrl = report.demo ? null : resolveUrl(report.video_url, assetBase);
  const posterUrl = resolveUrl(report.poster_url, assetBase) || resolveUrl(report.marker_url, assetBase);

  const fixThumb = (u) => resolveUrl(u, assetBase);

  const playAt = useCallback((ts) => {
    const v = videoRef.current;
    if (!v) return;
    const sec = tsToSeconds(ts);
    const seekPlay = () => {
      if (sec != null) { try { v.currentTime = sec; } catch { /* noop */ } }
      const p = v.play();
      // Unmuted autoplay can be rejected — retry muted so playback always starts.
      if (p?.catch) p.catch(() => { v.muted = true; v.play().catch(() => {}); });
    };
    v.scrollIntoView({ behavior: "smooth", block: "center" });
    if (v.readyState >= 1) seekPlay();
    else {
      v.addEventListener("loadedmetadata", seekPlay, { once: true });
      try { v.load(); } catch { /* noop */ }
    }
  }, []);

  // Resolve derived thumbnail URLs against the API base
  const topStrengths = d.topStrengths.map((s) => ({ ...s, thumb: fixThumb(s.thumb) }));
  const videoHighlight = d.videoHighlight ? { ...d.videoHighlight, thumb: fixThumb(d.videoHighlight.thumb) } : null;

  return (
    <div className="max-w-[1440px] mx-auto text-[#1C2B21]" data-testid="premium-report-v2" style={{ fontFamily: "'DM Sans', sans-serif" }}>
      <V2PageHeader reportDate={fmtDate(report.full_generated_at || report.paid_at || report.created_at)} />

      {/* Row 1 — hero / parent summary / score */}
      <div className="grid lg:grid-cols-[1fr_1.22fr_1fr] gap-4 mb-4">
        <PlayerHeroCard playerDetails={pd} photoCandidates={photoCandidates} positionAbbr={d.positionAbbr} />
        <ParentSummaryCard parentSummary={d.parentSummary} />
        <OverallScoreCard overall={d.overall} playerType={d.playerType} stars={d.stars} ctx={report.score_context?.overall} bracket={report.score_context?.bracket} />
      </div>

      {report.progression?.categories?.length > 0 ? (
        <div className="mb-4">
          <ProgressCard prog={report.progression} />
        </div>
      ) : (
        !report.demo && <ProgressTeaser playerName={pd.player_name} />
      )}

      {/* Row 2 — snapshot / match stats / age comparison */}
      <div className={`grid gap-4 mb-4 ${d.matchStats ? "lg:grid-cols-[1fr_0.96fr_1.04fr]" : "lg:grid-cols-2"}`}>
        <SnapshotCard snapshot={d.snapshot} />
        <MatchStatsCard matchStats={d.matchStats} />
        <AgeComparisonCard ageComparison={d.ageComparison} ageBracket={d.ageBracket} />
      </div>

      {/* Row 3 — top strengths / development priorities */}
      <div className="grid lg:grid-cols-[1.16fr_1fr] gap-4 mb-4">
        <TopStrengthsCard topStrengths={topStrengths} onPlayAt={playAt} fallbackThumb={resolveUrl(report.marker_url, assetBase) || posterUrl} />
        <DevPrioritiesCard devPriorities={d.devPriorities} />
      </div>

      {report.verification?.anchors > 0 && (
        <div className="mb-4">
          <VerifiedIdentityStrip verification={report.verification} />
        </div>
      )}

      {d.identityNote && (
        <div data-testid="v2-identity-note" className="mb-4 -mt-1 flex items-start gap-2 text-[11.5px] text-[#8A6D3B] bg-[#FFF8E9] border border-[#F0E3C4] rounded-[10px] px-3.5 py-2.5 leading-[1.5]">
          <ShieldCheck className="w-3.5 h-3.5 mt-0.5 shrink-0" />
          <span>{d.identityNote}</span>
        </div>
      )}

      {d.actionTimeline?.length > 0 && (
        <div className="mb-4">
          <ActionTimelineCard actions={d.actionTimeline} onPlayAt={playAt} />
        </div>
      )}

      {report.movement_map?.trail?.length > 0 && (
        <div className="mb-4">
          <MovementMapCard movement={report.movement_map} pace={report.pace_metrics} onPlayAt={playAt} />
        </div>
      )}

      {report.pace_metrics?.top_speed_kmh && (
        <div className="mb-4">
          <PaceCard pace={report.pace_metrics} onPlayAt={playAt} />
        </div>
      )}

      {report.score_meaning?.skills?.length ? (
        <div className="mb-4">
          <ScoreMeaningSection sm={report.score_meaning} playerName={pd.player_name} position={pd.position} onPlayAt={playAt} />
        </div>
      ) : report.score_context?.overall ? (
        <div className="mb-4">
          <ScoreGuideCard sctx={report.score_context} />
        </div>
      ) : null}

      {/* Row 4 — roadmap / training plan / parent tips */}
      <div className="grid lg:grid-cols-3 gap-4 mb-4">
        <RoadmapCard roadmap={d.roadmap} />
        <TrainingPlanCard trainingWeek={d.trainingWeek} />
        <ParentTipsCard parentTips={d.parentTips} />
      </div>

      {d.parentMetrics && (
        <div className="mb-4">
          <ParentValueMetricsCard metrics={d.parentMetrics} onPlayAt={playAt} />
        </div>
      )}

      {d.growYourGame && (
        <div className="mb-4">
          <GrowYourGameSection gyg={d.growYourGame} playerName={pd.player_name} onPlayAt={playAt} />
        </div>
      )}

      {(d.parentCorner || pd.age) && (
        <div className="mb-4">
          <ParentCornerSection parentCorner={d.parentCorner} playerName={pd.player_name} playerAge={pd.age} />
        </div>
      )}

      {/* The Path — honest dream roadmap, moves with every analysis */}
      <div className="mb-4">
        <DreamPathSection report={report} d={d} playerName={pd.player_name} />
      </div>

      {d.parentsPackage && (
        <div className="mb-4">
          <ParentsPackageSection pack={d.parentsPackage} playerName={pd.player_name} onPlayAt={playAt} />
        </div>
      )}

      {d.missions?.length > 0 && (
        <div className="mb-4">
          <MissionsCard missions={d.missions} />
        </div>
      )}

      {/* Row 5 — video highlight / coach notes / scout outlook */}
      <div className="grid lg:grid-cols-[1.08fr_1fr_1.1fr] gap-4">
        <VideoHighlightCard videoHighlight={videoHighlight} videoUrl={videoUrl} posterUrl={posterUrl} videoRef={videoRef} />
        <CoachNotesCard coachNotes={d.coachNotes} />
        <ScoutOutlookCard scoutOutlook={d.scoutOutlook} />
      </div>

      <V2Footer />
    </div>
  );
}
