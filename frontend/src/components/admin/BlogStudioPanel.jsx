// BlogStudioPanel — warm-tone one-click article generator + weekly auto-draft toggle.
import React, { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { PenLine, Loader2, X, CalendarClock, Sparkles } from "lucide-react";
import api from "@/lib/api";

export default function BlogStudioPanel({ onClose, onSaved }) {
  const [topic, setTopic] = useState("");
  const [keyword, setKeyword] = useState("");
  const [generating, setGenerating] = useState(false);
  const [autoWeekly, setAutoWeekly] = useState(false);
  const [lastAutoAt, setLastAutoAt] = useState(null);
  const pollRef = useRef(null);

  useEffect(() => {
    api.get("/blog-studio/config").then(({ data }) => {
      setAutoWeekly(!!data.auto_weekly);
      setLastAutoAt(data.last_auto_at || null);
    }).catch(() => {});
    return () => clearInterval(pollRef.current);
  }, []);

  const toggleWeekly = async () => {
    const next = !autoWeekly;
    setAutoWeekly(next);
    try {
      await api.put("/blog-studio/config", { auto_weekly: next });
      toast.success(next
        ? "Weekly auto-draft is ON — a fresh draft lands every week for your review"
        : "Weekly auto-draft is OFF");
    } catch (e) {
      setAutoWeekly(!next);
      toast.error("Could not save setting");
    }
  };

  const generate = async () => {
    setGenerating(true);
    try {
      const { data } = await api.post("/blog-studio/generate", { topic: topic.trim(), keyword: keyword.trim() });
      const jobId = data.job_id;
      toast.info("Writing your article in the ScoutMePlay voice — this takes ~1 minute…");
      pollRef.current = setInterval(async () => {
        try {
          const r = await api.get("/blog-studio/jobs");
          const job = (r.data?.items || []).find((j) => j.id === jobId);
          if (!job || job.status === "running") return;
          clearInterval(pollRef.current);
          setGenerating(false);
          if (job.status === "done") {
            toast.success(`Draft ready: "${job.title}" — review it in the list and publish when happy`);
            setTopic(""); setKeyword("");
            onSaved?.();
          } else {
            toast.error("Generation failed: " + (job.error || "unknown error"));
          }
        } catch { /* keep polling */ }
      }, 3000);
    } catch (e) {
      setGenerating(false);
      toast.error("Could not start: " + (e?.response?.data?.detail || e.message));
    }
  };

  return (
    <div data-testid="blog-studio-panel" className="border-2 border-forest/40 bg-forest/5 p-5 md:p-6 mb-6">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <PenLine className="w-5 h-5 text-forest" />
          <span className="font-barlow font-black uppercase text-lg tracking-tight text-forest">Blog Studio</span>
          <span className="text-[10px] uppercase tracking-[0.2em] font-bold bg-forest text-cream-card px-2 py-0.5">Warm voice</span>
        </div>
        <button onClick={onClose} className="text-ink/55 hover:text-ink p-1" aria-label="Close" data-testid="blog-studio-close">
          <X className="w-4 h-4" />
        </button>
      </div>

      <p className="text-sm text-ink/70 mb-4">
        One click writes a complete article in the same warm, human ScoutMePlay tone as the rest of the platform.
        It is always saved as a <b>draft</b> — nothing goes live without you.
      </p>

      <div className="grid md:grid-cols-[1fr_240px_auto] gap-2">
        <input
          data-testid="blog-studio-topic"
          value={topic}
          onChange={(e) => setTopic(e.target.value)}
          placeholder="Topic (optional — leave empty and we pick a fresh one)"
          className="px-3 py-2.5 bg-surface border border-gray-border focus:border-forest outline-none text-sm"
        />
        <input
          data-testid="blog-studio-keyword"
          value={keyword}
          onChange={(e) => setKeyword(e.target.value)}
          placeholder="SEO keyword (optional)"
          className="px-3 py-2.5 bg-surface border border-gray-border focus:border-forest outline-none text-sm"
        />
        <button
          onClick={generate}
          disabled={generating}
          data-testid="blog-studio-generate"
          className="bg-forest hover:bg-forest-pop text-cream-card font-barlow font-black uppercase tracking-widest text-xs px-6 py-2.5 flex items-center justify-center gap-2 transition-colors disabled:opacity-50"
        >
          {generating ? <Loader2 className="w-4 h-4 animate-spin" /> : <Sparkles className="w-4 h-4" />}
          {generating ? "Writing…" : "Write article"}
        </button>
      </div>

      <div className="mt-5 pt-4 border-t border-forest/20 flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-2.5">
          <CalendarClock className="w-4 h-4 text-forest" />
          <div>
            <div className="text-sm font-bold text-ink">Weekly auto-draft</div>
            <div className="text-xs text-ink/55">
              Every week a new draft appears here for your review.
              {lastAutoAt && <> Last: {lastAutoAt.split("T")[0]}</>}
            </div>
          </div>
        </div>
        <button
          type="button"
          role="switch"
          aria-checked={autoWeekly}
          onClick={toggleWeekly}
          data-testid="blog-studio-weekly-toggle"
          className={`relative w-12 h-7 rounded-full transition-colors ${autoWeekly ? "bg-forest" : "bg-ink/20"}`}
        >
          <span className={`absolute top-1 w-5 h-5 rounded-full bg-white shadow transition-all ${autoWeekly ? "left-6" : "left-1"}`} />
        </button>
      </div>
    </div>
  );
}
