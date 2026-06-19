import React, { useRef } from "react";
import { Link } from "react-router-dom";
import { motion, useInView } from "framer-motion";
import {
  Upload, ArrowRight, CheckCircle2,
  Sparkles, Lock, Play,
} from "lucide-react";

/* ===========================================================
   STEP CARD — alternating left/right visual + copy
   =========================================================== */
function StepCard({ stepNum, title, copy, visual, reverse = false, testId }) {
  const ref = useRef(null);
  const inView = useInView(ref, { once: true, margin: "-80px" });

  return (
    <div
      ref={ref}
      data-testid={testId}
      className={`grid md:grid-cols-12 gap-8 md:gap-12 items-center py-12 md:py-20 ${
        reverse ? "md:[&>*:first-child]:order-2" : ""
      }`}
    >
      {/* Visual side */}
      <motion.div
        initial={{ opacity: 0, x: reverse ? 40 : -40 }}
        animate={inView ? { opacity: 1, x: 0 } : {}}
        transition={{ duration: 0.8, ease: "easeOut" }}
        className="md:col-span-7"
      >
        {visual}
      </motion.div>

      {/* Copy side */}
      <motion.div
        initial={{ opacity: 0, y: 24 }}
        animate={inView ? { opacity: 1, y: 0 } : {}}
        transition={{ duration: 0.8, delay: 0.2, ease: "easeOut" }}
        className="md:col-span-5"
      >
        <div className="flex items-center gap-3 mb-4">
          <span className="font-barlow font-black text-volt text-7xl md:text-8xl leading-none">
            {stepNum}
          </span>
          <span className="text-[10px] sm:text-xs uppercase tracking-[0.3em] font-bold text-volt/70">
            Step {stepNum} of 4
          </span>
        </div>
        <h3 className="font-barlow font-black uppercase tracking-tight text-3xl md:text-4xl lg:text-5xl text-ink leading-[0.95]">
          {title}
        </h3>
        <p className="mt-5 text-base md:text-lg text-ink/75 leading-relaxed">
          {copy}
        </p>
      </motion.div>
    </div>
  );
}

/* ===========================================================
   STEP 1 VISUAL — phone with video drop-in
   =========================================================== */
function Step1Visual() {
  const ref = useRef(null);
  const inView = useInView(ref, { once: true, margin: "-100px" });

  return (
    <div
      ref={ref}
      className="relative aspect-[4/3] md:aspect-[5/4] w-full bg-gradient-to-br from-[#0c2415] via-deepnavy to-[#050d09] border border-volt/20 overflow-hidden"
      style={{ perspective: "1200px" }}
    >
      {/* Stadium glow backdrop */}
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,rgba(61,140,94,0.25)_0%,transparent_70%)]" />
      <div className="absolute inset-0 scoreline-grid opacity-30" />

      {/* Phone mockup */}
      <motion.div
        initial={{ rotateY: -25, rotateX: 15, scale: 0.85, opacity: 0 }}
        animate={inView ? { rotateY: -15, rotateX: 8, scale: 1, opacity: 1 } : {}}
        transition={{ duration: 1.2, ease: "easeOut" }}
        style={{ transformStyle: "preserve-3d" }}
        className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 w-[55%] aspect-[9/19] bg-black border-4 border-[#1a1a1a] rounded-[2rem] shadow-[0_30px_80px_rgba(204,255,0,0.15)]"
      >
        <div className="absolute top-2 left-1/2 -translate-x-1/2 w-16 h-1 bg-[#1a1a1a] rounded-full" />
        {/* Screen */}
        <div className="absolute inset-2 rounded-[1.6rem] bg-[#0c2415] overflow-hidden flex flex-col items-center justify-center p-3">
          {/* Upload icon */}
          <motion.div
            initial={{ y: -30, opacity: 0 }}
            animate={inView ? { y: 0, opacity: 1 } : {}}
            transition={{ delay: 0.6, duration: 0.8 }}
            className="w-12 h-12 border-2 border-dashed border-volt/60 flex items-center justify-center mb-3"
          >
            <Upload className="w-5 h-5 text-volt" />
          </motion.div>
          <span className="text-[8px] uppercase tracking-widest text-ink/60 font-bold">
            Drop video
          </span>

          {/* Progress bar */}
          <div className="mt-4 w-full h-1.5 bg-volt/15 overflow-hidden">
            <motion.div
              initial={{ width: "0%" }}
              animate={inView ? { width: "100%" } : {}}
              transition={{ delay: 1.2, duration: 1.8, ease: "easeInOut" }}
              className="h-full bg-gradient-to-r from-volt to-forest-pop"
            />
          </div>
          <motion.span
            initial={{ opacity: 0 }}
            animate={inView ? { opacity: 1 } : {}}
            transition={{ delay: 3, duration: 0.4 }}
            className="mt-3 flex items-center gap-1 text-[8px] text-volt font-bold uppercase tracking-widest"
          >
            <CheckCircle2 className="w-2.5 h-2.5" />
            Uploaded
          </motion.span>
        </div>
      </motion.div>

      {/* Floating file labels */}
      <motion.div
        initial={{ opacity: 0, x: -40, y: 20 }}
        animate={inView ? { opacity: 1, x: 0, y: 0 } : {}}
        transition={{ delay: 0.9, duration: 0.7 }}
        className="absolute top-6 left-6 text-[10px] uppercase tracking-widest font-bold text-volt/70 bg-volt/10 border border-volt/30 px-2 py-1"
      >
        match.mp4 · 30s
      </motion.div>
    </div>
  );
}

