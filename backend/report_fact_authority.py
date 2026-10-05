"""Bind published match claims and assessment evidence to canonical events.

The report model describes/grades evidence; it cannot create a second match
history. Raw model responses remain in the audit collection. Unknown coverage
is never converted into a claim that the player scored zero.
"""
import re
import math
from copy import deepcopy

VERSION = 1
NEUTRAL = "The verified evidence is insufficient to assess this claim."
_GOAL = re.compile(r"\b(?:goals?|scor(?:es|ed|ing)|finishing|finisher|goal[- ]scorer|find(?:s|ing)? the (?:net|back of the net)|clinical)\b|\bscore\b(?!\s+(?:of|is|was|:))", re.I)
_ASSIST = re.compile(r"\bassist(?:s|ed)?\b", re.I)
_SAVE = re.compile(r"\b(?:save[sd]?|saved|forces? a save)\b", re.I)
_TIMESTAMP = re.compile(r"\b(\d{1,2}):(\d{2})\b")
_CATEGORIES = ("technical", "tactical", "physical", "mentality")
_ADVICE = {"training_plan", "next_match_missions", "development_roadmap",
           "development_priorities_detailed", "parent_tips", "benchmarks"}


def _skill_supports(name, events):
    if str(name).lower() in {"shooting", "finishing"}:
        return any(e.get("canonical_event_type") in {"SHOT", "GOAL"} for e in events)
    return True


def _ms(text):
    match = _TIMESTAMP.search(str(text or ""))
    return (int(match[1]) * 60 + int(match[2])) * 1000 if match else None


def _matching(events, row):
    event_id = row.get("event_id")
    if event_id:
        return [e for e in events if e.get("event_id") == event_id]
    ms = row.get("evidence_time_ms")
    if not isinstance(ms, (int, float)):
        ms = _ms(row.get("timestamp"))
    if ms is None or not math.isfinite(ms):
        return []
    matches = []
    for e in events:
        start = e.get("start_ms", e.get("canonical_ms"))
        end = e.get("end_ms", e.get("canonical_ms"))
        if (isinstance(start, (int, float)) and isinstance(end, (int, float))
                and math.isfinite(start) and math.isfinite(end)
                and start - 1000 <= ms <= end + 1000):
            matches.append(e)
    return matches


def _supports(text, events):
    if _ASSIST.search(text):
        return any(e.get("canonical_event_type") == "ASSIST" and e.get("causal_verified") is True for e in events)
    if _SAVE.search(text):
        return any(e.get("canonical_outcome") == "SAVED" for e in events)
    if _GOAL.search(text):
        # Finishing assessments can use verified shots; an actual goal claim
        # requires the verified scoring outcome, never a model story.
        kinds = {e.get("canonical_event_type") for e in events}
        if re.search(r"\b(?:finishing|finisher|clinical)\b", text, re.I) and not re.search(r"\b(?:goals?|scor\w*|net)\b", text, re.I):
            return bool(kinds & {"SHOT", "GOAL"})
        return any(e.get("canonical_event_type") == "GOAL" and e.get("causal_verified") is True for e in events)
    return True


