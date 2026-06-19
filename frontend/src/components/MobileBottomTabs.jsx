/* ── Mobile bottom-tab navigation ──────────────────────────────────────
 *  Visible only on small screens (<768 px). Sticky to the viewport
 *  bottom. Four tabs: Home · Reports · Upload · Profile. Active route
 *  is highlighted in forest-green. Hidden entirely on auth pages and
 *  fullscreen flows (Marker Studio overlays, report PDF view) so the
 *  tabs never collide with a critical action button.
 *
 *  Important: this adds a 56 px-tall sticky element. The pages that
 *  scroll naturally below it must add bottom-padding on mobile so the
 *  last content row isn't covered. We do that via the body class
 *  `has-bottom-tabs` toggled here. */

import React from "react";
import { Link, useLocation } from "react-router-dom";
import { Home, FolderOpen, Upload, User } from "lucide-react";
import { useAuth } from "@/lib/auth-context";

const TABS = [
  { to: "/",          label: "Home",    icon: Home,       testid: "mobile-tab-home" },
  { to: "/dashboard", label: "Reports", icon: FolderOpen, testid: "mobile-tab-reports", auth: true },
  { to: "/upload",    label: "Upload",  icon: Upload,     testid: "mobile-tab-upload",  auth: true, primary: true },
  { to: "/profile",   label: "Profile", icon: User,       testid: "mobile-tab-profile", auth: true },
];

// Routes where the tab bar should hide entirely (fullscreen / critical-action
// flows). Marker Studio + ScoutMode already render as their own portals so we
// don't need to special-case them — the tab bar will simply sit behind their
// z-index. Auth pages (login / signup) hide the bar to keep the form focused.
const HIDDEN_ROUTES = ["/login", "/signup"];

export default function MobileBottomTabs() {
  const location = useLocation();
  const { user } = useAuth();
  const pathname = location.pathname;

  // For unauthenticated users, the Profile tab routes to login; the Reports
  // tab also requires auth (RequireAuth wrapper will redirect). We KEEP the
  // tabs visible so the user always sees the path forward.
  if (HIDDEN_ROUTES.some((r) => pathname === r || pathname.startsWith(`${r}/`))) {
    return null;
  }

  const isActive = (to) => {
    if (to === "/") return pathname === "/";
    return pathname === to || pathname.startsWith(`${to}/`);
  };

  // Resolve each tab's destination: unauthenticated users see auth-gated tabs
  // route to /login (so the next click still goes somewhere meaningful).
  const resolveTo = (tab) => {
    if (tab.auth && !user) return "/login";
    if (tab.to === "/profile") {
      // /profile doesn't exist as a route — point admins to /admin, others
      // to /dashboard. Keeps the destination always meaningful.
      if (user?.role === "admin" || user?.role === "scout") return "/admin";
      return "/dashboard";
    }
    return tab.to;
  };

  return (
    <nav
      data-testid="mobile-bottom-tabs"
      aria-label="Primary"
      className="md:hidden fixed bottom-0 left-0 right-0 z-[60] bg-cream-card border-t border-ink/10"
      style={{ paddingBottom: "env(safe-area-inset-bottom, 0px)" }}
    >
      <ul className="flex items-stretch justify-around">
        {TABS.map((tab) => {
          const Icon = tab.icon;
          const active = isActive(tab.to);
          const to = resolveTo(tab);
          const isProfileForAdmin = tab.to === "/profile" && (user?.role === "admin" || user?.role === "scout");
          return (
            <li key={tab.to} className="flex-1">
              <Link
                to={to}
                data-testid={tab.testid}
                aria-current={active ? "page" : undefined}
                className={`flex flex-col items-center justify-center gap-1 py-2 transition-colors ${
                  active ? "text-forest" : "text-ink/55 hover:text-forest"
                }`}
              >
                {tab.primary ? (
                  <span
                    className={`inline-flex items-center justify-center w-9 h-9 rounded-full -mt-1 transition-colors ${
                      active ? "bg-forest text-white" : "bg-forest/15 text-forest"
                    }`}
                  >
                    <Icon className="w-5 h-5" strokeWidth={2.4} />
                  </span>
                ) : (
                  <Icon className="w-5 h-5" strokeWidth={active ? 2.4 : 2} />
                )}
                <span className="text-[10px] uppercase tracking-widest font-black leading-none">
                  {isProfileForAdmin && tab.label === "Profile" ? "Admin" : tab.label}
                </span>
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
