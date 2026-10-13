"""Explicit human goal approvals, separate from automatic physical authority.

The caller supplies approvals from its trusted review store, never model JSON.
This module neither authenticates reviewers nor grants automatic proof status.
"""
from copy import deepcopy
import re


def project(approvals, *, source_video_sha256, automatic_events=()):
    result, rejected, seen = [], [], set()
    valid_source = isinstance(source_video_sha256, str) and bool(
        re.fullmatch(r"[0-9a-f]{64}", source_video_sha256))
    for approval in approvals or ():
        if not isinstance(approval, dict):
            rejected.append({"reason": "INVALID_REVIEW"})
            continue
        identifier = approval.get("review_id")
        required = ("review_id", "reviewer", "reviewed_at", "scene_id", "actor_id", "statement")
        valid = (valid_source and approval.get("source_video_sha256") == source_video_sha256
                 and approval.get("decision") == "APPROVE_GOAL"
                 and approval.get("source") == "EXPLICIT_USER_REVIEW"
                 and all(isinstance(approval.get(k), str) and approval[k].strip() for k in required)
                 and type(approval.get("contact_ms")) is int and approval["contact_ms"] >= 0
                 and isinstance(approval.get("observations"), list)
                 and bool(approval["observations"])
                 and all(isinstance(o, str) and o.strip() for o in approval["observations"]))
        if not valid:
            rejected.append({"review_id": identifier, "reason": "INCOMPLETE_OR_FOREIGN_REVIEW"})
            continue
        key = (approval["scene_id"], approval["actor_id"], approval["contact_ms"])
        if key in seen:
            continue
        seen.add(key)
        automatic_match = any(
            isinstance(e, dict) and e.get("canonical_event_type") == "GOAL"
            and e.get("scene_id") == key[0] and e.get("global_target_id") == key[1]
            and e.get("canonical_ms") == key[2]
            and e.get("reconciliation_authority") == "FIX10B_PHYSICAL_RECONCILIATION"
            for e in automatic_events)
        result.append({**deepcopy(approval), "event_type": "GOAL",
                       "status": "USER_CONFIRMED_GOAL", "automatic_proof_eligible": False,
                       "also_automatically_verified": automatic_match,
                       "observation_authority": "HUMAN_REVIEW_NOT_MACHINE_MEASUREMENT"})
    return {"events": result, "rejected": rejected, "user_confirmed_goals": len(result),
            "additional_user_confirmed_goals": sum(
                not e["also_automatically_verified"] for e in result)}
