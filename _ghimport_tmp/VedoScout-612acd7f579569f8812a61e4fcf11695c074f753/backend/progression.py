"""progression.py — deterministic development-curve math across a player's
reports. Pure arithmetic on existing scores — no AI, no estimates."""

from __future__ import annotations

from datetime import datetime

CATS = [
    ("technical", "Technical"), ("tactical", "Tactical"), ("physical", "Physical"),
    ("mentality", "Mentality"), ("overall_development", "Overall"),
]

SKILL_LABELS = {
    "first_touch": "First Touch", "ball_control": "Ball Control", "dribbling": "Dribbling",
    "passing": "Passing", "shooting": "Shooting", "weak_foot": "Weak Foot", "one_v_one": "1v1 Attacking",
    "positioning": "Positioning", "off_ball_movement": "Off-Ball Movement", "scanning": "Scanning",
    "decision_making": "Decision Making", "timing_of_runs": "Timing of Runs",
    "game_understanding": "Game Understanding",
    "acceleration": "Acceleration", "speed": "Speed", "balance": "Balance", "agility": "Agility",
    "intensity": "Intensity", "body_control": "Body Control",
    "confidence": "Confidence", "work_rate": "Work Rate", "courage_in_duels": "Courage in Duels",
    "response_to_mistakes": "Response to Mistakes", "competitive_mindset": "Competitive Drive",
    "focus": "Focus",
}

FLAT_BAND = 0.3
IMPROVE_MIN = 0.5
WATCH_MIN = -0.5


def _parse_dt(iso):
    try:
        return datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    except Exception:
        return None


def _date_label(iso) -> str:
    d = _parse_dt(iso)
    return d.strftime("%d %b").upper() if d else ""


def _cat_score(full: dict, key: str):
    v = ((full or {}).get("scores") or {}).get(key)
    return round(float(v), 1) if isinstance(v, (int, float)) else None


def _observed_skills(full: dict) -> dict:
    out = {}
    for cat in ("technical", "tactical", "physical", "mentality"):
        sec = (full or {}).get(cat) or {}
        if not isinstance(sec, dict):
            continue
        for k, sk in sec.items():
            if not isinstance(sk, dict) or sk.get("cannot_evaluate"):
                continue
            s = sk.get("score")
            conf = str(sk.get("confidence") or "").lower()
            if isinstance(s, (int, float)) and conf in ("", "high", "medium"):
                out[k] = round(float(s), 1)
    return out


def build_progression(current: dict, history: list) -> dict | None:
    """history = this player's EARLIER reports (chronological), each a dict
    with full_report + created_at. Returns the progression payload or None."""
    if not history:
        return None
    prev = history[-1]
    cur_full = current.get("full_report") or {}
    prev_full = prev.get("full_report") or {}

    categories = []
    for key, label in CATS:
        a, b = _cat_score(prev_full, key), _cat_score(cur_full, key)
        if a is None or b is None:
            continue
        delta = round(b - a, 1)
        categories.append({
            "key": key, "label": label, "prev": a, "cur": b, "delta": delta,
            "dir": "up" if delta >= FLAT_BAND else ("down" if delta <= -FLAT_BAND else "flat"),
        })
    if not categories:
        return None

    ps, cs = _observed_skills(prev_full), _observed_skills(cur_full)
    common = sorted(set(ps) & set(cs))
    trained = set()
    for p in (prev_full.get("development_priorities_detailed") or []):
        if isinstance(p, dict) and p.get("name"):
            trained.add(str(p["name"]).strip().lower().replace("_", " "))
    deltas = []
    for k in common:
        d = round(cs[k] - ps[k], 1)
        label = SKILL_LABELS.get(k, k.replace("_", " ").title())
        deltas.append({
            "key": k, "label": label, "prev": ps[k], "cur": cs[k], "delta": d,
            "trained": label.lower() in trained or k.replace("_", " ") in trained,
        })
    improvements = sorted([d for d in deltas if d["delta"] >= IMPROVE_MIN], key=lambda x: -x["delta"])[:3]
    watch = sorted([d for d in deltas if d["delta"] <= WATCH_MIN], key=lambda x: x["delta"])[:2]

    series = []
    for docx in history + [current]:
        f = docx.get("full_report") or {}
        row = {"date": docx.get("created_at"), "label": _date_label(docx.get("created_at"))}
        any_val = False
        for key, _lbl in CATS:
            out_key = "overall" if key == "overall_development" else key
            v = _cat_score(f, key)
            row[out_key] = v
            any_val = any_val or v is not None
        if any_val:
            series.append(row)

    days = None
    a_dt, b_dt = _parse_dt(prev.get("created_at")), _parse_dt(current.get("created_at"))
    if a_dt and b_dt:
        days = max(0, (b_dt - a_dt).days)

    return {
        "analysis_number": len(history) + 1,
        "prev_date": prev.get("created_at"),
        "prev_date_label": _date_label(prev.get("created_at")),
        "days_since": days,
        "categories": categories,
        "improvements": improvements,
        "watch": watch,
        "compared_skills": len(common),
        "not_comparable": len((set(ps) | set(cs)) - (set(ps) & set(cs))),
        "series": series,
    }
