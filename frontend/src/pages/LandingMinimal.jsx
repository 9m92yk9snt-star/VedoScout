/**
 * LandingMinimal — Short, conversion-focused landing variant.
 *
 * Layout (matching user-provided screenshots, top → bottom):
 *   1. Top bar (existing <Navigation />)
 *   2. Hero — "Ready to discover your true level?" + Upload CTA + Sign-in nudge
 *   3. Pricing — <PricingCards /> (Single $159 + 12-month $399)
 *   4. FAQ — "Honest answers. No fluff."
 *   5. Footer — Lightweight site footer (mobile bottom-tabs are mounted globally)
 *
 * Admin toggles between Landing.jsx (full) and LandingMinimal.jsx (minimal)
 * via /admin → Settings → "Active landing variant".
 */
import React, { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { ArrowRight, ShieldCheck, Send } from "lucide-react";

import Navigation from "@/components/Navigation";
import PricingTiers from "@/components/PricingTiers";
import SEO, { organizationJsonLd } from "@/components/SEO";
import api from "@/lib/api";
import { useAuth } from "@/lib/auth-context";

/* ─────────────────────────────────────────────────────────────────
 *  FAQ items — kept in sync with the long-form Landing FAQ. The
 *  pricing answer is filled dynamically from /settings/price.
 * ───────────────────────────────────────────────────────────────── */
const FAQ_ITEMS = [
  {
    q: "How long does it take to get my report?",
    a: "Every report is delivered within 48 hours of payment. If we miss that window for any reason, your purchase is refunded in full — automatically, no support tickets needed.",
  },
  {
    q: "Is my child too young for this?",
    a: "ScoutMePlay is built for ambitious players aged U7 to U21. The report adjusts to the player's age — a 9-year-old is benchmarked against age-appropriate development standards, not against a senior pro. You get an honest read of where the player is, and where they could realistically go next.",
  },
  {
    q: "What if my video isn't great quality?",
    a: "A phone camera at training or a game is perfectly fine. We need to see your player on the pitch with the ball. Wider shots (showing more of the pitch) are better than tight close-ups, and a clear view of the player's movement helps the scout review. If our scout can't fairly assess the video, we contact you and either offer a re-upload or a refund.",
  },
  {
    q: "How is this different from my child's coach feedback?",
    a: "A coach knows your player from the inside — that's irreplaceable. A scout looks from the outside, comparing your player against thousands of others in a structured 4-pillar framework (Technical, Tactical, Physical, Mentality). Coaches build your player day by day. ScoutMePlay tells you where they stand right now and what to focus on next.",
  },
  {
    q: "Does this guarantee a trial or contract?",
    a: "No, and we'll never claim that. ScoutMePlay is built to help players grow, not to broker contracts. Anyone promising guaranteed trials is selling you something we won't sell. Our job is to give you honest, professional feedback so you can train smarter — the rest is up to the player.",
  },
  {
    q: "Will my video be kept private?",
    a: "Yes. Your video is used only to produce your report and is never published, sold, or shared outside the scout reviewing it. You retain full ownership of your video and your report. You can request deletion of your account and data at any time from your dashboard.",
  },
  {
    q: "What's the difference between the single report and the monthly plans?",
    a: "__PRICE_FAQ__",
  },
  {
    q: "Can I get reports for more than one player?",
    a: "Yes — but each player needs their own report (or plan), so the analysis stays fair and personal. If you have multiple kids in football, each upload is reviewed independently against age-appropriate benchmarks.",
  },
];

export default function LandingMinimal() {
  const { user } = useAuth();
  const navigate = useNavigate();

  const handlePrimaryCta = () => {
    if (user) navigate("/upload");
    else navigate("/signup?next=/upload");
  };

  return (
    <div data-testid="landing-minimal" className="min-h-screen bg-cream-base text-ink overflow-x-clip">
      <SEO
        title="ScoutMePlay — Discover your true football level"
        description="Upload your football video and get an honest professional scout review in 48 hours. Built for ambitious U7–U21 players. No subscription, no fluff."
        canonical="/"
        jsonLd={organizationJsonLd()}
      />

      {/* ─────────── 1. TOP BAR ─────────── */}
      <Navigation />

      {/* ─────────── 2. HERO (USER UPLOAD + SIGN) ─────────── */}
      <HeroSection onPrimaryCta={handlePrimaryCta} isLoggedIn={!!user} />

      {/* ─────────── 3. PRICING (Free · Premium · VIP Premium) ─────────── */}
      <PricingTiers />

      {/* ─────────── 4. FAQ ─────────── */}
      <FAQSection />

      {/* ─────────── 5. FOOTER ─────────── */}
      <SiteFooter />
    </div>
  );
}

/* ============================================================ */
/*  HERO                                                         */
/* ============================================================ */
function HeroSection({ onPrimaryCta, isLoggedIn }) {
  return (
    <section
      data-testid="hero-minimal"
      className="relative px-6 md:px-10 pt-16 md:pt-24 pb-20 md:pb-28 border-b border-gray-border overflow-hidden"
    >
      {/* Subtle background pitch lines */}
      <div
        aria-hidden
        className="absolute inset-0 opacity-[0.05] pointer-events-none"
        style={{
          backgroundImage:
            "radial-gradient(circle at 1px 1px, #1F4F2F 1px, transparent 0)",
          backgroundSize: "36px 36px",
        }}
      />
      {/* Faint football silhouette in the background */}
      <div
        aria-hidden
        className="absolute inset-0 flex items-center justify-center pointer-events-none opacity-[0.04]"
      >
        <svg viewBox="0 0 200 200" className="w-[60%] max-w-[480px]" fill="none">
          <circle cx="100" cy="100" r="78" stroke="#0A1A12" strokeWidth="3" />
          <path
            d="M100 22 L120 60 L160 70 L130 100 L140 142 L100 122 L60 142 L70 100 L40 70 L80 60 Z"
            fill="#0A1A12"
            opacity="0.5"
          />
        </svg>
      </div>

      <div className="relative max-w-3xl mx-auto text-center">
        {/* Eyebrow */}
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4 }}
          className="inline-flex items-center gap-2.5 mb-6"
        >
          <span aria-hidden className="relative flex items-center justify-center w-2 h-2 shrink-0">
            <span className="absolute inset-0 rounded-full bg-volt animate-ping opacity-75" />
            <span className="relative rounded-full w-1.5 h-1.5 bg-volt" />
          </span>
          <span className="text-forest text-[10px] uppercase tracking-[0.28em] font-bold">
            Pro Scout Intelligence · 48h delivery
          </span>
          <span aria-hidden className="h-px w-8 bg-forest/35" />
        </motion.div>

        {/* Headline */}
        <motion.h1
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.05 }}
          data-testid="hero-headline"
          className="font-barlow font-black uppercase tracking-tighter text-5xl sm:text-6xl md:text-7xl leading-[0.92] text-ink"
        >
          Ready to discover<br />
          <span className="text-forest">your true level?</span>
        </motion.h1>

        {/* Subheadline */}
        <motion.p
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.15 }}
          className="mt-7 md:mt-9 text-base md:text-lg text-ink/70 leading-relaxed max-w-2xl mx-auto"
        >
          Upload your video and get an instant free scout preview. Built for ambitious
          U7–U21 players chasing the next level. No card needed to start.
        </motion.p>

        {/* Primary CTA */}
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.25 }}
          className="mt-9 md:mt-11"
        >
          <button
            type="button"
            onClick={onPrimaryCta}
            data-testid="hero-upload-cta"
            className="group inline-flex items-center justify-center gap-3 bg-forest hover:bg-forest-pop text-white font-barlow font-black uppercase tracking-[0.18em] text-base md:text-lg px-10 md:px-14 py-5 md:py-6 transition-all w-full sm:w-auto"
            style={{
              boxShadow:
                "0 24px 48px -16px rgba(31, 79, 47, 0.45), 0 10px 20px -8px rgba(31, 79, 47, 0.35), inset 0 1px 0 rgba(255,255,255,0.08)",
            }}
          >
            Upload your video
            <ArrowRight className="w-5 h-5 transition-transform group-hover:translate-x-1" />
          </button>

          {/* Sign-in nudge (for non-logged-in users) */}
          {!isLoggedIn && (
            <p className="mt-5 text-xs uppercase tracking-[0.2em] text-ink/55 font-bold">
              Already have an account?{" "}
              <Link
                to="/login"
                data-testid="hero-signin-link"
                className="text-forest hover:text-forest-pop underline underline-offset-4 decoration-forest/40"
              >
                Sign in
              </Link>
            </p>
          )}

          {/* Trust line */}
          <p className="mt-4 text-[11px] text-ink/55 flex items-center justify-center gap-1.5 uppercase tracking-[0.18em] font-bold">
            <ShieldCheck className="w-3.5 h-3.5 text-forest" />
            Free preview · No card to start
          </p>
        </motion.div>
      </div>
    </section>
  );
}

