// NewsletterSignup — warm weekly-letter signup, stored via /api/newsletter/subscribe.
import React, { useState } from "react";
import { Mail, Check, Loader2, ArrowRight } from "lucide-react";
import api from "@/lib/api";

const LIME = "#ccff00";

export default function NewsletterSignup({ source = "blog" }) {
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState("");

  const submit = async (e) => {
    e.preventDefault();
    if (!email.trim()) return;
    setBusy(true);
    setError("");
    try {
      await api.post("/newsletter/subscribe", { email: email.trim(), source });
      setDone(true);
    } catch (err) {
      setError(err?.response?.data?.detail || "Something went wrong — please try again.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <section
      data-testid="newsletter-signup"
      className="relative overflow-hidden rounded-2xl bg-forest text-cream-card px-6 py-8 md:px-10 md:py-10"
    >
      <div aria-hidden className="absolute -top-20 -right-16 w-64 h-64 rounded-full pointer-events-none opacity-20 blur-3xl" style={{ background: LIME }} />
      <div className="relative max-w-2xl">
        <div className="inline-flex items-center gap-2">
          <Mail className="w-4 h-4" style={{ color: LIME }} />
          <span className="text-[10px] uppercase tracking-[0.26em] font-bold" style={{ color: LIME }}>The ScoutMePlay Letter</span>
        </div>
        <h3 className="font-barlow font-black uppercase text-2xl md:text-3xl tracking-tight leading-tight mt-3">
          One good football story. Every week.
        </h3>
        <p className="mt-2.5 text-cream-card/75 text-sm md:text-[15px] leading-relaxed max-w-lg">
          Training ideas, honest scouting insight and stories from families on the same journey as yours — written by people, for people.
        </p>

        {done ? (
          <div className="mt-6 flex items-center gap-3" data-testid="newsletter-success">
            <span className="w-9 h-9 rounded-full flex items-center justify-center shrink-0" style={{ background: LIME }}>
              <Check className="w-5 h-5" style={{ color: "#0A1F0F" }} />
            </span>
            <div>
              <div className="font-barlow font-black uppercase tracking-wide text-base">You&apos;re in — welcome!</div>
              <div className="text-cream-card/70 text-xs mt-0.5">Your first letter lands with the next weekly story.</div>
            </div>
          </div>
        ) : (
          <>
            <form onSubmit={submit} className="mt-6 flex flex-col sm:flex-row gap-3 max-w-md" data-testid="newsletter-form">
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="Your email address"
                data-testid="newsletter-email-input"
                className="flex-1 px-4 py-3 rounded-full bg-white/10 border border-white/20 focus:border-white/50 outline-none text-sm text-cream-card placeholder:text-cream-card/45 transition-colors"
              />
              <button
                type="submit"
                disabled={busy}
                data-testid="newsletter-submit-btn"
                className="inline-flex items-center justify-center gap-2 font-barlow font-black uppercase tracking-widest text-xs px-6 py-3 rounded-full transition-transform hover:scale-[1.03] disabled:opacity-60"
                style={{ background: LIME, color: "#0A1F0F" }}
              >
                {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <>Join free <ArrowRight className="w-3.5 h-3.5" /></>}
              </button>
            </form>
            {error && <div className="mt-2 text-xs text-red-300" data-testid="newsletter-error">{error}</div>}
            <p className="mt-3 text-[11px] text-cream-card/50 max-w-md">
              By joining you agree to receive our weekly email. Unsubscribe anytime — one click, no hard feelings.
            </p>
          </>
        )}
      </div>
    </section>
  );
}
