import React, { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { motion, AnimatePresence, useReducedMotion } from "framer-motion";
import {
  Play, Pause, RotateCcw, Upload, MousePointer2, Sparkles,
  Eye, FileText, TrendingUp, ArrowRight, Volume2, CheckCircle2,
  Download, Star, Smartphone, Monitor, Tablet, Link2, Youtube,
  Trophy, Quote, Globe,
} from "lucide-react";

/* ============================================================================
   How It Works — animated walkthrough · 6 scenes · max wow
   ============================================================================ */

const FOREST = "#1F4F2F";
const FOREST_DEEP = "#143923";
const FOREST_SOFT = "rgba(31,79,47,0.12)";
const CREAM = "#F4EFE6";

// player with clear central figure — frame strip will actually show the player
const PLAYER_IMG =
  "https://images.unsplash.com/photo-1517466787929-bc90951d0974?w=1400&q=85&auto=format&fit=crop";

// scout scene assets — verified Unsplash IDs, no women, action contexts
const SCOUT_CARDS = [
  {
    img: "https://images.unsplash.com/photo-1522778119026-d647f0596c20?w=600&q=85&auto=format&fit=crop",
    role: "Stadium scout",
    leagues: "Premier League",
    clubs: "Manchester · Liverpool",
    icon: Eye,
  },
  {
    img: "https://images.unsplash.com/photo-1517048676732-d65bc937f952?w=600&q=85&auto=format&fit=crop",
    role: "Signing agent",
    leagues: "La Liga",
    clubs: "Madrid · Barcelona",
    icon: FileText,
  },
  {
    img: "https://images.unsplash.com/photo-1500648767791-00dcc994a43e?w=600&q=85&auto=format&fit=crop",
    role: "Academy scout",
    leagues: "Bundesliga",
    clubs: "Bayern · Dortmund",
    icon: Trophy,
  },
];

const SCENES = [
  { id: "upload",   duration: 7400, label: "Upload",  title: "Upload from anywhere",                       caption: "Phone, iPad, computer — or paste a Veo / YouTube link.",         Icon: Upload },
  { id: "mark",     duration: 7600, label: "Mark",    title: "Tap your player ten times",                  caption: "No AI guessing — you stay in control.",                          Icon: MousePointer2 },
  { id: "analyze",  duration: 7600, label: "Analyze", title: "Pro Scout Intelligence builds your report",  caption: "6 pillars · 47 metrics · one honest score.",                     Icon: Sparkles },
  { id: "scout",    duration: 7000, label: "Scouts",  title: "Real scouts watch your clip",                caption: "Human eyes from real clubs. Not just data.",                     Icon: Eye },
  { id: "report",   duration: 7600, label: "Report",  title: "Your professional PDF report",               caption: "Everything parents and players want to see — beautifully laid out.", Icon: FileText },
  { id: "progress", duration: 7000, label: "Progress",title: "Track your evolution",                       caption: "Upload again — watch exactly what improved.",                    Icon: TrendingUp },
];

/* ============================================================================
   Shared visual primitives
============================================================================ */

const ParticleField = ({ tone = "light", density = 24 }) => {
  const dots = useMemo(
    () => Array.from({ length: density }, () => ({
      x: Math.random() * 100,
      y: Math.random() * 100,
      r: 0.6 + Math.random() * 2.4,
      d: 4 + Math.random() * 6,
      delay: Math.random() * 3,
    })),
    [density]
  );
  const color = tone === "light" ? "rgba(255,255,255,0.55)" : "rgba(31,79,47,0.45)";
  return (
    <div className="absolute inset-0 overflow-hidden pointer-events-none z-0">
      {dots.map((p, i) => (
        <motion.span
          key={i}
          className="absolute rounded-full"
          style={{
            left: `${p.x}%`,
            top: `${p.y}%`,
            width: p.r,
            height: p.r,
            background: color,
            boxShadow: tone === "light" ? `0 0 10px ${color}` : "none",
          }}
          animate={{ opacity: [0, 0.9, 0], y: [0, -22, -44] }}
          transition={{ duration: p.d, delay: p.delay, repeat: Infinity, ease: "easeInOut" }}
        />
      ))}
    </div>
  );
};

/* Slow drifting ambient floating chips with brand keywords */
const FloatingChips = ({ items, tone = "light", delay = 0 }) => {
  const color = tone === "light" ? "rgba(255,255,255,0.35)" : "rgba(31,79,47,0.4)";
  return (
    <div className="absolute inset-0 overflow-hidden pointer-events-none z-[1]">
      {items.map((item, i) => (
        <motion.span
          key={i}
          className="absolute font-mono uppercase tracking-[0.2em] text-[9px] font-bold"
          style={{ color, left: `${item.x}%`, top: `${item.y}%` }}
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: [0, 1, 1, 0], y: [-2, -12, -22, -34] }}
          transition={{ duration: 5, delay: delay + i * 0.5, repeat: Infinity, repeatDelay: 1.5 }}
        >
          {item.t}
        </motion.span>
      ))}
    </div>
  );
};

