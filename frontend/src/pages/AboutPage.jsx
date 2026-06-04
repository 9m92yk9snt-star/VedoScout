import React from "react";
import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import { ChevronLeft, ShieldCheck, Brain, Video, Trophy, Mail } from "lucide-react";
import Navigation from "@/components/Navigation";

export default function AboutPage() {
  return (
    <div className="min-h-screen bg-deepnavy text-white">
      <Navigation />

      <div className="max-w-4xl mx-auto px-6 md:px-10 py-14 md:py-20">
        <Link
          to="/"
          data-testid="about-back-link"
          className="inline-flex items-center gap-1.5 text-xs uppercase tracking-[0.22em] font-bold text-white/55 hover:text-volt transition-colors"
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
        <p className="mt-3 text-sm md:text-base text-white/60 max-w-2xl">
          Where talent gets noticed — built for the players nobody saw coming.
        </p>

        <section className="mt-12 space-y-5 text-white/75 leading-relaxed text-base">
          <p>
            ScoutMePlay is a premium football analysis platform built by <span className="text-volt font-bold">Mentalkids</span> — a small team
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
                title: "Evidence-based AI analysis",
                body: "Multimodal AI watches the full clip, scores 11 dimensions of your game, and gives you timestamped evidence — not generic praise.",
              },
              {
                icon: Trophy,
                title: "Human scout review",
                body: "A real scout reads the AI output, watches your clip, and writes a personal review. Then you can chat with them about your game.",
              },
              {
                icon: ShieldCheck,
                title: "Built for trust",
                body: "No subscriptions. No upsells. No scammy 'reach out to clubs for you' promises. Just a premium report and a path you can actually follow.",
              },
            ].map((it) => (
              <div key={it.title} className="border border-white/10 bg-surface p-5">
                <div className="w-10 h-10 bg-volt/10 border border-volt/40 flex items-center justify-center mb-3">
                  <it.icon className="w-4 h-4 text-volt" />
                </div>
                <div className="font-barlow font-black uppercase text-base">{it.title}</div>
                <p className="mt-1.5 text-sm text-white/60 leading-relaxed">{it.body}</p>
              </div>
            ))}
          </div>
        </section>

        <section className="mt-14">
          <div className="text-[10px] uppercase tracking-[0.25em] font-bold text-volt">Who we are</div>
          <h2 className="mt-3 font-barlow font-black uppercase tracking-tighter text-2xl md:text-3xl">
            Mentalkids — the company behind ScoutMePlay
          </h2>
          <p className="mt-4 text-white/70 leading-relaxed">
            Mentalkids is the parent company of ScoutMePlay. We work with young athletes, parents and coaches across Scandinavia,
            building products that respect the kid's effort and the parent's wallet equally. We're not chasing 100 million users —
            we're trying to help the few thousand families who care enough to invest one premium report into their kid's future.
          </p>
        </section>

        <section className="mt-14 border-t border-white/10 pt-10">
          <div className="text-[10px] uppercase tracking-[0.25em] font-bold text-volt">Contact</div>
          <h2 className="mt-3 font-barlow font-black uppercase tracking-tighter text-2xl md:text-3xl">
            Talk to us
          </h2>
          <p className="mt-3 text-white/70">
            Press, partnerships, support, refunds, club inquiries — write to us at:
          </p>
          <a
            href="mailto:scoutmeplay@gmail.com"
            data-testid="about-contact-email"
            className="mt-4 inline-flex items-center gap-2 bg-volt hover:bg-white text-deepnavy font-barlow font-black uppercase tracking-widest text-sm px-6 py-3 transition-colors"
          >
            <Mail className="w-4 h-4" />
            scoutmeplay@gmail.com
          </a>
        </section>
      </div>

      <footer className="border-t border-white/10 py-10 mt-10">
        <div className="max-w-7xl mx-auto px-6 md:px-10 text-center text-[10px] uppercase tracking-[0.22em] text-white/40">
          © {new Date().getFullYear()} Mentalkids · ScoutMePlay · All rights reserved
        </div>
      </footer>
    </div>
  );
}
