// QualityAdmin — Quality tab: cross-content overview + site-wide duplicate scanner.
import React, { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { ShieldCheck, Loader2, Copy, ImageIcon, Type, ScanSearch, Camera, Check } from "lucide-react";
import api, { ASSET_BASE } from "@/lib/api";

const SEV_CLS = {
  CRITICAL: "bg-rose-100 text-rose-800",
  IMPORTANT: "bg-amber-100 text-amber-800",
  IMPROVEMENT: "bg-sky-100 text-sky-800",
};

function LandingGenPanel({ img, gen, onGenerate, onApply, busy }) {
  const [dismissed, setDismissed] = useState(false);
  const key = img.file;
  if (gen?.applied_at) {
    return <div className="mt-2 text-[11px] font-bold text-emerald-700" data-testid={`quality-landing-applied-${key}`}>New photo applied ✓ — old file backed up. Re-run the formula check to re-score.</div>;
  }
  if (dismissed) return null;
  if (gen?.status === "generating" || busy === key) {
    return (
      <div className="mt-2 flex items-center gap-2 text-[11px] text-ink/60" data-testid={`quality-landing-generating-${key}`}>
        <Loader2 className="w-3.5 h-3.5 animate-spin text-volt" /> Shooting a documentary replacement — ~30 seconds…
      </div>
    );
  }
  if (gen?.status === "ready" && gen.url) {
    return (
      <div className="mt-2" data-testid={`quality-landing-proposal-${key}`}>
        <div className="grid grid-cols-2 gap-2 max-w-md">
          <div>
            <div className="text-[9px] uppercase tracking-[0.2em] font-bold text-ink/45 mb-0.5">Current</div>
            <img src={`${ASSET_BASE}${img.url}`} alt="Current" className="w-full aspect-video object-cover border border-gray-border" />
          </div>
          <div>
            <div className="text-[9px] uppercase tracking-[0.2em] font-bold text-volt mb-0.5">Proposed</div>
            <img src={`${ASSET_BASE}${gen.url}`} alt="Proposed" className="w-full aspect-video object-cover border-2 border-volt" data-testid={`quality-landing-proposed-img-${key}`} />
          </div>
        </div>
        <div className="mt-2 flex flex-wrap gap-2">
          <button data-testid={`quality-landing-apply-${key}`} onClick={() => onApply(key)}
            className="inline-flex items-center gap-1 px-3 py-1.5 bg-volt text-white text-[10px] font-black uppercase tracking-wider">
            <Check className="w-3 h-3" /> Approve & replace
          </button>
          <button data-testid={`quality-landing-regen-${key}`} onClick={() => onGenerate(key)}
            className="px-3 py-1.5 border border-gray-border text-[10px] font-black uppercase tracking-wider text-ink/60 hover:text-ink">
            Generate again
          </button>
          <button data-testid={`quality-landing-reject-${key}`} onClick={() => setDismissed(true)}
            className="px-3 py-1.5 border border-gray-border text-[10px] font-black uppercase tracking-wider text-ink/50">
            Reject
          </button>
        </div>
      </div>
    );
  }
  return (
    <div className="mt-2">
      {gen?.status === "error" && <div className="text-[11px] text-rose-700 mb-1">Generation failed: {gen.error} — try again.</div>}
      <button
        data-testid={`quality-landing-gen-${key}`}
        onClick={() => onGenerate(key)}
        className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-ink text-cream-base text-[10px] font-black uppercase tracking-wider hover:bg-volt transition-colors"
      >
        <Camera className="w-3 h-3" /> Generate documentary replacement
      </button>
    </div>
  );
}

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
  const [autoQc, setAutoQc] = useState(null);
  const [landing, setLanding] = useState(null);
  const [checkingLanding, setCheckingLanding] = useState(false);
  const landingPollRef = useRef(null);

  const loadLanding = () => api.get("/admin/quality/latest", { params: { kind: "landing", target_id: "site" } }).then((r) => r.data);

  const pollLanding = () => {
    clearInterval(landingPollRef.current);
    landingPollRef.current = setInterval(async () => {
      try {
        const d = await loadLanding();
        if (d.status !== "checking") {
          clearInterval(landingPollRef.current);
          setCheckingLanding(false);
          setLanding(d);
          loadOverview();
          if (d.status === "error") toast.error(`Landing check failed: ${d.error}`);
          else toast.success(`Landing photos scored — overall ${d.scores?.overall}/100`);
        }
      } catch { /* keep polling */ }
    }, 4000);
  };

  const runLandingCheck = async () => {
    setCheckingLanding(true);
    try {
      await api.post("/admin/quality/landing/check");
      toast.info("Scoring every landing photo against the image formula — ~1-2 minutes…");
      pollLanding();
    } catch {
      setCheckingLanding(false);
      toast.error("Could not start landing check");
    }
  };

  const [genBusy, setGenBusy] = useState("");
  const genPollRef = useRef(null);

  const pollGen = (file) => {
    clearInterval(genPollRef.current);
    const key = file.replace(/\./g, "_");
    genPollRef.current = setInterval(async () => {
      try {
        const d = await loadLanding();
        const g = (d.gen || {})[key];
        if (g && g.status !== "generating") {
          clearInterval(genPollRef.current);
          setGenBusy("");
          setLanding(d);
          if (g.status === "error") toast.error(`Generation failed: ${g.error}`);
          else toast.success("Replacement ready — compare CURRENT vs PROPOSED and approve");
        }
      } catch { /* keep polling */ }
    }, 4000);
  };

  const generateReplacement = async (file) => {
    setGenBusy(file);
    try {
      await api.post(`/admin/quality/landing/${file}/generate`);
      toast.info("Shooting a documentary replacement — ~30 seconds…");
      pollGen(file);
    } catch {
      setGenBusy("");
      toast.error("Could not start generation");
    }
  };

  const applyReplacement = async (file) => {
    try {
      await api.post(`/admin/quality/landing/${file}/apply`);
      toast.success(`${file} replaced on the site — old photo backed up`);
      const d = await loadLanding();
      setLanding(d);
    } catch {
      toast.error("Could not apply replacement");
    }
  };

  const loadOverview = () => api.get("/admin/quality/overview").then(({ data }) => setOverview(data)).catch(() => {});

  useEffect(() => {
    loadOverview();
    api.get("/admin/quality/config").then(({ data }) => setAutoQc(!!data.auto_qc)).catch(() => {});
    api.get("/admin/quality/latest", { params: { kind: "duplicates", target_id: "site" } })
      .then(({ data }) => { if (data.found && data.status === "ready") setDup(data); })
      .catch(() => {});
    loadLanding().then((d) => {
      if (d.found && d.status === "ready") setLanding(d);
      else if (d.found && d.status === "checking") { setCheckingLanding(true); pollLanding(); }
    }).catch(() => {});
    return () => { clearInterval(landingPollRef.current); clearInterval(genPollRef.current); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const toggleAutoQc = async () => {
    const next = !autoQc;
    setAutoQc(next);
    try {
      await api.put("/admin/quality/config", { auto_qc: next });
      toast.success(next
        ? "Auto-QC ON — every new article and carousel gets quality-checked automatically"
        : "Auto-QC OFF");
    } catch {
      setAutoQc(!next);
      toast.error("Could not save setting");
    }
  };

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

      <div className="bg-surface border border-gray-border p-5 flex items-center justify-between flex-wrap gap-3" data-testid="quality-auto-qc-card">
        <div>
          <div className="font-barlow font-black uppercase text-sm tracking-tight">Auto-QC new content</div>
          <p className="text-xs text-ink/55 mt-0.5 max-w-xl">Every new blog article and carousel is quality-checked automatically the moment it's created — nothing generic slips live unnoticed.</p>
        </div>
        <button
          data-testid="quality-auto-qc-toggle"
          onClick={toggleAutoQc}
          disabled={autoQc === null}
          className={`px-4 py-2 text-xs font-black uppercase tracking-wider transition-colors ${autoQc ? "bg-volt text-white" : "border border-gray-border text-ink/50 hover:text-ink"}`}
        >
          {autoQc === null ? "…" : autoQc ? "ON" : "OFF"}
        </button>
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
            <Camera className="w-5 h-5 text-volt" />
            <h3 className="font-barlow font-black uppercase text-lg tracking-tight">Landing photos — formula check</h3>
            {landing?.status === "ready" && (
              <span className={`px-2.5 py-1 text-[11px] font-black uppercase tracking-wider ${landing.scores?.overall >= 85 ? "bg-emerald-100 text-emerald-800" : landing.scores?.overall >= 65 ? "bg-amber-100 text-amber-800" : "bg-rose-100 text-rose-800"}`}>
                Overall {landing.scores?.overall}/100
              </span>
            )}
          </div>
          <button
            data-testid="quality-landing-check"
            onClick={runLandingCheck}
            disabled={checkingLanding}
            className="inline-flex items-center gap-2 px-5 py-2.5 bg-volt text-white text-xs font-black uppercase tracking-wider hover:bg-volt-hover transition-colors disabled:opacity-50"
          >
            {checkingLanding ? <Loader2 className="w-4 h-4 animate-spin" /> : <Camera className="w-4 h-4" />}
            {checkingLanding ? "Scoring…" : "Run formula check"}
          </button>
        </div>
        <p className="text-xs text-ink/55 mt-1 max-w-2xl">
          Scores every hero and landing photo 0-100 on Authenticity, Football realism, Emotional relevance, Originality and Brand fit — the anti-generic image formula.
        </p>

        {landing?.status === "ready" && (
          <div className="mt-5 space-y-2" data-testid="quality-landing-results">
            {(landing.repetition || []).map((r, i) => (
              <div key={i} className="border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800 font-bold">REPETITION WARNING: {r}</div>
            ))}
            {[...(landing.images || [])].sort((a, b) => a.avg - b.avg).map((img) => (
              <div key={img.file} className="border border-gray-border bg-cream-base/40 p-3 flex gap-3" data-testid={`quality-landing-${img.file.replace(/\./g, "-")}`}>
                <img src={`${ASSET_BASE}${img.url}`} alt={img.label} className="w-24 h-16 object-cover border border-gray-border shrink-0" loading="lazy" />
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-sm font-bold text-ink">{img.label}</span>
                    <span className={`px-1.5 py-0.5 text-[9px] font-black uppercase tracking-wider ${img.classification === "AUTHENTIC" ? "bg-emerald-100 text-emerald-800" : img.classification === "REVIEW" ? "bg-amber-100 text-amber-800" : "bg-rose-100 text-rose-800"}`}>{img.classification}</span>
                    {img.verdict !== "KEEP" && <span className="px-1.5 py-0.5 text-[9px] font-black uppercase tracking-wider bg-rose-100 text-rose-800">{img.verdict}</span>}
                    <span className="text-[10px] text-ink/40">{img.used_on}</span>
                  </div>
                  <div className="mt-1.5 flex flex-wrap gap-1">
                    {[["authenticity", "Auth"], ["football_realism", "Realism"], ["emotional_relevance", "Emotion"], ["originality", "Original"], ["brand_fit", "Brand"]].map(([k, lbl]) => {
                      const v = img.scores?.[k];
                      const tone = v >= 85 ? "bg-emerald-50 text-emerald-700 border-emerald-200" : v >= 65 ? "bg-amber-50 text-amber-700 border-amber-200" : "bg-rose-50 text-rose-700 border-rose-200";
                      return <span key={k} className={`px-1.5 py-0.5 border text-[9px] font-bold uppercase tracking-wider ${tone}`}>{lbl} {v}</span>;
                    })}
                  </div>
                  {(img.issues || []).length > 0 && (
                    <ul className="mt-1.5 space-y-0.5">
                      {img.issues.map((iss, i) => <li key={i} className="text-[11px] text-rose-700">• {iss}</li>)}
                    </ul>
                  )}
                  {img.verdict !== "KEEP" && (
                    <LandingGenPanel
                      img={img}
                      gen={(landing.gen || {})[img.file.replace(/\./g, "_")]}
                      onGenerate={generateReplacement}
                      onApply={applyReplacement}
                      busy={genBusy}
                    />
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
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
