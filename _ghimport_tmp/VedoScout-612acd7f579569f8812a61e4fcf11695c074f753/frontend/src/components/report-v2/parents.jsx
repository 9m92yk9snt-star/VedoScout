// Parents Package — home drills, watch-together praise guide and the
// personal letter to the child. Renders only when full.parents_package exists.
import React from "react";
import { Home, Clapperboard, Mail, Play, XCircle, CheckCircle2 } from "lucide-react";
import { V2Card, V2Title } from "./sections";
import { canUseAuthorityProof } from "@/lib/authorityJoin.mjs";

function HomeDrillsCard({ drills }) {
  if (!drills?.length) return null;
  return (
    <V2Card testid="v2-home-drills-card">
      <V2Title icon={Home} right={<span className="text-[11px] font-extrabold tracking-[0.14em] text-[#1E5B3C] hidden md:block">NO PITCH NEEDED · JUST A BALL</span>}>
        Home Training · 10 Minutes a Day
      </V2Title>
      <div className="grid md:grid-cols-3 gap-4">
        {drills.map((d, i) => (
          <div key={i} data-testid={`v2-home-drill-${i}`} className="bg-[#FBF9F3] border border-[#E5DFCE] rounded-[12px] p-4">
            <div className="flex items-start justify-between gap-2">
              <div className="text-[13px] font-extrabold leading-snug uppercase tracking-[0.03em]">{d.name}</div>
              <span className="bg-[#12402A] text-[#CCFF00] font-barlow font-extrabold text-[11px] px-2 py-0.5 rounded-[6px] shrink-0">{d.minutes} MIN</span>
            </div>
            {d.equipment && <div className="text-[10.5px] text-[#8B957F] mt-1">You need: {d.equipment}</div>}
            <ol className="mt-2.5 space-y-1.5">
              {(d.steps || []).slice(0, 4).map((s, j) => (
                <li key={j} className="flex gap-2 text-[11.5px] leading-[1.5] text-[#3C4A40]">
                  <span className="w-4 h-4 rounded-full bg-[#E9F1E6] text-[#1E5B3C] text-[9px] font-extrabold flex items-center justify-center shrink-0 mt-0.5">{j + 1}</span>
                  {s}
                </li>
              ))}
            </ol>
            {d.success_sign && (
              <div className="mt-2.5 bg-[#F0F5EC] border border-[#DCE8D6] rounded-[9px] px-2.5 py-2 flex gap-1.5">
                <CheckCircle2 className="w-3 h-3 text-[#1E5B3C] shrink-0 mt-0.5" />
                <span className="text-[10.5px] leading-[1.45] text-[#3C4A40]">{d.success_sign}</span>
              </div>
            )}
            {d.targets && <div className="text-[9px] font-extrabold tracking-[0.1em] uppercase text-[#DD6B20] mt-2">Trains: {d.targets}</div>}
          </div>
        ))}
      </div>
    </V2Card>
  );
}

function WatchTogetherCard({ watch, onPlayAt, authority = false }) {
  if (!watch) return null;
  return (
    <V2Card testid="v2-watch-together-card">
      <V2Title icon={Clapperboard}>Watch the Video Together</V2Title>
      {watch.intro && <p className="text-[12px] text-[#68766B] leading-[1.55] mb-3">{watch.intro}</p>}
      {(watch.moments || []).slice(0, 3).map((m, i) => {
        // FIX 01 C01 — authority: no clickable proof without an authoritative ID.
        const proofable = canUseAuthorityProof(authority, m);
        const inner = (
          <>
            <span className="bg-[#12402A] text-[#CCFF00] font-barlow font-extrabold text-[12px] px-2 py-0.5 rounded-[6px] tabular-nums shrink-0 flex items-center gap-1">
              {proofable && <Play className="w-2.5 h-2.5 fill-[#CCFF00]" />} {m.timestamp}
            </span>
            <span className="text-[12px] leading-[1.55] text-[#3C4A40]">
              <b className="text-[#12402A]">Pause and say:</b> “{m.say_this}”
            </span>
          </>
        );
        return proofable ? (
          <button
            key={i}
            type="button"
            data-testid={`v2-wt-moment-${i}`}
            onClick={() => onPlayAt?.(m.timestamp, { evidenceId: m.evidence_id, eventId: m.event_id })}
            className="w-full text-left flex gap-3 items-start bg-[#FBF9F3] border border-[#E5DFCE] rounded-[11px] px-3.5 py-3 mb-2.5 group"
          >
            {inner}
          </button>
        ) : (
          <div
            key={i}
            data-testid={`v2-wt-moment-${i}`}
            className="w-full text-left flex gap-3 items-start bg-[#FBF9F3] border border-[#E5DFCE] rounded-[11px] px-3.5 py-3 mb-2.5"
          >
            {inner}
          </div>
        );
      })}
      {(watch.avoid || []).length > 0 && (
        <div className="mt-1 bg-[#FFF8E9] border border-[#F0E3C4] rounded-[11px] px-3.5 py-3">
          <div className="text-[10px] font-extrabold tracking-[0.12em] text-[#8A6D3B] mb-1.5">GOOD TO AVOID</div>
          {watch.avoid.slice(0, 2).map((a, i) => (
            <div key={i} className="flex gap-2 text-[11.5px] leading-[1.5] text-[#6b5a35] mb-1">
              <XCircle className="w-3 h-3 text-[#C89B18] shrink-0 mt-0.5" /> {a}
            </div>
          ))}
        </div>
      )}
    </V2Card>
  );
}

function LetterCard({ message, playerName }) {
  if (!message) return null;
  const first = String(playerName || "").split(" ")[0];
  return (
    <V2Card testid="v2-letter-card" className="!bg-[#FFFDF2]">
      <V2Title icon={Mail}>{first ? `A Message for ${first}` : "A Message for You"}</V2Title>
      <div className="px-1" style={{ fontFamily: "'Caveat', cursive" }}>
        {message.greeting && <div className="text-[24px] text-[#12402A] font-semibold">{message.greeting}</div>}
        <p data-testid="v2-letter-body" className="text-[21px] leading-[1.5] text-[#2C3B31] mt-1.5 whitespace-pre-line">{message.body}</p>
        {message.signoff && <div className="text-[22px] text-[#1E5B3C] font-semibold mt-3 text-right">{message.signoff}</div>}
      </div>
    </V2Card>
  );
}

export function ParentsPackageSection({ pack, playerName, onPlayAt }) {
  if (!pack) return null;
  const two = pack.watchTogether && pack.playerMessage;
  return (
    <div data-testid="v2-parents-package" className="space-y-4">
      <HomeDrillsCard drills={pack.homeDrills} />
      <div className={`grid gap-4 ${two ? "lg:grid-cols-[1.08fr_1fr]" : ""}`}>
        <WatchTogetherCard watch={pack.watchTogether} onPlayAt={onPlayAt} authority={!!pack.authority} />
        <LetterCard message={pack.playerMessage} playerName={playerName} />
      </div>
    </div>
  );
}
