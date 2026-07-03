/**
 * PremiumReadyBanner — Session 130
 *
 * Renders at the very top of ReportPage for Premium / VIP / Admin / Scout users
 * (or any report where is_paid || manually_unlocked). It is the visual signal
 * that this is a fully-unlocked premium report — zero blur, zero pricing, zero
 * upgrade prompts anywhere below.
 *
 * The click target smooth-scrolls to the report chapters container so the user
 * immediately lands on the Technical / Tactical / Physical / Mentality sections.
 */

import { motion } from "framer-motion";
import { ShieldCheck, Sparkles, Crown } from "lucide-react";

export default function PremiumReadyBanner({ playerName, onOpenReport }) {
  return (
    <motion.section
      initial={{ opacity: 0, y: -12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
      data-testid="premium-ready-banner"
      className="mt-6 relative bg-gradient-to-br from-deepnavy via-ink to-deepnavy border-2 border-volt/40 p-6 md:p-8 overflow-hidden"
      style={{
        boxShadow: "0 24px 60px -20px rgba(204,255,0,0.28), 0 0 0 1px rgba(204,255,0,0.10) inset",
      }}
    >
      <div aria-hidden className="absolute -top-24 -right-24 w-56 h-56 rounded-full bg-volt/20 blur-3xl pointer-events-none" />
      <div aria-hidden className="absolute -bottom-24 -left-24 w-56 h-56 rounded-full bg-forest/25 blur-3xl pointer-events-none" />

      <div className="relative flex flex-col md:flex-row items-start md:items-center justify-between gap-6">
        <div className="flex-1 min-w-0">
          <div className="inline-flex items-center gap-2 mb-3">
            <Crown className="w-4 h-4 text-volt" strokeWidth={2} />
            <span className="text-volt text-[10px] uppercase tracking-[0.35em] font-black">Premium Ready</span>
          </div>
          <h2
            className="font-barlow font-black uppercase text-2xl md:text-3xl lg:text-4xl text-cream-base tracking-tight leading-[0.95]"
            data-testid="premium-ready-banner-headline"
          >
            <span className="inline-block mr-2" aria-hidden>✅</span>
            Your Premium Scout Report is Ready
          </h2>
          <p
            className="mt-3 text-cream-base/70 text-sm md:text-base leading-relaxed"
            data-testid="premium-ready-banner-subtext"
          >
            Your analysis has been completed successfully.{playerName ? ` Full dossier for ${playerName} below.` : ""}
          </p>
          <div className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-2 text-[10px] uppercase tracking-[0.28em] font-bold text-cream-base/50">
            <span>Technical</span>
            <span aria-hidden>·</span>
            <span>Tactical</span>
            <span aria-hidden>·</span>
            <span>Physical</span>
            <span aria-hidden>·</span>
            <span>Mentality</span>
          </div>
        </div>

        <motion.button
          whileHover={{ scale: 1.02 }}
          whileTap={{ scale: 0.98 }}
          onClick={onOpenReport}
          data-testid="premium-ready-banner-open-btn"
          className="shrink-0 inline-flex items-center justify-center gap-2.5 bg-volt hover:bg-forest-pop text-ink hover:text-white font-barlow font-black uppercase tracking-[0.22em] text-xs md:text-sm px-6 md:px-8 py-3.5 md:py-4 transition-colors group"
          style={{ boxShadow: "0 12px 32px -8px rgba(204,255,0,0.5)" }}
        >
          <Sparkles className="w-3.5 h-3.5" />
          Open Full Premium Report
          <Sparkles className="w-3.5 h-3.5 transition-transform group-hover:rotate-12" />
        </motion.button>
      </div>

      <p className="relative mt-5 pt-4 border-t border-cream-base/10 text-[10px] text-cream-base/45 uppercase tracking-[0.22em] font-bold flex items-center gap-1.5">
        <ShieldCheck className="w-3 h-3" /> Elite-tier access · Included in your plan
      </p>
    </motion.section>
  );
}
