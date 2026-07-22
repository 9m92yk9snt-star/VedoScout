import React, { useState, useRef, useEffect } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import Navigation from "@/components/Navigation";
import CheckoutTransitionModal from "@/components/CheckoutTransitionModal";
import EmbeddedCheckoutModal from "@/components/EmbeddedCheckoutModal";
import PaymentBadges from "@/components/PaymentBadges";
import PrecisionScanOverlay from "@/components/PrecisionScanOverlay";
import { startBackgroundAnalysis } from "@/components/BackgroundAnalysisTracker";
import MarkerStudio from "@/components/MarkerStudio";
import HeroTeaser from "@/components/HeroTeaser";
import PremiumReadyOverlay from "@/components/PremiumReadyOverlay";
import { useAuth } from "@/lib/auth-context";
import { isPremiumUser } from "@/lib/premium";

const ASSET_BASE = process.env.REACT_APP_BACKEND_URL || "";
import api from "@/lib/api";
import { UploadCloud, Film, Loader2, ArrowRight, Crosshair, Check, RefreshCw, AlertCircle, Lock, Zap, Link as LinkIcon, FileUp } from "lucide-react";

export default function UploadPage() {
  const { user } = useAuth();
  const isPaidTier = isPremiumUser(user);
  const [searchParams, setSearchParams] = useSearchParams();
  const [eligibility, setEligibility] = useState(null);   // { eligible, reason, free_preview_used, prepaid_uploads }
  const [eligibilityLoading, setEligibilityLoading] = useState(true);
  const [prepaying, setPrepaying] = useState(false);
  const [price, setPrice] = useState(null);

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
  const [markerBox, setMarkerBox] = useState(null);
  // Fullscreen MarkerStudio sheet — replaces the old inline overlay
  const [studioOpen, setStudioOpen] = useState(false);

  // ── URL-paste mode ────────────────────────────────────────────────────
  const [sourceMode, setSourceMode] = useState("file"); // "file" | "url"
  const [pasteUrl, setPasteUrl] = useState("");
  const [urlFetching, setUrlFetching] = useState(false);
  const [tempVideoToken, setTempVideoToken] = useState(null);

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
  const [uploadPct, setUploadPct] = useState(0);            // 0–100 — XHR.upload.onprogress
  const [backendStep, setBackendStep] = useState(0);        // 1–5 real backend progress_step
  const [uploadPhase, setUploadPhase] = useState("idle");   // 'uploading' | 'analyzing' | 'done'
  const [heroReport, setHeroReport] = useState(null);       // populated to trigger HeroTeaser (free-tier)
  const [premiumReadyReport, setPremiumReadyReport] = useState(null); // Session 130 — premium-tier celebration screen
  // Holds the completed upload response while the "done" celebration is on
  // screen so the CTA on PrecisionScanOverlay can short-circuit the 1.8 s hold.
  const pendingDoneRef = useRef(null);
  // Flag set when the user clicks "Continue in background" — breaks the local
  // poll loop in handleSubmit so the global BackgroundAnalysisTracker can take
  // over and the user is free to navigate away.
  const backgroundedRef = useRef(false);

  const fileRef = useRef(null);
  const videoRef = useRef(null);
  const navigate = useNavigate();

  const setField = (k, v) => setForm((prev) => ({ ...prev, [k]: v }));

  // Fetch upload eligibility on mount + after returning from Stripe checkout
  const refreshEligibility = async () => {
    try {
      const { data } = await api.get("/me/upload-eligibility");
      setEligibility(data);
      // Tier-aware price for one extra report — matches what Stripe charges
      // (single_price for free users, premium/vip extra rate for subscribers).
      if (data?.extra_report_price) setPrice(Number(data.extra_report_price));
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
    api.get("/settings/price").then(({ data }) => {
      // Fallback only — eligibility's tier-aware extra_report_price wins
      setPrice((p) => p ?? (Number(data.single_price) || 129));
    }).catch(() => {});
  }, []);
  /* eslint-enable */

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

  // (Marker-overlay zoom/pan removed — fullscreen MarkerStudio now owns all gestures.)

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
    // Files above ~80 MB are sent as ≤24 MB chunks (see chunkedUpload below)
    // to bypass the Cloudflare/ingress ~100 MB request-body cap. The hard
    // ceiling is now 500 MB (matches the backend chunked-upload cap).
    const MAX_UPLOAD_BYTES = 500 * 1024 * 1024; // 500 MB
    if (f.size > MAX_UPLOAD_BYTES) {
      const sizeMb = (f.size / 1024 / 1024).toFixed(0);
      toast.error(
        `Video is ${sizeMb} MB — our upload limit is 500 MB. Trim the clip (max 5 min) and try again. Tip: iPhone → Settings › Camera › Record Video → 1080p HD at 30 fps.`,
        { duration: 12000 },
      );
      return;
    }
    if (videoUrl) URL.revokeObjectURL(videoUrl);
    if (markerPreviewUrl) URL.revokeObjectURL(markerPreviewUrl);
    setFile(f);
    setVideoUrl(URL.createObjectURL(f));
    setMarkerBlob(null);
    setMarkerPreviewUrl(null);
    setMarkerTimestamp(0);
    setMarkerBox(null);
    setStudioOpen(false);
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
      setMarkerBox(null);
      setStudioOpen(false);
      toast.success(`Video fetched (${(data.size_mb || 0).toFixed(1)} MB) — now mark your player.`);
    } catch (err) {
      const msg = err?.response?.data?.detail || err.message || "URL fetch failed.";
      // Veo errors are longer than usual — give the user enough time to read.
      const isLongMsg = typeof msg === "string" && msg.length > 80;
      toast.error(typeof msg === "string" ? msg : "Could not download that video.", {
        duration: isLongMsg ? 12000 : 5000,
      });
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

  /* ── MarkerStudio handoff ────────────────────────────────── */
  const [markerAnchors, setMarkerAnchors] = useState(null);
  const handleStudioConfirm = ({ markerBlob: blob, markerTimestamp: ts, markerBox: nbox, markerAnchors: anchors }) => {
    if (markerPreviewUrl) URL.revokeObjectURL(markerPreviewUrl);
    setMarkerBlob(blob);
    setMarkerPreviewUrl(URL.createObjectURL(blob));
    setMarkerTimestamp(ts || 0);
    setMarkerBox(nbox || null);
    setMarkerAnchors(anchors && anchors.length ? anchors : null);
    setStudioOpen(false);
    const count = anchors?.length || 1;
    toast.success(
      count > 1
        ? `${count} anchors locked. Pro Scout Intelligence will track this exact player across the whole clip.`
        : "Player locked. We'll analyse only the player in the box.",
    );
  };

  const reMark = () => {
    if (markerPreviewUrl) URL.revokeObjectURL(markerPreviewUrl);
    setMarkerBlob(null);
    setMarkerPreviewUrl(null);
    setMarkerTimestamp(0);
    setMarkerBox(null);
    setStudioOpen(true);
  };

  // ── Chunked upload — bypasses the Cloudflare/ingress ~100 MB body cap ──
  // Slices the file into ≤24 MB chunks, then assembles server-side into a
  // temp video consumed via the existing `temp_video_token` upload path.
  const CHUNK_SIZE = 24 * 1024 * 1024;
  const DIRECT_LIMIT = 80 * 1024 * 1024; // ≤80 MB still goes as one request

  const chunkedUpload = async (f) => {
    const initFd = new FormData();
    initFd.append("filename", f.name || "video.mp4");
    initFd.append("total_size", String(f.size));
    const { data: init } = await api.post("/me/chunked-upload/init", initFd);
    const total = Math.ceil(f.size / CHUNK_SIZE);
    let sent = 0;
    for (let i = 0; i < total; i++) {
      const blob = f.slice(i * CHUNK_SIZE, Math.min(f.size, (i + 1) * CHUNK_SIZE));
      const cfd = new FormData();
      cfd.append("upload_id", init.upload_id);
      cfd.append("index", String(i));
      cfd.append("chunk", blob, `part_${i}`);
      await api.post("/me/chunked-upload/chunk", cfd, {
        timeout: 300000,
        onUploadProgress: (ev) => {
          const done = sent + (ev.loaded || 0);
          setUploadPct(Math.min(99, Math.round((done * 100) / f.size)));
        },
      });
      sent += blob.size;
    }
    const doneFd = new FormData();
    doneFd.append("upload_id", init.upload_id);
    doneFd.append("total_chunks", String(total));
    const { data: fin } = await api.post("/me/chunked-upload/complete", doneFd, { timeout: 300000 });
    return fin.token;
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
    } else if (file.size > DIRECT_LIMIT) {
      // Large file → chunked upload first, then submit only the token.
      setUploadPhase("uploading");
      setUploadPct(0);
      let chunkToken = null;
      try {
        chunkToken = await chunkedUpload(file);
      } catch (err) {
        const msg = err?.response?.data?.detail || "Upload failed while sending the video. Please check your connection and try again.";
        toast.error(typeof msg === "string" ? msg : "Upload failed. Please try again.");
        setSubmitting(false);
        setUploadPhase("idle");
        return;
      }
      fd.append("temp_video_token", chunkToken);
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
    if (markerAnchors && markerAnchors.length) {
      fd.append(
        "marker_anchors",
        JSON.stringify(
          markerAnchors.map((a) => ({
            t: Number((a.t || 0).toFixed(2)),
            box: {
              x: Number(a.box.x.toFixed(4)),
              y: Number(a.box.y.toFixed(4)),
              w: Number(a.box.w.toFixed(4)),
              h: Number(a.box.h.toFixed(4)),
            },
            thumb: a.thumb || undefined,
          })),
        ),
      );
    }
    Object.entries(form).forEach(([k, v]) => {
      if (v !== "" && v !== null && v !== undefined) fd.append(k, String(v));
    });

    try {
      setUploadPct(0);
      setUploadPhase("uploading");
      const { data } = await api.post("/reports/upload", fd, {
        headers: { "Content-Type": "multipart/form-data" },
        timeout: 600000,
        onUploadProgress: (ev) => {
          if (ev.total) {
            const pct = Math.min(100, Math.round((ev.loaded * 100) / ev.total));
            setUploadPct(pct);
            if (pct >= 100) setUploadPhase("analyzing");
          }
        },
      });

      // ====== ASYNC PIPELINE — poll the status endpoint for real backend progress. ======
      // The upload endpoint now returns IMMEDIATELY (~30s) with analysis_status="analyzing"
      // while the two slow Gemini calls (content gate + preview generation) run as a
      // background task on the server. We poll /reports/{id}/status every 3s until
      // status === "ready" (success) or "failed" (rejected/error).
      let finalData = data;
      if (data?.analysis_status === "analyzing") {
        const start = Date.now();
        const MAX_WAIT_MS = 10 * 60 * 1000; // 10 minute hard ceiling
        backgroundedRef.current = false;
        // poll loop
        // eslint-disable-next-line no-constant-condition
        while (true) {
          // User clicked "Continue in background" → hand off to the global tracker.
          if (backgroundedRef.current) {
            startBackgroundAnalysis(data.id);
            setSubmitting(false);
            setUploadPhase("idle");
            toast.success("We'll let you know when your report is ready.", {
              duration: 4500,
            });
            navigate("/dashboard");
            return;
          }
          if (Date.now() - start > MAX_WAIT_MS) {
            startBackgroundAnalysis(data.id);
            toast.error("Your report is taking longer than expected. We've saved it — check your Dashboard in a minute.");
            navigate(`/dashboard`);
            return;
          }
          await new Promise((r) => setTimeout(r, 3000));
          try {
            const { data: statusResp } = await api.get(`/reports/${data.id}/status`);
            setUploadPhase("analyzing");
            // Feed the REAL backend progress into the overlay so the ladder
            // reflects reality (instead of the old client-side wall-clock lie
            // that jumped to step 5 in 36 s even when backend was still at 2).
            if (typeof statusResp.progress_step === "number") {
              setBackendStep(statusResp.progress_step);
              setUploadPct(Math.min(100, Math.round((statusResp.progress_step / 5) * 100)));
            }
            if (statusResp.status === "failed") {
              const errMsg = statusResp.error || "Analysis failed. Please try again or upload a clearer clip.";
              toast.error(errMsg);
              setUploadPhase("idle");
              return;
            }
            if (statusResp.status === "ready") {
              finalData = { ...data, ...statusResp };
              break;
            }
          } catch (pollErr) {
            // Transient network blips — keep polling. Hard 4xx/5xx will surface above.
            // eslint-disable-next-line no-console
            console.warn("status poll failed (will retry):", pollErr?.message);
          }
        }
      }

      setUploadPhase("done");
      // Remember the response so the CTA on the success overlay can fire it
      // straight away (otherwise we wait ~1.8 s for the celebration to land).
      // Session 127 — Premium tier users (admin/premium/vip/scout) NEVER see
      // the HeroTeaser paywall modal ("Unlock the full report — $159"). It's
      // reserved for free users only. Their reason may not be "prepaid" but
      // they still have full access via their role. Bundle the check into the
      // ref so both the timer-driven path AND the manual "View report" click
      // route them straight to the premium celebration screen.
      // Subscription-based premium (reason "subscription") and any report the
      // backend already marked paid must ALSO bypass the free-tier HeroTeaser.
      const skipHeroTeaser =
        isPaidTier ||
        eligibility?.reason === "prepaid" ||
        eligibility?.reason === "subscription" ||
        !!finalData?.is_paid;
      pendingDoneRef.current = { data: finalData, skipHeroTeaser };
      await new Promise((r) => setTimeout(r, 1800));
      if (!pendingDoneRef.current) return;
      pendingDoneRef.current = null;
      if (!skipHeroTeaser) {
        // Free-tier flow: HeroTeaser (blur + PricingCards) — modal navigates on dismiss.
        setHeroReport(finalData);
        return;
      }
      // Session 130 — Premium-tier flow: dedicated PremiumReadyOverlay
      // celebration screen. NO blur, NO pricing, NO upgrade prompts.
      setPremiumReadyReport(finalData);
    } catch (err) {
      // 402 with structured detail = pre-pay required
      const detail = err?.response?.data?.detail;
      const status = err?.response?.status;
      // 413 Request Entity Too Large — a URL-fetched video slipped past the
      // client-side guard (direct uploads >80 MB now go through chunking).
      if (status === 413) {
        toast.error(
          "That clip is too large for a single request. Please use the Upload File tab — large files are sent in chunks automatically.",
          { duration: 12000 },
        );
      } else if (status === 402 && (detail?.code === "PREPAY_REQUIRED" || typeof detail === "object")) {
        toast.info(detail?.message || `Pay $${price} to upload your next video.`);
        await refreshEligibility();
      } else {
        toast.error(
          (typeof detail === "string" ? detail : detail?.message) || "Upload failed. Please try again."
        );
      }
      setUploadPhase("idle");
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
      <PrecisionScanOverlay
        open={submitting && !heroReport && !premiumReadyReport}
        phase={uploadPhase === "uploading" ? "uploading" : uploadPhase === "done" ? "done" : "analyzing"}
        uploadPct={uploadPct}
        backendStep={backendStep}
        hideTimers={isPaidTier}
        onContinueInBackground={() => {
          // Set the flag — the poll loop in handleSubmit will detect it on its next
          // tick, hand off to startBackgroundAnalysis(), close the overlay, and
          // navigate the user to /dashboard.
          backgroundedRef.current = true;
        }}
        onViewReport={() => {
          const pending = pendingDoneRef.current;
          if (!pending) return;
          pendingDoneRef.current = null;
          if (!pending.skipHeroTeaser) {
            // Free preview: show the HeroTeaser (mirrors the timer-driven path).
            setHeroReport(pending.data);
          } else {
            // Session 130 — Premium celebration screen instead of instant nav.
            setPremiumReadyReport(pending.data);
          }
        }}
      />
      <HeroTeaser
        open={!!heroReport}
        report={heroReport}
        assetBase={ASSET_BASE}
        onUnlock={() => {
          if (heroReport?.id) {
            navigate(`/report/${heroReport.id}?unlock=1`);
          }
        }}
        onDismiss={() => {
          setHeroReport(null);
          if (heroReport?.id) navigate(`/report/${heroReport.id}`);
        }}
      />
      {/* Session 130 — Premium-tier celebration overlay. Deliberately separate
          from HeroTeaser (which is the free-tier paywall). Zero blur, zero
          pricing, single "Open Full Premium Report" CTA that navigates to the
          full dossier where the auto-gen useEffect kicks in. */}
      <PremiumReadyOverlay
        open={!!premiumReadyReport}
        report={premiumReadyReport}
        assetBase={ASSET_BASE}
        onOpenReport={() => {
          const target = premiumReadyReport?.id;
          setPremiumReadyReport(null);
          if (target) navigate(`/report/${target}`);
        }}
        onDismiss={() => {
          setPremiumReadyReport(null);
          navigate("/dashboard");
        }}
      />
      <MarkerStudio
        open={studioOpen}
        videoUrl={videoUrl}
        videoFile={file && !file._fromUrl ? file : null}
        initialTimestamp={
          videoRef.current ? (videoRef.current.currentTime || 0) : (markerTimestamp || 0)
        }
        onConfirm={handleStudioConfirm}
        onCancel={() => setStudioOpen(false)}
      />

      <div className="pt-28 pb-16 px-6">
        <div className="max-w-5xl mx-auto">
          <div className="mb-10">
            <span className="text-volt text-xs uppercase tracking-[0.25em] font-bold">Step 01</span>
            <h1 className="mt-3 font-barlow font-black uppercase text-4xl md:text-5xl tracking-tighter leading-[0.95]" data-testid="upload-title">
              Upload your video & lock onto your player
            </h1>
            <p className="mt-3 text-ink/65 max-w-2xl text-sm md:text-base">
              Upload the clip, scrub to the clearest moment, then drag a box around your player — head to feet. Our Pro Scout Intelligence locks onto their jersey, shorts, and body, and follows only that player through the video.
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
                        placeholder="Vimeo · Google Drive · .mp4 link"
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
                      Best with Vimeo, Google Drive shared links or any direct .mp4 / .mov URL.
                      <span className="block mt-1 text-forest font-bold">
                        Veo &amp; YouTube links can&apos;t be fetched directly — download the clip to your device, then use &ldquo;Upload File&rdquo; above.
                      </span>
                      Max 500 MB · max 5 min.
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
                    {/* Compact preview — review your clip, then open the full studio */}
                    <div className="relative bg-black border border-gray-border overflow-hidden">
                      <video
                        ref={videoRef}
                        src={videoUrl}
                        controls
                        playsInline
                        preload="metadata"
                        onLoadedMetadata={handleVideoLoadedMetadata}
                        data-testid="upload-video-preview"
                        className="w-full aspect-video bg-black"
                      />
                    </div>

                    {!markerBlob && (
                      <div className="bg-cream-card/90 border border-volt/30 p-3 flex flex-col sm:flex-row gap-3 items-start sm:items-center justify-between">
                        <div className="flex items-start gap-2.5 text-sm text-ink/80">
                          <AlertCircle className="w-4 h-4 text-volt mt-0.5 flex-shrink-0" />
                          <span>
                            Open the <span className="text-volt font-bold">Marker Studio</span> for a fullscreen view: pinch-zoom on your player, drag a box around them, or tap <span className="text-volt font-bold">Auto-find</span> to detect every player on the field.
                          </span>
                        </div>
                        <button
                          type="button"
                          onClick={() => setStudioOpen(true)}
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
                    <option value="highlight">Highlight reel — best moments from real games</option>
                    <option value="match">Match clip — live game footage (1v1 / 5v5 / full game)</option>
                    <option value="training">Training clip — passing rondos, possession drills</option>
                    <option value="drill">Drills — cones, agility, ball-mastery, technical work</option>
                    <option value="freestyle">Freestyle — solo ball-juggling / tricks</option>
                  </select>
                  {/* Tiny helper so the user understands how this affects the scout report. */}
                  <p className="mt-1.5 text-[10.5px] text-ink/55 leading-snug">
                    {form.video_type === "highlight" && "We'll judge game IQ + finishing — best moments only, expect short evidence."}
                    {form.video_type === "match" && "We'll judge tactical decisions, duels, off-ball runs and game-pace technique."}
                    {form.video_type === "training" && "We'll judge passing weight, body shape and decision-making vs teammates."}
                    {form.video_type === "drill" && "We'll judge ball mastery, body shape and rep consistency — NO match-action commentary."}
                    {form.video_type === "freestyle" && "We'll judge ball control and creativity only — no tactical scoring."}
                  </p>
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
                Pro Scout Intelligence locks onto the player in your box and tracks <span className="text-volt font-bold">only them</span>. Other players are ignored.
              </p>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}
