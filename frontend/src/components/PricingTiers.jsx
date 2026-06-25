/**
 * PricingTiers — Three-tier pricing comparison block (Free / Premium / VIP).
 *
 * Pixel-faithful rebuild of the user-supplied screenshot. Placed on the
 * minimal landing page directly below the upload hero. All three CTA
 * buttons are wired:
 *   - Free  "GET STARTED"     → /signup (or /upload if already logged in)
 *   - Premium "START PREMIUM"  → /signup?plan=premium  (placeholder for
 *                                future subscription checkout)
 *   - VIP   "GO VIP"           → /signup?plan=vip
 *
 * Section is purely presentational — no plan-specific backend logic is
 * wired here yet because the app currently ships a one-time-purchase
 * model ($159 single / $399 12-month). When the subscription backend
 * is built, only the `onClick` handlers below need to change.
 */
import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import {
  Check, X, Crown, Star, Trophy, TrendingUp,
  Shield, Users, BarChart3, Lock, ArrowRight, CreditCard, Loader2,
} from "lucide-react";

import api from "@/lib/api";
import { useAuth } from "@/lib/auth-context";

/* ── Plan data ───────────────────────────────────────────────────────── */
const FREE_FEATURES = [
  { label: "Professional Player Profile", included: true },
  { label: "1 Video Upload", included: true },
  { label: "Basic AI Football Analysis", included: true },
  { label: "Entry-Level Performance Insights", included: true },
  { label: "Progress Tracking", included: false },
  { label: "Development Plan", included: false },
  { label: "Download PDF Reports", included: false },
  { label: "Visible to Scouts", included: false },
  { label: "Real Scout Review", included: false },
  { label: "Direct Scout Contact", included: false },
  { label: "Personalized Scout Feedback Report", included: false },
];

const PREMIUM_FEATURES = [
  { label: "Professional Player Profile", included: true },
  { label: "5 Video Uploads Monthly", included: true },
  { label: "Advanced AI Football Analysis", included: true },
  { label: "Progress Tracking", included: true },
  { label: "Personal Development Plan", included: true },
  { label: "Download PDF Reports", included: true },
  { label: "Visible to Scouts in Player Database", included: true },
  { label: "Real Scout Review", included: false },
  { label: "Direct Scout Contact", included: false },
  { label: "Personalized Scout Feedback Report", included: false },
];

const VIP_FEATURES = [
  { label: "Everything in Premium", included: true },
  { label: "Unlimited Video Uploads", included: true },
  { label: "Elite AI Football Analysis", included: true },
  { label: "Real Scout Reviews Your Videos", included: true },
  { label: "Direct Contact with Professional Scouts", included: true },
  { label: "Personalized Scout Feedback Report", included: true },
  { label: "Maximum Exposure for Opportunities", included: true },
];

/* ── Custom inline cleat/boot SVG (no lucide equivalent exists) ──────── */
function CleatIcon({ className = "w-12 h-12", stroke = "#1F4F2F" }) {
  return (
    <svg viewBox="0 0 64 64" className={className} fill="none" aria-hidden>
      <path
        d="M6 38c4-1 7-3 11-3l8-1c2-3 5-7 9-9 5-2 12-2 18-1 6 1 11 4 12 7 1 4-2 9-7 11l-3 1H10c-3 0-5-2-5-4 0-1 .3-1.7 1-2z"
        stroke={stroke}
        strokeWidth="2.4"
        strokeLinejoin="round"
      />
      {/* stud-marks */}
      <circle cx="20" cy="46" r="2" fill={stroke} />
      <circle cx="30" cy="48" r="2" fill={stroke} />
      <circle cx="42" cy="48" r="2" fill={stroke} />
      <circle cx="52" cy="46" r="2" fill={stroke} />
      {/* laces */}
      <path d="M30 28l16-3M30 32l16-3M30 36l16-3" stroke={stroke} strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  );
}

