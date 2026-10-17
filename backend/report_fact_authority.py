"""Bind published match claims and assessment evidence to canonical events.

The report model describes/grades evidence; it cannot create a second match
history. Raw model responses remain in the audit collection. Unknown coverage
is never converted into a claim that the player scored zero.
"""
import re
import math
from copy import deepcopy

VERSION = 2
NEUTRAL = "The verified evidence is insufficient to assess this claim."
MISSING_ACTIONS = "The video evidence is incomplete. Missing detections do not establish a weakness in the player's shooting or scoring."
QUALITY_NOTE = (
    "This report contains partial verified evidence. Unconfirmed scoring claims "
    "and assessments without a verified player/action link have been withheld. "
    "Missing events do not establish zero shots, goals or assists, or a player weakness.")
_GOAL = re.compile(r"\b(?:goals?|scor(?:es|ed|ing)|finishing|finisher|goal[- ]scorer|find(?:s|ing)? the (?:net|back of the net)|clinical)\b|\bscore\b(?!\s+(?:of|is|was|:))", re.I)
_ASSIST = re.compile(r"\bassist(?:s|ed)?\b", re.I)
_SAVE = re.compile(r"\b(?:save[sd]?|saved|forces? a save)\b", re.I)
_COUNT_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
                "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}
_SCORING_COUNT = re.compile(
    r"\b(?P<count>\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s+"
    r"(?:(?:well[- ]taken|excellent|superb|fine|clinical|decisive|powerful|impressive)\s+){0,2}"
    r"(?P<kind>goals?|assists?)\b", re.I)
_TIMESTAMP = re.compile(r"\b(\d{1,2}):(\d{2})\b")
_CATEGORIES = ("technical", "tactical", "physical", "mentality")
_ADVICE = {"training_plan", "next_match_missions", "development_roadmap",
           "development_priorities_detailed", "parent_tips", "benchmarks"}
_SCORING_WORDS = r"(?:shots?|shooting|goals?|assists?|finishing|skud|afslutninger|m\u00e5l)"
_ABSENCE = re.compile(
    rf"\b(?:no|zero|0|without|lacks?|lacking|ingen|nul)\s+(?:any\s+)?(?:observed\s+|verified\s+)?{_SCORING_WORDS}\b"
    rf"|\b{_SCORING_WORDS}\b(?:\s+\w+){{0,4}}\s+(?:not|never|ikke)\s+(?:observed|seen|shown|attempted|recorded|observeret|set)\b"
    rf"|\b(?:did|does|has|have)\s+not\s+(?:attempt(?:ed)?|take(?:n)?|record(?:ed)?|produce(?:d)?)\s+(?:any\s+|a\s+)?{_SCORING_WORDS}\b", re.I)
_ABSENCE_AS_WEAKNESS = re.compile(
    r"\b(?:weak(?:ness)?|poor|underdeveloped|not (?:yet )?developed|lacking|needs? (?:development|improvement)|svag(?:hed)?|ikke udviklet)\b", re.I)


def assessment_prompt(template, canonical, player_details, content=None):
    """Retain the report schema/rubric, removing the second perception task."""
    import json
    schema_start = template.index("Produce a JSON object EXACTLY in this format:")
    schema_end = template.index("\nRULES FOR TOP-LEVEL", schema_start)
    schema = template[schema_start:schema_end].replace("THE CIRCLED PLAYER", "the identified player")
    rubric_start = template.index("🎯 BENCHMARK CALIBRATION")
    rubric_end = template.index("🎯 PLAYER DETAILS", rubric_start)
    rubric = template[rubric_start:rubric_end]
    facts = [{k: deepcopy(e.get(k)) for k in ("event_id", "canonical_ms", "start_ms", "end_ms",
              "canonical_event_type", "canonical_action_type", "canonical_outcome", "causal_verified",
              "actor_local_track_id", "foot", "pressure", "details", "causal_chain")}
             for e in (canonical or {}).get("events") or [] if (e.get("proof") or {}).get("proof_eligible") is True
             and e.get("global_target_id") == "GLOBAL_TARGET"]
    return (
        "Write the full development report from this resolved observation packet. No video or images are attached. "
        "Player identity and action roles have already been resolved: do not re-identify the player or discover actions. "
        "Use only these events for factual claims, including who passed, who shot and what the outcome was. "
        "A teammate's finish is not the target's shot. Missing observations do not establish zero actions or poor ability. "
        "Assess only qualities supported by the recorded action details; do not infer speed, scanning, balance or mentality "
        "merely from an event label. Leave an unsupported skill unrated. Use plain football coaching language. "
        "Every skill evidence row needs event_id, timestamp and what. Use the source timestamp, never clip playback time. "
        "The application supplies the canonical action_timeline, so return action_timeline=[]. "
        "Each sub-skill object uses score (1-10 or null), notes, confidence, confidence_reason, observations_used, "
        "evidence, cannot_evaluate, evaluable_reason, why_this_score, tier_for_age, benchmarks and verdict. "
        "When evidence is absent use score=null, cannot_evaluate=true, evidence=[] and an honest reason. "
        "Category scores average only observable skills and stay null when most skills are unobserved. "
        "Do not invent percentile measurements or physical attributes. Personal advice must follow the recorded evidence. "
        "Return a single valid JSON object.\nPlayer details: " + json.dumps(player_details or {}, ensure_ascii=False)
        + "\nVideo content metadata: " + json.dumps(content or {}, ensure_ascii=False)
        + "\nResolved observations: " + json.dumps(facts, ensure_ascii=False, separators=(",", ":"))
        + "\n" + rubric + "\n" + schema + prompt_block(canonical))


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
        # A pass ends before the receiver finishes; the goalkeeper intervenes
        # after the shooter's action. Those already resolved outcome times
        # belong to this event, rather than requiring another matching action.
        if e.get("causal_verified") is True:
            chain = e.get("causal_chain") or {}
            times = [chain.get(k) for k in ("target_contact_ms", "receiver_ms", "teammate_shot_ms", "goal_outcome_ms")]
            times.extend([start, end, (e.get("proof") or {}).get("outcome_ms")])
            times = [t for t in times if isinstance(t, (int, float)) and not isinstance(t, bool) and math.isfinite(t)]
            if times:
                start, end = min(times), max(times)
        if (isinstance(start, (int, float)) and isinstance(end, (int, float))
                and math.isfinite(start) and math.isfinite(end)
                and start - 1000 <= ms <= end + 1000):
            matches.append(e)
    return matches


