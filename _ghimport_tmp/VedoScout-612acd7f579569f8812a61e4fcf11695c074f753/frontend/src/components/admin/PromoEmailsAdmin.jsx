// PromoEmailsAdmin — every automated & promotion email in ONE place, with
// a clear name, when it is sent, and a "Send test" to any real inbox.
import React, { useState } from "react";
import { toast } from "sonner";
import { Mail, Send, Loader2 } from "lucide-react";
import api from "@/lib/api";
import { useAuth } from "@/lib/auth-context";

const EMAIL_TYPES = [
  { key: "welcome", name: "Welcome email", when: "Sent right after a new user signs up" },
  { key: "activation_24h", name: "Activation nudge — 24h", when: "24 hours after signup if no video was uploaded" },
  { key: "activation_72h", name: "Activation nudge — 72h (last)", when: "72 hours after signup if still no upload" },
  { key: "conv_waiting", name: "Your numbers are waiting — 24h", when: "24 hours after a free analysis without purchase" },
  { key: "conv_discount", name: "48h discount offer", when: "48 hours after a free analysis — automatic % discount" },
  { key: "conv_discovery", name: "Discovery nudge — 72h", when: "72 hours after a free analysis without purchase" },
  { key: "abandoned_checkout", name: "Abandoned checkout", when: "~1 hour after starting checkout without paying" },
  { key: "discount_campaign", name: "Manual campaign offer", when: "When you launch a Manual Campaign (Growth tab)" },
  { key: "report_ready", name: "Report ready", when: "When a premium report is finished" },
  { key: "purchase_confirmation", name: "Purchase receipt", when: "Right after a successful payment" },
  { key: "curve_reminder", name: "Progress curve reminder", when: "Weeks after a report — invites a progress update" },
];

export default function PromoEmailsAdmin() {
  const { user } = useAuth();
  const [to, setTo] = useState(user?.email || "");
  const [busyKey, setBusyKey] = useState(null);

  const sendTest = async (key) => {
    if (!to.includes("@")) {
      toast.error("Enter a valid test email address first");
      return;
    }
    setBusyKey(key);
    try {
      await api.post("/admin/emails/send-test", { template: key, to });
      toast.success(`Test sent to ${to} — check the inbox`);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not send the test email");
    } finally {
      setBusyKey(null);
    }
  };

  return (
    <div className="bg-white border border-[#E5DFCE] rounded-2xl p-5 md:p-6 mb-6" data-testid="promo-emails-admin">
      <h3 className="font-barlow font-black uppercase text-ink flex items-center gap-2">
        <Mail className="w-4 h-4 text-forest" /> Automated &amp; promotion emails
      </h3>
      <p className="text-xs text-ink/55 mt-1">
        Every email the platform can send — what it is, when it goes out, and a test send so you can see exactly how it looks in a real inbox.
      </p>
      <div className="mt-4 flex flex-col sm:flex-row sm:items-center gap-2">
        <label className="text-[11px] font-extrabold uppercase tracking-wider text-ink/60 shrink-0">Send tests to</label>
        <input
          type="email"
          value={to}
          onChange={(e) => setTo(e.target.value)}
          placeholder="your@email.com"
          data-testid="promo-test-email-input"
          className="w-full sm:max-w-xs border border-[#E5DFCE] rounded-xl px-3.5 py-2 text-sm focus:outline-none focus:border-forest"
        />
      </div>
      <div className="mt-4 divide-y divide-[#EFEADB] border border-[#EFEADB] rounded-xl overflow-hidden">
        {EMAIL_TYPES.map((t) => (
          <div key={t.key} className="flex items-center gap-3 px-4 py-3 bg-[#FBF9F3]" data-testid={`promo-email-row-${t.key}`}>
            <div className="min-w-0 flex-1">
              <div className="text-[13px] font-extrabold text-ink leading-tight">{t.name}</div>
              <div className="text-[11.5px] text-ink/55 leading-snug mt-0.5">{t.when}</div>
            </div>
            <button
              type="button"
              onClick={() => sendTest(t.key)}
              disabled={busyKey !== null}
              data-testid={`promo-email-test-${t.key}`}
              className="shrink-0 inline-flex items-center gap-1.5 bg-forest hover:bg-forest-pop text-white text-[11px] font-black uppercase tracking-wider px-3.5 py-2 rounded-lg transition-colors disabled:opacity-50"
            >
              {busyKey === t.key ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Send className="w-3.5 h-3.5" />}
              Send test
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
