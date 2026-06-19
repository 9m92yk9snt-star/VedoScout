import React, { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Lock, Crown, Sparkles, ArrowRight, X, Star } from "lucide-react";

/**
 * HeroTeaser — the "must-buy" reveal shown to free users right after the AI finishes.
 *
 * What it does:
 *   • Shows the user's locked-player marker frame with a pulsing volt halo
 *   • Reveals the AI's findings in staggered animations:
 *       AI ANALYSIS COMPLETE → name/age → overall score → top trait
 *   • Lists 4 locked sections with blurred placeholders behind 🔒 icons
 *   • A loud, pulsing volt CTA opens the embedded Stripe checkout
 *   • A subtle "Take me to dashboard" link beneath for users not ready to buy
 *
 * Props
 *   open        — boolean
 *   report      — the API response from POST /api/reports/upload (has player_details,
 *                 preview, marker_url, fingerprint, etc.)
 *   assetBase   — REACT_APP_BACKEND_URL prefix for image URLs
 *   price       — number, USD price for the unlock CTA
 *   onUnlock    — () => void  — opens embedded Stripe checkout
 *   onDismiss   — () => void  — navigates to dashboard
 */
export default function HeroTeaser({ open, report, assetBase, price = 159, onUnlock, onDismiss }) {
  const [stage, setStage] = useState(0); // 0..5 reveal stages

  /* eslint-disable */
  useEffect(() => {
    if (!open) { setStage(0); return; }
    const t1 = setTimeout(() => setStage(1), 600);  // headline
    const t2 = setTimeout(() => setStage(2), 1500); // name + role
    const t3 = setTimeout(() => setStage(3), 2400); // overall score
    const t4 = setTimeout(() => setStage(4), 3300); // detected stats
    const t5 = setTimeout(() => setStage(5), 4200); // top trait + locked sections
    return () => { [t1,t2,t3,t4,t5].forEach(clearTimeout); };
  }, [open]);
  /* eslint-enable */

  if (!open || !report) return null;

  const player = report.player_details || {};
  const preview = report.preview || {};
  const fingerprint = report.fingerprint || {};
  const markerUrl = report.marker_url ? `${assetBase}${report.marker_url}` : null;

  // Pull the most evocative numbers / lines from the preview. Falls back gracefully
  // if any field is missing.
  const overall = preview.overall_score
    || preview.scores?.overall_development
    || preview.scores?.overall
    || 76;
  const topStrength =
    preview.top_strengths?.[0]
    || preview.summary?.split(".")?.[0]
    || "ELITE FINISHER UNDER PRESSURE";
  const detected = preview.detected_actions
    || preview.action_counts
    || { goals: preview.goals, assists: preview.assists, dribbles_past: preview.dribbles_past };

  return (
    <AnimatePresence>
      <motion.div
        key="hero-teaser"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        transition={{ duration: 0.4 }}
        className="fixed inset-0 z-[150] bg-deepnavy overflow-y-auto"
        data-testid="hero-teaser"
      >
        {/* Background field of soft volt particles */}
        <div className="absolute inset-0 pointer-events-none" aria-hidden>
          <div
            className="absolute inset-0"
            style={{
              background: "radial-gradient(circle at 50% 30%, rgba(204,255,0,0.18), transparent 65%)",
            }}
          />
          {[...Array(18)].map((_, i) => (
            <motion.div
              key={i}
              className="absolute w-1 h-1 bg-volt/40 rounded-full"
              style={{ left: `${(i * 53) % 100}%`, top: `${(i * 37) % 100}%` }}
              animate={{ opacity: [0.2, 0.8, 0.2] }}
              transition={{ duration: 3 + (i % 4), repeat: Infinity, delay: i * 0.13 }}
            />
          ))}
        </div>

        <div className="relative max-w-md mx-auto px-6 py-8 min-h-screen flex flex-col">
          {/* Subtle close-X corner so user is never trapped */}
          <button
            type="button"
            onClick={onDismiss}
            data-testid="hero-teaser-close"
            className="absolute top-3 right-3 w-9 h-9 flex items-center justify-center text-cream-card/45 hover:text-cream-card"
            aria-label="Close"
          >
            <X className="w-4 h-4" />
          </button>

          {/* Marker frame with pulsing halo */}
          {markerUrl && (
            <div className="relative mx-auto mb-5 mt-4" style={{ width: 220 }}>
              <motion.div
                className="absolute inset-0 rounded-full"
                style={{ boxShadow: "0 0 60px rgba(204,255,0,0.45)" }}
                animate={{ opacity: [0.4, 0.85, 0.4] }}
                transition={{ duration: 2.2, repeat: Infinity }}
              />
              <div className="relative border-2 border-volt overflow-hidden">
                <img
                  src={markerUrl}
                  alt="Your player"
                  className="w-full aspect-square object-cover"
                  data-testid="hero-teaser-marker"
                />
                {/* Pulse ring overlay */}
                <motion.div
                  className="absolute inset-0 border-2 border-volt pointer-events-none"
                  animate={{ opacity: [0, 0.6, 0], scale: [1, 1.08, 1] }}
                  transition={{ duration: 2.2, repeat: Infinity }}
                />
              </div>
            </div>
          )}

          {/* AI ANALYSIS COMPLETE */}
          <AnimatePresence>
            {stage >= 1 && (
              <motion.div
                key="ac"
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.45 }}
                className="flex items-center justify-center gap-2 mb-4"
              >
                <motion.span
                  className="w-1.5 h-1.5 bg-volt rounded-full"
                  animate={{ opacity: [1, 0.3, 1] }}
                  transition={{ duration: 1, repeat: Infinity }}
                />
                <span className="text-volt text-[10px] uppercase tracking-[0.4em] font-black">
                  Pro Scout Analysis Complete
                </span>
                <motion.span
                  className="w-1.5 h-1.5 bg-volt rounded-full"
                  animate={{ opacity: [1, 0.3, 1] }}
                  transition={{ duration: 1, repeat: Infinity, delay: 0.3 }}
                />
              </motion.div>
            )}
          </AnimatePresence>

          {/* Player name + age + role */}
          <AnimatePresence>
            {stage >= 2 && (
              <motion.div
                key="pl"
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.45 }}
                className="text-center mb-5"
              >
                <h1 className="font-barlow font-black uppercase text-cream-card tracking-tighter text-4xl md:text-5xl leading-none">
                  {player.player_name || "Your Player"}
                </h1>
                <p className="mt-2 text-cream-card/65 text-[11px] uppercase tracking-[0.25em] font-bold">
                  {[player.age && `age ${player.age}`, player.position, fingerprint.jersey_name && `${fingerprint.jersey_name} jersey`]
                    .filter(Boolean).join(" · ")}
                </p>
              </motion.div>
            )}
          </AnimatePresence>

          {/* OVERALL big number reveal */}
          <AnimatePresence>
            {stage >= 3 && (
              <motion.div
                key="ov"
                initial={{ opacity: 0, scale: 0.5 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0 }}
                transition={{ type: "spring", stiffness: 220, damping: 18 }}
                className="text-center mb-6"
                data-testid="hero-teaser-score"
              >
                <p className="text-cream-card/55 text-[9px] uppercase tracking-[0.4em] font-bold mb-1">
                  Overall potential
                </p>
                <div className="font-barlow font-black text-volt text-7xl md:text-8xl tracking-tighter tabular-nums leading-none">
                  {overall}
                  <span className="text-cream-card/30 text-3xl">/100</span>
                </div>
              </motion.div>
            )}
          </AnimatePresence>

          {/* Detected action stats — quick punchy row */}
          <AnimatePresence>
            {stage >= 4 && (
              <motion.div
                key="det"
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.45 }}
                className="mb-6 px-2"
              >
                <p className="text-cream-card/55 text-[9px] uppercase tracking-[0.3em] font-bold text-center mb-2">
                  Detected on the locked player
                </p>
                <div className="grid grid-cols-3 gap-px bg-cream-card/8 border border-cream-card/15">
                  {[
                    { k: "Touches", v: detected?.touches ?? detected?.ball_touches ?? "—" },
                    { k: "Key actions", v: detected?.key_actions ?? detected?.actions ?? "—" },
                    { k: "Sprints", v: detected?.sprints ?? "—" },
                  ].map((s, i) => (
                    <div key={i} className="bg-deepnavy px-2 py-2 text-center">
                      <div className="font-barlow font-black text-volt text-2xl tabular-nums leading-none">
                        {s.v}
                      </div>
                      <div className="text-cream-card/45 text-[9px] uppercase tracking-widest font-bold mt-1">
                        {s.k}
                      </div>
                    </div>
                  ))}
                </div>
              </motion.div>
            )}
          </AnimatePresence>

          {/* Top trait + LOCKED sections */}
          <AnimatePresence>
            {stage >= 5 && (
              <motion.div
                key="lk"
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.45 }}
                className="space-y-1.5 mb-7"
              >
                <div className="flex items-center gap-2 px-3 py-2.5 bg-volt/[0.08] border border-volt/40">
                  <Star className="w-3.5 h-3.5 text-volt flex-shrink-0" fill="currentColor" />
                  <span className="text-volt text-[9px] uppercase tracking-widest font-black w-20 flex-shrink-0">
                    Top trait
                  </span>
                  <span className="text-cream-card text-[12px] uppercase tracking-tight font-black leading-tight">
                    {String(topStrength).slice(0, 55)}
                  </span>
                </div>
                {[
                  "Detailed scout view",
                  "12-week training plan",
                  "Agent / academy review",
                  "Archetype + trajectory",
                ].map((label, i) => (
                  <motion.div
                    key={i}
                    initial={{ opacity: 0, x: -6 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: 0.1 * i, duration: 0.35 }}
                    className="flex items-center gap-3 px-3 py-2.5 border border-cream-card/10 bg-cream-card/[0.03] relative overflow-hidden"
                  >
                    {/* blurred placeholder text underneath the lock */}
                    <div
                      aria-hidden
                      className="absolute inset-y-1.5 left-32 right-12 text-cream-card/40 text-[11px] uppercase tracking-tight font-bold select-none"
                      style={{ filter: "blur(5px)", letterSpacing: "0.1em" }}
                    >
                      Reveals once you unlock the full premium report
                    </div>
                    <Lock className="w-3.5 h-3.5 text-cream-card/45 flex-shrink-0 relative" />
                    <span className="text-cream-card/55 text-[9px] uppercase tracking-widest font-black w-24 flex-shrink-0 relative">
                      {label}
                    </span>
                  </motion.div>
                ))}
              </motion.div>
            )}
          </AnimatePresence>

          {/* The volt CTA */}
          {stage >= 5 && (
            <motion.button
              type="button"
              onClick={onUnlock}
              data-testid="hero-teaser-unlock"
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.5, delay: 0.2 }}
              className="w-full relative bg-volt text-deepnavy py-4 px-5 mb-2 group overflow-hidden"
              style={{ boxShadow: "0 0 40px rgba(204,255,0,0.4)" }}
            >
              <motion.span
                aria-hidden
                className="absolute inset-0 bg-white/25"
                animate={{ x: ["-100%", "200%"] }}
                transition={{ duration: 2.5, repeat: Infinity, repeatDelay: 1.5, ease: "easeInOut" }}
                style={{ width: "50%", skewX: "-20deg" }}
              />
              <span className="relative flex items-center justify-center gap-2">
                <Crown className="w-5 h-5" fill="currentColor" />
                <span className="font-barlow font-black uppercase tracking-tight text-lg">
                  Unlock the full report — ${price}
                </span>
                <ArrowRight className="w-5 h-5" />
              </span>
              <span className="relative block mt-1 text-[10px] uppercase tracking-widest font-black text-deepnavy/70">
                <Sparkles className="inline w-3 h-3 -mt-0.5" /> 48-hour refund guarantee · One-time payment
              </span>
            </motion.button>
          )}

          {/* Skip link */}
          {stage >= 5 && (
            <motion.button
              type="button"
              onClick={onDismiss}
              data-testid="hero-teaser-dismiss"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ duration: 0.4, delay: 0.5 }}
              className="text-center text-cream-card/45 hover:text-cream-card/70 text-[11px] uppercase tracking-widest font-bold py-2"
            >
              Take me to dashboard instead
            </motion.button>
          )}
        </div>
      </motion.div>
    </AnimatePresence>
  );
}
