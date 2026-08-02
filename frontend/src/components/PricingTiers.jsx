/**
 * PricingTiers — Four-tier pricing comparison block.
 *
 * Tiers (left to right): Free · Single Report (one-time $129) · Premium · VIP.
 *
 * Layout:
 *   - lg+ (≥1024 px):  4-column grid (all 4 cards visible at once)
 *   - md  (≥768 px):   2×2 grid
 *   - sm  (≤767 px):   Horizontal swipe carousel with scroll-snap. Each card is
 *                      ~78 % of the viewport so the user clearly sees the next
 *                      card peeking from the right edge — telegraphs swipeability.
 *
 * Prices are pulled dynamically from `/api/settings/price` so the values
 * always match what the admin set in the dashboard. Three prices are wired:
 *   - single_price  → Single Report one-time tier (default $129)
 *   - premium_price → Premium monthly tier         (default $29.99)
 *   - vip_price     → VIP Premium monthly tier     (default $49.99)
 *
 * CTAs:
 *   - Free          → /signup (or /upload if logged in)
 *   - Single Report → /upload (logged in starts prepay-checkout) or /signup
 *   - Premium       → /payments/subscribe { tier:"premium" }
 *   - VIP           → /payments/subscribe { tier:"vip" }
 */
import React, { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import {
  Check, X, Crown, Star, Trophy, TrendingUp,
  Shield, Users, BarChart3, Lock, ArrowRight, CreditCard, Loader2,
  Sparkles, ChevronLeft, ChevronRight,
} from "lucide-react";

import api from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { trackInitiateCheckout } from "@/lib/pixels";

const ASSET_BASE = process.env.REACT_APP_BACKEND_URL;
const IMG = (name) => `${ASSET_BASE}/api/static/landing/${name}`;

/* ── Plan feature lists ─────────────────────────────────────────────── */
const FREE_FEATURES = [
  { label: "Professional Player Profile", included: true },
  { label: "1 Video Upload",                included: true },
  { label: "Basic AI Football Analysis",    included: true },
  { label: "Entry-Level Performance Insights", included: true },
  { label: "Progress Tracking",            included: false },
  { label: "Personal Development Plan",     included: false },
  { label: "Download PDF Reports",          included: false },
  { label: "Real Scout Review",             included: false },
];

const SINGLE_FEATURES = [
  { label: "Full 4-Pillar Premium Report", included: true },
  { label: "Pro Scout Intelligence Analysis (instant)", included: true },
  { label: "Real Scout Review (within 48h)",  included: true },
  { label: "Downloadable PDF Report",         included: true },
  { label: "Personalised Feedback",           included: true },
  { label: "Timestamped Key Moments",         included: true },
  { label: "7 / 30 / 90-Day Training Plan",  included: true },
  { label: "48-Hour Scout Review Guarantee",  included: true },
];

const PREMIUM_FEATURES = [
  { label: "Professional Player Profile",      included: true },
  { label: "2 Video Reports Monthly",          included: true },
  { label: "Extra Reports at Subscriber Rate", included: true, hint: "cheaper than a single report" },
  { label: "Instant AI Analysis",              included: true, hint: "delivered as soon as the pipeline finishes" },
  { label: "Progress Tracking Over Time",      included: true },
  { label: "Personal Development Plan",        included: true },
  { label: "Download PDF Reports",             included: true },
  { label: "Visible in Scout Database",        included: true },
  { label: "Real Scout Review",                included: false },
];

const VIP_FEATURES = [
  { label: "Everything in Premium",                  included: true },
  { label: "4 Video Reports Monthly",                 included: true },
  { label: "Extra Reports at Deepest Discount",       included: true, hint: "cheapest per-report rate" },
  { label: "Instant AI + Real Scout Review (48h)",    included: true, hint: "AI report is instant, scout responds within 48h" },
  { label: "Direct Contact with Professional Scouts", included: true },
  { label: "Personalised Scout Feedback Report",      included: true },
  { label: "Maximum Exposure for Opportunities",      included: true },
];

/* ── helper: format price stripped of trailing .00 ───────────────────── */
function fmtPrice(value) {
  if (value == null || Number.isNaN(value)) return "—";
  const n = Number(value);
  return Number.isInteger(n) ? `$${n}` : `$${n.toFixed(2)}`;
}

/* ====================================================================== */
export default function PricingTiers() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [busyTier, setBusyTier] = useState(null);

  // ── live-pricing fetched from backend ──────────────────────────────
  const [prices, setPrices] = useState({ single: 129, premium: 29.99, vip: 49.99, premiumExtra: 89, vipExtra: 59 });
  useEffect(() => {
    let alive = true;
    api.get("/settings/price")
      .then(({ data }) => {
        if (!alive) return;
        setPrices({
          single:       Number(data.single_price)        || 129,
          premium:      Number(data.premium_price)       || 29.99,
          vip:          Number(data.vip_price)           || 49.99,
          premiumExtra: Number(data.premium_extra_price) || 89,
          vipExtra:     Number(data.vip_extra_price)     || 59,
        });
      })
      .catch(() => {});
    return () => { alive = false; };
  }, []);

  // ── CTA handlers ──────────────────────────────────────────────────
  const goFree = () => {
    // Guest-first flow: straight to /upload — account is created at "Start analysis".
    navigate("/upload");
  };

  // Single Report: one-time prepay flow. Logged-out users go to signup.
  const goSingleReport = async () => {
    if (!user) {
      navigate("/signup?plan=single&next=/upload");
      return;
    }
    if (busyTier) return;
    setBusyTier("single");
    try {
      const { data } = await api.post("/payments/prepay-upload", {
        origin_url: window.location.origin,
      });
      if (!data?.url) throw new Error("No checkout URL received");
      trackInitiateCheckout();
      window.location.href = data.url;
    } catch (err) {
      const detail = err?.response?.data?.detail || err.message || "Could not start checkout.";
      toast.error(detail, { duration: 8000 });
      setBusyTier(null);
    }
  };

  const startSubscription = async (tier) => {
    if (!user) {
      navigate(`/signup?plan=${tier}&next=/?subscribe=${tier}`);
      return;
    }
    if (busyTier) return;
    setBusyTier(tier);
    try {
      const { data } = await api.post("/payments/subscribe", {
        tier,
        origin_url: window.location.origin,
      });
      if (!data?.url) throw new Error("No checkout URL received");
      trackInitiateCheckout();
      window.location.href = data.url;
    } catch (err) {
      const detail = err?.response?.data?.detail || err.message || "Could not start checkout.";
      toast.error(detail, { duration: 8000 });
      setBusyTier(null);
    }
  };

  const goPremium = () => startSubscription("premium");
  const goVip     = () => startSubscription("vip");

  // Card definitions are passed into both the swipeable mobile track
  // and the grid layout for tablet/desktop. Keeps a single source of truth.
  const cards = useMemo(() => ([
    {
      key: "free",
      render: (size) => <FreeCard size={size} onCta={goFree} />,
    },
    {
      key: "single",
      render: (size) => (
        <SingleCard size={size} price={prices.single} onCta={goSingleReport} loading={busyTier === "single"} disabled={!!busyTier && busyTier !== "single"} />
      ),
    },
    {
      key: "premium",
      render: (size) => (
        <PremiumCard size={size} price={prices.premium} extraPrice={prices.premiumExtra} singlePrice={prices.single} onCta={goPremium} loading={busyTier === "premium"} disabled={!!busyTier && busyTier !== "premium"} />
      ),
    },
    {
      key: "vip",
      render: (size) => (
        <VipCard size={size} price={prices.vip} extraPrice={prices.vipExtra} singlePrice={prices.single} onCta={goVip} loading={busyTier === "vip"} disabled={!!busyTier && busyTier !== "vip"} />
      ),
    },
  ]), [prices.single, prices.premium, prices.vip, prices.premiumExtra, prices.vipExtra, busyTier, user]);

  return (
    <section
      data-testid="pricing-tiers"
      className="relative px-6 md:px-10 py-12 md:py-16 border-b border-gray-border bg-cream-base overflow-hidden"
    >
      <Header />

      {/* Mobile carousel */}
      <MobileCarousel cards={cards} />

      {/* Tablet + Desktop grid */}
      <div
        data-testid="pricing-tiers-cards-desktop"
        className="hidden md:grid mt-10 md:mt-12 max-w-7xl mx-auto grid-cols-2 lg:grid-cols-4 gap-4 lg:gap-5 items-stretch"
      >
        {cards.map((c) => (
          <div key={c.key} className="flex">
            {c.render("desktop")}
          </div>
        ))}
      </div>

      <TrustRow />
      <JourneyStrip onCta={goFree} />
      <PaymentFooter />
    </section>
  );
}