/* Character stagger reveal */
const StaggerText = ({ text, className = "", delay = 0, charDelay = 0.03 }) => {
  const chars = text.split("");
  return (
    <span className={className} aria-label={text}>
      {chars.map((c, i) => (
        <motion.span
          key={i}
          aria-hidden
          className="inline-block"
          initial={{ opacity: 0, y: 22, filter: "blur(8px)" }}
          animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
          transition={{ delay: delay + i * charDelay, duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
        >
          {c === " " ? "\u00A0" : c}
        </motion.span>
      ))}
    </span>
  );
};

/* Count-up number */
const CountUp = ({ from = 0, to = 100, delay = 0, duration = 1.2, suffix = "" }) => {
  const [n, setN] = useState(from);
  useEffect(() => {
    const t = setTimeout(() => {
      const start = performance.now();
      const tick = (now) => {
        const p = Math.min((now - start) / (duration * 1000), 1);
        const eased = 1 - Math.pow(1 - p, 3);
        setN(Math.round(from + (to - from) * eased));
        if (p < 1) requestAnimationFrame(tick);
      };
      requestAnimationFrame(tick);
    }, delay * 1000);
    return () => clearTimeout(t);
  }, [from, to, delay, duration]);
  return <span>{n}{suffix}</span>;
};

/* Discreet brand watermark always visible */
const BrandMark = () => (
  <div className="absolute bottom-3 right-3 z-20 text-[8px] uppercase tracking-[0.3em] font-bold text-white/35 pointer-events-none">
    ScoutMePlay
  </div>
);

/* ============================================================================
   Scene 1 — UPLOAD (multi-source: phone, iPad, computer, link)
============================================================================ */
const UploadScene = () => (
  <motion.div
    key="upload"
    className="absolute inset-0 flex flex-col items-center justify-center overflow-hidden"
    style={{ background: `radial-gradient(ellipse at 50% 30%, #163829 0%, #0A0F0D 70%)` }}
    initial={{ opacity: 0 }}
    animate={{ opacity: 1 }}
    exit={{ opacity: 0, filter: "blur(10px)" }}
    transition={{ duration: 0.6 }}
  >
    <ParticleField tone="light" density={28} />

    {/* moving aurora */}
    <motion.div
      className="absolute inset-0 pointer-events-none"
      style={{
        background: `radial-gradient(circle at 50% 35%, rgba(204,255,200,0.18) 0%, transparent 55%)`,
      }}
      animate={{ scale: [1, 1.08, 1] }}
      transition={{ duration: 5, repeat: Infinity, ease: "easeInOut" }}
    />

    <FloatingChips
      tone="light"
      items={[
        { t: "PHONE", x: 10, y: 25 },
        { t: ".MP4", x: 85, y: 22 },
        { t: "VEO LINK", x: 8, y: 70 },
        { t: "iPAD", x: 90, y: 75 },
      ]}
    />

    {/* opening title — character stagger */}
    <motion.div
      className="relative z-10 mb-5 text-center px-6"
      initial={{ opacity: 1 }}
      animate={{ opacity: [1, 1, 0] }}
      transition={{ duration: 2.7, times: [0, 0.7, 1] }}
    >
      <div className="text-[10px] uppercase tracking-[0.4em] font-bold text-white/55 mb-3">
        <StaggerText text="THE FULL PATH" delay={0.15} />
      </div>
      <div className="font-barlow font-black text-white text-3xl md:text-5xl leading-[0.95] tracking-tight">
        <StaggerText text="From any video," delay={0.5} />
        <br />
        <span className="font-serif-italic normal-case font-normal lowercase tracking-normal" style={{ color: "#CCFF99" }}>
          <StaggerText text="to scout-ready truth." delay={1.0} />
        </span>
      </div>
    </motion.div>

    {/* dropzone slides in */}
    <motion.div
      initial={{ scale: 0.85, opacity: 0, y: 40 }}
      animate={{ scale: 1, opacity: 1, y: 0 }}
      transition={{ delay: 2.5, duration: 0.8, ease: [0.16, 1, 0.3, 1] }}
      className="relative w-[78%] max-w-[520px] aspect-[16/9] border-2 border-dashed flex flex-col items-center justify-center bg-white/92 backdrop-blur z-10"
      style={{ borderColor: FOREST }}
    >
      <motion.div
        className="absolute -inset-1 pointer-events-none"
        style={{ boxShadow: `0 0 70px ${FOREST}` }}
        animate={{ opacity: [0, 0.55, 0.3] }}
        transition={{ delay: 2.6, duration: 1.6 }}
      />

      {/* corner brackets */}
      {["top-0 left-0 border-t-2 border-l-2","top-0 right-0 border-t-2 border-r-2","bottom-0 left-0 border-b-2 border-l-2","bottom-0 right-0 border-b-2 border-r-2"].map((p, i) => (
        <span key={i} aria-hidden className={`absolute ${p} w-4 h-4`} style={{ borderColor: FOREST }} />
      ))}

      {/* 4 source-method icons fly in */}
      <div className="flex items-center gap-4 md:gap-5 mb-3">
        {[Smartphone, Tablet, Monitor, Youtube].map((Icon, i) => (
          <motion.div
            key={i}
            initial={{ opacity: 0, scale: 0, y: 20 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            transition={{ delay: 3.0 + i * 0.18, type: "spring", stiffness: 200, damping: 14 }}
            className="relative w-9 h-9 md:w-10 md:h-10 flex items-center justify-center"
            style={{ background: FOREST_SOFT, border: `1.5px solid ${FOREST}` }}
          >
            <Icon className="w-4 h-4" style={{ color: FOREST }} strokeWidth={1.8} />
          </motion.div>
        ))}
      </div>

      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 3.9, duration: 0.4 }}
        className="text-[9px] uppercase tracking-[0.28em] font-bold text-ink/55"
      >
        Phone · iPad · Computer · Veo link
      </motion.div>

      {/* progress bar */}
      <div className="mt-4 w-[72%] h-1.5 bg-ink/10 overflow-hidden">
        <motion.div
          initial={{ width: 0 }}
          animate={{ width: "100%" }}
          transition={{ delay: 4.2, duration: 1.8, ease: "easeInOut" }}
          className="h-full"
          style={{ background: `linear-gradient(90deg, ${FOREST}, ${FOREST_DEEP})` }}
        />
      </div>
      <motion.span
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 6.0, duration: 0.4 }}
        className="mt-3 text-[10px] uppercase tracking-[0.3em] font-bold flex items-center gap-1.5"
        style={{ color: FOREST }}
      >
        <CheckCircle2 className="w-3.5 h-3.5" /> Video accepted
      </motion.span>
    </motion.div>

    <BrandMark />
  </motion.div>
);

/* ============================================================================
   Scene 2 — MARK (10-tap, player image actually contains the player)
============================================================================ */
// player figure is centered in this image (jersey #16) so taps land on the player body
const TAP_POINTS = [
  { x: 48, y: 38 }, { x: 52, y: 36 }, { x: 56, y: 40 },
  { x: 58, y: 48 }, { x: 56, y: 58 }, { x: 50, y: 64 },
  { x: 46, y: 70 }, { x: 52, y: 72 }, { x: 56, y: 66 }, { x: 60, y: 56 },
];

// background-position for each frame strip thumb — focuses around player
const FRAME_CROPS = [
  "50% 42%", "52% 40%", "55% 44%", "56% 50%", "54% 56%",
  "50% 60%", "48% 64%", "52% 66%", "55% 60%", "58% 54%",
];

