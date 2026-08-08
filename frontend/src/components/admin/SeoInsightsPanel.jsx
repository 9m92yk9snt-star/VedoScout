// SEO Insights — organic traffic (first-party analytics), article keyword performance, LLM keyword ideas.
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Search, TrendingUp, Lightbulb, Loader2, ExternalLink } from "lucide-react";
import api from "@/lib/api";

const fmtDay = (d) => (d || "").slice(5);

export default function SeoInsightsPanel() {
  const [data, setData] = useState(null);
  const [suggesting, setSuggesting] = useState(false);

  const load = () => api.get("/admin/seo/insights?days=30").then(({ data }) => setData(data)).catch(() => {});
  useEffect(() => { load(); }, []);

  const suggest = async () => {
    setSuggesting(true);
    try {
      const { data: r } = await api.post("/admin/seo/keyword-suggestions");
      if (r.error) toast.error(r.error);
      else toast.success("Fresh keyword ideas ready");
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not generate suggestions");
    } finally {
      setSuggesting(false);
    }
  };

  const maxDaily = Math.max(1, ...(data?.daily || []).map((d) => d.sessions));

  return (
    <div data-testid="seo-insights-panel" className="bg-surface border border-gray-border p-6 md:p-8">
      <div className="flex items-center gap-2 mb-1">
        <Search className="w-4 h-4 text-volt" />
        <span className="text-volt text-[10px] uppercase tracking-[0.22em] font-bold">Organic search</span>
      </div>
      <h2 className="font-barlow font-black uppercase text-2xl text-ink">SEO performance</h2>
      <p className="mt-2 text-ink/65 text-sm max-w-2xl">
        Measured by our own first-party analytics (visits arriving from Google, Bing &amp; other search engines) —
        no Google account needed. For query-level data ("which exact search phrases"), Google Search Console can be
        connected later.
      </p>

      {/* Stats */}
      <div className="mt-6 grid grid-cols-2 md:grid-cols-3 gap-4">
        <div className="border border-gray-border p-4" data-testid="seo-organic-sessions">
          <div className="text-[10px] uppercase tracking-[0.22em] font-bold text-ink/45">Organic visits · 30d</div>
          <div className="mt-1 font-barlow font-black text-3xl text-ink">{data ? data.organic_sessions : "—"}</div>
        </div>
        <div className="border border-gray-border p-4" data-testid="seo-organic-share">
          <div className="text-[10px] uppercase tracking-[0.22em] font-bold text-ink/45">Share of all visits</div>
          <div className="mt-1 font-barlow font-black text-3xl text-ink">{data ? `${data.organic_share_pct}%` : "—"}</div>
        </div>
        <div className="border border-gray-border p-4 col-span-2 md:col-span-1" data-testid="seo-daily-chart">
          <div className="text-[10px] uppercase tracking-[0.22em] font-bold text-ink/45 mb-2">Daily organic</div>
          <div className="flex items-end gap-[3px] h-12">
            {(data?.daily || []).length
              ? data.daily.map((d) => (
                  <div key={d.day} title={`${fmtDay(d.day)}: ${d.sessions}`} className="flex-1 bg-forest/70 min-w-[3px]"
                    style={{ height: `${Math.max(8, (d.sessions / maxDaily) * 100)}%` }} />
                ))
              : <span className="text-[11px] text-ink/40">No organic visits recorded yet — data grows from the moment the site is live</span>}
          </div>
        </div>
      </div>

      {/* Top landing pages */}
      {(data?.top_landing || []).length > 0 && (
        <div className="mt-6">
          <div className="text-[11px] uppercase tracking-[0.2em] font-bold text-ink/55 mb-2 flex items-center gap-1.5">
            <TrendingUp className="w-3.5 h-3.5" /> Top pages Google sends visitors to
          </div>
          <div className="flex flex-wrap gap-2">
            {data.top_landing.map((l) => (
              <span key={l.path} className="px-2.5 py-1 bg-forest/8 text-forest text-[11.5px] font-bold">
                {l.path} · {l.sessions}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Articles */}
      <div className="mt-7">
        <div className="text-[11px] uppercase tracking-[0.2em] font-bold text-ink/55 mb-2">Article keywords &amp; views</div>
        <div className="overflow-x-auto">
          <table className="w-full text-[12px]">
            <thead>
              <tr className="text-ink/45 text-left border-b border-gray-border">
                <th className="py-2 pr-2">Article</th><th className="pr-2">Keywords</th><th>Views</th>
              </tr>
            </thead>
            <tbody>
              {(data?.articles || []).map((a) => (
                <tr key={a.slug} className="border-b border-gray-border/60 text-ink/80" data-testid={`seo-article-${a.slug}`}>
                  <td className="py-2 pr-3 max-w-[260px]">
                    <a href={`/blog/${a.slug}`} target="_blank" rel="noreferrer" className="font-bold text-ink hover:text-forest inline-flex items-center gap-1">
                      <span className="truncate">{a.title}</span> <ExternalLink className="w-3 h-3 shrink-0" />
                    </a>
                  </td>
                  <td className="pr-3">
                    <div className="flex flex-wrap gap-1">
                      {(a.keywords || []).slice(0, 4).map((k) => (
                        <span key={k} className="px-1.5 py-0.5 bg-[#12402A0F] text-[#1F4F2F] text-[10.5px] font-semibold">{k}</span>
                      ))}
                    </div>
                  </td>
                  <td className="font-barlow font-black text-[14px]">{a.views}</td>
                </tr>
              ))}
              {data && !data.articles.length && (
                <tr><td colSpan={3} className="py-4 text-ink/45">No published articles yet.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Keyword suggestions */}
      <div className="mt-7 pt-5 border-t border-gray-border">
        <div className="flex items-center justify-between flex-wrap gap-3 mb-3">
          <div className="text-[11px] uppercase tracking-[0.2em] font-bold text-ink/55 flex items-center gap-1.5">
            <Lightbulb className="w-3.5 h-3.5" /> Keyword ideas for new articles
            {data?.suggestions_generated_at && (
              <span className="normal-case tracking-normal font-normal text-ink/40">· {data.suggestions_generated_at.slice(0, 10)}</span>
            )}
          </div>
          <button
            type="button"
            onClick={suggest}
            disabled={suggesting}
            data-testid="seo-suggest-keywords-btn"
            className="bg-forest hover:bg-forest-pop text-cream-card font-barlow font-black uppercase tracking-widest text-[11px] px-4 py-2 flex items-center gap-2 transition-colors disabled:opacity-50"
          >
            {suggesting && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
            {suggesting ? "Thinking…" : "Suggest new keywords"}
          </button>
        </div>
        {(data?.suggestions || []).length ? (
          <div className="space-y-2" data-testid="seo-suggestions-list">
            {data.suggestions.map((s, i) => (
              <div key={i} className="border border-gray-border p-3">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="font-bold text-ink text-[13px]">{s.keyword}</span>
                  <span className="px-1.5 py-0.5 bg-forest/10 text-forest text-[10px] font-black uppercase">{s.audience}</span>
                  <span className={`px-1.5 py-0.5 text-[10px] font-black uppercase ${s.interest === "high" ? "bg-[#CCFF00] text-[#12211A]" : "bg-ink/8 text-ink/60"}`}>
                    {s.interest} interest*
                  </span>
                </div>
                <div className="mt-1 text-[12px] text-ink/65">{s.intent}</div>
                <div className="mt-0.5 text-[12px] text-forest font-semibold">Idea: {s.article_idea}</div>
              </div>
            ))}
            <p className="text-[10.5px] text-ink/40">*Interest levels are editorial estimates — not measured search-volume data.</p>
          </div>
        ) : (
          <p className="text-[12px] text-ink/45">No suggestions yet — click the button and get 8 article-ready keyword ideas based on what you already cover.</p>
        )}
      </div>
    </div>
  );
}
