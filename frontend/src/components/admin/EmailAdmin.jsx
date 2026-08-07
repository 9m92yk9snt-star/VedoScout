/**
 * EmailAdmin.jsx — Admin bulk-email CMS + welcome/purchase email status.
 *
 * Features:
 *  - Shows SMTP enabled/disabled state at the top
 *  - Live recipient counts per segment (all / free / premium / vip / admins / progress_pass)
 *  - Compose form: subject + HTML body + preheader + segment select
 *  - Send test email to a single address (preview mode) before broadcasting
 *  - Send to segment triggers a background job — job list below polls for status
 *  - Job history table with sent/failed counts + status pill
 *
 * All backend calls hit /api/admin/bulk-email/*.
 */
import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import {
  Mail, Send, Users, Loader2, AlertCircle, CheckCircle2, XCircle,
  RefreshCw, Sparkles, Zap,
} from "lucide-react";

import api from "@/lib/api";

const SEGMENT_LABELS = {
  all: "All users",
  free: "Free tier only",
  premium: "Premium subscribers",
  vip: "VIP subscribers",
  progress_pass: "Progress Pass holders",
  admins: "Admins + Scouts",
};

function StatusPill({ status }) {
  const cfg = {
    queued:   { c: "bg-ink/10 text-ink/70 border-ink/20", i: <Loader2 className="w-3 h-3 animate-spin" /> },
    sending:  { c: "bg-forest/10 text-forest border-forest/40", i: <Loader2 className="w-3 h-3 animate-spin" /> },
    complete: { c: "bg-forest-pop/10 text-forest-pop border-forest-pop/40", i: <CheckCircle2 className="w-3 h-3" /> },
    error:    { c: "bg-red-500/10 text-red-500 border-red-500/40", i: <XCircle className="w-3 h-3" /> },
  }[status] || { c: "bg-ink/10 text-ink/60 border-ink/20", i: null };
  return (
    <span className={`inline-flex items-center gap-1 text-[9px] uppercase tracking-widest font-black border px-1.5 py-0.5 ${cfg.c}`}>
      {cfg.i} {status || "unknown"}
    </span>
  );
}

