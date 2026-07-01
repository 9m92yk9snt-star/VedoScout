import React, { useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import Navigation from "@/components/Navigation";
import { ArrowRight, Mail, ShieldCheck } from "lucide-react";
import api from "@/lib/api";

export default function ForgotPassword() {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSubmitting(true);
    try {
      await api.post("/auth/forgot-password", { email });
      setSent(true);
    } catch (err) {
      // Even on unexpected errors we show the generic success (matches the
      // backend privacy stance — never leak whether the email exists).
      setSent(true);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen bg-deepnavy text-ink" data-testid="forgot-password-page">
      <Navigation />
      <div className="pt-32 pb-20 px-6">
        <div className="max-w-md mx-auto">
          <span className="text-volt text-xs uppercase tracking-[0.25em] font-bold">
            Forgot password
          </span>
          <h1 className="mt-3 font-barlow font-black uppercase text-5xl tracking-tighter leading-[0.95]">
            Reset it in<br />60 seconds.
          </h1>
          <p className="mt-3 text-ink/65 text-sm">
            Enter the email on your ScoutMePlay account. We&apos;ll send a one-time reset link
            valid for 60 minutes.
          </p>

          {sent ? (
            <div className="mt-10 border border-forest/40 bg-forest/5 p-6" data-testid="forgot-sent">
              <div className="flex items-center gap-2 mb-3">
                <Mail className="w-5 h-5 text-forest-pop" />
                <div className="text-[10px] uppercase tracking-[0.24em] font-black text-forest-pop">
                  Check your inbox
                </div>
              </div>
              <p className="text-ink/80 text-sm leading-relaxed">
                If an account exists for <strong>{email || "that email"}</strong>, we&apos;ve just sent a reset link.
                Click the button in the email within the next <strong>60 minutes</strong>.
              </p>
              <p className="mt-4 text-[12px] text-ink/50">
                Nothing arriving? Check your spam folder, or{" "}
                <button
                  type="button"
                  onClick={() => { setSent(false); setEmail(""); }}
                  className="text-volt hover:text-ink underline underline-offset-2"
                >
                  try a different email
                </button>.
              </p>
            </div>
          ) : (
            <form onSubmit={handleSubmit} className="mt-10 space-y-5" data-testid="forgot-form">
              <div>
                <label className="text-xs uppercase tracking-[0.2em] font-bold text-ink/55 block mb-2">
                  Email
                </label>
                <input
                  type="email" required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  data-testid="forgot-email"
                  className="w-full bg-surface border border-gray-border px-4 py-3 text-ink focus:outline-none focus:border-volt focus:ring-1 focus:ring-volt transition-colors"
                  placeholder="you@email.com"
                  autoComplete="email"
                />
              </div>
              <button
                type="submit"
                disabled={submitting}
                data-testid="forgot-submit"
                className="w-full bg-volt hover:bg-forest-pop text-white font-barlow font-black uppercase tracking-widest text-base px-8 py-4 transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
              >
                {submitting ? "Sending..." : "Send reset link"}
                {!submitting && <ArrowRight className="w-4 h-4" />}
              </button>
              <div className="flex items-center justify-center gap-2 text-[10px] uppercase tracking-widest font-bold text-ink/40">
                <ShieldCheck className="w-3 h-3" />
                No email enumeration · rate-limited to prevent abuse
              </div>
            </form>
          )}

          <p className="mt-8 text-sm text-ink/55 text-center">
            Remembered it?{" "}
            <Link
              to="/login"
              data-testid="forgot-to-login"
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
