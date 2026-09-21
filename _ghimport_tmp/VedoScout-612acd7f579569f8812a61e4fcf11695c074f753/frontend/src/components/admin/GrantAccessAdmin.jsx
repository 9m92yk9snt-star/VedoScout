/**
 * GrantAccessAdmin — Admin-only tool.
 * Lets the admin create (or upgrade) a user account with full paid access
 * WITHOUT going through Stripe. Useful for:
 *   - Seeding test accounts on a fresh production DB
 *   - Comping a real scout/agency who was verified offline
 *   - Handing out VIP access to influencers, press, or partners
 *
 * Backend: POST /api/admin/grant-access
 */
import React, { useState } from "react";
import { toast } from "sonner";
import { UserPlus, Shield, Copy, RefreshCw, Check } from "lucide-react";
import api from "@/lib/api";

const ACCESS_TYPES = [
  {
    id: "scout_club",
    label: "Scout — Club tier",
    tone: "text-blue-400",
    perks: "Lifetime · unlimited reveals · 5 seats · verified",
  },
  {
    id: "scout_agent",
    label: "Scout — Agent tier",
    tone: "text-blue-300",
    perks: "Lifetime · 20 reveals/mo · 1 seat · verified",
  },
  {
    id: "vip",
    label: "VIP Player",
    tone: "text-volt",
    perks: "VIP sub (30d) · 10 prepaid uploads · 5 progress-pass · discoverable",
  },
  {
    id: "premium",
    label: "Premium Player",
    tone: "text-lime-400",
    perks: "Premium sub (30d) · 5 prepaid uploads · 2 reports/mo included",
  },
  {
    id: "prepaid_5",
    label: "Free tier + 5 prepaid",
    tone: "text-ink/60",
    perks: "No subscription · 5 free full-report credits",
  },
];

// Simple secure-ish password generator — capital + lower + digit + symbol.
function genPassword() {
  const upper = "ABCDEFGHJKLMNPQRSTUVWXYZ";
  const lower = "abcdefghijkmnpqrstuvwxyz";
  const digit = "23456789";
  const sym   = "!@#$%&*";
  const pick = (s) => s[Math.floor(Math.random() * s.length)];
  const arr = [
    pick(upper), pick(upper), pick(lower), pick(lower),
    pick(lower), pick(digit), pick(digit), pick(sym),
  ];
  // Shuffle
  for (let i = arr.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [arr[i], arr[j]] = [arr[j], arr[i]];
  }
  return arr.join("");
}

