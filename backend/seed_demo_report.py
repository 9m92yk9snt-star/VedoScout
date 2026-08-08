"""Seeds the public SAMPLE report (fictional player) shown at /sample-report.

Auto-seeded at backend startup via ensure_demo_report(db) — bump DEMO_VERSION
after editing content so preview AND production refresh on next boot/redeploy.
All content is fictional and schema-conformant with FULL_REPORT_PROMPT so the
premium UI renders fully.
"""

import asyncio
import logging
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

logger = logging.getLogger("demo_seed")

DEMO_ID = "demo-sample-report"
DEMO_VERSION = 2
NOW = datetime.now(timezone.utc).isoformat()

EV = lambda ts, obs: {"timestamp": ts, "observation": obs}  # noqa: E731

def sk(score, notes, conf, tier, evidence, verdict):
    return {"score": score, "notes": notes, "confidence": conf, "tier_for_age": tier,
            "evidence": evidence, "verdict": verdict, "cannot_evaluate": False}

FULL_REPORT = {
    "player_type": "Explosive, brave wide attacker with a genuine end product",
    "executive_summary": (
        "Noah is a right-footed winger who plays with real courage and — rarer at this age — "
        "real efficiency. Across the analysed footage he beat his marker in seven of nine "
        "one-against-one duels, scored with a perfectly timed run at 03:59 and set up a goal "
        "with a driven cutback at 04:10. His acceleration over the first five metres and his "
        "instant reaction after losing the ball are pro-academy traits already. The next "
        "steps are clear and very trainable: making the left foot a true option and keeping "
        "his scanning constant through transitions. The profile fits a direct wide role where "
        "he can face the full-back and attack space — and it projects upwards."
    ),
    "final_summary": (
        "A standout, brave winger whose numbers back up the eye test: 7/9 duels won, a goal, "
        "an assist and an instant counter-press after every loss. Keep feeding his love of "
        "one-v-one moments while the left foot catches up — this is a profile worth investing in."
    ),
    "scores": {"technical": 8, "tactical": 7, "physical": 8, "mentality": 9, "overall_development": 8},
    "technical": {
        "first_touch": sk(7, "Noah's first touch is secure and directional — he takes the ball across his body into his stride and away from pressure. At 00:41 he killed a chest-high ball instantly; at 02:13, under a hard touchline press, the touch popped slightly long — the only loose control in four minutes.", "high", "pro_academy",
                          [EV("00:41", "Chest-height ball killed instantly before turning up the line"), EV("01:28", "Received on the half-turn between the lines, first touch eliminated a defender"), EV("02:13", "Touch ran long under a tight press near the sideline")],
                          "Already directional under pressure — cushioning against the hardest press is the last step."),
        "dribbling": sk(9, "His signature weapon, and it is genuinely rare. The ball stays glued to his right foot at full sprint, he uses double feints and changes of pace, and he beat multiple defenders repeatedly — 00:58 (two beaten), 03:22 (25-metre carry through traffic), 04:10 (byline burst before the assist).", "high", "pro_academy",
                        [EV("00:58", "Double feint beats two defenders on the touchline at speed"), EV("03:22", "25-metre carry through central traffic without slowing"), EV("04:10", "Explosive byline burst past the recovering full-back")],
                        "Top of his age group. Protect it, then add the same moves off the left side."),
        "passing": sk(7, "Short combination play is crisp and correctly weighted — the 01:34 one-two was executed at match tempo. The final pass now produces real outcomes: the 04:10 driven cutback was an assist. Longer switches remain the growth edge.", "high", "strong_club",
                      [EV("01:34", "Crisp one-two on the edge of the box at full tempo"), EV("04:10", "Driven low cutback assist to the penalty spot")],
                      "The final pass has arrived — long-range switching is next."),
        "shooting": sk(8, "Strikes the ball cleanly and early. The 03:59 goal — a first-time, low finish across the keeper at the end of a timed run — is a finish many players two years older don't attempt. Shot selection is maturing: only one low-value attempt in the footage.", "high", "pro_academy",
                       [EV("03:59", "First-time finish low into the far corner — goal"), EV("01:52", "Shot from a tight angle when a square pass was on")],
                       "Natural, composed striker of the ball — keep building both-foot finishing."),
        "weak_foot": sk(6, "The left foot is functional for safety touches and short releases but he still shifts to his right when the left is the faster option (02:40). This is the single clearest unlock left in his game — and it is purely a repetition issue.", "medium", "strong_club",
                        [EV("02:40", "Turned back onto his right instead of releasing left-footed")],
                        "The one gap between him and a complete wide profile — daily left-foot reps."),
        "one_v_one": sk(9, "Elite appetite and elite execution for the age: seven of nine duels won. He approaches defenders at speed, commits them fully, rides contact without losing stride and — crucially — his duels now END in something: a shot, a cutback, a won corner.", "high", "pro_academy",
                        [EV("00:58", "Won the duel and drew a second defender out of shape"), EV("02:55", "Skipped past a lunging tackle near the corner flag"), EV("04:10", "Beat his man on the outside and delivered the assist")],
                        "A match-winning weapon that already produces outcomes."),
    },
    "tactical": {
        "positioning": sk(7, "Holds maximum width in build-up, stretching the back line and opening the half-space for his midfielder — visible at 00:22 and repeated all game. Occasionally drifts inside a beat early, but the base instinct is exactly right.", "high", "strong_club",
                          [EV("00:22", "Hugged the touchline, dragging the full-back out and opening the half-space")],
                          "The width discipline of an older player — timing the move inside is the polish."),
        "scanning": sk(7, "Checks his shoulder before most receptions — two clean scans before the 01:28 reception between the lines. Scanning still fades for a moment during fast transitions, which is normal at this age and very coachable.", "high", "strong_club",
                       [EV("01:28", "Two shoulder checks before receiving between the lines"), EV("00:41", "Scan before the chest control let him turn immediately")],
                       "An above-age habit — make it constant through transitions."),
        "decision_making": sk(7, "The dribble-first instinct now comes with judgement: the 04:10 cutback instead of a shot from a narrow angle was the standout decision of the footage. One tight-angle shot (01:52) with a free teammate remains the honest counter-example.", "high", "strong_club",
                              [EV("04:10", "Chose the cutback over a narrow-angle shot — assist"), EV("01:52", "Shot from a tight angle with a teammate free at the far post")],
                              "Bravery and judgement are converging — exactly the curve we want."),
        "timing_of_runs": sk(8, "Attacks the blind side and delays his run to stay onside like a player years older. The 03:59 goal started with a curved diagonal begun the moment his teammate's head came up — textbook.", "high", "pro_academy",
                             [EV("03:55", "Curved diagonal run behind the last line, timed to the passer's head lift"), EV("00:22", "Early width created the channel he later exploited")],
                             "A genuine separator — runs that create goals on their own."),
    },
    "physical": {
        "acceleration": sk(9, "Explosive over the first five metres — the burst at 00:58 opened three metres on a defender who had position. This is the engine behind his entire one-v-one game and it repeated late into the footage without fading.", "high", "pro_academy",
                           [EV("00:58", "Burst away from the full-back after the feint — three metres in five steps"), EV("04:10", "Beat the recovering defender to the byline in the final minute")],
                           "Top-end trait — among the best we see at this age."),
        "balance": sk(8, "Stays on his feet through shoulder contact at full speed and adjusts stride mid-dribble. Went to ground once in four minutes despite constant contact — remarkable for a player who invites this many duels.", "high", "pro_academy",
                      [EV("02:55", "Rode a lunging tackle and kept the ball moving at pace")],
                      "The contact balance of a much older player."),
        "intensity": sk(7, "Presses aggressively and repeatedly — the 01:05 thirty-metre recovery sprint is the effort of a two-way player. Late in the footage recovery jogs dip slightly, which is age-normal and builds naturally.", "high", "strong_club",
                        [EV("01:05", "Thirty-metre recovery sprint to cover the overlapping defender"), EV("04:02", "Slower recovery jog after losing the ball upfield")],
                        "An honest engine — the base for a complete wide player."),
    },
    "mentality": {
        "confidence": sk(9, "Wants the ball in every phase, including immediately after mistakes. At 02:58 he demanded the ball back seconds after losing it. Never hides on the wing, never plays safe to protect himself — this is the temperament scouts flag first.", "high", "pro_academy",
                         [EV("02:58", "Demanded the ball again immediately after a failed dribble"), EV("01:52", "Took responsibility for the chance rather than hiding")],
                         "Exceptional competitive appetite — the foundation everything else is built on."),
        "work_rate": sk(8, "Tracks his full-back honestly, joins the press on every trigger and sprints back thirty metres when the shape demands it. Two-way commitment at this level is rare in players with his attacking output.", "high", "pro_academy",
                        [EV("01:05", "Sprinted 30 metres to cover the overlapping defender"), EV("02:58", "First presser after his own loss of possession")],
                        "Honest two-way effort that coaches trust."),
        "response_to_mistakes": sk(9, "The best mental signature in the footage: after every loss of possession he restarts instantly — counter-press, win it back, go again. At 02:58 the ball was regained within four seconds. No head-drop, no hiding, four minutes straight.", "high", "pro_academy",
                                   [EV("02:58", "Won the ball back four seconds after losing it"), EV("04:02", "Immediate press restart even when the recovery run came late")],
                                   "An elite habit most seniors still have to learn — protect it."),
    },
    "scout_view": {
        "key_strengths": [
            "One-v-one dribbling that wins real duels — 7 of 9 in this footage",
            "First five metres of acceleration in the top group for his age",
            "Restarts within seconds of every mistake — an elite mental habit",
            "Times runs behind the defence like an older player — it produced a goal here",
            "End product arriving: a goal AND an assist inside four analysed minutes",
        ],
        "areas_of_concern": [
            "Left foot is functional but not yet a real option under pressure",
            "Scanning fades briefly during fast transitions",
        ],
        "development_priorities": [
            "Daily left-foot work — 10 minutes, wall passes and finishing",
            "Keep the scanning habit constant through transitions",
            "Extend passing range: driven switches beyond 25 metres",
        ],
        "appropriate_next_level": "Pro-academy standard in one-v-one play, acceleration and mentality; strong-club in the remaining tools and closing fast",
        "positional_suitability": "Right winger facing his full-back; projects into an inverted left-side role once the weak foot matures",
        "what_we_could_not_assess": ["Heading and aerial duels (no clear situations in the footage)", "Longer passing range beyond 25 metres"],
    },
    "potential_assessment": {
        "current_level": "Pro-academy traits in his headline tools — one-v-one, acceleration, mentality — with strong-club consistency around them",
        "development_potential": "Very high — bravery, explosive acceleration, instant recovery after mistakes AND measurable end product is a combination we see in a small fraction of players at this age",
        "recommended_next_step": "Seek higher-level match minutes this season and add two short technical sessions per week focused on the left foot and driven switches",
        "three_month_focus": "Left-foot confidence under pressure and constant scanning through transitions",
    },
    "overall_benchmark": {
        "tier": "pro_academy",
        "tier_label": "Pro Academy Standard",
        "comparison": "Compared with typical 12-year-old wingers, Noah's dribbling, acceleration and mental response sit in the top group; his weak foot and long passing sit at the strong-club line — and both are pure training questions.",
        "what_separates_from_next_tier": "A trustworthy left foot and constant scanning in transition — the athletic and mental hard parts are already there.",
        "realistic_next_step": "Consistent impact across full matches at a higher level of opposition — the footage says he is ready to be tested.",
    },
    "snapshot": {
        "biggest_strength": "One-v-one dribbling that produces goals",
        "biggest_development_area": "Left foot as a real option",
        "hidden_talent": "Back-post runs timed like an older player",
        "next_milestone": "A goal or assist started with his left foot",
        "overall_progress_note": "A standout profile developing exactly the right habits — keep going!",
    },
    "development_roadmap": {
        "now": "Daily 10-minute left-foot routine",
        "three_months": "Driven switches and cutbacks at full speed",
        "six_months": "Constant scanning through transitions",
        "twelve_months": "Match-deciding impact in both attacking half-spaces at a higher level",
    },
    "training_plan": {
        "weekly_focus": "Left foot + range of passing",
        "exercises": [
            {"name": "Wall passes — left foot only", "description": "50 passes against a wall, left foot, both cushioned and firm.", "duration": "10 min"},
            {"name": "Dribble + cutback circuit", "description": "Full-speed dribble to the byline cone, driven cutback into a 1-metre target zone.", "duration": "15 min"},
            {"name": "Scan-and-turn rondo", "description": "Receive on the half-turn with a mandatory shoulder check before every touch.", "duration": "12 min"},
            {"name": "Match challenge", "description": "Attempt three left-footed actions in the next match — any outcome counts.", "duration": "match"},
            {"name": "1v1 ladder", "description": "Five one-v-one duels against a partner, alternating starting side.", "duration": "10 min"},
        ],
        "thirty_day_plan": "Make the left foot feel normal: short daily reps beat long rare sessions.",
        "ninety_day_plan": "Every full-speed run ends with a measured cutback, driven cross or first-time shot — on either foot.",
    },
    "action_timeline": [
        {"timestamp": "00:22", "action_type": "off_ball_run", "title": "Holds Width in Build-Up", "description": "Stays glued to the touchline as his team builds, dragging the full-back three metres wider and opening the half-space his midfielder later attacks. Discipline most wingers learn years later.", "rating": "positive", "outcome": "space created", "identity_confidence": "high", "cross_verified": True, "tracking_verified": True},
        {"timestamp": "00:41", "action_type": "first_touch", "title": "Clean Chest-High Control", "description": "Kills an awkward bouncing ball instantly with one touch, already scanning before it arrives, and turns up the line in the same movement.", "rating": "positive", "outcome": "possession kept", "identity_confidence": "high", "cross_verified": True, "tracking_verified": True},
        {"timestamp": "00:58", "action_type": "dribble", "title": "Double Feint Beats Two", "description": "Feints inside, pushes outside at full pace and beats two defenders on the touchline — three metres of separation created in five steps. The signature moment of the footage.", "rating": "positive", "outcome": "attack progressed", "identity_confidence": "high", "cross_verified": True, "tracking_verified": True},
        {"timestamp": "01:05", "action_type": "defensive_action", "title": "30-Metre Recovery Sprint", "description": "The instant possession turns over he sprints thirty metres to cover the overlapping defender — two-way commitment straight after an attacking action.", "rating": "positive", "outcome": "danger covered", "identity_confidence": "high", "cross_verified": True, "tracking_verified": True},
        {"timestamp": "01:28", "action_type": "off_ball_run", "title": "Scans Twice, Receives Between Lines", "description": "Two clean shoulder checks before the ball travels, then receives on the half-turn between the lines — his first touch eliminates a defender because he already knew where the pressure was.", "rating": "positive", "outcome": "line broken", "identity_confidence": "high", "cross_verified": True, "tracking_verified": True},
        {"timestamp": "01:34", "action_type": "pass", "title": "Sharp One-Two at Tempo", "description": "Plays a crisp wall pass on the edge of the box and accelerates onto the return without breaking stride — combination play at genuine match tempo.", "rating": "positive", "outcome": "chance created", "identity_confidence": "high", "cross_verified": True, "tracking_verified": True},
        {"timestamp": "01:52", "action_type": "shot", "title": "Tight-Angle Shot", "description": "Shoots from a narrow angle with a teammate free at the far post — brave, but the square pass was the higher-value option. The honest note in an excellent performance.", "rating": "neutral", "outcome": "saved", "identity_confidence": "high", "cross_verified": True, "tracking_verified": True},
        {"timestamp": "02:40", "action_type": "dribble", "title": "Right-Foot Safety Turn", "description": "Under pressure he turns back onto his right foot when a left-footed release was the faster escape — the clearest picture of the weak-foot development point.", "rating": "neutral", "outcome": "possession kept", "identity_confidence": "high", "cross_verified": True, "tracking_verified": True},
        {"timestamp": "02:55", "action_type": "dribble", "title": "Rides the Lunging Tackle", "description": "Skips past a full-blooded lunge near the corner flag, absorbing the contact without losing stride or the ball — contact balance of a much older player.", "rating": "positive", "outcome": "attack progressed", "identity_confidence": "high", "cross_verified": True, "tracking_verified": True},
        {"timestamp": "02:58", "action_type": "duel", "title": "Ball Regained in 4 Seconds", "description": "Loses the ball, counter-presses instantly and wins it back within four seconds — no head-drop, no hesitation. The best mental signature in the entire clip.", "rating": "positive", "outcome": "ball regained", "identity_confidence": "high", "cross_verified": True, "tracking_verified": True},
        {"timestamp": "03:22", "action_type": "dribble", "title": "25-Metre Carry Through Traffic", "description": "Drives through central midfield at pace with the ball glued to his foot, drawing three opponents and releasing at exactly the right moment.", "rating": "positive", "outcome": "attack progressed", "identity_confidence": "high", "cross_verified": True, "tracking_verified": True},
        {"timestamp": "03:59", "action_type": "shot", "title": "GOAL — Timed Run, First-Time Finish", "description": "Starts a curved diagonal the moment the passer's head lifts, stays onside by half a metre and sweeps a first-time finish low across the keeper into the far corner.", "rating": "positive", "outcome": "goal", "identity_confidence": "high", "cross_verified": True, "tracking_verified": True},
        {"timestamp": "04:10", "action_type": "pass", "title": "ASSIST — Byline Burst + Driven Cutback", "description": "Beats the recovering full-back to the byline with pure acceleration, then chooses the driven low cutback to the penalty spot over a narrow-angle shot — finished first time by his teammate.", "rating": "positive", "outcome": "assist", "identity_confidence": "high", "cross_verified": True, "tracking_verified": True},
    ],
    "match_stats": {"total_actions": 31, "successful_dribbles": 7, "key_passes": 3, "shots": 4, "duels_won": "9/12", "minutes_analysed": 4},
    "video_comments": [
        {"timestamp": "00:58", "comment": "The double feint that beats two defenders — Noah's signature moment, three metres of separation in five steps.", "frame_url": "/api/uploads/demo-frame-dribble.jpg", "identity_verified": True},
        {"timestamp": "03:59", "comment": "The goal: run timed to the passer's head lift, finished first time low into the corner.", "frame_url": "/api/uploads/demo-frame-shot.jpg", "identity_verified": True},
    ],
    "parent_summary": {
        "headline": "A standout one-v-one winger whose bravery now produces goals",
        "paragraphs": [
            "Noah plays the game with courage — and this footage shows the courage paying off. He won seven of nine duels, scored with a perfectly timed run, set up another goal with a driven cutback, and his burst over the first five metres genuinely separates him from almost every player his age.",
            "The clearest next step is simple and very trainable: making his left foot a real option. Nothing in this report is a worry — these are the last rungs between a very good young winger and a complete one.",
        ],
        "good_news": "His instant reaction after mistakes — restarting within seconds, every single time — is a habit many senior players still have to learn. Combined with a goal and an assist in four analysed minutes, this is the profile of a player trending sharply upwards.",
    },
    "parent_tips": [
        "Praise the brave decision, even when the dribble doesn't come off.",
        "Ask 'what did you see?' rather than 'why did you lose it?' after games.",
        "Ten minutes of left-foot wall passes beats an hour once a week.",
        "Let match day stay fun — the development happens in training.",
    ],
    "coach_notes": [
        "Best used as a right winger facing his full-back with space to attack.",
        "Give him licence to take players on — the end product is already arriving.",
        "Left-foot bias: build drills where the left is the only option.",
        "Counter-pressing instinct is excellent — build the press around him.",
        "He is ready to be tested against stronger opposition — stretch him.",
    ],
    "scout_outlook": {
        "current_level_label": "Pro Academy Standard",
        "current_level_dots": 4,
        "potential_level_label": "Elite Pathway Potential",
        "potential_level_dots": 5,
        "recruitment_readiness": "High — Ready to Be Tested at the Next Level",
        "long_term_potential": "Very High",
        "long_term_note": "The bravery-acceleration-recovery combination is the hard part — and he already has it, with the numbers to prove it. The remaining gaps are exactly the trainable kind.",
    },
    "parents_package": {
        "home_drills": [
            {"name": "Left-Foot Wall Game", "minutes": 10, "equipment": "a ball and a wall", "steps": ["Stand 3 metres from a wall", "50 passes with the LEFT foot only", "Last 10: control with left, pass with left"], "success_sign": "The left-foot pass starts making the same sound as the right.", "targets": "Weak foot"},
            {"name": "Byline Cutback Race", "minutes": 8, "equipment": "two cones and a ball", "steps": ["Sprint-dribble to the far cone", "Chop the ball back around it", "Drive a firm pass into a 1-metre target zone"], "success_sign": "He hits the target zone 4 times out of 5 at full speed.", "targets": "Final pass"},
            {"name": "Shoulder-Check Freeze", "minutes": 5, "equipment": "just a ball", "steps": ["You call 'now' at random moments", "Noah freezes and points where the nearest 'defender' would be", "Then plays the next touch away from that spot"], "success_sign": "He starts checking before you call it.", "targets": "Scanning"},
        ],
        "watch_together": {
            "intro": "Watch these three moments together and let Noah talk first — your job is just to ask what he saw.",
            "moments": [
                {"timestamp": "00:58", "say_this": "I love that you went at him there — what did you spot that made you go outside?"},
                {"timestamp": "02:58", "say_this": "This is my favourite moment of the whole video — look how fast you won it back."},
                {"timestamp": "04:10", "say_this": "You could have shot here — what made you choose the pass? (The answer is why coaches will love you.)"},
            ],
            "avoid": ["Avoid replaying the lost balls more than once — the reaction matters more than the loss.", "Avoid comparing him to teammates while watching."],
        },
        "message_to_player": {
            "greeting": "Hey Noah,",
            "body": "That double feint at 00:58? Defenders will have nightmares about that one. The goal at 03:59 — timed like a pro. And the cutback at 04:10 instead of the shot? That decision is the moment I knew this report would be special. Here's your next secret weapon: your left foot. Ten minutes a day, just you and a wall. When that clicks, nobody on the pitch will know which way you're going — and this report says everything else is already there.",
            "signoff": "Keep playing YOUR way. — Your scout",
        },
    },
    "next_match_missions": [
        {"mission": "Use your left foot on purpose", "target": "3 times", "why": "Defenders can't guess your direction once the left is real."},
        {"mission": "Check your shoulder before receiving", "target": "5 times", "why": "You'll know your next move before the ball arrives."},
        {"mission": "Finish one full-speed run with a driven cutback", "target": "1 time", "why": "You assisted with it at 04:10 — now make it a trademark."},
    ],
    "cross_verification": {
        "status": "verified",
        "events_checked": 13,
        "events_dropped": 0,
        "dropped": [],
        "score_pairs": {"technical": [8, 8], "tactical": [7, 7], "physical": [8, 9], "mentality": [9, 9], "overall_development": [8, 8]},
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
        "teaser_score": 84,
        "headline": "A standout one-v-one winger — a goal AND an assist in four analysed minutes",
        "summary": "Explosive dribbling (7/9 duels won), pro-academy acceleration, and the best mental habit we look for: instant reactions after mistakes.",
    },
    "full_report": FULL_REPORT,
}