/* ────────────────────────────────────────────────────────────────────── */
export default function PricingTiers() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [busyTier, setBusyTier] = useState(null);  // "premium" | "vip" | null

  /* Free tier — no payment, just route to signup / upload */
  const goFree = () => {
    if (user) navigate("/upload");
    else navigate("/signup?plan=free");
  };

  /* Paid tiers — start a Stripe Checkout subscription session.
     If the user isn't logged in yet, we send them to signup first
     with `next` set so they land back here after creating an account. */
  const startSubscription = async (tier) => {
    if (!user) {
      navigate(`/signup?plan=${tier}&next=/?subscribe=${tier}`);
      return;
    }
    if (busyTier) return;
    setBusyTier(tier);
    try {
      const { data } = await api.post("/payments/subscribe", {
        tier,
        origin_url: window.location.origin,
      });
      if (!data?.url) throw new Error("No checkout URL received");
      // Full redirect to Stripe-hosted checkout
      window.location.href = data.url;
    } catch (err) {
      const detail = err?.response?.data?.detail || err.message || "Could not start checkout.";
      toast.error(detail, { duration: 8000 });
      setBusyTier(null);
    }
  };

  const goPremium = () => startSubscription("premium");
  const goVip = () => startSubscription("vip");

  return (
    <section
      data-testid="pricing-tiers"
      className="relative px-3 sm:px-6 md:px-10 py-10 sm:py-16 md:py-24 border-b border-gray-border bg-cream-base overflow-hidden"
    >
      {/* Section heading + player silhouette */}
      <Header />

      {/* Three pricing cards — always 3 columns side-by-side, even on mobile.
          Compressed paddings and font sizes on mobile make the content fit
          on a 360–400 px-wide phone screen while keeping the design intent
          from the user-provided screenshot (all plans visible at a glance,
          no swiping required). */}
      <div
        className="mt-8 sm:mt-12 md:mt-14 max-w-6xl mx-auto grid grid-cols-3 gap-1.5 sm:gap-4 md:gap-6"
        data-testid="pricing-tiers-cards"
      >
        <FreeCard onCta={goFree} />
        <PremiumCard onCta={goPremium} loading={busyTier === "premium"} disabled={!!busyTier && busyTier !== "premium"} />
        <VipCard onCta={goVip} loading={busyTier === "vip"} disabled={!!busyTier && busyTier !== "vip"} />
      </div>

      {/* Trust badges row */}
      <TrustRow />

      {/* "Your Journey · Our Mission" bottom CTA strip */}
      <JourneyStrip onCta={goFree} />

      {/* Payment-method footer line */}
      <PaymentFooter />
    </section>
  );
}

/* ============================================================ */
/*  HEADER                                                       */
/* ============================================================ */
function Header() {
  return (
    <div className="max-w-6xl mx-auto relative">
      <div className="flex flex-col md:flex-row items-start md:items-end justify-between gap-4">
        <div className="md:max-w-[68%]">
          <h2
            data-testid="pricing-tiers-title"
            className="font-barlow font-black uppercase tracking-tighter leading-[0.92] text-2xl sm:text-4xl md:text-6xl"
          >
            <span className="text-ink">Compare </span>
            <span className="text-forest">Plans</span><br />
            <span className="text-ink">Choose </span>
            <span className="text-forest">your path</span><br />
            <span className="text-ink">to the next level</span>
          </h2>
          <p className="mt-5 text-base md:text-lg text-ink/70 leading-relaxed max-w-xl">
            Powerful tools. Professional insights. Everything you need to get discovered.
          </p>
          <span className="inline-flex items-center gap-2 mt-5 px-3.5 py-1.5 bg-cream-card border border-forest/25 text-[10px] uppercase tracking-[0.22em] font-bold text-forest">
            <svg viewBox="0 0 24 24" className="w-3.5 h-3.5" fill="currentColor" aria-hidden>
              <path d="M12 2l8 4v6c0 5-3.5 9-8 10-4.5-1-8-5-8-10V6l8-4z" />
            </svg>
            Built for U7–U21 players
          </span>
        </div>
      </div>
    </div>
  );
}