/* ============================================================ */
/*  HEADER — bigger to match other section h2s on the site       */
/* ============================================================ */
function Header() {
  return (
    <div className="max-w-6xl mx-auto relative text-center">
      <div className="inline-flex items-center gap-2.5 mb-4">
        <span aria-hidden className="relative flex items-center justify-center w-2 h-2 shrink-0">
          <span className="absolute inset-0 rounded-full bg-volt animate-ping opacity-75" />
          <span className="relative rounded-full w-1.5 h-1.5 bg-volt" />
        </span>
        <span className="text-forest text-[10px] md:text-[11px] uppercase tracking-[0.28em] font-bold">
          Pricing · Pick your path
        </span>
        <span aria-hidden className="h-px w-8 bg-forest/35" />
      </div>
      <h2
        data-testid="pricing-tiers-title"
        className="font-barlow font-black uppercase tracking-tighter leading-[0.9] text-4xl md:text-6xl lg:text-7xl"
      >
        <span className="text-ink">Compare </span>
        <span className="text-forest">plans.</span><br />
        <span className="text-ink">Choose your </span>
        <span className="text-forest">level.</span>
      </h2>
      <p className="mt-5 text-base md:text-lg text-ink/65 leading-relaxed max-w-2xl mx-auto">
        Get a one-off scout report or commit to ongoing monthly progress. Same Pro Scout Intelligence, four ways in.
      </p>
      <span className="inline-flex items-center gap-2 mt-5 px-3.5 py-1.5 bg-cream-card border border-forest/25 text-[10px] uppercase tracking-[0.22em] font-bold text-forest">
        <svg viewBox="0 0 24 24" className="w-3.5 h-3.5" fill="currentColor" aria-hidden>
          <path d="M12 2l8 4v6c0 5-3.5 9-8 10-4.5-1-8-5-8-10V6l8-4z" />
        </svg>
        Built for U7–U21 players
      </span>
    </div>
  );
}

