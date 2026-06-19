import React, { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Crosshair, Activity, Volume2, Brain, ScanSearch, UploadCloud } from "lucide-react";
import KnowledgeCarousel from "./KnowledgeCarousel";

/**
 * PrecisionScanOverlay
 * Full-screen premium loader with two phases:
 *   • UPLOADING — real upload-progress percentage from XHR.upload.onprogress
 *   • ANALYZING — 5-step Precision Scout ladder (auto-progressing)
 * Beneath both, a rotating KnowledgeCarousel keeps the user engaged.
 *
 * Props
 *   open      — boolean
 *   phase     — 'uploading' | 'analyzing' | undefined (defaults to analyzing)
 *   uploadPct — 0..100 number, used only when phase === 'uploading'
 */
const ANALYSE_STEPS = [
  { id: 1, title: "Locking onto your player", caption: "Reading jersey + shorts colour and body shape", icon: Crosshair, dur: 5 },
  { id: 2, title: "Tracking across every frame", caption: "Following only the player in your anchors", icon: ScanSearch, dur: 9 },
  { id: 3, title: "Listening for crowd peaks", caption: "Cross-checking goals against the audio timeline", icon: Volume2, dur: 5 },
  { id: 4, title: "Detecting actions on the ball", caption: "Goals, shots, dribbles, key passes, tackles", icon: Activity, dur: 9 },
  { id: 5, title: "Writing your scout report", caption: "Confident voice — no guesses, no hedging", icon: Brain, dur: 8 },
];

export default function PrecisionScanOverlay({ open, phase = "analyzing", uploadPct = 0 }) {
  const [stepIdx, setStepIdx] = useState(0);
  const [elapsed, setElapsed] = useState(0);

  /* eslint-disable */
  useEffect(() => {
    if (!open) {
      setStepIdx(0);
      setElapsed(0);
      return;
    }
    let cancelled = false;
    let t = 0;
    const tick = () => {
      if (cancelled) return;
      t += 1;
      setElapsed(t);
      if (phase === "analyzing") {
        let acc = 0;
        for (let i = 0; i < ANALYSE_STEPS.length; i++) {
          acc += ANALYSE_STEPS[i].dur;
          if (t < acc) { setStepIdx(i); return; }
        }
        setStepIdx(ANALYSE_STEPS.length - 1);
      }
    };
    const id = setInterval(tick, 1000);
    return () => { cancelled = true; clearInterval(id); };
  }, [open, phase]);
  /* eslint-enable */

  if (!open) return null;

  return (
    <AnimatePresence>
      <motion.div
        key="scan-overlay"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        transition={{ duration: 0.35 }}
        className="fixed inset-0 z-[100] bg-deepnavy/95 backdrop-blur-md flex items-center justify-center px-6 py-8 overflow-y-auto"
        data-testid="precision-scan-overlay"
      >
        <div
          aria-hidden
          className="absolute inset-0 pointer-events-none"
          style={{
            background:
              "radial-gradient(circle at 50% 35%, rgba(204,255,0,0.10), transparent 60%)",
          }}
        />

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
            {phase === "uploading" ? (
              <UploadCloud className="w-9 h-9 text-volt relative" strokeWidth={1.5} />
            ) : (
              <Crosshair className="w-9 h-9 text-volt relative" strokeWidth={1.5} />
            )}
          </div>

          {phase === "uploading" ? (
            <>
              <div className="text-center mb-6">
                <p className="text-forest text-[10px] uppercase tracking-[0.3em] font-bold mb-3">
                  Precision Scout · Uploading
                </p>
                <h3 className="font-barlow font-black uppercase text-ink text-2xl md:text-3xl tracking-tight leading-tight">
                  Sending your video
                </h3>
                <p className="mt-2 text-ink/70 text-sm">
                  This usually takes 10–60 seconds depending on your connection.
                </p>
              </div>

              <div className="text-center mb-4">
                <div className="font-barlow font-black text-forest text-6xl md:text-7xl tracking-tighter tabular-nums leading-none" data-testid="upload-pct">
                  {Math.round(uploadPct)}%
                </div>
              </div>

              <div className="h-2 bg-cream-card/10 mb-3 overflow-hidden">
                <motion.div
                  className="h-full bg-volt"
                  initial={{ width: 0 }}
                  animate={{ width: `${uploadPct}%` }}
                  transition={{ duration: 0.3, ease: "easeOut" }}
                />
              </div>
              <p className="text-center text-forest/80 text-[10px] uppercase tracking-[0.3em] font-bold mb-7">
                {uploadPct < 100 ? "Uploading…" : "Upload complete — analysing"}
              </p>
            </>
          ) : (
            <>
              <AnimatePresence mode="wait">
                <motion.div
                  key={ANALYSE_STEPS[stepIdx].id}
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -8 }}
                  transition={{ duration: 0.3 }}
                  className="text-center mb-6"
                >
                  <p className="text-forest text-[10px] uppercase tracking-[0.3em] font-bold mb-3">
                    Precision Scout · Step {ANALYSE_STEPS[stepIdx].id} of {ANALYSE_STEPS.length}
                  </p>
                  <h3 className="font-barlow font-black uppercase text-ink text-2xl md:text-3xl tracking-tight leading-tight">
                    {ANALYSE_STEPS[stepIdx].title}
                  </h3>
                  <p className="mt-2 text-ink/70 text-sm">
                    {ANALYSE_STEPS[stepIdx].caption}
                  </p>
                </motion.div>
              </AnimatePresence>

              <div className="space-y-2 mb-4">
                {ANALYSE_STEPS.map((s, i) => {
                  const Icon = s.icon;
                  const isActive = i === stepIdx;
                  const isDone = i < stepIdx;
                  return (
                    <div
                      key={s.id}
                      className={`flex items-center gap-2.5 px-3 py-1.5 border transition-colors ${
                        isActive
                          ? "border-volt/60 bg-volt/[0.06]"
                          : isDone
                          ? "border-forest-pop/40 bg-forest-pop/[0.04]"
                          : "border-cream-card/10 bg-cream-card/[0.02]"
                      }`}
                    >
                      <Icon
                        className={`w-3.5 h-3.5 flex-shrink-0 ${
                          isActive ? "text-forest" : isDone ? "text-forest-pop" : "text-ink/35"
                        }`}
                        strokeWidth={1.6}
                      />
                      <span
                        className={`text-[11px] uppercase tracking-widest font-bold flex-1 ${
                          isActive ? "text-ink" : isDone ? "text-forest-pop" : "text-ink/45"
                        }`}
                      >
                        {s.title}
                      </span>
                      {isActive && (
                        <motion.span
                          className="w-1.5 h-1.5 rounded-full bg-volt"
                          animate={{ opacity: [1, 0.3, 1] }}
                          transition={{ duration: 1, repeat: Infinity }}
                        />
                      )}
                      {isDone && (
                        <span className="text-forest-pop text-[10px] uppercase tracking-widest font-bold">✓</span>
                      )}
                    </div>
                  );
                })}
              </div>
            </>
          )}

          <div className="mt-2 pt-5 border-t border-cream-card/10">
            <p className="text-center text-forest/75 text-[9px] uppercase tracking-[0.3em] font-bold mb-3">
              While you wait
            </p>
            <KnowledgeCarousel />
          </div>

          <p className="mt-6 text-center text-forest/70 text-[10px] uppercase tracking-[0.3em] font-bold">
            Elapsed · {Math.floor(elapsed / 60).toString().padStart(2, "0")}:{(elapsed % 60).toString().padStart(2, "0")}
          </p>
        </div>
      </motion.div>
    </AnimatePresence>
  );
}
