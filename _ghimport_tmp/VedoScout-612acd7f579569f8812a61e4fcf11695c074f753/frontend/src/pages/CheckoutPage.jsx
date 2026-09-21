// CheckoutPage — branded, conversion-focused Stripe Embedded Checkout for
// /checkout/single · /checkout/premium · /checkout/vip (guest + logged-in).
// Left column = ScoutMePlay brand story (per uploaded reference layouts),
// right column = the real Stripe payment form (Apple Pay / Link / card).
import React, { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams, useSearchParams, Link } from "react-router-dom";
import { loadStripe } from "@stripe/stripe-js";
import { EmbeddedCheckoutProvider, EmbeddedCheckout } from "@stripe/react-stripe-js";
import { toast } from "sonner";
import {
  ArrowLeft, Lock, Loader2, ShieldCheck, Check, Crown, Star, Target,
  TrendingUp, BadgeCheck, PlayCircle, FileDown, BarChart3, Heart,
  CalendarDays, FileCheck2, Timer, ChevronRight, AlertCircle, ArrowRight,
} from "lucide-react";
import api from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { trackInitiateCheckout, trackPurchase } from "@/lib/pixels";

const LIME = "#CCFF00";
const GOLD = "#F5C443";

const TIERS = {
  single: {
    accent: LIME,
    pageBg: "radial-gradient(120% 60% at 50% 0%, #131208 0%, #050604 45%, #030403 100%)",
    kicker: "YOUR DREAM. OUR ANALYSIS.",
    h1: [
      { t: "ONE MATCH.", accent: false },
      { t: "ONE REPORT.", accent: false },
      { t: "ENDLESS", accent: true },
      { t: "POSSIBILITIES.", accent: false },
    ],
    underlineWord: "POSSIBILITIES.",
    hero: "/checkout/hero-single.jpg",
    sub: ["We analyze every detail so you can step closer to ", "your next opportunity."],
    sectionTitle: "WHAT YOU'LL GET",
    benefits: [
      { icon: Target, title: "COMPLETE SCOUT REPORT", desc: "25+ key metrics & deep analysis of your performance." },
      { icon: BarChart3, title: "SCOUTME PRO ANALYSIS", desc: "Advanced data + tactical breakdown of your match." },
      { icon: PlayCircle, title: "KEY MOMENTS", desc: "Timestamps, highlights and important actions." },
      { icon: FileDown, title: "PDF REPORT", desc: "Download & keep your full professional report." },
      { icon: Star, title: "BUILT FOR YOUR FUTURE", desc: "Know your strengths. Fix your weaknesses. Chase your dream." },
    ],
    testimonial: {
      title: "DREAM BIG. WE'LL SHOW YOU HOW.",
      quote: "“This report gave me the confidence and clarity I needed. Now I know what to work on. Thank you!”",
      by: "– U16 Player",
    },
    trustRow: [
      { icon: FileCheck2, title: "ONE PAYMENT", sub: "No subscription" },
      { icon: Timer, title: "FAST DELIVERY", sub: "Report in 24–48h" },
      { icon: ShieldCheck, title: "100% SECURE", sub: "Your data is safe" },
    ],
    product: { name: "Single Scout Report", subline: "FULL REPORT. ONE PAYMENT.", per: "ONE-TIME", chipIcon: Star, chip: "A complete professional scout report from your match.", desc: null, crown: false },
    footerSub: "Your payment is protected. Your data is safe with us.",
    scriptLine: true,
  },
  premium: {
    accent: LIME,
    pageBg: "linear-gradient(175deg, #0A1810 0%, #06110A 40%, #040A06 100%)",
    kicker: "FOR PLAYERS CHASING MORE",
    h1: [
      { t: "YOUR DREAM", accent: false },
      { t: "DESERVES", accent: false },
      { t: "MORE.", accent: true },
    ],
    underlineWord: "MORE.",
    hero: "/checkout/hero-premium.jpg",
    sub: ["Every match can reveal something that ", "moves you forward."],
    sectionTitle: null,
    benefits: [
      { icon: Target, title: "SEE MORE", desc: "Discover details in your game you may never have noticed." },
      { icon: TrendingUp, title: "KEEP IMPROVING", desc: "Turn every report into a clearer direction for your development." },
      { icon: BadgeCheck, title: "GET SEEN", desc: "Build your profile and become visible inside the ScoutMePlay Scout Library." },
    ],
    plan: {
      name: "SCOUTMEPLAY PREMIUM",
      features: [
        "2 Video Reports Every Month",
        "ScoutMe Pro Match Analysis",
        "Progress Tracking",
        "Personal Development Plan",
        "Downloadable PDF Reports",
        "Scout Library Visibility",
        "Extra Reports at Subscriber Price",
      ],
    },
    upsell: {
      title: "WANT A PROFESSIONAL SCOUT'S OPINION TOO?",
      sub: "Real Scout Review is available with VIP.",
      linkText: "See VIP option",
      to: "/checkout/vip",
    },
    bottomLine: ["THOUSANDS OF PLAYERS. COUNTLESS DREAMS. ", "ONE NEXT STEP."],
    product: { name: "ScoutMePlay Premium", subline: null, per: "per month", chipIcon: CalendarDays, chip: "2 reports every month", desc: "Continue building your game, one report at a time.", crown: false },
    footerSub: "Your payment is protected. Cancel anytime.",
    scriptLine: false,
  },
  vip: {
    accent: GOLD,
    pageBg: "radial-gradient(120% 55% at 50% 0%, #171208 0%, #0A0805 45%, #050403 100%)",
    kicker: "FOR PLAYERS WHO WANT EVERY OPPORTUNITY",
    h1: [
      { t: "THE", accent: false },
      { t: "ULTIMATE", accent: false },
      { t: "ADVANTAGE.", accent: true },
    ],
    underlineWord: "ADVANTAGE.",
    hero: "/checkout/hero-vip.jpg",
    sub: ["Be ready when ", "opportunity finds you."],
    sectionTitle: null,
    benefitsGrid: [
      { icon: Crown, title: "MAXIMUM INSIGHT", desc: "See everything. Miss nothing." },
      { icon: Target, title: "REAL SCOUT REVIEW", desc: "Professional opinion within 48h." },
      { icon: Star, title: "MAX EXPOSURE", desc: "Put yourself in front of the right eyes." },
    ],
    plan: {
      name: "SCOUTMEPLAY VIP",
      features: [
        "Everything in Premium",
        "4 Video Reports Monthly",
        "Extra Reports at Deepest Discount",
        "Instant Analysis + Real Scout Review (48h)",
        "Direct Contact with Professional Scouts",
        "Personalised Scout Feedback Report",
        "Maximum Exposure for Opportunities",
      ],
    },
    promo: {
      title: "VIP → SEEN BY THE RIGHT PEOPLE",
      sub: "The closest you can get to real scouting opportunities.",
    },
    product: { name: "ScoutMePlay VIP", subline: null, per: "/ month", chipIcon: Crown, chip: "4 reports every month", desc: "Get the full scout experience. The plan made for players who want it all.", crown: true },
    footerSub: "Your payment is protected. Cancel anytime.",
    scriptLine: false,
  },
};

