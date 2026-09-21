// Section components for Premium Report V2 — rows 2-5 of the pixel-perfect
// report design. All data arrives pre-derived from derive.js.

import React from "react";
import {
  Star, Target, Flame, Trophy, BarChart3, Medal,
  PersonStanding, CircleDot, HeartPulse, Lightbulb, Play, Footprints,
  Bell, Brain, Wand2, Dumbbell, Timer, MonitorPlay, Route, ClipboardList,
  Check, Sprout, BedDouble, Heart, ShieldCheck, Clipboard, Binoculars, ArrowRight,
} from "lucide-react";
import { canUseAuthorityProof, strengthThumb } from "@/lib/authorityJoin.mjs";

export const V2Card = ({ children, className = "", testid }) => (
  <div data-testid={testid} className={`bg-white border border-[#E5DFCE] rounded-[14px] shadow-[0_2px_10px_rgba(30,50,35,0.06)] p-5 md:p-6 ${className}`}>
    {children}
  </div>
);

export const V2Title = ({ icon: Icon, children, tone = "green", right = null }) => (
  <div className="flex items-center justify-between mb-4">
    <div className="flex items-center gap-2.5 font-bold text-[13px] md:text-[14px] tracking-[0.08em] uppercase text-[#12402A]">
      <span className={`w-7 h-7 rounded-[7px] flex items-center justify-center ${tone === "orange" ? "bg-[#FDF3EA] text-[#DD6B20]" : "bg-[#E9F1E6] text-[#1E5B3C]"}`}>
        <Icon className="w-3.5 h-3.5" />
      </span>
      {children}
    </div>
    {right}
  </div>
);

/* ── ROW 2 ─────────────────────────────────────────────── */

export function MatchStatsCard({ matchStats }) {
  if (!matchStats) return null;
  return (
    <V2Card testid="v2-match-stats-card">
      <V2Title icon={BarChart3}>Key Stats From This Match</V2Title>
      {matchStats.map((s, i) => (
        <div key={i} className={`flex items-center gap-3 py-[9px] ${i < matchStats.length - 1 ? "border-b border-[#EFEADB]" : ""}`}>
          <div className="text-[10.5px] font-bold tracking-[0.09em] uppercase text-[#5B695E] w-[145px] shrink-0">{s.label}</div>
          <div className="flex-1 h-[5px] bg-[#EDE8DA] rounded-full overflow-hidden">
            <div className="h-full bg-[#1E5B3C] rounded-full" style={{ width: `${Math.max(4, s.pct)}%` }} />
          </div>
          <div className="font-barlow font-extrabold text-[18px] w-[52px] text-right tabular-nums">{s.value}</div>
        </div>
      ))}
    </V2Card>
  );
}

export function AgeComparisonCard({ ageComparison, ageBracket }) {
  if (!ageComparison?.length) return null;
  return (
    <V2Card testid="v2-age-comparison-card">
      <V2Title icon={Medal}>Comparison To Players Your Age{ageBracket ? ` (${ageBracket})` : ""}</V2Title>
      {ageComparison.map((c, i) => (
        <div key={i} className={`flex items-center gap-3 py-[10px] ${i < ageComparison.length - 1 ? "border-b border-[#EFEADB]" : ""}`}>
          <div className="text-[13px] font-semibold w-[130px] shrink-0 truncate">{c.name}</div>
          <div className="flex-1 h-[6px] bg-[#EDE8DA] rounded-full overflow-hidden">
            <div className="h-full rounded-full bg-gradient-to-r from-[#7BA05B] to-[#12402A]" style={{ width: `${c.width}%` }} />
          </div>
          <div className="text-[13px] font-extrabold text-[#12402A] w-[64px] text-right">{c.label}</div>
        </div>
      ))}
      <div className="text-[10.5px] text-[#93A08F] mt-2.5">These bars show how your child compares to other players his age.</div>
    </V2Card>
  );
}

/* ── ROW 3 ─────────────────────────────────────────────── */

const STRENGTH_ICONS = { technical: CircleDot, tactical: Lightbulb, physical: PersonStanding, mentality: HeartPulse };