/* ============================================================ */
/*  FAQ                                                          */
/* ============================================================ */
function FAQSection() {
  const [openIdx, setOpenIdx] = useState(0);
  const [price, setPrice] = useState(null);

  useEffect(() => {
    api.get("/settings/price")
      .then(({ data }) => {
        setPrice(data.price);
      })
      .catch(() => {});
  }, []);

  const priceFaqAnswer = price
    ? `The $${price} single report is a one-off purchase — one complete scout report for one player, delivered in 48 hours. The monthly plans (Premium $29.99/mo, VIP $49.99/mo) give you ongoing access: more uploads per month, advanced AI analysis, progress tracking, and (with VIP) a real scout reviewing your videos. Pick the single report if you just want to try once; pick a monthly plan if you want to keep tracking progress.`
    : "The single report is a one-off purchase — one complete scout report for one player, delivered in 48 hours. The monthly plans (Premium $29.99/mo, VIP $49.99/mo) give you ongoing access: more uploads per month, advanced AI analysis, progress tracking, and (with VIP) a real scout reviewing your videos.";

  return (
    <section
      data-testid="faq-minimal"
      className="relative py-16 md:py-20 border-b border-gray-border bg-cream-base"
    >
      <div
        aria-hidden
        className="absolute inset-0 opacity-[0.04] pointer-events-none"
        style={{
          backgroundImage:
            "radial-gradient(circle at 1px 1px, #1F4F2F 1px, transparent 0)",
          backgroundSize: "32px 32px",
        }}
      />
      <div className="relative max-w-3xl mx-auto px-6 md:px-10">
        <div className="text-center mb-10">
          <div className="inline-flex items-center gap-2.5 mb-3">
            <span aria-hidden className="relative flex items-center justify-center w-2 h-2 shrink-0">
              <span className="absolute inset-0 rounded-full bg-volt animate-ping opacity-75" />
              <span className="relative rounded-full w-1.5 h-1.5 bg-volt" />
            </span>
            <span className="text-forest text-[10px] uppercase tracking-[0.28em] font-bold">
              Common questions
            </span>
            <span aria-hidden className="h-px w-8 bg-forest/35" />
          </div>
          <h2 className="font-barlow font-black uppercase tracking-tighter text-3xl md:text-5xl leading-[0.95]">
            Honest answers.<br />
            <span className="text-forest">No fluff.</span>
          </h2>
          <div className="mt-5 inline-flex items-center gap-2.5 px-3 py-1.5 border border-forest/25 bg-forest/5">
            <svg viewBox="0 0 24 24" className="w-3.5 h-3.5 text-forest shrink-0" aria-hidden>
              <circle cx="12" cy="12" r="10" fill="none" stroke="currentColor" strokeWidth="1.4" opacity="0.3" />
              <line x1="12" y1="12" x2="12" y2="6" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
              <motion.line
                x1="12" y1="12" x2="16" y2="12"
                stroke="currentColor" strokeWidth="1.4" strokeLinecap="round"
                style={{ transformOrigin: "12px 12px" }}
                animate={{ rotate: [0, 360] }}
                transition={{ duration: 4, repeat: Infinity, ease: "linear" }}
              />
              <circle cx="12" cy="12" r="1.2" fill="currentColor" />
            </svg>
            <span className="text-[10px] uppercase tracking-[0.22em] font-bold text-forest/85">
              Answered in 30 seconds
            </span>
          </div>
        </div>

        <div className="space-y-2">
          {FAQ_ITEMS.map((item, i) => {
            const isOpen = openIdx === i;
            return (
              <div
                key={i}
                data-testid={`faq-minimal-item-${i}`}
                className={`border border-gray-border bg-cream-card transition-all duration-300 ${
                  isOpen ? "shadow-md" : "hover:border-forest/40"
                }`}
              >
                <button
                  type="button"
                  onClick={() => setOpenIdx(isOpen ? -1 : i)}
                  data-testid={`faq-minimal-toggle-${i}`}
                  aria-expanded={isOpen}
                  className="w-full flex items-start justify-between gap-4 text-left px-5 py-4 md:px-6 md:py-5"
                >
                  <span className="font-barlow font-black uppercase text-base md:text-lg tracking-tight leading-tight text-ink">
                    {item.q}
                  </span>
                  <span
                    aria-hidden
                    className={`shrink-0 mt-1 w-7 h-7 flex items-center justify-center rounded-full border-2 transition-all duration-300 ${
                      isOpen ? "bg-forest border-forest rotate-45 text-white" : "border-forest/40 text-forest"
                    }`}
                  >
                    <span className="text-lg leading-none font-bold">+</span>
                  </span>
                </button>
                {isOpen && (
                  <div className="px-5 pb-5 md:px-6 md:pb-6 -mt-1">
                    <p className="text-sm md:text-[15px] text-ink/70 leading-relaxed border-l-2 border-forest/40 pl-4">
                      {item.a === "__PRICE_FAQ__" ? priceFaqAnswer : item.a}
                    </p>
                  </div>
                )}
              </div>
            );
          })}
        </div>

        <div className="mt-10 text-center">
          <p className="text-[11px] uppercase tracking-[0.22em] text-ink/50 font-bold">
            Still have questions?
          </p>
          <Link
            to="/about#contact"
            data-testid="faq-minimal-contact-link"
            className="inline-flex items-center gap-2 mt-3 text-forest hover:text-forest-pop font-barlow font-black uppercase tracking-widest text-sm transition-colors"
          >
            <Send className="w-4 h-4" />
            Send us a message
          </Link>
        </div>
      </div>
    </section>
  );
}

