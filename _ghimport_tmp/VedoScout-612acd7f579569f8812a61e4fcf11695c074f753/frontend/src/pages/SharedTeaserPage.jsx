// SharedTeaserPage — public landing for a shared free-preview card (/s/:token).
import React, { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { Sparkles, ChevronRight, Loader2 } from "lucide-react";
import api from "@/lib/api";
import Navigation from "@/components/Navigation";

const LIME = "#CCFF00";
const INKG = "#0B1F14";
const ASSET_BASE = process.env.REACT_APP_BACKEND_URL || "";

export default function SharedTeaserPage() {
  const { token } = useParams();
  const [data, setData] = useState(null);
  const [err, setErr] = useState(false);

  useEffect(() => {
    api.get(`/teaser/${token}`).then(({ data }) => setData(data)).catch(() => setErr(true));
  }, [token]);

  if (err) {
    return (
      <div className="min-h-screen bg-[#F2EDE2]">
        <Navigation />
        <div className="max-w-lg mx-auto pt-28 px-6 text-center" data-testid="teaser-not-found">
          <h1 className="font-barlow font-black uppercase text-2xl text-[#101B12]">This story has moved on</h1>
          <p className="text-sm text-[#5C6657] mt-2">But every player has one waiting to be discovered.</p>
          <Link to="/upload" className="inline-flex items-center gap-2 mt-5 rounded-full px-8 py-3.5 font-barlow font-black uppercase text-[13px]" style={{ background: INKG, color: LIME }}>
            Discover your player&rsquo;s story <ChevronRight className="w-4 h-4" />
          </Link>
        </div>
      </div>
    );
  }
  if (!data) {
    return (
      <div className="min-h-screen bg-[#F2EDE2] flex items-center justify-center">
        <Loader2 className="w-7 h-7 animate-spin text-[#12402A]" />
      </div>
    );
  }

  const s = data.story || {};
  return (
    <div className="min-h-screen bg-[#F2EDE2] pb-20" data-testid="shared-teaser-page">
      <Navigation />
      <div className="max-w-lg mx-auto pt-24 px-5">
        <div className="text-center">
          <div className="inline-flex items-center gap-2 text-[10px] font-extrabold tracking-[0.22em] uppercase text-[#5C7A00]">
            <Sparkles className="w-3.5 h-3.5" /> A story discovered on video
          </div>
          <h1 className="font-barlow font-black uppercase text-[30px] leading-tight text-[#101B12] mt-2">
            {data.player_first}&rsquo;s first chapter
          </h1>
        </div>

        {data.card_feed_url && (
          <img
            src={`${ASSET_BASE}${data.card_feed_url}`}
            alt={`${data.player_first}'s card`}
            data-testid="teaser-card-image"
            className="w-full rounded-[22px] mt-5 shadow-xl"
          />
        )}

        {s.label && (
          <div className="bg-white rounded-2xl border border-[#E5DFCE] p-5 mt-5 shadow-sm" data-testid="teaser-story-card">
            <div className="flex items-start justify-between">
              <div className="font-barlow font-black uppercase text-[17px] text-[#101B12]">{s.label}</div>
              <div className="font-barlow font-black text-[28px] leading-none text-[#12402A]">
                {Number(s.score).toFixed(1)}<span className="text-[11px] font-bold text-[#8B957F]">/10</span>
              </div>
            </div>
            {(s.lines || []).map((l, i) => (
              <p key={i} className={`text-[13px] leading-[1.55] mt-2 ${i === 0 ? "text-[#174A30] font-semibold" : "text-[#3C4A40]"}`}>{l}</p>
            ))}
          </div>
        )}

        <div className="rounded-[22px] mt-5 p-6 text-center" style={{ background: INKG }}>
          <p className="text-white/85 text-[14px] font-semibold leading-relaxed">
            One video was enough to start {data.player_first}&rsquo;s story.<br />
            <span style={{ color: LIME }}>Your player has one too.</span>
          </p>
          <Link to="/upload" data-testid="teaser-cta-btn"
            className="inline-flex items-center gap-2 mt-4 rounded-full px-9 py-3.5 font-barlow font-black uppercase tracking-[0.05em] text-[14px] active:scale-[0.98] transition-transform"
            style={{ background: LIME, color: INKG }}>
            Discover your player&rsquo;s story <ChevronRight className="w-4 h-4" />
          </Link>
          <div className="text-white/45 text-[10.5px] mt-2.5">Free to try · takes about 5 minutes</div>
        </div>
      </div>
    </div>
  );
}
