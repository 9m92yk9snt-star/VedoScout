// SocialFollowSection — Instagram + Facebook follow boxes with admin-managed counts.
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
      const dur = 1400;
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

function FollowCard({ network, icon: Icon, url, followers, accent, chipStyle, btnStyle, handle }) {
  return (
    <a
      href={url}
      target="_blank"
      rel="noopener noreferrer"
      data-testid={`social-card-${network}`}
      className="group relative overflow-hidden rounded-2xl p-6 md:p-8 flex flex-col transition-transform duration-300 hover:-translate-y-1"
      style={{ background: "#0C1810", border: `1px solid ${accent}44`, boxShadow: `0 0 34px -10px ${accent}55` }}
    >
      <span
        aria-hidden
        className="absolute -top-16 -right-16 w-48 h-48 rounded-full opacity-25 blur-2xl pointer-events-none transition-opacity duration-500 group-hover:opacity-45"
        style={{ background: accent }}
      />
      <div className="flex items-center justify-between">
        <span className="w-12 h-12 rounded-xl flex items-center justify-center" style={chipStyle}>
          <Icon className="w-6 h-6 text-white" strokeWidth={2} />
        </span>
        <ArrowUpRight className="w-5 h-5 text-white/40 transition-all duration-300 group-hover:text-white group-hover:translate-x-0.5 group-hover:-translate-y-0.5" />
      </div>
      <div className="mt-6">
        {followers > 0 ? (
          <>
            <div className="font-barlow font-black text-white text-[40px] md:text-[48px] leading-none">
              <CountUp value={followers} testid={`social-follow-count-${network}`} />
            </div>
            <div className="mt-1 text-[10px] uppercase tracking-[0.24em] font-bold text-white/50">Followers &amp; counting</div>
          </>
        ) : (
          <div className="font-barlow font-black text-white text-[22px] md:text-[26px] leading-tight uppercase" data-testid={`social-follow-count-${network}`}>
            Join us from day one
          </div>
        )}
      </div>
      <p className="mt-4 text-[13.5px] text-white/70 leading-relaxed">
        {network === "instagram"
          ? "Player stories, best moments and behind-the-scenes from the pitch."
          : "News, real reports and the journeys of players just like you."}
      </p>
      <span
        className="mt-6 inline-flex items-center justify-center gap-2 rounded-lg font-barlow font-black uppercase tracking-[0.14em] text-[12.5px] py-3 px-5 text-white transition-transform duration-200 group-hover:scale-[1.02]"
        style={btnStyle}
        data-testid={`social-follow-btn-${network}`}
      >
        <Icon className="w-4 h-4" /> Follow {handle}
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
    <section className="relative px-6 md:px-10 py-14 md:py-20 overflow-hidden" style={{ background: "#081109" }} data-testid="social-follow-section">
      <div
        aria-hidden
        className="absolute inset-0 opacity-[0.05] pointer-events-none"
        style={{ backgroundImage: "radial-gradient(circle at 1px 1px, #CCFF00 1px, transparent 0)", backgroundSize: "30px 30px" }}
      />
      <div className="relative max-w-4xl mx-auto">
        <div className="text-center">
          <div className="text-[10px] font-extrabold tracking-[0.26em] uppercase text-volt">Join the journey</div>
          <h2 className="font-barlow font-black uppercase text-[28px] md:text-[38px] text-white leading-tight mt-2">
            Be part of the <span className="text-volt">story.</span>
          </h2>
          <p className="text-white/60 text-sm md:text-base mt-2 max-w-md mx-auto">
            Follow players chasing their dream — and get every new story first.
          </p>
        </div>
        <div className="mt-8 grid grid-cols-1 sm:grid-cols-2 gap-4 md:gap-6">
          {insta.url && (
            <FollowCard
              network="instagram" icon={Instagram} url={insta.url} followers={insta.followers || 0}
              accent="#DD2A7B" handle="on Instagram"
              chipStyle={{ background: igGradient }}
              btnStyle={{ background: igGradient }}
            />
          )}
          {face.url && (
            <FollowCard
              network="facebook" icon={Facebook} url={face.url} followers={face.followers || 0}
              accent="#1877F2" handle="on Facebook"
              chipStyle={{ background: "#1877F2" }}
              btnStyle={{ background: "#1877F2" }}
            />
          )}
        </div>
      </div>
    </section>
  );
}
