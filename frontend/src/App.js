import { useEffect, useState } from "react";
import "@/App.css";
import { BrowserRouter, Routes, Route, Navigate, useLocation } from "react-router-dom";
import { Toaster } from "sonner";
import { HelmetProvider } from "react-helmet-async";
import { AnimatePresence, motion } from "framer-motion";
import { AuthProvider, useAuth } from "@/lib/auth-context";
import api from "@/lib/api";

import Landing from "@/pages/Landing";
import LandingMinimal from "@/pages/LandingMinimal";
import Login from "@/pages/Login";
import Signup from "@/pages/Signup";
import ForgotPassword from "@/pages/ForgotPassword";
import ResetPassword from "@/pages/ResetPassword";
import UploadPage from "@/pages/UploadPage";
import ReportPage from "@/pages/ReportPage";
import AdminPage from "@/pages/AdminPage";
import DashboardPage from "@/pages/DashboardPage";
import AboutPage from "@/pages/AboutPage";
import PrivacyPage from "@/pages/PrivacyPage";
import MethodologyPage from "@/pages/MethodologyPage";
import TermsPage from "@/pages/TermsPage";
import BlogIndexPage from "@/pages/BlogIndexPage";
import BlogArticlePage from "@/pages/BlogArticlePage";
import TrajectoryPage from "@/pages/TrajectoryPage";
import ScoutsLandingPage from "@/pages/ScoutsLandingPage";
import PlayersDatabasePage from "@/pages/PlayersDatabasePage";
import AuthCallback from "@/components/auth/AuthCallback";
import CookieBanner from "@/components/CookieBanner";
import MobileBottomTabs from "@/components/MobileBottomTabs";
import { initPixels, trackPageView } from "@/lib/pixels";
import BackgroundAnalysisTracker from "@/components/BackgroundAnalysisTracker";

function RequireAuth({ children, adminOnly = false }) {
  const { user } = useAuth();
  if (!user) return <Navigate to="/login" replace />;
  if (adminOnly && user.role !== "admin" && user.role !== "scout") return <Navigate to="/dashboard" replace />;
  return children;
}

/* ── LandingRoute — chooses between the long-form <Landing /> and the
   short conversion-focused <LandingMinimal /> based on the admin-set
   `active_landing` value pulled from /api/settings/landing. Defaults to
   the minimal landing if the call fails or no value is set yet. The
   decision is cached in localStorage so subsequent navigations render
   instantly. */
function LandingRoute() {
  const cached = (() => {
    try { return window.localStorage.getItem("scoutmeplay.active_landing"); } catch { return null; }
  })();
  const [variant, setVariant] = useState(cached === "minimal" || cached === "full" ? cached : "minimal");

  useEffect(() => {
    let cancelled = false;
    api.get("/settings/landing")
      .then(({ data }) => {
        if (cancelled) return;
        const v = data?.active_landing === "full" ? "full" : "minimal";
        setVariant(v);
        try { window.localStorage.setItem("scoutmeplay.active_landing", v); } catch { /* private mode */ }
      })
      .catch(() => { if (!cancelled) setVariant((prev) => prev || "minimal"); });
    return () => { cancelled = true; };
  }, []);

  if (variant === "full") return <Landing />;
  return <LandingMinimal />;
}

/* ── Page transition wrapper — Framer Motion slide+fade between routes.
   AnimatePresence's mode="wait" ensures the outgoing page finishes its
   exit animation before the incoming one begins, so the user sees a
   clean 220 ms transition. Routes are keyed by location.pathname so
   AnimatePresence detects the change. */
function AnimatedRoutes() {
  const location = useLocation();
  useEffect(() => { initPixels(); }, []);
  useEffect(() => { trackPageView(); }, [location.pathname]);
  // Emergent Google OAuth callback — must run BEFORE any protected route.
  // Synchronous render-time check on useLocation().hash (per playbook).
  if (location.hash && location.hash.includes("session_id=")) {
    return <AuthCallback />;
  }
  return (
    <AnimatePresence mode="wait" initial={false}>
      <Routes location={location} key={location.pathname}>
        <Route path="/" element={<PageTransition><LandingRoute /></PageTransition>} />
        <Route path="/login" element={<PageTransition><Login /></PageTransition>} />
        <Route path="/signup" element={<PageTransition><Signup /></PageTransition>} />
        <Route path="/register" element={<Navigate to="/signup" replace />} />
        <Route path="/forgot-password" element={<PageTransition><ForgotPassword /></PageTransition>} />
        <Route path="/reset-password" element={<PageTransition><ResetPassword /></PageTransition>} />
        {/* /upload is PUBLIC — guests upload first, create an account right before analysis */}
        <Route path="/upload" element={<PageTransition><UploadPage /></PageTransition>} />
        <Route path="/dashboard" element={<PageTransition><RequireAuth><DashboardPage /></RequireAuth></PageTransition>} />
        <Route path="/trajectory/:id" element={<PageTransition><RequireAuth><TrajectoryPage /></RequireAuth></PageTransition>} />
        <Route path="/report/:id" element={<PageTransition><RequireAuth><ReportPage /></RequireAuth></PageTransition>} />
        <Route path="/admin" element={<PageTransition><RequireAuth adminOnly><AdminPage /></RequireAuth></PageTransition>} />
        <Route path="/about" element={<PageTransition><AboutPage /></PageTransition>} />
        <Route path="/privacy" element={<PageTransition><PrivacyPage /></PageTransition>} />
        <Route path="/methodology" element={<PageTransition><MethodologyPage /></PageTransition>} />
        <Route path="/terms" element={<PageTransition><TermsPage /></PageTransition>} />
        <Route path="/blog" element={<PageTransition><BlogIndexPage /></PageTransition>} />
        <Route path="/blog/:slug" element={<PageTransition><BlogArticlePage /></PageTransition>} />
        <Route path="/scouts" element={<PageTransition><ScoutsLandingPage /></PageTransition>} />
        <Route path="/players-database" element={<PageTransition><RequireAuth><PlayersDatabasePage /></RequireAuth></PageTransition>} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </AnimatePresence>
  );
}

function PageTransition({ children }) {
  // Honour the user's reduced-motion preference — if they prefer reduced
  // motion, skip the transform and just fade.
  const prefersReducedMotion = typeof window !== "undefined"
    && window.matchMedia
    && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const motionInit = prefersReducedMotion ? { opacity: 0 } : { opacity: 0, y: 10 };
  const motionExit = prefersReducedMotion ? { opacity: 0 } : { opacity: 0, y: -10 };
  return (
    <motion.div
      initial={motionInit}
      animate={{ opacity: 1, y: 0 }}
      exit={motionExit}
      transition={{ duration: 0.22, ease: "easeOut" }}
    >
      {children}
    </motion.div>
  );
}

function App() {
  return (
    <div className="App">
      <HelmetProvider>
        <AuthProvider>
          <BrowserRouter>
            <Toaster
              position="top-right"
              theme="dark"
              toastOptions={{
                style: {
                  background: "#0F1623",
                  color: "#fff",
                  border: "1px solid rgba(255,255,255,0.1)",
                  borderRadius: 0,
                },
              }}
            />
            <AnimatedRoutes />
            <CookieBanner />
            <MobileBottomTabs />
            <BackgroundAnalysisTracker />
          </BrowserRouter>
        </AuthProvider>
      </HelmetProvider>
    </div>
  );
}

export default App;
