// QualityAdmin — Quality tab: cross-content overview + site-wide duplicate scanner.
import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import { ShieldCheck, Loader2, Copy, ImageIcon, Type, ScanSearch } from "lucide-react";
import api from "@/lib/api";

const SEV_CLS = {
  CRITICAL: "bg-rose-100 text-rose-800",
  IMPORTANT: "bg-amber-100 text-amber-800",
  IMPROVEMENT: "bg-sky-100 text-sky-800",
};

function OverviewCard({ label, main, sub, testid }) {
  return (
    <div className="bg-surface border border-gray-border p-5" data-testid={testid}>
      <div className="text-[10px] uppercase tracking-[0.2em] font-bold text-ink/45">{label}</div>
      <div className="mt-2 font-barlow font-black text-3xl text-ink">{main}</div>
      <div className="text-[11px] text-ink/50 mt-1">{sub}</div>
    </div>
  );
}

export default function QualityAdmin() {
  const [overview, setOverview] = useState(null);
  const [dup, setDup] = useState(null);
  const [scanning, setScanning] = useState(false);

  const loadOverview = () => api.get("/admin/quality/overview").then(({ data }) => setOverview(data)).catch(() => {});

  useEffect(() => {
    loadOverview();
    api.get("/admin/quality/latest", { params: { kind: "duplicates", target_id: "site" } })
      .then(({ data }) => { if (data.found && data.status === "ready") setDup(data); })
      .catch(() => {});
  }, []);

  const scan = async () => {
    setScanning(true);
    try {
      const { data } = await api.post("/admin/quality/duplicates/scan");
      setDup(data);
      loadOverview();
      toast.success(data.warnings.length
        ? `Scan complete — ${data.warnings.length} repetition warning(s) found`
        : "Scan complete — no duplicates found");
    } catch {
      toast.error("Duplicate scan failed");
    } finally {
      setScanning(false);
    }
  };

  const o = overview;
  return (
    <div className="space-y-8" data-testid="quality-admin">
      <div>
        <div className="flex items-center gap-2 mb-1">
          <ShieldCheck className="w-5 h-5 text-volt" />
          <h2 className="font-barlow font-black uppercase text-2xl tracking-tight">Quality Engine</h2>
        </div>
        <p className="text-sm text-ink/60 max-w-2xl">
          The same anti-generic standard as Ad Studio, applied to your existing content.
          Run QC per article in the Blog tab, per carousel in Marketing, and on all SEO pages in SEO &amp; Social.
          Below: overview + the site-wide duplicate scanner.
        </p>
      </div>

      <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-px bg-cream-soft/40 border border-gray-border">
        <OverviewCard
          testid="quality-card-blog"
          label="Blog articles"
          main={o?.blog?.avg != null ? `${o.blog.avg}/100` : "—"}
          sub={o?.blog?.checked ? `${o.blog.checked} checked · ${o.blog.failing} with issues` : "No articles checked yet — use QC in the Blog tab"}
        />
        <OverviewCard
          testid="quality-card-carousel"
          label="Instagram carousels"
          main={o?.carousel?.avg != null ? `${o.carousel.avg}/100` : "—"}
          sub={o?.carousel?.checked ? `${o.carousel.checked} checked · ${o.carousel.failing} with issues` : "No carousels checked yet — use QC in Marketing"}
        />
        <OverviewCard
          testid="quality-card-seo"
          label="SEO pages"
          main={o?.seo?.score != null ? `${o.seo.score}/100` : "—"}
          sub={o?.seo?.checked ? `Last check ${(o.seo.checked_at || "").slice(0, 10)}` : "Not checked yet — run QC in SEO & Social"}
        />
        <OverviewCard
          testid="quality-card-duplicates"
          label="Duplicates"
          main={o?.duplicates?.score != null ? `${o.duplicates.score}/100` : "—"}
          sub={o?.duplicates?.scanned ? `${o.duplicates.warnings} warning(s) · ${(o.duplicates.checked_at || "").slice(0, 10)}` : "Not scanned yet"}
        />
      </div>

      <div className="bg-surface border border-gray-border p-6">
        <div className="flex items-center justify-between flex-wrap gap-3">
          <div className="flex items-center gap-2">
            <Copy className="w-5 h-5 text-volt" />
            <h3 className="font-barlow font-black uppercase text-lg tracking-tight">Repetition detection</h3>
          </div>
          <button
            data-testid="quality-scan-duplicates"
            onClick={scan}
            disabled={scanning}
            className="inline-flex items-center gap-2 px-5 py-2.5 bg-volt text-white text-xs font-black uppercase tracking-wider hover:bg-volt-hover transition-colors disabled:opacity-50"
          >
            {scanning ? <Loader2 className="w-4 h-4 animate-spin" /> : <ScanSearch className="w-4 h-4" />}
            {scanning ? "Scanning…" : "Scan for duplicates"}
          </button>
        </div>
        <p className="text-xs text-ink/55 mt-1 max-w-2xl">
          Compares blog titles, excerpts, meta descriptions and full-text sentences across articles, SEO pages, carousel captions — plus near-identical images across blog covers, Ad Studio and landing assets.
        </p>

        {dup && (
          <div className="mt-5">
            <div className="text-xs text-ink/50 mb-3">
              Scanned {dup.counts?.items_scanned} items · {dup.counts?.text} text + {dup.counts?.image} image warning(s)
            </div>
            {dup.warnings?.length === 0 && (
              <div className="bg-emerald-50 border border-emerald-200 px-3 py-2 text-xs text-emerald-800 font-bold" data-testid="quality-no-duplicates">
                No duplicated content found — the site stays varied.
              </div>
            )}
            <div className="space-y-2" data-testid="quality-warnings-list">
              {(dup.warnings || []).map((w, i) => (
                <div key={i} className="border border-gray-border p-3 bg-cream-base/40" data-testid={`quality-warning-${i}`}>
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className={`px-2 py-0.5 text-[9px] font-black uppercase tracking-wider ${SEV_CLS[w.severity] || "bg-gray-100 text-gray-700"}`}>{w.severity}</span>
                    <span className="inline-flex items-center gap-1 text-[10px] uppercase font-bold text-ink/50">
                      {w.type === "image" ? <ImageIcon className="w-3 h-3" /> : <Type className="w-3 h-3" />} {w.kind}
                    </span>
                    <span className="text-[10px] text-ink/40">{Math.round((w.similarity || 0) * 100)}% similar</span>
                  </div>
                  <div className="mt-1.5 text-xs text-ink/70">{w.detail}</div>
                  <div className="mt-1 text-[11px] text-ink/45">{(w.where || []).join("  ·  ")}</div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