/* ===========================================================
   STEP 2 VISUAL — phone showing 10-tap marking
   =========================================================== */
function Step2Visual() {
  const ref = useRef(null);
  const inView = useInView(ref, { once: true, margin: "-100px" });

  // 10 tap positions (mocked on a "player" silhouette)
  const taps = [
    { x: 50, y: 22 },  // head
    { x: 50, y: 38 },  // chest
    { x: 36, y: 40 },  // left shoulder
    { x: 64, y: 40 },  // right shoulder
    { x: 50, y: 55 },  // hip
    { x: 38, y: 60 },  // left arm
    { x: 62, y: 60 },  // right arm
    { x: 42, y: 78 },  // left knee
    { x: 58, y: 78 },  // right knee
    { x: 50, y: 92 },  // feet
  ];

  return (
    <div
      ref={ref}
      className="relative aspect-[4/3] md:aspect-[5/4] w-full bg-gradient-to-br from-[#0c2415] via-deepnavy to-[#050d09] border border-volt/20 overflow-hidden"
      style={{ perspective: "1200px" }}
    >
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,rgba(204,255,0,0.10)_0%,transparent_70%)]" />
      <div className="absolute inset-0 scoreline-grid opacity-25" />

      {/* Phone showing player silhouette */}
      <motion.div
        initial={{ rotateY: 18, rotateX: 6, opacity: 0 }}
        animate={inView ? { rotateY: 8, rotateX: 4, opacity: 1 } : {}}
        transition={{ duration: 1, ease: "easeOut" }}
        style={{ transformStyle: "preserve-3d" }}
        className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 w-[55%] aspect-[9/19] bg-black border-4 border-[#1a1a1a] rounded-[2rem] shadow-[0_30px_80px_rgba(204,255,0,0.18)]"
      >
        <div className="absolute top-2 left-1/2 -translate-x-1/2 w-16 h-1 bg-[#1a1a1a] rounded-full" />
        <div className="absolute inset-2 rounded-[1.6rem] bg-[#0a1a12] overflow-hidden">
          {/* Pitch lines */}
          <div className="absolute inset-0 opacity-30">
            <div className="absolute inset-x-2 top-1/2 h-px bg-volt/40" />
            <div className="absolute inset-y-2 left-1/2 w-px bg-volt/40" />
          </div>
          {/* Player silhouette SVG */}
          <svg
            viewBox="0 0 100 100"
            className="absolute inset-0 w-full h-full"
            preserveAspectRatio="xMidYMid meet"
          >
            {/* Body */}
            <ellipse cx="50" cy="22" rx="6" ry="7" fill="#1f4a32" opacity="0.85" />
            <path
              d="M 50 30 L 38 38 L 35 60 L 40 72 L 38 92 L 45 95 L 48 78 L 52 78 L 55 95 L 62 92 L 60 72 L 65 60 L 62 38 Z"
              fill="#1f4a32"
              opacity="0.85"
            />

            {/* X markers — animated in sequence */}
            {taps.map((t, i) => (
              <motion.g
                key={i}
                initial={{ opacity: 0, scale: 0 }}
                animate={inView ? { opacity: 1, scale: 1 } : {}}
                transition={{
                  delay: 0.5 + i * 0.18,
                  duration: 0.4,
                  type: "spring",
                  stiffness: 200,
                }}
              >
                <circle cx={t.x} cy={t.y} r="3" fill="#ccff00" opacity="0.3" />
                <text
                  x={t.x}
                  y={t.y + 1.5}
                  textAnchor="middle"
                  fontSize="4.5"
                  fontWeight="900"
                  fill="#ccff00"
                  fontFamily="monospace"
                >
                  ✕
                </text>
              </motion.g>
            ))}

            {/* Tap counter */}
            <motion.text
              x="50"
              y="10"
              textAnchor="middle"
              fontSize="3.5"
              fontWeight="900"
              fill="#ccff00"
              fontFamily="Barlow, sans-serif"
              initial={{ opacity: 0 }}
              animate={inView ? { opacity: 1 } : {}}
              transition={{ delay: 0.3 }}
            >
              10 / 10 TAPS
            </motion.text>
          </svg>
        </div>
      </motion.div>

      {/* Side floating label */}
      <motion.div
        initial={{ opacity: 0, x: 40 }}
        animate={inView ? { opacity: 1, x: 0 } : {}}
        transition={{ delay: 1.2, duration: 0.6 }}
        className="absolute top-6 right-6 text-[10px] uppercase tracking-widest font-bold text-volt bg-volt/10 border border-volt/40 px-2 py-1"
      >
        100% Manual · 0 AI Guess
      </motion.div>
    </div>
  );
}

