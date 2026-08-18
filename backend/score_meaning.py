"""score_meaning.py — deterministic 'numbers become discovery' layer.
Curated knowledge (content/skill_knowledge.json) mapped onto REAL analysis data.
Video evidence is linked ONLY when the moment is identity-verified (a user tap
anchor or an independent identity-checked frame). No estimates, no invention."""

from __future__ import annotations

import json
import os
from pathlib import Path

_KB = json.loads((Path(__file__).resolve().parent / "content" / "skill_knowledge.json").read_text())

_EVIDENCE_SOFT_GATE = os.environ.get("CV_EVIDENCE_SOFT_GATE", "1") == "1"
_EVIDENCE_HARD_GATE = os.environ.get("CV_EVIDENCE_HARD_GATE", "1") == "1"


def _risky_seconds(doc: dict) -> list:
    """Switch-risk moments from the CV shadow engine (P7 soft gate): evidence
    picking PREFERS other verified moments near these timestamps. It never
    drops evidence and never changes Analysis A/B — ordering preference only."""
    if not _EVIDENCE_SOFT_GATE:
        return []
    pv = ((doc.get("cv_shadow") or {}).get("prod_verify")) or {}
    out = []
    for x in pv.get("switch_ts") or []:
        t = x.get("t") if isinstance(x, dict) else x
        if isinstance(t, (int, float)):
            out.append(float(t))
    # track-end protection: empty-box windows (track box on nobody) count too
    for w in pv.get("empty_windows") or []:
        try:
            s = float(w[0])
            while s <= float(w[1]) + 0.01:
                out.append(s)
                s += 1.0
        except Exception:
            pass
    return out

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


def _pick_evidence(evidence: list, vsecs: list, used: list, risky: list | None = None):
    """Pick a proof moment from THIS skill's own model-cited evidence, preferring
    moments not already shown on another card (±3s) — proofs spread across the
    match instead of repeating one clip. Never invents timestamps.
    P7 soft gate: moments within ±1.5s of a shadow switch-risk flag are only
    deprioritized — picked last, never dropped."""
    cands = []
    for e in evidence or []:
        ts = (e or {}).get("timestamp") if isinstance(e, dict) else None
        s = _ts_sec(ts)
        if s is None:
            continue
        cands.append({"timestamp": str(ts), "sec": s, "verified": _is_verified(s, vsecs),
                      "evidence_id": e.get("evidence_id"), "event_id": e.get("event_id")})
    if not cands:
        return None
    def fresh(c):
        return all(abs(c["sec"] - u) > 3.0 for u in used)
    def exact(c):
        return sum(1 for u in used if abs(c["sec"] - u) < 0.5)
    def clash(c):
        return sum(1 for u in used if abs(c["sec"] - u) <= 3.0)
    def risk(c):
        return any(abs(c["sec"] - r) <= 1.5 for r in (risky or []))
    # PHASE 17 HARD GATE: identity-uncertain moments may NOT become report
    # evidence at all — "uncertain player + obvious action → reject". A card
    # with no safe cited moment shows no proof (temporarily missing proof is
    # acceptable; a confidently wrong proof is not).
    if _EVIDENCE_HARD_GATE and risky:
        safe = [c for c in cands if not risk(c)]
        if not safe:
            return None
        cands = safe
    pick = (next((c for c in cands if c["verified"] and fresh(c) and not risk(c)), None)
            or next((c for c in cands if c["verified"] and fresh(c)), None)
            or next((c for c in cands if fresh(c) and not risk(c)), None)
            or next((c for c in cands if fresh(c)), None)
            or sorted(cands, key=lambda c: (exact(c), clash(c), risk(c), not c["verified"]))[0])
    used.append(pick["sec"])
    out = {"timestamp": pick["timestamp"], "verified": pick["verified"]}
    # FIX 01 — preserve the authority IDs of the selected source evidence row
    # so frontend proof navigation joins by exact ID (selection policy unchanged).
    if pick.get("evidence_id"):
        out["evidence_id"] = pick["evidence_id"]
    if pick.get("event_id"):
        out["event_id"] = pick["event_id"]
    return out


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
            "evidence": None,
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
    # assign proof moments in display order so top cards get first pick and
    # each card prefers a moment the reader has not already seen
    used: list = []
    risky = _risky_seconds(doc)
    for s in skills:
        s["evidence"] = _pick_evidence((obs_map[s["key"]][1] or {}).get("evidence"), vsecs, used, risky)
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
