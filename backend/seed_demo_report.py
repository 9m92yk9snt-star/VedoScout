"""Seeds the public SAMPLE report (fictional player) shown at /sample-report.

Run:  python seed_demo_report.py
Idempotent — replaces the existing demo doc. All content is fictional and
schema-conformant with FULL_REPORT_PROMPT so the premium UI renders fully.
"""

import asyncio
import os
from datetime import datetime, timezone

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

DEMO_ID = "demo-sample-report"
NOW = datetime.now(timezone.utc).isoformat()

EV = lambda ts, obs: {"timestamp": ts, "observation": obs}  # noqa: E731

def sk(score, notes, conf, tier, evidence, verdict):
    return {"score": score, "notes": notes, "confidence": conf, "tier_for_age": tier,
            "evidence": evidence, "verdict": verdict, "cannot_evaluate": False}

FULL_REPORT = {
    "player_type": "Direct, brave wide attacker who loves running at defenders",
    "executive_summary": (
        "Noah is a right-footed winger who plays with real courage. Across the analysed "
        "footage he repeatedly took defenders on one-against-one, kept the ball close at "
        "speed and looked up before receiving. His first touch under pressure and his "
        "delivery at the end of runs are the clearest next steps. The profile fits a "
        "direct wide role where he can face the full-back and attack space."
    ),
    "final_summary": (
        "A brave, energetic winger with an honest engine. Keep feeding his love of "
        "one-v-one moments while sharpening the final action — the rest is developing "
        "exactly as it should at this age."
    ),
    "scores": {"technical": 7, "tactical": 6, "physical": 7, "mentality": 8, "overall_development": 7},
    "technical": {
        "first_touch": sk(6, "Noah's first touch is secure when he has space, taking the ball across his body into his stride. Under immediate pressure the touch pops up a little further from his feet.", "high", "strong_club",
                          [EV("00:41", "Chest-height ball killed instantly before turning"), EV("02:13", "Touch ran long under a tight press near the sideline")],
                          "Solid base — focus on cushioning the ball under pressure."),
        "dribbling": sk(8, "His standout tool. Keeps the ball glued to his right foot at speed, uses small feints and changes of pace to beat his man on the outside.", "high", "pro_academy",
                        [EV("00:58", "Beat two defenders on the touchline with a double feint"), EV("03:22", "Carried the ball 25 metres through midfield at pace")],
                        "Clearly ahead of age group — keep it sharp with both feet."),
        "passing": sk(6, "Short passing is tidy and mostly with the correct weight. Longer switches and cutback passes after runs still lose accuracy.", "medium", "strong_club",
                      [EV("01:34", "Crisp one-two on the edge of the box"), EV("03:47", "Cutback after a strong run hit the first defender")],
                      "Reliable short game — the final pass is the growth area."),
        "shooting": sk(7, "Strikes the ball cleanly with his right foot and doesn't hesitate when a chance appears. Composure in front of goal is good for his age.", "high", "strong_club",
                       [EV("03:59", "First-time finish low into the corner"), EV("01:52", "Shot from a tight angle when a square pass was on")],
                       "Natural striker of the ball — keep building shot selection."),
        "weak_foot": sk(5, "The left foot is used for safety touches only. He shifts the ball to his right even when the left is the faster option.", "medium", "standard_club",
                        [EV("02:40", "Turned back onto his right instead of releasing left-footed")],
                        "The single biggest technical unlock — daily left-foot reps."),
        "one_v_one": sk(8, "Wants the duel every time. Approaches defenders with speed, commits them, and rides light contact without losing balance.", "high", "pro_academy",
                        [EV("00:58", "Won his one-v-one and drew a second defender"), EV("02:55", "Skipped past a lunging tackle near the corner flag")],
                        "A real weapon — protect this bravery while adding end product."),
    },
    "tactical": {
        "positioning": sk(6, "Holds width well when his team builds up, stretching the pitch. Occasionally drifts inside too early which crowds the middle.", "medium", "strong_club",
                          [EV("00:22", "Hugged the touchline to create space for the overlapping full-back")],
                          "Good instincts — timing of when to come inside is next."),
        "scanning": sk(6, "Checks his shoulder before most receptions in build-up. Scanning drops when the ball is in the air or during transitions.", "medium", "strong_club",
                       [EV("01:28", "Two shoulder checks before receiving between the lines")],
                       "Above average habit for the age — make it constant."),
        "decision_making": sk(6, "Chooses the dribble first, which often works — but two or three times a simple pass kept the attack alive better.", "medium", "strong_club",
                              [EV("01:52", "Shot from a tight angle with a teammate free at the far post")],
                              "Balance the bravery with the simple option."),
        "timing_of_runs": sk(7, "Attacks the back post well and delays his run to stay onside. His best moments start without the ball.", "high", "pro_academy",
                             [EV("03:55", "Perfectly timed diagonal run behind the last line before the finish")],
                             "A genuine strength — keep making these runs."),
    },
    "physical": {
        "acceleration": sk(8, "Explosive over the first five metres — this is what makes his one-v-one game work. Reaches top speed quickly from a standing start.", "high", "pro_academy",
                           [EV("00:58", "Burst away from the full-back after the feint")],
                           "Top-end trait for the age group."),
        "balance": sk(7, "Stays on his feet through light shoulder contact and can adjust stride mid-dribble. Rarely on the ground.", "high", "strong_club",
                      [EV("02:55", "Rode a tackle and kept the ball moving")],
                      "Strong base for a wide player."),
        "intensity": sk(6, "Presses with energy in the first half of the footage; the intensity of recovery runs dips late on.", "medium", "strong_club",
                        [EV("04:02", "Slower recovery jog after losing the ball upfield")],
                        "Normal for the age — build the engine gradually."),
    },
    "mentality": {
        "confidence": sk(8, "Wants the ball in every phase, even straight after losing it. Never hides on the wing.", "high", "pro_academy",
                         [EV("02:58", "Demanded the ball again immediately after a failed dribble")],
                         "Exceptional appetite for the game."),
        "work_rate": sk(7, "Tracks his full-back honestly in the defensive phase and joins the press willingly.", "high", "strong_club",
                        [EV("01:05", "Sprinted 30 metres to cover the overlapping defender")],
                        "Honest two-way effort."),
        "response_to_mistakes": sk(8, "The best mental sign in the footage: after every loss of possession he restarts instantly — no head-drop, no hiding.", "high", "pro_academy",
                                   [EV("02:58", "Won the ball back four seconds after losing it")],
                                   "Elite habit for his age — protect it."),
    },
    "scout_view": {
        "key_strengths": [
            "Explosive one-v-one dribbling that beats defenders for real",
            "First five metres of acceleration are ahead of his age group",
            "Restarts instantly after mistakes — brilliant mental habit",
            "Times his runs behind the defence like an older player",
        ],
        "areas_of_concern": [
            "Left foot is currently a safety tool, not an option",
            "Final action (cutback / cross / last pass) lags behind the run that creates it",
        ],
        "development_priorities": [
            "Daily left-foot work — 10 minutes, wall passes and finishing",
            "End-product drills: cutbacks and low crosses at the end of full-speed runs",
            "Keep scanning habit constant during transitions",
        ],
        "appropriate_next_level": "Strong club level now, with pro-academy traits in one-v-one play and mentality",
        "positional_suitability": "Right winger facing his full-back; can develop into an inverted left-side role once the weak foot improves",
        "what_we_could_not_assess": ["Heading and aerial duels (no clear situations in the footage)", "Longer passing range beyond 25 metres"],
    },
    "potential_assessment": {
        "current_level": "Strong club standard with standout one-v-one qualities",
        "development_potential": "High — the rare combination of bravery, acceleration and instant recovery after mistakes gives real room to grow",
        "recommended_next_step": "Keep starting matches at current level and add two short technical sessions per week focused on the left foot and final pass",
        "three_month_focus": "Left-foot confidence and the quality of the final action after dribbles",
    },
    "overall_benchmark": {
        "tier": "strong_club",
        "tier_label": "Strong Club Standard",
        "comparison": "Compared with typical 12-year-old wingers, Noah's dribbling and acceleration sit in the top group, while his weak foot and final pass are at the average line.",
        "what_separates_from_next_tier": "A trustworthy left foot and a composed final action at the end of his runs — the running and bravery are already there.",
        "realistic_next_step": "Push for consistency across a full match and make the left foot a real option — that is the honest route to the next level.",
    },
    "snapshot": {
        "biggest_strength": "One-v-one dribbling at speed",
        "biggest_development_area": "Left foot as a real option",
        "hidden_talent": "Back-post runs timed like an older player",
        "next_milestone": "A goal or assist started with his left foot",
        "overall_progress_note": "Developing exactly the right habits — keep going!",
    },
    "development_roadmap": {
        "now": "Daily 10-minute left-foot routine",
        "three_months": "Cutbacks and low crosses at full speed",
        "six_months": "Constant scanning through transitions",
        "twelve_months": "Match impact in both attacking half-spaces",
    },
    "training_plan": {
        "weekly_focus": "Left foot + end product",
        "exercises": [
            {"name": "Wall passes — left foot only", "description": "50 passes against a wall, left foot, both cushioned and firm.", "duration": "10 min"},
            {"name": "Dribble + cutback circuit", "description": "Full-speed dribble to the byline cone, cut back to a target zone.", "duration": "15 min"},
            {"name": "Scan-and-turn rondo", "description": "Receive on the half-turn with a mandatory shoulder check before every touch.", "duration": "12 min"},
            {"name": "Match challenge", "description": "Attempt three left-footed actions in the next match — any outcome counts.", "duration": "match"},
            {"name": "1v1 ladder", "description": "Five one-v-one duels against a partner, alternating starting side.", "duration": "10 min"},
        ],
        "thirty_day_plan": "Make the left foot feel normal: short daily reps beat long rare sessions.",
        "ninety_day_plan": "End product: every full-speed run finishes with a measured cutback, cross or shot.",
    },
    "action_timeline": [
        {"timestamp": "00:22", "action_type": "off_ball_run", "title": "Holds Width in Build-Up", "description": "Stays wide on the touchline, dragging the full-back out and opening the half-space.", "rating": "positive", "outcome": "space created", "identity_confidence": "high", "cross_verified": True, "tracking_verified": True},
        {"timestamp": "00:41", "action_type": "first_touch", "title": "Clean Chest-High Control", "description": "Kills an awkward bouncing ball instantly and turns up the line.", "rating": "positive", "outcome": "possession kept", "identity_confidence": "high", "cross_verified": True, "tracking_verified": True},
        {"timestamp": "00:58", "action_type": "dribble", "title": "Double Feint Beats Two", "description": "Feints inside, pushes outside at pace and beats two defenders on the touchline.", "rating": "positive", "outcome": "attack progressed", "identity_confidence": "high", "cross_verified": True, "tracking_verified": True},
        {"timestamp": "01:34", "action_type": "pass", "title": "Sharp One-Two", "description": "Plays a crisp wall pass on the edge of the box and accelerates onto the return.", "rating": "positive", "outcome": "chance created", "identity_confidence": "high", "cross_verified": True, "tracking_verified": True},
        {"timestamp": "01:52", "action_type": "shot", "title": "Tight-Angle Shot", "description": "Shoots from a narrow angle with a teammate free at the far post — brave but the pass was on.", "rating": "neutral", "outcome": "saved", "identity_confidence": "high", "cross_verified": True, "tracking_verified": True},
        {"timestamp": "02:58", "action_type": "duel", "title": "Instant Reaction After Loss", "description": "Loses the ball, counter-presses immediately and wins it back within four seconds.", "rating": "positive", "outcome": "ball regained", "identity_confidence": "high", "cross_verified": True, "tracking_verified": True},
        {"timestamp": "03:22", "action_type": "dribble", "title": "25-Metre Carry", "description": "Drives through midfield at pace, keeping the ball close through traffic.", "rating": "positive", "outcome": "attack progressed", "identity_confidence": "high", "cross_verified": True, "tracking_verified": True},
        {"timestamp": "03:59", "action_type": "shot", "title": "First-Time Finish", "description": "Times his diagonal run behind the line and finishes low into the corner first time.", "rating": "positive", "outcome": "goal", "identity_confidence": "high", "cross_verified": True, "tracking_verified": True},
    ],
    "match_stats": {"total_actions": 24, "successful_dribbles": 5, "key_passes": 2, "shots": 3, "duels_won": "7/11", "minutes_analysed": 4},
    "video_comments": [
        {"timestamp": "00:58", "comment": "The double feint that beats two defenders — Noah's signature moment.", "frame_url": "/api/uploads/demo-frame-dribble.jpg", "identity_verified": True},
        {"timestamp": "03:59", "comment": "Run timed behind the line, finished first time into the corner.", "frame_url": "/api/uploads/demo-frame-shot.jpg", "identity_verified": True},
    ],
    "parent_summary": {
        "headline": "A brave one-v-one winger with the best mental habit we look for",
        "paragraphs": [
            "Noah plays the game with courage. He asks for the ball constantly, runs at defenders without fear, and his burst over the first five metres genuinely separates him from most players his age.",
            "The clearest next step is simple and very trainable: making his left foot a real option and finishing his brilliant runs with an equally good final pass. Nothing in this report is a worry — these are the normal next rungs on the ladder.",
        ],
        "good_news": "His instant reaction after mistakes — restarting within seconds, every single time — is a habit many older players still have to learn. Protect it by praising the reaction, not just the goals.",
    },
    "parent_tips": [
        "Praise the brave decision, even when the dribble doesn't come off.",
        "Ask 'what did you see?' rather than 'why did you lose it?' after games.",
        "Ten minutes of left-foot wall passes beats an hour once a week.",
        "Let match day stay fun — the development happens in training.",
    ],
    "coach_notes": [
        "Best used as a right winger facing his full-back with space to attack.",
        "Give him licence to take players on — the end product will catch up.",
        "Left-foot bias: build drills where the left is the only option.",
        "Counter-pressing instinct is excellent — build the press around him.",
        "Watch minutes late in matches; intensity dips before technique does.",
    ],
    "scout_outlook": {
        "current_level_label": "Strong Club Standard",
        "current_level_dots": 3,
        "potential_level_label": "Pro Academy Standard",
        "potential_level_dots": 4,
        "recruitment_readiness": "Medium — Keep Developing",
        "long_term_potential": "High",
        "long_term_note": "The bravery-acceleration-recovery combination is the hard part — and he already has it. The trainable parts are exactly that: trainable.",
    },
    "parents_package": {
        "home_drills": [
            {"name": "Left-Foot Wall Game", "minutes": 10, "equipment": "a ball and a wall", "steps": ["Stand 3 metres from a wall", "50 passes with the LEFT foot only", "Last 10: control with left, pass with left"], "success_sign": "The left-foot pass starts making the same sound as the right.", "targets": "Weak foot"},
            {"name": "Byline Cutback Race", "minutes": 8, "equipment": "two cones and a ball", "steps": ["Sprint-dribble to the far cone", "Chop the ball back around it", "Pass firmly into a 1-metre target zone"], "success_sign": "He hits the target zone 4 times out of 5 at full speed.", "targets": "Final pass"},
            {"name": "Shoulder-Check Freeze", "minutes": 5, "equipment": "just a ball", "steps": ["You call 'now' at random moments", "Noah freezes and points where the nearest 'defender' would be", "Then plays the next touch away from that spot"], "success_sign": "He starts checking before you call it.", "targets": "Scanning"},
        ],
        "watch_together": {
            "intro": "Watch these two moments together and let Noah talk first — your job is just to ask what he saw.",
            "moments": [
                {"timestamp": "00:58", "say_this": "I love that you went at him there — what did you spot that made you go outside?"},
                {"timestamp": "02:58", "say_this": "This is my favourite moment of the whole video — look how fast you won it back."},
            ],
            "avoid": ["Avoid replaying the lost balls more than once — the reaction matters more than the loss.", "Avoid comparing him to teammates while watching."],
        },
        "message_to_player": {
            "greeting": "Hey Noah,",
            "body": "That double feint at 00:58? Defenders will have nightmares about that one. And the way you won the ball back at 02:58 after losing it — that's the thing real pros do, and you're already doing it at 12. Here's your next secret weapon: your left foot. Ten minutes a day, just you and a wall. When that clicks, nobody on the pitch will know which way you're going.",
            "signoff": "Keep playing YOUR way. — Your scout",
        },
    },
    "next_match_missions": [
        {"mission": "Use your left foot on purpose", "target": "3 times", "why": "Defenders can't guess your direction once the left is real."},
        {"mission": "Check your shoulder before receiving", "target": "5 times", "why": "You'll know your next move before the ball arrives."},
        {"mission": "Finish one full-speed run with a cutback", "target": "1 time", "why": "Your runs deserve an ending as good as the start."},
    ],
    "cross_verification": {
        "status": "verified",
        "events_checked": 8,
        "events_dropped": 0,
        "dropped": [],
        "score_pairs": {"technical": [7, 7], "tactical": [6, 6], "physical": [7, 8], "mentality": [8, 8], "overall_development": [7, 7]},
        "max_score_gap": 1,
        "contradictions": [],
        "verified_at": NOW,
    },
}

