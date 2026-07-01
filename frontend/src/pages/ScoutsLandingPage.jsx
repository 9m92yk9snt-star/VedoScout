import React, { useEffect, useState, useRef } from "react";
import { Link, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { motion, useScroll, useTransform } from "framer-motion";
import {
  Search, Users, Shield, Sparkles, ArrowRight, Check, Loader2,
  Building2, UserCheck, Crown, ShieldCheck, Globe, Filter, Eye,
  Trophy, FileText, Play, ChevronDown, Star, X, MessageSquare,
} from "lucide-react";
import Navigation from "@/components/Navigation";
import api from "@/lib/api";
import { useAuth } from "@/lib/auth-context";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const IMG = (name) => `${BACKEND_URL}/api/static/landing/${name}`;

const ORG_TYPES = [
  { value: "solo_scout", label: "Independent scout" },
  { value: "scouting_agency", label: "Scouting agency" },
  { value: "agent", label: "Player agent" },
  { value: "club", label: "Football club" },
  { value: "media", label: "Football media" },
];

const HOW_STEPS = [
  {
    n: "01",
    title: "Filter the database",
    copy: "Position, age band, foot, country, minimum overall score, keyword. Every player is pre-scouted with a 4-pillar report.",
    icon: Filter,
  },
  {
    n: "02",
    title: "Preview reports & video",
    copy: "Full technical / tactical / physical / mindset breakdown. Timestamped highlights. Age-benchmarked percentiles.",
    icon: FileText,
  },
  {
    n: "03",
    title: "Reveal contact & message",
    copy: "One click reveals the player's email. Player is auto-notified you're interested. Deal-flow starts within minutes.",
    icon: MessageSquare,
  },
];

const TRUST_STATS = [
  { k: "19+", v: "Discoverable players" },
  { k: "48h", v: "Verification turnaround" },
  { k: "100%", v: "Refund if unverified" },
  { k: "0", v: "Renewal invoices" },
];

const FAQ = [
  {
    q: "How do you verify scouts and clubs?",
    a: "Every buyer completes a verification form before checkout — organization, role, LinkedIn URL, country, website. A ScoutMePlay admin manually reviews the info within 48 hours and awards the green Verified badge that players see. If we can't verify you, we refund the payment in full.",
  },
  {
    q: "Is this a monthly subscription?",
    a: "No. Scout Lifetime ($399) and Club Lifetime ($899) are one-time payments. You get permanent database access — no renewal invoices, no cancellations, no card-on-file surprises.",
  },
  {
    q: "How do players end up in the database?",
    a: "Players upload their match video, get a full AI scout report, then choose whether to make themselves discoverable. Minors under 16 require verified parental consent. Players can opt out any time.",
  },
  {
    q: "What's the difference between Scout and Club?",
    a: "Scout ($399) is for individual scouts, agents and small agencies — one login. Club ($899) is for football clubs and larger organizations — 5 team seats, priority support, and custom filter requests.",
  },
  {
    q: "Can I message players directly?",
    a: "Yes. One click reveals their email — the player is automatically notified that a verified scout viewed them. Reveals are unlimited on both tiers.",
  },
];

export default function ScoutsLandingPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [tiers, setTiers] = useState([]);
  const [access, setAccess] = useState(null);
  const [showVerification, setShowVerification] = useState(false);
  const [pendingTier, setPendingTier] = useState(null);
  const [loadingTier, setLoadingTier] = useState(null);
  const [openFaq, setOpenFaq] = useState(0);

  useEffect(() => {
    api.get("/scout-access/tiers").then(({ data }) => setTiers(data.tiers || []));
    if (user) {
      api.get("/scout-access/me").then(({ data }) => setAccess(data)).catch(() => {});
    }
  }, [user]);

  const startCheckout = (tierId) => {
    if (!user) {
      navigate(`/signup?next=/scouts&tier=${tierId}`);
      return;
    }
    setPendingTier(tierId);
    setShowVerification(true);
  };

  const submitVerificationAndCheckout = async (verificationData) => {
    setLoadingTier(pendingTier);
    try {
      const { data } = await api.post("/scout-access/subscribe", {
        tier: pendingTier,
        origin_url: window.location.origin,
        verification: verificationData,
      });
      if (data.url) window.location.href = data.url;
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Could not start checkout");
      setLoadingTier(null);
    }
  };

  return (
    <div data-testid="scouts-landing" className="min-h-screen bg-[#0A1F14] text-white antialiased overflow-x-hidden">
      <Navigation />

      <HeroSection access={access} />
      <MarqueeStrip />
      <ManifestoSection />
      <HowItWorks />
      <DatabasePreview />
      <TrustStats />
      <PricingSection
        tiers={tiers}
        access={access}
        loadingTier={loadingTier}
        onSubscribe={startCheckout}
      />
      <FaqSection openFaq={openFaq} setOpenFaq={setOpenFaq} />
      <FinalCta access={access} onSubscribe={() => startCheckout("scout")} />

      {showVerification && (
        <VerificationModal
          tier={pendingTier}
          onClose={() => { setShowVerification(false); setPendingTier(null); }}
          onSubmit={(data) => { setShowVerification(false); submitVerificationAndCheckout(data); }}
          loading={loadingTier === pendingTier}
        />
      )}
    </div>
  );
}

