import React, { useEffect, useMemo, useState } from "react";
import { ArrowLeft, ArrowRight, Lightbulb, Pause, Play } from "lucide-react";
import { tipDeck } from "../lib/footballTips.mjs";

function Pitch({ visual }) {
  const paths = { scan: "M45 68 Q55 20 108 34", touch: "M45 68 L82 45 L115 22", pass: "M35 70 L115 30 L70 20",
    shot: "M38 70 L80 48 L139 23", defend: "M110 25 Q78 35 72 75", dribble: "M40 75 Q90 70 60 50 T110 20",
    recover: "M112 25 Q45 24 45 75", run: "M35 75 Q30 22 115 30" };
  return <svg viewBox="0 0 160 100" fill="none" className="analysis-tip-pitch" aria-hidden="true">
    <rect x="5" y="5" width="150" height="90" rx="5" stroke="currentColor" opacity=".35" />
    <path d="M80 5v90M5 27h22v46H5M155 27h-22v46h22" stroke="currentColor" opacity=".28" />
    <circle cx="80" cy="50" r="17" stroke="currentColor" opacity=".28" />
    <path className="analysis-tip-route" d={paths[visual]} stroke="var(--tip-accent)" strokeWidth="3" strokeDasharray="5 5" />
    <circle cx="40" cy="73" r="7" fill="var(--tip-accent)" />
    <circle cx="112" cy="28" r="7" fill="#fff" fillOpacity=".13" stroke="white" strokeWidth="2" />
    <circle cx="65" cy="30" r="4" fill="white" opacity=".45" />
    {visual === "scan" && <path d="M32 48a25 25 0 0 1 38 4M25 38a38 38 0 0 1 56 5" stroke="var(--tip-accent)" opacity=".7" />}
    {visual === "defend" && <path d="M58 30v36m-7-7 7 7 7-7" stroke="var(--tip-accent)" strokeWidth="3" />}
  </svg>;
}

export default function FootballTips({ sessionKey = "upload" }) {
  const deck = useMemo(() => tipDeck(sessionKey), [sessionKey]);
  const [index, setIndex] = useState(0);
  const [paused, setPaused] = useState(() => window.matchMedia?.("(prefers-reduced-motion: reduce)").matches || false);
  useEffect(() => { setIndex(0); }, [sessionKey]);
  useEffect(() => {
    if (paused) return undefined;
    const timer = setInterval(() => { if (!document.hidden) setIndex(value => (value + 1) % deck.length); }, 5000);
    return () => clearInterval(timer);
  }, [paused, deck, index]);
  const tip = deck[index % deck.length];
  return <section className="analysis-tips" data-visual={tip.visual} data-paused={paused} aria-label="Football tips" data-testid="analysis-football-tips">
    <div className="analysis-tip-top"><span><Lightbulb size={15} /> Touchline tips <b>· {tip.category}</b></span><span>{String(index + 1).padStart(2, "0")} / 10</span></div>
    <div className="analysis-tip-scene" key={tip.id}>
      <Pitch visual={tip.visual} />
      <div className="analysis-tip-content"><h2>{tip.title}</h2><p>{tip.text}</p></div>
    </div>
    <div className="analysis-tip-footer"><span>General advice · not report findings</span><div className="analysis-tip-controls">
      <button type="button" aria-label="Previous football tip" onClick={() => setIndex(value => (value + 9) % 10)}><ArrowLeft size={17} /></button>
      <button type="button" aria-label={paused ? "Play football tips" : "Pause football tips"} aria-pressed={paused} onClick={() => setPaused(value => !value)}>{paused ? <Play size={15} /> : <Pause size={15} />}</button>
      <button type="button" aria-label="Next football tip" onClick={() => setIndex(value => (value + 1) % 10)}><ArrowRight size={17} /></button>
    </div></div>
    <div key={`${tip.id}-${paused}`} className="analysis-tip-timer" aria-hidden="true"><span /></div>
  </section>;
}
