"""verified_stats.py — FIX 07 VERIFIED STATS & CLAIM RECONCILIATION.

Deterministic code only (ZERO LLM / verifier / network calls). Input is the
already cross-verified report body. The LLM may observe and describe football,
but FINAL STATISTICAL AUTHORITY lives here:

    cross-verified canonical events  →  verified_stats  →  match_stats
                                     →  claim reconciliation over report text

Nothing in this module decides identity, verifies events, or overrides the
FIX02 keep/drop authority. FIX01 event_id / event_start_ms are never rewritten.
"""

from __future__ import annotations

import re

from evidence_authority import ts_to_ms

VERIFIED_STATS_VERSION = 1

EVENT_TYPES = {"GOAL", "ASSIST", "SHOT", "KEY_PASS", "PASS", "CROSS", "DRIBBLE",
               "DUEL", "TACKLE", "INTERCEPTION", "RECOVERY", "FIRST_TOUCH", "RUN",
               "DEFENSIVE_ACTION", "OTHER", "UNCLASSIFIED"}
ACTION_TYPES = {"SHOT", "PASS", "CROSS", "DRIBBLE", "DUEL", "TACKLE", "INTERCEPTION",
                "RECOVERY", "FIRST_TOUCH", "RUN", "DEFENSIVE_ACTION", "OTHER", "UNKNOWN"}
RESULTS = {"SCORED", "TEAMMATE_SCORED", "TEAMMATE_SHOT", "SAVED", "BLOCKED",
           "OFF_TARGET", "NO_GOAL", "OUTCOME_NOT_VISIBLE", "COMPLETED", "INCOMPLETE",
           "SUCCESS", "FAILED", "WON", "LOST", "UNRESOLVED", "POSSESSION_WON",
           "POSSESSION_LOST", "UNKNOWN"}

_LEGACY_ACTION = {"shot": "SHOT", "finish": "SHOT", "pass": "PASS", "cross": "CROSS",
                  "dribble": "DRIBBLE", "duel": "DUEL", "defensive": "DEFENSIVE_ACTION",
                  "first_touch": "FIRST_TOUCH", "run": "RUN"}


def _enum(v, allowed, default):
    up = str(v or "").strip().upper()
    return up if up in allowed else default


def normalize_canonical(ev_type, act_type, result, visible):
    """Normalise + enforce the GOAL/ASSIST hard gates deterministically.
    A GOAL that is not (SHOT + SCORED + visible) is demoted; an ASSIST that is
    not (PASS/CROSS + TEAMMATE_SCORED + visible) is demoted. Never guesses up."""
    et = _enum(ev_type, EVENT_TYPES, "UNCLASSIFIED")
    at = _enum(act_type, ACTION_TYPES, "UNKNOWN")
    res = _enum(result, RESULTS, "UNKNOWN")
    vis = visible is True
    if et == "GOAL":
        if at == "UNKNOWN":
            at = "SHOT"
        if at != "SHOT":
            et = at if at in EVENT_TYPES else "UNCLASSIFIED"
        elif not (res == "SCORED" and vis):
            et = "SHOT"
            if res == "SCORED":  # scored claimed but outcome not seen
                res = "OUTCOME_NOT_VISIBLE"
    if et == "ASSIST" and not (at in ("PASS", "CROSS") and res == "TEAMMATE_SCORED" and vis):
        if res == "TEAMMATE_SCORED" and not vis:
            res = "OUTCOME_NOT_VISIBLE"
        if res == "TEAMMATE_SHOT" and vis and at in ("PASS", "CROSS"):
            et = "KEY_PASS"
        else:
            et = "CROSS" if at == "CROSS" else "PASS"
            if at not in ("PASS", "CROSS"):
                et = at if at in EVENT_TYPES else "UNCLASSIFIED"
    return et, at, res, vis


def attach_canonical(ev: dict, verdict: dict) -> None:
    """Copy the verifier's canonical classification onto a KEPT event after
    deterministic normalisation. Does not touch keep/drop authority."""
    et, at, res, vis = normalize_canonical(
        verdict.get("canonical_event_type"), verdict.get("canonical_action_type"),
        verdict.get("canonical_result"), verdict.get("outcome_visible"))
    ev["canonical_event_type"] = et
    ev["canonical_action_type"] = at
    ev["canonical_result"] = res
    ev["outcome_visible"] = vis


def _ts_secs(ts):
    ms = ts_to_ms(ts)
    return None if ms is None else int(round(ms / 1000.0))


def _mmss(secs: int) -> str:
    mm, ss = divmod(max(0, int(secs)), 60)
    return f"{mm:02d}:{ss:02d}"