export function TopStrengthsCard({ topStrengths, onPlayAt, fallbackThumb, authority = false }) {
  if (!topStrengths?.length) return null;
  return (
    <V2Card testid="v2-top-strengths-card">
      <V2Title icon={Star} right={<span className="text-[11px] font-extrabold tracking-[0.14em] text-[#1E5B3C] w-[140px] text-center hidden md:block">EVIDENCE</span>}>
        Top Strengths
      </V2Title>
      {topStrengths.map((s, i) => {
        const Icon = STRENGTH_ICONS[s.category] || Star;
        // FIX 01 C01 — authority: never present generic imagery as evidence,
        // and no proof affordance without an authoritative reference.
        const proofable = s.proofable != null ? s.proofable : canUseAuthorityProof(authority, s);
        const thumb = strengthThumb(authority, s.thumb, fallbackThumb);
        return (
          <div key={i} data-testid={`v2-strength-${i}`} className={`flex items-center gap-3.5 py-3.5 ${i < topStrengths.length - 1 ? "border-b border-[#EFEADB]" : ""}`}>
            <div className="w-11 h-11 rounded-full bg-[#12402A] text-white flex items-center justify-center shrink-0">
              <Icon className="w-4.5 h-4.5 w-5 h-5" />
            </div>
            <div className="flex-1 min-w-0">
              <div className="text-[13.5px] font-extrabold tracking-[0.05em] uppercase">{s.name}</div>
              <p className="text-[12px] text-[#68766B] leading-[1.5] mt-0.5 max-w-[280px]">{s.note}</p>
              {s.timestamp && proofable && (
                <button
                  type="button"
                  onClick={() => onPlayAt?.(s.timestamp, { evidenceId: s.evidenceId, eventId: s.eventId })}
                  data-testid={`v2-strength-proof-${i}`}
                  className="md:hidden mt-2 inline-flex items-center gap-1.5 bg-[#12402A] text-[#CCFF00] text-[10px] font-extrabold tracking-[0.07em] uppercase px-2.5 py-1 rounded-full active:scale-95 transition-transform"
                >
                  <Play className="w-2.5 h-2.5 fill-[#CCFF00]" /> See the proof · {s.timestamp}
                </button>
              )}
            </div>
            <div className="font-barlow font-black text-[22px] text-[#12402A] w-[62px] shrink-0">
              {Number(s.score).toFixed(1)}<span className="text-[13px] text-[#A5AF9E] font-bold">/10</span>
            </div>
            <div className="font-barlow font-extrabold text-[15px] text-[#5B695E] w-[46px] shrink-0 hidden sm:block tabular-nums">{s.timestamp || ""}</div>
            {thumb && proofable ? (
              <button
                type="button"
                onClick={() => onPlayAt?.(s.timestamp, { evidenceId: s.evidenceId, eventId: s.eventId })}
                data-testid={`v2-strength-play-${i}`}
                className="relative w-[140px] h-[80px] rounded-[9px] overflow-hidden border border-[#E5DFCE] shrink-0 hidden md:block group"
              >
                <img src={thumb} alt={s.name} loading="lazy" className="w-full h-full object-cover" />
                <span className="absolute inset-0 flex items-center justify-center">
                  <span className="w-8 h-8 rounded-full bg-[#0A190F]/75 border-[1.5px] border-white/85 flex items-center justify-center transition-transform group-hover:scale-110">
                    <Play className="w-3 h-3 text-white fill-white ml-0.5" />
                  </span>
                </span>
                {s.thumb && s.thumbVerified && (
                  <span data-testid={`v2-strength-verified-${i}`} className="absolute left-1.5 top-1.5 flex items-center gap-1 bg-[#0A190F]/80 text-[#CCFF00] text-[8.5px] font-extrabold tracking-[0.08em] px-1.5 py-0.5 rounded-[4px] pointer-events-none">
                    <ShieldCheck className="w-2.5 h-2.5" /> IDENTITY-VERIFIED
                  </span>
                )}
              </button>
            ) : <div className="w-[140px] shrink-0 hidden md:block" />}
          </div>
        );
      })}
    </V2Card>
  );
}

const DP_ICONS = [Bell, Footprints, Brain];
const HTI_ICONS = [Dumbbell, Timer, MonitorPlay];

const AT_OUTCOME = { positive: "#12402A", neutral: "#5B695E", negative: "#DD6B20" };

