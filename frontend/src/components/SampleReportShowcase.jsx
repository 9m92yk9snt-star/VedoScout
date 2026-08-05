// SampleReportShowcase — "the discovery journey": swipeable anonymized sample
// report on the landing page. Same card size — each card is a chapter that sells
// curiosity, learning, dreams and being seen. All data static & anonymized.
import React, { useRef, useState } from "react";
import {
  ShieldCheck, ChevronLeft, ChevronRight, CheckCircle2, Target,
  Gauge, HeartHandshake, CalendarRange, ArrowRight, Sparkles,
  Lock, Eye, Search, MessageCircle, Footprints, Zap,
} from "lucide-react";

const FOREST = "#12402A";
const LIME = "#CCFF00";
const GOLD = "#F5C443";
const ASSET = process.env.REACT_APP_BACKEND_URL;

/* ---------- shared card shell ---------- */
function Card({ children, testid, dark }) {
  return (
    <div
      data-testid={testid}
      data-sample-card
      className={`snap-center shrink-0 w-[86vw] max-w-[380px] sm:w-[380px] rounded-2xl overflow-hidden shadow-[0_18px_50px_-18px_rgba(18,64,42,0.45)] border flex flex-col ${dark ? "border-[#1d3325]" : "border-[#E5DFCE] bg-[#FBF9F3]"}`}
      style={{ minHeight: 440, ...(dark ? { background: "#0B1B10" } : {}) }}
    >
      {children}
    </div>
  );
}

function CardHead({ kicker, title, page }) {
  return (
    <div className="px-5 pt-5">
      <div className="flex items-center justify-between">
        <span className="text-[9.5px] font-black uppercase tracking-[0.2em] text-[#75816F]">{kicker}</span>
        {page && <span className="text-[8.5px] font-black tracking-[0.14em] text-[#B4AE99]">{page}</span>}
      </div>
      <h3 className="font-barlow font-black uppercase tracking-tight text-[19px] text-[#182016] mt-0.5">{title}</h3>
    </div>
  );
}

function Bar({ label, score, meaning, delay }) {
  return (
    <div>
      <div className="flex items-baseline justify-between">
        <span className="text-[11px] font-extrabold uppercase tracking-[0.1em] text-[#3D4A38]">{label}</span>
        <span className="font-barlow font-black text-[17px] text-[#12402A]">{score.toFixed(1)}</span>
      </div>
      <div className="h-2 rounded-full bg-[#E5DFCE] mt-1.5 overflow-hidden">
        <div
          className="h-full rounded-full"
          style={{
            width: `${score * 10}%`,
            background: `linear-gradient(90deg, ${FOREST}, #2D6B3D)`,
            transformOrigin: "left",
            animation: `smp-fill 0.9s ${delay}s ease-out both`,
          }}
        />
      </div>
      {meaning && <p className="text-[11px] text-[#75816F] italic mt-1 leading-snug">{meaning}</p>}
    </div>
  );
}

