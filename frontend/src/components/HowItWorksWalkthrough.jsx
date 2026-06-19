import React, { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { motion, AnimatePresence, useReducedMotion } from "framer-motion";
import {
  Play, Pause, RotateCcw, Upload, MousePointer2, Sparkles,
  FileText, TrendingUp, ArrowRight, Volume2,
} from "lucide-react";

/* ============================================================================
   How It Works — animated walkthrough (silent, captioned, autoplay)
   5 scenes · 16:9 letterboxed · cream/forest aesthetic
   ============================================================================ */

const FOREST = "#1F4F2F";
const FOREST_SOFT = "rgba(31,79,47,0.12)";
const CREAM = "#F4EFE6";

const PLAYER_IMG =
  "https://images.unsplash.com/photo-1574629810360-7efbbe195018?w=1400&q=85&auto=format&fit=crop";

const SCENES = [
  { id: "upload", duration: 4200, label: "Upload", title: "Drop a 30-second clip", caption: "Phone footage works fine.", Icon: Upload },
  { id: "mark", duration: 6800, label: "Mark", title: "Tap your player 10 times", caption: "No AI guessing — you stay in control.", Icon: MousePointer2 },
  { id: "analyze", duration: 5400, label: "Analyze", title: "Pro Scout Intelligence builds your report", caption: "Six pillars. One honest score.", Icon: Sparkles },
  { id: "read", duration: 5800, label: "Read", title: "Timestamped video evidence", caption: "Every score backed by a moment in your clip.", Icon: FileText },
  { id: "progress", duration: 5600, label: "Progress", title: "Compare your evolution", caption: "Upload again — see exactly what improved.", Icon: TrendingUp },
];

/* ----------------------------------------------------------------------------
   Scene 1 — UPLOAD
---------------------------------------------------------------------------- */
const UploadScene = () => (
  <motion.div
    key="upload"
    className="absolute inset-0 flex items-center justify-center"
    initial={{ opacity: 0 }}
    animate={{ opacity: 1 }}
    exit={{ opacity: 0, filter: "blur(8px)" }}
    transition={{ duration: 0.6 }}
  >
    {/* dashed drop-zone */}
    <motion.div
      initial={{ scale: 0.96, opacity: 0 }}
      animate={{ scale: 1, opacity: 1 }}
      transition={{ duration: 0.7, ease: [0.16, 1, 0.3, 1] }}
      className="relative w-[78%] max-w-[520px] aspect-[16/10] border-2 border-dashed flex flex-col items-center justify-center bg-white/85 backdrop-blur-sm"
      style={{ borderColor: FOREST }}
    >
      {/* corner brackets */}
      {[
        "top-0 left-0 border-t-2 border-l-2",
        "top-0 right-0 border-t-2 border-r-2",
        "bottom-0 left-0 border-b-2 border-l-2",
        "bottom-0 right-0 border-b-2 border-r-2",
      ].map((p, i) => (
        <span key={i} aria-hidden className={`absolute ${p} w-4 h-4`} style={{ borderColor: FOREST }} />
      ))}

      {/* file card drops in */}
      <motion.div
        initial={{ y: -180, opacity: 0, rotate: -4 }}
        animate={{ y: 0, opacity: 1, rotate: 0 }}
        transition={{ delay: 0.5, type: "spring", stiffness: 120, damping: 14 }}
        className="bg-white shadow-2xl border border-ink/10 px-5 py-4 flex items-center gap-4"
      >
        <div className="w-12 h-12 flex items-center justify-center" style={{ background: FOREST_SOFT }}>
          <FileText className="w-5 h-5" style={{ color: FOREST }} strokeWidth={1.6} />
        </div>
        <div className="text-left">
          <div className="font-barlow font-black text-ink text-base leading-tight">match-clip-v3.mp4</div>
          <div className="text-[11px] uppercase tracking-[0.18em] text-ink/55 mt-0.5">24.6 MB · 30 s</div>
        </div>
      </motion.div>

      {/* progress bar */}
      <div className="mt-5 w-[70%] h-1 bg-ink/10 overflow-hidden">
        <motion.div
          initial={{ width: 0 }}
          animate={{ width: "100%" }}
          transition={{ delay: 1.1, duration: 2.2, ease: "easeInOut" }}
          className="h-full"
          style={{ background: FOREST }}
        />
      </div>
      <motion.span
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 3.2, duration: 0.4 }}
        className="mt-3 text-[10px] uppercase tracking-[0.25em] font-bold"
        style={{ color: FOREST }}
      >
        Ready
      </motion.span>
    </motion.div>
  </motion.div>
);

