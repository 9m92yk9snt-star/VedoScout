/**
 * PremiumReadyOverlay — the celebration screen premium-tier users see the
 * moment their video analysis finishes. NEVER contains blur, locked sections,
 * pricing tiers, or upgrade prompts — those live in the free-tier HeroTeaser.
 *
 * Cinematic stadium backdrop (Nano Banana generated) + gold "match complete"
 * treatment. Primary CTA opens the full dossier; secondary returns to dashboard.
 */

import { motion, AnimatePresence } from "framer-motion";
import { ShieldCheck, Crown, ArrowRight, LayoutDashboard, Target, Brain, Zap, Activity } from "lucide-react";

const RESOLVE_IMG = (report, assetBase) => {
  // Prefer the high-quality square DISPLAY crop (centred on the tapped player)
  const src = report?.display_crop_url || report?.subject_crop_url || report?.marker_url || report?.poster_url;
  if (!src) return null;
  if (/^https?:\/\//i.test(src)) return src;
  return `${assetBase || ""}${src}`;
};

const PILLARS = [
  { label: "Technical", Icon: Target },
  { label: "Tactical", Icon: Brain },
  { label: "Physical", Icon: Zap },
  { label: "Mentality", Icon: Activity },
];

export default function PremiumReadyOverlay({ open, report, assetBase, onOpenReport, onDismiss }) {
  const playerImg = RESOLVE_IMG(report, assetBase);
  const playerName = report?.player_details?.player_name || "your player";

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.35 }}
          className="fixed inset-0 z-[80] overflow-y-auto"
          data-testid="premium-ready-overlay"
        >
          {/* Cinematic stadium backdrop */}
          <div aria-hidden className="fixed inset-0 bg-[#04070B]">
            <img
              src="/assets/premium-ready-stadium.jpg"
              alt=""
              className="w-full h-full object-cover opacity-70"
            />
            <div className="absolute inset-0 bg-gradient-to-b from-[#04070B]/80 via-[#04070B]/45 to-[#04070B]/95" />
            <div className="absolute inset-0" style={{ background: "radial-gradient(ellipse at 50% 42%, transparent 0%, rgba(4,7,11,0.55) 70%, rgba(4,7,11,0.92) 100%)" }} />
          </div>

          {/* Gold + volt ambient glows */}
          <div aria-hidden className="fixed top-[8%] left-1/2 -translate-x-1/2 w-[640px] h-[280px] rounded-full bg-[#F5C443]/12 blur-3xl pointer-events-none" />
          <div aria-hidden className="fixed -bottom-32 -left-32 w-[420px] h-[420px] rounded-full bg-volt/10 blur-3xl pointer-events-none" />

          <div className="relative min-h-full flex items-center justify-center p-4 py-10 md:p-10">
            <motion.div
              initial={{ y: 36, opacity: 0, scale: 0.97 }}
              animate={{ y: 0, opacity: 1, scale: 1 }}
              transition={{ delay: 0.1, duration: 0.55, ease: [0.16, 1, 0.3, 1] }}
              className="relative max-w-2xl w-full text-center"
            >
              {/* Gold hairline crest badge */}
              <motion.div
                initial={{ opacity: 0, y: -10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.3, duration: 0.45 }}
                className="flex items-center justify-center gap-4 mb-8"
              >
                <span aria-hidden className="h-px w-14 md:w-24 bg-gradient-to-r from-transparent to-[#F5C443]/70" />
                <span className="inline-flex items-center gap-2 border border-[#F5C443]/45 bg-[#F5C443]/10 backdrop-blur-md px-4 py-2">
                  <Crown className="w-4 h-4 text-[#F5C443]" fill="#F5C443" />
                  <span className="text-[#F5C443] text-[10px] md:text-[11px] uppercase tracking-[0.4em] font-black">Premium Analysis Complete</span>
                </span>
                <span aria-hidden className="h-px w-14 md:w-24 bg-gradient-to-l from-transparent to-[#F5C443]/70" />
              </motion.div>

              {/* Player marker image with gold ring */}
              {playerImg && (
                <motion.div
                  initial={{ scale: 0.8, opacity: 0 }}
                  animate={{ scale: 1, opacity: 1 }}
                  transition={{ delay: 0.42, duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
                  className="relative mx-auto mb-7 w-32 h-32 md:w-40 md:h-40"
                >
                  <div className="absolute -inset-3 rounded-full border border-[#F5C443]/30" aria-hidden />
                  <div className="absolute inset-0 rounded-full bg-[#F5C443]/20 blur-2xl" aria-hidden />
                  <img
                    src={playerImg}
                    alt={`${playerName} — tracked marker`}
                    data-testid="premium-ready-player-img"
                    className="relative w-full h-full rounded-full object-cover border-2 border-[#F5C443]/80"
                    style={{ boxShadow: "0 24px 48px -12px rgba(245,196,67,0.4)" }}
                    onError={(e) => { e.currentTarget.style.display = "none"; }}
                  />
                  <div className="absolute -bottom-1 -right-1 w-9 h-9 rounded-full bg-volt flex items-center justify-center border-[3px] border-[#04070B]">
                    <ShieldCheck className="w-4.5 h-4.5 text-ink w-4 h-4" strokeWidth={2.5} />
                  </div>
                </motion.div>
              )}

              {/* Headline */}
              <motion.h2
                initial={{ opacity: 0, y: 14 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.52, duration: 0.5 }}
                className="font-barlow font-black uppercase text-4xl md:text-6xl text-white tracking-tight leading-[0.92]"
                data-testid="premium-ready-headline"
              >
                Your Scout Report<br />
                <span className="bg-gradient-to-r from-[#F5C443] via-[#FFE08A] to-[#F5C443] bg-clip-text text-transparent">Is Ready</span>
              </motion.h2>

              {/* Sub-text */}
              <motion.p
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.62, duration: 0.5 }}
                className="mt-5 text-white/70 text-sm md:text-base max-w-lg mx-auto leading-relaxed"
                data-testid="premium-ready-subtext"
              >
                Every touch, sprint and decision from <span className="text-white font-semibold">{playerName}</span>'s
                clip has been graded. Your full premium dossier is compiled and unlocked.
              </motion.p>

              {/* Pillar chips */}
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ delay: 0.72, duration: 0.45 }}
                className="mt-7 flex flex-wrap items-center justify-center gap-2.5"
              >
                {PILLARS.map(({ label, Icon }, i) => (
                  <motion.span
                    key={label}
                    initial={{ opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: 0.75 + i * 0.08, duration: 0.35 }}
                    className="inline-flex items-center gap-1.5 border border-white/15 bg-white/[0.06] backdrop-blur-md px-3.5 py-1.5 text-[10px] uppercase tracking-[0.24em] font-bold text-white/80"
                  >
                    <Icon className="w-3 h-3 text-volt" />
                    {label}
                  </motion.span>
                ))}
              </motion.div>

              {/* Primary CTA */}
              <motion.div
                initial={{ opacity: 0, y: 16 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.9, duration: 0.5 }}
                className="mt-10 flex flex-col sm:flex-row items-center justify-center gap-3"
              >
                <motion.button
                  whileHover={{ scale: 1.02 }}
                  whileTap={{ scale: 0.98 }}
                  onClick={onOpenReport}
                  data-testid="premium-ready-open-btn"
                  className="inline-flex items-center justify-center gap-3 bg-volt hover:bg-forest-pop text-ink hover:text-white font-barlow font-black uppercase tracking-[0.2em] text-sm md:text-base px-10 py-4 transition-colors group w-full sm:w-auto"
                  style={{ boxShadow: "0 18px 44px -10px rgba(204,255,0,0.5)" }}
                >
                  Open Full Premium Report
                  <ArrowRight className="w-4 h-4 transition-transform group-hover:translate-x-1" />
                </motion.button>
                <motion.button
                  whileHover={{ scale: 1.02 }}
                  whileTap={{ scale: 0.98 }}
                  onClick={onDismiss}
                  data-testid="premium-ready-dashboard-btn"
                  className="inline-flex items-center justify-center gap-2 border border-white/25 bg-white/[0.05] backdrop-blur-md text-white/85 hover:text-white hover:border-white/45 font-barlow font-black uppercase tracking-[0.2em] text-xs md:text-sm px-7 py-4 transition-colors w-full sm:w-auto"
                >
                  <LayoutDashboard className="w-4 h-4" />
                  Go to Dashboard
                </motion.button>
              </motion.div>

              <motion.p
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ delay: 1.05, duration: 0.4 }}
                className="mt-5 text-[10px] text-[#F5C443]/80 uppercase tracking-[0.24em] font-bold flex items-center justify-center gap-1.5"
              >
                <ShieldCheck className="w-3 h-3" /> Included in your plan · No extra charge
              </motion.p>

              {/* Subtle dismiss */}
              {onDismiss && (
                <button
                  onClick={onDismiss}
                  className="absolute -top-2 right-0 md:top-0 text-white/40 hover:text-white text-xs uppercase tracking-widest font-bold transition-colors"
                  data-testid="premium-ready-dismiss-btn"
                  aria-label="Close"
                >
                  Close
                </button>
              )}
            </motion.div>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
