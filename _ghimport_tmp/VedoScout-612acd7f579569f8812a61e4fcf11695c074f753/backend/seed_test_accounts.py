"""
Seed test accounts for the Elite Scout platform.
Creates:
  1. A free (preview-only) user
  2. A premium user with a fully unlocked sample report ready to view
Admin is already auto-seeded on backend startup.

Run from inside /app/backend:  python seed_test_accounts.py
"""
import asyncio
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

import bcrypt
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]

FREE_EMAIL = "free@elitescout.com"
FREE_PASSWORD = "Free@2026"
FREE_NAME = "Free Demo User"

PREMIUM_EMAIL = "premium@elitescout.com"
PREMIUM_PASSWORD = "Premium@2026"
PREMIUM_NAME = "Premium Demo User"


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()


# Pre-built sample preview (free)
PREVIEW = {
    "player_type": "Smart playmaker · strong left foot",
    "brief_summary": "Lukas is a smart playmaker who sees the game two steps ahead of others his age. He stays calm when defenders close him down and loves to play forward passes that cut the defence in half. His left foot is his weapon — he can find a teammate from almost anywhere on the pitch.",
    "top_strengths": [
        "Always looks around before the ball arrives",
        "Strong left foot — passes that open up defences",
        "Stays calm even when two players close him down",
    ],
    "area_for_improvement": "Gets tired late in matches. Needs more fitness work so he can keep pressing and running in the last 20 minutes.",
    "sample_section": {
        "title": "Sample: Technical Snapshot",
        "content": "Lukas has a clean first touch that almost always sets him up to play forward. His passing range with the left foot stands out for his age — he can hit short combinations and switch the play to the opposite wing equally well. The full premium report goes much deeper across every skill.",
    },
}

_BENCH_U13_14 = {
    "elite_academy": "8.5-10",
    "pro_academy":   "7-8.5",
    "strong_club":   "5.5-7",
    "standard_club": "4-5.5",
}

def _skill(score, notes, tier, why, verdict, *, cannot_eval=False):
    """Build an evidence-shaped sub-skill object aligned with the new AI prompt."""
    if cannot_eval:
        return {
            "score": None, "notes": notes, "confidence": "low",
            "confidence_reason": "Not visible in this clip", "observations_used": 0,
            "evidence": [], "cannot_evaluate": True, "evaluable_reason": notes,
        }
    return {
        "score": score, "notes": notes, "confidence": "high",
        "confidence_reason": "Multiple clear moments observed", "observations_used": 8,
        "evidence": [], "cannot_evaluate": False,
        "why_this_score": why,
        "tier_for_age": tier,
        "benchmarks": _BENCH_U13_14,
        "verdict": verdict,
    }


