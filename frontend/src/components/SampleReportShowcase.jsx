// SampleReportShowcase — interactive anonymized sample report on the landing
// page. Swipeable cards (mobile-first) showing exactly what parents receive.
// All data is static & anonymized — proof before purchase.
import React, { useRef, useState } from "react";
import {
  ShieldCheck, ChevronLeft, ChevronRight, CheckCircle2, Target,
  Gauge, HeartHandshake, CalendarRange, FileText, ArrowRight, Sparkles,
} from "lucide-react";

const FOREST = "#12402A";
const LIME = "#CCFF00";

/* ---------- shared card shell ---------- */
function Card({ children, testid }) {
  return (
    <div
      data-testid={testid}
      data-sample-card
      className="snap-center shrink-0 w-[86vw] max-w-[380px] sm:w-[380px] rounded-2xl overflow-hidden shadow-[0_18px_50px_-18px_rgba(18,64,42,0.45)] border border-[#E5DFCE] bg-[#FBF9F3] flex flex-col"
      style={{ minHeight: 440 }}
    >
      {children}
    </div>
  );
}

function CardHead({ kicker, title }) {
  return (
    <div className="px-5 pt-5">
      <span className="text-[9.5px] font-black uppercase tracking-[0.2em] text-[#75816F]">{kicker}</span>
      <h3 className="font-barlow font-black uppercase tracking-tight text-[19px] text-[#182016] mt-0.5">{title}</h3>
    </div>
  );
}

function Bar({ label, score, meaning }) {
  return (
    <div>
      <div className="flex items-baseline justify-between">
        <span className="text-[11px] font-extrabold uppercase tracking-[0.1em] text-[#3D4A38]">{label}</span>
        <span className="font-barlow font-black text-[17px] text-[#12402A]">{score.toFixed(1)}</span>
      </div>
      <div className="h-2 rounded-full bg-[#E5DFCE] mt-1.5 overflow-hidden">
        <div className="h-full rounded-full" style={{ width: `${score * 10}%`, background: `linear-gradient(90deg, ${FOREST}, #2D6B3D)` }} />
      </div>
      {meaning && <p className="text-[11px] text-[#75816F] italic mt-1 leading-snug">{meaning}</p>}
    </div>
  );
}

