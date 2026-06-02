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
    <div className="min-h-screen bg-deepnavy text-white">
      <Navigation />
      <div className="pt-28 pb-16 px-6">
        <div className="max-w-7xl mx-auto">
          <div className="flex flex-col md:flex-row md:items-end md:justify-between gap-6">
            <div>
              <span className="text-volt text-xs uppercase tracking-[0.25em] font-bold">Your dashboard</span>
              <h1 className="mt-3 font-barlow font-black uppercase text-4xl md:text-5xl tracking-tighter leading-[0.95]">
                Welcome, {user?.full_name?.split(" ")[0] || "Player"}
              </h1>
              <p className="mt-2 text-white/60 text-sm">Manage your uploads, previews and premium reports.</p>
            </div>
            <Link
              to="/upload"
              data-testid="dashboard-upload-btn"
              className="bg-volt hover:bg-white text-deepnavy font-barlow font-black uppercase tracking-widest text-sm px-6 py-3 transition-colors flex items-center gap-2 self-start md:self-end"
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
              <div className="border border-white/10 bg-surface p-12 text-center">
                <Film className="w-12 h-12 text-volt mx-auto mb-4" strokeWidth={1.5} />
                <h2 className="font-barlow font-black uppercase text-2xl">No uploads yet</h2>
                <p className="mt-2 text-white/60 text-sm">Upload your first football video and receive an AI-powered free preview.</p>
                <Link
                  to="/upload"
                  data-testid="dashboard-empty-upload-btn"
                  className="inline-flex mt-6 bg-volt hover:bg-white text-deepnavy font-barlow font-black uppercase tracking-widest text-sm px-6 py-3 transition-colors items-center gap-2"
                >
                  <Plus className="w-4 h-4" /> Upload video
                </Link>
              </div>
            ) : (
              <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-px bg-white/10 border border-white/10">
                {reports.map((r) => {
                  const unlocked = r.is_paid || r.manually_unlocked;
                  return (
                    <Link
                      to={`/report/${r.id}`}
                      key={r.id}
                      data-testid={`dashboard-report-${r.id}`}
                      className="group bg-surface p-6 hover:bg-deepnavy transition-colors flex flex-col"
                    >
                      <div className="flex items-center justify-between">
                        <span className="text-xs uppercase tracking-[0.2em] font-bold text-white/40">
                          {new Date(r.created_at).toLocaleDateString()}
                        </span>
                        {unlocked ? (
                          <span className="flex items-center gap-1.5 text-volt text-xs uppercase tracking-widest font-bold">
                            <CheckCircle2 className="w-3.5 h-3.5" /> Premium
                          </span>
                        ) : (
                          <span className="flex items-center gap-1.5 text-white/60 text-xs uppercase tracking-widest font-bold">
                            <Lock className="w-3.5 h-3.5" /> Preview
                          </span>
                        )}
                      </div>
                      <h3 className="mt-4 font-barlow font-black uppercase text-2xl text-white group-hover:text-volt transition-colors">
                        {r.player_details?.player_name}
                      </h3>
                      <p className="mt-1 text-sm text-white/60">
                        {r.player_details?.position} · age {r.player_details?.age}
                      </p>
                      <div className="mt-6 pt-6 border-t border-white/10 flex items-center justify-between">
                        <span className="text-xs uppercase tracking-widest text-white/40">{r.player_details?.video_type}</span>
                        <span className="text-volt text-xs uppercase tracking-widest font-bold">View →</span>
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
