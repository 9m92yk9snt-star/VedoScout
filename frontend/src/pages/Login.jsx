import React, { useState } from "react";
import { Link, useNavigate, useLocation } from "react-router-dom";
import { toast } from "sonner";
import { useAuth } from "@/lib/auth-context";
import { Mail, Lock, Eye, EyeOff, LogIn, ShieldCheck, ArrowRight } from "lucide-react";
import {
  AuthShell, AuthHeroImage, SmpLogo, AuthInput, GoogleButton, OrDivider,
  BenefitsStrip, TrustedBadge, googleRedirect,
} from "@/components/auth/AuthShell";

export default function Login() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [remember, setRemember] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const params = new URLSearchParams(location.search);
  const nextParam = params.get("next");
  const openPass = params.get("open_pass");
  const resolvedNext = nextParam
    ? (openPass ? `${nextParam}${nextParam.includes("?") ? "&" : "?"}open_pass=${openPass}` : nextParam)
    : null;

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSubmitting(true);
    try {
      const u = await login(email, password);
      toast.success("Welcome back");
      if (resolvedNext) {
        navigate(resolvedNext);
      } else if (u.role === "admin" || u.role === "scout") {
        navigate("/admin");
      } else if (u.is_paid_scout) {
        navigate("/players-database");
      } else {
        navigate("/dashboard");
      }
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Login failed");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <AuthShell>
      <AuthHeroImage />

      <div className="relative">
        <SmpLogo />

        {/* Headline */}
        <div className="mt-8 md:mt-10 max-w-[62%] md:max-w-[58%]">
          <h1 className="font-barlow font-black uppercase tracking-tight leading-[0.95] text-4xl sm:text-5xl text-[#161C12]" data-testid="login-headline">
            WELCOME BACK
            <span className="block text-[#63A61F] mt-1">CONTINUE YOUR FOOTBALL JOURNEY</span>
          </h1>
          <p className="mt-4 text-[15px] md:text-base leading-relaxed text-[#3D4435]">
            Log in to access your <span className="text-[#63A61F] font-semibold">dashboard</span>,
            track your <span className="text-[#63A61F] font-semibold">progress</span> and
            view your <span className="text-[#63A61F] font-semibold">reports</span>.
          </p>
        </div>

        {/* Card */}
        <div className="relative mt-8 bg-white rounded-3xl shadow-[0_24px_70px_rgba(30,50,10,0.12)] p-6 md:p-8" data-testid="login-card">
          <div className="flex items-center gap-4">
            <div className="w-14 h-14 rounded-full bg-[#EDF4E2] flex items-center justify-center shrink-0">
              <ShieldCheck className="w-7 h-7 text-[#63A61F]" strokeWidth={2} />
            </div>
            <div>
              <div className="font-barlow font-black uppercase text-xl md:text-2xl tracking-tight text-[#161C12] leading-tight">
                <span className="text-[#63A61F]">LOG IN</span> TO YOUR ACCOUNT
              </div>
              <div className="text-sm text-[#3D4435]">
                Access your <span className="text-[#63A61F] font-semibold">reports</span>, <span className="text-[#63A61F] font-semibold">progress</span> and more.
              </div>
            </div>
          </div>

          <form onSubmit={handleSubmit} className="mt-6 space-y-4" data-testid="login-form">
            <div>
              <label className="block text-[15px] font-semibold text-[#161C12] mb-2">Email</label>
              <AuthInput
                icon={Mail}
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="Enter your email"
                autoComplete="email"
                testId="login-email"
              />
            </div>
            <div>
              <label className="block text-[15px] font-semibold text-[#161C12] mb-2">Password</label>
              <AuthInput
                icon={Lock}
                type={showPassword ? "text" : "password"}
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Enter your password"
                autoComplete="current-password"
                testId="login-password"
                rightSlot={
                  <button
                    type="button"
                    onClick={() => setShowPassword((v) => !v)}
                    className="absolute right-4 top-1/2 -translate-y-1/2 text-[#9AA08F] hover:text-[#161C12]"
                    tabIndex={-1}
                    aria-label="Toggle password visibility"
                  >
                    {showPassword ? <EyeOff className="w-5 h-5" /> : <Eye className="w-5 h-5" />}
                  </button>
                }
              />
            </div>

            <div className="flex items-center justify-between pt-1">
              <label className="flex items-center gap-2.5 cursor-pointer select-none">
                <input
                  type="checkbox"
                  checked={remember}
                  onChange={(e) => setRemember(e.target.checked)}
                  data-testid="login-remember-me"
                  className="w-4.5 h-4.5 w-[18px] h-[18px] rounded border-[#C9C4B4] text-[#63A61F] accent-[#63A61F]"
                />
                <span className="text-[15px] text-[#161C12]">Remember me</span>
              </label>
              <Link
                to="/forgot-password"
                data-testid="login-forgot-password"
                className="text-[15px] font-semibold text-[#63A61F] hover:text-[#446E12] transition-colors"
              >
                Forgot password?
              </Link>
            </div>

            <button
              type="submit"
              disabled={submitting}
              data-testid="login-submit"
              className="w-full flex items-center justify-center gap-3 rounded-xl bg-[#63A61F] hover:bg-[#558F17] text-white font-barlow font-black uppercase tracking-[0.08em] text-lg py-4 transition-colors disabled:opacity-60"
            >
              <LogIn className="w-5 h-5" strokeWidth={2.4} />
              {submitting ? "Signing in..." : "LOG IN"}
            </button>
          </form>

          <OrDivider />
          <GoogleButton onClick={() => googleRedirect("/dashboard")} testId="login-google-btn" />

          <p className="mt-5 text-center text-[15px] text-[#3D4435]">
            Don&apos;t have an account?{" "}
            <Link
              to={`/signup${location.search || ""}`}
              data-testid="login-to-signup"
              className="inline-flex items-center gap-1.5 font-semibold text-[#63A61F] hover:text-[#446E12] transition-colors"
            >
              Create free account <ArrowRight className="w-4 h-4" />
            </Link>
          </p>
        </div>

        {/* Benefits + trust */}
        <div className="mt-8">
          <BenefitsStrip />
        </div>
        <div className="mt-8">
          <TrustedBadge />
        </div>
      </div>
    </AuthShell>
  );
}
