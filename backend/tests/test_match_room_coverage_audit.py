"""Synthetic, no-model regressions for opt-in Match Room coverage audit."""
from copy import deepcopy

from match_room_coverage_audit import audited_display_spans, source_gap_audit
from match_room_tracking import missing_display_windows


def observation(t):
    return {"media_ms": t, "identity_status": "CONFIRMED",
            "ground": [.5, .75], "frame_id": f"s{t:09}"}


def sample(t):
    return {
        "media_ms": t, "frame_id": f"position-contour:{t}",
        "ground": [.5, .75], "player_width": .09, "confidence": .95,
        "foreground": {"method": "SOURCE_PERSON_MASK", "frame_id": f"position-contour:{t}",
                       "media_ms": t, "polygons": [[[.4, .5], [.5, .5], [.5, .8]]]},
    }


def fixture():
    event = {"event_id": "same-event", "source_video_sha256": "same-source",
             "localization_method": "EXPLICIT_SOURCE_POSITIONS",
             "visual_samples": [observation(t) for t in (0, 125, 250, 375, 500)]}
    source_times = list(range(0, 133, 33)) + [360, 393, 426, 459, 492, 500]
    previous = {
        "event_id": event["event_id"], "source_video_sha256": event["source_video_sha256"],
        "method": "SOURCE_OBSERVATION_INSTANCE_CONTOUR",
        "segments": [{"id": "one-contiguous-claim", "source_frame_coverage": "COMPLETE_SEGMENT",
                      "reference_frame": "s000000000", "samples": [sample(t) for t in source_times]}],
    }
    return event, previous


def test_audit_detects_hidden_internal_gap_without_changing_scheduler_output():
    event, previous = fixture()
    before = deepcopy((event, previous))
    # Existing scheduler sees a single 0..500ms span and assumes coverage.
    assert missing_display_windows(event, previous) == []
    result = source_gap_audit(event, previous)
    assert result["status"] == "AUDITED"
    assert result["declared_spans"] == 1
    assert result["supported_source_runs"] == 2
    assert result["count"] == 2
    assert result["holes"] == [
        {"start_ms": 125, "end_ms": 250,
         "reason": "DECLARED_SEGMENT_SPAN_HAS_UNPROVEN_SOURCE_FRAMES"},
        {"start_ms": 250, "end_ms": 375,
         "reason": "DECLARED_SEGMENT_SPAN_HAS_UNPROVEN_SOURCE_FRAMES"},
    ]
    assert (event, previous) == before
    assert missing_display_windows(event, previous) == []


def test_audit_does_not_invent_coverage_from_absent_foreground_or_hidden_pose():
    event, previous = fixture()
    for t in (360, 393, 426):
        row = next(s for s in previous["segments"][0]["samples"] if s["media_ms"] == t)
        row["foreground"] = None
    result = source_gap_audit(event, previous)
    assert result["count"] >= 2
    # Source observation with hidden feet is not a measured contact.
    previous["segments"][0]["samples"][0]["ground"] = None
    assert audited_display_spans(previous)[0][0] != 0


def test_audit_refuses_cross_video_or_unconfirmed_identity_barriers():
    event, previous = fixture()
    bad = deepcopy(previous)
    bad["source_video_sha256"] = "different-video"
    assert source_gap_audit(event, bad)["status"] == "SOURCE_BINDING_REQUIRED"
    bad = deepcopy(event)
    bad["visual_samples"][2]["identity_status"] = "UNCERTAIN"
    bad["visual_samples"][2]["ground"] = None
    result = source_gap_audit(bad, previous)
    assert result["status"] == "AUDITED"
    assert all(not (h["start_ms"] < 250 < h["end_ms"]) for h in result["holes"])


def test_complete_masked_source_stamps_have_no_audited_holes():
    event, previous = fixture()
    previous["segments"][0]["samples"] = [sample(t) for t in range(0, 501, 25)]
    assert source_gap_audit(event, previous)["holes"] == []
    assert audited_display_spans(previous) == [[0, 500]]


