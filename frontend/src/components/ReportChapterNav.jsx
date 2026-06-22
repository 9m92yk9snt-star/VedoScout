import React, { useEffect, useState, useRef } from "react";
import { PitchLineDivider } from "./FootballAccents";

/**
 * ReportChapterNav — sticky table-of-contents bar that scrolls with the user
 * down a premium report. Highlights the currently-visible chapter and lets
 * the user jump to any section with one tap.
 *
 *  Implementation:
 *    • IntersectionObserver tracks which `<section id="…">` is currently in the
 *      top third of the viewport — that's the "active" chapter.
 *    • Clicking a chip uses `scrollIntoView({block:"start", behavior:"smooth"})`
 *      on the matching section; `scroll-mt-XX` on each anchor target makes sure
 *      the heading doesn't hide behind this sticky nav itself.
 *    • Renders horizontally scrollable on mobile (`overflow-x-auto`).
 *
 *  Props:
 *    chapters — [{ id: "report-…",  num: "01",  label: "Summary" }, …]
 */
export default function ReportChapterNav({ chapters }) {
  const [activeId, setActiveId] = useState(chapters?.[0]?.id || null);
  const observerRef = useRef(null);

  useEffect(() => {
    if (!chapters || chapters.length === 0) return;
    const sections = chapters
      .map((c) => document.getElementById(c.id))
      .filter(Boolean);
    if (sections.length === 0) return;

    // Trigger when a section's TOP enters the upper 35 % of the viewport — this
    // matches the "user is reading this chapter now" intuition better than the
    // raw boolean isIntersecting (which fires on bottom too).
    observerRef.current = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((e) => e.isIntersecting)
          .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);
        if (visible[0]) setActiveId(visible[0].target.id);
      },
      { rootMargin: "-15% 0px -65% 0px", threshold: 0 }
    );
    sections.forEach((s) => observerRef.current.observe(s));
    return () => observerRef.current?.disconnect();
  }, [chapters]);

  const handleClick = (id) => {
    const el = document.getElementById(id);
    if (!el) return;
    el.scrollIntoView({ behavior: "smooth", block: "start" });
    setActiveId(id);
  };

  if (!chapters || chapters.length === 0) return null;

  return (
    <div
      className="sticky top-0 z-30 bg-cream-base/90 backdrop-blur-md border-b border-forest/15"
      data-testid="report-chapter-nav"
    >
      <div className="max-w-screen-xl mx-auto px-3 md:px-6 py-2.5">
        <div className="flex items-center gap-2 md:gap-3 overflow-x-auto scrollbar-none">
          <div className="hidden md:flex items-center gap-2 text-forest/65 flex-shrink-0">
            <PitchLineDivider className="w-8 h-1.5 text-forest/45" />
            <span className="text-[10px] uppercase tracking-[0.25em] font-black text-forest">Report</span>
          </div>
          <div className="flex items-center gap-1.5 md:gap-2 flex-1">
            {chapters.map((c) => {
              const isActive = activeId === c.id;
              return (
                <button
                  type="button"
                  key={c.id}
                  onClick={() => handleClick(c.id)}
                  data-testid={`chapter-nav-${c.num}`}
                  className={
                    "relative flex-shrink-0 inline-flex items-center gap-1.5 px-2.5 md:px-3 py-1.5 rounded-sm border transition-all whitespace-nowrap " +
                    (isActive
                      ? "bg-forest text-cream-card border-forest shadow-[0_0_12px_rgba(31,79,47,0.35)]"
                      : "bg-cream-card/70 text-ink/65 border-forest/15 hover:border-forest/35 hover:text-forest")
                  }
                >
                  <span className={
                    "text-[10px] font-barlow font-black tabular-nums " +
                    (isActive ? "text-cream-card" : "text-forest/65")
                  }>
                    {c.num}
                  </span>
                  <span className="text-[10.5px] uppercase tracking-[0.18em] font-bold">
                    {c.label}
                  </span>
                </button>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
