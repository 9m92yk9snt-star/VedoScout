"""Pure matched-source hand-marked reference regions: not role attribution."""
from copy import deepcopy
import json
from pathlib import Path
import pytest
from scripts.compare_orman500_orman1000_selected_anchors import compare, unwrap

ANCHORS = Path(__file__).resolve().parents[2] / "testdata/sequence-pilot-orman400/anchors.json"
SIX = {0, 3, 4, 5, 6, 8}


def alignable_source_selections():
    previous = unwrap(json.loads(ANCHORS.read_text())["raw_marker_anchors"])
    current = deepcopy(previous)
    for i, row in enumerate(current):
        if i not in SIX:
            # Nonmatching times intentionally do not become same-PTS proof.
            row["t"] += .49
    return previous, current


def test_exact_six_human_source_instants_are_not_conflated_with_later_frames():
    old, new = alignable_source_selections()
    result = compare(old, new)
    assert result["previous_selection_count"] == 10
    assert result["current_selection_count"] == 10
    assert result["exact_shared_selection_times"] == 6
    assert [row["media_ms"] for row in result["matches"]] == [
        3070, 15350, 21480, 27630, 33770, 55760,
    ]
    assert result["all_six_source_regions_compatible"] is True
    assert result["prior_person_local_ids_transferred"] is False
    assert result["ball_contact_or_goal_scoring_actor_verified"] is False
    assert result["new_provider_calls"] == 0


def test_minor_review_margin_is_allowed_but_distinct_distant_player_is_not():
    old, current = alignable_source_selections()
    # The original ZIP exhibits about -0.004 normalized margin at 3.070 s;
    # a nearby partly visible target may fall just outside a tighter crop.
    current[0]["box"]["x"] = old[0]["target_point"]["x"] + .004
    current[0]["box"]["w"] = .06
    assert compare(old, current)["all_six_source_regions_compatible"] is True
    current[0]["box"]["x"] = .85
    assert compare(old, current)["all_six_source_regions_compatible"] is False


def test_missing_original_references_or_duplicate_time_fails_closed():
    old, new = alignable_source_selections()
    with pytest.raises(ValueError, match="TEN_HUMAN_SELECTIONS_REQUIRED"):
        compare(old[:-1], new)
    new[8]["t"] = new[6]["t"]
    with pytest.raises(ValueError, match="DUPLICATE_SOURCE_MEDIA_TIMES"):
        compare(old, new)
    new = deepcopy(old)
    for i in (0, 3, 4, 5, 6):
        new[i]["t"] += .05
    with pytest.raises(ValueError, match="NOT_ENOUGH_IDENTICAL_SELECTION_INSTANTS"):
        compare(old, new)
