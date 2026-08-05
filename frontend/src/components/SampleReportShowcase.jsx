// SampleReportShowcase — "the discovery journey" sample report carousel.
// Redesigned per /app/design_guidelines.json: layered depth, photo cards with
// green gradient overlays (never black), glass-morphism, glowing live elements.
import React, { useRef, useState } from "react";
import {
  ShieldCheck, ChevronLeft, ChevronRight, Target,
  ArrowRight, Sparkles, Lock, Eye, Zap, CheckCircle2,
  HeartHandshake, CalendarRange, Gauge, MessageCircle, Footprints,
} from "lucide-react";

const FOREST = "#12402A";
const FOREST_L = "#1F4F2F";
const LIME = "#CCFF00";
const GOLD = "#F5C443";
const ASSET = process.env.REACT_APP_BACKEND_URL;

const NOISE =
  "url(\"data:image/svg+xml,%3Csvg viewBox='0 0 200 200' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='2'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)' opacity='0.35'/%3E%3C/svg%3E\")";

/* ---------- shared shell ---------- */
function Card({ children, testid, className = "", style = {} }) {
  return (
    <div
      data-testid={testid}
      data-sample-card
      className={`snap-center shrink-0 w-[86vw] max-w-[380px] sm:w-[380px] rounded-3xl overflow-hidden shadow-[0_22px_55px_-20px_rgba(18,64,42,0.5)] flex flex-col group ${className}`}
      style={{ minHeight: 440, ...style }}
    >
      {children}
    </div>
  );
}

function Grain({ opacity = 0.05 }) {
  return <div aria-hidden className="absolute inset-0 pointer-events-none" style={{ backgroundImage: NOISE, opacity }} />;
}

function Kicker({ children, color = "#75816F", page }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-[9.5px] font-black uppercase tracking-[0.22em]" style={{ color }}>{children}</span>
      {page && <span className="text-[8.5px] font-black tracking-[0.14em]" style={{ color, opacity: 0.55 }}>{page}</span>}
    </div>
  );
}

/* ---------- 1 · dossier (dark, exclusive) ---------- */
function OverviewCard() {
  return (
    <Card testid="sample-card-overview" style={{ background: `linear-gradient(160deg, ${FOREST} 0%, #0E3322 100%)`, border: "1px solid rgba(204,255,0,0.14)" }}>
      <div className="relative flex-1 flex flex-col p-6">
        <Grain />
        <div aria-hidden className="absolute -top-16 -right-12 w-56 h-56 rounded-full pointer-events-none" style={{ background: "radial-gradient(circle, rgba(204,255,0,0.22) 0%, transparent 68%)" }} />
        <Kicker color={LIME} page="1 / 11">Official Scout Dossier</Kicker>
        <div className="relative mt-5">
          <div className="inline-flex items-center gap-2 bg-white/10 backdrop-blur-md border border-white/15 rounded-full px-3 py-1.5">
            <span className="w-2 h-2 rounded-full" style={{ background: LIME, animation: "smp-blink 1.8s ease-in-out infinite" }} />
            <span className="font-barlow font-black uppercase text-white text-[15px] leading-none tracking-tight">
              Mikkel <span className="blur-[6px] select-none">Andersen</span>
            </span>
          </div>
          <div className="flex gap-1.5 mt-2.5">
            {["U12", "Winger", "Right foot"].map((c) => (
              <span key={c} className="text-[9px] font-black uppercase tracking-[0.1em] bg-white/10 text-white/80 px-2 py-1 rounded-md">{c}</span>
            ))}
          </div>
        </div>
        <div className="relative mt-5 flex items-end gap-4">
          <div className="font-barlow font-black leading-none text-[86px]" style={{ color: LIME, textShadow: "0 0 38px rgba(204,255,0,0.45)", animation: "smp-scoreglow 2.8s ease-in-out infinite" }}>
            8.2
          </div>
          <div className="pb-3">
            <div className="text-[9px] font-black uppercase tracking-[0.18em] text-white/55">Overall / 10</div>
            <div className="text-[10px] font-bold mt-0.5" style={{ color: GOLD }}>vs U12 expectations</div>
          </div>
        </div>
        <p className="relative text-[13px] leading-relaxed mt-3 italic" style={{ color: GOLD }}>
          "A brave, direct winger who demands the ball — clearly above U12 expectations in 1v1."
        </p>
        <div className="relative mt-auto pt-4">
          <div className="rounded-2xl p-3.5 bg-white/10 backdrop-blur-md border border-white/15">
            <div className="flex items-center gap-2">
              <ShieldCheck className="w-4 h-4" style={{ color: LIME }} />
              <span className="text-[9.5px] font-black uppercase tracking-[0.14em] text-white">Identity locked</span>
            </div>
            <p className="text-[10.5px] text-white/70 leading-relaxed mt-1">
              Marked with 10 taps · optical tracking · dual verification. This is about <span className="text-white font-bold">your child</span> — never a lookalike.
            </p>
          </div>
        </div>
      </div>
    </Card>
  );
}

