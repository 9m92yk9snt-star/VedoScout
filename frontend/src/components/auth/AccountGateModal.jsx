import React, { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { useAuth } from "@/lib/auth-context";
import { trackSignUp } from "@/lib/pixels";
import { trackFunnel } from "@/lib/analytics";
import { Mail, Lock, Eye, EyeOff, UserPlus, LogIn, ShieldCheck, X, CheckCircle2, Loader2 } from "lucide-react";
import { AuthInput, GoogleButton, OrDivider } from "@/components/auth/AuthShell";
import { PASSWORD_RULES } from "@/pages/Signup";

/* Account gate — shown to guests the moment they hit "Start analysis".
   Their video is already uploaded (background chunked upload), the player is
   marked and details are filled — creating the account is the LAST step
   before analysis starts. Email+password only, or Google. */
export default function AccountGateModal({ open, onClose, onAuthed, onGoogleRedirect, uploadReady, uploadPct = 0 }) {
  const [tab, setTab] = useState("signup"); // 'signup' | 'login'
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [busy, setBusy] = useState(false);
  const { signup, login } = useAuth();

  const rulesMet = useMemo(() => PASSWORD_RULES.map((r) => r.test(password)), [password]);
  const allRulesMet = rulesMet.every(Boolean);

  if (!open) return null;

  const deriveName = (em) => {
    const base = (em.split("@")[0] || "Player").replace(/[._\-+]+/g, " ").trim();
    return base.replace(/\b\w/g, (c) => c.toUpperCase()) || "Player";
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (tab === "signup" && !allRulesMet) {
      toast.error("Password doesn't meet all requirements.");
      return;
    }
    setBusy(true);
    try {
      if (tab === "signup") {
        await signup(email, password, deriveName(email), "");
        trackFunnel("signup");
        trackSignUp();
        toast.success("Account created — starting your analysis now.");
      } else {
        await login(email, password);
        toast.success("Welcome back — starting your analysis now.");
      }
      onAuthed?.();
    } catch (err) {
      toast.error(err?.response?.data?.detail || (tab === "signup" ? "Sign up failed" : "Login failed"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 z-[95] flex items-center justify-center p-4" data-testid="account-gate-modal">
      <div className="absolute inset-0 bg-[#10160C]/70 backdrop-blur-sm" onClick={busy ? undefined : onClose} />
      <div className="relative w-full max-w-md bg-white rounded-3xl shadow-[0_24px_70px_rgba(0,0,0,0.35)] p-6 md:p-7 max-h-[92vh] overflow-y-auto">
        <button
          type="button"
          onClick={onClose}
          disabled={busy}
          data-testid="gate-close-btn"
          className="absolute top-4 right-4 text-[#9AA08F] hover:text-[#161C12] transition-colors"
          aria-label="Close"
        >
          <X className="w-5 h-5" />
        </button>

        {/* Trust line */}
        <div
          className="flex items-start gap-2.5 rounded-xl bg-[#EDF4E2] px-4 py-3 text-[#2C4A0E]"
          data-testid="gate-trust-line"
        >
          {uploadReady ? (
            <ShieldCheck className="w-5 h-5 shrink-0 mt-0.5 text-[#63A61F]" />
          ) : (
            <Loader2 className="w-5 h-5 shrink-0 mt-0.5 text-[#63A61F] animate-spin" />
          )}
          <p className="text-sm leading-snug font-medium">
            {uploadReady
              ? "Your video is uploaded and ready — create a free account to see your analysis."
              : `Your video is uploading (${Math.min(99, uploadPct)}%) — it keeps going while you create your account.`}
          </p>
        </div>

        {/* Tabs */}
        <div className="mt-5 grid grid-cols-2 rounded-xl bg-[#F1EDDF] p-1 gap-1">
          <button
            type="button"
            onClick={() => setTab("signup")}
            data-testid="gate-tab-signup"
            className={`rounded-lg py-2.5 text-sm font-barlow font-black uppercase tracking-wide transition-colors ${
              tab === "signup" ? "bg-[#63A61F] text-white" : "text-[#3D4435] hover:text-[#161C12]"
            }`}
          >
            Create free account
          </button>
          <button
            type="button"
            onClick={() => setTab("login")}
            data-testid="gate-tab-login"
            className={`rounded-lg py-2.5 text-sm font-barlow font-black uppercase tracking-wide transition-colors ${
              tab === "login" ? "bg-[#63A61F] text-white" : "text-[#3D4435] hover:text-[#161C12]"
            }`}
          >
            Log in
          </button>
        </div>

        <form onSubmit={handleSubmit} className="mt-5 space-y-4" data-testid="gate-form">
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
              testId="gate-email"
            />
          </div>
          <div>
            <label className="block text-[15px] font-semibold text-[#161C12] mb-2">Password</label>
            <AuthInput
              icon={Lock}
              type={showPassword ? "text" : "password"}
              required
              minLength={tab === "signup" ? 8 : undefined}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder={tab === "signup" ? "Create a password" : "Enter your password"}
              autoComplete={tab === "signup" ? "new-password" : "current-password"}
              testId="gate-password"
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

          {tab === "signup" && (
            <ul className="space-y-1.5" data-testid="gate-password-rules">
              {PASSWORD_RULES.map((r, i) => (
                <li key={r.key} className="flex items-center gap-2">
                  <CheckCircle2 className={`w-4 h-4 shrink-0 ${rulesMet[i] ? "text-[#63A61F]" : "text-[#C9C4B4]"}`} />
                  <span className={`text-[13px] ${rulesMet[i] ? "text-[#161C12]" : "text-[#6B7261]"}`}>{r.label}</span>
                </li>
              ))}
            </ul>
          )}

          {tab === "login" && (
            <div className="text-right">
              <Link to="/forgot-password" className="text-sm font-semibold text-[#63A61F] hover:text-[#446E12]" data-testid="gate-forgot-password">
                Forgot password?
              </Link>
            </div>
          )}

          <button
            type="submit"
            disabled={busy || (tab === "signup" && !allRulesMet)}
            data-testid="gate-submit"
            className="w-full flex items-center justify-center gap-3 rounded-xl bg-[#63A61F] hover:bg-[#558F17] text-white font-barlow font-black uppercase tracking-[0.08em] text-base py-3.5 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {busy ? (
              <Loader2 className="w-5 h-5 animate-spin" />
            ) : tab === "signup" ? (
              <UserPlus className="w-5 h-5" strokeWidth={2.4} />
            ) : (
              <LogIn className="w-5 h-5" strokeWidth={2.4} />
            )}
            {tab === "signup" ? "Create account & start analysis" : "Log in & start analysis"}
          </button>
        </form>

        <OrDivider />
        <GoogleButton
          onClick={onGoogleRedirect}
          disabled={!uploadReady}
          label={uploadReady ? "Continue with Google" : `Finishing upload… ${Math.min(99, uploadPct)}%`}
          testId="gate-google-btn"
        />
        {!uploadReady && (
          <p className="mt-2 text-center text-[11px] text-[#6B7261]">
            Google sign-in opens as soon as your video finishes uploading.
          </p>
        )}
      </div>
    </div>
  );
}