const MarkScene = () => (
  <motion.div
    key="mark"
    className="absolute inset-0 overflow-hidden"
    initial={{ opacity: 0 }}
    animate={{ opacity: 1 }}
    exit={{ opacity: 0, filter: "blur(10px)" }}
    transition={{ duration: 0.6 }}
  >
    <div className="absolute inset-0">
      <img src={PLAYER_IMG} alt="" className="absolute inset-0 w-full h-full object-cover" />
      <div className="absolute inset-0 bg-ink/35" />
    </div>

    {/* scanning grid */}
    <div className="absolute inset-0 opacity-25" style={{
      backgroundImage: `linear-gradient(rgba(255,255,255,0.08) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.08) 1px, transparent 1px)`,
      backgroundSize: "32px 32px",
    }} />

    <FloatingChips
      tone="light"
      delay={1}
      items={[
        { t: "TRACK", x: 6, y: 30 },
        { t: "PRECISION", x: 88, y: 25 },
      ]}
    />

    {/* top HUD */}
    <div className="absolute top-4 left-4 right-4 flex items-center justify-between z-20">
      <motion.span
        initial={{ opacity: 0, x: -20 }}
        animate={{ opacity: 1, x: 0 }}
        transition={{ delay: 0.3 }}
        className="text-[10px] uppercase tracking-[0.25em] font-bold text-white/90 bg-ink/55 backdrop-blur-md px-2.5 py-1 flex items-center gap-1.5"
      >
        <motion.span
          className="w-1.5 h-1.5 rounded-full bg-red-500"
          animate={{ opacity: [1, 0.3, 1] }}
          transition={{ duration: 1, repeat: Infinity }}
        />
        Live · marking
      </motion.span>
      <motion.span
        initial={{ opacity: 0, x: 20 }}
        animate={{ opacity: 1, x: 0 }}
        transition={{ delay: 0.3 }}
        className="font-barlow font-black text-white text-xl bg-ink/55 backdrop-blur-md px-3 py-1"
      >
        <TapCounter />
      </motion.span>
    </div>

    {/* crosshair following player path */}
    <Crosshair />

    {/* taps */}
    {TAP_POINTS.map((p, i) => (
      <TapRipple key={i} x={p.x} y={p.y} delay={0.8 + i * 0.55} />
    ))}

    {/* success flash */}
    <motion.div
      className="absolute inset-0 pointer-events-none z-30 flex items-center justify-center"
      initial={{ opacity: 0 }}
      animate={{ opacity: [0, 0, 1, 0] }}
      transition={{ delay: 6.3, duration: 1.2, times: [0, 0.1, 0.4, 1] }}
    >
      <div className="absolute inset-0" style={{ background: `radial-gradient(circle at 50% 50%, ${CREAM}66 0%, transparent 60%)` }} />
      <div className="font-barlow font-black text-white text-4xl tracking-widest" style={{ textShadow: `0 0 24px ${CREAM}` }}>
        LOCKED IN
      </div>
    </motion.div>

    {/* frame strip — now actually shows the player */}
    <div className="absolute left-0 right-0 px-4 z-20" style={{ bottom: "96px" }}>
      <div className="flex gap-1.5 justify-center">
        {FRAME_CROPS.map((bgPos, i) => (
          <motion.div
            key={i}
            initial={{ opacity: 0, y: 14, scale: 0.85 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            transition={{ delay: 0.9 + i * 0.55, type: "spring", stiffness: 260, damping: 16 }}
            className="w-8 h-10 md:w-10 md:h-12 border-2 border-white/90 overflow-hidden shadow-lg"
            style={{ boxShadow: `0 6px 16px rgba(0,0,0,0.45)` }}
          >
            <div
              className="w-full h-full bg-no-repeat"
              style={{
                backgroundImage: `url(${PLAYER_IMG})`,
                backgroundPosition: bgPos,
                backgroundSize: "180% auto",
              }}
            />
          </motion.div>
        ))}
      </div>
      <div className="text-center mt-1.5 text-[9px] uppercase tracking-[0.3em] font-bold text-white/85 flex items-center justify-center gap-1.5">
        <Sparkles className="w-2.5 h-2.5" /> Live frame strip
      </div>
    </div>

    <BrandMark />
  </motion.div>
);

const TapCounter = () => {
  const [n, setN] = useState(0);
  useEffect(() => {
    const t = TAP_POINTS.map((_, i) =>
      setTimeout(() => setN(i + 1), 800 + i * 550)
    );
    return () => t.forEach(clearTimeout);
  }, []);
  return <span>{n}<span className="text-white/55">/10</span></span>;
};

const Crosshair = () => (
  <motion.div
    initial={{ left: `${TAP_POINTS[0].x}%`, top: `${TAP_POINTS[0].y}%`, opacity: 0 }}
    animate={{
      left: TAP_POINTS.map((p) => `${p.x}%`),
      top: TAP_POINTS.map((p) => `${p.y}%`),
      opacity: [0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1],
    }}
    transition={{ duration: 5.5, delay: 0.6, times: [0, ...TAP_POINTS.map((_, i) => (i + 1) / TAP_POINTS.length)], ease: "easeInOut" }}
    className="absolute z-10 -translate-x-1/2 -translate-y-1/2 pointer-events-none"
  >
    <svg width="56" height="56" viewBox="0 0 56 56" aria-hidden>
      <circle cx="28" cy="28" r="18" fill="none" stroke={CREAM} strokeWidth="1.5" />
      <circle cx="28" cy="28" r="3" fill={CREAM} />
      <line x1="28" y1="2" x2="28" y2="16" stroke={CREAM} strokeWidth="1.5" />
      <line x1="28" y1="40" x2="28" y2="54" stroke={CREAM} strokeWidth="1.5" />
      <line x1="2" y1="28" x2="16" y2="28" stroke={CREAM} strokeWidth="1.5" />
      <line x1="40" y1="28" x2="54" y2="28" stroke={CREAM} strokeWidth="1.5" />
    </svg>
  </motion.div>
);

const TapRipple = ({ x, y, delay }) => (
  <>
    <motion.span
      initial={{ opacity: 0, scale: 0.4 }}
      animate={{ opacity: [0, 1, 0], scale: [0.4, 2.6, 3.2] }}
      transition={{ delay, duration: 1.2, ease: "easeOut" }}
      className="absolute z-10 -translate-x-1/2 -translate-y-1/2 pointer-events-none rounded-full"
      style={{
        left: `${x}%`,
        top: `${y}%`,
        width: 68,
        height: 68,
        border: `2px solid ${CREAM}`,
        boxShadow: `0 0 40px ${CREAM}`,
      }}
    />
    <motion.span
      initial={{ opacity: 0, scale: 0.2 }}
      animate={{ opacity: [0, 1, 0], scale: [0.2, 1, 1.2] }}
      transition={{ delay: delay + 0.1, duration: 0.6 }}
      className="absolute z-10 -translate-x-1/2 -translate-y-1/2 pointer-events-none rounded-full"
      style={{ left: `${x}%`, top: `${y}%`, width: 14, height: 14, background: CREAM }}
    />
  </>
);

/* ============================================================================
   Scene 3 — ANALYZE
============================================================================ */
const AnalyzeScene = () => (
  <motion.div
    key="analyze"
    className="absolute inset-0 overflow-hidden flex items-center justify-center"
    initial={{ opacity: 0 }}
    animate={{ opacity: 1 }}
    exit={{ opacity: 0, filter: "blur(10px)" }}
    transition={{ duration: 0.6 }}
  >
    <div className="absolute inset-0">
      <img src={PLAYER_IMG} alt="" className="w-full h-full object-cover" style={{ filter: "grayscale(1) brightness(0.42)" }} />
      <div className="absolute inset-0" style={{ background: `linear-gradient(180deg, rgba(244,239,230,0) 0%, rgba(244,239,230,0.7) 100%)` }} />
    </div>

    <ParticleField tone="dark" density={18} />
    <FloatingChips
      tone="dark"
      items={[
        { t: "VISION 88", x: 6, y: 18 },
        { t: "BALANCE 71", x: 86, y: 18 },
        { t: "DECISIONS 80", x: 12, y: 78 },
        { t: "ACCEL 75", x: 80, y: 80 },
      ]}
    />

    {/* scan sweep */}
    <motion.div
      initial={{ top: "-10%", opacity: 0 }}
      animate={{ top: "110%", opacity: [0, 1, 1, 0] }}
      transition={{ duration: 2.2, delay: 0.2, ease: "easeInOut" }}
      className="absolute left-0 right-0 h-px z-10 pointer-events-none"
      style={{ background: FOREST, boxShadow: `0 0 32px ${FOREST}, 0 0 80px ${FOREST}` }}
    />

    {/* "47 metrics" badge */}
    <motion.div
      initial={{ opacity: 0, x: -30 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ delay: 2.0 }}
      className="absolute top-4 left-4 z-20 bg-white shadow-lg border-l-4 px-3 py-2"
      style={{ borderColor: FOREST }}
    >
      <div className="text-[9px] uppercase tracking-[0.25em] font-bold text-ink/55">Engine</div>
      <div className="font-barlow font-black text-ink text-sm leading-tight">
        6 pillars · <CountUp from={0} to={47} delay={2.1} duration={1.1} /> metrics
      </div>
    </motion.div>

    <div className="relative z-20 flex flex-col md:flex-row items-center gap-2 md:gap-8 pb-24 md:pb-20 px-4">
      <div className="flex flex-col items-center">
        <RadarAssemble />
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 2.6, duration: 0.5 }}
          className="mt-2 text-center"
        >
          <div className="text-[9px] uppercase tracking-[0.3em] font-bold text-ink/55">Scout Score</div>
          <div className="font-barlow font-black text-5xl md:text-6xl mt-0.5 leading-none" style={{ color: FOREST }}>
            <CountUp from={0} to={78} delay={2.7} duration={1.5} />
            <span className="text-ink/30 text-2xl md:text-3xl ml-1">/100</span>
          </div>
        </motion.div>
      </div>

      <motion.div
        initial={{ opacity: 0, x: 30 }}
        animate={{ opacity: 1, x: 0 }}
        transition={{ delay: 3.4, duration: 0.6 }}
        className="hidden md:block w-[210px] bg-white/95 shadow-xl border border-ink/10 p-4 space-y-2"
      >
        <div className="text-[9px] uppercase tracking-[0.25em] font-bold text-ink/55 mb-1">Pillar Breakdown</div>
        {[
          { k: "Technical", v: 82 },
          { k: "Tactical", v: 88 },
          { k: "Physical", v: 68 },
          { k: "Mentality", v: 80 },
          { k: "Vision", v: 75 },
        ].map((row, i) => (
          <div key={row.k} className="flex items-center gap-2">
            <div className="text-[9px] font-bold uppercase text-ink/65 w-14">{row.k}</div>
            <div className="flex-1 h-1.5 bg-ink/10 overflow-hidden">
              <motion.div
                className="h-full"
                style={{ background: FOREST }}
                initial={{ width: 0 }}
                animate={{ width: `${row.v}%` }}
                transition={{ delay: 3.6 + i * 0.12, duration: 0.7, ease: [0.16, 1, 0.3, 1] }}
              />
            </div>
            <div className="text-[10px] font-barlow font-black w-6 text-right" style={{ color: FOREST }}>{row.v}</div>
          </div>
        ))}
      </motion.div>
    </div>
    <BrandMark />
  </motion.div>
);