def _event_action(e: dict) -> str:
    at = e.get("canonical_action_type")
    if at in ACTION_TYPES:
        return at
    return _LEGACY_ACTION.get(str(e.get("action_type") or "").lower(), "UNKNOWN")


def merge_discovered_scoring_events(full: dict, discovered: list) -> dict:
    """PART 4/5 — merge the verifier's full-video scoring scan with the
    surviving timeline. Only identity-CONFIRMED, outcome-visible GOAL/ASSIST
    discoveries are ADDED (before FIX01 assigns event_id). EXACT normalized
    timestamp + compatible canonical action dedup — no fuzzy matching.
    Returns the scoring-scan metadata (unresolved candidates included)."""
    scan = {"performed": True, "unresolved_goal_attempts": 0,
            "unresolved_assist_candidates": 0}
    timeline = [e for e in (full.get("action_timeline") or []) if isinstance(e, dict)]
    existing = set()
    for e in timeline:
        ts = _ts_secs(e.get("timestamp"))
        if ts is not None:
            existing.add((ts, _event_action(e)))
    for d in (discovered or []):
        if not isinstance(d, dict):
            continue
        if str(d.get("identity") or "").upper() != "CONFIRMED":
            continue  # FIX02 spirit: wrong/unseen player never enters
        et, at, res, vis = normalize_canonical(
            d.get("canonical_event_type"), d.get("canonical_action_type"),
            d.get("canonical_result"), d.get("outcome_visible"))
        if not vis:
            if at == "SHOT":
                scan["unresolved_goal_attempts"] += 1
            elif at in ("PASS", "CROSS"):
                scan["unresolved_assist_candidates"] += 1
            continue
        if et not in ("GOAL", "ASSIST"):
            continue  # the scan only ADDS verified goals/assists
        ts = _ts_secs(d.get("timestamp"))
        if ts is None or (ts, at) in existing:
            continue  # same scoring event already survives — never duplicate
        note = str(d.get("note") or "").strip()
        timeline.append({
            "timestamp": _mmss(ts),
            "action_type": at.lower(),
            "title": "Goal" if et == "GOAL" else "Assist",
            "description": note or ("Verified goal." if et == "GOAL" else "Verified assist."),
            "cross_verified": True,
            "canonical_event_type": et,
            "canonical_action_type": at,
            "canonical_result": res,
            "outcome_visible": True,
            "discovered_by_scoring_scan": True,
        })
        existing.add((ts, at))
    full["action_timeline"] = timeline
    return scan


_COUNT_KEYS = ("goals", "assists", "shots", "shots_on_target", "key_passes",
               "passes_attempted", "passes_completed", "crosses_attempted",
               "crosses_completed", "dribbles_attempted", "successful_dribbles",
               "duels_contested", "duels_won", "tackles_attempted", "tackles_won",
               "interceptions", "recoveries")


