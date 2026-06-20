import React, { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { motion, AnimatePresence, useReducedMotion } from "framer-motion";
import {
  Play, Pause, RotateCcw, Upload, MousePointer2, Sparkles,
  Eye, FileText, TrendingUp, ArrowRight, Volume2, VolumeX, CheckCircle2,
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

// cinematic stadium-night background for the Upload scene — single floodlight in mist/rain
const STADIUM_NIGHT_IMG =
  "https://images.unsplash.com/photo-1431324155629-1a6deb1dec8d?w=1600&q=85&auto=format&fit=crop";

// single male scout portrait (the only person in the Scout scene)
const SCOUT_PORTRAIT_IMG =
  "https://images.unsplash.com/photo-1500648767791-00dcc994a43e?w=900&q=85&auto=format&fit=crop";

const SCENES = [
  { id: "upload",   duration: 7400, label: "Upload",  title: "Upload from anywhere",                       caption: "Phone, iPad, computer — or paste a Veo / YouTube link.",         Icon: Upload },
  { id: "mark",     duration: 7600, label: "Mark",    title: "Tap your player ten times",                  caption: "No AI guessing — you stay in control.",                          Icon: MousePointer2 },
  { id: "analyze",  duration: 7600, label: "Analyze", title: "Pro Scout Intelligence builds your report",  caption: "6 pillars · 47 metrics · one honest score.",                     Icon: Sparkles },
  { id: "scout",    duration: 7000, label: "Scouts",  title: "Real scouts watch your clip",                caption: "Human eyes on every movement — not just data.",                  Icon: Eye },
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
   Scene 1 — UPLOAD (real upload-in-progress: 4 devices uploading in parallel)
============================================================================ */

// Each device has its own video thumbnail + upload progress timing
const DEVICES = [
  { id: "phone",    Icon: Smartphone, label: "PHONE",    crop: "52% 40%", barStart: 1.6, barEnd: 4.4 },
  { id: "ipad",     Icon: Tablet,     label: "iPAD",     crop: "54% 50%", barStart: 1.9, barEnd: 4.7 },
  { id: "computer", Icon: Monitor,    label: "COMPUTER", crop: "56% 55%", barStart: 2.2, barEnd: 5.0 },
  { id: "veo",      Icon: Youtube,    label: "VEO LINK", crop: "50% 45%", barStart: 2.5, barEnd: 5.3 },
];

const UploadScene = () => (
  <motion.div
    key="upload"
    className="absolute inset-0 overflow-hidden"
    initial={{ opacity: 0 }}
    animate={{ opacity: 1 }}
    exit={{ opacity: 0, filter: "blur(10px)" }}
    transition={{ duration: 0.6 }}
  >
    {/* cinematic stadium night backdrop */}
    <div className="absolute inset-0">
      <motion.img
        src={STADIUM_NIGHT_IMG}
        alt=""
        className="absolute inset-0 w-full h-full object-cover"
        initial={{ scale: 1.18 }}
        animate={{ scale: 1.0 }}
        transition={{ duration: 8, ease: "easeOut" }}
      />
      <div className="absolute inset-0" style={{
        background: `radial-gradient(ellipse at 50% 45%, rgba(0,0,0,0.3) 0%, rgba(0,0,0,0.88) 100%)`,
      }} />
      <div className="absolute inset-0" style={{
        background: `radial-gradient(ellipse at 50% 38%, rgba(204,255,200,0.16) 0%, transparent 55%)`,
      }} />
    </div>

    <ParticleField tone="light" density={36} />

    {/* opening title (briefly) */}
    <motion.div
      className="absolute inset-0 z-10 flex flex-col items-center justify-center px-6 text-center pointer-events-none"
      initial={{ opacity: 1 }}
      animate={{ opacity: [1, 1, 0] }}
      transition={{ duration: 1.6, times: [0, 0.7, 1] }}
    >
      <div className="font-barlow font-black text-white text-2xl sm:text-3xl md:text-5xl leading-[0.92] tracking-tight drop-shadow-2xl">
        <StaggerText text="Uploading from anywhere" delay={0.1} charDelay={0.02} />
      </div>
    </motion.div>

    {/* 4 device cards — each showing a video preview + upload progress */}
    {DEVICES.map((d, i) => (
      <DeviceUploadCard key={d.id} device={d} index={i} />
    ))}

    {/* light streaks flying from each device card into the central dropzone */}
    <svg className="absolute inset-0 w-full h-full pointer-events-none z-[2]" viewBox="0 0 100 56" preserveAspectRatio="none">
      {[
        { x1: 18, y1: 14, x2: 50, y2: 30 },
        { x1: 82, y1: 14, x2: 50, y2: 30 },
        { x1: 18, y1: 46, x2: 50, y2: 30 },
        { x1: 82, y1: 46, x2: 50, y2: 30 },
      ].map((s, i) => (
        <motion.line
          key={i}
          x1={s.x1} y1={s.y1} x2={s.x2} y2={s.y2}
          stroke="rgba(204,255,200,0.7)"
          strokeWidth="0.18"
          strokeDasharray="2 2"
          initial={{ pathLength: 0, opacity: 0 }}
          animate={{ pathLength: 1, opacity: [0, 1, 0.7, 1, 0.7, 1] }}
          transition={{ delay: 2.0 + i * 0.12, duration: 4 }}
        />
      ))}
    </svg>

    {/* streams of small data dots flowing along the connector lines */}
    {[0, 1, 2, 3].map((i) => (
      <DataStream key={i} index={i} />
    ))}

    {/* CENTER — receiving dropzone with master progress */}
    <motion.div
      initial={{ scale: 0.88, opacity: 0 }}
      animate={{ scale: 1, opacity: 1 }}
      transition={{ delay: 1.4, duration: 0.7, ease: [0.16, 1, 0.3, 1] }}
      className="absolute left-1/2 top-[44%] -translate-x-1/2 -translate-y-1/2 z-10 w-[42%] md:w-[34%] max-w-[280px] aspect-[16/9] flex items-center justify-center backdrop-blur-md"
      style={{
        background: "rgba(20,57,35,0.6)",
        border: "1.5px dashed rgba(204,255,200,0.8)",
        boxShadow: `0 30px 80px -10px rgba(0,0,0,0.85), 0 0 50px rgba(204,255,200,0.15) inset`,
      }}
    >
      {/* pulse */}
      <motion.div
        className="absolute inset-0 pointer-events-none"
        style={{ boxShadow: `0 0 60px rgba(204,255,200,0.55)` }}
        animate={{ opacity: [0.2, 0.6, 0.2] }}
        transition={{ delay: 1.6, duration: 2, repeat: Infinity }}
      />

      {/* corner brackets */}
      {["top-0 left-0 border-t-2 border-l-2","top-0 right-0 border-t-2 border-r-2","bottom-0 left-0 border-b-2 border-l-2","bottom-0 right-0 border-b-2 border-r-2"].map((p, i) => (
        <span key={i} aria-hidden className={`absolute ${p} w-4 h-4`} style={{ borderColor: "rgba(204,255,200,0.95)" }} />
      ))}

      <div className="relative z-10 flex flex-col items-center gap-1.5 px-2">
        <motion.div
          animate={{ y: [0, -4, 0] }}
          transition={{ delay: 1.6, duration: 1.5, repeat: Infinity, ease: "easeInOut" }}
        >
          <Upload className="w-5 h-5 md:w-7 md:h-7" style={{ color: "#CCFF99" }} strokeWidth={1.8} />
        </motion.div>
        <MasterStatus />
        {/* master progress bar */}
        <div className="w-full h-1 bg-white/15 overflow-hidden mt-1.5">
          <motion.div
            initial={{ width: 0 }}
            animate={{ width: "100%" }}
            transition={{ delay: 1.8, duration: 3.6, ease: "linear" }}
            className="h-full"
            style={{ background: "linear-gradient(90deg, rgba(204,255,200,1), #1F4F2F)" }}
          />
        </div>
      </div>
    </motion.div>

    {/* VIDEO ACCEPTED badge */}
    <motion.div
      initial={{ opacity: 0, y: 12, scale: 0.9 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ delay: 5.6, type: "spring", stiffness: 200, damping: 14 }}
      className="absolute left-1/2 top-[72%] -translate-x-1/2 z-20 flex items-center gap-2 px-4 py-2 bg-white text-[13px] md:text-[15px] uppercase tracking-[0.3em] font-bold"
      style={{ color: FOREST }}
    >
      <CheckCircle2 className="w-4 h-4 md:w-5 md:h-5" />
      All sources received
      <motion.span
        className="absolute -inset-1 pointer-events-none"
        style={{ boxShadow: `0 0 36px rgba(204,255,200,0.9)` }}
        animate={{ opacity: [0, 1, 0] }}
        transition={{ delay: 5.7, duration: 1.4 }}
      />
    </motion.div>

    <BrandMark />
  </motion.div>
);

/* Live master upload status text that rotates through devices */
const MasterStatus = () => {
  const labels = [
    { t: 1.9, msg: "Uploading from PHONE..." },
    { t: 2.6, msg: "Uploading from iPAD..." },
    { t: 3.3, msg: "Uploading from COMPUTER..." },
    { t: 4.0, msg: "Pulling from VEO LINK..." },
    { t: 4.8, msg: "Merging sources..." },
    { t: 5.4, msg: "Ready ✓" },
  ];
  const [idx, setIdx] = useState(0);
  useEffect(() => {
    const timers = labels.map((l, i) =>
      setTimeout(() => setIdx(i), l.t * 1000)
    );
    return () => timers.forEach(clearTimeout);
  }, []);
  return (
    <div className="text-[10px] md:text-[12px] uppercase tracking-[0.25em] font-bold text-white/95 leading-tight">
      {labels[idx].msg}
    </div>
  );
};

/* Card showing one source device "uploading" its clip */
const DeviceUploadCard = ({ device, index }) => {
  // Position in corners — mobile keeps them at corners but tighter
  const positions = [
    "top-[8%] left-[4%] md:top-[12%] md:left-[8%]",
    "top-[8%] right-[4%] md:top-[12%] md:right-[8%]",
    "bottom-[24%] left-[4%] md:bottom-[26%] md:left-[8%]",
    "bottom-[24%] right-[4%] md:bottom-[26%] md:right-[8%]",
  ];
  const { Icon, label, crop, barStart, barEnd } = device;

  return (
    <motion.div
      className={`absolute ${positions[index]} z-[15] w-[80px] md:w-[110px] pointer-events-none`}
      initial={{ opacity: 0, y: 30, scale: 0.7 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ delay: 0.8 + index * 0.12, type: "spring", stiffness: 180, damping: 14 }}
    >
      {/* device header */}
      <div className="flex items-center gap-1.5 mb-1 bg-ink/65 backdrop-blur-md px-2 py-1">
        <Icon className="w-3.5 h-3.5 md:w-4 md:h-4" style={{ color: "#CCFF99" }} strokeWidth={1.8} />
        <span className="text-[9px] md:text-[11px] uppercase tracking-[0.22em] font-bold text-white/95">{label}</span>
      </div>
      {/* video thumbnail */}
      <div className="relative aspect-video overflow-hidden border border-white/30 shadow-2xl">
        <div className="w-full h-full bg-no-repeat" style={{
          backgroundImage: `url(${PLAYER_IMG})`,
          backgroundPosition: crop,
          backgroundSize: "240% auto",
        }} />
        {/* scanning sweep while uploading */}
        <motion.div
          initial={{ top: "-100%" }}
          animate={{ top: "100%" }}
          transition={{ delay: barStart, duration: barEnd - barStart, ease: "linear", repeat: 1 }}
          className="absolute left-0 right-0 h-px z-10"
          style={{ background: "rgba(204,255,200,0.9)", boxShadow: "0 0 10px rgba(204,255,200,0.9)" }}
        />
        {/* live dot */}
        <motion.div
          className="absolute top-1 left-1 w-1.5 h-1.5 rounded-full bg-red-500"
          animate={{ opacity: [1, 0.3, 1] }}
          transition={{ duration: 0.8, repeat: Infinity }}
        />
      </div>
      {/* mini progress bar + percentage */}
      <div className="mt-1 flex items-center gap-1.5">
        <div className="flex-1 h-0.5 bg-white/15">
          <motion.div
            initial={{ width: 0 }}
            animate={{ width: "100%" }}
            transition={{ delay: barStart, duration: barEnd - barStart, ease: "easeInOut" }}
            className="h-full"
            style={{ background: "#CCFF99" }}
          />
        </div>
        <DevicePercent start={barStart} end={barEnd} />
      </div>
    </motion.div>
  );
};

/* Live count-up percentage matching the progress bar */
const DevicePercent = ({ start, end }) => {
  const [n, setN] = useState(0);
  useEffect(() => {
    const startMs = start * 1000;
    const durMs = (end - start) * 1000;
    const t = setTimeout(() => {
      const t0 = performance.now();
      const tick = (now) => {
        const p = Math.min((now - t0) / durMs, 1);
        setN(Math.round(p * 100));
        if (p < 1) requestAnimationFrame(tick);
      };
      requestAnimationFrame(tick);
    }, startMs);
    return () => clearTimeout(t);
  }, [start, end]);
  return (
    <span className="text-[10px] md:text-[12px] uppercase font-bold tracking-wider w-7 text-right" style={{ color: "#CCFF99" }}>
      {n}%
    </span>
  );
};

/* Stream of small data dots flowing along the connector line from a device to dropzone */
const DataStream = ({ index }) => {
  const corners = [
    { fromX: 18, fromY: 14 },
    { fromX: 82, fromY: 14 },
    { fromX: 18, fromY: 46 },
    { fromX: 82, fromY: 46 },
  ];
  const c = corners[index];
  const targetX = 50, targetY = 30;
  return (
    <div className="absolute inset-0 pointer-events-none z-[3]">
      {Array.from({ length: 5 }).map((_, i) => (
        <motion.span
          key={i}
          className="absolute rounded-full"
          style={{ width: 4, height: 4, background: "#CCFF99", boxShadow: "0 0 8px #CCFF99" }}
          initial={{
            left: `${c.fromX}%`,
            top: `${c.fromY}%`,
            opacity: 0,
          }}
          animate={{
            left: [`${c.fromX}%`, `${targetX}%`],
            top: [`${c.fromY}%`, `${targetY}%`],
            opacity: [0, 0.9, 0.9, 0],
            scale: [0.6, 1, 1, 0.5],
          }}
          transition={{
            delay: 2.0 + index * 0.2 + i * 0.45,
            duration: 1.4,
            repeat: 2,
            ease: "easeIn",
          }}
        />
      ))}
    </div>
  );
};

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
        className="font-barlow font-black text-white text-2xl md:text-3xl bg-ink/55 backdrop-blur-md px-3.5 py-1"
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
      <div className="font-barlow font-black text-white text-5xl md:text-6xl tracking-widest" style={{ textShadow: `0 0 24px ${CREAM}` }}>
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
          <div className="text-[11px] md:text-[12px] uppercase tracking-[0.32em] font-bold text-ink/65">Scout Score</div>
          <div className="font-barlow font-black text-6xl md:text-7xl mt-0.5 leading-none" style={{ color: FOREST }}>
            <CountUp from={0} to={78} delay={2.7} duration={1.5} />
            <span className="text-ink/30 text-3xl md:text-4xl ml-1">/100</span>
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
   Scene 4 — SCOUT REVIEW (tactics board · one scout looking · no club names)
============================================================================ */
const ScoutReviewScene = () => (
  <motion.div
    key="scout"
    className="absolute inset-0 overflow-hidden"
    style={{ background: `linear-gradient(135deg, #061310 0%, #0E2519 50%, #050908 100%)` }}
    initial={{ opacity: 0 }}
    animate={{ opacity: 1 }}
    exit={{ opacity: 0, filter: "blur(10px)" }}
    transition={{ duration: 0.6 }}
  >
    <ParticleField tone="light" density={26} />

    {/* tactical floating chips — no clubs/leagues, just tactical concepts */}
    <FloatingChips
      tone="light"
      items={[
        { t: "POSITIONING", x: 50, y: 10 },
        { t: "MOVEMENT", x: 8, y: 90 },
        { t: "DECISIONS", x: 85, y: 90 },
        { t: "VISION", x: 30, y: 88 },
      ]}
    />

    {/* moody spotlight from top */}
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 0.6 }}
      transition={{ duration: 1.2 }}
      className="absolute -top-10 left-1/2 -translate-x-1/2 w-[130%] h-[80%] pointer-events-none"
      style={{ background: `radial-gradient(ellipse at top, rgba(204,255,200,0.16) 0%, transparent 70%)` }}
    />

    {/* eyebrow */}
    <motion.div
      initial={{ opacity: 0, y: -10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.3 }}
      className="relative z-10 pt-5 px-6 text-center"
    >
      <div className="inline-flex items-center gap-2 text-[11px] md:text-[13px] uppercase tracking-[0.35em] font-bold text-white/85">
        <Eye className="w-3.5 h-3.5" /> Tactical scout review
      </div>
      <div className="mt-2 font-barlow font-black text-white text-3xl md:text-4xl leading-tight">
        <StaggerText text="Reviewed by real scouts." delay={0.5} />
      </div>
    </motion.div>

    <div className="absolute inset-x-0 bottom-20 md:bottom-24 top-[30%] flex items-stretch z-10 px-2 md:px-6 gap-2 md:gap-6">
      {/* LEFT — one scout, side profile, looking right at the board */}
      <ScoutFigure />

      {/* RIGHT — glass tactics board */}
      <TacticsBoard />
    </div>

    <BrandMark />
  </motion.div>
);

/* The single scout — one human looking at the players on the board */
const ScoutFigure = () => (
  <motion.div
    initial={{ opacity: 0, x: -30 }}
    animate={{ opacity: 1, x: 0 }}
    transition={{ delay: 0.8, duration: 0.9, ease: [0.16, 1, 0.3, 1] }}
    className="relative flex-shrink-0 w-[28%] md:w-[260px] h-full"
  >
    {/* portrait — desaturated, dramatic side-light */}
    <div className="relative w-full h-full overflow-hidden">
      <img
        src={SCOUT_PORTRAIT_IMG}
        alt=""
        className="w-full h-full object-cover"
        style={{
          objectPosition: "30% center",
          filter: "grayscale(0.6) contrast(1.05) brightness(0.85)",
        }}
      />
      {/* gradient overlay so scout fades into the dark background */}
      <div className="absolute inset-0" style={{
        background: "linear-gradient(90deg, transparent 0%, transparent 40%, rgba(6,19,16,0.9) 95%)",
      }} />
      {/* volt rim light from right */}
      <div className="absolute inset-y-0 right-0 w-3" style={{
        background: "linear-gradient(90deg, transparent 0%, rgba(204,255,200,0.45) 100%)",
        filter: "blur(4px)",
      }} />
      {/* watching indicator */}
      <motion.div
        initial={{ opacity: 0, scale: 0 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ delay: 1.8, type: "spring", stiffness: 200 }}
        className="absolute top-3 left-3 flex items-center gap-1.5 bg-ink/80 backdrop-blur text-white text-[8px] uppercase tracking-[0.25em] font-bold px-2 py-1"
      >
        <motion.span
          className="w-1 h-1 rounded-full bg-red-500"
          animate={{ opacity: [1, 0.3, 1] }}
          transition={{ duration: 0.9, repeat: Infinity }}
        />
        Watching
      </motion.div>
    </div>

    {/* gaze line — a subtle light ray from scout's eyes into the board */}
    <svg className="absolute top-1/2 -right-2 w-12 h-px pointer-events-none z-10" viewBox="0 0 100 1" preserveAspectRatio="none">
      <motion.line
        x1="0" y1="0.5" x2="100" y2="0.5"
        stroke="rgba(204,255,200,0.7)"
        strokeWidth="0.6"
        strokeDasharray="3 3"
        initial={{ pathLength: 0, opacity: 0 }}
        animate={{ pathLength: 1, opacity: 0.85 }}
        transition={{ delay: 2.3, duration: 0.8 }}
      />
    </svg>
  </motion.div>
);

/* Glass tactics board — animated half-pitch with player dots and arrows */
const TacticsBoard = () => {
  // 11 player positions on a half-pitch (right-attacking)
  // coordinates in viewBox 0..100 x, 0..120 y (taller for full pitch)
  const PLAYERS = [
    { x: 50,  y: 110, role: "GK" },
    { x: 18,  y: 88,  role: "LB" },
    { x: 40,  y: 92,  role: "CB" },
    { x: 60,  y: 92,  role: "CB" },
    { x: 82,  y: 88,  role: "RB" },
    { x: 30,  y: 62,  role: "LCM" },
    { x: 50,  y: 70,  role: "CDM" },
    { x: 70,  y: 62,  role: "RCM" },
    { x: 22,  y: 32,  role: "LW",  highlight: true },
    { x: 50,  y: 22,  role: "ST",  highlight: true },
    { x: 78,  y: 32,  role: "RW" },
  ];

  return (
    <motion.div
      initial={{ opacity: 0, x: 30 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ delay: 1.3, duration: 0.9, ease: [0.16, 1, 0.3, 1] }}
      className="relative flex-1 backdrop-blur-md shadow-2xl"
      style={{
        background: "linear-gradient(180deg, rgba(255,255,255,0.04) 0%, rgba(31,79,47,0.18) 100%)",
        border: "1px solid rgba(204,255,200,0.35)",
        boxShadow: "0 30px 60px -10px rgba(0,0,0,0.6), 0 0 0 1px rgba(255,255,255,0.05) inset",
      }}
    >
      {/* top label */}
      <div className="absolute top-2 left-3 right-3 flex items-center justify-between z-10">
        <div className="text-[8px] uppercase tracking-[0.3em] font-bold text-white/80">
          Tactics board · live
        </div>
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 2.4 }}
          className="text-[14px] md:text-[18px] uppercase tracking-[0.2em] font-barlow font-black"
          style={{ color: "#CCFF99" }}
        >
          4-3-3
        </motion.div>
      </div>

      {/* glass pitch SVG */}
      <svg viewBox="0 0 100 120" className="w-full h-full" preserveAspectRatio="xMidYMid meet">
        {/* pitch outline */}
        <motion.rect
          x="6" y="6" width="88" height="108"
          fill="none"
          stroke="rgba(204,255,200,0.65)"
          strokeWidth="0.35"
          initial={{ pathLength: 0 }}
          animate={{ pathLength: 1 }}
          transition={{ delay: 1.5, duration: 0.9 }}
        />
        {/* midline */}
        <motion.line
          x1="6" y1="60" x2="94" y2="60"
          stroke="rgba(204,255,200,0.55)"
          strokeWidth="0.3"
          initial={{ pathLength: 0 }}
          animate={{ pathLength: 1 }}
          transition={{ delay: 1.7, duration: 0.6 }}
        />
        {/* center circle */}
        <motion.circle
          cx="50" cy="60" r="9"
          fill="none"
          stroke="rgba(204,255,200,0.55)"
          strokeWidth="0.3"
          initial={{ pathLength: 0 }}
          animate={{ pathLength: 1 }}
          transition={{ delay: 1.8, duration: 0.7 }}
        />
        <circle cx="50" cy="60" r="0.6" fill="rgba(204,255,200,0.8)" />

        {/* penalty boxes */}
        <motion.rect
          x="28" y="6" width="44" height="14" fill="none"
          stroke="rgba(204,255,200,0.45)" strokeWidth="0.3"
          initial={{ pathLength: 0 }}
          animate={{ pathLength: 1 }}
          transition={{ delay: 1.9, duration: 0.6 }}
        />
        <motion.rect
          x="28" y="100" width="44" height="14" fill="none"
          stroke="rgba(204,255,200,0.45)" strokeWidth="0.3"
          initial={{ pathLength: 0 }}
          animate={{ pathLength: 1 }}
          transition={{ delay: 1.95, duration: 0.6 }}
        />

        {/* tactical arrows (movement) drawn after pitch */}
        <motion.path
          d="M 22 32 Q 35 24 50 22"
          fill="none"
          stroke="rgba(204,255,200,0.95)"
          strokeWidth="0.5"
          strokeLinecap="round"
          strokeDasharray="2 1.5"
          initial={{ pathLength: 0, opacity: 0 }}
          animate={{ pathLength: 1, opacity: 1 }}
          transition={{ delay: 3.0, duration: 0.9 }}
        />
        <motion.path
          d="M 78 32 Q 65 24 50 22"
          fill="none"
          stroke="rgba(204,255,200,0.95)"
          strokeWidth="0.5"
          strokeLinecap="round"
          strokeDasharray="2 1.5"
          initial={{ pathLength: 0, opacity: 0 }}
          animate={{ pathLength: 1, opacity: 1 }}
          transition={{ delay: 3.1, duration: 0.9 }}
        />
        {/* run-in arrow into the box */}
        <motion.path
          d="M 30 62 Q 38 45 50 35"
          fill="none"
          stroke="rgba(255,255,255,0.7)"
          strokeWidth="0.4"
          strokeLinecap="round"
          strokeDasharray="1.5 1"
          initial={{ pathLength: 0, opacity: 0 }}
          animate={{ pathLength: 1, opacity: 1 }}
          transition={{ delay: 3.4, duration: 0.9 }}
        />

        {/* arrowheads */}
        <motion.polygon
          points="50,21 48,23 52,23"
          fill="rgba(204,255,200,0.95)"
          initial={{ opacity: 0, scale: 0 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ delay: 3.95, type: "spring", stiffness: 200 }}
        />

        {/* players — animated in with stagger */}
        {PLAYERS.map((p, i) => (
          <motion.g key={i}
            initial={{ opacity: 0, scale: 0 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ delay: 2.1 + i * 0.06, type: "spring", stiffness: 200, damping: 14 }}
          >
            <circle
              cx={p.x} cy={p.y}
              r={p.highlight ? 2.2 : 1.8}
              fill={p.highlight ? "#CCFF99" : "rgba(255,255,255,0.95)"}
              stroke={p.highlight ? "#CCFF99" : "rgba(204,255,200,0.7)"}
              strokeWidth="0.3"
            />
            {p.highlight && (
              <motion.circle
                cx={p.x} cy={p.y} r="2.4"
                fill="none"
                stroke="#CCFF99"
                strokeWidth="0.3"
                animate={{ r: [2.4, 5.5], opacity: [0.9, 0] }}
                transition={{ delay: 3.6 + i * 0.1, duration: 1.6, repeat: Infinity, repeatDelay: 0.4 }}
              />
            )}
            <text
              x={p.x}
              y={p.y + 0.7}
              fontSize="1.4"
              fill={p.highlight ? "#061310" : "#061310"}
              textAnchor="middle"
              fontWeight="900"
              fontFamily="Barlow Condensed, sans-serif"
            >
              {p.highlight ? "✓" : ""}
            </text>
          </motion.g>
        ))}
      </svg>

      {/* bottom info strip */}
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 4.2 }}
        className="absolute bottom-2 left-3 right-3 flex items-center justify-between text-[8px] uppercase tracking-[0.25em] font-bold text-white/70"
      >
        <span>Frame · 01:12</span>
        <span style={{ color: "#CCFF99" }}>✓ Reviewed</span>
      </motion.div>
    </motion.div>
  );
};

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

    {/* fan of PDF pages — tighter on mobile */}
    <div className="relative z-10 flex items-center justify-center w-full pb-24" style={{ perspective: 1400 }}>
      <PdfPage delay={0.3} rotate={-12} translateX={-118} translateXMobile={-72} z={0} pageType="cover" />
      <PdfPage delay={0.55} rotate={-5} translateX={-50} translateXMobile={-26} z={1} pageType="radar" />
      <PdfPage delay={0.8} rotate={3} translateX={26} translateXMobile={16} z={2} pageType="strengths" />
      <PdfPage delay={1.05} rotate={11} translateX={94} translateXMobile={56} z={3} pageType="growth" />
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

