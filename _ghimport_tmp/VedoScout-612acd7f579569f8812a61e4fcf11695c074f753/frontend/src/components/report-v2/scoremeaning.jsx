// Score Meaning — "the numbers, translated". Every score becomes a discovery:
// two human sentences, verified video proof, fresh angles (no bare repetition)
// and position-specific meaning. Data comes from backend score_meaning payload.

import React, { useState } from "react";
import {
  Play, Lock, ChevronDown, Sparkles, Compass, Eye, TrendingUp,
  ArrowUpRight, ShieldCheck, ChevronRight,
} from "lucide-react";
import { V2Card } from "./sections";
import { canUseAuthorityProof } from "@/lib/authorityJoin.mjs";

const FOREST = "#12402A";
const LIME = "#CCFF00";

const CAT_LABEL = { technical: "Technical", tactical: "Tactical", physical: "Physical", mentality: "Mentality" };

const activeStep = (score) => (score < 7 ? "6" : score < 8.6 ? "8" : "9");

function AngleChips({ s, onPlayAt, seekable = true, authority = false }) {
  const a = s.angles || {};
  const ev = s.evidence;
  // FIX 01 C01 / FIX 02 — authority: no proof navigation and no "proven"
  // claim without an authoritative ID + fail-closed proof state.
  const proofable = canUseAuthorityProof(authority, ev);
  return (
    <div className="flex flex-wrap gap-1.5 mt-3">
      {ev?.verified && (!authority || proofable) && (
        seekable && onPlayAt && proofable ? (
          <button
            type="button"
            onClick={() => onPlayAt(ev.timestamp, { evidenceId: ev.evidence_id, eventId: ev.event_id })}
            data-testid={`sm-evidence-${s.key}`}
            className="inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-[10.5px] font-extrabold tracking-[0.04em] uppercase transition-transform hover:scale-[1.03] active:scale-[0.97]"
            style={{ background: FOREST, color: LIME }}
          >
            <Play className="w-3 h-3 fill-current" /> See why at {ev.timestamp}
          </button>
        ) : (
          <span
            data-testid={`sm-evidence-${s.key}`}
            className="inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-[10.5px] font-extrabold tracking-[0.04em] uppercase"
            style={{ background: FOREST, color: LIME }}
          >
            <ShieldCheck className="w-3 h-3" /> Proven on video at {ev.timestamp}
          </span>
        )
      )}
      {a.better_than != null && (
        <span className="inline-flex items-center gap-1 rounded-full px-3 py-1.5 text-[10.5px] font-bold bg-[#F0F5EC] border border-[#DCE8D6] text-[#1E5B3C]">
          Stronger than {a.better_than} of 10 his age
        </span>
      )}
      {typeof a.delta === "number" && a.delta !== 0 && (
        <span
          className={`inline-flex items-center gap-1 rounded-full px-3 py-1.5 text-[10.5px] font-bold border ${
            a.delta > 0 ? "bg-[#EAF6EC] border-[#CBE8D2] text-[#1C7C3A]" : "bg-[#FFF6EA] border-[#F0DFC0] text-[#8A6D3B]"
          }`}
        >
          <TrendingUp className="w-3 h-3" />
          {a.delta > 0 ? `+${a.delta.toFixed(1)} since last analysis` : `${a.delta.toFixed(1)} — worth watching`}
        </span>
      )}
      {a.gap_to_next != null && a.next_band && (
        <span className="inline-flex items-center gap-1 rounded-full px-3 py-1.5 text-[10.5px] font-bold bg-[#F7F4EA] border border-[#E5DFCE] text-[#5C6657]">
          <ArrowUpRight className="w-3 h-3" /> {a.gap_to_next.toFixed(1)} from {a.next_band} level
        </span>
      )}
    </div>
  );
}

function ScaleLadder({ scale, score }) {
  if (!scale) return null;
  const act = activeStep(score);
  return (
    <div className="space-y-1.5">
      {["6", "8", "9"].map((k) => (
        <div
          key={k}
          className={`flex gap-3 items-start rounded-[10px] px-3 py-2 border ${
            k === act ? "bg-[#12402A] border-[#12402A]" : "bg-[#FBF9F3] border-[#EDE8D6]"
          }`}
        >
          <span
            className="font-barlow font-black text-[16px] leading-none mt-0.5 w-5 text-center shrink-0"
            style={{ color: k === act ? LIME : "#8B957F" }}
          >
            {k}
          </span>
          <span className={`text-[11.5px] leading-[1.45] ${k === act ? "text-[#E9EFE2] font-semibold" : "text-[#5C6657]"}`}>
            {scale[k]}
            {k === act && <span className="ml-1.5 text-[9px] font-extrabold tracking-[0.1em] uppercase" style={{ color: LIME }}>← his zone</span>}
          </span>
        </div>
      ))}
    </div>
  );
}