export default function GrantAccessAdmin() {
  const [email, setEmail] = useState("");
  const [fullName, setFullName] = useState("");
  const [password, setPassword] = useState(genPassword());
  const [accessType, setAccessType] = useState("scout_club");
  const [busy, setBusy] = useState(false);
  const [lastGranted, setLastGranted] = useState(null);
  const [copiedField, setCopiedField] = useState(null);

  const copyToClipboard = async (val, field) => {
    try {
      await navigator.clipboard.writeText(val);
      setCopiedField(field);
      setTimeout(() => setCopiedField(null), 1500);
    } catch {
      toast.error("Could not copy");
    }
  };

  const submit = async (e) => {
    e?.preventDefault?.();
    if (!email || !fullName || !password) {
      toast.error("Fill in all fields");
      return;
    }
    setBusy(true);
    try {
      const { data } = await api.post("/admin/grant-access", {
        email: email.trim().toLowerCase(),
        full_name: fullName.trim(),
        password,
        access_type: accessType,
      });
      setLastGranted({
        email: data.email,
        password: data.password,
        role: data.role,
        access_type: data.access_type,
        at: new Date().toISOString(),
      });
      toast.success(`Access granted to ${data.email}`);
      // Clear form for the next grant
      setEmail("");
      setFullName("");
      setPassword(genPassword());
    } catch (err) {
      const msg = err?.response?.data?.detail || err.message || "Failed to grant access";
      toast.error(String(msg));
    } finally {
      setBusy(false);
    }
  };

  const selected = ACCESS_TYPES.find((a) => a.id === accessType) || ACCESS_TYPES[0];

  return (
    <div className="space-y-6" data-testid="grant-access-admin">
      {/* Header */}
      <div className="flex items-start gap-3">
        <div className="w-10 h-10 rounded-full bg-volt/10 border border-volt/30 flex items-center justify-center flex-shrink-0">
          <Shield className="w-5 h-5 text-volt" strokeWidth={2.4} />
        </div>
        <div>
          <h2 className="font-barlow font-black uppercase text-2xl md:text-3xl tracking-tight text-ink leading-tight">
            Grant Full Access
          </h2>
          <p className="mt-1 text-sm text-ink/60 max-w-2xl leading-relaxed">
            Create or upgrade a user with paid features — Scout tier, VIP or Premium — without going through Stripe.
            Useful for comping a verified scout, seeding test accounts, or gifting VIP to influencers / press.
          </p>
        </div>
      </div>

      {/* Form card */}
      <form
        onSubmit={submit}
        className="bg-white border border-ink/10 shadow-sm p-6 md:p-8 space-y-5"
      >
        {/* Access tier selector */}
        <div>
          <label className="text-[11px] uppercase tracking-[0.22em] font-black text-ink/70 mb-2 block">
            Access tier
          </label>
          <div className="grid gap-2">
            {ACCESS_TYPES.map((t) => (
              <label
                key={t.id}
                data-testid={`access-tier-${t.id}`}
                className={`flex items-center gap-3 p-3 border cursor-pointer transition-all ${
                  accessType === t.id
                    ? "border-forest bg-forest/5"
                    : "border-ink/15 hover:border-ink/30"
                }`}
              >
                <input
                  type="radio"
                  name="access_type"
                  value={t.id}
                  checked={accessType === t.id}
                  onChange={(e) => setAccessType(e.target.value)}
                  className="accent-forest w-4 h-4"
                />
                <div className="flex-1">
                  <div className={`font-black uppercase text-sm tracking-tight ${t.tone}`}>
                    {t.label}
                  </div>
                  <div className="text-xs text-ink/55 leading-tight">{t.perks}</div>
                </div>
              </label>
            ))}
          </div>
        </div>

        {/* Email + Name + Password inputs */}
        <div className="grid md:grid-cols-2 gap-4">
          <div>
            <label className="text-[11px] uppercase tracking-[0.22em] font-black text-ink/70 mb-1.5 block">
              Email
            </label>
            <input
              data-testid="grant-form-email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="john.smith@examplefc.com"
              className="w-full px-3 py-2.5 border border-ink/20 focus:border-forest outline-none text-sm"
              required
            />
          </div>
          <div>
            <label className="text-[11px] uppercase tracking-[0.22em] font-black text-ink/70 mb-1.5 block">
              Full name
            </label>
            <input
              data-testid="grant-form-name"
              type="text"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              placeholder="John Smith"
              className="w-full px-3 py-2.5 border border-ink/20 focus:border-forest outline-none text-sm"
              required
            />
          </div>
        </div>

        <div>
          <label className="text-[11px] uppercase tracking-[0.22em] font-black text-ink/70 mb-1.5 block">
            Password
          </label>
          <div className="flex gap-2">
            <input
              data-testid="grant-form-password"
              type="text"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="flex-1 px-3 py-2.5 border border-ink/20 focus:border-forest outline-none text-sm font-mono"
              required
            />
            <button
              type="button"
              onClick={() => setPassword(genPassword())}
              data-testid="grant-form-regen-pw"
              className="px-3 py-2 border border-ink/20 hover:border-forest hover:bg-forest/5 text-xs uppercase tracking-widest font-bold flex items-center gap-1.5"
              title="Regenerate random password"
            >
              <RefreshCw className="w-3.5 h-3.5" /> New
            </button>
          </div>
          <p className="mt-1.5 text-xs text-ink/50">
            User will need this password to log in. Copy it before submitting — you can&apos;t retrieve it later.
          </p>
        </div>

        {/* Submit */}
        <button
          type="submit"
          disabled={busy}
          data-testid="grant-form-submit"
          className="w-full md:w-auto px-6 py-3 bg-forest text-white font-black uppercase text-xs tracking-[0.22em] hover:bg-forest/90 disabled:opacity-50 flex items-center justify-center gap-2 transition-colors"
        >
          <UserPlus className="w-4 h-4" />
          {busy ? "Granting…" : `Grant ${selected.label}`}
        </button>
      </form>

      {/* Last granted receipt */}
      {lastGranted && (
        <div
          data-testid="grant-last-receipt"
          className="bg-gradient-to-br from-volt/10 to-transparent border border-volt/30 p-5"
        >
          <div className="flex items-center gap-2 mb-3">
            <Check className="w-4 h-4 text-forest" strokeWidth={2.8} />
            <span className="font-black uppercase text-xs tracking-[0.22em] text-forest">
              Access granted · {new Date(lastGranted.at).toLocaleTimeString()}
            </span>
          </div>
          <div className="space-y-2 font-mono text-sm">
            {[
              ["email", lastGranted.email],
              ["password", lastGranted.password],
              ["role", lastGranted.role],
              ["access_type", lastGranted.access_type],
            ].map(([k, v]) => (
              <div key={k} className="flex items-center gap-2">
                <span className="text-ink/50 text-xs uppercase tracking-widest font-bold min-w-[100px]">
                  {k}:
                </span>
                <span className="text-ink flex-1">{v}</span>
                <button
                  type="button"
                  onClick={() => copyToClipboard(v, k)}
                  data-testid={`grant-copy-${k}`}
                  className="text-ink/50 hover:text-forest text-xs flex items-center gap-1"
                >
                  {copiedField === k ? (
                    <><Check className="w-3 h-3" /> copied</>
                  ) : (
                    <><Copy className="w-3 h-3" /> copy</>
                  )}
                </button>
              </div>
            ))}
          </div>
          <button
            type="button"
            onClick={() => {
              const block = `Email: ${lastGranted.email}\nPassword: ${lastGranted.password}\nTier: ${lastGranted.access_type}`;
              copyToClipboard(block, "block");
            }}
            data-testid="grant-copy-all"
            className="mt-4 text-xs uppercase tracking-widest font-black text-forest border border-forest/30 hover:bg-forest/5 px-3 py-1.5 flex items-center gap-1.5"
          >
            <Copy className="w-3 h-3" />
            {copiedField === "block" ? "Copied all!" : "Copy all credentials"}
          </button>
        </div>
      )}
    </div>
  );
}
