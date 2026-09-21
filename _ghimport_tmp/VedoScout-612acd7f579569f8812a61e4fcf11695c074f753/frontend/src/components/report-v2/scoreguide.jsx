// Score Guide — translates every score into a level word + one plain sentence.
import React from "react";
import { BadgeCheck } from "lucide-react";
import { V2Card, V2Title } from "./sections";

const LEVELS = ["Grassroots", "Club", "Top Club", "Academy", "Elite"];
const CAT_LABELS = { technical: "Technical", tactical: "Tactical", physical: "Physical", mentality: "Mindset" };
const SKILL_LABELS = {
  first_touch: "First Touch", ball_control: "Ball Control", dribbling: "Dribbling", passing: "Passing",
  shooting: "Shooting", weak_foot: "Weak Foot", one_v_one: "1v1 Attacking", positioning: "Positioning",
  off_ball_movement: "Off-Ball Movement", scanning: "Scanning", decision_making: "Decision Making",
  timing_of_runs: "Timing of Runs", game_understanding: "Game Understanding", acceleration: "Acceleration",
  speed: "Speed", balance: "Balance", agility: "Agility", intensity: "Intensity", body_control: "Body Control",
  confidence: "Confidence", work_rate: "Work Rate", courage_in_duels: "Courage in Duels",
  response_to_mistakes: "Response to Mistakes", competitive_mindset: "Competitive Drive", focus: "Focus",
};

function LevelChip({ level, small }) {
  return (
    <span className={`inline-block bg-[#12402A] text-[#CCFF00] font-barlow font-extrabold uppercase tracking-[0.1em] rounded-full ${small ? "text-[9px] px-2 py-0.5" : "text-[10.5px] px-2.5 py-1"}`}>
      {level}
    </span>
  );
}

function LevelScale({ active }) {
  return (
    <div className="grid grid-cols-5 gap-1.5 mb-2" data-testid="v2-level-scale">
      {LEVELS.map((lv) => (
        <div
          key={lv}
          className={`text-center text-[9.5px] font-extrabold tracking-[0.1em] uppercase rounded-[7px] py-1.5 ${lv === active ? "bg-[#12402A] text-[#CCFF00]" : "bg-[#F1EDE0] text-[#8B957F]"}`}
        >
          {lv}
        </div>
      ))}
    </div>
  );
}

export function ScoreGuideCard({ sctx }) {
  if (!sctx?.overall) return null;
  const cats = sctx.categories || {};
  const skills = Object.entries(sctx.skills || {}).sort((a, b) => b[1].score - a[1].score);
  return (
    <V2Card testid="v2-score-guide-card">
      <V2Title icon={BadgeCheck} right={<span className="text-[11px] font-extrabold tracking-[0.14em] text-[#1E5B3C] hidden md:block">EVERY SCORE, TRANSLATED</span>}>
        What The Scores Mean · {sctx.bracket}
      </V2Title>
      <LevelScale active={sctx.overall.level} />
      <p className="text-[11.5px] text-[#8B957F] leading-[1.5] mb-4">
        Every score below is translated into a level every parent knows — and one plain sentence about what it looks like on the pitch.
      </p>
      <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-3 mb-4">
        {Object.keys(CAT_LABELS).filter((k) => cats[k]).map((k) => (
          <div key={k} data-testid={`v2-guide-cat-${k}`} className="bg-[#FBF9F3] border border-[#E5DFCE] rounded-[12px] p-3.5">
            <div className="text-[9px] font-extrabold tracking-[0.12em] uppercase text-[#75816F]">{CAT_LABELS[k]} · Pillar</div>
            <div className="flex items-center gap-2 my-1.5">
              <span className="font-barlow font-black text-[24px] leading-none tabular-nums">{cats[k].score.toFixed(1)}</span>
              <LevelChip level={cats[k].level} />
            </div>
            <p className="text-[11px] text-[#1E5B3C] italic leading-[1.45]">“{cats[k].line}”</p>
          </div>
        ))}
      </div>
      {skills.length > 0 && (
        <div className="grid md:grid-cols-2 gap-x-6 gap-y-0.5">
          {skills.map(([k, ctx]) => (
            <div key={k} data-testid={`v2-guide-skill-${k}`} className="py-2 border-b border-[#EFEBDD] last:border-0">
              <div className="flex items-center justify-between gap-2">
                <span className="text-[11.5px] font-extrabold uppercase tracking-[0.04em]">{SKILL_LABELS[k] || k}</span>
                <span className="flex items-center gap-1.5 shrink-0">
                  <span className="font-barlow font-black text-[14px] tabular-nums text-[#12402A]">{ctx.score.toFixed(1)}</span>
                  <LevelChip level={ctx.level} small />
                </span>
              </div>
              <p className="text-[10.5px] text-[#8B957F] leading-[1.45] mt-0.5">{ctx.line}</p>
            </div>
          ))}
        </div>
      )}
      <p className="text-[10px] text-[#9AA38F] leading-[1.5] mt-4">{sctx.method_note}</p>
    </V2Card>
  );
}
