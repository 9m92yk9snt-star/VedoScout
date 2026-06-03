import React from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "@/lib/auth-context";
import { LogOut, Shield, LayoutDashboard, Upload } from "lucide-react";

/* === Scout Reticle Logo Mark ===
   Custom premium SVG: viewfinder corner brackets framing a football.
   A small volt dot = the player being tracked. Reads as scouting + football. */
const LogoMark = ({ className = "w-9 h-9" }) => (
  <div className={`${className} relative flex items-center justify-center bg-deepnavy border border-volt/40 group-hover:border-volt transition-colors`}>
    <svg viewBox="0 0 36 36" className="w-full h-full" aria-hidden="true">
      {/* Corner brackets — viewfinder/scope */}
      <path d="M3 9 V3 H9" stroke="#ccff00" strokeWidth="2" fill="none" strokeLinecap="square" />
      <path d="M27 3 H33 V9" stroke="#ccff00" strokeWidth="2" fill="none" strokeLinecap="square" />
      <path d="M33 27 V33 H27" stroke="#ccff00" strokeWidth="2" fill="none" strokeLinecap="square" />
      <path d="M9 33 H3 V27" stroke="#ccff00" strokeWidth="2" fill="none" strokeLinecap="square" />
      {/* Football — circle with pentagon-suggested facets */}
      <circle cx="18" cy="18" r="7" fill="none" stroke="#ffffff" strokeWidth="1.5" />
      <path d="M18 11 L21.3 13.4 L20 17 L16 17 L14.7 13.4 Z" fill="#ffffff" />
      {/* Volt tracking dot — the player */}
      <circle cx="18" cy="18" r="1.5" fill="#ccff00" />
    </svg>
  </div>
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
      <div className="max-w-7xl mx-auto px-6 md:px-10 py-4 flex items-center justify-between gap-4">
        <Link to="/" data-testid="nav-logo" className="flex items-center gap-3 group shrink-0">
          <LogoMark />
          <span className="font-barlow font-black uppercase text-white tracking-tight text-xl leading-none whitespace-nowrap">
            Scout<span className="text-volt">Me</span>Play
          </span>
        </Link>

        <nav className="hidden md:flex items-center gap-8">
          {!user && (
            <>
              <Link to="/login" data-testid="nav-link-login" className="text-sm text-white/70 hover:text-volt uppercase tracking-widest font-semibold transition-colors">Sign in</Link>
              <Link to="/signup" data-testid="nav-link-signup" className="text-sm text-white/70 hover:text-volt uppercase tracking-widest font-semibold transition-colors">Sign up</Link>
            </>
          )}
        </nav>

        <div className="flex items-center gap-3">
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
                className="text-sm text-white/80 hover:text-white uppercase tracking-widest font-semibold transition-colors whitespace-nowrap"
              >
                Log in
              </Link>
              <Link
                to="/signup"
                data-testid="nav-signup-btn"
                className="relative bg-volt hover:bg-white text-deepnavy font-barlow font-black uppercase tracking-widest text-sm px-5 py-2.5 transition-colors whitespace-nowrap shrink-0"
              >
                Get started
                <span className="hidden sm:block absolute -bottom-5 left-0 right-0 text-[9px] text-white/55 font-bold tracking-[0.18em] text-center pt-1">
                  399 DKK · one-time
                </span>
              </Link>
            </>
          )}
        </div>
      </div>
    </header>
  );
}
