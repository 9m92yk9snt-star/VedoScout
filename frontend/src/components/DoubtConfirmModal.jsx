// Stage 3 — "doubt moment" control: the tracker flags low-confidence player
// crossovers and the owner taps THEIR player before the AI analysis continues.
// A moment where the player is not visible can be skipped individually —
// nobody is ever forced to tap blindly (a wrong tap is worse than no tap).
import React, { useState } from "react";
import { Crosshair, EyeOff, Loader2, ShieldQuestion, Undo2 } from "lucide-react";
import { ASSET_BASE } from "@/lib/api";

const abs = (u) => (u && u.startsWith("/") ? `${ASSET_BASE}${u}` : u);

export default function DoubtConfirmModal({ moments, onConfirm, onSkip, busy }) {
  const [taps, setTaps] = useState({});
  const [skips, setSkips] = useState({});
  if (!moments?.length) return null;
  const allAnswered = moments.every((_, i) => taps[i] || skips[i]);
  const tapCount = Object.keys(taps).length;

  const handleClick = (i, e) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const x = Math.min(Math.max((e.clientX - rect.left) / rect.width, 0), 1);
    const y = Math.min(Math.max((e.clientY - rect.top) / rect.height, 0), 1);
    setTaps((p) => ({ ...p, [i]: { x, y } }));
    setSkips((p) => {
      const n = { ...p };
      delete n[i];
      return n;
    });
  };

  const toggleSkip = (i) => {
    setSkips((p) => {
      const n = { ...p };
      if (n[i]) delete n[i];
      else n[i] = true;
      return n;
    });
    setTaps((p) => {
      const n = { ...p };
      delete n[i];
      return n;
    });
  };

  const submit = () => {
    if (tapCount === 0) {
      onSkip();
      return;
    }
    onConfirm(Object.entries(taps).map(([idx, p]) => ({ idx: Number(idx), x: p.x, y: p.y })));
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
              Tap <span className="text-volt font-bold">your player</span> in each image — and if you can&rsquo;t
              see your player in an image, skip that moment instead. Never guess.
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
                {skips[i] && (
                  <span className="ml-auto text-[10px] font-black uppercase tracking-[0.14em] text-ink/50">Skipped</span>
                )}
              </div>
              <div
                className={`relative w-full select-none border border-gray-border ${skips[i] ? "opacity-40" : "cursor-crosshair"}`}
                onClick={(e) => !skips[i] && handleClick(i, e)}
                data-testid={`doubt-frame-${i}`}
              >
                <img src={abs(m.frame_url)} alt={`Moment ${i + 1}`} className="w-full block" draggable={false} />
                {taps[i] && (
                  <span
                    className="absolute w-9 h-9 -translate-x-1/2 -translate-y-1/2 rounded-full border-[3px] border-volt shadow-[0_0_0_3px_rgba(5,10,15,0.55)] pointer-events-none"
                    style={{ left: `${taps[i].x * 100}%`, top: `${taps[i].y * 100}%` }}
                  />
                )}
                {!taps[i] && !skips[i] && (
                  <span className="absolute top-2 left-2 inline-flex items-center gap-1.5 bg-deepnavy/80 text-ink text-[10px] font-bold uppercase tracking-[0.12em] px-2 py-1 pointer-events-none">
                    <Crosshair className="w-3 h-3 text-volt" /> Tap your player
                  </span>
                )}
              </div>
              <button
                type="button"
                data-testid={`doubt-skip-moment-${i}`}
                onClick={() => toggleSkip(i)}
                className="mt-1.5 inline-flex items-center gap-1.5 text-[10.5px] uppercase tracking-[0.1em] font-bold text-ink/50 hover:text-ink/80 transition-colors"
              >
                {skips[i] ? (
                  <>
                    <Undo2 className="w-3 h-3" /> Undo — I can see my player after all
                  </>
                ) : (
                  <>
                    <EyeOff className="w-3 h-3" /> Can&rsquo;t see my player here — skip this moment
                  </>
                )}
              </button>
            </div>
          ))}
        </div>

        <div className="mt-6 flex flex-col sm:flex-row items-center gap-3">
          <button
            type="button"
            data-testid="doubt-confirm-btn"
            disabled={!allAnswered || busy}
            onClick={submit}
            className="w-full sm:w-auto flex-1 bg-volt text-deepnavy font-barlow font-black uppercase tracking-[0.16em] text-sm px-6 py-3 disabled:opacity-40 hover:brightness-110 transition-all flex items-center justify-center gap-2"
          >
            {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : null}
            {tapCount > 0 ? "Confirm player & continue" : "Continue without tapping"}
          </button>
          <button
            type="button"
            data-testid="doubt-skip-btn"
            disabled={busy}
            onClick={onSkip}
            className="text-xs uppercase tracking-[0.14em] font-bold text-ink/50 hover:text-ink/80 transition-colors px-3 py-2"
          >
            Skip all — let the tracker decide
          </button>
        </div>
        <p className="mt-3 text-[10.5px] text-ink/40 leading-relaxed">
          Skipping is always safe — the tracker then stops honestly at uncertain moments instead of guessing.
          A wrong tap is the only thing that can mislead the analysis, so only tap when you are sure.
        </p>
      </div>
    </div>
  );
}
