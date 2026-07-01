import React, { useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import { ChevronLeft, ChevronRight, Play, Video } from "lucide-react";
import api from "@/lib/api";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const abs = (u) => (u && u.startsWith("http") ? u : `${BACKEND_URL}${u}`);

/**
 * Landing-page swipeable demo-video carousel.
 * Placed directly below the "How it works" section.
 * Videos are admin-uploaded via /admin → "Demo Videos" tab.
 * The section auto-hides when no active videos exist so the landing looks
 * intentional even before the operator uploads anything.
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
    const step = card ? card.getBoundingClientRect().width + 24 : 400;
    el.scrollBy({ left: dir * step, behavior: "smooth" });
  };

  // Wait for the initial fetch to avoid layout flash. Once loaded, ALWAYS render
  // the section — even when the admin hasn't uploaded any videos yet — so the
  // landing page has the anchor visible and the operator can preview the section
  // while they build up content.
  if (loading) return null;

  return (
    <section
      id="demo-videos"
      data-testid="demo-video-carousel"
      className="relative py-14 md:py-16 overflow-hidden bg-cream-base border-y border-ink/10 text-ink"
    >
      {/* Subtle tinted band — no more full black takeover */}
      <div
        aria-hidden
        className="absolute inset-0 -z-10 opacity-30 pointer-events-none"
        style={{
          backgroundImage:
            "radial-gradient(ellipse at 90% 20%, rgba(31,79,47,0.10), transparent 55%)",
        }}
      />

      <div className="max-w-6xl mx-auto px-6 md:px-10">
        {/* Header — compact, one row */}
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          className="flex items-end justify-between flex-wrap gap-3 mb-6 md:mb-8"
        >
          <div>
            <div className="flex items-center gap-2 mb-1.5">
              <Video className="w-3.5 h-3.5 text-forest" />
              <span className="text-[10px] uppercase tracking-[0.24em] font-black text-forest">
                Watch the workflow
              </span>
            </div>
            <h2 className="font-barlow font-black uppercase tracking-tight text-2xl md:text-3xl leading-[0.95]">
              See how <span className="text-forest">it actually works.</span>
            </h2>
            <p className="mt-1.5 text-ink/55 text-sm leading-snug max-w-md">
              {videos.length === 0
                ? "First iPhone workflow demos landing here soon."
                : "Short walkthroughs. Real screen, real report."}
            </p>
          </div>

          {videos.length > 1 && (
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => scrollBy(-1)}
                data-testid="demo-carousel-prev"
                aria-label="Previous video"
                className="w-9 h-9 border border-ink/20 hover:border-forest hover:bg-forest/5 text-ink flex items-center justify-center transition-colors"
              >
                <ChevronLeft className="w-4 h-4" />
              </button>
              <button
                type="button"
                onClick={() => scrollBy(1)}
                data-testid="demo-carousel-next"
                aria-label="Next video"
                className="w-9 h-9 border border-ink/20 hover:border-forest hover:bg-forest/5 text-ink flex items-center justify-center transition-colors"
              >
                <ChevronRight className="w-4 h-4" />
              </button>
            </div>
          )}
        </motion.div>

        {/* Swipeable track */}
        <div
          ref={trackRef}
          className="flex gap-6 overflow-x-auto snap-x snap-mandatory scroll-smooth pb-4 -mx-6 px-6 md:mx-0 md:px-0 no-scrollbar"
          style={{ scrollbarWidth: "none", msOverflowStyle: "none" }}
        >
          {videos.length === 0 ? (
            <EmptyStateCard />
          ) : (
            videos.map((v) => (
              <VideoCard
                key={v.id}
                video={v}
                isPlaying={playingId === v.id}
                onPlay={() => setPlayingId(v.id)}
                onPause={() => setPlayingId(null)}
              />
            ))
          )}
        </div>

        {/* Dots — smaller, subtle */}
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

function EmptyStateCard() {
  return (
    <article
      data-demo-card
      data-testid="demo-empty-state"
      className="snap-start shrink-0 w-[85%] sm:w-[62%] md:w-[420px] bg-white border border-dashed border-ink/20 overflow-hidden flex items-center justify-center"
    >
      <div className="aspect-[16/10] w-full flex flex-col items-center justify-center px-6 text-center">
        <div className="w-10 h-10 border border-forest/40 bg-forest/5 flex items-center justify-center mb-3">
          <Video className="w-4 h-4 text-forest" strokeWidth={1.5} />
        </div>
        <div className="text-[10px] uppercase tracking-[0.22em] font-black text-forest mb-1.5">
          Coming soon
        </div>
        <h3 className="font-barlow font-black uppercase text-base md:text-lg leading-tight text-ink max-w-xs">
          First workflow clips landing here shortly.
        </h3>
      </div>
    </article>
  );
}

function VideoCard({ video, isPlaying, onPlay, onPause }) {
  const videoRef = useRef(null);
  const [started, setStarted] = useState(false);

  const handlePlayClick = async () => {
    setStarted(true);
    onPlay();
    // Slight delay to allow the <video> to mount if it wasn't yet
    requestAnimationFrame(() => {
      videoRef.current?.play().catch(() => { /* user must interact — will retry on next click */ });
    });
  };

  useEffect(() => {
    // If some other card started playing, pause this one
    if (!isPlaying && videoRef.current) {
      try { videoRef.current.pause(); } catch { /* noop */ }
    }
  }, [isPlaying]);

  return (
    <article
      data-demo-card
      data-testid={`demo-card-${video.id}`}
      className="snap-start shrink-0 w-[80%] sm:w-[58%] md:w-[340px] bg-white border border-ink/10 overflow-hidden group"
    >
      {/* Media — smaller, more compact aspect */}
      <div className="relative aspect-[9/14] max-h-[420px] bg-ink">
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
              <div className="absolute inset-0 bg-gradient-to-br from-forest/40 to-ink" />
            )}
            <div className="absolute inset-0 bg-black/30 group-hover/play:bg-black/10 transition-colors" />
            <div className="relative w-12 h-12 md:w-14 md:h-14 bg-volt text-ink rounded-full flex items-center justify-center transition-transform group-hover/play:scale-110 shadow-lg shadow-black/30">
              <Play className="w-5 h-5 md:w-6 md:h-6 ml-0.5" fill="currentColor" />
            </div>
          </button>
        )}
      </div>

      {/* Meta — light theme */}
      <div className="px-4 py-3 border-t border-ink/10">
        <h3 className="font-barlow font-black uppercase text-sm md:text-base tracking-tight leading-tight text-ink">
          {video.title}
        </h3>
        {video.subtitle && (
          <p className="mt-1 text-ink/60 text-xs leading-snug line-clamp-2">{video.subtitle}</p>
        )}
      </div>
    </article>
  );
}