/* ---------- 2 · four pillars (light, analytical-warm) ---------- */
function PillarBar({ label, score, meaning, delay }) {
  return (
    <div>
      <div className="flex items-baseline justify-between">
        <span className="text-[11px] font-extrabold uppercase tracking-[0.1em] text-[#3D4A38]">{label}</span>
        <span className="font-barlow font-black text-[18px]" style={{ color: FOREST }}>{score.toFixed(1)}</span>
      </div>
      <div className="relative h-2.5 rounded-full mt-1.5" style={{ background: "#12402A22" }}>
        <div
          className="absolute inset-y-0 left-0 rounded-full"
          style={{
            width: `${score * 10}%`,
            background: `linear-gradient(90deg, ${FOREST_L}, ${LIME})`,
            transformOrigin: "left",
            animation: `smp-fill 1s ${delay}s cubic-bezier(0.22,1,0.36,1) both`,
          }}
        />
        <span
          aria-hidden
          className="absolute top-1/2 -translate-y-1/2 w-3.5 h-3.5 rounded-full"
          style={{
            left: `calc(${score * 10}% - 7px)`,
            background: LIME,
            boxShadow: "0 0 12px rgba(204,255,0,0.9), 0 0 3px rgba(18,64,42,0.5)",
            animation: `smp-pop 0.4s ${delay + 0.85}s ease-out both`,
          }}
        />
      </div>
      <p className="text-[11px] text-[#75816F] italic mt-1 leading-snug">{meaning}</p>
    </div>
  );
}

function PillarsCard() {
  return (
    <Card testid="sample-card-pillars" className="bg-[#FBF9F3]" style={{ border: "1px solid rgba(18,64,42,0.12)" }}>
      <div className="relative flex-1 flex flex-col p-6">
        <Grain opacity={0.03} />
        <Kicker page="2 / 11">The numbers — translated into truth</Kicker>
        <h3 className="font-barlow font-black uppercase tracking-tight text-[21px] text-[#182016] mt-0.5">Things He Never Knew</h3>
        <div className="mt-5 space-y-4">
          <PillarBar label="Technical" score={8.4} meaning="His first touch buys him time others don't have." delay={0.1} />
          <PillarBar label="Game intelligence" score={7.6} meaning="Sees the pass early — plays it a beat later." delay={0.3} />
          <PillarBar label="Physical" score={7.9} meaning="Wins the metres that decide a 1v1." delay={0.5} />
          <PillarBar label="Mentality" score={8.1} meaning="A mistake switches him on — not off." delay={0.7} />
        </div>
        <div className="relative mt-auto pt-4">
          <div className="rounded-2xl p-3.5 flex items-center gap-3" style={{ background: FOREST }}>
            <Sparkles className="w-5 h-5 shrink-0" style={{ color: LIME }} />
            <p className="text-[11.5px] text-white/85 leading-snug">
              <span className="font-black text-white">Top 15% for his age group</span> — and now he knows exactly <span className="font-black" style={{ color: LIME }}>why</span>.
            </p>
          </div>
        </div>
      </div>
    </Card>
  );
}

/* ---------- 3 · superpowers (dark accent, layered) ---------- */
function StrengthsCard() {
  const strengths = [
    "Attacks his defender 1v1 without hesitation",
    "First touch opens the field — rarely needs a second",
    "Keeps working after losing the ball",
  ];
  return (
    <Card testid="sample-card-strengths" style={{ background: `linear-gradient(165deg, ${FOREST_L} 0%, ${FOREST} 100%)`, border: "1px solid rgba(204,255,0,0.12)" }}>
      <div className="relative flex-1 flex flex-col p-6">
        <Grain />
        <Kicker color={LIME} page="3 / 11">What the scout saw</Kicker>
        <h3 className="font-barlow font-black uppercase tracking-tight text-[21px] text-white mt-0.5 leading-tight">
          Superpowers he<br />didn&apos;t know he had
        </h3>
        <div className="mt-4 space-y-2.5">
          {strengths.map((s, i) => (
            <div key={s} className="flex items-start gap-2.5 rounded-2xl p-3 bg-white/10 backdrop-blur-md border border-white/10" style={{ animation: `smp-rise 0.5s ${0.12 * i}s ease-out both` }}>
              <span className="shrink-0 w-6 h-6 rounded-full flex items-center justify-center mt-0.5" style={{ background: "rgba(204,255,0,0.18)" }}>
                <Zap className="w-3.5 h-3.5" style={{ color: LIME }} />
              </span>
              <p className="text-[12.5px] text-white/90 leading-snug">{s}</p>
            </div>
          ))}
        </div>
        <div className="relative mt-auto pt-4">
          <div className="rounded-2xl p-3.5 -rotate-1 group-hover:rotate-0 transition-transform duration-500" style={{ background: "#0C2A1A", border: `1px solid ${GOLD}55`, boxShadow: "0 8px 24px -8px rgba(0,0,0,0.5)" }}>
            <div className="flex items-center gap-2">
              <Target className="w-4 h-4" style={{ color: GOLD }} />
              <span className="text-[9.5px] font-black uppercase tracking-[0.16em]" style={{ color: GOLD }}>The golden key</span>
            </div>
            <p className="text-[12px] text-white/80 leading-snug mt-1">
              Scanning before receiving — <span className="font-bold text-white">the one habit that unlocks his next level</span>. The plan shows how.
            </p>
          </div>
        </div>
      </div>
    </Card>
  );
}