def test_invalid_geometry_or_foreground_polygon_never_counts_as_coverage():
    event, previous = fixture()
    original = audited_display_spans(previous)
    assert original == [[0, 132], [360, 500]]
    changes = [
        {"player_width": .7},
        {"confidence": .2},
        {"ground": [1.4, .75]},
        {"foreground": {"method": "SOURCE_PERSON_MASK",
                        "frame_id": "wrong-source-frame",
                        "media_ms": 0,
                        "polygons": [[[.4, .5], [.5, .5], [.5, .8]]]}},
        {"foreground": {"method": "SOURCE_PERSON_MASK",
                        "frame_id": "position-contour:0",
                        "media_ms": 0,
                        "polygons": [[[.4, .5], [1.2, .5], [.5, .8]]]}}
    ]
    for change in changes:
        changed = deepcopy(previous)
        changed["segments"][0]["samples"][0].update(change)
        assert audited_display_spans(changed)[0][0] != 0
        assert source_gap_audit(event, changed)["status"] == "AUDITED"


def test_retained_report_audit_enforces_source_event_before_any_coverage_claim():
    import pytest
    from scripts.audit_matchroom_report_coverage import audit_report
    event, previous = fixture()
    sha = "a" * 64
    previous["source_video_sha256"] = sha
    row = {"event_id": event["event_id"], "source_video_sha256": sha,
           "match_room": {"event_id": event["event_id"],
                          "source_video_sha256": sha,
                          "samples": event["visual_samples"],
                          "tracking": previous}}
    document = {"canonical_events": {"source_video_sha256": sha},
                "full_report": {"video_comments": [row]}}
    result = audit_report(document)
    assert result["checked_events"] == 1
    assert result["total_hidden_source_pairs"] == 2
    assert result["model_calls"] == 0
    assert result["real_video_pts_verified"] is False
    bad = deepcopy(document)
    bad["full_report"]["video_comments"][0]["match_room"]["tracking"]["source_video_sha256"] = "b" * 64
    with pytest.raises(ValueError, match="CROSS_VIDEO_TRACK_DATA_REJECTED"):
        audit_report(bad)
    bad = deepcopy(document)
    bad["full_report"]["video_comments"][0]["match_room"]["tracking"]["event_id"] = "other"
    with pytest.raises(ValueError, match="TRACK_EVENT_BINDING_CHANGED"):
        audit_report(bad)



def test_contour_timeout_does_not_claim_missing_source_frames_or_silent_completion():
    from match_room_coverage_audit import contour_budget_observation
    result = contour_budget_observation({
        "contour_diagnostics": {"windows": [
            {"status": "TIME_BUDGET"},
            {"status": "SUPPORTED_SOURCE_OBSERVATIONS"},
            {"status": "TIME_BUDGET"},
        ]},
        "segments": [{"id": "source-first"}, {"id": "source-second"}],
        "refinement_diagnostics": {"status": "SUPPORTED_SOURCE_OBSERVATIONS"},
    })
    assert result == {
        "kind": "INITIAL_CONTOUR_PROCESSING",
        "initial_windows_examined": 3,
        "initial_windows_time_budget_reached": 2,
        "initial_windows_with_supported_observations": 1,
        "total_accepted_segments": 2,
        "source_frame_coverage_complete": None,
        "status": "INITIAL_WINDOW_TIME_BUDGET_REACHED",
    }
    # A later refinement might recover all missing frames; initial timeout
    # is a historical observation, not proof that the final clip is incomplete.
    assert result["source_frame_coverage_complete"] is None


def test_no_source_tracking_is_not_claimed_complete():
    from match_room_coverage_audit import contour_budget_observation
    empty = contour_budget_observation(None)
    assert empty["total_accepted_segments"] == 0
    assert empty["initial_windows_time_budget_reached"] == 0
    assert empty["source_frame_coverage_complete"] is None
    assert empty["status"] == "NO_INITIAL_TIME_BUDGET_RECORDED"