/* ---------- the 7 sample cards ---------- */
function OverviewCard() {
  return (
    <Card testid="sample-card-overview">
      <div className="px-5 py-4" style={{ background: FOREST }}>
        <div className="flex items-center justify-between">
          <span className="text-[9px] font-black uppercase tracking-[0.22em]" style={{ color: LIME }}>Official Scout Dossier</span>
          <span className="inline-flex items-center gap-1 text-[8.5px] font-black uppercase tracking-[0.12em] text-white/70">
            <ShieldCheck className="w-3 h-3" style={{ color: LIME }} /> Anonymized sample
          </span>
        </div>
        <div className="mt-3 flex items-end justify-between">
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
            <div className="font-barlow font-black leading-none text-[52px]" style={{ color: LIME }}>8.2</div>
            <div className="text-[8.5px] font-black uppercase tracking-[0.16em] text-white/60">Overall / 10</div>
          </div>
        </div>
      </div>
      <div className="px-5 py-4 flex-1 flex flex-col">
        <div className="rounded-xl border border-[#E5DFCE] bg-white p-3.5">
          <span className="text-[9px] font-black uppercase tracking-[0.18em] text-[#75816F]">Scout's first line</span>
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

function PillarsCard() {
  return (
    <Card testid="sample-card-pillars">
      <CardHead kicker="The numbers — translated" title="What They Really Mean" />
      <div className="px-5 pt-4 space-y-3">
        <Bar label="Technical" score={8.4} meaning="His first touch buys him time others don't have." />
        <Bar label="Game intelligence" score={7.6} meaning="Sees the pass early — plays it a beat later." />
        <Bar label="Physical" score={7.9} meaning="Wins the metres that decide a 1v1." />
        <Bar label="Mentality" score={8.1} meaning="A mistake doesn't slow him down — it switches him on." />
      </div>
      <div className="px-5 pb-5 mt-auto">
        <div className="rounded-xl bg-white border border-[#E5DFCE] p-3.5 flex items-center gap-3">
          <div className="shrink-0 w-10 h-10 rounded-full flex items-center justify-center" style={{ background: FOREST }}>
            <Sparkles className="w-4.5 h-4.5 w-5 h-5" style={{ color: LIME }} />
          </div>
          <p className="text-[11.5px] text-[#3D4A38] leading-snug">
            <span className="font-black text-[#12402A]">Top 15% for his age group</span> — every score comes with the evidence and the timestamp behind it.
          </p>
        </div>
      </div>
    </Card>
  );
}

function StrengthsCard() {
  const strengths = [
    "Attacks his defender 1v1 without hesitation",
    "First touch opens the field — rarely needs a second",
    "Keeps working after losing the ball",
  ];
  return (
    <Card testid="sample-card-strengths">
      <CardHead kicker="What the scout saw" title="Strengths & Focus" />
      <div className="px-5 pt-4 space-y-2.5">
        {strengths.map((s) => (
          <div key={s} className="flex items-start gap-2.5 bg-white border border-[#E5DFCE] rounded-xl p-3">
            <CheckCircle2 className="w-4 h-4 mt-0.5 shrink-0" style={{ color: "#2D6B3D" }} />
            <p className="text-[12.5px] text-[#3D4A38] leading-snug">{s}</p>
          </div>
        ))}
      </div>
      <div className="px-5 pb-5 pt-3 mt-auto">
        <div className="rounded-xl border border-[#EAD9B0] bg-[#FFF7E6] p-3.5">
          <div className="flex items-center gap-2">
            <Target className="w-4 h-4 text-[#A05A1C]" />
            <span className="text-[9.5px] font-black uppercase tracking-[0.16em] text-[#A05A1C]">Priority to train</span>
          </div>
          <p className="text-[12.5px] text-[#6B5028] leading-snug mt-1">
            Scans over his shoulder before receiving — <span className="font-bold">the one habit that unlocks his next level</span>. The plan shows exactly how.
          </p>
        </div>
      </div>
    </Card>
  );
}

function PaceCardSample() {
  return (
    <Card testid="sample-card-pace">
      <CardHead kicker="Measured — never guessed" title="Pace & Sprints" />
      <div className="px-5 pt-4">
        <div className="rounded-xl p-4" style={{ background: FOREST }}>
          <span className="text-[9px] font-black uppercase tracking-[0.18em] text-[#A9BC9C]">Top speed (est.)</span>
          <div className="flex items-baseline gap-2">
            <span className="font-barlow font-black text-[44px] leading-none" style={{ color: LIME }}>24.1</span>
            <span className="text-white/80 font-black text-[14px]">KM/H</span>
          </div>
          <div className="grid grid-cols-2 gap-2 mt-3">
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

function ParentsCard() {
  const rows = [
    ["Does he demand the ball?", "11 touches · always available"],
    ["Is he brave?", "8.5 / 10 — takes his man on"],
    ["After a mistake?", "Wins the ball straight back"],
    ["Work without the ball?", "7.0 — and growing"],
  ];
  return (
    <Card testid="sample-card-parents">
      <CardHead kicker="The questions you whisper" title="What Parents Ask" />
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
            The questions families actually ask — answered honestly. If there isn't enough evidence, the report says so instead of guessing.
          </p>
        </div>
      </div>
    </Card>
  );
}

function PlanCard() {
  const weeks = [
    ["Weeks 1–3", "Scanning before receiving — 10 min, 3×/week"],
    ["Weeks 4–8", "First touch under pressure — wall drills"],
    ["Weeks 9–12", "1v1 end product — final pass & finish"],
  ];
  return (
    <Card testid="sample-card-plan">
      <CardHead kicker="Personal roadmap" title="90-Day Development Plan" />
      <div className="px-5 pt-4 space-y-2.5">
        {weeks.map(([w, t]) => (
          <div key={w} className="flex items-start gap-3 bg-white border border-[#E5DFCE] rounded-xl p-3">
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

function CtaCard({ onPrimaryCta }) {
  const ASSET = process.env.REACT_APP_BACKEND_URL;
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
        <style>{`
          @keyframes smp-cta-shine { 0% { transform: translateX(-120%) skewX(-18deg); } 60%, 100% { transform: translateX(220%) skewX(-18deg); } }
          @keyframes smp-cta-glow { 0%, 100% { box-shadow: 0 0 22px rgba(204,255,0,0.35); } 50% { box-shadow: 0 0 40px rgba(204,255,0,0.65); } }
        `}</style>
        <div className="relative flex items-center gap-2">
          <Sparkles className="w-4 h-4" style={{ color: "#F5C443" }} />
          <span className="text-[10px] font-black uppercase tracking-[0.22em]" style={{ color: "#F5C443" }}>Your story is next</span>
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
  const cards = [OverviewCard, PillarsCard, StrengthsCard, PaceCardSample, ParentsCard, PlanCard];

  const handleScroll = () => {
    const el = scrollerRef.current;
    if (!el) return;
    const card = el.querySelector("[data-sample-card]");
    if (!card) return;
    const w = card.offsetWidth + 16;
    setActive(Math.min(cards.length, Math.round(el.scrollLeft / w)));
  };

  const nudge = (dir) => {
    const el = scrollerRef.current;
    if (!el) return;
    const card = el.querySelector("[data-sample-card]");
    el.scrollBy({ left: dir * ((card?.offsetWidth || 380) + 16), behavior: "smooth" });
  };

  return (
    <section id="sample-report" data-testid="sample-report-showcase" className="relative py-14 sm:py-20 overflow-hidden">
      <div className="max-w-7xl mx-auto px-5 sm:px-6">
        <div className="flex items-end justify-between gap-4">
          <div>
            <span className="text-[10px] font-black uppercase tracking-[0.24em] text-[#2D6B3D]">Proof before you pay</span>
            <h2 className="font-barlow font-black uppercase tracking-tight text-[26px] sm:text-4xl text-ink leading-[1.05] mt-1">
              See a real report
            </h2>
            <p className="text-sm text-ink/60 mt-2 max-w-md">
              An anonymized sample — swipe through exactly what you receive after uploading one clip.
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
          style={{ scrollPaddingLeft: 20, WebkitOverflowScrolling: "touch" }}
        >
          <div className="hidden lg:block shrink-0" style={{ width: "calc((100vw - 1280px) / 2)" }} />
          {cards.map((C, i) => <C key={i} onPrimaryCta={onPrimaryCta} />)}
          <CtaCard onPrimaryCta={onPrimaryCta} />
          <div className="shrink-0 w-2" />
        </div>
        {/* Centered swipe arrows — mobile only */}
        <button
          type="button" aria-label="Previous card" data-testid="sample-arrow-prev" onClick={() => nudge(-1)}
          className="sm:hidden absolute left-1.5 top-1/2 -translate-y-1/2 z-20 w-10 h-10 rounded-full flex items-center justify-center backdrop-blur-md active:scale-95 transition-transform"
          style={{ background: "rgba(10,20,14,0.62)", border: "1px solid rgba(204,255,0,0.55)", boxShadow: "0 4px 18px rgba(0,0,0,0.35)" }}
        >
          <ChevronLeft className="w-5 h-5" style={{ color: "#CCFF00" }} />
        </button>
        <button
          type="button" aria-label="Next card" data-testid="sample-arrow-next" onClick={() => nudge(1)}
          className="sm:hidden absolute right-1.5 top-1/2 -translate-y-1/2 z-20 w-10 h-10 rounded-full flex items-center justify-center backdrop-blur-md active:scale-95 transition-transform"
          style={{ background: "rgba(10,20,14,0.62)", border: "1px solid rgba(204,255,0,0.55)", boxShadow: "0 4px 18px rgba(0,0,0,0.35)" }}
        >
          <ChevronRight className="w-5 h-5" style={{ color: "#CCFF00" }} />
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
