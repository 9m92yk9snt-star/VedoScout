/**
 * ReportPaywallTiers — compact 3-tier paywall used INSIDE the locked report
 * overlay (post-preview). Mirrors the front-page PricingTiers offer (Single /
 * Premium / VIP) so the pricing model is identical everywhere. "Free" is
 * intentionally omitted — the visitor is already looking at their free preview.
 *
 * Prices come live from /settings/price (admin-editable):
 *   single_price · premium_price · vip_price · premium_extra_price · vip_extra_price
 *
 * CTAs:
 *   Single  → onUnlockSingle() — opens the existing embedded checkout that
 *             unlocks THIS report (charged at single_price).
 *   Premium → POST /payments/subscribe { tier:"premium" } → Stripe redirect
 *   VIP     → POST /payments/subscribe { tier:"vip" }     → Stripe redirect
 */
import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { Check, Star, Crown, ArrowRight, Loader2, FileCheck2, TrendingUp, ShieldCheck, Lock } from "lucide-react";
import api from "@/lib/api";
import { trackInitiateCheckout } from "@/lib/pixels";

function fmtPrice(v) {
  if (v == null || Number.isNaN(Number(v))) return "—";
  const n = Number(v);
  return Number.isInteger(n) ? `$${n}` : `$${n.toFixed(2)}`;
}

const Feat = ({ children, highlight = false, dark = false }) => (
  <li className="flex items-start gap-2 text-[13px]">
    {highlight
      ? <Star className={`w-3.5 h-3.5 mt-0.5 flex-shrink-0 ${dark ? "text-[#F5C443]" : "text-forest"}`} fill="currentColor" strokeWidth={2.5} />
      : <Check className={`w-3.5 h-3.5 mt-0.5 flex-shrink-0 ${dark ? "text-[#F5C443]/80" : "text-forest"}`} strokeWidth={2} />}
    <span className={dark ? "text-white/90" : "text-ink/85"}>{children}</span>
  </li>
);

