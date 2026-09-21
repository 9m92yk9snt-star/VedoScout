"""score_context.py — deterministic, age-calibrated benchmark context for every
score in a report. Curated scout language — no AI, identical output every time."""

from __future__ import annotations

BRACKETS = [(0, 8, "U6-U8"), (9, 11, "U9-U11"), (12, 14, "U12-U14"), (15, 17, "U15-U17"), (18, 99, "U18-U21")]

BANDS = [
    # (min_score, level)
    (9.0, "Elite"),
    (8.0, "Academy"),
    (7.0, "Top Club"),
    (5.5, "Club"),
    (0.0, "Grassroots"),
]

CAT_LINES = {
    "technical": {
        "high": "Ball mastery that stands out immediately in any session at this age.",
        "mid": "A solid technical base — the tools are there, now comes refinement.",
        "low": "Technique is still settling — completely normal, and the fastest area to improve with reps.",
    },
    "tactical": {
        "high": "Reads the game earlier than the players around him — the rarest quality at this age.",
        "mid": "Understands the game situations he meets — the next step is seeing them earlier.",
        "low": "Game understanding is still forming — it grows naturally with match minutes and questions.",
    },
    "physical": {
        "high": "Physical tools that change games at this age group.",
        "mid": "Physically holds his own — enough to let the football qualities shine.",
        "low": "Physically still growing into the game — patience here always pays off.",
    },
    "mentality": {
        "high": "The mindset coaches trust — brave, persistent and unafraid of mistakes.",
        "mid": "A healthy competitive base — confidence grows with every good session.",
        "low": "Mentality develops with safety and praise — the report's watch-together guide helps exactly here.",
    },
}

SKILL_LINES = {
    "first_touch": {"high": "Kills the ball dead under pressure — the touch that buys time everywhere.", "mid": "Reliable first contact; the next level is taking it into space, not just controlling it.", "low": "Touch still settling — wall work fixes this faster than anything.", "next": "Same clean touch, but while moving at speed and under contact."},
    "ball_control": {"high": "The ball obeys him in tight traffic — a natural carrier.", "mid": "Comfortable on the ball in normal space.", "low": "Control improves every week at this age with daily touches.", "next": "Keeping that control with head up, scanning while carrying."},
    "dribbling": {"high": "The kind of 1v1 confidence coaches build sessions around.", "mid": "Willing to take players on — success rate climbs with body feints.", "low": "Dribbling is a courage skill first — encourage every attempt.", "next": "Beating better defenders, and doing it on the weaker foot too."},
    "passing": {"high": "Passes with intention — weight and timing that create chances.", "mid": "Safe, sensible distribution; the step up is passing forward earlier.", "low": "Passing sharpens quickly with wall drills and small-sided games.", "next": "Breaking lines on purpose, not just keeping possession."},
    "shooting": {"high": "A genuine goal threat — strikes with conviction.", "mid": "Gets shots away; consistency of technique is the multiplier.", "low": "Finishing is repetition — ten shots a day change this fast.", "next": "Same strike quality first-time and from worse angles."},
    "weak_foot": {"high": "Genuinely two-footed — defenders can't show him one way.", "mid": "Uses the weaker side when needed — keep feeding it.", "low": "The single highest-return training hour at this age.", "next": "Choosing the weak foot naturally, not as a last resort."},
    "one_v_one": {"high": "Wins his duels — attacks defenders instead of avoiding them.", "mid": "Competes well 1v1; timing of the touch decides the rest.", "low": "1v1 bravery grows with permission to fail — praise attempts.", "next": "Winning duels against older or faster opponents."},
    "positioning": {"high": "Always seems to be where the game is going next.", "mid": "Positionally sound in familiar situations.", "low": "Positioning is learned by watching — great to train from the sofa.", "next": "Arriving early in dangerous zones, not just correct ones."},
    "off_ball_movement": {"high": "Moves to create space others don't see — scouts love this.", "mid": "Makes honest runs; the next step is timing them off the passer.", "low": "Movement improves fastest with simple 'move after pass' habits.", "next": "Double movements — one run to create the space for the second."},
    "scanning": {"high": "Checks his shoulder before the ball arrives — elite habit for the age.", "mid": "Scans in calm moments; the step is scanning under pressure.", "low": "The most trainable skill on this list — one look before each touch.", "next": "Scanning on the run, not only when standing still."},
    "decision_making": {"high": "Chooses fast and mostly right — plays a move ahead of peers.", "mid": "Sensible decisions when given time.", "low": "Decisions speed up naturally as scanning improves.", "next": "Making the same good choice half a second earlier."},
    "timing_of_runs": {"high": "Times runs off the passer's head-up moment — hard to defend.", "mid": "Runs are honest; syncing with the passer is the unlock.", "low": "Run timing clicks once he watches the passer, not the ball.", "next": "Staying onside at full sprint against a higher line."},
    "game_understanding": {"high": "Understands why, not just what — coaches notice within minutes.", "mid": "Follows the game plan and adapts to obvious cues.", "low": "Grows with every match watched and every question asked.", "next": "Recognising patterns before they happen — the playmaker layer."},
    "acceleration": {"high": "First three steps separate him from the age group.", "mid": "Quick enough to exploit the spaces he finds.", "low": "Acceleration develops with maturity — technique keeps him in games.", "next": "Explosive starts in both directions, not just forward."},
    "speed": {"high": "Top-end pace that stretches defences at this age.", "mid": "Keeps up with the game's tempo comfortably.", "low": "Pace often arrives with growth — never a verdict at this age.", "next": "Using the pace with the ball as well as without it."},
    "balance": {"high": "Rides contact and stays on his feet — rare body control.", "mid": "Stable in duels he expects.", "low": "Balance builds with play — tag games and 1v1s do the work.", "next": "Keeping balance through contact at higher speeds."},
    "agility": {"high": "Changes direction faster than defenders can react.", "mid": "Turns well in space; sharper cuts come with strength.", "low": "Agility grows quickly with footwork games at this age.", "next": "Same sharp turns with the ball under pressure."},
    "intensity": {"high": "Plays every phase at match tempo — sets the session's level.", "mid": "Good engine; consistency across the whole match is next.", "low": "Intensity follows enjoyment — keep it fun, it will come.", "next": "Sustaining that intensity in both boxes for 60+ minutes."},
    "body_control": {"high": "Coordinated beyond his years — movements look effortless.", "mid": "Controls his body well in familiar movements.", "low": "Coordination is age-driven — varied play accelerates it.", "next": "Marrying that control with maximum speed actions."},
    "confidence": {"high": "Wants the ball in every situation — you can't coach that in.", "mid": "Confident in his strengths; new challenges build the rest.", "low": "Confidence is built one praised decision at a time.", "next": "Carrying the same confidence into harder matches."},
    "work_rate": {"high": "Works both ways without being asked — coaches' favourite trait.", "mid": "Honest effort; the next level is sprinting to recover, every time.", "low": "Work rate follows purpose — small missions raise it fast.", "next": "Leading the pressing, not just joining it."},
    "courage_in_duels": {"high": "Goes into every duel like it matters — fearless.", "mid": "Competes when the duel comes to him.", "low": "Duel courage grows with body confidence — never force it.", "next": "Initiating duels against bigger opponents."},
    "response_to_mistakes": {"high": "Resets within seconds of a mistake — elite mental habit.", "mid": "Recovers from errors with a little time.", "low": "The watch-together guide targets exactly this — praise the reset.", "next": "Turning mistakes into immediate winning of the ball back."},
    "competitive_mindset": {"high": "Hates losing every drill — the engine behind development.", "mid": "Competes well when the stakes are visible.", "low": "Competitive edge sharpens with small games and scores.", "next": "Channelling the edge into focus, not frustration."},
    "focus": {"high": "Locked in for the full session — rare at this age.", "mid": "Focused in involved phases; off-ball focus is the step.", "low": "Focus spans grow with age — short, sharp drills help.", "next": "Staying switched on during the boring minutes."},
}