/* ============================================================ */
/*  MOBILE CAROUSEL — horizontal scroll-snap, peek next card     */
/* ============================================================ */
function MobileCarousel({ cards }) {
  const trackRef = useRef(null);
  const [idx, setIdx] = useState(0);

  // Track which card is most-centred to drive the dot indicators.
  useEffect(() => {
    const el = trackRef.current;
    if (!el) return;
    let raf;
    const onScroll = () => {
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(() => {
        const trackRect = el.getBoundingClientRect();
        const centre = trackRect.left + trackRect.width / 2;
        let bestIdx = 0;
        let bestDist = Infinity;
        Array.from(el.children).forEach((c, i) => {
          const r = c.getBoundingClientRect();
          const ccentre = r.left + r.width / 2;
          const d = Math.abs(centre - ccentre);
          if (d < bestDist) { bestDist = d; bestIdx = i; }
        });
        setIdx(bestIdx);
      });
    };
    el.addEventListener("scroll", onScroll, { passive: true });
    return () => {
      el.removeEventListener("scroll", onScroll);
      cancelAnimationFrame(raf);
    };
  }, []);

  const scrollToCard = (i) => {
    const el = trackRef.current;
    if (!el) return;
    const child = el.children[i];
    if (child) child.scrollIntoView({ behavior: "smooth", block: "nearest", inline: "center" });
  };

  return (
    <div className="md:hidden mt-8" data-testid="pricing-tiers-cards-mobile">
      {/* Edge-bleed swipe track. Each card is sized so 2 cards + a peek of
          the next are visible on a 390 px viewport — telegraphs swipeability
          (per user spec "se 2 og lidt af 3"). The `pt-5` reserves vertical
          space above the card body so floating top badges (-top-3) don't get
          clipped by the overflow-x-auto scroll container. */}
      <div
        ref={trackRef}
        className="-mx-6 px-6 flex gap-3 overflow-x-auto snap-x snap-mandatory scroll-smooth pt-5 pb-4"
        style={{ scrollbarWidth: "none" }}
      >
        {cards.map((c, i) => (
          <div
            key={c.key}
            data-testid={`pricing-mobile-slide-${i}`}
            className="snap-start shrink-0 w-[44vw] min-w-[155px] max-w-[200px] flex"
          >
            {c.render("mobile")}
          </div>
        ))}
        {/* trailing spacer keeps the last card scrollable into view */}
        <div aria-hidden className="shrink-0 w-[6vw]" />
      </div>

      {/* Pagination + swipe affordance */}
      <div className="mt-4 flex items-center justify-between gap-3 px-1">
        <button
          type="button"
          aria-label="Previous plan"
          data-testid="pricing-mobile-prev"
          onClick={() => scrollToCard(Math.max(0, idx - 1))}
          className="w-9 h-9 flex items-center justify-center border border-forest/30 text-forest bg-cream-card disabled:opacity-30"
          disabled={idx === 0}
        >
          <ChevronLeft className="w-4 h-4" />
        </button>

        <div className="flex items-center gap-1.5">
          {cards.map((_, i) => (
            <button
              key={i}
              type="button"
              aria-label={`Go to plan ${i + 1}`}
              data-testid={`pricing-mobile-dot-${i}`}
              onClick={() => scrollToCard(i)}
              className={`transition-all ${i === idx ? "w-6 bg-forest" : "w-1.5 bg-forest/30"} h-1.5`}
            />
          ))}
        </div>

        <button
          type="button"
          aria-label="Next plan"
          data-testid="pricing-mobile-next"
          onClick={() => scrollToCard(Math.min(cards.length - 1, idx + 1))}
          className="w-9 h-9 flex items-center justify-center border border-forest/30 text-forest bg-cream-card disabled:opacity-30"
          disabled={idx === cards.length - 1}
        >
          <ChevronRight className="w-4 h-4" />
        </button>
      </div>

      <p className="mt-2 text-center text-[10px] uppercase tracking-[0.22em] font-bold text-ink/40">
        Swipe to compare all plans →
      </p>
    </div>
  );
}

