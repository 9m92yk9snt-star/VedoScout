// GuestWelcomePage — landing after a guest (logged-out) Stripe checkout.
// Polls /payments/guest/status/{session_id}; the account is auto-created from
// the Stripe email server-side. New buyers just pick a password (one field)
// and are logged straight in. Existing accounts get a login prompt.
import React, { useEffect, useRef, useState } from "react";
import { useLocation, useNavigate, Link } from "react-router-dom";
import { toast } from "sonner";
import Navigation from "@/components/Navigation";
import api from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { trackPurchase } from "@/lib/pixels";
import { CheckCircle2, Loader2, Lock, ArrowRight, Crown, Upload } from "lucide-react";

export default function GuestWelcomePage() {
  const location = useLocation();
  const navigate = useNavigate();
  const { setAuthFromResponse, user } = useAuth();
  const sessionId = new URLSearchParams(location.search).get("guest_session");

  const [state, setState] = useState("checking"); // checking | paid | pending_timeout | error
  const [result, setResult] = useState(null);
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const tracked = useRef(false);

  useEffect(() => {
    if (!sessionId) { setState("error"); return; }
    let alive = true;
    let attempts = 0;
    const poll = async () => {
      if (!alive) return;
      attempts += 1;
      try {
        const { data } = await api.get(`/payments/guest/status/${sessionId}`);
        if (!alive) return;
        if (data.payment_status === "paid") {
          setResult(data);
          setState("paid");
          if (!tracked.current) { tracked.current = true; trackPurchase(); }
          return;
        }
        if (attempts >= 15) { setState("pending_timeout"); return; }
        setTimeout(poll, 2000);
      } catch {
        if (!alive) return;
        if (attempts >= 15) { setState("error"); return; }
        setTimeout(poll, 2500);
      }
    };
    poll();
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId]);

  const nextPath = result?.kind === "guest_single" ? "/upload" : "/dashboard";
  const planLabel =
    result?.tier === "vip" ? "VIP Premium" : result?.tier === "premium" ? "Premium" : "Premium Report";

  const setUpPassword = async (e) => {
    e.preventDefault();
    if (busy) return;
    setBusy(true);
    try {
      const { data } = await api.post("/auth/reset-password", {
        token: result.setup_token,
        new_password: password,
      });
      setAuthFromResponse(data);
      toast.success("You're all set — welcome to ScoutMePlay!", { duration: 6000 });
      navigate(nextPath);
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Could not set your password — try again.", { duration: 8000 });
      setBusy(false);
    }
  };

  return (
    <div className="min-h-screen bg-cream-base text-ink">
      <Navigation />
      <div className="pt-28 pb-20 px-6">
        <div className="max-w-lg mx-auto" data-testid="guest-welcome-page">
          {state === "checking" && (
            <div className="text-center py-16" data-testid="guest-welcome-checking">
              <Loader2 className="w-8 h-8 animate-spin text-forest mx-auto" />
              <p className="mt-4 text-sm text-ink/60 font-bold uppercase tracking-widest">Confirming your payment…</p>
            </div>
          )}

          {(state === "error" || state === "pending_timeout") && (
            <div className="bg-cream-card border border-gray-border rounded-3xl p-8 text-center" data-testid="guest-welcome-error">
              <h1 className="font-barlow font-black uppercase text-2xl">
                {state === "pending_timeout" ? "Payment still processing" : "Something went wrong"}
              </h1>
              <p className="mt-2 text-sm text-ink/65">
                {state === "pending_timeout"
                  ? "Your payment is taking a little longer to confirm. Refresh this page in a moment — your access is safe."
                  : "We couldn't find this checkout session. If you completed a payment, contact us and we'll sort it out."}
              </p>
              <button
                type="button"
                onClick={() => window.location.reload()}
                data-testid="guest-welcome-retry-btn"
                className="mt-5 inline-flex items-center gap-2 bg-forest hover:bg-forest-pop text-white font-barlow font-black uppercase tracking-widest text-xs px-5 py-3 rounded-full transition-colors"
              >
                Try again
              </button>
            </div>
          )}

          {state === "paid" && result && (
            <div className="bg-cream-card border border-gray-border rounded-3xl overflow-hidden" data-testid="guest-welcome-paid">
              <div className="p-7 text-white text-center" style={{ background: "#0F1F14" }}>
                <span className="inline-flex w-14 h-14 rounded-full items-center justify-center mb-3" style={{ background: "#CCFF00" }}>
                  <CheckCircle2 className="w-7 h-7 text-[#0F1F14]" />
                </span>
                <h1 className="font-barlow font-black uppercase text-3xl tracking-tight leading-none">
                  Payment received!
                </h1>
                <p className="mt-2 text-sm text-white/70">
                  <Crown className="inline w-3.5 h-3.5 text-[#CCFF00] -mt-0.5" fill="#CCFF00" /> {planLabel} is now active
                  {result.email ? <> for <b className="text-white">{result.email}</b></> : null}.
                </p>
              </div>

              <div className="p-7">
                {user ? (
                  <div className="text-center">
                    <p className="text-sm text-ink/70">You're logged in — everything is ready.</p>
                    <Link
                      to={nextPath}
                      data-testid="guest-welcome-continue-btn"
                      className="mt-4 inline-flex items-center gap-2 bg-forest hover:bg-forest-pop text-white font-barlow font-black uppercase tracking-widest text-sm px-6 py-3.5 rounded-full transition-colors"
                    >
                      {result.kind === "guest_single" ? <><Upload className="w-4 h-4" /> Upload your video</> : <>Go to your dashboard <ArrowRight className="w-4 h-4" /></>}
                    </Link>
                  </div>
                ) : result.account_status === "created" && result.setup_token ? (
                  <form onSubmit={setUpPassword} data-testid="guest-welcome-password-form">
                    <h2 className="font-barlow font-black uppercase text-lg tracking-tight">One last step</h2>
                    <p className="mt-1 text-[13px] text-ink/60">
                      We created your account automatically. Choose a password to access
                      {result.kind === "guest_single" ? " your upload and report" : " your Premium dashboard"}.
                    </p>
                    <label className="block mt-4 text-[10px] font-extrabold uppercase tracking-wider text-ink/55 mb-1">
                      Choose a password (min. 8 characters)
                    </label>
                    <input
                      type="password"
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      minLength={8}
                      required
                      autoFocus
                      data-testid="guest-welcome-password-input"
                      className="w-full bg-white border border-gray-border rounded-xl px-4 py-3 text-sm focus:outline-none focus:border-forest"
                      placeholder="••••••••"
                    />
                    <button
                      type="submit"
                      disabled={busy || password.length < 8}
                      data-testid="guest-welcome-password-submit"
                      className="mt-4 w-full flex items-center justify-center gap-2 bg-forest hover:bg-forest-pop text-white font-barlow font-black uppercase tracking-widest text-sm px-6 py-3.5 rounded-full transition-colors disabled:opacity-50"
                    >
                      {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : (
                        result.kind === "guest_single" ? <>Continue to upload <ArrowRight className="w-4 h-4" /></> : <>Enter your dashboard <ArrowRight className="w-4 h-4" /></>
                      )}
                    </button>
                    <p className="mt-3 text-[11px] text-ink/45 flex items-center gap-1.5 justify-center">
                      <Lock className="w-3 h-3" /> Secured — you can change it anytime
                    </p>
                  </form>
                ) : (
                  <div className="text-center" data-testid="guest-welcome-existing">
                    <h2 className="font-barlow font-black uppercase text-lg tracking-tight">Linked to your account</h2>
                    <p className="mt-1 text-[13px] text-ink/60">
                      An account already exists for {result.email || "this email"} — your purchase has been added to it. Log in to continue.
                    </p>
                    <Link
                      to={`/login?next=${encodeURIComponent(nextPath)}`}
                      data-testid="guest-welcome-login-btn"
                      className="mt-4 inline-flex items-center gap-2 bg-forest hover:bg-forest-pop text-white font-barlow font-black uppercase tracking-widest text-sm px-6 py-3.5 rounded-full transition-colors"
                    >
                      Log in <ArrowRight className="w-4 h-4" />
                    </Link>
                    <p className="mt-3 text-[11px] text-ink/45">
                      Forgot your password? <Link to="/forgot-password" className="text-forest underline">Reset it here</Link>.
                    </p>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
