// Exit-intent offer — a time-limited discount popup shown once when a visitor
// who has seen the pricing section is about to leave. Fully admin-configured
// (enabled, %, countdown, headline) and claimable pre-signup: the claimed code
// attaches to the account after signup/login and prices the first report.
import React, { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { X, Timer, Zap } from "lucide-react";
import api from "@/lib/api";
import { useAuth } from "@/lib/auth-context";

export function ExitIntentPopup({ config, isLoggedIn = false, onClose, preview = false }) {
  const [left, setLeft] = useState((config?.countdown_minutes || 15) * 60);
  const [busy, setBusy] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    const t = setInterval(() => setLeft((s) => (s > 0 ? s - 1 : 0)), 1000);
    return () => clearInterval(t);
  }, []);

  const mm = String(Math.floor(left / 60)).padStart(2, "0");
  const ss = String(left % 60).padStart(2, "0");
  const pct = Math.round(config?.percent || 10);

  const claim = async () => {
    if (preview) {
      toast.info("Preview only — visitors get a real claim here.");
      return;
    }
    setBusy(true);
    try {
      const { data } = await api.post("/exit-offer/claim");
      localStorage.setItem("smp_exit_offer", JSON.stringify({ code: data.code, percent: data.percent, expires_at: data.expires_at }));
      if (isLoggedIn) {
        try {
          await api.post("/exit-offer/attach", { code: data.code });
          localStorage.removeItem("smp_exit_offer");
        } catch { /* attaches on next login instead */ }
      }
      toast.success(`${Math.round(data.percent)}% discount locked in — it applies automatically at checkout!`);
      onClose?.();
      navigate("/upload");
    } catch {
      toast.error("Could not claim the offer right now.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 z-[120] flex items-center justify-center p-4 bg-[#0B1F14]/70 backdrop-blur-sm" data-testid="exit-offer-popup">
      <div className="relative w-full max-w-[440px] bg-[#FBF9F3] border border-[#E5DFCE] rounded-[22px] shadow-2xl overflow-hidden">
        <div className="h-1.5 w-full" style={{ background: "linear-gradient(90deg,#CCFF00,#1F4F2F)" }} />
        <button
          type="button"
          onClick={onClose}
          aria-label="Close offer"
          data-testid="exit-offer-close"
          className="absolute top-3.5 right-3.5 w-8 h-8 rounded-full bg-[#12211A]/8 hover:bg-[#12211A]/15 flex items-center justify-center text-[#12211A] transition-colors"
        >
          <X className="w-4 h-4" />
        </button>
        <div className="p-6 md:p-7 text-center">
          <span className="inline-flex items-center gap-1.5 bg-[#12211A] text-[#CCFF00] text-[10px] font-extrabold tracking-[0.14em] uppercase px-3 py-1.5 rounded-full">
            <Zap className="w-3 h-3" /> One-time offer
          </span>
          <h3 className="font-barlow font-black uppercase text-[26px] md:text-[30px] leading-[1.02] text-[#101B12] mt-3.5" data-testid="exit-offer-headline">
            {config?.headline || "Wait — see what the video says first"}
          </h3>
          <div className="mt-4 flex items-center justify-center gap-3">
            <span className="font-barlow font-black text-[54px] leading-none text-[#1F4F2F]">{pct}%</span>
            <span className="text-left text-[13px] font-bold text-[#3C4A40] leading-tight">off your<br />player report</span>
          </div>
          <div className="mt-4 inline-flex items-center gap-2 bg-white border border-[#E5DFCE] rounded-full px-4 py-2" data-testid="exit-offer-countdown">
            <Timer className="w-4 h-4 text-[#D9534F]" />
            <span className="text-[12px] font-bold text-[#3C4A40]">Offer expires in</span>
            <span className="font-barlow font-black text-[18px] tabular-nums text-[#D9534F]">{mm}:{ss}</span>
          </div>
          <button
            type="button"
            onClick={claim}
            disabled={busy || left === 0}
            data-testid="exit-offer-claim"
            className="mt-5 w-full bg-[#1F4F2F] hover:bg-[#173B26] text-white font-barlow font-black uppercase tracking-[0.08em] text-[15px] py-4 rounded-xl transition-colors disabled:opacity-50"
          >
            {left === 0 ? "Offer expired" : `Claim ${pct}% & start now`}
          </button>
          <p className="mt-2.5 text-[11.5px] text-[#75816F]">
            Applies automatically at checkout on your first report. No code needed.
          </p>
          <button type="button" onClick={onClose} data-testid="exit-offer-dismiss" className="mt-2 text-[12px] font-semibold text-[#8B957F] hover:text-[#3C4A40] transition-colors">
            No thanks, I&apos;ll pay full price
          </button>
        </div>
      </div>
    </div>
  );
}

export default function ExitIntentManager() {
  const { user } = useAuth();
  const [config, setConfig] = useState(null);
  const [show, setShow] = useState(false);
  const seenPricing = useRef(false);

  useEffect(() => {
    api.get("/exit-offer/config").then(({ data }) => setConfig(data)).catch(() => {});
  }, []);

  useEffect(() => {
    if (!config?.enabled) return undefined;
    if (user?.role === "admin") return undefined;
    if (sessionStorage.getItem("smp_exit_shown")) return undefined;

    const pricingEl = document.getElementById("pricing-section");
    const io = pricingEl
      ? new IntersectionObserver((es) => {
          if (es.some((e) => e.isIntersecting)) seenPricing.current = true;
        }, { threshold: 0.2 })
      : null;
    if (io && pricingEl) io.observe(pricingEl);

    const trigger = () => {
      if (!seenPricing.current) return;
      if (sessionStorage.getItem("smp_exit_shown")) return;
      sessionStorage.setItem("smp_exit_shown", "1");
      setShow(true);
    };
    const onMouseOut = (e) => {
      if (!e.relatedTarget && e.clientY <= 0) trigger();
    };
    let anchorY = window.scrollY;
    let anchorT = Date.now();
    const onScroll = () => {
      const y = window.scrollY;
      const t = Date.now();
      if (y > anchorY || t - anchorT > 800) {
        anchorY = y;
        anchorT = t;
        return;
      }
      if (anchorY - y > 450) trigger();
    };
    document.addEventListener("mouseout", onMouseOut);
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => {
      document.removeEventListener("mouseout", onMouseOut);
      window.removeEventListener("scroll", onScroll);
      io?.disconnect();
    };
  }, [config, user]);

  if (!config?.enabled || !show) return null;
  return <ExitIntentPopup config={config} isLoggedIn={!!user} onClose={() => setShow(false)} />;
}
