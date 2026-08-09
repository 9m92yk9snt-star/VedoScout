/**
 * DreamPricingTiers — the unified "dream" 4-tier pricing design used EVERYWHERE
 * (landing, free preview, dashboard, report paywall).
 *
 * Prices are live from /api/settings/price (admin-editable):
 *   single_price · premium_price · vip_price
 * Optional `discount` (report/campaign discount) shows a slashed single price.
 *
 * CTAs:
 *   Free    → /upload (guest-first)
 *   Single  → onUnlockSingle() when provided (unlock THIS report), otherwise
 *             prepay-upload checkout (landing flow). Guests → signup.
 *   Premium → POST /payments/subscribe { tier:"premium" }
 *   VIP     → POST /payments/subscribe { tier:"vip" }
 */
import React, { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import {
  Sparkles, Eye, TrendingUp, Star, Trophy, Crown, Check, X,
  ChevronRight, ChevronLeft, ArrowRight, ShieldCheck, Lock, BarChart3, Gem, Loader2,
} from "lucide-react";
import api from "@/lib/api";
import { trackInitiateCheckout } from "@/lib/pixels";

const ASSET_BASE = process.env.REACT_APP_BACKEND_URL;
const IMG = (n) => `${ASSET_BASE}/api/static/landing/${n}`;

function priceParts(v) {
  if (v == null || Number.isNaN(Number(v))) return { main: "—", dec: "" };
  const n = Number(v);
  if (Number.isInteger(n)) return { main: `$${n}`, dec: "" };
  const [i, d] = n.toFixed(2).split(".");
  return { main: `$${i}`, dec: `.${d}` };
}

/* ── Feature lists (exact copy of the approved design) ─────────────── */
const FREE_FEATURES = [
  { label: "Professional Player Profile", ok: true },
  { label: "1 Video Upload", ok: true },
  { label: "Basic Football Analysis", ok: true },
  { label: "Entry-Level Performance Insights", ok: true },
  { label: "Progress Tracking", ok: false },
  { label: "Personal Development Plan", ok: false },
  { label: "Download PDF Reports", ok: false },
  { label: "Real Scout Review", ok: false },
];
const SINGLE_FEATURES = [
  { label: "Full 4-Pillar Premium Report", ok: true },
  { label: "ScoutMe Pro Intelligence Analysis (instant)", ok: true },
  { label: "Real Scout Review (within 48h)", ok: true },
  { label: "Downloadable PDF Report", ok: true },
  { label: "Personalised Feedback", ok: true },
  { label: "Timestamped Key Moments", ok: true },
  { label: "7 / 30 / 90-Day Training Plan", ok: true },
  { label: "48-Hour Scout Review Guarantee", ok: true },
];
const PREMIUM_FEATURES = [
  { label: "Everything in Single Report", ok: true },
  { label: "2 Video Reports Monthly", ok: true },
  { label: "Extra Reports at Subscriber Rate", ok: true },
  { label: "Instant Analysis", ok: true },
  { label: "Progress Tracking Over Time", ok: true },
  { label: "Personal Development Plan", ok: true },
  { label: "Download PDF Reports", ok: true },
  { label: "Visible in Scout Database", ok: true },
  { label: "Real Scout Review", ok: false },
];
const VIP_FEATURES = [
  { label: "Everything in Premium", ok: true },
  { label: "4 Video Reports Monthly", ok: true },
  { label: "Extra Reports at Deepest Discount", ok: true },
  { label: "Instant Analysis + Real Scout Review (48h)", ok: true },
  { label: "Direct Contact with Professional Scouts", ok: true },
  { label: "Personalised Scout Feedback Report", ok: true },
  { label: "Maximum Exposure for Opportunities", ok: true },
];

/* ── Card themes ────────────────────────────────────────────────────── */
const TIERS = {
  free: {
    icon: Sparkles, img: "price-free.jpg", notchIcon: null,
    titleLines: [["Your", "#16281C"], ["Journey", "#2E7D4F"], ["Starts", "#16281C"]],
    tagline: "Every great player begins with one opportunity.",
    taglineCls: "text-[#3C4A40]",
    cardStyle: { background: "#F7F6F0", border: "1px solid rgba(20,40,28,0.14)" },
    name: "Free", nameCls: "text-[#16281C]",
    priceCls: "text-[#1F4F2F]", periodCls: "text-[#16281C]/55",
    check: { on: "#12402A", onIcon: "#FFFFFF", off: "#DAD5C6", offIcon: "#7A776A", text: "text-[#22301F]", textOff: "text-[#22301F]/45" },
    ctaCls: "border-[1.5px] border-[#16281C]/60 text-[#16281C] bg-transparent hover:bg-[#12402A] hover:border-[#12402A] hover:text-white",
    features: FREE_FEATURES,
  },
  single: {
    icon: Eye, img: "price-single.jpg", notchIcon: Trophy,
    titleLines: [["What", "#16281C"], ["Did We", "#16281C"], ["See?", "#1F4F2F"]],
    tagline: "One match. Hundreds of hidden details.",
    taglineCls: "text-[#4A4636]",
    cardStyle: { background: "#EFE9D8", border: "1px solid rgba(20,40,28,0.16)" },
    name: "Single Report", nameCls: "text-[#16281C]",
    priceCls: "text-[#1F4F2F]", periodCls: "text-[#16281C]/55",
    check: { on: "#12402A", onIcon: "#FFFFFF", off: "#D6D0BE", offIcon: "#7A776A", text: "text-[#22301F]", textOff: "text-[#22301F]/45" },
    ctaCls: "border-[1.5px] border-[#16281C]/70 text-[#16281C] bg-transparent hover:bg-[#16281C] hover:text-[#EFE9D8]",
    features: SINGLE_FEATURES,
  },
  premium: {
    icon: TrendingUp, img: "price-premium.jpg", notchIcon: Crown,
    titleLines: [["Keep", "#FFFFFF"], ["Improving", "#B8EC5A"]],
    tagline: "Every match reveals a better version of you.",
    taglineCls: "text-white/75",
    cardStyle: {
      background: "linear-gradient(180deg,#12381F 0%,#0A2413 55%,#07190D 100%)",
      border: "1px solid rgba(168,224,99,0.55)",
      boxShadow: "0 0 38px -8px rgba(168,224,99,0.35)",
    },
    name: "Premium", nameCls: "text-white",
    priceCls: "text-[#C6F45F]", periodCls: "text-white/60",
    check: { on: "#B8EC5A", onIcon: "#0B2413", off: "rgba(255,255,255,0.14)", offIcon: "rgba(255,255,255,0.55)", text: "text-white/90", textOff: "text-white/45" },
    ctaCls: "bg-[#CDF05A] text-[#0B2413] hover:bg-[#DBF97D]",
    features: PREMIUM_FEATURES,
  },
  vip: {
    icon: Star, img: "price-vip.jpg", notchIcon: Crown,
    titleLines: [["Chase", "#FFFFFF"], ["The", "#FFFFFF"], ["Dream", "#E8C258"]],
    tagline: "Be ready when opportunity finds you.",
    taglineCls: "text-white/75",
    cardStyle: {
      background: "#0B0A08",
      border: "1px solid rgba(232,194,88,0.5)",
      boxShadow: "0 0 38px -8px rgba(232,194,88,0.28)",
    },
    name: "VIP", nameCls: "text-white",
    priceCls: "text-[#EFC94C]", periodCls: "text-white/60",
    check: { on: "#E8C258", onIcon: "#0A0F0D", off: "rgba(255,255,255,0.14)", offIcon: "rgba(255,255,255,0.55)", text: "text-white/90", textOff: "text-white/45" },
    ctaCls: "bg-[#EFC94C] text-[#0A0F0D] hover:bg-[#F7D765]",
    features: VIP_FEATURES,
  },
};

function FeatureRow({ label, ok, t }) {
  return (
    <li className="flex items-start gap-2 md:gap-2.5">
      <span
        aria-hidden
        className="shrink-0 mt-0.5 w-[18px] h-[18px] md:w-5 md:h-5 rounded-full flex items-center justify-center"
        style={{ background: ok ? t.check.on : t.check.off }}
      >
        {ok
          ? <Check className="w-3 h-3" style={{ color: t.check.onIcon }} strokeWidth={3.2} />
          : <X className="w-3 h-3" style={{ color: t.check.offIcon }} strokeWidth={3} />}
      </span>
      <span className={`text-[12.5px] md:text-[13px] leading-snug ${ok ? t.check.text : t.check.textOff}`}>{label}</span>
    </li>
  );
}

function TierCard({ tier, price, period, cta, ctaIconLeft, onCta, loading, disabled, discount, singleFull, testid, ctaTestid, valueLine = null, bestValue = false }) {
  const t = TIERS[tier];
  const TIcon = t.icon;
  const NIcon = t.notchIcon;
  const p = priceParts(price);
  return (
    <article data-testid={testid} className="relative flex flex-col rounded-[22px] overflow-hidden snap-center shrink-0 w-[82vw] max-w-[320px] sm:w-[46%] sm:max-w-none lg:w-auto lg:shrink" style={{ ...t.cardStyle, transform: "translateZ(0)", WebkitBackfaceVisibility: "hidden" }}>
      {bestValue && (
        <div data-testid={`best-value-badge-${tier}`} className="text-center text-[9.5px] font-black uppercase tracking-[0.24em] py-1" style={{ background: "#E8C258", color: "#12211A" }}>
          Best value per report
        </div>
      )}
      {/* ── Header: icon + emotive title + tagline + atmosphere image ── */}
      <div className="relative">
        <div className="pt-5 md:pt-7 px-5 text-center relative z-10">
          <TIcon className="w-5 h-5 md:w-6 md:h-6 mx-auto" style={{ color: t.titleLines[t.titleLines.length - 1][1] }} strokeWidth={2} />
          <h3 className="mt-2 md:mt-3 font-barlow font-black uppercase text-[21px] md:text-[27px] leading-[0.92] tracking-tight">
            {t.titleLines.map(([txt, col]) => (
              <span key={txt} className="block" style={{ color: col }}>{txt}</span>
            ))}
          </h3>
          <p className={`mt-2 md:mt-3 text-[12.5px] md:text-[13.5px] leading-snug max-w-[210px] mx-auto ${t.taglineCls}`}>{t.tagline}</p>
        </div>
        <div
          className="relative mt-3 md:mt-4 h-28 md:h-48"
          style={{ clipPath: "polygon(0 0, 100% 0, 100% calc(100% - 13px), 56% calc(100% - 13px), 50% 100%, 44% calc(100% - 13px), 0 calc(100% - 13px))" }}
        >
          <img
            src={IMG(t.img)}
            alt=""
            loading="lazy"
            onError={(e) => { e.currentTarget.style.display = "none"; }}
            className="absolute inset-0 w-full h-full object-cover"
            style={{
              maskImage: "linear-gradient(to bottom, transparent 0%, black 22%)",
              WebkitMaskImage: "linear-gradient(to bottom, transparent 0%, black 22%)",
            }}
          />
        </div>
        {NIcon && (
          <NIcon
            aria-hidden
            className="absolute left-1/2 -translate-x-1/2 bottom-4 w-4 h-4 z-10"
            style={{ color: tier === "single" ? "#16281C" : t.priceCls.includes("EFC94C") || tier === "vip" ? "#E8C258" : "#B8EC5A" }}
            strokeWidth={2.2}
          />
        )}
      </div>

      {/* ── Body: plan name, price, features, CTA ── */}
      <div className="px-4 md:px-5 pt-4 md:pt-6 pb-4 md:pb-6 flex flex-col flex-1">
        <div className={`text-center font-barlow font-black uppercase text-[17px] md:text-[20px] tracking-wide ${t.nameCls}`}>{t.name}</div>

        {tier === "single" && discount?.discounted != null ? (
          <div className="text-center mt-1 md:mt-1.5">
            <span className="text-lg font-bold line-through opacity-40" style={{ color: "#16281C" }}>{priceParts(singleFull).main}{priceParts(singleFull).dec}</span>
            <span className={`ml-2 font-barlow font-black text-[36px] md:text-[42px] leading-none ${t.priceCls}`} data-testid="paywall-discounted-price">
              {priceParts(discount.discounted).main}<span className="text-[22px] md:text-[26px]">{priceParts(discount.discounted).dec}</span>
            </span>
            <div className="mt-2">
              <span className="inline-block text-[10px] font-extrabold tracking-widest uppercase px-2.5 py-1 rounded-full" style={{ background: "#CCFF00", color: "#12211A" }} data-testid="paywall-discount-chip">
                {Math.round(discount.percent)}% off — limited
              </span>
            </div>
          </div>
        ) : (
          <div className="text-center mt-1 md:mt-1.5">
            <span className={`font-barlow font-black text-[38px] md:text-[46px] leading-none ${t.priceCls}`}>
              {p.main}<span className="text-[24px] md:text-[28px]">{p.dec}</span>
            </span>
          </div>
        )}
        <div className={`text-center mt-1 md:mt-1.5 text-[10.5px] md:text-[11px] uppercase tracking-[0.24em] font-bold ${t.periodCls}`}>{period}</div>
        {valueLine && (
          <div data-testid={`value-line-${tier}`} className={`text-center mt-1.5 text-[10.5px] md:text-[11px] font-extrabold ${t.nameCls}`} style={{ letterSpacing: "0.02em" }}>
            {valueLine}
          </div>
        )}

        <ul className="mt-4 md:mt-6 space-y-2 md:space-y-3 flex-1">
          {t.features.map((f) => <FeatureRow key={f.label} {...f} t={t} />)}
        </ul>

        <button
          type="button"
          onClick={onCta}
          disabled={loading || disabled}
          data-testid={ctaTestid}
          className={`mt-5 md:mt-7 w-full rounded-lg font-barlow font-black uppercase tracking-[0.16em] text-[13px] py-3 md:py-3.5 flex items-center justify-center gap-2 transition-all disabled:opacity-60 disabled:cursor-wait ${t.ctaCls}`}
        >
          {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : (
            <>
              {ctaIconLeft && <ChevronLeft className="w-4 h-4" />}
              {cta}
              {!ctaIconLeft && (tier === "free" ? <ChevronRight className="w-4 h-4" /> : <ArrowRight className="w-4 h-4" />)}
            </>
          )}
        </button>
      </div>
    </article>
  );
}

/* ── Bottom trust strip ─────────────────────────────────────────────── */
function TrustStrip() {
  const items = [
    { icon: ShieldCheck, color: "#2D6B3D", text: ["No credit card", "required"] },
    { icon: Lock, color: "#1F4F2F", text: ["Secure one-time", "payment"] },
    { icon: BarChart3, color: "#1F4F2F", text: ["Track. Improve.", "Grow."] },
    { icon: Gem, color: "#B98A2E", text: ["Maximum exposure.", "Maximum opportunity."] },
  ];
  return (
    <div className="mt-5 md:mt-7 pt-4 md:pt-6 border-t border-[#12402A26] grid grid-cols-2 lg:grid-cols-4 gap-x-3 md:gap-x-4 gap-y-3 md:gap-y-4" data-testid="dream-pricing-trust">
      {items.map(({ icon: Icon, color, text }, i) => (
        <div key={i} className="flex items-center gap-2.5 md:gap-3 justify-center lg:justify-start">
          <span className="shrink-0 w-8 h-8 md:w-9 md:h-9 rounded-lg border flex items-center justify-center bg-white/60" style={{ borderColor: `${color}55` }}>
            <Icon className="w-4 h-4" style={{ color }} strokeWidth={2} />
          </span>
          <span className="text-[11px] md:text-[12px] leading-snug text-[#3D4A38] font-semibold">
            {text[0]}<br />{text[1]}
          </span>
        </div>
      ))}
    </div>
  );
}

/* ════════════════════════════════════════════════════════════════════ */
export default function DreamPricingTiers({ isLoggedIn = false, onUnlockSingle = null, discount = null }) {
  const navigate = useNavigate();
  const trackRef = useRef(null);
  const [busyTier, setBusyTier] = useState(null);
  const [edge, setEdge] = useState({ start: true, end: false });
  const [prices, setPrices] = useState({ single: 129, premium: 29.99, vip: 49.99 });

  const updateEdge = () => {
    const el = trackRef.current;
    if (!el) return;
    const max = el.scrollWidth - el.clientWidth;
    setEdge({ start: el.scrollLeft <= 8, end: el.scrollLeft >= max - 8 });
  };

  useEffect(() => {
    const t = setTimeout(updateEdge, 300);
    return () => clearTimeout(t);
  }, []);

  const nudge = (dir) => {
    const el = trackRef.current;
    if (!el) return;
    const card = el.querySelector("article");
    const step = (card?.offsetWidth || 300) + 16;
    const max = el.scrollWidth - el.clientWidth;
    el.scrollTo({ left: Math.max(0, Math.min(max, el.scrollLeft + dir * step)), behavior: "smooth" });
  };

  useEffect(() => {
    let alive = true;
    api.get("/settings/price")
      .then(({ data }) => {
        if (!alive) return;
        setPrices({
          single: Number(data.single_price) || 129,
          premium: Number(data.premium_price) || 29.99,
          vip: Number(data.vip_price) || 49.99,
        });
      })
      .catch(() => {});
    return () => { alive = false; };
  }, []);

  const goFree = () => navigate("/upload");

  // Best-price math — recalculates live from admin prices
  const perPremium = prices.premium / 2;
  const perVip = prices.vip / 4;
  const savePct = (per) => Math.max(0, Math.round((1 - per / (prices.single || 1)) * 100));
  const bestTier = perVip <= perPremium ? "vip" : "premium";

  const goSingle = async () => {
    if (isLoggedIn && onUnlockSingle) { onUnlockSingle(); return; }
    if (busyTier) return;
    setBusyTier("single");
    try {
      const endpoint = isLoggedIn ? "/payments/prepay-upload" : "/payments/guest/checkout";
      const { data } = await api.post(endpoint, { tier: "single", origin_url: window.location.origin });
      if (!data?.url) throw new Error("No checkout URL received");
      trackInitiateCheckout();
      window.location.href = data.url;
    } catch (err) {
      toast.error(err?.response?.data?.detail || err.message || "Could not start checkout.", { duration: 8000 });
      setBusyTier(null);
    }
  };

  const startSubscription = async (tier) => {
    if (busyTier) return;
    setBusyTier(tier);
    try {
      const endpoint = isLoggedIn ? "/payments/subscribe" : "/payments/guest/checkout";
      const { data } = await api.post(endpoint, { tier, origin_url: window.location.origin });
      if (!data?.url) throw new Error("No checkout URL received");
      trackInitiateCheckout();
      window.location.href = data.url;
    } catch (err) {
      toast.error(err?.response?.data?.detail || err.message || "Could not start checkout.", { duration: 8000 });
      setBusyTier(null);
    }
  };

  return (
    <div data-testid="dream-pricing-tiers" className="rounded-[22px] md:rounded-[26px] px-3 sm:px-6 py-4 md:py-8" style={{ background: "linear-gradient(170deg, #F3EFE1 0%, #E9E4D0 100%)", border: "1px solid rgba(18,64,42,0.16)", boxShadow: "0 18px 44px -22px rgba(18,64,42,0.35)" }}>
      <div className="relative">
        <div ref={trackRef} onScroll={updateEdge} className="flex lg:grid lg:grid-cols-4 gap-4 overflow-x-auto lg:overflow-visible snap-x snap-mandatory scroll-smooth pb-2 lg:pb-0 items-stretch smp-dream-scroll" style={{ scrollbarWidth: "none", msOverflowStyle: "none", overscrollBehaviorX: "contain", WebkitOverflowScrolling: "touch", transform: "translateZ(0)" }}>
        <TierCard
          tier="free" price={0} period="/ Month" cta="Start Here"
          onCta={goFree} testid="dream-card-free" ctaTestid="pricing-cta-free"
        />
        <TierCard
          tier="single" price={prices.single} period="One-Time" cta="Get My Report"
          onCta={goSingle} loading={busyTier === "single"} disabled={!!busyTier && busyTier !== "single"}
          discount={discount} singleFull={prices.single}
          testid="dream-card-single" ctaTestid="paywall-single-cta"
        />
        <TierCard
          tier="premium" price={prices.premium} period="/ Month" cta="Start Improving"
          onCta={() => startSubscription("premium")} loading={busyTier === "premium"} disabled={!!busyTier && busyTier !== "premium"}
          valueLine={`2 reports/mo ≈ $${perPremium.toFixed(2)} each — save ${savePct(perPremium)}%`}
          bestValue={bestTier === "premium"}
          testid="dream-card-premium" ctaTestid="paywall-premium-cta"
        />
        <TierCard
          tier="vip" price={prices.vip} period="/ Month" cta="Go VIP" ctaIconLeft
          onCta={() => startSubscription("vip")} loading={busyTier === "vip"} disabled={!!busyTier && busyTier !== "vip"}
          valueLine={`4 reports/mo ≈ $${perVip.toFixed(2)} each — save ${savePct(perVip)}%`}
          bestValue={bestTier === "vip"}
          testid="dream-card-vip" ctaTestid="paywall-vip-cta"
        />
        </div>
        {/* Centered swipe arrows — visible until the 4-column grid kicks in */}
        <button
          type="button" aria-label="Previous plan" data-testid="dream-arrow-prev" onClick={() => nudge(-1)}
          disabled={edge.start}
          className={`lg:hidden absolute left-1 top-1/2 -translate-y-1/2 z-20 w-11 h-11 rounded-full flex items-center justify-center backdrop-blur-md active:scale-90 transition-all duration-300 ${edge.start ? "opacity-25 pointer-events-none" : "opacity-100"}`}
          style={{ background: "rgba(18,64,42,0.88)", border: "1px solid rgba(245,196,67,0.6)", animation: edge.start ? "none" : "smp-arrow-pulse 2.2s ease-in-out infinite" }}
        >
          <ChevronLeft className="w-5 h-5" style={{ color: "#F5C443", animation: edge.start ? "none" : "smp-arrow-nudge-l 1.1s ease-in-out infinite" }} />
        </button>
        <button
          type="button" aria-label="Next plan" data-testid="dream-arrow-next" onClick={() => nudge(1)}
          disabled={edge.end}
          className={`lg:hidden absolute right-1 top-1/2 -translate-y-1/2 z-20 w-11 h-11 rounded-full flex items-center justify-center backdrop-blur-md active:scale-90 transition-all duration-300 ${edge.end ? "opacity-25 pointer-events-none" : "opacity-100"}`}
          style={{ background: "rgba(18,64,42,0.88)", border: "1px solid rgba(245,196,67,0.6)", animation: edge.end ? "none" : "smp-arrow-pulse 2.2s ease-in-out infinite" }}
        >
          <ChevronRight className="w-5 h-5" style={{ color: "#F5C443", animation: edge.end ? "none" : "smp-arrow-nudge-r 1.1s ease-in-out infinite" }} />
        </button>
      </div>
      <p className="lg:hidden mt-2 text-center text-[10px] uppercase tracking-[0.22em] font-bold text-[#12402A66]">
        Swipe to compare all plans →
      </p>
      <TrustStrip />
      <style>{`
        .smp-dream-scroll::-webkit-scrollbar{display:none;}
        @keyframes smp-arrow-pulse { 0%,100% { box-shadow: 0 0 12px rgba(245,196,67,0.25), 0 6px 20px rgba(18,64,42,0.35); } 50% { box-shadow: 0 0 28px rgba(245,196,67,0.6), 0 6px 20px rgba(18,64,42,0.35); } }
        @keyframes smp-arrow-nudge-l { 0%,100% { transform: translateX(0); } 50% { transform: translateX(-3px); } }
        @keyframes smp-arrow-nudge-r { 0%,100% { transform: translateX(0); } 50% { transform: translateX(3px); } }
      `}</style>
    </div>
  );
}