function ExpandPanel({ s, position }) {
  return (
    <div className="mt-3 pt-3 border-t border-[#EDE8D6] space-y-3.5" data-testid={`sm-expanded-${s.key}`}>
      {s.looks_for && (
        <div>
          <div className="flex items-center gap-1.5 text-[9.5px] font-extrabold tracking-[0.16em] uppercase text-[#8B957F] mb-1">
            <Eye className="w-3 h-3" /> What the trained eye watches
          </div>
          <p className="text-[12px] leading-[1.6] text-[#3C4A40]">{s.looks_for}</p>
        </div>
      )}
      <div>
        <div className="text-[9.5px] font-extrabold tracking-[0.16em] uppercase text-[#8B957F] mb-1.5">
          The difference between 6, 8 and 9
        </div>
        <ScaleLadder scale={s.scale} score={s.score} />
      </div>
      {s.next_level && (
        <div>
          <div className="flex items-center gap-1.5 text-[9.5px] font-extrabold tracking-[0.16em] uppercase text-[#8B957F] mb-1">
            <ArrowUpRight className="w-3 h-3" /> The road upward
          </div>
          <p className="text-[12px] leading-[1.6] text-[#3C4A40]">{s.next_level}</p>
        </div>
      )}
      {s.position_why && (
        <div className="bg-[#F0F5EC] border border-[#DCE8D6] rounded-[10px] px-3.5 py-3">
          <div className="flex items-center gap-1.5 text-[9.5px] font-extrabold tracking-[0.16em] uppercase text-[#12402A] mb-1">
            <Compass className="w-3 h-3" /> Why this matters for a {position || "player like him"}
          </div>
          <p className="text-[12px] leading-[1.6] text-[#1E5B3C] font-medium">{s.position_why}</p>
        </div>
      )}
    </div>
  );
}

export function SkillMeaningCard({ s, position, onPlayAt, seekable = true, defaultOpen = false, authority = false }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div
      className="bg-white border border-[#E5DFCE] rounded-[14px] shadow-[0_2px_10px_rgba(30,50,35,0.06)] p-4 md:p-5"
      data-testid={`sm-skill-card-${s.key}`}
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-[9px] font-extrabold tracking-[0.16em] uppercase text-[#8B957F]">{CAT_LABEL[s.category] || s.category}</div>
          <div className="font-barlow font-black text-[17px] tracking-[0.02em] uppercase text-[#101B12] leading-tight mt-0.5">{s.label}</div>
        </div>
        <div className="text-right shrink-0">
          <span className="font-barlow font-black text-[34px] leading-none text-[#12402A]" data-testid={`sm-score-${s.key}`}>
            {Number(s.score).toFixed(1)}
          </span>
          <span className="text-[11px] font-bold text-[#8B957F]">/10</span>
        </div>
      </div>
      {(s.lines || []).map((l, i) => (
        <p key={i} className={`text-[13px] leading-[1.58] mt-2 ${i === 0 ? "text-[#174A30] font-semibold" : "text-[#3C4A40]"}`}>{l}</p>
      ))}
      <AngleChips s={s} onPlayAt={onPlayAt} seekable={seekable} authority={authority} />
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        data-testid={`sm-expand-${s.key}`}
        className="mt-3 w-full flex items-center justify-between rounded-[10px] px-3.5 py-2.5 bg-[#FBF9F3] border border-[#EDE8D6] hover:bg-[#F5F1E3] transition-colors"
      >
        <span className="text-[11.5px] font-extrabold tracking-[0.06em] uppercase text-[#12402A]">
          What does {Number(s.score).toFixed(1)} really mean?
        </span>
        <ChevronDown className={`w-4 h-4 text-[#12402A] transition-transform ${open ? "rotate-180" : ""}`} />
      </button>
      {open && <ExpandPanel s={s} position={position} />}
    </div>
  );
}

