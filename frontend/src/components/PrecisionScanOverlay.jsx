import React, { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Crosshair, Activity, Volume2, Brain, ScanSearch, UploadCloud, CheckCircle2, FileText, ArrowRight } from "lucide-react";
import KnowledgeCarousel from "./KnowledgeCarousel";

/**
 * PrecisionScanOverlay
 * Full-screen premium loader with three phases:
 *   • UPLOADING — real upload-progress percentage from XHR.upload.onprogress
 *   • ANALYZING — 5-step Precision Scout ladder (auto-progressing)
 *   • DONE      — celebratory "report ready" confirmation with primary CTA
 * Beneath uploading/analyzing, a rotating KnowledgeCarousel keeps the user engaged.
 *
 * Props
 *   open      — boolean
 *   phase     — 'uploading' | 'analyzing' | 'done' (defaults to analyzing)
 *   uploadPct — 0..100 number, used only when phase === 'uploading'
 *   onViewReport — () => void, called when the user taps the done-phase CTA
 */
const ANALYSE_STEPS = [
  { id: 1, title: "Locking onto your player", caption: "Reading jersey + shorts colour and body shape", icon: Crosshair, dur: 5 },
  { id: 2, title: "Tracking across every frame", caption: "Following only the player in your anchors", icon: ScanSearch, dur: 9 },
  { id: 3, title: "Listening for crowd peaks", caption: "Cross-checking goals against the audio timeline", icon: Volume2, dur: 5 },
  { id: 4, title: "Detecting actions on the ball", caption: "Goals, shots, dribbles, key passes, tackles", icon: Activity, dur: 9 },
  { id: 5, title: "Writing your scout report", caption: "Confident voice — no guesses, no hedging", icon: Brain, dur: 8 },
];

export default function PrecisionScanOverlay({ open, phase = "analyzing", uploadPct = 0, onViewReport, onContinueInBackground }) {
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
            {phase === "done" ? (
              <CheckCircle2 className="w-10 h-10 text-volt relative" strokeWidth={1.6} />
            ) : phase === "uploading" ? (
              <UploadCloud className="w-9 h-9 text-volt relative" strokeWidth={1.5} />
            ) : (
              <Crosshair className="w-9 h-9 text-volt relative" strokeWidth={1.5} />
            )}
          </div>

          {phase === "done" ? (
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
          ) : phase === "uploading" ? (
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
                      className={`flex items-start gap-2.5 px-3 py-2 border transition-colors ${
                        isActive
                          ? "border-forest/40 bg-forest/[0.06]"
                          : isDone
                          ? "border-forest-pop/40 bg-forest-pop/[0.04]"
                          : "border-gray-border/70 bg-cream-card/60"
                      }`}
                    >
                      <Icon
                        className={`w-3.5 h-3.5 flex-shrink-0 mt-0.5 ${
                          isActive ? "text-forest" : isDone ? "text-forest-pop" : "text-ink/45"
                        }`}
                        strokeWidth={1.6}
                      />
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span
                            className={`text-[11px] uppercase tracking-widest font-bold ${
                              isActive ? "text-ink" : isDone ? "text-forest-pop" : "text-ink/65"
                            }`}
                          >
                            {s.title}
                          </span>
                          {isActive && (
                            <motion.span
                              className="w-1.5 h-1.5 rounded-full bg-forest"
                              animate={{ opacity: [1, 0.3, 1] }}
                              transition={{ duration: 1, repeat: Infinity }}
                            />
                          )}
                          {isDone && (
                            <span className="text-forest-pop text-[10px] font-bold ml-auto">✓</span>
                          )}
                        </div>
                        {/* Always-visible caption so the user understands what each step actually does. */}
                        <p className={`mt-0.5 text-[10.5px] leading-snug ${
                          isActive ? "text-ink/75" : isDone ? "text-forest-pop/80" : "text-ink/50"
                        }`}>
                          {s.caption}
                        </p>
                      </div>
                    </div>
                  );
                })}
              </div>
            </>
          )}

          {phase !== "done" && (
            <>
              <div className="mt-2 pt-5 border-t border-forest/15">
                <p className="text-center text-forest/75 text-[9px] uppercase tracking-[0.3em] font-bold mb-3">
                  While you wait
                </p>
                <KnowledgeCarousel />
              </div>

              <p className="mt-6 text-center text-forest/70 text-[10px] uppercase tracking-[0.3em] font-bold">
                Elapsed · {Math.floor(elapsed / 60).toString().padStart(2, "0")}:{(elapsed % 60).toString().padStart(2, "0")}
              </p>

              {/* "Continue in background" — appears for the analysing phase only,
                  and only after the upload itself is done. Lets the user dismiss
                  the overlay & keep browsing while the report cooks server-side.
                  They get a floating tracker pill + a toast when it's ready. */}
              {phase === "analyzing" && onContinueInBackground && (
                <button
                  type="button"
                  data-testid="overlay-continue-in-background"
                  onClick={onContinueInBackground}
                  className="mt-4 mx-auto block text-forest/85 hover:text-forest text-[11px] uppercase tracking-[0.22em] font-bold underline underline-offset-4 decoration-forest/40 hover:decoration-forest transition-colors"
                >
                  Continue in background →
                </button>
              )}
            </>
          )}
        </div>
      </motion.div>
    </AnimatePresence>
  );
}
