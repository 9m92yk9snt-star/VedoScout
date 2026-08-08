// Sticky mobile CTA on the landing pricing section — text is admin-editable (Settings).
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowRight } from "lucide-react";
import api from "@/lib/api";

export default function StickyPricingCTA({ isLoggedIn = false }) {
  const [cfg, setCfg] = useState(null);
  const [visible, setVisible] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    api.get("/settings/sticky-cta")
      .then(({ data }) => setCfg(data))
      .catch(() => setCfg({ enabled: true, text: "Get My Report" }));
  }, []);

  useEffect(() => {
    if (!cfg?.enabled) return;
    const el = document.getElementById("pricing-section");
    if (!el) return;
    const obs = new IntersectionObserver(
      ([entry]) => setVisible(entry.isIntersecting),
      { rootMargin: "160px 0px 160px 0px", threshold: 0 }
    );
    obs.observe(el);
    return () => obs.disconnect();
  }, [cfg]);

  if (!cfg?.enabled) return null;

  const onClick = () => {
    if (isLoggedIn) navigate("/upload");
    else navigate("/signup?plan=single&next=/upload");
  };

  return (
    <div
      data-testid="sticky-pricing-cta-wrap"
      aria-hidden={!visible}
      className={`lg:hidden fixed bottom-[62px] md:bottom-0 inset-x-0 z-40 px-4 pb-2 md:pb-4 pt-10 transition-all duration-300 ${
        visible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-6 pointer-events-none"
      }`}
      style={{ background: "linear-gradient(to top, rgba(16,24,17,0.5) 30%, transparent)" }}
    >
      <button
        type="button"
        onClick={onClick}
        tabIndex={visible ? 0 : -1}
        data-testid="sticky-pricing-cta"
        className="w-full rounded-full bg-[#CCFF00] text-[#0A0F0D] font-barlow font-black uppercase tracking-[0.16em] text-[13.5px] py-3.5 flex items-center justify-center gap-2 shadow-[0_12px_32px_-8px_rgba(12,24,14,0.65)] active:scale-[0.98] transition-transform"
      >
        {cfg.text || "Get My Report"} <ArrowRight className="w-4 h-4" strokeWidth={2.6} />
      </button>
    </div>
  );
}
