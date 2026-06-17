import React, { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Crosshair, Activity, Volume2, Brain, ScanSearch } from "lucide-react";

/**
 * PrecisionScanOverlay
 * Full-screen premium loader shown while the AI runs the multi-signal pipeline:
 *   1. Locking onto the player (visual fingerprint)
 *   2. Tracking the player across frames
 *   3. Listening for audio peaks (crowd / whistle / goal cheer)
 *   4. Detecting events
 *   5. Writing the scout report
 *
 * Pure visual feedback — does not call any API. Parent component drives the
 * lifecycle by mounting/unmounting this overlay.
 */
const STEPS = [
  { id: 1, title: "Locking onto your player", caption: "Reading jersey + shorts colour and body shape", icon: Crosshair, dur: 5 },
  { id: 2, title: "Tracking across every frame", caption: "Following only the player in your box", icon: ScanSearch, dur: 9 },
  { id: 3, title: "Listening for crowd peaks", caption: "Cross-checking goals against the audio timeline", icon: Volume2, dur: 5 },
  { id: 4, title: "Detecting actions on the ball", caption: "Goals, shots, dribbles, key passes, tackles", icon: Activity, dur: 9 },
  { id: 5, title: "Writing your scout report", caption: "Confident voice — no guesses, no hedging", icon: Brain, dur: 8 },
];

export default function PrecisionScanOverlay({ open }) {
  const [stepIdx, setStepIdx] = useState(0);
  const [elapsed, setElapsed] = useState(0);

  // Step progression — loops on the last step until parent dismisses the overlay
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
      // Sum durations to figure out the active step
      let acc = 0;
      for (let i = 0; i < STEPS.length; i++) {
        acc += STEPS[i].dur;
        if (t < acc) {
          setStepIdx(i);
          return;
        }
      }
      // Past the last step — hold on it
      setStepIdx(STEPS.length - 1);
    };
    const id = setInterval(tick, 1000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [open]);
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
        className="fixed inset-0 z-[100] bg-deepnavy/95 backdrop-blur-md flex items-center justify-center px-6"
        data-testid="precision-scan-overlay"
      >
        {/* subtle radial halo */}
        <div
          aria-hidden
          className="absolute inset-0 pointer-events-none"
          style={{
            background:
              "radial-gradient(circle at 50% 35%, rgba(204,255,0,0.10), transparent 60%)",
          }}
        />

        <div className="relative w-full max-w-md">
          {/* Crosshair pulse */}
          <div className="relative h-40 mb-8 flex items-center justify-center">
            <motion.div
              className="absolute w-32 h-32 rounded-full border border-volt/40"
              animate={{ scale: [1, 1.6, 1], opacity: [0.6, 0, 0.6] }}
              transition={{ duration: 2, repeat: Infinity, ease: "easeOut" }}
            />
            <motion.div
              className="absolute w-20 h-20 rounded-full border-2 border-volt"
              animate={{ scale: [1, 1.3, 1] }}
              transition={{ duration: 1.4, repeat: Infinity, ease: "easeInOut" }}
            />
            <Crosshair className="w-10 h-10 text-volt relative" strokeWidth={1.5} />
          </div>

          {/* Active step label */}
          <AnimatePresence mode="wait">
            <motion.div
              key={STEPS[stepIdx].id}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.3 }}
              className="text-center mb-8"
            >
              <p className="text-volt text-[10px] uppercase tracking-[0.3em] font-bold mb-3">
                Precision Scout · Step {STEPS[stepIdx].id} of {STEPS.length}
              </p>
              <h3 className="font-barlow font-black uppercase text-cream-card text-2xl md:text-3xl tracking-tight leading-tight">
                {STEPS[stepIdx].title}
              </h3>
              <p className="mt-3 text-cream-card/65 text-sm">
                {STEPS[stepIdx].caption}
              </p>
            </motion.div>
          </AnimatePresence>

          {/* Step ladder */}
          <div className="space-y-2.5">
            {STEPS.map((s, i) => {
              const Icon = s.icon;
              const isActive = i === stepIdx;
              const isDone = i < stepIdx;
              return (
                <div
                  key={s.id}
                  className={`flex items-center gap-3 px-3 py-2 border transition-colors ${
                    isActive
                      ? "border-volt/60 bg-volt/[0.06]"
                      : isDone
                      ? "border-forest-pop/40 bg-forest-pop/[0.04]"
                      : "border-cream-card/10 bg-cream-card/[0.02]"
                  }`}
                >
                  <Icon
                    className={`w-4 h-4 flex-shrink-0 ${
                      isActive
                        ? "text-volt"
                        : isDone
                        ? "text-forest-pop"
                        : "text-cream-card/35"
                    }`}
                    strokeWidth={1.6}
                  />
                  <span
                    className={`text-[12px] uppercase tracking-widest font-bold flex-1 ${
                      isActive
                        ? "text-cream-card"
                        : isDone
                        ? "text-forest-pop"
                        : "text-cream-card/40"
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
                    <span className="text-forest-pop text-[10px] uppercase tracking-widest font-bold">
                      ✓
                    </span>
                  )}
                </div>
              );
            })}
          </div>

          {/* Elapsed time, no fake progress bar */}
          <p className="mt-6 text-center text-cream-card/40 text-[10px] uppercase tracking-[0.3em] font-bold">
            Elapsed · {Math.floor(elapsed / 60)
              .toString()
              .padStart(2, "0")}
            :{(elapsed % 60).toString().padStart(2, "0")}
          </p>
        </div>
      </motion.div>
    </AnimatePresence>
  );
}
