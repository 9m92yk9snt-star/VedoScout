import React, { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import {
  Search, Users, Shield, Sparkles, ArrowRight, Check, Loader2,
  Building2, UserCheck, Crown, Zap,
} from "lucide-react";
import Navigation from "@/components/Navigation";
import api from "@/lib/api";
import { useAuth } from "@/lib/auth-context";

const TIER_ICON = {
  scout_basic: UserCheck,
  scout_pro: Zap,
  club_enterprise: Building2,
};

const TIER_ACCENT = {
  scout_basic: "border-forest text-forest",
  scout_pro: "border-forest-pop text-forest-pop",
  club_enterprise: "border-amber-600 text-amber-700",
};

export default function ScoutsLandingPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [tiers, setTiers] = useState([]);
  const [access, setAccess] = useState(null);
  const [loadingTier, setLoadingTier] = useState(null);

  useEffect(() => {
    api.get("/scout-access/tiers").then(({ data }) => setTiers(data.tiers || []));
    if (user) {
      api.get("/scout-access/me").then(({ data }) => setAccess(data)).catch(() => {});
    }
  }, [user]);

  const handleSubscribe = async (tierId) => {
    if (!user) {
      navigate(`/signup?next=/scouts&tier=${tierId}`);
      return;
    }
    setLoadingTier(tierId);
    try {
      const { data } = await api.post("/scout-access/subscribe", {
        tier: tierId,
        origin_url: window.location.origin,
      });
      if (data.url) window.location.href = data.url;
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Could not start checkout");
      setLoadingTier(null);
    }
  };

  return (
    <div data-testid="scouts-landing" className="min-h-screen bg-cream-base text-ink">
      <Navigation />

      {/* HERO */}
      <section className="relative overflow-hidden border-b border-ink/10 pt-16 pb-20 md:pt-24 md:pb-28">
        <div
          aria-hidden
          className="absolute inset-0 opacity-[0.05] pointer-events-none"
          style={{
            backgroundImage: "radial-gradient(circle at 2px 2px, #1F4F2F 1px, transparent 0)",
            backgroundSize: "28px 28px",
          }}
        />
        <div className="relative max-w-6xl mx-auto px-6 md:px-10">
          <div className="inline-flex items-center gap-2 border border-forest/30 bg-forest/5 px-3 py-1.5 mb-6">
            <Shield className="w-4 h-4 text-forest" />
            <span className="text-[11px] uppercase tracking-[0.22em] font-black text-forest">
              For scouts · agents · clubs
            </span>
          </div>
          <h1 className="font-barlow font-black uppercase tracking-tighter text-4xl md:text-6xl lg:text-7xl leading-[0.9]">
            The next generation of<br />
            <span className="text-forest">football talent</span><br />
            <span className="text-forest-pop">on tap.</span>
          </h1>
          <p className="mt-6 md:mt-8 text-base md:text-lg text-ink/70 leading-relaxed max-w-2xl">
            Search a curated database of ambitious young footballers — U7 to U21 — who've opted
            in to be found. Every player comes with a full AI-driven scout report:
            technical, tactical, physical and mindset scores. Video attached. Age-benchmarked.
            No noise.
          </p>

          {access?.active ? (
            <div className="mt-8 flex flex-wrap gap-3">
              <Link
                to="/players-database"
                data-testid="scouts-hero-enter-db"
                className="inline-flex items-center gap-2 bg-forest hover:bg-forest-pop text-white font-barlow font-black uppercase tracking-widest text-sm px-8 py-4 transition-colors"
              >
                <Search className="w-4 h-4" /> Enter the database
                <ArrowRight className="w-4 h-4" />
              </Link>
              <span className="inline-flex items-center gap-2 border border-forest/40 bg-forest/5 text-forest px-4 py-4 text-[11px] uppercase tracking-widest font-black">
                <Check className="w-4 h-4" /> {access.tier?.replace("_", " ")} · active
              </span>
            </div>
          ) : (
            <div className="mt-8 flex flex-wrap gap-3">
              <a
                href="#scout-pricing"
                data-testid="scouts-hero-cta"
                className="inline-flex items-center gap-2 bg-forest hover:bg-forest-pop text-white font-barlow font-black uppercase tracking-widest text-sm px-8 py-4 transition-colors"
              >
                See pricing <ArrowRight className="w-4 h-4" />
              </a>
              <a
                href="#how-it-works"
                className="inline-flex items-center gap-2 border-2 border-ink/20 hover:border-forest text-ink font-barlow font-black uppercase tracking-widest text-sm px-8 py-4 transition-colors"
              >
                How it works
              </a>
            </div>
          )}
        </div>
      </section>

      {/* WHY */}
      <section id="how-it-works" className="py-20 md:py-28 border-b border-ink/10">
        <div className="max-w-6xl mx-auto px-6 md:px-10">
          <div className="text-center mb-14">
            <div className="text-[10px] uppercase tracking-[0.28em] font-black text-forest mb-2">
              The scout advantage
            </div>
            <h2 className="font-barlow font-black uppercase tracking-tighter text-3xl md:text-5xl leading-[0.95]">
              Save weeks.<br /><span className="text-forest">Find hidden gems.</span>
            </h2>
          </div>

          <div className="grid md:grid-cols-3 gap-px bg-ink/10 border border-ink/10">
            {[
              {
                icon: Search,
                title: "Filter by position, age, foot, country",
                copy: "The players you actually want to look at — surfaced in seconds. No LinkedIn spam, no cold outreach.",
              },
              {
                icon: Sparkles,
                title: "AI-vetted scout reports on tap",
                copy: "Every discoverable player already has a report: 4-pillar scores, age-benchmarked percentiles, timestamped highlights.",
              },
              {
                icon: Shield,
                title: "GDPR-safe & parent-consented",
                copy: "Minors require verified parental consent before appearing. Every player can withdraw visibility instantly.",
              },
            ].map(({ icon: Icon, title, copy }) => (
              <div key={title} className="bg-cream-card p-8">
                <Icon className="w-8 h-8 text-forest mb-4" strokeWidth={1.5} />
                <h3 className="font-barlow font-black uppercase text-lg tracking-tight leading-tight">
                  {title}
                </h3>
                <p className="mt-3 text-sm text-ink/70 leading-relaxed">{copy}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* PRICING */}
      <section id="scout-pricing" className="py-20 md:py-28 bg-ink text-white">
        <div className="max-w-6xl mx-auto px-6 md:px-10">
          <div className="text-center mb-14">
            <div className="text-[10px] uppercase tracking-[0.28em] font-black text-volt mb-2">
              Simple pricing
            </div>
            <h2 className="font-barlow font-black uppercase tracking-tighter text-3xl md:text-5xl leading-[0.95]">
              Pick your access.<br /><span className="text-volt">Cancel anytime.</span>
            </h2>
          </div>

          <div className="grid md:grid-cols-3 gap-6">
            {tiers.map((t) => {
              const Icon = TIER_ICON[t.id] || UserCheck;
              const isCurrent = access?.active && access.tier === t.id;
              return (
                <article
                  key={t.id}
                  data-testid={`scouts-tier-${t.id}`}
                  className={`relative bg-[#0A0F0D] border-2 p-8 flex flex-col ${
                    t.id === "scout_pro" ? "border-volt" : "border-white/10"
                  }`}
                >
                  {t.id === "scout_pro" && (
                    <span className="absolute -top-3 left-1/2 -translate-x-1/2 bg-volt text-ink text-[10px] uppercase tracking-[0.2em] font-black px-3 py-1 whitespace-nowrap">
                      <Crown className="inline w-3 h-3 -mt-0.5" /> Most popular
                    </span>
                  )}
                  <Icon className={`w-8 h-8 mb-4 ${t.id === "scout_pro" ? "text-volt" : "text-white/60"}`} strokeWidth={1.5} />
                  <h3 className="font-barlow font-black uppercase text-2xl leading-tight tracking-tight">
                    {t.name.replace("ScoutMePlay ", "")}
                  </h3>
                  <div className="mt-3 flex items-baseline gap-2">
                    <span className="font-barlow font-black text-5xl text-white">${t.amount}</span>
                    <span className="text-white/50 text-sm">/ month</span>
                  </div>
                  <p className="mt-3 text-sm text-white/60 leading-relaxed">{t.description}</p>

                  <ul className="mt-6 space-y-2 flex-1">
                    <FeatureLine>Search index of discoverable players</FeatureLine>
                    <FeatureLine>Filter by position, foot, age, country, score</FeatureLine>
                    <FeatureLine>
                      {t.monthly_reveals === null
                        ? "Unlimited contact reveals"
                        : `${t.monthly_reveals} contact reveals / month`}
                    </FeatureLine>
                    {t.seats > 1 && <FeatureLine>{t.seats} team seats</FeatureLine>}
                    {t.id !== "scout_basic" && <FeatureLine>Saved favourites & CSV export</FeatureLine>}
                    {t.id === "club_enterprise" && <FeatureLine>Custom filters + priority support</FeatureLine>}
                  </ul>

                  {isCurrent ? (
                    <div className="mt-6 border-2 border-volt bg-volt/10 text-volt py-3 text-center font-barlow font-black uppercase tracking-widest text-sm">
                      Your current plan
                    </div>
                  ) : (
                    <button
                      type="button"
                      onClick={() => handleSubscribe(t.id)}
                      disabled={loadingTier === t.id}
                      data-testid={`scouts-tier-${t.id}-cta`}
                      className={`mt-6 group inline-flex items-center justify-center gap-2 py-3 font-barlow font-black uppercase tracking-widest text-sm transition-colors ${
                        t.id === "scout_pro"
                          ? "bg-volt hover:bg-white text-ink"
                          : "bg-white/10 hover:bg-white text-white hover:text-ink"
                      } disabled:opacity-60`}
                    >
                      {loadingTier === t.id ? (
                        <Loader2 className="w-4 h-4 animate-spin" />
                      ) : (
                        <>Subscribe <ArrowRight className="w-4 h-4 transition-transform group-hover:translate-x-1" /></>
                      )}
                    </button>
                  )}
                </article>
              );
            })}
          </div>

          <p className="mt-10 text-center text-xs text-white/40">
            Secure Stripe billing · Cancel anytime from your dashboard · No hidden fees.
          </p>
        </div>
      </section>

      {/* FOOTER CTA */}
      <section className="py-16 md:py-20 border-b border-ink/10">
        <div className="max-w-3xl mx-auto text-center px-6 md:px-10">
          <Users className="w-10 h-10 text-forest mx-auto mb-4" strokeWidth={1.5} />
          <h3 className="font-barlow font-black uppercase tracking-tighter text-2xl md:text-3xl">
            One database. Every player pre-scouted.
          </h3>
          <p className="mt-3 text-ink/70">
            Stop chasing tips. Start signing the players you found first.
          </p>
        </div>
      </section>
    </div>
  );
}

function FeatureLine({ children }) {
  return (
    <li className="flex items-start gap-2 text-sm text-white/85">
      <Check className="w-4 h-4 text-forest-pop shrink-0 mt-0.5" />
      <span>{children}</span>
    </li>
  );
}
