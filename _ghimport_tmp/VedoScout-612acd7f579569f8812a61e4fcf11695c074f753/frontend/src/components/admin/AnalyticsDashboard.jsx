import { useEffect, useState } from "react";
import api from "@/lib/api";
import { Loader2, TrendingDown, MousePointerClick, Globe2, Smartphone, BookOpen, LogOut, RefreshCw } from "lucide-react";
import { ResponsiveContainer, AreaChart, Area, XAxis, YAxis, Tooltip, CartesianGrid, Legend } from "recharts";

const RANGES = [7, 14, 30, 90];

const Card = ({ title, icon: Icon, children, testid }) => (
  <div className="bg-white border border-ink/10 rounded-xl p-4" data-testid={testid}>
    <div className="flex items-center gap-2 text-[11px] font-extrabold tracking-[0.14em] uppercase text-ink/65 mb-3">
      {Icon && <Icon className="w-3.5 h-3.5" />} {title}
    </div>
    {children}
  </div>
);

export const AnalyticsDashboard = () => {
  const [days, setDays] = useState(30);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = (d = days) => {
    setLoading(true);
    api.get(`/admin/analytics/overview?days=${d}`)
      .then(({ data }) => setData(data))
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  };
  useEffect(() => { load(days); }, [days]); // eslint-disable-line

  if (loading && !data) {
    return <div className="flex items-center gap-2 text-ink/55 text-sm py-10 justify-center"><Loader2 className="w-4 h-4 animate-spin" /> Loading analytics…</div>;
  }
  if (!data) return <div className="text-ink/55 text-sm py-10 text-center">Couldn't load analytics.</div>;

  const funnelMax = Math.max(1, ...data.funnel.map((f) => f.count));

  return (
    <div className="space-y-4" data-testid="analytics-dashboard">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <p className="text-[11.5px] text-ink/50">
          First-party · cookie-less · anonymous sessions · no IPs stored · admin pages excluded · auto-deleted after 180 days
        </p>
        <div className="flex items-center gap-1.5">
          {RANGES.map((r) => (
            <button key={r} onClick={() => setDays(r)} data-testid={`analytics-range-${r}`}
              className={`px-3 py-1.5 text-[11px] font-bold rounded-lg border ${days === r ? "bg-volt text-ink border-volt" : "border-ink/20 text-ink/65 hover:text-ink"}`}>
              {r}d
            </button>
          ))}
          <button onClick={() => load()} data-testid="analytics-refresh" className="px-2 py-1.5 rounded-lg border border-ink/20 text-ink/65 hover:text-ink">
            <RefreshCw className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* Daily chart */}
      <Card title={`Daily — last ${data.days} days`} testid="analytics-daily-chart">
        <div className="h-56">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={data.series} margin={{ top: 5, right: 10, left: -18, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(15,22,35,0.08)" />
              <XAxis dataKey="date" tick={{ fill: "rgba(15,22,35,0.5)", fontSize: 10 }} tickFormatter={(d) => d.slice(5)} />
              <YAxis tick={{ fill: "rgba(15,22,35,0.5)", fontSize: 10 }} allowDecimals={false} />
              <Tooltip contentStyle={{ background: "#0F1623", border: "1px solid rgba(255,255,255,0.15)", fontSize: 12 }} />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              <Area type="monotone" dataKey="visitors" name="Visitors" stroke="#CCFF00" fill="rgba(204,255,0,0.15)" strokeWidth={2} />
              <Area type="monotone" dataKey="signups" name="Signups" stroke="#4FC3F7" fill="rgba(79,195,247,0.12)" strokeWidth={2} />
              <Area type="monotone" dataKey="paid" name="Paid" stroke="#F48FB1" fill="rgba(244,143,177,0.12)" strokeWidth={2} />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </Card>

      {/* Funnel */}
      <Card title="Conversion funnel" icon={TrendingDown} testid="analytics-funnel">
        <div className="space-y-2">
          {data.funnel.map((f, i) => (
            <div key={f.step} className="flex items-center gap-3" data-testid={`funnel-step-${i}`}>
              <div className="w-36 shrink-0 text-[12px] text-ink/80 font-bold">{f.step}</div>
              <div className="flex-1 h-6 bg-ink/[0.06] rounded overflow-hidden relative">
                <div className="h-full bg-volt/70 rounded" style={{ width: `${Math.max(2, (f.count / funnelMax) * 100)}%` }} />
                <span className="absolute inset-y-0 left-2 flex items-center text-[11px] font-black text-ink">{f.count}</span>
              </div>
              <div className={`w-16 shrink-0 text-right text-[11px] font-bold ${f.pct_of_prev != null && f.pct_of_prev < 30 ? "text-red-400" : "text-ink/55"}`}>
                {f.pct_of_prev != null ? `${f.pct_of_prev}%` : "—"}
              </div>
            </div>
          ))}
        </div>
        <p className="text-[10.5px] text-ink/40 mt-2">% = share of the previous step. Signups/Paid counted from accounts & transactions; the rest from anonymous sessions.</p>
      </Card>

      <div className="grid md:grid-cols-2 gap-4">
        <Card title="Top pages" icon={Globe2} testid="analytics-top-pages">
          <table className="w-full text-[12px]">
            <thead><tr className="text-ink/45 text-left"><th className="pb-1.5">Path</th><th className="text-right">Views</th><th className="text-right">Avg time</th><th className="text-right">Scroll</th></tr></thead>
            <tbody>
              {data.top_pages.map((p) => (
                <tr key={p.path} className="border-t border-ink/10 text-ink/85">
                  <td className="py-1.5 pr-2 truncate max-w-[160px]">{p.path}</td>
                  <td className="text-right font-bold">{p.views}</td>
                  <td className="text-right text-ink/60">{p.avg_seconds}s</td>
                  <td className="text-right text-ink/60">{p.avg_scroll}%</td>
                </tr>
              ))}
              {!data.top_pages.length && <tr><td className="py-3 text-ink/45" colSpan={4}>No pageviews yet.</td></tr>}
            </tbody>
          </table>
        </Card>

        <Card title="Exit pages (where sessions end)" icon={LogOut} testid="analytics-exit-pages">
          <table className="w-full text-[12px]">
            <thead><tr className="text-ink/45 text-left"><th className="pb-1.5">Path</th><th className="text-right">Exits</th></tr></thead>
            <tbody>
              {data.exit_pages.map((p) => (
                <tr key={p.path} className="border-t border-ink/10 text-ink/85">
                  <td className="py-1.5 pr-2 truncate max-w-[220px]">{p.path}</td>
                  <td className="text-right font-bold">{p.exits}</td>
                </tr>
              ))}
              {!data.exit_pages.length && <tr><td className="py-3 text-ink/45" colSpan={2}>No data yet.</td></tr>}
            </tbody>
          </table>
        </Card>

        <Card title="Top CTA clicks" icon={MousePointerClick} testid="analytics-top-clicks">
          <table className="w-full text-[12px]">
            <tbody>
              {data.top_clicks.map((c) => (
                <tr key={c.name} className="border-t border-ink/10 text-ink/85">
                  <td className="py-1.5 pr-2 truncate max-w-[220px] font-mono text-[11px]">{c.name}</td>
                  <td className="text-right font-bold">{c.clicks}</td>
                </tr>
              ))}
              {!data.top_clicks.length && <tr><td className="py-3 text-ink/45">No clicks tracked yet.</td></tr>}
            </tbody>
          </table>
        </Card>

        <Card title="Campaigns (UTM) & devices" icon={Smartphone} testid="analytics-campaigns">
          <table className="w-full text-[12px] mb-3">
            <thead><tr className="text-ink/45 text-left"><th className="pb-1.5">Source</th><th>Campaign</th><th className="text-right">Sessions</th></tr></thead>
            <tbody>
              {data.campaigns.map((c, i) => (
                <tr key={i} className="border-t border-ink/10 text-ink/85">
                  <td className="py-1.5">{c.source}</td><td>{c.campaign}</td>
                  <td className="text-right font-bold">{c.sessions}</td>
                </tr>
              ))}
              {!data.campaigns.length && <tr><td className="py-3 text-ink/45" colSpan={3}>No UTM traffic yet — add ?utm_source=facebook&utm_campaign=... to your ad links.</td></tr>}
            </tbody>
          </table>
          <div className="flex gap-2 flex-wrap">
            {data.devices.map((d) => (
              <span key={d.device} className="px-2.5 py-1 rounded-full bg-ink/[0.07] text-[11px] text-ink/75">
                {d.device}: <b className="text-ink">{d.sessions}</b>
              </span>
            ))}
          </div>
        </Card>
      </div>

      <Card title="Blog readership" icon={BookOpen} testid="analytics-blog">
        {data.blog_pages.length ? (
          <table className="w-full text-[12px]">
            <tbody>
              {data.blog_pages.map((p) => (
                <tr key={p.path} className="border-t border-ink/10 text-ink/85">
                  <td className="py-1.5 pr-2 truncate max-w-[300px]">{p.path}</td>
                  <td className="text-right font-bold">{p.views} views</td>
                  <td className="text-right text-ink/60">{p.avg_seconds}s avg</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : <p className="text-ink/45 text-[12px]">No blog visits in this period.</p>}
        <p className="text-[10.5px] text-ink/40 mt-2">Landing page: avg scroll {data.landing_avg_scroll}% · avg time {data.landing_avg_seconds}s</p>
      </Card>
    </div>
  );
};

export default AnalyticsDashboard;
