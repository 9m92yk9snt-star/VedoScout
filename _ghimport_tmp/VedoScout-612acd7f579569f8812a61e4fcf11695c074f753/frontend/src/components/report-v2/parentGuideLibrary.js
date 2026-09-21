/* Curated, age-calibrated parent guidance library.
   IMPORTANT: This content is FIXED and reviewed — never AI-generated at runtime.
   The player's age only selects the bracket. General guidance, not medical advice. */

export const bracketForAge = (age) => {
  const a = Number(age) || 0;
  if (a <= 10) return "U8-U10";
  if (a <= 13) return "U11-U13";
  return "U14-U16";
};

export const GROWTH_HIGHLIGHT_AGES = [12, 13, 14, 15];

export const PARENT_GUIDE = {
  "U8-U10": [
    {
      id: "sleep",
      icon: "moon",
      title: "Sleep",
      body: "Children aged 6-12 need 9-12 hours of sleep. Sleep is when the brain stores new motor skills — the touches practised today are literally 'saved' overnight. A calm, consistent bedtime routine does more for development than an extra evening drill.",
      tips: [
        "Aim for the same bedtime every night — also on weekends",
        "Screens off 30-60 minutes before bed",
        "An early night before match day is free training",
      ],
    },
    {
      id: "food",
      icon: "apple",
      title: "Food & Hydration",
      body: "At this age food is fuel for growth AND play — never restriction. A normal, varied family diet covers almost everything. The most common issue is simply forgetting to drink water during matches.",
      tips: [
        "A small carb-rich meal 2-3 hours before matches (pasta, rice, bread)",
        "Water bottle at every training — small sips at every break",
        "A snack within an hour after playing (fruit, yoghurt, a sandwich)",
        "Never diets or weight talk at this age",
      ],
    },
    {
      id: "growth",
      icon: "bone",
      title: "Growing Pains & Injury Prevention",
      body: "Heel pain (Sever's disease) is very common between 8 and 12 — it is growth-related, not a real injury, but it is a signal to reduce load for a while. Variety protects: climbing, swimming, other games all build the same athletic base.",
      tips: [
        "Pain that changes how they run or walk = rest and fewer sessions",
        "Encourage several sports and free play — specialising this early adds risk, not advantage",
        "Well-fitting boots matter more than expensive boots",
      ],
    },
    {
      id: "developers",
      icon: "scale",
      title: "Early & Late Developers",
      body: "At this age the biggest player on the pitch is often just the oldest — children born in January can be nearly a year ahead of December-born teammates (the 'relative age effect'). Coaches and scouts know this. Skill, courage and game understanding are the real signals, and they are exactly what this report measures.",
      tips: [
        "Compare your child to their own last month — never to the biggest kid on the team",
        "Results and trophies at this age predict almost nothing",
      ],
    },
    {
      id: "mental",
      icon: "heart",
      title: "Mental Wellbeing",
      body: "At this age football should feel like play. The strongest predictor of a child staying in sport is simple: it stays fun, and love from home never depends on performance. Watch for signs the fun is fading — reluctance before training, stomach aches on match days.",
      tips: [
        "The best sentence after any match: 'I love watching you play'",
        "Let the coach coach — from the sideline, only encourage",
        "If they want to talk about the match, they will — often hours later",
      ],
    },
  ],
  "U11-U13": [
    {
      id: "sleep",
      icon: "moon",
      title: "Sleep",
      body: "Ages 11-13 need 9-11 hours. This is when training load typically increases — and sleep is where motor learning (first touch, coordination) is consolidated and growth hormone is released. A tired player learns almost nothing from a good session.",
      tips: [
        "9+ hours on nights before training and matches",
        "Screens out of the bedroom — blue light delays sleep onset",
        "If mornings are a struggle every day, total load may be too high",
      ],
    },
    {
      id: "food",
      icon: "apple",
      title: "Food & Hydration",
      body: "Growth plus football is a huge energy demand — appetite swings are normal and healthy. Under-eating is a far bigger risk than over-eating in active kids this age. Keep it simple: regular meals, real food, water.",
      tips: [
        "Carb-rich meal 2-3 hours before a match; a banana or bread 30-60 min before is fine",
        "Recovery within an hour after: carbs + a little protein (chocolate milk works)",
        "Never diets, calorie talk or weight focus — growth needs fuel",
      ],
    },
    {
      id: "growth",
      icon: "bone",
      title: "Growth Spurt & Injury Prevention",
      body: "Knee pain below the kneecap (Osgood-Schlatter) is common from 10-15 and is growth-related. Just as important: during a growth spurt, arms and legs grow faster than the brain can recalibrate — coordination, touch and speed can temporarily DIP for 6-12 months. Nothing is wrong. It comes back better.",
      tips: [
        "A performance dip during rapid growth is normal — say it out loud to your child, it removes enormous pressure",
        "Pain that persists or changes their movement = reduce load, see a physio if it lasts",
        "Keep one or two full rest days every week",
      ],
    },
    {
      id: "developers",
      icon: "scale",
      title: "Early & Late Developers",
      body: "This is where physical differences peak — some 12-year-olds look 15, others look 10. Academies increasingly use 'bio-banding' (grouping by biological rather than calendar age) precisely because size now says little about the player at 18. Late developers are often forced to out-think opponents — a long-term advantage.",
      tips: [
        "If your child is smaller: skills learned against bigger opponents transfer brilliantly later",
        "If your child is bigger: make sure they develop technique, not just dominance",
        "Selection setbacks now are about bodies, not futures",
      ],
    },
    {
      id: "mental",
      icon: "heart",
      title: "Mental Wellbeing",
      body: "Ages 11-13 is when kids start comparing themselves seriously — teammates, selections, social media. Your job is to be the one place where their worth never depends on football. Watch for perfectionism: fear of mistakes kills development faster than any technical flaw.",
      tips: [
        "Praise the actions this report highlights (effort, reactions, bravery) — not goals",
        "After a bad match: food, silence, patience. Talk when they open the door",
        "Keep at least one interest alive outside football",
      ],
    },
  ],
  "U14-U16": [
    {
      id: "sleep",
      icon: "moon",
      title: "Sleep",
      body: "Teenagers need 8-10 hours, but their body clock genuinely shifts later — melatonin releases later, so 'can't fall asleep at 21:30' is biology, not attitude. The fix is a consistent wake time and daylight in the morning, not earlier lights-out fights.",
      tips: [
        "Consistent wake-up time (also weekends, within an hour) beats early bedtimes",
        "Phone out of the bedroom is the single biggest sleep win for teens",
        "Napping 20-30 min after school is fine; 2 hours ruins the night",
      ],
    },
    {
      id: "food",
      icon: "apple",
      title: "Food & Hydration",
      body: "Peak growth years can demand 3000+ kcal on training days. Under-fuelling is the hidden performance killer at this age — it shows up as fatigue, repeated small injuries and stalled progress (RED-S). Watch that food stays a friend, not a control tool.",
      tips: [
        "Three meals plus real snacks on training days — hunger is data, not weakness",
        "Protein spread across the day supports the muscle they are finally able to build",
        "Any signs of restrictive eating or guilt around food: take it seriously early",
      ],
    },
    {
      id: "growth",
      icon: "bone",
      title: "Growth, Strength & Injury Prevention",
      body: "Around peak height velocity, muscle-tendon injuries (hamstring, groin, knee) become the main risk. This is the right age to add basic strength work — bodyweight first, quality over load. Structured rest is now a performance tool, not a punishment.",
      tips: [
        "Basic strength 2x/week (squats, lunges, core, nordics) cuts injury risk dramatically",
        "Sudden load spikes (extra teams, tournaments, trials in the same month) cause most injuries",
        "Niggles that last 2+ weeks deserve a physio, not silence",
      ],
    },
    {
      id: "developers",
      icon: "scale",
      title: "Early & Late Developers",
      body: "This is where late developers start catching up — and where early developers who relied on physique get exposed. Scouts at this level actively look 'through' the body to decision-making, scanning and speed of thought: exactly the qualities this report isolates. The pathway is longer than any single season.",
      tips: [
        "De-selection at 14-16 is a detour, not a verdict — many pros were released at this age",
        "Ask clubs WHAT development they see, not just whether he/she 'made it'",
      ],
    },
    {
      id: "mental",
      icon: "heart",
      title: "Mental Wellbeing",
      body: "Football is now tangled with identity, friendships and social media comparison. The teens who thrive have an identity bigger than the sport. Pressure signs to watch: sleep changes, irritability around match days, or the phrase 'I have to' replacing 'I want to'.",
      tips: [
        "Keep school, friendships and one non-football interest protected",
        "Their sporting dreams must be THEIRS — your role is the safety net, not the engine",
        "If joy disappears for months, a break is medicine, not failure",
      ],
    },
  ],
};
