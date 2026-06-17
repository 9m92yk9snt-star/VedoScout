import { useEffect } from "react";
import "@/App.css";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { Toaster } from "sonner";
import { HelmetProvider } from "react-helmet-async";
import { AuthProvider, useAuth } from "@/lib/auth-context";

import Landing from "@/pages/Landing";
import Login from "@/pages/Login";
import Signup from "@/pages/Signup";
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

function RequireAuth({ children, adminOnly = false }) {
  const { user } = useAuth();
  if (!user) return <Navigate to="/login" replace />;
  if (adminOnly && user.role !== "admin" && user.role !== "scout") return <Navigate to="/dashboard" replace />;
  return children;
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
            <Routes>
              <Route path="/" element={<Landing />} />
              <Route path="/login" element={<Login />} />
              <Route path="/signup" element={<Signup />} />
              <Route path="/upload" element={<RequireAuth><UploadPage /></RequireAuth>} />
              <Route path="/dashboard" element={<RequireAuth><DashboardPage /></RequireAuth>} />
              <Route path="/trajectory/:id" element={<RequireAuth><TrajectoryPage /></RequireAuth>} />
              <Route path="/report/:id" element={<RequireAuth><ReportPage /></RequireAuth>} />
              <Route path="/admin" element={<RequireAuth adminOnly><AdminPage /></RequireAuth>} />
              <Route path="/about" element={<AboutPage />} />
              <Route path="/privacy" element={<PrivacyPage />} />
              <Route path="/methodology" element={<MethodologyPage />} />
              <Route path="/terms" element={<TermsPage />} />
              <Route path="/blog" element={<BlogIndexPage />} />
              <Route path="/blog/:slug" element={<BlogArticlePage />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </BrowserRouter>
        </AuthProvider>
      </HelmetProvider>
    </div>
  );
}

export default App;