export function ActionTimelineCard({ actions, onPlayAt }) {
  if (!actions?.length) return null;
  return (
    <V2Card testid="v2-action-timeline-card">
      <V2Title icon={ClipboardList} right={<span className="text-[11px] font-extrabold tracking-[0.14em] text-[#1E5B3C] hidden md:block">{actions.length} ACTIONS · TAP TO WATCH</span>}>
        Action Timeline
      </V2Title>
      <div className="relative pl-7">
        <div className="absolute left-[7px] top-2 bottom-2 w-[2px] bg-[#EFEADB]" />
        {actions.map((a, i) => {
          // FIX 02 — defense-in-depth: unverified authority events render
          // non-clickable (no proof affordance, no timestamp-only navigation).
          const clickable = a.proofable !== false;
          const Row = clickable ? "button" : "div";
          return (
          <Row
            key={i}
            {...(clickable
              ? { type: "button", onClick: () => onPlayAt?.(a.timestamp, { eventId: a.eventId }) }
              : {})}
            data-testid={`v2-action-row-${i}`}
            className={`relative w-full text-left flex items-center gap-3 py-2.5 group ${i < actions.length - 1 ? "border-b border-[#F2EDDE]" : ""}`}
          >
            <span
              className="absolute -left-7 top-1/2 -translate-y-1/2 w-4 h-4 rounded-full border-[3px] border-white shadow-[0_1px_4px_rgba(30,50,35,0.25)]"
              style={{ background: AT_OUTCOME[a.outcome] || AT_OUTCOME.neutral }}
            />
            <span className="bg-[#12402A] text-[#CCFF00] font-barlow font-extrabold text-[12px] px-2 py-0.5 rounded-[6px] tabular-nums shrink-0">{a.timestamp}</span>
            <span className="flex-1 min-w-0">
              <span className="block text-[12.5px] font-extrabold tracking-[0.04em] uppercase text-[#1C2B21] group-hover:text-[#12402A] transition-colors">
                {a.title}
                {a.tracked && (
                  <span data-testid={`v2-action-tracked-${i}`} className="inline-flex items-center gap-[3px] align-middle ml-2 bg-[#12402A] text-[#CCFF00] text-[8px] font-extrabold tracking-[0.08em] px-1.5 py-[2px] rounded-[4px] normal-case">
                    <ShieldCheck className="w-2.5 h-2.5" /> TRACKING-VERIFIED
                  </span>
                )}
              </span>
              {a.description && <span className="block text-[11.5px] text-[#68766B] leading-[1.45]">{a.description}</span>}
            </span>
            {a.rating != null && (
              <span className="font-barlow font-black text-[17px] shrink-0 tabular-nums" style={{ color: AT_OUTCOME[a.outcome] || "#12402A" }}>
                {Number(a.rating).toFixed(1)}
              </span>
            )}
            {clickable && <Play className="w-3.5 h-3.5 text-[#12402A] shrink-0 opacity-0 group-hover:opacity-100 transition-opacity hidden md:block" />}
          </Row>
          );
        })}
      </div>
    </V2Card>
  );
}

export function DevPrioritiesCard({ devPriorities }) {
  if (!devPriorities?.length) return null;
  return (
    <V2Card testid="v2-dev-priorities-card" className="!bg-[#FFFBF6]">
      <V2Title icon={PersonStanding} tone="orange">Development Priorities</V2Title>
      <div className="grid md:grid-cols-[1.25fr_1fr] gap-5">
        <div>
          {devPriorities.map((p, i) => {
            const Icon = DP_ICONS[i % DP_ICONS.length];
            return (
              <div key={i} className={`flex gap-3.5 py-3.5 ${i < devPriorities.length - 1 ? "border-b border-[#F4E9DC]" : ""}`}>
                <div className="w-11 h-11 rounded-full border-2 border-[#DD6B20] bg-[#FDF3EA] text-[#DD6B20] flex items-center justify-center shrink-0">
                  <Icon className="w-4 h-4" />
                </div>
                <div className="min-w-0">
                  <span className="text-[13.5px] font-extrabold tracking-[0.05em] uppercase">{p.name}</span>
                  {p.score != null && (
                    <span className="font-barlow font-black text-[19px] text-[#DD6B20] ml-2.5">
                      {Number(p.score).toFixed(1)}<span className="text-[12px] text-[#C9B49C]">/10</span>
                    </span>
                  )}
                  <p className="text-[12px] text-[#68766B] leading-[1.55] mt-1">{p.issue}</p>
                </div>
              </div>
            );
          })}
        </div>
        <div className="md:border-l md:border-dashed md:border-[#EBD9C4] md:pl-5">
          <div className="text-[12px] font-extrabold tracking-[0.12em] text-[#DD6B20] mb-3.5 flex items-center gap-1.5">
            <Wand2 className="w-3.5 h-3.5" /> HOW TO IMPROVE
          </div>
          {devPriorities.map((p, i) => {
            const Icon = HTI_ICONS[i % HTI_ICONS.length];
            return (
              <div key={i} className="flex gap-3 mb-4">
                <div className="w-9 h-9 rounded-[10px] bg-[#FDF3EA] border border-[#F3D9BF] text-[#DD6B20] flex items-center justify-center shrink-0">
                  <Icon className="w-3.5 h-3.5" />
                </div>
                <p className="text-[12.5px] leading-[1.55] text-[#3C4A40]">{p.howTo}</p>
              </div>
            );
          })}
        </div>
      </div>
    </V2Card>
  );
}