/* ===========================================================
   STEP 3 VISUAL — scan line + radar materialising
   =========================================================== */
function Step3Visual() {
  const ref = useRef(null);
  const inView = useInView(ref, { once: true, margin: "-100px" });

  // Radar geometry — pentagon
  const axes = ["TEC", "TAC", "PHY", "MEN", "OVR"];
  const center = 50;
  const radius = 32;
  const values = [85, 78, 82, 88, 84]; // % of radius

  const radarPoint = (i, pct, total = 5) => {
    const angle = -Math.PI / 2 + (i * 2 * Math.PI) / total;
    const r = radius * (pct / 100);
    return {
      x: center + Math.cos(angle) * r,
      y: center + Math.sin(angle) * r,
    };
  };

  const fullPolygon = values.map((v, i) => {
    const p = radarPoint(i, v);
    return `${p.x},${p.y}`;
  }).join(" ");

  return (
    <div
      ref={ref}
      className="relative aspect-[4/3] md:aspect-[5/4] w-full bg-gradient-to-br from-[#0c2415] via-deepnavy to-[#050d09] border border-volt/20 overflow-hidden"
    >
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,rgba(204,255,0,0.12)_0%,transparent_70%)]" />
      <div className="absolute inset-0 scoreline-grid opacity-25" />

      {/* Scan line sweep */}
      <motion.div
        initial={{ y: "-100%", opacity: 0 }}
        animate={inView ? { y: ["100%", "-10%", "100%"], opacity: [0, 1, 0] } : {}}
        transition={{ duration: 2.4, ease: "easeInOut", delay: 0.3 }}
        className="absolute inset-x-0 h-12 z-20 pointer-events-none"
        style={{
          background:
            "linear-gradient(180deg, transparent 0%, rgba(204,255,0,0.5) 50%, transparent 100%)",
          boxShadow: "0 0 30px rgba(204,255,0,0.6)",
        }}
      />

      {/* Radar SVG */}
      <div className="absolute inset-0 flex items-center justify-center p-8">
        <svg viewBox="0 0 100 100" className="w-full max-w-[380px] aspect-square">
          {/* Grid pentagons */}
          {[0.25, 0.5, 0.75, 1].map((scale, idx) => {
            const pts = Array.from({ length: 5 }).map((_, i) => {
              const p = radarPoint(i, scale * 100);
              return `${p.x},${p.y}`;
            }).join(" ");
            return (
              <motion.polygon
                key={idx}
                points={pts}
                fill="none"
                stroke="#ccff00"
                strokeWidth="0.3"
                opacity="0.25"
                initial={{ opacity: 0 }}
                animate={inView ? { opacity: 0.25 } : {}}
                transition={{ delay: 0.2 + idx * 0.15, duration: 0.5 }}
              />
            );
          })}

          {/* Axis lines */}
          {axes.map((axis, i) => {
            const p = radarPoint(i, 100);
            return (
              <motion.line
                key={i}
                x1={center}
                y1={center}
                x2={p.x}
                y2={p.y}
                stroke="#ccff00"
                strokeWidth="0.3"
                opacity="0.4"
                initial={{ opacity: 0 }}
                animate={inView ? { opacity: 0.4 } : {}}
                transition={{ delay: 0.5 + i * 0.1, duration: 0.4 }}
              />
            );
          })}

          {/* Value polygon — animated fill */}
          <motion.polygon
            points={fullPolygon}
            fill="#ccff00"
            stroke="#ccff00"
            strokeWidth="0.7"
            initial={{ opacity: 0, scale: 0 }}
            animate={inView ? { opacity: [0, 0, 0.35], scale: 1 } : {}}
            transition={{ delay: 1.4, duration: 0.9, ease: "easeOut" }}
            style={{ transformOrigin: "50% 50%" }}
          />

          {/* Axis dots + labels */}
          {axes.map((axis, i) => {
            const p = radarPoint(i, 110);
            const vp = radarPoint(i, values[i]);
            return (
              <g key={i}>
                <motion.circle
                  cx={vp.x}
                  cy={vp.y}
                  r="1.4"
                  fill="#ccff00"
                  initial={{ opacity: 0 }}
                  animate={inView ? { opacity: 1 } : {}}
                  transition={{ delay: 2 + i * 0.08, duration: 0.3 }}
                />
                <motion.text
                  x={p.x}
                  y={p.y}
                  textAnchor="middle"
                  dominantBaseline="middle"
                  fontSize="3.5"
                  fontWeight="900"
                  fill="#fff8e6"
                  fontFamily="Barlow, sans-serif"
                  initial={{ opacity: 0 }}
                  animate={inView ? { opacity: 1 } : {}}
                  transition={{ delay: 1.8 + i * 0.08 }}
                >
                  {axis}
                </motion.text>
              </g>
            );
          })}

          {/* Center number */}
          <motion.text
            x={center}
            y={center + 1.5}
            textAnchor="middle"
            fontSize="9"
            fontWeight="900"
            fill="#ccff00"
            fontFamily="Barlow, sans-serif"
            initial={{ opacity: 0, scale: 0.5 }}
            animate={inView ? { opacity: 1, scale: 1 } : {}}
            transition={{ delay: 2.4, duration: 0.6, type: "spring" }}
          >
            8.4
          </motion.text>
        </svg>
      </div>

      {/* Floating stat tickers */}
      <div className="absolute bottom-6 left-6 right-6 flex flex-wrap gap-2">
        {[
          { label: "Touches", val: "47" },
          { label: "Pass %", val: "82" },
          { label: "Runs", val: "12" },
        ].map((s, i) => (
          <motion.div
            key={s.label}
            initial={{ opacity: 0, y: 20 }}
            animate={inView ? { opacity: 1, y: 0 } : {}}
            transition={{ delay: 2.6 + i * 0.15, duration: 0.5 }}
            className="px-3 py-1.5 bg-volt/10 border border-volt/30 backdrop-blur-sm"
          >
            <span className="text-[9px] uppercase tracking-widest text-volt/70 font-bold mr-2">
              {s.label}
            </span>
            <span className="text-sm font-barlow font-black text-volt">
              {s.val}
            </span>
          </motion.div>
        ))}
      </div>
    </div>
  );
}

