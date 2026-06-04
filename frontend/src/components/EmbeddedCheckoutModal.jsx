import React, { useEffect, useMemo, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Lock, Loader2, Check, ShieldCheck, AlertCircle, X } from "lucide-react";
import { loadStripe } from "@stripe/stripe-js";
import { EmbeddedCheckoutProvider, EmbeddedCheckout } from "@stripe/react-stripe-js";
import api from "@/lib/api";

/**
 * EmbeddedCheckoutModal
 *
 * True in-page Stripe checkout — mounts Stripe's embedded checkout iframe inside
 * a branded ScoutMePlay modal so the user never leaves the page.
 *
 * Lifecycle:
 *   - `preparing` : we're fetching the publishable key + creating the embedded session.
 *   - `ready`     : EmbeddedCheckout is mounted; user is paying.
 *   - `success`   : payment confirmed; auto-close after a beat.
 *   - `error`     : configuration/network problem; show message + close button.
 *
 * Props:
 *   open       : boolean
 *   sessionInit: async () => Promise<{ client_secret, session_id }>   // creates the embedded session
 *   amount     : number  (display only)
 *   currency   : string  (default "USD")
 *   product    : string
 *   onSuccess  : ({session_id, kind}) => void   // called once Stripe confirms paid
 *   onClose    : () => void
 */
