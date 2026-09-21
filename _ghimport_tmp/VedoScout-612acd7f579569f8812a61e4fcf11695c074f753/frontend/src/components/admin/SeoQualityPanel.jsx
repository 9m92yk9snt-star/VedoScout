// SeoQualityPanel — anti-generic QC for all public SEO metadata, with approve-to-apply.
import React, { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { ShieldCheck, Loader2, Check, X } from "lucide-react";
import api from "@/lib/api";
import { ScoreChip } from "./QualityCheckDialog";

function PageResult({ pageKey, page, onApplied }) {
  const [form, setForm] = useState(page.proposed || {});
  const [applying, setApplying] = useState(false);
  const [applied, setApplied] = useState(false);
  const failing = (page.checks || []).filter((c) => !c.pass);
  const hasProposal = Object.keys(page.proposed || {}).length > 0;

  const apply = async () => {
    setApplying(true);
    try {
      await api.post("/admin/quality/seo/apply", { pages: { [pageKey]: form } });
      setApplied(true);
      toast.success(`${page.label} SEO updated`);
      onApplied?.();
    } catch {
      toast.error("Could not apply");
    } finally {
      setApplying(false);
    }
  };

  if (page.passed && !hasProposal) {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-1 bg-emerald-50 border border-emerald-200 text-emerald-800 text-[10px] font-bold uppercase tracking-wider" data-testid={`seo-qc-pass-${pageKey}`}>
        <Check className="w-3 h-3" /> {page.label} {page.score}/100
      </span>
    );
  }

  return (
    <div className="border border-gray-border p-4 bg-cream-base/40" data-testid={`seo-qc-page-${pageKey}`}>
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div className="font-bold text-sm text-ink">{page.label} <span className="text-ink/40 font-normal text-xs">{page.path}</span></div>
        <ScoreChip label="Score" value={page.score} />
      </div>
      {failing.length > 0 && (
        <div className="mt-2 space-y-1">
          {failing.map((c) => (
            <div key={c.key} className="flex items-start gap-1.5 text-[12px] text-rose-700">
              <X className="w-3.5 h-3.5 shrink-0 mt-[2px]" /> {c.label}{c.issue ? ` — ${c.issue}` : ""}
            </div>
          ))}
        </div>
      )}
      {hasProposal && !applied && (
        <div className="mt-3 space-y-2">
          {["title", "description", "keywords"].filter((f) => page.proposed[f]).map((f) => (
            <div key={f}>
              <div className="text-[10px] uppercase tracking-[0.2em] font-bold text-ink/50">{f}</div>
              <div className="text-[11px] text-ink/45 mt-0.5">Current: {page.current?.[f] || "(empty)"}</div>
              <textarea
                data-testid={`seo-qc-input-${pageKey}-${f}`}
                value={form[f] || ""}
                onChange={(e) => setForm((x) => ({ ...x, [f]: e.target.value }))}
                rows={f === "title" ? 1 : 2}
                className="mt-1 w-full border border-volt/40 bg-white px-2 py-1.5 text-xs"
              />
            </div>
          ))}
          <button
            data-testid={`seo-qc-apply-${pageKey}`}
            onClick={apply}
            disabled={applying}
            className="inline-flex items-center gap-1 px-3 py-1.5 bg-volt text-white text-[10px] font-black uppercase tracking-wider disabled:opacity-50"
          >
            {applying ? <Loader2 className="w-3 h-3 animate-spin" /> : <Check className="w-3 h-3" />} Approve & apply
          </button>
        </div>
      )}
      {applied && <div className="mt-2 text-[11px] text-emerald-700 font-bold" data-testid={`seo-qc-applied-${pageKey}`}>Applied ✓</div>}
    </div>
  );
}

export default function SeoQualityPanel({ onApplied }) {
  const [result, setResult] = useState(null);
  const [checking, setChecking] = useState(false);
  const pollRef = useRef(null);

  const load = () => api.get("/admin/quality/latest", { params: { kind: "seo", target_id: "site" } }).then((r) => r.data);

  useEffect(() => {
    load().then((d) => {
      if (d.found && d.status === "ready") setResult(d);
      else if (d.found && d.status === "checking") { setChecking(true); poll(); }
    }).catch(() => {});
    return () => clearInterval(pollRef.current);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const poll = () => {
    clearInterval(pollRef.current);
    pollRef.current = setInterval(async () => {
      try {
        const d = await load();
        if (d.status !== "checking") {
          clearInterval(pollRef.current);
          setChecking(false);
          setResult(d);
          if (d.status === "error") toast.error(`SEO check failed: ${d.error}`);
        }
      } catch { /* keep polling */ }
    }, 3000);
  };

  const run = async () => {
    setChecking(true);
    try {
      await api.post("/admin/quality/seo/check");
      toast.info("Checking all public pages for generic SEO — ~30-60 seconds…");
      poll();
    } catch {
      setChecking(false);
      toast.error("Could not start SEO check");
    }
  };

  const pages = result?.status === "ready" ? Object.entries(result.pages || {}) : [];
  const passing = pages.filter(([, p]) => p.passed && !Object.keys(p.proposed || {}).length);
  const failing = pages.filter(([, p]) => !p.passed || Object.keys(p.proposed || {}).length);

  return (
    <div className="border border-gray-border bg-surface p-5" data-testid="seo-quality-panel">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div className="flex items-center gap-2">
          <ShieldCheck className="w-5 h-5 text-volt" />
          <h3 className="font-barlow font-black uppercase text-lg tracking-tight">Anti-generic SEO QC</h3>
          {result?.status === "ready" && <ScoreChip label="Site SEO" value={result.scores?.overall} />}
          {result?.stale && <span className="text-[10px] uppercase font-bold text-amber-700">SEO changed since last check</span>}
        </div>
        <button
          data-testid="seo-qc-run"
          onClick={run}
          disabled={checking}
          className="inline-flex items-center gap-2 px-4 py-2 bg-volt text-white text-xs font-black uppercase tracking-wider disabled:opacity-50"
        >
          {checking ? <Loader2 className="w-4 h-4 animate-spin" /> : <ShieldCheck className="w-4 h-4" />}
          {checking ? "Checking…" : "Run QC on all pages"}
        </button>
      </div>
      <p className="text-xs text-ink/55 mt-1">Checks every public page's title, description and keywords for generic filler, keyword stuffing, weak wording and inaccurate claims — you approve every change.</p>

      {result?.status === "ready" && (
        <div className="mt-4 space-y-3">
          {failing.map(([key, p]) => <PageResult key={key} pageKey={key} page={p} onApplied={onApplied} />)}
          {passing.length > 0 && (
            <div className="flex flex-wrap gap-1.5 pt-1">
              {passing.map(([key, p]) => <PageResult key={key} pageKey={key} page={p} />)}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