def _supports(text, events):
    if text in {NEUTRAL, MISSING_ACTIONS, QUALITY_NOTE}:
        return True
    for claim in _SCORING_COUNT.finditer(text):
        count_text = claim["count"].lower()
        count = int(count_text) if count_text.isdigit() else _COUNT_WORDS[count_text]
        kind = "GOAL" if claim["kind"].lower().startswith("goal") else "ASSIST"
        if count > sum(e.get("canonical_event_type") == kind and e.get("causal_verified") is True
                       for e in events):
            return False
    # A supported clause cannot authorize the other outcomes in the same
    # sentence. Each mentioned outcome needs its own canonical evidence.
    if _ASSIST.search(text) and not any(
            e.get("canonical_event_type") == "ASSIST" and e.get("causal_verified") is True
            for e in events):
        return False
    if _SAVE.search(text) and not any(e.get("canonical_outcome") == "SAVED" for e in events):
        return False
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
    previous = result.get("report_fact_authority") or {}
    removed = list(previous.get("unsupported_claim_paths") or []) if previous.get("authority") == "CANONICAL_EVENTS" else []
    unbound, invalid_skills = 0, []
    scoring_complete = (result.get("verified_stats") or {}).get("goals_assists_available") is True

    def absence_text(text, path):
        if not _ABSENCE.search(text):
            return None
        # Even exhaustive zero attempts cannot demonstrate undeveloped skill.
        # Partial detection cannot demonstrate zero attempts in the first place.
        if not scoring_complete or _ABSENCE_AS_WEAKNESS.search(text):
            removed.append(path)
            return MISSING_ACTIONS if not scoring_complete else NEUTRAL
        return None

    def clean_text(text, path, allowed=events):
        if text in {NEUTRAL, MISSING_ACTIONS, QUALITY_NOTE}:
            return text
        absent = absence_text(text, path)
        if absent is not None:
            return absent
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

    def walk(value, path, advice=False):
        if isinstance(value, dict):
            for k, v in list(value.items()):
                if k in {"action_timeline", "event_discovery", "verified_stats", "match_stats",
                                         "analysis_authority", "report_fact_authority", "evidence_authority_version"}:
                    continue
                if k == "evidence" and isinstance(v, list) and not advice:
                    continue  # evidence is checked below, including identity
                value[k] = walk(v, f"{path}.{k}", advice=advice or k in _ADVICE)
            return value
        if isinstance(value, list):
            return [walk(v, f"{path}[{i}]", advice=advice) for i, v in enumerate(value)]
        if isinstance(value, str):
            if advice:
                # Generic exercises remain useful; evidence claims embedded in
                # advice must not turn a detector failure into a player deficit.
                absent = absence_text(value, path)
                return value if absent is None else absent
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
                if len(matches) == 1 and _skill_supports(name, matches) and _supports(str(row.get("what") or ""), matches):
                    qualified = deepcopy(row)
                    qualified["canonical_event_ids"] = [e["event_id"] for e in matches if e.get("event_id")]
                    if matches[0].get("event_id"):
                        qualified["event_id"] = matches[0]["event_id"]
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
        result["evidence_quality_note"] = QUALITY_NOTE
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