/* ---------- 1 · dossier ---------- */
function OverviewCard() {
  return (
    <Card testid="sample-card-overview">
      <div className="relative px-5 py-4 overflow-hidden" style={{ background: FOREST }}>
        <div aria-hidden className="absolute -top-10 -right-6 w-40 h-40 rounded-full pointer-events-none" style={{ background: "radial-gradient(circle, rgba(204,255,0,0.28) 0%, transparent 70%)" }} />
        <div className="relative flex items-center justify-between">
          <span className="text-[9px] font-black uppercase tracking-[0.22em]" style={{ color: LIME }}>Official Scout Dossier</span>
          <span className="inline-flex items-center gap-1 text-[8.5px] font-black uppercase tracking-[0.12em] text-white/70">
            <ShieldCheck className="w-3 h-3" style={{ color: LIME }} /> Anonymized sample
          </span>
        </div>
        <div className="relative mt-3 flex items-end justify-between">
          <div>
            <div className="font-barlow font-black uppercase text-white text-[24px] leading-none">
              Mikkel <span className="blur-[7px] select-none">Andersen</span>
            </div>
            <div className="flex gap-1.5 mt-2">
              {["U12", "Winger", "Right foot"].map((c) => (
                <span key={c} className="text-[9px] font-black uppercase tracking-[0.1em] bg-white/10 text-white/85 px-2 py-0.5 rounded">{c}</span>
              ))}
            </div>
          </div>
          <div className="text-right">
            <div className="font-barlow font-black leading-none text-[52px]" style={{ color: LIME, textShadow: "0 0 26px rgba(204,255,0,0.45)", animation: "smp-scoreglow 2.6s ease-in-out infinite" }}>8.2</div>
            <div className="text-[8.5px] font-black uppercase tracking-[0.16em] text-white/60">Overall / 10</div>
          </div>
        </div>
      </div>
      <div className="px-5 py-4 flex-1 flex flex-col">
        <div className="rounded-xl border border-[#E5DFCE] bg-white p-3.5">
          <span className="text-[9px] font-black uppercase tracking-[0.18em] text-[#75816F]">The first line ever written about his game</span>
          <p className="text-[13px] text-[#3D4A38] leading-relaxed mt-1 italic">
            "A brave, direct winger who demands the ball and attacks his man — clearly above U12 expectations in 1v1 situations."
          </p>
        </div>
        <div className="mt-3 rounded-xl p-3.5" style={{ background: "#12402A" }}>
          <div className="flex items-center gap-2">
            <ShieldCheck className="w-4 h-4" style={{ color: LIME }} />
            <span className="text-[9.5px] font-black uppercase tracking-[0.14em] text-white">Identity locked</span>
          </div>
          <p className="text-[11px] text-white/70 leading-relaxed mt-1">
            Parent marked the player with 10 taps · optical tracking · dual identity verification. The report is about <span className="text-white font-bold">your child</span> — never a lookalike.
          </p>
        </div>
        <p className="mt-auto pt-3 text-[10px] text-[#8A937F]">Scored against U12 expectations — never against adults.</p>
      </div>
    </Card>
  );
}

/* ---------- 2 · the numbers ---------- */
function PillarsCard() {
  return (
    <Card testid="sample-card-pillars">
      <CardHead kicker="The numbers — translated into truth" title="Things He Never Knew" page="2 / 11" />
      <div className="px-5 pt-4 space-y-3">
        <Bar label="Technical" score={8.4} meaning="His first touch buys him time others don't have." delay={0.1} />
        <Bar label="Game intelligence" score={7.6} meaning="Sees the pass early — plays it a beat later." delay={0.25} />
        <Bar label="Physical" score={7.9} meaning="Wins the metres that decide a 1v1." delay={0.4} />
        <Bar label="Mentality" score={8.1} meaning="A mistake doesn't slow him down — it switches him on." delay={0.55} />
      </div>
      <div className="px-5 pb-5 mt-auto">
        <div className="rounded-xl bg-white border border-[#E5DFCE] p-3.5 flex items-center gap-3">
          <div className="shrink-0 w-10 h-10 rounded-full flex items-center justify-center" style={{ background: FOREST }}>
            <Sparkles className="w-5 h-5" style={{ color: LIME }} />
          </div>
          <p className="text-[11.5px] text-[#3D4A38] leading-snug">
            <span className="font-black text-[#12402A]">Top 15% for his age group</span> — and now he knows exactly <span className="font-black text-[#12402A]">why</span>. Every score comes with the clip moment behind it.
          </p>
        </div>
      </div>
    </Card>
  );
}

