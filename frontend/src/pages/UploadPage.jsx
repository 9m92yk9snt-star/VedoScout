import React, { useState, useRef, useEffect } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import Navigation from "@/components/Navigation";
import CheckoutTransitionModal from "@/components/CheckoutTransitionModal";
import api from "@/lib/api";
import { UploadCloud, Film, Loader2, ArrowRight, Crosshair, Check, RefreshCw, AlertCircle, Plus, Minus, Maximize2, Lock, Zap } from "lucide-react";

export default function UploadPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [eligibility, setEligibility] = useState(null);   // { eligible, reason, free_preview_used, prepaid_uploads }
  const [eligibilityLoading, setEligibilityLoading] = useState(true);
  const [prepaying, setPrepaying] = useState(false);

  // Stripe transition modal state
  const [checkoutModal, setCheckoutModal] = useState({ open: false, state: "preparing", errorMessage: null });

  const [file, setFile] = useState(null);
  const [videoUrl, setVideoUrl] = useState(null);
  const [markerBlob, setMarkerBlob] = useState(null);
  const [markerPreviewUrl, setMarkerPreviewUrl] = useState(null);
  const [markerTimestamp, setMarkerTimestamp] = useState(0);
  const [isMarking, setIsMarking] = useState(false);

  // P1: zoom + pan state for the marking overlay
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const gestureRef = useRef(null);
  const movedRef = useRef(false);

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

  // Fetch upload eligibility on mount + after returning from Stripe checkout
  const refreshEligibility = async () => {
    try {
      const { data } = await api.get("/me/upload-eligibility");
      setEligibility(data);
    } catch (err) {
      // If unauthorized, just leave eligibility null
      console.error("Eligibility check failed", err);
    } finally {
      setEligibilityLoading(false);
    }
  };

  useEffect(() => {
    refreshEligibility();
    // eslint-disable-next-line
  }, []);

  // Handle return from Stripe prepay checkout (?prepay_session=... or ?prepay_canceled=1)
  useEffect(() => {
    const sessionId = searchParams.get("prepay_session");
    const canceled = searchParams.get("prepay_canceled");
    if (sessionId) {
      (async () => {
        try {
          const { data } = await api.get(`/payments/status/${sessionId}`);
          if (data.payment_status === "paid") {
            // Show the celebration via the same transition modal
            setCheckoutModal({ open: true, state: "success", errorMessage: null });
            await refreshEligibility();
          } else {
            toast.info("Payment still pending. Refresh in a few seconds.");
          }
        } catch (e) {
          toast.error("Couldn't verify your payment. Refresh the page or contact support.");
        }
        // Clean up the query params
        const next = new URLSearchParams(searchParams);
        next.delete("prepay_session");
        setSearchParams(next, { replace: true });
      })();
    } else if (canceled) {
      toast.info("Payment cancelled.");
      const next = new URLSearchParams(searchParams);
      next.delete("prepay_canceled");
      setSearchParams(next, { replace: true });
    }
    // eslint-disable-next-line
  }, [searchParams.get("prepay_session"), searchParams.get("prepay_canceled")]);

  const handlePrepayUpload = async () => {
    setPrepaying(true);
    setCheckoutModal({ open: true, state: "preparing", errorMessage: null });
    try {
      const { data } = await api.post("/payments/prepay-upload", {
        origin_url: window.location.origin,
      });
      // Brief pause so the user perceives the modal, then redirect
      setCheckoutModal((m) => ({ ...m, state: "redirecting" }));
      setTimeout(() => {
        window.location.href = data.url;
      }, 700);
    } catch (err) {
      setPrepaying(false);
      setCheckoutModal({
        open: true,
        state: "error",
        errorMessage: err?.response?.data?.detail || "Couldn't start checkout. Try again.",
      });
    }
  };

  // Reset zoom/pan whenever marking starts or video changes
  useEffect(() => {
    if (!isMarking) {
      setZoom(1);
      setPan({ x: 0, y: 0 });
    }
  }, [isMarking, videoUrl]);

  // Zoom controls (clamped 1× – 4×)
  const clampZoom = (z) => Math.max(1, Math.min(4, z));
  const zoomIn = () => setZoom((z) => clampZoom(z + 0.5));
  const zoomOut = () =>
    setZoom((z) => {
      const nz = clampZoom(z - 0.5);
      if (nz <= 1.01) setPan({ x: 0, y: 0 });
      return nz;
    });
  const resetZoom = () => {
    setZoom(1);
    setPan({ x: 0, y: 0 });
  };

  // Pinch + pan gesture handlers (only active while marking)
  const onWrapperTouchStart = (e) => {
    if (!isMarking) return;
    if (e.touches.length === 2) {
      const t1 = e.touches[0];
      const t2 = e.touches[1];
      gestureRef.current = {
        type: "pinch",
        startDist: Math.hypot(t1.clientX - t2.clientX, t1.clientY - t2.clientY),
        startZoom: zoom,
      };
      movedRef.current = true;
    } else if (e.touches.length === 1 && zoom > 1.01) {
      gestureRef.current = {
        type: "pan",
        startX: e.touches[0].clientX,
        startY: e.touches[0].clientY,
        startPan: pan,
      };
      movedRef.current = false;
    } else {
      gestureRef.current = null;
      movedRef.current = false;
    }
  };

  const onWrapperTouchMove = (e) => {
    if (!isMarking || !gestureRef.current) return;
    if (gestureRef.current.type === "pinch" && e.touches.length === 2) {
      e.preventDefault();
      const t1 = e.touches[0];
      const t2 = e.touches[1];
      const d = Math.hypot(t1.clientX - t2.clientX, t1.clientY - t2.clientY);
      const ratio = d / gestureRef.current.startDist;
      const nz = clampZoom(gestureRef.current.startZoom * ratio);
      setZoom(nz);
      if (nz <= 1.01) setPan({ x: 0, y: 0 });
      movedRef.current = true;
    } else if (gestureRef.current.type === "pan" && e.touches.length === 1) {
      e.preventDefault();
      const dx = e.touches[0].clientX - gestureRef.current.startX;
      const dy = e.touches[0].clientY - gestureRef.current.startY;
      if (Math.abs(dx) > 4 || Math.abs(dy) > 4) movedRef.current = true;
      setPan({ x: gestureRef.current.startPan.x + dx, y: gestureRef.current.startPan.y + dy });
    }
  };

  const onWrapperTouchEnd = () => {
    gestureRef.current = null;
  };

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
    setMarkerTimestamp(0);
    setIsMarking(false);
  };

  // Force iOS Safari (and other browsers) to render the first frame instead of a black box
  const handleVideoLoadedMetadata = () => {
    const video = videoRef.current;
    if (!video) return;
    try {
      if (video.currentTime < 0.1) video.currentTime = 0.1;
    } catch (_) {
      /* ignore — seek can fail on some codecs */
    }
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
    // Ignore clicks that are actually the end of a pan/pinch gesture
    if (movedRef.current) {
      movedRef.current = false;
      return;
    }
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
    setMarkerTimestamp(0);
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
    fd.append("marker_timestamp", String(markerTimestamp || 0));
    Object.entries(form).forEach(([k, v]) => {
      if (v !== "" && v !== null && v !== undefined) fd.append(k, String(v));
    });

    try {
      const { data } = await api.post("/reports/upload", fd, {
        headers: { "Content-Type": "multipart/form-data" },
        timeout: 600000,
      });
      toast.success(
        eligibility?.reason === "prepaid"
          ? "Upload received — generating your premium report."
          : "Free preview generated. Review your insights."
      );
      navigate(`/report/${data.id}`);
    } catch (err) {
      // 402 with structured detail = pre-pay required
      const detail = err?.response?.data?.detail;
      if (err?.response?.status === 402 && (detail?.code === "PREPAY_REQUIRED" || typeof detail === "object")) {
        toast.info(detail?.message || "Pay 399 DKK to upload your next video.");
        await refreshEligibility();
      } else {
        toast.error(
          (typeof detail === "string" ? detail : detail?.message) || "Upload failed. Please try again."
        );
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen bg-deepnavy text-white">
      <Navigation />
      <CheckoutTransitionModal
        open={checkoutModal.open}
        state={checkoutModal.state}
        errorMessage={checkoutModal.errorMessage}
        amount={399}
        currency="DKK"
        product="ScoutMePlay – Football Video Analysis"
        onClose={() => setCheckoutModal({ open: false, state: "preparing", errorMessage: null })}
      />

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

            {/* Eligibility status pill */}
            {!eligibilityLoading && eligibility && (
              <div className="mt-5">
                {eligibility.reason === "free_preview" && (
                  <span data-testid="eligibility-free" className="inline-flex items-center gap-2 text-[11px] uppercase tracking-[0.22em] font-bold text-volt border border-volt/40 bg-volt/5 px-3 py-1.5">
                    <Zap className="w-3.5 h-3.5" /> 1 free preview available
                  </span>
                )}
                {eligibility.reason === "prepaid" && (
                  <span data-testid="eligibility-prepaid" className="inline-flex items-center gap-2 text-[11px] uppercase tracking-[0.22em] font-bold text-volt border border-volt/40 bg-volt/5 px-3 py-1.5">
                    <Check className="w-3.5 h-3.5" /> 1 prepaid upload · full premium report
                  </span>
                )}
                {eligibility.reason === "admin" && (
                  <span data-testid="eligibility-admin" className="inline-flex items-center gap-2 text-[11px] uppercase tracking-[0.22em] font-bold text-white/70 border border-white/20 px-3 py-1.5">
                    Admin · unlimited uploads
                  </span>
                )}
              </div>
            )}
          </div>

          {/* ===== PAYWALL — ineligible state ===== */}
          {!eligibilityLoading && eligibility && !eligibility.eligible && eligibility.reason === "prepay_required" && (
            <div data-testid="upload-paywall" className="mb-10 relative overflow-hidden border-2 border-volt bg-gradient-to-br from-volt/10 via-deepnavy/40 to-deepnavy/40 p-8 md:p-12" style={{ boxShadow: "0 0 80px rgba(204,255,0,0.12)" }}>
              <div className="grid md:grid-cols-3 gap-8 items-center">
                <div className="md:col-span-2">
                  <div className="inline-flex items-center gap-2 text-[10px] uppercase tracking-[0.25em] font-bold text-volt border border-volt/40 bg-volt/10 px-3 py-1.5 mb-5">
                    <Lock className="w-3.5 h-3.5" />
                    Free preview used
                  </div>
                  <h2 className="font-barlow font-black uppercase text-3xl md:text-5xl tracking-tighter leading-[0.95]">
                    Ready for your next video?
                  </h2>
                  <p className="mt-4 text-white/75 leading-relaxed text-sm md:text-base max-w-xl">
                    Pre-pay <span className="text-volt font-bold">399 DKK</span> to upload your next clip — your full premium report unlocks the moment analysis finishes. No second checkout. No subscriptions.
                  </p>
                  <ul className="mt-6 grid sm:grid-cols-2 gap-x-6 gap-y-2 text-sm text-white/80">
                    {[
                      "Full 11-section premium report",
                      "Evidence + confidence per category",
                      "Premium PDF you can share",
                      "Scout review chat unlocked",
                    ].map((s, i) => (
                      <li key={i} className="flex items-start gap-2">
                        <Check className="w-4 h-4 text-volt mt-0.5 shrink-0" />
                        <span>{s}</span>
                      </li>
                    ))}
                  </ul>
                  <button
                    type="button"
                    onClick={handlePrepayUpload}
                    disabled={prepaying}
                    data-testid="upload-prepay-btn"
                    className="mt-8 inline-flex items-center justify-center gap-3 bg-volt hover:bg-white text-deepnavy font-barlow font-black uppercase tracking-widest text-base px-7 py-4 transition-colors disabled:opacity-60"
                  >
                    {prepaying ? <Loader2 className="w-5 h-5 animate-spin" /> : <Lock className="w-5 h-5" />}
                    Pre-pay 399 DKK & upload
                    <ArrowRight className="w-5 h-5" />
                  </button>
                  <p className="mt-3 text-[11px] text-white/40 uppercase tracking-[0.2em] font-bold">
                    Secure Stripe checkout · one-time payment · no subscriptions
                  </p>
                </div>
                <div className="md:col-span-1 text-center md:text-right">
                  <div className="inline-block bg-deepnavy/60 border border-volt/30 p-6">
                    <div className="text-[10px] uppercase tracking-[0.25em] font-bold text-volt mb-2">Per upload</div>
                    <div className="font-barlow font-black text-6xl text-white leading-none">399</div>
                    <div className="mt-1 text-xs uppercase tracking-widest font-bold text-white/55">DKK · one-time</div>
                  </div>
                </div>
              </div>
            </div>
          )}

          <form onSubmit={handleSubmit} className={`space-y-px ${eligibility && !eligibility.eligible ? "opacity-40 pointer-events-none" : ""}`} data-testid="upload-form">
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
                    {/* Video + overlay (zoomable when marking) */}
                    <div
                      className="relative bg-black border border-white/10 overflow-hidden select-none"
                      onTouchStart={onWrapperTouchStart}
                      onTouchMove={onWrapperTouchMove}
                      onTouchEnd={onWrapperTouchEnd}
                      onTouchCancel={onWrapperTouchEnd}
                      style={{ touchAction: isMarking ? "none" : "auto" }}
                    >
                      {/* Transformed inner — video + clickable overlay scale together */}
                      <div
                        style={{
                          transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoom})`,
                          transformOrigin: "0 0",
                          transition: gestureRef.current ? "none" : "transform 0.15s ease-out",
                          willChange: "transform",
                        }}
                      >
                        <video
                          ref={videoRef}
                          src={videoUrl}
                          controls={!isMarking}
                          playsInline
                          preload="metadata"
                          onLoadedMetadata={handleVideoLoadedMetadata}
                          data-testid="upload-video-preview"
                          className="w-full aspect-video bg-black"
                          style={{ pointerEvents: isMarking ? "none" : "auto" }}
                        />
                        {isMarking && (
                          <div
                            ref={overlayRef}
                            onClick={handleOverlayClick}
                            className="absolute inset-0 cursor-crosshair"
                            style={{ backgroundColor: "rgba(5, 10, 15, 0.18)" }}
                            data-testid="upload-mark-overlay"
                          />
                        )}
                      </div>

                      {/* Static UI — NOT scaled */}
                      {isMarking && (
                        <>
                          <div className="pointer-events-none absolute top-3 left-3 right-3 flex items-center justify-between z-10">
                            <span className="pointer-events-auto bg-volt text-deepnavy text-[10px] uppercase tracking-widest font-black px-2 py-1 animate-pulse">
                              Tap on your player
                            </span>
                            <button
                              type="button"
                              onClick={(e) => {
                                e.stopPropagation();
                                cancelMarking();
                              }}
                              data-testid="upload-mark-cancel"
                              className="pointer-events-auto bg-deepnavy/80 backdrop-blur text-white text-[10px] uppercase tracking-widest font-bold px-2.5 py-1 border border-white/20"
                            >
                              Cancel
                            </button>
                          </div>

                          {/* Zoom controls */}
                          <div className="pointer-events-none absolute bottom-3 right-3 z-10 flex items-center gap-1.5">
                            <div className="pointer-events-auto flex items-center bg-deepnavy/85 backdrop-blur-sm border border-white/20">
                              <button
                                type="button"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  zoomOut();
                                }}
                                disabled={zoom <= 1.01}
                                data-testid="upload-zoom-out"
                                className="w-9 h-9 flex items-center justify-center text-white hover:text-volt disabled:opacity-30 disabled:cursor-not-allowed transition-colors border-r border-white/20"
                                aria-label="Zoom out"
                              >
                                <Minus className="w-4 h-4" />
                              </button>
                              <span className="px-2 min-w-[42px] text-center text-[11px] font-barlow font-black text-volt tracking-wider tabular-nums">
                                {Math.round(zoom * 100)}%
                              </span>
                              <button
                                type="button"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  zoomIn();
                                }}
                                disabled={zoom >= 3.99}
                                data-testid="upload-zoom-in"
                                className="w-9 h-9 flex items-center justify-center text-white hover:text-volt disabled:opacity-30 disabled:cursor-not-allowed transition-colors border-l border-white/20"
                                aria-label="Zoom in"
                              >
                                <Plus className="w-4 h-4" />
                              </button>
                            </div>
                            {zoom > 1.01 && (
                              <button
                                type="button"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  resetZoom();
                                }}
                                data-testid="upload-zoom-reset"
                                className="pointer-events-auto w-9 h-9 flex items-center justify-center text-white hover:text-volt bg-deepnavy/85 backdrop-blur-sm border border-white/20 transition-colors"
                                aria-label="Reset zoom"
                              >
                                <Maximize2 className="w-4 h-4" />
                              </button>
                            )}
                          </div>

                          {/* Hint when zoomed */}
                          {zoom > 1.01 && (
                            <div className="pointer-events-none absolute bottom-3 left-3 z-10">
                              <span className="bg-deepnavy/85 backdrop-blur-sm text-white/80 text-[9px] uppercase tracking-widest font-bold px-2 py-1 border border-white/15">
                                Drag to pan · Tap player when ready
                              </span>
                            </div>
                          )}
                        </>
                      )}
                    </div>

                    {!isMarking && !markerBlob && (
                      <div className="bg-deepnavy/60 border border-volt/30 p-3 flex flex-col sm:flex-row gap-3 items-start sm:items-center justify-between">
                        <div className="flex items-start gap-2.5 text-sm text-white/80">
                          <AlertCircle className="w-4 h-4 text-volt mt-0.5 flex-shrink-0" />
                          <span>
                            Scrub to a clear moment, then tap "Mark this player".{" "}
                            <span className="text-volt/80">Pinch to zoom for precision on mobile.</span>
                          </span>
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