/* ============================================================ */
/*  CARDS — one component per tier                                */
/* ============================================================ */

/* ── FREE ── */
function FreeCard({ onCta }) {
  return (
    <article
      data-testid="pricing-card-free"
      className="relative bg-cream-card border border-gray-border p-3 md:p-6 flex flex-col w-full"
    >
      {/* Subtle dotted pattern on mobile */}
      <div
        aria-hidden
        className="absolute inset-0 opacity-[0.05] pointer-events-none md:hidden"
        style={{
          backgroundImage: "radial-gradient(circle at 1px 1px, #1F4F2F 1px, transparent 0)",
          backgroundSize: "14px 14px",
        }}
      />
      {/* Corner brackets */}
      <span aria-hidden className="absolute top-1.5 left-1.5 w-2.5 h-2.5 border-l border-t border-forest/30 md:hidden" />
      <span aria-hidden className="absolute top-1.5 right-1.5 w-2.5 h-2.5 border-r border-t border-forest/30 md:hidden" />
      {/* Live-pulse dot */}
      <span aria-hidden className="absolute top-2 right-2 hidden md:hidden">
        <span className="relative flex items-center justify-center w-1.5 h-1.5">
          <span className="absolute inset-0 rounded-full bg-forest animate-ping opacity-60" />
          <span className="relative rounded-full w-1 h-1 bg-forest" />
        </span>
      </span>
      <BadgeHeader tone="ghost" icon={Sparkles} label="Start" />
      <Title size="md" className="text-ink">Free</Title>
      <Price amount="$0" suffix="/ month" tone="ink" />
      <SubLine className="text-ink/65 hidden md:block">Try a free preview. No card required.</SubLine>
      <Divider />
      <FeatureList items={FREE_FEATURES} tone="forest" />
      <Cta
        onClick={onCta}
        data-testid="pricing-cta-free"
        className="relative mt-4 w-full border-2 border-ink/85 text-ink hover:bg-ink hover:text-cream-base"
      >
        Get started
      </Cta>
    </article>
  );
}

/* ── SINGLE REPORT (one-time) ── */
function SingleCard({ price, onCta, loading = false, disabled = false }) {
  return (
    <article
      data-testid="pricing-card-single"
      className="relative bg-cream-base border-2 border-ink p-3 md:p-6 flex flex-col w-full"
      style={{ boxShadow: "8px 8px 0 0 rgba(10,26,18,0.95)" }}
    >
      {/* Diagonal stripe pattern */}
      <div
        aria-hidden
        className="absolute inset-0 opacity-[0.04] pointer-events-none md:hidden"
        style={{
          backgroundImage: "repeating-linear-gradient(135deg, #1F4F2F 0, #1F4F2F 1px, transparent 1px, transparent 8px)",
        }}
      />
      <span
        aria-hidden
        className="absolute -top-3 left-1/2 -translate-x-1/2 inline-flex items-center gap-1.5 px-2.5 md:px-3 py-1 rounded-full bg-volt text-ink text-[9px] md:text-[10px] uppercase tracking-[0.16em] md:tracking-[0.18em] font-black whitespace-nowrap border border-ink z-10"
      >
        <Sparkles className="w-3 h-3 fill-current" /> <span className="hidden sm:inline">One-time · </span>Full report
      </span>
      {/* Corner brackets — visible mobile only */}
      <span aria-hidden className="absolute top-1.5 left-1.5 w-2.5 h-2.5 border-l border-t border-ink md:hidden" />
      <span aria-hidden className="absolute top-1.5 right-1.5 w-2.5 h-2.5 border-r border-t border-ink md:hidden" />

      <BadgeHeader tone="forest" icon={Trophy} label="Single" />
      <Title size="md" className="text-ink">Single<br className="hidden md:inline lg:hidden" /> Report</Title>
      <Price amount={fmtPrice(price)} suffix="one-time" tone="forest" />
      <SubLine className="text-ink/70 hidden md:block">
        Everything you need in <span className="font-black text-ink">one</span> premium report.
      </SubLine>

      {/* Product image — small on mobile, larger on desktop */}
      <div className="relative mt-3 aspect-[16/8] md:aspect-[16/8] bg-ink/5 border border-ink/10 overflow-hidden">
        <img
          src={IMG("single-icon.png")}
          alt="Single scout report"
          loading="lazy"
          onError={(e) => { e.currentTarget.style.display = "none"; }}
          className="absolute inset-0 w-full h-full object-cover"
        />
        <span className="absolute top-1 left-1 md:top-2 md:left-2 bg-ink text-volt text-[8px] md:text-[9px] uppercase tracking-[0.18em] md:tracking-[0.22em] font-black px-1.5 md:px-2 py-0.5">
          48h
        </span>
      </div>

      <Divider />
      <FeatureList items={SINGLE_FEATURES} tone="forest" />

      <Cta
        onClick={onCta}
        disabled={loading || disabled}
        data-testid="pricing-cta-single"
        className="relative mt-4 w-full bg-ink hover:bg-forest text-volt font-black"
      >
        {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : (
          <><span className="hidden md:inline">Buy single report</span><span className="md:hidden">Buy report</span> <ArrowRight className="w-4 h-4 transition-transform group-hover:translate-x-0.5" /></>
        )}
      </Cta>
    </article>
  );
}