/* ─────────────────────────────  HERO  ───────────────────────────── */

function HeroSection({ access }) {
  const ref = useRef(null);
  const { scrollYProgress } = useScroll({ target: ref, offset: ["start start", "end start"] });
  const y = useTransform(scrollYProgress, [0, 1], [0, 120]);
  const opacity = useTransform(scrollYProgress, [0, 1], [1, 0.2]);

  return (
    <section
      ref={ref}
      className="relative min-h-[92vh] overflow-hidden isolate"
      data-testid="scouts-hero"
    >
      {/* Cinematic Nano Banana background */}
      <motion.div style={{ y }} className="absolute inset-0 -z-10">
        <img
          src={IMG("scouts-hero-tunnel.png")}
          alt=""
          className="w-full h-full object-cover opacity-70"
        />
        <div className="absolute inset-0 bg-gradient-to-r from-[#0A1F14] via-[#0A1F14]/85 to-transparent" />
        <div className="absolute inset-0 bg-gradient-to-b from-[#0A1F14]/60 via-transparent to-[#0A1F14]" />
      </motion.div>

      {/* Grain overlay */}
      <div
        className="absolute inset-0 -z-10 opacity-[0.08] pointer-events-none mix-blend-overlay"
        style={{
          backgroundImage: "url(\"data:image/svg+xml,%3Csvg viewBox='0 0 200 200' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='2' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E\")",
        }}
      />

      <motion.div
        style={{ opacity }}
        className="relative z-10 max-w-7xl mx-auto px-6 md:px-12 pt-20 pb-16 md:pt-32 md:pb-24 min-h-[92vh] flex flex-col justify-between"
      >
        <div>
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6 }}
            className="inline-flex items-center gap-2 border border-white/20 bg-white/5 backdrop-blur-sm px-4 py-2 mb-8"
          >
            <div className="w-1.5 h-1.5 bg-[#B8892C] rounded-full animate-pulse" />
            <span className="text-[10px] uppercase tracking-[0.3em] font-black text-white/80">
              For scouts · agents · clubs
            </span>
          </motion.div>

          <motion.h1
            initial={{ opacity: 0, y: 30 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8, delay: 0.1 }}
            className="font-barlow font-black uppercase tracking-tighter leading-[0.85] text-5xl md:text-7xl lg:text-8xl max-w-4xl"
          >
            The players<br />
            <span className="text-[#B8892C]">nobody</span> has<br />
            found yet.
          </motion.h1>

          <motion.p
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7, delay: 0.3 }}
            className="mt-8 text-base md:text-xl text-white/70 leading-relaxed max-w-xl"
          >
            One-time payment. Lifetime access to the ScoutMePlay database — a curated index
            of U7–U21 footballers, every one of them already scouted, scored and
            video-verified. Filter. Preview. Reveal. Sign.
          </motion.p>
        </div>

        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, delay: 0.5 }}
          className="mt-12 flex flex-wrap items-center gap-4"
        >
          {access?.active ? (
            <>
              <Link
                to="/players-database"
                data-testid="scouts-hero-enter-db"
                className="group inline-flex items-center gap-3 bg-[#B8892C] hover:bg-white text-[#0A1F14] font-barlow font-black uppercase tracking-widest text-sm px-8 py-4 transition-colors"
              >
                <Search className="w-4 h-4" /> Enter the database
                <ArrowRight className="w-4 h-4 transition-transform group-hover:translate-x-1" />
              </Link>
              <span className="inline-flex items-center gap-2 text-[11px] uppercase tracking-widest font-black text-[#B8892C]">
                <Check className="w-4 h-4" /> {access.tier} · lifetime {access.verified && "· verified"}
              </span>
            </>
          ) : (
            <>
              <a
                href="#pricing"
                data-testid="scouts-hero-cta"
                className="group inline-flex items-center gap-3 bg-[#B8892C] hover:bg-white text-[#0A1F14] font-barlow font-black uppercase tracking-widest text-sm px-8 py-4 transition-colors"
              >
                Get lifetime access
                <ArrowRight className="w-4 h-4 transition-transform group-hover:translate-x-1" />
              </a>
              <a
                href="#faq"
                className="group inline-flex items-center gap-3 border border-white/20 hover:border-white text-white font-barlow font-black uppercase tracking-widest text-sm px-8 py-4 backdrop-blur-sm transition-colors"
              >
                <Play className="w-4 h-4" /> How it works
              </a>
            </>
          )}

          {/* Trust chip */}
          <div className="hidden md:flex items-center gap-2 pl-4 ml-auto text-[10px] uppercase tracking-[0.24em] font-black text-white/50">
            <ShieldCheck className="w-4 h-4" />
            Verified by ScoutMePlay
          </div>
        </motion.div>

        {/* Scroll cue */}
        <motion.div
          initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 1.5, duration: 1 }}
          className="mt-16 flex items-center gap-2 text-[10px] uppercase tracking-[0.3em] font-black text-white/40"
        >
          <ChevronDown className="w-3 h-3 animate-bounce" />
          Scroll to explore
        </motion.div>
      </motion.div>
    </section>
  );
}

