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
import { motion, useMotionValue, useSpring } from "framer-motion";
import { ArrowRight, ShieldCheck, Send, PlayCircle, Instagram, Facebook, Twitter, Linkedin, Volleyball, FileText, Upload, Crosshair, Eye } from "lucide-react";

import Navigation from "@/components/Navigation";
import ReviewsStrip from "@/components/ReviewsStrip";
import SampleReportShowcase from "@/components/SampleReportShowcase";
import DreamPricingTiers from "@/components/DreamPricingTiers";
import StickyPricingCTA from "@/components/StickyPricingCTA";
import ExitIntentManager from "@/components/ExitIntentOffer";
import SEO, { organizationJsonLd, faqJsonLd } from "@/components/SEO";
import {
  TrustStrip,
  HowItWorks,
  WhatsInside,
  ImageStrip,
  FinalCta,
} from "@/components/LandingSections";
import DemoVideoCarousel from "@/components/DemoVideoCarousel";
import StatsTicker from "@/components/StatsTicker";
import SocialFollowSection from "@/components/SocialFollowSection";
import BlogHighlights from "@/components/BlogHighlights";
import api from "@/lib/api";
import { useAuth } from "@/lib/auth-context";

const ASSET_BASE = process.env.REACT_APP_BACKEND_URL;

