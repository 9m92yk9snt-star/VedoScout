// ReviewsStrip — small, warm family reviews on the landing page.
import React, { useEffect, useState } from "react";
import { Star } from "lucide-react";
import api from "@/lib/api";

const ASSET_BASE = process.env.REACT_APP_BACKEND_URL || "";

function Stars({ n }) {
  return (
    <span className="flex gap-0.5">
      {[1, 2, 3, 4, 5].map((i) => (
        <Star key={i} className="w-3.5 h-3.5" style={{ color: i <= n ? "#B9CE00" : "#D8D3C4", fill: i <= n ? "#B9CE00" : "none" }} />
      ))}
    </span>
  );
}

export default function ReviewsStrip() {
  const [items, setItems] = useState([]);
  useEffect(() => {
    api.get("/reviews").then(({ data }) => setItems(data?.items || [])).catch(() => {});
  }, []);
  if (!items.length) return null;
  return (
    <section className="py-14 px-5" data-testid="reviews-strip" style={{ background: "#F2EDE2" }}>
      <div className="max-w-6xl mx-auto">
        <div className="text-[10px] font-extrabold tracking-[0.24em] uppercase text-[#5C7A00]">Real families · real discoveries</div>
        <h2 className="font-barlow font-black uppercase text-[26px] md:text-[32px] text-[#101B12] leading-tight mt-1">
          What they found in their players
        </h2>
        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-4 mt-6">
          {items.slice(0, 8).map((r) => (
            <div key={r.id} className="bg-white rounded-2xl border border-[#E5DFCE] p-4 shadow-sm" data-testid={`review-card-${r.id}`}>
              <div className="flex items-center gap-3">
                {r.image_url ? (
                  <img src={r.image_url.startsWith("http") ? r.image_url : `${ASSET_BASE}${r.image_url}`} alt="" className="w-11 h-11 rounded-full object-cover border-2 border-[#CCFF00]" />
                ) : (
                  <span className="w-11 h-11 rounded-full bg-[#12402A] text-[#CCFF00] flex items-center justify-center font-barlow font-black text-[16px]">
                    {(r.name || "?").slice(0, 1).toUpperCase()}
                  </span>
                )}
                <div>
                  <div className="font-barlow font-black text-[13px] text-[#101B12] uppercase leading-none">{r.name}</div>
                  <div className="mt-1"><Stars n={r.stars} /></div>
                </div>
              </div>
              <p className="text-[12.5px] text-[#3C4A40] leading-[1.5] mt-3 line-clamp-2">{r.text}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
