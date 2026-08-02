import React, { useRef, useState } from "react";
import {
  Sprout, Play, ShieldCheck, ChevronDown, ListVideo, Heart, Star, CalendarDays,
} from "lucide-react";

/* GROW YOUR GAME — evidence-gated football education.
   Every lesson shown here survived the backend's 100%-evidence gate:
   verified timestamps, minimum-moment thresholds and tracking cross-checks.
   Warm, humble, development-first — for players and the people who support them. */

const CAT_META = {
  on_ball:   { label: "ON THE BALL",  bg: "#E8F3E4", fg: "#1E5B3C" },
  off_ball:  { label: "OFF THE BALL", bg: "#F3EDDC", fg: "#8A6D3B" },
  mentality: { label: "MENTALITY",    bg: "#F6E9E0", fg: "#B4530A" },
};

function LessonBlock({ label, children }) {
  return (
    <div>
      <div className="text-[9.5px] font-extrabold tracking-[0.16em] uppercase text-[#8B957F]">{label}</div>
      <p className="text-[13px] leading-relaxed text-[#3C4A40] mt-1">{children}</p>
    </div>
  );
}

function LessonCard({ lesson, index, playerFirst, onPlayAt, defaultOpen }) {
  const [open, setOpen] = useState(defaultOpen);
  const [explainOpen, setExplainOpen] = useState(false);
  const reelTimer = useRef(null);
  const cat = CAT_META[lesson.category] || CAT_META.on_ball;
  const moments = lesson.moments || [];

  const playAll = () => {
    if (!onPlayAt || !moments.length) return;
    clearTimeout(reelTimer.current);
    let i = 0;
    const step = () => {
      if (i >= moments.length) return;
      onPlayAt(moments[i].timestamp);
      i += 1;
      reelTimer.current = setTimeout(step, 9000);
    };
    step();
  };

  return (
    <div className="bg-white rounded-2xl border border-[#E5DFCE] overflow-hidden shadow-sm" data-testid={`gyg-lesson-${lesson.topic_id}`}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center gap-3 px-4 md:px-5 py-4 text-left hover:bg-[#FAF8F1] transition-colors"
        data-testid={`gyg-lesson-toggle-${lesson.topic_id}`}
      >
        <span className="shrink-0 bg-[#12402A] text-[#CCFF00] font-barlow font-black text-[11px] tracking-wider px-2.5 py-1.5 rounded-lg">
          LESSON {String(index + 1).padStart(2, "0")}
        </span>
        <span className="font-barlow font-black uppercase text-[17px] md:text-[19px] text-[#101B12] leading-tight flex-1 min-w-0">
          {lesson.title}
        </span>
        <span className="hidden sm:inline-flex text-[9px] font-extrabold tracking-[0.1em] px-2 py-1 rounded-md" style={{ background: cat.bg, color: cat.fg }}>
          {cat.label}
        </span>
        <span className="hidden md:inline-flex items-center gap-1.5 text-[9.5px] font-extrabold tracking-[0.06em] uppercase text-[#1E5B3C] bg-[#E8F3E4] px-2 py-1 rounded-md">
          <ShieldCheck className="w-3.5 h-3.5" /> {moments.length} moments verified
        </span>
        <ChevronDown className={`w-5 h-5 text-[#8B957F] shrink-0 transition-transform ${open ? "rotate-180" : ""}`} />
      </button>

      {open && (
        <div className="px-4 md:px-5 pb-5 space-y-4">
          <div className="md:hidden flex items-center gap-2">
            <span className="text-[9px] font-extrabold tracking-[0.1em] px-2 py-1 rounded-md" style={{ background: cat.bg, color: cat.fg }}>{cat.label}</span>
            <span className="inline-flex items-center gap-1 text-[9.5px] font-extrabold uppercase text-[#1E5B3C] bg-[#E8F3E4] px-2 py-1 rounded-md">
              <ShieldCheck className="w-3 h-3" /> {moments.length} verified
            </span>
          </div>

          <div className="grid md:grid-cols-2 gap-4">
            <LessonBlock label="What scouts look for">{lesson.what_scouts_look_for}</LessonBlock>
            <LessonBlock label="Why it matters">{lesson.why_it_matters}</LessonBlock>
          </div>

          <div className="rounded-xl bg-[#F4F8F0] border border-[#DCE8D4] p-4">
            <LessonBlock label={`What happened in ${playerFirst}'s match`}>{lesson.what_happened}</LessonBlock>
          </div>

          {/* AI evidence — the verified moments (Evidence Reel) */}
          <div>
            <div className="flex items-center justify-between gap-2">
              <div className="text-[9.5px] font-extrabold tracking-[0.16em] uppercase text-[#8B957F]">AI evidence — verified moments</div>
              {onPlayAt && moments.length > 1 && (
                <button
                  type="button"
                  onClick={playAll}
                  data-testid={`gyg-play-all-${lesson.topic_id}`}
                  className="inline-flex items-center gap-1.5 text-[10px] font-extrabold uppercase tracking-wide text-white bg-[#1E5B3C] hover:bg-[#12402A] px-2.5 py-1.5 rounded-lg transition-colors"
                >
                  <ListVideo className="w-3.5 h-3.5" /> Play all moments
                </button>
              )}
            </div>
            <div className="mt-2 space-y-1.5">
              {moments.map((m, i) => (
                <div key={i} className="flex items-start gap-2.5">
                  <button
                    type="button"
                    onClick={() => onPlayAt && onPlayAt(m.timestamp)}
                    data-testid={`gyg-play-moment-${lesson.topic_id}-${i}`}
                    className="shrink-0 inline-flex items-center gap-1 bg-[#12402A] text-[#CCFF00] text-[10.5px] font-extrabold px-2 py-1 rounded-md hover:bg-[#1E5B3C] transition-colors"
                  >
                    <Play className="w-3 h-3 fill-current" /> {m.timestamp}
                  </button>
                  <span className="text-[12.5px] leading-snug text-[#3C4A40]">{m.what}</span>
                </div>
              ))}
            </div>
          </div>

          {lesson.age_benchmark && (
            <div className="flex items-start gap-2.5 rounded-xl bg-[#FBF4DF] border border-[#EBD9A6] px-3.5 py-3" data-testid={`gyg-benchmark-${lesson.topic_id}`}>
              <Star className="w-4 h-4 text-[#B8860B] shrink-0 mt-0.5 fill-[#E8B32C]" />
              <p className="text-[12.5px] font-semibold text-[#6B5416] leading-snug">{lesson.age_benchmark}</p>
            </div>
          )}

          <div className="rounded-xl bg-[#12402A] p-4">
            <div className="text-[9.5px] font-extrabold tracking-[0.16em] uppercase text-[#9FC48A]">Personal improvement advice</div>
            <p className="text-[13px] leading-relaxed text-[#EAF2E2] mt-1">{lesson.personal_advice}</p>
          </div>

          {lesson.simple_explanation && (
            <div>
              <button
                type="button"
                onClick={() => setExplainOpen((v) => !v)}
                data-testid={`gyg-simple-explain-${lesson.topic_id}`}
                className="inline-flex items-center gap-2 text-[11px] font-extrabold uppercase tracking-wide text-[#8A6D3B] hover:text-[#6B5416] transition-colors"
              >
                <Heart className="w-3.5 h-3.5" />
                Explain it simply (for parents)
                <ChevronDown className={`w-3.5 h-3.5 transition-transform ${explainOpen ? "rotate-180" : ""}`} />
              </button>
              {explainOpen && (
                <p className="mt-2 text-[12.5px] leading-relaxed text-[#6B5F49] bg-[#F7F3E8] border border-[#E9E0C8] rounded-xl px-3.5 py-3">
                  {lesson.simple_explanation}
                </p>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export function GrowYourGameSection({ gyg, playerName, onPlayAt }) {
  if (!gyg?.lessons?.length) return null;
  const first = (playerName || "your player").split(" ")[0];
  const homework = gyg.homework || [];
  const topicTitle = (id) => (gyg.lessons.find((l) => l.topic_id === id) || {}).title || "";

  return (
    <section data-testid="gyg-section">
      {/* Header banner */}
      <div className="rounded-2xl bg-[#12402A] px-5 md:px-7 py-6 relative overflow-hidden">
        <div className="absolute -right-6 -top-8 opacity-[0.08] pointer-events-none">
          <Sprout className="w-44 h-44 text-[#CCFF00]" />
        </div>
        <div className="flex items-center gap-2.5">
          <span className="w-9 h-9 rounded-xl bg-[#CCFF00] flex items-center justify-center">
            <Sprout className="w-5 h-5 text-[#12402A]" />
          </span>
          <h2 className="font-barlow font-black uppercase tracking-tight text-2xl md:text-3xl text-white leading-none">
            GROW YOUR <span className="text-[#CCFF00]">GAME</span>
          </h2>
        </div>
        <p className="text-[#C9D8C0] text-[13px] md:text-[14px] mt-2 max-w-xl leading-relaxed">
          Real lessons from {first}&rsquo;s own match — for players and the people who support them.
        </p>
        <div className="inline-flex items-center gap-1.5 mt-3 bg-[#1E5B3C] text-[#CCFF00] text-[10px] font-extrabold uppercase tracking-[0.08em] px-2.5 py-1.5 rounded-lg" data-testid="gyg-evidence-note">
          <ShieldCheck className="w-3.5 h-3.5" />
          Only shown when we have verified evidence from this match
        </div>
      </div>

      {/* Lessons */}
      <div className="mt-3 space-y-3">
        {gyg.lessons.map((lesson, i) => (
          <LessonCard
            key={lesson.topic_id}
            lesson={lesson}
            index={i}
            playerFirst={first}
            onPlayAt={onPlayAt}
            defaultOpen={i === 0}
          />
        ))}
      </div>

      {/* This week's homework */}
      {homework.length > 0 && (
        <div className="mt-3 rounded-2xl bg-[#12402A] p-5 md:p-6" data-testid="gyg-homework">
          <div className="flex items-center gap-2.5">
            <span className="w-8 h-8 rounded-lg bg-[#CCFF00] flex items-center justify-center">
              <CalendarDays className="w-4.5 h-4.5 w-[18px] h-[18px] text-[#12402A]" />
            </span>
            <h3 className="font-barlow font-black uppercase text-lg md:text-xl text-white leading-none">
              THIS WEEK&rsquo;S <span className="text-[#CCFF00]">HOMEWORK</span>
            </h3>
          </div>
          <p className="text-[#C9D8C0] text-[12px] mt-1.5">
            15 minutes a day — every drill trains something we actually saw in {first}&rsquo;s match.
          </p>
          <div className="mt-4 space-y-3">
            {homework.map((hw, i) => (
              <div key={i} className="flex flex-col sm:flex-row sm:items-start gap-2 sm:gap-3 bg-[#1E5B3C]/60 rounded-xl px-3.5 py-3">
                <span className="shrink-0 bg-[#CCFF00] text-[#12402A] font-barlow font-black text-[10.5px] tracking-wide px-2 py-1 rounded-md uppercase w-fit">
                  {hw.days}
                </span>
                <div className="min-w-0">
                  <div className="text-[10px] font-extrabold tracking-[0.1em] uppercase text-[#9FC48A]">{topicTitle(hw.topic_id)}</div>
                  <p className="text-[13px] text-white leading-snug mt-0.5">{hw.drill}</p>
                  {hw.why && <p className="text-[11.5px] text-[#C9D8C0] leading-snug mt-1 italic">{hw.why}</p>}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}
