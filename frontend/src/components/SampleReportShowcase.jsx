// SampleReportShowcase — "the discovery journey" sample report carousel.
// v3: every card has its own background treatment (photo/texture — no flat matte
// green), gold replaces most neon accents, and every card plays its own reveal
// animation EVERY time it swipes into view (IntersectionObserver re-trigger).
import React, { useEffect, useRef, useState } from "react";
import {
  ShieldCheck, ChevronLeft, ChevronRight, Target,
  ArrowRight, Sparkles, Lock, Eye, Zap,
  HeartHandshake, CalendarRange, Gauge, MessageCircle, Footprints,
} from "lucide-react";

const FOREST = "#12402A";
const FOREST_L = "#1F4F2F";
const LIME = "#CCFF00";
const GOLD = "#F5C443";
const SAGE = "#9FB89B";
const ASSET = process.env.REACT_APP_BACKEND_URL;

const NOISE =
  "url(\"data:image/svg+xml,%3Csvg viewBox='0 0 200 200' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='2'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)' opacity='0.35'/%3E%3C/svg%3E\")";

/* ---------- in-view shell: reveal animations replay on every swipe ---------- */
function Card({ children, testid, className = "", style = {} }) {
  const ref = useRef(null);
  const [inView, setInView] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el) return undefined;
    const io = new IntersectionObserver(
      ([e]) => setInView(e.intersectionRatio >= 0.55),
      { threshold: [0, 0.55] }
    );
    io.observe(el);
    return () => io.disconnect();
  }, []);
  return (
    <div
      ref={ref}
      data-testid={testid}
      data-sample-card
      className={`snap-center shrink-0 w-[86vw] max-w-[380px] sm:w-[380px] rounded-3xl overflow-hidden shadow-[0_22px_55px_-20px_rgba(18,64,42,0.5)] flex flex-col group ${inView ? "smp-inview" : ""} ${className}`}
      style={{ minHeight: 440, ...style }}
    >
      {children}
    </div>
  );
}

function Grain({ opacity = 0.05 }) {
  return <div aria-hidden className="absolute inset-0 pointer-events-none" style={{ backgroundImage: NOISE, opacity }} />;
}

function Photo({ src, className = "", style = {} }) {
  return (
    <img
      src={src}
      alt=""
      loading="lazy"
      className={`absolute inset-0 w-full h-full object-cover smp-kenburns ${className}`}
      style={style}
      onError={(e) => { e.currentTarget.style.display = "none"; }}
    />
  );
}

function Kicker({ children, color = "#75816F", page, light }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-[9.5px] font-black uppercase tracking-[0.22em]" style={{ color }}>{children}</span>
      {page && <span className="text-[8.5px] font-black tracking-[0.14em]" style={{ color: light ? "rgba(255,255,255,0.45)" : "rgba(24,32,22,0.35)" }}>{page}</span>}
    </div>
  );
}

/* ---------- 1 · dossier (photo: kneeling under floodlights, count-up score) ---------- */
function ScoreCounter({ inViewSelector }) {
  const ref = useRef(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return undefined;
    const card = el.closest("[data-sample-card]");
    let raf;
    const run = () => {
      const t0 = performance.now();
      const tick = (t) => {
        const p = Math.min(1, (t - t0) / 1300);
        el.textContent = (8.2 * (1 - Math.pow(1 - p, 3))).toFixed(1);
        if (p < 1) raf = requestAnimationFrame(tick);
      };
      raf = requestAnimationFrame(tick);
    };
    const mo = new MutationObserver(() => {
      if (card.classList.contains("smp-inview")) { cancelAnimationFrame(raf); run(); }
      else el.textContent = "0.0";
    });
    mo.observe(card, { attributes: true, attributeFilter: ["class"] });
    if (card.classList.contains("smp-inview")) run();
    return () => { mo.disconnect(); cancelAnimationFrame(raf); };
  }, []);
  return <span ref={ref}>0.0</span>;
}