/* ============================================================ */
/*  FREE CARD                                                    */
/* ============================================================ */
function FreeCard({ onCta }) {
  return (
    <div
      data-testid="pricing-card-free"
      className="relative bg-cream-card border border-gray-border p-2 sm:p-5 md:p-7 flex flex-col w-full"
    >
      <div className="flex justify-center mb-2 sm:mb-4">
        <CleatIcon className="w-7 h-7 sm:w-10 sm:h-10 md:w-12 md:h-12" />
      </div>

      <h3 className="text-center font-barlow font-black uppercase text-sm sm:text-xl md:text-2xl text-ink tracking-tight">
        Free
      </h3>
      <div className="text-center mt-0.5 sm:mt-1">
        <span className="font-barlow font-black text-xl sm:text-3xl md:text-4xl text-ink">$0</span>
        <span className="block text-[8px] sm:text-[11px] uppercase tracking-[0.15em] sm:tracking-[0.22em] text-ink/60 font-bold">
          / month
        </span>
      </div>

      <p className="mt-2 sm:mt-3 text-center text-[10px] sm:text-sm text-ink/65 leading-snug">
        <span className="hidden sm:inline">Perfect for getting started<br />and exploring.</span>
        <span className="sm:hidden">Start here.</span>
      </p>

      <div className="my-3 sm:my-5 h-px bg-gray-border" />

      <ul className="space-y-1.5 sm:space-y-2.5 flex-1">
        {FREE_FEATURES.map((f, i) => (
          <FeatureItem key={i} {...f} tone="forest" />
        ))}
      </ul>

      <button
        type="button"
        onClick={onCta}
        data-testid="pricing-cta-free"
        className="mt-3 sm:mt-6 group inline-flex items-center justify-center gap-1 sm:gap-2 w-full border-2 border-ink/85 text-ink hover:bg-ink hover:text-cream-base font-barlow font-black uppercase tracking-[0.12em] sm:tracking-[0.2em] text-[10px] sm:text-sm py-2 sm:py-3.5 transition-all"
      >
        Get Started
      </button>
    </div>
  );
}

/* ============================================================ */
/*  PREMIUM CARD                                                 */
/* ============================================================ */
function PremiumCard({ onCta, loading = false, disabled = false }) {
  return (
    <div
      data-testid="pricing-card-premium"
      className="relative bg-[#0F3A22] border border-forest p-2 sm:p-5 md:p-7 flex flex-col text-white shadow-[0_24px_48px_-16px_rgba(15,58,34,0.55)] w-full"
    >
      {/* MOST POPULAR badge — half-overlapping the top edge */}
      <span
        aria-hidden
        className="absolute -top-2 sm:-top-3 left-1/2 -translate-x-1/2 inline-flex items-center gap-1 sm:gap-1.5 px-1.5 sm:px-3 py-0.5 sm:py-1 rounded-full bg-[#A5DD5F] text-[#0F3A22] text-[7px] sm:text-[10px] uppercase tracking-[0.1em] sm:tracking-[0.18em] font-black shadow-md whitespace-nowrap"
      >
        <Star className="w-2 h-2 sm:w-3 sm:h-3 fill-current" /> Most popular
      </span>

      <div className="flex justify-center mb-2 sm:mb-3 mt-1 sm:mt-2">
        <span className="w-8 h-8 sm:w-12 sm:h-12 md:w-14 md:h-14 rounded-full bg-white flex items-center justify-center">
          <TrendingUp className="w-4 h-4 sm:w-6 sm:h-6 md:w-7 md:h-7 text-[#0F3A22]" strokeWidth={2.6} />
        </span>
      </div>

      <h3 className="text-center font-barlow font-black uppercase text-sm sm:text-xl md:text-2xl tracking-tight">
        Premium
      </h3>
      <div className="text-center mt-0.5 sm:mt-1">
        <span className="font-barlow font-black text-xl sm:text-3xl md:text-5xl text-[#CCFF00]">$29.99</span>
        <span className="block text-[8px] sm:text-[11px] uppercase tracking-[0.15em] sm:tracking-[0.22em] text-white/70 font-bold mt-0.5 sm:mt-1">
          / month
        </span>
      </div>

      <p className="mt-2 sm:mt-3 text-center text-[10px] sm:text-sm text-white/75 leading-snug">
        <span className="hidden sm:inline">Take your development<br />seriously.</span>
        <span className="sm:hidden">Develop seriously.</span>
      </p>

      <div className="my-3 sm:my-5 h-px bg-white/15" />

      <ul className="space-y-1.5 sm:space-y-2.5 flex-1">
        {PREMIUM_FEATURES.map((f, i) => (
          <FeatureItem key={i} {...f} tone="lime" dark />
        ))}
      </ul>

      <button
        type="button"
        onClick={onCta}
        disabled={loading || disabled}
        data-testid="pricing-cta-premium"
        className="mt-3 sm:mt-6 group inline-flex items-center justify-center gap-1 sm:gap-2 w-full bg-[#A5DD5F] hover:bg-[#B9E97A] text-[#0F3A22] font-barlow font-black uppercase tracking-[0.12em] sm:tracking-[0.2em] text-[10px] sm:text-sm py-2 sm:py-3.5 transition-all disabled:opacity-60 disabled:cursor-wait"
      >
        {loading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <>Start Premium <ArrowRight className="hidden sm:inline w-4 h-4 transition-transform group-hover:translate-x-0.5" /></>}
      </button>
    </div>
  );
}

