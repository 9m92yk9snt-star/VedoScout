/**
 * LandingSections.jsx — Premium layout sections for LandingMinimal.
 *
 * Each section uses the existing site palette (cream-base / forest / volt)
 * and the existing typography (Barlow font-black). NO new colours, NO new
 * fonts. Only layout, hierarchy and section composition were redesigned to
 * remove the "confusing / empty" feel of the previous minimal landing.
 *
 *  TrustStrip       — 4 quick stats right under the hero
 *  HowItWorks       — 3-step pipeline (Upload → Mark → Get report)
 *  WhatsInside      — 4-feature grid with icons
 *  SocialProof      — Parent / player testimonial card
 *  FinalCta         — Bottom-of-page conversion strip
 */
import React from "react";
import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import {
  ArrowRight,
  UploadCloud,
  Target,
  FileText,
  ShieldCheck,
  Activity,
  Trophy,
  Users,
  Sparkles,
  Quote,
  Clock,
} from "lucide-react";

const ASSET_BASE = process.env.REACT_APP_BACKEND_URL;

/* ────────────────────────────────────────────────────────────────────── */
/*  Section wrapper — gives every block consistent vertical rhythm and    */
/*  an optional eyebrow + h2 header with the existing accent style.       */
/* ────────────────────────────────────────────────────────────────────── */
function Section({ id, eyebrow, headline, headlineAccent, sub, children, dark = false, className = "" }) {
  return (
    <section
      id={id}
      data-testid={id}
      className={`relative ${dark ? "bg-ink text-cream-base" : "bg-cream-base text-ink"} border-b border-gray-border px-6 md:px-10 py-16 md:py-24 ${className}`}
    >
      <div className="max-w-6xl mx-auto">
        {(eyebrow || headline) && (
          <header className="mb-10 md:mb-14 text-center">
            {eyebrow && (
              <div className="inline-flex items-center gap-2.5 mb-4">
                <span aria-hidden className="relative flex items-center justify-center w-2 h-2 shrink-0">
                  <span className="absolute inset-0 rounded-full bg-volt animate-ping opacity-75" />
                  <span className="relative rounded-full w-1.5 h-1.5 bg-volt" />
                </span>
                <span className={`${dark ? "text-volt" : "text-forest"} text-[10px] uppercase tracking-[0.28em] font-bold`}>
                  {eyebrow}
                </span>
                <span aria-hidden className={`h-px w-8 ${dark ? "bg-volt/40" : "bg-forest/35"}`} />
              </div>
            )}
            {headline && (
              <h2 className={`font-barlow font-black uppercase tracking-tighter text-3xl md:text-5xl leading-[0.95] ${dark ? "text-cream-base" : "text-ink"}`}>
                {headline}{" "}
                {headlineAccent && <span className={dark ? "text-volt" : "text-forest"}>{headlineAccent}</span>}
              </h2>
            )}
            {sub && (
              <p className={`mt-4 text-sm md:text-base ${dark ? "text-cream-base/65" : "text-ink/65"} max-w-xl mx-auto`}>
                {sub}
              </p>
            )}
          </header>
        )}
        {children}
      </div>
    </section>
  );
}

/* ────────────────────────────────────────────────────────────────────── */
/*  TrustStrip — Sits directly under the hero. Four compact stat tiles    */
/*  that establish credibility BEFORE the user is asked to look at price. */
/* ────────────────────────────────────────────────────────────────────── */
export function TrustStrip() {
  const items = [
    { value: "48h", label: "Report delivery", icon: Clock },
    { value: "U7–U21", label: "Age coverage", icon: Users },
    { value: "10-tap", label: "Marking workflow", icon: Target },
    { value: "Pro", label: "Scout Intelligence", icon: ShieldCheck },
  ];
  return (
    <section
      id="trust-strip"
      data-testid="trust-strip"
      className="relative bg-cream-card border-b border-gray-border px-6 md:px-10 py-6 md:py-8"
    >
      <div className="max-w-6xl mx-auto grid grid-cols-2 md:grid-cols-4 gap-4 md:gap-8">
        {items.map((it, idx) => {
          const Icon = it.icon;
          return (
            <motion.div
              key={it.label}
              initial={{ opacity: 0, y: 8 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: "-50px" }}
              transition={{ duration: 0.4, delay: idx * 0.06 }}
              className="flex items-center gap-3 md:gap-4"
            >
              <span className="shrink-0 w-9 h-9 md:w-10 md:h-10 bg-forest/8 border border-forest/15 flex items-center justify-center">
                <Icon className="w-4 h-4 md:w-5 md:h-5 text-forest" strokeWidth={1.9} aria-hidden="true" />
              </span>
              <div className="min-w-0">
                <div className="font-barlow font-black text-xl md:text-2xl uppercase tracking-tight leading-none text-ink">
                  {it.value}
                </div>
                <div className="mt-1 text-[10px] md:text-[11px] uppercase tracking-[0.18em] font-bold text-ink/55 truncate">
                  {it.label}
                </div>
              </div>
            </motion.div>
          );
        })}
      </div>
    </section>
  );
}