/* ── PREMIUM (monthly subscription) ── */
function PremiumCard({ price, extraPrice, singlePrice, onCta, loading = false, disabled = false }) {
  return (
    <article
      data-testid="pricing-card-premium"
      className="relative bg-[#0F3A22] border border-forest p-3 md:p-6 flex flex-col text-white w-full"
      style={{ boxShadow: "0 24px 48px -16px rgba(15,58,34,0.55)" }}
    >
      {/* Radial glow pattern on mobile */}
      <div
        aria-hidden
        className="absolute inset-0 opacity-30 pointer-events-none md:hidden"
        style={{
          background: "radial-gradient(circle at 50% 30%, rgba(204,255,0,0.18) 0%, transparent 60%)",
        }}
      />
      <span
        aria-hidden
        className="absolute -top-3 left-1/2 -translate-x-1/2 inline-flex items-center gap-1.5 px-2.5 md:px-3 py-1 rounded-full bg-[#A5DD5F] text-[#0F3A22] text-[9px] md:text-[10px] uppercase tracking-[0.16em] md:tracking-[0.18em] font-black whitespace-nowrap z-10"
      >
        <Star className="w-3 h-3 fill-current" /> Most popular
      </span>
      {/* Corner brackets — mobile only */}
      <span aria-hidden className="absolute top-1.5 left-1.5 w-2.5 h-2.5 border-l border-t border-[#A5DD5F]/50 md:hidden" />
      <span aria-hidden className="absolute top-1.5 right-1.5 w-2.5 h-2.5 border-r border-t border-[#A5DD5F]/50 md:hidden" />

      <BadgeHeader tone="lime" icon={TrendingUp} label="Monthly" />
      <Title size="md" className="text-white">Premium</Title>
      <Price amount={fmtPrice(price)} suffix="/ month" tone="lime" />
      <SubLine className="text-white/70 hidden md:block">Keep tracking. Keep growing.</SubLine>

      <Divider dark />
      <FeatureList items={PREMIUM_FEATURES} tone="lime" dark />

      {/* Extra-report savings ribbon — highlights the discount vs single-report */}
      {extraPrice != null && (
        <div
          data-testid="pricing-premium-extra-line"
          className="mt-3 border border-[#A5DD5F]/40 bg-[#A5DD5F]/10 px-3 py-2 flex items-center justify-between gap-2"
        >
          <div className="leading-tight">
            <div className="text-[10px] uppercase tracking-[0.16em] font-black text-[#A5DD5F]">
              Buy extra reports
            </div>
            <div className="text-[9.5px] text-white/70 mt-0.5">
              Subscriber discount price
            </div>
          </div>
          <div className="text-[11px] text-white/85 leading-tight text-right">
            <span className="font-barlow font-black text-[#CCFF00] text-base">{fmtPrice(extraPrice)}</span>
            <span className="ml-1 text-white/60 line-through decoration-white/40 text-[10px] tabular-nums">
              {singlePrice ? fmtPrice(singlePrice) : ""}
            </span>
            <span className="ml-1 opacity-70">/ extra</span>
          </div>
        </div>
      )}

      <Cta
        onClick={onCta}
        disabled={loading || disabled}
        data-testid="pricing-cta-premium"
        className="relative mt-4 w-full bg-[#A5DD5F] hover:bg-[#B9E97A] text-[#0F3A22]"
      >
        {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : (
          <><span className="hidden md:inline">Start premium</span><span className="md:hidden">Premium</span> <ArrowRight className="w-4 h-4 transition-transform group-hover:translate-x-0.5" /></>
        )}
      </Cta>
    </article>
  );
}

