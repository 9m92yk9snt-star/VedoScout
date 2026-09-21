import React from "react";
import { Link } from "react-router-dom";
import { Crown, Sparkles, Plus } from "lucide-react";

const HERO_IMG = {
  free: `${process.env.REACT_APP_BACKEND_URL}/api/static/landing/hero-free.jpg`,
  premium: `${process.env.REACT_APP_BACKEND_URL}/api/static/landing/hero-premium.jpg`,
};

/* Greeting hero — mirrors the approved dashboard mockups: player image on the
 * right (masked), dream-selling copy on the left, membership chip below. */
export default function DashboardHero({ user, tier = "free" }) {
  const first = user?.full_name?.split(" ")[0] || "Player";
  const isFree = tier === "free";
  const isVip = tier === "vip";
  const img = isFree ? HERO_IMG.free : HERO_IMG.premium;

  return (
    <div className="relative overflow-hidden -mx-6 px-6 pt-8 pb-2 min-h-[190px]" data-testid="dashboard-hero">
      <img
        src={img}
        alt=""
        aria-hidden
        className="absolute right-0 top-0 h-full w-[320px] sm:w-[420px] object-cover pointer-events-none select-none"
        style={{
          WebkitMaskImage: "linear-gradient(90deg, transparent 0, #000 30%)",
          maskImage: "linear-gradient(90deg, transparent 0, #000 30%)",
          opacity: 0.9,
        }}
      />
      <div className="relative z-10 max-w-lg">
        <span className="text-forest text-xs uppercase tracking-[0.25em] font-bold inline-flex items-center gap-2">
          <span className="relative flex items-center justify-center w-2 h-2 shrink-0" aria-hidden>
            <span className="absolute inset-0 rounded-full bg-volt animate-ping opacity-75" />
            <span className="relative rounded-full w-1.5 h-1.5 bg-volt" />
          </span>
          Player dashboard
        </span>
        <h1 className="mt-3 font-barlow font-black uppercase text-4xl md:text-5xl tracking-tighter leading-[0.95]" data-testid="dashboard-hero-greeting">
          Welcome back, <span className="text-forest">{first}</span>
        </h1>
        <p className="mt-2.5 text-ink/70 text-sm md:text-[15px] leading-relaxed max-w-sm" data-testid="dashboard-hero-copy">
          {isFree
            ? "Every pro started with one video. Scouts are searching right now — make sure they can see you."
            : "You're on the right path. Keep pushing — your next opportunity is closer than you think."}
        </p>
        <div className="mt-4 flex flex-wrap items-center gap-3">
          <span
            data-testid="dashboard-membership-chip"
            className={`inline-flex items-center gap-2 font-barlow font-black uppercase tracking-[0.14em] text-xs px-4 py-2 rounded-full ${
              isVip
                ? "bg-[#0A0F0D] text-[#F5C443]"
                : isFree
                ? "bg-cream-card border border-ink/15 text-ink/70"
                : "bg-[#0F1F14] text-[#CCFF00]"
            }`}
          >
            {isFree ? <Sparkles className="w-3.5 h-3.5" /> : <Crown className="w-3.5 h-3.5" fill="currentColor" />}
            {isVip ? "VIP Member" : isFree ? "Free Member" : "Premium Member"}
          </span>
          <Link
            to="/upload"
            data-testid="dashboard-upload-btn"
            className="bg-forest hover:bg-forest-pop text-white font-barlow font-black uppercase tracking-widest text-xs px-5 py-2.5 rounded-full transition-colors inline-flex items-center gap-2"
            style={{ boxShadow: "0 14px 28px -14px rgba(31,79,47,0.5)" }}
          >
            <Plus className="w-4 h-4" /> New upload
          </Link>
        </div>
      </div>
    </div>
  );
}