/* ============================================================ */
/*  VIP CARD                                                     */
/* ============================================================ */
function VipCard({ onCta, loading = false, disabled = false }) {
  return (
    <div
      data-testid="pricing-card-vip"
      className="relative bg-[#0A0F0D] border border-[#1F2724] p-2 sm:p-5 md:p-7 flex flex-col text-white shadow-[0_24px_48px_-16px_rgba(0,0,0,0.65)] w-full"
    >
      {/* BEST VALUE badge */}
      <span
        aria-hidden
        className="absolute -top-2 sm:-top-3 left-1/2 -translate-x-1/2 inline-flex items-center gap-1 sm:gap-1.5 px-1.5 sm:px-3 py-0.5 sm:py-1 rounded-full bg-[#F5C443] text-[#0A0F0D] text-[7px] sm:text-[10px] uppercase tracking-[0.1em] sm:tracking-[0.18em] font-black shadow-md whitespace-nowrap"
      >
        <Trophy className="w-2 h-2 sm:w-3 sm:h-3 fill-current" /> Best value
      </span>

      <div className="flex justify-center mb-2 sm:mb-3 mt-1 sm:mt-2">
        <span className="w-8 h-8 sm:w-12 sm:h-12 md:w-14 md:h-14 rounded-full bg-transparent border border-[#F5C443]/35 flex items-center justify-center">
          <Crown className="w-4 h-4 sm:w-6 sm:h-6 md:w-7 md:h-7 text-[#F5C443]" strokeWidth={2.2} fill="#F5C443" />
        </span>
      </div>

      <h3 className="text-center font-barlow font-black uppercase text-sm sm:text-xl md:text-2xl tracking-tight">
        <span className="hidden sm:inline">VIP Premium</span>
        <span className="sm:hidden">VIP</span>
      </h3>
      <div className="text-center mt-0.5 sm:mt-1">
        <span className="font-barlow font-black text-xl sm:text-3xl md:text-5xl text-[#F5C443]">$49.99</span>
        <span className="block text-[8px] sm:text-[11px] uppercase tracking-[0.15em] sm:tracking-[0.22em] text-white/70 font-bold mt-0.5 sm:mt-1">
          / month
        </span>
      </div>

      <p className="mt-2 sm:mt-3 text-center text-[10px] sm:text-sm text-white/75 leading-snug">
        <span className="hidden sm:inline">Maximum exposure.<br />Maximum opportunities.</span>
        <span className="sm:hidden">Max exposure.</span>
      </p>

      <div className="my-3 sm:my-5 h-px bg-white/15" />

      <ul className="space-y-1.5 sm:space-y-2.5 flex-1">
        {VIP_FEATURES.map((f, i) => (
          <FeatureItem key={i} {...f} tone="gold" dark />
        ))}
      </ul>

      <button
        type="button"
        onClick={onCta}
        disabled={loading || disabled}
        data-testid="pricing-cta-vip"
        className="mt-3 sm:mt-6 group inline-flex items-center justify-center gap-1 sm:gap-2 w-full bg-[#F5C443] hover:bg-[#FFD661] text-[#0A0F0D] font-barlow font-black uppercase tracking-[0.12em] sm:tracking-[0.2em] text-[10px] sm:text-sm py-2 sm:py-3.5 transition-all disabled:opacity-60 disabled:cursor-wait"
      >
        {loading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <>Go VIP <ArrowRight className="hidden sm:inline w-4 h-4 transition-transform group-hover:translate-x-0.5" /></>}
      </button>
    </div>
  );
}