CATS = ["technical", "tactical", "physical", "mentality"]

METHOD_NOTE = ("Levels are calibrated for organised youth football at this age group: "
               "Grassroots · Club · Top Club · Academy · Elite. A level describes this skill "
               "TODAY — it is a snapshot, not a ceiling.")


def _bracket(age) -> str:
    try:
        a = int(age)
    except (TypeError, ValueError):
        return "U12-U14"
    for lo, hi, label in BRACKETS:
        if lo <= a <= hi:
            return label
    return "U18-U21"


def _level(score: float) -> str:
    for mn, level in BANDS:
        if score >= mn:
            return level
    return "Grassroots"


def _tier(score: float) -> str:
    return "high" if score >= 7.5 else ("mid" if score >= 6.0 else "low")


def _ctx(score: float, line: str, next_step: str | None = None) -> dict:
    return {
        "score": round(score, 1),
        "level": _level(score),
        "line": line,
        "next_step": next_step if (next_step and score >= 7.5) else None,
    }


OVERALL_LINES = {
    "Elite": "A profile that would stand out even in an elite academy session for this age group.",
    "Academy": "Taken as a whole, this is the level academy players typically show at this age.",
    "Top Club": "The overall picture of a player who stands out at good club level.",
    "Club": "A solid club-level foundation for the age group — with clear room to climb.",
    "Grassroots": "Early on the football journey — exactly where the biggest jumps happen.",
}


def build_score_context(full: dict, age) -> dict | None:
    scores = (full or {}).get("scores") or {}
    ov = scores.get("overall_development")
    if not isinstance(ov, (int, float)):
        return None
    bracket = _bracket(age)
    categories = {}
    for cat in CATS:
        v = scores.get(cat)
        if isinstance(v, (int, float)):
            categories[cat] = _ctx(float(v), CAT_LINES[cat][_tier(float(v))])
    skills = {}
    for cat in CATS:
        sec = (full or {}).get(cat) or {}
        if not isinstance(sec, dict):
            continue
        for k, sk in sec.items():
            if not isinstance(sk, dict) or sk.get("cannot_evaluate"):
                continue
            s = sk.get("score")
            lines = SKILL_LINES.get(k)
            if isinstance(s, (int, float)) and lines:
                skills[k] = _ctx(float(s), lines[_tier(float(s))], lines.get("next"))
                skills[k]["category"] = cat
    return {
        "bracket": bracket,
        "overall": _ctx(float(ov), OVERALL_LINES[_level(float(ov))]),
        "categories": categories,
        "skills": skills,
        "method_note": METHOD_NOTE,
    }