# Pre-built full premium report
FULL_REPORT = {
    "player_type": "Smart playmaker · strong left foot",
    "executive_summary": "Lukas is a smart, calm playmaker with a left foot that opens up defences. He reads the game very well for his age and is brave on the ball under pressure. He plays simple when needed and risky when it pays off. The biggest area to grow is his fitness — he fades in the second half. Build the legs and the rest is already at a high level.",
    "technical": {
        "first_touch": _skill(8, "Clean first touch that sets him up to play forward almost every time. Rare to see him let the ball bounce away.", "pro_academy", "Scored 8 because his first touch consistently breaks pressure and sets up his next action — only loses control once or twice across the clip.", "Currently sitting at pro academy for a 14-year-old attacking midfielder. To reach elite, work on first touch when facing two defenders at once."),
        "ball_control": _skill(8, "Keeps the ball close in tight space. Comfortable on both surfaces of his left foot.", "pro_academy", "Scored 8 because he protects the ball through small spaces with consistent close control, only the weakest hand is his right foot.", "Currently at pro academy. To reach elite, add right-foot variations under pressure."),
        "dribbling": _skill(7, "Beats defenders with a feint and change of direction rather than pure pace. Effective in 1v1s.", "pro_academy", "Scored 7 because he wins 1v1s through deception rather than explosiveness — limited variety against quicker defenders.", "Currently at pro academy. To reach elite, add an explosive burst after the feint."),
        "passing": _skill(9, "His standout skill. Vision to find passes others miss, and the technique to deliver them.", "elite_academy", "Scored 9 because he picks line-breaking passes that other 14-year-olds simply don't see, and his weight is consistently right.", "Currently sitting at elite academy. To stay here, keep developing risk/reward judgement."),
        "shooting": _skill(7, "Strikes the ball cleanly with his left foot. Could be braver shooting from outside the box.", "pro_academy", "Scored 7 because his strike is clean but he chooses to pass when shooting is the better option.", "Currently at pro academy. To reach elite, add 2-3 shots per match from the edge of the box."),
        "weak_foot": _skill(5, "Right foot is rarely used. Needs daily work — even short passes and simple drills will make a big difference.", "standard_club", "Scored 5 because his right foot is almost never used in build-up, even for short passes that would naturally call for it.", "Currently sitting at standard club for weak foot. To reach strong club, log 10 minutes of right-foot wall-work daily."),
        "one_v_one": _skill(7, "Calm in 1v1 situations. Picks the right moment to go past or release the ball.", "pro_academy", "Scored 7 because his decision making in 1v1 is mature — but he lacks the explosive change of pace elite wingers have.", "Currently at pro academy. To reach elite, add a sharper acceleration out of the feint."),
    },
    "tactical": {
        "positioning": _skill(9, "Always finds the right pocket of space between defenders. Smart at finding angles for his teammates.", "elite_academy", "Scored 9 because he consistently appears in the half-spaces where his team needs an out-ball — rare for his age.", "Currently at elite academy. To stay here, keep this spatial awareness as the game gets quicker."),
        "off_ball_movement": _skill(8, "Moves to receive constantly. Could improve runs in behind the defence to add another threat.", "pro_academy", "Scored 8 because he never stands still, but most of his movement is to receive, not to penetrate behind.", "Currently at pro academy. To reach elite, mix in 2-3 runs in behind per half."),
        "scanning": _skill(9, "Looks over both shoulders before the ball arrives almost every time. Top level habit for his age.", "elite_academy", "Scored 9 because his scanning rate (2-3 looks per possession) is well above the pro academy norm for his age.", "Currently at elite academy. To stay here, keep this scanning habit when the game gets faster."),
        "decision_making": _skill(9, "Picks the killer pass when it's there. Recycles smartly when it isn't. Mature beyond his years.", "elite_academy", "Scored 9 because he balances risk and security like a much older player — rarely forces a pass that isn't on.", "Currently at elite academy."),
        "timing_of_runs": _skill(8, "Times runs into the box well. Could vary the timing more to be unpredictable.", "pro_academy", "Scored 8 because his timing is mostly right but predictable — quicker defenders will read him.", "Currently at pro academy. To reach elite, add delayed runs and double movements."),
        "game_understanding": _skill(9, "Reads the game very well. Anticipates where the next ball will go.", "elite_academy", "Scored 9 because he reacts before the ball is played — clear sign of high football IQ.", "Currently at elite academy."),
    },
    "physical": {
        "acceleration": _skill(7, "Quick first few steps when he needs them. Not explosive but enough to create separation.", "pro_academy", "Scored 7 because his first 3 steps are sharp enough to escape pressure, but not enough to beat defenders for pace.", "Currently at pro academy. To reach elite, add explosive sprint training (resistance bands, 5m starts)."),
        "speed": _skill(6, "Average top speed. Not a player who beats defenders by running past them.", "strong_club", "Scored 6 because he relies on smart movement rather than top-end speed — limits him in transition.", "Currently at strong club for speed. To reach pro academy, focus on top-end sprint mechanics."),
        "balance": _skill(8, "Stays on his feet through contact. Good lower body strength for his age.", "pro_academy", "Scored 8 because he absorbs contact and recovers his balance quickly — strong core control.", "Currently at pro academy."),
        "agility": _skill(8, "Changes direction sharply. Light on his feet in tight areas.", "pro_academy", "Scored 8 because his change of direction is sharp and economical, especially in the final third.", "Currently at pro academy."),
        "intensity": _skill(6, "Drops off in the second half. Fitness is the area that limits him most right now.", "strong_club", "Scored 6 because his press intensity falls off visibly after 60 minutes — the legs limit the whole game.", "Currently at strong club for intensity. To reach pro academy, build aerobic base and 90-min match fitness."),
        "body_control": _skill(8, "Uses his body well to shield the ball and protect possession under pressure.", "pro_academy", "Scored 8 because he uses body angles to shield possession even against bigger defenders.", "Currently at pro academy."),
    },
    "mentality": {
        "confidence": _skill(9, "Wants the ball in every situation, even when his team is under pressure. Never hides.", "elite_academy", "Scored 9 because he demands the ball in every phase, even when the team is losing — clear leadership trait.", "Currently at elite academy."),
        "work_rate": _skill(7, "Works hard but tires late. Fitness will lift this score quickly.", "pro_academy", "Scored 7 because his work rate is excellent for 60 minutes but drops off — purely a fitness ceiling.", "Currently at pro academy. To reach elite, build the engine to sustain work rate for 90 minutes."),
        "courage_in_duels": _skill(8, "Steps into challenges rather than avoiding them. Brave for his size.", "pro_academy", "Scored 8 because he steps INTO 50-50s rather than away — rare bravery for his physical size.", "Currently at pro academy."),
        "response_to_mistakes": _skill(9, "Reacts to losing the ball by sprinting to win it back. Doesn't sulk after errors.", "elite_academy", "Scored 9 because his reaction to losing possession is immediate counter-press — elite professional habit.", "Currently at elite academy."),
        "competitive_mindset": _skill(9, "Clearly hates losing. Lifts his teammates when the score is against them.", "elite_academy", "Scored 9 because he visibly drives standards in his team — already a competitive leader.", "Currently at elite academy."),
        "focus": _skill(8, "Stays in the game mentally throughout. Rare to see him switch off.", "pro_academy", "Scored 8 because he stays mentally engaged even when uninvolved for long periods.", "Currently at pro academy."),
    },
    "scout_view": {
        "key_strengths": [
            "Always looks around before he gets the ball",
            "Left foot can pick out any pass",
            "Stays calm under pressure",
            "Wants the ball in every situation",
        ],
        "areas_of_concern": [
            "Tires late in matches",
            "Right foot needs work",
            "Slow to react when team loses the ball",
        ],
        "development_priorities": [
            "Build match fitness so he can press for 90 minutes",
            "Daily right-foot work — even 10 minutes a day",
            "Add runs in behind the defence to his game",
            "Quicker reaction when transitioning to defence",
        ],
        "appropriate_next_level": "Ready to step up to a stronger U15 team or an academy trial",
        "positional_suitability": "Best as a creative #10 right behind the striker. Could also play as an 8 in a 4-3-3 if he gets fitter.",
        "what_we_could_not_assess": [],
    },
    "potential_assessment": {
        "current_level": "Already one of the better players in his age group at club level",
        "development_potential": "High ceiling. Technique and game intelligence are already at a level that's hard to teach. If fitness comes, the path is wide open.",
        "recommended_next_step": "Play with older players at training to challenge his fitness and physical game",
        "three_month_focus": "Fitness and right-foot development. Keep everything else ticking and grow these two areas.",
    },
    "training_plan": {
        "exercises": [
            {"name": "Receive and turn", "description": "Stand in tight space with a teammate or cone behind you. Maximum three touches — open your body, turn, pass, repeat. Builds confidence on the ball when defenders are close.", "duration": "15 min"},
            {"name": "Right-foot passing wall", "description": "10 passes against a wall with the right foot, then 10 with the left. Repeat 10 rounds. Simple and boring but it works.", "duration": "15 min"},
            {"name": "Shuttle runs", "description": "5 sets of 6 sprints between cones 10 meters apart, 30 second rest. Builds the late-game fitness that's missing right now.", "duration": "20 min"},
            {"name": "Pass and move squares", "description": "4 players in a 10x10 square. Pass, then move to a different corner. Builds scanning and movement together.", "duration": "20 min"},
            {"name": "Shooting from the edge of the box", "description": "Receive a pass, take one touch to set yourself, shoot with the left then the right foot. 10 reps each side.", "duration": "20 min"},
        ],
        "weekly_focus": "Mix one fitness session, one passing session, and one finishing session each week. Keep games in the rotation too — match minutes are still the best teacher.",
        "thirty_day_plan": "First 30 days are about building habits. Daily right-foot work for 10 minutes — even at home with a ball against a wall. Two fitness sessions a week minimum. Track how you feel in the last 15 minutes of every match.",
        "ninety_day_plan": "By 90 days, the right foot should be reliable for short passes and the legs should hold up for full matches. Add small-sided games with older players if possible — that's where the biggest jumps happen.",
    },
    "video_comments": [
        {"timestamp": "00:24", "comment": "Great first touch on a tough ball — already checking his shoulder before it arrives."},
        {"timestamp": "01:12", "comment": "Beats his man cleanly — fakes inside, goes outside, plays a perfect cut-back."},
        {"timestamp": "02:40", "comment": "Should look around earlier here — gets caught with the ball and loses it."},
        {"timestamp": "03:55", "comment": "Smart run in behind the defence — perfect timing between the two defenders."},
        {"timestamp": "05:18", "comment": "Brilliant left-footed switch of play. Changes the whole shape of the attack."},
        {"timestamp": "07:02", "comment": "Drops deep to help build-up — shows maturity in his game."},
    ],
    "scores": {
        "technical": 8,
        "tactical": 9,
        "physical": 7,
        "mentality": 9,
        "overall_development": 8,
    },
    "scores_confidence": {
        "technical": "high",
        "tactical": "high",
        "physical": "medium",
        "mentality": "high",
        "overall_development": "high",
    },
    "overall_benchmark": {
        "tier": "pro_academy",
        "tier_label": "Pro Academy Standard",
        "percentile": "Currently in the top 10-15% of U14 attacking midfielders observed — particularly strong on passing range, scanning and competitive mindset.",
        "realistic_next_step": "Trial at a regional pro academy or a strong talent centre. Step up to U15 training with older players to push physical development.",
        "what_separates_from_next_tier": "Match fitness for 90 minutes plus a reliable right foot — these two together would put him into the elite academy bracket within 12-18 months.",
        "age_bracket_used": "U13-U14",
    },
    "final_summary": "Lukas is one of the more impressive players we've reviewed in his age group. The technique and game intelligence are already at a high level — what he sees and chooses to do with the ball is mature. Fitness is the next big step, alongside daily right-foot work. Keep doing what he's doing, add those two areas, and the path forward is wide open.",
    "evidence_quality_note": "Footage was clear and showed Lukas across 60+ touches in a competitive match environment. Set-piece situations and goalkeeping moments were not assessable from this clip.",
}


