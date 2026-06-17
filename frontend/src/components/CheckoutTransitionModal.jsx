import React, { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Lock, Loader2, Check, ShieldCheck, AlertCircle, X } from "lucide-react";

/**
 * Premium full-screen transition modal that wraps a Stripe redirect so the
 * checkout never feels like "a new page popped up". Three lifecycle states:
 *  - "preparing"  : creating the session
 *  - "redirecting": session URL acquired, about to navigate
 *  - "success"    : post-checkout celebration (then auto-closes)
 *  - "error"      : recoverable error message
 */
const STAGES = ["Preparing secure checkout", "Connecting to Stripe", "Encrypting your session"];

export default function CheckoutTransitionModal({
  open,
  state = "preparing",
  amount = 1,
  currency = "USD",
  product = "ScoutMePlay – Football Video Analysis",
  errorMessage,
  onClose,
}) {
  const [stage, setStage] = useState(0);

  useEffect(() => {
    if (!open || state !== "preparing") return;
    let i = 0;
    const t = setInterval(() => {
      i = (i + 1) % STAGES.length;
      setStage(i);
    }, 900);
    return () => clearInterval(t);
  }, [open, state]);

  // Auto-close success modal after 2.5s
  useEffect(() => {
    if (open && state === "success" && onClose) {
      const t = setTimeout(onClose, 2500);
      return () => clearTimeout(t);
    }
  }, [open, state, onClose]);

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          key="checkout-overlay"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.25 }}
          data-testid="checkout-transition-modal"
          className="fixed inset-0 z-[100] flex items-center justify-center bg-cream-card backdrop-blur-xl px-6"
          onClick={state === "error" && onClose ? onClose : undefined}
        >
          {/* Volt halo */}
          <div aria-hidden className="pointer-events-none absolute inset-0 overflow-hidden">
            <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[700px] h-[700px] bg-volt/12 rounded-full blur-3xl" />
            <div className="absolute top-0 right-0 w-[300px] h-[300px] bg-volt/6 rounded-full blur-3xl" />
          </div>

          <motion.div
            initial={{ scale: 0.94, y: 14, opacity: 0 }}
            animate={{ scale: 1, y: 0, opacity: 1 }}
            exit={{ scale: 0.96, y: 8, opacity: 0 }}
            transition={{ duration: 0.35, ease: [0.2, 0.8, 0.2, 1] }}
            onClick={(e) => e.stopPropagation()}
            className="relative w-full max-w-md border-2 border-volt/30 bg-surface/90 backdrop-blur-2xl p-8 md:p-10 text-center"
            style={{ boxShadow: "0 0 80px rgba(204,255,0,0.18)" }}
          >
            {/* close button — only when error / success allows manual close */}
            {state === "error" && onClose && (
              <button
                onClick={onClose}
                aria-label="Close"
                data-testid="checkout-modal-close"
                className="absolute top-3 right-3 w-8 h-8 flex items-center justify-center text-ink/55 hover:text-ink"
              >
                <X className="w-4 h-4" />
              </button>
            )}

            {/* PRODUCT LABEL */}
            <div className="inline-flex items-center gap-2 text-[10px] uppercase tracking-[0.22em] font-bold text-volt border border-volt/40 bg-volt/10 px-3 py-1.5 mb-6">
              <ShieldCheck className="w-3 h-3" />
              ScoutMePlay
            </div>

            {/* ICON BLOCK */}
            <div className="relative w-20 h-20 mx-auto mb-6 flex items-center justify-center">
              <div className="absolute inset-0 bg-volt/15 rounded-full blur-xl" />
              {state === "preparing" || state === "redirecting" ? (
                <div className="relative w-20 h-20 flex items-center justify-center">
                  <motion.div
                    className="absolute inset-0 border-2 border-volt/30 rounded-full"
                    style={{ borderTopColor: "#ccff00" }}
                    animate={{ rotate: 360 }}
                    transition={{ duration: 1.4, ease: "linear", repeat: Infinity }}
                  />
                  <Lock className="relative w-7 h-7 text-volt" strokeWidth={1.8} />
                </div>
              ) : state === "success" ? (
                <motion.div
                  initial={{ scale: 0.4, opacity: 0 }}
                  animate={{ scale: 1, opacity: 1 }}
                  transition={{ type: "spring", stiffness: 320, damping: 14 }}
                  className="relative w-20 h-20 flex items-center justify-center"
                >
                  <div className="absolute inset-0 border-2 border-volt rounded-full" />
                  <div className="absolute inset-0 bg-volt/20 rounded-full" />
                  <Check className="relative w-9 h-9 text-volt" strokeWidth={2.5} />
                </motion.div>
              ) : (
                <div className="relative w-20 h-20 flex items-center justify-center">
                  <div className="absolute inset-0 border-2 border-orange-400/40 rounded-full" />
                  <AlertCircle className="relative w-9 h-9 text-orange-400" strokeWidth={1.6} />
                </div>
              )}
            </div>

            {/* HEADLINE */}
            <h2
              data-testid="checkout-modal-headline"
              className="font-barlow font-black uppercase tracking-tighter text-2xl md:text-3xl text-ink leading-tight"
            >
              {state === "preparing" && "Preparing your checkout"}
              {state === "redirecting" && "Connecting to Stripe…"}
              {state === "success" && "Payment confirmed"}
              {state === "error" && "Couldn't open checkout"}
            </h2>

            {/* DESCRIPTION */}
            <p className="mt-3 text-sm text-ink/70 leading-relaxed">
              {state === "preparing" && (
                <span className="inline-flex items-center gap-1.5">
                  <Loader2 className="w-3.5 h-3.5 animate-spin text-volt" />
                  {STAGES[stage]}
                </span>
              )}
              {state === "redirecting" && "Taking you to the secure payment page…"}
              {state === "success" && "Upload credit added to your account. Returning to ScoutMePlay…"}
              {state === "error" && (errorMessage || "Please try again, or contact support.")}
            </p>

            {/* PRICE STRIP — visible only during preparing/redirecting to anchor expectations */}
            {(state === "preparing" || state === "redirecting") && (
              <div className="mt-7 border-t border-gray-border pt-5 flex items-center justify-between text-left">
                <div>
                  <div className="text-[10px] uppercase tracking-[0.22em] font-bold text-ink/50">Product</div>
                  <div className="font-barlow font-black uppercase text-ink text-sm mt-0.5 leading-tight">{product}</div>
                </div>
                <div className="text-right">
                  <div className="text-[10px] uppercase tracking-[0.22em] font-bold text-ink/50">Amount</div>
                  <div className="font-barlow font-black text-ink text-xl mt-0.5 leading-none">
                    {currency === "USD" ? "$" : ""}{amount}<span className="text-volt text-sm ml-1">{currency}</span>
                  </div>
                </div>
              </div>
            )}

            {/* PROGRESS BAR — preparing only */}
            {state === "preparing" && (
              <div className="mt-6 h-1 bg-cream-soft/40 overflow-hidden">
                <motion.div
                  className="h-full bg-volt"
                  initial={{ width: "5%" }}
                  animate={{ width: ["10%", "55%", "85%", "70%", "90%"] }}
                  transition={{ duration: 4, repeat: Infinity, ease: "easeInOut" }}
                />
              </div>
            )}

            {/* Trust line */}
            <div className="mt-6 flex items-center justify-center gap-2 text-[10px] uppercase tracking-[0.22em] font-bold text-ink/50">
              <ShieldCheck className="w-3 h-3 text-volt" />
              Secure 256-bit · PCI compliant · Stripe
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
