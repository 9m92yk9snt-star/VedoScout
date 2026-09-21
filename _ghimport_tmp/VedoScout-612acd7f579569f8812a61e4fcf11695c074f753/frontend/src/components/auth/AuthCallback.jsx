import React, { useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { Loader2 } from "lucide-react";
import api from "@/lib/api";
import { useAuth } from "@/lib/auth-context";

/* Emergent Google OAuth callback — the user lands anywhere on the app with
   #session_id=... in the URL fragment. AppRouter renders this component
   synchronously (before any protected route runs), we exchange the session_id
   server-side for our own JWT and continue.
   REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH */
export default function AuthCallback() {
  const hasProcessed = useRef(false);
  const navigate = useNavigate();
  const { setAuthFromResponse } = useAuth();

  useEffect(() => {
    if (hasProcessed.current) return;
    hasProcessed.current = true;
    const sid = new URLSearchParams((window.location.hash || "").replace(/^#/, "")).get("session_id");
    (async () => {
      try {
        const { data } = await api.post("/auth/google/session", { session_id: sid });
        setAuthFromResponse(data);
        window.history.replaceState(null, "", window.location.pathname);
        const hasResume = !!sessionStorage.getItem("smp_resume_upload");
        if (hasResume) {
          navigate("/upload", { replace: true });
        } else if (data.user?.role === "admin" || data.user?.role === "scout") {
          navigate("/admin", { replace: true });
        } else {
          navigate("/dashboard", { replace: true });
        }
      } catch (err) {
        toast.error(err?.response?.data?.detail || "Google sign-in failed. Please try again.");
        window.history.replaceState(null, "", window.location.pathname);
        navigate("/login", { replace: true });
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="min-h-screen flex flex-col items-center justify-center gap-4" style={{ backgroundColor: "#F4F0E5" }} data-testid="auth-callback-loading">
      <Loader2 className="w-8 h-8 animate-spin text-[#63A61F]" />
      <span className="font-barlow font-bold uppercase tracking-[0.2em] text-sm text-[#3D4435]">Signing you in…</span>
    </div>
  );
}
