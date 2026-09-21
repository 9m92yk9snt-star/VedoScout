import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Cookie, X, SlidersHorizontal } from "lucide-react";

const STORAGE_KEY = "smp_cookie_consent_v1";
// Detect consent storage. Returns null if user hasn't decided yet.
function readConsent() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object") return null;
    return parsed;
  } catch {
    return null;
  }
}

function writeConsent(value) {
  try {
    localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({ ...value, decided_at: new Date().toISOString(), version: 1 })
    );
    // Notify any listeners (e.g. analytics loader) that consent has changed.
    window.dispatchEvent(new CustomEvent("smp:cookie-consent", { detail: value }));
  } catch {
    /* localStorage may be unavailable in incognito */
  }
}

const DEFAULT_PREFS = {
  necessary: true, // always on, cannot be disabled
  analytics: false,
  marketing: false,
};

export default function CookieBanner() {
  // null = undecided, object = decided
  const [consent, setConsent] = useState(() => readConsent());
  const [customising, setCustomising] = useState(false);
  const [prefs, setPrefs] = useState(DEFAULT_PREFS);

  // Surface a small re-open button after acceptance (subtle, bottom-left)
  const [showReopen, setShowReopen] = useState(false);

  useEffect(() => {
    // On first paint, if consent exists, we don't show the banner — but
    // surface the small "Cookie settings" pill so users can revisit choices.
    if (consent) setShowReopen(true);
  }, [consent]);

  const acceptAll = () => {
    const all = { necessary: true, analytics: true, marketing: true };
    writeConsent(all);
    setConsent(all);
    setShowReopen(true);
  };

  const rejectAll = () => {
    const minimal = { necessary: true, analytics: false, marketing: false };
    writeConsent(minimal);
    setConsent(minimal);
    setShowReopen(true);
  };

  const savePrefs = () => {
    const next = { ...prefs, necessary: true };
    writeConsent(next);
    setConsent(next);
    setCustomising(false);
    setShowReopen(true);
  };

  const reopen = () => {
    setPrefs(consent || DEFAULT_PREFS);
    setCustomising(true);
  };

  // ─────────────────────────────────────────────
  // RENDER
  // ─────────────────────────────────────────────
  // If consent already given AND not customising, show only the small "Cookie settings" re-open chip
  if (consent && !customising) {
    return showReopen ? (
      <button
        type="button"
        onClick={reopen}
        data-testid="cookie-reopen"
        aria-label="Cookie settings"
        className="fixed bottom-5 left-5 z-40 w-10 h-10 md:w-11 md:h-11 flex items-center justify-center rounded-full border border-ink/15 bg-deepnavy/95 text-ink/55 hover:text-ink hover:border-forest transition-all shadow-sm backdrop-blur-sm"
      >
        <Cookie className="w-4 h-4 md:w-5 md:h-5" strokeWidth={1.8} />
      </button>
    ) : null;
  }

  // Customise modal
  if (customising) {
    return (
      <div
        data-testid="cookie-customise"
        className="fixed inset-0 z-[60] flex items-end md:items-center justify-center bg-ink/40 backdrop-blur-sm p-0 md:p-4"
      >
        <div
          className="w-full md:max-w-xl bg-deepnavy border-2 border-volt md:rounded-none shadow-2xl text-ink"
          role="dialog"
          aria-labelledby="cookie-customise-title"
        >
          <div className="flex items-start justify-between gap-4 px-6 pt-6 pb-4 border-b border-gray-border">
            <div>
              <div className="text-[10px] uppercase tracking-[0.28em] font-bold text-volt">
                Cookie preferences
              </div>
              <h2
                id="cookie-customise-title"
                className="mt-2 font-barlow font-black uppercase text-2xl tracking-tighter leading-tight"
              >
                Choose what data you allow.
              </h2>
            </div>
            <button
              type="button"
              onClick={() => setCustomising(false)}
              data-testid="cookie-customise-close"
              aria-label="Close"
              className="shrink-0 w-8 h-8 flex items-center justify-center border border-gray-border hover:border-forest text-ink/55 hover:text-ink transition"
            >
              <X className="w-4 h-4" />
            </button>
          </div>

          <div className="px-6 py-5 max-h-[60vh] overflow-y-auto space-y-4">
            <CookieRow
              testid="cookie-row-necessary"
              title="Strictly necessary"
              desc="Required for the site to work — secure checkout (Stripe), login session, language. Cannot be disabled."
              checked={true}
              disabled
              onChange={() => {}}
            />
            <CookieRow
              testid="cookie-row-analytics"
              title="Analytics"
              desc="Anonymous usage data (page views, scroll depth) that helps us improve the site. No personal information is collected."
              checked={prefs.analytics}
              onChange={(v) => setPrefs((p) => ({ ...p, analytics: v }))}
            />
            <CookieRow
              testid="cookie-row-marketing"
              title="Marketing"
              desc="Used to measure ad campaigns and tailor messages if you arrived via a referral or social link. Off by default."
              checked={prefs.marketing}
              onChange={(v) => setPrefs((p) => ({ ...p, marketing: v }))}
            />
          </div>

          <div className="px-6 py-4 border-t border-gray-border flex flex-col sm:flex-row gap-2.5">
            <button
              type="button"
              onClick={rejectAll}
              data-testid="cookie-customise-reject"
              className="flex-1 px-4 py-2.5 border border-gray-border bg-transparent text-ink/70 hover:text-ink hover:border-forest text-[11px] uppercase tracking-[0.18em] font-bold transition-colors"
            >
              Reject all
            </button>
            <button
              type="button"
              onClick={savePrefs}
              data-testid="cookie-customise-save"
              className="flex-1 px-4 py-2.5 bg-forest hover:bg-forest-pop text-white text-[11px] uppercase tracking-[0.18em] font-bold transition-colors"
            >
              Save preferences
            </button>
            <button
              type="button"
              onClick={acceptAll}
              data-testid="cookie-customise-accept-all"
              className="flex-1 px-4 py-2.5 bg-volt hover:bg-forest-pop text-white text-[11px] uppercase tracking-[0.18em] font-bold transition-colors"
            >
              Accept all
            </button>
          </div>
        </div>
      </div>
    );
  }

  // First-visit banner — compact, non-blocking card (mobile: slim card above
  // the bottom tabs; desktop: small card bottom-left). Never covers the page.
  return (
    <div
      data-testid="cookie-banner"
      className="fixed bottom-0 left-0 right-0 sm:right-auto sm:left-5 z-[70] px-3 sm:px-0 pointer-events-none"
      style={{
        paddingBottom: "calc(env(safe-area-inset-bottom, 0px) + 70px)",
      }}
    >
      <div
        className="max-w-[420px] sm:max-w-[360px] mx-auto sm:mx-0 bg-deepnavy border border-volt/70 rounded-xl p-3 sm:p-3.5 pointer-events-auto"
        style={{ boxShadow: "0 16px 40px -14px rgba(10,15,13,0.5)" }}
      >
        <p className="text-[11.5px] leading-snug text-ink/75">
          <Cookie className="inline w-3.5 h-3.5 mr-1 -mt-0.5 text-volt" strokeWidth={2} />
          <span className="font-bold text-ink">Cookies — you choose.</span>{" "}
          Necessary ones keep the site running; analytics &amp; marketing only if you say yes.{" "}
          <Link
            to="/privacy"
            data-testid="cookie-link-privacy"
            className="text-forest hover:text-forest-pop underline underline-offset-2 font-bold"
          >
            Privacy
          </Link>
        </p>
        <div className="mt-2.5 flex items-stretch gap-1.5">
          <button
            type="button"
            onClick={acceptAll}
            data-testid="cookie-accept-all"
            className="flex-1 px-3 py-2 bg-volt hover:bg-forest-pop text-white text-[10.5px] uppercase tracking-[0.14em] font-bold rounded-lg transition-colors whitespace-nowrap"
          >
            Accept
          </button>
          <button
            type="button"
            onClick={rejectAll}
            data-testid="cookie-reject-all"
            className="flex-1 px-3 py-2 border border-gray-border text-ink/70 hover:text-ink hover:border-forest text-[10.5px] uppercase tracking-[0.14em] font-bold rounded-lg transition-colors whitespace-nowrap"
          >
            Reject
          </button>
          <button
            type="button"
            onClick={() => {
              setPrefs(DEFAULT_PREFS);
              setCustomising(true);
            }}
            data-testid="cookie-customise-open"
            aria-label="Customise cookie preferences"
            title="Customise"
            className="shrink-0 w-9 flex items-center justify-center border border-gray-border text-ink/60 hover:text-ink hover:border-forest rounded-lg transition-colors"
          >
            <SlidersHorizontal className="w-3.5 h-3.5" strokeWidth={2.2} />
          </button>
        </div>
      </div>
    </div>
  );
}

