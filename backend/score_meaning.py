"""score_meaning.py — deterministic 'numbers become discovery' layer.
Curated knowledge (content/skill_knowledge.json) mapped onto REAL analysis data.
Video evidence is linked ONLY when the moment is identity-verified (a user tap
anchor or an independent identity-checked frame). No estimates, no invention."""

from __future__ import annotations

import json
from pathlib import Path

_KB = json.loads((Path(__file__).resolve().parent / "content" / "skill_knowledge.json").read_text())

_NEXT_BANDS = [(5.5, "Club"), (7.0, "Top Club"), (8.0, "Academy"), (9.0, "Elite")]
_TIER_OUT_OF_10 = {"elite_academy": 9, "pro_academy": 8, "strong_club": 7, "standard_club": 5}


def _ts_sec(ts):
    try:
        m, s = str(ts).strip().split(":")
        return int(m) * 60 + int(s)
    except Exception:
        return None


def _band_key(score: float) -> str:
    b = _KB.get("bands") or {}
    if score <= float(b.get("low_max", 6.4)):
        return "low"
    if score <= float(b.get("mid_max", 7.9)):
        return "mid"
    return "high"


def _fmt(text, name, age):
    return str(text).replace("{name}", name).replace("{age}", str(age) if age else "this age")


def _verified_seconds(doc: dict) -> list:
    """Seconds where the tapped player's identity is 100% certain."""
    out = []
    for a in doc.get("anchors") or []:
        t = a.get("t") if isinstance(a, dict) else None
        if isinstance(t, (int, float)):
            out.append(("anchor", float(t)))
    for cmt in ((doc.get("full_report") or {}).get("video_comments") or []):
        if isinstance(cmt, dict) and cmt.get("identity_verified") is True:
            s = _ts_sec(cmt.get("timestamp"))
            if s is not None:
                out.append(("identity", float(s)))
    return out


def _is_verified(sec: float, vsecs: list) -> bool:
    return any(abs(sec - t) <= (4 if kind == "anchor" else 5) for kind, t in vsecs)


def _observed(full: dict) -> list:
    out = []
    for cat in ("technical", "tactical", "physical", "mentality"):
        sec = (full or {}).get(cat) or {}
        if not isinstance(sec, dict):
            continue
        for k, sk in sec.items():
            if not isinstance(sk, dict) or sk.get("cannot_evaluate"):
                continue
            s = sk.get("score")
            if isinstance(s, (int, float)):
                out.append((k, cat, float(s), sk))
    return out


def _better_than(score: float, tier: str):
    if tier in _TIER_OUT_OF_10:
        return _TIER_OUT_OF_10[tier]
    if score >= 9:
        return 9
    if score >= 8:
        return 8
    if score >= 7:
        return 7
    if score >= 5.5:
        return 6
    return 5


def _gap_to_next(score: float):
    for th, label in _NEXT_BANDS:
        if score < th:
            return round(th - score, 1), label
    return None, None


def _pick_evidence(evidence: list, vsecs: list):
    ev = None
    for e in evidence or []:
        ts = (e or {}).get("timestamp") if isinstance(e, dict) else None
        s = _ts_sec(ts)
        if s is None:
            continue
        verified = _is_verified(s, vsecs)
        if ev is None or (verified and not ev["verified"]):
            ev = {"timestamp": str(ts), "verified": verified}
        if ev["verified"]:
            break
    return ev


def _discovery(obs_map: dict, posdata: dict, kb_skills: dict, first: str):
    for rule in posdata.get("alt") or []:
        strong = rule.get("strong") or []
        weak = rule.get("weak") or []
        if not strong:
            continue
        ok = all(
            k in obs_map and obs_map[k][0] >= 7.5
            and str(obs_map[k][1].get("confidence") or "").lower() in ("", "high", "medium")
            for k in strong
        )
        if ok and weak:
            ok = all(k in obs_map and obs_map[k][0] <= 6.4 for k in weak)
        if ok:
            based = [{
                "key": k,
                "label": (kb_skills.get(k) or {}).get("label", k.replace("_", " ").title()),
                "score": round(obs_map[k][0], 1),
            } for k in strong]
            return {
                "suggest": rule.get("suggest"),
                "why": rule.get("why"),
                "based_on": based,
                "note": ("An idea worth exploring in training — not a verdict, and never a "
                         f"replacement for where {first} loves to play. The best careers stay curious."),
            }
    return None


def build_score_meaning(doc: dict, progression: dict | None = None) -> dict | None:
    full = doc.get("full_report") or {}
    pdet = doc.get("player_details") or {}
    obs = _observed(full)
    if not obs:
        return None
    first = str(pdet.get("player_name") or "Your player").split()[0]
    age = pdet.get("age")
    vsecs = _verified_seconds(doc)

    deltas = {}
    if isinstance(progression, dict):
        for e in (progression.get("improvements") or []) + (progression.get("watch") or []):
            if isinstance(e, dict) and e.get("key"):
                deltas[e["key"]] = e.get("delta")

    pos = pdet.get("position")
    posdata = (_KB.get("positions") or {}).get(pos) or {}
    weighs = {w.get("skill"): w.get("why") for w in posdata.get("weighs") or [] if isinstance(w, dict)}
    kb_skills = _KB.get("skills") or {}

    skills = []
    obs_map = {}
    for key, cat, score, sk in obs:
        obs_map[key] = (score, sk)
        kb = kb_skills.get(key)
        if not kb:
            continue
        gap, next_band = _gap_to_next(score)
        tier = str(sk.get("tier_for_age") or "").lower()
        skills.append({
            "key": key,
            "label": kb.get("label", key.replace("_", " ").title()),
            "category": cat,
            "score": round(score, 1),
            "lines": [_fmt(t, first, age) for t in (kb.get("translate") or {}).get(_band_key(score), [])][:2],
            "looks_for": kb.get("looks_for"),
            "scale": kb.get("scale"),
            "next_level": kb.get("next_level"),
            "evidence": _pick_evidence(sk.get("evidence"), vsecs),
            "position_why": weighs.get(key),
            "angles": {
                "better_than": _better_than(score, tier),
                "delta": deltas.get(key),
                "gap_to_next": gap,
                "next_band": next_band,
            },
        })
    if not skills:
        return None
    skills.sort(key=lambda s: (-s["score"], s["key"]))
    return {
        "position": pos,
        "position_line": posdata.get("line"),
        "skills": skills,
        "discovery": _discovery(obs_map, posdata, kb_skills, first),
    }


def build_score_meaning_teaser(doc: dict) -> dict:
    """Free-preview shape: exactly ONE fully unlocked score story (real data),
    the rest as label-only locked rows. Never leaks locked scores."""
    sm = build_score_meaning(doc)
    if not sm or not sm.get("skills"):
        labels = [v.get("label") for v in (_KB.get("skills") or {}).values() if v.get("label")]
        return {"unlocked": None, "locked_labels": labels[:10],
                "locked_count": len(labels), "has_discovery": False}
    sk = sm["skills"]
    unlocked = next((s for s in sk if (s.get("evidence") or {}).get("verified")), sk[0])
    bonus = None
    if doc.get("bonus_story_unlocked"):
        bonus = next((s for s in sk if s["key"] != unlocked["key"]), None)
    taken = {unlocked["key"]} | ({bonus["key"]} if bonus else set())
    locked = [s["label"] for s in sk if s["key"] not in taken]
    return {
        "unlocked": unlocked,
        "bonus": bonus,
        "locked_labels": locked[:10],
        "locked_count": len(locked),
        "has_discovery": bool(sm.get("discovery")),
    }
