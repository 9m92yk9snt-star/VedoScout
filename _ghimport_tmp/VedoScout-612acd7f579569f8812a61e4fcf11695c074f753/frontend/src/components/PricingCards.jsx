/**
 * PricingCards — 2-card pricing layout used on Landing + post-preview.
 *
 * Both cards always include the human scout/agent review.
 * Prices come from the public /settings/price endpoint and are admin-editable.
 *
 * Variant: "landing" (light/forest theme) or "dark" (deepnavy theme inside report page).
 */
import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { motion } from "framer-motion";
import {
  ShieldCheck, Star, ArrowRight, Crown, Check, BarChart3, Sparkles, Award, FileCheck2, Users, Lock,
} from "lucide-react";
import api from "@/lib/api";
import EmbeddedCheckoutModal from "@/components/EmbeddedCheckoutModal";

export default function PricingCards({
  variant = "landing",
  ctaSingle = "Get My Report",
  ctaPass = "Start The 12-Month Plan",
  singleHref = "/upload",
  isLoggedIn = false,
  onAfterPassActivate = null,
}) {
  const [price, setPrice] = useState(null);
  const [passPrice, setPassPrice] = useState(null);
  const [passModalOpen, setPassModalOpen] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    api.get("/settings/price")
      .then(({ data }) => {
        setPrice(data.price);
        setPassPrice(data.pass_price);
      })
      .catch(() => {});
  }, []);

  const startPassCheckout = async () => ({
    ...(await api.post("/progress/pass/checkout", { origin_url: window.location.origin })).data,
  });

  const onPassSuccess = async ({ session_id }) => {
    try {
      await api.post(`/progress/pass/activate/${session_id}`);
      toast.success("12-month plan activated! 3 reports + tracking are unlocked.");
      if (onAfterPassActivate) onAfterPassActivate();
      else navigate("/dashboard");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Activation failed");
    } finally {
      setPassModalOpen(false);
    }
  };

  const handleSingleClick = () => {
    if (!isLoggedIn) {
      // Anon users need an account first — send them straight to signup,
      // then bounce to /upload after sign-up so the buy chain is seamless.
      navigate(`/signup?next=${encodeURIComponent("/upload")}`);
      return;
    }
    navigate(singleHref);
  };

  const handlePassClick = () => {
    if (!isLoggedIn) {
      navigate("/login?next=/dashboard&open_pass=1");
      return;
    }
    setPassModalOpen(true);
  };

  const savings = (price && passPrice) ? Math.max(0, Math.round(price * 3 - passPrice)) : 0;
  const isDark = variant === "dark";

  return (
    <div
      data-testid="pricing-cards"
      className={`relative ${isDark ? "" : ""}`}
    >
      <div className="grid md:grid-cols-5 gap-5 md:gap-6 items-stretch">
        {/* ─────────────── Card 1: Single Report ─────────────── */}
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          whileInView={{ opacity: 1, y: 0 }}
          whileHover={{ y: -4 }}
          viewport={{ once: true, margin: "-80px" }}
          transition={{ duration: 0.4 }}
          data-testid="pricing-card-single"
          className={`md:col-span-2 relative p-6 md:p-8 flex flex-col h-full border transition-all duration-300 hover:scale-[1.008] ${
            isDark
              ? "bg-surface border-gray-border hover:border-forest"
              : "bg-cream-card border-gray-border hover:border-forest"
          }`}
          style={{
            boxShadow:
              "0 22px 48px -20px rgba(10, 15, 13, 0.18), 0 12px 24px -10px rgba(31, 79, 47, 0.14), 0 4px 8px -2px rgba(10, 15, 13, 0.08), inset 0 1px 0 rgba(255, 255, 255, 0.5)",
          }}
        >
          <div className="flex items-center gap-3 mb-3">
            <motion.div
              animate={{ y: [0, -2, 0] }}
              transition={{ duration: 3, repeat: Infinity, ease: "easeInOut" }}
              className={`relative w-10 h-10 flex items-center justify-center shrink-0 ${
                isDark ? "bg-volt/15 border border-volt/45" : "bg-forest/8 border border-forest/30"
              }`}
            >
              <FileCheck2 className={`w-4 h-4 ${isDark ? "text-volt" : "text-forest"}`} strokeWidth={1.7} />
              <motion.span
                aria-hidden
                className={`absolute inset-0 border pointer-events-none ${
                  isDark ? "border-volt" : "border-forest"
                }`}
                animate={{ scale: [1, 1.3], opacity: [0.45, 0] }}
                transition={{ duration: 2.4, repeat: Infinity, ease: "easeOut" }}
              />
            </motion.div>
            <span className={`text-[10px] uppercase tracking-[0.25em] font-bold ${isDark ? "text-volt" : "text-forest"}`}>
              Single report
            </span>
          </div>
          <h3 className="font-barlow font-black uppercase text-3xl md:text-4xl tracking-tighter leading-[0.95] text-ink">
            One Full Report
          </h3>
          <p className="mt-2 text-sm text-ink/70 min-h-[40px]">
            A complete picture of where your player stands today.
          </p>

          <div className="mt-5 flex items-baseline gap-2">
            <span className={`font-barlow font-black text-5xl md:text-6xl leading-none ${isDark ? "text-volt" : "text-forest"}`}>
              ${price ?? "—"}
            </span>
            <span className="text-ink/55 uppercase tracking-widest font-bold text-sm">USD</span>
          </div>
          <p className="text-[10px] text-ink/50 uppercase tracking-widest font-bold mt-1">One-time · No subscription</p>

          <ul className="mt-6 space-y-2.5 text-sm flex-1">
            <Feature>Upload 1 football video</Feature>
            <Feature>Advanced benchmarked intelligence analysis</Feature>
            <Feature>Pro-player archetype match</Feature>
            <Feature>Age-calibrated benchmark comparison</Feature>
            <Feature highlight>Personal scout / agent written review</Feature>
            <Feature>Professional PDF report</Feature>
          </ul>

          <button
            type="button"
            onClick={handleSingleClick}
            data-testid="pricing-single-cta"
            className={`mt-6 w-full font-barlow font-black uppercase tracking-widest text-sm py-3.5 flex items-center justify-center gap-2 transition-all group/btn ${
              isDark
                ? "bg-volt hover:bg-forest-pop text-white"
                : "bg-forest hover:bg-forest-pop text-white"
            }`}
          >
            {ctaSingle}
            <ArrowRight className="w-4 h-4 transition-transform group-hover/btn:translate-x-1" />
          </button>
          <p className="mt-3 text-[10px] text-ink/50 flex items-center justify-center gap-1.5">
            <ShieldCheck className="w-3 h-3" /> Free preview · No card to start
          </p>
        </motion.div>

        {/* ─────────────── Card 2: 12-Month Plan ─────────────── */}
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          whileInView={{ opacity: 1, y: 0 }}
          whileHover={{ y: -4 }}
          viewport={{ once: true, margin: "-80px" }}
          transition={{ duration: 0.4, delay: 0.1 }}
          data-testid="pricing-card-pass"
          className={`md:col-span-3 relative p-6 md:p-8 flex flex-col h-full border-2 transition-all duration-300 hover:scale-[1.012] ${
            isDark
              ? "bg-forest text-white border-volt"
              : "bg-forest text-white border-forest"
          }`}
          style={{
            boxShadow:
              "0 36px 80px -28px rgba(10, 15, 13, 0.55), 0 24px 48px -16px rgba(31, 79, 47, 0.45), 0 10px 22px -6px rgba(31, 79, 47, 0.28), 0 2px 4px rgba(10, 15, 13, 0.18), inset 0 1px 0 rgba(204, 255, 0, 0.18)",
          }}
        >
          {/* MOBILE-only banner — full-width, sticky-top "Best Value" + social proof.
              First thing a thumb-scroller sees on the $399 card. */}
          {savings > 0 && (
            <div
              data-testid="pricing-pass-mobile-banner"
              className="md:hidden -mt-6 -mx-6 mb-5 bg-cream-card text-forest border-b border-forest/20"
            >
              <div className="px-4 py-2.5 flex items-center justify-between gap-2 text-[10px] uppercase tracking-[0.2em] font-black">
                <span className="flex items-center gap-1.5">
                  <Crown className="w-3.5 h-3.5" />
                  Best value · Save ${savings}
                </span>
                <span className="flex items-center gap-1.5 text-forest/70">
                  <Users className="w-3 h-3" />
                  Most parents pick this
                </span>
              </div>
            </div>
          )}

          {/* Best Value ribbon — DESKTOP only (hidden on mobile, mobile uses banner above) */}
          {savings > 0 && (
            <div className="hidden md:flex absolute -top-3 right-6 bg-cream-card text-forest text-[10px] uppercase tracking-[0.22em] font-black px-3 py-1.5 items-center gap-1.5 border border-forest/30 shadow-md">
              <Crown className="w-3 h-3" />
              Best value · Save ${savings}
            </div>
          )}
          {/* Social proof tag — DESKTOP only */}
          <div className="hidden md:flex absolute -top-3 left-6 bg-forest-pop text-white text-[10px] uppercase tracking-[0.22em] font-black px-3 py-1.5 items-center gap-1.5 shadow-md">
            <Users className="w-3 h-3" />
            Most parents pick this
          </div>

          <div className="flex items-center gap-3 mb-3 md:mt-3">
            <motion.div
              animate={{ y: [0, -2, 0] }}
              transition={{ duration: 3, delay: 0.4, repeat: Infinity, ease: "easeInOut" }}
              className="relative w-10 h-10 flex items-center justify-center shrink-0 bg-volt/15 border border-volt/55"
            >
              <BarChart3 className="w-4 h-4 text-volt" strokeWidth={1.7} />
              <motion.span
                aria-hidden
                className="absolute inset-0 border border-volt pointer-events-none"
                animate={{ scale: [1, 1.3], opacity: [0.5, 0] }}
                transition={{ duration: 2.4, delay: 0.4, repeat: Infinity, ease: "easeOut" }}
              />
            </motion.div>
            <span className="text-[10px] uppercase tracking-[0.25em] font-bold text-volt">12 months · 3 reports</span>
          </div>

          {/* mini 12-month timeline visualisation — instantly conveys "3 reports across 12 months" */}
          <div className="mt-2 mb-3 max-w-[280px]" aria-hidden>
            <svg viewBox="0 0 100 14" className="w-full h-3.5">
              {/* baseline */}
              <line x1="6" y1="7" x2="94" y2="7" stroke="rgba(255,255,255,0.25)" strokeWidth="0.5" />
              <motion.line
                x1="6" y1="7" x2="94" y2="7" stroke="#CCFF00" strokeWidth="0.6"
                initial={{ pathLength: 0 }}
                whileInView={{ pathLength: 1 }}
                viewport={{ once: true }}
                transition={{ duration: 1.1, delay: 0.4 }}
              />
              {/* tick marks for every 3 months */}
              {[6, 28, 50, 72, 94].map((x, i) => (
                <line key={i} x1={x} y1="5.5" x2={x} y2="8.5" stroke="rgba(255,255,255,0.35)" strokeWidth="0.4" />
              ))}
              {/* 3 report drops at M0, M6, M12 */}
              {[6, 50, 94].map((x, i) => (
                <motion.g
                  key={i}
                  initial={{ scale: 0, opacity: 0 }}
                  whileInView={{ scale: 1, opacity: 1 }}
                  viewport={{ once: true }}
                  transition={{ delay: 0.6 + i * 0.18, type: "spring", stiffness: 220, damping: 14 }}
                  style={{ transformOrigin: `${x}px 7px`, transformBox: "fill-box" }}
                >
                  <circle cx={x} cy="7" r="3" fill="#CCFF00" />
                  <circle cx={x} cy="7" r="1.2" fill="#0E3D2E" />
                </motion.g>
              ))}
              {/* month labels */}
              <text x="6"  y="13.5" fontSize="2.4" fill="white" opacity="0.55" textAnchor="middle" fontWeight="700">M0</text>
              <text x="50" y="13.5" fontSize="2.4" fill="white" opacity="0.55" textAnchor="middle" fontWeight="700">M6</text>
              <text x="94" y="13.5" fontSize="2.4" fill="white" opacity="0.55" textAnchor="middle" fontWeight="700">M12</text>
            </svg>
          </div>
          <h3 className="font-barlow font-black uppercase text-3xl md:text-5xl tracking-tighter leading-[0.95]">
            Track The Full Year
          </h3>
          <p className="mt-2 text-sm text-white/70 max-w-md min-h-[40px]">
            Watch your player grow across a full season — three full reports, real progress tracking, real scout reviews.
          </p>

          <div className="mt-5 flex items-baseline gap-3">
            <span className="font-barlow font-black text-5xl md:text-6xl text-white leading-none">
              ${passPrice ?? "—"}
            </span>
            <span className="text-white/55 uppercase tracking-widest font-bold text-sm">USD</span>
            {price && passPrice && (
              <span className="text-white/45 text-sm line-through ml-1">
                ${Math.round(price * 3)}
              </span>
            )}
          </div>
          <p className="text-[10px] text-white/50 uppercase tracking-widest font-bold mt-1">
            One-time · No subscription · 3 reports / 12 months
          </p>

          <div className="mt-6 grid sm:grid-cols-2 gap-x-6 gap-y-2 sm:gap-y-2.5 text-[13px] sm:text-sm flex-1">
            <Feature dark>3 full reports across 12 months</Feature>
            <Feature dark>Advanced benchmarked intelligence × 3</Feature>
            <Feature dark highlight>Scout / agent review on every report</Feature>
            <Feature dark>Year-over-year progress tracking</Feature>
            <Feature dark>Growth chart vs pro-archetype path</Feature>
            <Feature dark>Development verdict + growth badges</Feature>
            <Feature dark>Shareable growth card image</Feature>
            <Feature dark>Between-the-lines narrative</Feature>
          </div>

          <div className="mt-6 flex flex-col sm:flex-row sm:items-center gap-3">
            <button
              type="button"
              onClick={handlePassClick}
              data-testid="pricing-pass-cta"
              className="flex-1 bg-cream-card hover:bg-white text-forest font-barlow font-black uppercase tracking-widest text-sm py-3.5 flex items-center justify-center gap-2 transition-all group/btn"
            >
              {ctaPass}
              <ArrowRight className="w-4 h-4 transition-transform group-hover/btn:translate-x-1" />
            </button>
          </div>
          <p className="mt-3 text-[10px] text-white/55 flex items-center justify-center gap-1.5">
            <Sparkles className="w-3 h-3" /> Includes everything in the single report — three times over
          </p>
        </motion.div>
      </div>

      {/* Savings hint band — sits BETWEEN cards conceptually */}
      {price && passPrice && savings > 0 && (
        <div className="mt-5 flex justify-center">
          <div className="inline-flex items-center gap-2 bg-cream-card border border-forest/25 px-4 py-2 text-xs text-ink/75">
            <Crown className="w-3.5 h-3.5 text-forest" />
            <span>
              <span className="font-bold text-ink">${price} × 3 = ${Math.round(price * 3)}</span>
              <span className="text-ink/55 mx-2">·</span>
              <span>You pay only <span className="font-bold text-forest">${passPrice}</span></span>
              <span className="text-ink/55 mx-2">·</span>
              <span className="font-bold text-forest">Save ${savings}</span>
            </span>
          </div>
        </div>
      )}

      {/* Guarantee + trust line */}
      <div className={`mt-6 grid sm:grid-cols-3 gap-3 text-xs ${isDark ? "text-ink/65" : "text-ink/65"}`}>
        <div className="flex items-center justify-center sm:justify-start gap-2 border border-gray-border bg-cream-card/60 px-4 py-3">
          <ShieldCheck className="w-4 h-4 text-forest flex-shrink-0" />
          <span><span className="font-bold text-ink">48h delivery</span> or full refund</span>
        </div>
        <div className="flex items-center justify-center gap-2 border border-gray-border bg-cream-card/60 px-4 py-3">
          <Award className="w-4 h-4 text-forest flex-shrink-0" />
          <span>Reviewed by <span className="font-bold text-ink">real scouts</span></span>
        </div>
        <div className="flex items-center justify-center sm:justify-end gap-2 border border-gray-border bg-cream-card/60 px-4 py-3">
          <Lock className="w-4 h-4 text-forest flex-shrink-0" />
          <span>Secure Stripe · <span className="font-bold text-ink">no subscription</span></span>
        </div>
      </div>

      <EmbeddedCheckoutModal
        open={passModalOpen}
        onClose={() => setPassModalOpen(false)}
        sessionInit={startPassCheckout}
        amount={passPrice ?? 399}
        currency="USD"
        product="ScoutMePlay — 12-Month Plan (3 reports)"
        onSuccess={onPassSuccess}
      />
    </div>
  );
}

function Feature({ children, dark = false, highlight = false }) {
  const Icon = highlight ? Star : Check;
  return (
    <li className="flex items-start gap-2">
      <Icon
        className={`w-3.5 h-3.5 sm:w-4 sm:h-4 mt-0.5 flex-shrink-0 ${
          highlight
            ? "text-volt"
            : dark
              ? "text-volt/80"
              : "text-forest"
        }`}
        strokeWidth={highlight ? 2.5 : 2}
        {...(highlight ? { fill: "currentColor" } : {})}
      />
      <span className={dark ? "text-white/90" : "text-ink/85"}>
        {children}
      </span>
    </li>
  );
}