export default function EmbeddedCheckoutModal({
  open,
  sessionInit,
  amount = 1,
  currency = "USD",
  product = "ScoutMePlay – Football Video Analysis",
  onSuccess,
  onClose,
}) {
  const [state, setState] = useState("preparing"); // preparing | ready | success | error
  const [errorMessage, setErrorMessage] = useState(null);
  const [clientSecret, setClientSecret] = useState(null);
  const [stripePromise, setStripePromise] = useState(null);
  const [sessionId, setSessionId] = useState(null);
  const pollRef = useRef(null);
  const startedRef = useRef(false);

  // 1) on open: fetch config + create session
  useEffect(() => {
    if (!open) {
      startedRef.current = false;
      setClientSecret(null);
      setSessionId(null);
      setState("preparing");
      setErrorMessage(null);
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
      return;
    }
    if (startedRef.current) return;
    startedRef.current = true;

    (async () => {
      try {
        // load publishable key
        const { data: cfg } = await api.get("/config/stripe");
        if (!cfg.embedded_available || !cfg.publishable_key) {
          throw new Error("Embedded checkout isn't configured yet — Stripe keys missing.");
        }
        setStripePromise(loadStripe(cfg.publishable_key));

        // create embedded session
        const init = await sessionInit();
        setClientSecret(init.client_secret);
        setSessionId(init.session_id);
        setState("ready");
      } catch (err) {
        const msg =
          err?.response?.data?.detail || err?.message || "Couldn't open checkout. Try again.";
        setErrorMessage(typeof msg === "string" ? msg : "Couldn't open checkout.");
        setState("error");
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  // 2) onComplete from Stripe iframe — confirm payment by polling backend
  const handleStripeComplete = () => {
    if (!sessionId) return;
    setState("preparing"); // show "confirming…" briefly
    let attempts = 0;
    const tick = async () => {
      attempts += 1;
      try {
        const { data } = await api.get(`/payments/embedded/status/${sessionId}`);
        if (data.payment_status === "paid") {
          clearInterval(pollRef.current);
          pollRef.current = null;
          setState("success");
          onSuccess && onSuccess({ session_id: sessionId, kind: data.kind });
        } else if (attempts >= 12) {
          // ~24s
          clearInterval(pollRef.current);
          pollRef.current = null;
          setErrorMessage("Payment is still processing. Refresh in a moment.");
          setState("error");
        }
      } catch (err) {
        clearInterval(pollRef.current);
        pollRef.current = null;
        setErrorMessage(err?.response?.data?.detail || "Couldn't verify payment.");
        setState("error");
      }
    };
    tick();
    pollRef.current = setInterval(tick, 2000);
  };

  // cleanup poll on unmount
  useEffect(() => () => pollRef.current && clearInterval(pollRef.current), []);

  // auto-close on success
  useEffect(() => {
    if (open && state === "success" && onClose) {
      const t = setTimeout(onClose, 2200);
      return () => clearTimeout(t);
    }
  }, [open, state, onClose]);

  const checkoutOptions = useMemo(
    () => ({ clientSecret, onComplete: handleStripeComplete }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [clientSecret, sessionId],
  );

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          key="embedded-overlay"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.25 }}
          data-testid="embedded-checkout-modal"
          className="fixed inset-0 z-[100] flex items-center justify-center bg-ink/85 backdrop-blur-xl px-4 py-6 overflow-y-auto"
        >
          {/* Soft halos */}
          <div aria-hidden className="pointer-events-none absolute inset-0 overflow-hidden">
            <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[700px] h-[700px] bg-forest/15 rounded-full blur-3xl" />
            <div className="absolute top-0 right-0 w-[300px] h-[300px] bg-forest/10 rounded-full blur-3xl" />
          </div>

          <motion.div
            initial={{ scale: 0.94, y: 14, opacity: 0 }}
            animate={{ scale: 1, y: 0, opacity: 1 }}
            exit={{ scale: 0.96, y: 8, opacity: 0 }}
            transition={{ duration: 0.35, ease: [0.2, 0.8, 0.2, 1] }}
            className="relative w-full max-w-lg border-2 border-forest/40 bg-cream-card my-auto"
            style={{ boxShadow: "0 0 80px rgba(31,79,47,0.18)" }}
          >
            {/* Header */}
            <div className="flex items-center justify-between px-6 md:px-8 pt-6 md:pt-7 pb-4 border-b border-gray-border">
              <div className="flex items-center gap-2.5">
                <div className="w-9 h-9 bg-forest/8 border border-forest/40 flex items-center justify-center">
                  <ShieldCheck className="w-4 h-4 text-volt" />
                </div>
                <div>
                  <div className="text-[10px] uppercase tracking-[0.22em] font-bold text-volt">
                    Mentalkids · ScoutMePlay
                  </div>
                  <div className="font-barlow font-black uppercase text-ink text-sm leading-tight mt-0.5">
                    Secure checkout
                  </div>
                </div>
              </div>
              {onClose && (state === "ready" || state === "error" || state === "success") && (
                <button
                  onClick={onClose}
                  aria-label="Close"
                  data-testid="embedded-modal-close"
                  className="w-8 h-8 flex items-center justify-center text-ink/55 hover:text-volt transition-colors"
                >
                  <X className="w-4 h-4" />
                </button>
              )}
            </div>

            {/* Body */}
            <div className="px-2 md:px-3 py-2">
              {state === "preparing" && (
                <div className="text-center py-12 px-6">
                  <div className="relative w-16 h-16 mx-auto mb-5 flex items-center justify-center">
                    <motion.div
                      className="absolute inset-0 border-2 border-volt/30 rounded-full"
                      style={{ borderTopColor: "#ccff00" }}
                      animate={{ rotate: 360 }}
                      transition={{ duration: 1.4, ease: "linear", repeat: Infinity }}
                    />
                    <Lock className="relative w-6 h-6 text-volt" strokeWidth={1.8} />
                  </div>
                  <h2
                    data-testid="embedded-modal-headline"
                    className="font-barlow font-black uppercase tracking-tighter text-xl md:text-2xl text-ink"
                  >
                    Preparing your checkout
                  </h2>
                  <p className="mt-2 text-sm text-ink/70 inline-flex items-center gap-1.5">
                    <Loader2 className="w-3.5 h-3.5 animate-spin text-volt" />
                    Encrypting your session…
                  </p>
                  <div className="mt-7 mx-6 border-t border-gray-border pt-4 flex items-center justify-between text-left">
                    <div>
                      <div className="text-[10px] uppercase tracking-[0.22em] font-bold text-ink/50">
                        Product
                      </div>
                      <div className="font-barlow font-black uppercase text-ink text-xs mt-0.5">
                        {product}
                      </div>
                    </div>
                    <div className="text-right">
                      <div className="text-[10px] uppercase tracking-[0.22em] font-bold text-ink/50">
                        Amount
                      </div>
                      <div className="font-barlow font-black text-ink text-lg leading-none mt-0.5">
                        ${amount}
                        <span className="text-volt text-xs ml-1">{currency}</span>
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {state === "ready" && clientSecret && stripePromise && (
                <div
                  data-testid="embedded-checkout-iframe-wrapper"
                  className="bg-cream-card"
                  // Stripe's embedded checkout fills available width; we give it a comfortable height
                  style={{ minHeight: 520 }}
                >
                  <EmbeddedCheckoutProvider stripe={stripePromise} options={checkoutOptions}>
                    <EmbeddedCheckout />
                  </EmbeddedCheckoutProvider>
                </div>
              )}

              {state === "success" && (
                <div className="text-center py-14 px-6">
                  <motion.div
                    initial={{ scale: 0.4, opacity: 0 }}
                    animate={{ scale: 1, opacity: 1 }}
                    transition={{ type: "spring", stiffness: 320, damping: 14 }}
                    className="relative w-16 h-16 mx-auto mb-5 flex items-center justify-center"
                  >
                    <div className="absolute inset-0 border-2 border-volt rounded-full" />
                    <div className="absolute inset-0 bg-volt/20 rounded-full" />
                    <Check className="relative w-8 h-8 text-volt" strokeWidth={2.5} />
                  </motion.div>
                  <h2
                    data-testid="embedded-success-headline"
                    className="font-barlow font-black uppercase tracking-tighter text-2xl md:text-3xl text-ink"
                  >
                    Payment confirmed
                  </h2>
                  <p className="mt-2 text-sm text-ink/70">
                    Your premium report is unlocking now…
                  </p>
                </div>
              )}

              {state === "error" && (
                <div className="text-center py-12 px-6">
                  <div className="relative w-16 h-16 mx-auto mb-5 flex items-center justify-center">
                    <div className="absolute inset-0 border-2 border-orange-400/40 rounded-full" />
                    <AlertCircle className="relative w-8 h-8 text-orange-400" strokeWidth={1.6} />
                  </div>
                  <h2 className="font-barlow font-black uppercase tracking-tighter text-xl md:text-2xl text-ink">
                    Couldn't open checkout
                  </h2>
                  <p
                    data-testid="embedded-error-message"
                    className="mt-3 text-sm text-ink/70 max-w-sm mx-auto"
                  >
                    {errorMessage || "Please try again, or contact support."}
                  </p>
                  {onClose && (
                    <button
                      onClick={onClose}
                      data-testid="embedded-error-close"
                      className="mt-6 inline-flex items-center justify-center gap-2 bg-volt hover:bg-forest-pop text-white font-barlow font-black uppercase tracking-widest text-xs px-6 py-3 transition-colors"
                    >
                      Close
                    </button>
                  )}
                </div>
              )}
            </div>

            {/* Trust footer */}
            <div className="px-6 md:px-8 py-4 border-t border-gray-border flex items-center justify-center gap-2 text-[10px] uppercase tracking-[0.22em] font-bold text-ink/50">
              <ShieldCheck className="w-3 h-3 text-volt" />
              Secure 256-bit · PCI compliant · Stripe
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
