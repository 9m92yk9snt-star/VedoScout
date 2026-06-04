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
  ArrowRight, Upload, Zap, ShieldCheck, FileText, Star, Brain, Target,
  Activity, Heart, Eye, Trophy, Footprints, Lock, Play, CheckCircle2,
  TrendingUp, Clock, Award, ClipboardList, Globe, Users,
  Lightbulb, Crown, Calendar, Dumbbell, Mail, Send,
} from "lucide-react";

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

const radarData = [
  { axis: "Technical", v: sample.scores.technical },
  { axis: "Tactical", v: sample.scores.tactical },
  { axis: "Physical", v: sample.scores.physical },
  { axis: "Mentality", v: sample.scores.mentality },
  { axis: "Overall", v: sample.scores.overall },
];

function AnimatedNumber({ value, duration = 1.6 }) {
  const ref = useRef(null);
  const inView = useInView(ref, { once: true, margin: "-15%" });
  const motionValue = useMotionValue(0);
  const [display, setDisplay] = useState(0);

  useEffect(() => {
    if (!inView) return;
    const controls = animate(motionValue, value, {
      duration,
      ease: [0.16, 1, 0.3, 1],
      onUpdate: (v) => setDisplay(Math.round(v)),
    });
    return controls.stop;
  }, [inView, value, motionValue, duration]);

  return <span ref={ref}>{display}</span>;
}

function ScoreBar({ label, value, locked = false, benchmark = 65 }) {
  const ref = useRef(null);
  const inView = useInView(ref, { once: true, margin: "-20%" });
  return (
    <div ref={ref} className={locked ? "opacity-70" : ""}>
      <div className="flex items-center justify-between mb-1.5">
        <span className="text-[11px] uppercase tracking-[0.18em] font-bold text-ink/70">{label}</span>
        <span className="font-barlow font-black text-volt text-base">
          {locked ? "—" : <AnimatedNumber value={value} />}<span className="text-ink/40 text-xs">/10</span>
        </span>
      </div>
      <div className="h-1 bg-cream-soft/40 overflow-hidden relative">
        <div
          className="absolute top-0 left-0 h-full bg-volt"
          style={{
            width: inView && !locked ? `${value * 10}%` : "0%",
            transition: "width 1.6s cubic-bezier(0.16, 1, 0.3, 1)",
            boxShadow: "0 0 8px rgba(204, 255, 0, 0.5)",
          }}
        />
        {/* peer benchmark line */}
        <div
          className="absolute top-0 h-full"
          style={{
            left: `${benchmark}%`,
            width: "1px",
            borderLeft: "1px dashed rgba(255,255,255,0.3)",
            height: "100%",
          }}
        />
      </div>
    </div>
  );
}

