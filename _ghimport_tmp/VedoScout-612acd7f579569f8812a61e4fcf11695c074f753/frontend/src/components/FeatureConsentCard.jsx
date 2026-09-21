import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import { Megaphone, CheckCircle2, Loader2 } from "lucide-react";
import { Link } from "react-router-dom";
import api from "@/lib/api";

export default function FeatureConsentCard() {
  const [status, setStatus] = useState(null); // 'granted' | 'withdrawn' | null
  const [loaded, setLoaded] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api.get("/account/feature-consent")
      .then(({ data }) => setStatus(data.status || null))
      .catch(() => { /* silent */ })
      .finally(() => setLoaded(true));
  }, []);

  const isOn = status === "granted";

  const toggle = async () => {
    setSaving(true);
    try {
      const next = !isOn;
      await api.put("/account/feature-consent", { granted: next });
      setStatus(next ? "granted" : "withdrawn");
      toast.success(next
        ? "Awesome — your intro clips can now be featured on our socials!"
        : "Consent withdrawn — we won't share any new clips.");
    } catch {
      toast.error("Could not save your choice. Please try again.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <section data-testid="feature-consent-card" className="mt-10 border border-ink/10 bg-cream-card overflow-hidden">
      <div className="flex items-center justify-between gap-4 px-6 md:px-8 py-5 border-b border-ink/10 bg-cream-base/40">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 border-2 border-forest flex items-center justify-center">
            <Megaphone className="w-5 h-5 text-forest" strokeWidth={2} />
          </div>
          <div>
            <div className="text-[10px] uppercase tracking-[0.24em] font-black text-forest">Get featured</div>
            <h3 className="font-barlow font-black uppercase text-xl md:text-2xl tracking-tight leading-none mt-0.5">
              Share the spotlight
            </h3>
          </div>
        </div>
        {isOn && (
          <span data-testid="feature-consent-status" className="hidden sm:inline-flex items-center gap-1.5 text-[11px] uppercase tracking-[0.16em] font-black text-forest-pop">
            <CheckCircle2 className="w-3.5 h-3.5" /> Featured: ON
          </span>
        )}
      </div>

      <div className="px-6 md:px-8 py-6 flex items-start justify-between gap-4">
        <div className="max-w-xl">
          <p className="text-sm text-ink/75 leading-relaxed">
            {isOn ? (
              <>Your player's <strong>cinematic intro clips</strong> may be featured on ScoutMePlay's
              Instagram &amp; Facebook — celebrating real players and inspiring the next ones. You can
              switch this off anytime; we'll stop sharing new clips immediately.</>
            ) : (
              <>Turn this on to let ScoutMePlay feature your player's <strong>cinematic intro clip</strong> on
              our Instagram &amp; Facebook. It feels like being scouted for the highlight reel — and it's
              100% optional.</>
            )}
          </p>
          <p className="mt-2 text-[11.5px] text-ink/50 leading-snug">
            Applies only to uploads where you also ticked the consent box. Withdrawing stops all future
            sharing — and we'll remove existing posts on request. For players under 18 this consent is
            given by the parent/guardian account holder. See our{" "}
            <Link to="/privacy" className="underline text-forest" data-testid="feature-consent-privacy-link">Privacy Policy</Link>.
          </p>
        </div>

        {loaded ? (
          <button
            type="button"
            role="switch"
            aria-checked={isOn}
            onClick={toggle}
            disabled={saving}
            data-testid="feature-consent-toggle"
            className={`shrink-0 relative w-14 h-8 border-2 transition-colors ${isOn ? "bg-forest border-forest" : "bg-cream-base border-ink/20"}`}
          >
            <span className={`absolute top-0.5 left-0.5 w-6 h-6 bg-white transition-transform ${isOn ? "translate-x-6" : "translate-x-0"}`} />
          </button>
        ) : (
          <Loader2 className="w-5 h-5 animate-spin text-ink/30 shrink-0" />
        )}
      </div>
    </section>
  );
}