/* ---------- 3 · superpowers ---------- */
function StrengthsCard() {
  const strengths = [
    "Attacks his defender 1v1 without hesitation",
    "First touch opens the field — rarely needs a second",
    "Keeps working after losing the ball",
  ];
  return (
    <Card testid="sample-card-strengths">
      <CardHead kicker="What the scout saw" title="Superpowers He Didn't Know He Had" page="3 / 11" />
      <div className="px-5 pt-4 space-y-2.5">
        {strengths.map((s, i) => (
          <div key={s} className="flex items-start gap-2.5 bg-white border border-[#E5DFCE] rounded-xl p-3" style={{ animation: `smp-rise 0.5s ${0.12 * i}s ease-out both` }}>
            <span className="shrink-0 w-5 h-5 rounded-full flex items-center justify-center mt-0.5" style={{ background: "#EAF4E4" }}>
              <Zap className="w-3 h-3" style={{ color: "#2D6B3D" }} />
            </span>
            <p className="text-[12.5px] text-[#3D4A38] leading-snug">{s}</p>
          </div>
        ))}
      </div>
      <div className="px-5 pb-5 pt-3 mt-auto">
        <div className="rounded-xl border border-[#EAD9B0] bg-[#FFF7E6] p-3.5">
          <div className="flex items-center gap-2">
            <Target className="w-4 h-4 text-[#A05A1C]" />
            <span className="text-[9.5px] font-black uppercase tracking-[0.16em] text-[#A05A1C]">The golden key</span>
          </div>
          <p className="text-[12.5px] text-[#6B5028] leading-snug mt-1">
            Scans over his shoulder before receiving — <span className="font-bold">the one habit that unlocks his next level</span>. The plan shows exactly how.
          </p>
        </div>
      </div>
    </Card>
  );
}

