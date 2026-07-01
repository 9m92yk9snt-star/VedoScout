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
      className="relative py-20 md:py-28 overflow-hidden bg-[#0A0F0D] text-white"
    >
      {/* Cinematic Nano Banana background */}
      <div className="absolute inset-0 -z-10 opacity-40 pointer-events-none">
        <img
          src={`${BACKEND_URL}/api/static/landing/demo-video-section-bg.png`}
          alt=""
          className="w-full h-full object-cover"
        />
        <div className="absolute inset-0 bg-gradient-to-b from-[#0A0F0D] via-[#0A0F0D]/60 to-[#0A0F0D]" />
      </div>

      {/* Grain overlay */}
      <div
        aria-hidden
        className="absolute inset-0 -z-10 opacity-[0.06] mix-blend-overlay pointer-events-none"
        style={{
          backgroundImage:
            "url(\"data:image/svg+xml,%3Csvg viewBox='0 0 200 200' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='2' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E\")",
        }}
      />

      <div className="max-w-7xl mx-auto px-6 md:px-10">
        {/* Header */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          className="flex items-end justify-between flex-wrap gap-4 mb-10 md:mb-14"
        >
          <div>
            <div className="flex items-center gap-2 mb-3">
              <Video className="w-4 h-4 text-volt" />
              <span className="text-[10px] uppercase tracking-[0.28em] font-black text-volt">
                Watch the workflow
              </span>
            </div>
            <h2 className="font-barlow font-black uppercase tracking-tighter text-3xl md:text-5xl lg:text-6xl leading-[0.9]">
              See how<br /><span className="text-volt">it actually works.</span>
            </h2>
            <p className="mt-3 text-white/60 max-w-md leading-relaxed">
              Short walkthroughs recorded by our team. Real screen, real report.
            </p>
          </div>

          {videos.length > 1 && (
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => scrollBy(-1)}
                data-testid="demo-carousel-prev"
                aria-label="Previous video"
                className="w-11 h-11 border border-white/20 hover:border-volt hover:bg-volt/10 text-white flex items-center justify-center transition-colors"
              >
                <ChevronLeft className="w-5 h-5" />
              </button>
              <button
                type="button"
                onClick={() => scrollBy(1)}
                data-testid="demo-carousel-next"
                aria-label="Next video"
                className="w-11 h-11 border border-white/20 hover:border-volt hover:bg-volt/10 text-white flex items-center justify-center transition-colors"
              >
                <ChevronRight className="w-5 h-5" />
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

        {/* Dots */}
        {videos.length > 1 && (
          <div className="mt-6 flex items-center justify-center gap-1.5">
            {videos.map((v, i) => (
              <div key={v.id} className="w-1 h-1 bg-white/20 rounded-full" />
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
      className="snap-start shrink-0 w-[85%] sm:w-[70%] md:w-[520px] lg:w-[640px] bg-[#0F1712] border border-dashed border-white/15 overflow-hidden flex items-center justify-center"
    >
      <div className="aspect-[16/9] w-full flex flex-col items-center justify-center px-8 text-center">
        <div className="w-14 h-14 border-2 border-volt/40 bg-volt/5 flex items-center justify-center mb-5">
          <Video className="w-6 h-6 text-volt" strokeWidth={1.5} />
        </div>
        <div className="text-[10px] uppercase tracking-[0.24em] font-black text-volt mb-3">
          Coming soon
        </div>
        <h3 className="font-barlow font-black uppercase text-xl md:text-2xl leading-tight text-white/90 max-w-sm">
          First workflow clips landing here shortly.
        </h3>
        <p className="mt-3 text-sm text-white/50 max-w-md leading-relaxed">
          Short iPhone demos of the upload → mark → report flow will appear in this carousel.
        </p>
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
      className="snap-start shrink-0 w-[85%] sm:w-[70%] md:w-[420px] lg:w-[460px] bg-[#0F1712] border border-white/10 overflow-hidden group"
    >
      {/* Media */}
      <div className="relative aspect-[9/16] max-h-[560px] bg-black">
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
            <div className="relative w-16 h-16 md:w-20 md:h-20 bg-volt text-ink rounded-full flex items-center justify-center transition-transform group-hover/play:scale-110 shadow-lg shadow-black/40">
              <Play className="w-7 h-7 md:w-8 md:h-8 ml-1" fill="currentColor" />
            </div>
          </button>
        )}
      </div>

      {/* Meta */}
      <div className="px-5 py-4 border-t border-white/5">
        <h3 className="font-barlow font-black uppercase text-lg md:text-xl tracking-tight leading-none">
          {video.title}
        </h3>
        {video.subtitle && (
          <p className="mt-2 text-white/60 text-sm leading-snug">{video.subtitle}</p>
        )}
      </div>
    </article>
  );
}
