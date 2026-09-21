import React from "react";

/**
 * PaymentBadges
 * Subtle trust line that reassures visitors which payment methods are accepted
 * BEFORE they click the CTA. Used near hero / pricing card / paywall buttons.
 *
 * Variants:
 *   - default: cream-card pill with all methods + "secure via Stripe" line
 *   - compact: just the method names inline (no pill, no Stripe line)
 *
 * Methods rendered:
 *   - Apple Pay (mini Apple icon + "Pay")
 *   - Google Pay (Google "G" colors + "Pay")
 *   - Card (Visa, Mastercard chip icon)
 */

const AppleMark = ({ className = "w-3.5 h-3.5" }) => (
  <svg viewBox="0 0 24 24" className={className} fill="currentColor" aria-hidden="true">
    <path d="M17.05 12.04c-.03-2.84 2.32-4.21 2.43-4.28-1.32-1.94-3.39-2.2-4.12-2.23-1.75-.18-3.42 1.03-4.31 1.03-.89 0-2.27-1-3.73-.97-1.92.03-3.69 1.12-4.68 2.83-2 3.47-.51 8.6 1.43 11.42.95 1.38 2.08 2.93 3.56 2.87 1.43-.06 1.97-.93 3.7-.93s2.22.93 3.74.9c1.55-.03 2.52-1.4 3.47-2.79 1.09-1.6 1.55-3.15 1.57-3.23-.03-.01-3.02-1.16-3.06-4.62zM14.18 3.83c.79-.96 1.32-2.29 1.18-3.62-1.14.05-2.52.76-3.34 1.72-.73.84-1.37 2.21-1.2 3.51 1.27.1 2.57-.65 3.36-1.61z"/>
  </svg>
);

const GoogleGMark = ({ className = "w-3.5 h-3.5" }) => (
  <svg viewBox="0 0 24 24" className={className} aria-hidden="true">
    <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
    <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.99.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
    <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
    <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
  </svg>
);

const CardMark = ({ className = "w-3.5 h-3.5" }) => (
  <svg viewBox="0 0 24 24" className={className} fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <rect x="2" y="5" width="20" height="14" rx="2" />
    <line x1="2" y1="10" x2="22" y2="10" />
  </svg>
);

export default function PaymentBadges({ variant = "default", className = "" }) {
  if (variant === "compact") {
    return (
      <div
        data-testid="payment-badges"
        className={`inline-flex items-center gap-2 text-[11px] uppercase tracking-[0.2em] font-bold text-ink/55 ${className}`}
      >
        <AppleMark className="w-3.5 h-3.5 text-ink/70" />
        <span>Apple&nbsp;Pay</span>
        <span className="text-ink/25">·</span>
        <GoogleGMark className="w-3.5 h-3.5" />
        <span>Google&nbsp;Pay</span>
        <span className="text-ink/25">·</span>
        <CardMark className="w-3.5 h-3.5 text-ink/70" />
        <span>Card</span>
      </div>
    );
  }

  return (
    <div
      data-testid="payment-badges"
      className={`inline-flex flex-wrap items-center gap-x-3 gap-y-1.5 ${className}`}
    >
      <div className="inline-flex items-center gap-1.5 px-2.5 py-1 bg-cream-card border border-gray-border rounded-full">
        <AppleMark className="w-3.5 h-3.5 text-ink" />
        <span className="text-[11px] uppercase tracking-[0.18em] font-bold text-ink/75">Apple&nbsp;Pay</span>
      </div>
      <div className="inline-flex items-center gap-1.5 px-2.5 py-1 bg-cream-card border border-gray-border rounded-full">
        <GoogleGMark className="w-3.5 h-3.5" />
        <span className="text-[11px] uppercase tracking-[0.18em] font-bold text-ink/75">Google&nbsp;Pay</span>
      </div>
      <div className="inline-flex items-center gap-1.5 px-2.5 py-1 bg-cream-card border border-gray-border rounded-full">
        <CardMark className="w-3.5 h-3.5 text-ink" />
        <span className="text-[11px] uppercase tracking-[0.18em] font-bold text-ink/75">Card</span>
      </div>
    </div>
  );
}
