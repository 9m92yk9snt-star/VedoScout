import React, { useEffect, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import {
  Search, MapPin, User, Ruler, Star, ChevronDown, Loader2, Eye, EyeOff,
  Filter, ArrowRight, Lock, Users, Sparkles, X,
} from "lucide-react";
import Navigation from "@/components/Navigation";
import api from "@/lib/api";

const POSITIONS = ["", "GK", "CB", "FB", "DM", "CM", "CAM", "W", "ST"];
const FEET = ["", "left", "right", "both"];

const abs = (path) =>
  path && path.startsWith("http") ? path : `${process.env.REACT_APP_BACKEND_URL}${path}`;

export default function PlayersDatabasePage() {
  const navigate = useNavigate();
  const location = useLocation();

  const [access, setAccess] = useState(null);
  const [accessLoading, setAccessLoading] = useState(true);
  const [results, setResults] = useState(null);
  const [searching, setSearching] = useState(false);
  const [selectedPlayerId, setSelectedPlayerId] = useState(null);

  // Filters
  const [filters, setFilters] = useState({
    q: "",
    position: "",
    country: "",
    preferred_foot: "",
    min_age: "",
    max_age: "",
    min_overall: "",
  });

  // Handle Stripe redirect back after scout subscription
  useEffect(() => {
    const params = new URLSearchParams(location.search);
    const sessionId = params.get("scout_session");
    if (!sessionId) return;
    params.delete("scout_session");
    const newSearch = params.toString();
    navigate({ pathname: location.pathname, search: newSearch ? `?${newSearch}` : "" }, { replace: true });
    const poll = async (attempts = 0) => {
      if (attempts > 6) return;
      try {
        const { data } = await api.get(`/scout-access/status/${sessionId}`);
        if (data.payment_status === "paid") {
          toast.success("Scout access active — welcome to the database.", { duration: 8000 });
          fetchAccess();
          return;
        }
        setTimeout(() => poll(attempts + 1), 1800);
      } catch { /* keep polling */ }
    };
    poll();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const fetchAccess = async () => {
    setAccessLoading(true);
    try {
      const { data } = await api.get("/scout-access/me");
      setAccess(data);
    } catch {
      setAccess({ active: false });
    } finally {
      setAccessLoading(false);
    }
  };

  useEffect(() => { fetchAccess(); }, []);

  useEffect(() => {
    if (access?.active) runSearch(filters);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [access?.active]);

  const runSearch = async (f) => {
    setSearching(true);
    try {
      const params = {};
      Object.entries(f).forEach(([k, v]) => {
        if (v !== "" && v !== null && v !== undefined) params[k] = v;
      });
      const { data } = await api.get("/players-database/search", { params });
      setResults(data);
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Search failed");
    } finally {
      setSearching(false);
    }
  };

  const handleFilterChange = (name, value) => {
    setFilters((f) => ({ ...f, [name]: value }));
  };

  const handleFilterSubmit = (e) => {
    e?.preventDefault();
    runSearch(filters);
  };

  const clearFilters = () => {
    const empty = {
      q: "", position: "", country: "", preferred_foot: "",
      min_age: "", max_age: "", min_overall: "",
    };
    setFilters(empty);
    runSearch(empty);
  };

  // -------- Access gating --------
  if (accessLoading) {
    return (
      <div className="min-h-screen bg-cream-base">
        <Navigation />
        <div className="flex items-center justify-center py-32">
          <Loader2 className="w-8 h-8 text-forest animate-spin" />
        </div>
      </div>
    );
  }

  if (!access?.active) {
    return (
      <div data-testid="players-database-paywall" className="min-h-screen bg-cream-base text-ink">
        <Navigation />
        <div className="max-w-2xl mx-auto text-center px-6 py-24">
          <Lock className="w-12 h-12 text-forest mx-auto mb-6" strokeWidth={1.5} />
          <div className="text-[11px] uppercase tracking-[0.28em] font-black text-forest mb-3">
            Scout access required
          </div>
          <h1 className="font-barlow font-black uppercase tracking-tighter text-3xl md:text-5xl leading-[0.95]">
            Only paid scouts, agents<br /><span className="text-forest">and clubs enter here.</span>
          </h1>
          <p className="mt-6 text-ink/70">
            The ScoutMePlay player database is a paid-access index. Subscribe to search discoverable
            players by position, age, foot and score — and message them directly.
          </p>
          <Link
            to="/scouts"
            data-testid="players-database-paywall-cta"
            className="mt-8 inline-flex items-center gap-2 bg-forest hover:bg-forest-pop text-white font-barlow font-black uppercase tracking-widest text-sm px-8 py-4 transition-colors"
          >
            See pricing <ArrowRight className="w-4 h-4" />
          </Link>
        </div>
      </div>
    );
  }

  // -------- Database UI --------
  const revealsRemaining = access?.reveals_remaining;
  const revealsLimit = access?.monthly_reveals;
  const showRevealBar = revealsLimit !== null;

  return (
    <div data-testid="players-database" className="min-h-screen bg-cream-base text-ink">
      <Navigation />

      {/* Header */}
      <section className="border-b border-ink/10 py-8 md:py-12">
        <div className="max-w-6xl mx-auto px-6 md:px-10">
          <div className="flex items-start justify-between gap-4 flex-wrap">
            <div>
              <div className="text-[10px] uppercase tracking-[0.28em] font-black text-forest mb-1">
                Scout database · {access.tier?.replace("_", " ")}
              </div>
              <h1 className="font-barlow font-black uppercase tracking-tighter text-3xl md:text-5xl leading-[0.95]">
                Player search
              </h1>
              <p className="mt-2 text-ink/60 text-sm md:text-base">
                {results ? `${results.total} discoverable player${results.total === 1 ? "" : "s"} match.` : "Searching…"}
              </p>
            </div>
            {showRevealBar && (
              <div className="border border-forest/30 bg-forest/5 px-4 py-3 flex items-center gap-3">
                <Sparkles className="w-4 h-4 text-forest" />
                <div>
                  <div className="text-[10px] uppercase tracking-[0.18em] font-black text-forest">
                    Contact reveals
                  </div>
                  <div className="text-lg font-barlow font-black leading-none mt-1">
                    {revealsRemaining} <span className="text-ink/40 text-sm">/ {revealsLimit} this month</span>
                  </div>
                </div>
              </div>
            )}
            {!showRevealBar && (
              <div className="border border-forest/30 bg-forest/5 px-4 py-3">
                <div className="text-[10px] uppercase tracking-[0.18em] font-black text-forest">
                  Contact reveals
                </div>
                <div className="text-lg font-barlow font-black leading-none mt-1">
                  Unlimited
                </div>
              </div>
            )}
          </div>
        </div>
      </section>

      {/* Filters */}
      <form onSubmit={handleFilterSubmit} className="border-b border-ink/10 bg-cream-card">
        <div className="max-w-6xl mx-auto px-6 md:px-10 py-5">
          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-3">
            <div className="col-span-2 md:col-span-4 lg:col-span-2 relative">
              <Search className="absolute top-3 left-3 w-4 h-4 text-ink/40" />
              <input
                type="text"
                data-testid="pdb-search-q"
                placeholder="Search name, club, bio…"
                value={filters.q}
                onChange={(e) => handleFilterChange("q", e.target.value)}
                className="w-full pl-9 pr-3 py-2.5 border border-ink/15 bg-white text-sm focus:border-forest focus:outline-none"
              />
            </div>
            <FilterSelect
              testid="pdb-filter-position"
              label="Position"
              value={filters.position}
              onChange={(v) => handleFilterChange("position", v)}
              options={POSITIONS.map((p) => ({ value: p, label: p || "Any" }))}
            />
            <FilterSelect
              testid="pdb-filter-foot"
              label="Foot"
              value={filters.preferred_foot}
              onChange={(v) => handleFilterChange("preferred_foot", v)}
              options={FEET.map((f) => ({ value: f, label: f ? f.charAt(0).toUpperCase() + f.slice(1) : "Any" }))}
            />
            <FilterInput
              testid="pdb-filter-country"
              label="Country"
              placeholder="Denmark"
              value={filters.country}
              onChange={(v) => handleFilterChange("country", v)}
            />
            <FilterInput
              testid="pdb-filter-min-age"
              label="Min age"
              type="number"
              placeholder="12"
              value={filters.min_age}
              onChange={(v) => handleFilterChange("min_age", v)}
            />
            <FilterInput
              testid="pdb-filter-max-age"
              label="Max age"
              type="number"
              placeholder="18"
              value={filters.max_age}
              onChange={(v) => handleFilterChange("max_age", v)}
            />
          </div>
          <div className="flex items-center justify-between mt-4">
            <button
              type="button"
              onClick={clearFilters}
              className="text-[11px] uppercase tracking-widest font-black text-ink/50 hover:text-ink transition-colors"
            >
              Clear filters
            </button>
            <button
              type="submit"
              disabled={searching}
              data-testid="pdb-apply-filters"
              className="inline-flex items-center gap-2 bg-forest hover:bg-forest-pop text-white font-barlow font-black uppercase tracking-widest text-xs px-5 py-2.5 transition-colors disabled:opacity-50"
            >
              {searching ? <Loader2 className="w-4 h-4 animate-spin" /> : <Filter className="w-4 h-4" />}
              Apply
            </button>
          </div>
        </div>
      </form>

      {/* Results grid */}
      <section className="py-8 md:py-12">
        <div className="max-w-6xl mx-auto px-6 md:px-10">
          {searching && (
            <div className="flex items-center justify-center py-16">
              <Loader2 className="w-6 h-6 text-forest animate-spin" />
            </div>
          )}
          {!searching && results && results.results.length === 0 && (
            <div className="text-center py-20">
              <Users className="w-12 h-12 text-ink/20 mx-auto mb-4" strokeWidth={1.5} />
              <h3 className="font-barlow font-black uppercase text-xl">No players match these filters.</h3>
              <p className="mt-2 text-ink/60 text-sm">Loosen the filters or clear them to see everyone.</p>
            </div>
          )}
          {!searching && results && results.results.length > 0 && (
            <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-px bg-ink/10 border border-ink/10">
              {results.results.map((p) => (
                <button
                  key={p.id}
                  type="button"
                  onClick={() => setSelectedPlayerId(p.id)}
                  data-testid={`pdb-player-card-${p.id}`}
                  className="group bg-cream-card hover:bg-white transition-colors flex flex-col text-left overflow-hidden"
                >
                  <div className="relative aspect-[4/3] bg-ink overflow-hidden">
                    {p.poster_url ? (
                      <img
                        src={abs(p.poster_url)}
                        alt=""
                        className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500"
                      />
                    ) : (
                      <div className="w-full h-full flex items-center justify-center bg-gradient-to-br from-ink to-forest/40">
                        <User className="w-12 h-12 text-white/30" strokeWidth={1} />
                      </div>
                    )}
                    <div className="absolute inset-0 bg-gradient-to-t from-ink/85 via-transparent to-transparent" />
                    <div className="absolute bottom-3 left-3 right-3 flex items-end justify-between gap-2">
                      <div className="flex items-center gap-2.5">
                        {p.avatar_url ? (
                          <img
                            src={abs(p.avatar_url)}
                            alt=""
                            className="w-10 h-10 border-2 border-volt object-cover"
                          />
                        ) : (
                          <div className="w-10 h-10 border-2 border-volt bg-forest flex items-center justify-center text-white font-barlow font-black">
                            {(p.display_name || "?").charAt(0).toUpperCase()}
                          </div>
                        )}
                        <div>
                          <div className="font-barlow font-black text-white uppercase text-lg leading-none">
                            {p.display_name}
                          </div>
                          <div className="text-white/70 text-[11px] uppercase tracking-widest mt-1">
                            {[p.position, p.age ? `${p.age}y` : null].filter(Boolean).join(" · ")}
                          </div>
                        </div>
                      </div>
                      {p.highest_overall != null && (
                        <div className="bg-volt text-ink font-barlow font-black text-lg leading-none px-2 py-1">
                          {p.highest_overall}
                        </div>
                      )}
                    </div>
                  </div>
                  <div className="p-4 space-y-1.5">
                    <div className="flex items-center gap-1.5 text-[12px] text-ink/70">
                      {p.country && (<><MapPin className="w-3.5 h-3.5" />{p.country}</>)}
                      {p.country && p.club ? <span className="text-ink/30">·</span> : null}
                      {p.club && <span>{p.club}</span>}
                    </div>
                    <div className="flex items-center gap-3 text-[11px] text-ink/50 uppercase tracking-widest font-bold">
                      {p.preferred_foot && <span>{p.preferred_foot} foot</span>}
                      {p.height_cm && <span>{p.height_cm} cm</span>}
                    </div>
                    <div className="flex items-center justify-between pt-2 border-t border-ink/10 mt-2">
                      <span className="text-[11px] uppercase tracking-widest font-black text-forest">
                        {p.reports_count} report{p.reports_count === 1 ? "" : "s"}
                      </span>
                      {p.contact_revealed ? (
                        <span className="inline-flex items-center gap-1 text-[11px] text-forest-pop font-black uppercase tracking-widest">
                          <Eye className="w-3 h-3" /> Revealed
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 text-[11px] text-ink/40 font-black uppercase tracking-widest">
                          <EyeOff className="w-3 h-3" /> Contact locked
                        </span>
                      )}
                    </div>
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>
      </section>

      {/* Player detail modal */}
      {selectedPlayerId && (
        <PlayerDetailDrawer
          playerId={selectedPlayerId}
          onClose={() => { setSelectedPlayerId(null); fetchAccess(); runSearch(filters); }}
        />
      )}
    </div>
  );
}

function FilterSelect({ label, value, onChange, options, testid }) {
  return (
    <label className="block">
      <div className="text-[9px] uppercase tracking-[0.2em] font-black text-forest mb-1">{label}</div>
      <div className="relative">
        <select
          value={value}
          onChange={(e) => onChange(e.target.value)}
          data-testid={testid}
          className="w-full appearance-none border border-ink/15 bg-white text-sm py-2.5 pl-3 pr-8 focus:border-forest focus:outline-none"
        >
          {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
        <ChevronDown className="pointer-events-none absolute right-2 top-3 w-4 h-4 text-ink/40" />
      </div>
    </label>
  );
}

function FilterInput({ label, type = "text", value, onChange, placeholder, testid }) {
  return (
    <label className="block">
      <div className="text-[9px] uppercase tracking-[0.2em] font-black text-forest mb-1">{label}</div>
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        data-testid={testid}
        className="w-full border border-ink/15 bg-white text-sm px-3 py-2.5 focus:border-forest focus:outline-none"
      />
    </label>
  );
}

function PlayerDetailDrawer({ playerId, onClose }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [revealing, setRevealing] = useState(false);

  useEffect(() => {
    setLoading(true);
    api.get(`/players-database/player/${playerId}`)
      .then(({ data }) => setData(data))
      .catch(() => toast.error("Could not load player"))
      .finally(() => setLoading(false));
  }, [playerId]);

  const doReveal = async () => {
    setRevealing(true);
    try {
      const { data: r } = await api.post(`/players-database/reveal/${playerId}`);
      setData((d) => ({
        ...d,
        player: { ...d.player, contact_revealed: true, contact_email: r.contact_email },
      }));
      toast.success(r.already_revealed ? "Already revealed." : "Contact revealed. The player has been notified.");
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Could not reveal");
    } finally {
      setRevealing(false);
    }
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      className="fixed inset-0 z-50 flex justify-end bg-ink/50 backdrop-blur-sm"
      onClick={onClose}
      data-testid="pdb-player-drawer"
    >
      <div
        className="w-full max-w-lg bg-cream-base overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="sticky top-0 z-10 bg-cream-base/95 backdrop-blur border-b border-ink/10 px-6 py-4 flex items-center justify-between">
          <div className="text-[10px] uppercase tracking-[0.24em] font-black text-forest">
            Scout view
          </div>
          <button
            type="button"
            onClick={onClose}
            data-testid="pdb-drawer-close"
            className="text-ink/50 hover:text-ink transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {loading && (
          <div className="flex items-center justify-center py-20">
            <Loader2 className="w-6 h-6 text-forest animate-spin" />
          </div>
        )}

        {data && (
          <div className="p-6">
            {/* Player identity */}
            <div className="flex items-start gap-4 mb-6">
              {data.player.avatar_url ? (
                <img
                  src={abs(data.player.avatar_url)}
                  alt=""
                  className="w-20 h-20 border-2 border-forest object-cover"
                />
              ) : (
                <div className="w-20 h-20 border-2 border-forest bg-forest/10 flex items-center justify-center font-barlow font-black text-3xl text-forest">
                  {(data.player.display_name || "?").charAt(0).toUpperCase()}
                </div>
              )}
              <div className="flex-1">
                <h2 className="font-barlow font-black uppercase text-2xl leading-tight tracking-tight">
                  {data.player.display_name}
                </h2>
                <div className="mt-1 text-[11px] uppercase tracking-widest text-ink/60 font-bold">
                  {[data.player.position, data.player.age ? `Age ${data.player.age}` : null, data.player.preferred_foot && `${data.player.preferred_foot} foot`].filter(Boolean).join(" · ")}
                </div>
                {data.player.highest_overall != null && (
                  <div className="mt-3 inline-flex items-center gap-1.5 bg-volt text-ink px-2.5 py-1 font-barlow font-black">
                    <Star className="w-3.5 h-3.5" />
                    <span className="text-sm">Overall {data.player.highest_overall}</span>
                  </div>
                )}
              </div>
            </div>

            {/* Meta grid */}
            <div className="grid grid-cols-2 gap-3 mb-6">
              <MetaTile icon={MapPin} label="Country" value={data.player.country} />
              <MetaTile icon={Users} label="Current club" value={data.player.club} />
              <MetaTile icon={Ruler} label="Height" value={data.player.height_cm ? `${data.player.height_cm} cm` : null} />
              <MetaTile icon={Star} label="Reports" value={`${data.player.reports_count}`} />
            </div>

            {data.player.bio && (
              <div className="mb-6 border-l-2 border-forest pl-4">
                <div className="text-[10px] uppercase tracking-[0.18em] font-black text-forest mb-1">Bio</div>
                <p className="text-sm text-ink/80 leading-relaxed">{data.player.bio}</p>
              </div>
            )}

            {/* Contact block */}
            <div className={`border-2 p-4 mb-6 ${
              data.player.contact_revealed
                ? "border-forest bg-forest/5"
                : "border-ink/15 bg-cream-card"
            }`}>
              <div className="flex items-center gap-2 mb-2">
                {data.player.contact_revealed
                  ? <Eye className="w-4 h-4 text-forest-pop" />
                  : <Lock className="w-4 h-4 text-ink/40" />}
                <div className="text-[11px] uppercase tracking-[0.18em] font-black">
                  {data.player.contact_revealed ? "Contact revealed" : "Contact info"}
                </div>
              </div>
              {data.player.contact_revealed ? (
                <a
                  href={`mailto:${data.player.contact_email}`}
                  data-testid="pdb-contact-email"
                  className="text-forest font-mono text-sm break-all hover:underline"
                >
                  {data.player.contact_email}
                </a>
              ) : (
                <>
                  <p className="text-sm text-ink/70 mb-3">
                    Reveal contact info to email this player directly. Uses one reveal from your monthly quota.
                    The player is notified so they can respond quickly.
                  </p>
                  <button
                    type="button"
                    onClick={doReveal}
                    disabled={revealing}
                    data-testid="pdb-reveal-btn"
                    className="w-full inline-flex items-center justify-center gap-2 bg-forest hover:bg-forest-pop text-white font-barlow font-black uppercase tracking-widest text-sm py-3 transition-colors disabled:opacity-60"
                  >
                    {revealing ? <Loader2 className="w-4 h-4 animate-spin" /> : <><Eye className="w-4 h-4" /> Reveal contact</>}
                  </button>
                </>
              )}
            </div>

            {/* Reports list */}
            {data.reports && data.reports.length > 0 && (
              <div>
                <div className="text-[10px] uppercase tracking-[0.18em] font-black text-forest mb-3">
                  Latest reports
                </div>
                <ul className="space-y-2">
                  {data.reports.map((r) => (
                    <li key={r.id} className="border border-ink/10 bg-cream-card p-3 flex items-center gap-3">
                      {r.poster_url ? (
                        <img src={abs(r.poster_url)} alt="" className="w-16 h-10 object-cover" />
                      ) : (
                        <div className="w-16 h-10 bg-ink/10" />
                      )}
                      <div className="flex-1 min-w-0">
                        <div className="text-sm font-bold truncate">
                          {r.player_details?.player_name || "Report"}
                        </div>
                        <div className="text-[11px] text-ink/50 uppercase tracking-widest">
                          {r.player_details?.position} · {new Date(r.created_at).toLocaleDateString()}
                        </div>
                      </div>
                      {r.preview_overall != null && (
                        <div className="text-forest font-barlow font-black text-lg">
                          {Math.round(r.preview_overall)}
                        </div>
                      )}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function MetaTile({ icon: Icon, label, value }) {
  return (
    <div className="border border-ink/10 bg-cream-card p-3">
      <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-[0.16em] font-black text-forest">
        <Icon className="w-3 h-3" />
        {label}
      </div>
      <div className="mt-1 text-sm font-bold text-ink">
        {value || <span className="text-ink/30 font-normal">—</span>}
      </div>
    </div>
  );
}