def build_verified_stats(full: dict, scan: dict | None = None) -> dict:
    """PART 7-10 — deterministic canonical counts over surviving cross-verified
    events. One event_id contributes at most once per statistic; malformed
    exact-time duplicates are suppressed; nothing is fuzzy-merged."""
    events = [e for e in (full.get("action_timeline") or [])
              if isinstance(e, dict) and e.get("cross_verified") is True]
    counted = {k: [] for k in _COUNT_KEYS}
    n = {k: 0 for k in _COUNT_KEYS}
    n["total_actions"] = 0
    n["defensive_actions"] = 0
    n["first_touches"] = 0
    n["runs"] = 0
    seen_ids: set = set()
    seen_sig: set = set()
    for i, e in enumerate(events):
        eid = e.get("event_id") or f"_idx{i}"
        if eid in seen_ids:
            continue  # V21 — duplicate event_id counts once
        seen_ids.add(eid)
        et = _enum(e.get("canonical_event_type"), EVENT_TYPES, "UNCLASSIFIED")
        at = _enum(e.get("canonical_action_type"), ACTION_TYPES, "UNKNOWN")
        res = _enum(e.get("canonical_result"), RESULTS, "UNKNOWN")
        vis = e.get("outcome_visible") is True
        ms = e.get("event_start_ms")
        if isinstance(ms, int):
            sig = (et, at, ms)
            if sig in seen_sig:
                continue  # V22 — malformed exact-time duplicate counts once
            seen_sig.add(sig)
        if et in ("UNCLASSIFIED", "OTHER") and at in ("UNKNOWN", "OTHER"):
            if et == "OTHER" or at == "OTHER":
                n["total_actions"] += 1  # a real (if generic) involvement
            continue  # no invented football stat from junk

        def _c(key):
            n[key] += 1
            counted[key].append(eid)

        n["total_actions"] += 1
        if et == "GOAL" and at == "SHOT" and res == "SCORED" and vis:
            _c("goals")
        if et == "ASSIST" and at in ("PASS", "CROSS") and res == "TEAMMATE_SCORED" and vis:
            _c("assists")
        if at == "SHOT":
            _c("shots")
            if res in ("SCORED", "SAVED"):
                _c("shots_on_target")
        if et == "ASSIST" or (et == "KEY_PASS" and res == "TEAMMATE_SHOT" and vis):
            _c("key_passes")
        if at == "PASS":
            _c("passes_attempted")
            if res == "COMPLETED" or et == "ASSIST" or (et == "KEY_PASS" and res == "TEAMMATE_SHOT"):
                _c("passes_completed")
        if at == "CROSS":
            _c("crosses_attempted")
            if res == "COMPLETED" or et == "ASSIST" or (et == "KEY_PASS" and res == "TEAMMATE_SHOT"):
                _c("crosses_completed")
        if at == "DRIBBLE":
            _c("dribbles_attempted")
            if res == "SUCCESS":
                _c("successful_dribbles")
        if at == "DUEL" and res in ("WON", "LOST"):
            _c("duels_contested")
            if res == "WON":
                _c("duels_won")
        if at == "TACKLE" and res in ("WON", "LOST"):
            _c("tackles_attempted")
            if res == "WON":
                _c("tackles_won")
        if at == "INTERCEPTION" and res in ("SUCCESS", "POSSESSION_WON"):
            _c("interceptions")
        if at == "RECOVERY" and res in ("SUCCESS", "POSSESSION_WON"):
            _c("recoveries")
        if at in ("TACKLE", "INTERCEPTION", "RECOVERY", "DEFENSIVE_ACTION"):
            n["defensive_actions"] += 1
        if at == "FIRST_TOUCH":
            n["first_touches"] += 1
        if at == "RUN":
            n["runs"] += 1

    pct = (round(n["passes_completed"] / n["passes_attempted"] * 100)
           if n["passes_attempted"] > 0 else None)
    scan = scan if isinstance(scan, dict) else {}
    vs = {
        "version": VERIFIED_STATS_VERSION,
        "source": "cross_verified_events",
        "available": True,
        "scoring_scan": {
            "performed": bool(scan.get("performed")),
            "verified_goals": n["goals"],
            "verified_assists": n["assists"],
            "unresolved_goal_attempts": int(scan.get("unresolved_goal_attempts") or 0),
            "unresolved_assist_candidates": int(scan.get("unresolved_assist_candidates") or 0),
        },
        "stats_completeness": {
            "goals_assists": "full_video_scoring_scan" if scan.get("performed")
            else "verified_timeline_events",
            "other_actions": "verified_timeline_events",
        },
        "total_actions": n["total_actions"],
        "pass_completion_pct": pct,
        "defensive_actions": n["defensive_actions"],
        "first_touches": n["first_touches"],
        "runs": n["runs"],
        "counted_event_ids": counted,
    }
    for k in _COUNT_KEYS:
        vs[k] = n[k]
    full["verified_stats"] = vs

    def _plural(cnt, word):
        return f"{cnt} {word}{'' if cnt == 1 else 's'}"

    full["verified_stat_line"] = " · ".join([
        _plural(n["goals"], "goal"), _plural(n["assists"], "assist"),
        _plural(n["shots"], "shot")])
    return vs


def rebuild_match_stats(full: dict) -> None:
    """PART 12 — match_stats is no longer model authority. Rebuilt from
    verified_stats; the model's event totals never survive. Fail closed when
    canonical stats are unavailable."""
    old = full.get("match_stats") if isinstance(full.get("match_stats"), dict) else {}
    minutes = old.get("minutes_analysed")
    vs = full.get("verified_stats")
    if not isinstance(vs, dict) or not vs.get("available"):
        full["match_stats"] = {"minutes_analysed": minutes,
                               "source": "verified_events_unavailable"}
        return
    full["match_stats"] = {
        "total_actions": vs["total_actions"],
        "goals": vs["goals"],
        "assists": vs["assists"],
        "shots": vs["shots"],
        "shots_on_target": vs["shots_on_target"],
        "key_passes": vs["key_passes"],
        "passes_attempted": vs["passes_attempted"],
        "passes_completed": vs["passes_completed"],
        "pass_completion_pct": vs["pass_completion_pct"],
        "crosses_attempted": vs["crosses_attempted"],
        "crosses_completed": vs["crosses_completed"],
        "dribbles_attempted": vs["dribbles_attempted"],
        "successful_dribbles": vs["successful_dribbles"],
        "duels_contested": vs["duels_contested"],
        "duels_won": f"{vs['duels_won']}/{vs['duels_contested']}",
        "tackles_attempted": vs["tackles_attempted"],
        "tackles_won": vs["tackles_won"],
        "interceptions": vs["interceptions"],
        "recoveries": vs["recoveries"],
        "defensive_actions": vs["defensive_actions"],
        "first_touches": vs["first_touches"],
        "runs": vs["runs"],
        "minutes_analysed": minutes,
        "source": "verified_events",
    }