/* ----------------------------------------------------------------------------
   Scene 2 — MARK (10-tap manual)
---------------------------------------------------------------------------- */
// Path the crosshair will follow — roughly tracing a player jersey across the frame
const TAP_POINTS = [
  { x: 38, y: 52 }, { x: 41, y: 48 }, { x: 45, y: 46 },
  { x: 50, y: 47 }, { x: 55, y: 50 }, { x: 58, y: 54 },
  { x: 56, y: 60 }, { x: 52, y: 64 }, { x: 48, y: 62 }, { x: 44, y: 57 },
];

const MarkScene = () => (
  <motion.div
    key="mark"
    className="absolute inset-0 overflow-hidden"
    initial={{ opacity: 0 }}
    animate={{ opacity: 1 }}
    exit={{ opacity: 0, filter: "blur(8px)" }}
    transition={{ duration: 0.6 }}
  >
    {/* video frame backdrop */}
    <div className="absolute inset-0">
      <img src={PLAYER_IMG} alt="" className="absolute inset-0 w-full h-full object-cover" />
      <div className="absolute inset-0 bg-ink/35" />
    </div>

    {/* top HUD */}
    <div className="absolute top-4 left-4 right-4 flex items-center justify-between z-20">
      <span className="text-[10px] uppercase tracking-[0.25em] font-bold text-white/80 bg-ink/55 backdrop-blur-md px-2.5 py-1">
        ● Marking · 0:03 / 0:30
      </span>
      <motion.span
        key="counter"
        className="font-barlow font-black text-white text-xl bg-ink/55 backdrop-blur-md px-3 py-1"
      >
        <TapCounter />
      </motion.span>
    </div>

    {/* crosshair following path */}
    <Crosshair />

    {/* taps */}
    {TAP_POINTS.map((p, i) => (
      <TapRipple key={i} x={p.x} y={p.y} delay={0.6 + i * 0.55} />
    ))}

    {/* bottom frame strip */}
    <div className="absolute left-0 right-0 px-4 z-20" style={{ bottom: "92px" }}>
      <div className="flex gap-1.5 justify-center">
        {TAP_POINTS.map((p, i) => (
          <motion.div
            key={i}
            initial={{ opacity: 0, y: 12, scale: 0.9 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            transition={{ delay: 0.7 + i * 0.55, type: "spring", stiffness: 240, damping: 18 }}
            className="w-8 h-10 md:w-10 md:h-12 border-2 border-white/90 overflow-hidden shadow-lg"
            style={{ boxShadow: `0 4px 14px ${FOREST_SOFT}` }}
          >
            <div className="w-full h-full bg-cover" style={{ backgroundImage: `url(${PLAYER_IMG})`, backgroundPosition: p_to_bg(p), backgroundSize: "300% 300%" }} />
          </motion.div>
        ))}
      </div>
      <div className="text-center mt-1.5 text-[9px] uppercase tracking-[0.25em] font-bold text-white/70">
        Live frame strip
      </div>
    </div>
  </motion.div>
);

// helper: pan background per point
function p_to_bg(p) {
  return `${p.x}% ${p.y}%`;
}

const TapCounter = () => {
  const [n, setN] = useState(0);
  useEffect(() => {
    const t = TAP_POINTS.map((_, i) =>
      setTimeout(() => setN(i + 1), 600 + i * 550)
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
    transition={{ duration: 5.5, delay: 0.4, times: [0, ...TAP_POINTS.map((_, i) => (i + 1) / TAP_POINTS.length)], ease: "easeInOut" }}
    className="absolute z-10 -translate-x-1/2 -translate-y-1/2 pointer-events-none"
  >
    <svg width="46" height="46" viewBox="0 0 46 46" aria-hidden>
      <circle cx="23" cy="23" r="14" fill="none" stroke={CREAM} strokeWidth="1.5" />
      <circle cx="23" cy="23" r="3" fill={CREAM} />
      <line x1="23" y1="2" x2="23" y2="14" stroke={CREAM} strokeWidth="1.5" />
      <line x1="23" y1="32" x2="23" y2="44" stroke={CREAM} strokeWidth="1.5" />
      <line x1="2" y1="23" x2="14" y2="23" stroke={CREAM} strokeWidth="1.5" />
      <line x1="32" y1="23" x2="44" y2="23" stroke={CREAM} strokeWidth="1.5" />
    </svg>
  </motion.div>
);

const TapRipple = ({ x, y, delay }) => (
  <motion.span
    initial={{ opacity: 0, scale: 0.4 }}
    animate={{ opacity: [0, 0.9, 0], scale: [0.4, 2.2, 2.6] }}
    transition={{ delay, duration: 1.1, ease: "easeOut" }}
    className="absolute z-10 -translate-x-1/2 -translate-y-1/2 pointer-events-none rounded-full"
    style={{
      left: `${x}%`,
      top: `${y}%`,
      width: 56,
      height: 56,
      border: `2px solid ${CREAM}`,
      boxShadow: `0 0 32px ${CREAM}`,
    }}
  />
);

/* ----------------------------------------------------------------------------
   Scene 3 — ANALYZE (scan + radar assembling + score count-up)
---------------------------------------------------------------------------- */
const AnalyzeScene = () => (
  <motion.div
    key="analyze"
    className="absolute inset-0 overflow-hidden flex items-center justify-center"
    initial={{ opacity: 0 }}
    animate={{ opacity: 1 }}
    exit={{ opacity: 0, filter: "blur(8px)" }}
    transition={{ duration: 0.6 }}
  >
    {/* desaturated player image left side */}
    <div className="absolute inset-0">
      <img src={PLAYER_IMG} alt="" className="w-full h-full object-cover" style={{ filter: "grayscale(1) brightness(0.55)" }} />
      <div className="absolute inset-0" style={{ background: `linear-gradient(180deg, rgba(244,239,230,0) 0%, rgba(244,239,230,0.55) 100%)` }} />
    </div>

    {/* scan line sweep */}
    <motion.div
      initial={{ top: "-10%", opacity: 0 }}
      animate={{ top: "110%", opacity: [0, 1, 1, 0] }}
      transition={{ duration: 2.4, delay: 0.2, ease: "easeInOut" }}
      className="absolute left-0 right-0 h-px z-10 pointer-events-none"
      style={{ background: FOREST, boxShadow: `0 0 24px ${FOREST}, 0 0 64px ${FOREST}` }}
    />

    {/* radar assembles */}
    <div className="relative z-20 flex flex-col items-center pb-24">
      <RadarAssemble />
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 2.6, duration: 0.5 }}
        className="mt-4 text-center"
      >
        <div className="text-[10px] uppercase tracking-[0.3em] font-bold text-ink/55">Scout Score</div>
        <div className="font-barlow font-black text-5xl md:text-6xl mt-1 leading-none" style={{ color: FOREST }}>
          <ScoreCounter from={0} to={78} delay={2.7} duration={1.4} />
          <span className="text-ink/30 text-3xl md:text-4xl ml-1">/100</span>
        </div>
      </motion.div>
    </div>
  </motion.div>
);

const ScoreCounter = ({ from, to, delay = 0, duration = 1.2 }) => {
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
  return <span>{n}</span>;
};

const RadarAssemble = () => {
  // 6 axes — value 0-100 scaled to radius
  const values = [82, 75, 68, 88, 72, 80];
  const max = 100;
  const R = 90;
  const cx = 110, cy = 110;
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
    <svg width="220" height="220" viewBox="0 0 220 220" aria-hidden>
      {/* axes */}
      {[0, 1, 2, 3, 4, 5].map((i) => {
        const p = point(i, 100);
        return <line key={`a${i}`} x1={cx} y1={cy} x2={p.x} y2={p.y} stroke={FOREST} strokeOpacity="0.18" strokeWidth="0.8" />;
      })}
      {/* rings */}
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
      {/* particles flying in to vertices */}
      {values.map((v, i) => {
        const target = point(i, v);
        const start = { x: cx + (Math.random() - 0.5) * 240, y: cy + (Math.random() - 0.5) * 240 };
        return (
          <motion.circle
            key={`p${i}`}
            r="3"
            fill={FOREST}
            initial={{ cx: start.x, cy: start.y, opacity: 0 }}
            animate={{ cx: target.x, cy: target.y, opacity: [0, 1, 1] }}
            transition={{ delay: 1.4 + i * 0.08, duration: 0.7, ease: [0.16, 1, 0.3, 1] }}
          />
        );
      })}
      {/* radar polygon — stroke draws */}
      <motion.polygon
        points={polyPoints}
        fill={FOREST}
        fillOpacity="0"
        stroke={FOREST}
        strokeWidth="1.6"
        strokeLinejoin="round"
        initial={{ pathLength: 0, fillOpacity: 0 }}
        animate={{ pathLength: 1, fillOpacity: 0.18 }}
        transition={{ delay: 2.1, duration: 0.9, ease: "easeOut" }}
      />
    </svg>
  );
};

/* ----------------------------------------------------------------------------
   Scene 4 — READ (phone mockup with timestamped evidence)
---------------------------------------------------------------------------- */
const EvidenceScene = () => (
  <motion.div
    key="read"
    className="absolute inset-0 flex items-center justify-center overflow-hidden"
    initial={{ opacity: 0 }}
    animate={{ opacity: 1 }}
    exit={{ opacity: 0, filter: "blur(8px)" }}
    transition={{ duration: 0.6 }}
  >
    {/* soft grid background */}
    <div className="absolute inset-0" style={{
      backgroundImage: `linear-gradient(${FOREST_SOFT} 1px, transparent 1px), linear-gradient(90deg, ${FOREST_SOFT} 1px, transparent 1px)`,
      backgroundSize: "48px 48px",
      opacity: 0.5,
    }} />

    <motion.div
      initial={{ rotateY: -18, opacity: 0, y: 30 }}
      animate={{ rotateY: -6, opacity: 1, y: 0 }}
      transition={{ duration: 0.9, ease: [0.16, 1, 0.3, 1] }}
      className="relative z-10"
      style={{ perspective: 1200 }}
    >
      {/* phone frame */}
      <div className="relative w-[230px] md:w-[270px] aspect-[9/19] bg-ink rounded-[28px] p-2.5 shadow-2xl border border-ink/30">
        <div className="w-full h-full bg-white rounded-[20px] overflow-hidden relative">
          {/* status bar */}
          <div className="h-6 bg-cream-base flex items-center justify-between px-4 text-[9px] font-bold text-ink/55">
            <span>9:41</span><span>●●●</span>
          </div>
          {/* content */}
          <div className="p-3 space-y-2.5">
            <div className="text-[8px] uppercase tracking-[0.25em] font-bold" style={{ color: FOREST }}>Video evidence</div>
            <div className="font-barlow font-black text-ink text-base leading-tight">Top 4 moments</div>
            {[
              { t: "00:24", c: "Great first touch on a tough ball" },
              { t: "01:12", c: "Beats his man · perfect cut-back" },
              { t: "02:40", c: "Should look earlier — loses possession" },
              { t: "03:55", c: "Smart run in behind — perfect timing" },
            ].map((row, i) => (
              <motion.div
                key={i}
                initial={{ opacity: 0, x: -10 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: 0.5 + i * 0.18 }}
                className={`flex items-start gap-2 p-2 border-l-2`}
                style={{ borderColor: i === 1 ? FOREST : `${FOREST}33` }}
              >
                <motion.span
                  className="text-[10px] font-mono font-bold px-1.5 py-0.5"
                  style={{
                    background: i === 1 ? FOREST : `${FOREST}1A`,
                    color: i === 1 ? CREAM : FOREST,
                  }}
                  animate={i === 1 ? { scale: [1, 1.08, 1] } : {}}
                  transition={i === 1 ? { delay: 1.8, duration: 0.6, repeat: 2 } : {}}
                >
                  {row.t}
                </motion.span>
                <span className="text-[9px] text-ink/70 leading-snug">{row.c}</span>
              </motion.div>
            ))}
          </div>

          {/* pulse ring on the active timestamp */}
          <motion.div
            initial={{ opacity: 0, scale: 0.5 }}
            animate={{ opacity: [0, 1, 0], scale: [0.5, 1.8, 2.4] }}
            transition={{ delay: 1.9, duration: 1.4, repeat: 1 }}
            className="absolute left-5 top-[148px] w-12 h-7 rounded-full pointer-events-none"
            style={{ border: `2px solid ${FOREST}` }}
          />
        </div>
        {/* phone notch */}
        <div className="absolute top-3 left-1/2 -translate-x-1/2 w-16 h-3 bg-ink rounded-full" />
      </div>
    </motion.div>

    {/* arrow + film strip showing video jump */}
    <motion.div
      initial={{ opacity: 0, x: -10 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ delay: 2.6, duration: 0.5 }}
      className="hidden md:flex flex-col items-center gap-3 ml-8 z-10"
    >
      <ArrowRight className="w-6 h-6" style={{ color: FOREST }} />
      <div className="w-44 aspect-video border-2 overflow-hidden relative" style={{ borderColor: FOREST }}>
        <img src={PLAYER_IMG} alt="" className="w-full h-full object-cover" />
        <div className="absolute inset-0 bg-ink/20" />
        <div className="absolute bottom-1 left-1 text-[8px] font-mono font-bold text-white bg-ink/70 px-1.5 py-0.5">01:12</div>
      </div>
      <span className="text-[10px] uppercase tracking-[0.25em] font-bold text-ink/55">Tap → video</span>
    </motion.div>
  </motion.div>
);

/* ----------------------------------------------------------------------------
   Scene 5 — PROGRESS (compare mode dual radar + delta banner)
---------------------------------------------------------------------------- */
const CompareScene = () => (
  <motion.div
    key="progress"
    className="absolute inset-0 flex items-center justify-center overflow-hidden"
    initial={{ opacity: 0 }}
    animate={{ opacity: 1 }}
    exit={{ opacity: 0, filter: "blur(8px)" }}
    transition={{ duration: 0.6 }}
  >
    {/* cream backdrop panel so the radars pop */}
    <div className="absolute inset-0" style={{ background: CREAM }} />
    <div className="absolute inset-0" style={{
      backgroundImage: `linear-gradient(${FOREST_SOFT} 1px, transparent 1px), linear-gradient(90deg, ${FOREST_SOFT} 1px, transparent 1px)`,
      backgroundSize: "56px 56px",
      opacity: 0.6,
    }} />
    {/* subtle volt halo */}
    <div className="absolute -top-20 -left-20 w-[300px] h-[300px] rounded-full pointer-events-none"
         style={{ background: `radial-gradient(circle, ${FOREST_SOFT} 0%, transparent 70%)`, filter: "blur(30px)" }} />

    <div className="relative z-10 flex flex-col items-center w-full max-w-3xl px-4 pb-24">
      {/* dual radar */}
      <div className="flex items-center justify-center gap-2 md:gap-6">
        <CompareRadar values={[62, 58, 60, 70, 58, 64]} label="January" delay={0.2} />
        <motion.div
          initial={{ opacity: 0, scale: 0.7 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ delay: 0.8 }}
          className="font-barlow font-black text-2xl"
          style={{ color: FOREST }}
        >
          →
        </motion.div>
        <CompareRadar values={[82, 75, 68, 88, 72, 80]} label="February" delay={0.6} highlight />
      </div>

      {/* delta banner */}
      <motion.div
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 2.0, duration: 0.55, ease: [0.16, 1, 0.3, 1] }}
        className="mt-6 flex flex-wrap items-center justify-center gap-x-3 gap-y-1 px-4 py-3 bg-white border-2 shadow-lg"
        style={{ borderColor: FOREST }}
      >
        <span className="text-[10px] uppercase tracking-[0.3em] font-bold pr-2 border-r" style={{ color: FOREST, borderColor: `${FOREST}40` }}>
          What changed
        </span>
        {[
          { k: "Vision", v: "+18" },
          { k: "Passing", v: "+17" },
          { k: "Acceleration", v: "+8" },
          { k: "Decisions", v: "+12" },
        ].map((d, i) => (
          <motion.span
            key={i}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 2.2 + i * 0.12 }}
            className="text-[10px] font-bold uppercase tracking-wider"
            style={{ color: FOREST }}
          >
            {d.k} <span className="font-barlow font-black">{d.v}</span>
          </motion.span>
        ))}
      </motion.div>
    </div>
  </motion.div>
);