/* ─────────────────────────────  MARQUEE  ───────────────────────────── */

function MarqueeStrip() {
  const items = [
    "One-time payment",
    "Lifetime access",
    "Verified professionals",
    "48-hour review",
    "100% refund if unverified",
    "Unlimited reveals",
    "GDPR-safe",
    "Parental consent enforced",
  ];
  const doubled = [...items, ...items];
  return (
    <div className="border-y border-white/10 bg-[#081810] overflow-hidden py-4">
      <div className="flex gap-12 whitespace-nowrap animate-marquee">
        {doubled.map((t, i) => (
          <div key={i} className="flex items-center gap-3 shrink-0">
            <Star className="w-3 h-3 text-[#B8892C]" fill="#B8892C" />
            <span className="text-[11px] uppercase tracking-[0.24em] font-black text-white/60">{t}</span>
          </div>
        ))}
      </div>
      <style>{`
        @keyframes marquee { from { transform: translateX(0); } to { transform: translateX(-50%); } }
        .animate-marquee { animation: marquee 30s linear infinite; }
      `}</style>
    </div>
  );
}

/* ─────────────────────────────  MANIFESTO  ───────────────────────────── */

function ManifestoSection() {
  return (
    <section className="relative py-24 md:py-36 overflow-hidden">
      <div className="max-w-6xl mx-auto px-6 md:px-12 grid md:grid-cols-[1fr,1.2fr] gap-16 items-center">
        <motion.div
          initial={{ opacity: 0, x: -30 }}
          whileInView={{ opacity: 1, x: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.7 }}
        >
          <div className="text-[10px] uppercase tracking-[0.3em] font-black text-[#B8892C] mb-5">
            Why ScoutMePlay
          </div>
          <h2 className="font-barlow font-black uppercase tracking-tighter text-4xl md:text-6xl leading-[0.9]">
            Every year<br />
            <span className="text-[#B8892C]">a top-10 kid</span><br />
            slips through<br />
            the cracks.
          </h2>
          <p className="mt-6 text-white/70 leading-relaxed text-lg max-w-md">
            Traditional scouting means driving 400 kilometers to watch one player who ends
            up not being the right fit. We flipped it. Players come to us. We scout them
            first. You get the shortlist.
          </p>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, x: 30 }}
          whileInView={{ opacity: 1, x: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.7, delay: 0.15 }}
          className="relative aspect-[4/5] md:aspect-[4/5] overflow-hidden border border-white/10"
        >
          <img
            src={IMG("scouts-boardroom.png")}
            alt=""
            className="w-full h-full object-cover"
          />
          <div className="absolute inset-0 bg-gradient-to-t from-[#0A1F14] via-transparent to-transparent" />
          <div className="absolute bottom-6 left-6 right-6">
            <div className="text-[10px] uppercase tracking-[0.24em] font-black text-[#B8892C] mb-2">
              The Scouting War-room
            </div>
            <div className="font-barlow font-black uppercase text-xl leading-none">
              4 pillars · every player
            </div>
          </div>
        </motion.div>
      </div>
    </section>
  );
}

/* ─────────────────────────────  HOW IT WORKS  ───────────────────────────── */