const RadarAssemble = () => {
  const values = [82, 75, 68, 88, 72, 80];
  const max = 100, R = 80;
  const cx = 100, cy = 100;
  const angle = (i) => -Math.PI / 2 + (i * 2 * Math.PI) / 6;
  const point = (i, v) => {
    const r = (v / max) * R;
    return { x: cx + r * Math.cos(angle(i)), y: cy + r * Math.sin(angle(i)) };
  };
  const polyPoints = values.map((v, i) => {
    const p = point(i, v);
    return `${p.x},${p.y}`;
  }).join(" ");

  return (
    <svg width="200" height="200" viewBox="0 0 200 200" aria-hidden>
      {[0, 1, 2, 3, 4, 5].map((i) => {
        const p = point(i, 100);
        return <line key={`a${i}`} x1={cx} y1={cy} x2={p.x} y2={p.y} stroke={FOREST} strokeOpacity="0.18" strokeWidth="0.8" />;
      })}
      {[0.33, 0.66, 1].map((s, idx) => {
        const pts = [0, 1, 2, 3, 4, 5].map((i) => {
          const p = point(i, 100 * s);
          return `${p.x},${p.y}`;
        }).join(" ");
        return <motion.polygon
          key={`r${idx}`}
          points={pts}
          fill="none"
          stroke={FOREST}
          strokeOpacity="0.12"
          strokeWidth="0.8"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.6 + idx * 0.2, duration: 0.4 }}
        />;
      })}
      {values.map((v, i) => {
        const target = point(i, v);
        const start = { x: cx + (Math.random() - 0.5) * 240, y: cy + (Math.random() - 0.5) * 240 };
        return (
          <motion.circle
            key={`p${i}`}
            r="4"
            fill={FOREST}
            initial={{ cx: start.x, cy: start.y, opacity: 0 }}
            animate={{ cx: target.x, cy: target.y, opacity: [0, 1, 1] }}
            transition={{ delay: 1.4 + i * 0.08, duration: 0.7, ease: [0.16, 1, 0.3, 1] }}
          />
        );
      })}
      <motion.polygon
        points={polyPoints}
        fill={FOREST}
        fillOpacity="0"
        stroke={FOREST}
        strokeWidth="1.8"
        strokeLinejoin="round"
        initial={{ pathLength: 0, fillOpacity: 0 }}
        animate={{ pathLength: 1, fillOpacity: 0.24 }}
        transition={{ delay: 2.1, duration: 0.9, ease: "easeOut" }}
      />
    </svg>
  );
};

