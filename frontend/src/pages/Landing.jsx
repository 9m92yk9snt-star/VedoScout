import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import Navigation from "@/components/Navigation";
import api from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import {
  ArrowRight, Upload, Zap, ShieldCheck, FileText, Star, Brain, Target,
  Activity, Heart, Eye, Trophy, Footprints, Lock,
} from "lucide-react";

const fadeUp = {
  hidden: { opacity: 0, y: 18 },
  visible: (i = 0) => ({ opacity: 1, y: 0, transition: { delay: i * 0.06, duration: 0.5, ease: "easeOut" } }),
};

const featureCards = [
  { icon: Brain, title: "AI Player Report", text: "Full written analysis of style, role and decisions." },
  { icon: Footprints, title: "Technical Analysis", text: "First touch, ball control, passing, shooting & 1v1." },
  { icon: Target, title: "Tactical Analysis", text: "Positioning, scanning, runs and game intelligence." },
  { icon: Activity, title: "Physical Analysis", text: "Acceleration, balance, agility and intensity." },
  { icon: Heart, title: "Mentality Analysis", text: "Confidence, work rate, focus and competitive edge." },
  { icon: Eye, title: "Scout View", text: "How a scout might assess this player — strengths & concerns." },
  { icon: Trophy, title: "Training Plan", text: "5 exercises, weekly focus, 30 & 90-day development." },
  { icon: FileText, title: "Premium PDF", text: "Download a clean, premium report you can share." },
];

