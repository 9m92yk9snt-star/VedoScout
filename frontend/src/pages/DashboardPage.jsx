import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import Navigation from "@/components/Navigation";
import api from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { Plus, Lock, CheckCircle2, Film, Loader2 } from "lucide-react";

export default function DashboardPage() {
  const { user } = useAuth();
  const [reports, setReports] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.get("/reports/mine")
      .then(({ data }) => setReports(data))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="min-h-screen bg-deepnavy text-ink">
      <Navigation />
      <div className="pt-28 pb-16 px-6">
        <div className="max-w-7xl mx-auto">
          <div className="flex flex-col md:flex-row md:items-end md:justify-between gap-6">
            <div>
              <span className="text-volt text-xs uppercase tracking-[0.25em] font-bold">Your dashboard</span>
              <h1 className="mt-3 font-barlow font-black uppercase text-4xl md:text-5xl tracking-tighter leading-[0.95]">
                Welcome, {user?.full_name?.split(" ")[0] || "Player"}
              </h1>
              <p className="mt-2 text-ink/65 text-sm">Manage your uploads, previews and premium reports.</p>
            </div>
            <Link
              to="/upload"
              data-testid="dashboard-upload-btn"
              className="bg-volt hover:bg-forest-pop text-white font-barlow font-black uppercase tracking-widest text-sm px-6 py-3 transition-colors flex items-center gap-2 self-start md:self-end"
            >
              <Plus className="w-4 h-4" />
              New upload
            </Link>
          </div>

          <div className="mt-10">
            {loading ? (
              <div className="text-center py-16">
                <Loader2 className="w-6 h-6 animate-spin text-volt mx-auto" />
              </div>
            ) : reports.length === 0 ? (
              <div className="border border-gray-border bg-surface p-12 text-center">
                <Film className="w-12 h-12 text-volt mx-auto mb-4" strokeWidth={1.5} />
                <h2 className="font-barlow font-black uppercase text-2xl">No uploads yet</h2>
                <p className="mt-2 text-ink/65 text-sm">Upload your first football video and receive an instant free scout preview.</p>
                <Link
                  to="/upload"
                  data-testid="dashboard-empty-upload-btn"
                  className="inline-flex mt-6 bg-volt hover:bg-forest-pop text-white font-barlow font-black uppercase tracking-widest text-sm px-6 py-3 transition-colors items-center gap-2"
                >
                  <Plus className="w-4 h-4" /> Upload video
                </Link>
              </div>
            ) : (
              <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-px bg-cream-soft/40 border border-gray-border">
                {reports.map((r) => {
                  const unlocked = r.is_paid || r.manually_unlocked;
                  return (
                    <Link
                      to={`/report/${r.id}`}
                      key={r.id}
                      data-testid={`dashboard-report-${r.id}`}
                      data-report-id={r.id}
                      className="group bg-surface hover:bg-deepnavy transition-colors flex flex-col overflow-hidden open-report-link"
                    >
                      {/* Thumbnail */}
                      <div className="relative aspect-video bg-deepnavy overflow-hidden">
                        {r.poster_url ? (
                          <img
                            src={`${process.env.REACT_APP_BACKEND_URL}${r.poster_url}`}
                            alt={r.player_details?.player_name}
                            className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500"
                          />
                        ) : (
                          <div className="w-full h-full flex items-center justify-center bg-gradient-to-br from-surface to-deepnavy">
                            <Film className="w-10 h-10 text-volt/40" strokeWidth={1.5} />
                          </div>
                        )}
                        <div className="absolute inset-0 bg-gradient-to-t from-deepnavy via-transparent to-transparent" />
                        <div className="absolute top-3 left-3 right-3 flex items-center justify-between">
                          <span className="text-[10px] uppercase tracking-[0.18em] font-bold text-ink/80 bg-cream-card/90 backdrop-blur px-2 py-1">
                            {new Date(r.created_at).toLocaleDateString()}
                          </span>
                          {unlocked ? (
                            <span className="flex items-center gap-1 bg-volt text-white text-[10px] uppercase tracking-widest font-black px-2 py-1">
                              <CheckCircle2 className="w-3 h-3" /> Premium
                            </span>
                          ) : (
                            <span className="flex items-center gap-1 bg-cream-card backdrop-blur border border-gray-border text-ink/80 text-[10px] uppercase tracking-widest font-bold px-2 py-1">
                              <Lock className="w-3 h-3" /> Preview
                            </span>
                          )}
                        </div>
                      </div>

                      {/* Body */}
                      <div className="p-5 flex-1 flex flex-col">
                        <h3 className="font-barlow font-black uppercase text-xl text-ink group-hover:text-volt transition-colors leading-tight">
                          {r.player_details?.player_name}
                        </h3>
                        <p className="mt-1 text-sm text-ink/65">
                          {r.player_details?.position} · age {r.player_details?.age}
                        </p>
                        <div className="mt-auto pt-4 flex items-center justify-between">
                          <span className="text-[10px] uppercase tracking-widest text-ink/50 font-bold">{r.player_details?.video_type}</span>
                          <span className="text-volt text-[10px] uppercase tracking-widest font-bold">View →</span>
                        </div>
                      </div>
                    </Link>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