/* ============================================================================
   Scene 4 — SCOUT REVIEW (action-context polaroid cards)
============================================================================ */
const ScoutReviewScene = () => (
  <motion.div
    key="scout"
    className="absolute inset-0 overflow-hidden"
    style={{ background: `linear-gradient(160deg, #0E2519 0%, #1A3A2A 50%, #060A08 100%)` }}
    initial={{ opacity: 0 }}
    animate={{ opacity: 1 }}
    exit={{ opacity: 0, filter: "blur(10px)" }}
    transition={{ duration: 0.6 }}
  >
    <ParticleField tone="light" density={22} />
    <FloatingChips
      tone="light"
      items={[
        { t: "BUNDESLIGA", x: 5, y: 30 },
        { t: "LA LIGA", x: 88, y: 32 },
        { t: "PREMIER LEAGUE", x: 10, y: 80 },
        { t: "EREDIVISIE", x: 80, y: 82 },
      ]}
    />

    {/* spotlight */}
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 0.5 }}
      transition={{ duration: 1.2 }}
      className="absolute -top-10 left-1/2 -translate-x-1/2 w-[130%] h-[80%] pointer-events-none"
      style={{ background: `radial-gradient(ellipse at top, rgba(204,255,200,0.18) 0%, transparent 70%)` }}
    />

    {/* eyebrow */}
    <motion.div
      initial={{ opacity: 0, y: -10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.3 }}
      className="relative z-10 pt-7 px-6 text-center"
    >
      <div className="inline-flex items-center gap-2 text-[10px] uppercase tracking-[0.35em] font-bold text-white/75">
        <Globe className="w-3 h-3" /> Real eyes · real clubs
      </div>
      <div className="mt-2 font-barlow font-black text-white text-2xl md:text-3xl leading-tight">
        <StaggerText text="Scouts watch your clip." delay={0.5} />
      </div>
    </motion.div>

    {/* polaroid scout cards */}
    <div className="absolute inset-x-0 bottom-24 flex justify-center gap-2 md:gap-4 px-3 z-10">
      {SCOUT_CARDS.map((s, i) => (
        <motion.div
          key={i}
          initial={{ opacity: 0, y: 80, rotate: i === 0 ? -4 : i === 2 ? 4 : 0, scale: 0.82 }}
          animate={{ opacity: 1, y: 0, rotate: i === 0 ? -3 : i === 2 ? 3 : 0, scale: 1 }}
          transition={{ delay: 1.4 + i * 0.4, type: "spring", stiffness: 110, damping: 13 }}
          className="relative bg-white shadow-2xl w-[120px] md:w-[180px] flex-shrink-0"
          style={{ boxShadow: "0 20px 50px -10px rgba(0,0,0,0.55)" }}
        >
          {/* photo */}
          <div className="relative aspect-[4/5] overflow-hidden">
            <img src={s.img} alt="" className="w-full h-full object-cover" />
            <div className="absolute inset-0 bg-gradient-to-t from-black/40 to-transparent" />

            {/* LIVE badge */}
            <motion.div
              initial={{ opacity: 0, scale: 0 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ delay: 2.4 + i * 0.4, type: "spring", stiffness: 200 }}
              className="absolute top-1.5 right-1.5 flex items-center gap-1 bg-ink/85 backdrop-blur-md text-white text-[8px] uppercase tracking-widest font-bold px-1.5 py-0.5"
            >
              <span className="w-1 h-1 rounded-full bg-red-500 animate-pulse" />
              Watching
            </motion.div>

            {/* scan line */}
            <motion.div
              initial={{ top: "-100%" }}
              animate={{ top: "100%" }}
              transition={{ delay: 1.7 + i * 0.4, duration: 1.6, ease: "easeInOut" }}
              className="absolute left-0 right-0 h-px z-10"
              style={{ background: "rgba(204,255,200,0.9)", boxShadow: "0 0 16px rgba(204,255,200,0.9)" }}
            />

            {/* icon overlay */}
            <div className="absolute bottom-1.5 left-1.5 w-6 h-6 flex items-center justify-center bg-white/90">
              <s.icon className="w-3 h-3" style={{ color: FOREST }} strokeWidth={2} />
            </div>
          </div>

          {/* caption */}
          <div className="p-2 md:p-2.5">
            <div className="text-[10px] uppercase tracking-[0.2em] font-bold text-ink/85 leading-tight">{s.role}</div>
            <div className="text-[8px] uppercase tracking-[0.18em] font-bold mt-1" style={{ color: FOREST }}>
              {s.leagues}
            </div>
            <div className="text-[8px] text-ink/55 mt-0.5 leading-tight">{s.clubs}</div>
            <motion.div
              initial={{ width: 0 }}
              animate={{ width: "100%" }}
              transition={{ delay: 3.3 + i * 0.4, duration: 0.5 }}
              className="h-0.5 mt-1.5"
              style={{ background: FOREST }}
            />
            <motion.div
              initial={{ opacity: 0, scale: 0 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ delay: 3.5 + i * 0.4, type: "spring", stiffness: 220 }}
              className="mt-1.5 flex items-center gap-1 text-[8px] uppercase tracking-wider font-bold"
              style={{ color: FOREST }}
            >
              <CheckCircle2 className="w-2.5 h-2.5" /> Signed off
            </motion.div>
          </div>
        </motion.div>
      ))}
    </div>

    {/* verdict signed counter */}
    <motion.div
      initial={{ opacity: 0, x: 30 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ delay: 4.4, duration: 0.55 }}
      className="absolute top-4 right-4 z-10 bg-white/95 shadow-xl border-l-4 px-3 py-2"
      style={{ borderColor: FOREST }}
    >
      <div className="text-[9px] uppercase tracking-[0.25em] font-bold text-ink/55">Verdicts signed</div>
      <div className="font-barlow font-black text-ink text-lg">
        <CountUp from={0} to={3} delay={4.5} duration={0.6} /> / 3
      </div>
    </motion.div>

    <BrandMark />
  </motion.div>
);

/* ============================================================================
   Scene 5 — REPORT PDF (4-page fan + download)
============================================================================ */
const ReportPdfScene = () => (
  <motion.div
    key="report"
    className="absolute inset-0 overflow-hidden flex items-center justify-center"
    initial={{ opacity: 0 }}
    animate={{ opacity: 1 }}
    exit={{ opacity: 0, filter: "blur(10px)" }}
    transition={{ duration: 0.6 }}
  >
    <div className="absolute inset-0" style={{ background: CREAM }} />
    <div className="absolute inset-0" style={{
      backgroundImage: `linear-gradient(${FOREST_SOFT} 1px, transparent 1px), linear-gradient(90deg, ${FOREST_SOFT} 1px, transparent 1px)`,
      backgroundSize: "48px 48px",
      opacity: 0.55,
    }} />
    <ParticleField tone="dark" density={14} />
    <FloatingChips
      tone="dark"
      items={[
        { t: "12 PAGES", x: 6, y: 25 },
        { t: "SHAREABLE", x: 88, y: 28 },
      ]}
    />

    <div className="absolute bottom-0 left-1/2 -translate-x-1/2 w-[600px] h-[260px] pointer-events-none"
         style={{ background: `radial-gradient(ellipse at bottom, ${FOREST_SOFT} 0%, transparent 70%)`, filter: "blur(20px)" }} />

    {/* fan of PDF pages */}
    <div className="relative z-10 flex items-center justify-center w-full pb-24" style={{ perspective: 1400 }}>
      <PdfPage delay={0.3} rotate={-12} translateX={-170} z={0} pageType="cover" />
      <PdfPage delay={0.55} rotate={-5} translateX={-72} z={1} pageType="radar" />
      <PdfPage delay={0.8} rotate={3} translateX={28} z={2} pageType="strengths" />
      <PdfPage delay={1.05} rotate={11} translateX={128} z={3} pageType="growth" />
    </div>

    {/* download badge */}
    <motion.div
      initial={{ opacity: 0, y: 20, scale: 0.8 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ delay: 3.2, type: "spring", stiffness: 200, damping: 14 }}
      className="absolute bottom-24 right-6 z-20 flex items-center gap-2 px-4 py-2.5 bg-ink text-white font-barlow font-black uppercase tracking-widest text-xs shadow-2xl"
    >
      <Download className="w-3.5 h-3.5" /> PDF · 12 pages
      <motion.span
        className="absolute -inset-1 pointer-events-none"
        style={{ boxShadow: `0 0 40px ${FOREST}` }}
        animate={{ opacity: [0, 1, 0.3] }}
        transition={{ delay: 3.4, duration: 1.2, repeat: 1 }}
      />
    </motion.div>

    <motion.div
      initial={{ opacity: 0, x: -20 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ delay: 4.0, duration: 0.55 }}
      className="absolute top-4 left-4 z-20 bg-white shadow-lg border-l-4 px-3 py-2"
      style={{ borderColor: FOREST }}
    >
      <div className="text-[9px] uppercase tracking-[0.25em] font-bold text-ink/55">Inside the PDF</div>
      <div className="font-barlow font-black text-ink text-sm leading-tight">
        Radar · Strengths · Growth Plan · Evidence
      </div>
    </motion.div>
  </motion.div>
);

