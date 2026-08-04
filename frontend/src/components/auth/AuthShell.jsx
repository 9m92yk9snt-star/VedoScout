import React from "react";
import { Link } from "react-router-dom";
import { Shield, Star, BarChart3, UserCheck, FileText, MessageCircle, Headphones } from "lucide-react";

/* Shared building blocks for the mockup-driven auth pages (Login / Signup)
   and the upload AccountGateModal. Colors are locked to the mockups:
   cream page #F7F3EA · primary green #63A61F · ink #161C12 */

export const AUTH_GREEN = "#63A61F";
export const AUTH_GREEN_DARK = "#558F17";
export const AUTH_INK = "#161C12";
export const AUTH_CREAM = "#F4F0E5";

const ASSET_BASE = process.env.REACT_APP_BACKEND_URL || "";
export const AUTH_HERO_IMG = `${ASSET_BASE}/api/static/landing/auth-hero-player.jpg`;
export const AUTH_AVATARS = [1, 2, 3, 4].map((i) => `${ASSET_BASE}/api/static/landing/auth-avatar-${i}.jpg`);

/* REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH */
export const googleRedirect = (path = "/dashboard") => {
  const redirectUrl = window.location.origin + path;
  window.location.href = `https://auth.emergentagent.com/?redirect=${encodeURIComponent(redirectUrl)}`;
};

export const SmpLogo = ({ className = "" }) => (
  <Link to="/" className={`inline-block ${className}`} data-testid="auth-logo">
    <span className="font-barlow font-black uppercase text-3xl md:text-4xl tracking-tight text-[#161C12] leading-none">
      SCOUT<span className="bg-[#63A61F] text-white px-1.5 mx-0.5">ME</span>PLAY
    </span>
    <span className="block mt-1.5 font-barlow font-bold uppercase tracking-[0.08em] text-sm md:text-base text-[#161C12]">
      KNOW YOUR <span className="text-[#63A61F]">TRUE LEVEL.</span>
    </span>
  </Link>
);

export const GoogleG = ({ className = "w-5 h-5" }) => (
  <svg viewBox="0 0 48 48" className={className} aria-hidden="true">
    <path fill="#FFC107" d="M43.6 20.1H42V20H24v8h11.3C33.7 32.7 29.3 36 24 36c-6.6 0-12-5.4-12-12s5.4-12 12-12c3.1 0 5.9 1.2 8 3l5.7-5.7C34.3 6.1 29.4 4 24 4 13 4 4 13 4 24s9 20 20 20 20-9 20-20c0-1.3-.1-2.7-.4-3.9z" />
    <path fill="#FF3D00" d="M6.3 14.7l6.6 4.8C14.7 15.1 19 12 24 12c3.1 0 5.9 1.2 8 3l5.7-5.7C34.3 6.1 29.4 4 24 4 16.3 4 9.7 8.3 6.3 14.7z" />
    <path fill="#4CAF50" d="M24 44c5.2 0 9.9-2 13.4-5.2l-6.2-5.2C29.2 35.1 26.7 36 24 36c-5.3 0-9.7-3.4-11.3-8.1l-6.5 5C9.5 39.6 16.2 44 24 44z" />
    <path fill="#1976D2" d="M43.6 20.1H42V20H24v8h11.3c-.8 2.2-2.2 4.2-4.1 5.5l6.2 5.2C36.9 39.2 44 34 44 24c0-1.3-.1-2.7-.4-3.9z" />
  </svg>
);

export const GoogleButton = ({ onClick, disabled = false, label = "Continue with Google", testId = "google-login-btn" }) => (
  <button
    type="button"
    onClick={onClick}
    disabled={disabled}
    data-testid={testId}
    className="w-full flex items-center justify-center gap-3 rounded-xl border border-[#E3E0D5] bg-white hover:bg-[#FAF8F1] text-[#1F2A17] font-semibold text-base py-3.5 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
  >
    <GoogleG />
    {label}
  </button>
);

export const OrDivider = () => (
  <div className="flex items-center gap-4 my-5">
    <div className="h-px flex-1 bg-[#E7E3D8]" />
    <span className="text-xs font-bold tracking-[0.2em] text-[#9AA08F] uppercase">OR</span>
    <div className="h-px flex-1 bg-[#E7E3D8]" />
  </div>
);