/* ── Sent log — every outgoing email + open tracking ───────────────────── */
function EmailSentLog() {
  const [data, setData] = useState(null);
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);

  const load = (query = q) => {
    api.get(`/admin/email-log?limit=100${query ? `&q=${encodeURIComponent(query)}` : ""}`)
      .then(({ data }) => setData(data))
      .catch(() => setData({ items: [], total: 0, opened: 0 }));
  };
  useEffect(() => { if (open) load(); }, [open]); // eslint-disable-line

  const fmt = (iso) => {
    try { const d = new Date(iso); return `${d.toLocaleDateString("en-GB", { day: "2-digit", month: "short" })} ${d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" })}`; }
    catch { return String(iso).slice(0, 16); }
  };

  return (
    <div className="border border-gray-border bg-white p-4" data-testid="email-sent-log">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        data-testid="email-sent-log-toggle"
        className="w-full flex items-center justify-between gap-3"
      >
        <div className="flex items-center gap-2">
          <Mail className="w-4 h-4 text-forest" />
          <span className="text-[11px] uppercase tracking-[0.2em] font-black text-ink/70">Sent log — who received &amp; opened what</span>
        </div>
        <span className="text-[11px] font-bold text-ink/45">{open ? "Hide" : "Show"}</span>
      </button>
      {open && (
        <div className="mt-4">
          <div className="flex items-center gap-2 mb-3 flex-wrap">
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && load()}
              placeholder="Search by recipient email…"
              data-testid="email-log-search"
              className="flex-1 min-w-[200px] border border-gray-border px-3 py-2 text-[13px] focus:outline-none focus:border-forest"
            />
            <button type="button" onClick={() => load()} data-testid="email-log-search-btn"
              className="px-4 py-2 text-[11px] font-black uppercase tracking-wider bg-ink text-white hover:bg-forest transition-colors">
              Search
            </button>
            {data && (
              <span className="text-[11.5px] text-ink/55" data-testid="email-log-stats">
                {data.total} sent · {data.opened} opened{data.total ? ` (${Math.round((data.opened / data.total) * 100)}%)` : ""}
              </span>
            )}
          </div>
          <p className="text-[10.5px] text-ink/40 mb-2">
            "Opened" uses an invisible tracking pixel — never 100% exact (Apple Mail &amp; some Gmail setups block or pre-load images), but a reliable engagement signal.
          </p>
          <div className="overflow-x-auto">
            <table className="w-full text-[12px]">
              <thead>
                <tr className="text-ink/45 text-left border-b border-gray-border">
                  <th className="py-2 pr-2">Sent</th><th className="pr-2">To</th><th className="pr-2">Category</th><th className="pr-2">Subject</th><th className="pr-2">Status</th><th>Opened</th>
                </tr>
              </thead>
              <tbody>
                {(data?.items || []).map((m) => (
                  <tr key={m.id} className="border-b border-gray-border/60 text-ink/80" data-testid={`email-log-row-${m.id}`}>
                    <td className="py-2 pr-2 whitespace-nowrap text-ink/55">{fmt(m.ts)}</td>
                    <td className="pr-2">{m.to}</td>
                    <td className="pr-2"><span className="px-1.5 py-0.5 bg-forest/8 text-forest font-bold text-[10.5px] uppercase">{m.category}</span></td>
                    <td className="pr-2 max-w-[240px] truncate">{m.subject}</td>
                    <td className="pr-2">
                      {m.status === "sent"
                        ? <span className="text-forest font-bold">sent</span>
                        : <span className="text-red-500 font-bold">failed</span>}
                    </td>
                    <td>
                      {m.opened_at
                        ? <span className="text-forest font-black">✓ {fmt(m.opened_at)}</span>
                        : <span className="text-ink/35">—</span>}
                    </td>
                  </tr>
                ))}
                {data && !data.items.length && (
                  <tr><td colSpan={6} className="py-4 text-ink/45">No emails logged yet — the log starts with the next email sent.</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

export default function EmailAdmin() {
  const [smtpEnabled, setSmtpEnabled] = useState(true);
  const [smtpNote, setSmtpNote] = useState(null);
  const [counts, setCounts] = useState({});
  const [loading, setLoading] = useState(true);
  const [form, setForm] = useState({
    subject: "",
    body_html: "",
    preheader: "",
    segment: "all",
    test_email: "",
  });
  const [sending, setSending] = useState(false);
  const [testing, setTesting] = useState(false);
  const [jobs, setJobs] = useState([]);
  const [jobsLoading, setJobsLoading] = useState(false);

  const loadAll = async () => {
    setLoading(true);
    try {
      const [seg, jl] = await Promise.all([
        api.get("/admin/bulk-email/segments"),
        api.get("/admin/bulk-email/jobs"),
      ]);
      setCounts(seg.data?.counts || {});
      setSmtpEnabled(!!seg.data?.smtp_enabled);
      setSmtpNote(seg.data?.note || null);
      setJobs(jl.data?.items || []);
    } catch {
      toast.error("Could not load email admin data");
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => { loadAll(); }, []);

  // Poll job list every 6s if any job is still sending
  useEffect(() => {
    const anyRunning = jobs.some((j) => j.status === "queued" || j.status === "sending");
    if (!anyRunning) return undefined;
    const id = setInterval(async () => {
      try {
        const { data } = await api.get("/admin/bulk-email/jobs");
        setJobs(data?.items || []);
      } catch { /* silent */ }
    }, 6000);
    return () => clearInterval(id);
  }, [jobs]);

  const canSend = form.subject.trim().length > 0 && form.body_html.trim().length > 0;
  const recipientCount = counts[form.segment] ?? 0;

  const sendTest = async () => {
    if (!form.test_email.trim()) {
      toast.error("Enter a test email address");
      return;
    }
    if (!canSend) {
      toast.error("Fill in subject and body first");
      return;
    }
    setTesting(true);
    try {
      const { data } = await api.post("/admin/bulk-email/send", {
        subject: form.subject.trim(),
        body_html: form.body_html.trim(),
        preheader: form.preheader.trim() || undefined,
        segment: form.segment,
        test_email: form.test_email.trim(),
      });
      if (data.sent === 1) {
        toast.success(`Test email sent to ${data.recipient}`);
      } else {
        const msg = data.smtp_enabled === false
          ? "SMTP not configured — test send skipped (add credentials to backend/.env)"
          : `Test failed for ${data.recipient}`;
        toast.error(msg, { duration: 8000 });
      }
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Test send failed");
    } finally {
      setTesting(false);
    }
  };

  const broadcast = async () => {
    if (!canSend) {
      toast.error("Fill in subject and body first");
      return;
    }
    const label = SEGMENT_LABELS[form.segment] || form.segment;
    if (!window.confirm(
      `Send this email to ${recipientCount} recipients (${label})?\n\n` +
      `Subject: ${form.subject}\n\n` +
      `This cannot be undone.`
    )) return;
    setSending(true);
    try {
      const { data } = await api.post("/admin/bulk-email/send", {
        subject: form.subject.trim(),
        body_html: form.body_html.trim(),
        preheader: form.preheader.trim() || undefined,
        segment: form.segment,
      });
      toast.success(`Queued ${data.queued} emails · job ${data.job_id?.slice(0, 8)}`);
      // refresh jobs list so the new one shows
      loadAll();
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Send failed");
    } finally {
      setSending(false);
    }
  };

  const StatusPillLocal = StatusPill; // ref alias — no-op, keeps existing usages working
  void StatusPillLocal;

  if (loading) {
    return (
      <div className="py-12 text-center" data-testid="email-admin-loading">
        <Loader2 className="w-8 h-8 text-forest mx-auto animate-spin" />
        <p className="mt-3 text-sm text-ink/60">Loading email admin...</p>
      </div>
    );
  }

  return (
    <div className="space-y-6" data-testid="email-admin">
      {/* Header */}
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <Mail className="w-4 h-4 text-volt" />
            <span className="text-volt text-[10px] uppercase tracking-[0.22em] font-bold">CMS · Email</span>
          </div>
          <h2 className="font-barlow font-black uppercase text-2xl md:text-3xl text-ink leading-tight">
            Bulk email &amp; transactional
          </h2>
          <p className="mt-2 text-sm text-ink/65 max-w-2xl leading-relaxed">
            Compose a broadcast and send it to a segment of users. Welcome emails and purchase confirmations
            are dispatched <strong>automatically</strong> from{" "}
            <code className="text-forest font-bold bg-forest/8 px-1.5 py-0.5">scoutmeplay@gmail.com</code>{" "}
            &mdash; you don&apos;t need to do anything for those.
          </p>
        </div>
        <button
          type="button"
          onClick={loadAll}
          data-testid="email-admin-refresh"
          className="inline-flex items-center gap-1.5 text-[10px] uppercase tracking-widest font-bold text-ink/50 hover:text-forest px-3 py-2 border border-gray-border hover:border-forest transition-colors"
        >
          <RefreshCw className="w-3 h-3" /> Refresh
        </button>
      </div>

      {/* Sent log — every outgoing email with open tracking */}
      <EmailSentLog />

      {/* SMTP status banner */}
      {smtpEnabled ? (
        <div
          data-testid="email-admin-smtp-ok"
          className="border border-forest-pop/40 bg-forest-pop/8 p-4 flex items-start gap-3"
        >
          <Zap className="w-4 h-4 text-forest-pop mt-0.5 shrink-0" />
          <div className="flex-1">
            <div className="text-[10px] uppercase tracking-[0.22em] font-black text-forest-pop">SMTP ACTIVE</div>
            <p className="mt-1 text-[13px] text-ink/80 leading-snug">
              Gmail SMTP is configured. Welcome + purchase-confirmation emails fire automatically. Bulk sends
              are throttled at 1 email/second (well under Gmail&apos;s ~100/hour limit).
            </p>
          </div>
        </div>
      ) : (
        <div
          data-testid="email-admin-smtp-warning"
          className="border border-orange-400/40 bg-orange-400/8 p-4 flex items-start gap-3"
        >
          <AlertCircle className="w-4 h-4 text-orange-500 mt-0.5 shrink-0" />
          <div className="flex-1">
            <div className="text-[10px] uppercase tracking-[0.22em] font-black text-orange-500">SMTP NOT CONFIGURED</div>
            <p className="mt-1 text-[13px] text-ink/80 leading-snug">
              {smtpNote || (
                <>Add <code className="text-forest bg-forest/8 px-1">SMTP_HOST</code>,
                {" "}<code className="text-forest bg-forest/8 px-1">SMTP_PORT</code>,
                {" "}<code className="text-forest bg-forest/8 px-1">SMTP_USERNAME</code> and
                {" "}<code className="text-forest bg-forest/8 px-1">SMTP_PASSWORD</code>
                {" "}to <code>backend/.env</code> to enable email sending.</>
              )}
            </p>
          </div>
        </div>
      )}

      {/* Compose card */}
      <div className="bg-surface border border-gray-border p-5 md:p-6" data-testid="email-admin-compose">
        <div className="text-[10px] uppercase tracking-[0.28em] font-black text-forest mb-4 flex items-center gap-1.5">
          <Send className="w-3.5 h-3.5" /> Compose broadcast
        </div>

        {/* Segment picker */}
        <div className="mb-4">
          <label className="block text-[10px] uppercase tracking-widest font-bold text-ink/55 mb-1.5">
            Recipient segment
          </label>
          <div className="flex flex-wrap gap-2">
            {Object.entries(SEGMENT_LABELS).map(([key, label]) => {
              const active = form.segment === key;
              const c = counts[key] ?? 0;
              return (
                <button
                  key={key}
                  type="button"
                  onClick={() => setForm((s) => ({ ...s, segment: key }))}
                  data-testid={`email-admin-segment-${key}`}
                  className={`inline-flex items-center gap-1.5 px-3 py-2 border text-[11px] font-semibold transition-colors ${
                    active
                      ? "bg-forest text-white border-forest"
                      : "bg-cream-card text-ink/70 border-gray-border hover:border-forest hover:text-forest"
                  }`}
                >
                  <Users className="w-3 h-3" /> {label}
                  <span className={`text-[10px] font-black ml-1 ${active ? "text-volt" : "text-ink/40"}`}>{c}</span>
                </button>
              );
            })}
          </div>
        </div>

        {/* Subject */}
        <div className="mb-3">
          <label className="block text-[10px] uppercase tracking-widest font-bold text-ink/55 mb-1.5">
            Subject line
          </label>
          <input
            type="text"
            maxLength={500}
            value={form.subject}
            onChange={(e) => setForm((s) => ({ ...s, subject: e.target.value }))}
            placeholder="e.g. New scout tools just launched"
            data-testid="email-admin-subject"
            className="w-full bg-deepnavy border border-gray-border px-3 py-2.5 text-ink font-semibold focus:outline-none focus:border-volt focus:ring-1 focus:ring-volt"
          />
        </div>

        {/* Preheader (optional) */}
        <div className="mb-3">
          <label className="block text-[10px] uppercase tracking-widest font-bold text-ink/55 mb-1.5">
            Preheader <span className="text-ink/35 normal-case font-normal">(inbox preview snippet — optional)</span>
          </label>
          <input
            type="text"
            maxLength={200}
            value={form.preheader}
            onChange={(e) => setForm((s) => ({ ...s, preheader: e.target.value }))}
            placeholder="e.g. Read what's new for your player this week"
            data-testid="email-admin-preheader"
            className="w-full bg-deepnavy border border-gray-border px-3 py-2 text-ink text-sm focus:outline-none focus:border-volt focus:ring-1 focus:ring-volt"
          />
        </div>

        {/* Body (HTML) */}
        <div className="mb-3">
          <label className="block text-[10px] uppercase tracking-widest font-bold text-ink/55 mb-1.5">
            Body <span className="text-ink/35 normal-case font-normal">(plain HTML — inline styles only for best inbox rendering)</span>
          </label>
          <textarea
            value={form.body_html}
            onChange={(e) => setForm((s) => ({ ...s, body_html: e.target.value }))}
            rows={10}
            data-testid="email-admin-body"
            placeholder="<p>Hi &ndash; big news for your player this month...</p>
<p><strong>Feature 1:</strong> new radar visualisation</p>
<p><a href='https://scoutmeplay.com/dashboard'>Open your dashboard →</a></p>"
            className="w-full bg-deepnavy border border-gray-border px-3 py-2.5 text-ink text-sm leading-relaxed focus:outline-none focus:border-volt focus:ring-1 focus:ring-volt resize-y font-mono"
          />
          <div className="mt-1 text-[10px] text-ink/40">
            {form.subject.length}/500 · {form.body_html.length} chars body · Wrapped automatically in the ScoutMePlay email chrome.
          </div>
        </div>

        {/* Test send + Broadcast */}
        <div className="mt-5 pt-5 border-t border-gray-border flex flex-wrap items-end gap-3">
          <div className="flex-1 min-w-[220px]">
            <label className="block text-[10px] uppercase tracking-widest font-bold text-ink/55 mb-1.5">
              Send TEST to (preview yourself first)
            </label>
            <input
              type="email"
              value={form.test_email}
              onChange={(e) => setForm((s) => ({ ...s, test_email: e.target.value }))}
              placeholder="you@example.com"
              data-testid="email-admin-test-email"
              className="w-full bg-cream-card border border-gray-border px-3 py-2 text-ink text-sm focus:outline-none focus:border-volt focus:ring-1 focus:ring-volt"
            />
          </div>
          <button
            type="button"
            onClick={sendTest}
            disabled={testing || !canSend || !form.test_email.trim()}
            data-testid="email-admin-send-test"
            className="inline-flex items-center gap-1.5 bg-cream-card hover:bg-gray-border text-ink font-barlow font-black uppercase tracking-widest text-xs px-4 py-2.5 border border-gray-border hover:border-forest transition-colors disabled:opacity-50"
          >
            {testing ? <Loader2 className="w-3 h-3 animate-spin" /> : <Sparkles className="w-3.5 h-3.5" />}
            Send test
          </button>
          <button
            type="button"
            onClick={broadcast}
            disabled={sending || !canSend || recipientCount === 0}
            data-testid="email-admin-broadcast"
            className="inline-flex items-center gap-1.5 bg-forest hover:bg-forest-pop text-white font-barlow font-black uppercase tracking-widest text-sm px-5 py-2.5 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {sending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
            Send to {recipientCount} users
          </button>
        </div>
      </div>

      {/* Job history */}
      <div>
        <div className="text-[10px] uppercase tracking-[0.28em] font-black text-ink/60 mb-2 flex items-center gap-1.5">
          <Mail className="w-3 h-3" /> Recent broadcasts
        </div>
        {jobs.length === 0 ? (
          <div className="border border-gray-border bg-cream-card p-6 text-center text-sm text-ink/55">
            No broadcasts yet. Compose your first one above.
          </div>
        ) : (
          <div className="border border-gray-border overflow-x-auto" data-testid="email-admin-jobs">
            <table className="w-full text-sm">
              <thead className="bg-volt text-white uppercase text-[10px] tracking-widest font-bold">
                <tr>
                  <th className="p-3 text-left">Subject</th>
                  <th className="p-3 text-left">Segment</th>
                  <th className="p-3 text-right">Sent</th>
                  <th className="p-3 text-right">Failed</th>
                  <th className="p-3 text-left">Status</th>
                  <th className="p-3 text-left">When</th>
                </tr>
              </thead>
              <tbody>
                {jobs.map((j) => {
                  const pct = j.total > 0 ? Math.round(((j.sent || 0) / j.total) * 100) : 0;
                  return (
                    <tr key={j.id} className="border-t border-gray-border">
                      <td className="p-3 text-ink font-semibold">{j.subject}</td>
                      <td className="p-3 text-ink/70">{SEGMENT_LABELS[j.segment] || j.segment}</td>
                      <td className="p-3 text-right tabular-nums text-forest-pop font-bold">
                        {j.sent || 0}<span className="text-ink/40 font-normal">/{j.total || 0}</span>
                        <div className="text-[9px] text-ink/40 font-normal">{pct}%</div>
                      </td>
                      <td className={`p-3 text-right tabular-nums font-bold ${(j.failed || 0) > 0 ? "text-red-500" : "text-ink/40"}`}>
                        {j.failed || 0}
                      </td>
                      <td className="p-3"><StatusPill status={j.status} /></td>
                      <td className="p-3 text-[10px] text-ink/55">
                        {j.created_at ? new Date(j.created_at).toLocaleString() : "—"}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <p className="mt-4 text-[11px] text-ink/45 leading-relaxed">
        <strong className="text-ink/60">Rate limit:</strong> Bulk sends throttle at 1 email/second to stay under
        Gmail&apos;s ~100/hour informal cap. Free Gmail accounts are capped at 500 sends per day —
        for higher volume, switch to a transactional provider (SendGrid / Postmark) in{" "}
        <code className="text-forest bg-forest/8 px-1">email_service.py</code>.
      </p>
    </div>
  );
}