const PdfPage = ({ delay, rotate, translateX, z, pageType }) => (
  <motion.div
    className="absolute"
    initial={{ opacity: 0, y: 80, rotate: rotate - 6, x: translateX, scale: 0.7 }}
    animate={{ opacity: 1, y: 0, rotate, x: translateX, scale: 1 }}
    transition={{ delay, type: "spring", stiffness: 110, damping: 14 }}
    style={{ zIndex: z }}
  >
    <div className="w-[150px] md:w-[185px] aspect-[3/4] bg-white shadow-2xl border border-ink/12 overflow-hidden relative">
      <PdfPageContent type={pageType} delay={delay + 0.5} />
    </div>
  </motion.div>
);

const PdfPageContent = ({ type, delay }) => {
  if (type === "cover") {
    return (
      <div className="p-3 h-full flex flex-col">
        <div className="text-[7px] uppercase tracking-[0.3em] font-bold" style={{ color: FOREST }}>ScoutMePlay</div>
        <div className="font-barlow font-black text-ink text-[11px] mt-1 leading-tight">SCOUTING REPORT</div>
        <div className="mt-auto">
          <div className="font-barlow font-black text-ink text-2xl leading-none">Lukas A.</div>
          <div className="text-[8px] text-ink/55 mt-1">U15 · CAM · Left foot</div>
          <motion.div
            initial={{ width: 0 }}
            animate={{ width: "65%" }}
            transition={{ delay, duration: 0.6 }}
            className="h-0.5 mt-2"
            style={{ background: FOREST }}
          />
          <div className="text-[7px] uppercase tracking-widest font-bold mt-1.5 text-ink/45">Feb 2026</div>
        </div>
      </div>
    );
  }
  if (type === "radar") {
    return (
      <div className="p-3 h-full flex flex-col items-center justify-center">
        <div className="text-[7px] uppercase tracking-[0.25em] font-bold text-ink/55 self-start">Overall radar</div>
        <svg width="115" height="115" viewBox="0 0 115 115" className="mt-1">
          {[0.33, 0.66, 1].map((s) => (
            <polygon key={s} points={hexPoints(s, 46, 57, 57)} fill="none" stroke={FOREST} strokeOpacity="0.15" strokeWidth="0.6" />
          ))}
          <motion.polygon
            points={hexPoints(0.8, 46, 57, 57)}
            fill={FOREST}
            fillOpacity="0"
            stroke={FOREST}
            strokeWidth="1.2"
            initial={{ pathLength: 0, fillOpacity: 0 }}
            animate={{ pathLength: 1, fillOpacity: 0.24 }}
            transition={{ delay, duration: 0.8 }}
          />
        </svg>
        <div className="mt-1 text-[11px] font-barlow font-black" style={{ color: FOREST }}>78 / 100</div>
      </div>
    );
  }
  if (type === "strengths") {
    return (
      <div className="p-3 h-full flex flex-col">
        <div className="text-[7px] uppercase tracking-[0.25em] font-bold" style={{ color: FOREST }}>Top strengths</div>
        {["Vision two steps ahead","Left foot weapon","Calm under press"].map((s, i) => (
          <motion.div
            key={i}
            initial={{ opacity: 0, x: -8 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: delay + i * 0.15 }}
            className="mt-2 flex items-start gap-1.5"
          >
            <Star className="w-2 h-2 mt-0.5 flex-shrink-0" style={{ color: FOREST }} fill={FOREST} />
            <div className="text-[8px] text-ink leading-snug">{s}</div>
          </motion.div>
        ))}
        <div className="mt-auto text-[7px] uppercase tracking-[0.25em] font-bold text-ink/45">Page 4</div>
      </div>
    );
  }
  return (
    <div className="p-3 h-full flex flex-col">
      <div className="text-[7px] uppercase tracking-[0.25em] font-bold" style={{ color: FOREST }}>Growth plan</div>
      <div className="text-[8px] text-ink mt-1.5 leading-snug">30-day · 90-day pathway</div>
      <svg viewBox="0 0 100 50" className="mt-2 w-full">
        <motion.polyline
          points="2,42 18,38 34,30 50,25 66,16 82,10 98,4"
          fill="none"
          stroke={FOREST}
          strokeWidth="1.6"
          strokeLinecap="round"
          initial={{ pathLength: 0 }}
          animate={{ pathLength: 1 }}
          transition={{ delay, duration: 1 }}
        />
        {[[2,42],[18,38],[34,30],[50,25],[66,16],[82,10],[98,4]].map(([x,y],i) => (
          <motion.circle
            key={i}
            cx={x} cy={y} r="1.6" fill={FOREST}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: delay + 0.1 + i * 0.08 }}
          />
        ))}
      </svg>
      <div className="mt-auto flex items-center justify-between">
        <div className="text-[7px] uppercase tracking-widest font-bold text-ink/45">90-day</div>
        <div className="text-[11px] font-barlow font-black" style={{ color: FOREST }}>+15</div>
      </div>
    </div>
  );
};

function hexPoints(scale, r, cx, cy) {
  return [0, 1, 2, 3, 4, 5].map((i) => {
    const a = -Math.PI / 2 + (i * 2 * Math.PI) / 6;
    const rad = r * scale;
    return `${cx + rad * Math.cos(a)},${cy + rad * Math.sin(a)}`;
  }).join(" ");
}

