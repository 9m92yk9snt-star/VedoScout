import React, { useState, useRef, useEffect } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import Navigation from "@/components/Navigation";
import CheckoutTransitionModal from "@/components/CheckoutTransitionModal";
import EmbeddedCheckoutModal from "@/components/EmbeddedCheckoutModal";
import PaymentBadges from "@/components/PaymentBadges";
import PrecisionScanOverlay from "@/components/PrecisionScanOverlay";
import api from "@/lib/api";
import { UploadCloud, Film, Loader2, ArrowRight, Crosshair, Check, RefreshCw, AlertCircle, Plus, Minus, Maximize2, Lock, Zap, Link as LinkIcon, FileUp } from "lucide-react";

export default function UploadPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [eligibility, setEligibility] = useState(null);   // { eligible, reason, free_preview_used, prepaid_uploads }
  const [eligibilityLoading, setEligibilityLoading] = useState(true);
  const [prepaying, setPrepaying] = useState(false);
  const [price, setPrice] = useState(1);

  // Embedded checkout state (preferred when Stripe keys are configured)
  const [embeddedOpen, setEmbeddedOpen] = useState(false);

  // Stripe transition modal state (legacy redirect fallback)
  const [checkoutModal, setCheckoutModal] = useState({ open: false, state: "preparing", errorMessage: null });

  const [file, setFile] = useState(null);
  const [videoUrl, setVideoUrl] = useState(null);
  const [markerBlob, setMarkerBlob] = useState(null);
  const [markerPreviewUrl, setMarkerPreviewUrl] = useState(null);
  const [markerTimestamp, setMarkerTimestamp] = useState(0);
  // ── Precision Scout: box-drag marker (normalised 0-1 coords) ──
  const [markerBox, setMarkerBox] = useState(null);       // {x,y,w,h} 0-1 once committed
  const [drawingBox, setDrawingBox] = useState(null);     // {x,y,w,h} live during drag (px in overlay space)
  const boxStartRef = useRef(null);                       // {sx, sy} drag start in overlay pixels
  const [isMarking, setIsMarking] = useState(false);

  // ── URL-paste mode ────────────────────────────────────────────────────
  const [sourceMode, setSourceMode] = useState("file"); // "file" | "url"
  const [pasteUrl, setPasteUrl] = useState("");
  const [urlFetching, setUrlFetching] = useState(false);
  const [tempVideoToken, setTempVideoToken] = useState(null);

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

  /* eslint-disable */
  useEffect(() => {
    refreshEligibility();
    api.get("/settings/price").then(({ data }) => setPrice(data.price)).catch(() => {});
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
    try {
      // Prefer the embedded checkout when configured
      const { data: cfg } = await api.get("/config/stripe");
      if (cfg.embedded_available) {
        setPrepaying(false);
        setEmbeddedOpen(true);
        return;
      }
    } catch (_) {
      // ignore — fall through to redirect mode
    }

    // Legacy redirect-style flow
    setCheckoutModal({ open: true, state: "preparing", errorMessage: null });
    try {
      const { data } = await api.post("/payments/prepay-upload", {
        origin_url: window.location.origin,
      });
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

  // Embedded checkout: backend session creator
  const embeddedPrepayInit = async () => {
    const { data } = await api.post("/payments/embedded/prepay-upload", {
      origin_url: window.location.origin,
    });
    return data;
  };

  const handleEmbeddedSuccess = async () => {
    await refreshEligibility();
    toast.success("Upload credit added. You can upload your next video now.");
  };

  // Reset zoom/pan whenever marking starts or video changes
  useEffect(() => {
    if (!isMarking) {
      setZoom(1);
      setPan({ x: 0, y: 0 });
    }
  }, [isMarking, videoUrl]);
  /* eslint-enable */

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

  // Pinch (2-finger) zoom only — single-finger drags now belong to the box marker
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
    } else {
      gestureRef.current = null;
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
    setTempVideoToken(null); // clear any prior URL-fetch
  };

  // Fetch a video from a public URL (YouTube / Vimeo / Veo / direct MP4)
  const handleUrlFetch = async (e) => {
    e?.preventDefault?.();
    const url = (pasteUrl || "").trim();
    if (!url) {
      toast.error("Paste a video URL first.");
      return;
    }
    if (!/^https?:\/\//i.test(url)) {
      toast.error("URL must start with http(s)://");
      return;
    }
    setUrlFetching(true);
    try {
      const { data } = await api.post("/me/url-fetch", { url }, { timeout: 130000 });
      // Clear any local file state and use the server-side temp video
      if (videoUrl && videoUrl.startsWith("blob:")) URL.revokeObjectURL(videoUrl);
      const apiBase = process.env.REACT_APP_BACKEND_URL || "";
      const fullPreview = `${apiBase}${data.preview_url}`;
      // Use a sentinel "file-like" object so the rest of the UI shows a name + size
      setFile({
        name: data.filename || "video-from-url.mp4",
        size: (data.size_mb || 0) * 1024 * 1024,
        _fromUrl: true,
      });
      setVideoUrl(fullPreview);
      setTempVideoToken(data.token);
      setMarkerBlob(null);
      setMarkerPreviewUrl(null);
      setMarkerTimestamp(0);
      setIsMarking(false);
      toast.success(`Video fetched (${(data.size_mb || 0).toFixed(1)} MB) — now mark your player.`);
    } catch (err) {
      const msg = err?.response?.data?.detail || err.message || "URL fetch failed.";
      toast.error(typeof msg === "string" ? msg : "Could not download that video.");
    } finally {
      setUrlFetching(false);
    }
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
    setDrawingBox(null);
    setMarkerBox(null);
  };

  const cancelMarking = () => {
    setIsMarking(false);
    setDrawingBox(null);
  };

  // Helpers — overlay-relative pixel coordinates for a pointer event
  const overlayCoords = (e) => {
    const overlay = overlayRef.current;
    if (!overlay) return null;
    const rect = overlay.getBoundingClientRect();
    return {
      x: Math.max(0, Math.min(rect.width, e.clientX - rect.left)),
      y: Math.max(0, Math.min(rect.height, e.clientY - rect.top)),
      w: rect.width,
      h: rect.height,
    };
  };

  // Pointer-driven box drawing — works on touch and mouse
  const onOverlayPointerDown = (e) => {
    if (!isMarking) return;
    e.preventDefault();
    e.stopPropagation();
    const p = overlayCoords(e);
    if (!p) return;
    boxStartRef.current = { sx: p.x, sy: p.y, w: p.w, h: p.h };
    movedRef.current = true; // prevent the wrapper's click-after-touch logic
    // Capture the exact moment of the video at the moment the user starts drawing
    const video = videoRef.current;
    if (video) setMarkerTimestamp(video.currentTime || 0);
    // Seed a tiny box at the click point so user gets instant visual feedback
    setDrawingBox({ x: p.x, y: p.y, w: 0, h: 0 });
    try {
      e.currentTarget.setPointerCapture?.(e.pointerId);
    } catch (_) { /* ignore */ }
  };

  const onOverlayPointerMove = (e) => {
    if (!isMarking || !boxStartRef.current) return;
    e.preventDefault();
    e.stopPropagation();
    const p = overlayCoords(e);
    if (!p) return;
    const { sx, sy } = boxStartRef.current;
    const x = Math.min(sx, p.x);
    const y = Math.min(sy, p.y);
    const w = Math.abs(p.x - sx);
    const h = Math.abs(p.y - sy);
    setDrawingBox({ x, y, w, h });
  };

  const onOverlayPointerUp = (e) => {
    if (!isMarking || !boxStartRef.current) return;
    e.preventDefault();
    e.stopPropagation();
    try {
      e.currentTarget.releasePointerCapture?.(e.pointerId);
    } catch (_) { /* ignore */ }
    const start = boxStartRef.current;
    boxStartRef.current = null;
    if (!drawingBox) return;
    const { sx, sy, w: rw, h: rh } = start;

    let { x, y, w, h } = drawingBox;
    // If user only tapped (very small box), auto-grow to a default size around the tap
    const minSide = Math.max(36, Math.min(rw, rh) * 0.12);
    if (w < minSide || h < minSide) {
      const defaultW = Math.max(rw * 0.15, 60);
      const defaultH = defaultW * 1.8; // tall portrait box, fits a person
      x = Math.max(0, sx - defaultW / 2);
      y = Math.max(0, sy - defaultH / 2);
      w = Math.min(rw - x, defaultW);
      h = Math.min(rh - y, defaultH);
    }
    // Commit normalised box
    const norm = {
      x: x / rw,
      y: y / rh,
      w: w / rw,
      h: h / rh,
    };
    setMarkerBox(norm);
    setDrawingBox({ x, y, w, h }); // keep visual box while confirm UI is shown
  };

  // Render the marker image (frame + green rectangle around the locked player)
  // and finalise. Called when user taps "Confirm" or after pointer-up on the
  // very rare desktop drag where we want immediate confirm.
  const confirmMarkerBox = () => {
    const video = videoRef.current;
    if (!video) return;
    if (!markerBox) {
      toast.error("Draw a box around your player first.");
      return;
    }
    const w = video.videoWidth;
    const h = video.videoHeight;
    if (!w || !h) {
      toast.error("Couldn't read the video frame. Try playing it briefly then re-mark.");
      return;
    }

    const canvas = document.createElement("canvas");
    canvas.width = w;
    canvas.height = h;
    const ctx = canvas.getContext("2d");
    ctx.drawImage(video, 0, 0, w, h);

    // Project normalised box into pixel coords
    const bx = Math.round(markerBox.x * w);
    const by = Math.round(markerBox.y * h);
    const bw = Math.max(8, Math.round(markerBox.w * w));
    const bh = Math.max(8, Math.round(markerBox.h * h));

    // Outer dim — darkens everything outside the box, focuses scout attention
    ctx.save();
    ctx.fillStyle = "rgba(5, 10, 15, 0.45)";
    ctx.beginPath();
    ctx.rect(0, 0, w, h);
    ctx.rect(bx, by, bw, bh);
    ctx.closePath();
    ctx.fill("evenodd");
    ctx.restore();

    // Glow halo
    ctx.save();
    ctx.shadowColor = "#CCFF00";
    ctx.shadowBlur = Math.max(12, Math.min(w, h) * 0.012);
    ctx.strokeStyle = "rgba(204, 255, 0, 0.5)";
    ctx.lineWidth = Math.max(4, Math.min(w, h) * 0.006);
    ctx.strokeRect(bx, by, bw, bh);
    ctx.restore();

    // Crisp volt border
    ctx.strokeStyle = "#CCFF00";
    ctx.lineWidth = Math.max(3, Math.min(w, h) * 0.004);
    ctx.strokeRect(bx, by, bw, bh);

    // Corner ticks — 4 L-shaped marks for that "lock-on" look
    const corner = Math.max(14, Math.min(bw, bh) * 0.18);
    ctx.strokeStyle = "#FFFFFF";
    ctx.lineWidth = Math.max(2, Math.min(w, h) * 0.0035);
    [
      [bx, by, +1, +1],
      [bx + bw, by, -1, +1],
      [bx, by + bh, +1, -1],
      [bx + bw, by + bh, -1, -1],
    ].forEach(([cx, cy, dx, dy]) => {
      ctx.beginPath();
      ctx.moveTo(cx, cy + dy * corner);
      ctx.lineTo(cx, cy);
      ctx.lineTo(cx + dx * corner, cy);
      ctx.stroke();
    });

    // Label
    const label = "LOCKED";
    const labelFont = `bold ${Math.max(14, w * 0.018)}px Arial`;
    ctx.font = labelFont;
    const tw = ctx.measureText(label).width;
    const padX = 10;
    const padY = 5;
    const lh = Math.max(20, w * 0.025);
    let lx = bx;
    let ly = by - lh - 4;
    if (ly < 4) ly = by + bh + 4;
    ctx.fillStyle = "#CCFF00";
    ctx.fillRect(lx, ly, tw + padX * 2, lh);
    ctx.fillStyle = "#050A0F";
    ctx.fillText(label, lx + padX, ly + lh - padY - 2);

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
        setDrawingBox(null);
        toast.success("Player locked. We'll analyse only the player in the box.");
      },
      "image/jpeg",
      0.92,
    );
  };

  // Legacy single-click handler removed — pointer drag now drives everything.
  // (Old function preserved as no-op to avoid touching JSX wiring that still
  // references it. New handlers live on the overlay's pointer events.)
  const handleOverlayClick = () => { /* deprecated — see onOverlayPointer* */ };

  const reMark = () => {
    if (markerPreviewUrl) URL.revokeObjectURL(markerPreviewUrl);
    setMarkerBlob(null);
    setMarkerPreviewUrl(null);
    setMarkerTimestamp(0);
    setMarkerBox(null);
    setDrawingBox(null);
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
    if (file?._fromUrl && tempVideoToken) {
      fd.append("temp_video_token", tempVideoToken);
    } else {
      fd.append("file", file);
    }
    fd.append("marker_image", markerBlob, "marker.jpg");
    fd.append("marker_timestamp", String(markerTimestamp || 0));
    if (markerBox) {
      fd.append(
        "marker_box",
        JSON.stringify({
          x: Number(markerBox.x.toFixed(4)),
          y: Number(markerBox.y.toFixed(4)),
          w: Number(markerBox.w.toFixed(4)),
          h: Number(markerBox.h.toFixed(4)),
        }),
      );
    }
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
        toast.info(detail?.message || `Pay $${price} to upload your next video.`);
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
    <div className="min-h-screen bg-deepnavy text-ink">
      <Navigation />
      <CheckoutTransitionModal
        open={checkoutModal.open}
        state={checkoutModal.state}
        errorMessage={checkoutModal.errorMessage}
        amount={price}
        currency="USD"
        product="ScoutMePlay – Football Video Analysis"
        onClose={() => setCheckoutModal({ open: false, state: "preparing", errorMessage: null })}
      />
      <EmbeddedCheckoutModal
        open={embeddedOpen}
        sessionInit={embeddedPrepayInit}
        amount={price}
        currency="USD"
        product="ScoutMePlay – Football Video Analysis"
        onSuccess={handleEmbeddedSuccess}
        onClose={() => setEmbeddedOpen(false)}
      />
      <PrecisionScanOverlay open={submitting} />

      <div className="pt-28 pb-16 px-6">
        <div className="max-w-5xl mx-auto">
          <div className="mb-10">
            <span className="text-volt text-xs uppercase tracking-[0.25em] font-bold">Step 01</span>
            <h1 className="mt-3 font-barlow font-black uppercase text-4xl md:text-5xl tracking-tighter leading-[0.95]" data-testid="upload-title">
              Upload your video & lock onto your player
            </h1>
            <p className="mt-3 text-ink/65 max-w-2xl text-sm md:text-base">
              Upload the clip, scrub to the clearest moment, then drag a box around your player — head to feet. Our AI locks onto their jersey, shorts, and body, and follows only that player through the video.
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
                  <span data-testid="eligibility-admin" className="inline-flex items-center gap-2 text-[11px] uppercase tracking-[0.22em] font-bold text-ink/70 border border-gray-border px-3 py-1.5">
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
                  <p className="mt-4 text-ink/75 leading-relaxed text-sm md:text-base max-w-xl">
                    Pre-pay <span className="text-volt font-bold">${price} USD</span> to upload your next clip — your full premium report unlocks the moment analysis finishes. No second checkout. No subscriptions.
                  </p>
                  <ul className="mt-6 grid sm:grid-cols-2 gap-x-6 gap-y-2 text-sm text-ink/80">
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
                    className="mt-8 inline-flex items-center justify-center gap-3 bg-volt hover:bg-forest-pop text-white font-barlow font-black uppercase tracking-widest text-base px-7 py-4 transition-colors disabled:opacity-60"
                  >
                    {prepaying ? <Loader2 className="w-5 h-5 animate-spin" /> : <Lock className="w-5 h-5" />}
                    Pre-pay ${price} USD & upload
                    <ArrowRight className="w-5 h-5" />
                  </button>
                  <p className="mt-3 text-[11px] text-ink/50 uppercase tracking-[0.2em] font-bold">
                    Secure Stripe checkout · one-time payment · no subscriptions
                  </p>
                  <div className="mt-3">
                    <PaymentBadges variant="compact" />
                  </div>
                </div>
                <div className="md:col-span-1 text-center md:text-right">
                  <div className="inline-block bg-cream-card/90 border border-volt/30 p-6">
                    <div className="text-[10px] uppercase tracking-[0.25em] font-bold text-volt mb-2">Per upload</div>
                    <div className="font-barlow font-black text-6xl text-ink leading-none">${price}</div>
                    <div className="mt-1 text-xs uppercase tracking-widest font-bold text-ink/60">USD · one-time</div>
                  </div>
                </div>
              </div>
            </div>
          )}

          <form onSubmit={handleSubmit} className={`space-y-px ${eligibility && !eligibility.eligible ? "opacity-40 pointer-events-none" : ""}`} data-testid="upload-form">
            {/* ===== STEP 1: FILE DROP ===== */}
            <div className="grid lg:grid-cols-5 gap-px bg-cream-soft/40 border border-gray-border">
              <div className="bg-surface p-6 md:p-8 lg:col-span-2">
                <div className="flex items-center justify-between mb-3">
                  <span className="text-xs uppercase tracking-[0.2em] font-bold text-ink/55">Step 1 · Video file</span>
                  {file && <span className="text-[10px] uppercase tracking-widest font-bold text-volt flex items-center gap-1"><Check className="w-3 h-3" /> Selected</span>}
                </div>

                {/* === Source mode tabs: file upload OR paste URL === */}
                <div className="flex items-center gap-px mb-4 border border-gray-border bg-cream-soft/60">
                  <button
                    type="button"
                    onClick={() => setSourceMode("file")}
                    data-testid="upload-mode-file"
                    className={`flex-1 px-3 py-2.5 text-[10px] uppercase tracking-[0.18em] font-bold flex items-center justify-center gap-2 transition-colors ${
                      sourceMode === "file"
                        ? "bg-volt text-white"
                        : "text-ink/60 hover:text-ink"
                    }`}
                  >
                    <FileUp className="w-3.5 h-3.5" /> Upload file
                  </button>
                  <button
                    type="button"
                    onClick={() => setSourceMode("url")}
                    data-testid="upload-mode-url"
                    className={`flex-1 px-3 py-2.5 text-[10px] uppercase tracking-[0.18em] font-bold flex items-center justify-center gap-2 transition-colors ${
                      sourceMode === "url"
                        ? "bg-volt text-white"
                        : "text-ink/60 hover:text-ink"
                    }`}
                  >
                    <LinkIcon className="w-3.5 h-3.5" /> Paste URL
                  </button>
                </div>

                {/* === URL paste box (when sourceMode === "url") === */}
                {sourceMode === "url" && (
                  <div className="mb-4 space-y-2">
                    <div className="flex items-stretch gap-2">
                      <input
                        type="url"
                        data-testid="upload-url-input"
                        value={pasteUrl}
                        onChange={(e) => setPasteUrl(e.target.value)}
                        placeholder="YouTube · Vimeo · Veo · Google Drive · .mp4 link"
                        className="flex-1 px-3 py-2.5 bg-cream-soft border border-gray-border focus:border-volt outline-none text-sm font-mono"
                        disabled={urlFetching}
                      />
                      <button
                        type="button"
                        onClick={handleUrlFetch}
                        disabled={urlFetching || !pasteUrl.trim()}
                        data-testid="upload-url-fetch"
                        className="bg-volt hover:bg-volt-hover text-white font-barlow font-black uppercase tracking-widest text-xs px-4 py-2.5 flex items-center gap-2 disabled:opacity-50 transition-colors"
                      >
                        {urlFetching ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <LinkIcon className="w-3.5 h-3.5" />}
                        {urlFetching ? "Fetching" : "Fetch"}
                      </button>
                    </div>
                    <p className="text-[10px] text-ink/55 leading-relaxed">
                      Works with public YouTube, Vimeo, Veo and direct MP4/MOV links. Max 200 MB · max 5 min.
                    </p>
                  </div>
                )}

                <label
                  onDragOver={(e) => e.preventDefault()}
                  onDrop={(e) => {
                    e.preventDefault();
                    if (sourceMode === "file") handleFile(e.dataTransfer.files?.[0]);
                  }}
                  data-testid="upload-dropzone"
                  className={`block cursor-pointer border-2 border-dashed border-gray-border hover:border-volt bg-cream-soft p-6 md:p-8 text-center transition-colors ${
                    sourceMode === "url" && !file ? "opacity-60" : ""
                  }`}
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
                      <p className="font-barlow font-bold uppercase text-ink text-base break-all">{file.name}</p>
                      <p className="text-xs text-ink/55">{(file.size / 1024 / 1024).toFixed(1)} MB</p>
                      <button
                        type="button"
                        onClick={(e) => {
                          e.preventDefault();
                          setFile(null);
                          setVideoUrl(null);
                          setMarkerBlob(null);
                          setMarkerPreviewUrl(null);
                        }}
                        className="text-xs text-ink/65 hover:text-volt uppercase tracking-widest font-semibold mt-2"
                      >
                        Replace file
                      </button>
                    </div>
                  ) : (
                    <div className="flex flex-col items-center gap-3">
                      <UploadCloud className="w-11 h-11 text-volt" strokeWidth={1.25} />
                      <p className="font-barlow font-black uppercase text-ink text-lg">Drop video here</p>
                      <p className="text-xs text-ink/55">MP4, MOV or WebM · max 5 minutes</p>
                      <span className="mt-1 text-xs text-volt uppercase tracking-widest font-bold">or click to browse</span>
                      <p className="mt-3 text-[11px] text-ink/50 leading-relaxed max-w-[260px] text-center">
                        Tip: pick your child&apos;s best moments — scouts decide in the first 3 minutes. Quality beats quantity.
                      </p>
                    </div>
                  )}
                </label>
              </div>

              {/* ===== STEP 2: VIDEO + MARK PLAYER ===== */}
              <div className="bg-surface p-6 md:p-8 lg:col-span-3">
                <div className="flex items-center justify-between mb-3">
                  <span className="text-xs uppercase tracking-[0.2em] font-bold text-ink/55">Step 2 · Lock onto your player</span>
                  {markerBlob && <span className="text-[10px] uppercase tracking-widest font-bold text-volt flex items-center gap-1"><Check className="w-3 h-3" /> Locked</span>}
                </div>

                {!file ? (
                  <div className="aspect-video bg-cream-soft border border-gray-border flex flex-col items-center justify-center text-center p-6">
                    <Crosshair className="w-10 h-10 text-ink/30 mb-3" strokeWidth={1.25} />
                    <p className="text-sm text-ink/50 uppercase tracking-widest font-bold">Upload a video first</p>
                  </div>
                ) : (
                  <div className="space-y-3">
                    {/* Video + overlay (zoomable when marking) */}
                    <div
                      className="relative bg-black border border-gray-border overflow-hidden select-none"
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
                          // eslint-disable-next-line
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
                            onPointerDown={onOverlayPointerDown}
                            onPointerMove={onOverlayPointerMove}
                            onPointerUp={onOverlayPointerUp}
                            onPointerCancel={onOverlayPointerUp}
                            className="absolute inset-0 cursor-crosshair"
                            style={{
                              backgroundColor: "rgba(5, 10, 15, 0.18)",
                              touchAction: "none",
                            }}
                            data-testid="upload-mark-overlay"
                          >
                            {drawingBox && (
                              <>
                                {/* Dim everything outside the box for instant focus */}
                                <div className="absolute inset-0 pointer-events-none" style={{
                                  background: `
                                    linear-gradient(rgba(5,10,15,0.55), rgba(5,10,15,0.55))
                                  `,
                                  WebkitMaskImage: `
                                    linear-gradient(#000,#000),
                                    linear-gradient(#000,#000)
                                  `,
                                  WebkitMaskClip: "padding-box, padding-box",
                                  WebkitMaskComposite: "xor",
                                  maskComposite: "exclude",
                                }} />
                                {/* The visible box */}
                                <div
                                  className="absolute pointer-events-none"
                                  style={{
                                    left: drawingBox.x,
                                    top: drawingBox.y,
                                    width: drawingBox.w,
                                    height: drawingBox.h,
                                    boxShadow:
                                      "0 0 0 9999px rgba(5,10,15,0.55), 0 0 28px rgba(204,255,0,0.45) inset, 0 0 22px rgba(204,255,0,0.35)",
                                    border: "2px solid #CCFF00",
                                  }}
                                >
                                  {/* Corner ticks */}
                                  {["tl", "tr", "bl", "br"].map((corner) => {
                                    const base = {
                                      position: "absolute",
                                      width: 14,
                                      height: 14,
                                      borderColor: "#FFFFFF",
                                      borderStyle: "solid",
                                    };
                                    const map = {
                                      tl: { ...base, top: -1, left: -1, borderWidth: "2px 0 0 2px" },
                                      tr: { ...base, top: -1, right: -1, borderWidth: "2px 2px 0 0" },
                                      bl: { ...base, bottom: -1, left: -1, borderWidth: "0 0 2px 2px" },
                                      br: { ...base, bottom: -1, right: -1, borderWidth: "0 2px 2px 0" },
                                    };
                                    return <span key={corner} style={map[corner]} />;
                                  })}
                                  {/* LOCKED tag */}
                                  {drawingBox.w > 70 && drawingBox.h > 30 && (
                                    <span
                                      className="absolute text-[9px] uppercase tracking-widest font-black px-1.5 py-0.5"
                                      style={{
                                        top: -18,
                                        left: 0,
                                        background: "#CCFF00",
                                        color: "#050A0F",
                                      }}
                                    >
                                      LOCKED
                                    </span>
                                  )}
                                </div>
                              </>
                            )}
                          </div>
                        )}
                      </div>

                      {/* Static UI — NOT scaled */}
                      {isMarking && (
                        <>
                          <div className="pointer-events-none absolute top-3 left-3 right-3 flex items-center justify-between z-10">
                            <span className="pointer-events-auto bg-volt text-white text-[10px] uppercase tracking-widest font-black px-2 py-1 animate-pulse">
                              {markerBox ? "Confirm or redraw" : "Drag a box around your player"}
                            </span>
                            <button
                              type="button"
                              onClick={(e) => {
                                e.stopPropagation();
                                cancelMarking();
                              }}
                              data-testid="upload-mark-cancel"
                              className="pointer-events-auto bg-cream-card backdrop-blur text-ink text-[10px] uppercase tracking-widest font-bold px-2.5 py-1 border border-gray-border"
                            >
                              Cancel
                            </button>
                          </div>

                          {/* Confirm bar — appears once the user has finished drawing */}
                          {markerBox && (
                            <div className="pointer-events-none absolute bottom-3 left-3 z-20 flex items-center gap-2">
                              <button
                                type="button"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  confirmMarkerBox();
                                }}
                                data-testid="upload-mark-confirm"
                                className="pointer-events-auto bg-volt hover:bg-volt/90 text-white font-barlow font-black uppercase tracking-widest text-[11px] px-3 py-2 flex items-center gap-1.5 transition-colors"
                              >
                                <Check className="w-3.5 h-3.5" /> Lock player
                              </button>
                              <button
                                type="button"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  setMarkerBox(null);
                                  setDrawingBox(null);
                                }}
                                data-testid="upload-mark-redraw"
                                className="pointer-events-auto bg-cream-card/95 backdrop-blur text-ink text-[10px] uppercase tracking-widest font-bold px-2.5 py-2 border border-gray-border flex items-center gap-1"
                              >
                                <RefreshCw className="w-3 h-3" /> Redraw
                              </button>
                            </div>
                          )}

                          {/* Zoom controls */}
                          <div className="pointer-events-none absolute bottom-3 right-3 z-10 flex items-center gap-1.5">
                            <div className="pointer-events-auto flex items-center bg-cream-card backdrop-blur-sm border border-gray-border">
                              <button
                                type="button"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  zoomOut();
                                }}
                                disabled={zoom <= 1.01}
                                data-testid="upload-zoom-out"
                                className="w-9 h-9 flex items-center justify-center text-ink hover:text-volt disabled:opacity-30 disabled:cursor-not-allowed transition-colors border-r border-gray-border"
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
                                className="w-9 h-9 flex items-center justify-center text-ink hover:text-volt disabled:opacity-30 disabled:cursor-not-allowed transition-colors border-l border-gray-border"
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
                                className="pointer-events-auto w-9 h-9 flex items-center justify-center text-ink hover:text-volt bg-cream-card backdrop-blur-sm border border-gray-border transition-colors"
                                aria-label="Reset zoom"
                              >
                                <Maximize2 className="w-4 h-4" />
                              </button>
                            )}
                          </div>

                          {/* Hint when zoomed */}
                          {zoom > 1.01 && (
                            <div className="pointer-events-none absolute bottom-3 left-3 z-10">
                              <span className="bg-cream-card backdrop-blur-sm text-ink/80 text-[9px] uppercase tracking-widest font-bold px-2 py-1 border border-gray-border">
                                Drag to pan · Tap player when ready
                              </span>
                            </div>
                          )}
                        </>
                      )}
                    </div>

                    {!isMarking && !markerBlob && (
                      <div className="bg-cream-card/90 border border-volt/30 p-3 flex flex-col sm:flex-row gap-3 items-start sm:items-center justify-between">
                        <div className="flex items-start gap-2.5 text-sm text-ink/80">
                          <AlertCircle className="w-4 h-4 text-volt mt-0.5 flex-shrink-0" />
                          <span>
                            Scrub to the clearest moment of your player, then{" "}
                            <span className="text-volt font-bold">drag a box around them</span> — head to feet.
                            <span className="text-ink/60"> Pinch to zoom for tight precision.</span>
                          </span>
                        </div>
                        <button
                          type="button"
                          onClick={startMarking}
                          data-testid="upload-mark-start"
                          className="flex-shrink-0 bg-volt hover:bg-forest-pop text-white font-barlow font-black uppercase tracking-widest text-xs px-4 py-2.5 transition-colors flex items-center gap-2"
                        >
                          <Crosshair className="w-3.5 h-3.5" />
                          Lock onto your player
                        </button>
                      </div>
                    )}

                    {markerBlob && markerPreviewUrl && (
                      <div className="bg-cream-card/90 border border-volt/30 p-3">
                        <div className="flex items-center justify-between mb-2">
                          <span className="text-[10px] uppercase tracking-widest font-bold text-volt flex items-center gap-1.5">
                            <Check className="w-3 h-3" /> Player locked
                          </span>
                          <button
                            type="button"
                            onClick={reMark}
                            data-testid="upload-mark-redo"
                            className="text-ink/65 hover:text-volt text-[10px] uppercase tracking-widest font-bold flex items-center gap-1 transition-colors"
                          >
                            <RefreshCw className="w-3 h-3" /> Re-mark
                          </button>
                        </div>
                        <img
                          src={markerPreviewUrl}
                          alt="Locked player"
                          data-testid="upload-mark-preview"
                          className="w-full aspect-video object-contain bg-black border border-gray-border"
                        />
                        <p className="mt-2 text-[11px] text-ink/55 text-center">
                          We&apos;ll analyse <span className="text-volt font-bold">only the player inside the box</span>.
                        </p>
                      </div>
                    )}
                  </div>
                )}
              </div>
            </div>

            {/* ===== STEP 3: PLAYER DETAILS ===== */}
            <div className="bg-surface border border-gray-border p-6 md:p-8 space-y-5">
              <span className="text-xs uppercase tracking-[0.2em] font-bold text-ink/55">Step 3 · Player details</span>

              <div className="grid sm:grid-cols-2 gap-4">
                <div>
                  <label className="text-xs uppercase tracking-[0.2em] font-bold text-ink/55 block mb-2">Player name *</label>
                  <input
                    required
                    type="text"
                    value={form.player_name}
                    onChange={(e) => setField("player_name", e.target.value)}
                    data-testid="upload-player-name"
                    className="w-full bg-deepnavy border border-gray-border px-3 py-3 text-ink focus:outline-none focus:border-volt focus:ring-1 focus:ring-volt"
                    placeholder="e.g. Lukas Andersen"
                  />
                </div>
                <div>
                  <label className="text-xs uppercase tracking-[0.2em] font-bold text-ink/55 block mb-2">Age *</label>
                  <input
                    required
                    type="number"
                    min="5"
                    max="50"
                    value={form.age}
                    onChange={(e) => setField("age", e.target.value)}
                    data-testid="upload-player-age"
                    className="w-full bg-deepnavy border border-gray-border px-3 py-3 text-ink focus:outline-none focus:border-volt focus:ring-1 focus:ring-volt"
                    placeholder="14"
                  />
                </div>
              </div>

              <div className="grid sm:grid-cols-2 gap-4">
                <div>
                  <label className="text-xs uppercase tracking-[0.2em] font-bold text-ink/55 block mb-2">Position *</label>
                  <select
                    required
                    value={form.position}
                    onChange={(e) => setField("position", e.target.value)}
                    data-testid="upload-player-position"
                    className="w-full bg-deepnavy border border-gray-border px-3 py-3 text-ink focus:outline-none focus:border-volt focus:ring-1 focus:ring-volt"
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
                  <label className="text-xs uppercase tracking-[0.2em] font-bold text-ink/55 block mb-2">Preferred foot *</label>
                  <select
                    required
                    value={form.preferred_foot}
                    onChange={(e) => setField("preferred_foot", e.target.value)}
                    data-testid="upload-player-foot"
                    className="w-full bg-deepnavy border border-gray-border px-3 py-3 text-ink focus:outline-none focus:border-volt focus:ring-1 focus:ring-volt"
                  >
                    <option value="right">Right</option>
                    <option value="left">Left</option>
                    <option value="both">Both</option>
                  </select>
                </div>
              </div>

              <div className="grid sm:grid-cols-2 gap-4">
                <div>
                  <label className="text-xs uppercase tracking-[0.2em] font-bold text-ink/55 block mb-2">Current club / team</label>
                  <input
                    type="text"
                    value={form.current_club}
                    onChange={(e) => setField("current_club", e.target.value)}
                    data-testid="upload-player-club"
                    className="w-full bg-deepnavy border border-gray-border px-3 py-3 text-ink focus:outline-none focus:border-volt focus:ring-1 focus:ring-volt"
                    placeholder="Optional"
                  />
                </div>
                <div>
                  <label className="text-xs uppercase tracking-[0.2em] font-bold text-ink/55 block mb-2">Video type *</label>
                  <select
                    value={form.video_type}
                    onChange={(e) => setField("video_type", e.target.value)}
                    data-testid="upload-video-type"
                    className="w-full bg-deepnavy border border-gray-border px-3 py-3 text-ink focus:outline-none focus:border-volt focus:ring-1 focus:ring-volt"
                  >
                    <option value="highlight">Highlight reel</option>
                    <option value="match">Match clip</option>
                    <option value="training">Training clip</option>
                  </select>
                </div>
              </div>

              <div>
                <label className="text-xs uppercase tracking-[0.2em] font-bold text-ink/55 block mb-2">Which player are you in the video? *</label>
                <textarea
                  required
                  value={form.description}
                  onChange={(e) => setField("description", e.target.value)}
                  data-testid="upload-player-description"
                  rows={3}
                  className="w-full bg-deepnavy border border-gray-border px-3 py-3 text-ink focus:outline-none focus:border-volt focus:ring-1 focus:ring-volt resize-none"
                  placeholder="e.g. I am number 10 in the white shirt — the one you just marked above."
                />
              </div>

              <button
                type="submit"
                disabled={submitting || !file || !markerBlob}
                data-testid="upload-submit-btn"
                className="w-full bg-volt hover:bg-forest-pop text-white font-barlow font-black uppercase tracking-widest text-base px-8 py-4 transition-colors disabled:opacity-40 disabled:cursor-not-allowed flex items-center justify-center gap-3 mt-2"
              >
                {submitting ? (
                  <>
                    <Loader2 className="w-5 h-5 animate-spin" />
                    Locking on · tracking · analysing
                  </>
                ) : !file ? (
                  "Upload a video first"
                ) : !markerBlob ? (
                  "Lock onto your player first"
                ) : (
                  <>
                    Start precision scan
                    <ArrowRight className="w-5 h-5" />
                  </>
                )}
              </button>
              <p className="text-xs text-ink/50 text-center">
                The AI locks onto the player in your box and tracks <span className="text-volt font-bold">only them</span>. Other players are ignored.
              </p>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}
