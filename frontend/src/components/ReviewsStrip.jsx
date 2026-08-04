// ReviewsStrip — compact, horizontally scrollable feedback cards (players + parents).
import React, { useEffect, useRef, useState } from "react";
import { Star, ChevronLeft, ChevronRight } from "lucide-react";
import api from "@/lib/api";

const ASSET_BASE = process.env.REACT_APP_BACKEND_URL || "";

function Stars({ n }) {
  return (
    <span className="flex gap-0.5">
      {[1, 2, 3, 4, 5].map((i) => (
        <Star key={i} className="w-3 h-3" style={{ color: i <= n ? "#B9CE00" : "#D8D3C4", fill: i <= n ? "#B9CE00" : "none" }} />
      ))}
    </span>
  );
}

export default function ReviewsStrip() {
  const [items, setItems] = useState([]);
  const trackRef = useRef(null);

  useEffect(() => {
    api.get("/reviews").then(({ data }) => setItems(data?.items || [])).catch(() => {});
  }, []);

  const scrollBy = (dir) => {
    const el = trackRef.current;
    if (!el) return;
    el.scrollBy({ left: dir * 260, behavior: "smooth" });
  };

  if (!items.length) return null;
  return (
    <section className="py-12 md:py-16 px-6 md:px-10 border-b border-gray-border" data-testid="reviews-strip" style={{ background: "#F2EDE2" }}>
      <div className="max-w-6xl mx-auto">
        <div className="flex items-end justify-between flex-wrap gap-3">
          <div>
            <div className="text-[10px] font-extrabold tracking-[0.24em] uppercase text-[#5C7A00]">Players &amp; parents · in their own words</div>
            <h2 className="font-barlow font-black uppercase text-[26px] md:text-[32px] text-[#101B12] leading-tight mt-1">
              Honest feedback that <span className="text-forest">moves players forward.</span>
            </h2>
          </div>
          <div className="hidden sm:flex items-center gap-2">
            <button type="button" onClick={() => scrollBy(-1)} data-testid="reviews-scroll-prev" aria-label="Previous reviews"
              className="w-8 h-8 border border-[#101B12]/20 hover:border-forest hover:bg-forest/5 text-[#101B12] flex items-center justify-center transition-colors">
              <ChevronLeft className="w-3.5 h-3.5" />
            </button>
            <button type="button" onClick={() => scrollBy(1)} data-testid="reviews-scroll-next" aria-label="Next reviews"
              className="w-8 h-8 border border-[#101B12]/20 hover:border-forest hover:bg-forest/5 text-[#101B12] flex items-center justify-center transition-colors">
              <ChevronRight className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
        <div
          ref={trackRef}
          data-testid="reviews-track"
          className="flex gap-4 overflow-x-auto snap-x snap-mandatory scroll-smooth mt-6 pb-2 -mx-6 px-6 md:mx-0 md:px-0 smp-reviews-scroll"
          style={{ scrollbarWidth: "none", msOverflowStyle: "none" }}
        >
          {items.map((r) => (
            <div key={r.id} className="snap-start shrink-0 w-[230px] bg-white rounded-2xl border border-[#E5DFCE] p-4 shadow-sm" data-testid={`review-card-${r.id}`}>
              <div className="flex items-center gap-3">
                {r.image_url ? (
                  <img src={r.image_url.startsWith("http") ? r.image_url : `${ASSET_BASE}${r.image_url}`} alt="" className="w-10 h-10 rounded-full object-cover border-2 border-[#CCFF00]" />
                ) : (
                  <span className="w-10 h-10 rounded-full bg-[#12402A] text-[#CCFF00] flex items-center justify-center font-barlow font-black text-[15px]">
                    {(r.name || "?").slice(0, 1).toUpperCase()}
                  </span>
                )}
                <div className="min-w-0">
                  <div className="font-barlow font-black text-[12px] text-[#101B12] uppercase leading-none truncate">{r.name}</div>
                  <div className="mt-1"><Stars n={r.stars} /></div>
                </div>
              </div>
              <p className="text-[12.5px] text-[#3C4A40] leading-[1.45] mt-3 line-clamp-2">&ldquo;{r.text}&rdquo;</p>
            </div>
          ))}
        </div>
      </div>
      <style>{`.smp-reviews-scroll::-webkit-scrollbar{display:none;}`}</style>
    </section>
  );
}