const CompareRadar = ({ values, label, delay = 0, highlight = false }) => {
  const max = 100, R = 70, cx = 90, cy = 90;
  const angle = (i) => -Math.PI / 2 + (i * 2 * Math.PI) / 6;
  const polyPoints = values.map((v, i) => {
    const r = (v / max) * R;
    return `${cx + r * Math.cos(angle(i))},${cy + r * Math.sin(angle(i))}`;
  }).join(" ");
  return (
    <motion.div
      initial={{ opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay, duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
      className="flex flex-col items-center"
    >
      <svg width="180" height="180" viewBox="0 0 180 180" aria-hidden>
        {[0.33, 0.66, 1].map((s, idx) => {
          const pts = [0, 1, 2, 3, 4, 5].map((i) => {
            const r = R * s;
            return `${cx + r * Math.cos(angle(i))},${cy + r * Math.sin(angle(i))}`;
          }).join(" ");
          return <polygon key={idx} points={pts} fill="none" stroke={FOREST} strokeOpacity="0.14" strokeWidth="0.8" />;
        })}
        {[0, 1, 2, 3, 4, 5].map((i) => {
          const r = R;
          return <line key={i} x1={cx} y1={cy} x2={cx + r * Math.cos(angle(i))} y2={cy + r * Math.sin(angle(i))} stroke={FOREST} strokeOpacity="0.14" strokeWidth="0.8" />;
        })}
        <motion.polygon
          points={polyPoints}
          fill={FOREST}
          fillOpacity={highlight ? 0.22 : 0.1}
          stroke={FOREST}
          strokeOpacity={highlight ? 1 : 0.45}
          strokeWidth={highlight ? 1.6 : 1.2}
          initial={{ pathLength: 0 }}
          animate={{ pathLength: 1 }}
          transition={{ delay: delay + 0.3, duration: 0.9, ease: "easeOut" }}
        />
      </svg>
      <div className={`mt-1 text-[10px] uppercase tracking-[0.3em] font-bold ${highlight ? "" : "text-ink/45"}`} style={{ color: highlight ? FOREST : undefined }}>
        {label}
      </div>
    </motion.div>
  );
};

/* ----------------------------------------------------------------------------
   Main component
---------------------------------------------------------------------------- */
export default function HowItWorksWalkthrough({ startHref = "/signup", price = 1 }) {
  const [sceneIdx, setSceneIdx] = useState(0);
  const [isPlaying, setIsPlaying] = useState(true);
  const [progress, setProgress] = useState(0); // 0-1 within current scene
  const reduceMotion = useReducedMotion();

  // pause when off-screen
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

  // scene timer
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

  const totalDur = useMemo(() => SCENES.reduce((a, s) => a + s.duration, 0), []);

  const sceneNode = (
    <AnimatePresence mode="wait">
      {sceneIdx === 0 && <UploadScene />}
      {sceneIdx === 1 && <MarkScene />}
      {sceneIdx === 2 && <AnalyzeScene />}
      {sceneIdx === 3 && <EvidenceScene />}
      {sceneIdx === 4 && <CompareScene />}
    </AnimatePresence>
  );

  return (
    <section
      ref={wrapRef}
      data-testid="how-it-works-walkthrough"
      className="relative py-20 md:py-28 border-t border-gray-border bg-cream-base overflow-hidden"
    >
      {/* subtle grain + halo */}
      <div className="absolute -top-32 -right-32 w-[480px] h-[480px] rounded-full pointer-events-none"
           style={{ background: `radial-gradient(circle, ${FOREST_SOFT} 0%, transparent 70%)`, filter: "blur(40px)" }} />

      <div className="relative z-10 max-w-6xl mx-auto px-6 md:px-10">
        {/* eyebrow */}
        <div className="flex items-center gap-4 mb-6">
          <span className="text-xs uppercase tracking-[0.3em] font-bold whitespace-nowrap" style={{ color: FOREST }}>
            How it works · 30 seconds
          </span>
          <span aria-hidden className="flex-1 h-px max-w-[240px]" style={{ background: `linear-gradient(90deg, ${FOREST}80, transparent)` }} />
        </div>

        <div className="grid lg:grid-cols-12 gap-8 items-center">
          {/* LEFT — scene player */}
          <div className="lg:col-span-8">
            <div className="relative">
              {/* film letterbox top/bottom */}
              <div className="relative aspect-video w-full bg-ink border border-ink/15 overflow-hidden shadow-[0_30px_80px_-20px_rgba(31,79,47,0.25)]">
                {/* cream inner border */}
                <div className="absolute inset-2 border z-[1] pointer-events-none" style={{ borderColor: `${CREAM}22` }} />
                {sceneNode}

                {/* SILENT badge top-left */}
                <div className="absolute top-3 left-3 z-30 flex items-center gap-1.5 text-[9px] uppercase tracking-[0.25em] font-bold text-white/65 bg-ink/40 backdrop-blur-md px-2 py-1">
                  <Volume2 className="w-3 h-3" /> Silent
                </div>

                {/* caption bar */}
                <motion.div
                  key={scene.id}
                  initial={{ opacity: 0, y: 12 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.5, delay: 0.15 }}
                  className="absolute bottom-0 left-0 right-0 z-30 px-4 md:px-6 py-3 md:py-4 bg-gradient-to-t from-ink/85 via-ink/60 to-transparent"
                >
                  <div className="text-[10px] uppercase tracking-[0.3em] font-bold flex items-center gap-2" style={{ color: CREAM, opacity: 0.85 }}>
                    <scene.Icon className="w-3.5 h-3.5" />
                    Step {sceneIdx + 1} · {scene.label}
                  </div>
                  <div className="font-barlow font-black text-white text-2xl md:text-3xl leading-tight mt-1">
                    {scene.title}
                  </div>
                  <div className="text-white/75 text-sm md:text-base mt-1">{scene.caption}</div>
                </motion.div>
              </div>

              {/* scrub bar */}
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
                {/* dot timeline */}
                <div className="flex-1 flex gap-1.5">
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
                          animate={{
                            scaleX: i < sceneIdx ? 1 : i === sceneIdx ? progress : 0,
                          }}
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

          {/* RIGHT — copy + CTA */}
          <div className="lg:col-span-4 lg:pl-4">
            <h2 className="font-barlow font-black uppercase text-3xl sm:text-4xl md:text-5xl leading-[0.95] tracking-tighter text-ink">
              See it work
              <br />
              <span className="font-serif-italic normal-case font-normal lowercase tracking-normal" style={{ color: FOREST }}>
                in 30 seconds
              </span>
            </h2>
            <p className="mt-5 text-ink/70 text-base leading-relaxed">
              Five steps from a phone clip to a professional scouting report — and back again when you want to track progress.
            </p>

            <ol className="mt-7 space-y-3">
              {SCENES.map((s, i) => (
                <li key={s.id} className={`flex items-center gap-3 transition-opacity ${i === sceneIdx ? "" : "opacity-50"}`}>
                  <span
                    className="w-8 h-8 flex items-center justify-center text-[11px] font-barlow font-black flex-shrink-0"
                    style={{
                      background: i === sceneIdx ? FOREST : "transparent",
                      color: i === sceneIdx ? CREAM : FOREST,
                      border: `1.5px solid ${FOREST}`,
                    }}
                  >
                    {String(i + 1).padStart(2, "0")}
                  </span>
                  <span className="font-barlow font-black uppercase text-sm tracking-wide text-ink">
                    {s.label}
                  </span>
                </li>
              ))}
            </ol>

            <Link
              to={startHref}
              data-testid="walkthrough-cta-start"
              className="mt-8 inline-flex w-full items-center justify-center gap-2 text-white font-barlow font-black uppercase tracking-widest text-sm py-3.5 transition-colors"
              style={{ background: FOREST }}
              onMouseEnter={(e) => (e.currentTarget.style.background = "#143923")}
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