const FAQ_ITEMS = [
  {
    q: "How long does it take to get my report?",
    a: "Your ScoutMe Pro Intelligence analysis is delivered instantly — as soon as the analysis pipeline finishes processing your video (typically 5–15 minutes, depending on clip length). If your plan includes a real scout review (VIP Premium), a professional scout responds with their personal feedback within 48 hours on top of the instant report. If we ever miss that 48-hour window on a scout review, your purchase is refunded in full — automatically, no support tickets needed.",
  },
  {
    q: "Is my child too young for this?",
    a: "ScoutMePlay is built for ambitious players aged U7 to U21. The report adjusts to the player's age — a 9-year-old is benchmarked against age-appropriate development standards, not against a senior pro. You get an honest read of where the player is, and where they could realistically go next.",
  },
  {
    q: "What if my video isn't great quality?",
    a: "A phone camera at training or a game is perfectly fine. We need to see the player on the pitch with the ball. Wider shots (showing more of the pitch) are better than tight close-ups, and a clear view of the player's movement helps the scout review. If our scout can't fairly assess the video, we contact you and either offer a re-upload or a refund.",
  },
  {
    q: "How is this different from my child's coach feedback?",
    a: "A coach knows the player from the inside — that's irreplaceable. A scout looks from the outside, comparing the player against thousands of others in a structured 4-pillar framework (Technical, Tactical, Physical, Mentality). Coaches build players day by day. ScoutMePlay tells you where they stand right now and what to focus on next.",
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

  // Admin-editable FAQ — pulled from /api/faq. Falls back to the hardcoded
  // FAQ_ITEMS on failure so the landing never renders empty.
  const [faqItems, setFaqItems] = useState(FAQ_ITEMS);
  useEffect(() => {
    let alive = true;
    api.get("/faq").then(({ data }) => {
      if (!alive) return;
      const items = Array.isArray(data?.items) ? data.items : [];
      if (items.length > 0) {
        setFaqItems(items.map((it) => ({ q: it.q, a: it.a })));
      }
    }).catch(() => { /* keep hardcoded fallback */ });
    return () => { alive = false; };
  }, []);

  const handlePrimaryCta = () => {
    // Guest-first flow: straight to /upload — account is created at "Start analysis".
    navigate("/upload");
  };

  return (
    <div data-testid="landing-minimal" className="min-h-screen bg-cream-base text-ink overflow-x-clip">
      <SEO
        pageKey="home"
        title="ScoutMePlay — Discover your true football level"
        description="Upload your football video and get an instant ScoutMe Pro report — plus a real professional scout review within 48h (VIP). Built for ambitious U7–U21 players."
        canonical="/"
        jsonLd={[organizationJsonLd(), faqJsonLd(faqItems)]}
      />

      <Navigation />
      <StatsTicker />

      <HeroSection onPrimaryCta={handlePrimaryCta} isLoggedIn={!!user} />
      <SampleReportShowcase onPrimaryCta={handlePrimaryCta} />
      <TrustStrip />
      <HowItWorks />
      <WhatsInside />
      <ImageStrip />
      <div id="pricing-section" data-testid="pricing-section">
        <DreamPricingTiers isLoggedIn={!!user} />
      </div>
      <StickyPricingCTA isLoggedIn={!!user} />
      <ExitIntentManager />
      <ReviewsStrip />
      <SocialFollowSection />
      <BlogHighlights />
      <FAQSection faqItems={faqItems} />
      <DemoVideoCarousel />
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
  const heroPlayer = `${ASSET_BASE}/api/static/landing/hero-player.jpg`;
  const CREAM = "#F4EFE6";
  const features = [
    { icon: Crosshair, l1: "Analyse", l2: "your game" },
    { icon: Eye, l1: "Get seen", l2: "by scouts" },
    { icon: ShieldCheck, l1: "Find trials &", l2: "opportunities" },
  ];
  // Mouse parallax — the photo leans gently away from the cursor (desktop).
  const mx = useMotionValue(0);
  const my = useMotionValue(0);
  const px = useSpring(mx, { stiffness: 42, damping: 16 });
  const py = useSpring(my, { stiffness: 42, damping: 16 });
  const handleHeroMouseMove = (e) => {
    const r = e.currentTarget.getBoundingClientRect();
    mx.set(((e.clientX - r.left) / r.width - 0.5) * -14);
    my.set(((e.clientY - r.top) / r.height - 0.5) * -10);
  };
  const resetHeroParallax = () => { mx.set(0); my.set(0); };
  return (
    <section
      id="hero-section"
      data-testid="hero-minimal"
      onMouseMove={handleHeroMouseMove}
      onMouseLeave={resetHeroParallax}
      className="relative px-5 md:px-10 pt-6 md:pt-12 pb-12 md:pb-16 border-b border-gray-border overflow-hidden bg-cream-base"
    >
      <div
        aria-hidden
        className="absolute -top-10 -left-10 w-72 h-72 rounded-full pointer-events-none"
        style={{ background: "radial-gradient(circle, rgba(204,255,0,0.16) 0%, transparent 70%)" }}
      />

      <div className="relative max-w-6xl mx-auto">
        {/* ── Copy + player image ── */}
        <div className="relative">
          {/* Player photo — bleeds right, blends into the cream background.
              "Alive" layers: slow drift + mouse parallax + light sweep + drifting dust motes. */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.9 }}
            aria-hidden
            className="absolute inset-y-0 -right-5 md:right-0 w-[60%] sm:w-[52%] lg:w-[46%] pointer-events-none select-none overflow-hidden"
            data-testid="hero-player-photo"
          >
            <style>{`
              @keyframes smp-hero-drift { from { transform: scale(1.06) translate(0px, 0px); } to { transform: scale(1.14) translate(-14px, -9px); } }
              @keyframes smp-hero-sweep { 0% { transform: translateX(-160%) rotate(16deg); } 55%, 100% { transform: translateX(320%) rotate(16deg); } }
              @keyframes smp-hero-mote { 0% { transform: translateY(0) translateX(0); opacity: 0; } 12% { opacity: var(--mo, 0.55); } 82% { opacity: var(--mo, 0.55); } 100% { transform: translateY(-46vh) translateX(var(--mx, 8px)); opacity: 0; } }
              @keyframes smp-hero-glowpulse { 0%, 100% { opacity: 0.25; } 50% { opacity: 0.5; } }
              @media (prefers-reduced-motion: reduce) { .smp-hero-anim { animation: none !important; } }
            `}</style>
            <motion.div className="absolute inset-0" style={{ x: px, y: py }}>
              <img
                src={heroPlayer}
                alt=""
                onError={(e) => { e.currentTarget.style.display = "none"; }}
                className="smp-hero-anim smp-hero-img w-full h-full object-cover object-top"
                style={{ animation: "smp-hero-drift 16s ease-in-out infinite alternate" }}
              />
            </motion.div>
            {/* warm breathing glow behind the player */}
            <div
              className="smp-hero-anim absolute inset-0"
              style={{
                background: "radial-gradient(52% 42% at 62% 34%, rgba(255,196,110,0.35) 0%, transparent 70%)",
                mixBlendMode: "screen",
                animation: "smp-hero-glowpulse 7s ease-in-out infinite",
              }}
            />
            {/* cinematic light sweep */}
            <span
              className="smp-hero-anim absolute -inset-y-10 w-[46%]"
              style={{
                background: "linear-gradient(90deg, transparent 0%, rgba(255,242,214,0.22) 45%, rgba(255,255,255,0.14) 55%, transparent 100%)",
                mixBlendMode: "screen",
                filter: "blur(6px)",
                animation: "smp-hero-sweep 8.5s ease-in-out infinite",
              }}
            />
            {/* drifting golden dust motes */}
            {[
              { l: "22%", b: "8%", s: 5, d: "0s", t: "11s", o: 0.5, x: "14px" },
              { l: "38%", b: "16%", s: 3, d: "2.2s", t: "13s", o: 0.42, x: "-10px" },
              { l: "58%", b: "6%", s: 6, d: "4.1s", t: "12s", o: 0.55, x: "10px" },
              { l: "72%", b: "20%", s: 4, d: "1.4s", t: "14s", o: 0.4, x: "-14px" },
              { l: "48%", b: "30%", s: 3, d: "5.6s", t: "12.5s", o: 0.45, x: "8px" },
              { l: "84%", b: "12%", s: 4, d: "3.3s", t: "11.5s", o: 0.5, x: "-8px" },
            ].map((m, i) => (
              <span
                key={i}
                className="smp-hero-anim absolute rounded-full"
                style={{
                  left: m.l, bottom: m.b, width: m.s, height: m.s,
                  background: "radial-gradient(circle, rgba(255,236,180,0.95) 0%, rgba(255,214,120,0.35) 60%, transparent 100%)",
                  filter: "blur(0.5px)",
                  "--mo": m.o, "--mx": m.x,
                  animation: `smp-hero-mote ${m.t} linear ${m.d} infinite`,
                  opacity: 0,
                }}
              />
            ))}
            <div
              className="absolute inset-0"
              style={{
                background: `linear-gradient(90deg, ${CREAM} 0%, rgba(244,239,230,0) 34%), linear-gradient(0deg, ${CREAM} 0%, rgba(244,239,230,0) 24%), linear-gradient(180deg, ${CREAM} 0%, rgba(244,239,230,0) 7%), linear-gradient(270deg, ${CREAM} 0%, rgba(244,239,230,0) 6%)`,
              }}
            />
          </motion.div>

          {/* Copy column — top-aligned with the player photo */}
          <div className="relative z-10">
            <motion.h1
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.55, delay: 0.05 }}
              data-testid="hero-headline"
              className="font-barlow font-black uppercase tracking-tighter leading-[0.88] text-ink text-[2.85rem] sm:text-6xl lg:text-[5.5rem] max-w-[64%] sm:max-w-[58%] lg:max-w-[56%]"
            >
              Turn your<br />
              game into<br />
              <span className="text-forest">opportunity.</span>
            </motion.h1>

            {/* Hand-drawn brush stroke */}
            <motion.svg
              initial={{ opacity: 0, scaleX: 0.6 }}
              animate={{ opacity: 1, scaleX: 1 }}
              transition={{ duration: 0.5, delay: 0.35 }}
              aria-hidden
              viewBox="0 0 220 12"
              className="mt-3 h-3 w-[190px] sm:w-[240px] text-ink origin-left"
              preserveAspectRatio="none"
            >
              <path
                d="M3 8 Q 40 3 85 6 T 160 5 T 217 6"
                stroke="currentColor"
                strokeWidth="5"
                fill="none"
                strokeLinecap="round"
              />
            </motion.svg>

            <motion.p
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.5, delay: 0.15 }}
              className="mt-6 md:mt-8 text-[15px] md:text-lg text-ink/75 leading-relaxed max-w-[58%] sm:max-w-[50%] lg:max-w-[44%]"
            >
              Upload your football video and get a detailed{" "}
              <span className="text-forest font-semibold">ScoutMe Pro analysis</span>.
              Discover your strengths, improve your game and showcase your talent
              to scouts looking for players.
            </motion.p>

            {/* Feature icon row */}
            <motion.div
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.5, delay: 0.25 }}
              className="mt-8 md:mt-10 grid grid-cols-3 max-w-[66%] sm:max-w-[56%] lg:max-w-[46%] divide-x divide-ink/15"
              data-testid="hero-feature-row"
            >
              {features.map(({ icon: Icon, l1, l2 }) => (
                <div key={l1} className="flex flex-col items-center text-center gap-2 px-1 sm:px-3">
                  <Icon className="w-6 h-6 md:w-7 md:h-7 text-forest shrink-0" strokeWidth={1.7} />
                  <span className="text-[9px] sm:text-[10px] md:text-[11px] uppercase tracking-[0.04em] font-black text-ink leading-[1.35] whitespace-nowrap">
                    {l1}<br />{l2}
                  </span>
                </div>
              ))}
            </motion.div>
          </div>
        </div>

        {/* ── CTA rows — full width ── */}
        <motion.div
          initial={{ opacity: 0, y: 14 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.35 }}
          className="relative z-10 mt-8 md:mt-12"
        >
          <style>{`
            @keyframes smp-hero-glow { 0%,100% { box-shadow: 0 22px 44px -14px rgba(51,105,30,0.55), 0 0 14px rgba(204,255,0,0.12); } 50% { box-shadow: 0 22px 44px -14px rgba(51,105,30,0.55), 0 0 30px rgba(204,255,0,0.4); } }
            @keyframes smp-hero-shine { 0% { transform: translateX(-160%) skewX(-18deg); } 60%, 100% { transform: translateX(280%) skewX(-18deg); } }
          `}</style>
          <button
            type="button"
            onClick={onPrimaryCta}
            data-testid="hero-upload-cta"
            className="group relative overflow-hidden w-full flex items-center gap-4 rounded-[18px] px-5 md:px-7 py-4.5 p-5 transition-transform hover:scale-[1.01] active:scale-[0.99]"
            style={{
              background: "linear-gradient(180deg, #79A83D 0%, #4C7A28 45%, #33591C 100%)",
              border: "1px solid rgba(255,255,255,0.25)",
              animation: "smp-hero-glow 2.8s ease-in-out infinite",
            }}
          >
            <span aria-hidden className="absolute inset-y-0 w-1/3 bg-white/15 pointer-events-none" style={{ animation: "smp-hero-shine 3.4s ease-in-out infinite" }} />
            <Upload className="relative z-10 w-6 h-6 md:w-7 md:h-7 text-white shrink-0" strokeWidth={2.2} />
            <span className="relative z-10 flex-1 text-center font-barlow font-black uppercase tracking-[0.06em] text-white text-[20px] sm:text-[26px] md:text-[30px] leading-none">
              Upload your video
            </span>
            <span aria-hidden className="relative z-10 hidden sm:block w-px h-8 md:h-10 bg-white/35 shrink-0" />
            <Volleyball className="relative z-10 w-6 h-6 md:w-8 md:h-8 text-white/90 shrink-0 transition-transform group-hover:rotate-45" strokeWidth={1.6} />
          </button>

          <div className="mt-3 grid grid-cols-1 sm:grid-cols-2 gap-3">
            <a
              href="#how-it-works-walkthrough"
              data-testid="hero-secondary-cta"
              className="inline-flex items-center justify-center gap-2.5 rounded-[14px] bg-cream-card border border-ink/10 shadow-[0_4px_14px_-6px_rgba(10,26,18,0.18)] text-ink hover:text-forest hover:border-forest/50 font-barlow font-black uppercase tracking-[0.14em] text-sm md:text-base px-6 py-4 transition-colors"
            >
              <PlayCircle className="w-5 h-5" /> How it works
            </a>
            <Link
              to="/sample-report"
              data-testid="hero-sample-report-cta"
              className="inline-flex items-center justify-center gap-2.5 rounded-[14px] bg-cream-card border border-ink/10 shadow-[0_4px_14px_-6px_rgba(10,26,18,0.18)] text-forest hover:text-ink hover:border-forest/50 font-barlow font-black uppercase tracking-[0.14em] text-sm md:text-base px-6 py-4 transition-colors"
            >
              <FileText className="w-5 h-5" /> See a sample report
            </Link>
          </div>

          {/* Trust line + sign-in nudge */}
          <div className="mt-5 flex flex-col sm:flex-row items-center justify-center gap-3 sm:gap-6">
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
          </div>
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
function FAQSection({ faqItems }) {
  const [openIdx, setOpenIdx] = useState(0);
  const [price, setPrice] = useState(null);

  useEffect(() => {
    api.get("/settings/price")
      .then(({ data }) => setPrice(data.price))
      .catch(() => {});
  }, []);

  const priceFaqAnswer = price
    ? `The $${price} single report is a one-off purchase — one complete scout report for one player. The analysis is delivered instantly, and a real professional scout follows up with written feedback within 48 hours. The monthly plans (Premium $29.99/mo, VIP $49.99/mo) give you ongoing access: more uploads per month, advanced analysis (instant), progress tracking, and (with VIP) a real scout reviewing your videos within 48h. Pick the single report if you just want to try once; pick a monthly plan if you want to keep tracking progress.`
    : "The single report is a one-off purchase — one complete scout report for one player. The analysis is instant; a real professional scout follows up within 48 hours. The monthly plans (Premium $29.99/mo, VIP $49.99/mo) give you ongoing access: more uploads per month, advanced analysis (instant), progress tracking, and (with VIP) a real scout reviewing your videos within 48h.";

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
          {faqItems.map((item, i) => {
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
  const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
  const [social, setSocial] = useState(null);
  useEffect(() => {
    api.get("/settings/price").then(({ data }) => setSocial(data?.social || null)).catch(() => {});
  }, []);

  const socialLinks = [
    ["instagram", Instagram, social?.instagram_url || social?.instagram],
    ["facebook", Facebook, social?.facebook_url || social?.facebook],
    ["twitter", Twitter, social?.twitter_url || social?.twitter],
    ["linkedin", Linkedin, social?.linkedin_url || social?.linkedin],
  ].filter(([, , url]) => !!url);

  return (
    <footer
      data-testid="footer-minimal"
      className="relative isolate overflow-hidden bg-ink text-white/75 px-6 md:px-10 pt-16 md:pt-20 pb-8"
    >
      {/* Aerial turf at midnight */}
      <div
        aria-hidden
        className="absolute inset-0 -z-30 opacity-70"
        style={{
          backgroundImage: `url(${BACKEND_URL}/api/static/landing/footer-hero-turf.png)`,
          backgroundSize: "cover",
          backgroundPosition: "center 30%",
        }}
      />
      <div
        aria-hidden
        className="absolute inset-0 -z-20"
        style={{
          background:
            "linear-gradient(180deg, rgba(8,18,12,0.86) 0%, rgba(8,18,12,0.68) 40%, rgba(8,18,12,0.94) 100%)",
        }}
      />
      {/* Floodlight glow along the top edge */}
      <div
        aria-hidden
        className="absolute top-0 left-0 right-0 h-px -z-10"
        style={{
          background:
            "linear-gradient(90deg, transparent 0%, rgba(204,255,0,0.4) 20%, rgba(245,196,67,0.45) 50%, rgba(204,255,0,0.4) 80%, transparent 100%)",
        }}
      />
      <span
        aria-hidden
        className="absolute top-0 left-1/2 -translate-x-1/2 w-64 h-12 -z-10 pointer-events-none"
        style={{ background: "radial-gradient(ellipse at top, rgba(245,196,67,0.32) 0%, transparent 70%)" }}
      />
      {/* Giant watermark */}
      <span
        aria-hidden
        className="absolute -bottom-6 left-1/2 -translate-x-1/2 -z-10 font-barlow font-black uppercase whitespace-nowrap select-none pointer-events-none tracking-tight"
        style={{ fontSize: "clamp(80px, 14vw, 200px)", color: "rgba(204,255,0,0.045)", lineHeight: 1 }}
      >
        ScoutMePlay
      </span>

      <div className="relative max-w-6xl mx-auto grid grid-cols-1 md:grid-cols-[1.5fr_1fr_1fr] gap-10 md:gap-8 text-center md:text-left">
        {/* Brand + story */}
        <div>
          <span className="font-barlow font-black uppercase text-white text-2xl md:text-3xl tracking-[0.14em]">
            SCOUT<span className="text-ink bg-volt px-[3px] mx-[1px]">ME</span>PLAY
          </span>
          <p className="mt-4 text-[15px] text-white/80 leading-relaxed max-w-sm mx-auto md:mx-0">
            Every player has a story worth seeing.
            <span className="text-white font-semibold"> Upload one clip — and let yours begin.</span>
          </p>
          <Link
            to="/upload"
            data-testid="footer-upload-link"
            className="group inline-flex items-center gap-2 mt-5 text-volt font-barlow font-black uppercase tracking-[0.16em] text-[12px] hover:text-[#D8FF33] transition-colors"
          >
            Start your story
            <ArrowRight className="w-3.5 h-3.5 transition-transform group-hover:translate-x-1" />
          </Link>
        </div>

        {/* Explore */}
        <div>
          <div className="text-[10px] font-black uppercase tracking-[0.28em] text-volt/80 mb-4">Explore</div>
          <ul className="space-y-2.5">
            {[
              ["/about", "About us", "footer-link-about"],
              ["/methodology", "How it works", "footer-link-methodology"],
              ["/blog", "Stories & blog", "footer-link-blog"],
              ["/upload", "Upload a video", "footer-link-upload"],
            ].map(([to, label, testid]) => (
              <li key={to}>
                <Link to={to} data-testid={testid} className="text-[13.5px] text-white/70 hover:text-volt transition-colors">
                  {label}
                </Link>
              </li>
            ))}
          </ul>
        </div>

        {/* Connect + legal */}
        <div>
          <div className="text-[10px] font-black uppercase tracking-[0.28em] text-volt/80 mb-4">Connect</div>
          <div className="flex items-center gap-3 justify-center md:justify-start">
            {socialLinks.length > 0 ? socialLinks.map(([key, Icon, url]) => (
              <a
                key={key}
                href={url}
                target="_blank"
                rel="noopener noreferrer"
                aria-label={key}
                data-testid={`footer-social-${key}`}
                className="w-9 h-9 rounded-full border border-white/20 flex items-center justify-center text-white/70 hover:text-volt hover:border-volt hover:-translate-y-0.5 transition-all"
              >
                <Icon className="w-4 h-4" />
              </a>
            )) : (
              <span className="text-[12px] text-white/40">Follow the journey — coming soon</span>
            )}
          </div>
          <ul className="mt-5 space-y-2.5">
            <li>
              <Link to="/privacy" data-testid="footer-link-privacy" className="text-[13.5px] text-white/70 hover:text-volt transition-colors">Privacy</Link>
            </li>
            <li>
              <Link to="/terms" data-testid="footer-link-terms" className="text-[13.5px] text-white/70 hover:text-volt transition-colors">Terms</Link>
            </li>
          </ul>
        </div>
      </div>

      {/* Bottom bar */}
      <div className="relative max-w-6xl mx-auto mt-12 pt-6 border-t border-white/10 flex flex-col sm:flex-row items-center justify-between gap-3">
        <span className="text-[11px] text-white/50">© {new Date().getFullYear()} ScoutMePlay. All rights reserved.</span>
        <span className="flex items-center gap-2 text-[10px] uppercase tracking-[0.2em] font-bold text-white/50">
          <ShieldCheck className="w-3.5 h-3.5 text-volt" strokeWidth={2.4} />
          <span>Secure Stripe · Cancel anytime</span>
        </span>
      </div>
    </footer>
  );
}