const PdfPage = ({ delay, rotate, translateX, translateXMobile, z, pageType }) => {
  const [isMobile, setIsMobile] = useState(false);
  useEffect(() => {
    const check = () => setIsMobile(window.innerWidth < 768);
    check();
    window.addEventListener("resize", check);
    return () => window.removeEventListener("resize", check);
  }, []);
  const tx = isMobile ? (translateXMobile ?? translateX) : translateX;
  return (
    <motion.div
      className="absolute"
      initial={{ opacity: 0, y: 80, rotate: rotate - 6, x: tx, scale: 0.7 }}
      animate={{ opacity: 1, y: 0, rotate, x: tx, scale: 1 }}
      transition={{ delay, type: "spring", stiffness: 110, damping: 14 }}
      style={{ zIndex: z }}
    >
      <div className="w-[100px] sm:w-[130px] md:w-[180px] aspect-[3/4] bg-white shadow-2xl border border-ink/12 overflow-hidden relative">
        <PdfPageContent type={pageType} delay={delay + 0.5} />
      </div>
    </motion.div>
  );
};

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
      className="relative z-10 pt-5 px-5 flex items-center gap-2 text-[11px] md:text-[13px] uppercase tracking-[0.3em] font-bold"
      style={{ color: FOREST }}
    >
      <TrendingUp className="w-3.5 h-3.5" /> Trajectory · 3 months
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
            <div className="text-[10px] md:text-[12px] uppercase tracking-[0.22em] font-bold text-ink/55">Overall score</div>
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: 2.0 }}
              className="text-base md:text-xl font-barlow font-black"
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
          <div className="text-[11px] md:text-[13px] uppercase tracking-[0.3em] font-bold mb-1.5" style={{ color: FOREST }}>
            What changed
          </div>
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
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
                className="text-[10px] md:text-[12px] font-bold uppercase tracking-wider"
                style={{ color: FOREST }}
              >
                {d.k} <span className="font-barlow font-black text-[13px] md:text-[16px]">{d.v}</span>
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
   Sound design cues — Web Audio API synthesis (layered over the music)
   Plays only when sound is on. No external SFX files.