function HowItWorks() {
  return (
    <section id="how" className="relative py-24 md:py-36 border-t border-white/5 bg-[#081810]">
      <div className="max-w-6xl mx-auto px-6 md:px-12">
        <motion.div
          initial={{ opacity: 0, y: 20 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }}
          className="mb-16 max-w-3xl"
        >
          <div className="text-[10px] uppercase tracking-[0.3em] font-black text-[#B8892C] mb-4">
            How it works
          </div>
          <h2 className="font-barlow font-black uppercase tracking-tighter text-4xl md:text-6xl leading-[0.9]">
            Three clicks<br /><span className="text-[#B8892C]">to a signing.</span>
          </h2>
        </motion.div>

        <div className="grid md:grid-cols-3 gap-6 md:gap-4">
          {HOW_STEPS.map((s, i) => {
            const Icon = s.icon;
            return (
              <motion.div
                key={s.n}
                initial={{ opacity: 0, y: 30 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ delay: i * 0.1, duration: 0.6 }}
                className="group relative bg-[#0A1F14] border border-white/10 p-8 md:p-10 hover:border-[#B8892C]/40 transition-colors overflow-hidden"
              >
                <div className="font-barlow font-black text-white/5 text-[140px] leading-none absolute -top-4 right-2 select-none pointer-events-none">
                  {s.n}
                </div>
                <div className="relative">
                  <div className="w-12 h-12 border border-[#B8892C]/50 flex items-center justify-center mb-6 bg-[#B8892C]/5">
                    <Icon className="w-5 h-5 text-[#B8892C]" strokeWidth={1.5} />
                  </div>
                  <div className="text-[10px] uppercase tracking-[0.24em] font-black text-[#B8892C] mb-2">
                    Step {s.n}
                  </div>
                  <h3 className="font-barlow font-black uppercase text-2xl leading-none mb-4">
                    {s.title}
                  </h3>
                  <p className="text-white/60 leading-relaxed text-sm">
                    {s.copy}
                  </p>
                </div>
              </motion.div>
            );
          })}
        </div>
      </div>
    </section>
  );
}

/* ─────────────────────────────  DATABASE PREVIEW  ───────────────────────────── */

function DatabasePreview() {
  return (
    <section className="relative py-24 md:py-36 overflow-hidden">
      <div className="max-w-6xl mx-auto px-6 md:px-12">
        <div className="grid md:grid-cols-[1.3fr,1fr] gap-12 md:gap-16 items-center">
          {/* Tablet image */}
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            whileInView={{ opacity: 1, scale: 1 }}
            viewport={{ once: true }}
            transition={{ duration: 0.8 }}
            className="relative aspect-[16/11] overflow-hidden border border-white/10 order-2 md:order-1"
          >
            <img
              src={IMG("scouts-data-tablet.png")}
              alt=""
              className="w-full h-full object-cover"
            />
            <div className="absolute inset-0 ring-1 ring-[#B8892C]/20 pointer-events-none" />
            <div className="absolute top-4 left-4 flex items-center gap-2 bg-[#0A1F14]/80 backdrop-blur px-3 py-1.5 border border-[#B8892C]/30">
              <div className="w-1.5 h-1.5 bg-[#B8892C] rounded-full animate-pulse" />
              <span className="text-[10px] uppercase tracking-[0.24em] font-black text-white/80">
                Live database
              </span>
            </div>
          </motion.div>

          {/* Copy */}
          <motion.div
            initial={{ opacity: 0, x: 30 }}
            whileInView={{ opacity: 1, x: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.7 }}
            className="order-1 md:order-2"
          >
            <div className="text-[10px] uppercase tracking-[0.3em] font-black text-[#B8892C] mb-5">
              What you unlock
            </div>
            <h2 className="font-barlow font-black uppercase tracking-tighter text-4xl md:text-5xl leading-[0.9]">
              Data. Video.<br />Human context.<br />
              <span className="text-[#B8892C]">All of it.</span>
            </h2>
            <ul className="mt-8 space-y-4">
              {[
                { icon: Filter, t: "Search by position, foot, country, age, minimum score" },
                { icon: FileText, t: "Full 4-pillar reports: technical · tactical · physical · mindset" },
                { icon: Play, t: "Timestamped highlight video attached to every player" },
                { icon: Users, t: "Age-benchmarked percentiles vs. their bracket" },
                { icon: Eye, t: "One-click contact reveal — player is auto-notified" },
              ].map(({ icon: Icon, t }) => (
                <li key={t} className="flex items-start gap-3">
                  <div className="w-8 h-8 border border-[#B8892C]/40 bg-[#B8892C]/5 flex items-center justify-center shrink-0">
                    <Icon className="w-3.5 h-3.5 text-[#B8892C]" />
                  </div>
                  <span className="text-white/80 text-[15px] leading-relaxed pt-1">{t}</span>
                </li>
              ))}
            </ul>
          </motion.div>
        </div>
      </div>
    </section>
  );
}

