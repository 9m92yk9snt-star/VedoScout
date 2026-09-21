// Blog bottom CTA banner — ScoutMePlay-style dark card with phone mockup,
// used on the blog index + article pages. Links back into the product.
import React from "react";
import { Link } from "react-router-dom";
import { ArrowRight, Play, ShieldCheck } from "lucide-react";
import { ASSET_BASE } from "@/lib/api";

const LIME = "#CCFF00";
const INK = "#0B1F14";

/* Slim in-article CTA — dropped mid-article at a section boundary. */
export function BlogMidCta() {
  return (
    <div
      className="not-prose my-10 rounded-[16px] overflow-hidden"
      style={{ background: INK, borderLeft: `4px solid ${LIME}` }}
      data-testid="blog-midcta"
    >
      <div className="relative flex flex-col sm:flex-row sm:items-center gap-4 px-5 py-4.5 p-5">
        <div aria-hidden className="absolute -top-10 -right-10 w-40 h-40 rounded-full pointer-events-none" style={{ background: `radial-gradient(circle, ${LIME}22, transparent 70%)` }} />
        <span className="w-10 h-10 shrink-0 rounded-full hidden sm:flex items-center justify-center" style={{ background: "rgba(204,255,0,0.14)", border: `1px solid ${LIME}44` }}>
          <Play className="w-4 h-4" style={{ color: LIME }} />
        </span>
        <div className="min-w-0 flex-1">
          <div className="text-[9px] uppercase tracking-[0.26em] font-bold" style={{ color: LIME }}>
            Free scout preview
          </div>
          <div className="text-white font-barlow font-black uppercase text-[16px] leading-tight mt-0.5">
            See your player through a scout&rsquo;s eyes — free.
          </div>
        </div>
        <Link
          to="/signup"
          data-testid="blog-midcta-btn"
          className="relative shrink-0 inline-flex items-center justify-center gap-1.5 font-barlow font-black uppercase tracking-widest text-[11px] px-5 py-2.5 rounded-full transition-transform hover:scale-[1.03] active:scale-[0.98]"
          style={{ background: LIME, color: "#0A1F0F" }}
        >
          Try it free <ArrowRight className="w-3.5 h-3.5" />
        </Link>
      </div>
    </div>
  );
}

export default function BlogCtaBanner({ source = "blog" }) {
  return (
    <section className="max-w-6xl mx-auto px-6 md:px-10 pb-14 md:pb-20" data-testid={`blog-cta-banner-${source}`}>
      <div className="relative overflow-hidden rounded-[24px]" style={{ background: INK }}>
        <div aria-hidden className="absolute -top-24 -right-24 w-96 h-96 rounded-full pointer-events-none" style={{ background: `radial-gradient(circle, ${LIME}26, transparent 68%)` }} />
        <div aria-hidden className="absolute -bottom-32 -left-20 w-80 h-80 rounded-full pointer-events-none" style={{ background: "radial-gradient(circle, rgba(46,125,50,0.35), transparent 70%)" }} />

        <div className="relative grid md:grid-cols-[1.25fr_1fr] gap-8 items-center p-7 md:p-12">
          {/* Copy */}
          <div>
            <div className="inline-flex items-center gap-2">
              <span className="w-1.5 h-1.5 rounded-full animate-pulse" style={{ background: LIME }} />
              <span className="text-[10px] uppercase tracking-[0.3em] font-bold" style={{ color: LIME }}>
                Start scouting
              </span>
            </div>
            <h2 className="mt-4 font-barlow font-black uppercase text-3xl md:text-5xl tracking-tight leading-[0.95] text-white">
              See your game
              <span className="block mt-1" style={{ color: LIME }}>like a real scout.</span>
            </h2>
            <p className="mt-4 text-white/70 text-sm md:text-base leading-relaxed max-w-md">
              Upload one video and get a free instant scout preview.
              No card required to start.
            </p>
            <div className="mt-7 flex flex-wrap items-center gap-5">
              <Link
                to="/signup"
                data-testid={`blog-cta-try-free-${source}`}
                className="inline-flex items-center gap-2 font-barlow font-black uppercase tracking-widest text-sm px-7 py-3.5 rounded-full transition-transform hover:scale-[1.03] active:scale-[0.98]"
                style={{ background: LIME, color: "#0A1F0F", boxShadow: `0 14px 34px -12px ${LIME}66` }}
              >
                Try it free <ArrowRight className="w-4 h-4" />
              </Link>
              <span className="flex items-center gap-2 text-white/60 text-[11px] font-bold">
                <span className="flex -space-x-2" aria-hidden>
                  {["JN", "MK", "LA"].map((x, i) => (
                    <span
                      key={x}
                      className="w-7 h-7 rounded-full border-2 flex items-center justify-center text-[8px] font-black"
                      style={{
                        borderColor: INK,
                        background: i === 1 ? LIME : "#2E7D32",
                        color: i === 1 ? "#0A1F0F" : "#EAF4E7",
                      }}
                    >
                      {x}
                    </span>
                  ))}
                </span>
                Hundreds of players scouted already
              </span>
            </div>
            <div className="mt-5 flex items-center gap-1.5 text-white/45 text-[10px] font-bold uppercase tracking-[0.14em]">
              <ShieldCheck className="w-3.5 h-3.5" /> Free preview · No card · 100% private
            </div>
          </div>

          {/* Phone mockup */}
          <div className="flex justify-center md:justify-end">
            <div
              className="relative w-[190px] md:w-[220px] rounded-[32px] p-2.5 -rotate-2"
              style={{ background: "#1A2B20", border: "1px solid rgba(255,255,255,0.14)", boxShadow: "0 30px 60px -20px rgba(0,0,0,0.6)" }}
              aria-hidden
            >
              <div className="rounded-[24px] overflow-hidden relative aspect-[9/16] bg-black">
                <img
                  src={`${ASSET_BASE}/api/uploads/demo-frame-dribble.jpg`}
                  alt=""
                  className="absolute inset-0 w-full h-full object-cover"
                  loading="lazy"
                />
                <div className="absolute inset-0" style={{ background: "linear-gradient(180deg, rgba(0,0,0,0.25) 0%, transparent 40%, rgba(0,0,0,0.65) 100%)" }} />
                <span className="absolute top-2.5 left-2.5 px-2 py-0.5 text-[8px] font-black uppercase tracking-[0.12em] rounded-full" style={{ background: LIME, color: "#0A1F0F" }}>
                  Live analysis
                </span>
                <span className="absolute inset-0 flex items-center justify-center">
                  <span className="w-12 h-12 rounded-full flex items-center justify-center" style={{ background: "rgba(255,255,255,0.92)" }}>
                    <Play className="w-5 h-5 text-[#0A1F0F] fill-[#0A1F0F] ml-0.5" />
                  </span>
                </span>
                <div className="absolute bottom-2.5 left-2.5 right-2.5">
                  <div className="flex items-center justify-between text-white text-[9px] font-black uppercase tracking-wide">
                    <span>Overall</span>
                    <span style={{ color: LIME }}>8.0</span>
                  </div>
                  <div className="mt-1 h-1 rounded-full bg-white/25 overflow-hidden">
                    <span className="block h-full rounded-full" style={{ width: "80%", background: LIME }} />
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