============================================================================ */
const useSFX = (enabled) => {
  const enabledRef = useRef(enabled);
  enabledRef.current = enabled;
  const ctxRef = useRef(null);

  const getCtx = React.useCallback(() => {
    if (typeof window === "undefined") return null;
    if (!ctxRef.current) {
      try {
        const AC = window.AudioContext || window.webkitAudioContext;
        if (AC) ctxRef.current = new AC();
      } catch (e) { /* noop */ }
    }
    if (ctxRef.current && ctxRef.current.state === "suspended") {
      try { ctxRef.current.resume(); } catch (e) { /* noop */ }
    }
    return ctxRef.current;
  }, []);

  /** Low cinematic "thunk" — sub bass impact, ~0.5s. For the score reveal. */
  const thunk = React.useCallback(() => {
    if (!enabledRef.current) return;
    const ctx = getCtx();
    if (!ctx) return;
    const now = ctx.currentTime;
    const osc = ctx.createOscillator();
    osc.type = "sine";
    osc.frequency.setValueAtTime(140, now);
    osc.frequency.exponentialRampToValueAtTime(45, now + 0.18);
    const gain = ctx.createGain();
    gain.gain.setValueAtTime(0, now);
    gain.gain.linearRampToValueAtTime(0.55, now + 0.01);
    gain.gain.exponentialRampToValueAtTime(0.0001, now + 0.5);
    osc.connect(gain).connect(ctx.destination);
    osc.start(now);
    osc.stop(now + 0.55);
  }, [getCtx]);

  /** Mechanical "ka-chunk" — sharp click + low body thud. For LOCKED IN. */
  const kaChunk = React.useCallback(() => {
    if (!enabledRef.current) return;
    const ctx = getCtx();
    if (!ctx) return;
    const now = ctx.currentTime;

    // Transient click (noise burst, high-passed)
    const bufferSize = Math.floor(ctx.sampleRate * 0.04);
    const noiseBuffer = ctx.createBuffer(1, bufferSize, ctx.sampleRate);
    const data = noiseBuffer.getChannelData(0);
    for (let i = 0; i < bufferSize; i++) data[i] = (Math.random() * 2 - 1) * (1 - i / bufferSize);
    const noise = ctx.createBufferSource();
    noise.buffer = noiseBuffer;
    const hp = ctx.createBiquadFilter();
    hp.type = "highpass";
    hp.frequency.value = 1500;
    const ng = ctx.createGain();
    ng.gain.setValueAtTime(0.35, now);
    ng.gain.exponentialRampToValueAtTime(0.0001, now + 0.06);
    noise.connect(hp).connect(ng).connect(ctx.destination);
    noise.start(now);

    // Body — low sine drop 80 → 35 Hz
    const osc = ctx.createOscillator();
    osc.type = "sine";
    osc.frequency.setValueAtTime(80, now);
    osc.frequency.exponentialRampToValueAtTime(35, now + 0.2);
    const og = ctx.createGain();
    og.gain.setValueAtTime(0, now);
    og.gain.linearRampToValueAtTime(0.5, now + 0.015);
    og.gain.exponentialRampToValueAtTime(0.0001, now + 0.45);
    osc.connect(og).connect(ctx.destination);
    osc.start(now);
    osc.stop(now + 0.5);
  }, [getCtx]);

  /** Soft "whoosh" — filtered noise sweep ~0.6s. For scene transitions. */
  const whoosh = React.useCallback(() => {
    if (!enabledRef.current) return;
    const ctx = getCtx();
    if (!ctx) return;
    const now = ctx.currentTime;
    const dur = 0.6;
    const bufferSize = Math.floor(ctx.sampleRate * dur);
    const noiseBuffer = ctx.createBuffer(1, bufferSize, ctx.sampleRate);
    const data = noiseBuffer.getChannelData(0);
    for (let i = 0; i < bufferSize; i++) data[i] = Math.random() * 2 - 1;
    const noise = ctx.createBufferSource();
    noise.buffer = noiseBuffer;
    const filter = ctx.createBiquadFilter();
    filter.type = "bandpass";
    filter.Q.value = 0.9;
    filter.frequency.setValueAtTime(400, now);
    filter.frequency.exponentialRampToValueAtTime(3500, now + dur * 0.55);
    filter.frequency.exponentialRampToValueAtTime(800, now + dur);
    const gain = ctx.createGain();
    gain.gain.setValueAtTime(0, now);
    gain.gain.linearRampToValueAtTime(0.28, now + dur * 0.4);
    gain.gain.exponentialRampToValueAtTime(0.0001, now + dur);
    noise.connect(filter).connect(gain).connect(ctx.destination);
    noise.start(now);
    noise.stop(now + dur);
  }, [getCtx]);

  /** Tiny UI tick — for each manual tap ripple. */
  const tick = React.useCallback(() => {
    if (!enabledRef.current) return;
    const ctx = getCtx();
    if (!ctx) return;
    const now = ctx.currentTime;
    const osc = ctx.createOscillator();
    osc.type = "triangle";
    osc.frequency.setValueAtTime(1800, now);
    osc.frequency.exponentialRampToValueAtTime(900, now + 0.05);
    const gain = ctx.createGain();
    gain.gain.setValueAtTime(0.18, now);
    gain.gain.exponentialRampToValueAtTime(0.0001, now + 0.08);
    osc.connect(gain).connect(ctx.destination);
    osc.start(now);
    osc.stop(now + 0.1);
  }, [getCtx]);

  /** Three-note ascending sparkle — for "All sources received". */
  const sparkle = React.useCallback(() => {
    if (!enabledRef.current) return;
    const ctx = getCtx();
    if (!ctx) return;
    const now = ctx.currentTime;
    const notes = [523.25, 659.25, 783.99, 1046.5]; // C5 E5 G5 C6
    notes.forEach((freq, i) => {
      const t = now + i * 0.08;
      const osc = ctx.createOscillator();
      osc.type = "sine";
      osc.frequency.value = freq;
      const gain = ctx.createGain();
      gain.gain.setValueAtTime(0, t);
      gain.gain.linearRampToValueAtTime(0.22, t + 0.01);
      gain.gain.exponentialRampToValueAtTime(0.0001, t + 0.4);
      osc.connect(gain).connect(ctx.destination);
      osc.start(t);
      osc.stop(t + 0.45);
    });
  }, [getCtx]);

  return useMemo(
    () => ({ thunk, kaChunk, whoosh, tick, sparkle }),
    [thunk, kaChunk, whoosh, tick, sparkle]
  );
};

