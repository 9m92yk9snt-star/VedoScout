import React, { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import {
  Search, Users, Shield, Sparkles, ArrowRight, Check, Loader2,
  Building2, UserCheck, Crown, Zap, X, ShieldCheck,
} from "lucide-react";
import Navigation from "@/components/Navigation";
import api from "@/lib/api";
import { useAuth } from "@/lib/auth-context";

const ORG_TYPES = [
  { value: "solo_scout", label: "Independent scout" },
  { value: "scouting_agency", label: "Scouting agency" },
  { value: "agent", label: "Player agent" },
  { value: "club", label: "Football club" },
  { value: "media", label: "Football media" },
];

export default function ScoutsLandingPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [tiers, setTiers] = useState([]);
  const [access, setAccess] = useState(null);
  const [showVerification, setShowVerification] = useState(false);
  const [pendingTier, setPendingTier] = useState(null);
  const [loadingTier, setLoadingTier] = useState(null);

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
                <Check className="w-4 h-4" /> {access.tier} · lifetime {access.verified ? "· verified" : "· pending review"}
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
              One-time fee.<br /><span className="text-forest">Lifetime access.</span>
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
                icon: ShieldCheck,
                title: "Verified professionals only",
                copy: "We manually review every scout and club. Verified accounts get a green badge — players trust who they're talking to.",
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
        <div className="max-w-4xl mx-auto px-6 md:px-10">
          <div className="text-center mb-14">
            <div className="text-[10px] uppercase tracking-[0.28em] font-black text-volt mb-2">
              One-time · Lifetime
            </div>
            <h2 className="font-barlow font-black uppercase tracking-tighter text-3xl md:text-5xl leading-[0.95]">
              Pay once.<br /><span className="text-volt">Search forever.</span>
            </h2>
            <p className="mt-4 text-white/60 max-w-xl mx-auto">
              No subscriptions. No hidden renewals. Verified scouts and clubs get lifetime access
              to the ScoutMePlay player database with a single payment.
            </p>
          </div>

          <div className="grid md:grid-cols-2 gap-6">
            {tiers.map((t) => {
              const isClub = t.id === "club";
              const Icon = isClub ? Building2 : UserCheck;
              const isCurrent = access?.active && access.tier === t.id;
              return (
                <article
                  key={t.id}
                  data-testid={`scouts-tier-${t.id}`}
                  className={`relative bg-[#0A0F0D] border-2 p-8 md:p-10 flex flex-col ${
                    isClub ? "border-volt" : "border-white/10"
                  }`}
                >
                  {isClub && (
                    <span className="absolute -top-3 left-1/2 -translate-x-1/2 bg-volt text-ink text-[10px] uppercase tracking-[0.2em] font-black px-3 py-1 whitespace-nowrap">
                      <Crown className="inline w-3 h-3 -mt-0.5" /> For serious clubs
                    </span>
                  )}
                  <Icon className={`w-9 h-9 mb-4 ${isClub ? "text-volt" : "text-white/60"}`} strokeWidth={1.5} />
                  <h3 className="font-barlow font-black uppercase text-2xl md:text-3xl leading-tight tracking-tight">
                    {t.name.replace("ScoutMePlay ", "").replace(" — Lifetime", "")}
                  </h3>
                  <div className="mt-3 flex items-baseline gap-2">
                    <span className="font-barlow font-black text-5xl md:text-6xl text-white">${t.amount}</span>
                    <span className="text-white/50 text-sm">one-time</span>
                  </div>
                  <p className="mt-3 text-sm text-white/60 leading-relaxed">{t.description}</p>

                  <ul className="mt-6 space-y-2 flex-1">
                    <FeatureLine>Lifetime access to the player database</FeatureLine>
                    <FeatureLine>Unlimited searches + filters</FeatureLine>
                    <FeatureLine>Unlimited contact reveals</FeatureLine>
                    <FeatureLine>Full player reports + video previews</FeatureLine>
                    {t.seats > 1 && <FeatureLine>{t.seats} team seats (share with your scouting team)</FeatureLine>}
                    {isClub && <FeatureLine>Priority support · custom filters on request</FeatureLine>}
                    <FeatureLine>
                      <span className="inline-flex items-center gap-1.5">
                        <ShieldCheck className="w-3.5 h-3.5 text-volt" /> Verified badge after manual review
                      </span>
                    </FeatureLine>
                  </ul>

                  {isCurrent ? (
                    <div className="mt-6 border-2 border-volt bg-volt/10 text-volt py-3 text-center font-barlow font-black uppercase tracking-widest text-sm">
                      Your current plan
                    </div>
                  ) : (
                    <button
                      type="button"
                      onClick={() => startCheckout(t.id)}
                      disabled={loadingTier === t.id}
                      data-testid={`scouts-tier-${t.id}-cta`}
                      className={`mt-6 group inline-flex items-center justify-center gap-2 py-4 font-barlow font-black uppercase tracking-widest text-sm transition-colors ${
                        isClub
                          ? "bg-volt hover:bg-white text-ink"
                          : "bg-white/10 hover:bg-white text-white hover:text-ink"
                      } disabled:opacity-60`}
                    >
                      {loadingTier === t.id ? (
                        <Loader2 className="w-4 h-4 animate-spin" />
                      ) : (
                        <>Get lifetime access <ArrowRight className="w-4 h-4 transition-transform group-hover:translate-x-1" /></>
                      )}
                    </button>
                  )}
                </article>
              );
            })}
          </div>

          <p className="mt-10 text-center text-xs text-white/40 max-w-md mx-auto">
            Secure Stripe checkout · One-time payment · Verified badge granted after manual review of your credentials.
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

      {/* Verification modal */}
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

function FeatureLine({ children }) {
  return (
    <li className="flex items-start gap-2 text-sm text-white/85">
      <Check className="w-4 h-4 text-forest-pop shrink-0 mt-0.5" />
      <span>{children}</span>
    </li>
  );
}

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
      className="fixed inset-0 z-50 flex items-start md:items-center justify-center bg-ink/70 backdrop-blur-sm p-4 overflow-y-auto"
      onClick={onClose}
      data-testid="verification-modal"
    >
      <form
        onSubmit={submit}
        onClick={(e) => e.stopPropagation()}
        className="w-full max-w-2xl bg-cream-base border border-ink/10 my-8"
      >
        <div className="flex items-start justify-between gap-4 border-b border-ink/10 px-6 md:px-8 py-5">
          <div>
            <div className="text-[10px] uppercase tracking-[0.22em] font-black text-forest">
              Step 1 of 2 · Verification
            </div>
            <h3 className="font-barlow font-black uppercase text-2xl md:text-3xl leading-none mt-1">
              Tell us who you are
            </h3>
            <p className="mt-2 text-sm text-ink/60">
              We manually review every scout & club before granting the verified badge.
              This info is only visible to admins — not to players.
            </p>
          </div>
          <button type="button" onClick={onClose} data-testid="verification-close" className="text-ink/40 hover:text-ink">
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

          <div className="border border-forest/30 bg-forest/5 p-4 text-sm text-ink/70 flex items-start gap-2.5">
            <ShieldCheck className="w-4 h-4 text-forest mt-0.5 shrink-0" />
            <div>
              <strong className="text-ink">You get instant database access after payment.</strong>{" "}
              A ScoutMePlay admin reviews your info within 48 hours and grants the green verified
              badge shown to players. If we can't verify you, we refund the payment in full.
            </div>
          </div>
        </div>

        <div className="flex items-center justify-between gap-3 border-t border-ink/10 px-6 md:px-8 py-4 bg-cream-card">
          <button
            type="button" onClick={onClose}
            className="text-[11px] uppercase tracking-widest font-black text-ink/50 hover:text-ink transition-colors"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={!canSubmit || loading}
            data-testid="verification-continue"
            className="inline-flex items-center gap-2 bg-forest hover:bg-forest-pop text-white font-barlow font-black uppercase tracking-widest text-sm px-6 py-3 transition-colors disabled:opacity-50"
          >
            {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <>Continue to secure checkout <ArrowRight className="w-4 h-4" /></>}
          </button>
        </div>
      </form>

      {/* Utility class for inputs inside the modal */}
      <style>{`
        .v-input {
          width: 100%;
          border: 1px solid rgba(31, 39, 36, 0.15);
          background: #fff;
          padding: 10px 12px;
          font-size: 14px;
          transition: border-color 0.15s;
        }
        .v-input:focus { border-color: #1F4F2F; outline: none; }
      `}</style>
    </div>
  );
}

function VField({ label, children }) {
  return (
    <label className="block">
      <div className="text-[10px] uppercase tracking-[0.2em] font-black text-forest mb-1.5">
        {label}
      </div>
      {children}
    </label>
  );
}