/* ── VIP (monthly subscription) ── */
function VipCard({ price, extraPrice, singlePrice, onCta, loading = false, disabled = false }) {
  return (
    <article
      data-testid="pricing-card-vip"
      className="relative bg-[#0A0F0D] border border-[#1F2724] p-3 md:p-6 flex flex-col text-white w-full"
      style={{ boxShadow: "0 24px 48px -16px rgba(0,0,0,0.65)" }}
    >
      {/* Sparkle dot pattern on mobile */}
      <div
        aria-hidden
        className="absolute inset-0 opacity-[0.10] pointer-events-none md:hidden"
        style={{
          backgroundImage:
            "radial-gradient(circle at 25% 35%, #F5C443 1px, transparent 1px), radial-gradient(circle at 75% 65%, #F5C443 1px, transparent 1px)",
          backgroundSize: "32px 32px",
        }}
      />
      <span
        aria-hidden
        className="absolute -top-3 left-1/2 -translate-x-1/2 inline-flex items-center gap-1.5 px-2.5 md:px-3 py-1 rounded-full bg-[#F5C443] text-[#0A0F0D] text-[9px] md:text-[10px] uppercase tracking-[0.16em] md:tracking-[0.18em] font-black whitespace-nowrap z-10"
      >
        <Trophy className="w-3 h-3 fill-current" /> Best value
      </span>
      {/* Corner brackets — mobile only */}
      <span aria-hidden className="absolute top-1.5 left-1.5 w-2.5 h-2.5 border-l border-t border-[#F5C443]/60 md:hidden" />
      <span aria-hidden className="absolute top-1.5 right-1.5 w-2.5 h-2.5 border-r border-t border-[#F5C443]/60 md:hidden" />

      <BadgeHeader tone="gold" icon={Crown} label="Monthly" />
      <Title size="md" className="text-white">
        <span className="hidden md:inline">VIP Premium</span>
        <span className="md:hidden">VIP</span>
      </Title>
      <Price amount={fmtPrice(price)} suffix="/ month" tone="gold" />
      <SubLine className="text-white/70 hidden md:block">Everything. 4 reports. Reviewed.</SubLine>

      <Divider dark />
      <FeatureList items={VIP_FEATURES} tone="gold" dark />

      {/* Extra-report savings ribbon */}
      {extraPrice != null && (
        <div
          data-testid="pricing-vip-extra-line"
          className="mt-3 border border-[#F5C443]/40 bg-[#F5C443]/10 px-3 py-2 flex items-center justify-between gap-2"
        >
          <div className="leading-tight">
            <div className="text-[10px] uppercase tracking-[0.16em] font-black text-[#F5C443]">
              Buy extra reports
            </div>
            <div className="text-[9.5px] text-white/70 mt-0.5">
              Deepest VIP discount price
            </div>
          </div>
          <div className="text-[11px] text-white/85 leading-tight text-right">
            <span className="font-barlow font-black text-[#F5C443] text-base">{fmtPrice(extraPrice)}</span>
            <span className="ml-1 text-white/60 line-through decoration-white/40 text-[10px] tabular-nums">
              {singlePrice ? fmtPrice(singlePrice) : ""}
            </span>
            <span className="ml-1 opacity-70">/ extra</span>
          </div>
        </div>
      )}

      <Cta
        onClick={onCta}
        disabled={loading || disabled}
        data-testid="pricing-cta-vip"
        className="relative mt-4 w-full bg-[#F5C443] hover:bg-[#FFD661] text-[#0A0F0D]"
      >
        {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : (
          <>Go VIP <ArrowRight className="w-4 h-4 transition-transform group-hover:translate-x-0.5" /></>
        )}
      </Cta>
    </article>
  );
}

/* ── Reusable subcomponents ─────────────────────────────────────────── */

