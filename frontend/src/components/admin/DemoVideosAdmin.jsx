import React, { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import {
  Plus, Trash2, Save, Video, Upload, Loader2, Image as ImageIcon,
  ChevronUp, ChevronDown, ExternalLink, Eye, EyeOff,
} from "lucide-react";
import api from "@/lib/api";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const abs = (u) => (u && u.startsWith("http") ? u : `${BACKEND_URL}${u}`);

/**
 * Admin CMS for the demo-video carousel shown on the landing page.
 * Lets the admin upload iPhone MOV/MP4 clips, add title/subtitle, reorder,
 * toggle active/draft, and delete. Videos are surfaced immediately on `/`.
 */
export default function DemoVideosAdmin() {
  const [videos, setVideos] = useState(null);
  const [creating, setCreating] = useState(false);
  const [busyId, setBusyId] = useState(null);
  const [confirmDeleteId, setConfirmDeleteId] = useState(null);

  const load = async () => {
    const { data } = await api.get("/admin/demo-videos");
    setVideos(data.items || []);
  };

  useEffect(() => { load(); }, []);

  // Auto-cancel pending confirm after 4s so the "Confirm delete?" state
  // doesn't sit around forever if the admin clicks away.
  useEffect(() => {
    if (!confirmDeleteId) return;
    const t = setTimeout(() => setConfirmDeleteId(null), 4000);
    return () => clearTimeout(t);
  }, [confirmDeleteId]);

  const createNew = () => {
    setCreating(true);
  };

  const handleSaveNew = async (payload) => {
    try {
      await api.post("/admin/demo-videos", payload);
      toast.success("Demo video added — visible on the landing page.");
      setCreating(false);
      await load();
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Could not save");
      throw err;
    }
  };

  const handleUpdate = async (id, payload) => {
    setBusyId(id);
    try {
      await api.put(`/admin/demo-videos/${id}`, payload);
      toast.success("Saved.");
      await load();
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Could not update");
    } finally {
      setBusyId(null);
    }
  };

  const handleDelete = async (id) => {
    // Inline "click twice to confirm" — window.confirm() is silently blocked
    // inside our preview iframe (Kubernetes ingress + sandbox), so we use
    // a two-state button UX instead.
    if (confirmDeleteId !== id) {
      setConfirmDeleteId(id);
      return;
    }
    setConfirmDeleteId(null);
    setBusyId(id);
    try {
      await api.delete(`/admin/demo-videos/${id}`);
      toast.success("Deleted.");
      await load();
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Could not delete");
    } finally {
      setBusyId(null);
    }
  };

  const move = async (id, direction) => {
    if (!videos) return;
    const idx = videos.findIndex((v) => v.id === id);
    if (idx < 0) return;
    const other = direction === "up" ? idx - 1 : idx + 1;
    if (other < 0 || other >= videos.length) return;
    const a = videos[idx];
    const b = videos[other];
    setBusyId(id);
    try {
      await Promise.all([
        api.put(`/admin/demo-videos/${a.id}`, { order: b.order }),
        api.put(`/admin/demo-videos/${b.id}`, { order: a.order }),
      ]);
      await load();
    } catch {
      toast.error("Could not reorder");
    } finally {
      setBusyId(null);
    }
  };

  if (videos === null) {
    return (
      <div className="flex items-center justify-center py-16">
        <Loader2 className="w-6 h-6 text-forest animate-spin" />
      </div>
    );
  }

  const active = videos.filter((v) => v.status === "active").length;

  return (
    <div className="space-y-6" data-testid="admin-demo-videos">
      <header className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h2 className="font-barlow font-black uppercase tracking-tight text-2xl">
            Demo Videos
          </h2>
          <p className="text-sm text-ink/60 mt-1 max-w-xl">
            Short clips shown in a swipeable carousel below "How it works" on the landing page.
            Record on your iPhone, upload the file, add a headline — visible instantly.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-[10px] uppercase tracking-widest font-black text-ink/50">
            {active} active · {videos.length} total
          </span>
          <button
            type="button"
            onClick={createNew}
            data-testid="demo-videos-new-btn"
            className="inline-flex items-center gap-2 bg-forest hover:bg-forest-pop text-white font-barlow font-black uppercase tracking-widest text-xs px-4 py-2.5 transition-colors"
          >
            <Plus className="w-4 h-4" /> Add video
          </button>
        </div>
      </header>

      {creating && (
        <DemoVideoForm
          onCancel={() => setCreating(false)}
          onSave={handleSaveNew}
          initialOrder={(videos.at(-1)?.order || 0) + 10}
        />
      )}

      {videos.length === 0 && !creating ? (
        <div className="border border-ink/10 bg-cream-card p-10 text-center">
          <Video className="w-10 h-10 text-ink/20 mx-auto mb-3" />
          <p className="text-ink/60 text-sm">No demo videos yet. Click "Add video" to upload your first iPhone clip.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {videos.map((v, i) => (
            <DemoVideoRow
              key={v.id}
              video={v}
              busy={busyId === v.id}
              pendingConfirm={confirmDeleteId === v.id}
              onUpdate={(payload) => handleUpdate(v.id, payload)}
              onDelete={() => handleDelete(v.id)}
              onMoveUp={i > 0 ? () => move(v.id, "up") : null}
              onMoveDown={i < videos.length - 1 ? () => move(v.id, "down") : null}
            />
          ))}
        </div>
      )}
    </div>
  );
}

/* ─────────────────────────── ROW ─────────────────────────── */

function DemoVideoRow({ video, busy, pendingConfirm, onUpdate, onDelete, onMoveUp, onMoveDown }) {
  const [title, setTitle] = useState(video.title || "");
  const [subtitle, setSubtitle] = useState(video.subtitle || "");
  const [dirty, setDirty] = useState(false);

  const toggleStatus = () =>
    onUpdate({ status: video.status === "active" ? "draft" : "active" });

  const saveText = () => {
    if (!title.trim()) {
      toast.error("Title is required");
      return;
    }
    onUpdate({ title, subtitle });
    setDirty(false);
  };

  return (
    <div className={`border p-4 md:p-5 ${
      video.status === "active"
        ? "border-forest/40 bg-forest/5"
        : "border-ink/10 bg-cream-card opacity-80"
    }`}>
      <div className="grid md:grid-cols-[140px,1fr,auto] gap-4 items-start">
        {/* Poster / thumbnail */}
        <div className="aspect-[9/16] max-h-[180px] bg-ink border border-ink/10 overflow-hidden flex items-center justify-center">
          {video.poster_url ? (
            <img src={abs(video.poster_url)} alt="" className="w-full h-full object-cover" />
          ) : video.video_url ? (
            <video src={abs(video.video_url)} muted preload="metadata" className="w-full h-full object-cover" />
          ) : (
            <Video className="w-8 h-8 text-white/30" />
          )}
        </div>

        {/* Text edit */}
        <div className="space-y-2 min-w-0">
          <input
            type="text" maxLength={80}
            value={title}
            onChange={(e) => { setTitle(e.target.value); setDirty(true); }}
            data-testid={`demo-row-title-${video.id}`}
            placeholder="Title (e.g. Upload your first clip)"
            className="w-full border border-ink/15 bg-white px-3 py-2 text-sm font-bold focus:border-forest focus:outline-none"
          />
          <textarea
            rows={2} maxLength={180}
            value={subtitle}
            onChange={(e) => { setSubtitle(e.target.value); setDirty(true); }}
            data-testid={`demo-row-subtitle-${video.id}`}
            placeholder="Optional short caption (max 180 chars)"
            className="w-full border border-ink/15 bg-white px-3 py-2 text-sm focus:border-forest focus:outline-none resize-none"
          />
          <div className="flex flex-wrap items-center gap-3 text-[11px] text-ink/50">
            <span>Order: {video.order}</span>
            {video.video_url && (
              <a
                href={abs(video.video_url)}
                target="_blank" rel="noreferrer"
                className="text-forest hover:underline inline-flex items-center gap-1"
              >
                Open video <ExternalLink className="w-3 h-3" />
              </a>
            )}
            <span className={`uppercase tracking-widest font-black ${
              video.status === "active" ? "text-forest-pop" : "text-ink/40"
            }`}>
              {video.status}
            </span>
          </div>
        </div>

        {/* Controls */}
        <div className="flex flex-col gap-2 items-stretch">
          <button
            type="button" onClick={saveText} disabled={!dirty || busy}
            data-testid={`demo-row-save-${video.id}`}
            className="inline-flex items-center gap-1.5 text-[11px] uppercase tracking-widest font-black bg-forest hover:bg-forest-pop text-white px-3 py-2 transition-colors disabled:opacity-40"
          >
            <Save className="w-3.5 h-3.5" /> Save
          </button>
          <button
            type="button" onClick={toggleStatus} disabled={busy}
            className={`inline-flex items-center gap-1.5 text-[11px] uppercase tracking-widest font-black px-3 py-2 transition-colors ${
              video.status === "active"
                ? "bg-ink/10 hover:bg-ink/20 text-ink"
                : "bg-volt hover:bg-forest-pop hover:text-white text-ink"
            }`}
          >
            {video.status === "active" ? <><EyeOff className="w-3.5 h-3.5" /> Hide</> : <><Eye className="w-3.5 h-3.5" /> Publish</>}
          </button>
          <div className="flex gap-1">
            <button
              type="button" onClick={onMoveUp} disabled={!onMoveUp || busy}
              aria-label="Move up"
              className="flex-1 border border-ink/15 hover:bg-ink/5 text-ink px-2 py-1.5 disabled:opacity-30 transition-colors"
            >
              <ChevronUp className="w-3.5 h-3.5 mx-auto" />
            </button>
            <button
              type="button" onClick={onMoveDown} disabled={!onMoveDown || busy}
              aria-label="Move down"
              className="flex-1 border border-ink/15 hover:bg-ink/5 text-ink px-2 py-1.5 disabled:opacity-30 transition-colors"
            >
              <ChevronDown className="w-3.5 h-3.5 mx-auto" />
            </button>
          </div>
          <button
            type="button" onClick={onDelete} disabled={busy}
            data-testid={`demo-row-delete-${video.id}`}
            className={`inline-flex items-center gap-1.5 text-[11px] uppercase tracking-widest font-black px-3 py-2 transition-colors ${
              pendingConfirm
                ? "bg-red-600 text-white border border-red-600 animate-pulse"
                : "border border-red-300 text-red-700 hover:bg-red-100"
            }`}
          >
            <Trash2 className="w-3.5 h-3.5" />
            {pendingConfirm ? "Click to confirm" : "Delete"}
          </button>
        </div>
      </div>
    </div>
  );
}

/* ─────────────────────────── NEW FORM ─────────────────────────── */

function DemoVideoForm({ onCancel, onSave, initialOrder = 10 }) {
  const [title, setTitle] = useState("");
  const [subtitle, setSubtitle] = useState("");
  const [videoUrl, setVideoUrl] = useState("");
  const [posterUrl, setPosterUrl] = useState("");
  const [status, setStatus] = useState("active");
  const [uploadingVideo, setUploadingVideo] = useState(false);
  const [uploadingPoster, setUploadingPoster] = useState(false);
  const [saving, setSaving] = useState(false);
  const videoInputRef = useRef(null);
  const posterInputRef = useRef(null);

  const handleVideoUpload = async (file) => {
    if (!file) return;
    if (file.size > 100 * 1024 * 1024) {
      toast.error("Video must be 100 MB or smaller.");
      return;
    }
    setUploadingVideo(true);
    try {
      const form = new FormData();
      form.append("file", file);
      const { data } = await api.post("/admin/demo-videos/upload-video", form, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setVideoUrl(data.url);
      toast.success("Video uploaded.");
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Upload failed");
    } finally {
      setUploadingVideo(false);
    }
  };

  const handlePosterUpload = async (file) => {
    if (!file) return;
    setUploadingPoster(true);
    try {
      const form = new FormData();
      form.append("file", file);
      const { data } = await api.post("/admin/demo-videos/upload-poster", form, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setPosterUrl(data.url);
      toast.success("Poster uploaded.");
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Upload failed");
    } finally {
      setUploadingPoster(false);
    }
  };

  const canSave = title.trim() && videoUrl && !uploadingVideo && !uploadingPoster && !saving;

  const submit = async () => {
    if (!canSave) return;
    setSaving(true);
    try {
      await onSave({
        title: title.trim(),
        subtitle: subtitle.trim() || null,
        video_url: videoUrl,
        poster_url: posterUrl || null,
        order: initialOrder,
        status,
      });
    } catch { /* toasted upstream */ }
    setSaving(false);
  };

  return (
    <div className="border-2 border-forest/40 bg-forest/5 p-5" data-testid="demo-video-form">
      <div className="grid md:grid-cols-2 gap-4">
        <label className="block">
          <div className="text-[10px] uppercase tracking-[0.18em] font-black text-forest mb-1.5">Title *</div>
          <input
            type="text" maxLength={80}
            value={title} onChange={(e) => setTitle(e.target.value)}
            data-testid="demo-form-title"
            placeholder="Upload your first clip"
            className="w-full border border-ink/15 bg-white px-3 py-2 text-sm focus:border-forest focus:outline-none"
          />
        </label>

        <label className="block">
          <div className="text-[10px] uppercase tracking-[0.18em] font-black text-forest mb-1.5">Status</div>
          <select
            value={status} onChange={(e) => setStatus(e.target.value)}
            data-testid="demo-form-status"
            className="w-full border border-ink/15 bg-white px-3 py-2 text-sm focus:border-forest focus:outline-none"
          >
            <option value="active">Active — show on landing</option>
            <option value="draft">Draft — hidden</option>
          </select>
        </label>

        <label className="block md:col-span-2">
          <div className="text-[10px] uppercase tracking-[0.18em] font-black text-forest mb-1.5">Subtitle (optional)</div>
          <textarea
            rows={2} maxLength={180}
            value={subtitle} onChange={(e) => setSubtitle(e.target.value)}
            data-testid="demo-form-subtitle"
            placeholder="Short caption shown under the title (max 180 chars)"
            className="w-full border border-ink/15 bg-white px-3 py-2 text-sm resize-none focus:border-forest focus:outline-none"
          />
        </label>

        {/* Video file upload */}
        <div className="block md:col-span-2">
          <div className="text-[10px] uppercase tracking-[0.18em] font-black text-forest mb-1.5">Video file *</div>
          <div className="flex flex-wrap items-center gap-3">
            <input
              ref={videoInputRef}
              type="file"
              accept="video/mp4,video/quicktime,video/webm,video/x-m4v"
              onChange={(e) => handleVideoUpload(e.target.files?.[0])}
              className="hidden"
              data-testid="demo-form-video-input"
            />
            <button
              type="button"
              onClick={() => videoInputRef.current?.click()}
              disabled={uploadingVideo}
              className="inline-flex items-center gap-2 bg-forest hover:bg-forest-pop text-white text-[11px] uppercase tracking-widest font-black px-4 py-2 transition-colors disabled:opacity-50"
            >
              {uploadingVideo ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Upload className="w-3.5 h-3.5" />}
              {uploadingVideo ? "Uploading…" : "Upload iPhone clip"}
            </button>
            {videoUrl && (
              <a
                href={abs(videoUrl)}
                target="_blank" rel="noreferrer"
                className="text-[11px] text-forest hover:underline inline-flex items-center gap-1"
              >
                {videoUrl.split("/").pop()} <ExternalLink className="w-3 h-3" />
              </a>
            )}
          </div>
          <p className="text-[10.5px] text-ink/40 mt-1.5">MP4 / MOV / WebM · max 100 MB</p>
        </div>

        {/* Poster upload (optional) */}
        <div className="block md:col-span-2">
          <div className="text-[10px] uppercase tracking-[0.18em] font-black text-forest mb-1.5">Poster image (optional)</div>
          <div className="flex flex-wrap items-center gap-3">
            <input
              ref={posterInputRef}
              type="file"
              accept="image/jpeg,image/png,image/webp"
              onChange={(e) => handlePosterUpload(e.target.files?.[0])}
              className="hidden"
              data-testid="demo-form-poster-input"
            />
            <button
              type="button"
              onClick={() => posterInputRef.current?.click()}
              disabled={uploadingPoster}
              className="inline-flex items-center gap-2 bg-ink/10 hover:bg-ink/20 text-ink text-[11px] uppercase tracking-widest font-black px-4 py-2 transition-colors disabled:opacity-50"
            >
              {uploadingPoster ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <ImageIcon className="w-3.5 h-3.5" />}
              {uploadingPoster ? "Uploading…" : "Upload poster"}
            </button>
            {posterUrl && (
              <img src={abs(posterUrl)} alt="" className="w-12 h-16 object-cover border border-ink/20" />
            )}
          </div>
          <p className="text-[10.5px] text-ink/40 mt-1.5">Skip this and we'll use the video's first frame automatically.</p>
        </div>
      </div>

      <div className="flex items-center justify-end gap-2 mt-5 pt-4 border-t border-ink/10">
        <button
          type="button" onClick={onCancel}
          className="text-[11px] uppercase tracking-widest font-black text-ink/50 hover:text-ink transition-colors"
        >
          Cancel
        </button>
        <button
          type="button" onClick={submit} disabled={!canSave}
          data-testid="demo-form-save"
          className="inline-flex items-center gap-2 bg-forest hover:bg-forest-pop text-white font-barlow font-black uppercase tracking-widest text-xs px-5 py-2.5 transition-colors disabled:opacity-40"
        >
          {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
          Save video
        </button>
      </div>
    </div>
  );
}