/* ---------- 4 · physical reality (photo: muddy boots) ---------- */
function PaceCardSample() {
  return (
    <Card testid="sample-card-pace">
      <div className="relative flex-1 flex flex-col p-6 overflow-hidden">
        <img
          src={`${ASSET}/api/static/landing/carousel-bg-2.jpg`}
          alt=""
          loading="lazy"
          className="absolute inset-0 w-full h-full object-cover transition-transform duration-700 group-hover:scale-105"
          onError={(e) => { e.currentTarget.style.display = "none"; }}
        />
        <div aria-hidden className="absolute inset-0" style={{ background: `linear-gradient(180deg, ${FOREST}E6 0%, ${FOREST}66 45%, ${FOREST}F2 100%)` }} />
        <svg aria-hidden className="absolute inset-0 w-full h-full pointer-events-none" viewBox="0 0 380 440" fill="none">
          <path d="M-10 340 C 90 300, 150 380, 230 320 S 360 220, 400 250" stroke={LIME} strokeWidth="2" strokeDasharray="6 8" opacity="0.5" style={{ animation: "smp-dash 6s linear infinite" }} />
        </svg>
        <div className="relative">
          <Kicker color={LIME} page="4 / 11">Measured — never guessed</Kicker>
          <h3 className="font-barlow font-black uppercase tracking-tight text-[21px] text-white mt-0.5">How fast is he really?</h3>
        </div>
        <div className="relative mt-6">
          <div className="flex items-baseline gap-2">
            <span className="font-barlow font-black text-[68px] leading-none" style={{ color: LIME, textShadow: "0 0 34px rgba(204,255,0,0.5)" }}>24.1</span>
            <span className="text-white font-black text-[15px]">KM/H</span>
          </div>
          <div className="text-[9.5px] font-black uppercase tracking-[0.18em] text-white/60 mt-1">Top speed · from his own match</div>
          <div className="flex gap-2 mt-4">
            {[["7", "Sprints"], ["412 m", "Tracked"]].map(([v, l]) => (
              <div key={l} className="rounded-2xl px-4 py-2.5 bg-white/10 backdrop-blur-md border border-white/15 text-center">
                <div className="font-barlow font-black text-[20px] leading-none" style={{ color: LIME }}>{v}</div>
                <div className="text-[8.5px] font-black uppercase tracking-[0.12em] text-white/60 mt-1">{l}</div>
              </div>
            ))}
          </div>
        </div>
        <div className="relative mt-auto pt-4">
          <p className="text-[12.5px] text-white/85 leading-snug italic">
            "Faster than most wingers his age — and the report shows the <span className="font-bold not-italic" style={{ color: LIME }}>exact sprint</span> where he proved it."
          </p>
          <div className="flex items-center gap-2 mt-2.5">
            <Gauge className="w-3.5 h-3.5 shrink-0" style={{ color: LIME }} />
            <p className="text-[10px] text-white/55">Pixel-level tracking of your marked player — never invented.</p>
          </div>
        </div>
      </div>
    </Card>
  );
}

/* ---------- 5 · parent curiosity (photo: golden hour parent+child) ---------- */
function CuriosityCard() {
  const rows = [
    "Which foot does he really trust under pressure?",
    "What happens in the 8 seconds after he loses the ball?",
    "The habit a scout would notice first?",
  ];
  return (
    <Card testid="sample-card-curiosity">
      <div className="relative flex-1 flex flex-col p-6 overflow-hidden">
        <img
          src={`${ASSET}/api/blog/uploads/cover-bounce-back.jpg`}
          alt=""
          loading="lazy"
          className="absolute inset-0 w-full h-full object-cover transition-transform duration-700 group-hover:scale-105"
          onError={(e) => { e.currentTarget.style.display = "none"; }}
        />
        <div aria-hidden className="absolute inset-0" style={{ background: `linear-gradient(180deg, ${FOREST}59 0%, ${FOREST}8C 45%, ${FOREST}F5 100%)` }} />
        <div className="relative">
          <Kicker color="#EAF4D0" page="5 / 11">The things you&apos;ll finally know</Kicker>
          <h3 className="font-barlow font-black uppercase tracking-tight text-[21px] text-white mt-0.5" style={{ textShadow: "0 2px 12px rgba(10,26,16,0.55)" }}>
            What you&apos;ll discover
          </h3>
        </div>
        <div className="relative mt-auto space-y-2">
          {rows.map((q, i) => (
            <div key={q} className="rounded-2xl px-3.5 py-2.5 bg-white/12 backdrop-blur-md border border-white/20" style={{ animation: `smp-rise 0.5s ${0.12 * i}s ease-out both` }}>
              <p className="text-[12px] font-bold text-white leading-snug">{q}</p>
              <div className="flex items-center gap-1.5 mt-1">
                <Lock className="w-3 h-3 shrink-0 text-white/60" style={{ animation: "smp-blink 2.2s ease-in-out infinite" }} />
                <span className="text-[10.5px] text-white/70 blur-[4px] select-none">The answer is waiting in the report</span>
              </div>
            </div>
          ))}
          <div className="flex items-center justify-center gap-2 pt-2">
            <span className="w-1.5 h-1.5 rounded-full" style={{ background: LIME, animation: "smp-blink 1.6s ease-in-out infinite" }} />
            <p className="text-[10.5px] font-black uppercase tracking-[0.14em]" style={{ color: LIME }}>Unlock the full picture — with the clip to prove it</p>
          </div>
        </div>
      </div>
    </Card>
  );
}