/* ============================================================ */
/*  Feature row                                                  */
/* ============================================================ */
function FeatureItem({ label, included, tone = "forest", dark = false }) {
  const tones = {
    forest: { bg: "bg-forest", off: "bg-gray-border" },
    lime: { bg: "bg-[#A5DD5F]", off: "bg-white/15" },
    gold: { bg: "bg-[#F5C443]", off: "bg-white/15" },
  };
  const t = tones[tone] || tones.forest;
  const textCls = dark
    ? included ? "text-white" : "text-white/55"
    : included ? "text-ink" : "text-ink/45";

  return (
    <li className="flex items-start gap-1 sm:gap-2.5">
      <span
        aria-hidden
        className={`shrink-0 mt-0.5 w-3 h-3 sm:w-5 sm:h-5 rounded-full flex items-center justify-center ${included ? t.bg : t.off}`}
      >
        {included
          ? <Check className={`w-2 h-2 sm:w-3 sm:h-3 ${dark ? "text-[#0F3A22]" : "text-white"}`} strokeWidth={3.5} />
          : <X className={`w-2 h-2 sm:w-3 sm:h-3 ${dark ? "text-white/60" : "text-ink/55"}`} strokeWidth={3} />
        }
      </span>
      <span className={`text-[9px] sm:text-[13px] leading-tight sm:leading-snug ${textCls}`}>
        {label}
      </span>
    </li>
  );
}

/* ============================================================ */
/*  Trust row                                                    */
/* ============================================================ */
function TrustRow() {
  const items = [
    { icon: Shield, title: "Trusted by thousands of players", body: "Join a growing community of ambitious footballers worldwide." },
    { icon: Users, title: "Connected with top scouts worldwide", body: "Your profile and videos seen by professional scouts." },
    { icon: BarChart3, title: "Data-driven performance insights", body: "Advanced AI analysis to help you improve and stand out." },
    { icon: Lock, title: "Secure & private your data", body: "Your data is encrypted and never shared. Always protected." },
  ];
  return (
    <div
      data-testid="pricing-trust-row"
      className="mt-12 md:mt-14 max-w-6xl mx-auto grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6 bg-cream-card border border-gray-border px-5 md:px-8 py-7 md:py-8"
    >
      {items.map(({ icon: Icon, title, body }, i) => (
        <div key={i} className="flex flex-col">
          <Icon className="w-7 h-7 text-forest mb-3" strokeWidth={1.8} />
          <h4 className="font-barlow font-black uppercase text-[11px] tracking-[0.18em] text-ink leading-tight">
            {title}
          </h4>
          <p className="mt-2 text-xs text-ink/65 leading-relaxed">{body}</p>
        </div>
      ))}
    </div>
  );
}

