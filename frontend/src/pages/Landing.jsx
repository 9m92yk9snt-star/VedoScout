import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import Navigation from "@/components/Navigation";
import api from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import {
  ArrowRight, Upload, Zap, ShieldCheck, FileText, Star, Brain, Target,
} from "lucide-react";

const fadeUp = {
  hidden: { opacity: 0, y: 18 },
  visible: (i = 0) => ({ opacity: 1, y: 0, transition: { delay: i * 0.06, duration: 0.5, ease: "easeOut" } }),
};

export default function Landing() {
  const [price, setPrice] = useState(399);
  const { user } = useAuth();

  useEffect(() => {
    api.get("/settings/price").then(({ data }) => setPrice(data.price_dkk)).catch(() => {});
  }, []);

  // Where the CTAs route to
  const startHref = user ? "/upload" : "/signup";
  const startLabel = user ? "Upload your video" : "Get started";

  return (
    <div className="min-h-screen bg-deepnavy text-white relative overflow-hidden">
      <Navigation transparent />

      {/* ============ HERO — focused, action-first ============ */}
      <section
        data-testid="hero-section"
        className="relative min-h-screen flex items-center pt-24 pb-12"
      >
        {/* Background image with overlay */}
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

              {/* Action CTAs */}
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

              {/* Trust strip — compact */}
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
            </div>

            {/* Right — compact "what you get" card */}
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

      {/* ============ Compact disclaimer + footer in one band ============ */}
      <footer className="relative z-10 border-t border-white/10 bg-deepnavy">
        <div className="max-w-7xl mx-auto px-6 md:px-10 py-6 flex flex-col md:flex-row items-center justify-between gap-3">
          <p className="text-[11px] text-white/45 uppercase tracking-[0.18em] font-bold text-center md:text-left">
            Independent development feedback. Does not guarantee trials, contracts or academy selection.
          </p>
          <div className="flex items-center gap-3">
            <div className="w-6 h-6 bg-volt flex items-center justify-center">
              <span className="text-deepnavy font-barlow font-black text-xs leading-none">E</span>
            </div>
            <span className="font-barlow font-black uppercase tracking-tight text-sm">Elite Scout</span>
          </div>
        </div>
      </footer>
    </div>
  );
}
