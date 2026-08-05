// CarouselStudioAdmin — generate Instagram carousel slides in ScoutMePlay style.
import React, { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { Images, Loader2, Sparkles, Trash2, Download, Copy } from "lucide-react";
import api from "@/lib/api";

const BACKEND = process.env.REACT_APP_BACKEND_URL;

export const CarouselStudioAdmin = () => {
  const [topic, setTopic] = useState("");
  const [commentWord, setCommentWord] = useState("GUIDE");
  const [slides, setSlides] = useState(7);
  const [busy, setBusy] = useState(false);
  const [jobs, setJobs] = useState([]);
  const pollRef = useRef(null);

  const load = async () => {
    try {
      const { data } = await api.get("/carousel/jobs");
      setJobs(data.items || []);
    } catch { /* noop */ }
  };

  useEffect(() => { load(); return () => clearInterval(pollRef.current); }, []);

  const generate = async () => {
    if (!topic.trim()) { toast.error("Type a topic first"); return; }
    setBusy(true);
    try {
      const { data } = await api.post("/carousel/generate", { topic: topic.trim(), slides, comment_word: commentWord.trim() || "GUIDE" });
      toast.info("Writing & designing your slides — takes ~1 minute…");
      const jobId = data.job_id;
      pollRef.current = setInterval(async () => {
        const r = await api.get("/carousel/jobs");
        setJobs(r.data.items || []);
        const job = (r.data.items || []).find((j) => j.id === jobId);
        if (!job || job.status === "running") return;
        clearInterval(pollRef.current);
        setBusy(false);
        if (job.status === "done") { toast.success("Carousel ready — download the slides below"); setTopic(""); }
        else toast.error("Generation failed: " + (job.error || "unknown"));
      }, 3000);
    } catch (e) {
      setBusy(false);
      toast.error("Could not start: " + (e?.response?.data?.detail || e.message));
    }
  };

  const remove = async (id) => {
    if (!window.confirm("Delete this carousel?")) return;
    await api.delete(`/carousel/jobs/${id}`);
    load();
  };

  const copyCaption = (caption) => {
    navigator.clipboard.writeText(caption || "").then(() => toast.success("Caption copied"));
  };

  return (
    <div className="border border-gray-border bg-surface p-5 md:p-6" data-testid="carousel-studio">
      <div className="flex items-center gap-2 mb-2">
        <Images className="w-5 h-5 text-forest" />
        <h3 className="font-barlow font-black uppercase text-xl tracking-tight">Carousel Studio</h3>
      </div>
      <p className="text-sm text-ink/60 mb-4">
        One click creates a full Instagram carousel — dark cinematic slides in the ScoutMePlay voice.
        Download the images and post them from your phone. The last slide asks readers to comment your keyword.
      </p>

      <div className="grid md:grid-cols-[1fr_140px_120px_auto] gap-2">
        <input
          data-testid="carousel-topic"
          value={topic}
          onChange={(e) => setTopic(e.target.value)}
          placeholder='Topic — e.g. "5 mistakes football parents make on match day"'
          className="px-3 py-2.5 bg-cream-soft/40 border border-gray-border focus:border-forest outline-none text-sm"
        />
        <input
          data-testid="carousel-comment-word"
          value={commentWord}
          onChange={(e) => setCommentWord(e.target.value.toUpperCase())}
          placeholder="Keyword"
          title='The word people comment (e.g. "GUIDE" or "5")'
          className="px-3 py-2.5 bg-cream-soft/40 border border-gray-border focus:border-forest outline-none text-sm font-bold"
        />
        <select
          data-testid="carousel-slides-count"
          value={slides}
          onChange={(e) => setSlides(parseInt(e.target.value, 10))}
          className="px-3 py-2.5 bg-cream-soft/40 border border-gray-border focus:border-forest outline-none text-sm"
        >
          {[5, 6, 7, 8, 9].map((n) => <option key={n} value={n}>{n} slides</option>)}
        </select>
        <button
          onClick={generate}
          disabled={busy}
          data-testid="carousel-generate-btn"
          className="bg-forest hover:bg-forest-pop text-cream-card font-barlow font-black uppercase tracking-widest text-xs px-6 py-2.5 flex items-center justify-center gap-2 transition-colors disabled:opacity-50"
        >
          {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Sparkles className="w-4 h-4" />}
          {busy ? "Creating…" : "Create carousel"}
        </button>
      </div>

      <div className="mt-6 space-y-6" data-testid="carousel-jobs">
        {jobs.map((j) => (
          <div key={j.id} className="border border-gray-border p-4" data-testid={`carousel-job-${j.id}`}>
            <div className="flex items-center justify-between flex-wrap gap-2">
              <div>
                <div className="font-bold text-ink text-sm">{j.topic}</div>
                <div className="text-[11px] text-ink/50">{(j.created_at || "").split("T")[0]} · {j.status}</div>
              </div>
              <div className="flex items-center gap-2">
                {j.status === "done" && (
                  <>
                    <button onClick={() => copyCaption(j.caption)} className="text-xs uppercase tracking-widest font-bold border border-gray-border hover:border-forest px-3 py-2 flex items-center gap-1.5" data-testid={`carousel-copy-caption-${j.id}`}>
                      <Copy className="w-3.5 h-3.5" /> Caption
                    </button>
                    <a
                      href={`${BACKEND}/api/carousel/jobs/${j.id}/zip`}
                      onClick={async (e) => {
                        e.preventDefault();
                        const r = await api.get(`/carousel/jobs/${j.id}/zip`, { responseType: "blob" });
                        const url = URL.createObjectURL(r.data);
                        const a = document.createElement("a");
                        a.href = url; a.download = `scoutmeplay-carousel-${j.id.slice(0, 8)}.zip`; a.click();
                        URL.revokeObjectURL(url);
                      }}
                      className="bg-forest text-cream-card text-xs uppercase tracking-widest font-bold px-3 py-2 flex items-center gap-1.5 hover:bg-forest-pop"
                      data-testid={`carousel-download-${j.id}`}
                    >
                      <Download className="w-3.5 h-3.5" /> Download all
                    </a>
                  </>
                )}
                {j.status === "running" && <Loader2 className="w-4 h-4 animate-spin text-forest" />}
                <button onClick={() => remove(j.id)} className="text-red-400 hover:bg-red-400 hover:text-white p-2" data-testid={`carousel-delete-${j.id}`}>
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>
            </div>
            {j.status === "failed" && <div className="mt-2 text-xs text-red-500">{j.error}</div>}
            {j.status === "done" && (
              <div className="mt-3 flex gap-2 overflow-x-auto pb-2">
                {(j.slide_urls || []).map((u, i) => (
                  <a key={u} href={`${BACKEND}${u}`} target="_blank" rel="noopener noreferrer" className="shrink-0">
                    <img src={`${BACKEND}${u}`} alt={`Slide ${i + 1}`} className="w-28 h-28 object-cover border border-gray-border hover:border-forest" />
                  </a>
                ))}
              </div>
            )}
          </div>
        ))}
        {jobs.length === 0 && <div className="text-sm text-ink/50">No carousels yet — create your first one above.</div>}
      </div>
    </div>
  );
};