function CookieRow({ title, desc, checked, disabled, onChange, testid }) {
  return (
    <div
      data-testid={testid}
      className={`p-4 border ${disabled ? "border-gray-border bg-cream-soft/40" : "border-gray-border bg-surface"} flex items-start gap-4`}
    >
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <h4 className="font-barlow font-black uppercase text-sm tracking-tight text-ink">
            {title}
          </h4>
          {disabled && (
            <span className="text-[9px] uppercase tracking-[0.22em] font-bold text-forest bg-volt/[0.18] px-2 py-0.5">
              Always on
            </span>
          )}
        </div>
        <p className="mt-1.5 text-xs text-ink/60 leading-relaxed">{desc}</p>
      </div>
      {/* Toggle pill */}
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        disabled={disabled}
        onClick={() => !disabled && onChange(!checked)}
        className={`shrink-0 mt-1 relative w-11 h-6 rounded-full transition-colors ${
          checked ? "bg-volt" : "bg-ink/15"
        } ${disabled ? "opacity-70 cursor-not-allowed" : "cursor-pointer"}`}
      >
        <span
          aria-hidden
          className={`absolute top-0.5 left-0.5 w-5 h-5 rounded-full bg-white shadow transition-transform ${
            checked ? "translate-x-5" : "translate-x-0"
          }`}
        />
      </button>
    </div>
  );
}
