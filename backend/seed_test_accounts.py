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

# Pre-built full premium report
FULL_REPORT = {
    "player_type": "Smart playmaker · strong left foot",
    "executive_summary": "Lukas is a smart, calm playmaker with a left foot that opens up defences. He reads the game very well for his age and is brave on the ball under pressure. He plays simple when needed and risky when it pays off. The biggest area to grow is his fitness — he fades in the second half. Build the legs and the rest is already at a high level.",
    "technical": {
        "first_touch": {"score": 8, "notes": "Clean first touch that sets him up to play forward almost every time. Rare to see him let the ball bounce away."},
        "ball_control": {"score": 8, "notes": "Keeps the ball close in tight space. Comfortable on both surfaces of his left foot."},
        "dribbling": {"score": 7, "notes": "Beats defenders with a feint and change of direction rather than pure pace. Effective in 1v1s."},
        "passing": {"score": 9, "notes": "His standout skill. Vision to find passes others miss, and the technique to deliver them."},
        "shooting": {"score": 7, "notes": "Strikes the ball cleanly with his left foot. Could be braver shooting from outside the box."},
        "weak_foot": {"score": 5, "notes": "Right foot is rarely used. Needs daily work — even short passes and simple drills will make a big difference."},
        "one_v_one": {"score": 7, "notes": "Calm in 1v1 situations. Picks the right moment to go past or release the ball."},
    },
    "tactical": {
        "positioning": {"score": 9, "notes": "Always finds the right pocket of space between defenders. Smart at finding angles for his teammates."},
        "off_ball_movement": {"score": 8, "notes": "Moves to receive constantly. Could improve runs in behind the defence to add another threat."},
        "scanning": {"score": 9, "notes": "Looks over both shoulders before the ball arrives almost every time. Top level habit for his age."},
        "decision_making": {"score": 9, "notes": "Picks the killer pass when it's there. Recycles smartly when it isn't. Mature beyond his years."},
        "timing_of_runs": {"score": 8, "notes": "Times runs into the box well. Could vary the timing more to be unpredictable."},
        "game_understanding": {"score": 9, "notes": "Reads the game very well. Anticipates where the next ball will go."},
    },
    "physical": {
        "acceleration": {"score": 7, "notes": "Quick first few steps when he needs them. Not explosive but enough to create separation."},
        "speed": {"score": 6, "notes": "Average top speed. Not a player who beats defenders by running past them."},
        "balance": {"score": 8, "notes": "Stays on his feet through contact. Good lower body strength for his age."},
        "agility": {"score": 8, "notes": "Changes direction sharply. Light on his feet in tight areas."},
        "intensity": {"score": 6, "notes": "Drops off in the second half. Fitness is the area that limits him most right now."},
        "body_control": {"score": 8, "notes": "Uses his body well to shield the ball and protect possession under pressure."},
    },
    "mentality": {
        "confidence": {"score": 9, "notes": "Wants the ball in every situation, even when his team is under pressure. Never hides."},
        "work_rate": {"score": 7, "notes": "Works hard but tires late. Fitness will lift this score quickly."},
        "courage_in_duels": {"score": 8, "notes": "Steps into challenges rather than avoiding them. Brave for his size."},
        "response_to_mistakes": {"score": 9, "notes": "Reacts to losing the ball by sprinting to win it back. Doesn't sulk after errors."},
        "competitive_mindset": {"score": 9, "notes": "Clearly hates losing. Lifts his teammates when the score is against them."},
        "focus": {"score": 8, "notes": "Stays in the game mentally throughout. Rare to see him switch off."},
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
    "final_summary": "Lukas is one of the more impressive players we've reviewed in his age group. The technique and game intelligence are already at a high level — what he sees and chooses to do with the ball is mature. Fitness is the next big step, alongside daily right-foot work. Keep doing what he's doing, add those two areas, and the path forward is wide open.",
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
