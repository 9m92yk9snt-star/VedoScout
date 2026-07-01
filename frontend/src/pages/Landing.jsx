import React, { useEffect, useState, useRef } from "react";
import { Link } from "react-router-dom";
import { motion, useScroll, useInView, animate, useMotionValue } from "framer-motion";
import {
  Radar, RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, ResponsiveContainer,
} from "recharts";
import Navigation from "@/components/Navigation";
import api from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import {
  ArrowRight, ArrowDown, Upload, Zap, ShieldCheck, FileText, Star, Brain, Target,
  Activity, Heart, Eye, Trophy, Footprints, Lock, Play, CheckCircle2, Download,
  TrendingUp, Clock, Award, ClipboardList, Globe, Users,
  Lightbulb, Crown, Calendar, Dumbbell, Mail, Send, Twitter, Facebook, Linkedin, Instagram, MessageCircle,
} from "lucide-react";
import PaymentBadges from "@/components/PaymentBadges";
import PricingCards from "@/components/PricingCards";
import SEO, { organizationJsonLd } from "@/components/SEO";
import HowItWorksWalkthrough from "@/components/HowItWorksWalkthrough";

const fadeUp = {
  hidden: { opacity: 0, y: 18 },
  visible: (i = 0) => ({ opacity: 1, y: 0, transition: { delay: i * 0.06, duration: 0.5, ease: "easeOut" } }),
};

/* ===== Feature cards — natural football language ===== */
const reportCards = [
  {
    icon: Brain,
    title: "Player Report",
    text: "A complete breakdown of your game, strengths, and what makes you unique.",
    viz: { type: "scorePill", label: "Scout Score", value: "8.2/10" },
  },
  {
    icon: Footprints,
    title: "Technical",
    text: "First touch, passing, dribbling, shooting and everything you do with the ball.",
    viz: { type: "progressBar", percent: 81, value: "8.1" },
  },
  {
    icon: Target,
    title: "Tactical",
    text: "Positioning, game intelligence, movement and decision-making off the ball.",
    viz: { type: "heatmap" },
  },
  {
    icon: Activity,
    title: "Physical",
    text: "Speed, strength, endurance, agility and overall athletic performance.",
    viz: { type: "barChart", bars: [40, 55, 70, 78, 60, 50, 72, 55, 35, 78, 65, 70], value: "7.8" },
  },
  {
    icon: Lightbulb,
    title: "Mentality",
    text: "Confidence, focus, work rate and how you handle pressure & challenges.",
    viz: { type: "scorePill", label: "Mental Score", value: "8.5/10" },
  },
  {
    icon: Eye,
    title: "Scout View",
    text: "What a real scout would love, worry about, and the level that fits you next.",
    viz: { type: "stars", value: 4 },
  },
  {
    icon: Trophy,
    title: "Training Plan",
    text: "5 specific exercises + weekly focus + 30-day plan + 90-day plan.",
    viz: { type: "miniIcons", icons: [Calendar, Dumbbell, Target] },
  },
  {
    icon: TrendingUp,
    title: "Potential & Projection",
    text: "Your current level, potential ceiling, and realistic pathway to the next level.",
    viz: { type: "lineChart" },
  },
  {
    icon: ShieldCheck,
    title: "Comparison",
    text: "How you compare to players at your level and what sets you apart.",
    viz: { type: "topPercent", percent: 82, label: "TOP 18%" },
  },
  {
    icon: FileText,
    title: "Premium PDF",
    text: "A clean, professional report you can share with your coach, parents, or academies.",
    viz: { type: "pill", label: "PDF Included", PillIcon: FileText },
  },
  {
    icon: Lock,
    title: "Private & Secure",
    text: "Your data is safe. We never share your report with anyone.",
    viz: { type: "pill", label: "100% Private", PillIcon: Lock },
  },
];

/* ===== Card visualization renderer ===== */
function CardViz({ viz }) {
  if (!viz) return null;
  switch (viz.type) {
    case "scorePill":
      return (
        <div className="flex items-center justify-between gap-3">
          <span className="text-[10px] uppercase tracking-[0.15em] font-bold text-ink/70 border border-ink/10 rounded-full px-3 py-1.5 whitespace-nowrap">
            {viz.label}
          </span>
          <span className="font-barlow font-black text-2xl md:text-3xl text-volt leading-none">
            {viz.value}
          </span>
        </div>
      );
    case "progressBar":
      return (
        <div className="flex items-center gap-3">
          <div className="flex-1 h-2 bg-cream-soft/40 overflow-hidden">
            <div className="h-full bg-volt" style={{ width: `${viz.percent}%` }} />
          </div>
          <span className="font-barlow font-black text-volt text-lg leading-none">{viz.value}</span>
        </div>
      );
    case "heatmap":
      return (
        <svg viewBox="0 0 80 48" className="w-full h-16" aria-hidden>
          <rect width="80" height="48" fill="rgba(255,255,255,0.04)" stroke="rgba(255,255,255,0.18)" strokeWidth="0.5" />
          <line x1="40" y1="0" x2="40" y2="48" stroke="rgba(255,255,255,0.18)" strokeWidth="0.5" />
          <circle cx="40" cy="24" r="6" fill="none" stroke="rgba(255,255,255,0.18)" strokeWidth="0.5" />
          <rect x="0" y="14" width="6" height="20" fill="none" stroke="rgba(255,255,255,0.18)" strokeWidth="0.5" />
          <rect x="74" y="14" width="6" height="20" fill="none" stroke="rgba(255,255,255,0.18)" strokeWidth="0.5" />
          {/* Hot spots */}
          <circle cx="52" cy="24" r="9" fill="#ff5252" opacity="0.55" />
          <circle cx="44" cy="20" r="6" fill="#ff9a3c" opacity="0.7" />
          <circle cx="58" cy="30" r="5" fill="#ccff00" opacity="0.85" />
          <circle cx="64" cy="22" r="3" fill="#ccff00" opacity="0.7" />
        </svg>
      );
    case "barChart":
      return (
        <div className="flex items-end gap-1.5 h-10">
          {viz.bars.map((h, i) => (
            <div
              key={i}
              className={`flex-1 ${h > 60 ? "bg-volt" : "bg-cream-soft/60"}`}
              style={{ height: `${h}%` }}
            />
          ))}
          <span className="font-barlow font-black text-volt text-lg leading-none ml-2 self-center">{viz.value}</span>
        </div>
      );
    case "stars":
      return (
        <div className="flex items-center gap-1">
          {[1, 2, 3, 4, 5].map((i) => (
            <Star
              key={i}
              className={`w-5 h-5 ${i <= viz.value ? "text-volt fill-volt" : "text-ink/25"}`}
              strokeWidth={1.5}
            />
          ))}
        </div>
      );
    case "miniIcons":
      return (
        <div className="flex items-center gap-4">
          {viz.icons.map((Ic, i) => (
            <Ic key={i} className="w-5 h-5 text-volt" strokeWidth={1.5} />
          ))}
        </div>
      );
    case "lineChart":
      return (
        <svg viewBox="0 0 80 30" className="w-full h-12" aria-hidden>
          {/* baseline */}
          <line x1="0" y1="27" x2="80" y2="27" stroke="rgba(255,255,255,0.1)" strokeWidth="0.4" />
          <polyline
            points="2,24 12,22 22,18 32,20 42,15 52,11 62,8 72,4"
            fill="none"
            stroke="#ccff00"
            strokeWidth="1.4"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
          {[[2, 24], [12, 22], [22, 18], [32, 20], [42, 15], [52, 11], [62, 8], [72, 4]].map(([x, y], i) => (
            <circle key={i} cx={x} cy={y} r="1.2" fill="#ccff00" />
          ))}
          <text x="55" y="3" fontSize="3.4" fill="#ccff00" fontWeight="bold" letterSpacing="0.2">
            90-DAY
          </text>
        </svg>
      );
    case "topPercent":
      return (
        <div className="flex items-center gap-3">
          <div className="flex-1 h-2 bg-cream-soft/40 overflow-hidden">
            <div className="h-full bg-volt" style={{ width: `${viz.percent}%` }} />
          </div>
          <span className="font-barlow font-black text-volt text-sm leading-none whitespace-nowrap">{viz.label}</span>
        </div>
      );
    case "pill": {
      const { PillIcon } = viz;
      return (
        <span className="inline-flex items-center gap-2 text-[10px] uppercase tracking-[0.18em] font-bold text-ink/85 border border-ink/10 rounded-full px-3.5 py-1.5">
          {viz.label}
          {PillIcon && <PillIcon className="w-3.5 h-3.5 text-volt" />}
        </span>
      );
    }
    default:
      return null;
  }
}

/* ===== Sample report data — natural football language ===== */
const sample = {
  player: {
    name: "Lukas A.",
    number: 10,
    age: 14,
    position: "Attacking Midfielder",
    positionShort: "CAM",
    foot: "Left",
    club: "IK Falken U15",
    videoType: "Match clip",
    type: "Smart playmaker · strong left foot",
  },
  scores: { technical: 8, tactical: 9, physical: 7, mentality: 9, overall: 8 },
  summary:
    "Lukas is a smart playmaker who sees the game two steps ahead of others his age. He stays calm when defenders close him down and loves to play forward passes that cut the defence in half. His left foot is his weapon — he can find a teammate from almost anywhere on the pitch. The one thing to work on: he gets tired in the second half when he has to sprint again and again. Build the legs, and the rest is already there.",
  strengths: [
    "Always looks around before the ball arrives",
    "Strong left foot — passes that open up defences",
    "Stays calm even when two players close him down",
  ],
  improvement:
    "Gets tired late in matches. Needs more fitness work so he can keep pressing and running in the last 20 minutes.",
  technical: [
    { k: "First touch", v: 8 },
    { k: "Ball control", v: 8 },
    { k: "Dribbling", v: 7 },
    { k: "Passing", v: 9 },
    { k: "Shooting", v: 7 },
    { k: "Weak foot", v: 5 },
    { k: "1v1", v: 7 },
  ],
  tactical: [
    { k: "Positioning", v: 9 },
    { k: "Off-ball runs", v: 8 },
    { k: "Game awareness", v: 9 },
    { k: "Decision making", v: 9 },
    { k: "Timing of runs", v: 8 },
    { k: "Reading the game", v: 9 },
  ],
  scoutStrengths: [
    "Always looks around before he gets the ball",
    "Left foot can pick out any pass",
    "Calm under pressure",
  ],
  scoutConcerns: [
    "Tires late in matches",
    "Right foot needs work",
    "Slow to react when team loses the ball",
  ],
  nextLevel: "Ready to step up to a stronger U15 team or an academy trial",
  bestPosition: "Best as a creative #10 right behind the striker",
  timeline: [
    { t: "00:24", c: "Great first touch on a tough ball — already checking his shoulder before it arrives." },
    { t: "01:12", c: "Beats his man cleanly — fakes inside, goes outside, plays a perfect cut-back." },
    { t: "02:40", c: "Should look around earlier here — gets caught with the ball and loses it." },
    { t: "03:55", c: "Smart run in behind the defence — perfect timing between the two defenders." },
  ],
  exercise: {
    name: "Receive and turn",
    duration: "15 min",
    desc: "Stand in tight space with a teammate or cone behind you. Maximum three touches — open your body, turn, pass, repeat. Builds confidence on the ball when defenders are close.",
  },
};

// ── Position variants — switch the SAMPLE CARD between 4 player profiles (D)
const SAMPLE_VARIANTS = {
  CAM: { // existing Lukas (default)
    player: sample.player,
    scores: sample.scores,
    summary: sample.summary,
    shortVerdict: sample.shortVerdict,
    strengths: sample.strengths,
    improvement: sample.improvement,
  },
  GK: {
    player: {
      name: "Aron P.",
      number: 1,
      age: 14,
      position: "Goalkeeper",
      positionShort: "GK",
      foot: "Right",
      club: "FC Nordvest U15",
      videoType: "Training session",
      type: "Quick reflexes · brave on through balls",
    },
    scores: { technical: 7, tactical: 8, physical: 8, mentality: 9, overall: 8 },
    summary:
      "Aron is a calm, confident keeper who reads the game well. His distribution starts attacks — both feet are accurate over 30 metres. The bravery to come off his line on through balls is already at U17 level. Areas to grow: aerial command in crowded boxes and a louder voice organising the back four.",
    strengths: [
      "Brave coming off his line on through balls",
      "Both feet accurate up to 30 m for distribution",
      "Stays calm and composed when his team is under pressure",
    ],
    improvement:
      "Needs louder communication to organise the back four, and better aerial command in crowded six-yard boxes.",
  },
  DEF: {
    player: {
      name: "Mateo R.",
      number: 4,
      age: 14,
      position: "Centre Back",
      positionShort: "CB",
      foot: "Right",
      club: "AC Stelvio U15",
      videoType: "Match clip",
      type: "Aerial monster · strong reader of the game",
    },
    scores: { technical: 7, tactical: 9, physical: 9, mentality: 8, overall: 8 },
    summary:
      "Mateo dominates the air in his box and reads the game two steps ahead of strikers his age. He wins almost every duel and stays calm when his team is under pressure. To unlock the next level: improve his first step on quick turns, and cleaner passing under press.",
    strengths: [
      "Wins almost every aerial duel in his box",
      "Reads attackers two steps ahead — anticipates passes",
      "Stays composed when his side is under pressure",
    ],
    improvement:
      "First step on quick turns needs sharpening, and his short passing under high press still drops in accuracy.",
  },
  FWD: {
    player: {
      name: "Liam K.",
      number: 9,
      age: 14,
      position: "Striker",
      positionShort: "ST",
      foot: "Right",
      club: "IFK Visby U15",
      videoType: "Match highlights",
      type: "Cold finisher · clever runs in behind",
    },
    scores: { technical: 8, tactical: 8, physical: 8, mentality: 9, overall: 8 },
    summary:
      "Liam scores in moments where others freeze. The composure inside the box is rare for his age and his timing of runs in behind defences is already pro-level. To round out the game: link play with the midfield and intensity off the ball when his team loses possession.",
    strengths: [
      "Stays cold-blooded inside the box — finishes when others freeze",
      "Timing of runs in behind defences is already pro-level",
      "First-touch turn-and-shoot is consistent across both feet",
    ],
    improvement:
      "Link-up play with the midfield needs more variety, and pressing intensity drops the moment his team loses the ball.",
  },
};
const POSITIONS = [
  { id: "GK",  label: "GK" },
  { id: "DEF", label: "DEF" },
  { id: "CAM", label: "MID" },
  { id: "FWD", label: "FWD" },
];

/* ─────────────────────────────────────────────────────────────────
 * BentoTiltCard — 3D mouse-tracked tilt wrapper for cards (C)
 * Tilts up to 5° based on mouse position over the card.
 * Returns smoothly to neutral on mouse-leave.
 * Drop-in replacement for <motion.div> with all motion props supported.
 * ──────────────────────────────────────────────────────────────── */
const BentoTiltCard = React.forwardRef(function BentoTiltCard(
  { children, className, style, maxTilt = 5, ...rest },
  fwdRef
) {
  const localRef = useRef(null);
  const ref = fwdRef || localRef;
  const rotateX = useMotionValue(0);
  const rotateY = useMotionValue(0);

  const handleMove = (e) => {
    const node = ref.current;
    if (!node) return;
    const r = node.getBoundingClientRect();
    const x = (e.clientX - r.left) / r.width;
    const y = (e.clientY - r.top) / r.height;
    rotateY.set((x - 0.5) * maxTilt * 2);
    rotateX.set(-(y - 0.5) * maxTilt * 2);
  };
  const handleLeave = () => {
    animate(rotateX, 0, { duration: 0.4, ease: "easeOut" });
    animate(rotateY, 0, { duration: 0.4, ease: "easeOut" });
  };

  return (
    <motion.div
      ref={ref}
      onMouseMove={handleMove}
      onMouseLeave={handleLeave}
      className={className}
      style={{
        rotateX,
        rotateY,
        transformPerspective: 1000,
        transformStyle: "preserve-3d",
        willChange: "transform",
        ...style,
      }}
      {...rest}
    >
      {children}
    </motion.div>
  );
});