/* ─────────────────────────────  TRUST STATS  ───────────────────────────── */

function TrustStats() {
  return (
    <section className="relative py-16 md:py-24 border-y border-white/5 bg-[#081810]">
      <div className="max-w-6xl mx-auto px-6 md:px-12 grid grid-cols-2 md:grid-cols-4 gap-8 md:gap-4">
        {TRUST_STATS.map((s, i) => (
          <motion.div
            key={s.v}
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ delay: i * 0.08 }}
            className="text-center md:text-left border-t-2 border-[#B8892C]/40 pt-4"
          >
            <div className="font-barlow font-black text-5xl md:text-6xl lg:text-7xl leading-none text-white">
              {s.k}
            </div>
            <div className="mt-2 text-[10px] uppercase tracking-[0.24em] font-black text-white/50">
              {s.v}
            </div>
          </motion.div>
        ))}
      </div>
    </section>
  );
}

/* ─────────────────────────────  PRICING  ───────────────────────────── */

function PricingSection({ tiers, access, loadingTier, onSubscribe }) {
  return (
    <section id="pricing" className="relative py-24 md:py-36 overflow-hidden">
      {/* Ambient glow */}
      <div className="absolute inset-0 -z-10 opacity-40 pointer-events-none">
        <div className="absolute top-1/3 left-1/2 -translate-x-1/2 w-[600px] h-[600px] bg-[#B8892C]/10 blur-[100px] rounded-full" />
      </div>

      <div className="max-w-5xl mx-auto px-6 md:px-12">
        <motion.div
          initial={{ opacity: 0, y: 20 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }}
          className="text-center mb-16"
        >
          <div className="text-[10px] uppercase tracking-[0.3em] font-black text-[#B8892C] mb-4">
            One-time · Lifetime
          </div>
          <h2 className="font-barlow font-black uppercase tracking-tighter text-4xl md:text-6xl lg:text-7xl leading-[0.85]">
            Pay once.<br /><span className="text-[#B8892C]">Search forever.</span>
          </h2>
          <p className="mt-5 text-white/60 max-w-xl mx-auto text-[15px] leading-relaxed">
            No subscriptions. No hidden renewals. Full refund if you cannot be verified within 48 hours.
          </p>
        </motion.div>

        <div className="grid md:grid-cols-2 gap-6">
          {tiers.map((t, i) => {
            const isClub = t.id === "club";
            const Icon = isClub ? Building2 : UserCheck;
            const isCurrent = access?.active && access.tier === t.id;
            return (
              <motion.article
                key={t.id}
                initial={{ opacity: 0, y: 30 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ delay: i * 0.1, duration: 0.6 }}
                data-testid={`scouts-tier-${t.id}`}
                className={`relative flex flex-col overflow-hidden ${
                  isClub ? "" : ""
                }`}
              >
                {/* Card border/frame */}
                <div className={`absolute inset-0 border-2 pointer-events-none ${
                  isClub ? "border-[#B8892C]" : "border-white/15"
                }`} />

                {/* Corner ornaments (only club) */}
                {isClub && (
                  <>
                    <div className="absolute -top-px -left-px w-6 h-6 border-t-2 border-l-2 border-white pointer-events-none" />
                    <div className="absolute -top-px -right-px w-6 h-6 border-t-2 border-r-2 border-white pointer-events-none" />
                    <div className="absolute -bottom-px -left-px w-6 h-6 border-b-2 border-l-2 border-white pointer-events-none" />
                    <div className="absolute -bottom-px -right-px w-6 h-6 border-b-2 border-r-2 border-white pointer-events-none" />
                  </>
                )}

                <div className={`p-8 md:p-10 flex flex-col flex-1 ${
                  isClub ? "bg-[#B8892C]/5" : "bg-white/[0.02]"
                }`}>
                  {isClub && (
                    <span className="absolute top-6 right-6 bg-[#B8892C] text-[#0A1F14] text-[9px] uppercase tracking-[0.2em] font-black px-2.5 py-1">
                      <Crown className="inline w-3 h-3 -mt-0.5 mr-1" /> Best for teams
                    </span>
                  )}

                  <Icon className={`w-10 h-10 mb-6 ${isClub ? "text-[#B8892C]" : "text-white/50"}`} strokeWidth={1.2} />

                  <h3 className="font-barlow font-black uppercase text-3xl md:text-4xl leading-none tracking-tight">
                    {isClub ? "Club" : "Scout"}
                  </h3>
                  <p className="mt-2 text-[13px] text-white/50 leading-snug">
                    {isClub ? "Football clubs · larger organizations" : "Individual scouts · agents · small agencies"}
                  </p>

                  <div className="mt-6 flex items-baseline gap-2">
                    <span className="font-barlow font-black text-6xl md:text-7xl text-white">${t.amount}</span>
                    <span className="text-white/40 text-sm uppercase tracking-widest font-bold">one-time</span>
                  </div>
                  <div className="text-[11px] text-white/40 mt-1 uppercase tracking-widest font-bold">
                    Lifetime access · no renewals
                  </div>

                  <div className="my-8 h-px bg-white/10" />

                  <ul className="space-y-3 flex-1">
                    <FeatureLine>Full scout database — filter by position, age, foot, country</FeatureLine>
                    <FeatureLine>Unlimited searches</FeatureLine>
                    <FeatureLine>Unlimited contact reveals</FeatureLine>
                    <FeatureLine>Full 4-pillar reports + timestamped video</FeatureLine>
                    {isClub && <FeatureLine><strong>5 team seats</strong> for your scouting staff</FeatureLine>}
                    {isClub && <FeatureLine>Priority support · custom filter requests</FeatureLine>}
                    <FeatureLine>
                      <span className="inline-flex items-center gap-1.5">
                        <ShieldCheck className="w-3.5 h-3.5 text-[#B8892C]" />
                        Verified badge after manual review
                      </span>
                    </FeatureLine>
                    <FeatureLine>100% refund if unverified</FeatureLine>
                  </ul>

                  {isCurrent ? (
                    <div className="mt-8 border-2 border-[#B8892C] bg-[#B8892C]/10 text-[#B8892C] py-3.5 text-center font-barlow font-black uppercase tracking-widest text-sm">
                      Your current plan
                    </div>
                  ) : (
                    <button
                      type="button"
                      onClick={() => onSubscribe(t.id)}
                      disabled={loadingTier === t.id}
                      data-testid={`scouts-tier-${t.id}-cta`}
                      className={`group mt-8 inline-flex items-center justify-center gap-2 py-4 font-barlow font-black uppercase tracking-widest text-sm transition-all disabled:opacity-60 ${
                        isClub
                          ? "bg-[#B8892C] hover:bg-white text-[#0A1F14]"
                          : "bg-white/10 hover:bg-white text-white hover:text-[#0A1F14] border border-white/20"
                      }`}
                    >
                      {loadingTier === t.id ? (
                        <Loader2 className="w-4 h-4 animate-spin" />
                      ) : (
                        <>Get lifetime access <ArrowRight className="w-4 h-4 transition-transform group-hover:translate-x-1" /></>
                      )}
                    </button>
                  )}
                </div>
              </motion.article>
            );
          })}
        </div>

        <div className="mt-10 flex items-center justify-center gap-2 text-[10px] uppercase tracking-[0.24em] font-black text-white/40">
          <Shield className="w-3 h-3" /> Stripe secure checkout · Cancel anytime before verification
        </div>
      </div>
    </section>
  );
}

