/**
 * LandingSections.jsx — Premium layout sections for LandingMinimal (v2).
 *
 * v2 changes (Feb 2026):
 *  - Tighter section vertical rhythm (py-12 md:py-16)
 *  - Custom Nano-Banana imagery in HowItWorks + WhatsInside
 *  - Elegant graphic flourishes (chalk lines, corner brackets, vol numerals)
 *  - Replaces generic Lucide icons inside step cards with photographic mini-tiles
 *  - Adds a cinematic full-width image strip between WhatsInside & Pricing
 *
 * Palette stays cream-base / forest / volt — NO new colours.
 *
 *  TrustStrip        — 4 quick stats under the hero
 *  HowItWorks        — 3-step pipeline with image tiles
 *  WhatsInside       — 4-feature grid with subtle photographic flair
 *  ImageStrip        — Full-width cinematic break with overlay headline
 *  SocialProof       — Parent testimonial + player portrait
 *  FinalCta          — Bottom conversion strip
 */
import React from "react";
import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import {
  ArrowRight,
  ShieldCheck,
  Activity,
  Trophy,
  Users,
  Clock,
  Target,
  Quote,
  PlayCircle,
} from "lucide-react";

const ASSET_BASE = process.env.REACT_APP_BACKEND_URL;
const IMG = (name) => `${ASSET_BASE}/api/static/landing/${name}`;

