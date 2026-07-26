import React, { useMemo, useState } from "react";
import { Link, useNavigate, useLocation } from "react-router-dom";
import { toast } from "sonner";
import { useAuth } from "@/lib/auth-context";
import Navigation from "@/components/Navigation";
import { trackSignUp } from "@/lib/pixels";
import { ArrowRight, Check, X, Eye, EyeOff, ShieldCheck } from "lucide-react";

const RULES = [
  { key: "len", label: "At least 10 characters", test: (p) => p.length >= 10 },
  { key: "lower", label: "One lowercase letter", test: (p) => /[a-z]/.test(p) },
  { key: "upper", label: "One uppercase letter", test: (p) => /[A-Z]/.test(p) },
  { key: "digit", label: "One number", test: (p) => /\d/.test(p) },
  { key: "symbol", label: "One symbol (! ? # $ %)", test: (p) => /[^A-Za-z0-9]/.test(p) },
];

function scorePassword(pw) {
  return RULES.filter((r) => r.test(pw)).length;
}

export default function Signup() {
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  // Hidden honeypot — matches the backend `website` field.
  // Bots that auto-fill every input trigger this and get rejected.
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

  const score = useMemo(() => scorePassword(password), [password]);
  const passwordsMatch = password && password === confirmPassword;
  const canSubmit = score === RULES.length && passwordsMatch && fullName.trim() && email.trim();

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (score < RULES.length) {
      toast.error("Password doesn't meet all requirements.");
      return;
    }
    if (!passwordsMatch) {
      toast.error("Passwords don't match.");
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

  const strengthLabel = ["Very weak", "Weak", "Fair", "Strong", "Very strong", "Excellent"][score];
  const strengthColor = [
    "bg-red-500/70", "bg-red-400", "bg-orange-400", "bg-yellow-400", "bg-lime-400", "bg-forest-pop",
  ][score];

  return (
    <div className="min-h-screen bg-deepnavy text-ink">
      <Navigation />
      <div className="pt-32 pb-20 px-6">
        <div className="max-w-md mx-auto">
          <span className="text-volt text-xs uppercase tracking-[0.25em] font-bold">Get started</span>
          <h1 className="mt-3 font-barlow font-black uppercase text-5xl tracking-tighter leading-[0.95]">
            Create account
          </h1>
          <p className="mt-3 text-ink/65 text-sm">
            Free preview included. No card required to start.
          </p>

          <form onSubmit={handleSubmit} className="mt-10 space-y-5" data-testid="signup-form">
            <div>
              <label className="text-xs uppercase tracking-[0.2em] font-bold text-ink/55 block mb-2">Full name</label>
              <input
                type="text" required
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                data-testid="signup-name"
                className="w-full bg-surface border border-gray-border px-4 py-3 text-ink focus:outline-none focus:border-volt focus:ring-1 focus:ring-volt transition-colors"
                placeholder="Jane Doe"
              />
            </div>

            <div>
              <label className="text-xs uppercase tracking-[0.2em] font-bold text-ink/55 block mb-2">Email</label>
              <input
                type="email" required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                data-testid="signup-email"
                className="w-full bg-surface border border-gray-border px-4 py-3 text-ink focus:outline-none focus:border-volt focus:ring-1 focus:ring-volt transition-colors"
                placeholder="you@email.com"
                autoComplete="email"
              />
            </div>

            <div>
              <label className="text-xs uppercase tracking-[0.2em] font-bold text-ink/55 block mb-2">
                Password
              </label>
              <div className="relative">
                <input
                  type={showPassword ? "text" : "password"}
                  required
                  minLength={10}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  data-testid="signup-password"
                  className="w-full bg-surface border border-gray-border pl-4 pr-11 py-3 text-ink focus:outline-none focus:border-volt focus:ring-1 focus:ring-volt transition-colors"
                  placeholder="Minimum 10 characters"
                  autoComplete="new-password"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword((v) => !v)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-ink/50 hover:text-ink"
                  tabIndex={-1}
                  aria-label="Toggle password visibility"
                >
                  {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>

              {/* Strength meter */}
              {password.length > 0 && (
                <div className="mt-2 space-y-2" data-testid="password-strength">
                  <div className="flex gap-1">
                    {[0, 1, 2, 3, 4].map((i) => (
                      <div
                        key={i}
                        className={`h-1 flex-1 transition-colors ${
                          i < score ? strengthColor : "bg-white/10"
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
                          {ok ? (
                            <Check className="w-3 h-3 text-forest-pop shrink-0" />
                          ) : (
                            <X className="w-3 h-3 text-ink/30 shrink-0" />
                          )}
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
                Confirm password
              </label>
              <input
                type={showPassword ? "text" : "password"}
                required
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                data-testid="signup-password-confirm"
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
                <p className="mt-1.5 text-[11px] text-red-400">Passwords don't match yet.</p>
              )}
              {passwordsMatch && (
                <p className="mt-1.5 text-[11px] text-forest-pop inline-flex items-center gap-1">
                  <Check className="w-3 h-3" /> Passwords match.
                </p>
              )}
            </div>

            {/* Honeypot — visually hidden, not tabbable, not autocompletable */}
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
              className="w-full bg-volt hover:bg-forest-pop text-white font-barlow font-black uppercase tracking-widest text-base px-8 py-4 transition-colors disabled:opacity-40 disabled:cursor-not-allowed flex items-center justify-center gap-2"
            >
              {submitting ? "Creating..." : "Create account"}
              {!submitting && <ArrowRight className="w-4 h-4" />}
            </button>

            <div className="flex items-center justify-center gap-2 text-[10px] uppercase tracking-widest font-bold text-ink/40">
              <ShieldCheck className="w-3 h-3" />
              Passwords are bcrypt-hashed · never stored in plain text
            </div>
          </form>

          <p className="mt-8 text-sm text-ink/55 text-center">
            Have an account?{" "}
            <Link
              to={`/login${location.search || ""}`}
              data-testid="signup-to-login"
              className="text-volt hover:text-ink transition-colors uppercase tracking-widest font-semibold"
            >
              Log in
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