/* ────────────────────────────────────────────────────────────────────── */
/*  HowItWorks — Three-step pipeline using existing forest accent.        */
/*  Replaces the "user lands on hero then immediately sees pricing"       */
/*  confusion with an obvious value walkthrough.                          */
/* ────────────────────────────────────────────────────────────────────── */
export function HowItWorks() {
  const steps = [
    {
      n: "01",
      icon: UploadCloud,
      title: "Upload your video",
      body: "30 seconds to 5 minutes of match, training or freestyle. Phone footage works perfectly — wider shots are best.",
    },
    {
      n: "02",
      icon: Target,
      title: "Mark your player",
      body: "Tap your player on 10 frames so Pro Scout Intelligence locks onto them. No AI guessing, no wrong player in the report.",
    },
    {
      n: "03",
      icon: FileText,
      title: "Get the scout report",
      body: "Free preview in seconds. Unlock the full 4-pillar premium report — Technical, Tactical, Physical, Mentality — in 48 hours.",
    },
  ];
  return (
    <Section
      id="how-it-works-walkthrough"
      eyebrow="How it works"
      headline="Three steps."
      headlineAccent="No fluff."
      sub="From phone-footage to a real scout report in under five minutes of your time."
    >
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 md:gap-6">
        {steps.map((s, idx) => {
          const Icon = s.icon;
          return (
            <motion.div
              key={s.n}
              initial={{ opacity: 0, y: 12 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: "-60px" }}
              transition={{ duration: 0.45, delay: idx * 0.08 }}
              data-testid={`how-step-${s.n}`}
              className="group relative bg-cream-card border border-gray-border p-6 md:p-8 hover:border-forest/40 hover:-translate-y-0.5 transition-all duration-300"
            >
              <span className="absolute top-5 right-5 font-barlow font-black text-5xl text-forest/10 leading-none">
                {s.n}
              </span>
              <span className="inline-flex w-11 h-11 bg-forest text-white items-center justify-center mb-5">
                <Icon className="w-5 h-5" strokeWidth={2} />
              </span>
              <h3 className="font-barlow font-black uppercase tracking-tight text-xl md:text-2xl text-ink leading-tight">
                {s.title}
              </h3>
              <p className="mt-3 text-sm text-ink/65 leading-relaxed">{s.body}</p>
            </motion.div>
          );
        })}
      </div>
    </Section>
  );
}

/* ────────────────────────────────────────────────────────────────────── */
/*  WhatsInside — 4-feature grid. Shows the user EXACTLY what they get    */
/*  in the report before they reach the pricing table. Big driver of      */
/*  comprehension + conversion.                                           */
/* ────────────────────────────────────────────────────────────────────── */
export function WhatsInside() {
  const features = [
    {
      icon: Activity,
      title: "4-pillar score",
      body: "Technical · Tactical · Physical · Mentality — each scored against age-appropriate benchmarks.",
    },
    {
      icon: Target,
      title: "Pixel-perfect tracking",
      body: "Your player is locked frame-by-frame. The report describes them — not random players in the background.",
    },
    {
      icon: FileText,
      title: "Timestamped moments",
      body: "Every key action gets a clickable timestamp so you can rewatch the exact moment the scout describes.",
    },
    {
      icon: Trophy,
      title: "Personal training plan",
      body: "5 prescriptive drills plus a 7-day, 30-day and 90-day plan written specifically for your player's gaps.",
    },
  ];
  return (
    <Section
      id="what-you-get"
      eyebrow="What's inside"
      headline="A real scouting"
      headlineAccent="dossier."
      sub="Not a generic AI summary. A structured premium report parents and academies actually use."
    >
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 md:gap-6">
        {features.map((f, idx) => {
          const Icon = f.icon;
          return (
            <motion.div
              key={f.title}
              initial={{ opacity: 0, y: 12 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: "-60px" }}
              transition={{ duration: 0.45, delay: idx * 0.06 }}
              data-testid={`feature-${idx}`}
              className="group bg-cream-card border border-gray-border p-6 md:p-7 hover:border-forest/40 transition-colors flex gap-4 md:gap-5"
            >
              <span className="shrink-0 w-11 h-11 bg-forest/10 border border-forest/20 flex items-center justify-center text-forest">
                <Icon className="w-5 h-5" strokeWidth={2} />
              </span>
              <div className="min-w-0">
                <h3 className="font-barlow font-black uppercase tracking-tight text-lg md:text-xl text-ink leading-tight">
                  {f.title}
                </h3>
                <p className="mt-1.5 text-sm text-ink/65 leading-relaxed">{f.body}</p>
              </div>
            </motion.div>
          );
        })}
      </div>
    </Section>
  );
}

