import React, { useState } from "react";
import {
  Heart, Ruler, Sprout, Megaphone, Brain, ChevronDown, Moon, Apple, Bone, Scale, Info,
} from "lucide-react";
import { PARENT_GUIDE, bracketForAge, GROWTH_HIGHLIGHT_AGES } from "./parentGuideLibrary";

/* FOR YOU ON THE SIDELINE — the parent corner.
   Layer 1: AI-written, personalized from THIS report (validated server-side).
   Layer 2: curated age-bracket guidance (fixed content, never AI-generated). */

const AMBER = "#8A6D3B";

const PC_CARDS = [
  { key: "size_and_potential", icon: Ruler, title: "Can scouts see past size?" },
  { key: "development_takes_time", icon: Sprout, title: "Development takes time" },
  { key: "your_role_on_the_sideline", icon: Megaphone, title: "Your role on the sideline" },
  { key: "how_to_support_mentally", icon: Brain, title: "How to support mentally" },
];

const TOPIC_ICONS = { moon: Moon, apple: Apple, bone: Bone, scale: Scale, heart: Heart };

function GuideTopic({ topic, highlighted }) {
  const [open, setOpen] = useState(highlighted);
  const Icon = TOPIC_ICONS[topic.icon] || Heart;
  return (
    <div className={`rounded-xl border overflow-hidden ${highlighted ? "border-[#D9B85C] bg-[#FDF8EA]" : "border-[#E9E0C8] bg-white"}`} data-testid={`pc-guide-${topic.id}`}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center gap-3 px-4 py-3.5 text-left hover:bg-[#FAF5E8] transition-colors"
        data-testid={`pc-guide-toggle-${topic.id}`}
      >
        <span className="w-8 h-8 rounded-lg bg-[#F3EAD3] flex items-center justify-center shrink-0">
          <Icon className="w-4 h-4 text-[#8A6D3B]" />
        </span>
        <span className="font-barlow font-black uppercase text-[15px] text-[#3E3115] flex-1">{topic.title}</span>
        {highlighted && (
          <span className="hidden sm:inline text-[9px] font-extrabold uppercase tracking-[0.08em] text-[#8A6D3B] bg-[#F3E3B3] px-2 py-1 rounded-md">
            Likely relevant right now
          </span>
        )}
        <ChevronDown className={`w-4.5 h-4.5 w-[18px] h-[18px] text-[#B8A87E] transition-transform ${open ? "rotate-180" : ""}`} />
      </button>
      {open && (
        <div className="px-4 pb-4">
          <p className="text-[13px] leading-relaxed text-[#57492A]">{topic.body}</p>
          <ul className="mt-2.5 space-y-1.5">
            {topic.tips.map((t, i) => (
              <li key={i} className="flex items-start gap-2 text-[12.5px] text-[#57492A]">
                <span className="mt-[7px] w-1.5 h-1.5 rounded-full bg-[#C9A84C] shrink-0" />
                {t}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

export function ParentCornerSection({ parentCorner, playerName, playerAge }) {
  const cards = PC_CARDS.filter((c) => parentCorner?.[c.key]);
  const bracket = bracketForAge(playerAge);
  const topics = PARENT_GUIDE[bracket] || [];
  const highlightGrowth = GROWTH_HIGHLIGHT_AGES.includes(Number(playerAge));
  if (!cards.length && !topics.length) return null;
  const first = (playerName || "your player").split(" ")[0];

  return (
    <section data-testid="parent-corner-section">
      {/* Warm header — deliberately different from the green performance sections */}
      <div className="rounded-2xl bg-[#5C4A22] px-5 md:px-7 py-6 relative overflow-hidden">
        <div className="absolute -right-8 -top-6 opacity-[0.09] pointer-events-none">
          <Heart className="w-40 h-40 text-[#F3E3B3]" />
        </div>
        <div className="flex items-center gap-2.5">
          <span className="w-9 h-9 rounded-xl bg-[#F3E3B3] flex items-center justify-center">
            <Heart className="w-5 h-5 text-[#5C4A22]" />
          </span>
          <h2 className="font-barlow font-black uppercase tracking-tight text-2xl md:text-3xl text-white leading-none">
            FOR YOU ON THE <span className="text-[#F3E3B3]">SIDELINE</span>
          </h2>
        </div>
        <p className="text-[#E5D9BC] text-[13px] md:text-[14px] mt-2 max-w-xl leading-relaxed">
          Written for parents — not part of {first}&rsquo;s analysis. How to support the player behind the report.
        </p>
      </div>

      {/* Layer 1 — personalized from this match */}
      {cards.length > 0 && (
        <div className="mt-3 grid md:grid-cols-2 gap-3">
          {cards.map(({ key, icon: Icon, title }) => (
            <div key={key} className="bg-white rounded-2xl border border-[#E9E0C8] p-5" data-testid={`pc-card-${key}`}>
              <div className="flex items-center gap-2.5">
                <span className="w-8 h-8 rounded-lg bg-[#F3EAD3] flex items-center justify-center shrink-0">
                  <Icon className="w-4 h-4 text-[#8A6D3B]" />
                </span>
                <h3 className="font-barlow font-black uppercase text-[15px] md:text-base text-[#3E3115] leading-tight">{title}</h3>
              </div>
              <p className="mt-3 text-[13px] leading-relaxed text-[#57492A]">{parentCorner[key]}</p>
              <div className="mt-3 inline-flex items-center gap-1.5 text-[9px] font-extrabold uppercase tracking-[0.08em] text-[#8A6D3B] bg-[#F7F1E3] px-2 py-1 rounded-md">
                <Sprout className="w-3 h-3" /> Based on this match
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Layer 2 — curated age-bracket guidance */}
      {topics.length > 0 && (
        <div className="mt-3 rounded-2xl bg-[#FBF7EC] border border-[#E9E0C8] p-5" data-testid="pc-age-guide">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="font-barlow font-black uppercase text-lg text-[#3E3115]">
              FOR YOUR AGE GROUP <span className="text-[#8A6D3B]">({bracket})</span>
            </h3>
          </div>
          <p className="text-[12px] text-[#8A7A55] mt-1">
            Curated guidance for players this age — sleep, fuel, growth and wellbeing.
          </p>
          <div className="mt-4 space-y-2.5">
            {topics.map((t) => (
              <GuideTopic key={t.id} topic={t} highlighted={t.id === "growth" && highlightGrowth} />
            ))}
          </div>
          <div className="mt-4 flex items-start gap-2 text-[11px] text-[#8A7A55]" data-testid="pc-disclaimer">
            <Info className="w-3.5 h-3.5 shrink-0 mt-0.5" />
            General guidance based on established knowledge about youth development — not medical advice. See a doctor or physiotherapist for persistent pain or concerns.
          </div>
        </div>
      )}
    </section>
  );
}
