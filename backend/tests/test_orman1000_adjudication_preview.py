"""Strict shadow-only, model-free adjudication tests for the user's 1+3 target."""
from copy import deepcopy
import json
from pathlib import Path
import pytest

from scripts.preview_orman1000_adjudication import (
    propose, MANIFEST_PATH, APPROVAL_PATH, TARGET_EVENT
)

MANIFEST = json.loads(MANIFEST_PATH.read_text())
PRIOR = json.loads(APPROVAL_PATH.read_text())
SOURCE = "fa56f933859508d037b1f0ecb929c8b14ee3d2a5886fe8be312dcdc24a8be5e2"


def synthetic_source_bundle():
    # Only the disputed event carries a current Orman1000 source-bound receipt.
    # Other 20 distinct IDs test count invariance; no invented event geometry.
    other = [
        {"event_id": f"distinct:{i}",
         "canonical_event_type": "GOAL" if i == 0 else
                                 "ASSIST" if i in (1, 2) else "DRIBBLE",
         "source_video_sha256": SOURCE}
        for i in range(20)
    ]
    disputed = {
        "event_id": TARGET_EVENT, "source_video_sha256": SOURCE,
        "canonical_event_type": "GOAL", "canonical_action_type": "SHOT",
        "canonical_outcome": "GOAL", "canonical_ms": 49881,
        "contact_ms": None,
        "proof": {"source_video_sha256": SOURCE, "receipts": [
            {"packet_id": "contact_review_006",
             "response_sha256": "7c3fd71f15b0b7736f9b879573c30c38e1426ddc4d6ea7d4daacb2182db06631"}
        ]}
    }
    return {"source_video_sha256": SOURCE, "events": [*other, disputed]}


def test_approved_distinct_white_finisher_yields_only_unpublished_counterfactual():
    bundle, old, manifest = synthetic_source_bundle(), deepcopy(PRIOR), deepcopy(MANIFEST)
    before = deepcopy((bundle, old, manifest))
    result = propose(bundle, old, manifest,
                     manifest["primary_evidence_archive"]["archive_sha256"])
    assert result["status"] == "REVIEW_PROPOSAL_NOT_PUBLISHED"
    assert result["same_footage_frame_matches"] == 13
    assert result["exported_observed_counts"] == {"goals": 2, "assists": 2}
    assert result["proposed_observed_counts_if_approved"] == {"goals": 1, "assists": 3}
    assert result["actor_ids_transferred_across_model_runs"] is False
    assert result["suggested_action"]["current_source_receiver_visual_id"] is None
    assert result["suggested_action"]["current_source_finisher_visual_id"] is None
    assert result["suggested_action"]["proposed_change_auto_approved"] is False
    assert result["canonical_event_overwritten"] is False
    assert result["report_or_database_written"] is False
    assert result["new_paid_model_calls"] == 0
    assert len(result["all_other_20_events_sha256"]) == 64
    assert (bundle, old, manifest) == before


@pytest.mark.parametrize("mutator", [
    lambda b,o,m: b.update(source_video_sha256="foreign-source"),
    lambda b,o,m: m["cross_sha_perceptual_source_comparison"].update(visual_near_matches=12),
    lambda b,o,m: m["primary_evidence_archive"].update(archive_sha256="other-zip"),
    lambda b,o,m: b["events"][-1].update(contact_ms=49881),
    lambda b,o,m: b["events"][-1].update(canonical_event_type="ASSIST"),
    lambda b,o,m: b["events"].append(deepcopy(b["events"][-1])),
    lambda b,o,m: o["result"]["target_events"][0].update(receiver="p1"),
    lambda b,o,m: o.update(source_video_sha256="foreign-source"),
    lambda b,o,m: m["prior_model_conflict_at_50_seconds"]["receipts"].clear(),
])
def test_ambiguous_forged_or_modified_source_evidence_blocks_adjudication(mutator):
    bundle, old, manifest = synthetic_source_bundle(), deepcopy(PRIOR), deepcopy(MANIFEST)
    mutator(bundle, old, manifest)
    with pytest.raises(ValueError):
        propose(bundle, old, manifest,
                MANIFEST["primary_evidence_archive"]["archive_sha256"])


def test_unverified_archive_digest_fails_closed():
    with pytest.raises(ValueError, match="UNBOUND_SOURCE_OR_PREVIOUS_RECEIPT"):
        propose(synthetic_source_bundle(), PRIOR, MANIFEST, "unknown-archive")
