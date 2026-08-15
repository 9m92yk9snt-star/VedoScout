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
import AccountGateModal from "@/components/auth/AccountGateModal";
import PremiumReadyOverlay from "@/components/PremiumReadyOverlay";
import { useAuth } from "@/lib/auth-context";
import { isPremiumUser } from "@/lib/premium";

const ASSET_BASE = process.env.REACT_APP_BACKEND_URL || "";
import api from "@/lib/api";
import { trackFunnel } from "@/lib/analytics";
import { UploadCloud, Film, Loader2, ArrowRight, Crosshair, Check, RefreshCw, AlertCircle, Lock, Zap, Link as LinkIcon, FileUp, ShieldCheck, Clock, FileText, Lightbulb, Play, Maximize2, User, Calendar, Shirt, Hash, Video, Heart, Footprints, TrendingUp, CheckCircle2, Rocket, ZoomIn, ScanSearch, EyeOff, LocateFixed, Globe, Camera, ChevronsUpDown, X as XIcon } from "lucide-react";
import { COUNTRIES } from "@/lib/countries";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from "@/components/ui/command";

const LIME = "#ccff00";

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
    jersey_number: "",
    country: "",
    video_type: "match",
    description: "",
  });
  // ── Step 3 required player photo (upload OR the locked video image) ──
  const [playerPhoto, setPlayerPhoto] = useState(null); // { dataUrl } — compressed ≤512px JPEG
  const [photoSource, setPhotoSource] = useState(null); // 'upload' | 'video_crop'
  const [featureConsent, setFeatureConsent] = useState(false); // optional social-feature consent (GDPR: never required)
  const [countryOpen, setCountryOpen] = useState(false);
  const photoInputRef = useRef(null);
  const [submitting, setSubmitting] = useState(false);
  const [uploadPct, setUploadPct] = useState(0);            // 0–100 — XHR.upload.onprogress
  const [backendStep, setBackendStep] = useState(0);        // 1–5 real backend progress_step
  const [uploadPhase, setUploadPhase] = useState("idle");   // 'uploading' | 'analyzing' | 'done'
  const [premiumReadyReport, setPremiumReadyReport] = useState(null); // Session 130 — premium-tier celebration screen
  const [howOpen, setHowOpen] = useState(false); // Step 2 "How it works" inline explainer
  const [videoMeta, setVideoMeta] = useState(null); // { duration, width, height } — smart summary card
  const [profiles, setProfiles] = useState([]); // Stage 5 — saved player identity profiles
  // Holds the completed upload response while the "done" celebration is on
  // screen so the CTA on PrecisionScanOverlay can short-circuit the 1.8 s hold.
  const pendingDoneRef = useRef(null);
  // Flag set when the user clicks "Go to Dashboard" — breaks the local
  // poll loop in handleSubmit so the global BackgroundAnalysisTracker can take
  // over and the user is free to navigate away.
  const backgroundedRef = useRef(false);
  // The report id from the upload response — lets the Go-to-Dashboard handler
  // hand off to the background tracker immediately (no poll-tick dependency).
  const reportIdRef = useRef(null);

  // ── Guest-first flow (Session 144) — upload first, account right before analysis ──
  const [gateOpen, setGateOpen] = useState(false);
  const [bgUpload, setBgUpload] = useState({ status: "idle", pct: 0, token: null });
  const bgUploadRef = useRef(null);

  const fileRef = useRef(null);
  const videoRef = useRef(null);
  const navigate = useNavigate();

  const setField = (k, v) => setForm((prev) => ({ ...prev, [k]: v }));

  /* ── Player photo helpers — compress to ≤512px JPEG so it's small enough
     for FormData AND sessionStorage (Google sign-in round trip). ── */
  const compressPhoto = (f) => new Promise((resolve, reject) => {
    const img = new Image();
    const url = URL.createObjectURL(f);
    img.onload = () => {
      try {
        const maxSide = 512;
        const scale = Math.min(1, maxSide / Math.max(img.width, img.height));
        const c = document.createElement("canvas");
        c.width = Math.round(img.width * scale);
        c.height = Math.round(img.height * scale);
        c.getContext("2d").drawImage(img, 0, 0, c.width, c.height);
        URL.revokeObjectURL(url);
        resolve(c.toDataURL("image/jpeg", 0.85));
      } catch (err) { URL.revokeObjectURL(url); reject(err); }
    };
    img.onerror = () => { URL.revokeObjectURL(url); reject(new Error("bad image")); };
    img.src = url;
  });

  const handlePhotoFile = async (f) => {
    if (!f) return;
    if (!/^image\//.test(f.type)) {
      toast.error("Please choose an image file (JPG, PNG, HEIC…).");
      return;
    }
    try {
      const dataUrl = await compressPhoto(f);
      setPlayerPhoto({ dataUrl });
      setPhotoSource("upload");
      toast.success("Player photo added.");
    } catch (_) {
      toast.error("Couldn't read that image — try another photo.");
    }
  };

  // Stage 5 — saved players on this account (identity memory) for one-tap pre-fill
  useEffect(() => {
    let alive = true;
    api.get("/me/player-profiles")
      .then(({ data }) => { if (alive) setProfiles(data?.profiles || []); })
      .catch(() => {});
    return () => { alive = false; };
  }, []);

  const applyProfile = (p) => {
    setForm((prev) => ({
      ...prev,
      player_name: p.player_name || "",
      age: p.age != null ? String(p.age) : "",
      position: p.position || "",
      preferred_foot: p.preferred_foot || "right",
      current_club: p.current_club && p.current_club !== "Independent" ? p.current_club : "",
      jersey_number: p.jersey_number || "",
    }));
    toast.success(`Details filled from ${p.player_name}'s profile — the scout also remembers how ${p.player_name} looks.`);
  };

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
    trackFunnel("upload_started");
    setMarkerBlob(null);
    setMarkerPreviewUrl(null);
    setMarkerTimestamp(0);
    setMarkerBox(null);
    setStudioOpen(false);
    setTempVideoToken(null); // clear any prior URL-fetch
    setVideoMeta(null);
    startBgUpload(f); // Session 144 — upload starts NOW, hidden behind marking + details
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
      setVideoMeta(null);
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
      setVideoMeta({
        duration: Number.isFinite(video.duration) && video.duration > 0 ? video.duration : null,
        width: video.videoWidth || null,
        height: video.videoHeight || null,
      });
    } catch (_) { /* ignore */ }
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
    trackFunnel("player_tapped");
    const count = anchors?.length || 1;
    toast.success(
      count > 1
        ? `${count} anchors locked. ScoutMe Pro Intelligence will track this exact player across the whole clip.`
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
  // Slices the file into ≤8 MB chunks, then assembles server-side into a
  // temp video consumed via the existing `temp_video_token` upload path.
  // Small chunks + per-request RETRY make mobile (5G/4G) uploads survive
  // transient drops and strict production proxy timeouts.
  const CHUNK_SIZE = 8 * 1024 * 1024;
  const DIRECT_LIMIT = 12 * 1024 * 1024; // ≤12 MB still goes as one request

  // Retry transient failures: network drops (no response), gateway timeouts
  // and 5xx. Never retries real 4xx rejections (413 too large, 403, ...).
  const postRetry = async (url, fd, cfg = {}, attempts = 4) => {
    let wait = 1500;
    for (let a = 1; ; a++) {
      try {
        return await api.post(url, fd, cfg);
      } catch (err) {
        const st = err?.response?.status;
        const retriable = !err?.response || st === 408 || st === 425 || st === 429 || st >= 500;
        if (!retriable || a >= attempts) throw err;
        await new Promise((r) => setTimeout(r, wait));
        wait *= 2;
      }
    }
  };

  const chunkedUpload = async (f, onPct = (p) => setUploadPct(p)) => {
    const initFd = new FormData();
    initFd.append("filename", f.name || "video.mp4");
    initFd.append("total_size", String(f.size));
    const { data: init } = await postRetry("/me/chunked-upload/init", initFd, { timeout: 60000 });
    const total = Math.ceil(f.size / CHUNK_SIZE);
    let sent = 0;
    for (let i = 0; i < total; i++) {
      const blob = f.slice(i * CHUNK_SIZE, Math.min(f.size, (i + 1) * CHUNK_SIZE));
      const cfd = new FormData();
      cfd.append("upload_id", init.upload_id);
      cfd.append("index", String(i));
      cfd.append("chunk", blob, `part_${i}`);
      await postRetry("/me/chunked-upload/chunk", cfd, {
        timeout: 180000,
        onUploadProgress: (ev) => {
          const done = sent + (ev.loaded || 0);
          onPct(Math.min(99, Math.round((done * 100) / f.size)));
        },
      });
      sent += blob.size;
    }
    const doneFd = new FormData();
    doneFd.append("upload_id", init.upload_id);
    doneFd.append("total_chunks", String(total));
    const { data: fin } = await postRetry("/me/chunked-upload/complete", doneFd, { timeout: 300000 });
    return fin.token;
  };

  // ── Background upload — starts the moment a file is picked so the transfer
  // is hidden behind marking + details (guests AND logged-in users) ──
  const startBgUpload = (f) => {
    const gen = {};
    bgUploadRef.current = gen;
    setBgUpload({ status: "uploading", pct: 0, token: null });
    gen.promise = (async () => {
      try {
        const token = await chunkedUpload(f, (pct) => {
          if (bgUploadRef.current === gen) setBgUpload((s) => ({ ...s, pct }));
        });
        if (bgUploadRef.current === gen) setBgUpload({ status: "done", pct: 100, token });
        return token;
      } catch (err) {
        if (bgUploadRef.current === gen) setBgUpload({ status: "failed", pct: 0, token: null });
        return null;
      }
    })();
  };

  // While the analysis overlay waits on the background upload, mirror its progress.
  useEffect(() => {
    if (submitting && uploadPhase === "uploading" && bgUpload.status === "uploading") {
      setUploadPct(bgUpload.pct);
    }
  }, [bgUpload, submitting, uploadPhase]);

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
    if (!form.country) {
      toast.error("Please select the player's country — it's required.");
      return;
    }
    if (!(photoSource === "video_crop" || (photoSource === "upload" && playerPhoto?.dataUrl))) {
      toast.error("Please add a player photo — upload one or use the locked video image.");
      return;
    }
    // Category duration rules (client-side fast feedback — backend re-checks)
    const dur = videoMeta?.duration;
    const minSec = form.video_type === "match" ? 30 : 15;
    if (dur && dur < minSec - 0.5) {
      toast.error(`This category needs at least ${minSec} seconds of video — your clip is ${Math.round(dur)}s. Choose a longer clip or a different category.`, { duration: 8000 });
      return;
    }
    if (dur && dur > 305) {
      toast.error("Maximum video length is 5 minutes — please trim your clip.");
      return;
    }
    if (!user) {
      // Guest — the video is already uploading/uploaded in the background.
      // Creating the account is the LAST step; analysis starts right after.
      setGateOpen(true);
      return;
    }
    await doSubmit();
  };

  const doSubmit = async (o = {}) => {
    const _file = o.file || file;
    const _markerBlob = o.markerBlob || markerBlob;
    const _tempToken = o.tempVideoToken || tempVideoToken;
    const _markerTimestamp = o.markerTimestamp !== undefined ? o.markerTimestamp : markerTimestamp;
    const _markerBox = o.markerBox !== undefined ? o.markerBox : markerBox;
    const _markerAnchors = o.markerAnchors !== undefined ? o.markerAnchors : markerAnchors;
    const _form = o.form || form;
    const _photoSource = o.photoSource !== undefined ? o.photoSource : photoSource;
    const _playerPhoto = o.playerPhoto !== undefined ? o.playerPhoto : playerPhoto;

    setSubmitting(true);
    const fd = new FormData();
    if (_file?._fromUrl && _tempToken) {
      fd.append("temp_video_token", _tempToken);
    } else if (bgUpload.status === "done" && bgUpload.token) {
      // Background upload already finished — submit only the token.
      fd.append("temp_video_token", bgUpload.token);
    } else if (bgUpload.status === "uploading" && bgUploadRef.current?.promise) {
      // Background upload still in flight — wait for it (progress mirrors into the overlay).
      setUploadPhase("uploading");
      const token = await bgUploadRef.current.promise;
      if (token) {
        fd.append("temp_video_token", token);
      } else if (_file.size > DIRECT_LIMIT) {
        setUploadPct(0);
        let chunkToken = null;
        try {
          chunkToken = await chunkedUpload(_file);
        } catch (err) {
          const msg = err?.response?.data?.detail || "Upload failed while sending the video. Please check your connection and try again.";
          toast.error(typeof msg === "string" ? msg : "Upload failed. Please try again.");
          setSubmitting(false);
          setUploadPhase("idle");
          return;
        }
        fd.append("temp_video_token", chunkToken);
      } else {
        fd.append("file", _file);
      }
    } else if (_file.size > DIRECT_LIMIT) {
      // Large file → chunked upload first, then submit only the token.
      setUploadPhase("uploading");
      setUploadPct(0);
      let chunkToken = null;
      try {
        chunkToken = await chunkedUpload(_file);
      } catch (err) {
        const msg = err?.response?.data?.detail || "Upload failed while sending the video. Please check your connection and try again.";
        toast.error(typeof msg === "string" ? msg : "Upload failed. Please try again.");
        setSubmitting(false);
        setUploadPhase("idle");
        return;
      }
      fd.append("temp_video_token", chunkToken);
    } else {
      fd.append("file", _file);
    }
    fd.append("marker_image", _markerBlob, "marker.jpg");
    fd.append("marker_timestamp", String(_markerTimestamp || 0));
    if (_markerBox) {
      fd.append(
        "marker_box",
        JSON.stringify({
          x: Number(_markerBox.x.toFixed(4)),
          y: Number(_markerBox.y.toFixed(4)),
          w: Number(_markerBox.w.toFixed(4)),
          h: Number(_markerBox.h.toFixed(4)),
        }),
      );
    }
    if (_markerAnchors && _markerAnchors.length) {
      fd.append(
        "marker_anchors",
        JSON.stringify(
          _markerAnchors.map((a) => ({
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
    Object.entries(_form).forEach(([k, v]) => {
      if (v !== "" && v !== null && v !== undefined) fd.append(k, String(v));
    });
    // Required player photo — either an uploaded (compressed) photo or the
    // locked video image (backend uses the high-quality display crop).
    if (_photoSource) fd.append("photo_source", _photoSource);
    fd.append("feature_consent", featureConsent ? "true" : "false");
    if (_photoSource === "upload" && _playerPhoto?.dataUrl) {
      try {
        const photoBlob = await (await fetch(_playerPhoto.dataUrl)).blob();
        fd.append("player_photo", photoBlob, "player-photo.jpg");
      } catch (_) { /* backend validates */ }
    }

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
      reportIdRef.current = data?.id || null;
      if (data?.id) trackFunnel("analysis_submitted");
      if (data?.analysis_status === "analyzing") {
        const start = Date.now();
        const MAX_WAIT_MS = 10 * 60 * 1000; // 10 minute hard ceiling
        backgroundedRef.current = false;
        // poll loop
        // eslint-disable-next-line no-constant-condition
        while (true) {
          // User clicked "Go to Dashboard" → the button handler already did the
          // navigation + toast; just make sure the tracker owns this report and
          // stop the local loop (covers a click that landed mid-upload too).
          if (backgroundedRef.current) {
            startBackgroundAnalysis(data.id);
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
        // Free-tier flow: straight to the report route — the NEW high-CTR
        // FreePreviewLanding conversion page renders there. (Old HeroTeaser
        // modal removed per owner request.)
        setUploadPhase("idle");
        if (finalData?.id) navigate(`/report/${finalData.id}`);
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

  /* ── Google sign-in from the account gate — persists the finished upload +
     markers + form to sessionStorage, then round-trips through Emergent auth.
     The resume effect below picks everything up and auto-submits. ── */
  const blobToDataUrl = (blob) => new Promise((res, rej) => {
    const r = new FileReader();
    r.onload = () => res(r.result);
    r.onerror = rej;
    r.readAsDataURL(blob);
  });

  const handleGateGoogle = async () => {
    const token = file?._fromUrl ? tempVideoToken : bgUpload.token;
    if (!token) return; // button is disabled until the upload finishes
    let markerDataUrl = null;
    try {
      if (markerBlob) markerDataUrl = await blobToDataUrl(markerBlob);
    } catch (_) { /* ignore */ }
    const state = {
      token,
      fileName: file?.name,
      fileSize: file?.size || 0,
      markerTimestamp,
      markerBox,
      markerAnchors,
      markerDataUrl,
      form,
      photoSource,
      playerPhotoDataUrl: photoSource === "upload" ? playerPhoto?.dataUrl || null : null,
    };
    try {
      sessionStorage.setItem("smp_resume_upload", JSON.stringify(state));
    } catch (_) {
      // Quota — retry without the anchor thumbnails (backend re-derives crops).
      try {
        sessionStorage.setItem("smp_resume_upload", JSON.stringify({
          ...state,
          markerAnchors: (markerAnchors || []).map((a) => ({ ...a, thumb: undefined })),
        }));
      } catch (_e) {
        toast.error("Could not save your progress for Google sign-in — use email signup instead.");
        return;
      }
    }
    // REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
    const redirectUrl = window.location.origin + "/upload";
    window.location.href = `https://auth.emergentagent.com/?redirect=${encodeURIComponent(redirectUrl)}`;
  };

  /* ── Resume after the Google OAuth round-trip — restore the persisted upload
     state and start the analysis immediately. ── */
  useEffect(() => {
    if (!user) return;
    const raw = sessionStorage.getItem("smp_resume_upload");
    if (!raw) return;
    sessionStorage.removeItem("smp_resume_upload");
    (async () => {
      try {
        const st = JSON.parse(raw);
        if (!st?.token) return;
        const stub = { name: st.fileName || "video.mp4", size: st.fileSize || 0, _fromUrl: true };
        setFile(stub);
        setTempVideoToken(st.token);
        setMarkerTimestamp(st.markerTimestamp || 0);
        setMarkerBox(st.markerBox || null);
        setMarkerAnchors(st.markerAnchors || null);
        if (st.form) setForm((prev) => ({ ...prev, ...st.form }));
        const resumedPhotoSource = st.photoSource || null;
        const resumedPhoto = st.playerPhotoDataUrl ? { dataUrl: st.playerPhotoDataUrl } : null;
        if (resumedPhotoSource) setPhotoSource(resumedPhotoSource);
        if (resumedPhoto) setPlayerPhoto(resumedPhoto);
        let blob = null;
        if (st.markerDataUrl) {
          blob = await (await fetch(st.markerDataUrl)).blob();
          setMarkerBlob(blob);
          setMarkerPreviewUrl(URL.createObjectURL(blob));
        }
        if (!blob) {
          toast.info("Welcome back! Please re-mark your player, then start the analysis.");
          return;
        }
        toast.success("Welcome! Your video is ready — starting the analysis now.");
        doSubmit({
          file: stub,
          markerBlob: blob,
          tempVideoToken: st.token,
          markerTimestamp: st.markerTimestamp || 0,
          markerBox: st.markerBox || null,
          markerAnchors: st.markerAnchors || null,
          form: st.form || form,
          photoSource: resumedPhotoSource,
          playerPhoto: resumedPhoto,
        });
      } catch (_) { /* corrupted resume state — user can submit manually */ }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user]);

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
        open={submitting && !premiumReadyReport}
        phase={uploadPhase === "uploading" ? "uploading" : uploadPhase === "done" ? "done" : "analyzing"}
        uploadPct={uploadPct}
        backendStep={backendStep}
        playerName={form.player_name}
        playerAge={form.age}
        playerPosition={form.position}
        tapsCount={markerAnchors?.length || 0}
        heroImage={markerPreviewUrl}
        onContinueInBackground={() => {
          // Immediate handoff — never depend on the poll loop's next tick.
          backgroundedRef.current = true;
          const rid = reportIdRef.current;
          if (rid) {
            startBackgroundAnalysis(rid);
            toast.success("We'll let you know when your report is ready.", { duration: 4500 });
          } else {
            // Upload POST still in flight — the poll loop hands off once the id exists.
            toast.success("Your upload keeps running — we'll let you know when the report is ready.", { duration: 4500 });
          }
          setSubmitting(false);
          setUploadPhase("idle");
          navigate("/dashboard");
        }}
        onViewReport={() => {
          const pending = pendingDoneRef.current;
          if (!pending) return;
          pendingDoneRef.current = null;
          if (!pending.skipHeroTeaser) {
            // Free preview → the NEW conversion page (FreePreviewLanding) on the report route.
            setSubmitting(false);
            setUploadPhase("idle");
            if (pending.data?.id) navigate(`/report/${pending.data.id}`);
          } else {
            // Session 130 — Premium celebration screen instead of instant nav.
            setPremiumReadyReport(pending.data);
          }
        }}
      />
      {/* Old free-tier HeroTeaser modal REMOVED — free users now land on the
          FreePreviewLanding conversion page at /report/{id}. */}
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
      {/* Session 144 — guest account gate: shown at "Start analysis" when not logged in */}
      <AccountGateModal
        open={gateOpen}
        onClose={() => setGateOpen(false)}
        uploadReady={(file?._fromUrl && !!tempVideoToken) || bgUpload.status === "done"}
        uploadPct={bgUpload.pct}
        onAuthed={async () => {
          setGateOpen(false);
          try { await refreshEligibility(); } catch (_) { /* ignore */ }
          doSubmit();
        }}
        onGoogleRedirect={handleGateGoogle}
      />

      <div className="pt-[76px] md:pt-24 pb-10 px-4 sm:px-6">
        <div className="max-w-6xl mx-auto">

          {/* ===== HERO ===== */}
          <section className="mb-5 md:mb-8">
            <div className="grid grid-cols-[1.3fr_1fr] md:grid-cols-2 gap-4 md:gap-10 items-start md:items-center">
              <div>
                <h1
                  data-testid="upload-title"
                  className="font-barlow font-black uppercase text-[28px] leading-[0.95] sm:text-5xl lg:text-6xl tracking-tighter text-ink"
                >
                  Every match tells a story.{" "}
                  <span style={{ color: "#A6C800" }}>Let&rsquo;s discover yours.</span>
                </h1>
                <p className="mt-2.5 text-ink/70 text-[13px] md:text-base leading-snug max-w-md">
                  One upload. <span className="font-bold text-ink">One player.</span>
                  <br className="hidden sm:block" />{" "}
                  One professional ScoutMe Benchmark Analysis.
                </p>

                {/* Trust chips — desktop position (inside text column) */}
                <div className="hidden sm:flex mt-5 items-stretch flex-wrap gap-y-3">
                  <div className="flex items-center gap-2.5 pr-5">
                    <ShieldCheck className="w-7 h-7 text-forest shrink-0" strokeWidth={1.6} />
                    <span className="text-[10px] uppercase tracking-[0.14em] font-bold text-ink/75 leading-tight">ScoutMe Pro<br />benchmark<br />analysis</span>
                  </div>
                  <div className="flex items-center gap-2.5 px-5 border-l border-ink/10">
                    <Clock className="w-7 h-7 text-forest shrink-0" strokeWidth={1.6} />
                    <span className="text-[10px] uppercase tracking-[0.14em] font-bold text-ink/75 leading-tight">Max<br />5 minutes</span>
                  </div>
                  <div className="flex items-center gap-2.5 px-5 border-l border-ink/10">
                    <FileText className="w-7 h-7 text-forest shrink-0" strokeWidth={1.6} />
                    <span className="text-[10px] uppercase tracking-[0.14em] font-bold text-ink/75 leading-tight">Personal<br />PDF report</span>
                  </div>
                </div>
              </div>

              {/* Hero image with scout-frame brackets */}
              <div className="relative w-full max-w-[300px] justify-self-end">
                <div className="relative p-2.5">
                  <img
                    src="/assets/upload-hero.jpg"
                    alt="Young player, number 10, ready to be discovered"
                    className="w-full aspect-[4/5] md:aspect-[4/5] object-cover"
                    loading="eager"
                  />
                  <span className="absolute top-0 left-0 w-8 h-8 border-t-[3px] border-l-[3px]" style={{ borderColor: LIME }} />
                  <span className="absolute top-0 right-0 w-8 h-8 border-t-[3px] border-r-[3px]" style={{ borderColor: LIME }} />
                  <span className="absolute bottom-0 left-0 w-8 h-8 border-b-[3px] border-l-[3px]" style={{ borderColor: LIME }} />
                  <span className="absolute bottom-0 right-0 w-8 h-8 border-b-[3px] border-r-[3px]" style={{ borderColor: LIME }} />
                  <Crosshair className="absolute -bottom-2.5 -right-2.5 w-9 h-9" style={{ color: LIME }} strokeWidth={1.5} />
                </div>
              </div>
            </div>

            {/* Trust chips — mobile position (full row under hero) */}
            <div className="sm:hidden mt-3 flex items-stretch flex-wrap gap-y-2">
              <div className="flex items-center gap-2 pr-3">
                <ShieldCheck className="w-6 h-6 text-forest shrink-0" strokeWidth={1.6} />
                <span className="text-[9px] uppercase tracking-[0.08em] font-bold text-ink/75 leading-tight">ScoutMe Pro<br />benchmark<br />analysis</span>
              </div>
              <div className="flex items-center gap-2 px-3 border-l border-ink/10">
                <Clock className="w-6 h-6 text-forest shrink-0" strokeWidth={1.6} />
                <span className="text-[9px] uppercase tracking-[0.08em] font-bold text-ink/75 leading-tight">Max<br />5 minutes</span>
              </div>
              <div className="flex items-center gap-2 px-3 border-l border-ink/10">
                <FileText className="w-6 h-6 text-forest shrink-0" strokeWidth={1.6} />
                <span className="text-[9px] uppercase tracking-[0.08em] font-bold text-ink/75 leading-tight">Personal<br />PDF report</span>
              </div>
            </div>

            {/* Guest + eligibility pills */}
            <div className="mt-3 flex flex-wrap gap-2">
              {!user && (
                <span data-testid="guest-upload-pill" className="inline-flex items-center gap-2 rounded-full text-[10px] sm:text-[11px] uppercase tracking-[0.1em] font-bold text-forest border border-forest/30 bg-forest/5 px-3 py-1.5">
                  <Zap className="w-3.5 h-3.5 shrink-0" /> No account needed — create one right before the analysis
                </span>
              )}
              {!eligibilityLoading && eligibility && eligibility.reason === "free_preview" && (
                <span data-testid="eligibility-free" className="inline-flex items-center gap-2 rounded-full text-[10px] sm:text-[11px] uppercase tracking-[0.1em] font-bold text-forest border border-forest/30 bg-forest/5 px-3 py-1.5">
                  <Zap className="w-3.5 h-3.5" /> 1 free preview available
                </span>
              )}
              {!eligibilityLoading && eligibility && eligibility.reason === "prepaid" && (
                <span data-testid="eligibility-prepaid" className="inline-flex items-center gap-2 rounded-full text-[10px] sm:text-[11px] uppercase tracking-[0.1em] font-bold text-forest border border-forest/30 bg-forest/5 px-3 py-1.5">
                  <Check className="w-3.5 h-3.5" /> 1 prepaid upload · full premium report
                </span>
              )}
              {!eligibilityLoading && eligibility && eligibility.reason === "admin" && (
                <span data-testid="eligibility-admin" className="inline-flex items-center gap-2 rounded-full text-[10px] sm:text-[11px] uppercase tracking-[0.1em] font-bold text-ink/70 border border-gray-border px-3 py-1.5">
                  Admin · unlimited uploads
                </span>
              )}
            </div>
          </section>

          {/* ===== PAYWALL — ineligible state ===== */}
          {!eligibilityLoading && eligibility && !eligibility.eligible && eligibility.reason === "prepay_required" && (
            <div data-testid="upload-paywall" className="mb-10 relative overflow-hidden rounded-3xl border-2 border-volt bg-gradient-to-br from-volt/10 via-deepnavy/40 to-deepnavy/40 p-8 md:p-12" style={{ boxShadow: "0 0 80px rgba(45,107,61,0.12)" }}>
              <div className="grid md:grid-cols-3 gap-8 items-center">
                <div className="md:col-span-2">
                  <div className="inline-flex items-center gap-2 rounded-full text-[10px] uppercase tracking-[0.25em] font-bold text-volt border border-volt/40 bg-volt/10 px-3 py-1.5 mb-5">
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
                    className="mt-8 inline-flex items-center justify-center gap-3 rounded-2xl bg-forest hover:bg-forest-pop text-white font-barlow font-black uppercase tracking-widest text-base px-7 py-4 shadow-lg shadow-forest/25 active:scale-[0.98] transition-[transform,box-shadow,background-color] duration-200 disabled:opacity-60"
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
                  <div className="inline-block rounded-2xl bg-cream-card/90 border border-volt/30 p-6">
                    <div className="text-[10px] uppercase tracking-[0.25em] font-bold text-volt mb-2">Per upload</div>
                    <div className="font-barlow font-black text-6xl text-ink leading-none">${price}</div>
                    <div className="mt-1 text-xs uppercase tracking-widest font-bold text-ink/60">USD · one-time</div>
                  </div>
                </div>
              </div>
            </div>
          )}

          <form onSubmit={handleSubmit} className={`space-y-3 sm:space-y-5 ${eligibility && !eligibility.eligible ? "opacity-40 pointer-events-none" : ""}`} data-testid="upload-form">

            {/* Hidden file input — shared by dropzone + choose-file + upload-another */}
            <input
              ref={fileRef}
              type="file"
              accept="video/mp4,video/quicktime,video/webm"
              className="hidden"
              onChange={(e) => handleFile(e.target.files?.[0])}
              data-testid="upload-file-input"
            />

            {/* ===== STEP 1: UPLOAD YOUR VIDEO ===== */}
            <section className="bg-surface rounded-3xl border border-gray-border p-4 sm:p-7">
              <div className="flex items-center justify-between gap-3 flex-wrap">
                <div className="flex items-center gap-3">
                  {file ? (
                    <span className="w-8 h-8 rounded-full bg-forest flex items-center justify-center shrink-0"><Check className="w-4.5 h-4.5 text-white" strokeWidth={3} /></span>
                  ) : (
                    <span className="w-8 h-8 rounded-full flex items-center justify-center font-barlow font-black text-ink shrink-0" style={{ background: LIME }}>1</span>
                  )}
                  <h2 className="font-barlow font-black uppercase tracking-tight text-lg md:text-xl text-ink">Upload your video</h2>
                </div>
                {file && (
                  <span data-testid="step1-video-ready" className="inline-flex items-center gap-1.5 rounded-full bg-cream-base border border-ink/10 px-3.5 py-1.5 text-[10px] uppercase tracking-[0.16em] font-black text-ink/80">
                    <CheckCircle2 className="w-3.5 h-3.5 text-forest" /> Video ready
                  </span>
                )}
              </div>

              {!file ? (
                <div className="mt-4">
                  <label
                    onDragOver={(e) => e.preventDefault()}
                    onDrop={(e) => {
                      e.preventDefault();
                      if (sourceMode === "file") handleFile(e.dataTransfer.files?.[0]);
                    }}
                    onClick={(e) => { e.preventDefault(); setSourceMode("file"); fileRef.current?.click(); }}
                    data-testid="upload-dropzone"
                    className="block cursor-pointer rounded-2xl border-2 border-dashed border-ink/20 hover:border-forest bg-cream-base/50 px-5 py-6 text-center transition-colors"
                  >
                    <div className="flex flex-col items-center gap-1">
                      <UploadCloud className="w-10 h-10 text-forest-pop" strokeWidth={1.25} />
                      <p className="font-barlow font-black uppercase text-ink text-base tracking-tight mt-1">Drag &amp; drop your video here</p>
                      <p className="text-[13px] text-ink/55 font-semibold">or tap to browse</p>
                      <p className="mt-1.5 text-[11px] font-bold text-ink/55 uppercase tracking-widest">MP4 · MOV · WebM &nbsp;—&nbsp; up to 5 minutes</p>
                    </div>
                  </label>

                  <div className="mt-3 grid grid-cols-2 gap-3">
                    <button
                      type="button"
                      onClick={() => { setSourceMode("file"); fileRef.current?.click(); }}
                      data-testid="upload-mode-file"
                      className="rounded-2xl bg-forest hover:bg-forest-pop text-white p-3.5 sm:p-4 flex items-center justify-center gap-2.5 shadow-lg shadow-forest/20 active:scale-[0.98] transition-[transform,box-shadow,background-color] duration-200"
                    >
                      <FileUp className="w-4.5 h-4.5 shrink-0" />
                      <span className="text-left">
                        <span className="block font-barlow font-black uppercase tracking-wide text-[13px] sm:text-sm leading-none">Choose file</span>
                        <span className="hidden sm:block text-white/65 text-[10px] mt-1">Upload from your device</span>
                      </span>
                    </button>
                    <button
                      type="button"
                      onClick={() => setSourceMode(sourceMode === "url" ? "file" : "url")}
                      data-testid="upload-mode-url"
                      className={`rounded-2xl p-3.5 sm:p-4 flex items-center justify-center gap-2.5 border active:scale-[0.98] transition-[transform,border-color,background-color] duration-200 ${
                        sourceMode === "url" ? "bg-cream-soft border-forest/40" : "bg-cream-base/70 border-ink/10 hover:border-forest/40"
                      }`}
                    >
                      <LinkIcon className="w-4.5 h-4.5 shrink-0 text-forest" />
                      <span className="text-left">
                        <span className="block font-barlow font-black uppercase tracking-wide text-[13px] sm:text-sm text-ink leading-none">Paste URL</span>
                        <span className="hidden sm:block text-ink/50 text-[10px] mt-1">Vimeo, Drive or direct link</span>
                      </span>
                    </button>
                  </div>

                  {sourceMode === "url" && (
                    <div className="mt-3 space-y-2">
                      <div className="flex items-stretch gap-2">
                        <input
                          type="url"
                          data-testid="upload-url-input"
                          value={pasteUrl}
                          onChange={(e) => setPasteUrl(e.target.value)}
                          placeholder="Vimeo · Google Drive · .mp4 link"
                          className="flex-1 min-w-0 rounded-xl px-3 py-2.5 bg-white border border-gray-border focus:border-forest outline-none text-sm font-mono"
                          disabled={urlFetching}
                        />
                        <button
                          type="button"
                          onClick={handleUrlFetch}
                          disabled={urlFetching || !pasteUrl.trim()}
                          data-testid="upload-url-fetch"
                          className="rounded-xl bg-forest hover:bg-forest-pop text-white font-barlow font-black uppercase tracking-widest text-xs px-4 py-2.5 flex items-center gap-2 disabled:opacity-50 transition-colors"
                        >
                          {urlFetching ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <LinkIcon className="w-3.5 h-3.5" />}
                          {urlFetching ? "Fetching" : "Fetch"}
                        </button>
                      </div>
                      <p className="text-[10px] text-ink/55 leading-relaxed">
                        Best with Vimeo, Google Drive shared links or any direct .mp4 / .mov URL.
                        <span className="block mt-1 text-forest font-bold">
                          Veo &amp; YouTube links can&apos;t be fetched directly — download the clip to your device, then use &ldquo;Choose File&rdquo;.
                        </span>
                        Max 500 MB · max 5 min.
                      </p>
                    </div>
                  )}
                </div>
              ) : (
                <div className="mt-4">
                  {/* Compact intelligent summary card */}
                  <div data-testid="upload-video-summary" className="rounded-2xl bg-cream-base/70 border border-ink/8 p-3.5 flex items-center gap-4">
                    <div className="w-[86px] h-[64px] rounded-xl bg-forest border border-forest-pop/60 flex items-center justify-center shrink-0 shadow-inner">
                      <Play className="w-7 h-7 text-white/90 fill-current" />
                    </div>
                    <div className="min-w-0">
                      <p className="font-barlow font-black text-ink text-base truncate">{file.name}</p>
                      <p className="text-[12.5px] text-ink/60 font-semibold mt-0.5">
                        {(file.size / 1024 / 1024).toFixed(1)} MB
                        {videoMeta?.duration ? <> &nbsp;·&nbsp; {Math.floor(videoMeta.duration / 60)}:{String(Math.floor(videoMeta.duration % 60)).padStart(2, "0")}</> : null}
                        {videoMeta?.height ? <> &nbsp;·&nbsp; {Math.min(videoMeta.width || videoMeta.height, videoMeta.height)}p</> : null}
                      </p>
                      <p className="flex items-center gap-1.5 text-[12px] font-bold text-forest mt-1.5">
                        <CheckCircle2 className="w-4 h-4 shrink-0" /> Video verified — ready for player selection
                      </p>
                      <p className="text-[10.5px] text-ink/45 mt-0.5">
                        ScoutMe Pro Intelligence confirms it&rsquo;s real football during the analysis.
                      </p>
                    </div>
                  </div>

                  <button
                    type="button"
                    onClick={() => { setSourceMode("file"); fileRef.current?.click(); }}
                    data-testid="upload-another-video"
                    className="mt-3 w-full rounded-2xl bg-forest hover:bg-forest-pop text-white font-barlow font-black uppercase tracking-[0.16em] text-[13px] py-3.5 flex items-center justify-center gap-2.5 shadow-lg shadow-forest/20 active:scale-[0.98] transition-[transform,box-shadow,background-color] duration-200"
                  >
                    <UploadCloud className="w-4.5 h-4.5" /> Upload another video
                  </button>
                </div>
              )}

              <div className="mt-3.5 flex items-center justify-center gap-2 text-[12px] sm:text-sm text-ink/55">
                <Lock className="w-3.5 h-3.5 text-ink/40 shrink-0" />
                Your video is private, secure and used only for your analysis.
              </div>
            </section>

            {/* ===== STEP 2: LOCK ONTO YOUR PLAYER ===== */}
            <section className={`bg-surface rounded-3xl border border-gray-border p-4 sm:p-7 ${!file ? "opacity-55" : ""}`}>
              <div className="flex items-center justify-between gap-3 flex-wrap">
                <div className="flex items-center gap-3">
                  {markerBlob ? (
                    <span className="w-8 h-8 rounded-full bg-forest flex items-center justify-center shrink-0"><Check className="w-4.5 h-4.5 text-white" strokeWidth={3} /></span>
                  ) : (
                    <span className={`w-8 h-8 rounded-full flex items-center justify-center font-barlow font-black shrink-0 ${file ? "text-ink" : "text-ink/45 bg-cream-soft"}`} style={file ? { background: LIME } : undefined}>2</span>
                  )}
                  <h2 className="font-barlow font-black uppercase tracking-tight text-lg md:text-xl text-ink">Lock onto your player</h2>
                </div>
                {!markerBlob && (
                  <button
                    type="button"
                    onClick={() => setHowOpen((v) => !v)}
                    data-testid="upload-how-it-works"
                    className="inline-flex items-center gap-2 rounded-full border border-ink/20 hover:border-forest px-4 py-2 text-[10px] uppercase tracking-[0.16em] font-black text-ink/75 transition-colors"
                  >
                    <Play className="w-3 h-3 fill-current" /> How it works
                  </button>
                )}
                {markerBlob && (
                  <span className="inline-flex items-center gap-1.5 rounded-full bg-cream-base border border-ink/10 px-3.5 py-1.5 text-[10px] uppercase tracking-[0.16em] font-black text-ink/80">
                    <CheckCircle2 className="w-3.5 h-3.5 text-forest" /> Locked
                  </span>
                )}
              </div>

              {howOpen && !markerBlob && (
                <div className="mt-3 rounded-xl bg-cream-soft/80 px-4 py-3 grid sm:grid-cols-3 gap-2.5 text-[12px] text-ink/75">
                  <span className="flex items-center gap-2"><Video className="w-4 h-4 text-forest shrink-0" /> 1. We analyze your video</span>
                  <span className="flex items-center gap-2"><Crosshair className="w-4 h-4 text-forest shrink-0" /> 2. You select the player</span>
                  <span className="flex items-center gap-2"><TrendingUp className="w-4 h-4 text-forest shrink-0" /> 3. We reveal their story</span>
                </div>
              )}

              {/* Waiting state — slim, no dead space */}
              {!file && (
                <p className="mt-2.5 text-[13px] text-ink/50 pl-11">Waiting for your video — complete step 1 first.</p>
              )}

              {/* Active state — real video + scout tools */}
              {file && !markerBlob && (
                <div className="mt-4 space-y-3">
                  <div className="relative bg-black rounded-2xl border border-gray-border overflow-hidden">
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

                  {/* Studio capabilities — informational, the single action is the CTA below */}
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                    {[
                      { icon: ZoomIn, label: "Zoom" },
                      { icon: ScanSearch, label: "Auto detect" },
                      { icon: EyeOff, label: "Ignore others" },
                      { icon: LocateFixed, label: "Scout precision" },
                    ].map((t) => (
                      <div
                        key={t.label}
                        data-testid={`upload-tool-${t.label.toLowerCase().replace(/ /g, "-")}`}
                        className="rounded-xl bg-cream-base/50 border border-ink/8 px-3 py-2.5 flex items-center justify-center gap-2 text-[10px] uppercase tracking-[0.12em] font-black text-ink/50 select-none"
                      >
                        <t.icon className="w-3.5 h-3.5 text-forest/60" /> {t.label}
                      </div>
                    ))}
                  </div>
                  <p className="text-[10.5px] text-ink/45 text-center -mt-1">
                    All tools are built into the studio — open it with the button below.
                  </p>

                  {/* Info + primary CTA */}
                  <div className="rounded-2xl bg-cream-base/70 border border-ink/8 p-3.5 flex flex-col sm:flex-row items-stretch sm:items-center gap-3">
                    <div className="flex items-center gap-3 flex-1 min-w-0">
                      <span className="w-10 h-10 rounded-xl bg-white border border-ink/10 flex items-center justify-center shrink-0">
                        <Crosshair className="w-5 h-5 text-ink/70" />
                      </span>
                      <p className="text-[12.5px] text-ink/70 leading-snug">
                        Only your selected player will be analysed.<br className="hidden sm:block" />{" "}
                        <span className="font-bold text-ink">Tap once. We&rsquo;ll ignore everyone else.</span>
                      </p>
                    </div>
                    <button
                      type="button"
                      onClick={() => setStudioOpen(true)}
                      data-testid="upload-mark-start"
                      className="rounded-2xl bg-forest hover:bg-forest-pop text-white px-5 py-3 flex flex-col items-center justify-center gap-0.5 shadow-lg shadow-forest/25 active:scale-[0.98] transition-[transform,box-shadow,background-color] duration-200 shrink-0"
                    >
                      <span className="flex items-center gap-2 font-barlow font-black uppercase tracking-[0.14em] text-[13px]">
                        <Crosshair className="w-4 h-4" /> Lock onto player
                      </span>
                      <span className="text-white/65 text-[10px] font-semibold">Takes less than 20 seconds →</span>
                    </button>
                  </div>
                </div>
              )}

              {/* Done state — compact locked card */}
              {markerBlob && markerPreviewUrl && (
                <div className="mt-4 rounded-2xl bg-cream-base/70 border border-ink/8 p-3.5 flex items-center gap-4">
                  <img
                    src={markerPreviewUrl}
                    alt="Locked player"
                    data-testid="upload-mark-preview"
                    className="w-[86px] h-[64px] rounded-xl object-cover bg-black border border-ink/10 shrink-0"
                  />
                  <div className="min-w-0 flex-1">
                    <p className="flex items-center gap-1.5 text-[13px] font-black text-ink">
                      <CheckCircle2 className="w-4 h-4 text-forest shrink-0" /> Player locked successfully
                    </p>
                    <p className="text-[12px] text-ink/55 mt-0.5">Tracking precision ready — only this player will be analysed.</p>
                  </div>
                  <button
                    type="button"
                    onClick={reMark}
                    data-testid="upload-mark-redo"
                    className="shrink-0 rounded-xl border border-ink/15 hover:border-forest text-ink/70 hover:text-forest text-[10px] uppercase tracking-[0.14em] font-black px-3.5 py-2.5 flex items-center gap-1.5 transition-colors"
                  >
                    <RefreshCw className="w-3.5 h-3.5" /> Re-mark
                  </button>
                </div>
              )}
            </section>

            {/* ===== STEP 3: TELL US ABOUT YOUR PLAYER ===== */}
            <section className={`bg-surface rounded-3xl border border-gray-border p-4 sm:p-7 ${!markerBlob ? "opacity-55" : ""}`}>
              <div className="flex items-center gap-3">
                <span className={`w-8 h-8 rounded-full flex items-center justify-center font-barlow font-black shrink-0 ${markerBlob ? "text-ink" : "text-ink/45 bg-cream-soft"}`} style={markerBlob ? { background: LIME } : undefined}>3</span>
                <h2 className="font-barlow font-black uppercase tracking-tight text-lg md:text-xl text-ink">Tell us about your player</h2>
              </div>

              {!markerBlob ? (
                <p className="mt-2.5 text-[13px] text-ink/50 pl-11">Waiting for player lock — complete step 2 first.</p>
              ) : (
                <div className="mt-4 space-y-4">
                  {profiles.length > 0 && (
                    <div data-testid="upload-profile-picker" className="rounded-2xl bg-cream-base/70 border border-forest/25 p-3.5">
                      <span className="text-[10px] uppercase tracking-[0.18em] font-black text-forest block mb-2">
                        Same player again? Tap to pre-fill
                      </span>
                      <div className="flex flex-wrap gap-2">
                        {profiles.map((p, i) => (
                          <button
                            key={p.id || i}
                            type="button"
                            data-testid={`upload-profile-chip-${i}`}
                            onClick={() => applyProfile(p)}
                            className="inline-flex items-center gap-1.5 rounded-full border border-gray-border hover:border-forest bg-white text-ink text-xs font-bold px-3.5 py-1.5 transition-colors"
                          >
                            {p.player_name}
                            <span className="text-ink/45 font-normal">
                              · {p.age != null ? `U${Math.min(21, Math.max(5, Number(p.age) + 1))}` : ""} {p.position || ""}
                            </span>
                          </button>
                        ))}
                      </div>
                    </div>
                  )}

                  <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4">
                    <div>
                      <label className="text-[11px] font-bold text-ink/70 block mb-1.5">Player name <span className="text-forest">*</span></label>
                      <div className="relative">
                        <User className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-ink/40 pointer-events-none" />
                        <input
                          required
                          type="text"
                          value={form.player_name}
                          onChange={(e) => setField("player_name", e.target.value)}
                          data-testid="upload-player-name"
                          className="w-full bg-white border border-gray-border rounded-xl pl-10 pr-3 py-2.5 sm:py-3 text-sm text-ink focus:outline-none focus:border-forest focus:ring-1 focus:ring-forest"
                          placeholder="e.g. Lukas Andersen"
                        />
                      </div>
                    </div>
                    <div>
                      <label className="text-[11px] font-bold text-ink/70 block mb-1.5">Age <span className="text-forest">*</span></label>
                      <div className="relative">
                        <Calendar className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-ink/40 pointer-events-none" />
                        <input
                          required
                          type="number"
                          min="5"
                          max="50"
                          value={form.age}
                          onChange={(e) => setField("age", e.target.value)}
                          data-testid="upload-player-age"
                          className="w-full bg-white border border-gray-border rounded-xl pl-10 pr-3 py-2.5 sm:py-3 text-sm text-ink focus:outline-none focus:border-forest focus:ring-1 focus:ring-forest"
                          placeholder="e.g. 14"
                        />
                      </div>
                    </div>
                    <div>
                      <label className="text-[11px] font-bold text-ink/70 block mb-1.5">Position <span className="text-forest">*</span></label>
                      <div className="relative">
                        <Shirt className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-ink/40 pointer-events-none" />
                        <select
                          required
                          value={form.position}
                          onChange={(e) => setField("position", e.target.value)}
                          data-testid="upload-player-position"
                          className="w-full bg-white border border-gray-border rounded-xl pl-10 pr-3 py-2.5 sm:py-3 text-sm text-ink focus:outline-none focus:border-forest focus:ring-1 focus:ring-forest"
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
                    </div>
                    <div>
                      <label className="text-[11px] font-bold text-ink/70 block mb-1.5">Preferred foot <span className="text-forest">*</span></label>
                      <div className="relative">
                        <Footprints className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-ink/40 pointer-events-none" />
                        <select
                          required
                          value={form.preferred_foot}
                          onChange={(e) => setField("preferred_foot", e.target.value)}
                          data-testid="upload-player-foot"
                          className="w-full bg-white border border-gray-border rounded-xl pl-10 pr-3 py-2.5 sm:py-3 text-sm text-ink focus:outline-none focus:border-forest focus:ring-1 focus:ring-forest"
                        >
                          <option value="right">Right</option>
                          <option value="left">Left</option>
                          <option value="both">Both</option>
                        </select>
                      </div>
                    </div>
                    <div>
                      <label className="text-[11px] font-bold text-ink/70 block mb-1.5">Country <span className="text-forest">*</span></label>
                      <Popover open={countryOpen} onOpenChange={setCountryOpen}>
                        <PopoverTrigger asChild>
                          <button
                            type="button"
                            data-testid="upload-player-country"
                            className="w-full bg-white border border-gray-border rounded-xl pl-10 pr-3 py-2.5 sm:py-3 text-sm text-left focus:outline-none focus:border-forest relative flex items-center justify-between"
                          >
                            <Globe className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-ink/40 pointer-events-none" />
                            <span className={form.country ? "text-ink" : "text-ink/40"}>
                              {form.country || "Select country"}
                            </span>
                            <ChevronsUpDown className="w-3.5 h-3.5 text-ink/40 shrink-0" />
                          </button>
                        </PopoverTrigger>
                        <PopoverContent className="p-0 w-[260px]" align="start">
                          <Command>
                            <CommandInput placeholder="Search country…" data-testid="upload-country-search" />
                            <CommandList className="max-h-56">
                              <CommandEmpty>No country found.</CommandEmpty>
                              <CommandGroup>
                                {COUNTRIES.map((c) => (
                                  <CommandItem
                                    key={c}
                                    value={c}
                                    data-testid={`upload-country-item-${c.toLowerCase().replace(/[^a-z]/g, "-")}`}
                                    onSelect={() => { setField("country", c); setCountryOpen(false); }}
                                  >
                                    <Check className={`mr-2 h-4 w-4 ${form.country === c ? "opacity-100 text-forest" : "opacity-0"}`} />
                                    {c}
                                  </CommandItem>
                                ))}
                              </CommandGroup>
                            </CommandList>
                          </Command>
                        </PopoverContent>
                      </Popover>
                    </div>
                    <div>
                      <label className="text-[11px] font-bold text-ink/70 block mb-1.5">Current club / team</label>
                      <div className="relative">
                        <ShieldCheck className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-ink/40 pointer-events-none" />
                        <input
                          type="text"
                          value={form.current_club}
                          onChange={(e) => setField("current_club", e.target.value)}
                          data-testid="upload-player-club"
                          className="w-full bg-white border border-gray-border rounded-xl pl-10 pr-3 py-2.5 sm:py-3 text-sm text-ink focus:outline-none focus:border-forest focus:ring-1 focus:ring-forest"
                          placeholder="Optional"
                        />
                      </div>
                    </div>
                    <div>
                      <label className="text-[11px] font-bold text-ink/70 block mb-1.5">Shirt number</label>
                      <div className="relative">
                        <Hash className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-ink/40 pointer-events-none" />
                        <input
                          type="text"
                          inputMode="numeric"
                          maxLength={3}
                          value={form.jersey_number}
                          onChange={(e) => setField("jersey_number", e.target.value.replace(/[^0-9]/g, ""))}
                          data-testid="upload-player-jersey"
                          className="w-full bg-white border border-gray-border rounded-xl pl-10 pr-3 py-2.5 sm:py-3 text-sm text-ink focus:outline-none focus:border-forest focus:ring-1 focus:ring-forest"
                          placeholder="e.g. 10 — sharpens"
                        />
                      </div>
                    </div>
                    <div className="col-span-2">
                      <label className="text-[11px] font-bold text-ink/70 block mb-1.5">Video type <span className="text-forest">*</span></label>
                      <div className="relative">
                        <Video className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-ink/40 pointer-events-none" />
                        <select
                          value={form.video_type}
                          onChange={(e) => setField("video_type", e.target.value)}
                          data-testid="upload-video-type"
                          className="w-full bg-white border border-gray-border rounded-xl pl-10 pr-3 py-2.5 sm:py-3 text-sm text-ink focus:outline-none focus:border-forest focus:ring-1 focus:ring-forest"
                        >
                          <option value="match">Match — full match, training match or small-sided game</option>
                          <option value="skills">Skills &amp; Technical Training — drills, ball mastery, tricks, juggling, shooting</option>
                          <option value="highlight">Highlights — best moments, multiple matches combined</option>
                        </select>
                      </div>
                      <p className="mt-1.5 text-[10.5px] text-ink/55 leading-snug" data-testid="upload-video-type-hint">
                        {form.video_type === "match" && "Live game footage — we'll judge decisions, duels, off-ball runs and game-pace technique. Minimum 30 seconds · maximum 5 minutes."}
                        {form.video_type === "skills" && "Cone drills, technical exercises, ball mastery, tricks, juggling, passing or shooting practice. Minimum 15 seconds · maximum 5 minutes."}
                        {form.video_type === "highlight" && "Best moments — can combine several matches. We'll judge game IQ + execution per moment. Minimum 15 seconds · maximum 5 minutes."}
                      </p>
                    </div>
                  </div>

                  {/* ── Required player photo — upload OR use the locked video image ── */}
                  <div data-testid="upload-player-photo-section">
                    <label className="text-[11px] font-bold text-ink/70 block mb-1.5">Player photo <span className="text-forest">*</span></label>
                    <input
                      ref={photoInputRef}
                      type="file"
                      accept="image/*"
                      className="hidden"
                      onChange={(e) => { handlePhotoFile(e.target.files?.[0]); e.target.value = ""; }}
                      data-testid="upload-player-photo-input"
                    />
                    {photoSource ? (
                      <div className="rounded-2xl bg-cream-base/70 border border-forest/25 p-3 flex items-center gap-3.5" data-testid="upload-photo-preview">
                        <img
                          src={photoSource === "upload" ? playerPhoto?.dataUrl : markerPreviewUrl}
                          alt="Player"
                          className="w-14 h-14 rounded-xl object-cover bg-black border border-ink/10 shrink-0"
                        />
                        <div className="min-w-0 flex-1">
                          <p className="flex items-center gap-1.5 text-[13px] font-black text-ink">
                            <CheckCircle2 className="w-4 h-4 text-forest shrink-0" />
                            {photoSource === "upload" ? "Photo added" : "Using the locked video image"}
                          </p>
                          <p className="text-[11px] text-ink/55 mt-0.5">Shown on the player's report profile.</p>
                        </div>
                        <button
                          type="button"
                          onClick={() => { setPlayerPhoto(null); setPhotoSource(null); }}
                          data-testid="upload-photo-remove"
                          className="shrink-0 rounded-xl border border-ink/15 hover:border-forest text-ink/60 hover:text-forest p-2 transition-colors"
                          aria-label="Remove photo"
                        >
                          <XIcon className="w-4 h-4" />
                        </button>
                      </div>
                    ) : (
                      <div className="grid grid-cols-2 gap-2.5">
                        <button
                          type="button"
                          onClick={() => photoInputRef.current?.click()}
                          data-testid="upload-photo-upload-btn"
                          className="rounded-2xl border-2 border-dashed border-ink/20 hover:border-forest bg-cream-base/50 px-3 py-3.5 flex items-center justify-center gap-2.5 transition-colors"
                        >
                          <Camera className="w-4.5 h-4.5 text-forest shrink-0" />
                          <span className="text-left">
                            <span className="block font-barlow font-black uppercase tracking-wide text-[12px] text-ink leading-none">Upload photo</span>
                            <span className="block text-ink/50 text-[10px] mt-1">From your device</span>
                          </span>
                        </button>
                        <button
                          type="button"
                          onClick={() => {
                            if (!markerPreviewUrl) { toast.error("Lock onto your player in step 2 first."); return; }
                            setPhotoSource("video_crop");
                            toast.success("We'll use the locked video image as the player photo.");
                          }}
                          data-testid="upload-photo-crop-btn"
                          className={`rounded-2xl border-2 border-dashed px-3 py-3.5 flex items-center justify-center gap-2.5 transition-colors ${markerPreviewUrl ? "border-ink/20 hover:border-forest bg-cream-base/50" : "border-ink/10 bg-cream-base/30 opacity-50"}`}
                        >
                          <Crosshair className="w-4.5 h-4.5 text-forest shrink-0" />
                          <span className="text-left">
                            <span className="block font-barlow font-black uppercase tracking-wide text-[12px] text-ink leading-none">Use video image</span>
                            <span className="block text-ink/50 text-[10px] mt-1">Your locked player frame</span>
                          </span>
                        </button>
                      </div>
                    )}
                  </div>

                  <div>
                    <label className="text-[11px] font-bold text-ink/70 block mb-1.5">Which player are you in the video? <span className="text-forest">*</span></label>
                    <div className="relative">
                      <Crosshair className="absolute left-3.5 top-3.5 w-4 h-4 text-ink/40 pointer-events-none" />
                      <textarea
                        required
                        value={form.description}
                        onChange={(e) => setField("description", e.target.value)}
                        data-testid="upload-player-description"
                        rows={2}
                        className="w-full bg-white border border-gray-border rounded-xl pl-10 pr-3 py-2.5 sm:py-3 text-sm text-ink focus:outline-none focus:border-forest focus:ring-1 focus:ring-forest resize-none"
                        placeholder="e.g. I am number 10 in the white shirt — the one you just marked above."
                      />
                    </div>
                  </div>

                  {/* OPTIONAL social-feature consent — never required, default OFF (GDPR art. 7) */}
                  <button
                    type="button"
                    onClick={() => setFeatureConsent((v) => !v)}
                    data-testid="upload-feature-consent-card"
                    className={`w-full text-left rounded-2xl border-2 px-4 py-3.5 transition-colors ${featureConsent ? "border-forest bg-forest/5" : "border-dashed border-ink/20 bg-cream-base/50 hover:border-forest/50"}`}
                  >
                    <div className="flex items-start gap-3">
                      <span
                        data-testid="upload-feature-consent-checkbox"
                        aria-checked={featureConsent}
                        role="checkbox"
                        className={`mt-0.5 w-5 h-5 rounded-md border-2 flex items-center justify-center shrink-0 transition-colors ${featureConsent ? "bg-forest border-forest" : "bg-white border-ink/30"}`}
                      >
                        {featureConsent && <Check className="w-3.5 h-3.5 text-white" strokeWidth={3} />}
                      </span>
                      <span>
                        <span className="flex items-center gap-1.5 font-barlow font-black uppercase tracking-wide text-[12.5px] text-ink leading-none">
                          <Zap className="w-3.5 h-3.5 text-forest" style={{ fill: "#A6C800", color: "#A6C800" }} />
                          Show off your talent — get featured!
                        </span>
                        <span className="block text-[12px] text-ink/65 leading-snug mt-1.5">
                          Yes — ScoutMePlay may share {form.player_name?.trim() ? `${form.player_name.trim().split(" ")[0]}'s` : "my player's"} cinematic
                          intro clip on our Instagram &amp; Facebook, celebrating real players and inspiring the next ones.
                        </span>
                        <span className="block text-[10.5px] text-ink/45 leading-snug mt-1.5">
                          100% optional — your report works exactly the same without it. Withdraw anytime in your
                          Dashboard. For players under 18 this consent is given by the parent/guardian.
                        </span>
                      </span>
                    </div>
                  </button>

                  <div>
                    <button
                      type="submit"
                      disabled={submitting || !file || !markerBlob}
                      data-testid="upload-submit-btn"
                      className="w-full rounded-2xl bg-forest hover:bg-forest-pop text-white font-barlow font-black uppercase tracking-[0.16em] text-base px-8 py-4 shadow-lg shadow-forest/25 active:scale-[0.98] transition-[transform,box-shadow,background-color] duration-200 disabled:opacity-40 disabled:cursor-not-allowed flex items-center justify-center gap-3"
                    >
                      {submitting ? (
                        <>
                          <Loader2 className="w-5 h-5 animate-spin" />
                          Locking on · tracking · analysing
                        </>
                      ) : (
                        <>
                          <Rocket className="w-5 h-5" />
                          {form.player_name?.trim() ? `Start ${form.player_name.trim().split(" ")[0]}'s analysis` : "Start the analysis"}
                        </>
                      )}
                    </button>
                    <p className="mt-2.5 text-xs text-ink/55 text-center flex items-center justify-center gap-1.5">
                      <ShieldCheck className="w-3.5 h-3.5 text-forest" />
                      {form.player_name?.trim() ? `Takes about 5 minutes. ${form.player_name.trim().split(" ")[0]}'s personal report will be waiting.` : "Takes about 5 minutes. You'll get your personal report."}
                    </p>
                  </div>
                </div>
              )}
            </section>
          </form>

          {/* ===== TRUST FOOTER STRIP ===== */}
          <section className="mt-4 sm:mt-6 bg-surface rounded-3xl border border-gray-border px-5 sm:px-8 py-4 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
            <div className="flex items-start gap-3">
              <Heart className="w-6 h-6 shrink-0 mt-0.5" style={{ color: "#A6C800", fill: "#A6C800" }} />
              <div>
                <p className="font-bold text-ink text-sm">Because every player deserves to know their true potential.</p>
                <p className="text-ink/55 text-xs mt-0.5">We&rsquo;re here to help them take the next step.</p>
              </div>
            </div>
            <div className="flex items-center gap-3">
              <div className="flex -space-x-2.5">
                {[
                  { i: "MK", c: "#1F4F2F" },
                  { i: "LA", c: "#2D6B3D" },
                  { i: "SJ", c: "#0A0F0D" },
                  { i: "NP", c: "#8A6D3B" },
                ].map((a) => (
                  <span key={a.i} className="w-9 h-9 rounded-full border-2 border-white flex items-center justify-center text-[10px] font-black text-white" style={{ background: a.c }}>
                    {a.i}
                  </span>
                ))}
              </div>
              <p className="text-[11px] text-ink/60 leading-snug max-w-[130px]">Trusted by players and parents all over the world.</p>
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}
