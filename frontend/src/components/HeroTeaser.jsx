import React, { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Lock, X, Star, ShieldCheck } from "lucide-react";
import ReportPaywallTiers from "@/components/ReportPaywallTiers";

/**
 * HeroTeaser — the "must-buy" reveal shown to free users right after the AI finishes.
 *
 * Cream/forest theme (premium):
 *   - Cream base background with a soft forest radial vignette
 *   - The locked-player marker frame sits inside a forest-green halo
 *   - Real preview data is revealed in stages: name → score → top traits → snippet → locks
 *   - 4 locked sections shown with blurred placeholders behind 🔒 icons
 *   - Closes with the unified 3-tier pricing (Single / Premium / VIP) via
 *     <ReportPaywallTiers /> — live prices from /settings/price
 *   - Subtle "Take me to dashboard" link beneath for users not ready to buy
 *
 * Props
 *   open        — boolean
 *   report      — the API response from POST /api/reports/upload (has player_details,
 *                 preview, marker_url, fingerprint, etc.)
 *   assetBase   — REACT_APP_BACKEND_URL prefix for image URLs
 *   onUnlock    — () => void  — Single-report CTA (navigates to the report with ?unlock=1)
 *   onDismiss   — () => void  — navigates to dashboard
 */
export default function HeroTeaser({ open, report, assetBase, onUnlock, onDismiss }) {
  const [stage, setStage] = useState(0); // 0..5 reveal stages

  /* eslint-disable */
  useEffect(() => {
    if (!open) { setStage(0); return; }
    const t1 = setTimeout(() => setStage(1), 500);  // headline
    const t2 = setTimeout(() => setStage(2), 1200); // name + role
    const t3 = setTimeout(() => setStage(3), 1900); // overall score
    const t4 = setTimeout(() => setStage(4), 2600); // brief summary + strengths
    const t5 = setTimeout(() => setStage(5), 3400); // locked sections + CTA
    return () => { [t1,t2,t3,t4,t5].forEach(clearTimeout); };
  }, [open]);
  /* eslint-enable */

  if (!open || !report) return null;

  const player = report.player_details || {};
  const preview = report.preview || {};
  const fingerprint = report.fingerprint || {};
  // Player hero image: the high-quality square DISPLAY crop centred on the
  // exact box the user drew (guaranteed to show THEIR player) → fallback to
  // the tight subject crop → legacy full marker frame. Override URLs from R2
  // are absolute; legacy /api/uploads paths need the backend prefix.
  const absUrl = (u) => (u && u.startsWith("http") ? u : `${assetBase}${u}`);
  const playerImg = report.display_crop_url || report.subject_crop_url || report.marker_url;
  const markerUrl = playerImg ? absUrl(playerImg) : null;

  // Pull real preview content with graceful fallbacks
  const overall = preview.overall_score
    || preview.scores?.overall_development
    || preview.scores?.overall
    || 76;
  const strengths = Array.isArray(preview.top_strengths) && preview.top_strengths.length
    ? preview.top_strengths.slice(0, 3)
    : ["Confident on the ball under pressure"];
  const briefSummary = preview.brief_summary || preview.summary
    || preview.sample_section?.content
    || "";
  const playerType = preview.player_type || "";
  const improvement = preview.area_for_improvement || "";
  const confidence = String(preview.confidence || "medium").toLowerCase();

  return (
    <AnimatePresence>
      <motion.div
        key="hero-teaser"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        transition={{ duration: 0.4 }}
        className="fixed inset-0 z-[150] bg-cream-base overflow-y-auto"
        data-testid="hero-teaser"
      >
        {/* Soft forest radial vignette to set the premium mood */}
        <div className="absolute inset-0 pointer-events-none" aria-hidden>
          <div
            className="absolute inset-0"
            style={{
              background: "radial-gradient(circle at 50% 0%, rgba(31,79,47,0.15), transparent 55%), radial-gradient(circle at 50% 100%, rgba(31,79,47,0.08), transparent 60%)",
            }}
          />
          {/* Sparse forest specks */}
          {[...Array(14)].map((_, i) => (
            <motion.div
              key={i}
              className="absolute w-1 h-1 bg-forest/25 rounded-full"
              style={{ left: `${(i * 53) % 100}%`, top: `${(i * 37) % 100}%` }}
              animate={{ opacity: [0.2, 0.6, 0.2] }}
              transition={{ duration: 3 + (i % 4), repeat: Infinity, delay: i * 0.13 }}
            />
          ))}
        </div>

        <div className="relative max-w-5xl mx-auto px-6 pt-10 pb-8 min-h-screen flex flex-col">
          {/* Close-X corner so user is never trapped */}
          <button
            type="button"
            onClick={onDismiss}
            data-testid="hero-teaser-close"
            className="absolute top-3 right-3 w-9 h-9 flex items-center justify-center text-ink/50 hover:text-ink rounded-full"
            aria-label="Close"
          >
            <X className="w-4 h-4" />
          </button>

          <div className="max-w-md mx-auto w-full">
          {/* Marker frame with forest halo + Pro Scout badge */}
          {markerUrl && (
            <div className="relative mx-auto mb-5" style={{ width: 200 }}>
              <motion.div
                className="absolute -inset-3 rounded-full"
                style={{ boxShadow: "0 0 60px rgba(31,79,47,0.35), 0 0 0 6px rgba(31,79,47,0.08)" }}
                animate={{ opacity: [0.5, 0.95, 0.5] }}
                transition={{ duration: 2.2, repeat: Infinity }}
              />
              <div className="relative border-2 border-forest overflow-hidden rounded-sm bg-white shadow-xl">
                <img
                  src={markerUrl}
                  alt="Your player"
                  className="w-full aspect-square object-cover"
                  data-testid="hero-teaser-marker"
                />
                {/* corner ribbon — PRO SCOUT VERIFIED */}
                <div className="absolute bottom-0 left-0 right-0 bg-forest text-white text-[9px] uppercase tracking-[0.2em] font-black py-1 text-center flex items-center justify-center gap-1">
                  <ShieldCheck className="w-3 h-3" />
                  Pro Scout Locked
                </div>
              </div>
            </div>
          )}

          {/* "Analysis complete" tag */}
          <AnimatePresence>
            {stage >= 1 && (
              <motion.div
                key="ac"
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.45 }}
                className="flex items-center justify-center gap-2 mb-3"
              >
                <motion.span
                  className="w-1.5 h-1.5 bg-forest rounded-full"
                  animate={{ opacity: [1, 0.3, 1] }}
                  transition={{ duration: 1, repeat: Infinity }}
                />
                <span className="text-forest text-[10px] uppercase tracking-[0.4em] font-black">
                  Pro Scout Analysis Complete
                </span>
                <motion.span
                  className="w-1.5 h-1.5 bg-forest rounded-full"
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
                <h1
                  className="font-barlow font-black uppercase text-ink tracking-tighter text-4xl md:text-5xl leading-none"
                  data-testid="hero-teaser-player-name"
                >
                  {player.player_name || "Your Player"}
                </h1>
                <p className="mt-2 text-ink/65 text-[11px] uppercase tracking-[0.25em] font-bold">
                  {[
                    player.age && `Age ${player.age}`,
                    player.position,
                    fingerprint.jersey_name && `${fingerprint.jersey_name} jersey`,
                  ].filter(Boolean).join(" · ")}
                </p>
                {playerType && (
                  <p className="mt-3 text-forest text-sm font-bold italic px-2">
                    &ldquo;{playerType}&rdquo;
                  </p>
                )}
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
                <p className="text-ink/55 text-[9px] uppercase tracking-[0.4em] font-bold mb-1">
                  Overall potential
                </p>
                <div className="font-barlow font-black text-forest text-7xl md:text-8xl tracking-tighter tabular-nums leading-none">
                  {overall}
                  <span className="text-ink/35 text-3xl">/100</span>
                </div>
                <p className="mt-2 text-ink/55 text-[10px] uppercase tracking-[0.2em] font-bold">
                  Confidence: <span className="text-forest font-black">{confidence}</span>
                </p>
              </motion.div>
            )}
          </AnimatePresence>

          {/* Brief summary + Top strengths */}
          <AnimatePresence>
            {stage >= 4 && (
              <motion.div
                key="det"
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.45 }}
                className="mb-6 space-y-3"
              >
                {briefSummary && (() => {
                  const teaser = String(briefSummary).slice(0, 90).replace(/\s+\S*$/, "");
                  const hasMore = String(briefSummary).length > teaser.length;
                  return (
                    <div className="bg-white border border-gray-border p-4 rounded-sm shadow-sm">
                      <p className="text-ink/45 text-[9px] uppercase tracking-[0.3em] font-bold mb-2">
                        What the scout saw — preview
                      </p>
                      <p className="text-ink text-sm leading-relaxed">
                        {teaser}
                        {hasMore && (
                          <>
                            <span aria-hidden className="text-ink/85">…</span>
                            <span
                              aria-hidden
                              className="ml-1 text-ink/55 select-none"
                              style={{ filter: "blur(5px)" }}
                            >
                              the rest of the scout&apos;s observation is unlocked in the full report
                            </span>
                          </>
                        )}
                      </p>
                      {hasMore && (
                        <div className="mt-3 inline-flex items-center gap-1.5 text-forest text-[10px] uppercase tracking-[0.25em] font-black">
                          <Lock className="w-3 h-3" />
                          Unlock to read the full breakdown
                        </div>
                      )}
                    </div>
                  );
                })()}

                <div className="bg-cream-soft/60 border border-forest/15 p-4 rounded-sm">
                  <p className="text-forest text-[9px] uppercase tracking-[0.3em] font-black mb-3 flex items-center gap-1.5">
                    <Star className="w-3 h-3" fill="currentColor" />
                    1 of {Math.max(strengths.length, 3)} top strengths revealed
                  </p>
                  <ul className="space-y-2">
                    {/* Only the FIRST strength is fully visible. */}
                    {strengths.slice(0, 1).map((s, i) => (
                      <motion.li
                        key={i}
                        initial={{ opacity: 0, x: -6 }}
                        animate={{ opacity: 1, x: 0 }}
                        transition={{ delay: 0.1 * i, duration: 0.35 }}
                        className="flex items-start gap-2 text-ink text-[13px] leading-snug"
                      >
                        <span className="inline-flex items-center justify-center w-5 h-5 rounded-full bg-forest text-cream-card text-[10px] font-black flex-shrink-0">{i + 1}</span>
                        <span className="font-semibold">{s}</span>
                      </motion.li>
                    ))}
                    {/* Strengths 2 and 3: blurred. If we have fewer real strengths,
                        we still render two blurred placeholders so the lock feels real. */}
                    {[1, 2].map((idx) => {
                      const s = strengths[idx] || "Strong second-touch consistency in tight spaces";
                      return (
                        <li
                          key={`lock-${idx}`}
                          className="flex items-start gap-2 text-ink/65 text-[13px] leading-snug select-none"
                          style={{ filter: "blur(4px)" }}
                          aria-hidden
                        >
                          <span className="inline-flex items-center justify-center w-5 h-5 rounded-full bg-forest/40 text-cream-card text-[10px] font-black flex-shrink-0">{idx + 1}</span>
                          <span className="font-semibold">{s}</span>
                        </li>
                      );
                    })}
                  </ul>
                  <p className="mt-3 inline-flex items-center gap-1.5 text-forest text-[10px] uppercase tracking-[0.25em] font-black">
                    <Lock className="w-3 h-3" />
                    Unlock to reveal 2 more
                  </p>
                </div>

                {improvement && (
                  <div className="relative bg-white border border-gray-border p-3 rounded-sm overflow-hidden">
                    <p className="text-ink/45 text-[9px] uppercase tracking-[0.3em] font-bold mb-1 flex items-center gap-1.5">
                      <Lock className="w-3 h-3 text-forest" />
                      One area to improve · locked
                    </p>
                    <p
                      className="text-ink/85 text-[12px] leading-snug select-none"
                      style={{ filter: "blur(5px)" }}
                      aria-hidden
                    >
                      {String(improvement).slice(0, 160)}
                    </p>
                  </div>
                )}
              </motion.div>
            )}
          </AnimatePresence>

          {/* Locked sections */}
          <AnimatePresence>
            {stage >= 5 && (
              <motion.div
                key="lk"
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.45 }}
                className="space-y-1.5 mb-6"
              >
                <p className="text-ink/55 text-[9px] uppercase tracking-[0.3em] font-bold mb-2">
                  Unlocked in the full report
                </p>
                {[
                  "Detailed scout view (12 sub-scores)",
                  "12-week training plan",
                  "Agent / academy review",
                  "Archetype + 5-year trajectory",
                ].map((label, i) => (
                  <motion.div
                    key={i}
                    initial={{ opacity: 0, x: -6 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: 0.08 * i, duration: 0.3 }}
                    className="flex items-center gap-3 px-3 py-2.5 border border-gray-border bg-white rounded-sm relative overflow-hidden"
                  >
                    {/* blurred placeholder text underneath the lock */}
                    <div
                      aria-hidden
                      className="absolute inset-y-1.5 left-44 right-3 text-ink/40 text-[11px] uppercase tracking-tight font-bold select-none truncate"
                      style={{ filter: "blur(5px)" }}
                    >
                      Reveals on unlock
                    </div>
                    <Lock className="w-3.5 h-3.5 text-forest/65 flex-shrink-0 relative" />
                    <span className="text-ink/85 text-[10px] uppercase tracking-widest font-black w-40 flex-shrink-0 relative">
                      {label}
                    </span>
                  </motion.div>
                ))}
              </motion.div>
            )}
          </AnimatePresence>
          </div>

          {/* Unified 3-tier pricing (Single / Premium / VIP) — live prices */}
          {stage >= 5 && (
            <motion.div
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.5, delay: 0.2 }}
              className="w-full mb-2"
              data-testid="hero-teaser-tiers"
            >
              <div className="text-center mb-6">
                <p className="text-forest text-[10px] uppercase tracking-[0.4em] font-black mb-2">
                  Unlock the full report
                </p>
                <h2 className="font-barlow font-black uppercase text-ink tracking-tighter text-2xl md:text-3xl leading-none">
                  Choose how you want in
                </h2>
              </div>
              <ReportPaywallTiers isLoggedIn onUnlockSingle={onUnlock} />
            </motion.div>
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
              className="text-center text-ink/55 hover:text-ink/85 text-[11px] uppercase tracking-widest font-bold py-2"
            >
              Take me to dashboard instead
            </motion.button>
          )}
        </div>
      </motion.div>
    </AnimatePresence>
  );
}