async def ensure_demo_report(db) -> None:
    """Startup-safe: restores bundled demo images into uploads/ and (re)seeds
    the sample report when missing or outdated. Idempotent — runs every boot."""
    base = Path(__file__).parent
    try:
        uploads = base / "uploads"
        uploads.mkdir(parents=True, exist_ok=True)
        src = base / "static" / "demo"
        if src.is_dir():
            for f in src.glob("*.jpg"):
                dst = uploads / f.name
                if not dst.exists():
                    shutil.copyfile(f, dst)
    except Exception:
        logger.exception("demo image restore failed (non-fatal)")
    try:
        existing = await db.reports.find_one({"id": DEMO_ID}, {"demo_version": 1})
        if existing and existing.get("demo_version") == DEMO_VERSION:
            return
        await db.reports.delete_many({"id": DEMO_ID})
        await db.reports.insert_one({**DOC, "demo_version": DEMO_VERSION})
        logger.info("demo sample report seeded (v%s)", DEMO_VERSION)
    except Exception:
        logger.exception("demo report seed failed (non-fatal)")


async def main():
    from motor.motor_asyncio import AsyncIOMotorClient
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]
    await db.reports.delete_many({"id": DEMO_ID})
    await ensure_demo_report(db)
    print(f"Seeded demo report: {DEMO_ID} (v{DEMO_VERSION})")


if __name__ == "__main__":
    asyncio.run(main())
