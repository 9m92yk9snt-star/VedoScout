import React, { useEffect, useState } from "react";

const BAR_GRADIENT = "linear-gradient(90deg, #2D6B3D 0%, #7ED957 60%, #CCFF00 100%)";

/* Animated skill bars — the premium replacement for the old radar chart.
 * Dark-panel friendly: gradient forest→lime fills with a subtle glow. */
export const SkillBars = ({ scores = [], compact = false }) => {
  const [armed, setArmed] = useState(false);
  useEffect(() => {
    const t = setTimeout(() => setArmed(true), 150);
    return () => clearTimeout(t);
  }, []);
  return (
    <div className="w-full space-y-3" data-testid="skill-bars">
      {scores.map((s, i) => (
        <div key={s.label} className="flex items-center gap-3" data-testid={`skill-bar-${s.label.toLowerCase()}`}>
          <span className={`${compact ? "w-16 text-[10px]" : "w-20 text-[11px]"} uppercase tracking-[0.14em] font-bold text-white/70 shrink-0`}>
            {s.label}
          </span>
          <div className="flex-1 h-2.5 rounded-full bg-white/10 overflow-hidden">
            <div
              className="h-full rounded-full"
              style={{
                width: armed && s.value != null ? `${Math.max(4, (s.value / 10) * 100)}%` : "0%",
                background: BAR_GRADIENT,
                boxShadow: "0 0 12px rgba(204,255,0,0.35)",
                transition: `width 900ms cubic-bezier(.2,.8,.2,1) ${i * 100}ms`,
              }}
            />
          </div>
          <span
            className="w-9 text-right font-barlow font-black text-[15px] shrink-0"
            style={{ color: "#CCFF00" }}
            data-testid={`skill-bar-value-${s.label.toLowerCase()}`}
          >
            {s.value != null ? Number(s.value).toFixed(1) : "—"}
          </span>
        </div>
      ))}
    </div>
  );
};