/* ===========================================================
   STEP 4 VISUAL — fanned report pages + Stripe unlock
   =========================================================== */
function Step4Visual({ priceLabel = "$1" }) {
  const ref = useRef(null);
  const inView = useInView(ref, { once: true, margin: "-100px" });

  const pages = [
    { rotate: -8, x: -36, y: 8, delay: 0.2 },
    { rotate: -3, x: -18, y: 4, delay: 0.4 },
    { rotate: 0, x: 0, y: 0, delay: 0.6 },
    { rotate: 4, x: 18, y: 4, delay: 0.8 },
    { rotate: 9, x: 36, y: 10, delay: 1.0 },
  ];

  return (
    <div
      ref={ref}
      className="relative aspect-[4/3] md:aspect-[5/4] w-full bg-gradient-to-br from-[#0c2415] via-deepnavy to-[#050d09] border border-volt/20 overflow-hidden"
      style={{ perspective: "1200px" }}
    >
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,rgba(204,255,0,0.14)_0%,transparent_70%)]" />
      <div className="absolute inset-0 scoreline-grid opacity-25" />

      {/* Fanned pages */}
      <div className="absolute left-1/2 top-[42%] -translate-x-1/2 -translate-y-1/2 w-[280px] h-[200px]">
        {pages.map((p, i) => (
          <motion.div
            key={i}
            initial={{ opacity: 0, x: 0, y: 60, rotate: 0, scale: 0.8 }}
            animate={
              inView
                ? { opacity: 1, x: p.x, y: p.y, rotate: p.rotate, scale: 1 }
                : {}
            }
            transition={{
              duration: 0.7,
              delay: p.delay,
              ease: "easeOut",
            }}
            className="absolute inset-0 bg-[#fff8e6] border border-volt/30 shadow-[0_8px_30px_rgba(0,0,0,0.4)] p-4"
            style={{ transformOrigin: "bottom center", zIndex: i }}
          >
            {/* Mock page content */}
            <div className="flex items-center gap-2 mb-3 pb-2 border-b border-deepnavy/15">
              <div className="w-6 h-6 bg-volt flex items-center justify-center">
                <span className="text-deepnavy text-[10px] font-black">SP</span>
              </div>
              <span className="text-[8px] uppercase tracking-widest text-deepnavy/60 font-bold">
                ScoutMePlay · Pg {i + 1}
              </span>
            </div>
            <div className="space-y-1.5">
              <div className="h-1.5 bg-deepnavy/15 w-3/4" />
              <div className="h-1.5 bg-deepnavy/15 w-full" />
              <div className="h-1.5 bg-deepnavy/15 w-5/6" />
              <div className="h-1.5 bg-volt/40 w-2/3 mt-2" />
            </div>
            <div className="mt-3 grid grid-cols-3 gap-1">
              <div className="h-6 bg-deepnavy/10" />
              <div className="h-6 bg-volt/30" />
              <div className="h-6 bg-deepnavy/10" />
            </div>
          </motion.div>
        ))}
      </div>

      {/* Stripe unlock pill */}
      <motion.div
        initial={{ opacity: 0, y: 30, scale: 0.85 }}
        animate={inView ? { opacity: 1, y: 0, scale: 1 } : {}}
        transition={{ delay: 1.4, duration: 0.7, type: "spring", stiffness: 150 }}
        className="absolute left-1/2 bottom-8 -translate-x-1/2 flex items-center gap-3 bg-volt text-deepnavy font-barlow font-black uppercase tracking-widest text-sm px-5 py-3 shadow-[0_15px_40px_rgba(204,255,0,0.4)]"
        data-testid="how-it-works-stripe-pill"
      >
        <Lock className="w-4 h-4" />
        Unlock for {priceLabel}
        <ArrowRight className="w-4 h-4" />
      </motion.div>

      {/* Sparkles around pill */}
      <motion.div
        initial={{ opacity: 0 }}
        animate={inView ? { opacity: 1 } : {}}
        transition={{ delay: 1.6, duration: 1 }}
        className="absolute left-1/2 bottom-12 -translate-x-1/2 pointer-events-none"
      >
        {[0, 60, 120, 180, 240, 300].map((angle, i) => (
          <motion.span
            key={i}
            className="absolute w-1 h-1 bg-volt rounded-full"
            initial={{ opacity: 0, x: 0, y: 0 }}
            animate={
              inView
                ? {
                    opacity: [0, 1, 0],
                    x: Math.cos((angle * Math.PI) / 180) * 60,
                    y: Math.sin((angle * Math.PI) / 180) * 30,
                  }
                : {}
            }
            transition={{
              delay: 1.8,
              duration: 1.2,
              repeat: Infinity,
              repeatDelay: 1.5,
              ease: "easeOut",
            }}
          />
        ))}
      </motion.div>
    </div>
  );
}

