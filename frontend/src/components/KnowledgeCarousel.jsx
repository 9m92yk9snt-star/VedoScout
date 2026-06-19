import React, { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";

/**
 * KnowledgeCarousel — soft rotating cards of football "did you know" facts shown
 * while the user waits on upload + analysis. Pure presentation; no API calls.
 */
const FACTS = [
  {
    icon: "🎯",
    headline: "Scouts decide in 3 minutes",
    body: "Top European scouts say the first 3 minutes of footage decides 80% of their evaluation. Clear angles win every time.",
  },
  {
    icon: "🧠",
    headline: "Off-ball is half the game",
    body: "From age 14, professional academies value off-ball movement as much as on-ball moments. Your AI report includes both.",
  },
  {
    icon: "🏃",
    headline: "U12 players change position 4× per match",
    body: "Young players rarely play one role. Our AI tells you the role your child actually plays — based on heatmap evidence, not declarations.",
  },
  {
    icon: "📏",
    headline: "Body shape > body strength",
    body: "First touch + scanning posture are stronger predictors of future success at U13–U15 than raw physical attributes.",
  },
  {
    icon: "⚡",
    headline: "Sprint count beats sprint speed",
    body: "Pro academies care more about how many sprints a player makes in a match than their top speed. Volume builds careers.",
  },
  {
    icon: "🎨",
    headline: "Left foot? You're rarer than you think",
    body: "Only ~22% of pros are left-footed. Two-footed players are even rarer — and far more valuable in any scouting database.",
  },
  {
    icon: "📊",
    headline: "1 in 4,000",
    body: "Roughly 1 in 4,000 grassroots players reaches a senior professional level. The earlier the honest feedback, the better the odds.",
  },
  {
    icon: "🥅",
    headline: "Goals tell you the least",
    body: "Goal counts are deceptive — passing under pressure, recovery runs, and decision speed are what separate elite prospects.",
  },
];

export function KnowledgeCarousel({ paused = false }) {
  const [i, setI] = useState(0);
  useEffect(() => {
    if (paused) return;
    const id = setInterval(() => setI((v) => (v + 1) % FACTS.length), 6000);
    return () => clearInterval(id);
  }, [paused]);
  const fact = FACTS[i];
  return (
    <div className="relative max-w-md mx-auto">
      <AnimatePresence mode="wait">
        <motion.div
          key={i}
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -8 }}
          transition={{ duration: 0.4 }}
          className="text-center px-4"
        >
          <div className="text-3xl mb-2">{fact.icon}</div>
          <h4 className="font-barlow font-black uppercase text-ink tracking-tight text-base mb-2 leading-tight">
            {fact.headline}
          </h4>
          <p className="text-ink/75 text-[12px] leading-relaxed">
            {fact.body}
          </p>
        </motion.div>
      </AnimatePresence>
      <div className="flex items-center justify-center gap-1 mt-4">
        {FACTS.map((_, k) => (
          <span
            key={k}
            className={`h-1 transition-all ${k === i ? "w-6 bg-volt" : "w-1.5 bg-ink/15"}`}
          />
        ))}
      </div>
    </div>
  );
}

export default KnowledgeCarousel;
