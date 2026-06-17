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
  ShieldCheck, Star, ArrowRight, Crown, Check, BarChart3, Sparkles, Award, FileCheck2,
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
      <div className="grid md:grid-cols-5 gap-5 md:gap-6">
        {/* ─────────────── Card 1: Single Report ─────────────── */}
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-80px" }}
          transition={{ duration: 0.4 }}
          data-testid="pricing-card-single"
          className={`md:col-span-2 relative p-6 md:p-8 flex flex-col border ${
            isDark
              ? "bg-surface border-gray-border"
              : "bg-cream-card border-gray-border"
          }`}
        >
          <div className="flex items-center gap-2 mb-2">
            <FileCheck2 className={`w-4 h-4 ${isDark ? "text-volt" : "text-forest"}`} />
            <span className={`text-[10px] uppercase tracking-[0.25em] font-bold ${isDark ? "text-volt" : "text-forest"}`}>
              Single report
            </span>
          </div>
          <h3 className="font-barlow font-black uppercase text-3xl md:text-4xl tracking-tighter leading-[0.95] text-ink">
            One Full Report
          </h3>
          <p className="mt-2 text-sm text-ink/70">
            A complete picture of where your player stands today.
          </p>

          <div className="mt-5 flex items-baseline gap-2">
            <span className={`font-barlow font-black text-5xl md:text-6xl leading-none ${isDark ? "text-volt" : "text-forest"}`}>
              ${price ?? "—"}
            </span>
            <span className="text-ink/55 uppercase tracking-widest font-bold text-sm">USD</span>
          </div>
          <p className="text-[10px] text-ink/50 uppercase tracking-widest font-bold mt-1">One-time · No subscription</p>

          <ul className="mt-6 space-y-2.5 text-sm">
            <Feature>Upload 1 football video</Feature>
            <Feature>Advanced benchmarked intelligence analysis</Feature>
            <Feature>Pro-player archetype match</Feature>
            <Feature>Age-calibrated benchmark comparison</Feature>
            <Feature highlight>Personal scout / agent written review</Feature>
            <Feature>Professional PDF report</Feature>
          </ul>

          <button
            type="button"
            onClick={() => navigate(singleHref)}
            data-testid="pricing-single-cta"
            className={`mt-6 w-full font-barlow font-black uppercase tracking-widest text-sm py-3.5 flex items-center justify-center gap-2 transition-colors ${
              isDark
                ? "bg-volt hover:bg-forest-pop text-white"
                : "bg-forest hover:bg-forest-pop text-white"
            }`}
          >
            {ctaSingle}
            <ArrowRight className="w-4 h-4" />
          </button>
          <p className="mt-3 text-[10px] text-ink/50 flex items-center justify-center gap-1.5">
            <ShieldCheck className="w-3 h-3" /> Free preview · No card to start
          </p>
        </motion.div>

        {/* ─────────────── Card 2: 12-Month Plan ─────────────── */}
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-80px" }}
          transition={{ duration: 0.4, delay: 0.1 }}
          data-testid="pricing-card-pass"
          className={`md:col-span-3 relative p-6 md:p-8 flex flex-col border-2 ${
            isDark
              ? "bg-forest text-white border-volt"
              : "bg-forest text-white border-forest"
          }`}
          style={{ boxShadow: "0 20px 80px rgba(31, 79, 47, 0.18)" }}
        >
          {/* Best Value ribbon */}
          {savings > 0 && (
            <div className="absolute -top-3 right-6 bg-cream-card text-forest text-[10px] uppercase tracking-[0.22em] font-black px-3 py-1.5 flex items-center gap-1.5 border border-forest/30 shadow-md">
              <Crown className="w-3 h-3" />
              Best value · Save ${savings}
            </div>
          )}

          <div className="flex items-center gap-2 mb-2">
            <BarChart3 className="w-4 h-4 text-volt" />
            <span className="text-[10px] uppercase tracking-[0.25em] font-bold text-volt">12 months · 3 reports</span>
          </div>
          <h3 className="font-barlow font-black uppercase text-3xl md:text-5xl tracking-tighter leading-[0.95]">
            Track The Full Year
          </h3>
          <p className="mt-2 text-sm text-white/70 max-w-md">
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

          <div className="mt-6 grid sm:grid-cols-2 gap-x-6 gap-y-2.5 text-sm">
            <Feature dark>3 full reports across 12 months</Feature>
            <Feature dark>Advanced benchmarked intelligence × 3</Feature>
            <Feature dark highlight>Scout / agent review on every report</Feature>
            <Feature dark>Year-over-year progress tracking</Feature>
            <Feature dark>Growth chart vs pro-archetype path</Feature>
            <Feature dark>Development verdict + growth badges</Feature>
            <Feature dark>Shareable growth card image</Feature>
            <Feature dark>AI between-the-lines narrative</Feature>
          </div>

          <div className="mt-6 flex flex-col sm:flex-row sm:items-center gap-3">
            <button
              type="button"
              onClick={handlePassClick}
              data-testid="pricing-pass-cta"
              className="flex-1 bg-cream-card hover:bg-white text-forest font-barlow font-black uppercase tracking-widest text-sm py-3.5 flex items-center justify-center gap-2 transition-colors"
            >
              {ctaPass}
              <ArrowRight className="w-4 h-4" />
            </button>
          </div>
          <p className="mt-3 text-[10px] text-white/55 flex items-center justify-center gap-1.5">
            <Sparkles className="w-3 h-3" /> Includes everything in the single report — three times over
          </p>
        </motion.div>
      </div>

      {/* Footer trust line */}
      <p className={`mt-6 text-center text-xs ${isDark ? "text-ink/55" : "text-ink/60"} flex items-center justify-center gap-2 flex-wrap`}>
        <ShieldCheck className="w-3.5 h-3.5 text-forest" />
        Both plans include a personal review from a real scout / agent.
        Both include a free preview before you pay.
        Secure Stripe checkout.
      </p>

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
        className={`w-4 h-4 mt-0.5 flex-shrink-0 ${
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
