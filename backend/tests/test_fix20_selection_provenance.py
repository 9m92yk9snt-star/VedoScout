"""A changed human selection must be distinguishable in an exported run."""
from copy import deepcopy
import pytest

import analysis_jobs as jobs


@pytest.fixture
def inputs(tmp_path):
    video = tmp_path / "canonical.mp4"
    video.write_bytes(b"original canonical video bytes")
    anchor = {"t": 1., "segment": 1, "verify": False,
              "box": {"x": .2, "y": .2, "w": .3, "h": .5},
              "target_point": {"x": .3, "y": .4}}
    return video, anchor


@pytest.mark.parametrize("change", [
    {"target_point": {"x": .4, "y": .4}},
    {"visible_mask": {"width": 96, "height": 192, "runs": [0, 18432]}},
    {"player_behind": True}, {"visibility": "partial"},
    {"include_points": [{"x": .3, "y": .5}]},
    {"exclude_points": [{"x": .4, "y": .5}]},
    {"tracking_check": {"status": "user_confirmed", "start": 1., "end": 1.5}},
    {"continuity": [{"t": 1.4, "segment": 1, "same_player": True,
                      "box": {"x": .25, "y": .2, "w": .3, "h": .5}}]},
])
def test_selection_changes_are_visible_even_when_geometry_hash_matches(inputs, change):
    video, anchor = inputs
    before = jobs.manifest(video, [anchor], {})
    after = jobs.manifest(video, [{**anchor, **change}], {})
    assert before["original_taps_sha256"] == after["original_taps_sha256"]
    assert before["selection_inputs_sha256"] != after["selection_inputs_sha256"]


def test_mask_pixels_offset_and_player_declaration_are_recorded(inputs):
    video, anchor = inputs
    anchor["visible_mask"] = {"width": 96, "height": 192, "runs": [0, 18432]}
    original = deepcopy(anchor)
    first = jobs.manifest(video, [anchor], {}, player_details={"jersey_number": 15})
    anchor["visible_mask"]["runs"] = [1, 18431]
    other_mask = jobs.manifest(video, [anchor], {})
    offset = jobs.manifest(video, [original], {}, anchor_time_offset=.3)
    player = jobs.manifest(video, [original], {}, player_details={"jersey_number": 5})
    assert other_mask["selection_inputs_sha256"] != first["selection_inputs_sha256"]
    assert offset["selection_inputs_sha256"] != first["selection_inputs_sha256"]
    assert player["player_details_sha256"] != first["player_details_sha256"]
    assert first["selection_input_schema"] == 1
    assert "jersey_number" not in first


def test_transient_urls_and_unconsumed_hints_do_not_change_selection_hash(inputs):
    video, anchor = inputs
    original = deepcopy(anchor)
    first = jobs.manifest(video, [anchor], {})
    anchor.update(crop_url="https://example.invalid/temporary", filename="new.jpg",
                  target_point={"x": .3, "y": .4}, ignored_hint="not an input")
    after = jobs.manifest(video, [anchor], {})
    assert after["selection_inputs_sha256"] == first["selection_inputs_sha256"]
    assert original["target_point"] == anchor["target_point"]
