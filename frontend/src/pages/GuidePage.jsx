// GuidePage — free parent guide lead magnet with email capture.
import React, { useState } from "react";
import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import { Check, Loader2, ArrowRight, BookOpen, Download } from "lucide-react";
import Navigation from "@/components/Navigation";
import SEO from "@/components/SEO";
import api from "@/lib/api";

const LIME = "#ccff00";
const BACKEND = process.env.REACT_APP_BACKEND_URL;

const MISTAKES = [
  "The car ride home — and the 60 seconds that undo a whole match",
  "Mistaking pressure for dedication (the burnout trap)",
  "Only noticing match day — the habits nobody sees",
  "Praising the wrong things (scouts watch something else entirely)",
  "The one nobody admits: your expectations, their dream",
];

export default function GuidePage() {
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState("");

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api.post("/guide/subscribe", { email: email.trim(), name: name.trim() });
      setDone(true);
    } catch (err) {
      setError(err?.response?.data?.detail || "Something went wrong — please try again.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="min-h-screen bg-cream-base text-ink">
      <SEO
        title="Free Guide — The 5 Things Every Football Parent Gets Wrong"
        description="A free, honest guide for football families. 5 mistakes almost every parent makes — each with a self-check and a fix you can use this week."
        url="/guide"
      />
      <Navigation />

      <section className="relative overflow-hidden" style={{ background: "#0C1810" }} data-testid="guide-hero">
        <div aria-hidden className="absolute -top-24 -right-24 w-96 h-96 rounded-full opacity-15 blur-3xl pointer-events-none" style={{ background: LIME }} />
        <div className="max-w-6xl mx-auto px-6 md:px-10 py-14 md:py-20 grid md:grid-cols-[1fr_360px] gap-10 md:gap-14 items-center">
          <div>
            <div className="inline-flex items-center gap-2">
              <BookOpen className="w-4 h-4" style={{ color: LIME }} />
              <span className="text-[10px] uppercase tracking-[0.26em] font-bold" style={{ color: LIME }}>Free guide for football families</span>
            </div>
            <h1 className="font-barlow font-black uppercase text-4xl sm:text-5xl lg:text-6xl text-white leading-[0.95] tracking-tight mt-4">
              The 5 things every
              <span className="block" style={{ color: LIME }}>football parent</span>
              gets wrong.
            </h1>
            <p className="mt-5 text-white/70 text-base md:text-lg leading-relaxed max-w-xl">
              Written by people who love football and care about kids. Every mistake comes with a
              self-check and a fix you can use the same day.
            </p>

            <ul className="mt-7 space-y-2.5 max-w-xl">
              {MISTAKES.map((m, i) => (
                <motion.li
                  key={i}
                  initial={{ opacity: 0, x: -12 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: 0.1 + i * 0.08 }}
                  className="flex items-start gap-3 text-white/80 text-sm md:text-[15px]"
                >
                  <span className="shrink-0 w-6 h-6 rounded-full flex items-center justify-center font-barlow font-black text-[12px] mt-0.5" style={{ background: LIME, color: "#0A1F0F" }}>
                    {i + 1}
                  </span>
                  {m}
                </motion.li>
              ))}
            </ul>

            {done ? (
              <div className="mt-8 flex items-center gap-3 max-w-xl" data-testid="guide-success">
                <span className="w-10 h-10 rounded-full flex items-center justify-center shrink-0" style={{ background: LIME }}>
                  <Check className="w-5 h-5" style={{ color: "#0A1F0F" }} />
                </span>
                <div>
                  <div className="font-barlow font-black uppercase tracking-wide text-white">Check your inbox 📬</div>
                  <div className="text-white/65 text-sm mt-0.5">
                    The guide is on its way. Can&apos;t wait?{" "}
                    <a href={`${BACKEND}/api/guide/pdf`} target="_blank" rel="noopener noreferrer" className="underline font-bold" style={{ color: LIME }} data-testid="guide-direct-download">
                      Download it right here
                    </a>
                  </div>
                </div>
              </div>
            ) : (
              <>
                <form onSubmit={submit} className="mt-8 flex flex-col sm:flex-row gap-3 max-w-xl" data-testid="guide-form">
                  <input
                    type="text"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="First name (optional)"
                    data-testid="guide-name-input"
                    className="sm:w-44 px-4 py-3.5 rounded-full bg-white/10 border border-white/20 focus:border-white/50 outline-none text-sm text-white placeholder:text-white/40 transition-colors"
                  />
                  <input
                    type="email"
                    required
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="Your email address"
                    data-testid="guide-email-input"
                    className="flex-1 px-4 py-3.5 rounded-full bg-white/10 border border-white/20 focus:border-white/50 outline-none text-sm text-white placeholder:text-white/40 transition-colors"
                  />
                  <button
                    type="submit"
                    disabled={busy}
                    data-testid="guide-submit-btn"
                    className="inline-flex items-center justify-center gap-2 font-barlow font-black uppercase tracking-widest text-xs px-7 py-3.5 rounded-full transition-transform hover:scale-[1.03] disabled:opacity-60"
                    style={{ background: LIME, color: "#0A1F0F" }}
                  >
                    {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <>Send me the guide <Download className="w-4 h-4" /></>}
                  </button>
                </form>
                {error && <div className="mt-2 text-xs text-red-300" data-testid="guide-error">{error}</div>}
                <p className="mt-3 text-[11px] text-white/40 max-w-xl">
                  100% free. We&apos;ll also send you a few helpful follow-up emails — unsubscribe anytime with one click.
                </p>
              </>
            )}
          </div>

          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, delay: 0.2 }}
            className="hidden md:block"
          >
            <img
              src={`${BACKEND}/api/static/landing/guide-book-mockup.jpg`}
              alt="The 5 Things Every Football Parent Gets Wrong — free guide"
              className="w-full rounded-2xl shadow-2xl"
              data-testid="guide-book-image"
            />
          </motion.div>
        </div>
      </section>

      <section className="max-w-3xl mx-auto px-6 md:px-10 py-14 md:py-20 text-center">
        <h2 className="font-barlow font-black uppercase text-lg md:text-lg text-ink tracking-tight">
          Why we wrote it
        </h2>
        <p className="mt-4 text-ink/70 leading-relaxed">
          We watch thousands of youth match videos. The pattern is unmistakable: the biggest difference
          between players who keep growing and players who stall isn&apos;t talent — it&apos;s what happens
          around them. This guide is everything we wish every football parent knew, in 20 honest minutes.
        </p>
        <Link
          to="/blog"
          className="inline-flex items-center gap-2 mt-8 text-[11px] uppercase tracking-[0.22em] font-bold text-forest hover:underline"
          data-testid="guide-blog-link"
        >
          More from our journal <ArrowRight className="w-3.5 h-3.5" />
        </Link>
      </section>
    </div>
  );
}