function OverviewCard() {
  return (
    <Card testid="sample-card-overview" style={{ background: "#0F3823", border: "1px solid rgba(245,196,67,0.18)" }}>
      <div className="relative flex-1 flex flex-col p-6 overflow-hidden">
        <Photo src={`${ASSET}/api/static/landing/carousel-bg-7.jpg`} style={{ opacity: 0.4 }} />
        <div aria-hidden className="absolute inset-0" style={{ background: `linear-gradient(175deg, ${FOREST}E8 0%, ${FOREST}80 42%, #0C2E1CF5 100%)` }} />
        <Grain />
        <div className="relative smp-a smp-a-rise">
          <Kicker color={GOLD} page="1 / 11" light>Official Scout Dossier</Kicker>
        </div>
        <div className="relative mt-4 smp-a smp-a-rise" style={{ animationDelay: "0.1s" }}>
          <div className="inline-flex items-center gap-2 bg-white/10 backdrop-blur-md border border-white/15 rounded-full px-3 py-1.5">
            <span className="w-2 h-2 rounded-full" style={{ background: GOLD, animation: "smp-blink 1.8s ease-in-out infinite" }} />
            <span className="font-barlow font-black uppercase text-white text-[15px] leading-none tracking-tight">
              Mikkel <span className="blur-[6px] select-none">Andersen</span>
            </span>
          </div>
          <div className="flex gap-1.5 mt-2.5">
            {["U12", "Winger", "Right foot"].map((c) => (
              <span key={c} className="text-[9px] font-black uppercase tracking-[0.1em] bg-white/10 backdrop-blur-sm text-white/85 px-2 py-1 rounded-md">{c}</span>
            ))}
          </div>
        </div>
        <div className="relative mt-4 flex items-end gap-4 smp-a smp-a-rise" style={{ animationDelay: "0.22s" }}>
          <div className="font-barlow font-black leading-none text-[78px]" style={{ color: LIME, textShadow: "0 0 26px rgba(204,255,0,0.35)" }}>
            <ScoreCounter />
          </div>
          <div className="pb-2.5">
            <div className="text-[9px] font-black uppercase tracking-[0.18em] text-white/60">Overall / 10</div>
            <div className="text-[10px] font-bold mt-0.5" style={{ color: GOLD }}>vs U12 expectations</div>
          </div>
        </div>
        <p className="relative text-[13px] leading-relaxed mt-3 italic smp-a smp-a-rise" style={{ color: GOLD, animationDelay: "0.4s", textShadow: "0 1px 8px rgba(10,26,16,0.6)" }}>
          "A brave, direct winger who demands the ball — clearly above U12 expectations in 1v1."
        </p>
        <div className="relative mt-3 smp-a smp-a-slideL" style={{ animationDelay: "0.55s" }}>
          <div className="inline-flex items-center gap-2 rounded-full px-3 py-1.5 bg-white/10 backdrop-blur-md border border-white/15">
            <span className="w-1.5 h-1.5 rounded-full" style={{ background: GOLD }} />
            <span className="text-[10px] text-white/85">Key moment: <span className="font-bold text-white">07:12</span> — the run that opened this report</span>
          </div>
        </div>
        <div className="relative mt-auto pt-4 smp-a smp-a-rise" style={{ animationDelay: "0.7s" }}>
          <div className="rounded-2xl p-3.5 bg-white/10 backdrop-blur-md border border-white/15">
            <div className="flex items-center gap-2">
              <ShieldCheck className="w-4 h-4" style={{ color: GOLD }} />
              <span className="text-[9.5px] font-black uppercase tracking-[0.14em] text-white">Identity locked</span>
            </div>
            <p className="text-[10.5px] text-white/70 leading-relaxed mt-1">
              Marked with 10 taps · optical tracking · dual verification. This is about <span className="text-white font-bold">your player</span> — never a lookalike.
            </p>
          </div>
        </div>
      </div>
    </Card>
  );
}

/* ---------- 2 · four pillars (light + pitch-lines watermark) ---------- */
function PillarBar({ label, score, meaning, delay }) {
  return (
    <div className="smp-a smp-a-rise" style={{ animationDelay: `${delay}s` }}>
      <div className="flex items-baseline justify-between">
        <span className="text-[11px] font-extrabold uppercase tracking-[0.1em] text-[#3D4A38]">{label}</span>
        <span className="font-barlow font-black text-[18px]" style={{ color: FOREST }}>{score.toFixed(1)}</span>
      </div>
      <div className="relative h-2.5 rounded-full mt-1.5" style={{ background: "rgba(18,64,42,0.12)" }}>
        <div
          className="absolute inset-y-0 left-0 rounded-full smp-a smp-a-fill"
          style={{ width: `${score * 10}%`, background: `linear-gradient(90deg, ${FOREST_L}, #7FA650)`, animationDelay: `${delay + 0.15}s` }}
        />
        <span
          aria-hidden
          className="absolute top-1/2 w-3.5 h-3.5 rounded-full smp-a smp-a-pop"
          style={{ left: `calc(${score * 10}% - 7px)`, background: GOLD, boxShadow: "0 0 10px rgba(245,196,67,0.8)", animationDelay: `${delay + 0.9}s` }}
        />
      </div>
      <p className="text-[11px] text-[#75816F] italic mt-1 leading-snug">{meaning}</p>
    </div>
  );
}

function PitchLines() {
  return (
    <svg aria-hidden className="absolute inset-0 w-full h-full pointer-events-none" viewBox="0 0 380 480" fill="none" style={{ opacity: 0.08 }}>
      <circle cx="190" cy="240" r="80" stroke={FOREST} strokeWidth="1.5" />
      <line x1="0" y1="240" x2="380" y2="240" stroke={FOREST} strokeWidth="1.5" />
      <rect x="110" y="-40" width="160" height="90" stroke={FOREST} strokeWidth="1.5" />
      <rect x="110" y="430" width="160" height="90" stroke={FOREST} strokeWidth="1.5" />
    </svg>
  );
}