export function PositionDiscoveryCard({ discovery, playerName, currentPosition }) {
  if (!discovery?.suggest) return null;
  const first = (playerName || "he").split(" ")[0];
  return (
    <div className="rounded-[16px] overflow-hidden" style={{ background: "#0B1F14" }} data-testid="sm-discovery-card">
      <div className="p-6 md:p-7">
        <div className="flex items-center gap-2 text-[10px] font-extrabold tracking-[0.22em] uppercase" style={{ color: LIME }}>
          <Sparkles className="w-3.5 h-3.5" /> A discovery about {first}
        </div>
        <h3 className="font-barlow font-black text-white text-[22px] md:text-[26px] leading-tight mt-2 uppercase">
          The match hints at another home on the pitch:{" "}
          <span style={{ color: LIME }}>{discovery.suggest}</span>
        </h3>
        <p className="text-white/80 text-[13.5px] leading-[1.65] mt-3 max-w-[640px]">{discovery.why}</p>
        {(discovery.based_on || []).length > 0 && (
          <div className="flex flex-wrap gap-2 mt-4">
            {discovery.based_on.map((b) => (
              <span key={b.key} className="inline-flex items-center gap-2 rounded-full px-3.5 py-1.5 bg-white/8 border border-white/15 text-[11px] font-bold text-white/90" style={{ background: "rgba(255,255,255,0.08)" }}>
                {b.label}
                <span className="font-barlow font-black" style={{ color: LIME }}>{Number(b.score).toFixed(1)}</span>
              </span>
            ))}
          </div>
        )}
        <div className="mt-4 rounded-[10px] px-4 py-3 bg-white/5 border border-white/10">
          <p className="text-white/60 text-[11.5px] leading-[1.6] italic">
            {discovery.note || `An idea worth exploring in training — not a verdict. ${currentPosition ? `${first} stays a ${currentPosition} for as long as that's where the joy lives.` : ""}`}
          </p>
        </div>
      </div>
    </div>
  );
}

export function ScoreMeaningSection({ sm, playerName, position, onPlayAt, authority = false }) {
  const [showAll, setShowAll] = useState(false);
  if (!sm?.skills?.length) return null;
  const first = (playerName || "your player").split(" ")[0];
  const visible = showAll ? sm.skills : sm.skills.slice(0, 6);
  const hidden = sm.skills.length - 6;
  return (
    <section data-testid="score-meaning-section">
      <div className="rounded-t-[16px] px-6 md:px-8 py-6" style={{ background: FOREST }}>
        <div className="text-[10px] font-extrabold tracking-[0.22em] uppercase" style={{ color: LIME }}>
          ScoutMe Pro Intelligence
        </div>
        <h2 className="font-barlow font-black text-white text-[24px] md:text-[28px] uppercase leading-tight mt-1">
          The numbers, translated
        </h2>
        <p className="text-[#C9D8C0] text-[13px] leading-[1.6] mt-1.5 max-w-[680px]">
          A number on its own says nothing. Below, every score becomes a discovery about {first} —
          what it looks like on the pitch, the proof behind it, and what it means for where he can go next.
        </p>
        {sm.position_line && (
          <div className="mt-3 inline-flex items-start gap-2 rounded-[10px] px-3.5 py-2.5 bg-white/5 border border-white/10 max-w-[680px]">
            <Compass className="w-3.5 h-3.5 mt-0.5 shrink-0" style={{ color: LIME }} />
            <span className="text-white/80 text-[12px] leading-[1.55]" data-testid="sm-position-line">{sm.position_line}</span>
          </div>
        )}
      </div>
      <div className="bg-[#F5F1E3] border border-t-0 border-[#E5DFCE] rounded-b-[16px] p-4 md:p-5">
        <div className="grid md:grid-cols-2 gap-4">
          {visible.map((s) => (
            <SkillMeaningCard key={s.key} s={s} position={position} onPlayAt={onPlayAt} authority={authority} />
          ))}
        </div>
        {hidden > 0 && (
          <button
            type="button"
            onClick={() => setShowAll((v) => !v)}
            data-testid="sm-showall-btn"
            className="mt-4 w-full flex items-center justify-center gap-2 rounded-full py-3 font-barlow font-black uppercase tracking-[0.05em] text-[13px] transition-transform active:scale-[0.99]"
            style={{ background: FOREST, color: LIME }}
          >
            {showAll ? "Show fewer" : `Discover all ${sm.skills.length} numbers`}
            <ChevronDown className={`w-4 h-4 transition-transform ${showAll ? "rotate-180" : ""}`} />
          </button>
        )}
        {sm.discovery && (
          <div className="mt-4">
            <PositionDiscoveryCard discovery={sm.discovery} playerName={playerName} currentPosition={sm.position} />
          </div>
        )}
      </div>
    </section>
  );
}

// ─── Free preview teaser — exactly ONE real, fully-open score story ───
export function ScoreMeaningTeaser({ teaser, playerName, onUnlock, bonusOverride = null }) {
  if (!teaser) return null;
  const first = (playerName || "your player").split(" ")[0];
  const bonus = teaser.bonus || bonusOverride;
  const lockedLabels = (teaser.locked_labels || []).filter((l) => l !== bonus?.label);
  return (
    <div className="mt-5" data-testid="smt-section">
      <div className="flex items-center gap-2 text-[11px] font-extrabold tracking-[0.16em] uppercase text-[#12402A]">
        <Sparkles className="w-4 h-4" /> What the numbers really mean
      </div>
      <p className="text-[12.5px] text-[#5C6657] mt-1">
        Every score in the full report comes with its own story — here is one of {first}&rsquo;s, completely open.
      </p>

      {teaser.unlocked ? (
        <div className="mt-3" data-testid="smt-unlocked-card">
          <div className="relative">
            <span
              className="absolute -top-2.5 left-4 z-10 text-[9px] font-extrabold tracking-[0.12em] uppercase px-2.5 py-1 rounded-full"
              style={{ background: LIME, color: "#12211A" }}
            >
              Yours free — a taste of the full report
            </span>
            <SkillMeaningCard s={teaser.unlocked} position={null} seekable={false} defaultOpen={false} />
          </div>
        </div>
      ) : (
        <div className="mt-3 bg-white rounded-2xl border border-[#E9E4D5] p-4 shadow-sm text-[12.5px] text-[#5C6657]" data-testid="smt-pending-card">
          {first}&rsquo;s score stories are written during the complete evaluation — every number arrives with meaning, proof and a next step.
        </div>
      )}

      {bonus && (
        <div className="mt-4" data-testid="smt-bonus-card">
          <div className="relative">
            <span
              className="absolute -top-2.5 left-4 z-10 text-[9px] font-extrabold tracking-[0.12em] uppercase px-2.5 py-1 rounded-full"
              style={{ background: "#12402A", color: "#CCFF00" }}
            >
              Unlocked by your share — thank you
            </span>
            <SkillMeaningCard s={bonus} position={null} seekable={false} defaultOpen={false} />
          </div>
        </div>
      )}

      {lockedLabels.length > 0 && (
        <div className="mt-3 bg-white rounded-2xl border border-[#E9E4D5] p-4 shadow-sm" data-testid="smt-locked-list">
          <div className="flex items-center justify-between">
            <div className="font-barlow font-black text-[14px] text-[#12211A] uppercase">
              {teaser.locked_count || lockedLabels.length} more of {first}&rsquo;s numbers are waiting to tell their story
            </div>
            <Lock className="w-4 h-4 text-[#8B957F]" />
          </div>
          <div className="mt-2.5 space-y-2">
            {lockedLabels.slice(0, 6).map((label, i) => (
              <div key={label} className="flex items-center gap-2.5" data-testid={`smt-locked-row-${i}`}>
                <span className="text-[12px] font-bold text-[#12211A] whitespace-nowrap">{label}</span>
                <span className="flex-1 h-3 rounded bg-gradient-to-r from-[#EDE9DB] to-[#F6F2E6] relative overflow-hidden">
                  <span className="absolute inset-y-0 left-2 right-10 blur-[6px] rounded bg-[#9FC400]/40 select-none" aria-hidden />
                </span>
                <Lock className="w-3.5 h-3.5 text-[#8B957F] shrink-0" />
              </div>
            ))}
          </div>
          {(teaser.locked_count || 0) > 6 && (
            <div className="text-[11px] text-[#8B957F] font-bold mt-2">
              + {(teaser.locked_count || lockedLabels.length) - 6} more inside the full report
            </div>
          )}
        </div>
      )}

      {teaser.has_discovery && (
        <div className="mt-3 rounded-2xl p-5 flex items-center gap-4" style={{ background: "#0B1F14" }} data-testid="smt-discovery-teaser">
          <span className="w-12 h-12 rounded-full flex items-center justify-center shrink-0 animate-pulse" style={{ background: "rgba(204,255,0,0.12)", border: "1px solid rgba(204,255,0,0.35)" }}>
            <Compass className="w-5 h-5" style={{ color: LIME }} />
          </span>
          <div className="flex-1">
            <div className="text-[9.5px] font-extrabold tracking-[0.2em] uppercase" style={{ color: LIME }}>Something else was noticed…</div>
            <p className="text-white/85 text-[13px] leading-[1.55] font-semibold mt-1">
              The match whispered something about <span style={{ color: LIME }}>where {first} could play</span> —
              a possibility most people would never guess. It&rsquo;s waiting inside the full report.
            </p>
          </div>
          <Lock className="w-5 h-5 text-white/70 shrink-0" />
        </div>
      )}

      <button
        type="button"
        onClick={onUnlock}
        data-testid="smt-unlock-btn"
        className="mt-3 w-full inline-flex items-center justify-center gap-2 rounded-full py-3.5 font-barlow font-black uppercase tracking-[0.05em] text-[14px] transition-transform active:scale-[0.98] hover:brightness-95"
        style={{ background: "#12211A", color: LIME }}
      >
        Give every one of {first}&rsquo;s numbers its story <ChevronRight className="w-4 h-4" />
      </button>
    </div>
  );
}