/* ============================================================ */
/*  FOOTER                                                       */
/* ============================================================ */
function SiteFooter() {
  return (
    <footer
      data-testid="footer-minimal"
      className="bg-ink text-white/70 px-6 md:px-10 py-10 md:py-14"
    >
      <div className="max-w-6xl mx-auto flex flex-col md:flex-row items-center md:items-start justify-between gap-6">
        <div>
          <span className="font-barlow font-black uppercase text-white text-xl tracking-[0.16em]">
            SCOUT<span className="text-ink bg-volt px-[3px]">ME</span>PLAY
          </span>
          <p className="mt-3 text-xs uppercase tracking-[0.18em] text-white/55 font-bold">
            See your game through scout eyes
          </p>
        </div>

        <nav className="flex flex-wrap items-center gap-x-5 gap-y-2 text-[11px] uppercase tracking-[0.18em] font-bold">
          <Link data-testid="footer-link-about" to="/about" className="text-white/70 hover:text-white">About</Link>
          <Link data-testid="footer-link-methodology" to="/methodology" className="text-white/70 hover:text-white">Methodology</Link>
          <Link data-testid="footer-link-blog" to="/blog" className="text-white/70 hover:text-white">Blog</Link>
          <Link data-testid="footer-link-privacy" to="/privacy" className="text-white/70 hover:text-white">Privacy</Link>
          <Link data-testid="footer-link-terms" to="/terms" className="text-white/70 hover:text-white">Terms</Link>
        </nav>
      </div>

      <div className="max-w-6xl mx-auto mt-8 pt-6 border-t border-white/10 text-[10px] uppercase tracking-[0.2em] text-white/45 font-bold flex flex-col sm:flex-row items-center justify-between gap-3">
        <span>© {new Date().getFullYear()} ScoutMePlay · MentalKids · Denmark</span>
        <span className="flex items-center gap-1.5">
          <ShieldCheck className="w-3 h-3 text-forest" />
          Secure Stripe · No subscription
        </span>
      </div>
    </footer>
  );
}