const radarData = [
  { axis: "Technical", v: sample.scores.technical },
  { axis: "Tactical", v: sample.scores.tactical },
  { axis: "Physical", v: sample.scores.physical },
  { axis: "Mentality", v: sample.scores.mentality },
  { axis: "Overall", v: sample.scores.overall },
];

function AnimatedNumber({ value, duration = 1.6, decimals = 0, prefix = "", suffix = "" }) {
  const ref = useRef(null);
  const inView = useInView(ref, { once: true, margin: "-15%" });
  const motionValue = useMotionValue(0);
  const [display, setDisplay] = useState(0);

  useEffect(() => {
    if (!inView) return;
    const controls = animate(motionValue, value, {
      duration,
      ease: [0.16, 1, 0.3, 1],
      onUpdate: (v) => setDisplay(v),
    });
    return controls.stop;
  }, [inView, value, motionValue, duration]);

  const formatted = decimals > 0 ? display.toFixed(decimals) : Math.round(display).toString();
  return <span ref={ref}>{prefix}{formatted}{suffix}</span>;
}

function ScoreBar({ label, value, locked = false, benchmark = 65 }) {
  const ref = useRef(null);
  const inView = useInView(ref, { once: true, margin: "-20%" });
  return (
    <div ref={ref} className="group">
      <div className="flex items-center justify-between mb-1.5">
        <span className="text-[11px] uppercase tracking-[0.18em] font-bold text-ink/85 flex items-center gap-1.5">
          {label}
          {locked && (
            <Lock aria-hidden className="w-2.5 h-2.5 text-forest/60 shrink-0" strokeWidth={2.2} />
          )}
        </span>
        {locked ? (
          <span className="font-barlow font-black text-ink/35 text-base flex items-center gap-1 select-none" aria-hidden>
            <span className="score-blur">{value}</span>
            <span className="text-ink/30 text-xs">/10</span>
          </span>
        ) : (
          <span className="font-barlow font-black text-volt text-base">
            <AnimatedNumber value={value} /><span className="text-ink/40 text-xs">/10</span>
          </span>
        )}
      </div>
      <div className={`h-1.5 overflow-hidden relative rounded-full ${locked ? "bg-cream-soft/50 locked-bar" : "bg-cream-soft/40"}`}>
        {!locked && (
          <div
            className="absolute top-0 left-0 h-full bg-gradient-to-r from-forest via-forest-pop to-volt"
            style={{
              width: inView ? `${value * 10}%` : "0%",
              transition: "width 1.6s cubic-bezier(0.16, 1, 0.3, 1)",
              boxShadow: "0 0 8px rgba(204, 255, 0, 0.5)",
            }}
          />
        )}
        {/* peer benchmark line */}
        <div
          className="absolute top-0 h-full"
          style={{
            left: `${benchmark}%`,
            width: "1px",
            borderLeft: "1px dashed rgba(31,79,47,0.35)",
            height: "100%",
          }}
        />
      </div>
    </div>
  );
}