/* ---------- 4 · pace ---------- */
function PaceCardSample() {
  return (
    <Card testid="sample-card-pace">
      <CardHead kicker="Now he knows — with proof" title="How Fast Is He Really?" page="4 / 11" />
      <div className="px-5 pt-4">
        <div className="relative rounded-xl p-4 overflow-hidden" style={{ background: FOREST }}>
          <div aria-hidden className="absolute -bottom-12 -left-8 w-44 h-44 rounded-full pointer-events-none" style={{ background: "radial-gradient(circle, rgba(204,255,0,0.22) 0%, transparent 70%)" }} />
          <span className="relative text-[9px] font-black uppercase tracking-[0.18em] text-[#A9BC9C]">Top speed (est.)</span>
          <div className="relative flex items-baseline gap-2">
            <span className="font-barlow font-black text-[44px] leading-none" style={{ color: LIME, textShadow: "0 0 24px rgba(204,255,0,0.4)" }}>24.1</span>
            <span className="text-white/80 font-black text-[14px]">KM/H</span>
          </div>
          <div className="relative grid grid-cols-2 gap-2 mt-3">
            <div className="bg-white/10 rounded-lg p-2.5 text-center">
              <div className="font-barlow font-black text-[20px]" style={{ color: LIME }}>7</div>
              <div className="text-[8.5px] font-black uppercase tracking-[0.12em] text-white/60">Sprints</div>
            </div>
            <div className="bg-white/10 rounded-lg p-2.5 text-center">
              <div className="font-barlow font-black text-[20px]" style={{ color: LIME }}>412 m</div>
              <div className="text-[8.5px] font-black uppercase tracking-[0.12em] text-white/60">Distance tracked</div>
            </div>
          </div>
        </div>
      </div>
      <div className="px-5 pb-5 pt-3 mt-auto">
        <div className="rounded-xl bg-white border border-[#E5DFCE] p-3.5">
          <p className="text-[12px] text-[#3D4A38] leading-snug italic">
            "Faster than most wingers his age — and the report shows the <span className="font-bold not-italic text-[#12402A]">exact sprint</span> where he proved it."
          </p>
        </div>
        <div className="flex items-start gap-2.5 mt-3">
          <Gauge className="w-4 h-4 mt-0.5 shrink-0 text-[#2D6B3D]" />
          <p className="text-[11px] text-[#8A937F] leading-relaxed">
            Pixel-level optical tracking of <span className="font-bold text-[#3D4A38]">your marked player</span> — never invented.
          </p>
        </div>
      </div>
    </Card>
  );
}

/* ---------- 5 · curiosity (blurred answers) ---------- */
function CuriosityCard() {
  const rows = [
    ["Which foot does he really trust under pressure?", "Left — and the moment that proves it"],
    ["What happens in the 8 seconds after he loses the ball?", "Something scouts love to see"],
    ["The habit a scout would notice first?", "It shows up 14 times in one half"],
    ["Where should he play next season?", "The data has a clear opinion"],
  ];
  return (
    <Card testid="sample-card-curiosity">
      <CardHead kicker="The things you'll finally know" title="What You'll Discover" page="5 / 11" />
      <div className="px-5 pt-4 space-y-2.5">
        {rows.map(([q, a], i) => (
          <div key={q} className="bg-white border border-[#E5DFCE] rounded-xl px-3.5 py-2.5" style={{ animation: `smp-rise 0.5s ${0.1 * i}s ease-out both` }}>
            <p className="text-[11.5px] font-extrabold text-[#3D4A38] leading-snug">{q}</p>
            <div className="flex items-center gap-1.5 mt-1">
              <Lock className="w-3 h-3 shrink-0 text-[#B4AE99]" />
              <span className="text-[11px] text-[#75816F] blur-[4px] select-none">{a}</span>
            </div>
          </div>
        ))}
      </div>
      <div className="px-5 pb-5 pt-3 mt-auto">
        <p className="text-[11px] text-[#8A937F] leading-relaxed">
          Every answer is in the full report — <span className="font-bold text-[#3D4A38]">with the clip moment to prove it</span>. Discoveries about your own child you can't get anywhere else.
        </p>
      </div>
    </Card>
  );
}

/* ---------- 6 · parents ask ---------- */
function ParentsCard() {
  const rows = [
    ["Does he demand the ball?", "11 touches · always available"],
    ["Is he brave?", "8.5 / 10 — takes his man on"],
    ["After a mistake?", "Wins the ball straight back"],
    ["Work without the ball?", "7.0 — and growing"],
  ];
  return (
    <Card testid="sample-card-parents">
      <CardHead kicker="The questions you whisper" title="What Parents Ask" page="6 / 11" />
      <div className="px-5 pt-4 space-y-2">
        {rows.map(([k, v]) => (
          <div key={k} className="flex items-center justify-between bg-white border border-[#E5DFCE] rounded-xl px-3.5 py-2.5">
            <span className="text-[11px] font-extrabold uppercase tracking-[0.08em] text-[#75816F]">{k}</span>
            <span className="font-barlow font-black text-[14px] text-[#12402A] text-right">{v}</span>
          </div>
        ))}
      </div>
      <div className="px-5 pb-5 pt-3 mt-auto">
        <div className="flex items-start gap-2.5">
          <HeartHandshake className="w-4 h-4 mt-0.5 shrink-0 text-[#2D6B3D]" />
          <p className="text-[11px] text-[#8A937F] leading-relaxed">
            The questions families actually ask — answered honestly, with warmth. If there isn't enough evidence, the report says so instead of guessing.
          </p>
        </div>
      </div>
    </Card>
  );
}

/* ---------- 7 · plan ---------- */
function PlanCard() {
  const weeks = [
    ["Weeks 1–3", "Scanning before receiving — 10 min, 3×/week"],
    ["Weeks 4–8", "First touch under pressure — wall drills"],
    ["Weeks 9–12", "1v1 end product — final pass & finish"],
  ];
  return (
    <Card testid="sample-card-plan">
      <CardHead kicker="Personal roadmap" title="A Map to Who He's Becoming" page="7 / 11" />
      <div className="px-5 pt-4 space-y-2.5">
        {weeks.map(([w, t], i) => (
          <div key={w} className="flex items-start gap-3 bg-white border border-[#E5DFCE] rounded-xl p-3" style={{ animation: `smp-rise 0.5s ${0.12 * i}s ease-out both` }}>
            <span className="shrink-0 text-[9px] font-black uppercase tracking-[0.1em] px-2 py-1 rounded" style={{ background: FOREST, color: LIME }}>{w}</span>
            <p className="text-[12px] text-[#3D4A38] leading-snug">{t}</p>
          </div>
        ))}
      </div>
      <div className="px-5 pb-5 pt-3 mt-auto">
        <div className="flex items-start gap-2.5">
          <CalendarRange className="w-4 h-4 mt-0.5 shrink-0 text-[#2D6B3D]" />
          <p className="text-[11px] text-[#8A937F] leading-relaxed">
            Plus 3 countable <span className="font-bold text-[#3D4A38]">next-match missions</span> your child can take straight into the weekend game.
          </p>
        </div>
      </div>
    </Card>
  );
}

/* ---------- 8 · the road ahead (dream) ---------- */
function RoadCard() {
  const steps = [
    ["Today", "One clip uploaded — the game finally on record", true],
    ["This season", "Report + plan in hand — training with purpose", false],
    ["Next season", "A stronger, smarter version of his own game", false],
    ["When he's ready", "Visible to real scouts who are looking", false],
  ];
  return (
    <Card testid="sample-card-road" dark>
      <div className="relative flex-1 flex flex-col overflow-hidden">
        <img
          src={`${ASSET}/api/static/landing/carousel-bg-1.jpg`}
          alt=""
          loading="lazy"
          className="absolute inset-0 w-full h-full object-cover opacity-45"
          onError={(e) => { e.currentTarget.style.display = "none"; }}
        />
        <div aria-hidden className="absolute inset-0" style={{ background: "linear-gradient(180deg, rgba(6,14,9,0.55) 0%, rgba(6,14,9,0.88) 70%, rgba(6,14,9,0.97) 100%)" }} />
        <div className="relative px-5 pt-5">
          <div className="flex items-center justify-between">
            <span className="text-[9.5px] font-black uppercase tracking-[0.2em]" style={{ color: GOLD }}>Where this can lead</span>
            <span className="text-[8.5px] font-black tracking-[0.14em] text-white/40">8 / 11</span>
          </div>
          <h3 className="font-barlow font-black uppercase tracking-tight text-[19px] text-white mt-0.5">The Road Ahead</h3>
        </div>
        <div className="relative px-5 pt-4 pb-2 flex-1">
          <div className="relative pl-5">
            <div aria-hidden className="absolute left-[7px] top-2 bottom-2 w-px" style={{ background: "linear-gradient(180deg, #CCFF00 0%, rgba(204,255,0,0.15) 100%)" }} />
            <div className="space-y-3.5">
              {steps.map(([k, t, now], i) => (
                <div key={k} className="relative" style={{ animation: `smp-rise 0.5s ${0.12 * i}s ease-out both` }}>
                  <span
                    aria-hidden
                    className="absolute -left-5 top-1 w-[15px] h-[15px] rounded-full border-2"
                    style={now
                      ? { background: LIME, borderColor: LIME, boxShadow: "0 0 14px rgba(204,255,0,0.7)" }
                      : { background: "#0B1B10", borderColor: "rgba(204,255,0,0.45)" }}
                  />
                  <div className="text-[9px] font-black uppercase tracking-[0.16em]" style={{ color: now ? LIME : "rgba(255,255,255,0.55)" }}>{k}</div>
                  <p className="text-[12px] text-white/85 leading-snug mt-0.5">{t}</p>
                </div>
              ))}
            </div>
          </div>
        </div>
        <div className="relative px-5 pb-5">
          <div className="flex items-start gap-2.5">
            <Footprints className="w-4 h-4 mt-0.5 shrink-0" style={{ color: GOLD }} />
            <p className="text-[10.5px] text-white/60 leading-relaxed">
              No promises — just a clear next step. Every step on this road is <span className="font-bold text-white/85">his own</span>. We light it up.
            </p>
          </div>
        </div>
      </div>
    </Card>
  );
}

/* ---------- 9 · a real scout replied ---------- */
function ScoutReplyCard() {
  return (
    <Card testid="sample-card-scoutreply">
      <CardHead kicker="Not just software — real people" title="A Real Scout Replied" page="9 / 11" />
      <div className="px-5 pt-4 flex-1">
        <div className="flex items-start gap-3" style={{ animation: "smp-rise 0.5s 0.1s ease-out both" }}>
          <div className="shrink-0 w-10 h-10 rounded-full flex items-center justify-center font-barlow font-black text-[13px]" style={{ background: FOREST, color: LIME }}>JK</div>
          <div className="flex-1">
            <div className="flex items-baseline gap-2">
              <span className="text-[11px] font-black text-[#182016]">J. K.</span>
              <span className="text-[9px] font-black uppercase tracking-[0.1em] text-[#75816F]">Professional scout · 14 yrs</span>
            </div>
            <div className="mt-1.5 rounded-xl rounded-tl-sm bg-white border border-[#E5DFCE] p-3.5">
              <p className="text-[12.5px] text-[#3D4A38] leading-relaxed italic">
                "I watched the clip twice. The way he attacks the back post at <span className="font-bold not-italic text-[#12402A]">07:12</span> — that's not taught, that's instinct. Keep him wide. Keep him brave. I'd like to see him again in the spring."
              </p>
            </div>
            <div className="mt-2 rounded-xl rounded-tl-sm bg-white border border-[#E5DFCE] p-3" style={{ animation: "smp-rise 0.5s 0.35s ease-out both" }}>
              <p className="text-[11.5px] text-[#3D4A38] leading-snug">
                One drill from me: <span className="font-bold text-[#12402A]">back-post timing, 2×/week</span>. Small habit — big difference at trials.
              </p>
            </div>
          </div>
        </div>
      </div>
      <div className="px-5 pb-5 pt-3 mt-auto">
        <div className="flex items-start gap-2.5">
          <MessageCircle className="w-4 h-4 mt-0.5 shrink-0 text-[#2D6B3D]" />
          <p className="text-[11px] text-[#8A937F] leading-relaxed">
            A real, experienced scout reads the report and writes back — <span className="font-bold text-[#3D4A38]">personal words about your child's game</span>, not a template.
          </p>
        </div>
      </div>
    </Card>
  );
}

/* ---------- 10 · seen in the scout library ---------- */
function LibraryCard() {
  return (
    <Card testid="sample-card-library">
      <CardHead kicker="Being seen changes everything" title="Found in the Scout Library" page="10 / 11" />
      <div className="px-5 pt-4 flex-1">
        <div className="rounded-xl border border-[#E5DFCE] bg-white p-3 flex items-center gap-2.5">
          <Search className="w-4 h-4 shrink-0 text-[#75816F]" />
          <span className="text-[11.5px] text-[#75816F]">U12 · winger · brave in 1v1 · right foot…</span>
        </div>
        <div className="mt-3 rounded-xl p-3.5" style={{ background: FOREST, animation: "smp-rise 0.5s 0.15s ease-out both" }}>
          <div className="flex items-center justify-between">
            <div>
              <div className="font-barlow font-black uppercase text-white text-[16px] leading-none">
                Mikkel <span className="blur-[5px] select-none">A.</span>
              </div>
              <div className="text-[9px] font-black uppercase tracking-[0.12em] text-white/60 mt-1">U12 · Winger · 8.2 overall</div>
            </div>
            <span className="inline-flex items-center gap-1.5 text-[9px] font-black uppercase tracking-[0.1em] px-2 py-1 rounded-full" style={{ background: "rgba(204,255,0,0.15)", color: LIME }}>
              <Eye className="w-3 h-3" /> Viewed by scouts
            </span>
          </div>
          <div className="mt-3 pt-3 border-t border-white/10 flex items-center justify-between">
            <span className="text-[10px] text-white/60">Profile opened <span className="font-bold text-white">3 times</span> this month</span>
            <span className="text-[9px] font-black uppercase tracking-[0.1em]" style={{ color: LIME }}>While he was training</span>
          </div>
        </div>
        <p className="text-[11.5px] text-[#3D4A38] leading-relaxed mt-3">
          While your family sleeps, his profile is quietly doing its job — in the library <span className="font-bold text-[#12402A]">real scouts search</span> when they look for players like him.
        </p>
      </div>
      <div className="px-5 pb-5 pt-3 mt-auto">
        <div className="flex items-start gap-2.5">
          <ShieldCheck className="w-4 h-4 mt-0.5 shrink-0 text-[#2D6B3D]" />
          <p className="text-[11px] text-[#8A937F] leading-relaxed">
            Only with your family's consent — you decide what scouts can see, always.
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
      <div className="relative flex-1 flex flex-col px-5 py-6 overflow-hidden">
        <img
          src={`${ASSET}/api/static/landing/finalcta-stadium.jpg`}
          alt=""
          loading="lazy"
          className="absolute inset-0 w-full h-full object-cover"
          onError={(e) => { e.currentTarget.style.display = "none"; }}
        />
        <div aria-hidden className="absolute inset-0" style={{ background: "linear-gradient(180deg, rgba(5,8,5,0.62) 0%, rgba(5,8,5,0.3) 45%, rgba(5,8,5,0.9) 100%)" }} />
        <div className="relative flex items-center gap-2">
          <Sparkles className="w-4 h-4" style={{ color: GOLD }} />
          <span className="text-[10px] font-black uppercase tracking-[0.22em]" style={{ color: GOLD }}>Your story is next</span>
        </div>
        <h3 className="relative font-barlow font-black uppercase text-white text-[26px] leading-[1.02] mt-3">
          One clip.<br />One report.<br />
          <span style={{ color: LIME }}>A whole new way<br />to see your game.</span>
        </h3>
        <div className="relative mt-auto pt-6">
          <p className="text-[12.5px] text-white/80 leading-relaxed mb-4">
            The lights are already on. The next report we write could be about <span className="font-bold text-white">you</span>.
          </p>
          <button
            type="button"
            data-testid="sample-report-cta"
            onClick={onPrimaryCta}
            className="relative overflow-hidden w-full inline-flex items-center justify-center gap-2 font-barlow font-black uppercase tracking-[0.12em] text-[14px] px-6 py-4 rounded-xl transition-transform active:scale-[0.98] hover:scale-[1.02]"
            style={{ background: LIME, color: "#0D2818", animation: "smp-cta-glow 2.6s ease-in-out infinite" }}
          >
            <span aria-hidden className="absolute inset-y-0 w-1/3 bg-white/40 pointer-events-none" style={{ animation: "smp-cta-shine 2.8s ease-in-out infinite" }} />
            Upload your video <ArrowRight className="w-4 h-4" />
          </button>
          <p className="text-center text-[10px] text-white/60 mt-2.5">Free preview · no card needed to start</p>
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
        @keyframes smp-rise { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
        @keyframes smp-scoreglow { 0%,100% { text-shadow: 0 0 18px rgba(204,255,0,0.35); } 50% { text-shadow: 0 0 34px rgba(204,255,0,0.7); } }
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
              An anonymized sample — swipe through the discoveries one clip unlocks. Eleven pages of a player's story.
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
          style={{ background: "rgba(10,20,14,0.62)", border: "1px solid rgba(204,255,0,0.55)", animation: edge.start ? "none" : "smp-sarrow-pulse 2.2s ease-in-out infinite" }}
        >
          <ChevronLeft className="w-5 h-5" style={{ color: "#CCFF00", animation: edge.start ? "none" : "smp-sarrow-nudge-l 1.1s ease-in-out infinite" }} />
        </button>
        <button
          type="button" aria-label="Next card" data-testid="sample-arrow-next" onClick={() => nudge(1)}
          disabled={edge.end}
          className={`sm:hidden absolute right-1.5 top-1/2 -translate-y-1/2 z-20 w-10 h-10 rounded-full flex items-center justify-center backdrop-blur-md active:scale-90 transition-all duration-300 ${edge.end ? "opacity-25 pointer-events-none" : "opacity-100"}`}
          style={{ background: "rgba(10,20,14,0.62)", border: "1px solid rgba(204,255,0,0.55)", animation: edge.end ? "none" : "smp-sarrow-pulse 2.2s ease-in-out infinite" }}
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