/* ---------- 6 · honest answers (light, warm) ---------- */
function ParentsCard() {
  const rows = [
    ["Does he demand the ball?", "11 touches · always available"],
    ["Is he brave?", "8.5 / 10 — takes his man on"],
    ["After a mistake?", "Wins the ball straight back"],
    ["Work without the ball?", "7.0 — and growing"],
  ];
  return (
    <Card testid="sample-card-parents" className="bg-[#FBF9F3]" style={{ border: "1px solid rgba(18,64,42,0.12)" }}>
      <div className="relative flex-1 flex flex-col p-6">
        <Grain opacity={0.03} />
        <Kicker page="6 / 11">The questions you whisper</Kicker>
        <h3 className="font-barlow font-black uppercase tracking-tight text-[21px] text-[#182016] mt-0.5">What parents ask</h3>
        <div className="mt-4 space-y-2">
          {rows.map(([k, v], i) => (
            <div key={k} className="flex items-center justify-between gap-3 bg-white border border-[#12402A1A] rounded-2xl px-3.5 py-2.5 hover:border-[#12402A40] transition-colors" style={{ animation: `smp-rise 0.5s ${0.1 * i}s ease-out both` }}>
              <span className="text-[10.5px] font-extrabold uppercase tracking-[0.08em] text-[#75816F]">{k}</span>
              <span className="font-barlow font-black text-[14px] text-right" style={{ color: FOREST }}>{v}</span>
            </div>
          ))}
        </div>
        <div className="relative mt-auto pt-4 flex items-start gap-2.5">
          <HeartHandshake className="w-4 h-4 mt-0.5 shrink-0" style={{ color: FOREST_L }} />
          <p className="text-[11px] text-[#8A937F] leading-relaxed">
            Answered honestly, with warmth. If there isn&apos;t enough evidence, the report says so — instead of guessing.
          </p>
        </div>
      </div>
    </Card>
  );
}

