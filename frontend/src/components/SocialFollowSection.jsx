// SocialFollowSection — compact side-by-side Instagram + Facebook follow cards.
import React, { useEffect, useRef, useState } from "react";
import { Instagram, Facebook, ArrowUpRight } from "lucide-react";
import api from "@/lib/api";

function formatFollowers(n) {
  if (n >= 1000000) return `${(n / 1000000).toFixed(1).replace(/\.0$/, "")}M`;
  if (n >= 1000) return `${(n / 1000).toFixed(1).replace(/\.0$/, "")}K`;
  return String(n);
}

function CountUp({ value, testid }) {
  const [display, setDisplay] = useState(0);
  const ref = useRef(null);
  const started = useRef(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return undefined;
    const io = new IntersectionObserver((entries) => {
      if (!entries[0].isIntersecting || started.current) return;
      started.current = true;
      const t0 = performance.now();
      const dur = 1200;
      const tick = (t) => {
        const p = Math.min(1, (t - t0) / dur);
        setDisplay(Math.round(value * (1 - Math.pow(1 - p, 3))));
        if (p < 1) requestAnimationFrame(tick);
      };
      requestAnimationFrame(tick);
    }, { threshold: 0.4 });
    io.observe(el);
    return () => io.disconnect();
  }, [value]);

  return <span ref={ref} data-testid={testid}>{formatFollowers(display)}</span>;
}

function FollowCard({ network, icon: Icon, url, followers, accent, chipStyle, label }) {
  return (
    <a
      href={url}
      target="_blank"
      rel="noopener noreferrer"
      data-testid={`social-card-${network}`}
      className="group relative bg-surface border border-gray-border rounded-xl p-4 md:p-5 flex flex-col gap-3 transition-all duration-300 hover:-translate-y-0.5 hover:shadow-lg"
      style={{ "--accent": accent }}
      onMouseEnter={(e) => { e.currentTarget.style.borderColor = accent; }}
      onMouseLeave={(e) => { e.currentTarget.style.borderColor = ""; }}
    >
      <div className="flex items-center justify-between">
        <span className="w-9 h-9 md:w-10 md:h-10 rounded-lg flex items-center justify-center shrink-0" style={chipStyle}>
          <Icon className="w-4.5 h-4.5 md:w-5 md:h-5 text-white" strokeWidth={2} />
        </span>
        <ArrowUpRight className="w-4 h-4 text-ink/30 transition-all duration-300 group-hover:translate-x-0.5 group-hover:-translate-y-0.5" style={{ color: undefined }} />
      </div>
      <div>
        <div className="font-barlow font-black uppercase text-ink text-sm md:text-base leading-none tracking-tight">{label}</div>
        {followers > 0 ? (
          <div className="mt-1.5 text-[11px] md:text-xs text-ink/55 font-bold">
            <span className="font-barlow font-black text-ink text-lg md:text-xl mr-1" style={{ color: accent }}>
              <CountUp value={followers} testid={`social-follow-count-${network}`} />
            </span>
            followers &amp; counting
          </div>
        ) : (
          <div className="mt-1.5 text-[11px] md:text-xs text-ink/55 font-bold" data-testid={`social-follow-count-${network}`}>
            Join us from day one
          </div>
        )}
      </div>
      <span
        className="mt-auto inline-flex items-center justify-center gap-1.5 rounded-full font-barlow font-black uppercase tracking-[0.14em] text-[11px] py-2 px-3 text-white transition-transform duration-200 group-hover:scale-[1.03]"
        style={chipStyle}
        data-testid={`social-follow-btn-${network}`}
      >
        <Icon className="w-3.5 h-3.5" /> Follow
      </span>
    </a>
  );
}

export default function SocialFollowSection() {
  const [data, setData] = useState(null);

  useEffect(() => {
    api.get("/social-follow").then(({ data }) => setData(data)).catch(() => {});
  }, []);

  if (!data || data.enabled === false) return null;
  const insta = data.instagram || {};
  const face = data.facebook || {};
  if (!insta.url && !face.url) return null;

  const igGradient = "linear-gradient(45deg,#F58529 0%,#DD2A7B 45%,#8134AF 75%,#515BD4 100%)";

  return (
    <section className="relative px-6 md:px-10 py-10 md:py-14 bg-cream-soft/50 border-y border-gray-border" data-testid="social-follow-section">
      <div className="relative max-w-2xl mx-auto">
        <div className="text-center">
          <div className="text-[10px] font-extrabold tracking-[0.26em] uppercase text-forest">Join the journey</div>
          <h2 className="font-barlow font-black uppercase text-[22px] md:text-[28px] text-ink leading-tight mt-1.5">
            Be part of the <span className="text-forest">story.</span>
          </h2>
          <p className="text-ink/60 text-[13px] md:text-sm mt-1.5 max-w-md mx-auto">
            Follow players chasing their dream — and get every new story first.
          </p>
        </div>
        <div className="mt-6 grid grid-cols-2 gap-3 md:gap-4">
          {insta.url && (
            <FollowCard
              network="instagram" icon={Instagram} url={insta.url} followers={insta.followers || 0}
              accent="#DD2A7B" label="Instagram"
              chipStyle={{ background: igGradient }}
            />
          )}
          {face.url && (
            <FollowCard
              network="facebook" icon={Facebook} url={face.url} followers={face.followers || 0}
              accent="#1877F2" label="Facebook"
              chipStyle={{ background: "#1877F2" }}
            />
          )}
        </div>
      </div>
    </section>
  );
}
