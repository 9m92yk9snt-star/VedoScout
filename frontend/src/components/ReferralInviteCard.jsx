// ReferralInviteCard — dashboard card: personal invite link, copy/share,
// active credit badge and the list of invited teammates.
import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import { Users2, Copy, Share2, Gift, Check } from "lucide-react";
import api from "@/lib/api";

export default function ReferralInviteCard() {
  const [data, setData] = useState(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    api.get("/referral/me").then(({ data: d }) => setData(d)).catch(() => {});
  }, []);

  if (!data?.enabled) return null;
  const pct = Math.round(data.percent);
  const link = `${window.location.origin}/?ref=${data.code}`;

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(link);
      setCopied(true);
      toast.success("Invite link copied!");
      setTimeout(() => setCopied(false), 2000);
    } catch {
      toast.error("Could not copy the link");
    }
  };

  const share = async () => {
    const text = `Get your football game analyzed on ScoutMePlay — sign up with my link and we both get ${pct}% off: ${link}`;
    if (navigator.share) {
      try { await navigator.share({ title: "ScoutMePlay", text, url: link }); } catch { /* cancelled */ }
    } else {
      copy();
    }
  };

  return (
    <section className="mt-10 bg-cream-card border border-ink/10 p-5 md:p-6" data-testid="referral-invite-card">
      <div className="flex flex-col md:flex-row md:items-center gap-4 justify-between">
        <div className="min-w-0">
          <div className="flex items-center gap-2 text-[10px] font-extrabold uppercase tracking-[0.16em] text-forest">
            <Users2 className="w-4 h-4" /> Invite a teammate
          </div>
          <h3 className="font-barlow font-black uppercase text-xl md:text-2xl text-ink mt-1 leading-tight">
            You both get {pct}% off
          </h3>
          <p className="text-sm text-ink/60 mt-1">
            Share your link — when a teammate signs up, you BOTH get {pct}% off your next report. Applied automatically at checkout.
          </p>
          {data.credit && (
            <span className="inline-flex items-center gap-1.5 mt-2 bg-forest/10 border border-forest/30 text-forest text-[11px] font-extrabold px-3 py-1 rounded-full" data-testid="referral-credit-badge">
              <Gift className="w-3.5 h-3.5" /> {Math.round(data.credit.percent)}% credit active — valid until {new Date(data.credit.expires_at).toLocaleDateString()}
            </span>
          )}
        </div>
        <div className="shrink-0 w-full md:w-auto">
          <div className="flex items-center gap-2 bg-white border border-ink/15 rounded-xl px-3 py-2.5">
            <span className="text-[12px] text-ink/70 font-mono truncate max-w-[220px]" data-testid="referral-link-text">{link}</span>
            <button type="button" onClick={copy} data-testid="referral-copy-btn" aria-label="Copy invite link"
              className="w-8 h-8 rounded-lg bg-ink text-white flex items-center justify-center hover:bg-forest transition-colors shrink-0">
              {copied ? <Check className="w-4 h-4" /> : <Copy className="w-4 h-4" />}
            </button>
            <button type="button" onClick={share} data-testid="referral-share-btn" aria-label="Share invite link"
              className="w-8 h-8 rounded-lg bg-forest text-white flex items-center justify-center hover:bg-forest-pop transition-colors shrink-0">
              <Share2 className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>
      {data.invited?.length > 0 && (
        <div className="mt-4 border-t border-ink/10 pt-3" data-testid="referral-invited-list">
          <div className="text-[10px] font-extrabold uppercase tracking-wider text-ink/45">Invited teammates ({data.invited.length})</div>
          <ul className="mt-1.5 space-y-1">
            {data.invited.map((i, idx) => (
              <li key={idx} className="text-[12.5px] text-ink/70 flex items-center gap-2">
                <Check className="w-3.5 h-3.5 text-forest" />
                <b>{i.name || i.email}</b> · {i.date ? new Date(i.date).toLocaleDateString() : ""}
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