export default function ReportPaywallTiers({ isLoggedIn = false, onUnlockSingle, singleTitle = "Unlock this report", playerName = "" }) {
  const pFirst = String(playerName || "").trim().split(" ")[0];
  const navigate = useNavigate();
  const [busyTier, setBusyTier] = useState(null);
  const [prices, setPrices] = useState({ single: null, premium: null, vip: null, premiumExtra: null, vipExtra: null });

  useEffect(() => {
    let alive = true;
    api.get("/settings/price")
      .then(({ data }) => {
        if (!alive) return;
        setPrices({
          single: Number(data.single_price) || 129,
          premium: Number(data.premium_price) || 29.99,
          vip: Number(data.vip_price) || 49.99,
          premiumExtra: Number(data.premium_extra_price) || 89,
          vipExtra: Number(data.vip_extra_price) || 59,
        });
      })
      .catch(() => {});
    return () => { alive = false; };
  }, []);

  const handleSingle = () => {
    if (!isLoggedIn) { navigate("/signup?plan=single&next=/dashboard"); return; }
    if (onUnlockSingle) onUnlockSingle();
  };

  const startSubscription = async (tier) => {
    if (!isLoggedIn) { navigate(`/signup?plan=${tier}&next=/?subscribe=${tier}`); return; }
    if (busyTier) return;
    setBusyTier(tier);
    try {
      const { data } = await api.post("/payments/subscribe", { tier, origin_url: window.location.origin });
      if (!data?.url) throw new Error("No checkout URL received");
      trackInitiateCheckout();
      window.location.href = data.url;
    } catch (err) {
      toast.error(err?.response?.data?.detail || err.message || "Could not start checkout.", { duration: 8000 });
      setBusyTier(null);
    }
  };

  const CtaBtn = ({ testid, onClick, loading, children, dark = false }) => (
    <button
      type="button"
      data-testid={testid}
      onClick={onClick}
      disabled={!!busyTier}
      className={`mt-5 w-full font-barlow font-black uppercase tracking-widest text-sm py-3.5 flex items-center justify-center gap-2 transition-all group/btn disabled:opacity-60 ${
        dark ? "bg-[#F5C443] hover:bg-white text-[#0A0F0D]" : "bg-forest hover:bg-forest-pop text-white"
      }`}
    >
      {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : (
        <>
          {children}
          <ArrowRight className="w-4 h-4 transition-transform group-hover/btn:translate-x-1" />
        </>
      )}
    </button>
  );

  return (
    <div data-testid="report-paywall-tiers">
      <div className="grid md:grid-cols-3 gap-4 md:gap-5 items-stretch">
        {/* ── Single Report ─────────────────────────────── */}
        <div data-testid="paywall-card-single" className="relative p-6 flex flex-col h-full border border-gray-border bg-cream-card hover:border-forest transition-colors">
          <div className="flex items-center gap-2 mb-2">
            <FileCheck2 className="w-4 h-4 text-forest" strokeWidth={1.8} />
            <span className="text-[10px] uppercase tracking-[0.25em] font-bold text-forest">Single report</span>
          </div>
          <h4 className="font-barlow font-black uppercase text-2xl tracking-tight text-ink leading-none">{singleTitle}</h4>
          <div className="mt-4 flex items-baseline gap-2">
            <span className="font-barlow font-black text-4xl md:text-5xl text-forest leading-none">{fmtPrice(prices.single)}</span>
            <span className="text-ink/50 uppercase tracking-widest font-bold text-xs">one-time</span>
          </div>
          <ul className="mt-5 space-y-2 flex-1">
            <Feat>Full 4-pillar premium report</Feat>
            <Feat highlight>Real scout review within 48h</Feat>
            <Feat>Timestamped key moments</Feat>
            <Feat>7 / 30 / 90-day training plan</Feat>
            <Feat>Downloadable PDF report</Feat>
          </ul>
          <CtaBtn testid="paywall-single-cta" onClick={handleSingle}>{pFirst ? `Unlock ${pFirst}'s full report` : "Unlock now"}</CtaBtn>
        </div>

        {/* ── Premium (most popular) ────────────────────── */}
        <div data-testid="paywall-card-premium" className="relative p-6 flex flex-col h-full border-2 border-forest bg-cream-card transition-colors">
          <div className="absolute -top-3 left-1/2 -translate-x-1/2 bg-forest text-white text-[10px] uppercase tracking-[0.22em] font-black px-3 py-1 whitespace-nowrap">
            Most popular
          </div>
          <div className="flex items-center gap-2 mb-2 mt-1">
            <TrendingUp className="w-4 h-4 text-forest" strokeWidth={1.8} />
            <span className="text-[10px] uppercase tracking-[0.25em] font-bold text-forest">Premium</span>
          </div>
          <h4 className="font-barlow font-black uppercase text-2xl tracking-tight text-ink leading-none">Train &amp; track monthly</h4>
          <div className="mt-4 flex items-baseline gap-2">
            <span className="font-barlow font-black text-4xl md:text-5xl text-forest leading-none">{fmtPrice(prices.premium)}</span>
            <span className="text-ink/50 uppercase tracking-widest font-bold text-xs">/ month</span>
          </div>
          <ul className="mt-5 space-y-2 flex-1">
            <Feat>2 video reports every month</Feat>
            <Feat>Instant analysis — no waiting</Feat>
            <Feat>Progress tracking over time</Feat>
            <Feat>Personal development plan</Feat>
            <Feat>Visible in the scout database</Feat>
            <Feat>Extra reports at {fmtPrice(prices.premiumExtra)}</Feat>
          </ul>
          <CtaBtn testid="paywall-premium-cta" onClick={() => startSubscription("premium")} loading={busyTier === "premium"}>Go Premium</CtaBtn>
        </div>

        {/* ── VIP ───────────────────────────────────────── */}
        <div data-testid="paywall-card-vip" className="relative p-6 flex flex-col h-full border border-[#F5C443]/50 bg-[#0A0F0D] text-white transition-colors">
          <div className="flex items-center gap-2 mb-2">
            <Crown className="w-4 h-4 text-[#F5C443]" strokeWidth={1.8} />
            <span className="text-[10px] uppercase tracking-[0.25em] font-bold text-[#F5C443]">VIP</span>
          </div>
          <h4 className="font-barlow font-black uppercase text-2xl tracking-tight leading-none">Maximum exposure</h4>
          <div className="mt-4 flex items-baseline gap-2">
            <span className="font-barlow font-black text-4xl md:text-5xl text-[#F5C443] leading-none">{fmtPrice(prices.vip)}</span>
            <span className="text-white/50 uppercase tracking-widest font-bold text-xs">/ month</span>
          </div>
          <ul className="mt-5 space-y-2 flex-1">
            <Feat dark>Everything in Premium</Feat>
            <Feat dark>4 video reports every month</Feat>
            <Feat dark highlight>Scout review on every report (48h)</Feat>
            <Feat dark>Direct contact with real scouts</Feat>
            <Feat dark>Extra reports at {fmtPrice(prices.vipExtra)}</Feat>
          </ul>
          <CtaBtn testid="paywall-vip-cta" onClick={() => startSubscription("vip")} loading={busyTier === "vip"} dark>Go VIP</CtaBtn>
        </div>
      </div>

      <div className="mt-5 grid sm:grid-cols-3 gap-3 text-xs text-ink/65">
        <div className="flex items-center justify-center sm:justify-start gap-2 border border-gray-border bg-cream-card/60 px-4 py-3">
          <ShieldCheck className="w-4 h-4 text-forest flex-shrink-0" />
          <span><span className="font-bold text-ink">48h scout review</span> guarantee</span>
        </div>
        <div className="flex items-center justify-center gap-2 border border-gray-border bg-cream-card/60 px-4 py-3">
          <Star className="w-4 h-4 text-forest flex-shrink-0" />
          <span>Cancel subscription <span className="font-bold text-ink">anytime</span></span>
        </div>
        <div className="flex items-center justify-center sm:justify-end gap-2 border border-gray-border bg-cream-card/60 px-4 py-3">
          <Lock className="w-4 h-4 text-forest flex-shrink-0" />
          <span>Secure <span className="font-bold text-ink">Stripe</span> checkout</span>
        </div>
      </div>
    </div>
  );
}
