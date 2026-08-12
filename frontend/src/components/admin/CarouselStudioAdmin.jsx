// CarouselStudioAdmin — generate Instagram carousel slides in ScoutMePlay style.
import React, { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { Images, Loader2, Sparkles, Trash2, Download, Copy, Instagram, Link2, X, Send, ShieldCheck } from "lucide-react";
import api from "@/lib/api";
import QualityCheckDialog from "@/components/admin/QualityCheckDialog";

const BACKEND = process.env.REACT_APP_BACKEND_URL;

function InstagramConnectCard({ config, onChanged }) {
  const [open, setOpen] = useState(false);
  const [token, setToken] = useState("");
  const [igId, setIgId] = useState("");
  const [busy, setBusy] = useState(false);

  const connect = async () => {
    if (!token.trim() || !igId.trim()) { toast.error("Paste both the access token and the account ID"); return; }
    setBusy(true);
    try {
      const { data } = await api.put("/instagram/config", { access_token: token.trim(), ig_user_id: igId.trim() });
      toast.success(`Connected as @${data.username || igId}`);
      setToken(""); setIgId(""); setOpen(false);
      onChanged();
    } catch (e) {
      toast.error(e?.response?.data?.detail || e.message);
    } finally { setBusy(false); }
  };

  const disconnect = async () => {
    if (!window.confirm("Disconnect Instagram? Publishing will stop working until you reconnect.")) return;
    await api.delete("/instagram/config");
    toast.success("Instagram disconnected");
    onChanged();
  };

  return (
    <div className="border border-gray-border bg-cream-soft/30 p-4 mb-5" data-testid="instagram-connect-card">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div className="flex items-center gap-2.5">
          <span className="w-8 h-8 rounded-lg flex items-center justify-center" style={{ background: "linear-gradient(45deg,#F58529,#DD2A7B,#8134AF)" }}>
            <Instagram className="w-4.5 h-4.5 text-white" />
          </span>
          <div>
            <div className="font-bold text-ink text-sm">Instagram connection</div>
            {config?.connected ? (
              <div className="text-xs text-forest font-bold" data-testid="instagram-connected-as">Connected as @{config.username || config.ig_user_id}</div>
            ) : (
              <div className="text-xs text-ink/55">Not connected — connect to post carousels directly to your profile</div>
            )}
          </div>
        </div>
        {config?.connected ? (
          <button onClick={disconnect} data-testid="instagram-disconnect-btn"
            className="text-xs uppercase tracking-widest font-bold text-red-500 border border-red-300 hover:bg-red-500 hover:text-white px-3 py-2 transition-colors flex items-center gap-1.5">
            <X className="w-3.5 h-3.5" /> Disconnect
          </button>
        ) : (
          <button onClick={() => setOpen((v) => !v)} data-testid="instagram-connect-btn"
            className="text-xs uppercase tracking-widest font-bold text-forest border border-forest/40 hover:bg-forest hover:text-cream-card px-3 py-2 transition-colors flex items-center gap-1.5">
            <Link2 className="w-3.5 h-3.5" /> Connect
          </button>
        )}
      </div>
      {open && !config?.connected && (
        <div className="mt-4 space-y-2" data-testid="instagram-connect-form">
          <p className="text-xs text-ink/60">
            Requires an Instagram <b>Business</b> account linked to your Facebook Page + a Meta app access token.
            In the Meta App Dashboard: <b>Instagram → API setup</b> → generate a long-lived token, then find your account ID via
            <code className="bg-cream-soft px-1 mx-1">me/accounts?fields=instagram_business_account</code>.
            Ask in the chat and we&apos;ll walk you through it step by step.
          </p>
          <input value={token} onChange={(e) => setToken(e.target.value)} placeholder="Long-lived access token"
            data-testid="instagram-token-input"
            className="w-full px-3 py-2.5 bg-surface border border-gray-border focus:border-forest outline-none text-xs font-mono" />
          <div className="flex gap-2">
            <input value={igId} onChange={(e) => setIgId(e.target.value)} placeholder="Instagram Business account ID (1784…)"
              data-testid="instagram-igid-input"
              className="flex-1 px-3 py-2.5 bg-surface border border-gray-border focus:border-forest outline-none text-xs font-mono" />
            <button onClick={connect} disabled={busy} data-testid="instagram-save-btn"
              className="bg-forest hover:bg-forest-pop text-cream-card font-barlow font-black uppercase tracking-widest text-xs px-5 py-2.5 flex items-center gap-2 disabled:opacity-50">
              {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Link2 className="w-4 h-4" />} Connect
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

export const CarouselStudioAdmin = () => {
  const [topic, setTopic] = useState("");
  const [commentWord, setCommentWord] = useState("GUIDE");
  const [slides, setSlides] = useState(7);
  const [busy, setBusy] = useState(false);
  const [jobs, setJobs] = useState([]);
  const [qcJob, setQcJob] = useState(null);
  const [igConfig, setIgConfig] = useState(null);
  const pollRef = useRef(null);
  const igPollRef = useRef(null);

  const load = async () => {
    try {
      const { data } = await api.get("/carousel/jobs");
      setJobs(data.items || []);
      return data.items || [];
    } catch { return []; }
  };

  const loadIg = async () => {
    try {
      const { data } = await api.get("/instagram/config");
      setIgConfig(data);
    } catch { /* noop */ }
  };

  useEffect(() => {
    load(); loadIg();
    return () => { clearInterval(pollRef.current); clearInterval(igPollRef.current); };
  }, []);

  const postToInstagram = async (job) => {
    if (!window.confirm(`Post this carousel (${(job.slide_urls || []).length} slides) to Instagram now?`)) return;
    try {
      await api.post(`/instagram/publish/${job.id}`, { origin_url: window.location.origin });
      toast.info("Publishing to Instagram — this can take a minute…");
      await load();
      clearInterval(igPollRef.current);
      igPollRef.current = setInterval(async () => {
        const items = await load();
        const j = items.find((x) => x.id === job.id);
        if (!j || j.instagram_status === "publishing") return;
        clearInterval(igPollRef.current);
        if (j.instagram_status === "published") toast.success("Posted to Instagram 🎉");
        else toast.error("Instagram publish failed: " + (j.instagram_error || "unknown"));
      }, 5000);
    } catch (e) {
      toast.error(e?.response?.data?.detail || e.message);
    }
  };

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
        Post it directly to Instagram below, or download the images and post from your phone.
        The last slide asks readers to comment your keyword.
      </p>

      <InstagramConnectCard config={igConfig} onChanged={loadIg} />

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
                    {j.instagram_status === "published" ? (
                      <a href={j.instagram_permalink || "#"} target="_blank" rel="noopener noreferrer"
                        data-testid={`carousel-ig-published-${j.id}`}
                        className="text-xs uppercase tracking-widest font-bold text-white px-3 py-2 flex items-center gap-1.5"
                        style={{ background: "linear-gradient(45deg,#F58529,#DD2A7B,#8134AF)" }}>
                        <Instagram className="w-3.5 h-3.5" /> On Instagram ↗
                      </a>
                    ) : j.instagram_status === "publishing" ? (
                      <span className="text-xs uppercase tracking-widest font-bold text-ink/60 px-3 py-2 flex items-center gap-1.5 border border-gray-border" data-testid={`carousel-ig-publishing-${j.id}`}>
                        <Loader2 className="w-3.5 h-3.5 animate-spin" /> Publishing…
                      </span>
                    ) : (
                      <button onClick={() => postToInstagram(j)} disabled={!igConfig?.connected}
                        title={igConfig?.connected ? "Post this carousel to Instagram" : "Connect Instagram first"}
                        data-testid={`carousel-ig-post-${j.id}`}
                        className="text-xs uppercase tracking-widest font-bold text-white px-3 py-2 flex items-center gap-1.5 disabled:opacity-40 hover:opacity-90"
                        style={{ background: "linear-gradient(45deg,#F58529,#DD2A7B,#8134AF)" }}>
                        <Send className="w-3.5 h-3.5" /> Post to Instagram
                      </button>
                    )}
                    <button onClick={() => setQcJob(j)} className="text-xs uppercase tracking-widest font-bold border border-gray-border hover:border-forest px-3 py-2 flex items-center gap-1.5" data-testid={`carousel-qc-${j.id}`} title="Anti-generic QC">
                      <ShieldCheck className="w-3.5 h-3.5" /> QC
                    </button>
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
            {j.instagram_status === "failed" && (
              <div className="mt-2 text-xs text-red-500" data-testid={`carousel-ig-error-${j.id}`}>
                Instagram: {j.instagram_error} — fix the connection and press &quot;Post to Instagram&quot; again.
              </div>
            )}
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
      {qcJob && (
        <QualityCheckDialog
          kind="carousel"
          targetId={qcJob.id}
          title={qcJob.topic}
          onClose={() => setQcJob(null)}
          onApplied={load}
        />
      )}
    </div>
  );
};