DOC = {
    "id": DEMO_ID,
    "demo": True,
    "user_id": "demo-system",
    "user_email": "demo@scoutmeplay.com",
    "is_paid": True,
    "paid_at": NOW,
    "created_at": NOW,
    "full_generated_at": NOW,
    "analysis_status": "ready",
    "full_report_status": "ready",
    "progress_step": 5,
    "video_duration_sec": 252.0,
    "player_details": {
        "player_name": "Noah (Sample Player)",
        "age": "12",
        "position": "Winger",
        "preferred_foot": "right",
        "current_club": "Riverside United U12",
        "jersey_number": "11",
        "country": "Denmark",
        "video_type": "match",
        "description": "Fictional sample player — this report shows exactly what every family receives.",
    },
    "identity_stats": {"checked": 4, "verified": 4, "dropped": 0},
    "anchors": [{"t": t, "box": {"x": 0.45, "y": 0.4, "w": 0.08, "h": 0.16}} for t in (12.0, 55.0, 98.0, 141.0, 190.0, 232.0)],
    "player_track": {"points": [{"t": float(t), "x": 0.3 + 0.4 * ((t % 60) / 60.0), "y": 0.35 + 0.2 * ((t % 30) / 30.0), "conf": 0.9} for t in range(10, 240, 3)], "segments": 3},
    "display_crop_filename": "demo-player.jpg",
    "player_photo_filename": "demo-player.jpg",
    "photo_source": "upload",
    "preview": {
        "teaser_score": 70,
        "headline": "A brave one-v-one winger with pro-academy habits",
        "summary": "Explosive dribbling, honest work rate and the best mental habit we look for — instant reactions after mistakes.",
    },
    "full_report": FULL_REPORT,
}


async def main():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]
    await db.reports.delete_many({"id": DEMO_ID})
    await db.reports.insert_one(dict(DOC))
    print(f"Seeded demo report: {DEMO_ID}")


if __name__ == "__main__":
    asyncio.run(main())
