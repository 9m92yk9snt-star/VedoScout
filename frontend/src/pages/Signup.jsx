import React, { useMemo, useState } from "react";
import { Link, useNavigate, useLocation } from "react-router-dom";
import { toast } from "sonner";
import { useAuth } from "@/lib/auth-context";
import { trackSignUp } from "@/lib/pixels";
import { Mail, Lock, User, Eye, EyeOff, UserPlus, ArrowRight, CheckCircle2 } from "lucide-react";
import {
  AuthShell, AuthHeroImage, SmpLogo, AuthInput, GoogleButton, OrDivider,
  BenefitsStrip, TrustedBadge, googleRedirect,
} from "@/components/auth/AuthShell";

export const PASSWORD_RULES = [
  { key: "len", label: "At least 8 characters", test: (p) => p.length >= 8 },
  { key: "upper", label: "One uppercase letter", test: (p) => /[A-Z]/.test(p) },
  { key: "digit", label: "One number", test: (p) => /\d/.test(p) },
];

export default function Signup() {
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  // Hidden honeypot — matches the backend `website` field.
  const [honeypot, setHoneypot] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const { signup } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const params = new URLSearchParams(location.search);
  const nextParam = params.get("next");
  const openPass = params.get("open_pass");
  const resolvedNext = nextParam
    ? (openPass ? `${nextParam}${nextParam.includes("?") ? "&" : "?"}open_pass=${openPass}` : nextParam)
    : null;

  const rulesMet = useMemo(() => PASSWORD_RULES.map((r) => r.test(password)), [password]);
  const allRulesMet = rulesMet.every(Boolean);
  const canSubmit = allRulesMet && fullName.trim() && email.trim();

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!allRulesMet) {
      toast.error("Password doesn't meet all requirements.");
      return;
    }
    setSubmitting(true);
    try {
      await signup(email, password, fullName, honeypot);
      trackSignUp();
      toast.success("Account created. Let's upload your video.");
      navigate(resolvedNext || "/upload");
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Sign up failed");
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
          <h1 className="font-barlow font-black uppercase tracking-tight leading-[0.95] text-4xl sm:text-5xl text-[#161C12]" data-testid="signup-headline">
            DISCOVER YOUR
            <span className="block text-[#63A61F] mt-1">TRUE FOOTBALL LEVEL</span>
          </h1>
          <p className="mt-4 text-[15px] md:text-base leading-relaxed text-[#3D4435]">
            Professional powered by <span className="text-[#63A61F] font-semibold">ScoutMe pro</span>{" "}
            benchmark analysis and real football scouts.
          </p>
        </div>

        {/* Card */}
        <div className="relative mt-8 bg-white rounded-3xl shadow-[0_24px_70px_rgba(30,50,10,0.12)] p-6 md:p-8" data-testid="signup-card">
          <form onSubmit={handleSubmit} className="space-y-4" data-testid="signup-form">
            <div>
              <label className="block text-[15px] font-semibold text-[#161C12] mb-2">Full Name</label>
              <AuthInput
                icon={User}
                type="text"
                required
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                placeholder="Enter your full name"
                autoComplete="name"
                testId="signup-name"
              />
            </div>
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
                testId="signup-email"
              />
            </div>
            <div>
              <label className="block text-[15px] font-semibold text-[#161C12] mb-2">Password</label>
              <AuthInput
                icon={Lock}
                type={showPassword ? "text" : "password"}
                required
                minLength={8}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Create a password"
                autoComplete="new-password"
                testId="signup-password"
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

            {/* Password requirements checklist — always visible per mockup */}
            <ul className="space-y-2 pt-1" data-testid="signup-password-rules">
              {PASSWORD_RULES.map((r, i) => (
                <li key={r.key} className="flex items-center gap-2.5">
                  <CheckCircle2
                    className={`w-5 h-5 shrink-0 transition-colors ${rulesMet[i] ? "text-[#63A61F]" : "text-[#C9C4B4]"}`}
                    strokeWidth={2}
                  />
                  <span className={`text-[15px] ${rulesMet[i] ? "text-[#161C12]" : "text-[#6B7261]"}`}>{r.label}</span>
                </li>
              ))}
            </ul>

            {/* Honeypot — visually hidden, not tabbable */}
            <div aria-hidden="true" className="absolute -left-[9999px] w-px h-px overflow-hidden opacity-0 pointer-events-none">
              <label>
                Do not fill this
                <input
                  type="text"
                  tabIndex={-1}
                  autoComplete="off"
                  value={honeypot}
                  onChange={(e) => setHoneypot(e.target.value)}
                  name="website"
                />
              </label>
            </div>

            <button
              type="submit"
              disabled={submitting || !canSubmit}
              data-testid="signup-submit"
              className="w-full flex items-center justify-center gap-3 rounded-xl bg-[#63A61F] hover:bg-[#558F17] text-white font-barlow font-black uppercase tracking-[0.08em] text-lg py-4 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <UserPlus className="w-5 h-5" strokeWidth={2.4} />
              {submitting ? "Creating..." : "CREATE FREE ACCOUNT"}
            </button>

            <p className="text-center text-[15px] text-[#3D4435]">
              Already have an account?{" "}
              <Link
                to={`/login${location.search || ""}`}
                data-testid="signup-to-login"
                className="inline-flex items-center gap-1.5 font-semibold text-[#63A61F] hover:text-[#446E12] transition-colors"
              >
                Sign in <ArrowRight className="w-4 h-4" />
              </Link>
            </p>
          </form>

          <OrDivider />
          <GoogleButton onClick={() => googleRedirect("/dashboard")} testId="signup-google-btn" />
        </div>

        {/* Benefits + avatars + trust */}
        <div className="mt-8">
          <BenefitsStrip />
        </div>
        <div className="mt-8">
          <TrustedBadge withAvatars />
        </div>
      </div>
    </AuthShell>
  );
}