function PillarsCard() {
  return (
    <Card testid="sample-card-pillars" style={{ background: "linear-gradient(170deg, #FBF9F3 0%, #F1EDDF 100%)", border: "1px solid rgba(18,64,42,0.12)" }}>
      <div className="relative flex-1 flex flex-col p-6 overflow-hidden">
        <PitchLines />
        <Grain opacity={0.03} />
        <div className="smp-a smp-a-rise">
          <Kicker page="2 / 11">The numbers — translated into truth</Kicker>
          <h3 className="font-barlow font-black uppercase tracking-tight text-[21px] text-[#182016] mt-0.5">Things He Never Knew</h3>
        </div>
        <div className="relative mt-5 space-y-4">
          <PillarBar label="Technical" score={8.4} meaning="His first touch buys him time others don't have." delay={0.1} />
          <PillarBar label="Game intelligence" score={7.6} meaning="Sees the pass early — plays it a beat later." delay={0.28} />
          <PillarBar label="Physical" score={7.9} meaning="Wins the metres that decide a 1v1." delay={0.46} />
          <PillarBar label="Mentality" score={8.1} meaning="A mistake switches him on — not off." delay={0.64} />
        </div>
        <div className="relative mt-auto pt-4 smp-a smp-a-rise" style={{ animationDelay: "0.9s" }}>
          <div className="rounded-2xl p-3.5 flex items-center gap-3" style={{ background: FOREST }}>
            <Sparkles className="w-5 h-5 shrink-0" style={{ color: GOLD }} />
            <p className="text-[11.5px] text-white/85 leading-snug">
              <span className="font-black text-white">Top 15% for his age group</span> — and now he knows exactly <span className="font-black" style={{ color: GOLD }}>why</span>.
            </p>
          </div>
        </div>
      </div>
    </Card>
  );
}

