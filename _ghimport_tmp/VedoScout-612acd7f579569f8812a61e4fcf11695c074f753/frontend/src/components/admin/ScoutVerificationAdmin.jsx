import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import {
  ShieldCheck, Shield, Ban, RotateCcw, ExternalLink, Loader2, Mail,
  Phone, Globe, Linkedin, MapPin, Users, DollarSign,
} from "lucide-react";
import api from "@/lib/api";

export default function ScoutVerificationAdmin() {
  const [scouts, setScouts] = useState(null);
  const [busy, setBusy] = useState(null);

  const load = () =>
    api.get("/admin/scouts").then(({ data }) => setScouts(data.scouts || []));

  useEffect(() => { load(); }, []);

  const toggleVerified = async (u) => {
    setBusy(u.user_id + ":verify");
    try {
      await api.put(`/admin/scouts/${u.user_id}/verify`, { verified: !u.verified });
      toast.success(u.verified ? "Verified badge removed." : "Verified badge granted.");
      await load();
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Could not update");
    } finally {
      setBusy(null);
    }
  };

  const revoke = async (u) => {
    const reason = window.prompt(`Revoke access for ${u.full_name || u.email}? Reason (shown internally only):`);
    if (reason === null) return;
    setBusy(u.user_id + ":revoke");
    try {
      await api.put(`/admin/scouts/${u.user_id}/revoke`, { reason });
      toast.success("Access revoked.");
      await load();
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Could not revoke");
    } finally {
      setBusy(null);
    }
  };

  const restore = async (u) => {
    setBusy(u.user_id + ":restore");
    try {
      await api.put(`/admin/scouts/${u.user_id}/restore`);
      toast.success("Access restored.");
      await load();
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Could not restore");
    } finally {
      setBusy(null);
    }
  };

  if (scouts === null) {
    return (
      <div className="flex items-center justify-center py-16">
        <Loader2 className="w-6 h-6 text-forest animate-spin" />
      </div>
    );
  }

  const totalActive = scouts.filter((s) => s.status === "active").length;
  const totalVerified = scouts.filter((s) => s.verified).length;
  const totalRevoked = scouts.filter((s) => s.status === "revoked").length;
  const revenue = scouts
    .filter((s) => s.status !== "revoked")
    .reduce((sum, s) => sum + (s.tier === "club" ? 899 : 399), 0);

  return (
    <div className="space-y-6" data-testid="admin-scout-verification">
      <header>
        <h2 className="font-barlow font-black uppercase tracking-tight text-2xl">
          Scout & Club Verification
        </h2>
        <p className="text-sm text-ink/60 mt-1">
          Manually review paying scouts and clubs. Grant the green Verified badge to boost trust.
          Revoke access for abuse — refunds handled outside Stripe.
        </p>
      </header>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatTile icon={Users} label="Total accounts" value={scouts.length} />
        <StatTile icon={ShieldCheck} label="Active" value={totalActive} accent="text-forest-pop" />
        <StatTile icon={Shield} label="Verified" value={totalVerified} accent="text-volt-dark" />
        <StatTile icon={DollarSign} label="Lifetime revenue" value={`$${revenue.toLocaleString()}`} />
      </div>

      {scouts.length === 0 ? (
        <div className="border border-ink/10 bg-cream-card p-10 text-center">
          <Users className="w-10 h-10 text-ink/20 mx-auto mb-3" />
          <p className="text-ink/60 text-sm">No paid scouts or clubs yet.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {scouts.map((s) => (
            <ScoutRow
              key={s.user_id}
              scout={s}
              busy={busy}
              onToggleVerified={() => toggleVerified(s)}
              onRevoke={() => revoke(s)}
              onRestore={() => restore(s)}
            />
          ))}
        </div>
      )}
      <p className="text-xs text-ink/50 mt-2">
        Revoked count: {totalRevoked}. Payments are lifetime one-time — no automatic renewals.
      </p>
    </div>
  );
}

function StatTile({ icon: Icon, label, value, accent = "text-ink" }) {
  return (
    <div className="border border-ink/10 bg-cream-card p-4">
      <div className="flex items-center gap-2 text-[10px] uppercase tracking-[0.16em] font-black text-forest">
        <Icon className="w-3.5 h-3.5" /> {label}
      </div>
      <div className={`mt-1 font-barlow font-black text-2xl ${accent}`}>{value}</div>
    </div>
  );
}