export default function Landing() {
  const [price, setPrice] = useState(1);
  const [social, setSocial] = useState({
    twitter_url:   "https://twitter.com/scoutmeplay",
    facebook_url:  "https://www.facebook.com/scoutmeplay",
    linkedin_url:  "https://www.linkedin.com/company/scoutmeplay",
    instagram_url: "https://www.instagram.com/scoutmeplay",
  });
  // Position switcher state (D) — current sample-card player
  const [activePosition, setActivePosition] = useState("CAM");
  const current = SAMPLE_VARIANTS[activePosition] || SAMPLE_VARIANTS.CAM;
  // Dynamically re-derive radar data for the active player
  const dynamicRadar = [
    { axis: "Technical", v: current.scores.technical },
    { axis: "Tactical",  v: current.scores.tactical },
    { axis: "Physical",  v: current.scores.physical },
    { axis: "Mentality", v: current.scores.mentality },
    { axis: "Overall",   v: current.scores.overall },
  ];

  const { user } = useAuth();
  const { scrollYProgress } = useScroll();

  useEffect(() => {
    api.get("/settings/price").then(({ data }) => {
      setPrice(data.price);
      if (data.social) setSocial(data.social);
    }).catch(() => {});
  }, []);

  const startHref = user ? "/upload" : "/signup";
  const startLabel = "Upload your video";

  return (
    <div className="min-h-screen bg-deepnavy text-ink relative overflow-hidden">
      <SEO
        title="Where talent gets noticed — Football scouting reports"
        description="Upload your football video and receive a premium scouting report powered by advanced football intelligence, professional player benchmarks, and real scouts. Built for ambitious U7–U21 players."
        keywords="football scouting, youth football, player report, U14 scouting, U16 scouting, football academy, talent scout, player analysis, football trial"
        url="/"
        type="website"
        jsonLd={organizationJsonLd(typeof window !== "undefined" ? window.location.origin : "")}
      />
      {/* Scroll progress bar */}
      <motion.div className="scroll-progress-bar" style={{ scaleX: scrollYProgress }} />
      <Navigation transparent />

      {/* ============ HERO ============ */}
      <section data-testid="hero-section" className="relative min-h-screen flex items-center pt-24 pb-12">
        <div className="absolute inset-0 z-0">
          <img
            src="https://images.unsplash.com/photo-1706675780107-7c43cc487928?crop=entropy&cs=srgb&fm=jpg&ixid=M3w4NTYxODh8MHwxfHNlYXJjaHwyfHxzb2NjZXIlMjBwbGF5ZXIlMjBzdGFkaXVtJTIwbGlnaHRzJTIwbmlnaHR8ZW58MHx8fHwxNzgwNDE1ODUwfDA&ixlib=rb-4.1.0&q=85"
            alt="Stadium under lights"
            className="w-full h-full object-cover opacity-45"
          />
          <div className="absolute inset-0 bg-gradient-to-br from-deepnavy/85 via-deepnavy/60 to-deepnavy" />
          <div className="absolute inset-0 scoreline-grid opacity-30" />
          {/* Atmospheric sweep */}
          <div className="absolute inset-0 overflow-hidden pointer-events-none">
            <div
              className="absolute -inset-x-1/4 top-0 h-full opacity-30 animate-sweep-slow"
              style={{ background: "linear-gradient(90deg, transparent 0%, rgba(204,255,0,0.06) 50%, transparent 100%)" }}
            />
          </div>
          {/* Volt halos */}
          <div className="volt-halo" style={{ width: 480, height: 480, top: "20%", right: "-10%" }} />
          <div className="volt-halo" style={{ width: 320, height: 320, bottom: "-10%", left: "30%", opacity: 0.5 }} />
        </div>

        {/* Letterbox top + bottom */}
        <div className="hero-letterbox-top" />
        <div className="hero-letterbox-bottom" />

        <div className="relative z-10 w-full max-w-7xl mx-auto px-6 md:px-10">
          <div className="grid lg:grid-cols-12 gap-10 lg:gap-16 items-start">
            <div className="lg:col-span-6">
              <motion.div initial="hidden" animate="visible" variants={fadeUp} custom={0}>
                <div className="inline-flex items-center gap-2.5 border border-volt/30 bg-volt/10 backdrop-blur-sm px-4 py-2 relative overflow-hidden">
                  <span aria-hidden className="relative flex items-center justify-center w-2 h-2 shrink-0">
                    <span className="absolute inset-0 rounded-full bg-volt animate-ping opacity-75" />
                    <span className="relative rounded-full w-1.5 h-1.5 bg-volt" />
                  </span>
                  <Target className="w-3.5 h-3.5 text-volt shrink-0" />
                  <span className="text-volt text-[10px] sm:text-xs uppercase tracking-[0.22em] sm:tracking-[0.25em] font-bold whitespace-nowrap">
                    ScoutMePlay · Football Scouting Service
                  </span>
                </div>
              </motion.div>

              <motion.h1
                initial="hidden" animate="visible" variants={fadeUp} custom={1}
                data-testid="hero-title"
                className="mt-6 font-barlow font-black uppercase text-5xl sm:text-6xl md:text-7xl leading-[0.92] tracking-tighter"
              >
                Where <span className="font-serif-italic normal-case font-normal lowercase tracking-normal">talent</span>
                <span className="block text-gradient-volt mt-1">gets noticed.</span>
              </motion.h1>

              <motion.p
                initial="hidden" animate="visible" variants={fadeUp} custom={2}
                data-testid="hero-description"
                className="mt-7 max-w-xl text-base md:text-lg text-ink/80 leading-relaxed"
              >
                You train every day. You give everything on the pitch. But does anyone actually <span className="text-ink font-semibold italic">see you</span>? Upload your video. Get the <span className="text-ink font-semibold">scout view</span>. See where you stand and what it&apos;ll take to reach the next level.
                <br />
                <span className="block mt-3 text-sm md:text-base text-ink/65">
                  For ambitious players, <span className="text-volt font-bold">U7 to U21</span>.
                </span>
              </motion.p>

              <motion.div
                initial="hidden" animate="visible" variants={fadeUp} custom={3}
                className="mt-8 flex flex-col sm:flex-row gap-3 sm:gap-4 max-w-xl"
              >
                <Link
                  to={startHref}
                  data-testid="hero-cta-upload"
                  className="group flex-1 bg-volt hover:bg-forest-pop text-white font-barlow font-black uppercase tracking-widest text-base px-6 py-4 flex items-center justify-center gap-3 transition-colors animate-pulse-glow"
                >
                  <Upload className="w-5 h-5" />
                  {startLabel}
                  <ArrowRight className="w-5 h-5 group-hover:translate-x-1 transition-transform" />
                </Link>
                {!user && (
                  <Link
                    to="/login"
                    data-testid="hero-cta-login"
                    className="flex-1 border border-gray-border hover:border-volt hover:text-volt text-ink font-barlow font-black uppercase tracking-widest text-base px-6 py-4 flex items-center justify-center gap-2 transition-colors"
                  >
                    Sign in
                  </Link>
                )}
              </motion.div>

              <motion.div
                initial="hidden" animate="visible" variants={fadeUp} custom={4}
                className="mt-5 flex items-center"
              >
                <PaymentBadges variant="compact" />
              </motion.div>

              <motion.div
                initial="hidden" animate="visible" variants={fadeUp} custom={5}
                data-testid="hero-trust-bar"
                className="mt-7 max-w-xl"
              >
                <div className="flex items-center gap-3 mb-2">
                  <span aria-hidden className="h-px w-6 bg-volt/50" />
                  <span className="text-[9px] uppercase tracking-[0.32em] font-bold text-volt/80">Verified</span>
                  <span aria-hidden className="flex-1 h-px bg-gradient-to-r from-volt/30 to-transparent" />
                </div>
                <div className="grid grid-cols-2 gap-px bg-volt/20 border border-volt/25">
                  {[
                    { Icon: Trophy,      label: "Pro player benchmarks" },
                    { Icon: Brain,       label: "Football intelligence" },
                    { Icon: Users,       label: "Real scouts & agents" },
                    { Icon: FileText,    label: "Premium PDF report" },
                    { Icon: ShieldCheck, label: "Secure Stripe payment" },
                    { Icon: Star,        label: "One-time · no subscription" },
                  ].map(({ Icon, label }, i) => (
                    <motion.span
                      key={i}
                      initial={{ opacity: 0, x: -8 }}
                      animate={{ opacity: 1, x: 0 }}
                      transition={{ delay: 0.6 + i * 0.05, duration: 0.4 }}
                      whileHover={{ x: 2 }}
                      className="group relative flex items-center gap-2.5 bg-deepnavy px-3 py-2.5 min-w-0 cursor-default transition-colors hover:bg-deepnavy/70"
                    >
                      <span aria-hidden className="absolute left-0 top-0 bottom-0 w-[2px] bg-volt opacity-0 group-hover:opacity-100 transition-opacity" />
                      <span aria-hidden className="w-1 h-1 rounded-full bg-volt shrink-0" />
                      <Icon className="w-3.5 h-3.5 text-volt shrink-0" strokeWidth={2} />
                      <span className="truncate text-[10px] sm:text-[11px] uppercase tracking-[0.16em] font-bold text-ink/75">{label}</span>
                    </motion.span>
                  ))}
                </div>
              </motion.div>
            </div>

            {/* ===== RIGHT: Icon-bulleted feature stack with mini visualizations ===== */}
            <motion.div
              initial={{ opacity: 0, x: 24 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: 0.3, duration: 0.6, ease: "easeOut" }}
              className="lg:col-span-6 lg:pt-4 relative z-10"
              data-testid="hero-feature-bullets"
            >
              <div className="relative pl-10 sm:pl-12 space-y-10 md:space-y-12">
                {/* Vertical guide line (animated draw) */}
                <motion.div
                  aria-hidden
                  initial={{ scaleY: 0 }}
                  animate={{ scaleY: 1 }}
                  transition={{ delay: 0.5, duration: 1.0, ease: "easeOut" }}
                  className="absolute left-0 top-2 bottom-2 w-px bg-gradient-to-b from-volt/10 via-volt/50 to-volt/10 origin-top"
                />

                {[
                  {
                    Icon: Trophy,
                    n: "01",
                    body: (
                      <>
                        <span className="text-volt font-semibold">Pro player benchmarked</span> — your performance compared to professional profiles and position-specific standards used at the highest level of the game.
                      </>
                    ),
                    viz: (
                      <svg viewBox="0 0 110 28" className="w-32 md:w-36 h-7 md:h-8 text-volt" aria-hidden>
                        <text x="0" y="7" fontSize="5" fill="currentColor" opacity="0.6" fontWeight="700" letterSpacing="0.5">YOU</text>
                        <rect x="22" y="2" width="80" height="5" fill="currentColor" opacity="0.15" />
                        <motion.rect
                          x="22" y="2" height="5" fill="currentColor"
                          initial={{ width: 0 }}
                          whileInView={{ width: 56 }}
                          viewport={{ once: true }}
                          transition={{ duration: 1.0, delay: 0.7, ease: "easeOut" }}
                        />
                        <text x="0" y="24" fontSize="5" fill="currentColor" opacity="0.6" fontWeight="700" letterSpacing="0.5">PRO</text>
                        <rect x="22" y="19" width="80" height="5" fill="currentColor" opacity="0.15" />
                        <motion.rect
                          x="22" y="19" height="5" fill="currentColor"
                          initial={{ width: 0 }}
                          whileInView={{ width: 80 }}
                          viewport={{ once: true }}
                          transition={{ duration: 1.0, delay: 0.95, ease: "easeOut" }}
                        />
                      </svg>
                    ),
                  },
                  {
                    Icon: ClipboardList,
                    n: "02",
                    body: (
                      <>
                        <span className="text-volt font-semibold">Detailed football analysis</span> — technical, tactical, physical and mental scores with strengths, weaknesses, evidence and a personal development plan.
                      </>
                    ),
                    viz: (
                      <svg viewBox="0 0 110 28" className="w-32 md:w-36 h-7 md:h-8 text-volt" aria-hidden>
                        {[
                          { x: 6, h: 22, label: "TEC" },
                          { x: 30, h: 17, label: "TAC" },
                          { x: 54, h: 19, label: "PHY" },
                          { x: 78, h: 24, label: "MEN" },
                        ].map((b, i) => (
                          <g key={i}>
                            <rect x={b.x} y="2" width="16" height="20" fill="currentColor" opacity="0.1" />
                            <motion.rect
                              x={b.x} width="16" fill="currentColor"
                              initial={{ height: 0, y: 22 }}
                              whileInView={{ height: b.h, y: 22 - b.h }}
                              viewport={{ once: true }}
                              transition={{ delay: 0.7 + i * 0.12, duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
                            />
                            <text x={b.x + 8} y="27" fontSize="3.2" fill="currentColor" opacity="0.55" fontWeight="700" textAnchor="middle" letterSpacing="0.3">{b.label}</text>
                          </g>
                        ))}
                      </svg>
                    ),
                  },
                  {
                    Icon: Users,
                    n: "03",
                    body: (
                      <>
                        <span className="text-volt font-semibold">Real scouts &amp; agents</span> connected to clubs worldwide — guidance on trials, club changes, contracts and finding the right academy for your next step.
                      </>
                    ),
                    viz: (
                      <svg viewBox="0 0 110 28" className="w-32 md:w-36 h-7 md:h-8 text-volt" aria-hidden>
                        {/* central player node */}
                        <circle cx="18" cy="14" r="3.4" fill="currentColor" />
                        <motion.circle
                          cx="18" cy="14" r="3.4" fill="none" stroke="currentColor" strokeWidth="0.5"
                          animate={{ r: [3.4, 7], opacity: [0.7, 0] }}
                          transition={{ duration: 1.8, repeat: Infinity, ease: "easeOut" }}
                        />
                        {/* scout/agent nodes */}
                        {[
                          { x: 46, y: 4,  d: 0.5 },
                          { x: 64, y: 12, d: 0.7 },
                          { x: 86, y: 8,  d: 0.9 },
                          { x: 102,y: 14, d: 1.1 },
                          { x: 86, y: 22, d: 1.3 },
                          { x: 56, y: 24, d: 1.5 },
                        ].map((p, i) => (
                          <g key={i}>
                            <motion.line
                              x1="18" y1="14" x2={p.x} y2={p.y}
                              stroke="currentColor" strokeWidth="0.45" opacity="0.45"
                              initial={{ pathLength: 0 }}
                              whileInView={{ pathLength: 1 }}
                              viewport={{ once: true }}
                              transition={{ delay: p.d, duration: 0.4 }}
                            />
                            <motion.circle
                              cx={p.x} cy={p.y} r="2"
                              fill="currentColor" opacity="0.85"
                              initial={{ opacity: 0, scale: 0 }}
                              whileInView={{ opacity: 0.85, scale: 1 }}
                              viewport={{ once: true }}
                              transition={{ delay: p.d + 0.3, type: "spring", stiffness: 220 }}
                            />
                          </g>
                        ))}
                      </svg>
                    ),
                  },
                ].map(({ Icon, n, body, viz }, i) => (
                  <motion.div
                    key={i}
                    initial={{ opacity: 0, x: 18 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: 0.45 + i * 0.18, duration: 0.55, ease: [0.16, 1, 0.3, 1] }}
                    className="relative flex items-start gap-5"
                  >
                    {/* Icon disk with pulse halo + step number */}
                    <div className="absolute -left-10 sm:-left-12 top-0 w-14 h-14 sm:w-16 sm:h-16 -translate-x-1/2 z-10">
                      <motion.div
                        animate={{ y: [0, -2, 0] }}
                        transition={{ duration: 3, delay: i * 0.5, repeat: Infinity, ease: "easeInOut" }}
                        className="relative w-full h-full flex items-center justify-center bg-deepnavy border border-volt/50 shadow-[0_8px_24px_-8px_rgba(204,255,0,0.35)]"
                      >
                        <Icon className="w-6 h-6 sm:w-7 sm:h-7 text-volt" strokeWidth={1.5} />
                        <motion.span
                          aria-hidden
                          className="absolute inset-0 border border-volt pointer-events-none"
                          animate={{ scale: [1, 1.35], opacity: [0.45, 0] }}
                          transition={{ duration: 2.4, delay: i * 0.4, repeat: Infinity, ease: "easeOut" }}
                        />
                      </motion.div>
                      <span className="absolute -top-1.5 -right-1.5 bg-volt text-deepnavy font-barlow font-black text-[10px] tracking-wider px-1.5 py-0.5 leading-none border-2 border-deepnavy">
                        {n}
                      </span>
                    </div>

                    <div className="flex-1 min-w-0 pt-2.5 sm:pt-3.5">
                      <p className="text-sm md:text-base text-ink/80 leading-relaxed">
                        {body}
                      </p>
                      <div className="mt-3 opacity-90">{viz}</div>
                    </div>
                  </motion.div>
                ))}
              </div>
            </motion.div>
          </div>

          {/* ===== Bottom: Boot tagline + horizontal-lined punchline ===== */}
          <motion.div
            initial={{ opacity: 0, y: 14 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, amount: 0.4 }}
            transition={{ duration: 0.6, ease: "easeOut" }}
            className="mt-16 md:mt-20"
          >
            <div className="flex items-center justify-center gap-3 md:gap-4">
              {/* Premium Eye icon — matches "eyes of professionals" */}
              <div className="relative flex items-center justify-center w-11 h-11 md:w-14 md:h-14 shrink-0">
                <span aria-hidden className="absolute inset-0 bg-volt/20 blur-xl rounded-full" />
                <span aria-hidden className="absolute inset-1.5 border border-volt/40 rounded-full" />
                <Eye className="relative w-6 h-6 md:w-7 md:h-7 text-volt" strokeWidth={1.6} fill="rgba(204,255,0,0.08)" />
              </div>
              <p className="font-serif-italic italic text-xl md:text-2xl text-ink leading-snug text-center">
                See your game through the eyes of{" "}
                <span className="text-volt">professionals.</span>
              </p>
            </div>

            <div className="mt-7 md:mt-9 flex items-center gap-4 md:gap-6 max-w-3xl mx-auto">
              <div className="flex-1 h-px bg-gradient-to-r from-transparent via-volt/40 to-volt/40" />
              <p className="font-barlow font-black uppercase tracking-[0.22em] text-xs md:text-sm whitespace-nowrap">
                <span className="text-volt">Know your potential.</span>{" "}
                <span className="text-ink">Unlock your future.</span>
              </p>
              <div className="flex-1 h-px bg-gradient-to-l from-transparent via-volt/40 to-volt/40" />
            </div>
          </motion.div>
        </div>
      </section>

      {/* ============ HOW IT WORKS — animated walkthrough (silent autoplay) ============ */}
      <HowItWorksWalkthrough startHref={startHref} price={price} />

      {/* ============ HOW IT WORKS · 3 STEPS section removed (consolidated CTAs to reduce duplicates) ============ */}

      {/* ============ WHAT YOU RECEIVE — rich feature cards ============ */}
      <section id="what-you-get" data-testid="what-you-get" className="section-accent-top relative py-16 md:py-20 border-t border-gray-border overflow-hidden">
        <div className="absolute inset-0 z-0 opacity-15">
          <img
            src="https://images.pexels.com/photos/16826135/pexels-photo-16826135.jpeg"
            alt="Pitch"
            className="w-full h-full object-cover"
          />
          <div className="absolute inset-0 bg-cream-card" />
        </div>
        {/* Subtle volt glow accents */}
        <div aria-hidden className="absolute -top-40 right-0 w-[420px] h-[420px] bg-volt/10 rounded-full blur-3xl pointer-events-none" />

        <div className="relative z-10 max-w-7xl mx-auto px-6 md:px-10">
          {/* Header */}
          <div className="mb-10 md:mb-14">
            <div className="grid lg:grid-cols-12 gap-8 lg:gap-10 items-center">
              <div className="lg:col-span-8">
                <div className="flex items-center gap-4 mb-5">
                  <span aria-hidden className="relative flex items-center justify-center w-2 h-2 shrink-0">
                    <span className="absolute inset-0 rounded-full bg-volt animate-ping opacity-75" />
                    <span className="relative rounded-full w-1.5 h-1.5 bg-volt" />
                  </span>
                  <span className="text-volt text-xs uppercase tracking-[0.3em] font-bold whitespace-nowrap">Inside your report</span>
                  <span aria-hidden className="flex-1 h-px bg-gradient-to-r from-volt/60 via-volt/20 to-transparent max-w-[200px]" />
                </div>
                <h2
                  data-testid="report-section-title"
                  className="font-barlow font-black uppercase text-4xl sm:text-5xl md:text-6xl tracking-tighter leading-[0.92]"
                >
                  What does a real scout see{" "}
                  <span className="block">
                    that{" "}
                    <span className="font-serif-italic normal-case font-normal lowercase tracking-normal text-volt">you</span>{" "}
                    don't?
                  </span>
                </h2>
                <p className="mt-5 text-ink/75 text-base md:text-lg max-w-xl leading-relaxed">
                  Professional analysis. Honest insights. Built to help you grow.
                </p>
              </div>

              {/* Decorative jersey badge — visually echoes the reference */}
              <div className="hidden lg:flex lg:col-span-4 justify-end">
                <div className="relative w-full max-w-[180px] aspect-[3/4]">
                  <div className="absolute inset-0 border border-volt/30 bg-cream-card/90 backdrop-blur-sm">
                    {/* corner brackets */}
                    <span className="absolute top-0 left-0 w-5 h-5 border-t-2 border-l-2 border-volt" />
                    <span className="absolute top-0 right-0 w-5 h-5 border-t-2 border-r-2 border-volt" />
                    <span className="absolute bottom-0 left-0 w-5 h-5 border-b-2 border-l-2 border-volt" />
                    <span className="absolute bottom-0 right-0 w-5 h-5 border-b-2 border-r-2 border-volt" />

                    <div className="absolute inset-0 flex flex-col items-center justify-center text-center px-4">
                      <span className="text-[9px] uppercase tracking-[0.25em] font-bold text-volt/80 mb-1.5">Your name</span>
                      <span
                        className="font-barlow font-black text-volt leading-none"
                        style={{ fontSize: "5rem", textShadow: "0 6px 30px rgba(204,255,0,0.35)" }}
                      >
                        10
                      </span>
                      <span className="mt-2.5 text-[9px] uppercase tracking-[0.2em] font-bold text-ink/55">
                        Built for the next level
                      </span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* ===== BENTO grid — asymmetric, dynamic, alive ===== */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-12 gap-4 md:gap-5 auto-rows-min lg:auto-rows-[240px]">
            {(() => {
              const bento = [
                { cls: "sm:col-span-2 lg:col-span-6 lg:row-span-2", variant: "hero" },        // 0 Player Report
                { cls: "lg:col-span-3", variant: "tint" },                                     // 1 Technical
                { cls: "lg:col-span-3", variant: "default" },                                  // 2 Tactical
                { cls: "lg:col-span-3", variant: "default" },                                  // 3 Physical
                { cls: "lg:col-span-3", variant: "tint" },                                     // 4 Mentality
                { cls: "lg:col-span-4", variant: "default" },                                  // 5 Scout View
                { cls: "sm:col-span-2 lg:col-span-8", variant: "wide" },                       // 6 Training Plan
                { cls: "lg:col-span-4", variant: "tint" },                                     // 7 Potential
                { cls: "lg:col-span-4", variant: "default" },                                  // 8 Comparison
                { cls: "sm:col-span-2 lg:col-span-8", variant: "wide" },                       // 9 PDF (widened to remove empty cell next to closer)
                { cls: "sm:col-span-2 lg:col-span-12", variant: "default" },                   // 10 Private (full-width finale)
              ];

              const renderCard = (card, i) => {
                const b = bento[i];
                const number = String(i + 1).padStart(2, "0");

                /* ===== HERO variant — Player Report, dark forest, oversized ===== */
                if (b.variant === "hero") {
                  return (
                    <BentoTiltCard
                      key={i}
                      initial={{ opacity: 0, y: 24 }}
                      whileInView={{ opacity: 1, y: 0 }}
                      viewport={{ once: true, amount: 0.2 }}
                      transition={{ duration: 0.6, delay: i * 0.06, ease: "easeOut" }}
                      data-testid={`feature-card-${i}`}
                      className={`${b.cls} relative overflow-hidden bg-forest text-cream-card border border-volt/30 p-7 md:p-10 flex flex-col group hover:border-volt transition-colors duration-300`}
                      style={{ boxShadow: "0 0 80px rgba(204,255,0,0.08)" }}
                    >
                      {/* radial volt glow */}
                      <div aria-hidden className="absolute -top-24 -right-24 w-72 h-72 bg-volt/15 rounded-full blur-3xl pointer-events-none" />
                      <div aria-hidden className="absolute -bottom-32 -left-32 w-72 h-72 bg-volt/10 rounded-full blur-3xl pointer-events-none" />

                      <span className="absolute top-6 right-7 font-barlow font-black text-xs text-volt/40 tracking-widest">{number}</span>

                      <div className="relative flex items-center gap-3 mb-6">
                        <card.icon className="w-10 h-10 md:w-12 md:h-12 group-hover:scale-110 transition-transform duration-300" strokeWidth={1.5} style={{ color: "#ccff00" }} />
                        <span className="text-[10px] uppercase tracking-[0.3em] font-bold text-cream-card/70">Hero metric</span>
                      </div>

                      <h3 className="relative font-barlow font-black uppercase text-3xl md:text-5xl text-cream-card mb-4 leading-[0.95] tracking-tight">
                        {card.title}
                      </h3>

                      <p className="relative text-sm md:text-base text-cream-card/80 leading-relaxed max-w-md">
                        {card.text}
                      </p>

                      {/* ===== ANIMATED 5-AXIS RADAR — live product preview ===== */}
                      <div className="relative mt-auto pt-8 flex items-end justify-between gap-4 border-t border-cream-card/15">
                        <div className="flex flex-col">
                          <span className="text-[10px] uppercase tracking-[0.25em] font-bold text-cream-card/70 mb-3">5-Axis Scout Profile</span>
                          <div className="relative w-[170px] h-[170px] md:w-[180px] md:h-[180px]">
                            <svg viewBox="0 0 200 200" className="w-full h-full overflow-visible" aria-hidden>
                              {/* Background grid pentagons */}
                              {[0.25, 0.5, 0.75, 1].map((scale, gi) => {
                                const pts = [0, 1, 2, 3, 4].map((j) => {
                                  const a = ((-90 + j * 72) * Math.PI) / 180;
                                  const r = 70 * scale;
                                  return `${100 + r * Math.cos(a)},${100 + r * Math.sin(a)}`;
                                }).join(" ");
                                return (
                                  <polygon
                                    key={gi}
                                    points={pts}
                                    fill="none"
                                    stroke="rgba(255,253,243,0.12)"
                                    strokeWidth="0.6"
                                  />
                                );
                              })}
                              {/* 5 radial spokes */}
                              {[0, 1, 2, 3, 4].map((j) => {
                                const a = ((-90 + j * 72) * Math.PI) / 180;
                                return (
                                  <line
                                    key={`s${j}`}
                                    x1="100"
                                    y1="100"
                                    x2={100 + 70 * Math.cos(a)}
                                    y2={100 + 70 * Math.sin(a)}
                                    stroke="rgba(255,253,243,0.10)"
                                    strokeWidth="0.6"
                                  />
                                );
                              })}
                              {/* Animated data polygon — draws on scroll */}
                              <motion.polygon
                                points={[8, 9, 7, 9, 9].map((v, j) => {
                                  const a = ((-90 + j * 72) * Math.PI) / 180;
                                  const r = (v / 10) * 70;
                                  return `${100 + r * Math.cos(a)},${100 + r * Math.sin(a)}`;
                                }).join(" ")}
                                fill="#ccff00"
                                fillOpacity="0.20"
                                stroke="#ccff00"
                                strokeWidth="1.6"
                                strokeLinejoin="round"
                                initial={{ scale: 0, opacity: 0 }}
                                whileInView={{ scale: 1, opacity: 1 }}
                                viewport={{ once: true, amount: 0.3 }}
                                transition={{ duration: 1.1, ease: [0.16, 1, 0.3, 1] }}
                                style={{ transformOrigin: "100px 100px", filter: "drop-shadow(0 0 8px rgba(204,255,0,0.5))" }}
                              />
                              {/* Animated vertex dots */}
                              {[8, 9, 7, 9, 9].map((v, j) => {
                                const a = ((-90 + j * 72) * Math.PI) / 180;
                                const r = (v / 10) * 70;
                                const cx = 100 + r * Math.cos(a);
                                const cy = 100 + r * Math.sin(a);
                                return (
                                  <motion.circle
                                    key={`d${j}`}
                                    cx={cx}
                                    cy={cy}
                                    r="2.8"
                                    fill="#ccff00"
                                    initial={{ scale: 0, opacity: 0 }}
                                    whileInView={{ scale: 1, opacity: 1 }}
                                    viewport={{ once: true, amount: 0.3 }}
                                    transition={{ duration: 0.4, delay: 0.85 + j * 0.07, ease: "easeOut" }}
                                    style={{ transformOrigin: `${cx}px ${cy}px` }}
                                  />
                                );
                              })}
                              {/* Axis labels with score values */}
                              {[
                                { label: "TECH", value: 8 },
                                { label: "TACT", value: 9 },
                                { label: "PHYS", value: 7 },
                                { label: "MENT", value: 9 },
                                { label: "DEC", value: 9 },
                              ].map((axis, j) => {
                                const a = ((-90 + j * 72) * Math.PI) / 180;
                                const lr = 88;
                                const lx = 100 + lr * Math.cos(a);
                                const ly = 100 + lr * Math.sin(a);
                                return (
                                  <g key={`l${j}`}>
                                    <motion.text
                                      x={lx}
                                      y={ly - 2}
                                      fontSize="8"
                                      fontWeight="800"
                                      fill="rgba(255,253,243,0.72)"
                                      textAnchor="middle"
                                      dominantBaseline="middle"
                                      letterSpacing="0.4"
                                      initial={{ opacity: 0 }}
                                      whileInView={{ opacity: 1 }}
                                      viewport={{ once: true, amount: 0.3 }}
                                      transition={{ duration: 0.5, delay: 1.0 + j * 0.06 }}
                                    >
                                      {axis.label}
                                    </motion.text>
                                    <motion.text
                                      x={lx}
                                      y={ly + 7}
                                      fontSize="7.5"
                                      fontWeight="900"
                                      fill="#ccff00"
                                      textAnchor="middle"
                                      dominantBaseline="middle"
                                      initial={{ opacity: 0 }}
                                      whileInView={{ opacity: 1 }}
                                      viewport={{ once: true, amount: 0.3 }}
                                      transition={{ duration: 0.5, delay: 1.15 + j * 0.06 }}
                                    >
                                      {axis.value}
                                    </motion.text>
                                  </g>
                                );
                              })}
                              {/* Center pulse dot */}
                              <motion.circle
                                cx="100"
                                cy="100"
                                r="2"
                                fill="#ccff00"
                                initial={{ opacity: 0 }}
                                whileInView={{ opacity: 1 }}
                                viewport={{ once: true, amount: 0.3 }}
                                transition={{ duration: 0.4, delay: 0.4 }}
                              />
                            </svg>
                          </div>
                        </div>

                        <div className="flex flex-col items-end gap-3">
                          <div className="text-right">
                            <span className="block text-[10px] uppercase tracking-[0.25em] font-bold text-cream-card/70 mb-1">Overall</span>
                            <span className="font-barlow font-black text-4xl md:text-5xl leading-none" style={{ color: "#ccff00", textShadow: "0 4px 30px rgba(204,255,0,0.45)" }}>
                              8.2<span className="text-cream-card/55 text-xl md:text-2xl">/10</span>
                            </span>
                          </div>
                          <span className="hidden md:inline-flex items-center gap-2 text-[10px] uppercase tracking-[0.22em] font-bold text-cream-card/75 border border-cream-card/25 rounded-full px-3 py-1.5">
                            Live demo
                            <span className="w-1.5 h-1.5 rounded-full animate-pulse" style={{ background: "#ccff00" }} />
                          </span>
                        </div>
                      </div>
                    </BentoTiltCard>
                  );
                }

                /* ===== WIDE variant — Training Plan, horizontal layout ===== */
                if (b.variant === "wide") {
                  return (
                    <BentoTiltCard
                      key={i}
                      initial={{ opacity: 0, y: 18 }}
                      whileInView={{ opacity: 1, y: 0 }}
                      viewport={{ once: true, amount: 0.2 }}
                      transition={{ duration: 0.5, delay: i * 0.06, ease: "easeOut" }}
                      data-testid={`feature-card-${i}`}
                      className={`${b.cls} relative bg-surface/80 backdrop-blur-sm border border-gray-border hover:border-volt/50 p-6 md:p-8 flex flex-col md:flex-row md:items-stretch md:gap-8 group transition-colors duration-300`}
                    >
                      <span className="absolute top-5 right-6 font-barlow font-black text-xs text-ink/35 tracking-widest">{number}</span>

                      <div className="md:w-2/5 flex flex-col">
                        <card.icon className="w-9 h-9 md:w-10 md:h-10 text-volt mb-5 group-hover:scale-110 transition-transform duration-300" strokeWidth={1.5} />
                        <h3 className="font-barlow font-black uppercase text-2xl md:text-3xl text-ink mb-3 leading-tight tracking-tight">
                          {card.title}
                        </h3>
                        <p className="text-sm text-ink/70 leading-relaxed">{card.text}</p>
                      </div>

                      <div className="hidden md:block w-px bg-gradient-to-b from-transparent via-volt/30 to-transparent" />

                      <div className="md:w-3/5 mt-6 md:mt-0 flex flex-col justify-center gap-3">
                        {[
                          { day: "Week 1-2", focus: "First-touch under pressure" },
                          { day: "Week 3-4", focus: "Weak-foot finishing reps" },
                          { day: "Week 5-8", focus: "Sprint endurance · 90-min legs" },
                        ].map((row, k) => (
                          <div key={k} className="flex items-center gap-3 group/row">
                            <span className="w-5 h-5 border border-volt/50 flex items-center justify-center shrink-0 group-hover/row:bg-volt transition-colors">
                              <svg viewBox="0 0 12 12" className="w-3 h-3 text-volt group-hover/row:text-deepnavy" fill="none" stroke="currentColor" strokeWidth="2.5">
                                <polyline points="2,6 5,9 10,3" />
                              </svg>
                            </span>
                            <span className="text-[10px] uppercase tracking-[0.2em] font-bold text-volt w-20 shrink-0">{row.day}</span>
                            <span className="text-sm text-ink/80">{row.focus}</span>
                          </div>
                        ))}
                        <div className="mt-2 pt-3 border-t border-gray-border">
                          <CardViz viz={card.viz} />
                        </div>
                      </div>
                    </BentoTiltCard>
                  );
                }

                /* ===== TINT / DEFAULT — standard card with optional volt accent ===== */
                const isTint = b.variant === "tint";
                return (
                  <BentoTiltCard
                    key={i}
                    initial={{ opacity: 0, y: 18 }}
                    whileInView={{ opacity: 1, y: 0 }}
                    viewport={{ once: true, amount: 0.2 }}
                    transition={{ duration: 0.5, delay: (i % 4) * 0.06, ease: "easeOut" }}
                    data-testid={`feature-card-${i}`}
                    className={`${b.cls} relative overflow-hidden border border-gray-border hover:border-volt/50 p-6 md:p-7 flex flex-col group transition-colors duration-300 ${
                      isTint ? "bg-gradient-to-br from-surface/90 via-surface/70 to-volt/[0.06]" : "bg-surface/80 backdrop-blur-sm"
                    }`}
                  >
                    {isTint && (
                      <div aria-hidden className="absolute -top-12 -right-12 w-32 h-32 bg-volt/15 rounded-full blur-2xl pointer-events-none" />
                    )}
                    <span className="absolute top-5 right-6 font-barlow font-black text-xs text-ink/35 tracking-widest">{number}</span>

                    <card.icon className="relative w-8 h-8 md:w-9 md:h-9 text-volt mb-5 group-hover:scale-110 group-hover:rotate-[-4deg] transition-transform duration-300" strokeWidth={1.5} />

                    <h3 className="relative font-barlow font-black uppercase text-xl md:text-2xl text-ink mb-2 leading-tight tracking-tight">
                      {card.title}
                    </h3>

                    <p className="relative text-sm text-ink/70 leading-relaxed mb-5 flex-1">
                      {card.text}
                    </p>

                    <div className="relative mt-auto pt-4 border-t border-gray-border">
                      <CardViz viz={card.viz} />
                    </div>
                  </BentoTiltCard>
                );
              };

              return (
                <>
                  {/* Cards 0-8 (Player Report → Comparison) */}
                  {reportCards.slice(0, 9).map((card, i) => renderCard(card, i))}

                  {/* ===== Special highlight CLOSER card — Premium (spans 2 rows on desktop) ===== */}
                  <motion.div
                    initial={{ opacity: 0, y: 18 }}
                    whileInView={{ opacity: 1, y: 0 }}
                    viewport={{ once: true, amount: 0.2 }}
                    transition={{ duration: 0.6, delay: 0.18, ease: "easeOut" }}
                    data-testid="feature-card-highlight"
                    className="sm:col-span-2 lg:col-span-4 lg:row-span-2 relative overflow-hidden bg-gradient-to-br from-forest-pop via-forest to-forest border-2 p-7 md:p-8 flex flex-col group hover:-translate-y-1 transition-all duration-300"
                    style={{ borderColor: "#ccff00", boxShadow: "0 0 80px rgba(204,255,0,0.22)" }}
                  >
                    {/* pulsing volt glow */}
                    <div aria-hidden className="absolute -top-20 -right-20 w-64 h-64 bg-volt/25 rounded-full blur-3xl pointer-events-none animate-pulse" style={{ animationDuration: "4s" }} />
                    <div aria-hidden className="absolute -bottom-32 -left-20 w-72 h-72 bg-volt/15 rounded-full blur-3xl pointer-events-none" />

                    <span className="absolute top-5 right-6 font-barlow font-black text-xs text-cream-card/40 tracking-widest">12</span>

                    <Crown className="relative w-12 h-12 md:w-14 md:h-14 mb-6 group-hover:scale-110 transition-transform duration-300" strokeWidth={1.5} fill="#ccff00" fillOpacity="0.28" style={{ color: "#ccff00" }} />

                    <h3 className="relative font-barlow font-black uppercase text-2xl md:text-3xl text-cream-card mb-3 leading-[0.95] tracking-tight">
                      100% Personal.
                      <br />
                      <span style={{ color: "#ccff00" }}>100% Game Changing.</span>
                    </h3>

                    <p className="relative text-sm md:text-base text-cream-card/85 leading-relaxed mt-3">
                      This is more than a report.{" "}
                      <span className="font-serif-italic italic" style={{ color: "#ccff00" }}>It&apos;s your advantage.</span>
                    </p>

                    {/* Mini trust signals */}
                    <div className="relative mt-6 grid grid-cols-2 gap-2 text-[10px] uppercase tracking-[0.18em] font-bold text-cream-card/75">
                      <span className="flex items-center gap-1.5"><span className="w-1 h-1 rounded-full" style={{ background: "#ccff00" }} /> Pro benchmarks</span>
                      <span className="flex items-center gap-1.5"><span className="w-1 h-1 rounded-full" style={{ background: "#ccff00" }} /> Real scouts</span>
                      <span className="flex items-center gap-1.5"><span className="w-1 h-1 rounded-full" style={{ background: "#ccff00" }} /> Premium PDF</span>
                      <span className="flex items-center gap-1.5"><span className="w-1 h-1 rounded-full" style={{ background: "#ccff00" }} /> 5–10 min</span>
                    </div>

                    <div className="relative mt-auto pt-6 border-t border-cream-card/15">
                      <Link
                        to={startHref}
                        data-testid="report-section-cta"
                        className="inline-flex items-center gap-2 font-barlow font-black uppercase text-sm tracking-[0.22em] hover:text-cream-card transition-colors group/btn"
                        style={{ color: "#ccff00" }}
                      >
                        Unlock your report
                        <ArrowRight className="w-4 h-4 group-hover/btn:translate-x-1 transition-transform" />
                      </Link>
                    </div>
                  </motion.div>

                  {/* Cards 9-10 (PDF + Private) — rendered after closer to fill bottom row */}
                  {reportCards.slice(9, 11).map((card, idx) => renderCard(card, idx + 9))}
                </>
              );
            })()}
          </div>

          {/* ===== Bottom trust bar ===== */}
          <div
            data-testid="report-trust-bar"
            className="mt-10 md:mt-14 border border-gray-border bg-surface/60 backdrop-blur-sm divide-y md:divide-y-0 md:divide-x divide-gray-border/60 grid md:grid-cols-3"
          >
            {[
              { Icon: Clock, t: "5–10 Minutes", s: "To complete" },
              { Icon: Zap, t: "Instant access", s: "To your free preview" },
              { Icon: ShieldCheck, t: "Real scouts", s: "Real reports" },
            ].map(({ Icon, t, s }, i) => (
              <div key={i} className="flex items-center gap-3.5 px-6 py-5">
                <Icon className="w-5 h-5 text-volt shrink-0" strokeWidth={1.8} />
                <div className="flex flex-col leading-tight">
                  <span className="font-barlow font-black uppercase text-ink text-sm tracking-wider">{t}</span>
                  <span className="text-ink/65 text-[11px] uppercase tracking-[0.18em] font-bold mt-0.5">{s}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ============ SAMPLE REPORT — RICH, COMPELLING, WOW ============ */}
      <section
        data-testid="example-report"
        className="section-accent-top relative py-16 md:py-20 border-t border-gray-border overflow-hidden"
      >
        {/* Soft background */}
        <div className="absolute inset-0 z-0 pointer-events-none">
          <div className="absolute -top-32 -left-32 w-96 h-96 bg-volt/10 rounded-full blur-3xl" />
          <div className="absolute -bottom-32 -right-32 w-96 h-96 bg-volt/5 rounded-full blur-3xl" />
        </div>

        <div className="relative z-10 max-w-7xl mx-auto px-6 md:px-10">
          <div className="mb-10 md:mb-14 relative">
            <span aria-hidden className="section-num-bg">02</span>
            <div className="max-w-3xl relative">
              <div className="flex items-center gap-4 mb-5">
                <span aria-hidden className="relative flex items-center justify-center w-2 h-2 shrink-0">
                  <span className="absolute inset-0 rounded-full bg-volt animate-ping opacity-75" />
                  <span className="relative rounded-full w-1.5 h-1.5 bg-volt" />
                </span>
                <span className="text-volt text-xs uppercase tracking-[0.3em] font-bold whitespace-nowrap">A real example</span>
                <span aria-hidden className="flex-1 h-px bg-gradient-to-r from-volt/60 via-volt/20 to-transparent max-w-[200px]" />
              </div>
              <h2 className="font-barlow font-black uppercase text-4xl md:text-6xl tracking-tighter leading-[0.95]">
                This is what you get.
              </h2>
              <p className="mt-5 text-ink/75 max-w-2xl text-base md:text-lg leading-relaxed">
                Below is a real example. The first box is the free preview — like the one you'll see right after you
                upload. Everything else is what our scouts unlock for <span className="text-volt font-bold">${price} USD</span>.
              </p>
            </div>
          </div>

          {/* === SAMPLE REPORT HEADER — pro football card === */}
          <div className="grid lg:grid-cols-5 gap-px bg-cream-soft/40 border border-gray-border mb-px">
            {/* Player card — premium football style */}
            <div className="bg-surface lg:col-span-2 relative overflow-hidden">
              {/* Pitch background */}
              <div className="absolute inset-0 opacity-25 pointer-events-none">
                <img
                  src="https://images.pexels.com/photos/12616082/pexels-photo-12616082.jpeg"
                  alt="Pitch"
                  className="w-full h-full object-cover"
                />
                <div className="absolute inset-0 bg-gradient-to-tr from-deepnavy via-deepnavy/85 to-deepnavy/40" />
              </div>

              {/* Top stripe with badge + free tag + position switcher (D) */}
              <div className="relative flex items-center justify-between gap-3 px-5 py-3 border-b border-gray-border bg-cream-card/90">
                <span className="text-volt text-[10px] uppercase tracking-[0.25em] font-bold flex items-center gap-1.5 whitespace-nowrap">
                  <span className="w-1.5 h-1.5 bg-volt rounded-full animate-pulse" /> Free Preview
                </span>
                {/* Position tab switcher (4 positions) */}
                <div
                  data-testid="sample-position-switcher"
                  className="flex items-stretch gap-px bg-gray-border border border-gray-border shadow-[0_1px_0_rgba(0,0,0,0.04)]"
                >
                  {POSITIONS.map((p) => {
                    const isActive = activePosition === p.id;
                    return (
                      <button
                        key={p.id}
                        type="button"
                        onClick={() => setActivePosition(p.id)}
                        data-testid={`sample-position-${p.id.toLowerCase()}`}
                        aria-pressed={isActive}
                        className={`px-3 sm:px-3.5 py-1.5 text-[10px] uppercase tracking-[0.2em] font-black transition-all ${
                          isActive
                            ? "bg-forest text-white shadow-inner"
                            : "bg-cream-card text-ink/60 hover:text-ink hover:bg-cream-soft/60"
                        }`}
                      >
                        {p.label}
                      </button>
                    );
                  })}
                </div>
                <span className="text-ink/55 text-[10px] uppercase tracking-[0.2em] font-bold hidden sm:inline whitespace-nowrap">{current.player.videoType}</span>
              </div>

              <motion.div
                key={activePosition}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.35, ease: "easeOut" }}
                className="relative px-5 md:px-7 py-6 md:py-7"
              >
                {/* Big jersey number + name */}
                <div className="flex items-start gap-5">
                  <div className="flex-shrink-0">
                    <div className="text-[11px] uppercase tracking-[0.18em] font-bold text-volt/70 mb-1">No.</div>
                    <div className="font-barlow font-black text-volt leading-none" style={{ fontSize: "5.5rem", textShadow: "0 4px 24px rgba(204,255,0,0.3)" }}>
                      {current.player.number}
                    </div>
                  </div>
                  <div className="flex-1 min-w-0 pt-2">
                    <div className="text-[10px] uppercase tracking-[0.22em] font-bold text-ink/50 mb-1">Player</div>
                    <h3 className="font-barlow font-black uppercase text-3xl md:text-4xl tracking-tighter leading-[0.9] text-ink">
                      {current.player.name}
                    </h3>
                    <div className="mt-2 inline-flex items-center gap-2 bg-volt/10 border border-volt/30 px-2.5 py-1">
                      <span className="font-barlow font-black uppercase text-volt text-sm leading-none">{current.player.positionShort}</span>
                      <span className="text-ink/65 text-[11px]">·</span>
                      <span className="text-ink/80 text-xs">{current.player.position}</span>
                    </div>
                  </div>
                </div>

                {/* Meta row */}
                <div className="mt-6 grid grid-cols-3 gap-px bg-forest/15 border border-forest/20">
                  <div className="bg-cream-card/95 p-3.5">
                    <div className="text-[9px] uppercase tracking-[0.22em] text-ink/55 font-black">Age</div>
                    <div className="font-barlow font-black text-ink text-2xl leading-none mt-1.5">{current.player.age}</div>
                  </div>
                  <div className="bg-cream-card/95 p-3.5">
                    <div className="text-[9px] uppercase tracking-[0.22em] text-ink/55 font-black">Foot</div>
                    <div className="font-barlow font-black text-ink text-lg leading-none mt-2">{current.player.foot}</div>
                  </div>
                  <div className="bg-cream-card/95 p-3.5">
                    <div className="text-[9px] uppercase tracking-[0.22em] text-ink/55 font-black">Team</div>
                    <div className="font-barlow font-black text-ink text-sm leading-none mt-2 truncate">{current.player.club}</div>
                  </div>
                </div>

                {/* Style tag */}
                <div className="mt-4 flex items-center gap-2 text-xs text-ink/75">
                  <Star className="w-3.5 h-3.5 text-volt flex-shrink-0" fill="currentColor" />
                  <span className="font-bold">{current.player.type}</span>
                </div>

                {/* Score row — premium 4-pillar scoreboard */}
                <div className="mt-6 grid grid-cols-4 gap-px bg-volt/15 border border-volt/30 overflow-hidden">
                  {[
                    { k: "TECH", v: current.scores.technical, Icon: Footprints },
                    { k: "TACT", v: current.scores.tactical,  Icon: Target },
                    { k: "PHYS", v: current.scores.physical,  Icon: Activity },
                    { k: "MENT", v: current.scores.mentality, Icon: Lightbulb },
                  ].map((s, i) => {
                    // Heatmap intensity: score 9+ = strongest tint, < 6 = nearly empty
                    const intensity = Math.max(0.06, Math.min(0.32, (s.v - 5) * 0.06));
                    const pct = Math.max(5, Math.min(100, s.v * 10));
                    return (
                      <div key={`${activePosition}-${i}`} data-testid={`sample-score-${s.k.toLowerCase()}`} className="relative bg-cream-card py-4 px-2 text-center overflow-hidden">
                        {/* Pitch-zone heatmap behind */}
                        <div
                          aria-hidden
                          className="absolute inset-0 pointer-events-none"
                          style={{
                            background: `radial-gradient(ellipse at center bottom, rgba(31, 79, 47, ${intensity}) 0%, rgba(31, 79, 47, 0) 70%)`,
                          }}
                        />
                        <div className="relative flex items-center justify-center gap-1.5 text-[10px] uppercase tracking-[0.18em] text-ink/65 font-black">
                          <s.Icon className="w-3 h-3 text-forest" strokeWidth={2.2} />
                          {s.k}
                        </div>
                        <div className="relative font-barlow font-black text-4xl text-volt mt-1 leading-none" style={{ textShadow: "0 2px 14px rgba(204,255,0,0.25)" }}>
                          <AnimatedNumber value={s.v} duration={1.4} />
                          <span className="text-ink/40 text-base font-bold align-top ml-0.5">/10</span>
                        </div>
                        {/* Animated horizontal bar — thicker for premium feel */}
                        <div className="relative mt-2.5 mx-2 h-1.5 bg-cream-soft/70 overflow-hidden rounded-full">
                          <motion.div
                            key={`${activePosition}-${i}-bar`}
                            initial={{ width: 0 }}
                            whileInView={{ width: `${pct}%` }}
                            viewport={{ once: false, margin: "-30px" }}
                            transition={{ duration: 1.3, delay: 0.1 + i * 0.08, ease: [0.16, 1, 0.3, 1] }}
                            className="h-full bg-gradient-to-r from-forest via-forest-pop to-volt rounded-full"
                          />
                        </div>
                      </div>
                    );
                  })}
                </div>
              </motion.div>
            </div>

            {/* Brief summary card */}
            <div className="bg-surface p-6 md:p-8 lg:col-span-3">
              <div className="flex items-center justify-between mb-4">
                <span className="text-volt text-[11px] uppercase tracking-[0.25em] font-bold flex items-center gap-1.5">
                  <span className="w-1.5 h-1.5 bg-volt rounded-full" /> What our scouts saw
                </span>
                <span className="text-ink/50 text-[10px] uppercase tracking-[0.22em] font-bold">Free preview</span>
              </div>
              <p className="text-ink text-base md:text-[17px] leading-[1.65]">{current.summary}</p>

              <div className="mt-7 grid sm:grid-cols-2 gap-6 pt-6 border-t border-gray-border">
                <div>
                  <div className="text-xs uppercase tracking-[0.22em] font-black text-forest mb-3 flex items-center gap-2">
                    <CheckCircle2 className="w-3.5 h-3.5" />
                    What he does well
                  </div>
                  <ul className="space-y-2.5">
                    {current.strengths.map((s, i) => (
                      <li key={`${activePosition}-${i}`} className="flex items-start gap-2.5 text-sm text-ink leading-snug">
                        <CheckCircle2 className="w-4 h-4 text-volt mt-0.5 flex-shrink-0" />
                        <span>{s}</span>
                      </li>
                    ))}
                  </ul>
                </div>
                <div>
                  <div className="text-xs uppercase tracking-[0.22em] font-black text-amber-600 mb-3 flex items-center gap-2">
                    <Target className="w-3.5 h-3.5" />
                    What to work on
                  </div>
                  <p className="text-sm text-ink/85 leading-relaxed">{current.improvement}</p>
                </div>
              </div>
            </div>
          </div>

          {/* === PREMIUM SECTIONS — headers/labels CRISP, only the values are locked === */}
          <div className="relative">
            {/* The actual content (labels readable, scores teased) */}
            <div className="relative grid lg:grid-cols-3 gap-px bg-cream-soft/40 border border-gray-border">
              {/* Radar chart card */}
              <div className="bg-surface p-6 md:p-8 relative">
                <div className="flex items-center justify-between mb-1">
                  <span className="text-volt text-[11px] uppercase tracking-[0.25em] font-bold flex items-center gap-1.5">
                    <span className="w-1.5 h-1.5 bg-volt rounded-full" /> Premium · Performance Radar
                  </span>
                  <span className="locked-pill"><Lock className="w-2.5 h-2.5" strokeWidth={2.2} />Locked</span>
                </div>
                <h3 className="mt-3 font-barlow font-black uppercase text-2xl text-ink">Performance map</h3>
                <p className="mt-1.5 text-xs text-ink/65 leading-snug">Five-axis profile vs position benchmark.</p>
                <div className="mt-4 h-56 relative">
                  {/* Crisp axis labels overlay (peeking through) */}
                  <div className="absolute inset-0 pointer-events-none z-10">
                    {[
                      { label: "Technical", x: "50%", y: "8%" },
                      { label: "Tactical", x: "92%", y: "38%" },
                      { label: "Physical", x: "78%", y: "88%" },
                      { label: "Mentality", x: "22%", y: "88%" },
                      { label: "Decision", x: "8%", y: "38%" },
                    ].map((a) => (
                      <span
                        key={a.label}
                        className="absolute -translate-x-1/2 -translate-y-1/2 text-[10px] uppercase tracking-[0.22em] font-black text-ink/85 bg-cream-card/85 backdrop-blur-sm px-1.5 py-0.5 border border-ink/10 whitespace-nowrap"
                        style={{ left: a.x, top: a.y }}
                      >
                        {a.label}
                      </span>
                    ))}
                  </div>
                  {/* Blurred polygon underneath */}
                  <div className="score-blur absolute inset-0">
                    <ResponsiveContainer width="100%" height="100%">
                      <RadarChart data={dynamicRadar}>
                        <PolarGrid stroke="rgba(31,79,47,0.18)" />
                        <PolarAngleAxis dataKey="axis" tick={false} />
                        <PolarRadiusAxis domain={[0, 10]} tick={false} axisLine={false} />
                        <Radar dataKey="v" stroke="#CCFF00" fill="#CCFF00" fillOpacity={0.45} />
                      </RadarChart>
                    </ResponsiveContainer>
                  </div>
                </div>
              </div>

              {/* Technical scores card */}
              <div className="bg-surface p-6 md:p-8 relative">
                <div className="flex items-center justify-between mb-1">
                  <span className="text-volt text-[11px] uppercase tracking-[0.25em] font-bold flex items-center gap-1.5">
                    <span className="w-1.5 h-1.5 bg-volt rounded-full" /> Premium · Technical
                  </span>
                  <span className="locked-pill"><Lock className="w-2.5 h-2.5" strokeWidth={2.2} />Locked</span>
                </div>
                <h3 className="mt-3 font-barlow font-black uppercase text-2xl text-ink">Technical analysis</h3>
                <p className="mt-1.5 text-xs text-ink/65 leading-snug">7 metrics — vs peers at the same age & position.</p>
                <div className="mt-5 space-y-3">
                  {sample.technical.slice(0, 5).map((t, i) => (
                    <ScoreBar key={i} label={t.k} value={t.v} locked />
                  ))}
                </div>
              </div>

              {/* Tactical scores card */}
              <div className="bg-surface p-6 md:p-8 relative">
                <div className="flex items-center justify-between mb-1">
                  <span className="text-volt text-[11px] uppercase tracking-[0.25em] font-bold flex items-center gap-1.5">
                    <span className="w-1.5 h-1.5 bg-volt rounded-full" /> Premium · Tactical
                  </span>
                  <span className="locked-pill"><Lock className="w-2.5 h-2.5" strokeWidth={2.2} />Locked</span>
                </div>
                <h3 className="mt-3 font-barlow font-black uppercase text-2xl text-ink">Tactical analysis</h3>
                <p className="mt-1.5 text-xs text-ink/65 leading-snug">Positioning, off-ball runs, game awareness, decision making.</p>
                <div className="mt-5 space-y-3">
                  {sample.tactical.slice(0, 5).map((t, i) => (
                    <ScoreBar key={i} label={t.k} value={t.v} locked />
                  ))}
                </div>
              </div>

              {/* Scout view */}
              <div className="bg-surface p-6 md:p-8 lg:col-span-2 relative">
                <div className="flex items-center justify-between mb-1">
                  <span className="text-volt text-[11px] uppercase tracking-[0.25em] font-bold flex items-center gap-1.5">
                    <span className="w-1.5 h-1.5 bg-volt rounded-full" /> Premium · Scout View
                  </span>
                  <span className="locked-pill"><Lock className="w-2.5 h-2.5" strokeWidth={2.2} />Locked</span>
                </div>
                <h3 className="mt-3 font-barlow font-black uppercase text-2xl text-ink">How a scout would see this player</h3>
                <div className="mt-5 grid sm:grid-cols-2 gap-6">
                  <div>
                    <div className="text-xs uppercase tracking-[0.2em] font-black text-forest mb-2 flex items-center gap-2">
                      <CheckCircle2 className="w-3.5 h-3.5" /> What he'd love
                    </div>
                    <ul className="space-y-2 text-sm text-ink/85">
                      {sample.scoutStrengths.map((s, i) => (
                        <li key={i} className="flex gap-2">
                          <span className="text-volt mt-1 shrink-0">▶</span>
                          <span className="score-blur">{s}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                  <div>
                    <div className="text-xs uppercase tracking-[0.2em] font-black text-amber-600 mb-2 flex items-center gap-2">
                      <Target className="w-3.5 h-3.5" /> What he'd worry about
                    </div>
                    <ul className="space-y-2 text-sm text-ink/85">
                      {sample.scoutConcerns.map((s, i) => (
                        <li key={i} className="flex gap-2">
                          <span className="text-amber-600 mt-1 shrink-0">▶</span>
                          <span className="score-blur">{s}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                </div>
                <div className="mt-6 pt-6 border-t border-gray-border grid sm:grid-cols-2 gap-4">
                  <div>
                    <div className="text-[10px] uppercase tracking-[0.22em] font-black text-ink/70 mb-1">Next level to aim for</div>
                    <div className="text-sm text-ink/90 score-blur">{sample.nextLevel}</div>
                  </div>
                  <div>
                    <div className="text-[10px] uppercase tracking-[0.22em] font-black text-ink/70 mb-1">Best position</div>
                    <div className="text-sm text-ink/90 score-blur">{sample.bestPosition}</div>
                  </div>
                </div>
              </div>

              {/* Training exercise card */}
              <div className="bg-surface p-6 md:p-8 relative">
                <div className="flex items-center justify-between mb-1">
                  <span className="text-volt text-[11px] uppercase tracking-[0.25em] font-bold flex items-center gap-1.5">
                    <span className="w-1.5 h-1.5 bg-volt rounded-full" /> Premium · Training Plan
                  </span>
                  <span className="locked-pill"><Lock className="w-2.5 h-2.5" strokeWidth={2.2} />Locked</span>
                </div>
                <h3 className="mt-3 font-barlow font-black uppercase text-2xl text-ink">Drill of the week</h3>
                <p className="mt-1.5 text-xs text-ink/65 leading-snug">Custom drill tailored to your player's biggest weak spot.</p>
                <div className="mt-5 border border-volt/30 bg-deepnavy p-4">
                  <div className="flex items-center justify-between mb-2">
                    <span className="font-barlow font-black uppercase text-ink text-base score-blur">{sample.exercise.name}</span>
                    <span className="flex items-center gap-1 text-xs text-volt font-bold"><Clock className="w-3 h-3" />15 min</span>
                  </div>
                  <p className="text-xs text-ink/70 leading-relaxed score-blur">{sample.exercise.desc}</p>
                </div>
                <div className="mt-4 flex items-center justify-between text-[10px] uppercase tracking-[0.18em] font-black text-ink/65">
                  <span className="flex items-center gap-1.5"><Award className="w-3 h-3 text-volt" />4 more drills</span>
                  <span className="flex items-center gap-1.5"><TrendingUp className="w-3 h-3 text-volt" />30 & 90-day plan</span>
                </div>
              </div>

              {/* Video timeline */}
              <div className="bg-surface p-6 md:p-8 lg:col-span-3 relative">
                <div className="flex items-center justify-between mb-1">
                  <span className="text-volt text-[11px] uppercase tracking-[0.25em] font-bold flex items-center gap-1.5">
                    <span className="w-1.5 h-1.5 bg-volt rounded-full" /> Premium · Video Comments
                  </span>
                  <span className="locked-pill"><Lock className="w-2.5 h-2.5" strokeWidth={2.2} />Locked</span>
                </div>
                <h3 className="mt-3 font-barlow font-black uppercase text-2xl text-ink">Timestamped feedback</h3>
                <p className="mt-1.5 text-xs text-ink/65 leading-snug">Every key moment on your clip, marked with a comment.</p>
                <div className="mt-5 space-y-2">
                  {sample.timeline.map((c, i) => (
                    <div key={i} className="flex items-start gap-4 bg-cream-card/90 border border-gray-border px-4 py-3">
                      <div className="flex items-center gap-2 flex-shrink-0">
                        <Play className="w-3 h-3 text-volt" fill="currentColor" />
                        <span className="font-barlow font-black text-volt text-base min-w-[44px]">{c.t}</span>
                      </div>
                      <p className="text-sm text-ink/85 score-blur">{c.c}</p>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            {/* The sample-report SHOWCASE overlay — premium "scout scope" treatment */}
            <div className="absolute inset-0 z-10 pointer-events-none flex items-center justify-center">
              <motion.div
                initial={{ opacity: 0, scale: 0.92, y: 10 }}
                whileInView={{ opacity: 1, scale: 1, y: 0 }}
                viewport={{ once: true, margin: "-100px" }}
                transition={{ duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
                whileHover={{ y: -3 }}
                className="pointer-events-auto relative max-w-md mx-6 text-center"
              >
                {/* Outer pulsing volt halo */}
                <motion.div
                  aria-hidden
                  className="absolute -inset-6 pointer-events-none -z-10"
                  style={{
                    background: "radial-gradient(circle at center, rgba(204,255,0,0.28) 0%, rgba(204,255,0,0.0) 70%)",
                    filter: "blur(28px)",
                  }}
                  animate={{ opacity: [0.55, 0.95, 0.55], scale: [0.96, 1.03, 0.96] }}
                  transition={{ duration: 3.6, repeat: Infinity, ease: "easeInOut" }}
                />

                {/* The card itself — dark forest with volt double border */}
                <div
                  className="relative bg-forest text-cream-card border-2 border-volt p-8 md:p-10 overflow-hidden"
                  style={{
                    boxShadow:
                      "0 30px 100px -10px rgba(8,18,12,0.65), 0 0 0 6px rgba(31,79,47,0.18), 0 0 80px rgba(204,255,0,0.22)",
                  }}
                >
                  {/* Volt corner brackets — like the cover page jersey */}
                  <span aria-hidden className="absolute top-3 left-3 w-5 h-5 border-t-2 border-l-2 border-volt" />
                  <span aria-hidden className="absolute top-3 right-3 w-5 h-5 border-t-2 border-r-2 border-volt" />
                  <span aria-hidden className="absolute bottom-3 left-3 w-5 h-5 border-b-2 border-l-2 border-volt" />
                  <span aria-hidden className="absolute bottom-3 right-3 w-5 h-5 border-b-2 border-r-2 border-volt" />

                  {/* Subtle radial volt glow inside top */}
                  <div
                    aria-hidden
                    className="absolute -top-24 left-1/2 -translate-x-1/2 w-64 h-64 pointer-events-none"
                    style={{
                      background: "radial-gradient(circle, rgba(204,255,0,0.25) 0%, transparent 70%)",
                      filter: "blur(20px)",
                    }}
                  />

                  {/* === SCOUT SCOPE emblem (replaces the flat eye box) === */}
                  <div className="relative mx-auto mb-6 w-20 h-20 md:w-24 md:h-24">
                    <svg viewBox="0 0 100 100" className="absolute inset-0 w-full h-full" aria-hidden>
                      {/* outer rotating dashed ring */}
                      <motion.g
                        style={{ transformOrigin: "50px 50px" }}
                        animate={{ rotate: 360 }}
                        transition={{ duration: 26, repeat: Infinity, ease: "linear" }}
                      >
                        <circle cx="50" cy="50" r="46" fill="none" stroke="#CCFF00" strokeWidth="1.2"
                                strokeDasharray="3 4" opacity="0.55" />
                      </motion.g>
                      {/* mid concentric ring */}
                      <circle cx="50" cy="50" r="36" fill="none" stroke="#CCFF00" strokeWidth="1" opacity="0.4" />
                      {/* crosshair lines */}
                      <line x1="50" y1="6"  x2="50" y2="20" stroke="#CCFF00" strokeWidth="1.2" opacity="0.7" />
                      <line x1="50" y1="80" x2="50" y2="94" stroke="#CCFF00" strokeWidth="1.2" opacity="0.7" />
                      <line x1="6"  y1="50" x2="20" y2="50" stroke="#CCFF00" strokeWidth="1.2" opacity="0.7" />
                      <line x1="80" y1="50" x2="94" y2="50" stroke="#CCFF00" strokeWidth="1.2" opacity="0.7" />
                      {/* inner scanning sweep arc */}
                      <motion.g
                        style={{ transformOrigin: "50px 50px" }}
                        animate={{ rotate: 360 }}
                        transition={{ duration: 4, repeat: Infinity, ease: "linear" }}
                      >
                        <path
                          d="M50 50 L50 18 A32 32 0 0 1 78 44 Z"
                          fill="#CCFF00"
                          opacity="0.18"
                        />
                      </motion.g>
                      {/* inner solid ring */}
                      <circle cx="50" cy="50" r="24" fill="none" stroke="#CCFF00" strokeWidth="1.4" opacity="0.85" />
                      {/* center pulsing dot */}
                      <motion.circle
                        cx="50" cy="50" r="6"
                        fill="#CCFF00"
                        animate={{ r: [5.5, 7.5, 5.5], opacity: [0.85, 1, 0.85] }}
                        transition={{ duration: 1.8, repeat: Infinity, ease: "easeInOut" }}
                      />
                      <circle cx="50" cy="50" r="2.4" fill="#1F4F2F" />
                    </svg>
                  </div>

                  <span className="text-volt text-[11px] uppercase tracking-[0.3em] font-bold flex items-center justify-center gap-2">
                    <span aria-hidden className="w-6 h-px bg-volt/60" />
                    The full breakdown
                    <span aria-hidden className="w-6 h-px bg-volt/60" />
                  </span>

                  <h3 className="mt-3 font-barlow font-black uppercase text-3xl md:text-4xl tracking-tighter leading-[0.95] text-cream-card">
                    See what a
                    <span className="block mt-1">
                      <span className="font-serif-italic normal-case font-normal lowercase tracking-normal text-volt">scout</span>
                      <span>{" "}sees</span>
                    </span>
                  </h3>

                  <p className="mt-4 text-sm text-cream-card/85 leading-relaxed">
                    Where your player stands today. What separates them from the next level. The 5 drills that will actually move the needle. Reviewed by a real scout — not just a number on a page.
                  </p>

                  <button
                    type="button"
                    data-testid="sample-see-plans-cta"
                    onClick={() => {
                      const el = document.getElementById("pricing");
                      if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
                    }}
                    className="mt-7 group relative w-full bg-volt hover:bg-volt-hover text-ink font-barlow font-black uppercase tracking-[0.2em] text-sm py-4 flex items-center justify-center gap-2 transition-all duration-300 overflow-hidden"
                    style={{ boxShadow: "0 6px 24px rgba(204,255,0,0.4)" }}
                  >
                    {/* shimmer sweep on hover */}
                    <span
                      aria-hidden
                      className="absolute inset-0 -translate-x-full group-hover:translate-x-full transition-transform duration-700 ease-out pointer-events-none"
                      style={{
                        background: "linear-gradient(120deg, transparent 35%, rgba(255,255,255,0.45) 50%, transparent 65%)",
                      }}
                    />
                    <span className="relative">See plans</span>
                    <ArrowDown className="relative w-4 h-4 group-hover:translate-y-1 transition-transform" />
                  </button>

                  <p className="mt-4 text-[10px] text-cream-card/65 flex items-center justify-center gap-1.5 uppercase tracking-[0.2em] font-bold">
                    <ShieldCheck className="w-3 h-3 text-volt" /> Free preview · No card to start
                  </p>
                  <div className="mt-5 pt-5 border-t border-cream-card/15 flex justify-center">
                    <PaymentBadges variant="compact" />
                  </div>
                </div>
              </motion.div>
            </div>
          </div>
        </div>
      </section>

      {/* ============ PRICING — clean section with formation backdrop (line art only) ============ */}
      <section id="pricing" data-testid="pricing-section" className="section-accent-top relative py-16 md:py-20 border-t border-gray-border overflow-hidden">
        {/* Subtle dot pattern */}
        <div
          aria-hidden
          className="absolute inset-0 opacity-[0.04] pointer-events-none"
          style={{
            backgroundImage:
              "radial-gradient(circle at 1px 1px, #1F4F2F 1px, transparent 0)",
            backgroundSize: "24px 24px",
          }}
        />

        {/* Formation diagram backdrop — 4-3-3, subtle white dots */}
        <svg
          aria-hidden
          viewBox="0 0 1200 800"
          preserveAspectRatio="xMidYMid slice"
          className="absolute inset-0 w-full h-full opacity-[0.06] pointer-events-none"
        >
          {/* Pitch outline */}
          <rect x="80" y="60" width="1040" height="680" fill="none" stroke="#1F4F2F" strokeWidth="2" />
          {/* Centre line + circle */}
          <line x1="600" y1="60" x2="600" y2="740" stroke="#1F4F2F" strokeWidth="2" />
          <circle cx="600" cy="400" r="80" fill="none" stroke="#1F4F2F" strokeWidth="2" />
          {/* Penalty boxes */}
          <rect x="80" y="240" width="160" height="320" fill="none" stroke="#1F4F2F" strokeWidth="2" />
          <rect x="960" y="240" width="160" height="320" fill="none" stroke="#1F4F2F" strokeWidth="2" />
          {/* 4-3-3 formation player dots (left side) */}
          {[
            [140, 400],   // GK
            [260, 180], [260, 320], [260, 480], [260, 620],   // 4 defenders
            [400, 260], [400, 400], [400, 540],   // 3 mids
            [540, 220], [540, 580],   // 2 wide forwards
            [560, 400],   // CF
          ].map(([cx, cy], i) => (
            <circle key={i} cx={cx} cy={cy} r="14" fill="#1F4F2F" opacity="0.6" />
          ))}
          {/* Highlighted player — volt with halo */}
          <circle cx="400" cy="400" r="20" fill="#CCFF00" opacity="0.5" />
          <circle cx="400" cy="400" r="32" fill="none" stroke="#CCFF00" strokeWidth="2" opacity="0.4" />
        </svg>

        <div className="relative z-10 max-w-7xl mx-auto px-6 md:px-10">
          <div className="text-center max-w-3xl mx-auto">
            <div className="inline-flex items-center gap-2.5 mb-4">
              <span aria-hidden className="relative flex items-center justify-center w-2 h-2 shrink-0">
                <span className="absolute inset-0 rounded-full bg-volt animate-ping opacity-75" />
                <span className="relative rounded-full w-1.5 h-1.5 bg-volt" />
              </span>
              <span className="text-volt text-xs uppercase tracking-[0.3em] font-bold">Pricing</span>
              <span aria-hidden className="h-px w-12 bg-gradient-to-r from-volt/55 to-transparent" />
            </div>
            <h2 className="font-barlow font-black uppercase text-4xl md:text-6xl tracking-tighter leading-[0.95]">
              Where does your player stand —
              <span className="block text-volt mt-2">and where will they be in a year?</span>
            </h2>
            <p className="mt-5 text-ink/70 text-base md:text-lg leading-relaxed">
              Both plans include a personal review from a real scout / agent on top of the advanced benchmarked intelligence analysis.
            </p>

            {/* Trust strip — sits above the cards to reduce price anxiety */}
            <div className="mt-7 flex flex-wrap items-center justify-center gap-x-6 gap-y-2 text-[11px] uppercase tracking-[0.18em] font-bold text-ink/55">
              <span className="flex items-center gap-1.5">
                <ShieldCheck className="w-3.5 h-3.5 text-forest" /> Scout review in 48h
              </span>
              <span className="text-ink/25">·</span>
              <span className="flex items-center gap-1.5">
                <Users className="w-3.5 h-3.5 text-forest" /> Trusted across 12+ countries
              </span>
              <span className="text-ink/25">·</span>
              <span className="flex items-center gap-1.5">
                <Lock className="w-3.5 h-3.5 text-forest" /> Secure Stripe checkout
              </span>
            </div>
          </div>

          <div className="mt-12">
            <PricingCards isLoggedIn={!!user} singleHref={startHref} />
          </div>
        </div>
      </section>

      {/* ============ FAQ — Most common parent / player questions ============ */}
      <FAQSection />

      {/* ============ TRUST — 2-column with football photo plate ============ */}
      <section id="trust" data-testid="trust-section" className="section-accent-top relative py-16 md:py-20 border-t border-gray-border">
        <div className="max-w-7xl mx-auto px-6 md:px-10">
          {/* ── Refund Guarantee — premium graphic banner ── */}
          <div
            data-testid="refund-guarantee-strip"
            className="relative mb-14 grid md:grid-cols-12 border border-gray-border bg-deepnavy overflow-hidden"
            style={{
              boxShadow:
                "0 36px 70px -28px rgba(10, 15, 13, 0.45), 0 12px 28px -10px rgba(10, 15, 13, 0.18)",
            }}
          >
            {/* ─── LEFT: Gold Champion Medallion ─── */}
            <div className="relative md:col-span-5 bg-ink text-white p-8 md:p-10 overflow-hidden flex items-center justify-center">
              {/* Deep navy → ink radial backdrop with soft warm glow behind badge */}
              <div
                aria-hidden
                className="absolute inset-0 pointer-events-none"
                style={{
                  background:
                    "radial-gradient(circle at 50% 50%, rgba(212,175,55,0.10) 0%, rgba(212,175,55,0.04) 30%, rgba(10,15,13,1) 70%)",
                }}
              />
              {/* Tiny stars pattern */}
              <div
                aria-hidden
                className="absolute inset-0 opacity-[0.04] pointer-events-none"
                style={{
                  backgroundImage:
                    "radial-gradient(circle at 25% 25%, #F4D87C 1px, transparent 1.5px), radial-gradient(circle at 75% 65%, #F4D87C 1px, transparent 1.5px), radial-gradient(circle at 40% 80%, #F4D87C 1px, transparent 1.5px)",
                  backgroundSize: "120px 120px",
                }}
              />

              {/* SVG MEDALLION */}
              <svg
                viewBox="0 0 300 300"
                aria-hidden
                className="relative w-[240px] md:w-[280px] h-auto"
                style={{
                  filter:
                    "drop-shadow(0 24px 36px rgba(0,0,0,0.55)) drop-shadow(0 8px 14px rgba(168,136,41,0.35))",
                }}
              >
                <defs>
                  {/* Outer ring metallic gold */}
                  <linearGradient id="gold-rim" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#F4D87C" />
                    <stop offset="35%" stopColor="#D4AF37" />
                    <stop offset="70%" stopColor="#A88829" />
                    <stop offset="100%" stopColor="#7A6018" />
                  </linearGradient>
                  {/* Inner medallion face — radial highlight */}
                  <radialGradient id="gold-face" cx="40%" cy="32%" r="75%">
                    <stop offset="0%" stopColor="#FBE9A6" />
                    <stop offset="45%" stopColor="#E6C76A" />
                    <stop offset="85%" stopColor="#B7902B" />
                    <stop offset="100%" stopColor="#8B7126" />
                  </radialGradient>
                  {/* Inner dark ring */}
                  <radialGradient id="dark-ring" cx="50%" cy="50%" r="50%">
                    <stop offset="0%" stopColor="#1A1A18" />
                    <stop offset="100%" stopColor="#0A0807" />
                  </radialGradient>
                  {/* Text path — full circle, going CW from top */}
                  <path
                    id="badge-ring-text-path"
                    d="M 150,38 A 112,112 0 1,1 149.99,38"
                    fill="none"
                  />
                </defs>

                {/* Starburst rays behind */}
                {Array.from({ length: 24 }).map((_, i) => {
                  const a = (i / 24) * 360;
                  return (
                    <line
                      key={i}
                      x1="150"
                      y1="150"
                      x2={150 + Math.cos((a * Math.PI) / 180) * 145}
                      y2={150 + Math.sin((a * Math.PI) / 180) * 145}
                      stroke="#D4AF37"
                      strokeWidth={i % 2 === 0 ? "1.5" : "0.8"}
                      opacity={i % 2 === 0 ? "0.22" : "0.10"}
                    />
                  );
                })}

                {/* Outer gold ring */}
                <circle cx="150" cy="150" r="140" fill="url(#gold-rim)" />
                {/* Dark inner ring (where the curved text sits) */}
                <circle cx="150" cy="150" r="125" fill="url(#dark-ring)" />
                {/* Medallion face */}
                <circle cx="150" cy="150" r="108" fill="url(#gold-face)" />

                {/* Inner thin gold accent ring */}
                <circle cx="150" cy="150" r="100" fill="none" stroke="#7A6018" strokeWidth="1.5" opacity="0.5" />
                <circle cx="150" cy="150" r="96" fill="none" stroke="#FBE9A6" strokeWidth="0.6" opacity="0.85" />

                {/* Outer ring curved text */}
                <text fontFamily="Barlow Condensed, Barlow, sans-serif" fontWeight="900" fontSize="14" fill="#FBE9A6" letterSpacing="3.6">
                  <textPath href="#badge-ring-text-path" startOffset="0">
                    ★ GUARANTEED · 48 HOURS · GUARANTEED · 48 HOURS ★
                  </textPath>
                </text>

                {/* Center: "48" big */}
                <text
                  x="150"
                  y="158"
                  fontFamily="Barlow Condensed, Barlow, sans-serif"
                  fontWeight="900"
                  fontSize="92"
                  fill="#0A0807"
                  textAnchor="middle"
                  letterSpacing="-3"
                >
                  48h
                </text>
                {/* Subtle text shine highlight */}
                <text
                  x="150"
                  y="158"
                  fontFamily="Barlow Condensed, Barlow, sans-serif"
                  fontWeight="900"
                  fontSize="92"
                  fill="#FBE9A6"
                  textAnchor="middle"
                  letterSpacing="-3"
                  opacity="0.18"
                  transform="translate(0,-2)"
                >
                  48h
                </text>

                {/* Below "OR IT'S FREE" */}
                <text
                  x="150"
                  y="198"
                  fontFamily="Barlow Condensed, Barlow, sans-serif"
                  fontWeight="900"
                  fontSize="13"
                  fill="#0A0807"
                  textAnchor="middle"
                  letterSpacing="3.5"
                >
                  OR IT&apos;S FREE
                </text>

                {/* Decorative side stars inside the face */}
                <text x="78" y="160" fontSize="14" fill="#7A6018" textAnchor="middle" opacity="0.6">★</text>
                <text x="222" y="160" fontSize="14" fill="#7A6018" textAnchor="middle" opacity="0.6">★</text>

                {/* Bottom laurel-style chevron */}
                <text x="150" y="222" fontSize="10" fill="#7A6018" textAnchor="middle" letterSpacing="2" opacity="0.7">— SCOUTMEPLAY —</text>
              </svg>
            </div>

            {/* ─── RIGHT: 3-step journey + body ─── */}
            <div className="md:col-span-7 p-8 md:p-10 bg-deepnavy text-ink relative">
              {/* Faint scout-notebook dot pattern */}
              <div
                aria-hidden
                className="absolute inset-0 opacity-[0.04] pointer-events-none"
                style={{
                  backgroundImage: "radial-gradient(circle at 1px 1px, #1F4F2F 1px, transparent 0)",
                  backgroundSize: "26px 26px",
                }}
              />
              <div className="relative">
                <div className="flex items-start gap-4 md:gap-5">
                  <div className="flex-1 min-w-0">
                    <h3 className="font-barlow font-black uppercase text-2xl md:text-3xl tracking-tighter leading-[1.02]">
                      Your report in <span className="text-forest">48 hours</span>,<br />
                      or we refund you.<br />
                      <span className="text-forest">Automatically.</span>
                    </h3>
                  </div>
                  {/* 48h countdown arc visualisation — animated SVG */}
                  <motion.div
                    initial={{ scale: 0.8, opacity: 0 }}
                    whileInView={{ scale: 1, opacity: 1 }}
                    viewport={{ once: true }}
                    transition={{ duration: 0.6, delay: 0.2, ease: [0.16, 1, 0.3, 1] }}
                    className="relative shrink-0 w-[88px] h-[88px] md:w-[104px] md:h-[104px]"
                    aria-hidden
                  >
                    <svg viewBox="0 0 110 110" className="w-full h-full">
                      <defs>
                        <linearGradient id="countdown-grad" x1="0" y1="0" x2="1" y2="1">
                          <stop offset="0%" stopColor="#CCFF00" />
                          <stop offset="100%" stopColor="#1F4F2F" />
                        </linearGradient>
                      </defs>
                      {/* track */}
                      <circle cx="55" cy="55" r="44" fill="none" stroke="rgba(31,79,47,0.15)" strokeWidth="6" />
                      {/* hour ticks */}
                      {Array.from({ length: 12 }).map((_, i) => {
                        const a = (i / 12) * Math.PI * 2 - Math.PI / 2;
                        const r1 = 50, r2 = 53;
                        return (
                          <line
                            key={i}
                            x1={55 + r1 * Math.cos(a)} y1={55 + r1 * Math.sin(a)}
                            x2={55 + r2 * Math.cos(a)} y2={55 + r2 * Math.sin(a)}
                            stroke="rgba(31,79,47,0.35)" strokeWidth="1"
                          />
                        );
                      })}
                      {/* main 48h progress sweep — sweeps 80% of the dial */}
                      <motion.circle
                        cx="55" cy="55" r="44" fill="none"
                        stroke="url(#countdown-grad)" strokeWidth="6"
                        strokeLinecap="round"
                        strokeDasharray="276.46"
                        transform="rotate(-90 55 55)"
                        initial={{ strokeDashoffset: 276.46 }}
                        whileInView={{ strokeDashoffset: 55 }}
                        viewport={{ once: true }}
                        transition={{ duration: 1.6, delay: 0.35, ease: "easeOut" }}
                      />
                      {/* sweeping highlight */}
                      <motion.line
                        x1="55" y1="55" x2="55" y2="14"
                        stroke="#CCFF00" strokeWidth="1.6" strokeLinecap="round"
                        style={{ transformOrigin: "55px 55px" }}
                        animate={{ rotate: [0, 360] }}
                        transition={{ duration: 6, repeat: Infinity, ease: "linear" }}
                        opacity="0.55"
                      />
                      {/* center label "48h" */}
                      <text
                        x="55" y="56"
                        textAnchor="middle" dominantBaseline="middle"
                        fontFamily="Barlow Condensed, sans-serif"
                        fontWeight="900"
                        fontSize="28"
                        fill="#1F4F2F"
                      >
                        48h
                      </text>
                      <text
                        x="55" y="72"
                        textAnchor="middle"
                        fontFamily="Barlow Condensed, sans-serif"
                        fontWeight="700"
                        fontSize="6.5"
                        fill="#1F4F2F"
                        opacity="0.55"
                        letterSpacing="0.5"
                      >
                        DELIVERY
                      </text>
                    </svg>
                  </motion.div>
                </div>

                {/* 3-step visual journey */}
                <ol className="mt-6 grid grid-cols-3 gap-0 relative">
                  {/* Connecting horizontal line behind dots */}
                  <span aria-hidden className="absolute left-[16%] right-[16%] top-[18px] h-[2px] bg-forest/25 pointer-events-none" />
                  {[
                    { n: "01", t: "You pay", d: "Stripe-secure checkout" },
                    { n: "02", t: "Instant AI report", d: "Delivered right after upload" },
                    { n: "03", t: "Scout follow-up", d: "Real scout within 48h" },
                  ].map((s, i) => (
                    <li key={i} data-testid={`refund-step-${i}`} className="relative flex flex-col items-center text-center px-1.5">
                      <span className="relative w-9 h-9 rounded-full bg-forest text-white flex items-center justify-center font-barlow font-black text-sm shadow-md">
                        {s.n}
                      </span>
                      <span className="mt-2.5 font-barlow font-black uppercase text-[12px] tracking-tight text-ink leading-tight">
                        {s.t}
                      </span>
                      <span className="mt-0.5 text-[10px] uppercase tracking-[0.14em] font-bold text-ink/55 leading-tight">
                        {s.d}
                      </span>
                    </li>
                  ))}
                </ol>

                {/* Bottom: trust chips */}
                <div className="mt-7 pt-4 border-t border-gray-border flex flex-wrap items-center gap-x-5 gap-y-2 text-[10px] uppercase tracking-[0.18em] font-bold text-ink/65">
                  <span className="flex items-center gap-1.5"><CheckCircle2 className="w-3.5 h-3.5 text-forest" /> No support tickets</span>
                  <span className="flex items-center gap-1.5"><CheckCircle2 className="w-3.5 h-3.5 text-forest" /> 100% Stripe refund</span>
                  <span className="flex items-center gap-1.5"><CheckCircle2 className="w-3.5 h-3.5 text-forest" /> Auto-issued in 5 days</span>
                </div>
              </div>
            </div>
          </div>

          <div className="grid md:grid-cols-12 border border-gray-border bg-surface overflow-hidden">
            {/* Left: football photo plate (5/12) */}
            <div className="relative md:col-span-5 min-h-[220px] md:min-h-[280px] bg-deepnavy overflow-hidden">
              <img
                src="https://images.pexels.com/photos/12616082/pexels-photo-12616082.jpeg"
                alt=""
                className="absolute inset-0 w-full h-full object-cover"
                style={{ filter: "sepia(0.35) saturate(1.5) hue-rotate(75deg) contrast(0.95)" }}
              />
              {/* Forest tint overlay + corner brackets like a scout notepad */}
              <div className="absolute inset-0 bg-gradient-to-tr from-forest/85 via-forest/45 to-forest/15" />
              <span aria-hidden className="absolute top-5 left-5 w-6 h-6 border-t-2 border-l-2 border-volt" />
              <span aria-hidden className="absolute top-5 right-5 w-6 h-6 border-t-2 border-r-2 border-volt" />
              <span aria-hidden className="absolute bottom-5 left-5 w-6 h-6 border-b-2 border-l-2 border-volt" />
              <span aria-hidden className="absolute bottom-5 right-5 w-6 h-6 border-b-2 border-r-2 border-volt" />
              {/* Floating eyebrow + shield */}
              <div className="absolute bottom-6 left-6 right-6 flex items-center gap-3 text-white">
                <ShieldCheck className="w-8 h-8 text-volt shrink-0" strokeWidth={1.5} />
                <span className="text-[10px] uppercase tracking-[0.28em] font-bold text-white/90">
                  Built for growth · not for promises
                </span>
              </div>
            </div>
            {/* Right: copy (7/12) */}
            <div className="md:col-span-7 p-8 md:p-12 flex flex-col justify-center">
              <div className="inline-flex items-center gap-2.5 mb-3">
                <span aria-hidden className="relative flex items-center justify-center w-2 h-2 shrink-0">
                  <span className="absolute inset-0 rounded-full bg-volt animate-ping opacity-75" />
                  <span className="relative rounded-full w-1.5 h-1.5 bg-volt" />
                </span>
                <span className="text-volt text-[10px] uppercase tracking-[0.25em] font-bold">
                  Our promise
                </span>
              </div>
              <h3 className="font-barlow font-black uppercase text-2xl md:text-3xl tracking-tighter leading-[0.95]">
                Honest scouting feedback.
                <span className="block text-forest mt-1">Built for growth.</span>
              </h3>
              <p className="mt-4 text-sm text-ink/70 leading-relaxed max-w-2xl">
                ScoutMePlay gives you honest, professional football feedback to help young players get better.
                It does <strong className="text-ink">not</strong> promise trials, contracts, or academy spots.
                Your scores are here to guide your training — not to decide your future.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* ============ FINAL CTA ============ */}
      <section data-testid="final-cta" className="section-accent-top relative py-16 md:py-20 border-t border-gray-border overflow-hidden">
        <div className="absolute inset-0 z-0">
          <img
            src="https://images.pexels.com/photos/12616082/pexels-photo-12616082.jpeg"
            alt="Player action"
            className="w-full h-full object-cover opacity-25"
          />
          <div className="absolute inset-0 bg-gradient-to-t from-deepnavy via-deepnavy/80 to-deepnavy/60" />
        </div>
        <div className="relative z-10 max-w-5xl mx-auto px-6 md:px-10 text-center">
          <h2 className="font-barlow font-black uppercase text-5xl md:text-7xl tracking-tighter leading-[0.95]">
            Ready to discover
            <span className="block text-volt mt-2">your true level?</span>
          </h2>
          <p className="mt-6 text-ink/65 max-w-2xl mx-auto">
            Upload your video and get an instant free scout preview. Built for ambitious U7–U21 players chasing the next level. No card needed to start.
          </p>
          <div className="mt-10">
            <Link
              to={startHref}
              data-testid="final-cta-btn"
              className="inline-flex items-center gap-3 bg-volt hover:bg-forest-pop text-white font-barlow font-black uppercase tracking-widest text-base px-10 py-5 transition-colors"
            >
              {startLabel}
              <ArrowRight className="w-5 h-5" />
            </Link>
            <div className="mt-5 flex justify-center">
              <PaymentBadges variant="compact" />
            </div>
          </div>
        </div>
      </section>

      {/* ============ FOOTER — Premium solid forest band ============ */}
      <footer
        data-testid="site-footer"
        className="relative mt-12 text-white overflow-hidden"
        style={{
          background:
            "linear-gradient(180deg, #0E2218 0%, #0A1C12 50%, #050D08 100%)",
        }}
      >
        {/* Crisp lime accent edge at top */}
        <div aria-hidden className="absolute inset-x-0 top-0 h-[2px] bg-gradient-to-r from-transparent via-volt/80 to-transparent" />
        {/* Pitch lines pattern — extremely subtle horizontal scoreline */}
        <div
          aria-hidden
          className="absolute inset-0 pointer-events-none opacity-[0.04]"
          style={{
            backgroundImage:
              "repeating-linear-gradient(0deg, rgba(255,255,255,0.4) 0 1px, transparent 1px 56px)",
          }}
        />
        {/* Soft grain noise for premium texture */}
        <div
          aria-hidden
          className="absolute inset-0 pointer-events-none opacity-[0.05] mix-blend-overlay"
          style={{
            backgroundImage:
              "url(\"data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='160' height='160'><filter id='n'><feTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='2' stitchTiles='stitch'/></filter><rect width='100%' height='100%' filter='url(%23n)' opacity='0.85'/></svg>\")",
          }}
        />
        {/* Single contained accent — bottom-right only, very subtle */}
        <div aria-hidden className="absolute -bottom-32 right-1/4 w-[420px] h-[420px] bg-forest-pop/[0.08] rounded-full blur-3xl pointer-events-none" />

        <div className="relative max-w-7xl mx-auto px-6 md:px-10 pt-16 md:pt-20 pb-10">
          <div className="grid grid-cols-2 md:grid-cols-12 gap-10 md:gap-12">

            {/* ── Brand block ── */}
            <div className="col-span-2 md:col-span-5">
              {/* Same wordmark as the top nav */}
              <Link to="/" data-testid="footer-logo" className="inline-flex flex-col leading-none group">
                <span className="font-barlow font-black uppercase text-white text-2xl tracking-[0.16em] whitespace-nowrap flex items-baseline gap-[1px]">
                  <span>SCOUT</span>
                  <span
                    className="relative inline-block px-[3px] text-ink transition-colors duration-300"
                    style={{ background: "#ccff00" }}
                  >
                    ME
                  </span>
                  <span>PLAY</span>
                </span>
                <span className="mt-2 flex items-center gap-1.5 text-[9px] text-white/55 font-bold uppercase tracking-[0.14em] whitespace-nowrap">
                  <span
                    aria-hidden
                    className="inline-block w-1 h-1 rounded-full"
                    style={{ background: "#ccff00", boxShadow: "0 0 6px #ccff0099" }}
                  />
                  See your game through scout eyes
                </span>
              </Link>

              <p className="mt-6 text-sm text-white/65 leading-relaxed max-w-md">
                A premium football scouting platform that gives ambitious young players honest,
                professional feedback — built to help every player understand their game and reach the next level.
              </p>

              {/* Social share — premium pill row */}
              <div className="mt-8">
                <div className="text-[10px] uppercase tracking-[0.25em] font-bold text-white/40 mb-3">
                  Share ScoutMePlay
                </div>
                <div className="flex items-center gap-2.5">
                  {[
                    {
                      label: "Share on X",
                      Icon: Twitter,
                      href: `https://twitter.com/intent/tweet?text=${encodeURIComponent("Discover ScoutMePlay — where talent gets noticed. A premium football scouting platform for U7–U21 players.")}&url=${encodeURIComponent(typeof window !== "undefined" ? window.location.origin : "")}`,
                    },
                    {
                      label: "Share on Facebook",
                      Icon: Facebook,
                      href: `https://www.facebook.com/sharer/sharer.php?u=${encodeURIComponent(typeof window !== "undefined" ? window.location.origin : "")}`,
                    },
                    {
                      label: "Share on LinkedIn",
                      Icon: Linkedin,
                      href: `https://www.linkedin.com/sharing/share-offsite/?url=${encodeURIComponent(typeof window !== "undefined" ? window.location.origin : "")}`,
                    },
                    {
                      label: "Share on WhatsApp",
                      Icon: MessageCircle,
                      href: `https://wa.me/?text=${encodeURIComponent("Check out ScoutMePlay — football scouting reports for young players. " + (typeof window !== "undefined" ? window.location.origin : ""))}`,
                    },
                  ].map(({ label, Icon, href }, i) => (
                    <a
                      key={i}
                      href={href}
                      target="_blank"
                      rel="noopener noreferrer"
                      data-testid={`footer-share-${label.toLowerCase().replace(/[^a-z]+/g, "-")}`}
                      aria-label={label}
                      className="group w-10 h-10 flex items-center justify-center rounded-full border border-white/15 bg-white/[0.04] backdrop-blur-sm text-white/60 hover:text-ink hover:border-volt hover:bg-volt transition-all duration-300"
                    >
                      <Icon className="w-4 h-4 transition-transform group-hover:scale-110" strokeWidth={1.8} />
                    </a>
                  ))}
                </div>

                {/* Follow row — admin-editable handles */}
                <div className="mt-5 text-[10px] uppercase tracking-[0.25em] font-bold text-white/40 mb-3">
                  Follow us
                </div>
                <div className="flex items-center gap-2.5">
                  {[
                    { key: "instagram_url", label: "Follow on Instagram", Icon: Instagram },
                    { key: "twitter_url",   label: "Follow on X",         Icon: Twitter },
                    { key: "facebook_url",  label: "Follow on Facebook",  Icon: Facebook },
                    { key: "linkedin_url",  label: "Follow on LinkedIn",  Icon: Linkedin },
                  ]
                    .filter((it) => social && social[it.key])
                    .map(({ key, label, Icon }, i) => (
                      <a
                        key={i}
                        href={social[key]}
                        target="_blank"
                        rel="noopener noreferrer"
                        data-testid={`footer-follow-${key.replace("_url", "")}`}
                        aria-label={label}
                        className="group w-10 h-10 flex items-center justify-center rounded-full border border-white/15 bg-white/[0.04] backdrop-blur-sm text-white/60 hover:text-ink hover:border-volt hover:bg-volt transition-all duration-300"
                      >
                        <Icon className="w-4 h-4 transition-transform group-hover:scale-110" strokeWidth={1.8} />
                      </a>
                    ))}
                </div>
              </div>
            </div>

            {/* ── Explore column ── */}
            <div className="col-span-1 md:col-span-2">
              <div className="text-[10px] uppercase tracking-[0.25em] font-bold text-volt">Explore</div>
              <ul className="mt-5 space-y-3 text-sm">
                <FooterLink to="/" testid="footer-link-home">Home</FooterLink>
                <FooterLink to="/about" testid="footer-link-about">About</FooterLink>
                <FooterLink to="/blog" testid="footer-link-blog">Blog</FooterLink>
                <FooterLink to="/about#contact" testid="footer-link-contact-form" icon={Send}>
                  Contact
                </FooterLink>
              </ul>
            </div>

            {/* ── Product column ── */}
            <div className="col-span-1 md:col-span-3">
              <div className="text-[10px] uppercase tracking-[0.25em] font-bold text-volt">Product</div>
              <ul className="mt-5 space-y-3 text-sm">
                <FooterLink to="/?scroll=how-it-works" testid="footer-link-how-it-works">How it works</FooterLink>
                <FooterLink to="/?scroll=what-you-get" testid="footer-link-whats-inside">What&apos;s inside</FooterLink>
                <FooterLink to="/?scroll=example-report" testid="footer-link-sample">Sample report</FooterLink>
                <FooterLink to="/?scroll=pricing-section" testid="footer-link-pricing">Pricing</FooterLink>
              </ul>
            </div>

            {/* ── Legal column ── */}
            <div className="col-span-2 md:col-span-2">
              <div className="text-[10px] uppercase tracking-[0.25em] font-bold text-volt">Legal</div>
              <ul className="mt-5 space-y-3 text-sm">
                <FooterLink to="/privacy" testid="footer-link-privacy">Privacy Policy</FooterLink>
                <FooterLink to="/terms" testid="footer-link-terms">Terms of Service</FooterLink>
                <FooterLink to="/methodology" testid="footer-link-methodology">Methodology</FooterLink>
              </ul>
            </div>
          </div>

          {/* Bottom bar */}
          <div className="mt-14 pt-6 border-t border-white/10 flex flex-col md:flex-row justify-between gap-3 items-center">
            <p className="text-[10px] uppercase tracking-[0.22em] font-bold text-white/45">
              © {new Date().getFullYear()} ScoutMePlay · All rights reserved
            </p>
            <p className="text-[10px] uppercase tracking-[0.22em] font-bold text-white/45 flex items-center gap-2">
              <span
                aria-hidden
                className="inline-block w-1 h-1 rounded-full"
                style={{ background: "#ccff00", boxShadow: "0 0 6px #ccff0099" }}
              />
              Where talent gets noticed
            </p>
          </div>
        </div>
      </footer>
    </div>
  );
}

/* Footer link helper — keeps every link visually consistent + on-brand hover */
function FooterLink({ to, children, testid, icon: IconCmp }) {
  return (
    <li>
      <Link
        to={to}
        data-testid={testid}
        className="group inline-flex items-center gap-1.5 text-white/60 hover:text-white transition-colors duration-300"
      >
        {IconCmp && <IconCmp className="w-3.5 h-3.5 shrink-0 opacity-70 group-hover:opacity-100 transition-opacity" />}
        <span className="relative">
          {children}
          <span
            aria-hidden
            className="absolute left-0 -bottom-0.5 h-px w-0 group-hover:w-full transition-all duration-300"
            style={{ background: "#ccff00" }}
          />
        </span>
      </Link>
    </li>
  );
}

/* ─────────────────────────────────────────────────────────────────
 *  FAQ Section — accordion of the most common parent / player questions
 *  Honest, no promises, no metrics.
 * ───────────────────────────────────────────────────────────────── */
const FAQ_ITEMS = [
  {
    q: "How long does it take to get my report?",
    a: "Your Pro Scout Intelligence analysis is delivered instantly — as soon as the AI pipeline finishes processing your video (typically 5–15 minutes, depending on clip length). If your plan includes a real scout review (VIP Premium), a professional scout responds with their personal feedback within 48 hours on top of the instant AI report. If we ever miss that 48-hour window on a scout review, your purchase is refunded in full — automatically, no support tickets needed.",
  },
  {
    q: "Is my child too young for this?",
    a: "ScoutMePlay is built for ambitious players aged U7 to U21. The report adjusts to the player's age — a 9-year-old is benchmarked against age-appropriate development standards, not against a senior pro. You get an honest read of where the player is, and where they could realistically go next.",
  },
  {
    q: "What if my video isn't great quality?",
    a: "A phone camera at training or a game is perfectly fine. We need to see your player on the pitch with the ball. Wider shots (showing more of the pitch) are better than tight close-ups, and a clear view of the player's movement helps the scout review. If our scout can't fairly assess the video, we contact you and either offer a re-upload or a refund.",
  },
  {
    q: "How is this different from my child's coach feedback?",
    a: "A coach knows your player from the inside — that's irreplaceable. A scout looks from the outside, comparing your player against thousands of others in a structured 4-pillar framework (Technical, Tactical, Physical, Mentality). Coaches build your player day by day. ScoutMePlay tells you where they stand right now and what to focus on next.",
  },
  {
    q: "Does this guarantee a trial or contract?",
    a: "No, and we'll never claim that. ScoutMePlay is built to help players grow, not to broker contracts. Anyone promising guaranteed trials is selling you something we won't sell. Our job is to give you honest, professional feedback so you can train smarter — the rest is up to the player.",
  },
  {
    q: "Will my video be kept private?",
    a: "Yes. Your video is used only to produce your report and is never published, sold, or shared outside the scout reviewing it. You retain full ownership of your video and your report. You can request deletion of your account and data at any time from your dashboard.",
  },
  {
    q: "What's the difference between the single report and the 12-month plan?",
    a: "__PRICE_FAQ__",   // Dynamic — FAQSection fills this with live prices from /settings/price
  },
  {
    q: "Can I get reports for more than one player?",
    a: "Yes — but each player needs their own report (or plan), so the analysis stays fair and personal. If you have multiple kids in football, each upload is reviewed independently against age-appropriate benchmarks.",
  },
];

function FAQSection() {
  const [openIdx, setOpenIdx] = useState(0);
  // Load live prices so the pricing FAQ always matches whatever the admin
  // currently has set (same /settings/price endpoint PricingCards uses).
  const [price, setPrice] = useState(null);
  const [passPrice, setPassPrice] = useState(null);
  useEffect(() => {
    api.get("/settings/price")
      .then(({ data }) => { setPrice(data.price); setPassPrice(data.pass_price); })
      .catch(() => {});
  }, []);
  const priceFaqAnswer = (price && passPrice)
    ? `The $${price} is one complete report for one player. The $${passPrice} plan gives you 3 reports across 365 days for the same player — perfect if you want to track progress every few months and see how training translates into score improvements. The 12-month plan also includes a trajectory dashboard showing changes between reports.`
    : "One single report covers one player. The 12-month plan gives you 3 reports across 365 days for the same player — perfect if you want to track progress every few months and see how training translates into score improvements. The 12-month plan also includes a trajectory dashboard showing changes between reports.";
  return (
    <section
      data-testid="faq-section"
      className="section-accent-top relative py-16 md:py-20 border-t border-gray-border bg-deepnavy"
    >
      {/* Subtle scout-notebook dot pattern */}
      <div
        aria-hidden
        className="absolute inset-0 opacity-[0.04] pointer-events-none"
        style={{
          backgroundImage: "radial-gradient(circle at 1px 1px, #1F4F2F 1px, transparent 0)",
          backgroundSize: "32px 32px",
        }}
      />
      <div className="relative max-w-3xl mx-auto px-6 md:px-10">
        <div className="text-center mb-10">
          <div className="inline-flex items-center gap-2.5 mb-3">
            <span aria-hidden className="relative flex items-center justify-center w-2 h-2 shrink-0">
              <span className="absolute inset-0 rounded-full bg-volt animate-ping opacity-75" />
              <span className="relative rounded-full w-1.5 h-1.5 bg-volt" />
            </span>
            <span className="text-volt text-[10px] uppercase tracking-[0.28em] font-bold">
              Common questions
            </span>
            <span aria-hidden className="h-px w-8 bg-volt/35" />
          </div>
          <h2 className="font-barlow font-black uppercase tracking-tighter text-3xl md:text-5xl leading-[0.95]">
            Honest answers.<br />
            <span className="text-forest">No fluff.</span>
          </h2>

          {/* "answered in 30 seconds" mini header viz — small clock with sweeping arc */}
          <div className="mt-5 inline-flex items-center gap-2.5 px-3 py-1.5 border border-volt/25 bg-volt/5">
            <svg viewBox="0 0 24 24" className="w-3.5 h-3.5 text-volt shrink-0" aria-hidden>
              <circle cx="12" cy="12" r="10" fill="none" stroke="currentColor" strokeWidth="1.4" opacity="0.3" />
              <motion.circle
                cx="12" cy="12" r="10"
                fill="none" stroke="currentColor" strokeWidth="1.4"
                strokeDasharray="62.83" strokeDashoffset="62.83"
                transform="rotate(-90 12 12)" strokeLinecap="round"
                initial={{ strokeDashoffset: 62.83 }}
                whileInView={{ strokeDashoffset: 5 }}
                viewport={{ once: true }}
                transition={{ duration: 1.6, delay: 0.3, ease: "easeOut" }}
              />
              <line x1="12" y1="12" x2="12" y2="6" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
              <motion.line
                x1="12" y1="12" x2="16" y2="12"
                stroke="currentColor" strokeWidth="1.4" strokeLinecap="round"
                style={{ transformOrigin: "12px 12px" }}
                animate={{ rotate: [0, 360] }}
                transition={{ duration: 4, repeat: Infinity, ease: "linear" }}
              />
              <circle cx="12" cy="12" r="1.2" fill="currentColor" />
            </svg>
            <span className="text-[10px] uppercase tracking-[0.22em] font-bold text-volt/85">
              Answered in 30 seconds
            </span>
          </div>
        </div>

        <div className="space-y-2">
          {FAQ_ITEMS.map((item, i) => {
            const isOpen = openIdx === i;
            return (
              <div
                key={i}
                data-testid={`faq-item-${i}`}
                className={`border border-gray-border bg-surface transition-all duration-300 ${
                  isOpen ? "shadow-md" : "hover:border-forest/40"
                }`}
              >
                <button
                  type="button"
                  onClick={() => setOpenIdx(isOpen ? -1 : i)}
                  data-testid={`faq-toggle-${i}`}
                  aria-expanded={isOpen}
                  className="w-full flex items-start justify-between gap-4 text-left px-5 py-4 md:px-6 md:py-5"
                >
                  <span className="font-barlow font-black uppercase text-base md:text-lg tracking-tight leading-tight text-ink">
                    {item.q}
                  </span>
                  <span
                    aria-hidden
                    className={`shrink-0 mt-1 w-7 h-7 flex items-center justify-center rounded-full border-2 transition-all duration-300 ${
                      isOpen ? "bg-volt border-volt rotate-45" : "border-forest/40 text-forest"
                    }`}
                  >
                    <span className="text-lg leading-none font-bold">+</span>
                  </span>
                </button>
                {isOpen && (
                  <div className="px-5 pb-5 md:px-6 md:pb-6 -mt-1">
                    <p className="text-sm md:text-[15px] text-ink/70 leading-relaxed border-l-2 border-volt/40 pl-4">
                      {item.a === "__PRICE_FAQ__" ? priceFaqAnswer : item.a}
                    </p>
                  </div>
                )}
              </div>
            );
          })}
        </div>

        {/* Soft pointer to the contact form for unanswered questions */}
        <div className="mt-10 text-center">
          <p className="text-[11px] uppercase tracking-[0.22em] text-ink/50 font-bold">
            Still have questions?
          </p>
          <Link
            to="/about#contact"
            data-testid="faq-contact-link"
            className="inline-flex items-center gap-2 mt-3 text-forest hover:text-forest-pop font-barlow font-black uppercase tracking-widest text-sm transition-colors"
          >
            <Send className="w-4 h-4" />
            Send us a message
          </Link>
        </div>
      </div>
    </section>
  );
}