/* ── ROW 4 ─────────────────────────────────────────────── */

const ROAD_ICONS = [PersonStanding, Timer, Footprints, Trophy];

export function RoadmapCard({ roadmap }) {
  return (
    <V2Card testid="v2-roadmap-card">
      <V2Title icon={Route}>Development Roadmap</V2Title>
      <div className="flex items-start justify-between gap-1 mt-1">
        {roadmap.map((m, i) => {
          const Icon = ROAD_ICONS[i % ROAD_ICONS.length];
          return (
            <React.Fragment key={i}>
              <div className="text-center flex-1 min-w-0">
                <div className="w-12 h-12 rounded-full bg-[#12402A] text-white flex items-center justify-center mx-auto mb-2">
                  <Icon className="w-[18px] h-[18px]" />
                </div>
                <div className="text-[10.5px] font-extrabold tracking-[0.1em]">{m.key}</div>
                <p className="text-[10.5px] text-[#68766B] leading-[1.45] mt-1 line-clamp-3">{m.text}</p>
              </div>
              {i < roadmap.length - 1 && <ArrowRight className="w-3.5 h-3.5 text-[#B9C4AE] mt-[18px] shrink-0" />}
            </React.Fragment>
          );
        })}
      </div>
    </V2Card>
  );
}

const TP_ICONS = [CircleDot, Footprints, PersonStanding, Trophy];

export function TrainingPlanCard({ trainingWeek }) {
  return (
    <V2Card testid="v2-training-plan-card">
      <V2Title icon={ClipboardList}>
        Training Plan <span className="font-semibold text-[#8B957F] normal-case tracking-normal text-[12px]">(Weekly example)</span>
      </V2Title>
      <div className="grid grid-cols-4 gap-2">
        {trainingWeek.map((d, i) => {
          const Icon = TP_ICONS[i % TP_ICONS.length];
          return (
            <div key={i} className="bg-[#FBF9F3] border border-[#E5DFCE] rounded-[10px] p-2.5 text-center">
              <div className="text-[10px] font-extrabold tracking-[0.1em] text-[#12402A]">{d.day}</div>
              <div className="text-[11px] font-bold mt-1 leading-[1.35] line-clamp-2 min-h-[30px]">{d.name}</div>
              <div className="text-[10px] text-[#68766B] mt-0.5 min-h-[14px]">{d.mins}</div>
              <Icon className="w-[18px] h-[18px] text-[#1E5B3C] mx-auto mt-2" />
            </div>
          );
        })}
      </div>
      <div className="mt-3 text-center text-[11.5px] text-[#68766B] leading-[1.5]">
        <b className="text-[#12402A]">Consistency is more important than perfection.</b><br />
        Small steps every day = Big progress.
      </div>
    </V2Card>
  );
}

const TIP_ICONS = [Check, Sprout, BedDouble, Heart];

export function ParentTipsCard({ parentTips }) {
  return (
    <V2Card testid="v2-parent-tips-card">
      <V2Title icon={Heart}>Parent Tips</V2Title>
      {parentTips.map((tip, i) => {
        const Icon = TIP_ICONS[i % TIP_ICONS.length];
        return (
          <div key={i} className={`flex items-start gap-3 py-2.5 ${i < parentTips.length - 1 ? "border-b border-[#EFEADB]" : ""}`}>
            <div className="w-[30px] h-[30px] rounded-full bg-[#E9F1E6] text-[#1E5B3C] flex items-center justify-center shrink-0">
              <Icon className="w-3 h-3" />
            </div>
            <p className="text-[12.5px] leading-[1.5] text-[#3C4A40] font-medium pt-[5px]">{tip}</p>
          </div>
        );
      })}
    </V2Card>
  );
}

/* ── ROW 5 ─────────────────────────────────────────────── */