export default function CheckoutPage() {
  const { tier } = useParams();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const { user } = useAuth();
  const reportId = searchParams.get("report");

  const cfg = TIERS[tier];
  const accent = cfg?.accent || LIME;

  const [state, setState] = useState("loading"); // loading | ready | confirming | error | already-subscribed
  const [errorMessage, setErrorMessage] = useState(null);
  const [clientSecret, setClientSecret] = useState(null);
  const [stripePromise, setStripePromise] = useState(null);
  const [amount, setAmount] = useState(null);
  const [prices, setPrices] = useState({ single: 129, premium: 29.99, vip: 49.99 });
  const sessionIdRef = useRef(null);
  const startedRef = useRef(false);
  const pollRef = useRef(null);

  useEffect(() => {
    if (!cfg) navigate("/", { replace: true });
  }, [cfg, navigate]);

  useEffect(() => {
    api.get("/settings/price")
      .then(({ data }) => setPrices({
        single: Number(data.single_price) || 129,
        premium: Number(data.premium_price) || 29.99,
        vip: Number(data.vip_price) || 49.99,
      }))
      .catch(() => {});
  }, []);

  const createSession = async () => {
    const origin_url = window.location.origin;
    if (!user) {
      const { data } = await api.post("/payments/guest/embedded", { tier, origin_url });
      return data;
    }
    if (tier === "single") {
      if (reportId) {
        const { data } = await api.post("/payments/embedded/unlock", { report_id: reportId, origin_url });
        return data;
      }
      const { data } = await api.post("/payments/embedded/prepay-upload", { origin_url });
      return data;
    }
    const { data } = await api.post("/payments/embedded/subscribe", { tier, origin_url });
    return data;
  };

  // Graceful fallback to hosted Stripe when embedded keys aren't configured
  const fallbackRedirect = async () => {
    const origin_url = window.location.origin;
    let url = null;
    if (!user) {
      const { data } = await api.post("/payments/guest/checkout", { tier, origin_url });
      url = data?.url;
    } else if (tier === "single") {
      if (reportId) {
        const { data } = await api.post("/payments/checkout", { report_id: reportId, origin_url });
        url = data?.url;
      } else {
        const { data } = await api.post("/payments/prepay-upload", { origin_url });
        url = data?.url;
      }
    } else {
      const { data } = await api.post("/payments/subscribe", { tier, origin_url });
      url = data?.url;
    }
    if (!url) throw new Error("Could not start checkout.");
    trackInitiateCheckout();
    window.location.href = url;
  };

  useEffect(() => {
    if (!cfg || startedRef.current) return;
    startedRef.current = true;
    (async () => {
      try {
        const { data: sc } = await api.get("/config/stripe");
        if (!sc.embedded_available || !sc.publishable_key) {
          await fallbackRedirect();
          return;
        }
        setStripePromise(loadStripe(sc.publishable_key));
        const init = await createSession();
        setClientSecret(init.client_secret);
        sessionIdRef.current = init.session_id;
        if (init.amount) setAmount(Number(init.amount));
        setState("ready");
        trackInitiateCheckout();
      } catch (err) {
        if (err?.response?.status === 409) {
          setState("already-subscribed");
          return;
        }
        const msg = err?.response?.data?.detail || err?.message || "Couldn't open checkout. Try again.";
        setErrorMessage(typeof msg === "string" ? msg : "Couldn't open checkout.");
        setState("error");
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cfg]);

  useEffect(() => () => pollRef.current && clearInterval(pollRef.current), []);

  const handleComplete = () => {
    const sid = sessionIdRef.current;
    if (!sid) return;
    if (!user) {
      // /welcome polls guest status itself and handles account creation
      navigate(`/welcome?guest_session=${sid}`);
      return;
    }
    setState("confirming");
    const statusUrl = tier === "single"
      ? `/payments/embedded/status/${sid}`
      : `/payments/subscribe/status/${sid}`;
    let attempts = 0;
    const tick = async () => {
      attempts += 1;
      try {
        const { data } = await api.get(statusUrl);
        if (data.payment_status === "paid") {
          clearInterval(pollRef.current);
          pollRef.current = null;
          trackPurchase(amount || prices[tier], "USD");
          if (tier === "single" && reportId) {
            toast.success("Payment confirmed — your full report is unlocking now!", { duration: 6000 });
            navigate(`/report/${reportId}`);
          } else if (tier === "single") {
            toast.success("Report credit added — upload your match video!", { duration: 6000 });
            navigate("/upload");
          } else {
            toast.success(`${tier === "vip" ? "VIP" : "Premium"} is now active — welcome!`, { duration: 6000 });
            navigate("/dashboard");
          }
        } else if (attempts >= 15) {
          clearInterval(pollRef.current);
          pollRef.current = null;
          setErrorMessage("Payment is still processing. Refresh this page in a moment — your access is safe.");
          setState("error");
        }
      } catch {
        clearInterval(pollRef.current);
        pollRef.current = null;
        setErrorMessage("Couldn't verify the payment yet. Refresh this page in a moment — your access is safe.");
        setState("error");
      }
    };
    tick();
    pollRef.current = setInterval(tick, 2000);
  };

  const checkoutOptions = useMemo(
    () => ({ clientSecret, onComplete: handleComplete }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [clientSecret],
  );

  if (!cfg) return null;

  const displayPrice = amount != null ? amount : prices[tier];
  const priceStr = tier === "single"
    ? `$${Number.isInteger(displayPrice) ? displayPrice : displayPrice.toFixed(2)}`
    : `$${Number(displayPrice).toFixed(2)}`;

  const goBack = () => {
    if (window.history.length > 2) navigate(-1);
    else navigate("/");
  };

  const AccentCheck = () => (
    <span
      className="w-5 h-5 rounded-full flex items-center justify-center shrink-0 mt-0.5"
      style={{ background: `${accent}22`, border: `1px solid ${accent}55` }}
    >
      <Check className="w-3 h-3" style={{ color: accent }} strokeWidth={3} />
    </span>
  );

  const ChipIcon = cfg.product.chipIcon;

  return (
    <div data-testid="checkout-page" className="min-h-screen text-white" style={{ background: cfg.pageBg }}>
      {/* ── Header ── */}
      <header className="sticky top-0 z-40" style={{ background: "rgba(3,5,3,0.94)", backdropFilter: "blur(10px)" }}>
        <div className="max-w-6xl mx-auto px-4 lg:px-8 h-14 flex items-center justify-between">
          <button
            type="button"
            onClick={goBack}
            aria-label="Go back"
            data-testid="checkout-back-btn"
            className="w-9 h-9 -ml-2 flex items-center justify-center text-white/80 hover:text-white transition-colors"
          >
            <ArrowLeft className="w-5 h-5" strokeWidth={2.4} />
          </button>
          <Link
            to="/"
            data-testid="checkout-logo-home-link"
            className="font-barlow font-black text-white text-xl tracking-[0.1em] select-none"
          >
            SCOUT
            <span className="px-[4px] mx-[1px]" style={{ background: LIME, color: "#0A0F0D" }}>ME</span>
            PLAY
          </Link>
          <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-[0.18em] font-bold text-white/60">
            <Lock className="w-3 h-3" style={{ color: accent }} />
            Secure
          </div>
        </div>
        <div className="h-[2px] w-full" style={{ background: `linear-gradient(90deg, ${accent} 0%, ${accent}66 45%, transparent 90%)` }} />
      </header>

      <main className="max-w-6xl mx-auto px-4 lg:px-8 pt-8 lg:pt-12 pb-10 lg:grid lg:grid-cols-[1.02fr_0.98fr] lg:gap-12 lg:items-start">
        {/* ── Brand top: kicker + headline + hero + sub ── */}
        <section className="lg:col-start-1 lg:row-start-1">
          <p data-testid="checkout-kicker" className="text-[11px] md:text-xs font-extrabold uppercase tracking-[0.26em]" style={{ color: accent }}>
            {cfg.kicker}
          </p>
          <h1 data-testid="checkout-headline" className="mt-3 font-barlow font-black uppercase leading-[0.94] tracking-tight text-4xl sm:text-5xl lg:text-6xl">
            {cfg.h1.map((line, i) => (
              <span key={i} className="block" style={line.accent ? { color: accent } : undefined}>
                {line.t}
                {line.t === cfg.underlineWord && (
                  <span aria-hidden className="block h-[6px] mt-1.5 rounded-full max-w-[230px]" style={{ background: accent, opacity: 0.9 }} />
                )}
              </span>
            ))}
          </h1>

          <div className="relative mt-6 rounded-2xl overflow-hidden max-w-[430px]" style={{ border: `1px solid ${accent}30` }}>
            <img
              src={cfg.hero}
              alt=""
              data-testid="checkout-hero-img"
              className="w-full object-cover"
              style={{ aspectRatio: "4/4.4" }}
              loading="eager"
            />
            <div aria-hidden className="absolute inset-0" style={{ background: "linear-gradient(to top, rgba(3,5,3,0.85) 0%, transparent 35%), linear-gradient(to bottom, rgba(3,5,3,0.5) 0%, transparent 25%)" }} />
            <p data-testid="checkout-sub" className="absolute bottom-4 left-4 right-4 text-[15px] leading-snug text-white/90 font-medium">
              {cfg.sub[0]}
              <span className="font-bold" style={{ color: accent }}>{cfg.sub[1]}</span>
            </p>
          </div>
        </section>

        {/* ── Payment card (mobile: right after hero; desktop: right column) ── */}
        <section className="lg:col-start-2 lg:row-start-1 lg:row-span-2 mt-8 lg:mt-0 lg:sticky lg:top-20">
          <div
            data-testid="checkout-payment-card"
            className="rounded-[24px] p-5 md:p-6 text-[#12160F]"
            style={{ background: "#F6F3EA", boxShadow: "0 30px 80px -28px rgba(0,0,0,0.75)", border: `1px solid ${accent}40` }}
          >
            {/* Product summary */}
            <div className={tier === "single" ? "text-center" : ""}>
              {tier === "single" && (
                <span className="inline-flex w-14 h-14 rounded-full items-center justify-center mb-3" style={{ background: `${accent}2E`, border: `2px solid ${accent}` }}>
                  <FileCheck2 className="w-6 h-6 text-[#39420F]" strokeWidth={2} />
                </span>
              )}
              <div className={`flex items-center gap-2 ${tier === "single" ? "justify-center" : ""}`}>
                <h2 data-testid="checkout-product-name" className="font-bold text-xl md:text-2xl tracking-tight">
                  {cfg.product.name}
                </h2>
                {cfg.product.crown && (
                  <span className="w-8 h-8 rounded-full flex items-center justify-center" style={{ border: `1.5px solid ${GOLD}`, background: "#FCF6E6" }}>
                    <Crown className="w-4 h-4" style={{ color: "#B8860B" }} fill="#F5C443" />
                  </span>
                )}
              </div>
              {cfg.product.subline && (
                <div className="mt-1 text-[11px] font-bold uppercase tracking-[0.2em] text-[#12160F]/55">{cfg.product.subline}</div>
              )}
              <div className={`mt-2 flex items-end gap-2 ${tier === "single" ? "justify-center" : ""}`}>
                <div data-testid="checkout-price" className="font-barlow font-black leading-none text-5xl md:text-[54px] tracking-tight">
                  {priceStr}
                </div>
                <div className="pb-1 text-[12px] font-bold text-[#12160F]/60 leading-tight uppercase">
                  USD<br />{cfg.product.per}
                </div>
              </div>
              {reportId && user && (
                <div className="mt-2 text-[12px] font-semibold text-[#12160F]/60">Unlocks the full report for this match.</div>
              )}
              <div
                data-testid="checkout-price-chip"
                className={`mt-3 inline-flex items-start gap-2 rounded-xl px-3.5 py-2.5 text-[13px] font-semibold text-left ${tier === "single" ? "mx-auto" : ""}`}
                style={{ background: tier === "vip" ? "#F7ECD2" : "#EBF5C8", border: `1px solid ${tier === "vip" ? "#E4CD96" : "#D3E693"}` }}
              >
                <ChipIcon className="w-4 h-4 mt-[1px] shrink-0" style={{ color: tier === "vip" ? "#B8860B" : "#5A7A12" }} />
                <span>{cfg.product.chip}</span>
              </div>
              {cfg.product.desc && (
                <p className="mt-3 text-[14px] text-[#12160F]/75 leading-snug">{cfg.product.desc}</p>
              )}
            </div>

            {/* Secure divider */}
            <div className="mt-5 mb-1 flex items-center gap-3">
              <span className="flex-1 h-px bg-[#12160F]/12" />
              <span className="inline-flex items-center gap-1.5 text-[10px] font-extrabold uppercase tracking-[0.24em] text-[#12160F]/55">
                Secure <Lock className="w-3 h-3" /> Checkout
              </span>
              <span className="flex-1 h-px bg-[#12160F]/12" />
            </div>

            {/* Stripe embedded form / states */}
            {state === "loading" && (
              <div data-testid="checkout-loading" className="py-14 text-center">
                <div className="relative w-14 h-14 mx-auto flex items-center justify-center">
                  <span className="absolute inset-0 rounded-full border-2 animate-spin" style={{ borderColor: `${accent}40`, borderTopColor: tier === "vip" ? GOLD : "#5A7A12" }} />
                  <Lock className="w-5 h-5 text-[#12160F]/70" />
                </div>
                <p className="mt-4 text-sm font-semibold text-[#12160F]/60 inline-flex items-center gap-1.5">
                  <Loader2 className="w-3.5 h-3.5 animate-spin" /> Preparing your secure checkout…
                </p>
              </div>
            )}

            {state === "already-subscribed" && (
              <div data-testid="checkout-already-subscribed" className="py-10 text-center">
                <BadgeCheck className="w-10 h-10 mx-auto" style={{ color: "#5A7A12" }} />
                <h3 className="mt-3 font-barlow font-black uppercase text-xl">You're already subscribed</h3>
                <p className="mt-1 text-sm text-[#12160F]/65">Manage or change your plan from your dashboard.</p>
                <Link
                  to="/dashboard"
                  data-testid="checkout-go-dashboard-btn"
                  className="mt-5 inline-flex items-center gap-2 bg-[#12402A] hover:bg-[#1B5A3C] text-white font-barlow font-black uppercase tracking-widest text-xs px-6 py-3 rounded-full transition-colors"
                >
                  Go to dashboard <ArrowRight className="w-4 h-4" />
                </Link>
              </div>
            )}

            {state === "error" && (
              <div data-testid="checkout-error" className="py-10 text-center">
                <AlertCircle className="w-10 h-10 mx-auto text-orange-500" />
                <h3 className="mt-3 font-barlow font-black uppercase text-xl">Couldn't open checkout</h3>
                <p data-testid="checkout-error-message" className="mt-1 text-sm text-[#12160F]/65 max-w-xs mx-auto">{errorMessage}</p>
                <button
                  type="button"
                  onClick={() => window.location.reload()}
                  data-testid="checkout-error-retry"
                  className="mt-5 inline-flex items-center gap-2 bg-[#12402A] hover:bg-[#1B5A3C] text-white font-barlow font-black uppercase tracking-widest text-xs px-6 py-3 rounded-full transition-colors"
                >
                  Try again
                </button>
              </div>
            )}

            {(state === "ready" || state === "confirming") && clientSecret && stripePromise && (
              <div data-testid="checkout-stripe-wrapper" className="relative rounded-2xl overflow-hidden" style={{ minHeight: 480 }}>
                <EmbeddedCheckoutProvider stripe={stripePromise} options={checkoutOptions}>
                  <EmbeddedCheckout />
                </EmbeddedCheckoutProvider>
                {state === "confirming" && (
                  <div data-testid="checkout-confirming-overlay" className="absolute inset-0 z-10 flex flex-col items-center justify-center" style={{ background: "rgba(246,243,234,0.94)" }}>
                    <Loader2 className="w-8 h-8 animate-spin" style={{ color: "#12402A" }} />
                    <p className="mt-3 text-sm font-bold uppercase tracking-widest text-[#12160F]/70">Confirming your payment…</p>
                  </div>
                )}
              </div>
            )}

            {cfg.scriptLine && state !== "already-subscribed" && (
              <div data-testid="checkout-script-line" className="mt-4 text-center">
                <div className="text-[22px] leading-none text-[#12160F]/70" style={{ fontFamily: "'Caveat', cursive" }}>
                  Your dream is real.
                </div>
                <div className="mt-1 text-[11px] font-extrabold uppercase tracking-[0.26em] text-[#12160F]/80 inline-flex items-center gap-1.5">
                  We help you get there. <Heart className="w-3 h-3" style={{ color: "#8CA31A" }} fill="#CCFF00" />
                </div>
              </div>
            )}
          </div>
        </section>

        {/* ── Brand rest: benefits, plan summary, testimonial / upsell ── */}
        <section className="lg:col-start-1 lg:row-start-2 mt-10 lg:mt-10">
          {cfg.sectionTitle && (
            <h2 className="font-barlow font-black uppercase tracking-[0.14em] text-white text-base md:text-lg">{cfg.sectionTitle}</h2>
          )}

          {/* Single + Premium: stacked benefit rows */}
          {cfg.benefits && (
            <div className={`${cfg.sectionTitle ? "mt-4" : ""} space-y-3`}>
              {cfg.benefits.map((b, i) => {
                const BIcon = b.icon;
                return (
                  <div
                    key={b.title}
                    data-testid={`checkout-benefit-${i}`}
                    className="flex items-start gap-4 rounded-2xl px-4 py-4"
                    style={{ background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.08)" }}
                  >
                    <span className="w-11 h-11 rounded-full flex items-center justify-center shrink-0" style={{ border: `1.5px solid ${accent}`, background: `${accent}12` }}>
                      <BIcon className="w-5 h-5" style={{ color: accent }} strokeWidth={1.9} />
                    </span>
                    <div>
                      <div className="font-barlow font-black uppercase tracking-wide text-[15px]" style={{ color: tier === "premium" ? accent : "#FFFFFF" }}>{b.title}</div>
                      <div className="mt-0.5 text-[13.5px] leading-snug text-white/75">{b.desc}</div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}

          {/* VIP: 3-up icon grid */}
          {cfg.benefitsGrid && (
            <div className="grid grid-cols-3 gap-3">
              {cfg.benefitsGrid.map((b, i) => {
                const BIcon = b.icon;
                return (
                  <div key={b.title} data-testid={`checkout-benefit-${i}`} className="text-center px-1">
                    <BIcon className="w-7 h-7 mx-auto" style={{ color: accent }} strokeWidth={1.7} />
                    <div className="mt-2 font-barlow font-black uppercase tracking-wide text-[12px] text-white">{b.title}</div>
                    <div className="mt-1 text-[11.5px] leading-snug text-white/65">{b.desc}</div>
                  </div>
                );
              })}
            </div>
          )}

          {/* Plan summary box (premium / vip) */}
          {cfg.plan && (
            <div
              data-testid="checkout-plan-summary"
              className="mt-6 rounded-2xl p-5"
              style={{ border: `1.5px solid ${accent}66`, background: "rgba(255,255,255,0.03)" }}
            >
              <div className="text-[12px] font-extrabold uppercase tracking-[0.22em]" style={{ color: accent }}>{cfg.plan.name}</div>
              <div className="mt-1.5 flex items-baseline gap-2">
                <span className="font-barlow font-black text-4xl md:text-[44px] leading-none" style={{ color: tier === "vip" ? accent : "#FFFFFF" }}>
                  ${Number(prices[tier]).toFixed(2)}
                </span>
                <span className="text-sm font-bold text-white/70 uppercase">/ month</span>
              </div>
              <div className="mt-4 h-px" style={{ background: `${accent}30` }} />
              <ul className="mt-4 space-y-2.5">
                {cfg.plan.features.map((f, i) => (
                  <li key={f} data-testid={`checkout-plan-feature-${i}`} className="flex items-start gap-2.5 text-[14px] text-white/90">
                    <AccentCheck /> {f}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Single: testimonial */}
          {cfg.testimonial && (
            <div
              data-testid="checkout-testimonial"
              className="mt-6 rounded-2xl p-5"
              style={{ border: `1.5px solid ${accent}45`, background: "rgba(255,255,255,0.03)" }}
            >
              <div className="flex items-center gap-2.5">
                <Heart className="w-6 h-6" style={{ color: accent, filter: `drop-shadow(0 0 6px ${accent}80)` }} strokeWidth={1.8} />
                <div className="font-barlow font-black uppercase tracking-wide text-[14px]" style={{ color: accent }}>{cfg.testimonial.title}</div>
              </div>
              <p className="mt-3 text-[14.5px] leading-relaxed text-white/85 italic">{cfg.testimonial.quote}</p>
              <div className="mt-3 flex items-center gap-1" aria-label="5 out of 5 stars">
                {[0, 1, 2, 3, 4].map((i) => (
                  <Star key={i} className="w-4 h-4" style={{ color: "#F5C443" }} fill="#F5C443" />
                ))}
              </div>
              <div className="mt-1.5 text-[12.5px] text-white/60">{cfg.testimonial.by}</div>
            </div>
          )}

          {/* Premium: VIP upsell */}
          {cfg.upsell && (
            <div
              className="mt-5 rounded-2xl p-5 flex items-start gap-4"
              style={{ border: `1.5px solid ${GOLD}55`, background: "rgba(245,196,67,0.05)" }}
            >
              <Crown className="w-7 h-7 shrink-0" style={{ color: GOLD }} strokeWidth={1.7} />
              <div>
                <div className="font-barlow font-black uppercase tracking-wide text-[14px]" style={{ color: GOLD }}>{cfg.upsell.title}</div>
                <div className="mt-0.5 text-[13px] text-white/75">{cfg.upsell.sub}</div>
                <Link
                  to={cfg.upsell.to}
                  data-testid="checkout-vip-upsell-link"
                  className="mt-2 inline-flex items-center gap-1 text-[13px] font-bold underline underline-offset-4"
                  style={{ color: "#8AB4F8" }}
                >
                  {cfg.upsell.linkText} <ChevronRight className="w-3.5 h-3.5" />
                </Link>
              </div>
            </div>
          )}

          {/* VIP: promo box */}
          {cfg.promo && (
            <div
              data-testid="checkout-vip-promo"
              className="mt-5 rounded-2xl p-5 flex items-center gap-4"
              style={{ border: `1.5px solid ${accent}55`, background: "rgba(245,196,67,0.05)" }}
            >
              <span className="w-12 h-12 rounded-full flex items-center justify-center shrink-0" style={{ border: `1.5px solid ${accent}`, boxShadow: `0 0 14px ${accent}40` }}>
                <Crown className="w-5 h-5" style={{ color: accent }} strokeWidth={1.8} />
              </span>
              <div className="flex-1">
                <div className="font-barlow font-black uppercase tracking-wide text-[14px] text-white">{cfg.promo.title}</div>
                <div className="mt-0.5 text-[13px] text-white/70">{cfg.promo.sub}</div>
              </div>
              <ChevronRight className="w-5 h-5 text-white/50 shrink-0" />
            </div>
          )}

          {/* Single: trust row */}
          {cfg.trustRow && (
            <div data-testid="checkout-trust-row" className="mt-7 grid grid-cols-3 gap-3">
              {cfg.trustRow.map((t) => {
                const TIcon = t.icon;
                return (
                  <div key={t.title} className="text-center">
                    <TIcon className="w-6 h-6 mx-auto" style={{ color: accent }} strokeWidth={1.8} />
                    <div className="mt-1.5 font-barlow font-black uppercase tracking-wide text-[11.5px] text-white">{t.title}</div>
                    <div className="text-[11px] text-white/60">{t.sub}</div>
                  </div>
                );
              })}
            </div>
          )}

          {/* Premium: bottom line */}
          {cfg.bottomLine && (
            <p className="mt-8 text-center lg:text-left text-[12px] font-extrabold uppercase tracking-[0.2em] text-white/80">
              {cfg.bottomLine[0]}
              <span style={{ color: accent }}>{cfg.bottomLine[1]}</span>
            </p>
          )}
        </section>
      </main>

      {/* ── Footer trust band ── */}
      <footer
        data-testid="checkout-footer-trust"
        className="mt-4 pb-24 md:pb-8 pt-5"
        style={{ borderTop: `2px solid ${accent}`, background: "#040504" }}
      >
        <div className="max-w-6xl mx-auto px-4 lg:px-8 flex items-center gap-3.5">
          <span className="w-11 h-11 rounded-xl flex items-center justify-center shrink-0" style={{ background: `${accent}18`, border: `1.5px solid ${accent}` }}>
            <ShieldCheck className="w-5 h-5" style={{ color: accent }} strokeWidth={1.9} />
          </span>
          <div>
            <div className="text-[11px] font-extrabold uppercase tracking-[0.22em]" style={{ color: accent }}>
              Secure payment · Powered by Stripe
            </div>
            <div className="mt-0.5 text-[12.5px] text-white/65">{cfg.footerSub}</div>
          </div>
        </div>
      </footer>
    </div>
  );
}
