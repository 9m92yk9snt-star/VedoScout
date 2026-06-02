import React, { useState, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import Navigation from "@/components/Navigation";
import api from "@/lib/api";
import { UploadCloud, Film, Loader2, ArrowRight } from "lucide-react";

export default function UploadPage() {
  const [file, setFile] = useState(null);
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
  const navigate = useNavigate();

  const setField = (k, v) => setForm((prev) => ({ ...prev, [k]: v }));

  const handleFile = (f) => {
    if (!f) return;
    if (f.size > 200 * 1024 * 1024) {
      toast.error("Video too large. Please upload under 200MB for best results.");
      return;
    }
    setFile(f);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!file) {
      toast.error("Please select a video file");
      return;
    }
    if (!form.player_name || !form.age || !form.position || !form.description) {
      toast.error("Please fill out all required fields");
      return;
    }

    setSubmitting(true);
    const fd = new FormData();
    fd.append("file", file);
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
              Upload your video
            </h1>
            <p className="mt-3 text-white/60 max-w-2xl text-sm md:text-base">
              Provide a highlight, match clip or training clip with player details. Our AI will generate an instant free preview.
            </p>
          </div>

          <form onSubmit={handleSubmit} className="grid lg:grid-cols-5 gap-px bg-white/10 border border-white/10" data-testid="upload-form">
            {/* Drop zone */}
            <div className="bg-surface p-6 md:p-8 lg:col-span-2">
              <div className="text-xs uppercase tracking-[0.2em] font-bold text-white/50 mb-3">Video file</div>
              <label
                onDragOver={(e) => e.preventDefault()}
                onDrop={(e) => {
                  e.preventDefault();
                  handleFile(e.dataTransfer.files?.[0]);
                }}
                data-testid="upload-dropzone"
                className="block cursor-pointer border-2 border-dashed border-white/20 hover:border-volt bg-deepnavy/40 p-8 md:p-10 text-center transition-colors"
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
                    <Film className="w-10 h-10 text-volt" strokeWidth={1.5} />
                    <p className="font-barlow font-bold uppercase text-white text-lg break-all">{file.name}</p>
                    <p className="text-xs text-white/50">{(file.size / 1024 / 1024).toFixed(1)} MB</p>
                    <button
                      type="button"
                      onClick={(e) => {
                        e.preventDefault();
                        setFile(null);
                      }}
                      className="text-xs text-white/60 hover:text-volt uppercase tracking-widest font-semibold mt-2"
                    >
                      Replace file
                    </button>
                  </div>
                ) : (
                  <div className="flex flex-col items-center gap-3">
                    <UploadCloud className="w-12 h-12 text-volt" strokeWidth={1.25} />
                    <p className="font-barlow font-black uppercase text-white text-xl">Drop video here</p>
                    <p className="text-xs text-white/50">MP4, MOV or WebM · up to 200MB</p>
                    <span className="mt-2 text-xs text-volt uppercase tracking-widest font-bold">or click to browse</span>
                  </div>
                )}
              </label>
              <p className="mt-5 text-xs text-white/40 leading-relaxed">
                Tip: shorter, high-quality clips (under 5 min) typically receive richer analysis.
              </p>
            </div>

            {/* Player details */}
            <div className="bg-surface p-6 md:p-8 lg:col-span-3 space-y-5">
              <div className="text-xs uppercase tracking-[0.2em] font-bold text-white/50">Player details</div>

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
                  placeholder="e.g. I am number 10 in the white shirt, playing as an attacking midfielder."
                />
              </div>

              <button
                type="submit"
                disabled={submitting}
                data-testid="upload-submit-btn"
                className="w-full bg-volt hover:bg-white text-deepnavy font-barlow font-black uppercase tracking-widest text-base px-8 py-4 transition-colors disabled:opacity-50 flex items-center justify-center gap-3 mt-2"
              >
                {submitting ? (
                  <>
                    <Loader2 className="w-5 h-5 animate-spin" />
                    Analyzing video... this may take a few minutes
                  </>
                ) : (
                  <>
                    Generate free preview
                    <ArrowRight className="w-5 h-5" />
                  </>
                )}
              </button>
              <p className="text-xs text-white/40 text-center">
                By uploading you confirm this is your video and you agree to receive AI-generated developmental feedback.
              </p>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}
