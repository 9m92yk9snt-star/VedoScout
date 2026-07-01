"""
Seeds ~18 fictional discoverable players into the ScoutMePlay database
so the /players-database search index looks lived-in from day one.

Each fake player gets:
  - A random name, birth_year, position, foot, country, club
  - A GDPR-safe simulated parental_consent=true
  - discoverable=true
  - A single fake paid report with a realistic overall score (65-92)
  - No avatar file — the initial-badge is displayed in the UI

Idempotent: reruns only add missing seed users (matched by fixed emails).

Run: python /app/backend/seed_fictional_players.py
"""
import asyncio
import os
import random
import uuid
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
from passlib.hash import bcrypt

load_dotenv()

MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]
CURRENT_YEAR = datetime.now(timezone.utc).year

FIRST_NAMES_MALE = [
    "Lukas", "Mikkel", "Noah", "Jonas", "Elias", "Oliver", "Emil", "Adam",
    "Kian", "Milo", "Malik", "Sebastian", "Ibrahim", "Yassin", "Rasmus",
    "Nikolai", "Sander", "Anton", "Jacob", "Marcus",
]
LAST_NAMES = [
    "Andersen", "Jensen", "Kristensen", "Larsen", "Nielsen", "Petersen",
    "Rasmussen", "Sørensen", "Christensen", "Møller", "Hansen", "Poulsen",
    "Johansen", "Olsen", "Thomsen", "Madsen", "Pedersen", "Jørgensen",
]
POSITIONS = ["GK", "CB", "FB", "DM", "CM", "CAM", "W", "ST"]
FEET = ["left", "right", "both"]
COUNTRIES = [
    "Denmark", "Denmark", "Denmark", "Sweden", "Norway", "Netherlands",
    "Germany", "Belgium", "England", "France", "Spain", "Portugal",
    "Croatia", "Serbia", "Poland",
]
CLUBS_BY_COUNTRY = {
    "Denmark": ["Brøndby IF", "FC København", "AGF", "OB", "AaB", "FC Midtjylland", "Silkeborg IF", "AB", "Lyngby BK", "HB Køge"],
    "Sweden": ["Malmö FF", "AIK", "Djurgården", "Hammarby", "IFK Göteborg"],
    "Norway": ["Rosenborg", "Molde FK", "Bodø/Glimt", "Vålerenga"],
    "Netherlands": ["Ajax", "PSV", "Feyenoord", "AZ Alkmaar", "FC Utrecht"],
    "Germany": ["Bayern München", "BVB", "RB Leipzig", "VfB Stuttgart", "Bayer 04 Leverkusen"],
    "Belgium": ["Anderlecht", "Genk", "Club Brugge", "Standard Liège"],
    "England": ["Chelsea Academy", "Arsenal Academy", "Man City Academy", "Southampton FC"],
    "France": ["OL Academy", "OM Youth", "Lille Youth", "PSG U16"],
    "Spain": ["FC Barcelona La Masia", "Real Madrid Cantera", "Athletic Bilbao", "Valencia CF"],
    "Portugal": ["SL Benfica", "FC Porto", "Sporting CP"],
    "Croatia": ["Dinamo Zagreb", "Hajduk Split"],
    "Serbia": ["Red Star Belgrade", "FK Partizan"],
    "Poland": ["Legia Warsaw", "Lech Poznań"],
}
BIOS = [
    "Left-footed playmaker with a knack for late runs. Loves to receive between the lines.",
    "Aggressive box-to-box engine — never stops running, wins duels, chips in with goals.",
    "Small-frame technician. Elite first touch, ambidextrous, reads the game two moves ahead.",
    "Physical target man who links play. Aerial dominance and hold-up under pressure.",
    "Two-footed defender who steps out with the ball. Composed in transition.",
    "Vertical winger — direct, fearless in 1v1, cuts inside to shoot.",
    "Modern number 10. Line-breaking passes, presses from the front, disciplined in the block.",
    "Ball-playing keeper. Comfortable under high press, sweeps aggressively behind the line.",
]


def _rand_email(first, last, idx):
    return f"demo.player.{first.lower()}.{last.lower()}.{idx}@scoutmeplay.local"


async def _seed_one_player(db, idx, *, discoverable=True, avatar=False):
    first = random.choice(FIRST_NAMES_MALE)
    last = random.choice(LAST_NAMES)
    full_name = f"{first} {last}"
    email = _rand_email(first, last, idx)

    existing = await db.users.find_one({"email": email}, {"_id": 0, "id": 1})
    if existing:
        return existing["id"], full_name, False

    # Age between 12 and 19 → born between 6 and 13 years ago from CURRENT_YEAR
    age = random.randint(12, 19)
    birth_year = CURRENT_YEAR - age
    country = random.choice(COUNTRIES)
    club = random.choice(CLUBS_BY_COUNTRY.get(country, ["Local FC"]))
    position = random.choice(POSITIONS)
    foot = random.choices(FEET, weights=[3, 6, 1])[0]  # right-foot dominant
    height_cm = random.randint(155, 190) if position != "GK" else random.randint(178, 195)
    weight_kg = round(height_cm * random.uniform(0.31, 0.42))
    bio = random.choice(BIOS)

    user_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    user_doc = {
        "id": user_id,
        "email": email,
        "full_name": full_name,
        "password_hash": bcrypt.hash("SeedPlayer2026!"),
        "role": "user",
        "created_at": now,
        "birth_year": birth_year,
        "discoverable": discoverable,
        "parent_consent": True,
        "discoverable_updated_at": now,
        "public_profile": {
            "position": position,
            "preferred_foot": foot,
            "height_cm": height_cm,
            "weight_kg": weight_kg,
            "country": country,
            "club": club,
            "bio": bio,
        },
        "is_seeded": True,  # flag so admin can filter/delete these later
    }
    await db.users.insert_one(user_doc)

    # Attach a fake paid report so the search index shows a highest_overall score.
    report_id = str(uuid.uuid4())
    overall = round(random.uniform(65, 92), 1)
    report_doc = {
        "id": report_id,
        "user_id": user_id,
        "user_email": email,
        "player_details": {
            "player_name": full_name,
            "age": age,
            "position": position,
            "preferred_foot": foot,
            "country": country,
            "club": club,
        },
        "preview": {
            "overall": overall,
            "technical": round(random.uniform(60, 95), 1),
            "tactical": round(random.uniform(55, 90), 1),
            "physical": round(random.uniform(60, 92), 1),
            "mindset": round(random.uniform(60, 95), 1),
            "summary": bio,
        },
        "is_paid": True,
        "manually_unlocked": True,
        "analysis_status": "complete",
        "created_at": (datetime.now(timezone.utc) - timedelta(days=random.randint(1, 90))).isoformat(),
        "is_seeded": True,
    }
    await db.reports.insert_one(report_doc)

    return user_id, full_name, True


async def main():
    random.seed(42)  # deterministic seed set — reruns produce the same players
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]

    target_count = 18
    created = 0
    skipped = 0
    for idx in range(target_count):
        _uid, name, was_created = await _seed_one_player(db, idx)
        if was_created:
            created += 1
            print(f"  + seeded {name}")
        else:
            skipped += 1
            print(f"  · exists  {name}")

    total_discoverable = await db.users.count_documents({"discoverable": True})
    print(f"\nDone — created={created}, skipped={skipped}, total discoverable in DB={total_discoverable}")
    client.close()


if __name__ == "__main__":
    asyncio.run(main())