/* ============================================================================
   Scene 6 — PROGRESS
============================================================================ */
const CompareScene = () => (
  <motion.div
    key="progress"
    className="absolute inset-0 overflow-hidden"
    initial={{ opacity: 0 }}
    animate={{ opacity: 1 }}
    exit={{ opacity: 0, filter: "blur(10px)" }}
    transition={{ duration: 0.6 }}
  >
    <div className="absolute inset-0" style={{ background: CREAM }} />
    <div className="absolute inset-0" style={{
      backgroundImage: `linear-gradient(${FOREST_SOFT} 1px, transparent 1px), linear-gradient(90deg, ${FOREST_SOFT} 1px, transparent 1px)`,
      backgroundSize: "56px 56px",
      opacity: 0.6,
    }} />
    <div className="absolute -top-20 -left-20 w-[340px] h-[340px] rounded-full pointer-events-none"
         style={{ background: `radial-gradient(circle, ${FOREST_SOFT} 0%, transparent 70%)`, filter: "blur(30px)" }} />
    <ParticleField tone="dark" density={14} />
    <FloatingChips
      tone="dark"
      items={[
        { t: "+18 VISION", x: 6, y: 18 },
        { t: "+17 PASSING", x: 80, y: 20 },
        { t: "+12 DECISIONS", x: 8, y: 82 },
      ]}
    />

    <motion.div
      initial={{ opacity: 0, y: -8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.2 }}
      className="relative z-10 pt-5 px-5 flex items-center gap-2 text-[10px] uppercase tracking-[0.3em] font-bold"
      style={{ color: FOREST }}
    >
      <TrendingUp className="w-3 h-3" /> Trajectory · 3 months
    </motion.div>

    <div className="relative z-10 flex flex-col items-center w-full px-3 pb-24 mt-2">
      <div className="flex items-center justify-center gap-1.5 md:gap-5">
        <CompareRadar values={[62, 58, 60, 70, 58, 64]} label="Nov" delay={0.4} />
        <CompareRadar values={[72, 65, 64, 78, 65, 72]} label="Dec" delay={0.7} mid />
        <motion.div
          initial={{ opacity: 0, scale: 0.5 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ delay: 1.1 }}
          className="font-barlow font-black text-xl"
          style={{ color: FOREST }}
        >
          →
        </motion.div>
        <CompareRadar values={[82, 75, 68, 88, 72, 80]} label="Feb" delay={1.0} highlight />
      </div>

      <div className="mt-4 flex flex-col md:flex-row items-center gap-3 w-full max-w-2xl">
        <motion.div
          initial={{ opacity: 0, x: -20 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ delay: 1.6, duration: 0.55 }}
          className="flex-1 bg-white border border-ink/10 shadow-lg p-3 w-full"
        >
          <div className="flex items-center justify-between mb-1">
            <div className="text-[9px] uppercase tracking-[0.2em] font-bold text-ink/55">Overall score</div>
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: 2.0 }}
              className="text-[10px] font-barlow font-black"
              style={{ color: FOREST }}
            >
              +<CountUp from={0} to={26} delay={2.1} duration={0.8} /> pts
            </motion.div>
          </div>
          <svg viewBox="0 0 200 50" className="w-full h-12">
            <line x1="0" y1="46" x2="200" y2="46" stroke={FOREST} strokeOpacity="0.15" strokeWidth="0.5" />
            <motion.polyline
              points="6,38 50,32 100,22 150,14 194,6"
              fill="none"
              stroke={FOREST}
              strokeWidth="1.8"
              strokeLinecap="round"
              initial={{ pathLength: 0 }}
              animate={{ pathLength: 1 }}
              transition={{ delay: 1.8, duration: 1.1, ease: "easeOut" }}
            />
            {[[6,38],[50,32],[100,22],[150,14],[194,6]].map(([x,y],i) => (
              <motion.circle
                key={i}
                cx={x} cy={y} r="2.5"
                fill={FOREST}
                initial={{ opacity: 0, scale: 0 }}
                animate={{ opacity: 1, scale: 1 }}
                transition={{ delay: 2.0 + i * 0.12, type: "spring", stiffness: 200 }}
              />
            ))}
            <motion.text
              x="194" y="2" fontSize="6" fill={FOREST} fontWeight="bold" textAnchor="end"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: 2.7 }}
            >
              78
            </motion.text>
          </svg>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, x: 20 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ delay: 2.0, duration: 0.55, ease: [0.16, 1, 0.3, 1] }}
          className="px-3 py-2.5 bg-white border-2 shadow-lg w-full md:w-auto"
          style={{ borderColor: FOREST }}
        >
          <div className="text-[9px] uppercase tracking-[0.3em] font-bold mb-1" style={{ color: FOREST }}>
            What changed
          </div>
          <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1">
            {[
              { k: "Vision", v: "+18" },
              { k: "Passing", v: "+17" },
              { k: "Decisions", v: "+12" },
            ].map((d, i) => (
              <motion.span
                key={i}
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 2.3 + i * 0.12 }}
                className="text-[9px] font-bold uppercase tracking-wider"
                style={{ color: FOREST }}
              >
                {d.k} <span className="font-barlow font-black text-[11px]">{d.v}</span>
              </motion.span>
            ))}
          </div>
        </motion.div>
      </div>
    </div>
  </motion.div>
);

const CompareRadar = ({ values, label, delay = 0, highlight = false, mid = false }) => {
  const max = 100, R = highlight ? 56 : mid ? 50 : 44;
  const cx = 70, cy = 70;
  const angle = (i) => -Math.PI / 2 + (i * 2 * Math.PI) / 6;
  const polyPoints = values.map((v, i) => {
    const r = (v / max) * R;
    return `${cx + r * Math.cos(angle(i))},${cy + r * Math.sin(angle(i))}`;
  }).join(" ");
  return (
    <motion.div
      initial={{ opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay, duration: 0.55, ease: [0.16, 1, 0.3, 1] }}
      className="flex flex-col items-center"
    >
      <svg width="140" height="140" viewBox="0 0 140 140" aria-hidden>
        {[0.33, 0.66, 1].map((s, idx) => {
          const pts = [0, 1, 2, 3, 4, 5].map((i) => {
            const r = R * s;
            return `${cx + r * Math.cos(angle(i))},${cy + r * Math.sin(angle(i))}`;
          }).join(" ");
          return <polygon key={idx} points={pts} fill="none" stroke={FOREST} strokeOpacity="0.14" strokeWidth="0.7" />;
        })}
        {[0, 1, 2, 3, 4, 5].map((i) => {
          const r = R;
          return <line key={i} x1={cx} y1={cy} x2={cx + r * Math.cos(angle(i))} y2={cy + r * Math.sin(angle(i))} stroke={FOREST} strokeOpacity="0.14" strokeWidth="0.7" />;
        })}
        <motion.polygon
          points={polyPoints}
          fill={FOREST}
          fillOpacity={highlight ? 0.28 : mid ? 0.16 : 0.1}
          stroke={FOREST}
          strokeOpacity={highlight ? 1 : mid ? 0.6 : 0.4}
          strokeWidth={highlight ? 1.8 : 1.2}
          initial={{ pathLength: 0 }}
          animate={{ pathLength: 1 }}
          transition={{ delay: delay + 0.3, duration: 0.8, ease: "easeOut" }}
        />
      </svg>
      <div className="text-[9px] uppercase tracking-[0.3em] font-bold mt-0.5"
           style={{ color: highlight ? FOREST : mid ? `${FOREST}99` : `${FOREST}66` }}>
        {label}
      </div>
    </motion.div>
  );
};

