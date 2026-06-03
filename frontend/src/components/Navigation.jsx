import React from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "@/lib/auth-context";
import { LogOut, Shield, LayoutDashboard, Upload } from "lucide-react";

/* === ScoutMePlay Emblem ===
   Stylized scout/warrior mark: scope reticle on top, flared wings,
   vertical body, blade pointing down. Reads as targeting + sport + edge. */
const LogoMark = ({ className = "w-10 h-12" }) => (
  <svg viewBox="0 0 50 60" className={className} aria-hidden="true" fill="none" stroke="#ccff00" strokeLinecap="square" strokeLinejoin="miter">
    {/* Scope reticle */}
    <circle cx="25" cy="12" r="7" strokeWidth="2.5" />
    <line x1="25" y1="1" x2="25" y2="5" strokeWidth="2.5" />
    <line x1="8" y1="12" x2="14" y2="12" strokeWidth="2.5" />
    <line x1="36" y1="12" x2="42" y2="12" strokeWidth="2.5" />
    {/* Inner crosshair dot */}
    <circle cx="25" cy="12" r="1.5" fill="#ccff00" stroke="none" />

    {/* Helmet wings flaring outward */}
    <path d="M25 22 L9 29 L18 33 Z" fill="#ccff00" stroke="none" />
    <path d="M25 22 L41 29 L32 33 Z" fill="#ccff00" stroke="none" />

    {/* Vertical body */}
    <line x1="25" y1="22" x2="25" y2="49" strokeWidth="2.5" />

    {/* Inner arms / chevron */}
    <path d="M15 38 L25 31 L35 38" strokeWidth="2.5" />

    {/* Bottom blade */}
    <path d="M20 49 L25 60 L30 49 Z" fill="#ccff00" stroke="none" />
  </svg>
);

export default function Navigation({ transparent = false }) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const handleLogout = () => {
    logout();
    navigate("/");
  };

  return (
    <header
      data-testid="main-nav"
      className={`fixed top-0 left-0 right-0 z-50 ${
        transparent ? "bg-deepnavy/40 backdrop-blur-xl" : "bg-deepnavy/90 backdrop-blur-xl"
      } border-b border-white/10`}
    >
      <div className="max-w-7xl mx-auto px-4 sm:px-6 md:px-10 py-3 sm:py-4 flex items-center justify-between gap-2 sm:gap-3">
        <Link to="/" data-testid="nav-logo" className="flex items-center gap-2.5 sm:gap-3 group min-w-0 shrink">
          <LogoMark className="w-12 h-14 sm:w-14 sm:h-16 shrink-0 group-hover:scale-105 transition-transform" />
          <div className="flex flex-col leading-none min-w-0">
            <span className="font-barlow font-black uppercase text-white text-base sm:text-xl tracking-[0.16em] sm:tracking-[0.18em] whitespace-nowrap">
              SCOUTMEPLAY
            </span>
            <span className="text-[7px] sm:text-[10px] text-volt font-bold uppercase tracking-[0.12em] sm:tracking-[0.22em] mt-1.5 sm:mt-2 whitespace-nowrap">
              One video away from your dream
            </span>
          </div>
        </Link>

        <nav className="hidden md:flex items-center gap-8" aria-hidden="true" />

        <div className="flex items-center gap-2 sm:gap-3 shrink-0">
          {user ? (
            <>
              <Link
                to="/dashboard"
                data-testid="nav-dashboard-btn"
                className="hidden sm:flex items-center gap-2 text-sm text-white/80 hover:text-white uppercase tracking-widest font-semibold transition-colors"
              >
                <LayoutDashboard className="w-4 h-4" />
                Dashboard
              </Link>
              {user.role === "admin" && (
                <Link
                  to="/admin"
                  data-testid="nav-admin-btn"
                  className="hidden sm:flex items-center gap-2 text-sm text-volt hover:text-white uppercase tracking-widest font-semibold transition-colors"
                >
                  <Shield className="w-4 h-4" />
                  Admin
                </Link>
              )}
              <Link
                to="/upload"
                data-testid="nav-upload-cta"
                className="bg-volt hover:bg-white text-deepnavy font-barlow font-black uppercase tracking-widest text-sm px-4 py-2 transition-colors flex items-center gap-2"
              >
                <Upload className="w-4 h-4" />
                Upload
              </Link>
              <button
                onClick={handleLogout}
                data-testid="nav-logout-btn"
                aria-label="Sign out"
                className="text-white/60 hover:text-white p-2 transition-colors"
              >
                <LogOut className="w-4 h-4" />
              </button>
            </>
          ) : (
            <>
              <Link
                to="/login"
                data-testid="nav-login-btn"
                className="text-xs sm:text-sm text-white/80 hover:text-white uppercase tracking-widest font-semibold transition-colors whitespace-nowrap"
              >
                Log in
              </Link>
              <span aria-hidden="true" className="hidden sm:block h-7 w-px bg-white/15" />
              <Link
                to="/signup"
                data-testid="nav-signup-btn"
                className="bg-volt hover:bg-white text-deepnavy font-barlow font-black uppercase tracking-widest text-[11px] sm:text-sm px-3 sm:px-5 py-2 sm:py-2.5 transition-colors whitespace-nowrap shrink-0"
              >
                Get started
              </Link>
            </>
          )}
        </div>
      </div>
    </header>
  );
}
