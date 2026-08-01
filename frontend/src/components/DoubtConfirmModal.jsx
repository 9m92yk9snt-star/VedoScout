// Stage 3 — "doubt moment" control: the tracker flags low-confidence player
// crossovers and the owner taps THEIR player before the AI analysis continues.
import React, { useState } from "react";
import { Crosshair, Loader2, ShieldQuestion } from "lucide-react";
import { ASSET_BASE } from "@/lib/api";

const abs = (u) => (u && u.startsWith("/") ? `${ASSET_BASE}${u}` : u);

export default function DoubtConfirmModal({ moments, onConfirm, onSkip, busy }) {
  const [taps, setTaps] = useState({});
  if (!moments?.length) return null;
  const allTapped = moments.every((_, i) => taps[i]);

  const handleClick = (i, e) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const x = Math.min(Math.max((e.clientX - rect.left) / rect.width, 0), 1);
    const y = Math.min(Math.max((e.clientY - rect.top) / rect.height, 0), 1);
    setTaps((p) => ({ ...p, [i]: { x, y } }));
  };

  return (
    <div
      data-testid="doubt-confirm-modal"
      className="fixed inset-0 z-[90] flex items-center justify-center bg-deepnavy/90 backdrop-blur-sm px-4 py-8 overflow-y-auto"
    >
      <div className="w-full max-w-2xl bg-surface border-2 border-volt/50 p-6 md:p-8 my-auto">
        <div className="flex items-start gap-3">
          <span className="w-10 h-10 shrink-0 rounded-full bg-volt/15 flex items-center justify-center">
            <ShieldQuestion className="w-5 h-5 text-volt" />
          </span>
          <div>
            <h2 className="font-barlow font-black uppercase tracking-[0.14em] text-lg text-ink">
              Quick check — confirm your player
            </h2>
            <p className="text-sm text-ink/65 mt-1 leading-relaxed">
              Our tracker briefly lost certainty at {moments.length === 1 ? "one crossover moment" : `${moments.length} crossover moments`}.
              Tap <span className="text-volt font-bold">your player</span> in each image so the analysis follows the right player.
            </p>
          </div>
        </div>

        <div className="mt-5 space-y-5">
          {moments.map((m, i) => (
            <div key={i} data-testid={`doubt-moment-${i}`}>
              <div className="flex items-center gap-2 mb-2">
                <span className="text-[10px] font-black uppercase tracking-[0.18em] bg-volt text-deepnavy px-2 py-0.5">
                  Moment {i + 1} · {Number(m.t).toFixed(1)}s
                </span>
                <span className="text-[10px] uppercase tracking-[0.12em] text-ink/45 font-bold">{m.reason}</span>
                {taps[i] && (
                  <span className="ml-auto text-[10px] font-black uppercase tracking-[0.14em] text-volt">✓ Marked</span>
                )}
              </div>
              <div
                className="relative w-full cursor-crosshair select-none border border-gray-border"
                onClick={(e) => handleClick(i, e)}
                data-testid={`doubt-frame-${i}`}
              >
                <img src={abs(m.frame_url)} alt={`Moment ${i + 1}`} className="w-full block" draggable={false} />
                {taps[i] && (
                  <span
                    className="absolute w-9 h-9 -translate-x-1/2 -translate-y-1/2 rounded-full border-[3px] border-volt shadow-[0_0_0_3px_rgba(5,10,15,0.55)] pointer-events-none"
                    style={{ left: `${taps[i].x * 100}%`, top: `${taps[i].y * 100}%` }}
                  />
                )}
                {!taps[i] && (
                  <span className="absolute top-2 left-2 inline-flex items-center gap-1.5 bg-deepnavy/80 text-ink text-[10px] font-bold uppercase tracking-[0.12em] px-2 py-1 pointer-events-none">
                    <Crosshair className="w-3 h-3 text-volt" /> Tap your player
                  </span>
                )}
              </div>
            </div>
          ))}
        </div>

        <div className="mt-6 flex flex-col sm:flex-row items-center gap-3">
          <button
            type="button"
            data-testid="doubt-confirm-btn"
            disabled={!allTapped || busy}
            onClick={() => onConfirm(Object.entries(taps).map(([idx, p]) => ({ idx: Number(idx), x: p.x, y: p.y })))}
            className="w-full sm:w-auto flex-1 bg-volt text-deepnavy font-barlow font-black uppercase tracking-[0.16em] text-sm px-6 py-3 disabled:opacity-40 hover:brightness-110 transition-all flex items-center justify-center gap-2"
          >
            {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : null}
            Confirm player & continue
          </button>
          <button
            type="button"
            data-testid="doubt-skip-btn"
            disabled={busy}
            onClick={onSkip}
            className="text-xs uppercase tracking-[0.14em] font-bold text-ink/50 hover:text-ink/80 transition-colors px-3 py-2"
          >
            Skip — let the tracker decide
          </button>
        </div>
        <p className="mt-3 text-[10.5px] text-ink/40 leading-relaxed">
          The analysis continues automatically in a moment even if you skip — the tracker then stops honestly at
          uncertain moments instead of guessing.
        </p>
      </div>
    </div>
  );
}