/* ────────────────────────────────────────────────────────────────────── */
/*  Generic section wrapper — tighter vertical rhythm than v1, optional   */
/*  eyebrow + heading + sub.                                              */
/* ────────────────────────────────────────────────────────────────────── */
function Section({ id, eyebrow, headline, headlineAccent, sub, children, dark = false, tight = false, className = "" }) {
  const padY = tight ? "py-10 md:py-14" : "py-12 md:py-16";
  return (
    <section
      id={id}
      data-testid={id}
      className={`relative ${dark ? "bg-ink text-cream-base" : "bg-cream-base text-ink"} border-b border-gray-border px-6 md:px-10 ${padY} ${className}`}
    >
      <div className="max-w-6xl mx-auto">
        {(eyebrow || headline) && (
          <header className="mb-8 md:mb-12 text-center">
            {eyebrow && (
              <div className="inline-flex items-center gap-2.5 mb-3">
                <span aria-hidden className="relative flex items-center justify-center w-2 h-2 shrink-0">
                  <span className="absolute inset-0 rounded-full bg-volt animate-ping opacity-75" />
                  <span className="relative rounded-full w-1.5 h-1.5 bg-volt" />
                </span>
                <span className={`${dark ? "text-volt" : "text-forest"} text-[10px] md:text-[11px] uppercase tracking-[0.28em] font-bold`}>
                  {eyebrow}
                </span>
                <span aria-hidden className={`h-px w-8 ${dark ? "bg-volt/40" : "bg-forest/35"}`} />
              </div>
            )}
            {headline && (
              <h2 className={`font-barlow font-black uppercase tracking-tighter text-3xl md:text-5xl lg:text-6xl leading-[0.92] ${dark ? "text-cream-base" : "text-ink"}`}>
                {headline}{" "}
                {headlineAccent && <span className={dark ? "text-volt" : "text-forest"}>{headlineAccent}</span>}
              </h2>
            )}
            {sub && (
              <p className={`mt-4 text-base md:text-lg ${dark ? "text-cream-base/65" : "text-ink/65"} max-w-2xl mx-auto leading-relaxed`}>
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
/*  TrustStrip — Sits directly under hero. Cream-card body. Four          */
/*  compact stat tiles with hairline vertical separators (premium feel).  */
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
      className="relative bg-cream-card border-b border-gray-border px-6 md:px-10 py-5 md:py-7"
    >
      <div className="max-w-6xl mx-auto grid grid-cols-2 md:grid-cols-4 gap-x-6 gap-y-4 md:gap-x-0">
        {items.map((it, idx) => {
          const Icon = it.icon;
          return (
            <motion.div
              key={it.label}
              initial={{ opacity: 0, y: 6 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: "-40px" }}
              transition={{ duration: 0.4, delay: idx * 0.06 }}
              className={`flex items-center gap-3 md:gap-4 md:px-6 ${idx > 0 ? "md:border-l md:border-forest/15" : ""}`}
            >
              <span className="shrink-0 w-9 h-9 md:w-10 md:h-10 bg-forest/8 border border-forest/15 flex items-center justify-center">
                <Icon className="w-4 h-4 md:w-5 md:h-5 text-forest" strokeWidth={1.9} aria-hidden="true" />
              </span>
              <div className="min-w-0">
                <div className="font-barlow font-black text-2xl md:text-3xl uppercase tracking-tight leading-none text-ink">
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
/*  HowItWorks — 3 step cards. Each card now has a Nano Banana mini-tile  */
/*  (16:9) at the top showing a real photographic action, with a giant    */
/*  "01 / 02 / 03" numeral bottom-right. Premium product-walkthrough feel. */
/* ────────────────────────────────────────────────────────────────────── */
export function HowItWorks() {
  const steps = [
    {
      n: "01",
      img: IMG("step-upload.png"),
      title: "Upload your video",
      body: "30 seconds to 5 minutes of match, training or freestyle. Phone footage works perfectly — wider shots are best.",
      eyebrow: "Step 01 · upload",
    },
    {
      n: "02",
      img: IMG("step-mark.png"),
      title: "Mark your player",
      body: "Tap your player on 10 frames so ScoutMe Pro Intelligence locks onto them. No guessing, no wrong player.",
      eyebrow: "Step 02 · mark",
    },
    {
      n: "03",
      img: IMG("step-report.png"),
      title: "Get the scout report",
      body: "Free preview in seconds. Unlock the full 4-pillar premium report — Technical, Tactical, Physical, Mentality — in 48 hours.",
      eyebrow: "Step 03 · report",
    },
  ];
  return (
    <Section
      id="how-it-works-walkthrough"
      eyebrow="How it works"
      headline="Three steps."
      headlineAccent="No fluff."
      sub="From phone-footage to a real scout report in under five minutes of your time."
      tight
    >
      <div className="relative grid grid-cols-1 md:grid-cols-3 gap-4 md:gap-5">
        {/* Vertical timeline line — only visible on mobile (stacked layout) */}
        <span
          aria-hidden
          className="md:hidden absolute left-7 top-12 bottom-12 w-[2px] bg-gradient-to-b from-forest via-forest/30 to-forest"
        />
        {steps.map((s, idx) => (
          <motion.div
            key={s.n}
            initial={{ opacity: 0, y: 14 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, margin: "-60px" }}
            transition={{ duration: 0.5, delay: idx * 0.08 }}
            data-testid={`how-step-${s.n}`}
            className="group relative bg-cream-card border border-gray-border overflow-hidden hover:border-forest/40 hover:-translate-y-0.5 transition-all duration-300 md:ml-0 ml-0"
          >
            {/* Mobile step circle marker — sits on the vertical timeline */}
            <span
              aria-hidden
              className="md:hidden absolute top-4 left-4 z-10 w-7 h-7 rounded-full bg-forest text-white border-2 border-cream-base flex items-center justify-center font-barlow font-black text-[11px]"
            >
              {s.n}
            </span>

            {/* Image tile (16:10 ratio) */}
            <div className="relative aspect-[16/10] bg-ink overflow-hidden">
              <img
                src={s.img}
                alt={s.title}
                loading="lazy"
                onError={(e) => {
                  e.currentTarget.style.display = "none";
                }}
                className="absolute inset-0 w-full h-full object-cover group-hover:scale-[1.03] transition-transform duration-700"
              />
              {/* Forest tint overlay for cohesion */}
              <div aria-hidden className="absolute inset-0 bg-gradient-to-t from-forest/30 via-transparent to-transparent" />
              {/* Eyebrow chip */}
              <span className="absolute top-3 right-3 md:right-auto md:left-3 bg-volt text-ink text-[9px] uppercase tracking-[0.22em] font-black px-2 py-1">
                {s.eyebrow}
              </span>
              {/* Giant numeral, bottom right (desktop only — mobile uses the timeline dot) */}
              <span
                aria-hidden
                className="hidden md:block absolute bottom-1 right-3 font-barlow font-black text-[88px] leading-none text-cream-base/35 select-none"
                style={{ WebkitTextStroke: "1px rgba(204,255,0,0.55)" }}
              >
                {s.n}
              </span>
            </div>
            {/* Body */}
            <div className="p-5 md:p-6">
              <h3 className="font-barlow font-black uppercase tracking-tight text-xl md:text-2xl text-ink leading-tight">
                {s.title}
              </h3>
              <p className="mt-2.5 text-sm text-ink/65 leading-relaxed">{s.body}</p>
            </div>
          </motion.div>
        ))}
      </div>
    </Section>
  );
}

/* ────────────────────────────────────────────────────────────────────── */
/*  WhatsInside — 4-feature grid with stronger forest icon badges + tiny  */
/*  thumbnail strip on the right of each card.                            */
/* ────────────────────────────────────────────────────────────────────── */
export function WhatsInside() {
  const features = [
    {
      icon: Activity,
      title: "4-pillar scoring",
      body: "Technical · Tactical · Physical · Mentality — each scored against age-appropriate benchmarks.",
    },
    {
      icon: Target,
      title: "Pixel-perfect tracking",
      body: "Your player is locked frame-by-frame. The report describes them — not random players in the background.",
    },
    {
      icon: PlayCircle,
      title: "Timestamped moments",
      body: "Every key action gets a clickable timestamp so you can rewatch the exact moment the scout describes.",
    },
    {
      icon: Trophy,
      title: "Personal training plan",
      body: "5 prescriptive drills plus a 7, 30 and 90-day plan written specifically for your player's gaps.",
    },
  ];
  return (
    <Section
      id="what-you-get"
      eyebrow="What's inside"
      headline="A real scouting"
      headlineAccent="dossier."
      sub="Not a generic auto-summary. A structured premium report parents and academies actually use."
      tight
    >
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 md:gap-5">
        {features.map((f, idx) => {
          const Icon = f.icon;
          return (
            <motion.div
              key={f.title}
              initial={{ opacity: 0, y: 10 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: "-60px" }}
              transition={{ duration: 0.45, delay: idx * 0.06 }}
              data-testid={`feature-${idx}`}
              className="group relative bg-cream-card border border-gray-border p-5 md:p-6 hover:border-forest/40 hover:-translate-y-0.5 transition-all duration-300 flex gap-4 md:gap-5 overflow-hidden"
            >
              {/* Subtle dotted background pattern (mobile + desktop) */}
              <div
                aria-hidden
                className="absolute inset-0 opacity-[0.04] pointer-events-none"
                style={{
                  backgroundImage: "radial-gradient(circle at 1px 1px, #1F4F2F 1px, transparent 0)",
                  backgroundSize: "16px 16px",
                }}
              />
              {/* Vertical accent strip — visible on every breakpoint */}
              <span aria-hidden className="absolute left-0 top-0 bottom-0 w-[3px] bg-forest/10 group-hover:bg-forest transition-colors" />
              {/* Top-right corner bracket */}
              <span aria-hidden className="absolute top-2 right-2 w-3 h-3 border-r border-t border-forest/30 group-hover:border-forest transition-colors" />

              <span className="relative shrink-0 w-12 h-12 bg-forest text-white border border-forest flex items-center justify-center">
                <Icon className="w-5 h-5" strokeWidth={2.1} />
              </span>
              <div className="relative min-w-0 flex-1">
                <div className="flex items-baseline gap-3">
                  <h3 className="font-barlow font-black uppercase tracking-tight text-lg md:text-xl text-ink leading-tight">
                    {f.title}
                  </h3>
                  <span aria-hidden className="flex-1 h-px bg-forest/15" />
                </div>
                <p className="mt-1.5 text-sm md:text-[15px] text-ink/65 leading-relaxed">{f.body}</p>
              </div>
            </motion.div>
          );
        })}
      </div>
    </Section>
  );
}

/* ────────────────────────────────────────────────────────────────────── */
/*  ImageStrip — Full-width cinematic break between WhatsInside and       */
/*  Pricing. Big wide Nano Banana image + overlay headline. Adds visual   */
/*  punch + breaks the cream monotony.                                    */
/* ────────────────────────────────────────────────────────────────────── */
export function ImageStrip() {
  return (
    <section
      id="image-strip"
      data-testid="image-strip"
      className="relative bg-ink overflow-hidden border-b border-gray-border"
    >
      {/* Mobile: 5:6 portrait aspect so the headline gets real estate.
          Desktop: 21:8 cinematic strip. */}
      <div className="relative aspect-[5/6] md:aspect-[21/8] w-full">
        <picture>
          {/* Square crop optimised for mobile */}
          <source media="(max-width: 767px)" srcSet={IMG("imagestrip-mobile.png")} />
          <img
            src={IMG("feature-strip.png")}
            alt="Training session at dusk"
            loading="lazy"
            onError={(e) => {
              e.currentTarget.style.display = "none";
            }}
            className="absolute inset-0 w-full h-full object-cover"
          />
        </picture>
        {/* Mobile uses a bottom-to-top dark scrim so text is at the bottom; desktop keeps the left-to-right scrim */}
        <div aria-hidden className="absolute inset-0 bg-gradient-to-t md:bg-gradient-to-r from-ink/90 md:from-ink/85 via-ink/35 md:via-ink/40 to-transparent" />
        {/* Mobile decorative corner brackets */}
        <span aria-hidden className="md:hidden absolute top-4 left-4 w-5 h-5 border-l-2 border-t-2 border-volt" />
        <span aria-hidden className="md:hidden absolute top-4 right-4 w-5 h-5 border-r-2 border-t-2 border-volt" />

        <div className="absolute inset-0 flex items-end md:items-center px-6 pb-8 md:pb-0 md:px-12">
          <div className="max-w-2xl text-center md:text-left mx-auto md:mx-0">
            <div className="inline-flex items-center gap-2 mb-3 justify-center md:justify-start">
              <span className="w-6 md:w-8 h-px bg-volt" />
              <span className="text-volt text-[10px] md:text-[11px] uppercase tracking-[0.28em] font-bold">
                Real scouts · Real evidence
              </span>
              <span className="md:hidden w-6 h-px bg-volt" />
            </div>
            <h3 className="font-barlow font-black uppercase tracking-tighter text-4xl md:text-6xl text-cream-base leading-[0.9]">
              Built for the<br />
              <span className="text-volt">next level.</span>
            </h3>
            <p className="mt-4 text-cream-base/75 text-sm md:text-base max-w-md mx-auto md:mx-0 leading-relaxed">
              ScoutMe Pro Intelligence reviews every frame &mdash; then a real scout signs off on every premium report.
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}

/* ────────────────────────────────────────────────────────────────────── */
/*  SocialProof — Single high-conviction testimonial card.                */
/* ────────────────────────────────────────────────────────────────────── */
export function SocialProof() {
  return (
    <Section
      id="social-proof"
      eyebrow="Trusted by parents"
      headline="Honest feedback that"
      headlineAccent="moves players forward."
      tight
    >
      <div className="grid grid-cols-1 md:grid-cols-5 gap-6 md:gap-8 items-stretch">
        {/* Quote card — spans 3 cols */}
        <div className="md:col-span-3 bg-cream-card border border-gray-border p-7 md:p-10 flex flex-col relative">
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
            src={IMG("social-proof-player.png")}
            alt="Youth football player"
            loading="lazy"
            onError={(e) => {
              e.currentTarget.style.display = "none";
            }}
            className="absolute inset-0 w-full h-full object-cover"
          />
          <div aria-hidden className="absolute inset-0 bg-gradient-to-t from-ink/55 via-transparent to-transparent" />
          {/* Corner brackets */}
          <span aria-hidden className="absolute top-3 left-3 w-4 h-4 border-l-2 border-t-2 border-volt" />
          <span aria-hidden className="absolute top-3 right-3 w-4 h-4 border-r-2 border-t-2 border-volt" />
          <span aria-hidden className="absolute bottom-3 left-3 w-4 h-4 border-l-2 border-b-2 border-volt" />
          <span aria-hidden className="absolute bottom-3 right-3 w-4 h-4 border-r-2 border-b-2 border-volt" />
        </div>
      </div>
    </Section>
  );
}

/* ────────────────────────────────────────────────────────────────────── */
/*  FinalCta — Final conversion strip (dark ink panel).                   */
/* ────────────────────────────────────────────────────────────────────── */
export function FinalCta({ isLoggedIn }) {
  const target = isLoggedIn ? "/upload" : "/signup?next=/upload";
  return (
    <section
      id="final-cta"
      data-testid="final-cta"
      className="relative bg-ink text-cream-base px-6 md:px-10 py-14 md:py-20 overflow-hidden"
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
        <div className="inline-flex items-center gap-2.5 mb-4">
          <span aria-hidden className="relative flex items-center justify-center w-2 h-2 shrink-0">
            <span className="absolute inset-0 rounded-full bg-volt animate-ping opacity-75" />
            <span className="relative rounded-full w-1.5 h-1.5 bg-volt" />
          </span>
          <span className="text-volt text-[10px] md:text-[11px] uppercase tracking-[0.28em] font-bold">
            Free preview · No card to start
          </span>
        </div>
        <h2 className="font-barlow font-black uppercase tracking-tighter text-4xl md:text-6xl lg:text-7xl leading-[0.9]">
          Your next level is one<br />
          <span className="text-volt">upload away.</span>
        </h2>
        <p className="mt-4 text-cream-base/70 max-w-xl mx-auto text-base md:text-lg leading-relaxed">
          Get an honest professional read in 48 hours. Built for ambitious U7–U21 players.
        </p>
        <Link
          to={target}
          data-testid="final-cta-button"
          className="mt-8 inline-flex items-center justify-center gap-3 bg-volt hover:bg-[#D8FF33] text-ink font-barlow font-black uppercase tracking-[0.18em] text-base md:text-lg px-10 md:px-14 py-5 md:py-6 transition-colors"
        >
          Upload your video
          <ArrowRight className="w-5 h-5" />
        </Link>
        <div className="mt-5 flex items-center justify-center gap-5 text-[10px] uppercase tracking-[0.18em] font-bold text-cream-base/55">
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