/* ============================================================ */
/*  Journey strip                                                */
/* ============================================================ */
function JourneyStrip({ onCta }) {
  return (
    <div
      data-testid="pricing-journey-strip"
      className="mt-8 md:mt-10 max-w-6xl mx-auto relative bg-[#0F3A22] text-white px-6 md:px-10 py-8 md:py-10 overflow-hidden border border-forest/40"
    >
      {/* faint stadium vignette using radial gradient — no external image */}
      <div
        aria-hidden
        className="absolute inset-0 opacity-30"
        style={{
          background:
            "radial-gradient(ellipse at right, rgba(204,255,0,0.18) 0%, transparent 55%), radial-gradient(circle at 80% 50%, rgba(255,255,255,0.06) 0%, transparent 50%)",
        }}
      />
      <div className="relative max-w-2xl">
        <h3 className="font-barlow font-black uppercase tracking-tighter text-2xl md:text-3xl leading-[0.95]">
          Your journey.<br /><span className="text-[#CCFF00]">Our mission.</span>
        </h3>
        <p className="mt-3 text-sm md:text-base text-white/75 leading-relaxed">
          We&apos;re here to help you get discovered, grow your skills and reach
          your full potential. The next level is closer than you think.
        </p>
        <button
          type="button"
          onClick={onCta}
          data-testid="pricing-journey-cta"
          className="group inline-flex items-center justify-center gap-2 mt-5 px-6 py-3 bg-transparent border-2 border-[#CCFF00] text-[#CCFF00] hover:bg-[#CCFF00] hover:text-[#0F3A22] font-barlow font-black uppercase tracking-[0.2em] text-sm transition-all"
        >
          Upload your video
          <ArrowRight className="w-4 h-4 transition-transform group-hover:translate-x-0.5" />
        </button>
      </div>
    </div>
  );
}

/* ============================================================ */
/*  Payment footer                                               */
/* ============================================================ */
function PaymentFooter() {
  return (
    <div
      data-testid="pricing-payment-footer"
      className="mt-8 max-w-6xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-4 px-5 py-4 bg-cream-card border border-gray-border"
    >
      <div className="flex items-center gap-2.5">
        <Lock className="w-4 h-4 text-forest" />
        <div className="leading-tight">
          <div className="text-[11px] uppercase tracking-[0.18em] font-black text-ink">
            No credit card required to start
          </div>
          <div className="text-[11px] text-ink/60">Start free. Upgrade anytime.</div>
        </div>
      </div>
      <div className="flex items-center gap-4 text-ink/65 text-[12px] font-bold">
        <span className="inline-flex items-center gap-1.5">
          {/* Apple */}
          <svg viewBox="0 0 24 24" className="w-4 h-4" fill="currentColor" aria-hidden>
            <path d="M16.365 1.43c.073 1.115-.376 2.183-1.057 2.961-.731.847-1.94 1.5-3.118 1.41-.097-1.064.45-2.18 1.117-2.886.74-.78 2.005-1.4 3.058-1.486zM20.5 17.5c-.55 1.25-.8 1.81-1.5 2.92-.98 1.55-2.36 3.47-4.07 3.49-1.52.02-1.91-1-3.97-1-2.06 0-2.49 1-3.97 1.02-1.65.06-2.91-1.67-3.89-3.22C.96 17.49.07 12.94 1.86 9.9c.99-1.65 2.77-2.69 4.7-2.72 1.48-.03 2.88 1 3.97 1 1.09 0 2.79-1.23 4.7-1.05.79.03 3.01.32 4.44 2.41-.12.07-2.65 1.55-2.62 4.62.04 3.68 3.23 4.9 3.27 4.91z" />
          </svg>
          Apple Pay
        </span>
        <span className="inline-flex items-center gap-1.5">
          {/* Google */}
          <svg viewBox="0 0 24 24" className="w-4 h-4" aria-hidden>
            <path fill="#4285F4" d="M12 11v2.8h6.5c-.3 1.6-2 4.6-6.5 4.6-3.9 0-7-3.2-7-7.2s3.1-7.2 7-7.2c2.2 0 3.7.9 4.6 1.7l3.1-3C17.8 1.3 15.2.2 12 .2 5.9.2.9 5.2.9 11.3S5.9 22.4 12 22.4c6.9 0 11.4-4.8 11.4-11.6 0-.8-.1-1.4-.2-1.9H12z"/>
          </svg>
          Google Pay
        </span>
        <span className="inline-flex items-center gap-1.5">
          <CreditCard className="w-4 h-4" />
          Card
        </span>
      </div>
    </div>
  );
}
