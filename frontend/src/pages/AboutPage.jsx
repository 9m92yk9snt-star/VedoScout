import React, { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { motion } from "framer-motion";
import { toast } from "sonner";
import { ChevronLeft, ShieldCheck, Brain, Video, Trophy, Mail, Send, Loader2, CheckCircle2 } from "lucide-react";
import Navigation from "@/components/Navigation";
import SEO from "@/components/SEO";
import api from "@/lib/api";

export default function AboutPage() {
  const { hash } = useLocation();
  useEffect(() => {
    if (hash) {
      const el = document.querySelector(hash);
      if (el) {
        // small delay so DOM is fully rendered
        setTimeout(() => el.scrollIntoView({ behavior: "smooth", block: "start" }), 100);
      }
    }
  }, [hash]);

  return (
    <div className="min-h-screen bg-deepnavy text-ink">
      <SEO
        title="About ScoutMePlay — Built by people who love football"
        description="ScoutMePlay was built by scouts, parents and engineers who care about young footballers. Learn our story, methodology and what makes our reports different."
        url="/about"
      />
      <Navigation />

      <div className="max-w-4xl mx-auto px-6 md:px-10 py-14 md:py-20">
        <Link
          to="/"
          data-testid="about-back-link"
          className="inline-flex items-center gap-1.5 text-xs uppercase tracking-[0.22em] font-bold text-ink/60 hover:text-volt transition-colors"
        >
          <ChevronLeft className="w-3.5 h-3.5" />
          Back to home
        </Link>

        <motion.h1
          initial={{ opacity: 0, y: 14 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.55 }}
          className="mt-6 font-barlow font-black uppercase tracking-tighter leading-[0.95] text-4xl sm:text-5xl lg:text-6xl"
        >
          About <span className="text-volt">ScoutMePlay</span>
        </motion.h1>
        <p className="mt-3 text-sm md:text-base text-ink/65 max-w-2xl">
          Where talent gets noticed — built for the players nobody saw coming.
        </p>

        <section className="mt-12 space-y-5 text-ink/75 leading-relaxed text-base">
          <p>
              ScoutMePlay is a premium football analysis platform — a small team
            of football, technology and youth-development specialists based in Denmark. We grew up in football, watched too many
            talented kids slip through cracks for reasons that had nothing to do with their ability, and decided to build the tool
            we wish had existed when we were 14.
          </p>
          <p>
            Most young players play their best games in front of an audience of one — their dad on the sideline, recording on a
            phone. That clip is gold. Hidden in it is a tactical decision a scout would pay attention to, a body shape a coach
            would correct, a moment of bravery the kid doesn't even realise they made. ScoutMePlay turns that one shaky clip into
            a real scouting report.
          </p>
        </section>

        <section className="mt-14">
          <div className="text-[10px] uppercase tracking-[0.25em] font-bold text-volt">What we do</div>
          <h2 className="mt-3 font-barlow font-black uppercase tracking-tighter text-2xl md:text-3xl">
            Honest feedback. Real evidence. One fixed price.
          </h2>

          <div className="mt-6 grid sm:grid-cols-2 gap-4">
            {[
              {
                icon: Video,
                title: "Upload & mark",
                body: "You upload one clip and mark which player on the pitch is you. We do the rest.",
              },
              {
                icon: Brain,
                title: "Evidence-based Pro Scout Intelligence",
                body: "Our Pro Scout Intelligence watches the full clip, scores 11 dimensions of your game, and gives you timestamped evidence — not generic praise.",
              },
              {
                icon: Trophy,
                title: "Human scout review",
                body: "A real scout reads the scout intelligence output, watches your clip, and writes a personal review. Then you can chat with them about your game.",
              },
              {
                icon: ShieldCheck,
                title: "Built for trust",
                body: "No subscriptions. No upsells. No scammy 'reach out to clubs for you' promises. Just a premium report and a path you can actually follow.",
              },
            ].map((it) => (
              <div key={it.title} className="border border-gray-border bg-surface p-5">
                <div className="w-10 h-10 bg-volt/10 border border-volt/40 flex items-center justify-center mb-3">
                  <it.icon className="w-4 h-4 text-volt" />
                </div>
                <div className="font-barlow font-black uppercase text-base">{it.title}</div>
                <p className="mt-1.5 text-sm text-ink/65 leading-relaxed">{it.body}</p>
              </div>
            ))}
          </div>
        </section>

        <section className="mt-14">
          <div className="text-[10px] uppercase tracking-[0.25em] font-bold text-volt">Who we are</div>
          <h2 className="mt-3 font-barlow font-black uppercase tracking-tighter text-2xl md:text-3xl">
            The team behind ScoutMePlay
          </h2>
          <p className="mt-4 text-ink/70 leading-relaxed">
            We work with young athletes, parents and coaches across Scandinavia and beyond,
            building products that respect the kid's effort and the parent's wallet equally. We're not chasing 100 million users —
            we're trying to help the few thousand families who care enough to invest one premium report into their kid's future.
          </p>
        </section>

        <section id="contact" className="mt-14 border-t border-gray-border pt-10">
          <div className="text-[10px] uppercase tracking-[0.25em] font-bold text-volt">Contact</div>
          <h2 className="mt-3 font-barlow font-black uppercase tracking-tighter text-2xl md:text-3xl">
            Talk to us
          </h2>
          <p className="mt-3 text-ink/70 max-w-xl">
            Press, partnerships, support, refunds, club inquiries — write to us below.
            We read every message and reply within 24 hours.
          </p>

          <ContactForm />
        </section>
      </div>

      <footer className="border-t border-gray-border py-10 mt-10">
        <div className="max-w-7xl mx-auto px-6 md:px-10 text-center text-[10px] uppercase tracking-[0.22em] text-ink/50">
          © {new Date().getFullYear()} ScoutMePlay · All rights reserved
        </div>
      </footer>
    </div>
  );
}

// ============== Contact Form ==============

function ContactForm() {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [message, setMessage] = useState("");
  const [honeypot, setHoneypot] = useState("");   // hidden field — bots fill this
  const [submitting, setSubmitting] = useState(false);
  const [sent, setSent] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    if (!name.trim() || !email.trim() || message.trim().length < 10) {
      toast.error("Please fill in your name, email and a message of at least 10 characters.");
      return;
    }
    setSubmitting(true);
    try {
      await api.post("/contact", {
        name: name.trim(),
        email: email.trim().toLowerCase(),
        message: message.trim(),
        company: honeypot || undefined,
      });
      setSent(true);
      setName(""); setEmail(""); setMessage("");
      toast.success("Message received. We'll get back to you within 24 hours.");
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Couldn't send. Please try again or email us directly.");
    } finally {
      setSubmitting(false);
    }
  };

  if (sent) {
    return (
      <div className="mt-6 border-2 border-volt/30 bg-volt/5 p-6 max-w-xl">
        <div className="flex items-start gap-3">
          <div className="w-10 h-10 bg-volt/15 border border-volt flex items-center justify-center shrink-0">
            <CheckCircle2 className="w-5 h-5 text-volt" />
          </div>
          <div>
            <div className="font-barlow font-black uppercase text-base text-ink">Message sent</div>
            <p className="text-sm text-ink/70 mt-1.5 leading-relaxed">
              Thanks for reaching out. We read every message and reply within 24 hours.
            </p>
            <button
              onClick={() => setSent(false)}
              data-testid="contact-send-another"
              className="mt-4 text-xs uppercase tracking-[0.22em] font-bold text-volt hover:text-ink transition-colors"
            >
              Send another →
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <form onSubmit={submit} data-testid="contact-form" className="mt-6 max-w-xl space-y-4">
      {/* Honeypot — visually hidden, ignored by users, often filled by bots */}
      <div className="absolute -left-[9999px]" aria-hidden="true">
        <label>
          Company (leave blank)
          <input
            type="text"
            tabIndex={-1}
            autoComplete="off"
            value={honeypot}
            onChange={(e) => setHoneypot(e.target.value)}
          />
        </label>
      </div>

      <div>
        <label className="text-[10px] uppercase tracking-[0.22em] font-bold text-ink/55 block mb-1.5">
          Your name
        </label>
        <input
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="e.g. Maria Hansen"
          required
          minLength={2}
          maxLength={80}
          data-testid="contact-name-input"
          className="w-full bg-deepnavy border border-gray-border px-3 py-2.5 text-ink text-sm focus:outline-none focus:border-volt focus:ring-1 focus:ring-volt"
        />
      </div>

      <div>
        <label className="text-[10px] uppercase tracking-[0.22em] font-bold text-ink/55 block mb-1.5">
          Your email
        </label>
        <input
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="you@example.com"
          required
          data-testid="contact-email-input"
          className="w-full bg-deepnavy border border-gray-border px-3 py-2.5 text-ink text-sm focus:outline-none focus:border-volt focus:ring-1 focus:ring-volt"
        />
      </div>

      <div>
        <label className="text-[10px] uppercase tracking-[0.22em] font-bold text-ink/55 block mb-1.5">
          Message
        </label>
        <textarea
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          placeholder="Tell us what's on your mind — questions, partnerships, refund requests, anything."
          required
          minLength={10}
          maxLength={4000}
          rows={6}
          data-testid="contact-message-input"
          className="w-full bg-deepnavy border border-gray-border px-3 py-2.5 text-ink text-sm focus:outline-none focus:border-volt focus:ring-1 focus:ring-volt resize-y"
        />
        <div className="mt-1 text-[10px] text-ink/45 text-right">{message.length} / 4000</div>
      </div>

      <button
        type="submit"
        disabled={submitting}
        data-testid="contact-submit"
        className="inline-flex items-center gap-2 bg-volt hover:bg-forest-pop text-white font-barlow font-black uppercase tracking-widest text-sm px-7 py-3 transition-colors disabled:opacity-50"
      >
        {submitting ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
        Send message
      </button>
    </form>
  );
}
