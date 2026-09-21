import React, { useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import { ChevronLeft, ChevronRight, Play, Video } from "lucide-react";
import api from "@/lib/api";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const abs = (u) => (u && u.startsWith("http") ? u : `${BACKEND_URL}${u}`);

/**
 * Landing-page swipeable demo-video carousel.
 * Placed directly below the "How it works" section.
 * Design language: light cream base + Nano Banana halo glow behind the card,
 * inline SVG chalk-arrow accents, CSS film-strip perforations.
 */
export default function DemoVideoCarousel() {
  const [videos, setVideos] = useState([]);
  const [loading, setLoading] = useState(true);
  const [playingId, setPlayingId] = useState(null);
  const trackRef = useRef(null);

  useEffect(() => {
    api.get("/demo-videos")
      .then(({ data }) => setVideos(data.items || []))
      .catch(() => setVideos([]))
      .finally(() => setLoading(false));
  }, []);

  const scrollBy = (dir) => {
    const el = trackRef.current;
    if (!el) return;
    const card = el.querySelector("[data-demo-card]");
    const step = card ? card.getBoundingClientRect().width + 24 : 360;
    el.scrollBy({ left: dir * step, behavior: "smooth" });
  };

  if (loading) return null;
  if (videos.length === 0) return null;

  return (
    <section
      id="demo-videos"
      data-testid="demo-video-carousel"
      className="relative py-8 md:py-10 overflow-hidden bg-cream-base border-y border-ink/10 text-ink"
    >
      {/* Warm Nano Banana halo — sits behind the card, punchy but soft */}
      <div
        aria-hidden
        className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 w-[440px] h-[440px] -z-10 pointer-events-none opacity-50"
        style={{
          backgroundImage: `url(${BACKEND_URL}/api/static/landing/demo-halo-bokeh.png)`,
          backgroundSize: "cover",
          backgroundPosition: "center",
          mixBlendMode: "multiply",
        }}
      />

      {/* Inline SVG chalk-arrow — dynamic, points from headline to the card */}
      <ChalkArrow />

      {/* Pitch-line diagonal stripes — subtle chalkboard energy */}
      <div
        aria-hidden
        className="absolute inset-x-0 top-0 h-full -z-10 opacity-[0.04] pointer-events-none"
        style={{
          backgroundImage:
            "repeating-linear-gradient(115deg, transparent 0 32px, #1F4F2F 32px 33px)",
        }}
      />

      <div className="max-w-5xl mx-auto px-6 md:px-10">
        {/* Header — compact, one row */}
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          className="flex items-end justify-between flex-wrap gap-3 mb-4 md:mb-5"
        >
          <div>
            <div className="flex items-center gap-2 mb-1">
              <Video className="w-3 h-3 text-forest" />
              <span className="text-[9px] uppercase tracking-[0.24em] font-black text-forest">
                Watch the workflow
              </span>
              <span aria-hidden className="inline-block w-6 h-px bg-forest/40" />
            </div>
            <h2 className="font-barlow font-black uppercase tracking-tighter text-2xl md:text-3xl leading-[0.95]">
              See how <span className="text-forest">it actually works.</span>
            </h2>
            <p className="mt-1.5 text-ink/55 text-sm leading-snug max-w-md">
              Short walkthroughs. Real screen, real report.
            </p>
          </div>

          {videos.length > 1 && (
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => scrollBy(-1)}
                data-testid="demo-carousel-prev"
                aria-label="Previous video"
                className="w-8 h-8 border border-ink/20 hover:border-forest hover:bg-forest/5 text-ink flex items-center justify-center transition-colors"
              >
                <ChevronLeft className="w-3.5 h-3.5" />
              </button>
              <button
                type="button"
                onClick={() => scrollBy(1)}
                data-testid="demo-carousel-next"
                aria-label="Next video"
                className="w-8 h-8 border border-ink/20 hover:border-forest hover:bg-forest/5 text-ink flex items-center justify-center transition-colors"
              >
                <ChevronRight className="w-3.5 h-3.5" />
              </button>
            </div>
          )}
        </motion.div>

        {/* Swipeable track */}
        <div
          ref={trackRef}
          className="relative flex gap-6 overflow-x-auto snap-x snap-mandatory scroll-smooth pb-4 -mx-6 px-6 md:mx-0 md:px-0 no-scrollbar"
          style={{ scrollbarWidth: "none", msOverflowStyle: "none" }}
        >
          {videos.map((v) => (
            <VideoCard
              key={v.id}
              video={v}
              isPlaying={playingId === v.id}
              onPlay={() => setPlayingId(v.id)}
              onPause={() => setPlayingId(null)}
            />
          ))}
        </div>

        {/* Dots */}
        {videos.length > 1 && (
          <div className="mt-4 flex items-center justify-center gap-1.5">
            {videos.map((v) => (
              <div key={v.id} className="w-1 h-1 bg-ink/25 rounded-full" />
            ))}
          </div>
        )}
      </div>

      <style>{`.no-scrollbar::-webkit-scrollbar{display:none;}`}</style>
    </section>
  );
}