export default function Landing() {
  const [price, setPrice] = useState(1);
  const { user } = useAuth();
  const { scrollYProgress } = useScroll();

  useEffect(() => {
    api.get("/settings/price").then(({ data }) => setPrice(data.price)).catch(() => {});
  }, []);

  const startHref = user ? "/upload" : "/signup";
  const startLabel = user ? "Upload your video" : "Get started";

  return (
    <div className="min-h-screen bg-deepnavy text-ink relative overflow-hidden">
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
                <div className="inline-flex items-center gap-2 border border-volt/30 bg-volt/10 px-4 py-2">
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
                Upload your football video and get{" "}
                <span className="text-ink font-semibold">professional feedback</span>{" "}
                from experienced scouts and agents connected to clubs around the world.
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
                className="mt-8 flex flex-wrap items-center gap-x-6 gap-y-3 text-xs uppercase tracking-[0.18em] font-bold text-ink/55"
              >
                <span className="flex items-center gap-1.5"><ShieldCheck className="w-3.5 h-3.5 text-volt" /> Secure Stripe payment</span>
                <span className="flex items-center gap-1.5"><Star className="w-3.5 h-3.5 text-volt" /> ${price} USD · one-time</span>
                <span className="flex items-center gap-1.5"><FileText className="w-3.5 h-3.5 text-volt" /> Premium PDF report</span>
              </motion.div>
            </div>

            {/* ===== RIGHT: Icon-bulleted feature stack ===== */}
            <motion.div
              initial={{ opacity: 0, x: 24 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: 0.3, duration: 0.6, ease: "easeOut" }}
              className="lg:col-span-6 lg:pt-4 relative z-10"
              data-testid="hero-feature-bullets"
            >
              <div className="relative pl-8 sm:pl-10 space-y-9 md:space-y-11">
                {/* Vertical guide line (volt) */}
                <div aria-hidden className="absolute left-0 top-2 bottom-2 w-px bg-gradient-to-b from-volt/10 via-volt/40 to-volt/10" />

                {[
                  {
                    Icon: ClipboardList,
                    body: (
                      <>
                        Receive a{" "}
                        <span className="text-volt font-semibold">detailed visual report</span>{" "}
                        covering your strengths, weaknesses, playing style, and development areas.
                      </>
                    ),
                  },
                  {
                    Icon: Globe,
                    body: (
                      <>
                        Exceptional talents may receive{" "}
                        <span className="text-volt font-semibold">scout attention</span>, trial recommendations, and guidance on the next step in their football journey.
                      </>
                    ),
                  },
                  {
                    Icon: Users,
                    body: (
                      <>
                        Our network of scouts and agents can provide{" "}
                        <span className="text-volt font-semibold">guidance</span>, answer questions, and help you explore future opportunities.
                      </>
                    ),
                  },
                ].map(({ Icon, body }, i) => (
                  <div key={i} className="relative flex items-start gap-5">
                    {/* Icon disk */}
                    <div className="absolute -left-8 sm:-left-10 top-0 w-12 h-12 sm:w-14 sm:h-14 -translate-x-1/2 flex items-center justify-center bg-deepnavy border border-volt/40 shrink-0">
                      <Icon className="w-5 h-5 sm:w-6 sm:h-6 text-volt" strokeWidth={1.5} />
                    </div>
                    <p className="text-sm md:text-base text-ink/75 leading-relaxed pt-2.5 sm:pt-3.5">
                      {body}
                    </p>
                  </div>
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

      {/* ============ HOW IT WORKS — 3 steps card (clean section after hero) ============ */}
      <section
        data-testid="how-it-works"
        className="relative py-16 md:py-20 border-t border-gray-border bg-deepnavy"
      >
        <div className="max-w-3xl mx-auto px-6 md:px-10">
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, amount: 0.3 }}
            transition={{ duration: 0.6, ease: "easeOut" }}
            className="card-premium border border-gray-border bg-surface/85 backdrop-blur-xl p-6 md:p-10"
          >
            <div className="flex items-center justify-between mb-7">
              <span className="text-volt text-xs uppercase tracking-[0.25em] font-bold">How it works · 3 steps</span>
              <span className="text-ink/50 text-xs uppercase tracking-widest font-bold">~ 2 min</span>
            </div>

            <ol className="space-y-5 md:space-y-6">
              {[
                { n: "01", t: "Sign up", d: "Free account. No card required to start." },
                { n: "02", t: "Upload video & details", d: "Highlight, match or training clip." },
                { n: "03", t: "Get instant free preview", d: `Unlock full report for $${price} USD.` },
              ].map((s, i) => (
                <li key={i} className="flex gap-4 md:gap-5 items-start">
                  <span className="font-barlow font-black text-3xl md:text-4xl text-volt/40 leading-none w-10 md:w-12 flex-shrink-0">{s.n}</span>
                  <div>
                    <div className="font-barlow font-black uppercase text-ink text-lg md:text-xl leading-tight">{s.t}</div>
                    <div className="text-xs md:text-sm text-ink/65 mt-1">{s.d}</div>
                  </div>
                </li>
              ))}
            </ol>

            <Link
              to={startHref}
              data-testid="card-cta"
              className="mt-8 md:mt-10 w-full bg-volt hover:bg-forest-pop text-white font-barlow font-black uppercase tracking-widest text-sm py-3.5 flex items-center justify-center gap-2 transition-colors"
            >
              Start free preview
              <ArrowRight className="w-4 h-4" />
            </Link>

            <div className="mt-6 pt-6 border-t border-gray-border grid grid-cols-3 gap-2">
              {[
                { i: Brain, l: "Report" },
                { i: Target, l: "Scout View" },
                { i: FileText, l: "PDF" },
              ].map(({ i: Icon, l }, idx) => (
                <div key={idx} className="flex flex-col items-center gap-1.5 text-center">
                  <Icon className="w-4 h-4 text-volt" strokeWidth={1.5} />
                  <span className="text-[10px] uppercase tracking-widest font-bold text-ink/65">{l}</span>
                </div>
              ))}
            </div>

            <a
              href="#what-you-get"
              className="mt-7 flex items-center justify-center gap-2 text-[11px] uppercase tracking-[0.25em] font-bold text-ink/50 hover:text-volt transition-colors"
            >
              See an example report below
              <span className="w-8 h-px bg-current" />
            </a>
          </motion.div>
        </div>
      </section>

      {/* ============ WHAT YOU RECEIVE — rich feature cards ============ */}
      <section id="what-you-get" data-testid="what-you-get" className="section-accent-top relative py-24 md:py-32 border-t border-gray-border overflow-hidden">
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
          <div className="mb-12 md:mb-16">
            <div className="flex items-center gap-4 mb-6">
              <span className="text-volt text-xs uppercase tracking-[0.25em] font-bold whitespace-nowrap">Inside your report</span>
              <span aria-hidden className="flex-1 h-px bg-gradient-to-r from-volt/60 via-volt/20 to-transparent max-w-[260px]" />
            </div>

            <div className="grid lg:grid-cols-12 gap-8 items-end">
              <div className="lg:col-span-8">
                <h2
                  data-testid="report-section-title"
                  className="font-barlow font-black uppercase text-4xl sm:text-5xl md:text-6xl lg:text-7xl tracking-tighter leading-[0.95]"
                >
                  What does a real scout see{" "}
                  <br className="hidden md:block" />
                  that{" "}
                  <span className="font-serif-italic normal-case font-normal lowercase tracking-normal text-volt">you</span>{" "}
                  don't?
                </h2>
                <p className="mt-6 text-ink/70 text-base md:text-lg max-w-xl leading-relaxed">
                  Professional analysis. Honest insights. Built to help you grow.
                </p>
              </div>

              {/* Decorative jersey badge — visually echoes the reference */}
              <div className="hidden lg:flex lg:col-span-4 justify-end">
                <div className="relative w-full max-w-[260px] aspect-[3/4]">
                  <div className="absolute inset-0 border border-volt/30 bg-cream-card/90 backdrop-blur-sm">
                    {/* corner brackets */}
                    <span className="absolute top-0 left-0 w-5 h-5 border-t-2 border-l-2 border-volt" />
                    <span className="absolute top-0 right-0 w-5 h-5 border-t-2 border-r-2 border-volt" />
                    <span className="absolute bottom-0 left-0 w-5 h-5 border-b-2 border-l-2 border-volt" />
                    <span className="absolute bottom-0 right-0 w-5 h-5 border-b-2 border-r-2 border-volt" />

                    <div className="absolute inset-0 flex flex-col items-center justify-center text-center px-4">
                      <span className="text-[10px] uppercase tracking-[0.25em] font-bold text-volt/80 mb-2">Your name</span>
                      <span
                        className="font-barlow font-black text-volt leading-none"
                        style={{ fontSize: "7rem", textShadow: "0 6px 30px rgba(204,255,0,0.35)" }}
                      >
                        10
                      </span>
                      <span className="mt-3 text-[10px] uppercase tracking-[0.2em] font-bold text-ink/55">
                        Built for the next level
                      </span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* ===== Cards grid 3 cols ===== */}
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4 md:gap-5">
            {reportCards.map((card, i) => (
              <motion.div
                key={i}
                initial={{ opacity: 0, y: 18 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true, amount: 0.2 }}
                transition={{ duration: 0.5, delay: (i % 3) * 0.08, ease: "easeOut" }}
                data-testid={`feature-card-${i}`}
                className="relative bg-surface/80 backdrop-blur-sm border border-gray-border hover:border-volt/40 p-6 md:p-7 flex flex-col group transition-colors"
              >
                {/* Number — top right */}
                <span className="absolute top-5 right-6 font-barlow font-black text-xs text-ink/35 tracking-widest">
                  {String(i + 1).padStart(2, "0")}
                </span>

                {/* Icon */}
                <card.icon className="w-8 h-8 md:w-9 md:h-9 text-volt mb-6 group-hover:scale-105 transition-transform" strokeWidth={1.5} />

                {/* Title */}
                <h3 className="font-barlow font-black uppercase text-xl md:text-2xl text-ink mb-3 leading-tight tracking-tight">
                  {card.title}
                </h3>

                {/* Description */}
                <p className="text-sm text-ink/70 leading-relaxed mb-6 flex-1">
                  {card.text}
                </p>

                {/* Visualization at bottom */}
                <div className="mt-auto pt-5 border-t border-gray-border">
                  <CardViz viz={card.viz} />
                </div>
              </motion.div>
            ))}

            {/* ===== Special highlight card — 12 ===== */}
            <motion.div
              initial={{ opacity: 0, y: 18 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, amount: 0.2 }}
              transition={{ duration: 0.6, delay: 0.18, ease: "easeOut" }}
              data-testid="feature-card-highlight"
              className="relative bg-gradient-to-br from-volt/10 via-deepnavy/40 to-deepnavy/40 border-2 border-volt p-6 md:p-7 flex flex-col"
              style={{ boxShadow: "0 0 60px rgba(204,255,0,0.12)" }}
            >
              <span className="absolute top-5 right-6 font-barlow font-black text-xs text-volt/40 tracking-widest">12</span>

              <Crown className="w-9 h-9 md:w-10 md:h-10 text-volt mb-6" strokeWidth={1.5} fill="#ccff00" fillOpacity="0.18" />

              <h3 className="font-barlow font-black uppercase text-xl md:text-2xl text-ink mb-2 leading-tight tracking-tight">
                100% Personal.<br />
                100% Game Changing.
              </h3>

              <p className="text-sm text-ink/80 leading-relaxed mt-3">
                This is more than a report.{" "}
                <span className="text-volt font-serif-italic italic">It's your advantage.</span>
              </p>

              <div className="mt-auto pt-5 border-t border-volt/20">
                <Link
                  to={startHref}
                  data-testid="report-section-cta"
                  className="inline-flex items-center gap-2 font-barlow font-black uppercase text-xs tracking-[0.22em] text-volt hover:text-ink transition-colors"
                >
                  Unlock your report
                  <ArrowRight className="w-3.5 h-3.5" />
                </Link>
              </div>
            </motion.div>
          </div>

          {/* ===== Bottom trust bar ===== */}
          <div
            data-testid="report-trust-bar"
            className="mt-12 md:mt-16 border border-gray-border bg-surface/40 backdrop-blur-sm divide-y md:divide-y-0 md:divide-x divide-white/10 grid md:grid-cols-3"
          >
            {[
              { Icon: Clock, t: "5–10 Minutes", s: "To complete" },
              { Icon: Zap, t: "Instant access", s: "To your free preview" },
              { Icon: ShieldCheck, t: "Real scouts", s: "Real reports" },
            ].map(({ Icon, t, s }, i) => (
              <div key={i} className="flex items-center gap-3 px-6 py-5">
                <Icon className="w-5 h-5 text-volt shrink-0" strokeWidth={1.8} />
                <div className="flex flex-col leading-tight">
                  <span className="font-barlow font-black uppercase text-ink text-sm tracking-wider">{t}</span>
                  <span className="text-ink/60 text-[11px] uppercase tracking-[0.18em] font-bold mt-0.5">{s}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ============ SAMPLE REPORT — RICH, COMPELLING, WOW ============ */}
      <section
        data-testid="example-report"
        className="section-accent-top relative py-24 md:py-32 border-t border-gray-border overflow-hidden"
      >
        {/* Soft background */}
        <div className="absolute inset-0 z-0 pointer-events-none">
          <div className="absolute -top-32 -left-32 w-96 h-96 bg-volt/10 rounded-full blur-3xl" />
          <div className="absolute -bottom-32 -right-32 w-96 h-96 bg-volt/5 rounded-full blur-3xl" />
        </div>

        <div className="relative z-10 max-w-7xl mx-auto px-6 md:px-10">
          <div className="mb-12 relative flex flex-col md:flex-row md:items-end md:justify-between gap-6">
            <span aria-hidden className="section-num-bg">02</span>
            <div className="max-w-3xl relative">
              <span className="text-volt text-xs uppercase tracking-[0.25em] font-bold">A real example</span>
              <h2 className="mt-4 font-barlow font-black uppercase text-4xl md:text-6xl tracking-tighter leading-[0.95]">
                This is what you get.
              </h2>
              <p className="mt-4 text-ink/70 max-w-2xl">
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

              {/* Top stripe with badge + free tag */}
              <div className="relative flex items-center justify-between px-5 py-3 border-b border-gray-border bg-cream-card/90">
                <span className="text-volt text-[10px] uppercase tracking-[0.25em] font-bold flex items-center gap-1.5">
                  <span className="w-1.5 h-1.5 bg-volt rounded-full animate-pulse" /> Free Preview
                </span>
                <span className="text-ink/50 text-[10px] uppercase tracking-[0.2em] font-bold">{sample.player.videoType}</span>
              </div>

              <div className="relative px-5 md:px-7 py-6 md:py-7">
                {/* Big jersey number + name */}
                <div className="flex items-start gap-5">
                  <div className="flex-shrink-0">
                    <div className="text-[11px] uppercase tracking-[0.18em] font-bold text-volt/70 mb-1">No.</div>
                    <div className="font-barlow font-black text-volt leading-none" style={{ fontSize: "5.5rem", textShadow: "0 4px 24px rgba(204,255,0,0.3)" }}>
                      {sample.player.number}
                    </div>
                  </div>
                  <div className="flex-1 min-w-0 pt-2">
                    <div className="text-[10px] uppercase tracking-[0.22em] font-bold text-ink/50 mb-1">Player</div>
                    <h3 className="font-barlow font-black uppercase text-3xl md:text-4xl tracking-tighter leading-[0.9] text-ink">
                      {sample.player.name}
                    </h3>
                    <div className="mt-2 inline-flex items-center gap-2 bg-volt/10 border border-volt/30 px-2.5 py-1">
                      <span className="font-barlow font-black uppercase text-volt text-sm leading-none">{sample.player.positionShort}</span>
                      <span className="text-ink/65 text-[11px]">·</span>
                      <span className="text-ink/80 text-xs">{sample.player.position}</span>
                    </div>
                  </div>
                </div>

                {/* Meta row */}
                <div className="mt-6 grid grid-cols-3 gap-px bg-cream-soft/20 border border-gray-border">
                  <div className="bg-cream-card/90 p-3">
                    <div className="text-[9px] uppercase tracking-widest text-ink/50 font-bold">Age</div>
                    <div className="font-barlow font-black text-ink text-2xl leading-none mt-1">{sample.player.age}</div>
                  </div>
                  <div className="bg-cream-card/90 p-3">
                    <div className="text-[9px] uppercase tracking-widest text-ink/50 font-bold">Foot</div>
                    <div className="font-barlow font-black text-ink text-lg leading-none mt-1.5">{sample.player.foot}</div>
                  </div>
                  <div className="bg-cream-card/90 p-3">
                    <div className="text-[9px] uppercase tracking-widest text-ink/50 font-bold">Team</div>
                    <div className="font-barlow font-black text-ink text-sm leading-none mt-1.5 truncate">{sample.player.club}</div>
                  </div>
                </div>

                {/* Style tag */}
                <div className="mt-4 flex items-center gap-2 text-xs text-ink/70">
                  <Star className="w-3.5 h-3.5 text-volt flex-shrink-0" fill="currentColor" />
                  <span className="font-bold">{sample.player.type}</span>
                </div>

                {/* Score row */}
                <div className="mt-5 grid grid-cols-4 gap-px bg-cream-soft/40 border border-volt/20">
                  {[
                    { k: "TECH", v: sample.scores.technical },
                    { k: "TACT", v: sample.scores.tactical },
                    { k: "PHYS", v: sample.scores.physical },
                    { k: "MENT", v: sample.scores.mentality },
                  ].map((s, i) => (
                    <div key={i} className="bg-cream-card py-3 text-center">
                      <div className="text-[9px] uppercase tracking-widest text-ink/50 font-bold">{s.k}</div>
                      <div className="font-barlow font-black text-3xl text-volt mt-0.5 leading-none">{s.v}</div>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            {/* Brief summary card */}
            <div className="bg-surface p-6 md:p-8 lg:col-span-3">
              <div className="flex items-center justify-between mb-4">
                <span className="text-volt text-[11px] uppercase tracking-[0.25em] font-bold">What our scouts saw</span>
                <span className="text-ink/40 text-[10px] uppercase tracking-widest font-bold">Free preview</span>
              </div>
              <p className="text-ink text-base md:text-[17px] leading-[1.65]">{sample.summary}</p>

              <div className="mt-7 grid sm:grid-cols-2 gap-6 pt-6 border-t border-gray-border">
                <div>
                  <div className="text-xs uppercase tracking-[0.2em] font-bold text-ink/50 mb-3">What he does well</div>
                  <ul className="space-y-2.5">
                    {sample.strengths.map((s, i) => (
                      <li key={i} className="flex items-start gap-2.5 text-sm text-ink leading-snug">
                        <CheckCircle2 className="w-4 h-4 text-volt mt-0.5 flex-shrink-0" />
                        <span>{s}</span>
                      </li>
                    ))}
                  </ul>
                </div>
                <div>
                  <div className="text-xs uppercase tracking-[0.2em] font-bold text-ink/50 mb-3">What to work on</div>
                  <p className="text-sm text-ink/85 leading-relaxed">{sample.improvement}</p>
                </div>
              </div>
            </div>
          </div>

          {/* === PREMIUM SECTIONS — blurred but visually rich === */}
          <div className="relative">
            {/* The actual content (blurred) */}
            <div className="blur-locked grid lg:grid-cols-3 gap-px bg-cream-soft/40 border border-gray-border">
              {/* Radar chart card */}
              <div className="bg-surface p-6 md:p-8">
                <span className="text-volt text-[11px] uppercase tracking-[0.25em] font-bold">Premium · Performance Radar</span>
                <h3 className="mt-3 font-barlow font-black uppercase text-2xl">Performance map</h3>
                <div className="mt-4 h-56">
                  <ResponsiveContainer width="100%" height="100%">
                    <RadarChart data={radarData}>
                      <PolarGrid stroke="rgba(255,255,255,0.15)" />
                      <PolarAngleAxis dataKey="axis" tick={{ fill: "#94A3B8", fontSize: 10 }} />
                      <PolarRadiusAxis domain={[0, 10]} tick={false} axisLine={false} />
                      <Radar dataKey="v" stroke="#CCFF00" fill="#CCFF00" fillOpacity={0.4} />
                    </RadarChart>
                  </ResponsiveContainer>
                </div>
              </div>

              {/* Technical scores card */}
              <div className="bg-surface p-6 md:p-8">
                <span className="text-volt text-[11px] uppercase tracking-[0.25em] font-bold">Premium · Technical</span>
                <h3 className="mt-3 font-barlow font-black uppercase text-2xl">Technical analysis</h3>
                <div className="mt-5 space-y-3">
                  {sample.technical.slice(0, 5).map((t, i) => (
                    <ScoreBar key={i} label={t.k} value={t.v} />
                  ))}
                </div>
              </div>

              {/* Tactical scores card */}
              <div className="bg-surface p-6 md:p-8">
                <span className="text-volt text-[11px] uppercase tracking-[0.25em] font-bold">Premium · Tactical</span>
                <h3 className="mt-3 font-barlow font-black uppercase text-2xl">Tactical analysis</h3>
                <div className="mt-5 space-y-3">
                  {sample.tactical.slice(0, 5).map((t, i) => (
                    <ScoreBar key={i} label={t.k} value={t.v} />
                  ))}
                </div>
              </div>

              {/* Scout view */}
              <div className="bg-surface p-6 md:p-8 lg:col-span-2">
                <span className="text-volt text-[11px] uppercase tracking-[0.25em] font-bold">Premium · Scout View</span>
                <h3 className="mt-3 font-barlow font-black uppercase text-2xl">How a scout would see this player</h3>
                <div className="mt-5 grid sm:grid-cols-2 gap-6">
                  <div>
                    <div className="text-xs uppercase tracking-[0.2em] font-bold text-volt mb-2">What he'd love</div>
                    <ul className="space-y-2 text-sm text-ink/85">
                      {sample.scoutStrengths.map((s, i) => (
                        <li key={i} className="flex gap-2"><span className="text-volt mt-1">▶</span>{s}</li>
                      ))}
                    </ul>
                  </div>
                  <div>
                    <div className="text-xs uppercase tracking-[0.2em] font-bold text-yellow-400 mb-2">What he'd worry about</div>
                    <ul className="space-y-2 text-sm text-ink/85">
                      {sample.scoutConcerns.map((s, i) => (
                        <li key={i} className="flex gap-2"><span className="text-yellow-400 mt-1">▶</span>{s}</li>
                      ))}
                    </ul>
                  </div>
                </div>
                <div className="mt-6 pt-6 border-t border-gray-border grid sm:grid-cols-2 gap-4">
                  <div>
                    <div className="text-[10px] uppercase tracking-[0.18em] font-bold text-ink/50 mb-1">Next level to aim for</div>
                    <div className="text-sm text-ink">{sample.nextLevel}</div>
                  </div>
                  <div>
                    <div className="text-[10px] uppercase tracking-[0.18em] font-bold text-ink/50 mb-1">Best position</div>
                    <div className="text-sm text-ink">{sample.bestPosition}</div>
                  </div>
                </div>
              </div>

              {/* Training exercise card */}
              <div className="bg-surface p-6 md:p-8">
                <span className="text-volt text-[11px] uppercase tracking-[0.25em] font-bold">Premium · Training Plan</span>
                <h3 className="mt-3 font-barlow font-black uppercase text-2xl">Drill of the week</h3>
                <div className="mt-5 border border-volt/30 bg-deepnavy p-4">
                  <div className="flex items-center justify-between mb-2">
                    <span className="font-barlow font-black uppercase text-ink text-base">{sample.exercise.name}</span>
                    <span className="flex items-center gap-1 text-xs text-volt font-bold"><Clock className="w-3 h-3" />{sample.exercise.duration}</span>
                  </div>
                  <p className="text-xs text-ink/70 leading-relaxed">{sample.exercise.desc}</p>
                </div>
                <div className="mt-4 flex items-center justify-between text-[10px] uppercase tracking-widest font-bold text-ink/50">
                  <span className="flex items-center gap-1"><Award className="w-3 h-3 text-volt" />4 more drills</span>
                  <span className="flex items-center gap-1"><TrendingUp className="w-3 h-3 text-volt" />30 & 90-day plan</span>
                </div>
              </div>

              {/* Video timeline */}
              <div className="bg-surface p-6 md:p-8 lg:col-span-3">
                <span className="text-volt text-[11px] uppercase tracking-[0.25em] font-bold">Premium · Video Comments</span>
                <h3 className="mt-3 font-barlow font-black uppercase text-2xl">Timestamped feedback</h3>
                <div className="mt-5 space-y-2">
                  {sample.timeline.map((c, i) => (
                    <div key={i} className="flex items-start gap-4 bg-cream-card/90 border border-gray-border px-4 py-3">
                      <div className="flex items-center gap-2 flex-shrink-0">
                        <Play className="w-3 h-3 text-volt" fill="currentColor" />
                        <span className="font-barlow font-black text-volt text-base min-w-[44px]">{c.t}</span>
                      </div>
                      <p className="text-sm text-ink/85">{c.c}</p>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            {/* The premium CTA overlay */}
            <div className="absolute inset-0 z-10 pointer-events-none flex items-center justify-center">
              <motion.div
                initial={{ opacity: 0, scale: 0.95 }}
                whileInView={{ opacity: 1, scale: 1 }}
                viewport={{ once: true, margin: "-100px" }}
                transition={{ duration: 0.5 }}
                className="pointer-events-auto border border-volt/30 bg-cream-card backdrop-blur-2xl p-8 md:p-10 max-w-md mx-6 text-center shadow-2xl"
                style={{ boxShadow: "0 20px 80px rgba(204,255,0,0.15)" }}
              >
                <div className="inline-flex items-center justify-center w-14 h-14 bg-volt/10 border border-volt/30 mb-5">
                  <Lock className="w-6 h-6 text-volt" strokeWidth={1.5} />
                </div>
                <span className="text-volt text-[11px] uppercase tracking-[0.3em] font-bold">Premium</span>
                <h3 className="mt-3 font-barlow font-black uppercase text-3xl md:text-4xl tracking-tighter leading-[0.95]">
                  Unlock the<br />full report
                </h3>
                <p className="mt-4 text-sm text-ink/70 leading-relaxed">
                  Full performance map · all 4 score categories · scout view · 5 personal drills · 30 & 90-day plan · timestamped video comments · premium PDF.
                </p>

                <div className="mt-6 flex items-baseline justify-center gap-2">
                  <span className="font-barlow font-black text-5xl md:text-6xl text-volt leading-none">${price}</span>
                  <span className="text-ink/65 uppercase tracking-widest font-bold text-sm">USD</span>
                </div>
                <p className="text-[10px] text-ink/50 uppercase tracking-widest font-bold mt-1">one-time · no subscription</p>

                <Link
                  to={startHref}
                  data-testid="sample-unlock-cta"
                  className="mt-6 w-full bg-volt hover:bg-forest-pop text-white font-barlow font-black uppercase tracking-widest text-sm py-3.5 flex items-center justify-center gap-2 transition-colors"
                >
                  {startLabel}
                  <ArrowRight className="w-4 h-4" />
                </Link>
                <p className="mt-3 text-[10px] text-ink/50 flex items-center justify-center gap-1.5">
                  <ShieldCheck className="w-3 h-3" /> Free preview · No card to start
                </p>
              </motion.div>
            </div>
          </div>
        </div>
      </section>

      {/* ============ TRUST ============ */}
      <section id="trust" data-testid="trust-section" className="section-accent-top relative py-20 border-t border-gray-border">
        <div className="max-w-7xl mx-auto px-6 md:px-10">
          <div className="border border-gray-border bg-surface p-8 md:p-12 flex flex-col md:flex-row gap-6 md:items-center">
            <ShieldCheck className="w-12 h-12 text-volt flex-shrink-0" strokeWidth={1.5} />
            <div>
              <h3 className="font-barlow font-black uppercase text-2xl md:text-3xl">Honest scouting feedback. Built for growth.</h3>
              <p className="mt-3 text-sm text-ink/70 leading-relaxed max-w-3xl">
                ScoutMePlay gives you honest, professional football feedback to help young players get better.
                It does <strong className="text-ink">not</strong> promise trials, contracts, or academy spots.
                Your scores are here to guide your training — not to decide your future.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* ============ FINAL CTA ============ */}
      <section data-testid="final-cta" className="section-accent-top relative py-24 md:py-32 border-t border-gray-border overflow-hidden">
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
            Your move.
            <span className="block text-volt mt-2">Show the world what you've got.</span>
          </h2>
          <p className="mt-6 text-ink/65 max-w-2xl mx-auto">
            Upload a video, mark yourself, and you'll get an instant free preview from our scouts. No card needed to start.
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
          </div>
        </div>
      </section>

      <footer className="border-t border-gray-border mt-10">
        <div className="max-w-7xl mx-auto px-6 md:px-10 py-12">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-8 md:gap-10">
            {/* Brand */}
            <div className="col-span-2">
              <div className="flex items-center gap-3">
                <div className="w-9 h-9 bg-volt flex items-center justify-center">
                  <span className="text-ink font-barlow font-black text-base leading-none">S</span>
                </div>
                <div>
                  <div className="font-barlow font-black uppercase tracking-tight text-base leading-none">ScoutMePlay</div>
                  <div className="text-[10px] uppercase tracking-[0.22em] font-bold text-ink/50 mt-1">by Mentalkids</div>
                </div>
              </div>
              <p className="mt-4 text-sm text-ink/60 leading-relaxed max-w-xs">
                ScoutMePlay combines advanced scouting technology with human review to deliver
                honest player feedback. Where talent gets noticed.
              </p>
            </div>

            {/* About column */}
            <div>
              <div className="text-[10px] uppercase tracking-[0.25em] font-bold text-volt">About</div>
              <ul className="mt-4 space-y-2.5 text-sm">
                <li>
                  <Link
                    to="/about"
                    data-testid="footer-link-about"
                    className="text-ink/70 hover:text-volt transition-colors"
                  >
                    About ScoutMePlay
                  </Link>
                </li>
                <li>
                  <Link
                    to="/about#what-we-do"
                    className="text-ink/70 hover:text-volt transition-colors"
                  >
                    How it works
                  </Link>
                </li>
                <li>
                  <span className="text-ink/50 cursor-default">Mentalkids · Denmark</span>
                </li>
              </ul>
            </div>

            {/* Contact + Privacy column */}
            <div>
              <div className="text-[10px] uppercase tracking-[0.25em] font-bold text-volt">Contact</div>
              <ul className="mt-4 space-y-2.5 text-sm">
                <li>
                  <Link
                    to="/about#contact"
                    data-testid="footer-link-contact-form"
                    className="inline-flex items-center gap-1.5 text-ink/70 hover:text-volt transition-colors"
                  >
                    <Send className="w-3.5 h-3.5 shrink-0" />
                    Send us a message
                  </Link>
                </li>
                <li>
                  <a
                    href="mailto:scoutmeplay@gmail.com"
                    data-testid="footer-link-email"
                    className="inline-flex items-center gap-1.5 text-ink/70 hover:text-volt transition-colors break-all"
                  >
                    <Mail className="w-3.5 h-3.5 shrink-0" />
                    scoutmeplay@gmail.com
                  </a>
                </li>
              </ul>

              <div className="text-[10px] uppercase tracking-[0.25em] font-bold text-volt mt-6">Legal</div>
              <ul className="mt-4 space-y-2.5 text-sm">
                <li>
                  <Link
                    to="/privacy"
                    data-testid="footer-link-privacy"
                    className="text-ink/70 hover:text-volt transition-colors"
                  >
                    Privacy Policy
                  </Link>
                </li>
              </ul>
            </div>
          </div>

          <div className="mt-10 pt-6 border-t border-gray-border flex flex-col md:flex-row justify-between gap-3 items-center">
            <p className="text-[10px] uppercase tracking-[0.22em] font-bold text-ink/50">
              © {new Date().getFullYear()} Mentalkids · ScoutMePlay
            </p>
            <p className="text-[10px] uppercase tracking-[0.22em] font-bold text-ink/50">
              Where talent gets noticed · Football scouting service
            </p>
          </div>
        </div>
      </footer>
    </div>
  );
}
