// SeoAdmin — per-page SEO manager (title / description / keywords) + sitemap & feed links.
import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import { Globe, Sparkles, ExternalLink } from "lucide-react";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;

function GooglePreview({ path, title, description }) {
  const host = typeof window !== "undefined" ? window.location.host : "scoutmeplay.com";
  return (
    <div className="rounded-lg bg-white border border-ink/10 p-3.5">
      <div className="text-[11px] text-[#202124] flex items-center gap-1.5">
        <Globe className="w-3 h-3 text-ink/40" /> {host}{path}
      </div>
      <div className="text-[#1a0dab] text-[16px] leading-snug mt-0.5 truncate">
        {title ? (title.toLowerCase().includes("scoutmeplay") ? title : `${title} · ScoutMePlay`) : "—"}
      </div>
      <div className="text-[#4d5156] text-[12.5px] leading-snug mt-0.5 line-clamp-2">{description || "—"}</div>
    </div>
  );
}

export default function SeoAdmin() {
  const [pages, setPages] = useState(null);
  const [form, setForm] = useState({});
  const [saving, setSaving] = useState(false);
  const [filling, setFilling] = useState(false);

  const load = () =>
    api.get("/admin/seo").then(({ data }) => {
      setPages(data.pages);
      const f = {};
      data.pages.forEach((p) => {
        f[p.key] = {
          title: p.override?.title || "",
          description: p.override?.description || "",
          keywords: p.override?.keywords || "",
        };
      });
      setForm(f);
    }).catch(() => toast.error("Could not load SEO settings"));

  useEffect(() => { load(); }, []);

  const set = (key, field, value) => setForm((f) => ({ ...f, [key]: { ...f[key], [field]: value } }));

  const save = async () => {
    setSaving(true);
    try {
      await api.put("/admin/seo", { pages: form });
      toast.success("SEO saved — live on next page load");
    } catch {
      toast.error("Could not save SEO");
    } finally {
      setSaving(false);
    }
  };

  const autofill = async () => {
    setFilling(true);
    try {
      const { data } = await api.post("/admin/seo/autofill");
      const f = {};
      Object.entries(data.pages).forEach(([k, v]) => { f[k] = { ...v }; });
      setForm(f);
      toast.success("Recommended SEO filled in for every page — remember to Save");
    } catch {
      toast.error("Auto-fill failed");
    } finally {
      setFilling(false);
    }
  };

  if (!pages) return <div className="text-ink/50 text-sm py-6">Loading SEO settings…</div>;

  return (
    <div className="space-y-6" data-testid="seo-admin">
      {/* Search engine files */}
      <div className="rounded-lg border border-ink/10 bg-white/5 p-4">
        <div className="font-bold text-ink mb-1">Search engine files (automatic)</div>
        <p className="text-xs text-ink/50 mb-3">
          These update themselves — every published blog post is added automatically. Submit the sitemap once in
          {" "}<a className="underline text-forest" href="https://search.google.com/search-console" target="_blank" rel="noopener noreferrer">Google Search Console</a>
          {" "}and Google keeps crawling on its own.
        </p>
        <div className="flex flex-wrap gap-2">
          {[
            ["Sitemap", "/api/sitemap.xml", "seo-link-sitemap"],
            ["Robots.txt", "/api/robots.txt", "seo-link-robots"],
            ["Blog RSS feed", "/api/rss.xml", "seo-link-rss"],
          ].map(([label, path, tid]) => (
            <a key={path} href={`${BACKEND_URL}${path}`} target="_blank" rel="noopener noreferrer" data-testid={tid}
              className="inline-flex items-center gap-1.5 text-xs font-bold border border-ink/15 rounded-md px-3 py-1.5 text-ink/70 hover:border-forest hover:text-forest transition-colors">
              {label} <ExternalLink className="w-3 h-3" />
            </a>
          ))}
        </div>
        <p className="text-[11px] text-ink/40 mt-3">
          Blog posts get their SEO automatically from their title and excerpt — including article structured data for Google.
        </p>
      </div>

      {/* Actions */}
      <div className="flex flex-wrap items-center gap-3">
        <Button onClick={save} disabled={saving} data-testid="seo-save-btn">{saving ? "Saving…" : "Save all pages"}</Button>
        <Button variant="outline" onClick={autofill} disabled={filling} data-testid="seo-autofill-btn">
          <Sparkles className="w-4 h-4 mr-1.5" /> {filling ? "Filling…" : "Auto-fill recommended SEO"}
        </Button>
      </div>

      {/* Per-page editors */}
      <div className="space-y-4">
        {pages.map((p) => {
          const f = form[p.key] || {};
          return (
            <div key={p.key} className="rounded-lg border border-ink/10 p-4" data-testid={`seo-page-${p.key}`}>
              <div className="flex items-baseline justify-between flex-wrap gap-2">
                <div className="font-bold text-ink text-sm">{p.label} <span className="text-ink/35 font-normal">({p.path})</span></div>
              </div>
              <div className="grid lg:grid-cols-2 gap-4 mt-3">
                <div className="space-y-3">
                  <div>
                    <label className="text-[11px] uppercase tracking-wider text-ink/40 font-bold flex justify-between">
                      <span>Title</span><span>{(f.title || "").length}/70</span>
                    </label>
                    <Input maxLength={70} value={f.title || ""} placeholder={p.title} onChange={(e) => set(p.key, "title", e.target.value)} data-testid={`seo-title-${p.key}`} />
                  </div>
                  <div>
                    <label className="text-[11px] uppercase tracking-wider text-ink/40 font-bold flex justify-between">
                      <span>Description</span><span>{(f.description || "").length}/175</span>
                    </label>
                    <textarea
                      maxLength={175} rows={2} value={f.description || ""} placeholder={p.description}
                      onChange={(e) => set(p.key, "description", e.target.value)}
                      data-testid={`seo-desc-${p.key}`}
                      className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm resize-none"
                    />
                  </div>
                  <div>
                    <label className="text-[11px] uppercase tracking-wider text-ink/40 font-bold">Keywords (comma separated)</label>
                    <Input maxLength={300} value={f.keywords || ""} placeholder={p.keywords} onChange={(e) => set(p.key, "keywords", e.target.value)} data-testid={`seo-keywords-${p.key}`} />
                  </div>
                </div>
                <div>
                  <div className="text-[11px] uppercase tracking-wider text-ink/40 font-bold mb-1.5">Google preview</div>
                  <GooglePreview path={p.path} title={f.title || p.title} description={f.description || p.description} />
                </div>
              </div>
            </div>
          );
        })}
      </div>

      <Button onClick={save} disabled={saving} data-testid="seo-save-btn-bottom">{saving ? "Saving…" : "Save all pages"}</Button>
    </div>
  );
}