export function VideoHighlightCard({ videoHighlight, videoUrl, posterUrl, videoRef }) {
  return (
    <V2Card testid="v2-video-highlight-card">
      <V2Title icon={ShieldCheck}>Video Evidence Highlight</V2Title>
      <div className="relative rounded-[11px] overflow-hidden border border-[#E5DFCE] bg-black aspect-video">
        {videoUrl ? (
          <video
            ref={videoRef}
            src={videoUrl}
            poster={videoHighlight?.thumb || posterUrl || undefined}
            controls
            playsInline
            preload="metadata"
            data-testid="v2-report-video"
            className="absolute inset-0 w-full h-full object-cover"
          />
        ) : (
          videoHighlight?.thumb && <img src={videoHighlight.thumb} alt="" loading="lazy" className="absolute inset-0 w-full h-full object-cover" />
        )}
        {videoHighlight?.timestamp && (
          <span className="absolute left-3 bottom-12 bg-[#0A190F]/85 text-white font-barlow font-extrabold text-[13px] px-2.5 py-0.5 rounded-[5px] pointer-events-none">
            {videoHighlight.timestamp}
          </span>
        )}
        {videoHighlight?.thumbVerified && (
          <span data-testid="v2-highlight-verified" className="absolute right-3 bottom-12 flex items-center gap-1 bg-[#0A190F]/85 text-[#CCFF00] font-extrabold text-[9px] tracking-[0.08em] px-2 py-0.5 rounded-[5px] pointer-events-none">
            <ShieldCheck className="w-3 h-3" /> IDENTITY-VERIFIED FRAME
          </span>
        )}
      </div>
      {videoHighlight?.caption && (
        <p className="text-[12.5px] text-[#3C4A40] leading-[1.55] mt-3">{videoHighlight.caption}</p>
      )}
    </V2Card>
  );
}

export function CoachNotesCard({ coachNotes }) {
  if (!coachNotes?.length) return null;
  return (
    <V2Card testid="v2-coach-notes-card">
      <V2Title icon={Clipboard}>Coach Notes</V2Title>
      <ul>
        {coachNotes.map((n, i) => (
          <li key={i} className="flex gap-2.5 text-[13px] leading-[1.55] text-[#3C4A40] mb-2.5">
            <span className="text-[#1E5B3C] font-black">•</span>{n}
          </li>
        ))}
      </ul>
    </V2Card>
  );
}

const Dots = ({ n }) => (
  <div className="flex gap-1.5 mt-1.5">
    {[1, 2, 3, 4, 5].map((i) => (
      <span key={i} className={`w-[11px] h-[11px] rounded-full ${i <= n ? "bg-[#12402A]" : "bg-[#DCE3D2]"}`} />
    ))}
  </div>
);

export function ScoutOutlookCard({ scoutOutlook }) {
  return (
    <V2Card testid="v2-scout-outlook-card">
      <V2Title icon={Binoculars}>Next Level Outlook</V2Title>
      <div className="grid grid-cols-[1.05fr_1fr] gap-4">
        <div>
          <div className="mb-3.5">
            <div className="text-[10px] font-extrabold tracking-[0.13em] uppercase text-[#8B957F]">Current Level</div>
            <div className="text-[14px] font-extrabold mt-0.5">{scoutOutlook.currentLabel}</div>
            <Dots n={scoutOutlook.currentDots} />
          </div>
          <div className="mb-3.5">
            <div className="text-[10px] font-extrabold tracking-[0.13em] uppercase text-[#8B957F]">Potential Level</div>
            <div className="text-[14px] font-extrabold mt-0.5">{scoutOutlook.potentialLabel}</div>
            <Dots n={scoutOutlook.potentialDots} />
          </div>
          <div>
            <div className="text-[10px] font-extrabold tracking-[0.13em] uppercase text-[#8B957F]">Recruitment Readiness</div>
            <div className="text-[14px] font-extrabold mt-0.5">{scoutOutlook.readiness}</div>
          </div>
        </div>
        <div className="border-l border-[#E5DFCE] pl-4 text-center">
          <div className="text-[10px] font-extrabold tracking-[0.13em] uppercase text-[#8B957F]">Long-Term Potential</div>
          <div className="flex justify-center gap-1 my-2">
            {[1, 2, 3, 4, 5].map((i) => (
              <Star key={i} className={`w-4 h-4 ${i <= (scoutOutlook.longTerm === "High" ? 5 : scoutOutlook.longTerm === "Medium" ? 4 : 3) ? "text-[#E8B32C] fill-[#E8B32C]" : "text-[#DCE3D2]"}`} />
            ))}
          </div>
          <div className="text-[16px] font-extrabold text-[#12402A]">{scoutOutlook.longTerm}</div>
          <p className="text-[11.5px] text-[#68766B] leading-[1.5] mt-1.5">{scoutOutlook.longTermNote}</p>
        </div>
      </div>
    </V2Card>
  );
}