function BadgeHeader({ tone = "ghost", icon: Icon, label }) {
  const tones = {
    ghost:  "bg-forest/10 text-forest border border-forest/20",
    forest: "bg-forest text-white",
    lime:   "bg-[#A5DD5F]/15 text-[#A5DD5F] border border-[#A5DD5F]/30",
    gold:   "bg-[#F5C443]/15 text-[#F5C443] border border-[#F5C443]/30",
  };
  return (
    <div className="flex justify-center mb-3 mt-1">
      <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 text-[10px] uppercase tracking-[0.22em] font-bold ${tones[tone]}`}>
        <Icon className="w-3 h-3" strokeWidth={2.4} />
        {label}
      </span>
    </div>
  );
}

function Title({ children, className = "" }) {
  return (
    <h3 className={`text-center font-barlow font-black uppercase text-lg md:text-3xl leading-[0.95] tracking-tight ${className}`}>
      {children}
    </h3>
  );
}

function Price({ amount, suffix, tone = "ink" }) {
  const colour = {
    ink:    "text-ink",
    forest: "text-forest",
    lime:   "text-[#CCFF00]",
    gold:   "text-[#F5C443]",
  }[tone] || "text-ink";
  return (
    <div className="text-center mt-2">
      <span className={`font-barlow font-black text-3xl md:text-5xl lg:text-6xl leading-none ${colour}`}>{amount}</span>
      <span className="block text-[9px] md:text-[11px] uppercase tracking-[0.2em] md:tracking-[0.22em] font-bold opacity-70 mt-1.5">
        {suffix}
      </span>
    </div>
  );
}

function SubLine({ children, className = "" }) {
  return (
    <p className={`mt-3 text-center text-sm leading-snug ${className}`}>
      {children}
    </p>
  );
}

function Divider({ dark = false }) {
  return <div className={`my-4 h-px ${dark ? "bg-white/15" : "bg-gray-border"}`} />;
}

function FeatureList({ items, tone = "forest", dark = false }) {
  return (
    <ul className="space-y-2 flex-1">
      {items.map((f, i) => <FeatureItem key={i} {...f} tone={tone} dark={dark} />)}
    </ul>
  );
}

function FeatureItem({ label, included, tone = "forest", dark = false }) {
  const tones = {
    forest: { bg: "bg-forest",        off: "bg-gray-border" },
    lime:   { bg: "bg-[#A5DD5F]",     off: "bg-white/15" },
    gold:   { bg: "bg-[#F5C443]",     off: "bg-white/15" },
  };
  const t = tones[tone] || tones.forest;
  const textCls = dark
    ? included ? "text-white" : "text-white/55"
    : included ? "text-ink"  : "text-ink/45";
  return (
    <li className="flex items-start gap-2">
      <span
        aria-hidden
        className={`shrink-0 mt-0.5 w-4 h-4 rounded-full flex items-center justify-center ${included ? t.bg : t.off}`}
      >
        {included
          ? <Check className={`w-2.5 h-2.5 ${dark ? "text-[#0F3A22]" : "text-white"}`} strokeWidth={3.5} />
          : <X className={`w-2.5 h-2.5 ${dark ? "text-white/60" : "text-ink/55"}`} strokeWidth={3} />}
      </span>
      <span className={`text-[12.5px] leading-snug ${textCls}`}>{label}</span>
    </li>
  );
}

function Cta({ children, className = "", ...rest }) {
  return (
    <button
      type="button"
      {...rest}
      className={`group inline-flex items-center justify-center gap-2 font-barlow font-black uppercase tracking-[0.18em] text-xs sm:text-sm py-3 sm:py-3.5 transition-all disabled:opacity-60 disabled:cursor-wait ${className}`}
    >
      {children}
    </button>
  );
}

/* ============================================================ */
/*  Trust row                                                    */
/* ============================================================ */
function TrustRow() {
  const items = [
    { icon: Shield,    title: "Trusted by ambitious players",  body: "Join a growing community of footballers worldwide." },
    { icon: Users,     title: "Connected with pro scouts",     body: "Your profile and videos seen by professional scouts." },
    { icon: BarChart3, title: "Data-driven insights",          body: "Advanced AI analysis to help you improve and stand out." },
    { icon: Lock,      title: "Secure & private by default",   body: "Your data is encrypted and never shared. Always protected." },
  ];
  return (
    <div
      data-testid="pricing-trust-row"
      className="mt-12 md:mt-14 max-w-6xl mx-auto grid grid-cols-2 lg:grid-cols-4 gap-5 bg-cream-card border border-gray-border px-5 md:px-8 py-6 md:py-7"
    >
      {items.map(({ icon: Icon, title, body }, i) => (
        <div key={i} className="flex flex-col">
          <Icon className="w-6 h-6 text-forest mb-2.5" strokeWidth={1.8} />
          <h4 className="font-barlow font-black uppercase text-[11px] tracking-[0.18em] text-ink leading-tight">
            {title}
          </h4>
          <p className="mt-1.5 text-xs text-ink/65 leading-relaxed">{body}</p>
        </div>
      ))}
    </div>
  );
}

/* ============================================================ */
/*  Journey strip                                                */
/* ============================================================ */
function JourneyStrip({ onCta }) {
  return (
    <div
      data-testid="pricing-journey-strip"
      className="mt-8 max-w-6xl mx-auto relative bg-[#0F3A22] text-white px-6 md:px-10 py-8 md:py-10 overflow-hidden border border-forest/40"
    >
      <div
        aria-hidden
        className="absolute inset-0 opacity-30"
        style={{
          background:
            "radial-gradient(ellipse at right, rgba(204,255,0,0.18) 0%, transparent 55%), radial-gradient(circle at 80% 50%, rgba(255,255,255,0.06) 0%, transparent 50%)",
        }}
      />
      <div className="relative max-w-2xl">
        <h3 className="font-barlow font-black uppercase tracking-tighter text-2xl md:text-3xl leading-[0.95]">
          Your journey.<br /><span className="text-[#CCFF00]">Our mission.</span>
        </h3>
        <p className="mt-3 text-sm md:text-base text-white/75 leading-relaxed">
          We&apos;re here to help you get discovered, grow your skills and reach
          your full potential. The next level is closer than you think.
        </p>
        <button
          type="button"
          onClick={onCta}
          data-testid="pricing-journey-cta"
          className="group inline-flex items-center justify-center gap-2 mt-5 px-6 py-3 bg-transparent border-2 border-[#CCFF00] text-[#CCFF00] hover:bg-[#CCFF00] hover:text-[#0F3A22] font-barlow font-black uppercase tracking-[0.2em] text-sm transition-all"
        >
          Upload your video
          <ArrowRight className="w-4 h-4 transition-transform group-hover:translate-x-0.5" />
        </button>
      </div>
    </div>
  );
}

/* ============================================================ */
/*  Payment footer                                               */
/* ============================================================ */
function PaymentFooter() {
  return (
    <div
      data-testid="pricing-payment-footer"
      className="mt-8 max-w-6xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-4 px-5 py-4 bg-cream-card border border-gray-border"
    >
      <div className="flex items-center gap-2.5">
        <Lock className="w-4 h-4 text-forest" />
        <div className="leading-tight">
          <div className="text-[11px] uppercase tracking-[0.18em] font-black text-ink">
            No card required to start free
          </div>
          <div className="text-[11px] text-ink/60">Start free. Upgrade anytime.</div>
        </div>
      </div>
      <div className="flex items-center gap-4 text-ink/65 text-[12px] font-bold">
        <span className="inline-flex items-center gap-1.5">
          <svg viewBox="0 0 24 24" className="w-4 h-4" fill="currentColor" aria-hidden>
            <path d="M16.365 1.43c.073 1.115-.376 2.183-1.057 2.961-.731.847-1.94 1.5-3.118 1.41-.097-1.064.45-2.18 1.117-2.886.74-.78 2.005-1.4 3.058-1.486zM20.5 17.5c-.55 1.25-.8 1.81-1.5 2.92-.98 1.55-2.36 3.47-4.07 3.49-1.52.02-1.91-1-3.97-1-2.06 0-2.49 1-3.97 1.02-1.65.06-2.91-1.67-3.89-3.22C.96 17.49.07 12.94 1.86 9.9c.99-1.65 2.77-2.69 4.7-2.72 1.48-.03 2.88 1 3.97 1 1.09 0 2.79-1.23 4.7-1.05.79.03 3.01.32 4.44 2.41-.12.07-2.65 1.55-2.62 4.62.04 3.68 3.23 4.9 3.27 4.91z" />
          </svg>
          Apple Pay
        </span>
        <span className="inline-flex items-center gap-1.5">
          <svg viewBox="0 0 24 24" className="w-4 h-4" aria-hidden>
            <path fill="#4285F4" d="M12 11v2.8h6.5c-.3 1.6-2 4.6-6.5 4.6-3.9 0-7-3.2-7-7.2s3.1-7.2 7-7.2c2.2 0 3.7.9 4.6 1.7l3.1-3C17.8 1.3 15.2.2 12 .2 5.9.2.9 5.2.9 11.3S5.9 22.4 12 22.4c6.9 0 11.4-4.8 11.4-11.6 0-.8-.1-1.4-.2-1.9H12z"/>
          </svg>
          Google Pay
        </span>
        <span className="inline-flex items-center gap-1.5">
          <CreditCard className="w-4 h-4" />
          Card
        </span>
      </div>
    </div>
  );
}
