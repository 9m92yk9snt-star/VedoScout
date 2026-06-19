import React, { useRef } from "react";
import { Link } from "react-router-dom";
import { motion, useScroll, useTransform } from "framer-motion";
import { ArrowRight, ArrowDown, Upload, ShieldCheck } from "lucide-react";

/* ===========================================================
   CSS-3D ROTATING FOOTBALL
   Built from stacked SVG panels + CSS transform: rotateY
   Cinematic, bulletproof, zero WebGL deps
   =========================================================== */
function CinematicFootball() {
  return (
    <div className="football-stage">
      {/* Soft ground shadow */}
      <div className="football-shadow" />
      {/* Volt halo behind */}
      <div className="football-halo" />

      {/* The rotating ball — wrapped in a 3D perspective */}
      <div className="football-3d" aria-hidden="true">
        <div className="football-ball">
          {/* Football SVG — classic 12 pentagons + 20 hexagons truncated icosahedron */}
          <svg
            viewBox="0 0 200 200"
            className="football-svg"
            xmlns="http://www.w3.org/2000/svg"
          >
            <defs>
              {/* Subtle cream-to-white gradient for premium look */}
              <radialGradient id="ballGrad" cx="40%" cy="35%" r="65%">
                <stop offset="0%" stopColor="#ffffff" />
                <stop offset="40%" stopColor="#fff8e6" />
                <stop offset="100%" stopColor="#e8dfb8" />
              </radialGradient>
              {/* Volt rim shimmer */}
              <radialGradient id="ballRim" cx="50%" cy="50%" r="50%">
                <stop offset="80%" stopColor="rgba(204,255,0,0)" />
                <stop offset="100%" stopColor="rgba(204,255,0,0.55)" />
              </radialGradient>
              {/* Glossy highlight */}
              <radialGradient id="ballGloss" cx="35%" cy="28%" r="35%">
                <stop offset="0%" stopColor="rgba(255,255,255,0.7)" />
                <stop offset="100%" stopColor="rgba(255,255,255,0)" />
              </radialGradient>
            </defs>

            {/* Base sphere */}
            <circle cx="100" cy="100" r="92" fill="url(#ballGrad)" />

            {/* Pentagon panels (dark forest) — arranged like a real football */}
            {/* Center pentagon */}
            <polygon
              points="100,72 122,86 114,112 86,112 78,86"
              fill="#0c2415"
            />
            {/* Top pentagon */}
            <polygon
              points="100,32 118,42 114,62 86,62 82,42"
              fill="#0c2415"
              opacity="0.92"
            />
            {/* Left pentagon */}
            <polygon
              points="40,98 58,86 70,108 56,128 38,118"
              fill="#0c2415"
              opacity="0.88"
            />
            {/* Right pentagon */}
            <polygon
              points="160,98 142,86 130,108 144,128 162,118"
              fill="#0c2415"
              opacity="0.88"
            />
            {/* Bottom pentagon */}
            <polygon
              points="100,156 84,148 88,128 112,128 116,148"
              fill="#0c2415"
              opacity="0.85"
            />

            {/* Connecting volt-green seam lines (cinematic touch) */}
            <g stroke="#ccff00" strokeWidth="0.6" opacity="0.45" fill="none">
              {/* Star pattern lines from center pentagon outward */}
              <line x1="100" y1="72" x2="100" y2="32" />
              <line x1="78" y1="86" x2="40" y2="98" />
              <line x1="122" y1="86" x2="160" y2="98" />
              <line x1="86" y1="112" x2="84" y2="148" />
              <line x1="114" y1="112" x2="116" y2="148" />
              {/* Equator hint */}
              <ellipse cx="100" cy="100" rx="92" ry="22" />
            </g>

            {/* Glossy highlight */}
            <circle cx="100" cy="100" r="92" fill="url(#ballGloss)" />
            {/* Volt rim glow */}
            <circle cx="100" cy="100" r="92" fill="url(#ballRim)" />
            {/* Sharp edge */}
            <circle
              cx="100"
              cy="100"
              r="92"
              fill="none"
              stroke="rgba(204,255,0,0.35)"
              strokeWidth="0.8"
            />
          </svg>
        </div>
      </div>

      {/* Orbiting scout markers (3 volt diamonds) */}
      {[0, 1, 2].map((i) => (
        <div
          key={i}
          className="scout-orbit"
          style={{ animationDelay: `${i * -3.33}s` }}
        >
          <span className="scout-orbit-marker" />
        </div>
      ))}

      {/* Floating dust particles */}
      {Array.from({ length: 14 }).map((_, i) => (
        <span
          key={i}
          className="football-dust"
          style={{
            left: `${(i * 71) % 100}%`,
            top: `${(i * 47) % 100}%`,
            animationDelay: `${(i * 0.6) % 8}s`,
            animationDuration: `${6 + (i % 4)}s`,
          }}
        />
      ))}

      {/* Scan ring (slow sweeping highlight) */}
      <div className="football-scan-ring" />

      {/* Inline styles for the 3D scene — keeps everything self-contained */}
      <style>{`
        .football-stage {
          position: absolute;
          inset: 0;
          display: flex;
          align-items: center;
          justify-content: center;
          perspective: 1400px;
          perspective-origin: 50% 45%;
          overflow: hidden;
          pointer-events: none;
        }
        .football-halo {
          position: absolute;
          width: 520px;
          height: 520px;
          border-radius: 50%;
          background: radial-gradient(closest-side,
            rgba(204,255,0,0.35) 0%,
            rgba(204,255,0,0.08) 45%,
            transparent 75%);
          filter: blur(10px);
          animation: footballHaloPulse 6s ease-in-out infinite;
        }
        .football-shadow {
          position: absolute;
          bottom: 18%;
          width: 360px;
          height: 50px;
          border-radius: 50%;
          background: radial-gradient(ellipse,
            rgba(0,0,0,0.55) 0%,
            transparent 70%);
          filter: blur(8px);
          animation: shadowBreath 6s ease-in-out infinite;
        }
        .football-3d {
          width: 360px;
          height: 360px;
          transform-style: preserve-3d;
          animation: ballFloat 5.5s ease-in-out infinite;
          filter: drop-shadow(0 25px 35px rgba(0,0,0,0.45))
                  drop-shadow(0 0 35px rgba(204,255,0,0.18));
        }
        .football-ball {
          width: 100%;
          height: 100%;
          animation: ballSpin 14s linear infinite;
          transform-style: preserve-3d;
        }
        .football-svg {
          width: 100%;
          height: 100%;
          display: block;
        }

        /* Orbits */
        .scout-orbit {
          position: absolute;
          top: 50%;
          left: 50%;
          width: 460px;
          height: 460px;
          margin-top: -230px;
          margin-left: -230px;
          transform-style: preserve-3d;
          animation: scoutOrbit 10s linear infinite;
        }
        .scout-orbit-marker {
          position: absolute;
          top: -8px;
          left: 50%;
          width: 14px;
          height: 14px;
          margin-left: -7px;
          background: #ccff00;
          transform: rotate(45deg);
          box-shadow:
            0 0 18px rgba(204,255,0,0.9),
            0 0 32px rgba(204,255,0,0.6);
        }

        /* Dust */
        .football-dust {
          position: absolute;
          width: 3px;
          height: 3px;
          border-radius: 50%;
          background: rgba(204,255,0,0.7);
          box-shadow: 0 0 6px rgba(204,255,0,0.7);
          animation: dustDrift linear infinite;
        }

        /* Scan ring */
        .football-scan-ring {
          position: absolute;
          width: 520px;
          height: 520px;
          border-radius: 50%;
          border: 1px solid rgba(204,255,0,0.25);
          animation: scanRingPulse 4s ease-out infinite;
        }

        /* === Animations === */
        @keyframes ballSpin {
          from { transform: rotateY(0deg) rotateX(8deg); }
          to   { transform: rotateY(360deg) rotateX(8deg); }
        }
        @keyframes ballFloat {
          0%, 100% { transform: translateY(0); }
          50%      { transform: translateY(-12px); }
        }
        @keyframes scoutOrbit {
          from { transform: rotateZ(0deg) rotateX(70deg); }
          to   { transform: rotateZ(360deg) rotateX(70deg); }
        }
        @keyframes dustDrift {
          0%   { transform: translate(0,0); opacity: 0; }
          15%  { opacity: 0.9; }
          85%  { opacity: 0.9; }
          100% { transform: translate(20px,-40px); opacity: 0; }
        }
        @keyframes footballHaloPulse {
          0%, 100% { transform: scale(1); opacity: 0.95; }
          50%      { transform: scale(1.07); opacity: 0.75; }
        }
        @keyframes shadowBreath {
          0%, 100% { transform: scale(1); opacity: 0.7; }
          50%      { transform: scale(0.92); opacity: 0.55; }
        }
        @keyframes scanRingPulse {
          0%   { transform: scale(0.9); opacity: 0; }
          50%  { opacity: 0.5; }
          100% { transform: scale(1.25); opacity: 0; }
        }

        @media (max-width: 640px) {
          .football-3d { width: 260px; height: 260px; }
          .football-halo { width: 360px; height: 360px; }
          .scout-orbit { width: 320px; height: 320px; margin-top:-160px; margin-left:-160px; }
          .football-scan-ring { width: 380px; height: 380px; }
          .football-shadow { width: 240px; }
        }
      `}</style>
    </div>
  );
}

