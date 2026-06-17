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
  Activity, Heart, Eye, Trophy, Footprints, Lock, Play, CheckCircle2,
  TrendingUp, Clock, Award, ClipboardList, Globe, Users,
  Lightbulb, Crown, Calendar, Dumbbell, Mail, Send, Twitter, Facebook, Linkedin, Instagram, MessageCircle,
} from "lucide-react";
import PaymentBadges from "@/components/PaymentBadges";
import PricingCards from "@/components/PricingCards";
import SEO, { organizationJsonLd } from "@/components/SEO";

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
  const [social, setSocial] = useState({
    twitter_url:   "https://twitter.com/scoutmeplay",
    facebook_url:  "https://www.facebook.com/scoutmeplay",
    linkedin_url:  "https://www.linkedin.com/company/scoutmeplay",
    instagram_url: "https://www.instagram.com/scoutmeplay",
  });
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
                Upload your football video and receive a detailed scouting report powered by{" "}
                <span className="text-ink font-semibold">advanced football intelligence</span>,{" "}
                <span className="text-ink font-semibold">professional player benchmarks</span>, and{" "}
                <span className="text-ink font-semibold">real scouts and agents</span> connected to clubs around the world.
                <br />
                <span className="block mt-3 text-sm md:text-base text-ink/65">
                  Built for ambitious players from <span className="text-volt font-bold">U7 to U21</span> chasing their football dreams.
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
                className="mt-7 flex flex-wrap items-center gap-x-5 gap-y-3 text-[11px] uppercase tracking-[0.18em] font-bold text-ink/65"
              >
                <span className="flex items-center gap-1.5"><Trophy className="w-3.5 h-3.5 text-volt" /> Pro player benchmarks</span>
                <span className="flex items-center gap-1.5"><Brain className="w-3.5 h-3.5 text-volt" /> Football intelligence</span>
                <span className="flex items-center gap-1.5"><Users className="w-3.5 h-3.5 text-volt" /> Real scouts &amp; agents</span>
                <span className="flex items-center gap-1.5"><FileText className="w-3.5 h-3.5 text-volt" /> Premium PDF report</span>
                <span className="flex items-center gap-1.5"><ShieldCheck className="w-3.5 h-3.5 text-volt" /> Secure Stripe payment</span>
                <span className="flex items-center gap-1.5"><Star className="w-3.5 h-3.5 text-volt" /> One-time payment · no subscription</span>
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
                    Icon: Trophy,
                    body: (
                      <>
                        <span className="text-volt font-semibold">Pro player benchmarked</span> — your performance compared to professional profiles and position-specific standards used at the highest level of the game.
                      </>
                    ),
                  },
                  {
                    Icon: ClipboardList,
                    body: (
                      <>
                        <span className="text-volt font-semibold">Detailed football analysis</span> — technical, tactical, physical and mental scores with strengths, weaknesses, evidence and a personal development plan.
                      </>
                    ),
                  },
                  {
                    Icon: Users,
                    body: (
                      <>
                        <span className="text-volt font-semibold">Real scouts &amp; agents</span> connected to clubs worldwide — guidance on trials, club changes, contracts and finding the right academy for your next step.
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
      <section id="what-you-get" data-testid="what-you-get" className="section-accent-top relative py-16 md:py-24 border-t border-gray-border overflow-hidden">
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
                { cls: "lg:col-span-4", variant: "default" },                                  // 9 PDF
                { cls: "lg:col-span-4", variant: "default" },                                  // 10 Private
              ];

              const renderCard = (card, i) => {
                const b = bento[i];
                const number = String(i + 1).padStart(2, "0");

                /* ===== HERO variant — Player Report, dark forest, oversized ===== */
                if (b.variant === "hero") {
                  return (
                    <motion.div
                      key={i}
                      initial={{ opacity: 0, y: 24 }}
                      whileInView={{ opacity: 1, y: 0 }}
                      viewport={{ once: true, amount: 0.2 }}
                      transition={{ duration: 0.6, ease: "easeOut" }}
                      data-testid={`feature-card-${i}`}
                      className={`${b.cls} relative overflow-hidden bg-forest text-cream-card border border-volt/30 p-7 md:p-10 flex flex-col group hover:border-volt transition-all duration-300 hover:-translate-y-1`}
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
                    </motion.div>
                  );
                }

                /* ===== WIDE variant — Training Plan, horizontal layout ===== */
                if (b.variant === "wide") {
                  return (
                    <motion.div
                      key={i}
                      initial={{ opacity: 0, y: 18 }}
                      whileInView={{ opacity: 1, y: 0 }}
                      viewport={{ once: true, amount: 0.2 }}
                      transition={{ duration: 0.5, delay: 0.08, ease: "easeOut" }}
                      data-testid={`feature-card-${i}`}
                      className={`${b.cls} relative bg-surface/80 backdrop-blur-sm border border-gray-border hover:border-volt/50 p-6 md:p-8 flex flex-col md:flex-row md:items-stretch md:gap-8 group hover:-translate-y-1 transition-all duration-300`}
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
                    </motion.div>
                  );
                }

                /* ===== TINT / DEFAULT — standard card with optional volt accent ===== */
                const isTint = b.variant === "tint";
                return (
                  <motion.div
                    key={i}
                    initial={{ opacity: 0, y: 18 }}
                    whileInView={{ opacity: 1, y: 0 }}
                    viewport={{ once: true, amount: 0.2 }}
                    transition={{ duration: 0.5, delay: (i % 4) * 0.06, ease: "easeOut" }}
                    data-testid={`feature-card-${i}`}
                    className={`${b.cls} relative overflow-hidden border border-gray-border hover:border-volt/50 p-6 md:p-7 flex flex-col group hover:-translate-y-1 transition-all duration-300 ${
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
                  </motion.div>
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
        className="section-accent-top relative py-16 md:py-24 border-t border-gray-border overflow-hidden"
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

            {/* The sample-report SHOWCASE overlay (price-free — directs to /pricing) */}
            <div className="absolute inset-0 z-10 pointer-events-none flex items-center justify-center">
              <motion.div
                initial={{ opacity: 0, scale: 0.95 }}
                whileInView={{ opacity: 1, scale: 1 }}
                viewport={{ once: true, margin: "-100px" }}
                transition={{ duration: 0.5 }}
                className="pointer-events-auto border border-forest/20 bg-cream-card backdrop-blur-2xl p-8 md:p-10 max-w-md mx-6 text-center shadow-2xl"
                style={{ boxShadow: "0 20px 80px rgba(31, 79, 47, 0.15)" }}
              >
                <div className="inline-flex items-center justify-center w-14 h-14 bg-forest/10 border border-forest/25 mb-5">
                  <Eye className="w-6 h-6 text-forest" strokeWidth={1.5} />
                </div>
                <span className="text-forest text-[11px] uppercase tracking-[0.3em] font-bold">Sample · See it in action</span>
                <h3 className="mt-3 font-barlow font-black uppercase text-3xl md:text-4xl tracking-tighter leading-[0.95]">
                  This is your<br />report
                </h3>
                <p className="mt-4 text-sm text-ink/70 leading-relaxed">
                  Full performance map · all 4 score categories · scout view · 5 personal drills · 30 &amp; 90-day plan · timestamped video comments · personal scout review · premium PDF.
                </p>

                <button
                  type="button"
                  data-testid="sample-see-plans-cta"
                  onClick={() => {
                    const el = document.getElementById("pricing");
                    if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
                  }}
                  className="mt-7 w-full bg-forest hover:bg-forest-pop text-white font-barlow font-black uppercase tracking-widest text-sm py-3.5 flex items-center justify-center gap-2 transition-colors"
                >
                  See plans
                  <ArrowDown className="w-4 h-4" />
                </button>
                <p className="mt-3 text-[10px] text-ink/55 flex items-center justify-center gap-1.5">
                  <ShieldCheck className="w-3 h-3" /> Free preview · No card to start
                </p>
                <div className="mt-4 pt-4 border-t border-gray-border flex justify-center">
                  <PaymentBadges variant="compact" />
                </div>
              </motion.div>
            </div>
          </div>
        </div>
      </section>

      {/* ============ PRICING ============ */}
      <section id="pricing" data-testid="pricing-section" className="section-accent-top relative py-16 md:py-20 border-t border-gray-border overflow-hidden">
        {/* Subtle background pattern */}
        <div
          aria-hidden
          className="absolute inset-0 opacity-[0.04] pointer-events-none"
          style={{
            backgroundImage:
              "radial-gradient(circle at 1px 1px, #1F4F2F 1px, transparent 0)",
            backgroundSize: "24px 24px",
          }}
        />
        <div className="relative max-w-7xl mx-auto px-6 md:px-10">
          <div className="text-center max-w-3xl mx-auto">
            <span className="text-volt text-xs uppercase tracking-[0.25em] font-bold">Pricing</span>
            <h2 className="mt-3 font-barlow font-black uppercase text-4xl md:text-6xl tracking-tighter leading-[0.95]">
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
      <section data-testid="final-cta" className="section-accent-top relative py-16 md:py-24 border-t border-gray-border overflow-hidden">
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
