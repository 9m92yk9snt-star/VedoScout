/**
 * PremiumReadyOverlay — Session 130
 *
 * Dedicated "Premium Ready" celebration screen shown to Premium / VIP / Admin /
 * Scout users right after their video upload finishes analysing. Deliberately
 * NEVER contains blur, locked sections, pricing tiers, or upgrade prompts —
 * those are reserved for the free-tier HeroTeaser flow.
 *
 * Rendered in place of HeroTeaser on UploadPage completion state (see the
 * `skipHeroTeaser` branching added in Session 127).
 */

import { motion, AnimatePresence } from "framer-motion";
import { Sparkles, ShieldCheck, Crown } from "lucide-react";

const RESOLVE_IMG = (report, assetBase) => {
  const src = report?.marker_url || report?.subject_crop_url || report?.poster_url;
  if (!src) return null;
  if (/^https?:\/\//i.test(src)) return src;
  return `${assetBase || ""}${src}`;
};

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
          transition={{ duration: 0.3 }}
          className="fixed inset-0 z-[80] flex items-center justify-center p-4 md:p-8"
          data-testid="premium-ready-overlay"
          style={{
            background: "radial-gradient(circle at 50% 30%, rgba(15,23,42,0.98) 0%, rgba(2,6,23,1) 65%)",
          }}
        >
          {/* Ambient light effects */}
          <div aria-hidden className="absolute -top-40 -right-40 w-[520px] h-[520px] rounded-full bg-volt/15 blur-3xl pointer-events-none" />
          <div aria-hidden className="absolute -bottom-40 -left-40 w-[520px] h-[520px] rounded-full bg-forest/20 blur-3xl pointer-events-none" />

          <motion.div
            initial={{ y: 32, opacity: 0, scale: 0.96 }}
            animate={{ y: 0, opacity: 1, scale: 1 }}
            transition={{ delay: 0.1, duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
            className="relative max-w-2xl w-full bg-gradient-to-br from-deepnavy via-ink to-deepnavy border-2 border-volt/40 p-8 md:p-14 text-center"
            style={{ boxShadow: "0 40px 80px -20px rgba(204,255,0,0.30), 0 0 0 1px rgba(204,255,0,0.10) inset" }}
          >
            {/* Premium badge */}
            <motion.div
              initial={{ opacity: 0, y: -8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.35, duration: 0.4 }}
              className="inline-flex items-center gap-2 mb-6"
            >
              <Crown className="w-4 h-4 text-volt" strokeWidth={2} />
              <span className="text-volt text-[11px] uppercase tracking-[0.4em] font-black">Premium Ready</span>
              <Crown className="w-4 h-4 text-volt" strokeWidth={2} />
            </motion.div>

            {/* Player marker image (if available — resolves via same R2 proxy as ReportPage) */}
            {playerImg && (
              <motion.div
                initial={{ scale: 0.85, opacity: 0 }}
                animate={{ scale: 1, opacity: 1 }}
                transition={{ delay: 0.45, duration: 0.5 }}
                className="relative mx-auto mb-6 w-32 h-32 md:w-36 md:h-36"
              >
                <div className="absolute inset-0 rounded-full bg-volt/25 blur-2xl" aria-hidden />
                <img
                  src={playerImg}
                  alt={`${playerName} — tracked marker`}
                  data-testid="premium-ready-player-img"
                  className="relative w-full h-full rounded-full object-cover border-2 border-volt/60"
                  style={{ boxShadow: "0 20px 40px -12px rgba(204,255,0,0.35)" }}
                  onError={(e) => { e.currentTarget.style.display = "none"; }}
                />
                <div className="absolute -bottom-1 -right-1 w-8 h-8 rounded-full bg-volt flex items-center justify-center border-2 border-deepnavy">
                  <ShieldCheck className="w-4 h-4 text-ink" strokeWidth={2.5} />
                </div>
              </motion.div>
            )}

            {/* Headline */}
            <motion.h2
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.55, duration: 0.5 }}
              className="font-barlow font-black uppercase text-4xl md:text-5xl text-cream-base tracking-tight leading-[0.95]"
              data-testid="premium-ready-headline"
            >
              <span className="inline-block mr-2" aria-hidden>✅</span>
              Your Premium<br />
              <span className="text-volt">Scout Report is Ready</span>
            </motion.h2>

            {/* Sub-text */}
            <motion.p
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.65, duration: 0.5 }}
              className="mt-5 text-cream-base/75 text-sm md:text-base max-w-md mx-auto leading-relaxed"
              data-testid="premium-ready-subtext"
            >
              Your analysis has been completed successfully.
            </motion.p>

            {/* Chapters preview strip */}
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: 0.75, duration: 0.4 }}
              className="mt-6 flex flex-wrap items-center justify-center gap-x-4 gap-y-2 text-[10px] uppercase tracking-[0.28em] font-bold text-cream-base/45"
            >
              <span>Technical</span>
              <span aria-hidden>·</span>
              <span>Tactical</span>
              <span aria-hidden>·</span>
              <span>Physical</span>
              <span aria-hidden>·</span>
              <span>Mentality</span>
            </motion.div>

            {/* Primary CTA */}
            <motion.button
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.85, duration: 0.5 }}
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
              onClick={onOpenReport}
              data-testid="premium-ready-open-btn"
              className="mt-9 inline-flex items-center justify-center gap-3 bg-volt hover:bg-forest-pop text-ink hover:text-white font-barlow font-black uppercase tracking-[0.22em] text-sm md:text-base px-10 py-4 transition-colors group"
              style={{ boxShadow: "0 16px 40px -10px rgba(204,255,0,0.55)" }}
            >
              <Sparkles className="w-4 h-4" />
              Open Full Premium Report
              <Sparkles className="w-4 h-4 transition-transform group-hover:rotate-12" />
            </motion.button>

            <motion.p
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: 0.95, duration: 0.4 }}
              className="mt-4 text-[10px] text-cream-base/45 uppercase tracking-[0.22em] font-bold flex items-center justify-center gap-1.5"
            >
              <ShieldCheck className="w-3 h-3" /> Elite-tier access · Included in your plan
            </motion.p>

            {/* Subtle dismiss */}
            {onDismiss && (
              <button
                onClick={onDismiss}
                className="absolute top-4 right-4 text-cream-base/40 hover:text-cream-base text-xs uppercase tracking-widest font-bold transition-colors"
                data-testid="premium-ready-dismiss-btn"
                aria-label="Close"
              >
                Close
              </button>
            )}
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