function FeatureLine({ children }) {
  return (
    <li className="flex items-start gap-2 text-sm text-white/85">
      <Check className="w-4 h-4 text-[#B8892C] shrink-0 mt-0.5" />
      <span>{children}</span>
    </li>
  );
}

/* ─────────────────────────────  FAQ  ───────────────────────────── */

function FaqSection({ openFaq, setOpenFaq }) {
  return (
    <section id="faq" className="relative py-24 md:py-36 border-t border-white/5 bg-[#081810]">
      <div className="max-w-3xl mx-auto px-6 md:px-12">
        <motion.div
          initial={{ opacity: 0, y: 20 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }}
          className="mb-14"
        >
          <div className="text-[10px] uppercase tracking-[0.3em] font-black text-[#B8892C] mb-4">
            FAQ
          </div>
          <h2 className="font-barlow font-black uppercase tracking-tighter text-4xl md:text-5xl leading-[0.9]">
            Questions,<br /><span className="text-[#B8892C]">answered.</span>
          </h2>
        </motion.div>

        <div className="border-t border-white/10">
          {FAQ.map((item, i) => (
            <div key={i} className="border-b border-white/10">
              <button
                type="button"
                onClick={() => setOpenFaq(openFaq === i ? -1 : i)}
                data-testid={`scouts-faq-${i}`}
                className="w-full flex items-center justify-between gap-4 py-5 md:py-6 text-left group"
              >
                <span className="font-barlow font-black uppercase text-base md:text-lg tracking-tight leading-tight text-white group-hover:text-[#B8892C] transition-colors">
                  {item.q}
                </span>
                <ChevronDown
                  className={`w-5 h-5 shrink-0 text-[#B8892C] transition-transform ${
                    openFaq === i ? "rotate-180" : ""
                  }`}
                />
              </button>
              {openFaq === i && (
                <motion.div
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: "auto" }}
                  exit={{ opacity: 0, height: 0 }}
                  className="pb-6 pr-8 text-white/70 leading-relaxed text-[15px]"
                >
                  {item.a}
                </motion.div>
              )}
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

/* ─────────────────────────────  FINAL CTA  ───────────────────────────── */

function FinalCta({ access, onSubscribe }) {
  return (
    <section className="relative overflow-hidden">
      <div className="absolute inset-0 -z-10">
        <img
          src={IMG("scouts-signing-desk.png")}
          alt=""
          className="w-full h-full object-cover opacity-30"
        />
        <div className="absolute inset-0 bg-gradient-to-b from-[#0A1F14]/95 via-[#0A1F14]/85 to-[#0A1F14]" />
      </div>

      <div className="relative max-w-4xl mx-auto px-6 md:px-12 py-24 md:py-36 text-center">
        <motion.div
          initial={{ opacity: 0, y: 20 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }}
        >
          <Trophy className="w-12 h-12 md:w-16 md:h-16 text-[#B8892C] mx-auto mb-6" strokeWidth={1} />
          <h2 className="font-barlow font-black uppercase tracking-tighter text-4xl md:text-6xl lg:text-7xl leading-[0.85]">
            Your next<br /><span className="text-[#B8892C]">signing</span> is<br />in the database.
          </h2>
          <p className="mt-6 text-white/70 max-w-xl mx-auto text-lg leading-relaxed">
            Stop chasing tips. Start signing the players you found first.
          </p>

          {access?.active ? (
            <Link
              to="/players-database"
              className="mt-10 inline-flex items-center gap-3 bg-[#B8892C] hover:bg-white text-[#0A1F14] font-barlow font-black uppercase tracking-widest text-sm px-10 py-5 transition-colors"
            >
              <Search className="w-4 h-4" /> Enter the database <ArrowRight className="w-4 h-4" />
            </Link>
          ) : (
            <button
              type="button"
              onClick={onSubscribe}
              data-testid="scouts-final-cta"
              className="mt-10 group inline-flex items-center gap-3 bg-[#B8892C] hover:bg-white text-[#0A1F14] font-barlow font-black uppercase tracking-widest text-sm px-10 py-5 transition-colors"
            >
              Get lifetime access — $399
              <ArrowRight className="w-4 h-4 transition-transform group-hover:translate-x-1" />
            </button>
          )}
        </motion.div>
      </div>
    </section>
  );
}

/* ─────────────────────────────  VERIFICATION MODAL  ───────────────────────────── */

function VerificationModal({ tier, onClose, onSubmit, loading }) {
  const [form, setForm] = useState({
    organization_name: "",
    organization_type: tier === "club" ? "club" : "solo_scout",
    role_title: "",
    country: "",
    website: "",
    linkedin_url: "",
    phone: "",
    notes: "",
  });

  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));
  const canSubmit = form.organization_name.trim() && form.role_title.trim() && form.country.trim();

  const submit = (e) => {
    e.preventDefault();
    if (!canSubmit) return;
    onSubmit(form);
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      className="fixed inset-0 z-50 flex items-start md:items-center justify-center bg-black/80 backdrop-blur-md p-4 overflow-y-auto"
      onClick={onClose}
      data-testid="verification-modal"
    >
      <form
        onSubmit={submit}
        onClick={(e) => e.stopPropagation()}
        className="w-full max-w-2xl bg-[#0A1F14] border-2 border-[#B8892C]/30 my-8 shadow-2xl"
      >
        <div className="flex items-start justify-between gap-4 border-b border-white/10 px-6 md:px-8 py-6 bg-gradient-to-r from-[#B8892C]/10 to-transparent">
          <div>
            <div className="text-[10px] uppercase tracking-[0.24em] font-black text-[#B8892C]">
              Step 1 of 2 · Verification
            </div>
            <h3 className="font-barlow font-black uppercase text-white text-2xl md:text-3xl leading-none mt-1">
              Tell us who you are
            </h3>
            <p className="mt-2 text-sm text-white/60">
              A ScoutMePlay admin reviews this within 48 hours. Full refund if we cannot verify you.
            </p>
          </div>
          <button type="button" onClick={onClose} data-testid="verification-close" className="text-white/50 hover:text-white transition-colors">
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="px-6 md:px-8 py-6 space-y-4">
          <div className="grid md:grid-cols-2 gap-4">
            <VField label="Organization / Club name *" required>
              <input
                type="text" maxLength={80} required
                data-testid="v-org-name"
                value={form.organization_name}
                onChange={(e) => set("organization_name", e.target.value)}
                placeholder="Brøndby IF Scouting"
                className="v-input"
              />
            </VField>
            <VField label="Type *" required>
              <select
                data-testid="v-org-type"
                value={form.organization_type}
                onChange={(e) => set("organization_type", e.target.value)}
                className="v-input"
              >
                {ORG_TYPES.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
              </select>
            </VField>
            <VField label="Your role / title *" required>
              <input
                type="text" maxLength={80} required
                data-testid="v-role-title"
                value={form.role_title}
                onChange={(e) => set("role_title", e.target.value)}
                placeholder="Head of Recruitment"
                className="v-input"
              />
            </VField>
            <VField label="Country *" required>
              <input
                type="text" maxLength={40} required
                data-testid="v-country"
                value={form.country}
                onChange={(e) => set("country", e.target.value)}
                placeholder="Denmark"
                className="v-input"
              />
            </VField>
            <VField label="Organization website">
              <input
                type="url" maxLength={200}
                data-testid="v-website"
                value={form.website}
                onChange={(e) => set("website", e.target.value)}
                placeholder="https://brondby.com"
                className="v-input"
              />
            </VField>
            <VField label="Your LinkedIn URL">
              <input
                type="url" maxLength={200}
                data-testid="v-linkedin"
                value={form.linkedin_url}
                onChange={(e) => set("linkedin_url", e.target.value)}
                placeholder="https://linkedin.com/in/..."
                className="v-input"
              />
            </VField>
            <VField label="Phone (optional)">
              <input
                type="tel" maxLength={40}
                data-testid="v-phone"
                value={form.phone}
                onChange={(e) => set("phone", e.target.value)}
                placeholder="+45 12 34 56 78"
                className="v-input"
              />
            </VField>
          </div>
          <VField label="Anything else we should know? (optional)">
            <textarea
              rows={2} maxLength={400}
              data-testid="v-notes"
              value={form.notes}
              onChange={(e) => set("notes", e.target.value)}
              placeholder="Recent placements, references, licenses…"
              className="v-input resize-none"
            />
          </VField>

          <div className="border border-[#B8892C]/30 bg-[#B8892C]/5 p-4 text-sm text-white/70 flex items-start gap-2.5">
            <ShieldCheck className="w-4 h-4 text-[#B8892C] mt-0.5 shrink-0" />
            <div>
              <strong className="text-white">Instant database access after payment.</strong>{" "}
              An admin reviews your info within 48 hours and grants the green verified badge
              that players see. If we cannot verify you, we refund in full.
            </div>
          </div>
        </div>

        <div className="flex items-center justify-between gap-3 border-t border-white/10 px-6 md:px-8 py-4 bg-[#081810]">
          <button
            type="button" onClick={onClose}
            className="text-[11px] uppercase tracking-widest font-black text-white/50 hover:text-white transition-colors"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={!canSubmit || loading}
            data-testid="verification-continue"
            className="inline-flex items-center gap-2 bg-[#B8892C] hover:bg-white text-[#0A1F14] font-barlow font-black uppercase tracking-widest text-sm px-6 py-3 transition-colors disabled:opacity-50"
          >
            {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <>Continue to secure checkout <ArrowRight className="w-4 h-4" /></>}
          </button>
        </div>
      </form>

      <style>{`
        .v-input {
          width: 100%;
          border: 1px solid rgba(255, 255, 255, 0.12);
          background: rgba(255, 255, 255, 0.03);
          color: #fff;
          padding: 10px 12px;
          font-size: 14px;
          transition: border-color 0.15s;
        }
        .v-input:focus { border-color: #B8892C; outline: none; }
        .v-input::placeholder { color: rgba(255, 255, 255, 0.3); }
      `}</style>
    </div>
  );
}

function VField({ label, children }) {
  return (
    <label className="block">
      <div className="text-[10px] uppercase tracking-[0.2em] font-black text-[#B8892C] mb-1.5">
        {label}
      </div>
      {children}
    </label>
  );
}
