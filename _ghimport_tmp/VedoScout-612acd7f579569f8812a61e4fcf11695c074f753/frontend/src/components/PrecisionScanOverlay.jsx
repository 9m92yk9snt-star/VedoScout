import React, { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { ShieldCheck, Lightbulb, Lock, LayoutGrid, Check, FileText, ArrowRight, CheckCircle2 } from "lucide-react";

/**
 * PrecisionScanOverlay — "Waiting Experience"
 * Pixel-faithful recreation of the approved reference design, driven by the
 * REAL backend `progress_step` (1..5) polled from /api/reports/{id}/status.
 *
 * Phases:
 *   • uploading — unified progress (upload maps to 0–15 % of the journey)
 *   • analyzing — live % + 6-step checklist mapped to real pipeline stages
 *   • done      — celebratory confirmation (unchanged, user-approved earlier)
 */
const LIME = "#CCFF00";
const INK = "#0C100B";
const CREAM = "#F0EDE5";

/* Real backend steps: 1=received, 2=preparing, 3=content-gate, 4=gemini, 5=ready.
   Visual stages 1..6 (checklist rows). Stage 4 is the long Gemini stage — after
   55 s inside it we honestly advance the visual to "Building your development
   plan" (both rows belong to the same backend stage). */
function visualStageFor(phase, backendStep, stepElapsed) {
  if (phase === "uploading") return 1;
  const s = Math.max(1, Number(backendStep) || 1);
  if (s <= 1) return 1;
  if (s === 2) return 2;
  if (s === 3) return 3;
  if (s === 4) return stepElapsed > 55 ? 5 : 4;
  return 6;
}

/* Smooth, monotonic percent. Upload = 0–15 %. Each visual stage eases toward
   its cap and never goes backwards. */
const STAGE_PCT = { 1: [15, 26], 2: [26, 40], 3: [40, 52], 4: [52, 86], 5: [86, 97], 6: [97, 99] };
const STAGE_TAU = { 1: 18, 2: 30, 3: 25, 4: 60, 5: 40, 6: 30 };

const CHECKLIST = [
  { id: 1, title: "Video received & prepared", sub: () => "Quality check complete" },
  { id: 2, title: "Your player locked", sub: (t) => (t > 0 ? `${t}/${t} taps verified – player identified` : "Player identified from your marking") },
  { id: 3, title: "Optical tracking complete", sub: () => "Top speed, sprints & movements tracked" },
  { id: 4, title: "Scout analyzing every action", sub: () => "Technique • Decisions • Off-ball • Bravery", now: true },
  { id: 5, title: "Building your development plan", sub: () => "Almost there..." },
  { id: 6, title: "Quality check & report ready", sub: () => "Final review before delivery" },
];

const MINI_STAGES = [
  { label: "Detecting", from: 1 },
  { label: "Tracking", from: 2 },
  { label: "Analysing", from: 4 },
  { label: "Building Report", from: 5 },
];

function LivenessLine({ lastProgressAt }) {
  // Honest server-activity indicator: green while the analysis worker stamps
  // heartbeats, amber if the heartbeat goes stale (worker restarting).
  const [, force] = useState(0);
  useEffect(() => {
    const id = setInterval(() => force((n) => n + 1), 5000);
    return () => clearInterval(id);
  }, []);
  if (!lastProgressAt) return null;
  const age = Math.max(0, Math.round((Date.now() - new Date(lastProgressAt).getTime()) / 1000));
  const fresh = age < 120;
  return (
    <div className="mt-1.5 flex items-center gap-1.5 text-[11.5px] font-semibold" data-testid="wait-liveness"
         style={{ color: fresh ? "#9BE7B4" : "#F2B06B" }}>
      <span className="w-1.5 h-1.5 rounded-full" style={{ background: fresh ? "#2FBF71" : "#D97B29", animation: fresh ? "wait-blink 1.6s infinite" : "none" }} />
      {fresh ? `Live — server activity ${age}s ago` : "Server reconnecting — resumes automatically"}
    </div>
  );
}

export default function PrecisionScanOverlay({
  open,
  phase = "analyzing",
  uploadPct = 0,
  backendStep = 0,
  playerName = "",
  playerAge = "",
  playerPosition = "",
  tapsCount = 0,
  heroImage = null,
  lastProgressAt = null,
  onViewReport,
  onContinueInBackground,
}) {
  const [tick, setTick] = useState(0);
  const stepStartRef = useRef(Date.now());
  const lastStepRef = useRef(backendStep);
  const maxPctRef = useRef(0);

  useEffect(() => {
    if (!open) {
      maxPctRef.current = 0;
      lastStepRef.current = 0;
      stepStartRef.current = Date.now();
      setTick(0);
      return;
    }
    const id = setInterval(() => setTick((t) => t + 1), 1000);
    return () => clearInterval(id);
  }, [open]);

  useEffect(() => {
    if (backendStep !== lastStepRef.current) {
      lastStepRef.current = backendStep;
      stepStartRef.current = Date.now();
    }
  }, [backendStep]);

  if (!open) return null;

  const stepElapsed = (Date.now() - stepStartRef.current) / 1000;
  const stage = visualStageFor(phase, backendStep, stepElapsed);

  let pct;
  if (phase === "uploading") {
    pct = Math.min(15, (uploadPct / 100) * 15);
  } else if (phase === "done") {
    pct = 100;
  } else {
    const [start, cap] = STAGE_PCT[stage] || [15, 26];
    const tau = STAGE_TAU[stage] || 30;
    pct = start + (cap - start) * (1 - Math.exp(-stepElapsed / tau));
  }
  maxPctRef.current = Math.max(maxPctRef.current, pct);
  const displayPct = Math.round(maxPctRef.current);

  const remainingSec = Math.max(5, Math.round(((100 - maxPctRef.current) * 1.5) / 5) * 5);
  const etaLabel = remainingSec >= 90 ? `~ ${Math.round(remainingSec / 60)} min left` : `~ ${remainingSec} sec left`;

  const metaChip = [playerAge ? `U${playerAge}` : null, playerPosition ? String(playerPosition).toUpperCase() : null]
    .filter(Boolean)
    .join("  •  ");

  return (
    <AnimatePresence>
      <motion.div
        key="scan-overlay"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        transition={{ duration: 0.35 }}
        className="fixed inset-0 z-[100] overflow-y-auto"
        style={{ background: CREAM }}
        data-testid="precision-scan-overlay"
      >
        <style>{`
          @keyframes wait-sheen { 0% { transform: translateX(-110%);} 100% { transform: translateX(240%);} }
          @keyframes wait-radar { 0% { transform: scale(0.55); opacity: 0.9;} 100% { transform: scale(1.25); opacity: 0;} }
          @keyframes wait-blink { 0%,100% { opacity: 1;} 50% { opacity: 0.25;} }
        `}</style>

        {phase === "done" ? (
          <DoneScreen onViewReport={onViewReport} />
        ) : (
          <div className="w-full max-w-[520px] mx-auto px-5 pt-6 pb-10">
            {/* ── Top bar ─────────────────────────────────────── */}
            <div className="flex items-center justify-between mb-6">
              <span className="font-barlow font-black uppercase text-[22px] tracking-[0.05em] flex items-baseline gap-[1px]" style={{ color: INK }}>
                <span>SCOUT</span>
                <span className="px-[4px]" style={{ background: LIME }}>ME</span>
                <span>PLAY</span>
              </span>
              <span className="text-[12px] font-extrabold tracking-[0.18em]" style={{ color: INK }} data-testid="wait-step-indicator">
                STEP 3/3
              </span>
            </div>

            {/* ── Kicker + headline ───────────────────────────── */}
            <div className="flex items-center gap-2.5 mb-2.5">
              <span className="w-3 h-3 rounded-full flex-shrink-0" style={{ background: LIME, animation: "wait-blink 1.6s infinite" }} />
              <span className="text-[11px] font-extrabold tracking-[0.22em] uppercase whitespace-nowrap" style={{ color: "#1F4F2F" }}>
                Scoutme Pro Benchmark Analysis
              </span>
            </div>
            <h1
              className="font-barlow font-black uppercase leading-[0.98] whitespace-nowrap"
              style={{ color: INK, fontSize: "clamp(24px, 7vw, 37px)", letterSpacing: "-0.005em" }}
              data-testid="wait-headline"
            >
              Your video is being analyzed
            </h1>
            <p className="mt-3 text-[16px] leading-[1.45]" style={{ color: "#3A4136" }}>
              Every touch. Every run. Every decision.
              <br />
              Building your <span className="font-bold" style={{ color: "#1F4F2F" }}>Scout Report</span>.
            </p>

            {/* ── Player chips ────────────────────────────────── */}
            <div className="flex flex-wrap gap-2.5 mt-4">
              {playerName ? (
                <span className="inline-flex items-center gap-1.5 bg-white rounded-full px-4 py-2 text-[12px] font-extrabold tracking-[0.06em] uppercase shadow-sm border border-[#E7E2D2]" style={{ color: INK }} data-testid="wait-chip-player">
                  <span aria-hidden>⚽</span> {playerName}
                </span>
              ) : null}
              {metaChip ? (
                <span className="inline-flex items-center bg-white rounded-full px-4 py-2 text-[12px] font-extrabold tracking-[0.06em] uppercase shadow-sm border border-[#E7E2D2]" style={{ color: INK }} data-testid="wait-chip-meta">
                  {metaChip}
                </span>
              ) : null}
              <span className="inline-flex items-center gap-1.5 rounded-full px-4 py-2 text-[12px] font-extrabold tracking-[0.06em] uppercase" style={{ background: INK, color: LIME }} data-testid="wait-chip-identity">
                <ShieldCheck className="w-3.5 h-3.5" strokeWidth={2.6} />
                Identity Locked
              </span>
            </div>

            {/* ── Hero live-scan card ─────────────────────────── */}
            <div className="relative rounded-[22px] overflow-hidden mt-5" style={{ background: "#101408" }} data-testid="wait-hero-card">
              {heroImage ? (
                <img src={heroImage} alt="" className="absolute inset-0 w-full h-full object-cover" />
              ) : (
                <div className="absolute inset-0" style={{ background: "radial-gradient(circle at 70% 30%, #1E3A22, #0B0F08 70%)" }} />
              )}
              <div className="absolute inset-0" style={{ background: "linear-gradient(90deg, rgba(8,11,6,0.92) 0%, rgba(8,11,6,0.62) 42%, rgba(8,11,6,0.18) 100%)" }} />
              <div className="absolute inset-x-0 bottom-0 h-24" style={{ background: "linear-gradient(180deg, transparent, rgba(6,9,5,0.9))" }} />

              <div className="relative p-5 pb-4">
                <div className="flex justify-end">
                  <span className="inline-flex items-center gap-1.5 text-white text-[12px] font-extrabold tracking-[0.12em] uppercase">
                    <span className="w-2.5 h-2.5 rounded-full bg-[#FF2E2E]" style={{ animation: "wait-blink 1.1s infinite" }} />
                    Live Scan
                  </span>
                </div>

                <div className="mt-1">
                  <div className="font-barlow font-black leading-none tabular-nums" style={{ color: LIME, fontSize: "clamp(56px, 17vw, 78px)" }} data-testid="wait-live-pct">
                    {displayPct}%
                  </div>
                  <div className="mt-2 text-white font-bold text-[16px]" data-testid="wait-eta">{etaLabel}</div>
                  <LivenessLine lastProgressAt={lastProgressAt} />
                  <div className="mt-0.5 text-[13px]" style={{ color: "rgba(255,255,255,0.72)" }}>
                    Typically ready in ~90 sec
                  </div>
                </div>

                <div className="mt-4 h-[10px] rounded-full overflow-hidden" style={{ background: "rgba(255,255,255,0.18)" }}>
                  <div className="h-full rounded-full relative overflow-hidden transition-[width] duration-700 ease-out" style={{ width: `${Math.max(3, displayPct)}%`, background: LIME }}>
                    <span className="absolute inset-y-0 w-1/3" style={{ background: "linear-gradient(90deg, transparent, rgba(255,255,255,0.55), transparent)", animation: "wait-sheen 1.8s infinite" }} />
                  </div>
                </div>

                <div className="mt-4 flex items-center justify-between gap-1 -mx-0.5">
                  {MINI_STAGES.map((m, i) => {
                    const next = MINI_STAGES[i + 1];
                    const isDone = next ? stage >= next.from : stage >= 6;
                    const isActive = !isDone && stage >= m.from;
                    return (
                      <span key={m.label} className="inline-flex items-center gap-1 text-[10.5px] tracking-tight font-semibold text-white whitespace-nowrap">
                        <span
                          className="w-2 h-2 rounded-full flex-shrink-0"
                          style={{
                            background: isDone ? "#4ADE80" : isActive ? LIME : "rgba(255,255,255,0.35)",
                            animation: isActive ? "wait-blink 1.3s infinite" : "none",
                          }}
                        />
                        {m.label}
                      </span>
                    );
                  })}
                </div>
              </div>
            </div>

            {/* ── Checklist card ──────────────────────────────── */}
            <div className="rounded-[24px] mt-4 px-4 py-3 shadow-sm border border-[#E9E4D5]" style={{ background: "#FAF8F1" }} data-testid="wait-checklist">
              {CHECKLIST.map((row, i) => {
                const idx = i + 1;
                const isDone = idx < stage;
                const isActive = idx === stage;
                const isLast = i === CHECKLIST.length - 1;
                return (
                  <div
                    key={row.id}
                    className={`relative flex items-start gap-3.5 py-3 pr-1 ${isActive ? "rounded-2xl px-3 -mx-1" : "px-2"}`}
                    style={isActive ? { background: "rgba(204,255,0,0.16)" } : undefined}
                    data-testid={`wait-stage-row-${idx}`}
                  >
                    {!isLast && (
                      <span
                        className="absolute w-[3px]"
                        style={{ left: isActive ? 29 : 25, top: 46, bottom: -8, background: isDone ? LIME : "#E4DFCE" }}
                        aria-hidden
                      />
                    )}

                    {isDone ? (
                      <span className="relative z-10 w-9 h-9 rounded-full flex items-center justify-center flex-shrink-0" style={{ background: INK }}>
                        <Check className="w-4.5 h-4.5" style={{ color: LIME, width: 18, height: 18 }} strokeWidth={3.2} />
                      </span>
                    ) : isActive ? (
                      <span className="relative z-10 w-9 h-9 rounded-full flex items-center justify-center flex-shrink-0" style={{ border: `3.5px solid ${LIME}`, background: "#FDFCF7" }}>
                        <span className="w-[18px] h-[18px] rounded-full" style={{ background: INK }} />
                      </span>
                    ) : (
                      <span className="relative z-10 w-9 h-9 rounded-full flex-shrink-0" style={{ border: "3px solid #CFCABA", background: "#FDFCF7" }} />
                    )}

                    <div className={`flex-1 min-w-0 pt-0.5 ${!isActive && !isLast ? "border-b border-[#ECE7D8] pb-3 -mb-3" : ""}`}>
                      <div className="flex items-center gap-2">
                        <span className="font-bold text-[15px] leading-tight" style={{ color: isDone ? "#232920" : isActive ? INK : "#8C877A" }}>
                          {row.title}
                        </span>
                        {isActive && row.now && (
                          <span className="text-[11px] font-extrabold tracking-[0.08em] uppercase px-2 py-[2px] rounded-md flex-shrink-0" style={{ background: LIME, color: INK }}>
                            Now
                          </span>
                        )}
                      </div>
                      <div className="mt-0.5 text-[12.5px] leading-snug" style={{ color: isDone || isActive ? "#6C7566" : "#A29D8E" }}>
                        {row.sub(tapsCount)}
                      </div>
                    </div>

                    {isDone && (
                      <span className="text-[14px] font-bold pt-1 flex-shrink-0" style={{ color: "#2F8F4E" }}>
                        Done
                      </span>
                    )}
                    {isActive && (
                      <span className="relative w-12 h-12 flex-shrink-0 flex items-center justify-center" aria-hidden>
                        <span className="absolute inset-0 rounded-full" style={{ border: `2px solid ${LIME}`, opacity: 0.5, animation: "wait-radar 1.6s ease-out infinite" }} />
                        <span className="absolute inset-[7px] rounded-full" style={{ border: `2px solid ${LIME}`, opacity: 0.65 }} />
                        <span className="w-4 h-4 rounded-full flex items-center justify-center" style={{ background: INK }}>
                          <span className="w-1.5 h-1.5 rounded-full" style={{ background: LIME }} />
                        </span>
                      </span>
                    )}
                  </div>
                );
              })}
            </div>

            {/* ── Scout tip card ──────────────────────────────── */}
            <div className="relative rounded-[22px] overflow-hidden mt-4 min-h-[168px]" style={{ background: "#0B0E0A" }} data-testid="wait-scout-tip">
              <img src="/assets/scout-tip.jpg" alt="" className="absolute right-0 top-0 h-full w-[58%] object-cover" />
              <div className="absolute inset-0" style={{ background: "linear-gradient(90deg, #0B0E0A 42%, rgba(11,14,10,0.72) 62%, rgba(11,14,10,0.05) 100%)" }} />
              <div className="relative z-10 p-5 flex gap-3.5 items-start">
                <span className="w-11 h-11 rounded-full flex items-center justify-center flex-shrink-0" style={{ border: `2px solid ${LIME}` }}>
                  <Lightbulb className="w-5 h-5" style={{ color: LIME }} strokeWidth={2} />
                </span>
                <div className="min-w-0">
                  <div className="text-[10.5px] font-extrabold tracking-[0.28em] uppercase" style={{ color: LIME }}>
                    Scout Tip
                  </div>
                  <div className="mt-1 font-barlow font-black uppercase text-white leading-[1.02] whitespace-nowrap" style={{ fontSize: "clamp(17px, 5.4vw, 24px)" }}>
                    Scan <span style={{ color: LIME }}>before</span> you receive
                  </div>
                  <p className="mt-1.5 text-[12.5px] leading-[1.5] max-w-[210px]" style={{ color: "rgba(255,255,255,0.82)" }}>
                    Scouts look at the details you don&rsquo;t see during the game.
                  </p>
                </div>
              </div>
            </div>

            {/* ── Leave-safe note + CTA ───────────────────────── */}
            <div className="mt-5 text-center">
              <p className="text-[13px] font-medium leading-[1.55]" style={{ color: "#2A2F26" }}>
                <Lock className="w-3.5 h-3.5 inline-block -mt-0.5 mr-1.5" strokeWidth={2.4} />
                Your Scout Report will appear here automatically.
                <br />
                You can safely leave—find it in your Dashboard when it&rsquo;s ready.
              </p>
              <button
                type="button"
                data-testid="wait-go-dashboard-btn"
                onClick={() => { if (onContinueInBackground) onContinueInBackground(); }}
                className="mt-4 inline-flex items-center justify-center gap-2.5 rounded-full px-12 py-4 font-barlow font-black uppercase tracking-[0.06em] text-[17px] transition-transform active:scale-[0.98] hover:brightness-95"
                style={{ background: LIME, color: INK, boxShadow: "0 14px 30px -14px rgba(120,150,0,0.55)" }}
              >
                <LayoutGrid className="w-[18px] h-[18px]" strokeWidth={2.6} fill="currentColor" />
                Go to Dashboard
              </button>
            </div>
          </div>
        )}
      </motion.div>
    </AnimatePresence>
  );
}

/* DONE phase — unchanged celebratory confirmation (user-approved earlier). */
function DoneScreen({ onViewReport }) {
  return (
    <div className="min-h-full flex items-center justify-center px-6 py-10">
      <div className="relative w-full max-w-md">
        <div className="relative h-32 mb-6 flex items-center justify-center">
          <motion.div
            className="absolute w-28 h-28 rounded-full border border-volt/40"
            animate={{ scale: [1, 1.5, 1], opacity: [0.55, 0, 0.55] }}
            transition={{ duration: 2, repeat: Infinity, ease: "easeOut" }}
          />
          <motion.div
            className="absolute w-20 h-20 rounded-full border-2 border-volt"
            animate={{ scale: [1, 1.25, 1] }}
            transition={{ duration: 1.4, repeat: Infinity, ease: "easeInOut" }}
          />
          <CheckCircle2 className="w-10 h-10 text-volt relative" strokeWidth={1.6} />
        </div>

        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.45 }}
          className="text-center"
          data-testid="scan-done-state"
        >
          <p className="text-forest text-[10px] uppercase tracking-[0.3em] font-bold mb-3">
            Precision Scout · Complete
          </p>
          <h3 className="font-barlow font-black uppercase text-ink text-3xl md:text-4xl tracking-tight leading-tight">
            Your scout report is ready
          </h3>
          <p className="mt-3 text-ink/75 text-sm leading-relaxed max-w-sm mx-auto">
            We&rsquo;ve locked onto your player, scored every touch, and written the full report. It&rsquo;s saved to your dashboard too — you can come back to it any time.
          </p>

          <button
            type="button"
            onClick={() => { if (onViewReport) onViewReport(); }}
            data-testid="scan-done-cta"
            className="mt-7 w-full flex items-center justify-center gap-2 py-4 bg-volt text-cream-base font-barlow font-black uppercase tracking-widest text-[13px] hover:bg-forest transition-colors shadow-[0_8px_24px_rgba(45,107,61,0.35)]"
          >
            <FileText className="w-4 h-4" strokeWidth={2.2} />
            View your scout report
            <ArrowRight className="w-4 h-4" strokeWidth={2.2} />
          </button>

          <p className="mt-4 text-ink/55 text-[11px]">
            Taking you there in a moment&hellip;
          </p>
        </motion.div>
      </div>
    </div>
  );
}