/* ────────────────────────────────────────────────────────────────────── */
/*  SocialProof — Single high-conviction testimonial card. Cream theme,   */
/*  forest accent, anonymous to comply with youth privacy.                */
/* ────────────────────────────────────────────────────────────────────── */
export function SocialProof() {
  const heroImage = `${ASSET_BASE}/api/static/landing/social-proof-player.png`;
  return (
    <Section
      id="social-proof"
      eyebrow="Trusted by parents"
      headline="Honest feedback that"
      headlineAccent="moves players forward."
    >
      <div className="grid grid-cols-1 md:grid-cols-5 gap-6 md:gap-10 items-stretch">
        {/* Quote card — spans 3 cols */}
        <div className="md:col-span-3 bg-cream-card border border-gray-border p-7 md:p-10 flex flex-col">
          <Quote className="w-9 h-9 text-forest/40 mb-4" strokeWidth={2.2} aria-hidden="true" />
          <p className="font-barlow text-xl md:text-2xl text-ink leading-relaxed">
            &ldquo;We&apos;ve watched a hundred of his matches. Scout<span className="bg-volt text-ink px-[3px]">Me</span>Play
            told us &mdash; in 48 hours &mdash; what his coach took two seasons to see. The training plan changed how we
            spend Saturday mornings.&rdquo;
          </p>
          <div className="mt-auto pt-7 flex items-center gap-3 border-t border-gray-border">
            <span className="w-10 h-10 bg-forest text-white font-barlow font-black flex items-center justify-center text-sm uppercase">M</span>
            <div>
              <div className="font-barlow font-black uppercase tracking-tight text-ink text-sm">Mette · parent</div>
              <div className="text-[11px] uppercase tracking-[0.18em] text-ink/50 font-bold">Denmark · son age 13</div>
            </div>
          </div>
        </div>

        {/* Portrait image — spans 2 cols */}
        <div className="md:col-span-2 relative min-h-[280px] md:min-h-0 bg-ink border border-gray-border overflow-hidden">
          <img
            src={heroImage}
            alt="Youth football player"
            onError={(e) => {
              e.currentTarget.style.display = "none";
            }}
            className="absolute inset-0 w-full h-full object-cover"
          />
          {/* Cream overlay to keep theme cohesion */}
          <div aria-hidden className="absolute inset-0 bg-gradient-to-t from-ink/60 via-transparent to-transparent" />
          <div className="absolute bottom-5 left-5 right-5 flex items-center gap-2">
            <Sparkles className="w-4 h-4 text-volt" />
            <span className="text-volt text-[10px] uppercase tracking-[0.22em] font-bold">
              Real reports · honest reads
            </span>
          </div>
        </div>
      </div>
    </Section>
  );
}

/* ────────────────────────────────────────────────────────────────────── */
/*  FinalCta — Final conversion strip. Dark ink panel matches the footer  */
/*  so the page has a satisfying close before site-footer renders.        */
/* ────────────────────────────────────────────────────────────────────── */
export function FinalCta({ isLoggedIn }) {
  const target = isLoggedIn ? "/upload" : "/signup?next=/upload";
  return (
    <section
      id="final-cta"
      data-testid="final-cta"
      className="relative bg-ink text-cream-base px-6 md:px-10 py-16 md:py-24 overflow-hidden"
    >
      <div
        aria-hidden
        className="absolute inset-0 opacity-[0.05] pointer-events-none"
        style={{
          backgroundImage: "radial-gradient(circle at 1px 1px, #CCFF00 1px, transparent 0)",
          backgroundSize: "32px 32px",
        }}
      />
      <div className="relative max-w-3xl mx-auto text-center">
        <div className="inline-flex items-center gap-2.5 mb-5">
          <span aria-hidden className="relative flex items-center justify-center w-2 h-2 shrink-0">
            <span className="absolute inset-0 rounded-full bg-volt animate-ping opacity-75" />
            <span className="relative rounded-full w-1.5 h-1.5 bg-volt" />
          </span>
          <span className="text-volt text-[10px] uppercase tracking-[0.28em] font-bold">
            Free preview · No card to start
          </span>
        </div>
        <h2 className="font-barlow font-black uppercase tracking-tighter text-4xl md:text-6xl leading-[0.92]">
          Your next level is one<br />
          <span className="text-volt">upload away.</span>
        </h2>
        <p className="mt-5 text-cream-base/65 max-w-xl mx-auto text-sm md:text-base">
          Get an honest professional read in 48 hours. Built for ambitious U7–U21 players.
        </p>
        <Link
          to={target}
          data-testid="final-cta-button"
          className="mt-9 inline-flex items-center justify-center gap-3 bg-volt hover:bg-[#D8FF33] text-ink font-barlow font-black uppercase tracking-[0.18em] text-base md:text-lg px-10 md:px-14 py-5 md:py-6 transition-colors"
        >
          Upload your video
          <ArrowRight className="w-5 h-5" />
        </Link>
        <div className="mt-6 flex items-center justify-center gap-5 text-[10px] uppercase tracking-[0.18em] font-bold text-cream-base/55">
          <span className="flex items-center gap-1.5"><ShieldCheck className="w-3 h-3 text-volt" /> Secure Stripe</span>
          <span className="w-1 h-1 bg-cream-base/30 rounded-full" />
          <span>Cancel anytime</span>
          <span className="w-1 h-1 bg-cream-base/30 rounded-full hidden sm:inline-block" />
          <span className="hidden sm:inline">Refund if we miss 48h</span>
        </div>
      </div>
    </section>
  );
}