/* ---------- 3 · superpowers (photo: rain training, gold bolts) ---------- */
function StrengthsCard() {
  const strengths = [
    "Attacks his defender 1v1 without hesitation",
    "First touch opens the field — rarely needs a second",
    "Keeps working after losing the ball",
  ];
  return (
    <Card testid="sample-card-strengths" style={{ background: "#123526", border: "1px solid rgba(245,196,67,0.16)" }}>
      <div className="relative flex-1 flex flex-col p-6 overflow-hidden">
        <Photo src={`${ASSET}/api/static/landing/carousel-bg-6.jpg`} style={{ opacity: 0.38 }} />
        <div aria-hidden className="absolute inset-0" style={{ background: `linear-gradient(180deg, ${FOREST_L}D9 0%, ${FOREST}99 45%, #0D2E1DF2 100%)` }} />
        <div aria-hidden className="absolute -right-5 top-6 font-barlow font-black leading-none pointer-events-none select-none" style={{ fontSize: 170, color: "rgba(255,255,255,0.05)" }}>3</div>
        <Grain />
        <div className="relative smp-a smp-a-rise">
          <Kicker color={GOLD} page="3 / 11" light>What the scout saw</Kicker>
          <h3 className="font-barlow font-black uppercase tracking-tight text-[21px] text-white mt-0.5 leading-tight" style={{ textShadow: "0 2px 10px rgba(10,26,16,0.5)" }}>
            Superpowers he<br />didn&apos;t know he had
          </h3>
        </div>
        <div className="relative mt-4 space-y-2.5">
          {strengths.map((s, i) => (
            <div key={s} className={`flex items-start gap-2.5 rounded-2xl p-3 bg-white/10 backdrop-blur-md border border-white/12 smp-a ${i % 2 ? "smp-a-slideR" : "smp-a-slideL"}`} style={{ animationDelay: `${0.15 + 0.16 * i}s` }}>
              <span className="shrink-0 w-6 h-6 rounded-full flex items-center justify-center mt-0.5" style={{ background: "rgba(245,196,67,0.18)" }}>
                <Zap className="w-3.5 h-3.5" style={{ color: GOLD }} />
              </span>
              <p className="text-[12.5px] text-white/90 leading-snug">{s}</p>
            </div>
          ))}
        </div>
        <div className="relative mt-auto pt-4 smp-a smp-a-tilt" style={{ animationDelay: "0.72s" }}>
          <div className="rounded-2xl p-3.5" style={{ background: "rgba(12,42,26,0.9)", border: `1px solid ${GOLD}66`, boxShadow: "0 8px 24px -8px rgba(0,0,0,0.5)" }}>
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

/* ---------- 4 · pace (photo: muddy boots, drawing sprint path) ---------- */
function PaceCardSample() {
  return (
    <Card testid="sample-card-pace">
      <div className="relative flex-1 flex flex-col p-6 overflow-hidden">
        <Photo src={`${ASSET}/api/static/landing/carousel-bg-2.jpg`} />
        <div aria-hidden className="absolute inset-0" style={{ background: `linear-gradient(180deg, ${FOREST}E0 0%, ${FOREST}59 45%, ${FOREST}F0 100%)` }} />
        <svg aria-hidden className="absolute inset-0 w-full h-full pointer-events-none" viewBox="0 0 380 440" fill="none">
          <path className="smp-a smp-a-draw" d="M-10 340 C 90 300, 150 380, 230 320 S 360 220, 400 250" stroke={GOLD} strokeWidth="2.5" strokeDasharray="1" pathLength="1" opacity="0.75" style={{ animationDelay: "0.4s" }} />
        </svg>
        <div className="relative smp-a smp-a-rise">
          <Kicker color={GOLD} page="4 / 11" light>Measured — never guessed</Kicker>
          <h3 className="font-barlow font-black uppercase tracking-tight text-[21px] text-white mt-0.5" style={{ textShadow: "0 2px 10px rgba(10,26,16,0.5)" }}>How fast is he really?</h3>
        </div>
        <div className="relative mt-6 smp-a smp-a-slideL" style={{ animationDelay: "0.18s" }}>
          <div className="flex items-baseline gap-2">
            <span className="font-barlow font-black text-[64px] leading-none text-white" style={{ textShadow: "0 0 30px rgba(255,255,255,0.35)" }}>24.1</span>
            <span className="font-black text-[15px]" style={{ color: GOLD }}>KM/H</span>
          </div>
          <div className="text-[9.5px] font-black uppercase tracking-[0.18em] text-white/65 mt-1">Top speed · from his own match</div>
          <div className="flex gap-2 mt-4">
            {[["7", "Sprints"], ["412 m", "Tracked"]].map(([v, l], i) => (
              <div key={l} className="rounded-2xl px-4 py-2.5 bg-white/10 backdrop-blur-md border border-white/15 text-center smp-a smp-a-pop" style={{ animationDelay: `${0.5 + i * 0.15}s` }}>
                <div className="font-barlow font-black text-[20px] leading-none text-white">{v}</div>
                <div className="text-[8.5px] font-black uppercase tracking-[0.12em] text-white/60 mt-1">{l}</div>
              </div>
            ))}
          </div>
        </div>
        <div className="relative mt-auto pt-4 smp-a smp-a-rise" style={{ animationDelay: "0.8s" }}>
          <p className="text-[12.5px] text-white/85 leading-snug italic">
            "Faster than most wingers his age — and the report shows the <span className="font-bold not-italic" style={{ color: GOLD }}>exact sprint</span> where he proved it."
          </p>
          <div className="flex items-center gap-2 mt-2.5">
            <Gauge className="w-3.5 h-3.5 shrink-0" style={{ color: GOLD }} />
            <p className="text-[10px] text-white/55">Pixel-level tracking of your marked player — never invented.</p>
          </div>
        </div>
      </div>
    </Card>
  );
}

/* ---------- 5 · parent curiosity (photo: golden hour, wiggling locks) ---------- */
function CuriosityCard() {
  const rows = [
    "Which foot does he really trust under pressure?",
    "What happens in the 8 seconds after he loses the ball?",
    "The habit a scout would notice first?",
  ];
  return (
    <Card testid="sample-card-curiosity">
      <div className="relative flex-1 flex flex-col p-6 overflow-hidden">
        <Photo src={`${ASSET}/api/blog/uploads/cover-bounce-back.jpg`} />
        <div aria-hidden className="absolute inset-0" style={{ background: `linear-gradient(180deg, ${FOREST}4D 0%, ${FOREST}80 45%, ${FOREST}F5 100%)` }} />
        <div className="relative smp-a smp-a-rise">
          <Kicker color="#F3E9C8" page="5 / 11" light>The things you&apos;ll finally know</Kicker>
          <h3 className="font-barlow font-black uppercase tracking-tight text-[21px] text-white mt-0.5" style={{ textShadow: "0 2px 12px rgba(10,26,16,0.55)" }}>
            What you&apos;ll discover
          </h3>
        </div>
        <div className="relative mt-auto space-y-2">
          {rows.map((q, i) => (
            <div key={q} className="rounded-2xl px-3.5 py-2.5 bg-white/12 backdrop-blur-md border border-white/20 smp-a smp-a-rise" style={{ animationDelay: `${0.15 + 0.15 * i}s` }}>
              <p className="text-[12px] font-bold text-white leading-snug">{q}</p>
              <div className="flex items-center gap-1.5 mt-1">
                <Lock className="w-3 h-3 shrink-0 smp-wiggle" style={{ color: GOLD, animationDelay: `${1 + i * 0.4}s` }} />
                <span className="text-[10.5px] text-white/70 blur-[4px] select-none">The answer is waiting in the report</span>
              </div>
            </div>
          ))}
          <div className="flex items-center justify-center gap-2 pt-2 smp-a smp-a-rise" style={{ animationDelay: "0.7s" }}>
            <span className="w-1.5 h-1.5 rounded-full" style={{ background: GOLD, animation: "smp-blink 1.6s ease-in-out infinite" }} />
            <p className="text-[10.5px] font-black uppercase tracking-[0.14em]" style={{ color: GOLD }}>Unlock the full picture — with the clip to prove it</p>
          </div>
        </div>
      </div>
    </Card>
  );
}

/* ---------- 6 · honest answers (light, alternating slide-ins) ---------- */
function ParentsCard() {
  const rows = [
    ["Does he demand the ball?", "11 touches · always available"],
    ["Is he brave?", "8.5 / 10 — takes his man on"],
    ["After a mistake?", "Wins the ball straight back"],
    ["Work without the ball?", "7.0 — and growing"],
  ];
  return (
    <Card testid="sample-card-parents" style={{ background: "linear-gradient(160deg, #FBF9F3 0%, #F3EFE1 100%)", border: "1px solid rgba(18,64,42,0.12)" }}>
      <div className="relative flex-1 flex flex-col p-6 overflow-hidden">
        <div aria-hidden className="absolute -top-8 -right-3 font-serif leading-none pointer-events-none select-none" style={{ fontSize: 190, color: "rgba(18,64,42,0.07)" }}>&rdquo;</div>
        <Grain opacity={0.03} />
        <div className="smp-a smp-a-rise">
          <Kicker page="6 / 11">The questions you whisper</Kicker>
          <h3 className="font-barlow font-black uppercase tracking-tight text-[21px] text-[#182016] mt-0.5">What parents ask</h3>
        </div>
        <div className="relative mt-4 space-y-2">
          {rows.map(([k, v], i) => (
            <div key={k} className={`flex items-center justify-between gap-3 bg-white border border-[#12402A1A] rounded-2xl px-3.5 py-2.5 smp-a ${i % 2 ? "smp-a-slideR" : "smp-a-slideL"}`} style={{ animationDelay: `${0.12 + 0.13 * i}s` }}>
              <span className="text-[10.5px] font-extrabold uppercase tracking-[0.08em] text-[#75816F]">{k}</span>
              <span className="font-barlow font-black text-[14px] text-right" style={{ color: FOREST }}>{v}</span>
            </div>
          ))}
        </div>
        <div className="relative mt-auto pt-4 flex items-start gap-2.5 smp-a smp-a-rise" style={{ animationDelay: "0.75s" }}>
          <HeartHandshake className="w-4 h-4 mt-0.5 shrink-0" style={{ color: GOLD }} />
          <p className="text-[11px] text-[#8A937F] leading-relaxed">
            Answered honestly, with warmth. If there isn&apos;t enough evidence, the report says so — instead of guessing.
          </p>
        </div>
      </div>
    </Card>
  );
}

/* ---------- 7 · 90-day plan (photo: tunnel, timeline draws down) ---------- */
function PlanCard() {
  const nodes = [
    ["Today", "Scanning before receiving — 10 min, 3×/week"],
    ["Week 4", "First touch under pressure — wall drills"],
    ["Week 12", "1v1 end product — final pass & finish"],
  ];
  return (
    <Card testid="sample-card-plan" style={{ background: "#0F3823", border: "1px solid rgba(245,196,67,0.16)" }}>
      <div className="relative flex-1 flex flex-col p-6 overflow-hidden">
        <Photo src={`${ASSET}/api/static/landing/carousel-bg-4.jpg`} style={{ opacity: 0.32 }} />
        <div aria-hidden className="absolute inset-0" style={{ background: `linear-gradient(180deg, ${FOREST}E6 0%, ${FOREST}8C 45%, #0C2E1CF5 100%)` }} />
        <Grain />
        <div className="relative smp-a smp-a-rise">
          <Kicker color={GOLD} page="7 / 11" light>Personal roadmap</Kicker>
          <h3 className="font-barlow font-black uppercase tracking-tight text-[21px] text-white mt-0.5 leading-tight" style={{ textShadow: "0 2px 10px rgba(10,26,16,0.5)" }}>
            A map to who<br />he&apos;s becoming
          </h3>
        </div>
        <div className="relative mt-5 pl-6 flex-1">
          <div aria-hidden className="absolute left-[9px] top-2 bottom-3 w-[2px] smp-a smp-a-growY" style={{ background: `linear-gradient(180deg, ${GOLD}, ${GOLD}33)`, animationDelay: "0.2s" }} />
          <div className="space-y-4">
            {nodes.map(([k, t], i) => (
              <div key={k} className="relative smp-a smp-a-rise" style={{ animationDelay: `${0.35 + 0.2 * i}s` }}>
                <span aria-hidden className="absolute -left-6 top-0.5 w-[18px] h-[18px] rounded-full border-2 flex items-center justify-center"
                  style={i === 0
                    ? { background: GOLD, borderColor: GOLD, boxShadow: "0 0 14px rgba(245,196,67,0.7)" }
                    : { background: "#0F3823", borderColor: "rgba(245,196,67,0.5)" }}>
                  {i === 0 && <span className="w-1.5 h-1.5 rounded-full" style={{ background: FOREST }} />}
                </span>
                <div className="text-[9.5px] font-black uppercase tracking-[0.16em]" style={{ color: i === 0 ? GOLD : "rgba(255,255,255,0.55)" }}>{k}</div>
                <div className="mt-1 rounded-2xl p-3 bg-white/10 backdrop-blur-md border border-white/10">
                  <p className="text-[12px] text-white/90 leading-snug">{t}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
        <div className="relative mt-auto pt-4 flex items-start gap-2.5 smp-a smp-a-rise" style={{ animationDelay: "1s" }}>
          <CalendarRange className="w-4 h-4 mt-0.5 shrink-0" style={{ color: GOLD }} />
          <p className="text-[10.5px] text-white/60 leading-relaxed">
            Plus 3 countable <span className="font-bold text-white/90">next-match missions</span> for the weekend game.
          </p>
        </div>
      </div>
    </Card>
  );
}

/* ---------- 8 · the road ahead (photo: dusk silhouette, steps light up) ---------- */
function RoadCard() {
  return (
    <Card testid="sample-card-road">
      <div className="relative flex-1 flex flex-col p-6 overflow-hidden">
        <Photo src={`${ASSET}/api/static/landing/carousel-bg-1.jpg`} />
        <div aria-hidden className="absolute inset-0" style={{ background: `linear-gradient(180deg, ${FOREST_L}40 0%, ${FOREST}73 50%, ${FOREST}F0 100%)` }} />
        <div aria-hidden className="absolute -bottom-20 left-1/2 -translate-x-1/2 w-72 h-72 rounded-full pointer-events-none" style={{ background: "radial-gradient(circle, rgba(245,196,67,0.3) 0%, transparent 65%)" }} />
        <div className="relative smp-a smp-a-rise">
          <Kicker color={GOLD} page="8 / 11" light>Where this can lead</Kicker>
          <h3 className="font-barlow font-black uppercase tracking-tight text-[26px] text-white mt-0.5 leading-[1.02]" style={{ textShadow: "0 2px 14px rgba(10,26,16,0.6)" }}>
            The road<br />ahead
          </h3>
        </div>
        <div className="relative mt-auto">
          <p className="font-barlow font-black uppercase text-[17px] leading-tight smp-a smp-a-slideL" style={{ color: GOLD, textShadow: "0 2px 10px rgba(10,26,16,0.6)", animationDelay: "0.2s" }}>
            From the local pitch<br />to the scout&apos;s notebook.
          </p>
          <div className="mt-3 space-y-2">
            {[["Today", "One clip — the game finally on record"], ["This season", "Training with purpose, not guesses"], ["When he's ready", "Visible to real scouts who are looking"]].map(([k, t], i) => (
              <div key={k} className="flex items-start gap-2.5 smp-a smp-a-slideL" style={{ animationDelay: `${0.4 + 0.2 * i}s` }}>
                <span aria-hidden className="w-2 h-2 rounded-full shrink-0 mt-1" style={i === 0 ? { background: GOLD, boxShadow: "0 0 10px rgba(245,196,67,0.9)" } : { background: "rgba(245,196,67,0.45)" }} />
                <div className="min-w-0">
                  <div className="text-[9.5px] font-black uppercase tracking-[0.14em] leading-none" style={{ color: GOLD }}>{k}</div>
                  <p className="text-[11.5px] text-white/85 leading-snug mt-0.5">{t}</p>
                </div>
              </div>
            ))}
          </div>
          <div className="flex items-start gap-2 mt-3.5 pt-3 border-t border-white/15 smp-a smp-a-rise" style={{ animationDelay: "1.05s" }}>
            <Footprints className="w-3.5 h-3.5 mt-0.5 shrink-0" style={{ color: GOLD }} />
            <p className="text-[10px] text-white/60 leading-relaxed">No promises — just a clear next step. Every step is <span className="font-bold text-white/85">his own</span>. We light the road.</p>
          </div>
        </div>
      </div>
    </Card>
  );
}

/* ---------- 9 · a real scout replied (bubbles arrive like a live chat) ---------- */
function ScoutReplyCard() {
  return (
    <Card testid="sample-card-scoutreply" style={{ background: "linear-gradient(165deg, #FBF9F3 0%, #F1EDE0 100%)", border: "1px solid rgba(18,64,42,0.12)" }}>
      <div className="relative flex-1 flex flex-col p-6 overflow-hidden">
        <Grain opacity={0.03} />
        <div className="smp-a smp-a-rise">
          <Kicker page="9 / 11">Not just software — real people</Kicker>
          <h3 className="font-barlow font-black uppercase tracking-tight text-[21px] text-[#182016] mt-0.5">A real scout replied</h3>
        </div>
        <div className="mt-4 flex items-start gap-3">
          <div className="relative shrink-0 smp-a smp-a-pop" style={{ animationDelay: "0.15s" }}>
            <div className="w-11 h-11 rounded-full flex items-center justify-center font-barlow font-black text-[14px]" style={{ background: `linear-gradient(140deg, ${FOREST_L}, ${FOREST})`, color: GOLD, boxShadow: "0 6px 16px -6px rgba(18,64,42,0.6)" }}>JK</div>
            <span aria-hidden className="absolute -bottom-0.5 -right-0.5 w-3.5 h-3.5 rounded-full border-2 border-[#FBF9F3]" style={{ background: "#3BA55D", animation: "smp-blink 2s ease-in-out infinite" }} />
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-baseline gap-2 smp-a smp-a-rise" style={{ animationDelay: "0.2s" }}>
              <span className="text-[11.5px] font-black text-[#182016]">J. K.</span>
              <span className="text-[9px] font-black uppercase tracking-[0.1em] text-[#75816F]">Professional scout · 14 yrs</span>
            </div>
            <div className="mt-1.5 rounded-2xl rounded-tl-md bg-white border border-[#12402A1A] p-3.5 shadow-sm smp-a smp-a-bubble" style={{ animationDelay: "0.55s" }}>
              <p className="text-[12.5px] text-[#3D4A38] leading-relaxed">
                "I watched the clip twice. The way he attacks the back post at <span className="font-bold" style={{ color: FOREST }}>07:12</span> — that&apos;s not taught, that&apos;s instinct. Keep him wide. Keep him brave."
              </p>
            </div>
            <div className="mt-2 rounded-2xl rounded-tl-md p-3.5 smp-a smp-a-bubble" style={{ background: FOREST, animationDelay: "1.4s" }}>
              <p className="text-[12px] text-white/90 leading-snug">
                One drill from me: <span className="font-bold" style={{ color: GOLD }}>back-post timing, 2×/week</span>. Small habit — big difference at trials.
              </p>
            </div>
            <div className="flex items-center gap-1.5 mt-2 pl-1 smp-a smp-a-rise" style={{ animationDelay: "2s" }}>
              {[0, 1, 2].map((i) => (
                <span key={i} className="w-1.5 h-1.5 rounded-full bg-[#75816F]" style={{ animation: `smp-blink 1.2s ${i * 0.2}s ease-in-out infinite` }} />
              ))}
              <span className="text-[9.5px] text-[#8A937F] ml-1">scout is typing…</span>
            </div>
          </div>
        </div>
        <div className="relative mt-auto pt-4 flex items-start gap-2.5 smp-a smp-a-rise" style={{ animationDelay: "0.9s" }}>
          <MessageCircle className="w-4 h-4 mt-0.5 shrink-0" style={{ color: GOLD }} />
          <p className="text-[11px] text-[#8A937F] leading-relaxed">
            A real, experienced scout reads the report and writes back — <span className="font-bold text-[#3D4A38]">personal words about the player&apos;s game</span>, never a template.
          </p>
        </div>
      </div>
    </Card>
  );
}

/* ---------- 10 · spotted (radar ping + notification slides in) ---------- */
function LibraryCard() {
  return (
    <Card testid="sample-card-library" style={{ background: "linear-gradient(150deg, #10331F 0%, #16241B 100%)", border: "1px solid rgba(245,196,67,0.16)" }}>
      <div className="relative flex-1 flex flex-col p-6 overflow-hidden">
        <Grain />
        <div aria-hidden className="absolute inset-0 pointer-events-none" style={{ backgroundImage: "radial-gradient(rgba(245,196,67,0.06) 1px, transparent 1px)", backgroundSize: "22px 22px" }} />
        <div className="relative smp-a smp-a-rise">
          <Kicker color={GOLD} page="10 / 11" light>Being seen changes everything</Kicker>
          <h3 className="font-barlow font-black uppercase tracking-tight text-[24px] text-white mt-0.5 leading-tight">
            You&apos;ve been<br />spotted
          </h3>
        </div>
        <div className="relative mx-auto mt-4 mb-1 smp-a smp-a-pop" style={{ width: 172, height: 172, animationDelay: "0.2s" }}>
          {[172, 124, 76].map((d, i) => (
            <span key={d} aria-hidden className="absolute rounded-full border"
              style={{
                width: d, height: d, left: (172 - d) / 2, top: (172 - d) / 2,
                borderColor: "rgba(245,196,67,0.3)",
                animation: `smp-radar 3s ${i * 0.5}s ease-out infinite`,
              }} />
          ))}
          <span aria-hidden className="absolute rounded-full" style={{ width: 14, height: 14, left: 79, top: 79, background: GOLD, boxShadow: "0 0 22px rgba(245,196,67,0.9)", animation: "smp-blink 1.6s ease-in-out infinite" }} />
          <span aria-hidden className="absolute rounded-full" style={{ width: 8, height: 8, left: 122, top: 44, background: "rgba(245,196,67,0.8)", animation: "smp-blink 2.4s 0.8s ease-in-out infinite" }} />
          <span aria-hidden className="absolute inset-0 rounded-full" style={{ background: "conic-gradient(from 0deg, rgba(245,196,67,0.2), transparent 70%)", animation: "smp-spin 4s linear infinite" }} />
        </div>
        <div className="relative rounded-2xl p-3.5 bg-white/10 backdrop-blur-md border border-white/15 smp-a smp-a-slideUp" style={{ animationDelay: "0.9s" }}>
          <div className="flex items-start gap-2">
            <Eye className="w-4 h-4 shrink-0 mt-0.5" style={{ color: GOLD }} />
            <p className="text-[11.5px] text-white/90 leading-snug">
              A scout opened his profile <span className="font-bold text-white">today</span>{" "}
              <span className="text-[8.5px] font-black uppercase tracking-[0.1em] px-2 py-0.5 rounded-full align-middle whitespace-nowrap" style={{ background: "rgba(245,196,67,0.16)", color: GOLD }}>3× this month</span>
            </p>
          </div>
          <p className="text-[10px] text-white/55 mt-1.5 pl-6">— while he was at training, dreaming about it.</p>
        </div>
        <div className="relative mt-auto pt-3 flex items-start gap-2.5 smp-a smp-a-rise" style={{ animationDelay: "1.2s" }}>
          <ShieldCheck className="w-4 h-4 mt-0.5 shrink-0" style={{ color: GOLD }} />
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
        <Photo src={`${ASSET}/api/static/landing/finalcta-stadium.jpg`} />
        <div aria-hidden className="absolute inset-0" style={{ background: `linear-gradient(180deg, ${FOREST}99 0%, ${FOREST}40 45%, ${FOREST}F0 100%)` }} />
        <div className="relative flex items-center gap-2 smp-a smp-a-rise">
          <Sparkles className="w-4 h-4" style={{ color: GOLD }} />
          <span className="text-[10px] font-black uppercase tracking-[0.22em]" style={{ color: GOLD }}>Your story is next</span>
        </div>
        <h3 className="relative font-barlow font-black uppercase text-white text-[27px] leading-[1.02] mt-3 smp-a smp-a-rise" style={{ textShadow: "0 2px 14px rgba(10,26,16,0.55)", animationDelay: "0.15s" }}>
          It starts with<br />one video.<br />
          <span style={{ color: LIME }}>The rest is<br />your story.</span>
        </h3>
        <div className="relative mt-auto pt-6">
          <p className="text-[12.5px] text-white/85 leading-relaxed mb-4 smp-a smp-a-rise" style={{ animationDelay: "0.35s" }}>
            The lights are already on. The next report we write could be about <span className="font-bold text-white">you</span>.
          </p>
          <button
            type="button"
            data-testid="sample-report-cta"
            onClick={onPrimaryCta}
            className="relative overflow-hidden w-full inline-flex items-center justify-center gap-2 font-barlow font-black uppercase tracking-[0.12em] text-[14px] px-6 py-4 rounded-2xl transition-transform active:scale-[0.98] hover:scale-[1.02] smp-a smp-a-slideUp"
            style={{ background: LIME, color: "#0D2818", animationDelay: "0.5s", boxShadow: "0 0 28px rgba(204,255,0,0.35)" }}
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
        .smp-a { opacity: 0; }
        .smp-inview .smp-a { animation-fill-mode: both; }
        .smp-inview .smp-a-rise { animation: smp-rise 0.65s cubic-bezier(0.22,1,0.36,1) both; }
        .smp-inview .smp-a-slideL { animation: smp-slideL 0.65s cubic-bezier(0.22,1,0.36,1) both; }
        .smp-inview .smp-a-slideR { animation: smp-slideR 0.65s cubic-bezier(0.22,1,0.36,1) both; }
        .smp-inview .smp-a-slideUp { animation: smp-slideUp 0.7s cubic-bezier(0.22,1,0.36,1) both; }
        .smp-inview .smp-a-pop { animation: smp-pop 0.5s cubic-bezier(0.34,1.56,0.64,1) both; }
        .smp-inview .smp-a-bubble { animation: smp-bubble 0.55s cubic-bezier(0.34,1.56,0.64,1) both; }
        .smp-inview .smp-a-tilt { animation: smp-tilt 0.7s cubic-bezier(0.34,1.56,0.64,1) both; }
        .smp-a-fill { transform: scaleX(0); transform-origin: left; opacity: 1; }
        .smp-inview .smp-a-fill { animation: smp-fillx 1s cubic-bezier(0.22,1,0.36,1) both; }
        .smp-a-draw { stroke-dashoffset: 1; opacity: 1; }
        .smp-inview .smp-a-draw { animation: smp-draw 1.6s ease-out both; }
        .smp-a-growY { transform: scaleY(0); transform-origin: top; opacity: 1; }
        .smp-inview .smp-a-growY { animation: smp-growy 0.9s ease-out both; }
        .smp-inview .smp-wiggle { animation: smp-wiggle 0.6s ease-in-out both; }
        .smp-kenburns { animation: smp-kenburns 16s ease-in-out infinite alternate; }
        @keyframes smp-rise { from { opacity: 0; transform: translateY(14px); } to { opacity: 1; transform: translateY(0); } }
        @keyframes smp-slideL { from { opacity: 0; transform: translateX(-18px); } to { opacity: 1; transform: translateX(0); } }
        @keyframes smp-slideR { from { opacity: 0; transform: translateX(18px); } to { opacity: 1; transform: translateX(0); } }
        @keyframes smp-slideUp { from { opacity: 0; transform: translateY(26px); } to { opacity: 1; transform: translateY(0); } }
        @keyframes smp-pop { from { opacity: 0; transform: scale(0.4); } to { opacity: 1; transform: scale(1); } }
        @keyframes smp-bubble { from { opacity: 0; transform: translateY(10px) scale(0.92); } to { opacity: 1; transform: translateY(0) scale(1); } }
        @keyframes smp-tilt { from { opacity: 0; transform: rotate(-4deg) translateY(16px); } to { opacity: 1; transform: rotate(-1deg) translateY(0); } }
        @keyframes smp-fillx { from { transform: scaleX(0); } to { transform: scaleX(1); } }
        @keyframes smp-draw { from { stroke-dashoffset: 1; } to { stroke-dashoffset: 0; } }
        @keyframes smp-growy { from { transform: scaleY(0); } to { transform: scaleY(1); } }
        @keyframes smp-wiggle { 0%,100% { transform: rotate(0); } 25% { transform: rotate(-14deg); } 55% { transform: rotate(11deg); } 80% { transform: rotate(-6deg); } }
        @keyframes smp-blink { 0%,100% { opacity: 1; } 50% { opacity: 0.35; } }
        @keyframes smp-radar { 0% { transform: scale(0.6); opacity: 0.9; } 100% { transform: scale(1.25); opacity: 0; } }
        @keyframes smp-spin { to { transform: rotate(360deg); } }
        @keyframes smp-kenburns { from { transform: scale(1); } to { transform: scale(1.09) translateX(-6px); } }
        @keyframes smp-cta-shine { 0% { transform: translateX(-120%) skewX(-18deg); } 60%, 100% { transform: translateX(220%) skewX(-18deg); } }
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
        <button
          type="button" aria-label="Previous card" data-testid="sample-arrow-prev" onClick={() => nudge(-1)}
          disabled={edge.start}
          className={`sm:hidden absolute left-1.5 top-1/2 -translate-y-1/2 z-20 w-10 h-10 rounded-full flex items-center justify-center backdrop-blur-md active:scale-90 transition-all duration-300 ${edge.start ? "opacity-25 pointer-events-none" : "opacity-100"}`}
          style={{ background: "rgba(18,64,42,0.72)", border: "1px solid rgba(245,196,67,0.6)", boxShadow: "0 4px 18px rgba(0,0,0,0.3)" }}
        >
          <ChevronLeft className="w-5 h-5" style={{ color: GOLD }} />
        </button>
        <button
          type="button" aria-label="Next card" data-testid="sample-arrow-next" onClick={() => nudge(1)}
          disabled={edge.end}
          className={`sm:hidden absolute right-1.5 top-1/2 -translate-y-1/2 z-20 w-10 h-10 rounded-full flex items-center justify-center backdrop-blur-md active:scale-90 transition-all duration-300 ${edge.end ? "opacity-25 pointer-events-none" : "opacity-100"}`}
          style={{ background: "rgba(18,64,42,0.72)", border: "1px solid rgba(245,196,67,0.6)", boxShadow: "0 4px 18px rgba(0,0,0,0.3)" }}
        >
          <ChevronRight className="w-5 h-5" style={{ color: GOLD }} />
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
