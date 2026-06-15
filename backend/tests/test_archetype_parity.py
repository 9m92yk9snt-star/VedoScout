"""
test_archetype_parity.py — ensures every archetype across every position
has the deep `academy_bio` field populated with all 5 age brackets,
so the report's "What [PRO] was doing at age N" panel + the Gemini
personalised narrative render for every position, not just AM.
"""

import json
from pathlib import Path

ARCHETYPES_PATH = Path(__file__).resolve().parent.parent / "data" / "archetypes.json"
REQUIRED_BRACKETS = {"8-10", "11-12", "13-14", "15-17", "18-21"}
POSITIONS = [
    "goalkeeper",
    "centre back",
    "full back",
    "defensive midfielder",
    "central midfielder",
    "attacking midfielder",
    "winger",
    "striker",
]


def _load():
    return json.loads(ARCHETYPES_PATH.read_text(encoding="utf-8"))


def test_all_positions_present():
    data = _load()
    for pos in POSITIONS:
        assert pos in data, f"Position missing in archetypes.json: {pos}"
        assert isinstance(data[pos], list) and data[pos], f"{pos} must be a non-empty list"


def test_every_archetype_has_academy_bio_with_all_brackets():
    """Full parity — every single archetype across all 8 positions must
    expose `academy_bio` with all 5 age brackets, each a non-empty string."""
    data = _load()
    missing = []
    incomplete = []
    for pos in POSITIONS:
        for a in data[pos]:
            bio = a.get("academy_bio")
            if not isinstance(bio, dict) or not bio:
                missing.append(f"{pos}::{a.get('id')}::{a.get('name')}")
                continue
            present = set(bio.keys())
            missing_keys = REQUIRED_BRACKETS - present
            if missing_keys:
                incomplete.append(f"{pos}::{a.get('id')}  missing brackets={sorted(missing_keys)}")
            for k, v in bio.items():
                assert isinstance(v, str) and v.strip(), (
                    f"{pos}::{a.get('id')}::{k} bracket must be a non-empty string"
                )
    assert not missing, f"Archetypes with no academy_bio: {missing}"
    assert not incomplete, f"Archetypes with incomplete brackets: {incomplete}"


def test_goalkeeper_has_career_brief_everywhere():
    """GK was the only position previously missing career_brief — full parity now required."""
    data = _load()
    no_brief = [a.get("id") for a in data["goalkeeper"] if not a.get("career_brief")]
    assert not no_brief, f"Goalkeepers without career_brief: {no_brief}"


def test_no_obvious_placeholder_content():
    """Reject TBD/lorem/etc. placeholders in academy_bio."""
    data = _load()
    banned = ("tbd", "todo", "lorem ipsum", "xxxx", "fill me", "placeholder")
    for pos in POSITIONS:
        for a in data[pos]:
            bio = a.get("academy_bio") or {}
            for bracket, text in bio.items():
                low = text.lower()
                for word in banned:
                    assert word not in low, (
                        f"{pos}::{a.get('id')}::{bracket} contains placeholder '{word}'"
                    )


def test_bracket_lookup_returns_string_for_typical_ages():
    """Spot-check: the same age-bracket function used by server.py must resolve
    real bios for ages spanning U7-U21."""
    data = _load()
    age_to_bracket = {7: "8-10", 9: "8-10", 11: "11-12", 13: "13-14", 16: "15-17", 19: "18-21"}
    for pos in POSITIONS:
        sample = data[pos][0]
        bio = sample["academy_bio"]
        for age, bracket in age_to_bracket.items():
            assert bracket in bio, f"{pos}::{sample['id']} missing bracket {bracket} for age {age}"
            assert bio[bracket], f"{pos}::{sample['id']}::{bracket} is empty"
