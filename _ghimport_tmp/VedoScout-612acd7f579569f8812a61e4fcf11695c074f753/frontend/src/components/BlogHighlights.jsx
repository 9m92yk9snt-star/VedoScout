// BlogHighlights — compact swipeable strip with the 3 newest journal articles.
import React, { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { ChevronLeft, ChevronRight, Clock, ArrowRight } from "lucide-react";
import api from "@/lib/api";

const ASSET_BASE = process.env.REACT_APP_BACKEND_URL || "";
const img = (u) => (u && !u.startsWith("http") ? `${ASSET_BASE}${u}` : u);

function PostCard({ post }) {
  return (
    <Link
      to={`/blog/${post.slug}`}
      data-testid={`blog-highlight-${post.slug}`}
      className="group snap-start shrink-0 w-[78vw] max-w-[300px] md:w-auto md:max-w-none md:shrink relative flex flex-col rounded-2xl overflow-hidden bg-white border border-[#E5DFCE] shadow-sm transition-all duration-300 hover:-translate-y-1 hover:shadow-lg"
    >
      <div className="relative aspect-[16/10] overflow-hidden bg-ink">
        <img
          src={img(post.cover_image_url)}
          alt={post.cover_image_alt || post.title}
          loading="lazy"
          onError={(e) => { e.currentTarget.style.display = "none"; }}
          className="absolute inset-0 w-full h-full object-cover transition-transform duration-700 group-hover:scale-105"
        />
        <div aria-hidden className="absolute inset-0 bg-gradient-to-t from-ink/60 via-transparent to-transparent" />
        <span className="absolute top-3 left-3 text-[9px] font-black uppercase tracking-[0.16em] px-2.5 py-1 rounded-full bg-[#12402A] text-[#CCFF00]">
          {post.category}
        </span>
        <span className="absolute bottom-3 right-3 inline-flex items-center gap-1 text-[10px] font-bold text-white/85">
          <Clock className="w-3 h-3" /> {post.reading_time_minutes || 3} min
        </span>
      </div>
      <div className="flex flex-col flex-1 p-4">
        <h3 className="font-barlow font-black uppercase text-[15px] leading-tight text-[#101B12] line-clamp-2 group-hover:text-forest transition-colors">
          {post.title}
        </h3>
        <p className="mt-2 text-[12px] text-[#5A6157] leading-snug line-clamp-2">{post.subtitle || post.excerpt}</p>
        <span className="mt-auto pt-3 inline-flex items-center gap-1.5 text-[10.5px] font-black uppercase tracking-[0.16em] text-forest">
          Read the story
          <ArrowRight className="w-3 h-3 transition-transform group-hover:translate-x-1" />
        </span>
      </div>
    </Link>
  );
}

export default function BlogHighlights() {
  const [posts, setPosts] = useState([]);
  const trackRef = useRef(null);
  const [edge, setEdge] = useState({ start: true, end: false });

  useEffect(() => {
    api.get("/blog/posts?limit=3").then(({ data }) => setPosts(data?.items || [])).catch(() => {});
  }, []);

  const updateEdge = () => {
    const el = trackRef.current;
    if (!el) return;
    const max = el.scrollWidth - el.clientWidth;
    setEdge({ start: el.scrollLeft <= 8, end: el.scrollLeft >= max - 8 });
  };

  const nudge = (dir) => {
    const el = trackRef.current;
    if (!el) return;
    const card = el.querySelector("a");
    const step = (card?.offsetWidth || 280) + 16;
    const max = el.scrollWidth - el.clientWidth;
    el.scrollTo({ left: Math.max(0, Math.min(max, el.scrollLeft + dir * step)), behavior: "smooth" });
  };

  if (!posts.length) return null;
  return (
    <section className="py-12 md:py-16 px-6 md:px-10 border-b border-gray-border" style={{ background: "#F2EDE2" }} data-testid="blog-highlights">
      <div className="max-w-6xl mx-auto">
        <div className="flex items-end justify-between flex-wrap gap-3">
          <div>
            <div className="text-[10px] font-extrabold tracking-[0.24em] uppercase text-[#5C7A00]">From the journal</div>
            <h2 className="font-barlow font-black uppercase text-[26px] md:text-[32px] text-[#101B12] leading-tight mt-1">
              Stories that <span className="text-forest">build players.</span>
            </h2>
          </div>
          <Link to="/blog" data-testid="blog-highlights-all" className="group inline-flex items-center gap-1.5 text-[11px] font-black uppercase tracking-[0.18em] text-forest hover:text-[#12402A] transition-colors">
            All articles <ArrowRight className="w-3.5 h-3.5 transition-transform group-hover:translate-x-1" />
          </Link>
        </div>

        <div className="relative mt-6">
          <div
            ref={trackRef}
            onScroll={updateEdge}
            className="flex md:grid md:grid-cols-3 gap-4 overflow-x-auto md:overflow-visible snap-x snap-mandatory scroll-smooth pb-2 md:pb-0 smp-blog-scroll"
            style={{ scrollbarWidth: "none", msOverflowStyle: "none", overscrollBehaviorX: "contain", transform: "translateZ(0)" }}
          >
            {posts.map((p) => <PostCard key={p.slug} post={p} />)}
          </div>
          <button
            type="button" aria-label="Previous article" data-testid="blog-arrow-prev" onClick={() => nudge(-1)}
            disabled={edge.start}
            className={`md:hidden absolute left-1 top-1/2 -translate-y-1/2 z-20 w-10 h-10 rounded-full flex items-center justify-center backdrop-blur-md active:scale-90 transition-all duration-300 ${edge.start ? "opacity-25 pointer-events-none" : "opacity-100"}`}
            style={{ background: "rgba(10,20,14,0.62)", border: "1px solid rgba(204,255,0,0.55)", boxShadow: "0 4px 16px rgba(0,0,0,0.3)" }}
          >
            <ChevronLeft className="w-5 h-5" style={{ color: "#CCFF00" }} />
          </button>
          <button
            type="button" aria-label="Next article" data-testid="blog-arrow-next" onClick={() => nudge(1)}
            disabled={edge.end}
            className={`md:hidden absolute right-1 top-1/2 -translate-y-1/2 z-20 w-10 h-10 rounded-full flex items-center justify-center backdrop-blur-md active:scale-90 transition-all duration-300 ${edge.end ? "opacity-25 pointer-events-none" : "opacity-100"}`}
            style={{ background: "rgba(10,20,14,0.62)", border: "1px solid rgba(204,255,0,0.55)", boxShadow: "0 4px 16px rgba(0,0,0,0.3)" }}
          >
            <ChevronRight className="w-5 h-5" style={{ color: "#CCFF00" }} />
          </button>
        </div>
      </div>
      <style>{`.smp-blog-scroll::-webkit-scrollbar{display:none;}`}</style>
    </section>
  );
}
