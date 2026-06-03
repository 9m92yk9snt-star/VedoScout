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
} from "lucide-react";

const fadeUp = {
  hidden: { opacity: 0, y: 18 },
  visible: (i = 0) => ({ opacity: 1, y: 0, transition: { delay: i * 0.06, duration: 0.5, ease: "easeOut" } }),
};

/* ===== Feature cards — natural football language ===== */
const featureCards = [
  {
    icon: Brain,
    title: "Player Report",
    text: "A full written breakdown of how you play, your strengths, and what makes you unique on the pitch.",
    preview: "\"Lukas plays like a smart playmaker. He sees passes before others, and his left foot is dangerous.\"",
  },
  {
    icon: Footprints,
    title: "Technical",
    text: "First touch · ball control · dribbling · passing · shooting · weak foot · 1v1 battles.",
    preview: "Score from 1–10 for every skill, with a tip on how to improve each one.",
  },
  {
    icon: Target,
    title: "Tactical",
    text: "Where you stand · how you move without the ball · how you read the game.",
    preview: "We tell you when your positioning is great and when you need to think faster.",
  },
  {
    icon: Activity,
    title: "Physical",
    text: "Speed · acceleration · balance · agility · stamina · body control.",
    preview: "How your body holds up across a full match — and what fitness work will help most.",
  },
  {
    icon: Heart,
    title: "Mentality",
    text: "Confidence · work rate · bravery in duels · focus · how you react to mistakes.",
    preview: "We look at how you compete when the score is against your team.",
  },
  {
    icon: Eye,
    title: "Scout View",
    text: "How a real scout would look at you — what they'd love, what they'd worry about, and what level fits you next.",
    preview: "Strengths · areas to work on · best position · next competitive level to target.",
  },
  {
    icon: Trophy,
    title: "Training Plan",
    text: "5 specific exercises just for you · a weekly focus · a 30-day plan · a 90-day plan.",
    preview: "Real drills you can do at training or at home — not generic gym work.",
  },
  {
    icon: FileText,
    title: "Premium PDF",
    text: "A clean, professional PDF you can share with your coach, your parents, or academies.",
    preview: "Designed to look like a real scout dossier — print-ready.",
  },
];

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
        <span className="text-[11px] uppercase tracking-[0.18em] font-bold text-white/70">{label}</span>
        <span className="font-barlow font-black text-volt text-base">
          {locked ? "—" : <AnimatedNumber value={value} />}<span className="text-white/30 text-xs">/10</span>
        </span>
      </div>
      <div className="h-1 bg-white/10 overflow-hidden relative">
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
  const [price, setPrice] = useState(399);
  const { user } = useAuth();
  const { scrollYProgress } = useScroll();

  useEffect(() => {
    api.get("/settings/price").then(({ data }) => setPrice(data.price_dkk)).catch(() => {});
  }, []);

  const startHref = user ? "/upload" : "/signup";
  const startLabel = user ? "Upload your video" : "Get started";

  return (
    <div className="min-h-screen bg-deepnavy text-white relative overflow-hidden">
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
                className="mt-7 max-w-xl text-base md:text-lg text-white/80 leading-relaxed"
              >
                Upload your football video and get{" "}
                <span className="text-white font-semibold">professional feedback</span>{" "}
                from experienced scouts and agents connected to clubs around the world.
              </motion.p>

              <motion.div
                initial="hidden" animate="visible" variants={fadeUp} custom={3}
                className="mt-8 flex flex-col sm:flex-row gap-3 sm:gap-4 max-w-xl"
              >
                <Link
                  to={startHref}
                  data-testid="hero-cta-upload"
                  className="group flex-1 bg-volt hover:bg-white text-deepnavy font-barlow font-black uppercase tracking-widest text-base px-6 py-4 flex items-center justify-center gap-3 transition-colors animate-pulse-glow"
                >
                  <Upload className="w-5 h-5" />
                  {startLabel}
                  <ArrowRight className="w-5 h-5 group-hover:translate-x-1 transition-transform" />
                </Link>
                {!user && (
                  <Link
                    to="/login"
                    data-testid="hero-cta-login"
                    className="flex-1 border border-white/20 hover:border-volt hover:text-volt text-white font-barlow font-black uppercase tracking-widest text-base px-6 py-4 flex items-center justify-center gap-2 transition-colors"
                  >
                    Sign in
                  </Link>
                )}
              </motion.div>

              <motion.div
                initial="hidden" animate="visible" variants={fadeUp} custom={4}
                className="mt-8 flex flex-wrap items-center gap-x-6 gap-y-3 text-xs uppercase tracking-[0.18em] font-bold text-white/50"
              >
                <span className="flex items-center gap-1.5"><ShieldCheck className="w-3.5 h-3.5 text-volt" /> Secure Stripe payment</span>
                <span className="flex items-center gap-1.5"><Star className="w-3.5 h-3.5 text-volt" /> {price} DKK · one-time</span>
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
                    <p className="text-sm md:text-base text-white/75 leading-relaxed pt-2.5 sm:pt-3.5">
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
              {/* Inline soccer-boot SVG */}
              <svg viewBox="0 0 44 32" className="w-9 h-7 md:w-11 md:h-8 shrink-0" aria-hidden="true">
                {/* Upper body of boot */}
                <path
                  d="M3 22 Q3 12 11 9 L26 6 Q38 6 40 14 Q41 18 40 22 L3 22 Z"
                  fill="#ccff00"
                />
                {/* Sole */}
                <path
                  d="M3 22 L40 22 L38 26 L5 26 Z"
                  fill="#ccff00"
                />
                {/* Heel cup highlight */}
                <path d="M3 22 Q3 16 7 14 L7 22 Z" fill="#a8d000" />
                {/* Lace lines */}
                <line x1="18" y1="10.5" x2="32" y2="10.5" stroke="#0d111a" strokeWidth="1.2" strokeLinecap="round" />
                <line x1="18" y1="14" x2="32" y2="14" stroke="#0d111a" strokeWidth="1.2" strokeLinecap="round" />
                <line x1="18" y1="17.5" x2="32" y2="17.5" stroke="#0d111a" strokeWidth="1.2" strokeLinecap="round" />
                {/* Studs */}
                <circle cx="9" cy="29" r="1.3" fill="#ccff00" />
                <circle cx="18" cy="29" r="1.3" fill="#ccff00" />
                <circle cx="27" cy="29" r="1.3" fill="#ccff00" />
                <circle cx="35" cy="29" r="1.3" fill="#ccff00" />
              </svg>
              <p className="font-serif-italic italic text-xl md:text-2xl text-white/95 leading-snug text-center">
                See your game through the eyes of{" "}
                <span className="text-volt">professionals.</span>
              </p>
            </div>

            <div className="mt-7 md:mt-9 flex items-center gap-4 md:gap-6 max-w-3xl mx-auto">
              <div className="flex-1 h-px bg-gradient-to-r from-transparent via-volt/40 to-volt/40" />
              <p className="font-barlow font-black uppercase tracking-[0.22em] text-xs md:text-sm whitespace-nowrap">
                <span className="text-volt">Know your potential.</span>{" "}
                <span className="text-white">Unlock your future.</span>
              </p>
              <div className="flex-1 h-px bg-gradient-to-l from-transparent via-volt/40 to-volt/40" />
            </div>
          </motion.div>
        </div>
      </section>

      {/* ============ HOW IT WORKS — 3 steps card (clean section after hero) ============ */}
      <section
        data-testid="how-it-works"
        className="relative py-16 md:py-20 border-t border-white/10 bg-deepnavy"
      >
        <div className="max-w-3xl mx-auto px-6 md:px-10">
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, amount: 0.3 }}
            transition={{ duration: 0.6, ease: "easeOut" }}
            className="card-premium border border-white/10 bg-surface/85 backdrop-blur-xl p-6 md:p-10"
          >
            <div className="flex items-center justify-between mb-7">
              <span className="text-volt text-xs uppercase tracking-[0.25em] font-bold">How it works · 3 steps</span>
              <span className="text-white/40 text-xs uppercase tracking-widest font-bold">~ 2 min</span>
            </div>

            <ol className="space-y-5 md:space-y-6">
              {[
                { n: "01", t: "Sign up", d: "Free account. No card required to start." },
                { n: "02", t: "Upload video & details", d: "Highlight, match or training clip." },
                { n: "03", t: "Get instant free preview", d: `Unlock full report for ${price} DKK.` },
              ].map((s, i) => (
                <li key={i} className="flex gap-4 md:gap-5 items-start">
                  <span className="font-barlow font-black text-3xl md:text-4xl text-volt/40 leading-none w-10 md:w-12 flex-shrink-0">{s.n}</span>
                  <div>
                    <div className="font-barlow font-black uppercase text-white text-lg md:text-xl leading-tight">{s.t}</div>
                    <div className="text-xs md:text-sm text-white/60 mt-1">{s.d}</div>
                  </div>
                </li>
              ))}
            </ol>

            <Link
              to={startHref}
              data-testid="card-cta"
              className="mt-8 md:mt-10 w-full bg-volt hover:bg-white text-deepnavy font-barlow font-black uppercase tracking-widest text-sm py-3.5 flex items-center justify-center gap-2 transition-colors"
            >
              Start free preview
              <ArrowRight className="w-4 h-4" />
            </Link>

            <div className="mt-6 pt-6 border-t border-white/10 grid grid-cols-3 gap-2">
              {[
                { i: Brain, l: "Report" },
                { i: Target, l: "Scout View" },
                { i: FileText, l: "PDF" },
              ].map(({ i: Icon, l }, idx) => (
                <div key={idx} className="flex flex-col items-center gap-1.5 text-center">
                  <Icon className="w-4 h-4 text-volt" strokeWidth={1.5} />
                  <span className="text-[10px] uppercase tracking-widest font-bold text-white/60">{l}</span>
                </div>
              ))}
            </div>

            <a
              href="#what-you-get"
              className="mt-7 flex items-center justify-center gap-2 text-[11px] uppercase tracking-[0.25em] font-bold text-white/40 hover:text-volt transition-colors"
            >
              See an example report below
              <span className="w-8 h-px bg-current" />
            </a>
          </motion.div>
        </div>
      </section>

      {/* ============ WHAT YOU RECEIVE — rich feature cards ============ */}
      <section id="what-you-get" data-testid="what-you-get" className="section-accent-top relative py-24 md:py-32 border-t border-white/10">
        <div className="absolute inset-0 z-0 opacity-15">
          <img
            src="https://images.pexels.com/photos/16826135/pexels-photo-16826135.jpeg"
            alt="Pitch"
            className="w-full h-full object-cover"
          />
          <div className="absolute inset-0 bg-deepnavy/90" />
        </div>
        <div className="relative z-10 max-w-7xl mx-auto px-6 md:px-10">
          <div className="mb-16 relative flex flex-col md:flex-row md:items-end md:justify-between gap-6">
            <span aria-hidden className="section-num-bg">01</span>
            <div className="max-w-3xl relative">
              <span className="text-volt text-xs uppercase tracking-[0.25em] font-bold">Inside your report</span>
              <h2 className="mt-4 font-barlow font-black uppercase text-4xl md:text-6xl tracking-tighter leading-[0.95]">
                Eleven sections.<br />Like a real scout wrote it just for you.
              </h2>
            </div>
            <p className="text-white/60 max-w-md text-sm md:text-base">
              Every box below is a real part of your report. Scores, notes, drills — all written about the player in
              YOUR video.
            </p>
          </div>

          <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-px bg-white/10 border border-white/10">
            {featureCards.map((f, i) => (
              <div
                key={i}
                data-testid={`feature-card-${i}`}
                className="card-premium p-6 md:p-7 group cursor-default flex flex-col"
              >
                <div className="flex items-start justify-between mb-5">
                  <f.icon className="w-7 h-7 text-volt" strokeWidth={1.5} />
                  <span className="font-barlow font-black text-xs text-white/20 tracking-widest">0{i + 1}</span>
                </div>
                <h3 className="font-barlow font-black uppercase text-lg text-white mb-2 leading-tight">{f.title}</h3>
                <p className="text-xs text-white/55 leading-relaxed mb-4 flex-1">{f.text}</p>
                <div className="mt-auto pt-4 border-t border-white/5">
                  <p className="text-[11px] italic text-volt/80 leading-snug">"{f.preview}"</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ============ SAMPLE REPORT — RICH, COMPELLING, WOW ============ */}
      <section
        data-testid="example-report"
        className="section-accent-top relative py-24 md:py-32 border-t border-white/10 overflow-hidden"
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
              <p className="mt-4 text-white/65 max-w-2xl">
                Below is a real example. The first box is the free preview — like the one you'll see right after you
                upload. Everything else is what our scouts unlock for <span className="text-volt font-bold">{price} DKK</span>.
              </p>
            </div>
          </div>

          {/* === SAMPLE REPORT HEADER — pro football card === */}
          <div className="grid lg:grid-cols-5 gap-px bg-white/10 border border-white/10 mb-px">
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
              <div className="relative flex items-center justify-between px-5 py-3 border-b border-white/10 bg-deepnavy/60">
                <span className="text-volt text-[10px] uppercase tracking-[0.25em] font-bold flex items-center gap-1.5">
                  <span className="w-1.5 h-1.5 bg-volt rounded-full animate-pulse" /> Free Preview
                </span>
                <span className="text-white/40 text-[10px] uppercase tracking-[0.2em] font-bold">{sample.player.videoType}</span>
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
                    <div className="text-[10px] uppercase tracking-[0.22em] font-bold text-white/40 mb-1">Player</div>
                    <h3 className="font-barlow font-black uppercase text-3xl md:text-4xl tracking-tighter leading-[0.9] text-white">
                      {sample.player.name}
                    </h3>
                    <div className="mt-2 inline-flex items-center gap-2 bg-volt/10 border border-volt/30 px-2.5 py-1">
                      <span className="font-barlow font-black uppercase text-volt text-sm leading-none">{sample.player.positionShort}</span>
                      <span className="text-white/60 text-[11px]">·</span>
                      <span className="text-white/80 text-xs">{sample.player.position}</span>
                    </div>
                  </div>
                </div>

                {/* Meta row */}
                <div className="mt-6 grid grid-cols-3 gap-px bg-white/5 border border-white/10">
                  <div className="bg-deepnavy/60 p-3">
                    <div className="text-[9px] uppercase tracking-widest text-white/40 font-bold">Age</div>
                    <div className="font-barlow font-black text-white text-2xl leading-none mt-1">{sample.player.age}</div>
                  </div>
                  <div className="bg-deepnavy/60 p-3">
                    <div className="text-[9px] uppercase tracking-widest text-white/40 font-bold">Foot</div>
                    <div className="font-barlow font-black text-white text-lg leading-none mt-1.5">{sample.player.foot}</div>
                  </div>
                  <div className="bg-deepnavy/60 p-3">
                    <div className="text-[9px] uppercase tracking-widest text-white/40 font-bold">Team</div>
                    <div className="font-barlow font-black text-white text-sm leading-none mt-1.5 truncate">{sample.player.club}</div>
                  </div>
                </div>

                {/* Style tag */}
                <div className="mt-4 flex items-center gap-2 text-xs text-white/70">
                  <Star className="w-3.5 h-3.5 text-volt flex-shrink-0" fill="currentColor" />
                  <span className="font-bold">{sample.player.type}</span>
                </div>

                {/* Score row */}
                <div className="mt-5 grid grid-cols-4 gap-px bg-white/10 border border-volt/20">
                  {[
                    { k: "TECH", v: sample.scores.technical },
                    { k: "TACT", v: sample.scores.tactical },
                    { k: "PHYS", v: sample.scores.physical },
                    { k: "MENT", v: sample.scores.mentality },
                  ].map((s, i) => (
                    <div key={i} className="bg-deepnavy/80 py-3 text-center">
                      <div className="text-[9px] uppercase tracking-widest text-white/40 font-bold">{s.k}</div>
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
                <span className="text-white/30 text-[10px] uppercase tracking-widest font-bold">Free preview</span>
              </div>
              <p className="text-white/90 text-base md:text-[17px] leading-[1.65]">{sample.summary}</p>

              <div className="mt-7 grid sm:grid-cols-2 gap-6 pt-6 border-t border-white/10">
                <div>
                  <div className="text-xs uppercase tracking-[0.2em] font-bold text-white/40 mb-3">What he does well</div>
                  <ul className="space-y-2.5">
                    {sample.strengths.map((s, i) => (
                      <li key={i} className="flex items-start gap-2.5 text-sm text-white/90 leading-snug">
                        <CheckCircle2 className="w-4 h-4 text-volt mt-0.5 flex-shrink-0" />
                        <span>{s}</span>
                      </li>
                    ))}
                  </ul>
                </div>
                <div>
                  <div className="text-xs uppercase tracking-[0.2em] font-bold text-white/40 mb-3">What to work on</div>
                  <p className="text-sm text-white/85 leading-relaxed">{sample.improvement}</p>
                </div>
              </div>
            </div>
          </div>

          {/* === PREMIUM SECTIONS — blurred but visually rich === */}
          <div className="relative">
            {/* The actual content (blurred) */}
            <div className="blur-locked grid lg:grid-cols-3 gap-px bg-white/10 border border-white/10">
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
                    <ul className="space-y-2 text-sm text-white/85">
                      {sample.scoutStrengths.map((s, i) => (
                        <li key={i} className="flex gap-2"><span className="text-volt mt-1">▶</span>{s}</li>
                      ))}
                    </ul>
                  </div>
                  <div>
                    <div className="text-xs uppercase tracking-[0.2em] font-bold text-yellow-400 mb-2">What he'd worry about</div>
                    <ul className="space-y-2 text-sm text-white/85">
                      {sample.scoutConcerns.map((s, i) => (
                        <li key={i} className="flex gap-2"><span className="text-yellow-400 mt-1">▶</span>{s}</li>
                      ))}
                    </ul>
                  </div>
                </div>
                <div className="mt-6 pt-6 border-t border-white/10 grid sm:grid-cols-2 gap-4">
                  <div>
                    <div className="text-[10px] uppercase tracking-[0.18em] font-bold text-white/40 mb-1">Next level to aim for</div>
                    <div className="text-sm text-white/90">{sample.nextLevel}</div>
                  </div>
                  <div>
                    <div className="text-[10px] uppercase tracking-[0.18em] font-bold text-white/40 mb-1">Best position</div>
                    <div className="text-sm text-white/90">{sample.bestPosition}</div>
                  </div>
                </div>
              </div>

              {/* Training exercise card */}
              <div className="bg-surface p-6 md:p-8">
                <span className="text-volt text-[11px] uppercase tracking-[0.25em] font-bold">Premium · Training Plan</span>
                <h3 className="mt-3 font-barlow font-black uppercase text-2xl">Drill of the week</h3>
                <div className="mt-5 border border-volt/30 bg-deepnavy p-4">
                  <div className="flex items-center justify-between mb-2">
                    <span className="font-barlow font-black uppercase text-white text-base">{sample.exercise.name}</span>
                    <span className="flex items-center gap-1 text-xs text-volt font-bold"><Clock className="w-3 h-3" />{sample.exercise.duration}</span>
                  </div>
                  <p className="text-xs text-white/70 leading-relaxed">{sample.exercise.desc}</p>
                </div>
                <div className="mt-4 flex items-center justify-between text-[10px] uppercase tracking-widest font-bold text-white/40">
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
                    <div key={i} className="flex items-start gap-4 bg-deepnavy/60 border border-white/5 px-4 py-3">
                      <div className="flex items-center gap-2 flex-shrink-0">
                        <Play className="w-3 h-3 text-volt" fill="currentColor" />
                        <span className="font-barlow font-black text-volt text-base min-w-[44px]">{c.t}</span>
                      </div>
                      <p className="text-sm text-white/85">{c.c}</p>
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
                className="pointer-events-auto border border-volt/30 bg-deepnavy/95 backdrop-blur-2xl p-8 md:p-10 max-w-md mx-6 text-center shadow-2xl"
                style={{ boxShadow: "0 20px 80px rgba(204,255,0,0.15)" }}
              >
                <div className="inline-flex items-center justify-center w-14 h-14 bg-volt/10 border border-volt/30 mb-5">
                  <Lock className="w-6 h-6 text-volt" strokeWidth={1.5} />
                </div>
                <span className="text-volt text-[11px] uppercase tracking-[0.3em] font-bold">Premium</span>
                <h3 className="mt-3 font-barlow font-black uppercase text-3xl md:text-4xl tracking-tighter leading-[0.95]">
                  Unlock the<br />full report
                </h3>
                <p className="mt-4 text-sm text-white/65 leading-relaxed">
                  Full performance map · all 4 score categories · scout view · 5 personal drills · 30 & 90-day plan · timestamped video comments · premium PDF.
                </p>

                <div className="mt-6 flex items-baseline justify-center gap-2">
                  <span className="font-barlow font-black text-5xl md:text-6xl text-volt leading-none">{price}</span>
                  <span className="text-white/60 uppercase tracking-widest font-bold text-sm">DKK</span>
                </div>
                <p className="text-[10px] text-white/40 uppercase tracking-widest font-bold mt-1">one-time · no subscription</p>

                <Link
                  to={startHref}
                  data-testid="sample-unlock-cta"
                  className="mt-6 w-full bg-volt hover:bg-white text-deepnavy font-barlow font-black uppercase tracking-widest text-sm py-3.5 flex items-center justify-center gap-2 transition-colors"
                >
                  {startLabel}
                  <ArrowRight className="w-4 h-4" />
                </Link>
                <p className="mt-3 text-[10px] text-white/40 flex items-center justify-center gap-1.5">
                  <ShieldCheck className="w-3 h-3" /> Free preview · No card to start
                </p>
              </motion.div>
            </div>
          </div>
        </div>
      </section>

      {/* ============ TRUST ============ */}
      <section id="trust" data-testid="trust-section" className="section-accent-top relative py-20 border-t border-white/10">
        <div className="max-w-7xl mx-auto px-6 md:px-10">
          <div className="border border-white/10 bg-surface p-8 md:p-12 flex flex-col md:flex-row gap-6 md:items-center">
            <ShieldCheck className="w-12 h-12 text-volt flex-shrink-0" strokeWidth={1.5} />
            <div>
              <h3 className="font-barlow font-black uppercase text-2xl md:text-3xl">Honest scouting feedback. Built for growth.</h3>
              <p className="mt-3 text-sm text-white/70 leading-relaxed max-w-3xl">
                ScoutMePlay gives you honest, professional football feedback to help young players get better.
                It does <strong className="text-white">not</strong> promise trials, contracts, or academy spots.
                Your scores are here to guide your training — not to decide your future.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* ============ FINAL CTA ============ */}
      <section data-testid="final-cta" className="section-accent-top relative py-24 md:py-32 border-t border-white/10 overflow-hidden">
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
          <p className="mt-6 text-white/60 max-w-2xl mx-auto">
            Upload a video, mark yourself, and you'll get an instant free preview from our scouts. No card needed to start.
          </p>
          <div className="mt-10">
            <Link
              to={startHref}
              data-testid="final-cta-btn"
              className="inline-flex items-center gap-3 bg-volt hover:bg-white text-deepnavy font-barlow font-black uppercase tracking-widest text-base px-10 py-5 transition-colors"
            >
              {startLabel}
              <ArrowRight className="w-5 h-5" />
            </Link>
          </div>
        </div>
      </section>

      <footer className="border-t border-white/10 py-10">
        <div className="max-w-7xl mx-auto px-6 md:px-10 flex flex-col md:flex-row justify-between gap-4 items-center">
          <div className="flex items-center gap-3">
            <div className="w-7 h-7 bg-volt flex items-center justify-center">
              <span className="text-deepnavy font-barlow font-black text-sm leading-none">S</span>
            </div>
            <span className="font-barlow font-black uppercase tracking-tight">ScoutMePlay</span>
          </div>
          <p className="text-xs text-white/40 uppercase tracking-[0.2em]">Where talent gets noticed · Football scouting service</p>
          <p className="mt-2 text-[10px] text-white/30 normal-case tracking-normal max-w-md md:text-right">
            ScoutMePlay combines advanced scouting technology with human review to deliver honest player feedback.
          </p>
        </div>
      </footer>
    </div>
  );
}