async def upsert_user(db, email, password, name, role="user"):
    existing = await db.users.find_one({"email": email.lower()})
    if existing:
        await db.users.update_one(
            {"email": email.lower()},
            {"$set": {"password_hash": hash_password(password), "full_name": name, "role": role}},
        )
        return existing["id"]
    user_id = str(uuid.uuid4())
    await db.users.insert_one({
        "id": user_id,
        "email": email.lower(),
        "password_hash": hash_password(password),
        "full_name": name,
        "role": role,
        "created_at": now_iso(),
    })
    return user_id


async def seed_premium_report(db, user_id, user_email):
    """Insert a pre-built, fully unlocked sample report for the premium user."""
    # remove old demo report
    await db.reports.delete_many({"user_id": user_id, "demo": True})

    report_id = str(uuid.uuid4())
    report_doc = {
        "id": report_id,
        "user_id": user_id,
        "user_email": user_email,
        "player_details": {
            "player_name": "Lukas A.",
            "age": 14,
            "position": "Attacking Midfielder",
            "preferred_foot": "left",
            "current_club": "IK Falken U15",
            "video_type": "match",
            "description": "I am number 10 in the white shirt, playing as an attacking midfielder.",
        },
        "video_filename": "demo-sample.mp4",  # no real file — premium card still renders without a video player issue
        "video_size_bytes": 0,
        "preview": PREVIEW,
        "full_report": FULL_REPORT,
        "is_paid": True,
        "manually_unlocked": True,
        "demo": True,
        "created_at": now_iso(),
        "paid_at": now_iso(),
    }
    await db.reports.insert_one(report_doc)
    return report_id


async def main():
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]

    free_id = await upsert_user(db, FREE_EMAIL, FREE_PASSWORD, FREE_NAME, role="user")
    premium_id = await upsert_user(db, PREMIUM_EMAIL, PREMIUM_PASSWORD, PREMIUM_NAME, role="user")
    report_id = await seed_premium_report(db, premium_id, PREMIUM_EMAIL.lower())

    print("\n=== TEST ACCOUNTS SEEDED ===\n")
    print(f"FREE user:    {FREE_EMAIL}  /  {FREE_PASSWORD}  (no reports yet)")
    print(f"PREMIUM user: {PREMIUM_EMAIL}  /  {PREMIUM_PASSWORD}")
    print(f"  -> 1 unlocked report id: {report_id}")
    print(f"ADMIN:        admin@elitescout.com  /  Admin@2026!Elite\n")
    client.close()


if __name__ == "__main__":
    asyncio.run(main())