function ScoutRow({ scout, busy, onToggleVerified, onRevoke, onRestore }) {
  const v = scout.verification || {};
  const isRevoked = scout.status === "revoked";
  return (
    <div className={`border p-4 md:p-5 ${
      isRevoked ? "border-red-300 bg-red-50/40 opacity-80"
                : scout.verified ? "border-forest/40 bg-forest/5"
                : "border-ink/10 bg-cream-card"
    }`}>
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <h3 className="font-barlow font-black uppercase text-lg tracking-tight">
              {scout.full_name || scout.email}
            </h3>
            <span className={`text-[10px] uppercase tracking-widest font-black px-2 py-0.5 border ${
              scout.tier === "club" ? "border-volt-dark text-volt-dark" : "border-forest text-forest"
            }`}>
              {scout.tier}
            </span>
            {scout.verified && (
              <span className="inline-flex items-center gap-1 text-[10px] uppercase tracking-widest font-black text-forest-pop border border-forest-pop/40 bg-forest-pop/10 px-2 py-0.5">
                <ShieldCheck className="w-3 h-3" /> Verified
              </span>
            )}
            {isRevoked && (
              <span className="inline-flex items-center gap-1 text-[10px] uppercase tracking-widest font-black text-red-700 border border-red-300 bg-red-100 px-2 py-0.5">
                <Ban className="w-3 h-3" /> Revoked
              </span>
            )}
          </div>
          <div className="text-xs text-ink/60 mt-1 flex items-center gap-1.5">
            <Mail className="w-3 h-3" /> {scout.email}
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={onToggleVerified}
            disabled={busy === scout.user_id + ":verify"}
            data-testid={`verify-toggle-${scout.user_id}`}
            className={`inline-flex items-center gap-1.5 text-[11px] uppercase tracking-widest font-black px-3 py-2 transition-colors ${
              scout.verified
                ? "bg-ink/10 hover:bg-ink/20 text-ink"
                : "bg-forest hover:bg-forest-pop text-white"
            }`}
          >
            {busy === scout.user_id + ":verify"
              ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
              : scout.verified
                ? <><Shield className="w-3.5 h-3.5" /> Unverify</>
                : <><ShieldCheck className="w-3.5 h-3.5" /> Grant verified</>}
          </button>
          {isRevoked ? (
            <button
              type="button" onClick={onRestore}
              disabled={busy === scout.user_id + ":restore"}
              className="inline-flex items-center gap-1.5 text-[11px] uppercase tracking-widest font-black bg-ink text-white px-3 py-2 hover:bg-forest transition-colors"
            >
              <RotateCcw className="w-3.5 h-3.5" /> Restore
            </button>
          ) : (
            <button
              type="button" onClick={onRevoke}
              disabled={busy === scout.user_id + ":revoke"}
              className="inline-flex items-center gap-1.5 text-[11px] uppercase tracking-widest font-black text-red-700 hover:bg-red-100 border border-red-300 px-3 py-2 transition-colors"
            >
              <Ban className="w-3.5 h-3.5" /> Revoke
            </button>
          )}
        </div>
      </div>

      {isRevoked && scout.revoked_reason && (
        <div className="mt-3 text-xs text-red-700 border-l-2 border-red-400 pl-2.5">
          <strong>Revoke reason:</strong> {scout.revoked_reason}
        </div>
      )}

      {/* Verification info */}
      <div className="mt-4 grid md:grid-cols-2 gap-x-6 gap-y-1.5 text-sm">
        <InfoLine icon={Users} label="Organization" value={v.organization_name} />
        <InfoLine label="Type" value={v.organization_type} />
        <InfoLine label="Role" value={v.role_title} />
        <InfoLine icon={MapPin} label="Country" value={v.country} />
        <InfoLine icon={Globe} label="Website" value={v.website} isLink />
        <InfoLine icon={Linkedin} label="LinkedIn" value={v.linkedin_url} isLink />
        <InfoLine icon={Phone} label="Phone" value={v.phone} />
        {v.notes && <InfoLine label="Notes" value={v.notes} full />}
      </div>
    </div>
  );
}

function InfoLine({ icon: Icon, label, value, isLink, full }) {
  if (!value) return (
    <div className={full ? "md:col-span-2" : ""}>
      <span className="text-[10px] uppercase tracking-widest font-black text-ink/40 mr-2">{label}</span>
      <span className="text-ink/30 text-sm">—</span>
    </div>
  );
  return (
    <div className={`flex items-start gap-1.5 ${full ? "md:col-span-2" : ""}`}>
      {Icon && <Icon className="w-3.5 h-3.5 text-ink/40 mt-0.5 shrink-0" />}
      <div>
        <span className="text-[10px] uppercase tracking-widest font-black text-forest mr-1.5">{label}:</span>
        {isLink ? (
          <a href={value} target="_blank" rel="noreferrer" className="text-forest hover:underline break-all">
            {value.replace(/^https?:\/\//, "").replace(/\/$/, "")}
            <ExternalLink className="inline w-3 h-3 ml-1 -mt-0.5" />
          </a>
        ) : (
          <span className="text-ink">{value}</span>
        )}
      </div>
    </div>
  );
}