# ------------------------------------------------------ claim reconciliation

_NUMS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
         "seven": 7, "eight": 8, "nine": 9, "ten": 10}
_NUM_RE = r"(\d+|one|two|three|four|five|six|seven|eight|nine|ten)"


def _num(tok) -> int | None:
    tok = str(tok).lower()
    if tok.isdigit():
        return int(tok)
    return _NUMS.get(tok)


_CREATOR_RE = re.compile(rf"\b{_NUM_RE}[-\s]goal\s+creator\b", re.I)
_GOAL_COUNT_RES = (
    re.compile(rf"\b{_NUM_RE}\s+goals?\b", re.I),
    re.compile(rf"\b{_NUM_RE}[-\s]goal\b", re.I),
    re.compile(rf"\bscored\s+{_NUM_RE}\b", re.I),
)
_GOAL_FIXED = ((re.compile(r"\bhat[\s-]?trick\b", re.I), 3),
               (re.compile(r"\bbrace\b", re.I), 2),
               (re.compile(r"\bscored\s+twice\b", re.I), 2))
_ASSIST_RES = (
    re.compile(rf"\b{_NUM_RE}\s+assists?\b", re.I),
    re.compile(rf"\bassisted\s+{_NUM_RE}\b", re.I),
)
_AGG_RE = re.compile(
    rf"\b{_NUM_RE}\s+(shots|key\s+passes|passes|crosses|dribbles|duels|tackles|"
    rf"interceptions|recoveries)\b", re.I)
_AGG_KEY = {"shots": "shots", "key passes": "key_passes", "passes": "passes_attempted",
            "crosses": "crosses_attempted", "dribbles": "dribbles_attempted",
            "duels": "duels_contested", "tackles": "tackles_attempted",
            "interceptions": "interceptions", "recoveries": "recoveries"}


def _sentence_supported(sent: str, vs: dict) -> bool:
    creator = _CREATOR_RE.search(sent)
    if creator:
        c = _num(creator.group(1))
        if c is not None and c != vs["assists"]:
            return False
    else:
        for rx in _GOAL_COUNT_RES:
            m = rx.search(sent)
            if m:
                c = _num(m.group(1))
                if c is not None and c != vs["goals"]:
                    return False
    for rx, c in _GOAL_FIXED:
        if rx.search(sent) and vs["goals"] != c:
            return False
    for rx in _ASSIST_RES:
        m = rx.search(sent)
        if m:
            c = _num(m.group(1))
            if c is not None and c != vs["assists"]:
                return False
    for m in _AGG_RE.finditer(sent):
        c = _num(m.group(1))
        key = _AGG_KEY.get(re.sub(r"\s+", " ", m.group(2).lower()))
        if c is not None and key and c != vs[key]:
            return False
    return True


def _canonical_line(vs: dict) -> str:
    g, a = vs["goals"], vs["assists"]
    return (f"Verified in this footage: {g} goal{'' if g == 1 else 's'} "
            f"and {a} assist{'' if a == 1 else 's'}.")


def _reconcile_str(text, vs, fallback=None):
    if not isinstance(text, str) or not text.strip():
        return text
    parts = re.split(r"(?<=[.!?])\s+", text)
    kept = [s for s in parts if _sentence_supported(s, vs)]
    if len(kept) == len(parts):
        return text
    out = " ".join(kept).strip()
    return out if out else (fallback if fallback is not None else out)


def _walk(node, vs, fallback=None):
    if isinstance(node, str):
        return _reconcile_str(node, vs, fallback)
    if isinstance(node, list):
        out = [_walk(x, vs, fallback) for x in node]
        return [x for x in out if not (isinstance(x, str) and not x.strip())]
    if isinstance(node, dict):
        return {k: _walk(v, vs, fallback) for k, v in node.items()}
    return node


_GOAL_LANG = re.compile(
    r"\b(goals?|scores?|scored|scoring|finish(?:es|ed)?|puts?\s+it\s+in\s+the\s+net|"
    r"into\s+the\s+(?:net|goal)|back\s+of\s+the\s+net)\b", re.I)