/* ─── Inline SVG chalk arrow — decorative, hidden on mobile ─── */
function ChalkArrow() {
  return (
    <svg
      aria-hidden
      viewBox="0 0 900 300"
      className="hidden md:block absolute left-[38%] top-4 w-[260px] h-[100px] -z-10 pointer-events-none opacity-70"
      preserveAspectRatio="none"
    >
      <defs>
        <filter id="chalkRoughen" x="-2%" y="-10%" width="104%" height="120%">
          <feTurbulence type="fractalNoise" baseFrequency="0.9" numOctaves="2" seed="7" />
          <feDisplacementMap in="SourceGraphic" scale="2.2" />
        </filter>
        <marker id="chalkHead" viewBox="0 0 12 12" refX="10" refY="6"
                markerWidth="7" markerHeight="7" orient="auto-start-reverse">
          <path d="M 0 0 L 12 6 L 0 12 Z" fill="#1F4F2F" opacity="0.75"
                filter="url(#chalkRoughen)" />
        </marker>
      </defs>
      <path
        d="M 20 40 C 220 20, 420 90, 640 210"
        stroke="#1F4F2F"
        strokeWidth="2.2"
        strokeLinecap="round"
        strokeDasharray="6 4"
        fill="none"
        opacity="0.65"
        filter="url(#chalkRoughen)"
        markerEnd="url(#chalkHead)"
      />
    </svg>
  );
}

/* ─── VIDEO CARD ─── */
function VideoCard({ video, isPlaying, onPlay, onPause }) {
  const videoRef = useRef(null);
  const [started, setStarted] = useState(false);

  const handlePlayClick = () => {
    setStarted(true);
    onPlay();
    requestAnimationFrame(() => {
      videoRef.current?.play().catch(() => { /* ignore */ });
    });
  };

  useEffect(() => {
    if (!isPlaying && videoRef.current) {
      try { videoRef.current.pause(); } catch { /* noop */ }
    }
  }, [isPlaying]);

  return (
    <PremiumFrame testid={`demo-card-${video.id}`}>
      <div className="relative aspect-[9/16] bg-black">
        {started ? (
          <video
            ref={videoRef}
            src={abs(video.video_url)}
            poster={video.poster_url ? abs(video.poster_url) : undefined}
            controls
            playsInline
            preload="metadata"
            onPause={onPause}
            className="w-full h-full object-cover bg-black"
            data-testid={`demo-video-el-${video.id}`}
          />
        ) : (
          <button
            type="button"
            onClick={handlePlayClick}
            data-testid={`demo-play-btn-${video.id}`}
            className="absolute inset-0 w-full h-full flex items-center justify-center group/play"
            aria-label={`Play ${video.title}`}
          >
            {video.poster_url ? (
              <img
                src={abs(video.poster_url)}
                alt=""
                className="absolute inset-0 w-full h-full object-cover"
              />
            ) : (
              <div className="absolute inset-0 bg-gradient-to-br from-forest via-forest/70 to-ink" />
            )}
            <div className="absolute inset-0 bg-gradient-to-t from-black/70 via-black/10 to-transparent group-hover/play:from-black/50 transition-colors" />
            {/* Volt play button — larger, bolder, with soft glow */}
            <div className="relative w-16 h-16 md:w-[68px] md:h-[68px] bg-volt text-ink rounded-full flex items-center justify-center transition-transform duration-300 group-hover/play:scale-110 shadow-[0_10px_30px_-4px_rgba(204,255,0,0.55)] ring-4 ring-volt/25">
              <Play className="w-6 h-6 md:w-7 md:h-7 ml-0.5" fill="currentColor" strokeWidth={0} />
            </div>
          </button>
        )}
      </div>
      {/* Caption strip inside the frame */}
      <div className="px-4 py-3 bg-gradient-to-b from-ink to-[#0a1614] border-t border-volt/20">
        <h3 className="font-barlow font-black uppercase text-sm md:text-base tracking-tight leading-tight text-white">
          {video.title}
        </h3>
        {video.subtitle && (
          <p className="mt-1 text-white/55 text-xs leading-snug line-clamp-2">{video.subtitle}</p>
        )}
      </div>
    </PremiumFrame>
  );
}

/* ─── PREMIUM FRAME — clean iPhone-mockup styled bezel with brass ticks ─── */
function PremiumFrame({ children, testid }) {
  return (
    <article
      data-demo-card
      data-testid={testid}
      className="snap-start shrink-0 w-[72%] sm:w-[48%] md:w-[240px] relative group"
    >
      {/* Corner brass ticks — top-left */}
      <span aria-hidden className="absolute -top-1 -left-1 w-3 h-3 border-t-2 border-l-2 border-volt/70 z-10" />
      <span aria-hidden className="absolute -top-1 -right-1 w-3 h-3 border-t-2 border-r-2 border-volt/70 z-10" />
      <span aria-hidden className="absolute -bottom-1 -left-1 w-3 h-3 border-b-2 border-l-2 border-volt/70 z-10" />
      <span aria-hidden className="absolute -bottom-1 -right-1 w-3 h-3 border-b-2 border-r-2 border-volt/70 z-10" />

      {/* Soft glow behind the frame — only visible on hover */}
      <span
        aria-hidden
        className="absolute -inset-2 bg-forest/25 blur-xl opacity-0 group-hover:opacity-60 transition-opacity duration-500 -z-10"
      />

      {/* The frame itself — deep bezel + inner ring, no sprocket holes */}
      <div
        className="relative bg-ink rounded-[10px] p-[3px] shadow-[0_18px_40px_-12px_rgba(31,79,47,0.4),0_2px_0_0_rgba(0,0,0,0.05)] transition-transform duration-500 group-hover:-translate-y-1"
      >
        {/* Inner bezel line — thin volt-tinted ring for the premium feel */}
        <div className="rounded-[8px] overflow-hidden border border-volt/15 bg-black">
          {children}
        </div>
      </div>
    </article>
  );
}