/* ===========================================================
   CINEMATIC HERO COMPONENT
   =========================================================== */
export default function CinematicHero({ startHref = "/signup" }) {
  const sectionRef = useRef(null);
  const { scrollYProgress } = useScroll({
    target: sectionRef,
    offset: ["start start", "end start"],
  });

  // Subtle parallax on copy as user scrolls
  const copyY = useTransform(scrollYProgress, [0, 1], [0, -80]);
  const copyOpacity = useTransform(scrollYProgress, [0, 0.65], [1, 0]);
  const sceneOpacity = useTransform(scrollYProgress, [0, 0.7], [1, 0.2]);

  return (
    <section
      ref={sectionRef}
      data-testid="cinematic-hero-section"
      className="relative w-full min-h-[100vh] bg-deepnavy overflow-hidden border-b border-volt/10"
    >
      {/* === Atmospheric backdrop === */}
      <div className="absolute inset-0 z-0 pointer-events-none">
        {/* Stadium gradient */}
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,rgba(61,140,94,0.20)_0%,rgba(8,16,12,0.85)_55%,#050d09_100%)]" />
        {/* Volt sweep */}
        <div
          className="absolute -inset-x-1/4 inset-y-0 animate-sweep-slow opacity-30"
          style={{
            background:
              "linear-gradient(115deg, transparent 0%, rgba(204,255,0,0.10) 50%, transparent 100%)",
          }}
        />
        {/* Scoreline grid */}
        <div className="absolute inset-0 scoreline-grid opacity-25" />
        {/* Cinematic letterbox top/bottom */}
        <div className="absolute top-0 inset-x-0 h-24 bg-gradient-to-b from-black/80 to-transparent" />
        <div className="absolute bottom-0 inset-x-0 h-32 bg-gradient-to-t from-deepnavy via-deepnavy/70 to-transparent" />
        {/* Star dust backdrop */}
        {Array.from({ length: 40 }).map((_, i) => (
          <span
            key={i}
            className="absolute w-px h-px bg-ink/50 rounded-full animate-twinkle"
            style={{
              left: `${(i * 37) % 100}%`,
              top: `${(i * 23) % 100}%`,
              animationDelay: `${(i * 0.3) % 5}s`,
            }}
          />
        ))}
      </div>

      {/* === 3D FOOTBALL SCENE — right side panel === */}
      <motion.div
        style={{ opacity: sceneOpacity }}
        className="absolute inset-y-0 right-0 z-[1] w-full lg:w-[55%] pointer-events-none"
        data-testid="cinematic-hero-scene"
      >
        <CinematicFootball />
      </motion.div>

      {/* Mobile-only dim under canvas so text stays legible */}
      <div className="absolute inset-0 z-[2] lg:hidden bg-gradient-to-b from-deepnavy/55 via-deepnavy/40 to-deepnavy/80 pointer-events-none" />

      {/* Left-side fade for copy contrast on desktop */}
      <div className="absolute inset-y-0 left-0 z-[2] hidden lg:block w-[60%] bg-gradient-to-r from-deepnavy via-deepnavy/95 to-transparent pointer-events-none" />

      {/* === COPY OVERLAY === */}
      <motion.div
        style={{ y: copyY, opacity: copyOpacity }}
        className="relative z-10 w-full max-w-7xl mx-auto px-6 md:px-10 pt-32 md:pt-40 pb-24 md:pb-32 min-h-[100vh] flex flex-col justify-center"
      >
        <div className="w-full lg:max-w-2xl">
          {/* Eyebrow chip */}
          <motion.div
            initial={{ opacity: 0, y: 14 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7, ease: "easeOut" }}
            className="inline-flex items-center self-start gap-2 border border-volt/40 bg-volt/10 px-4 py-2 backdrop-blur-sm"
            data-testid="cinematic-hero-chip"
          >
            <span className="w-1.5 h-1.5 bg-volt animate-pulse rounded-full" />
            <span className="text-volt text-[10px] sm:text-xs uppercase tracking-[0.28em] font-bold whitespace-nowrap">
              ScoutMePlay · Pro Scout Intelligence
            </span>
          </motion.div>

          {/* Headline — user copy */}
          <motion.h1
            initial={{ opacity: 0, y: 24 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.9, ease: "easeOut", delay: 0.15 }}
            data-testid="cinematic-hero-title"
            className="mt-8 font-barlow font-black uppercase text-4xl sm:text-5xl md:text-6xl lg:text-7xl leading-[0.9] tracking-tighter text-ink"
          >
            Upload Your Video.
            <span className="block mt-2 text-gradient-volt">
              Get a Deep Football
            </span>
            <span className="block text-gradient-volt">
              Intelligence Report.
            </span>
          </motion.h1>

          {/* Value chips line */}
          <motion.div
            initial={{ opacity: 0, y: 18 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8, ease: "easeOut", delay: 0.45 }}
            data-testid="cinematic-hero-values"
            className="mt-7 flex flex-wrap items-center gap-x-3 gap-y-2 text-ink/90"
          >
            {[
              "Benchmarked Data",
              "Real Scout Review",
              "Agent Feedback",
              "Player Tracking",
            ].map((v, i) => (
              <React.Fragment key={v}>
                <span className="text-sm sm:text-base md:text-lg font-semibold tracking-wide">
                  {v}
                </span>
                {i < 3 && (
                  <span className="text-volt/70 text-base sm:text-lg" aria-hidden>
                    •
                  </span>
                )}
              </React.Fragment>
            ))}
          </motion.div>

          {/* Sub-tagline */}
          <motion.p
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8, ease: "easeOut", delay: 0.65 }}
            data-testid="cinematic-hero-subtagline"
            className="mt-6 text-volt font-barlow font-black uppercase tracking-[0.18em] text-sm sm:text-base"
          >
            No Subscriptions. No Guesswork.
          </motion.p>

          {/* CTAs */}
          <motion.div
            initial={{ opacity: 0, y: 18 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8, ease: "easeOut", delay: 0.85 }}
            className="mt-10 flex flex-col sm:flex-row items-stretch sm:items-center gap-3 sm:gap-4"
          >
            <Link
              to={startHref}
              data-testid="cinematic-hero-cta-primary"
              className="group bg-volt hover:bg-forest-pop text-deepnavy hover:text-white font-barlow font-black uppercase tracking-widest text-base px-6 py-4 flex items-center justify-center gap-3 transition-colors animate-pulse-glow"
            >
              <Upload className="w-5 h-5" strokeWidth={2.4} />
              Upload your video
              <ArrowRight className="w-5 h-5 group-hover:translate-x-1 transition-transform" />
            </Link>
            <a
              href="#how-it-works"
              data-testid="cinematic-hero-cta-secondary"
              className="border border-volt/40 hover:border-volt text-ink hover:text-volt font-barlow font-black uppercase tracking-widest text-base px-6 py-4 flex items-center justify-center gap-2 transition-colors backdrop-blur-sm"
            >
              See how it works
              <ArrowDown className="w-4 h-4" />
            </a>
          </motion.div>

          {/* Trust micro-line */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 1, delay: 1.1 }}
            className="mt-10 flex items-center gap-3 text-[11px] uppercase tracking-[0.22em] font-bold text-ink/55"
            data-testid="cinematic-hero-trust"
          >
            <ShieldCheck className="w-3.5 h-3.5 text-volt shrink-0" />
            <span>Secure Stripe · Pro benchmarks · One-time payment</span>
          </motion.div>
        </div>
      </motion.div>

      {/* Scroll cue */}
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 1.4, duration: 1 }}
        className="absolute bottom-6 left-1/2 -translate-x-1/2 z-10 flex flex-col items-center gap-2 text-ink/60"
        data-testid="cinematic-hero-scroll-cue"
      >
        <span className="text-[10px] uppercase tracking-[0.3em] font-bold">
          Scroll
        </span>
        <motion.div
          animate={{ y: [0, 8, 0] }}
          transition={{ duration: 1.6, repeat: Infinity, ease: "easeInOut" }}
        >
          <ArrowDown className="w-4 h-4 text-volt" />
        </motion.div>
      </motion.div>

      {/* Local helper keyframes for twinkle stars */}
      <style>{`
        @keyframes twinkle {
          0%, 100% { opacity: 0.2; }
          50%      { opacity: 1; }
        }
        .animate-twinkle { animation: twinkle 3s ease-in-out infinite; }
      `}</style>
    </section>
  );
}