/* ============================================================================
   Main
============================================================================ */
export default function HowItWorksWalkthrough({ startHref = "/signup", price = 1 }) {
  const [sceneIdx, setSceneIdx] = useState(0);
  const [isPlaying, setIsPlaying] = useState(true);
  const [progress, setProgress] = useState(0);
  const reduceMotion = useReducedMotion();

  const wrapRef = useRef(null);
  useEffect(() => {
    if (!wrapRef.current || typeof IntersectionObserver === "undefined") return;
    const obs = new IntersectionObserver(
      ([e]) => setIsPlaying(e.isIntersecting && !reduceMotion),
      { threshold: 0.3 }
    );
    obs.observe(wrapRef.current);
    return () => obs.disconnect();
  }, [reduceMotion]);

  useEffect(() => {
    if (!isPlaying) return;
    const dur = SCENES[sceneIdx].duration;
    const start = performance.now();
    let raf;
    const tick = (now) => {
      const p = Math.min((now - start) / dur, 1);
      setProgress(p);
      if (p < 1) raf = requestAnimationFrame(tick);
      else {
        setSceneIdx((i) => (i + 1) % SCENES.length);
        setProgress(0);
      }
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [sceneIdx, isPlaying]);

  const scene = SCENES[sceneIdx];

  const sceneNode = (
    <AnimatePresence mode="wait">
      {sceneIdx === 0 && <UploadScene />}
      {sceneIdx === 1 && <MarkScene />}
      {sceneIdx === 2 && <AnalyzeScene />}
      {sceneIdx === 3 && <ScoutReviewScene />}
      {sceneIdx === 4 && <ReportPdfScene />}
      {sceneIdx === 5 && <CompareScene />}
    </AnimatePresence>
  );

  return (
    <section
      ref={wrapRef}
      data-testid="how-it-works-walkthrough"
      className="relative py-20 md:py-28 border-t border-gray-border bg-cream-base overflow-hidden"
    >
      <div className="absolute -top-32 -right-32 w-[480px] h-[480px] rounded-full pointer-events-none"
           style={{ background: `radial-gradient(circle, ${FOREST_SOFT} 0%, transparent 70%)`, filter: "blur(40px)" }} />
      <div className="absolute -bottom-32 -left-32 w-[420px] h-[420px] rounded-full pointer-events-none"
           style={{ background: `radial-gradient(circle, ${FOREST_SOFT} 0%, transparent 70%)`, filter: "blur(40px)" }} />

      <div className="relative z-10 max-w-6xl mx-auto px-6 md:px-10">
        <div className="flex items-center gap-4 mb-6">
          <span className="text-xs uppercase tracking-[0.3em] font-bold whitespace-nowrap" style={{ color: FOREST }}>
            How it works · the full path
          </span>
          <span aria-hidden className="flex-1 h-px max-w-[240px]" style={{ background: `linear-gradient(90deg, ${FOREST}80, transparent)` }} />
        </div>

        <div className="grid lg:grid-cols-12 gap-8 items-center">
          <div className="lg:col-span-8">
            <div className="relative">
              <div className="relative aspect-video w-full bg-ink border border-ink/15 overflow-hidden shadow-[0_30px_80px_-20px_rgba(31,79,47,0.35)]">
                <div className="absolute inset-2 border z-[1] pointer-events-none" style={{ borderColor: `${CREAM}22` }} />
                {sceneNode}

                <div className="absolute top-3 left-3 z-30 flex items-center gap-1.5 text-[9px] uppercase tracking-[0.25em] font-bold text-white/65 bg-ink/40 backdrop-blur-md px-2 py-1">
                  <Volume2 className="w-3 h-3" /> Silent
                </div>

                <motion.div
                  key={scene.id}
                  initial={{ opacity: 0, y: 14 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.5, delay: 0.15 }}
                  className="absolute bottom-0 left-0 right-0 z-30 px-4 md:px-6 py-3 md:py-4 bg-gradient-to-t from-ink/90 via-ink/65 to-transparent"
                >
                  <div className="text-[10px] uppercase tracking-[0.3em] font-bold flex items-center gap-2" style={{ color: CREAM, opacity: 0.85 }}>
                    <scene.Icon className="w-3.5 h-3.5" />
                    Step {sceneIdx + 1} / {SCENES.length} · {scene.label}
                  </div>
                  <div className="font-barlow font-black text-white text-xl md:text-3xl leading-tight mt-1">
                    {scene.title}
                  </div>
                  <div className="text-white/75 text-sm md:text-base mt-1">{scene.caption}</div>
                </motion.div>
              </div>

              <div className="mt-3 flex items-center gap-3">
                <button
                  data-testid="walkthrough-play-pause"
                  onClick={() => setIsPlaying((p) => !p)}
                  className="w-10 h-10 flex items-center justify-center bg-ink text-white hover:bg-forest transition-colors flex-shrink-0"
                  aria-label={isPlaying ? "Pause" : "Play"}
                >
                  {isPlaying ? <Pause className="w-4 h-4" /> : <Play className="w-4 h-4 ml-0.5" />}
                </button>
                <button
                  data-testid="walkthrough-restart"
                  onClick={() => { setSceneIdx(0); setProgress(0); setIsPlaying(true); }}
                  className="w-10 h-10 flex items-center justify-center border border-ink/15 text-ink/70 hover:text-ink hover:border-ink/40 transition-colors flex-shrink-0"
                  aria-label="Restart"
                >
                  <RotateCcw className="w-4 h-4" />
                </button>
                <div className="flex-1 flex gap-1">
                  {SCENES.map((s, i) => (
                    <button
                      key={s.id}
                      data-testid={`walkthrough-jump-${s.id}`}
                      onClick={() => { setSceneIdx(i); setProgress(0); setIsPlaying(true); }}
                      className="flex-1 group relative"
                      aria-label={`Jump to ${s.label}`}
                    >
                      <div className="h-1 bg-ink/10 overflow-hidden">
                        <motion.div
                          className="h-full origin-left"
                          style={{ background: FOREST }}
                          animate={{ scaleX: i < sceneIdx ? 1 : i === sceneIdx ? progress : 0 }}
                          transition={{ duration: 0.1 }}
                        />
                      </div>
                      <div className="mt-1.5 text-[9px] uppercase tracking-[0.18em] font-bold text-ink/45 group-hover:text-ink/85 transition-colors text-left">
                        {s.label}
                      </div>
                    </button>
                  ))}
                </div>
              </div>
            </div>
          </div>

          <div className="lg:col-span-4 lg:pl-2">
            <h2 className="font-barlow font-black uppercase text-3xl sm:text-4xl md:text-5xl leading-[0.95] tracking-tighter text-ink">
              From any video,
              <br />
              <span className="font-serif-italic normal-case font-normal lowercase tracking-normal" style={{ color: FOREST }}>
                to scout-ready truth.
              </span>
            </h2>
            <p className="mt-5 text-ink/70 text-base leading-relaxed">
              Upload from any device or paste a Veo / YouTube link. Pro Scout Intelligence + real human scouts. A full PDF and a living progress chart any coach respects.
            </p>

            <div className="mt-6 grid grid-cols-3 gap-2">
              {[
                { Icon: Sparkles, k: "47", l: "metrics" },
                { Icon: Eye, k: "3", l: "scouts" },
                { Icon: FileText, k: "12", l: "PDF pages" },
              ].map((s, i) => (
                <motion.div
                  key={i}
                  whileHover={{ y: -2 }}
                  className="border border-ink/10 bg-white px-2 py-2.5 text-center"
                >
                  <s.Icon className="w-3.5 h-3.5 mx-auto" style={{ color: FOREST }} />
                  <div className="font-barlow font-black text-ink text-lg leading-none mt-1">{s.k}</div>
                  <div className="text-[8px] uppercase tracking-widest font-bold text-ink/55 mt-0.5">{s.l}</div>
                </motion.div>
              ))}
            </div>

            <Link
              to={startHref}
              data-testid="walkthrough-cta-start"
              className="mt-6 inline-flex w-full items-center justify-center gap-2 text-white font-barlow font-black uppercase tracking-widest text-sm py-3.5 transition-colors"
              style={{ background: FOREST }}
              onMouseEnter={(e) => (e.currentTarget.style.background = FOREST_DEEP)}
              onMouseLeave={(e) => (e.currentTarget.style.background = FOREST)}
            >
              Start free preview
              <ArrowRight className="w-4 h-4" />
            </Link>

            <a
              href="#what-you-get"
              data-testid="walkthrough-cta-sample"
              className="mt-3 flex items-center justify-center gap-2 text-[11px] uppercase tracking-[0.25em] font-bold text-ink/55 hover:text-ink transition-colors"
            >
              See inside the report
              <ArrowRight className="w-3.5 h-3.5" />
            </a>

            <div className="mt-6 pt-5 border-t border-ink/10 flex items-center justify-between text-[10px] uppercase tracking-[0.22em] font-bold text-ink/45">
              <span>Full report · ${price}</span>
              <span>No subscription</span>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
