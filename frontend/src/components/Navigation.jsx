import React, { useEffect, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "@/lib/auth-context";
import api from "@/lib/api";
import { LogOut, Shield, LayoutDashboard, Upload, ChevronRight, Menu, X, Home, ArrowUp } from "lucide-react";

const LIME = "#ccff00";

const NAV_LINKS = [
  { label: "Home", testid: "hero-section", isHome: true },
  { label: "How it works", testid: "how-it-works-walkthrough" },
  { label: "What's inside", testid: "what-you-get" },
  { label: "Sample", testid: "example-report" },
  { label: "Pricing", testid: "pricing-section" },
  { label: "Blog", to: "/blog" },
  { label: "Methodology", to: "/methodology" },
];

// Sections shown on the right-edge scroll-spy rail (desktop, landing page only)
const RAIL_SECTIONS = [
  { id: "hero-section", label: "Top" },
  { id: "how-it-works-walkthrough", label: "How it works" },
  { id: "what-you-get", label: "Inside" },
  { id: "example-report", label: "Sample" },
  { id: "pricing-section", label: "Pricing" },
  { id: "final-cta", label: "Start" },
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

  // One-shot first-visit pulse on the Upload Video CTA for brand-new users
  // (0 reports). Mirrors the Dashboard's Unlock-pill pulse pattern — a tiny
  // forest-green ring fires once to draw the eye to the next-step CTA, then
  // a localStorage flag keeps subsequent visits calm.
  const [uploadCtaPulse, setUploadCtaPulse] = useState(false);
  useEffect(() => {
    if (!user) return; // no auth → no fetch, no pulse
    const key = `nav_upload_pulse_seen_v1_${user.id || user.email || "u"}`;
    let cancelled = false;
    try {
      if (window.localStorage.getItem(key)) return;
    } catch { return; }
    // Lazy-fetch report count only when the flag is missing (cost: one call
    // per browser per user, ever). The /reports endpoint is what the
    // Dashboard already calls — backed by the same handler.
    (async () => {
      try {
        const { data } = await api.get("/reports");
        if (cancelled) return;
        const count = Array.isArray(data) ? data.length : (data?.reports?.length || 0);
        if (count > 0) {
          // user already has reports — they've passed this milestone; mark
          // the flag so we never fetch again on subsequent navigations.
          try { window.localStorage.setItem(key, "1"); } catch { /* private mode */ }
          return;
        }
        setUploadCtaPulse(true);
        try { window.localStorage.setItem(key, "1"); } catch { /* private mode */ }
        // remove the class after the animation completes so the DOM stays clean
        setTimeout(() => { if (!cancelled) setUploadCtaPulse(false); }, 2200);
      } catch {
        // silently ignore — pulse hint is non-critical
      }
    })();
    return () => { cancelled = true; };
  }, [user]);

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

  const handleAnchor = (testid, isHome = false) => (e) => {
    e.preventDefault();
    setMobileOpen(false);
    // Home link: if not on landing, navigate to "/" — else just scroll to top of hero
    if (isHome && location.pathname !== "/") {
      navigate("/");
      window.scrollTo({ top: 0, behavior: "smooth" });
      return;
    }
    const el = document.querySelector(`[data-testid="${testid}"]`);
    if (el) {
      el.scrollIntoView({ behavior: "smooth", block: "start" });
    } else {
      navigate(`/?scroll=${testid}`);
    }
  };

  const slug = (s) => s.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");

  const isLanding = location.pathname === "/";

  return (
    <>
      <header
        data-testid="main-nav"
        className={`sticky top-0 left-0 right-0 z-50 transition-all duration-300 ${
          scrolled
            ? "bg-ink/90 backdrop-blur-xl border-b border-white/10"
            : "bg-ink border-b border-black/40"
        }`}
        style={scrolled ? { boxShadow: "0 8px 30px -16px rgba(0,0,0,0.7)" } : undefined}
      >
        <div
          className={`max-w-7xl mx-auto px-4 sm:px-6 md:px-10 flex items-center justify-between gap-3 transition-all duration-300 ${
            scrolled ? "py-2.5" : "py-3 sm:py-4"
          }`}
        >
          {/* === LOGO — refined premium wordmark === */}
          <Link
            to="/"
            data-testid="nav-logo"
            className="flex flex-col leading-none min-w-0 shrink group"
            onClick={(e) => {
              if (location.pathname === "/") {
                e.preventDefault();
                window.scrollTo({ top: 0, behavior: "smooth" });
              }
            }}
            aria-label="ScoutMePlay — home"
          >
            <span className="font-barlow font-black uppercase text-white text-xl sm:text-2xl tracking-[0.14em] sm:tracking-[0.16em] whitespace-nowrap flex items-baseline gap-[1px]">
              <span>SCOUT</span>
              <span
                className="relative inline-block px-[3px] text-ink transition-colors duration-300"
                style={{
                  background: LIME,
                  boxShadow: `0 0 0 0 ${LIME}00`,
                }}
              >
                ME
              </span>
              <span>PLAY</span>
            </span>
            <span
              className={`hidden md:flex items-center gap-1.5 text-[9px] text-white/55 font-bold uppercase tracking-[0.14em] whitespace-nowrap transition-all duration-300 ${
                scrolled ? "opacity-0 max-h-0 mt-0 overflow-hidden" : "opacity-100 mt-1.5"
              }`}
            >
              <span
                aria-hidden
                className="inline-block w-1 h-1 rounded-full"
                style={{ background: LIME, boxShadow: `0 0 6px ${LIME}99` }}
              />
              See your game through scout eyes
            </span>
          </Link>

          {/* === MIDDLE NAV LINKS — desktop only === */}
          <nav className="hidden lg:flex items-center gap-5 xl:gap-7" aria-label="Primary">
            {NAV_LINKS.map((item, i) => {
              const testid = `nav-link-${slug(item.label)}`;
              const activeHome = item.isHome && isLanding;
              const cls = `relative text-[11px] uppercase tracking-[0.18em] font-bold transition-colors py-1 group/link flex items-center gap-1.5 whitespace-nowrap ${
                activeHome ? "text-white" : "text-white/65 hover:text-white"
              }`;
              const underline = (
                <span
                  aria-hidden
                  className={`absolute left-0 -bottom-0.5 h-[1.5px] transition-all duration-300 ${
                    activeHome ? "w-full" : "w-0 group-hover/link:w-full"
                  }`}
                  style={{ background: LIME, boxShadow: `0 0 6px ${LIME}80` }}
                />
              );
              const icon = item.isHome ? <Home className="w-3 h-3" strokeWidth={2.4} /> : null;
              if (item.to) {
                return (
                  <Link key={i} to={item.to} data-testid={testid} className={cls}>
                    {icon}{item.label}
                    {underline}
                  </Link>
                );
              }
              return (
                <button key={i} type="button" onClick={handleAnchor(item.testid, item.isHome)} data-testid={testid} className={cls}>
                  {icon}{item.label}
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
                  className={`${uploadCtaPulse ? "scoutme-unlock-pulse " : ""}group/cta relative bg-forest hover:bg-forest-pop text-white font-barlow font-black uppercase tracking-widest text-xs sm:text-sm px-4 sm:px-5 py-2 sm:py-2.5 rounded-full flex items-center gap-2 transition-all`}
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
                const cls = "flex items-center gap-3 text-white text-2xl font-barlow font-black uppercase tracking-[0.06em] py-3 hover:translate-x-1 hover:text-[#ccff00] transition-all text-left";
                const icon = item.isHome ? <Home className="w-5 h-5 shrink-0 opacity-70" strokeWidth={2.2} /> : null;
                if (item.to) {
                  return (
                    <Link key={i} to={item.to} onClick={() => setMobileOpen(false)} data-testid={testid} className={cls}>
                      {icon}{item.label}
                    </Link>
                  );
                }
                return (
                  <button key={i} type="button" onClick={handleAnchor(item.testid, item.isHome)} data-testid={testid} className={cls}>
                    {icon}{item.label}
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

      {/* === SECTION RAIL — right-edge scroll-spy (desktop, landing only) === */}
      {isLanding && <SectionRail />}

      {/* === BACK TO TOP — floating button (landing only) === */}
      {isLanding && <BackToTop scrolled={scrolled} />}
    </>
  );
}

/* ------------------------------------------------------------------
 * SectionRail — premium vertical scroll-spy rail (desktop only)
 * Tracks visible section, highlights active dot, expands label on hover.
 * ------------------------------------------------------------------ */
function SectionRail() {
  const [active, setActive] = useState(0);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const onScroll = () => {
      const y = window.scrollY;
      setVisible(y > 200);
      const trigger = window.innerHeight * 0.38;
      let idx = 0;
      for (let i = 0; i < RAIL_SECTIONS.length; i++) {
        const el = document.querySelector(`[data-testid="${RAIL_SECTIONS[i].id}"]`);
        if (!el) continue;
        const rect = el.getBoundingClientRect();
        if (rect.top - trigger <= 0) idx = i;
      }
      setActive(idx);
    };
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  const jump = (id) => {
    const el = document.querySelector(`[data-testid="${id}"]`);
    if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
    else if (id === "hero-section") window.scrollTo({ top: 0, behavior: "smooth" });
  };

  return (
    <div
      data-testid="section-rail"
      aria-hidden={!visible}
      className={`fixed right-4 xl:right-6 top-1/2 -translate-y-1/2 z-40 hidden xl:flex flex-col items-end gap-3 transition-all duration-500 ${
        visible ? "opacity-100 translate-x-0" : "opacity-0 translate-x-3 pointer-events-none"
      }`}
    >
      {/* Vertical accent line behind dots */}
      <div
        aria-hidden
        className="absolute right-[5px] top-1 bottom-1 w-px bg-gradient-to-b from-transparent via-ink/15 to-transparent pointer-events-none"
      />
      {RAIL_SECTIONS.map((s, i) => {
        const isActive = active === i;
        return (
          <button
            key={s.id}
            type="button"
            onClick={() => jump(s.id)}
            data-testid={`rail-${s.id}`}
            aria-label={`Jump to ${s.label}`}
            aria-current={isActive ? "true" : undefined}
            className="group relative flex items-center gap-2.5 cursor-pointer outline-none"
          >
            {/* Label — hidden until hover, fully visible when active */}
            <span
              className={`text-[10px] uppercase tracking-[0.22em] font-bold whitespace-nowrap transition-all duration-300 ${
                isActive
                  ? "opacity-100 text-ink translate-x-0"
                  : "opacity-0 -translate-x-1 text-ink/70 group-hover:opacity-100 group-hover:translate-x-0"
              }`}
            >
              {s.label}
            </span>
            {/* Dot */}
            <span
              aria-hidden
              className={`relative block rounded-full transition-all duration-300 ${
                isActive ? "w-3 h-3" : "w-2 h-2 group-hover:w-2.5 group-hover:h-2.5"
              }`}
              style={{
                background: isActive ? "#1F4F2F" : "transparent",
                border: isActive ? "2px solid #1F4F2F" : "1.5px solid rgba(10,15,13,0.4)",
                boxShadow: isActive ? "0 0 0 4px rgba(31,79,47,0.12)" : "none",
              }}
            />
          </button>
        );
      })}
    </div>
  );
}

/* ------------------------------------------------------------------
 * BackToTop — appears after 600px scroll, jumps user back to hero
 * ------------------------------------------------------------------ */
function BackToTop({ scrolled }) {
  const [show, setShow] = useState(false);
  useEffect(() => {
    const onScroll = () => setShow(window.scrollY > 600);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  const toTop = () => {
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  return (
    <button
      type="button"
      onClick={toTop}
      data-testid="back-to-top"
      aria-label="Back to top"
      className={`fixed bottom-5 right-5 md:bottom-7 md:right-7 z-40 w-11 h-11 md:w-12 md:h-12 flex items-center justify-center rounded-full transition-all duration-300 group/btt ${
        show ? "opacity-100 translate-y-0 pointer-events-auto" : "opacity-0 translate-y-3 pointer-events-none"
      }`}
      style={{
        background: "#1F4F2F",
        color: "#fff",
        boxShadow:
          "0 12px 30px -8px rgba(31,79,47,0.45), 0 4px 10px -2px rgba(10,15,13,0.18), inset 0 1px 0 rgba(204,255,0,0.25)",
      }}
    >
      <ArrowUp className="w-4 h-4 md:w-5 md:h-5 transition-transform group-hover/btt:-translate-y-0.5" strokeWidth={2.5} />
    </button>
  );
}