/* ---------- 7 · 90-day plan (dark timeline) ---------- */
function PlanCard() {
  const nodes = [
    ["Today", "Scanning before receiving — 10 min, 3×/week"],
    ["Week 4", "First touch under pressure — wall drills"],
    ["Week 12", "1v1 end product — final pass & finish"],
  ];
  return (
    <Card testid="sample-card-plan" style={{ background: `linear-gradient(160deg, ${FOREST} 0%, #0E3322 100%)`, border: "1px solid rgba(204,255,0,0.14)" }}>
      <div className="relative flex-1 flex flex-col p-6">
        <Grain />
        <Kicker color={LIME} page="7 / 11">Personal roadmap</Kicker>
        <h3 className="font-barlow font-black uppercase tracking-tight text-[21px] text-white mt-0.5 leading-tight">
          A map to who<br />he&apos;s becoming
        </h3>
        <div className="relative mt-5 pl-6 flex-1">
          <div aria-hidden className="absolute left-[9px] top-2 bottom-3 w-0 border-l-2 border-dashed" style={{ borderColor: "rgba(204,255,0,0.5)" }} />
          <div className="space-y-4">
            {nodes.map(([k, t], i) => (
              <div key={k} className="relative" style={{ animation: `smp-rise 0.5s ${0.14 * i}s ease-out both` }}>
                <span aria-hidden className="absolute -left-6 top-0.5 w-[18px] h-[18px] rounded-full border-2 flex items-center justify-center"
                  style={i === 0
                    ? { background: LIME, borderColor: LIME, boxShadow: "0 0 16px rgba(204,255,0,0.75)" }
                    : { background: FOREST, borderColor: "rgba(204,255,0,0.5)" }}>
                  {i === 0 && <span className="w-1.5 h-1.5 rounded-full" style={{ background: FOREST }} />}
                </span>
                <div className="text-[9.5px] font-black uppercase tracking-[0.16em]" style={{ color: i === 0 ? LIME : "rgba(255,255,255,0.55)" }}>{k}</div>
                <div className="mt-1 rounded-2xl p-3 bg-white/10 backdrop-blur-md border border-white/10">
                  <p className="text-[12px] text-white/90 leading-snug">{t}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
        <div className="relative mt-auto pt-4 flex items-start gap-2.5">
          <CalendarRange className="w-4 h-4 mt-0.5 shrink-0" style={{ color: LIME }} />
          <p className="text-[10.5px] text-white/60 leading-relaxed">
            Plus 3 countable <span className="font-bold text-white/90">next-match missions</span> for the weekend game.
          </p>
        </div>
      </div>
    </Card>
  );
}

/* ---------- 8 · the road ahead (photo: dusk silhouette, dream) ---------- */
function RoadCard() {
  return (
    <Card testid="sample-card-road">
      <div className="relative flex-1 flex flex-col p-6 overflow-hidden">
        <img
          src={`${ASSET}/api/static/landing/carousel-bg-1.jpg`}
          alt=""
          loading="lazy"
          className="absolute inset-0 w-full h-full object-cover transition-transform duration-700 group-hover:scale-105"
          onError={(e) => { e.currentTarget.style.display = "none"; }}
        />
        <div aria-hidden className="absolute inset-0" style={{ background: `linear-gradient(180deg, ${FOREST_L}4D 0%, ${FOREST}80 50%, ${FOREST}F0 100%)` }} />
        <div aria-hidden className="absolute -bottom-20 left-1/2 -translate-x-1/2 w-72 h-72 rounded-full pointer-events-none" style={{ background: "radial-gradient(circle, rgba(245,196,67,0.3) 0%, transparent 65%)" }} />
        <div className="relative">
          <Kicker color={GOLD} page="8 / 11">Where this can lead</Kicker>
          <h3 className="font-barlow font-black uppercase tracking-tight text-[26px] text-white mt-0.5 leading-[1.02]" style={{ textShadow: "0 2px 14px rgba(10,26,16,0.6)" }}>
            The road<br />ahead
          </h3>
        </div>
        <div className="relative mt-auto">
          <p className="font-barlow font-black uppercase text-[17px] leading-tight" style={{ color: GOLD, textShadow: "0 2px 10px rgba(10,26,16,0.6)" }}>
            From the local pitch<br />to the scout&apos;s notebook.
          </p>
          <div className="mt-3 space-y-2">
            {[["Today", "One clip — the game finally on record"], ["This season", "Training with purpose, not guesses"], ["When he's ready", "Visible to real scouts who are looking"]].map(([k, t], i) => (
              <div key={k} className="flex items-start gap-2.5" style={{ animation: `smp-rise 0.5s ${0.12 * i}s ease-out both` }}>
                <span aria-hidden className="w-2 h-2 rounded-full shrink-0 mt-1" style={i === 0 ? { background: GOLD, boxShadow: "0 0 10px rgba(245,196,67,0.9)" } : { background: "rgba(245,196,67,0.45)" }} />
                <div className="min-w-0">
                  <div className="text-[9.5px] font-black uppercase tracking-[0.14em] leading-none" style={{ color: GOLD }}>{k}</div>
                  <p className="text-[11.5px] text-white/85 leading-snug mt-0.5">{t}</p>
                </div>
              </div>
            ))}
          </div>
          <div className="flex items-start gap-2 mt-3.5 pt-3 border-t border-white/15">
            <Footprints className="w-3.5 h-3.5 mt-0.5 shrink-0" style={{ color: GOLD }} />
            <p className="text-[10px] text-white/60 leading-relaxed">No promises — just a clear next step. Every step is <span className="font-bold text-white/85">his own</span>. We light the road.</p>
          </div>
        </div>
      </div>
    </Card>
  );
}

/* ---------- 9 · a real scout replied (light, human) ---------- */
function ScoutReplyCard() {
  return (
    <Card testid="sample-card-scoutreply" className="bg-[#FBF9F3]" style={{ border: "1px solid rgba(18,64,42,0.12)", boxShadow: "0 22px 55px -20px rgba(18,64,42,0.5)" }}>
      <div className="relative flex-1 flex flex-col p-6">
        <Grain opacity={0.03} />
        <Kicker page="9 / 11">Not just software — real people</Kicker>
        <h3 className="font-barlow font-black uppercase tracking-tight text-[21px] text-[#182016] mt-0.5">A real scout replied</h3>
        <div className="mt-4 flex items-start gap-3">
          <div className="relative shrink-0">
            <div className="w-11 h-11 rounded-full flex items-center justify-center font-barlow font-black text-[14px]" style={{ background: `linear-gradient(140deg, ${FOREST_L}, ${FOREST})`, color: LIME, boxShadow: "0 6px 16px -6px rgba(18,64,42,0.6)" }}>JK</div>
            <span aria-hidden className="absolute -bottom-0.5 -right-0.5 w-3.5 h-3.5 rounded-full border-2 border-[#FBF9F3]" style={{ background: "#3BA55D", animation: "smp-blink 2s ease-in-out infinite" }} />
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-baseline gap-2">
              <span className="text-[11.5px] font-black text-[#182016]">J. K.</span>
              <span className="text-[9px] font-black uppercase tracking-[0.1em] text-[#75816F]">Professional scout · 14 yrs</span>
            </div>
            <div className="mt-1.5 rounded-2xl rounded-tl-md bg-white border border-[#12402A1A] p-3.5 shadow-sm" style={{ animation: "smp-rise 0.5s 0.1s ease-out both" }}>
              <p className="text-[12.5px] text-[#3D4A38] leading-relaxed">
                "I watched the clip twice. The way he attacks the back post at <span className="font-bold" style={{ color: FOREST }}>07:12</span> — that&apos;s not taught, that&apos;s instinct. Keep him wide. Keep him brave."
              </p>
            </div>
            <div className="mt-2 rounded-2xl rounded-tl-md p-3.5" style={{ background: FOREST, animation: "smp-rise 0.5s 0.4s ease-out both" }}>
              <p className="text-[12px] text-white/90 leading-snug">
                One drill from me: <span className="font-bold" style={{ color: LIME }}>back-post timing, 2×/week</span>. Small habit — big difference at trials.
              </p>
            </div>
            <div className="flex items-center gap-1.5 mt-2 pl-1" style={{ animation: "smp-rise 0.5s 0.65s ease-out both" }}>
              {[0, 1, 2].map((i) => (
                <span key={i} className="w-1.5 h-1.5 rounded-full bg-[#75816F]" style={{ animation: `smp-blink 1.2s ${i * 0.2}s ease-in-out infinite` }} />
              ))}
              <span className="text-[9.5px] text-[#8A937F] ml-1">scout is typing…</span>
            </div>
          </div>
        </div>
        <div className="relative mt-auto pt-4 flex items-start gap-2.5">
          <MessageCircle className="w-4 h-4 mt-0.5 shrink-0" style={{ color: FOREST_L }} />
          <p className="text-[11px] text-[#8A937F] leading-relaxed">
            A real, experienced scout reads the report and writes back — <span className="font-bold text-[#3D4A38]">personal words about your child&apos;s game</span>, never a template.
          </p>
        </div>
      </div>
    </Card>
  );
}

/* ---------- 10 · spotted in the scout library (radar) ---------- */
function LibraryCard() {
  return (
    <Card testid="sample-card-library" style={{ background: `linear-gradient(150deg, ${FOREST} 0%, #16241B 100%)`, border: "1px solid rgba(204,255,0,0.14)" }}>
      <div className="relative flex-1 flex flex-col p-6 overflow-hidden">
        <Grain />
        <Kicker color={LIME} page="10 / 11">Being seen changes everything</Kicker>
        <h3 className="font-barlow font-black uppercase tracking-tight text-[24px] text-white mt-0.5 leading-tight">
          You&apos;ve been<br />spotted
        </h3>
        {/* radar */}
        <div className="relative mx-auto mt-4 mb-1" style={{ width: 172, height: 172 }}>
          {[172, 124, 76].map((d, i) => (
            <span key={d} aria-hidden className="absolute rounded-full border"
              style={{
                width: d, height: d, left: (172 - d) / 2, top: (172 - d) / 2,
                borderColor: "rgba(204,255,0,0.25)",
                animation: `smp-radar 3s ${i * 0.5}s ease-out infinite`,
              }} />
          ))}
          <span aria-hidden className="absolute rounded-full" style={{ width: 14, height: 14, left: 79, top: 79, background: LIME, boxShadow: "0 0 22px rgba(204,255,0,0.9)", animation: "smp-blink 1.6s ease-in-out infinite" }} />
          <span aria-hidden className="absolute inset-0 rounded-full" style={{ background: "conic-gradient(from 0deg, rgba(204,255,0,0.18), transparent 70%)", animation: "smp-spin 4s linear infinite" }} />
        </div>
        <div className="relative rounded-2xl p-3.5 bg-white/10 backdrop-blur-md border border-white/15" style={{ animation: "smp-rise 0.5s 0.2s ease-out both" }}>
          <div className="flex items-start gap-2">
            <Eye className="w-4 h-4 shrink-0 mt-0.5" style={{ color: LIME }} />
            <p className="text-[11.5px] text-white/90 leading-snug">
              A scout opened his profile <span className="font-bold text-white">today</span>{" "}
              <span className="text-[8.5px] font-black uppercase tracking-[0.1em] px-2 py-0.5 rounded-full align-middle whitespace-nowrap" style={{ background: "rgba(204,255,0,0.16)", color: LIME }}>3× this month</span>
            </p>
          </div>
          <p className="text-[10px] text-white/55 mt-1.5 pl-6">— while he was at training, dreaming about it.</p>
        </div>
        <div className="relative mt-auto pt-3 flex items-start gap-2.5">
          <ShieldCheck className="w-4 h-4 mt-0.5 shrink-0" style={{ color: LIME }} />
          <p className="text-[10.5px] text-white/60 leading-relaxed">
            Only with your family&apos;s consent — in the library <span className="font-bold text-white/90">real scouts search</span>. You decide what they see.
          </p>
        </div>
      </div>
    </Card>
  );
}

/* ---------- 11 · CTA ---------- */
function CtaCard({ onPrimaryCta }) {
  return (
    <Card testid="sample-card-cta">
      <div className="relative flex-1 flex flex-col p-6 overflow-hidden">
        <img
          src={`${ASSET}/api/static/landing/finalcta-stadium.jpg`}
          alt=""
          loading="lazy"
          className="absolute inset-0 w-full h-full object-cover transition-transform duration-700 group-hover:scale-105"
          onError={(e) => { e.currentTarget.style.display = "none"; }}
        />
        <div aria-hidden className="absolute inset-0" style={{ background: `linear-gradient(180deg, ${FOREST}A6 0%, ${FOREST}40 45%, ${FOREST}F2 100%)` }} />
        <div className="relative flex items-center gap-2">
          <Sparkles className="w-4 h-4" style={{ color: GOLD }} />
          <span className="text-[10px] font-black uppercase tracking-[0.22em]" style={{ color: GOLD }}>Your story is next</span>
        </div>
        <h3 className="relative font-barlow font-black uppercase text-white text-[27px] leading-[1.02] mt-3" style={{ textShadow: "0 2px 14px rgba(10,26,16,0.55)" }}>
          It starts with<br />one video.<br />
          <span style={{ color: LIME }}>The rest is<br />your story.</span>
        </h3>
        <div className="relative mt-auto pt-6">
          <p className="text-[12.5px] text-white/85 leading-relaxed mb-4">
            The lights are already on. The next report we write could be about <span className="font-bold text-white">you</span>.
          </p>
          <button
            type="button"
            data-testid="sample-report-cta"
            onClick={onPrimaryCta}
            className="relative overflow-hidden w-full inline-flex items-center justify-center gap-2 font-barlow font-black uppercase tracking-[0.12em] text-[14px] px-6 py-4 rounded-2xl transition-transform active:scale-[0.98] hover:scale-[1.02]"
            style={{ background: LIME, color: "#0D2818", animation: "smp-cta-glow 2.6s ease-in-out infinite" }}
          >
            <span aria-hidden className="absolute inset-y-0 w-1/3 bg-white/40 pointer-events-none" style={{ animation: "smp-cta-shine 2.8s ease-in-out infinite" }} />
            Upload your video <ArrowRight className="w-4 h-4" />
          </button>
          <p className="text-center text-[10px] text-white/65 mt-2.5">Free preview · no card needed to start</p>
        </div>
      </div>
    </Card>
  );
}

/* ---------- main section ---------- */
export const SampleReportShowcase = ({ onPrimaryCta }) => {
  const scrollerRef = useRef(null);
  const [active, setActive] = useState(0);
  const [edge, setEdge] = useState({ start: true, end: false });
  const cards = [OverviewCard, PillarsCard, StrengthsCard, PaceCardSample, CuriosityCard, ParentsCard, PlanCard, RoadCard, ScoutReplyCard, LibraryCard];

  const handleScroll = () => {
    const el = scrollerRef.current;
    if (!el) return;
    const card = el.querySelector("[data-sample-card]");
    if (!card) return;
    const w = card.offsetWidth + 16;
    setActive(Math.min(cards.length, Math.round(el.scrollLeft / w)));
    const max = el.scrollWidth - el.clientWidth;
    setEdge({ start: el.scrollLeft <= 8, end: el.scrollLeft >= max - 8 });
  };

  const nudge = (dir) => {
    const el = scrollerRef.current;
    if (!el) return;
    const card = el.querySelector("[data-sample-card]");
    const step = (card?.offsetWidth || 380) + 16;
    const max = el.scrollWidth - el.clientWidth;
    el.scrollTo({ left: Math.max(0, Math.min(max, el.scrollLeft + dir * step)), behavior: "smooth" });
  };

  return (
    <section id="sample-report" data-testid="sample-report-showcase" className="relative py-14 sm:py-20 overflow-hidden">
      <style>{`
        @keyframes smp-fill { from { transform: scaleX(0); } to { transform: scaleX(1); } }
        @keyframes smp-pop { from { opacity: 0; transform: translateY(-50%) scale(0); } to { opacity: 1; transform: translateY(-50%) scale(1); } }
        @keyframes smp-rise { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
        @keyframes smp-scoreglow { 0%,100% { text-shadow: 0 0 22px rgba(204,255,0,0.35); } 50% { text-shadow: 0 0 44px rgba(204,255,0,0.75); } }
        @keyframes smp-blink { 0%,100% { opacity: 1; } 50% { opacity: 0.35; } }
        @keyframes smp-dash { to { stroke-dashoffset: -140; } }
        @keyframes smp-radar { 0% { transform: scale(0.6); opacity: 0.9; } 100% { transform: scale(1.25); opacity: 0; } }
        @keyframes smp-spin { to { transform: rotate(360deg); } }
        @keyframes smp-cta-shine { 0% { transform: translateX(-120%) skewX(-18deg); } 60%, 100% { transform: translateX(220%) skewX(-18deg); } }
        @keyframes smp-cta-glow { 0%, 100% { box-shadow: 0 0 22px rgba(204,255,0,0.35); } 50% { box-shadow: 0 0 40px rgba(204,255,0,0.65); } }
      `}</style>
      <div className="max-w-7xl mx-auto px-5 sm:px-6">
        <div className="flex items-end justify-between gap-4">
          <div>
            <span className="text-[10px] font-black uppercase tracking-[0.24em] text-[#2D6B3D]">Proof before you pay</span>
            <h2 className="font-barlow font-black uppercase tracking-tight text-[26px] sm:text-4xl text-ink leading-[1.05] mt-1">
              See a real report
            </h2>
            <p className="text-sm text-ink/60 mt-2 max-w-md">
              An anonymized sample — swipe through the discoveries one clip unlocks. Eleven pages of a player&apos;s story.
            </p>
          </div>
          <div className="hidden sm:flex gap-2">
            <button type="button" aria-label="Previous card" data-testid="sample-prev" onClick={() => nudge(-1)}
              className="w-10 h-10 rounded-full border border-ink/15 flex items-center justify-center text-ink/60 hover:border-forest hover:text-forest transition-colors">
              <ChevronLeft className="w-4 h-4" />
            </button>
            <button type="button" aria-label="Next card" data-testid="sample-next" onClick={() => nudge(1)}
              className="w-10 h-10 rounded-full border border-ink/15 flex items-center justify-center text-ink/60 hover:border-forest hover:text-forest transition-colors">
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>

      <div className="relative">
        <div
          ref={scrollerRef}
          onScroll={handleScroll}
          data-testid="sample-report-scroller"
          className="mt-7 flex gap-4 overflow-x-auto snap-x snap-mandatory scrollbar-hide px-5 sm:px-6 pb-3"
          style={{ scrollPaddingLeft: 20, WebkitOverflowScrolling: "touch", overscrollBehaviorX: "contain", transform: "translateZ(0)" }}
        >
          <div className="hidden lg:block shrink-0" style={{ width: "calc((100vw - 1280px) / 2)" }} />
          {cards.map((C, i) => <C key={i} onPrimaryCta={onPrimaryCta} />)}
          <CtaCard onPrimaryCta={onPrimaryCta} />
          <div className="shrink-0 w-2" />
        </div>
        {/* Centered swipe arrows — mobile only */}
        <style>{`
          @keyframes smp-sarrow-pulse { 0%,100% { box-shadow: 0 0 10px rgba(204,255,0,0.25), 0 4px 18px rgba(0,0,0,0.35); } 50% { box-shadow: 0 0 24px rgba(204,255,0,0.6), 0 4px 18px rgba(0,0,0,0.35); } }
          @keyframes smp-sarrow-nudge-l { 0%,100% { transform: translateX(0); } 50% { transform: translateX(-3px); } }
          @keyframes smp-sarrow-nudge-r { 0%,100% { transform: translateX(0); } 50% { transform: translateX(3px); } }
        `}</style>
        <button
          type="button" aria-label="Previous card" data-testid="sample-arrow-prev" onClick={() => nudge(-1)}
          disabled={edge.start}
          className={`sm:hidden absolute left-1.5 top-1/2 -translate-y-1/2 z-20 w-10 h-10 rounded-full flex items-center justify-center backdrop-blur-md active:scale-90 transition-all duration-300 ${edge.start ? "opacity-25 pointer-events-none" : "opacity-100"}`}
          style={{ background: "rgba(18,64,42,0.7)", border: "1px solid rgba(204,255,0,0.55)", animation: edge.start ? "none" : "smp-sarrow-pulse 2.2s ease-in-out infinite" }}
        >
          <ChevronLeft className="w-5 h-5" style={{ color: "#CCFF00", animation: edge.start ? "none" : "smp-sarrow-nudge-l 1.1s ease-in-out infinite" }} />
        </button>
        <button
          type="button" aria-label="Next card" data-testid="sample-arrow-next" onClick={() => nudge(1)}
          disabled={edge.end}
          className={`sm:hidden absolute right-1.5 top-1/2 -translate-y-1/2 z-20 w-10 h-10 rounded-full flex items-center justify-center backdrop-blur-md active:scale-90 transition-all duration-300 ${edge.end ? "opacity-25 pointer-events-none" : "opacity-100"}`}
          style={{ background: "rgba(18,64,42,0.7)", border: "1px solid rgba(204,255,0,0.55)", animation: edge.end ? "none" : "smp-sarrow-pulse 2.2s ease-in-out infinite" }}
        >
          <ChevronRight className="w-5 h-5" style={{ color: "#CCFF00", animation: edge.end ? "none" : "smp-sarrow-nudge-r 1.1s ease-in-out infinite" }} />
        </button>
      </div>

      <div className="flex justify-center gap-1.5 mt-4" data-testid="sample-dots">
        {[...Array(cards.length + 1)].map((_, i) => (
          <span key={i} className="h-1.5 rounded-full transition-all duration-300"
            style={{ width: i === active ? 18 : 6, background: i === active ? "#1F4F2F" : "#C9C2AF" }} />
        ))}
      </div>
    </section>
  );
};

export default SampleReportShowcase;