export default function Landing() {
  const [price, setPrice] = useState(399);
  const { user } = useAuth();

  useEffect(() => {
    api.get("/settings/price").then(({ data }) => setPrice(data.price_dkk)).catch(() => {});
  }, []);

  const startHref = user ? "/upload" : "/signup";
  const startLabel = user ? "Upload your video" : "Get started";

  return (
    <div className="min-h-screen bg-deepnavy text-white relative overflow-hidden">
      <Navigation transparent />

      {/* ============ HERO — focused, single viewport ============ */}
      <section
        data-testid="hero-section"
        className="relative min-h-screen flex items-center pt-24 pb-12"
      >
        <div className="absolute inset-0 z-0">
          <img
            src="https://images.unsplash.com/photo-1706675780107-7c43cc487928?crop=entropy&cs=srgb&fm=jpg&ixid=M3w4NTYxODh8MHwxfHNlYXJjaHwyfHxzb2NjZXIlMjBwbGF5ZXIlMjBzdGFkaXVtJTIwbGlnaHRzJTIwbmlnaHR8ZW58MHx8fHwxNzgwNDE1ODUwfDA&ixlib=rb-4.1.0&q=85"
            alt="Stadium under lights"
            className="w-full h-full object-cover opacity-45"
          />
          <div className="absolute inset-0 bg-gradient-to-br from-deepnavy/85 via-deepnavy/60 to-deepnavy" />
          <div className="absolute inset-0 scoreline-grid opacity-30" />
        </div>

        <div className="relative z-10 w-full max-w-7xl mx-auto px-6 md:px-10">
          <div className="grid lg:grid-cols-12 gap-10 lg:gap-16 items-center">
            {/* Left — copy + CTAs */}
            <div className="lg:col-span-7">
              <motion.div initial="hidden" animate="visible" variants={fadeUp} custom={0}>
                <div className="inline-flex items-center gap-2 border border-volt/30 bg-volt/10 px-4 py-2">
                  <Zap className="w-3.5 h-3.5 text-volt" />
                  <span className="text-volt text-xs uppercase tracking-[0.25em] font-bold">
                    AI-Powered Football Scouting
                  </span>
                </div>
              </motion.div>

              <motion.h1
                initial="hidden"
                animate="visible"
                variants={fadeUp}
                custom={1}
                data-testid="hero-title"
                className="mt-6 font-barlow font-black uppercase text-5xl sm:text-6xl md:text-7xl leading-[0.92] tracking-tighter"
              >
                Upload your football video.
                <span className="block text-gradient-volt mt-1">
                  Get a professional player analysis.
                </span>
              </motion.h1>

              <motion.p
                initial="hidden"
                animate="visible"
                variants={fadeUp}
                custom={2}
                className="mt-6 text-base md:text-lg text-white/70 max-w-xl leading-relaxed"
              >
                Instant AI feedback on strengths, weaknesses & a personalized development plan.
                Free preview · one-time payment unlocks the full premium report + PDF.
              </motion.p>

              <motion.div
                initial="hidden"
                animate="visible"
                variants={fadeUp}
                custom={3}
                className="mt-8 flex flex-col sm:flex-row gap-3 sm:gap-4 max-w-xl"
              >
                <Link
                  to={startHref}
                  data-testid="hero-cta-upload"
                  className="group flex-1 bg-volt hover:bg-white text-deepnavy font-barlow font-black uppercase tracking-widest text-base px-6 py-4 flex items-center justify-center gap-3 transition-colors animate-pulse-glow"
                >
                  <Upload className="w-5 h-5" />
                  {startLabel}
                  <ArrowRight className="w-5 h-5 group-hover:translate-x-1 transition-transform" />
                </Link>
                {!user && (
                  <Link
                    to="/login"
                    data-testid="hero-cta-login"
                    className="flex-1 border border-white/20 hover:border-volt hover:text-volt text-white font-barlow font-black uppercase tracking-widest text-base px-6 py-4 flex items-center justify-center gap-2 transition-colors"
                  >
                    Sign in
                  </Link>
                )}
              </motion.div>

              <motion.div
                initial="hidden"
                animate="visible"
                variants={fadeUp}
                custom={4}
                className="mt-8 flex flex-wrap items-center gap-x-6 gap-y-3 text-xs uppercase tracking-[0.18em] font-bold text-white/50"
              >
                <span className="flex items-center gap-1.5"><ShieldCheck className="w-3.5 h-3.5 text-volt" /> Secure Stripe payment</span>
                <span className="flex items-center gap-1.5"><Star className="w-3.5 h-3.5 text-volt" /> {price} DKK · one-time</span>
                <span className="flex items-center gap-1.5"><FileText className="w-3.5 h-3.5 text-volt" /> Premium PDF report</span>
              </motion.div>

              {/* Scroll hint */}
              <motion.a
                href="#what-you-get"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ delay: 0.8 }}
                className="mt-10 inline-flex items-center gap-2 text-[11px] uppercase tracking-[0.25em] font-bold text-white/40 hover:text-volt transition-colors"
              >
                Scroll to learn more
                <span className="w-8 h-px bg-current" />
              </motion.a>
            </div>

            {/* Right — 3 steps card */}
            <motion.div
              initial={{ opacity: 0, x: 24 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: 0.3, duration: 0.6, ease: "easeOut" }}
              className="lg:col-span-5"
            >
              <div className="border border-white/10 bg-surface/80 backdrop-blur-xl p-6 md:p-8">
                <div className="flex items-center justify-between mb-6">
                  <span className="text-volt text-xs uppercase tracking-[0.25em] font-bold">3 steps</span>
                  <span className="text-white/40 text-xs uppercase tracking-widest font-bold">~ 2 min</span>
                </div>

                <ol className="space-y-5">
                  {[
                    { n: "01", t: "Sign up", d: "Free account. No card required to start." },
                    { n: "02", t: "Upload video & details", d: "Highlight, match or training clip." },
                    { n: "03", t: "Get instant free preview", d: "Unlock full report for " + price + " DKK." },
                  ].map((s, i) => (
                    <li key={i} className="flex gap-4 items-start">
                      <span className="font-barlow font-black text-3xl text-volt/40 leading-none w-10 flex-shrink-0">{s.n}</span>
                      <div>
                        <div className="font-barlow font-black uppercase text-white text-lg leading-tight">{s.t}</div>
                        <div className="text-xs text-white/60 mt-0.5">{s.d}</div>
                      </div>
                    </li>
                  ))}
                </ol>

                <Link
                  to={startHref}
                  data-testid="card-cta"
                  className="mt-8 w-full bg-volt hover:bg-white text-deepnavy font-barlow font-black uppercase tracking-widest text-sm py-3 flex items-center justify-center gap-2 transition-colors"
                >
                  Start free preview
                  <ArrowRight className="w-4 h-4" />
                </Link>

                <div className="mt-5 pt-5 border-t border-white/10 grid grid-cols-3 gap-2">
                  {[
                    { i: Brain, l: "AI Report" },
                    { i: Target, l: "Scout View" },
                    { i: FileText, l: "PDF" },
                  ].map(({ i: Icon, l }, idx) => (
                    <div key={idx} className="flex flex-col items-center gap-1.5 text-center">
                      <Icon className="w-4 h-4 text-volt" strokeWidth={1.5} />
                      <span className="text-[10px] uppercase tracking-widest font-bold text-white/60">{l}</span>
                    </div>
                  ))}
                </div>
              </div>
            </motion.div>
          </div>
        </div>
      </section>

      {/* ============ WHAT YOU RECEIVE — proof of value ============ */}
      <section id="what-you-get" data-testid="what-you-get" className="relative py-24 md:py-32 border-t border-white/10">
        <div className="absolute inset-0 z-0 opacity-20">
          <img
            src="https://images.pexels.com/photos/16826135/pexels-photo-16826135.jpeg"
            alt="Pitch"
            className="w-full h-full object-cover"
          />
          <div className="absolute inset-0 bg-deepnavy/85" />
        </div>
        <div className="relative z-10 max-w-7xl mx-auto px-6 md:px-10">
          <div className="mb-16 flex flex-col md:flex-row md:items-end md:justify-between gap-6">
            <div className="max-w-3xl">
              <span className="text-volt text-xs uppercase tracking-[0.25em] font-bold">Premium Report</span>
              <h2 className="mt-4 font-barlow font-black uppercase text-4xl md:text-6xl tracking-tighter leading-[0.95]">
                Everything you receive
              </h2>
            </div>
            <p className="text-white/60 max-w-md text-sm md:text-base">
              A scout-grade breakdown across technical, tactical, physical and mental dimensions, with concrete
              development steps.
            </p>
          </div>

          <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-px bg-white/10 border border-white/10">
            {featureCards.map((f, i) => (
              <div
                key={i}
                data-testid={`feature-card-${i}`}
                className="bg-deepnavy p-6 md:p-8 hover:bg-surface hover:-translate-y-1 transition-all group cursor-default"
              >
                <f.icon className="w-8 h-8 text-volt mb-6" strokeWidth={1.5} />
                <h3 className="font-barlow font-black uppercase text-lg text-white mb-2">{f.title}</h3>
                <p className="text-xs text-white/55 leading-relaxed">{f.text}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ============ SAMPLE REPORT PREVIEW — strongest conversion ============ */}
      <section data-testid="example-report" className="relative py-24 md:py-32 border-t border-white/10">
        <div className="max-w-7xl mx-auto px-6 md:px-10">
          <div className="mb-12 max-w-3xl">
            <span className="text-volt text-xs uppercase tracking-[0.25em] font-bold">Sample Preview</span>
            <h2 className="mt-4 font-barlow font-black uppercase text-4xl md:text-6xl tracking-tighter leading-[0.95]">
              A glimpse of the report
            </h2>
            <p className="mt-4 text-white/60 max-w-xl">Free preview is unlocked. Premium sections appear blurred until purchase.</p>
          </div>

          <div className="grid lg:grid-cols-3 gap-px bg-white/10 border border-white/10">
            <div className="bg-surface p-8 lg:col-span-1">
              <span className="text-xs uppercase tracking-[0.25em] text-volt font-bold">Free preview</span>
              <h3 className="mt-3 font-barlow font-black uppercase text-3xl">Creative Attacking Midfielder</h3>
              <p className="mt-4 text-sm text-white/70 leading-relaxed">
                Press-resistant, scans well between lines. Strong left-footed passing range and timing of arrival in
                the half-spaces.
              </p>
              <div className="mt-6">
                <div className="text-xs uppercase tracking-[0.2em] text-white/40 font-bold mb-3">Top strengths</div>
                <ul className="space-y-2 text-sm text-white">
                  <li className="flex items-start gap-2"><span className="text-volt mt-1">▶</span> Vision & line-breaking passes</li>
                  <li className="flex items-start gap-2"><span className="text-volt mt-1">▶</span> Body orientation when receiving</li>
                  <li className="flex items-start gap-2"><span className="text-volt mt-1">▶</span> Calm under high pressure</li>
                </ul>
              </div>
            </div>

            {[
              { title: "Tactical Analysis", lines: ["Positioning: 8/10", "Off-ball movement: 7/10", "Scanning frequency: 9/10", "Timing of runs: 8/10"] },
              { title: "Physical & Mentality", lines: ["Acceleration: 8/10", "Balance: 7/10", "Work rate: 9/10", "Courage in duels: 8/10"] },
            ].map((card, i) => (
              <div key={i} className="bg-surface p-8 relative overflow-hidden">
                <div className="blur-locked">
                  <span className="text-xs uppercase tracking-[0.25em] text-volt font-bold">Premium</span>
                  <h3 className="mt-3 font-barlow font-black uppercase text-3xl">{card.title}</h3>
                  <ul className="mt-6 space-y-3">
                    {card.lines.map((l, j) => (
                      <li key={j} className="flex items-center justify-between text-sm">
                        <span className="text-white/80">{l.split(":")[0]}</span>
                        <span className="text-volt font-barlow font-black text-lg">{l.split(":")[1]}</span>
                      </li>
                    ))}
                  </ul>
                </div>
                <div className="absolute inset-0 bg-deepnavy/40 backdrop-blur-md flex flex-col items-center justify-center text-center p-8">
                  <Lock className="w-8 h-8 text-volt mb-4" strokeWidth={1.5} />
                  <p className="font-barlow font-black uppercase text-xl text-white">Unlock full report</p>
                  <p className="mt-2 text-xs text-white/60 max-w-[220px]">Single payment unlocks every premium section.</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ============ TRUST ============ */}
      <section id="trust" data-testid="trust-section" className="relative py-24 border-t border-white/10">
        <div className="max-w-7xl mx-auto px-6 md:px-10">
          <div className="border border-white/10 bg-surface p-8 md:p-12 flex flex-col md:flex-row gap-6 md:items-center">
            <ShieldCheck className="w-12 h-12 text-volt flex-shrink-0" strokeWidth={1.5} />
            <div>
              <h3 className="font-barlow font-black uppercase text-2xl md:text-3xl">Independent development feedback</h3>
              <p className="mt-3 text-sm text-white/70 leading-relaxed max-w-3xl">
                This platform provides independent football development feedback. It does <strong className="text-white">not</strong> guarantee trials,
                contracts or academy selection. All scores are presented as developmental guidance, not definitive
                scouting evaluations.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* ============ FINAL CTA ============ */}
      <section data-testid="final-cta" className="relative py-24 md:py-32 border-t border-white/10 overflow-hidden">
        <div className="absolute inset-0 z-0">
          <img
            src="https://images.pexels.com/photos/12616082/pexels-photo-12616082.jpeg"
            alt="Player action"
            className="w-full h-full object-cover opacity-25"
          />
          <div className="absolute inset-0 bg-gradient-to-t from-deepnavy via-deepnavy/80 to-deepnavy/60" />
        </div>
        <div className="relative z-10 max-w-5xl mx-auto px-6 md:px-10 text-center">
          <h2 className="font-barlow font-black uppercase text-5xl md:text-7xl tracking-tighter leading-[0.95]">
            Ready when you are.
            <span className="block text-volt mt-2">Start your free preview.</span>
          </h2>
          <p className="mt-6 text-white/60 max-w-2xl mx-auto">
            Upload a video, enter player details, and receive an instant AI preview. No card required to start.
          </p>
          <div className="mt-10">
            <Link
              to={startHref}
              data-testid="final-cta-btn"
              className="inline-flex items-center gap-3 bg-volt hover:bg-white text-deepnavy font-barlow font-black uppercase tracking-widest text-base px-10 py-5 transition-colors"
            >
              {startLabel}
              <ArrowRight className="w-5 h-5" />
            </Link>
          </div>
        </div>
      </section>

      {/* ============ FOOTER ============ */}
      <footer className="border-t border-white/10 py-10">
        <div className="max-w-7xl mx-auto px-6 md:px-10 flex flex-col md:flex-row justify-between gap-4 items-center">
          <div className="flex items-center gap-3">
            <div className="w-7 h-7 bg-volt flex items-center justify-center">
              <span className="text-deepnavy font-barlow font-black text-sm leading-none">E</span>
            </div>
            <span className="font-barlow font-black uppercase tracking-tight">Elite Scout</span>
          </div>
          <p className="text-xs text-white/40 uppercase tracking-[0.2em]">Independent AI player feedback. Built for development.</p>
        </div>
      </footer>
    </div>
  );
}
