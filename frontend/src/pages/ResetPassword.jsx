import React, { useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import Navigation from "@/components/Navigation";
import { ArrowRight, Check, X, Eye, EyeOff, ShieldCheck } from "lucide-react";
import api from "@/lib/api";
import { useAuth } from "@/lib/auth-context";

const RULES = [
  { key: "len", label: "At least 10 characters", test: (p) => p.length >= 10 },
  { key: "lower", label: "One lowercase letter", test: (p) => /[a-z]/.test(p) },
  { key: "upper", label: "One uppercase letter", test: (p) => /[A-Z]/.test(p) },
  { key: "digit", label: "One number", test: (p) => /\d/.test(p) },
  { key: "symbol", label: "One symbol (! ? # $ %)", test: (p) => /[^A-Za-z0-9]/.test(p) },
];
const score = (pw) => RULES.filter((r) => r.test(pw)).length;

export default function ResetPassword() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const token = params.get("token") || "";
  const { setAuthFromResponse } = useAuth();

  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const s = useMemo(() => score(password), [password]);
  const passwordsMatch = password && password === confirmPassword;
  const canSubmit = s === RULES.length && passwordsMatch && token;

  if (!token) {
    return (
      <div className="min-h-screen bg-deepnavy text-ink">
        <Navigation />
        <div className="pt-32 pb-20 px-6 max-w-md mx-auto">
          <h1 className="font-barlow font-black uppercase text-4xl">Invalid reset link</h1>
          <p className="mt-3 text-ink/60 text-sm">
            This link is missing its token. Request a fresh one from the forgot-password page.
          </p>
          <Link
            to="/forgot-password"
            className="mt-8 inline-flex items-center gap-2 bg-volt hover:bg-forest-pop text-white font-barlow font-black uppercase tracking-widest text-sm px-6 py-3 transition-colors"
          >
            Request new link <ArrowRight className="w-4 h-4" />
          </Link>
        </div>
      </div>
    );
  }

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (s < RULES.length) {
      toast.error("Password doesn't meet all requirements.");
      return;
    }
    if (!passwordsMatch) {
      toast.error("Passwords don't match.");
      return;
    }
    setSubmitting(true);
    try {
      const { data } = await api.post("/auth/reset-password", {
        token,
        new_password: password,
      });
      if (data?.access_token) {
        // Persist the fresh session — user is logged in immediately.
        localStorage.setItem("elite_token", data.access_token);
        localStorage.setItem("elite_user", JSON.stringify(data.user));
        if (typeof setAuthFromResponse === "function") setAuthFromResponse(data);
      }
      toast.success("Password updated. You're logged in.");
      const u = data?.user;
      if (u?.role === "admin" || u?.role === "scout") navigate("/admin");
      else if (u?.is_paid_scout) navigate("/players-database");
      else navigate("/dashboard");
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Could not reset password");
    } finally {
      setSubmitting(false);
    }
  };

  const strengthLabel = ["Very weak", "Weak", "Fair", "Strong", "Very strong", "Excellent"][s];
  const strengthColor = [
    "bg-red-500/70", "bg-red-400", "bg-orange-400", "bg-yellow-400", "bg-lime-400", "bg-forest-pop",
  ][s];

  return (
    <div className="min-h-screen bg-deepnavy text-ink" data-testid="reset-password-page">
      <Navigation />
      <div className="pt-32 pb-20 px-6">
        <div className="max-w-md mx-auto">
          <span className="text-volt text-xs uppercase tracking-[0.25em] font-bold">
            Reset password
          </span>
          <h1 className="mt-3 font-barlow font-black uppercase text-5xl tracking-tighter leading-[0.95]">
            Pick a new<br />password.
          </h1>
          <p className="mt-3 text-ink/65 text-sm">
            You&apos;ll be logged in automatically once it&apos;s saved.
          </p>

          <form onSubmit={handleSubmit} className="mt-10 space-y-5" data-testid="reset-form">
            <div>
              <label className="text-xs uppercase tracking-[0.2em] font-bold text-ink/55 block mb-2">
                New password
              </label>
              <div className="relative">
                <input
                  type={showPassword ? "text" : "password"}
                  required minLength={10}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  data-testid="reset-password-input"
                  className="w-full bg-surface border border-gray-border pl-4 pr-11 py-3 text-ink focus:outline-none focus:border-volt focus:ring-1 focus:ring-volt transition-colors"
                  placeholder="Minimum 10 characters"
                  autoComplete="new-password"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword((v) => !v)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-ink/50 hover:text-ink"
                  tabIndex={-1}
                >
                  {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>

              {password.length > 0 && (
                <div className="mt-2 space-y-2">
                  <div className="flex gap-1">
                    {[0, 1, 2, 3, 4].map((i) => (
                      <div
                        key={i}
                        className={`h-1 flex-1 transition-colors ${
                          i < s ? strengthColor : "bg-white/10"
                        }`}
                      />
                    ))}
                  </div>
                  <div className="text-[10px] uppercase tracking-widest font-black text-ink/70">
                    {strengthLabel}
                  </div>
                  <ul className="text-[11px] text-ink/60 space-y-1 mt-2">
                    {RULES.map((r) => {
                      const ok = r.test(password);
                      return (
                        <li key={r.key} className="flex items-center gap-2">
                          {ok ? <Check className="w-3 h-3 text-forest-pop shrink-0" /> : <X className="w-3 h-3 text-ink/30 shrink-0" />}
                          <span className={ok ? "text-ink/70" : "text-ink/40"}>{r.label}</span>
                        </li>
                      );
                    })}
                  </ul>
                </div>
              )}
            </div>

            <div>
              <label className="text-xs uppercase tracking-[0.2em] font-bold text-ink/55 block mb-2">
                Confirm new password
              </label>
              <input
                type={showPassword ? "text" : "password"}
                required
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                data-testid="reset-password-confirm"
                className={`w-full bg-surface border px-4 py-3 text-ink focus:outline-none focus:ring-1 transition-colors ${
                  confirmPassword && !passwordsMatch
                    ? "border-red-500 focus:border-red-500 focus:ring-red-500"
                    : passwordsMatch
                      ? "border-forest-pop/60 focus:border-forest-pop focus:ring-forest-pop"
                      : "border-gray-border focus:border-volt focus:ring-volt"
                }`}
                placeholder="Type it again"
                autoComplete="new-password"
              />
              {confirmPassword && !passwordsMatch && (
                <p className="mt-1.5 text-[11px] text-red-400">Passwords don&apos;t match yet.</p>
              )}
              {passwordsMatch && (
                <p className="mt-1.5 text-[11px] text-forest-pop inline-flex items-center gap-1">
                  <Check className="w-3 h-3" /> Passwords match.
                </p>
              )}
            </div>

            <button
              type="submit"
              disabled={submitting || !canSubmit}
              data-testid="reset-submit"
              className="w-full bg-volt hover:bg-forest-pop text-white font-barlow font-black uppercase tracking-widest text-base px-8 py-4 transition-colors disabled:opacity-40 disabled:cursor-not-allowed flex items-center justify-center gap-2"
            >
              {submitting ? "Saving..." : "Set new password & log in"}
              {!submitting && <ArrowRight className="w-4 h-4" />}
            </button>

            <div className="flex items-center justify-center gap-2 text-[10px] uppercase tracking-widest font-bold text-ink/40">
              <ShieldCheck className="w-3 h-3" />
              One-time use link · valid for 60 minutes
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}
