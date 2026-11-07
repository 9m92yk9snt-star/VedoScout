"""Source-scoped provenance for disputed Orman1000 event reclassification.

Keep the ORIGINAL model evidence and its contradictory conclusion visible to
an auditor. The independent human role review has a different authority and
cannot rewrite or masquerade as an old model receipt. All functions are pure.
"""
import hashlib
import json

TARGET = "47ad617d2ba76a4683cd"
CURRENT = "fa56f933859508d037b1f0ecb929c8b14ee3d2a5886fe8be312dcdc24a8be5e2"
OLD = "b9e2ba4975ed9dc2497f860a80644711bfd12a2125d9fba6390600b0409ab999"
PREVIOUS_RECEIPT = "c1b78325895885002ccc58f036b0a29824406997108b12648f3805a46e0040ff"


def canonical_hash(value):
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()).hexdigest()


def make_resolution(original_event, role_review):
    """Only propose a review trail, never certify the submitted role evidence."""
    if (not isinstance(original_event, dict) or original_event.get("event_id") != TARGET
            or original_event.get("source_video_sha256") != CURRENT
            or not isinstance(role_review, dict)
            or role_review.get("source_video_sha256") != CURRENT
            or role_review.get("event_id") != TARGET):
        raise ValueError("REVIEW_EVENT_OR_SOURCE_NOT_BOUND")
    proof = original_event.get("proof") or {}
    receipt_rows = proof.get("receipts") or []
    if (proof.get("source_video_sha256") != CURRENT or not receipt_rows
            or any(r.get("origin") != "LIVE_MODEL_REQUEST"
                   or not r.get("response_sha256") for r in receipt_rows)):
        raise ValueError("ORIGINAL_MODEL_PROOF_NOT_PRESERVED")
    return {
        "schema_version": 1,
        "disputed_event_id": TARGET,
        "source_video_sha256": CURRENT,
        "original_canonical_event_sha256": canonical_hash(original_event),
        "source_model_receipts_retained": [dict(x) for x in receipt_rows],
        "source_model_original_action": "SHOT",
        "source_model_original_outcome": "GOAL",
        "source_model_original_finisher_scope": original_event.get("causal_chain", {}).get("finisher_visual_id"),
        "previous_approved_receipt_source_sha256": OLD,
        "previous_approved_response_sha256": PREVIOUS_RECEIPT,
        "previous_model_role_ids_transferred": False,
        "review_authority": "INDEPENDENT_CURRENT_SOURCE_PERSON_ROLE_REVIEW",
        "review_source_frame_ids": list(role_review.get("evidence_frames") or []),
        "review_source_frame_sha256": dict(role_review.get("source_decoded_bgr_frame_sha256") or {}),
        "review_current_source_finisher_visual_id": role_review.get("current_source_finisher_visual_id"),
        "review_contact_inference": role_review.get("finishing_contact_evidence"),
        "hidden_contact_exact_ms_claimed": False,
        "original_receipts_modified": False,
    }


def resolution_problems(original_event, corrected_event, role_review):
    """Reject a corrected claim whose review trail lacks immutable authority."""
    errors = []
    original_proof = (original_event or {}).get("proof") or {}
    corrected_proof = (corrected_event or {}).get("proof") or {}
    if canonical_hash(original_proof) != canonical_hash(corrected_proof):
        errors.append("ORIGINAL_CONTRADICTORY_MODEL_RECEIPTS_REWRITTEN")
    trail = (corrected_event or {}).get("review_resolution")
    if not isinstance(trail, dict):
        errors.append("INDEPENDENT_REVIEW_AUDIT_TRAIL_MISSING")
        return errors
    try:
        expected = make_resolution(original_event, role_review)
    except (ValueError, AttributeError):
        errors.append("INDEPENDENT_REVIEW_PROVENANCE_NOT_SOURCE_BOUND")
        return errors
    if trail != expected:
        errors.append("INDEPENDENT_REVIEW_PROVENANCE_DOES_NOT_MATCH_SOURCE")
    if (corrected_event.get("causal_chain") or {}).get("finisher_visual_id") != expected["review_current_source_finisher_visual_id"]:
        errors.append("REVIEW_TRAIL_FINISHER_NOT_CURRENT_EVENT")
    return errors