/* ===========================================================
   FULL EXPORT — HowItWorks3D section
   =========================================================== */
export default function HowItWorks3D({ startHref = "/signup", priceLabel = "$159" }) {
  return (
    <section
      id="how-it-works"
      data-testid="how-it-works-3d"
      className="relative py-20 md:py-28 bg-deepnavy border-t border-volt/10 overflow-hidden"
    >
      {/* Backdrop */}
      <div className="absolute inset-0 pointer-events-none">
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top,rgba(61,140,94,0.12)_0%,transparent_60%)]" />
        <div className="absolute inset-0 scoreline-grid opacity-20" />
      </div>

      <div className="relative max-w-7xl mx-auto px-6 md:px-10">
        {/* Section header */}
        <motion.div
          initial={{ opacity: 0, y: 24 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, amount: 0.4 }}
          transition={{ duration: 0.8, ease: "easeOut" }}
          className="text-center max-w-3xl mx-auto mb-12 md:mb-16"
        >
          <div className="inline-flex items-center gap-2 border border-volt/40 bg-volt/10 px-4 py-2 mb-6">
            <Sparkles className="w-3.5 h-3.5 text-volt" />
            <span className="text-volt text-[10px] sm:text-xs uppercase tracking-[0.28em] font-bold">
              How it works · 4 steps
            </span>
          </div>
          <h2
            className="font-barlow font-black uppercase text-4xl sm:text-5xl md:text-6xl tracking-tighter text-ink leading-[0.95]"
            data-testid="how-it-works-title"
          >
            From your phone
            <span className="block text-gradient-volt mt-1">to a real scout report.</span>
          </h2>
          <p className="mt-6 text-base md:text-lg text-ink/70 max-w-2xl mx-auto">
            No subscriptions. No guesswork. Just deep football intelligence — delivered in days, not months.
          </p>
        </motion.div>

        {/* Steps */}
        <StepCard
          stepNum="01"
          title="Upload your video"
          copy="Drop a 30-second clip from any phone. Match footage, training drill, set-piece — anything where your player is on the ball."
          visual={<Step1Visual />}
          testId="how-it-works-step-1"
        />

        <div className="border-t border-volt/10" />

        <StepCard
          stepNum="02"
          title="Tap your player 10 times."
          copy="100% manual marking. You tap the player you want analysed — no AI guessing, no wrong subjects. Pro Scout Intelligence locks onto exactly who you want."
          visual={<Step2Visual />}
          reverse
          testId="how-it-works-step-2"
        />

        <div className="border-t border-volt/10" />

        <StepCard
          stepNum="03"
          title="Pro Scout Intelligence breaks it down."
          copy="Every touch, every run, every decision — analysed against pro academy benchmarks. Technical, tactical, physical, mental — scored in detail."
          visual={<Step3Visual />}
          testId="how-it-works-step-3"
        />

        <div className="border-t border-volt/10" />

        <StepCard
          stepNum="04"
          title={`Your academy-grade report. ${priceLabel}.`}
          copy="A premium multi-page PDF report — your strengths, your gaps, your development plan, scout view and pro benchmarks. One-time payment, yours forever."
          visual={<Step4Visual priceLabel={priceLabel} />}
          reverse
          testId="how-it-works-step-4"
        />

        {/* Final CTA */}
        <motion.div
          initial={{ opacity: 0, y: 24 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, amount: 0.4 }}
          transition={{ duration: 0.8 }}
          className="mt-16 md:mt-20 flex flex-col items-center text-center"
        >
          <p className="font-serif-italic italic text-lg md:text-2xl text-ink/85 max-w-2xl">
            Built by scouts. For scouts. For families. For futures.
          </p>
          <Link
            to={startHref}
            data-testid="how-it-works-cta"
            className="mt-8 group inline-flex items-center gap-3 bg-volt hover:bg-forest-pop text-deepnavy hover:text-white font-barlow font-black uppercase tracking-widest text-base px-8 py-4 transition-colors animate-pulse-glow"
          >
            <Play className="w-5 h-5" strokeWidth={2.4} />
            Start your scout report
            <ArrowRight className="w-5 h-5 group-hover:translate-x-1 transition-transform" />
          </Link>
        </motion.div>
      </div>
    </section>
  );
}
