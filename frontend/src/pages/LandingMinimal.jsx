/**
 * LandingMinimal — Premium, ryddet landing layout.
 *
 * Layout (top → bottom):
 *   1. Top bar (existing <Navigation />)
 *   2. Hero — split layout (text + Nano-Banana pitch image)
 *   3. TrustStrip — 4 quick stats
 *   4. HowItWorks — 3-step pipeline (Upload → Mark → Get report)
 *   5. WhatsInside — 4-feature grid
 *   6. PricingTiers — Free · Premium · VIP (existing component)
 *   7. SocialProof — parent testimonial
 *   8. FAQ — Honest answers, no fluff
 *   9. FinalCta — last conversion strip
 *  10. SiteFooter
 *
 * Palette stays exactly cream-base / forest / volt — no new colours.
 */
import React, { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { ArrowRight, ShieldCheck, Send, PlayCircle } from "lucide-react";

import Navigation from "@/components/Navigation";
import PricingTiers from "@/components/PricingTiers";
import SEO, { organizationJsonLd } from "@/components/SEO";
import {
  TrustStrip,
  HowItWorks,
  WhatsInside,
  ImageStrip,
  SocialProof,
  FinalCta,
} from "@/components/LandingSections";
import api from "@/lib/api";
import { useAuth } from "@/lib/auth-context";

const ASSET_BASE = process.env.REACT_APP_BACKEND_URL;

const FAQ_ITEMS = [
  {
    q: "How long does it take to get my report?",
    a: "Your Pro Scout Intelligence analysis is delivered instantly — as soon as the AI pipeline finishes processing your video (typically 5–15 minutes, depending on clip length). If your plan includes a real scout review (VIP Premium), a professional scout responds with their personal feedback within 48 hours on top of the instant AI report. If we ever miss that 48-hour window on a scout review, your purchase is refunded in full — automatically, no support tickets needed.",
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
        description="Upload your football video and get an instant AI scout report — plus a real professional scout review within 48h (VIP). Built for ambitious U7–U21 players."
        canonical="/"
        jsonLd={organizationJsonLd()}
      />

      <Navigation />

      <HeroSection onPrimaryCta={handlePrimaryCta} isLoggedIn={!!user} />
      <TrustStrip />
      <HowItWorks />
      <WhatsInside />
      <ImageStrip />
      <div id="pricing-section" data-testid="pricing-section">
        <PricingTiers />
      </div>
      <SocialProof />
      <FAQSection />
      <FinalCta isLoggedIn={!!user} />
      <SiteFooter />
    </div>
  );
}

/* ============================================================ */
/*  HERO — Lagdelt komposition med dybde og WAU effekt           */
/*  Left: dramatic copy + CTA + live scout activity ticker       */
/*  Right: stacked images (action shot + floating scout report)  */
/* ============================================================ */
function HeroSection({ onPrimaryCta, isLoggedIn }) {
  const heroAction = `${ASSET_BASE}/api/static/landing/hero-action.png`;
  const heroReport = `${ASSET_BASE}/api/static/landing/hero-report-card.png`;
  return (
    <section
      id="hero-section"
      data-testid="hero-minimal"
      className="relative px-6 md:px-10 pt-12 md:pt-16 pb-14 md:pb-20 border-b border-gray-border overflow-hidden bg-cream-base"
    >
      {/* Layered backdrop: grid + fading dot field + corner accents */}
      <div
        aria-hidden
        className="absolute inset-0 opacity-[0.05] pointer-events-none"
        style={{
          backgroundImage:
            "linear-gradient(#1F4F2F 1px, transparent 1px), linear-gradient(90deg, #1F4F2F 1px, transparent 1px)",
          backgroundSize: "56px 56px",
          maskImage: "radial-gradient(ellipse at center, black 0%, transparent 75%)",
          WebkitMaskImage: "radial-gradient(ellipse at center, black 0%, transparent 75%)",
        }}
      />
      <div
        aria-hidden
        className="absolute -top-10 -left-10 w-72 h-72 rounded-full pointer-events-none"
        style={{
          background: "radial-gradient(circle, rgba(204,255,0,0.18) 0%, transparent 70%)",
        }}
      />
      <div
        aria-hidden
        className="absolute bottom-0 right-0 w-96 h-96 rounded-full pointer-events-none"
        style={{
          background: "radial-gradient(circle, rgba(31,79,47,0.22) 0%, transparent 70%)",
        }}
      />

      <div className="relative max-w-6xl mx-auto grid grid-cols-1 lg:grid-cols-12 gap-8 lg:gap-12 items-center">
        {/* ───────── LEFT — copy + CTA ───────── */}
        <div className="lg:col-span-6 text-center lg:text-left relative">
          {/* Eyebrow with chalk line */}
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4 }}
            className="inline-flex items-center gap-2.5 mb-4"
          >
            <span aria-hidden className="relative flex items-center justify-center w-2 h-2 shrink-0">
              <span className="absolute inset-0 rounded-full bg-volt animate-ping opacity-75" />
              <span className="relative rounded-full w-1.5 h-1.5 bg-volt" />
            </span>
            <span className="text-forest text-[10px] md:text-[11px] uppercase tracking-[0.28em] font-bold">
              Pro Scout Intelligence · Instant AI · 48h scout review
            </span>
            <span aria-hidden className="h-px w-8 bg-forest/35" />
          </motion.div>

          {/* Headline — bigger, tighter, with subtle accent */}
          <motion.h1
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.55, delay: 0.05 }}
            data-testid="hero-headline"
            className="font-barlow font-black uppercase tracking-tighter text-[3.25rem] sm:text-7xl lg:text-[5.75rem] leading-[0.86] text-ink"
          >
            See your game<br />
            through<br />
            <span className="relative inline-block text-forest">
              scout eyes.
              <svg
                aria-hidden
                className="absolute -bottom-2 left-0 w-full h-2 text-volt"
                viewBox="0 0 200 8"
                preserveAspectRatio="none"
              >
                <path
                  d="M0 5 Q 50 0 100 5 T 200 5"
                  stroke="currentColor"
                  strokeWidth="3"
                  fill="none"
                  strokeLinecap="round"
                />
              </svg>
            </span>
          </motion.h1>

          {/* Subheadline */}
          <motion.p
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, delay: 0.15 }}
            className="mt-6 text-base md:text-lg text-ink/70 leading-relaxed max-w-xl mx-auto lg:mx-0"
          >
            Upload your video. Get an <span className="text-forest font-semibold">instant AI scout report</span>, plus a real professional scout&apos;s written follow-up within 48 hours (VIP).
            Built for ambitious U7&ndash;U21 players chasing the next level.
          </motion.p>

          {/* CTA row */}
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, delay: 0.25 }}
            className="mt-7 flex flex-col sm:flex-row items-center lg:items-start gap-3 sm:gap-4 justify-center lg:justify-start"
          >
            <button
              type="button"
              onClick={onPrimaryCta}
              data-testid="hero-upload-cta"
              className="group inline-flex items-center justify-center gap-3 bg-forest hover:bg-forest-pop text-white font-barlow font-black uppercase tracking-[0.18em] text-sm md:text-base px-8 md:px-10 py-4 md:py-5 transition-all w-full sm:w-auto"
              style={{
                boxShadow:
                  "0 26px 48px -16px rgba(31, 79, 47, 0.5), 0 10px 20px -8px rgba(31, 79, 47, 0.35), inset 0 1px 0 rgba(255,255,255,0.08)",
              }}
            >
              Upload your video
              <ArrowRight className="w-5 h-5 transition-transform group-hover:translate-x-1" />
            </button>
            <a
              href="#how-it-works-walkthrough"
              data-testid="hero-secondary-cta"
              className="inline-flex items-center justify-center gap-2 text-ink hover:text-forest font-barlow font-black uppercase tracking-[0.18em] text-sm border-2 border-ink/15 hover:border-forest/60 px-7 py-4 transition-colors w-full sm:w-auto"
            >
              <PlayCircle className="w-4 h-4" /> How it works
            </a>
          </motion.div>

          {/* Trust line + sign-in nudge */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.5, delay: 0.4 }}
            className="mt-5 flex flex-col sm:flex-row items-center lg:items-start gap-3 sm:gap-5 justify-center lg:justify-start"
          >
            <span className="text-[11px] text-ink/55 flex items-center gap-1.5 uppercase tracking-[0.18em] font-bold">
              <ShieldCheck className="w-3.5 h-3.5 text-forest" />
              Free preview · No card to start
            </span>
            {!isLoggedIn && (
              <span className="text-[11px] uppercase tracking-[0.18em] text-ink/55 font-bold">
                Have an account?{" "}
                <Link
                  to="/login"
                  data-testid="hero-signin-link"
                  className="text-forest hover:text-forest-pop underline underline-offset-4 decoration-forest/40"
                >
                  Sign in
                </Link>
              </span>
            )}
          </motion.div>
        </div>

        {/* ───────── RIGHT — Lagdelt billed-komposition ───────── */}
        <motion.div
          initial={{ opacity: 0, scale: 0.97 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.7, delay: 0.1 }}
          className="lg:col-span-6 relative"
          data-testid="hero-composition"
        >
          {/* MAIN — action shot frame */}
          <div className="relative aspect-[4/5] w-full bg-ink overflow-hidden border border-gray-border">
            <img
              src={heroAction}
              alt="Young footballer in action"
              onError={(e) => {
                e.currentTarget.style.display = "none";
              }}
              className="absolute inset-0 w-full h-full object-cover"
            />
            {/* Forest gradient overlay for cohesion */}
            <div
              aria-hidden
              className="absolute inset-0 bg-gradient-to-tr from-ink/45 via-transparent to-forest/25 mix-blend-multiply"
            />
            {/* Corner brackets */}
            <span aria-hidden className="absolute top-3 left-3 w-5 h-5 border-l-2 border-t-2 border-volt" />
            <span aria-hidden className="absolute top-3 right-3 w-5 h-5 border-r-2 border-t-2 border-volt" />
            <span aria-hidden className="absolute bottom-3 left-3 w-5 h-5 border-l-2 border-b-2 border-volt" />
            <span aria-hidden className="absolute bottom-3 right-3 w-5 h-5 border-r-2 border-b-2 border-volt" />

            {/* Floating "TRACKING" badge */}
            <div className="absolute top-5 left-5">
              <span className="inline-flex items-center gap-1.5 bg-volt text-ink text-[10px] uppercase tracking-[0.22em] font-black px-2.5 py-1.5">
                <span className="w-1.5 h-1.5 bg-ink rounded-full animate-pulse" />
                Pro scout · live
              </span>
            </div>

            {/* Bottom caption */}
            <div className="absolute bottom-5 left-5 right-5 flex items-end justify-between gap-3">
              <div>
                <div className="text-[10px] uppercase tracking-[0.22em] text-volt/95 font-bold">Match footage</div>
                <div className="font-barlow font-black uppercase text-white text-xl md:text-2xl leading-tight">
                  Instant AI + 48h scout
                </div>
              </div>
            </div>

            {/* Decorative scan line */}
            <motion.div
              aria-hidden
              initial={{ opacity: 0 }}
              animate={{ opacity: [0, 0.5, 0] }}
              transition={{ duration: 3, repeat: Infinity, delay: 1 }}
              className="absolute inset-x-0 h-px bg-volt"
              style={{ top: "30%" }}
            />
          </div>

          {/* FLOATING SCOUT REPORT CARD — overlapper bottom-left of image */}
          <motion.div
            initial={{ opacity: 0, y: 20, rotate: -8 }}
            animate={{ opacity: 1, y: 0, rotate: -4 }}
            transition={{ duration: 0.75, delay: 0.4, ease: "easeOut" }}
            className="absolute -bottom-6 md:-bottom-8 -left-4 md:-left-10 w-[55%] md:w-[44%] z-10"
            data-testid="hero-floating-report"
          >
            <div
              className="relative bg-cream-card border-2 border-ink overflow-hidden"
              style={{
                boxShadow:
                  "0 32px 60px -16px rgba(10,26,18,0.4), 0 12px 22px -10px rgba(10,26,18,0.3)",
              }}
            >
              <img
                src={heroReport}
                alt="Scout report preview"
                onError={(e) => {
                  e.currentTarget.style.display = "none";
                }}
                className="block w-full h-auto"
              />
              {/* Bottom strip with score */}
              <div className="bg-forest text-white px-2 md:px-3 py-1.5 md:py-2 flex items-center justify-between border-t border-ink">
                <span className="text-[8px] md:text-[9px] uppercase tracking-[0.18em] md:tracking-[0.22em] font-bold">Scout report</span>
                <span className="text-[8px] md:text-[9px] uppercase tracking-[0.18em] md:tracking-[0.22em] font-bold text-volt">
                  4-pillar · Instant AI
                </span>
              </div>
            </div>
          </motion.div>

          {/* STATS CHIP — top right */}
          <motion.div
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.6, delay: 0.55 }}
            className="absolute -top-3 md:-top-4 -right-2 md:-right-3 z-10 bg-ink text-cream-base px-3 md:px-4 py-2 md:py-3 flex items-center gap-2 md:gap-3 border border-ink"
            style={{
              boxShadow:
                "0 18px 36px -10px rgba(10,26,18,0.4)",
            }}
          >
            <span className="w-7 md:w-9 h-7 md:h-9 bg-volt text-ink flex items-center justify-center font-barlow font-black text-sm md:text-base leading-none">
              7.8
            </span>
            <div className="text-left">
              <div className="text-[8px] md:text-[9px] uppercase tracking-[0.18em] md:tracking-[0.22em] font-bold text-volt">Overall</div>
              <div className="text-[9px] md:text-[11px] uppercase tracking-[0.16em] md:tracking-[0.18em] font-bold text-cream-base/80">U14 · AMF</div>
            </div>
          </motion.div>
        </motion.div>
      </div>

      {/* HERO LIVE-TICKER — below the composition, full width */}
      <div className="relative max-w-6xl mx-auto mt-16 md:mt-16 pt-6 border-t border-forest/15 flex flex-wrap items-center justify-center md:justify-between gap-x-6 md:gap-x-8 gap-y-3">
        <span className="text-[10px] md:text-[11px] uppercase tracking-[0.28em] font-bold text-ink/45 flex items-center gap-2">
          <span aria-hidden className="relative flex items-center justify-center w-1.5 h-1.5 shrink-0">
            <span className="absolute inset-0 rounded-full bg-forest animate-ping opacity-60" />
            <span className="relative rounded-full w-1 h-1 bg-forest" />
          </span>
          Live · scouting now
        </span>
        <div className="flex items-center gap-4 md:gap-10 text-[9px] md:text-[11px] uppercase tracking-[0.2em] md:tracking-[0.22em] font-bold text-ink/55 flex-wrap justify-center">
          <span><span className="text-forest font-black">+128</span> reports / mo</span>
          <span><span className="text-forest font-black">12</span> countries</span>
          <span><span className="text-forest font-black">98%</span> 48h</span>
        </div>
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
      .then(({ data }) => setPrice(data.price))
      .catch(() => {});
  }, []);

  const priceFaqAnswer = price
    ? `The $${price} single report is a one-off purchase — one complete scout report for one player. The AI analysis is delivered instantly, and a real professional scout follows up with written feedback within 48 hours. The monthly plans (Premium $29.99/mo, VIP $49.99/mo) give you ongoing access: more uploads per month, advanced AI analysis (instant), progress tracking, and (with VIP) a real scout reviewing your videos within 48h. Pick the single report if you just want to try once; pick a monthly plan if you want to keep tracking progress.`
    : "The single report is a one-off purchase — one complete scout report for one player. The AI analysis is instant; a real professional scout follows up within 48 hours. The monthly plans (Premium $29.99/mo, VIP $49.99/mo) give you ongoing access: more uploads per month, advanced AI analysis (instant), progress tracking, and (with VIP) a real scout reviewing your videos within 48h.";

  return (
    <section
      id="faq-section"
      data-testid="faq-minimal"
      className="relative py-16 md:py-24 border-b border-gray-border bg-cream-base"
    >
      <div
        aria-hidden
        className="absolute inset-0 opacity-[0.04] pointer-events-none"
        style={{
          backgroundImage: "radial-gradient(circle at 1px 1px, #1F4F2F 1px, transparent 0)",
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
          <p className="mt-4 text-sm md:text-base text-ink/65 max-w-xl mx-auto">
            Answered in 30 seconds — everything parents and players ask before booking a report.
          </p>
        </div>

        <div className="space-y-2">
          {FAQ_ITEMS.map((item, i) => {
            const isOpen = openIdx === i;
            return (
              <div
                key={i}
                data-testid={`faq-minimal-item-${i}`}
                className={`border bg-cream-card transition-all duration-300 ${
                  isOpen
                    ? "border-forest shadow-[0_6px_22px_-12px_rgba(31,79,47,0.35)]"
                    : "border-gray-border hover:border-forest/40"
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
