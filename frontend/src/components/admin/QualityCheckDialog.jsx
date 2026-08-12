// QualityCheckDialog — shared anti-generic QC modal for blog articles + carousels.
import React, { useEffect, useRef, useState, useCallback } from "react";
import { toast } from "sonner";
import { X, ShieldCheck, Loader2, RefreshCw, Check, AlertTriangle } from "lucide-react";
import api from "@/lib/api";

const GROUP_LABEL = { text: "Text", seo: "SEO / Keywords", image: "Image" };

export function ScoreChip({ label, value }) {
  if (value == null) return null;
  const tone = value >= 85 ? "bg-emerald-100 text-emerald-800" : value >= 65 ? "bg-amber-100 text-amber-800" : "bg-rose-100 text-rose-800";
  return (
    <span className={`px-2.5 py-1 text-[11px] font-black uppercase tracking-wider ${tone}`}>
      {label} {value}/100
    </span>
  );
}

export function ChecksList({ checks }) {
  const groups = [...new Set((checks || []).map((c) => c.group || "text"))];
  return (
    <div className="space-y-3">
      {groups.map((g) => (
        <div key={g}>
          <div className="text-[10px] uppercase tracking-[0.2em] font-bold text-ink/40 mb-1">{GROUP_LABEL[g] || g}</div>
          {(checks || []).filter((c) => (c.group || "text") === g).map((c) => (
            <div key={c.key} className="flex items-start gap-1.5 text-[12px] py-0.5">
              {c.pass ? <Check className="w-3.5 h-3.5 text-emerald-600 shrink-0 mt-[2px]" /> : <X className="w-3.5 h-3.5 text-rose-600 shrink-0 mt-[2px]" />}
              <span className={c.pass ? "text-ink/60" : "text-rose-700"}>
                {c.label}{!c.pass && c.issue ? ` — ${c.issue}` : ""}
              </span>
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}

export function ProposedField({ fieldKey, label, current, proposed, onApply, applying }) {
  const [value, setValue] = useState(proposed);
  const [dismissed, setDismissed] = useState(false);
  if (dismissed) return null;
  return (
    <div className="border border-gray-border p-3 bg-cream-base/50" data-testid={`qc-proposed-${fieldKey}`}>
      <div className="text-[10px] uppercase tracking-[0.2em] font-bold text-ink/50">{label}</div>
      <div className="mt-1.5 text-[11px] text-ink/50"><span className="font-bold uppercase text-[9px] tracking-wider">Current: </span>{current || "(empty)"}</div>
      <textarea
        data-testid={`qc-proposed-input-${fieldKey}`}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        rows={Math.min(5, Math.max(2, Math.ceil((value || "").length / 80)))}
        className="mt-2 w-full border border-volt/40 bg-white px-2 py-1.5 text-xs"
      />
      <div className="mt-2 flex gap-2">
        <button
          data-testid={`qc-apply-${fieldKey}`}
          onClick={() => onApply(fieldKey, value)}
          disabled={applying || !value.trim()}
          className="inline-flex items-center gap-1 px-3 py-1.5 bg-volt text-white text-[10px] font-black uppercase tracking-wider disabled:opacity-50"
        >
          {applying ? <Loader2 className="w-3 h-3 animate-spin" /> : <Check className="w-3 h-3" />} Approve & apply
        </button>
        <button
          data-testid={`qc-reject-${fieldKey}`}
          onClick={() => setDismissed(true)}
          className="px-3 py-1.5 border border-gray-border text-[10px] font-black uppercase tracking-wider text-ink/50"
        >
          Reject
        </button>
      </div>
    </div>
  );
}

const BLOG_FIELD_LABELS = {
  title: "Title", excerpt: "Excerpt", meta_title: "Meta title",
  meta_description: "Meta description", meta_keywords: "Meta keywords", cover_image_alt: "Cover alt text",
};

export default function QualityCheckDialog({ kind, targetId, title, onClose, onApplied }) {
  const [result, setResult] = useState(null);
  const [checking, setChecking] = useState(false);
  const [applying, setApplying] = useState(false);
  const pollRef = useRef(null);

  const load = useCallback(async () => {
    const { data } = await api.get(`/admin/quality/latest`, { params: { kind, target_id: targetId } });
    return data;
  }, [kind, targetId]);

  const startPoll = useCallback(() => {
    clearInterval(pollRef.current);
    pollRef.current = setInterval(async () => {
      try {
        const data = await load();
        if (data.status !== "checking") {
          clearInterval(pollRef.current);
          setChecking(false);
          setResult(data);
          if (data.status === "error") toast.error(`Check failed: ${data.error}`);
        }
      } catch { /* keep polling */ }
    }, 3000);
  }, [load]);

  const runCheck = useCallback(async () => {
    setChecking(true);
    try {
      await api.post(`/admin/quality/${kind}/${targetId}/check`);
      startPoll();
    } catch {
      setChecking(false);
      toast.error("Could not start check");
    }
  }, [kind, targetId, startPoll]);

  useEffect(() => {
    load().then((data) => {
      if (!data.found) runCheck();
      else if (data.status === "checking") { setChecking(true); startPoll(); }
      else setResult(data);
    }).catch(() => toast.error("Could not load QC state"));
    return () => clearInterval(pollRef.current);
  }, [load, runCheck, startPoll]);

  const apply = async (fieldKey, value) => {
    setApplying(true);
    try {
      if (kind === "blog") await api.post(`/admin/quality/blog/${targetId}/apply`, { fields: { [fieldKey]: value } });
      else await api.post(`/admin/quality/carousel/${targetId}/apply`, { caption: value });
      toast.success(`${BLOG_FIELD_LABELS[fieldKey] || "Caption"} updated`);
      onApplied?.();
    } catch {
      toast.error("Could not apply change");
    } finally {
      setApplying(false);
    }
  };

  const ready = result?.status === "ready";
  const cls = result?.image_classification;

  return (
    <div className="fixed inset-0 z-50 bg-ink/60 flex items-start justify-center overflow-y-auto p-4 md:p-10" data-testid="qc-dialog">
      <div className="bg-surface border border-gray-border w-full max-w-2xl">
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-border sticky top-0 bg-surface">
          <div className="flex items-center gap-2 min-w-0">
            <ShieldCheck className="w-5 h-5 text-volt shrink-0" />
            <div className="min-w-0">
              <div className="font-barlow font-black uppercase text-lg leading-tight truncate">Anti-generic QC</div>
              <div className="text-[11px] text-ink/50 truncate">{title}</div>
            </div>
          </div>
          <button onClick={onClose} data-testid="qc-close" className="p-1.5 text-ink/50 hover:text-ink shrink-0"><X className="w-5 h-5" /></button>
        </div>

        <div className="p-5 space-y-5">
          {checking && (
            <div className="text-center py-10" data-testid="qc-checking">
              <Loader2 className="w-6 h-6 animate-spin text-volt mx-auto" />
              <div className="mt-3 text-sm text-ink/60">Running the anti-generic quality check…</div>
            </div>
          )}

          {!checking && result?.status === "error" && (
            <div className="bg-rose-50 border border-rose-200 p-4 text-sm text-rose-800" data-testid="qc-error">
              Check failed: {result.error}
              <button onClick={runCheck} className="ml-3 underline font-bold">Try again</button>
            </div>
          )}

          {!checking && ready && (
            <>
              {result.stale && (
                <div className="flex items-center gap-2 bg-amber-50 border border-amber-200 px-3 py-2 text-xs text-amber-800" data-testid="qc-stale">
                  <AlertTriangle className="w-4 h-4" /> Content changed since this check — re-run for fresh results.
                </div>
              )}
              <div className="flex flex-wrap items-center gap-2">
                <ScoreChip label="Overall" value={result.scores?.overall} />
                <ScoreChip label="Text" value={result.scores?.text} />
                <ScoreChip label="SEO" value={result.scores?.seo} />
                <ScoreChip label="Image" value={result.scores?.image} />
                {cls && cls !== "NONE" && (
                  <span className={`px-2.5 py-1 text-[11px] font-black uppercase tracking-wider ${cls === "AUTHENTIC" ? "bg-emerald-100 text-emerald-800" : cls === "REVIEW" ? "bg-amber-100 text-amber-800" : "bg-rose-100 text-rose-800"}`} data-testid="qc-image-classification">
                    Cover: {cls.replace("_", " ")}{result.image_recommendation && result.image_recommendation !== "NONE" && result.image_recommendation !== "KEEP" ? ` → ${result.image_recommendation}` : ""}
                  </span>
                )}
                <button onClick={runCheck} data-testid="qc-rerun" className="ml-auto inline-flex items-center gap-1 px-2.5 py-1 border border-gray-border text-[10px] font-bold uppercase tracking-wider text-ink/60 hover:text-ink">
                  <RefreshCw className="w-3 h-3" /> Re-run
                </button>
              </div>

              <ChecksList checks={result.checks} />

              {result.proposed && Object.keys(result.proposed).length > 0 && (
                <div className="space-y-3">
                  <div className="font-barlow font-black uppercase text-sm tracking-tight border-t border-gray-border pt-4">Proposed improvements — you decide</div>
                  {Object.entries(result.proposed).map(([k, v]) => (
                    <ProposedField
                      key={k}
                      fieldKey={k}
                      label={BLOG_FIELD_LABELS[k] || "Caption"}
                      current={result.current?.[k]}
                      proposed={v}
                      onApply={apply}
                      applying={applying}
                    />
                  ))}
                </div>
              )}
              {result.passed && (!result.proposed || !Object.keys(result.proposed).length) && (
                <div className="bg-emerald-50 border border-emerald-200 px-3 py-2 text-xs text-emerald-800 font-bold" data-testid="qc-all-pass">
                  All checks passed — nothing generic found.
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