export const AuthInput = ({ icon: Icon, rightSlot = null, testId, ...rest }) => (
  <div className="relative">
    <Icon className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-[#63A61F]" strokeWidth={2} />
    <input
      data-testid={testId}
      className="w-full rounded-xl border border-[#E3E0D5] bg-white pl-12 pr-11 py-3.5 text-[#161C12] placeholder-[#A8AE9D] text-[15px] focus:outline-none focus:border-[#63A61F] focus:ring-2 focus:ring-[#63A61F]/25 transition-colors"
      {...rest}
    />
    {rightSlot}
  </div>
);

const BENEFITS = [
  { icon: BarChart3, label: "Benchmarked performance analysis" },
  { icon: UserCheck, label: "Real scout review & feedback" },
  { icon: FileText, label: "Professional PDF report & development plan" },
  { icon: MessageCircle, label: "Direkt chat with scout" },
  { icon: Headphones, label: "Get connection and support" },
];

export const BenefitsStrip = () => (
  <div className="rounded-2xl bg-[#F1EDDF] px-4 py-6 md:px-6" data-testid="auth-benefits-strip">
    <div className="text-center font-barlow font-bold uppercase tracking-[0.06em] text-base md:text-lg text-[#161C12]">
      SCOUTME <span className="text-[#63A61F]">PRO</span> BENCHMARKED ANALYSIS
    </div>
    <div className="mt-5 grid grid-cols-5 divide-x divide-[#DDD8C6]">
      {BENEFITS.map(({ icon: Icon, label }, i) => (
        <div key={i} className="flex flex-col items-center text-center px-1.5 md:px-3 gap-2">
          <Icon className="w-7 h-7 md:w-8 md:h-8 text-[#63A61F]" strokeWidth={1.6} />
          <span className="text-[9px] md:text-[11px] leading-snug text-[#3D4435]">{label}</span>
        </div>
      ))}
    </div>
  </div>
);

export const TrustedBadge = ({ withAvatars = false }) => (
  <div className="flex items-center justify-center gap-4 flex-wrap" data-testid="auth-trusted-badge">
    {withAvatars && (
      <div className="flex -space-x-3">
        {AUTH_AVATARS.map((src, i) => (
          <img
            key={i}
            src={src}
            alt=""
            className="w-11 h-11 md:w-12 md:h-12 rounded-full object-cover border-2 border-white shadow-sm"
            loading="lazy"
          />
        ))}
      </div>
    )}
    <div className="flex items-center gap-3">
      <span className="relative inline-flex">
        <Shield className="w-9 h-9 text-[#63A61F]" strokeWidth={1.8} />
        <Star className="w-3.5 h-3.5 text-[#63A61F] fill-[#63A61F] absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-[60%]" />
      </span>
      <span className="font-barlow font-bold uppercase tracking-[0.04em] text-sm md:text-base text-[#161C12] leading-snug max-w-[260px]">
        TRUSTED BY <span className="text-[#63A61F]">COACHES, SCOUTS, PLAYERS AND FAMILIES.</span>
      </span>
    </div>
  </div>
);

/* Cream page shell with dotted corners + hero player image on the right */
export const AuthShell = ({ children }) => (
  <div className="min-h-screen relative overflow-hidden" style={{ backgroundColor: AUTH_CREAM }}>
    {/* corner dot grids */}
    <div
      aria-hidden
      className="absolute top-6 right-6 w-24 h-16 opacity-60 pointer-events-none"
      style={{ backgroundImage: "radial-gradient(#9BB878 1.5px, transparent 1.5px)", backgroundSize: "14px 14px" }}
    />
    <div
      aria-hidden
      className="absolute bottom-10 left-4 w-20 h-14 opacity-50 pointer-events-none"
      style={{ backgroundImage: "radial-gradient(#9BB878 1.5px, transparent 1.5px)", backgroundSize: "14px 14px" }}
    />
    <div className="relative max-w-xl lg:max-w-2xl mx-auto px-5 md:px-8 pt-8 md:pt-10 pb-14">{children}</div>
  </div>
);

export const AuthHeroImage = () => (
  <img
    src={AUTH_HERO_IMG}
    alt="ScoutMePlay player"
    className="absolute top-0 right-0 w-[52%] max-w-[340px] md:max-w-[380px] pointer-events-none select-none"
    style={{
      maskImage: "linear-gradient(to bottom, black 70%, transparent 98%), linear-gradient(to left, black 72%, transparent 99%)",
      WebkitMaskImage: "linear-gradient(to bottom, black 70%, transparent 98%), linear-gradient(to left, black 72%, transparent 99%)",
      maskComposite: "intersect",
      WebkitMaskComposite: "source-in",
    }}
    data-testid="auth-hero-image"
  />
);