def apply(full, canonical):
    result = deepcopy(full)
    events = [e for e in (canonical or {}).get("events") or []
              if e.get("actor_resolution", {}).get("proof_eligible") is True
              or e.get("proof", {}).get("proof_eligible") is True
              or e.get("proof_eligible") is True]
    # Published canonical events are already resolver-qualified. Older event
    # schemas record the actor proof as VERIFIED without its repeated boolean.
    events.extend(e for e in (canonical or {}).get("events") or [] if e not in events
                  and e.get("actor_resolution", {}).get("status") == "VERIFIED")
    removed, unbound, invalid_skills = [], 0, []

    def clean_text(text, path, allowed=events):
        parts = re.split(r"(?<=[.!?])\s+", text)
        keep = []
        for sentence in parts:
            timed = _ms(sentence)
            relevant = (_matching(allowed, {"timestamp": sentence}) if timed is not None else allowed)
            if not _supports(sentence, relevant):
                removed.append(path)
            else:
                keep.append(sentence)
        return " ".join(keep) if keep else NEUTRAL

    def walk(value, path):
        if isinstance(value, dict):
            for k, v in list(value.items()):
                if k in _ADVICE or k in {"action_timeline", "event_discovery", "verified_stats", "match_stats",
                                         "analysis_authority", "report_fact_authority", "evidence_authority_version"}:
                    continue
                if k == "evidence" and isinstance(v, list):
                    continue  # evidence is checked below, including identity
                value[k] = walk(v, f"{path}.{k}")
            return value
        if isinstance(value, list):
            return [walk(v, f"{path}[{i}]") for i, v in enumerate(value)]
        if isinstance(value, str):
            return clean_text(value, path)
        return value

    for category in _CATEGORIES:
        for name, skill in (result.get(category) or {}).items():
            if not isinstance(skill, dict) or not isinstance(skill.get("evidence"), list):
                continue
            supported = []
            for row in skill["evidence"]:
                if not isinstance(row, dict):
                    continue
                matches = _matching(events, row)
                if matches and _skill_supports(name, matches) and _supports(str(row.get("what") or ""), matches):
                    qualified = deepcopy(row)
                    qualified["canonical_event_ids"] = [e["event_id"] for e in matches if e.get("event_id")]
                    qualified["identity_verified"] = True
                    supported.append(qualified)
                else:
                    unbound += 1
            skill["evidence"] = supported
            skill["observations_used"] = len(supported)
            if not supported:
                invalid_skills.append(f"{category}.{name}")
                skill.update(score=None, cannot_evaluate=True, confidence="Low",
                             confidence_reason=NEUTRAL, verdict=NEUTRAL, why_this_score=NEUTRAL,
                             notes=NEUTRAL, tier_for_age=None)
    comments = []
    for c in result.get("video_comments") or []:
        if not isinstance(c, dict):
            continue
        if _supports(str(c.get("comment") or ""), _matching(events, c)):
            comments.append(c)
        else:
            removed.append("video_comments")
    result["video_comments"] = comments
    result = walk(result, "full_report")
    if invalid_skills:
        # Do not invent a replacement grade by averaging a few remaining skills.
        # The model's aggregate was calculated from a different evidence set.
        for category in _CATEGORIES:
            if any(path.startswith(category + ".") for path in invalid_skills):
                result.setdefault("scores", {})[category] = None
                result.setdefault("scores_confidence", {})[category] = "Low"
        result.setdefault("scores", {})["overall_development"] = None
        result.setdefault("scores_confidence", {})["overall_development"] = "Low"
        result["overall_benchmark"] = {"tier": None, "tier_label": "Insufficient verified evidence",
                                       "percentile": None, "evidence_status": "PARTIAL"}
    result["report_fact_authority"] = {
        "version": VERSION, "authority": "CANONICAL_EVENTS",
        "status": "REVIEW_REQUIRED" if invalid_skills or removed else "CONSISTENT",
        "unsupported_claim_paths": sorted(set(removed)),
        "unbound_skill_observations": unbound, "unrated_skills": invalid_skills,
        "verified_event_ids": [e["event_id"] for e in events if e.get("event_id")],
    }
    if invalid_skills or removed:
        result["evidence_quality_note"] = (
            "This report contains partial verified evidence. Unconfirmed scoring claims "
            "and assessments without a verified player/action link have been withheld. "
            "Missing events do not establish zero goals or assists.")
    return result


def prompt_block(canonical):
    import json
    facts = [{k: e.get(k) for k in ("event_id", "canonical_ms", "start_ms", "end_ms",
                                    "canonical_action_type", "canonical_event_type", "canonical_outcome", "causal_verified")}
             for e in (canonical or {}).get("events") or []]
    return ("\nFINAL MATCH FACT AUTHORITY: The following verified events are the sole "
            "source of match actions, goals, assists and their evidence timestamps. "
            "Do not create additional match outcomes from this video. Missing events mean "
            "incomplete evidence, never proof of zero. Every assessment evidence row must "
            "reference a relevant event_id. Set score=null and cannot_evaluate=true when "
            "its supporting action is unverified. Apply this to parent prose, summaries, "
            "video comments, shooting/weak-foot grades and benchmarks as well.\n"
            + json.dumps(facts, separators=(",", ":")))
