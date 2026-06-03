import React, { useState, useRef, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import Navigation from "@/components/Navigation";
import api from "@/lib/api";
import { UploadCloud, Film, Loader2, ArrowRight, Crosshair, Check, RefreshCw, AlertCircle } from "lucide-react";

export default function UploadPage() {
  const [file, setFile] = useState(null);
  const [videoUrl, setVideoUrl] = useState(null);
  const [markerBlob, setMarkerBlob] = useState(null);
  const [markerPreviewUrl, setMarkerPreviewUrl] = useState(null);
  const [isMarking, setIsMarking] = useState(false);

  const [form, setForm] = useState({
    player_name: "",
    age: "",
    position: "",
    preferred_foot: "right",
    current_club: "",
    video_type: "highlight",
    description: "",
  });
  const [submitting, setSubmitting] = useState(false);

  const fileRef = useRef(null);
  const videoRef = useRef(null);
  const overlayRef = useRef(null);
  const navigate = useNavigate();

  const setField = (k, v) => setForm((prev) => ({ ...prev, [k]: v }));

  // Clean up object URLs
  useEffect(() => {
    return () => {
      if (videoUrl) URL.revokeObjectURL(videoUrl);
      if (markerPreviewUrl) URL.revokeObjectURL(markerPreviewUrl);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleFile = (f) => {
    if (!f) return;
    if (f.size > 200 * 1024 * 1024) {
      toast.error("Video too large. Please upload under 200MB for best results.");
      return;
    }
    if (videoUrl) URL.revokeObjectURL(videoUrl);
    if (markerPreviewUrl) URL.revokeObjectURL(markerPreviewUrl);
    setFile(f);
    setVideoUrl(URL.createObjectURL(f));
    setMarkerBlob(null);
    setMarkerPreviewUrl(null);
    setIsMarking(false);
  };

  const startMarking = () => {
    const video = videoRef.current;
    if (!video) return;
    if (video.readyState < 2) {
      toast.info("Hold on — the video is still loading. Try again in a moment.");
      return;
    }
    video.pause();
    setIsMarking(true);
  };

  const cancelMarking = () => setIsMarking(false);

  const handleOverlayClick = (e) => {
    const video = videoRef.current;
    const overlay = overlayRef.current;
    if (!video || !overlay) return;

    const rect = overlay.getBoundingClientRect();
    const clickX = e.clientX - rect.left;
    const clickY = e.clientY - rect.top;
    const xRatio = clickX / rect.width;
    const yRatio = clickY / rect.height;

    const w = video.videoWidth;
    const h = video.videoHeight;
    if (!w || !h) {
      toast.error("Couldn't read the video frame. Try playing the video first then mark again.");
      return;
    }

    // Capture the exact moment of the video at the click time
    const captureTime = video.currentTime || 0;
    setMarkerTimestamp(captureTime);

    const canvas = document.createElement("canvas");
    canvas.width = w;
    canvas.height = h;
    const ctx = canvas.getContext("2d");
    ctx.drawImage(video, 0, 0, w, h);

    // Draw glowing circle around the click point
    const px = xRatio * w;
    const py = yRatio * h;
    const radius = Math.max(w, h) * 0.05;

    // Outer glow
    ctx.beginPath();
    ctx.arc(px, py, radius * 1.6, 0, Math.PI * 2);
    ctx.strokeStyle = "rgba(204, 255, 0, 0.25)";
    ctx.lineWidth = radius * 0.6;
    ctx.stroke();

    // Main bright ring
    ctx.beginPath();
    ctx.arc(px, py, radius, 0, Math.PI * 2);
    ctx.strokeStyle = "#CCFF00";
    ctx.lineWidth = Math.max(4, radius * 0.18);
    ctx.stroke();

    // Inner dot
    ctx.beginPath();
    ctx.arc(px, py, radius * 0.18, 0, Math.PI * 2);
    ctx.fillStyle = "#CCFF00";
    ctx.fill();

    // Crosshair lines from circle to edges (subtle)
    ctx.beginPath();
    ctx.strokeStyle = "rgba(204, 255, 0, 0.45)";
    ctx.lineWidth = Math.max(2, radius * 0.08);
    ctx.setLineDash([radius * 0.4, radius * 0.4]);
    ctx.moveTo(px - radius * 1.6, py);
    ctx.lineTo(0, py);
    ctx.moveTo(px + radius * 1.6, py);
    ctx.lineTo(w, py);
    ctx.moveTo(px, py - radius * 1.6);
    ctx.lineTo(px, 0);
    ctx.moveTo(px, py + radius * 1.6);
    ctx.lineTo(px, h);
    ctx.stroke();
    ctx.setLineDash([]);

    // Label tag
    const tagText = "THIS PLAYER";
    ctx.font = `bold ${Math.max(16, w * 0.022)}px Arial`;
    const textW = ctx.measureText(tagText).width;
    const tagX = Math.min(Math.max(px - textW / 2 - 12, 8), w - textW - 16);
    const tagY = Math.min(py + radius * 1.8 + 6, h - 36);
    ctx.fillStyle = "#CCFF00";
    ctx.fillRect(tagX, tagY, textW + 24, 32);
    ctx.fillStyle = "#050A0F";
    ctx.fillText(tagText, tagX + 12, tagY + 22);

    canvas.toBlob(
      (blob) => {
        if (!blob) {
          toast.error("Could not capture frame. Try a different moment.");
          return;
        }
        if (markerPreviewUrl) URL.revokeObjectURL(markerPreviewUrl);
        setMarkerBlob(blob);
        setMarkerPreviewUrl(URL.createObjectURL(blob));
        setIsMarking(false);
        toast.success("Player marked. Confirm below or re-mark if needed.");
      },
      "image/jpeg",
      0.9,
    );
  };

  const reMark = () => {
    if (markerPreviewUrl) URL.revokeObjectURL(markerPreviewUrl);
    setMarkerBlob(null);
    setMarkerPreviewUrl(null);
    setIsMarking(true);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!file) {
      toast.error("Please select a video file");
      return;
    }
    if (!markerBlob) {
      toast.error("Please mark your player on the video first");
      return;
    }
    if (!form.player_name || !form.age || !form.position || !form.description) {
      toast.error("Please fill out all required fields");
      return;
    }

    setSubmitting(true);
    const fd = new FormData();
    fd.append("file", file);
    fd.append("marker_image", markerBlob, "marker.jpg");
    Object.entries(form).forEach(([k, v]) => {
      if (v !== "" && v !== null && v !== undefined) fd.append(k, String(v));
    });

    try {
      const { data } = await api.post("/reports/upload", fd, {
        headers: { "Content-Type": "multipart/form-data" },
        timeout: 600000,
      });
      toast.success("Free preview generated. Review your insights.");
      navigate(`/report/${data.id}`);
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Upload failed. Please try again.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen bg-deepnavy text-white">
      <Navigation />

      <div className="pt-28 pb-16 px-6">
        <div className="max-w-5xl mx-auto">
          <div className="mb-10">
            <span className="text-volt text-xs uppercase tracking-[0.25em] font-bold">Step 01</span>
            <h1 className="mt-3 font-barlow font-black uppercase text-4xl md:text-5xl tracking-tighter leading-[0.95]" data-testid="upload-title">
              Upload your video & mark your player
            </h1>
            <p className="mt-3 text-white/60 max-w-2xl text-sm md:text-base">
              Upload the clip, scrub to the best moment, and click on the player. Our scouts then review only that exact player.
            </p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-px" data-testid="upload-form">
            {/* ===== STEP 1: FILE DROP ===== */}
            <div className="grid lg:grid-cols-5 gap-px bg-white/10 border border-white/10">
              <div className="bg-surface p-6 md:p-8 lg:col-span-2">
                <div className="flex items-center justify-between mb-3">
                  <span className="text-xs uppercase tracking-[0.2em] font-bold text-white/50">Step 1 · Video file</span>
                  {file && <span className="text-[10px] uppercase tracking-widest font-bold text-volt flex items-center gap-1"><Check className="w-3 h-3" /> Selected</span>}
                </div>
                <label
                  onDragOver={(e) => e.preventDefault()}
                  onDrop={(e) => {
                    e.preventDefault();
                    handleFile(e.dataTransfer.files?.[0]);
                  }}
                  data-testid="upload-dropzone"
                  className="block cursor-pointer border-2 border-dashed border-white/20 hover:border-volt bg-deepnavy/40 p-6 md:p-8 text-center transition-colors"
                >
                  <input
                    ref={fileRef}
                    type="file"
                    accept="video/mp4,video/quicktime,video/webm"
                    className="hidden"
                    onChange={(e) => handleFile(e.target.files?.[0])}
                    data-testid="upload-file-input"
                  />
                  {file ? (
                    <div className="flex flex-col items-center gap-3">
                      <Film className="w-9 h-9 text-volt" strokeWidth={1.5} />
                      <p className="font-barlow font-bold uppercase text-white text-base break-all">{file.name}</p>
                      <p className="text-xs text-white/50">{(file.size / 1024 / 1024).toFixed(1)} MB</p>
                      <button
                        type="button"
                        onClick={(e) => {
                          e.preventDefault();
                          setFile(null);
                          setVideoUrl(null);
                          setMarkerBlob(null);
                          setMarkerPreviewUrl(null);
                        }}
                        className="text-xs text-white/60 hover:text-volt uppercase tracking-widest font-semibold mt-2"
                      >
                        Replace file
                      </button>
                    </div>
                  ) : (
                    <div className="flex flex-col items-center gap-3">
                      <UploadCloud className="w-11 h-11 text-volt" strokeWidth={1.25} />
                      <p className="font-barlow font-black uppercase text-white text-lg">Drop video here</p>
                      <p className="text-xs text-white/50">MP4, MOV or WebM · max 5 minutes</p>
                      <span className="mt-1 text-xs text-volt uppercase tracking-widest font-bold">or click to browse</span>
                      <p className="mt-3 text-[11px] text-white/45 leading-relaxed max-w-[260px] text-center">
                        Tip: pick your child's best moments — scouts decide in the first 3 minutes. Quality beats quantity.
                      </p>
                    </div>
                  )}
                </label>
              </div>

              {/* ===== STEP 2: VIDEO + MARK PLAYER ===== */}
              <div className="bg-surface p-6 md:p-8 lg:col-span-3">
                <div className="flex items-center justify-between mb-3">
                  <span className="text-xs uppercase tracking-[0.2em] font-bold text-white/50">Step 2 · Mark your player</span>
                  {markerBlob && <span className="text-[10px] uppercase tracking-widest font-bold text-volt flex items-center gap-1"><Check className="w-3 h-3" /> Marked</span>}
                </div>

                {!file ? (
                  <div className="aspect-video bg-deepnavy/40 border border-white/10 flex flex-col items-center justify-center text-center p-6">
                    <Crosshair className="w-10 h-10 text-white/20 mb-3" strokeWidth={1.25} />
                    <p className="text-sm text-white/40 uppercase tracking-widest font-bold">Upload a video first</p>
                  </div>
                ) : (
                  <div className="space-y-3">
                    {/* Video + overlay */}
                    <div className="relative bg-black border border-white/10">
                      <video
                        ref={videoRef}
                        src={videoUrl}
                        controls={!isMarking}
                        playsInline
                        preload="metadata"
                        onLoadedMetadata={handleVideoLoadedMetadata}
                        data-testid="upload-video-preview"
                        className="w-full aspect-video bg-black"
                      />
                      {isMarking && (
                        <div
                          ref={overlayRef}
                          onClick={handleOverlayClick}
                          className="absolute inset-0 cursor-crosshair"
                          style={{ backgroundColor: "rgba(5, 10, 15, 0.25)" }}
                          data-testid="upload-mark-overlay"
                        >
                          <div className="absolute top-3 left-3 right-3 flex items-center justify-between">
                            <span className="bg-volt text-deepnavy text-[10px] uppercase tracking-widest font-black px-2 py-1 animate-pulse">
                              Tap on your player
                            </span>
                            <button
                              type="button"
                              onClick={(e) => { e.stopPropagation(); cancelMarking(); }}
                              data-testid="upload-mark-cancel"
                              className="bg-deepnavy/80 backdrop-blur text-white text-[10px] uppercase tracking-widest font-bold px-2 py-1 border border-white/20"
                            >
                              Cancel
                            </button>
                          </div>
                        </div>
                      )}
                    </div>

                    {!isMarking && !markerBlob && (
                      <div className="bg-deepnavy/60 border border-volt/30 p-3 flex flex-col sm:flex-row gap-3 items-start sm:items-center justify-between">
                        <div className="flex items-start gap-2.5 text-sm text-white/80">
                          <AlertCircle className="w-4 h-4 text-volt mt-0.5 flex-shrink-0" />
                          <span>Scrub to a moment where your player is clearly visible, then tap "Mark this player".</span>
                        </div>
                        <button
                          type="button"
                          onClick={startMarking}
                          data-testid="upload-mark-start"
                          className="flex-shrink-0 bg-volt hover:bg-white text-deepnavy font-barlow font-black uppercase tracking-widest text-xs px-4 py-2.5 transition-colors flex items-center gap-2"
                        >
                          <Crosshair className="w-3.5 h-3.5" />
                          Mark this player
                        </button>
                      </div>
                    )}

                    {markerBlob && markerPreviewUrl && (
                      <div className="bg-deepnavy/60 border border-volt/30 p-3">
                        <div className="flex items-center justify-between mb-2">
                          <span className="text-[10px] uppercase tracking-widest font-bold text-volt flex items-center gap-1.5">
                            <Check className="w-3 h-3" /> Player marked
                          </span>
                          <button
                            type="button"
                            onClick={reMark}
                            data-testid="upload-mark-redo"
                            className="text-white/60 hover:text-volt text-[10px] uppercase tracking-widest font-bold flex items-center gap-1 transition-colors"
                          >
                            <RefreshCw className="w-3 h-3" /> Re-mark
                          </button>
                        </div>
                        <img
                          src={markerPreviewUrl}
                          alt="Marked player"
                          data-testid="upload-mark-preview"
                          className="w-full aspect-video object-contain bg-black border border-white/5"
                        />
                        <p className="mt-2 text-[11px] text-white/50 text-center">
                          We'll review <span className="text-volt font-bold">only the player circled above</span>.
                        </p>
                      </div>
                    )}
                  </div>
                )}
              </div>
            </div>

            {/* ===== STEP 3: PLAYER DETAILS ===== */}
            <div className="bg-surface border border-white/10 p-6 md:p-8 space-y-5">
              <span className="text-xs uppercase tracking-[0.2em] font-bold text-white/50">Step 3 · Player details</span>

              <div className="grid sm:grid-cols-2 gap-4">
                <div>
                  <label className="text-xs uppercase tracking-[0.2em] font-bold text-white/50 block mb-2">Player name *</label>
                  <input
                    required
                    type="text"
                    value={form.player_name}
                    onChange={(e) => setField("player_name", e.target.value)}
                    data-testid="upload-player-name"
                    className="w-full bg-deepnavy border border-white/10 px-3 py-3 text-white focus:outline-none focus:border-volt focus:ring-1 focus:ring-volt"
                    placeholder="e.g. Lukas Andersen"
                  />
                </div>
                <div>
                  <label className="text-xs uppercase tracking-[0.2em] font-bold text-white/50 block mb-2">Age *</label>
                  <input
                    required
                    type="number"
                    min="5"
                    max="50"
                    value={form.age}
                    onChange={(e) => setField("age", e.target.value)}
                    data-testid="upload-player-age"
                    className="w-full bg-deepnavy border border-white/10 px-3 py-3 text-white focus:outline-none focus:border-volt focus:ring-1 focus:ring-volt"
                    placeholder="14"
                  />
                </div>
              </div>

              <div className="grid sm:grid-cols-2 gap-4">
                <div>
                  <label className="text-xs uppercase tracking-[0.2em] font-bold text-white/50 block mb-2">Position *</label>
                  <select
                    required
                    value={form.position}
                    onChange={(e) => setField("position", e.target.value)}
                    data-testid="upload-player-position"
                    className="w-full bg-deepnavy border border-white/10 px-3 py-3 text-white focus:outline-none focus:border-volt focus:ring-1 focus:ring-volt"
                  >
                    <option value="">Select position</option>
                    <option value="Goalkeeper">Goalkeeper</option>
                    <option value="Centre-back">Centre-back</option>
                    <option value="Full-back">Full-back</option>
                    <option value="Wing-back">Wing-back</option>
                    <option value="Defensive Midfielder">Defensive Midfielder</option>
                    <option value="Central Midfielder">Central Midfielder</option>
                    <option value="Attacking Midfielder">Attacking Midfielder</option>
                    <option value="Winger">Winger</option>
                    <option value="Striker">Striker</option>
                  </select>
                </div>
                <div>
                  <label className="text-xs uppercase tracking-[0.2em] font-bold text-white/50 block mb-2">Preferred foot *</label>
                  <select
                    required
                    value={form.preferred_foot}
                    onChange={(e) => setField("preferred_foot", e.target.value)}
                    data-testid="upload-player-foot"
                    className="w-full bg-deepnavy border border-white/10 px-3 py-3 text-white focus:outline-none focus:border-volt focus:ring-1 focus:ring-volt"
                  >
                    <option value="right">Right</option>
                    <option value="left">Left</option>
                    <option value="both">Both</option>
                  </select>
                </div>
              </div>

              <div className="grid sm:grid-cols-2 gap-4">
                <div>
                  <label className="text-xs uppercase tracking-[0.2em] font-bold text-white/50 block mb-2">Current club / team</label>
                  <input
                    type="text"
                    value={form.current_club}
                    onChange={(e) => setField("current_club", e.target.value)}
                    data-testid="upload-player-club"
                    className="w-full bg-deepnavy border border-white/10 px-3 py-3 text-white focus:outline-none focus:border-volt focus:ring-1 focus:ring-volt"
                    placeholder="Optional"
                  />
                </div>
                <div>
                  <label className="text-xs uppercase tracking-[0.2em] font-bold text-white/50 block mb-2">Video type *</label>
                  <select
                    value={form.video_type}
                    onChange={(e) => setField("video_type", e.target.value)}
                    data-testid="upload-video-type"
                    className="w-full bg-deepnavy border border-white/10 px-3 py-3 text-white focus:outline-none focus:border-volt focus:ring-1 focus:ring-volt"
                  >
                    <option value="highlight">Highlight reel</option>
                    <option value="match">Match clip</option>
                    <option value="training">Training clip</option>
                  </select>
                </div>
              </div>

              <div>
                <label className="text-xs uppercase tracking-[0.2em] font-bold text-white/50 block mb-2">Which player are you in the video? *</label>
                <textarea
                  required
                  value={form.description}
                  onChange={(e) => setField("description", e.target.value)}
                  data-testid="upload-player-description"
                  rows={3}
                  className="w-full bg-deepnavy border border-white/10 px-3 py-3 text-white focus:outline-none focus:border-volt focus:ring-1 focus:ring-volt resize-none"
                  placeholder="e.g. I am number 10 in the white shirt — the one you just marked above."
                />
              </div>

              <button
                type="submit"
                disabled={submitting || !file || !markerBlob}
                data-testid="upload-submit-btn"
                className="w-full bg-volt hover:bg-white text-deepnavy font-barlow font-black uppercase tracking-widest text-base px-8 py-4 transition-colors disabled:opacity-40 disabled:cursor-not-allowed flex items-center justify-center gap-3 mt-2"
              >
                {submitting ? (
                  <>
                    <Loader2 className="w-5 h-5 animate-spin" />
                    Analysing... this can take 1–3 minutes
                  </>
                ) : !file ? (
                  "Upload a video first"
                ) : !markerBlob ? (
                  "Mark your player first"
                ) : (
                  <>
                    Generate free preview
                    <ArrowRight className="w-5 h-5" />
                  </>
                )}
              </button>
              <p className="text-xs text-white/40 text-center">
                The scouts will review <span className="text-volt font-bold">only the player you marked</span>. Other players in the video are ignored.
              </p>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}