_ASSIST_LANG = re.compile(r"\b(assists?|assisted|sets?\s+up\s+the\s+goal)\b", re.I)
_SAFE_TITLE = {"GOAL": "Goal", "ASSIST": "Assist", "SHOT": "Shot attempt",
               "KEY_PASS": "Key pass", "PASS": "Pass", "CROSS": "Cross",
               "DRIBBLE": "Dribble", "DUEL": "Duel", "TACKLE": "Tackle",
               "INTERCEPTION": "Interception", "RECOVERY": "Recovery",
               "FIRST_TOUCH": "First touch", "RUN": "Run",
               "DEFENSIVE_ACTION": "Defensive action", "OTHER": "Involvement",
               "UNCLASSIFIED": "Verified match involvement"}


def _scrub_lang(text: str, safe: str, *patterns) -> str:
    parts = re.split(r"(?<=[.!?])\s+", text)
    kept = [s for s in parts if not any(p.search(s) for p in patterns)]
    out = " ".join(kept).strip()
    return out if out else f"Verified {safe.lower()}."


def _reconcile_event_texts(full: dict) -> None:
    """PART 15/16 — event-bound text and exactly-bound video comments may not
    claim an outcome beyond the event's canonical classification."""
    events = [e for e in (full.get("action_timeline") or []) if isinstance(e, dict)]
    by_id = {}
    for e in events:
        et = _enum(e.get("canonical_event_type"), EVENT_TYPES, "UNCLASSIFIED")
        if e.get("event_id"):
            by_id[e["event_id"]] = et
        bad = []
        if et not in ("GOAL", "ASSIST"):
            bad.append(_GOAL_LANG)
        if et != "ASSIST":
            bad.append(_ASSIST_LANG)
        if not bad:
            continue
        safe = _SAFE_TITLE.get(et, "Verified match involvement")
        title = e.get("title")
        if isinstance(title, str) and any(p.search(title) for p in bad):
            e["title"] = safe
        desc = e.get("description")
        if isinstance(desc, str) and any(p.search(desc) for p in bad):
            e["description"] = _scrub_lang(desc, safe, *bad)
    for c in (full.get("video_comments") or []):
        if not isinstance(c, dict):
            continue
        et = by_id.get(c.get("event_id"))
        if et is None:
            continue  # only EXACTLY event-bound comments are event-gated
        bad = []
        if et not in ("GOAL", "ASSIST"):
            bad.append(_GOAL_LANG)
        if et != "ASSIST":
            bad.append(_ASSIST_LANG)
        txt = c.get("comment")
        if bad and isinstance(txt, str) and any(p.search(txt) for p in bad):
            c["comment"] = _scrub_lang(txt, _SAFE_TITLE.get(et, "involvement"), *bad)


def reconcile_verified_claims(full: dict) -> None:
    """PART 13/14/17 — explicit numeric football-stat claims in report prose,
    snapshot and cinematic sources must agree with verified_stats. Minimal
    deterministic intervention: the contradictory SENTENCE is removed; an
    emptied high-value field receives the canonical verified line."""
    vs = full.get("verified_stats")
    if not isinstance(vs, dict) or not vs.get("available"):
        return
    line = _canonical_line(vs)
    for key in ("executive_summary", "final_summary"):
        if isinstance(full.get(key), str):
            full[key] = _reconcile_str(full[key], vs, fallback=line)
    for key in ("scout_view", "parent_summary", "coach_notes", "parent_tips"):
        if key in full and full.get(key) is not None:
            full[key] = _walk(full[key], vs)
    snap = full.get("snapshot")
    if isinstance(snap, dict):
        for k, v in list(snap.items()):
            if isinstance(v, str):
                snap[k] = _reconcile_str(v, vs, fallback="Verified match involvement")
    sm = full.get("snapshot_moments")
    if isinstance(sm, list):  # cinematic intro source
        for m in sm:
            if isinstance(m, dict):
                for k in ("title", "desc"):
                    if isinstance(m.get(k), str):
                        m[k] = _reconcile_str(m[k], vs,
                                              fallback="Verified match involvement")
    _reconcile_event_texts(full)


def apply_verified_stats_authority(full: dict) -> dict:
    """FIX07 pipeline step (after FIX01 attach, before proof authority):
    build verified stats → rebuild match_stats → reconcile claims."""
    if not isinstance(full, dict):
        return full
    scan = full.pop("_scoring_scan", None)
    build_verified_stats(full, scan)
    rebuild_match_stats(full)
    reconcile_verified_claims(full)
    return full