/* ============================================================================
   Main
============================================================================ */

// Royalty-free cinematic soundtrack (CC BY 4.0 — Kevin MacLeod · incompetech.com)
// "Rite of Passage" — epic cinematic ~11 min, plays seamlessly through the whole walkthrough loop
const SOUNDTRACK_URL = "https://incompetech.com/music/royalty-free/mp3-royaltyfree/Rite%20of%20Passage.mp3";
const SOUNDTRACK_NAME = "Rite of Passage";

export default function HowItWorksWalkthrough({ startHref = "/signup", price = 1 }) {
  const [sceneIdx, setSceneIdx] = useState(0);
  const [isPlaying, setIsPlaying] = useState(true);
  const [progress, setProgress] = useState(0);
  const [soundOn, setSoundOn] = useState(false);
  const reduceMotion = useReducedMotion();

  const sfx = useSFX(soundOn);
  const audioRef = useRef(null);
  const wrapRef = useRef(null);
  const [inView, setInView] = useState(true);
  const prevSceneIdxRef = useRef(0);

  useEffect(() => {
    if (!wrapRef.current || typeof IntersectionObserver === "undefined") return;
    const obs = new IntersectionObserver(
      ([e]) => setInView(e.isIntersecting),
      { threshold: 0.3 }
    );
    obs.observe(wrapRef.current);
    return () => obs.disconnect();
  }, []);

  // pause animation when off-screen or motion is reduced
  useEffect(() => {
    setIsPlaying(inView && !reduceMotion);
  }, [inView, reduceMotion]);

  // sound: only play when sound is on AND in view AND visual is playing
  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) return;
    if (soundOn && inView && isPlaying) {
      audio.volume = 0.35;
      audio.play().catch(() => { /* autoplay blocked — user already opted-in via toggle so silently ignore */ });
    } else {
      audio.pause();
    }
  }, [soundOn, inView, isPlaying]);

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

  // SFX cues — schedule scene-specific sounds when scene changes and sound is on
  useEffect(() => {
    if (!soundOn || !isPlaying) return;

    // Whoosh on every scene change (but not the very first render)
    if (prevSceneIdxRef.current !== sceneIdx) {
      sfx.whoosh();
      prevSceneIdxRef.current = sceneIdx;
    }

    const timers = [];

    if (sceneIdx === 0) {
      // Upload — sparkle when "All sources received" pops at 5.6s
      timers.push(setTimeout(() => sfx.sparkle(), 5600));
    } else if (sceneIdx === 1) {
      // Mark — soft ticks on each of 10 taps, then ka-chunk on LOCKED IN
      const baseDelay = 800;
      const gap = 550;
      for (let i = 0; i < 10; i++) {
        timers.push(setTimeout(() => sfx.tick(), baseDelay + i * gap));
      }
      timers.push(setTimeout(() => sfx.kaChunk(), 6300));
    } else if (sceneIdx === 2) {
      // Analyze — thunk when the 78/100 score lands
      timers.push(setTimeout(() => sfx.thunk(), 3100));
    } else if (sceneIdx === 5) {
      // Progress — thunk when "+26 pts" appears
      timers.push(setTimeout(() => sfx.thunk(), 2200));
    }

    return () => timers.forEach(clearTimeout);
  }, [sceneIdx, soundOn, isPlaying, sfx]);

  const scene = SCENES[sceneIdx];

  const handleSoundToggle = () => {
    setSoundOn((s) => !s);
    // ensure load on first enable (preload="none" means file isn't fetched until play)
    if (!soundOn && audioRef.current) {
      try { audioRef.current.load(); } catch (e) { /* noop */ }
    }
  };

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

                {/* hidden audio element — fetched lazily after first sound-on click */}
                <audio
                  ref={audioRef}
                  src={SOUNDTRACK_URL}
                  loop
                  preload="none"
                />

                {/* Sound toggle — clickable, replaces silent badge */}
                <button
                  data-testid="walkthrough-sound-toggle"
                  onClick={handleSoundToggle}
                  className="absolute top-3 left-3 z-30 flex items-center gap-1.5 text-[9px] uppercase tracking-[0.25em] font-bold px-2 py-1 backdrop-blur-md transition-colors"
                  style={{
                    background: soundOn ? "rgba(204,255,200,0.95)" : "rgba(20,57,35,0.45)",
                    color: soundOn ? "#0A0F0D" : "rgba(255,255,255,0.7)",
                  }}
                  aria-label={soundOn ? "Sound on — click to mute" : "Click to enable cinematic sound"}
                >
                  {soundOn ? <Volume2 className="w-3 h-3" /> : <VolumeX className="w-3 h-3" />}
                  {soundOn ? "Sound on" : "Push for sound"}
                </button>

                {/* Pulse hint ring around the sound button on first scene load (when off) */}
                {!soundOn && (
                  <motion.span
                    className="absolute top-2.5 left-2.5 z-20 pointer-events-none"
                    style={{
                      width: 138, height: 28,
                      border: "2px solid rgba(204,255,200,0.9)",
                      borderRadius: 2,
                    }}
                    initial={{ opacity: 0 }}
                    animate={{ opacity: [0, 1, 0] }}
                    transition={{ duration: 1.6, delay: 1.2, repeat: 1 }}
                  />
                )}

                <motion.div
                  key={scene.id}
                  initial={{ opacity: 0, y: 14 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.5, delay: 0.15 }}
                  className="absolute bottom-0 left-0 right-0 z-30 px-4 md:px-6 py-3 md:py-5 bg-gradient-to-t from-ink/95 via-ink/70 to-transparent"
                >
                  <div className="text-[11px] md:text-[13px] uppercase tracking-[0.3em] font-bold flex items-center gap-2" style={{ color: CREAM, opacity: 0.9 }}>
                    <scene.Icon className="w-4 h-4" />
                    Step {sceneIdx + 1} / {SCENES.length} · {scene.label}
                  </div>
                  <div className="font-barlow font-black text-white text-2xl sm:text-3xl md:text-5xl leading-[1.0] tracking-tight mt-1.5">
                    {scene.title}
                  </div>
                  <div className="text-white/85 text-base md:text-xl mt-1.5 leading-snug">{scene.caption}</div>
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

            <div className="mt-6 pt-5 border-t border-ink/10 flex flex-wrap items-center justify-between gap-y-2 text-[10px] uppercase tracking-[0.22em] font-bold text-ink/45">
              <span>Full report · ${price}</span>
              <span>No subscription</span>
            </div>
            {soundOn && (
              <div className="mt-2 text-[8px] uppercase tracking-[0.18em] font-bold text-ink/35">
                Music: &ldquo;{SOUNDTRACK_NAME}&rdquo; · Kevin MacLeod · incompetech.com · CC BY 4.0
              </div>
            )}
          </div>
        </div>
      </div>
    </section>
  );
}
