import React, { useEffect, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "@/lib/auth-context";
import { LogOut, Shield, LayoutDashboard, Upload, ChevronRight, Menu, X } from "lucide-react";

const LIME = "#ccff00";

const NAV_LINKS = [
  { label: "How it works", testid: "how-it-works" },
  { label: "What's inside", testid: "what-you-get" },
  { label: "Sample", testid: "example-report" },
  { label: "Blog", to: "/blog" },
  { label: "Methodology", to: "/methodology" },
];

export default function Navigation() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [scrolled, setScrolled] = useState(false);
  const [progress, setProgress] = useState(0);
  const [mobileOpen, setMobileOpen] = useState(false);

  // Scroll listener — shrinks bar + drives progress strip
  useEffect(() => {
    const onScroll = () => {
      const y = window.scrollY;
      setScrolled(y > 24);
      const max = document.documentElement.scrollHeight - window.innerHeight;
      setProgress(max > 0 ? Math.min(1, Math.max(0, y / max)) : 0);
    };
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  // Lock body scroll while mobile menu open
  useEffect(() => {
    document.body.style.overflow = mobileOpen ? "hidden" : "";
    return () => { document.body.style.overflow = ""; };
  }, [mobileOpen]);

  // Cross-page anchor: ?scroll=<testid>
  useEffect(() => {
    const params = new URLSearchParams(location.search);
    const target = params.get("scroll");
    if (!target) return;
    const tryScroll = (attempt = 0) => {
      const el = document.querySelector(`[data-testid="${target}"]`);
      if (el) {
        el.scrollIntoView({ behavior: "smooth", block: "start" });
        window.history.replaceState({}, "", location.pathname);
      } else if (attempt < 12) {
        setTimeout(() => tryScroll(attempt + 1), 120);
      }
    };
    setTimeout(() => tryScroll(0), 80);
  }, [location]);

  const handleLogout = () => {
    logout();
    navigate("/");
  };

  const handleAnchor = (testid) => (e) => {
    e.preventDefault();
    setMobileOpen(false);
    const el = document.querySelector(`[data-testid="${testid}"]`);
    if (el) {
      el.scrollIntoView({ behavior: "smooth", block: "start" });
    } else {
      navigate(`/?scroll=${testid}`);
    }
  };

  const slug = (s) => s.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");

  return (
    <>
      <header
        data-testid="main-nav"
        className={`sticky top-0 left-0 right-0 z-50 transition-all duration-300 ${
          scrolled
            ? "bg-ink/85 backdrop-blur-xl border-b border-white/10"
            : "bg-ink border-b border-black/40"
        }`}
        style={scrolled ? { boxShadow: "0 8px 30px -16px rgba(0,0,0,0.7)" } : undefined}
      >
        <div
          className={`max-w-7xl mx-auto px-4 sm:px-6 md:px-10 flex items-center justify-between gap-3 transition-all duration-300 ${
            scrolled ? "py-2.5" : "py-3 sm:py-4"
          }`}
        >
          {/* === LOGO — refined wordmark (Direction A) === */}
          <Link to="/" data-testid="nav-logo" className="flex flex-col leading-none min-w-0 shrink group">
            <span className="font-barlow font-black uppercase text-white text-xl sm:text-2xl tracking-[0.14em] sm:tracking-[0.16em] whitespace-nowrap">
              SCOUT
              <span
                className="text-forest-pop group-hover:text-white transition-colors duration-300 relative inline-block"
                style={{ textShadow: `0 0 0 transparent` }}
              >
                ME
              </span>
              PLAY
            </span>
            <span
              className={`hidden md:inline-block text-[10px] text-white/55 font-bold uppercase tracking-[0.24em] whitespace-nowrap transition-all duration-300 ${
                scrolled ? "opacity-0 max-h-0 mt-0 overflow-hidden" : "opacity-100 mt-1.5"
              }`}
            >
              See your game through scout eyes
            </span>
          </Link>

          {/* === MIDDLE NAV LINKS — desktop only === */}
          <nav className="hidden lg:flex items-center gap-7 xl:gap-9" aria-label="Primary">
            {NAV_LINKS.map((item, i) => {
              const testid = `nav-link-${slug(item.label)}`;
              const cls = "relative text-[11px] uppercase tracking-[0.20em] font-bold text-white/65 hover:text-white transition-colors py-1 group/link";
              const underline = (
                <span
                  aria-hidden
                  className="absolute left-0 -bottom-0.5 w-0 h-[1.5px] group-hover/link:w-full transition-all duration-300"
                  style={{ background: LIME, boxShadow: `0 0 6px ${LIME}80` }}
                />
              );
              if (item.to) {
                return (
                  <Link key={i} to={item.to} data-testid={testid} className={cls}>
                    {item.label}
                    {underline}
                  </Link>
                );
              }
              return (
                <button key={i} type="button" onClick={handleAnchor(item.testid)} data-testid={testid} className={cls}>
                  {item.label}
                  {underline}
                </button>
              );
            })}
          </nav>

          {/* === RIGHT — auth / user CTAs === */}
          <div className="flex items-center gap-2 sm:gap-3 shrink-0">
            {user ? (
              <>
                <Link
                  to="/dashboard"
                  data-testid="nav-dashboard-btn"
                  className="hidden md:flex items-center gap-2 text-xs text-white/75 hover:text-white uppercase tracking-widest font-semibold transition-colors"
                >
                  <LayoutDashboard className="w-4 h-4" />
                  Dashboard
                </Link>
                {user.role === "admin" && (
                  <Link
                    to="/admin"
                    data-testid="nav-admin-btn"
                    className="hidden md:flex items-center gap-2 text-xs text-forest-pop hover:text-white uppercase tracking-widest font-semibold transition-colors"
                  >
                    <Shield className="w-4 h-4" />
                    Admin
                  </Link>
                )}
                <Link
                  to="/upload"
                  data-testid="nav-upload-cta"
                  className="group/cta relative bg-forest hover:bg-forest-pop text-white font-barlow font-black uppercase tracking-widest text-xs sm:text-sm px-4 sm:px-5 py-2 sm:py-2.5 rounded-full flex items-center gap-2 transition-all"
                  onMouseEnter={(e) => { e.currentTarget.style.boxShadow = `0 0 24px 2px ${LIME}40`; }}
                  onMouseLeave={(e) => { e.currentTarget.style.boxShadow = "none"; }}
                >
                  <Upload className="w-4 h-4" />
                  <span className="hidden sm:inline">Upload video</span>
                  <span className="sm:hidden">Upload</span>
                  <ChevronRight className="w-3.5 h-3.5 group-hover/cta:translate-x-0.5 transition-transform" />
                </Link>
                <button
                  onClick={handleLogout}
                  data-testid="nav-logout-btn"
                  aria-label="Sign out"
                  className="text-white/55 hover:text-white border border-white/15 hover:border-white/40 p-2 transition-colors"
                >
                  <LogOut className="w-4 h-4" />
                </button>
              </>
            ) : (
              <>
                <Link
                  to="/login"
                  data-testid="nav-login-btn"
                  className="hidden sm:inline-flex text-xs sm:text-sm text-white/75 hover:text-white uppercase tracking-widest font-semibold transition-colors whitespace-nowrap"
                >
                  Log in
                </Link>
                <Link
                  to="/signup"
                  data-testid="nav-signup-btn"
                  className="group/cta relative bg-forest hover:bg-forest-pop text-white font-barlow font-black uppercase tracking-widest text-[11px] sm:text-sm px-4 sm:px-5 py-2 sm:py-2.5 rounded-full flex items-center gap-1.5 whitespace-nowrap shrink-0 transition-all"
                  onMouseEnter={(e) => { e.currentTarget.style.boxShadow = `0 0 28px 2px ${LIME}55`; }}
                  onMouseLeave={(e) => { e.currentTarget.style.boxShadow = "none"; }}
                >
                  Get started
                  <ChevronRight className="w-3.5 h-3.5 group-hover/cta:translate-x-0.5 transition-transform" />
                </Link>
              </>
            )}

            {/* Mobile hamburger — only renders below lg */}
            <button
              type="button"
              onClick={() => setMobileOpen(true)}
              data-testid="nav-mobile-menu-btn"
              aria-label="Open menu"
              className="lg:hidden text-white/75 hover:text-white p-1.5 -mr-1 transition-colors"
            >
              <Menu className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* === Scroll progress strip — 2px lime line === */}
        <div className="h-[2px] bg-white/5 overflow-hidden" aria-hidden>
          <div
            className="h-full transition-[width] duration-150 ease-out"
            style={{
              width: `${progress * 100}%`,
              background: LIME,
              boxShadow: progress > 0.001 ? `0 0 8px ${LIME}99` : "none",
            }}
          />
        </div>
      </header>

      {/* === MOBILE MENU OVERLAY === */}
      {mobileOpen && (
        <div
          data-testid="mobile-menu-overlay"
          className="fixed inset-0 z-[100] lg:hidden"
          onClick={() => setMobileOpen(false)}
        >
          <div className="absolute inset-0 bg-ink/85 backdrop-blur-xl" />
          <div
            className="absolute top-0 right-0 bottom-0 w-full max-w-sm bg-forest p-7 flex flex-col gap-6 shadow-2xl overflow-y-auto"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between">
              <span className="font-barlow font-black uppercase text-white text-xl tracking-[0.14em]">
                SCOUT<span style={{ color: LIME }}>ME</span>PLAY
              </span>
              <button
                type="button"
                onClick={() => setMobileOpen(false)}
                data-testid="nav-mobile-close-btn"
                aria-label="Close menu"
                className="text-white/70 hover:text-white p-2"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="h-px bg-white/10 my-1" />

            <nav className="flex flex-col gap-1" aria-label="Mobile primary">
              {NAV_LINKS.map((item, i) => {
                const testid = `mobile-nav-${slug(item.label)}`;
                const cls = "block text-white text-2xl font-barlow font-black uppercase tracking-[0.06em] py-3 hover:translate-x-1 hover:text-[#ccff00] transition-all text-left";
                if (item.to) {
                  return (
                    <Link key={i} to={item.to} onClick={() => setMobileOpen(false)} data-testid={testid} className={cls}>
                      {item.label}
                    </Link>
                  );
                }
                return (
                  <button key={i} type="button" onClick={handleAnchor(item.testid)} data-testid={testid} className={cls}>
                    {item.label}
                  </button>
                );
              })}
            </nav>

            <div className="mt-auto pt-6 border-t border-white/15 flex flex-col gap-3">
              {user ? (
                <>
                  <Link
                    to="/dashboard"
                    onClick={() => setMobileOpen(false)}
                    className="flex items-center gap-2 text-white/85 hover:text-white text-sm uppercase tracking-widest font-bold py-1.5"
                  >
                    <LayoutDashboard className="w-4 h-4" /> Dashboard
                  </Link>
                  {user.role === "admin" && (
                    <Link
                      to="/admin"
                      onClick={() => setMobileOpen(false)}
                      className="flex items-center gap-2 hover:text-white text-sm uppercase tracking-widest font-bold py-1.5"
                      style={{ color: LIME }}
                    >
                      <Shield className="w-4 h-4" /> Admin
                    </Link>
                  )}
                  <Link
                    to="/upload"
                    onClick={() => setMobileOpen(false)}
                    className="font-barlow font-black uppercase tracking-widest text-sm px-5 py-3.5 text-center rounded-full flex items-center justify-center gap-2"
                    style={{ background: LIME, color: "#0A1F0F" }}
                  >
                    <Upload className="w-4 h-4" /> Upload video <ChevronRight className="w-4 h-4" />
                  </Link>
                  <button
                    type="button"
                    onClick={() => { handleLogout(); setMobileOpen(false); }}
                    className="text-white/55 hover:text-white text-[11px] uppercase tracking-widest font-bold flex items-center justify-center gap-2 mt-1"
                  >
                    <LogOut className="w-3.5 h-3.5" /> Sign out
                  </button>
                </>
              ) : (
                <>
                  <Link
                    to="/login"
                    onClick={() => setMobileOpen(false)}
                    className="text-white/85 hover:text-white text-sm uppercase tracking-widest font-bold py-2 text-center"
                  >
                    Log in
                  </Link>
                  <Link
                    to="/signup"
                    onClick={() => setMobileOpen(false)}
                    className="font-barlow font-black uppercase tracking-widest text-sm px-5 py-3.5 text-center rounded-full flex items-center justify-center gap-2"
                    style={{ background: LIME, color: "#0A1F0F" }}
                  >
                    Get started <ChevronRight className="w-4 h-4" />
                  </Link>
                </>
              )}
            </div>
          </div>
        </div>
      )}
    </>
  );
}
