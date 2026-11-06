"""Offline, read-only audit of gaps hidden by end-to-end segment spans.

No video decoding, no model calls, no interpolation and no changes to the
production scheduler or analysis acceptance gates. A segment's first and
last timestamps do NOT by themselves prove all intervening source frames
have a valid overlay. This auditor reports only documented gaps.
"""
from match_room_position_contours import endpoint_pairs

MAX_SOURCE_GAP_MS = 75


def _valid_sample(row):
    if not isinstance(row, dict):
        return False
    ms = row.get("media_ms")
    if type(ms) is not int or ms < 0:
        return False
    ground = row.get("ground")
    estimate = row.get("display_ground")
    if ground is None and (
        row.get("display_estimated") is not True
        or row.get("source_ground_observation") is not False
        or not (isinstance(estimate, list) and len(estimate) == 2
                and all(type(v) in (int, float) and 0 <= v <= 1 for v in estimate))
    ):
        return False
    fg = row.get("foreground") or {}
    return (fg.get("method") == "SOURCE_PERSON_MASK"
            and fg.get("frame_id") == row.get("frame_id")
            and fg.get("media_ms") == ms
            and isinstance(fg.get("polygons"), list)
            and bool(fg["polygons"]))


def audited_display_spans(previous):
    """Contiguous supported source masks; NEVER fill an absent frame."""
    spans = []
    for segment in previous.get("segments") or []:
        if not isinstance(segment, dict) or segment.get("source_frame_coverage") != "COMPLETE_SEGMENT":
            continue
        rows = segment.get("samples")
        if not isinstance(rows, list):
            continue
        lo = last = None
        for row in rows:
            if not _valid_sample(row):
                if lo is not None:
                    spans.append([lo, last])
                lo = last = None
                continue
            stamp = row["media_ms"]
            if lo is None:
                lo = last = stamp
            elif 0 < stamp - last <= MAX_SOURCE_GAP_MS:
                last = stamp
            else:
                spans.append([lo, last])
                lo = last = stamp
        if lo is not None:
            spans.append([lo, last])
    return sorted(spans)


def source_gap_audit(event, previous):
    """Flag claimed endpoint coverage containing a documented internal hole.

    A discrepancy is diagnostic only: it does not authorize interpolation or
    extra refinement, and unverified source/identity blocks the entire audit.
    """
    if (event.get("localization_method") != "EXPLICIT_SOURCE_POSITIONS"
            or previous.get("method") != "SOURCE_OBSERVATION_INSTANCE_CONTOUR"
            or not event.get("source_video_sha256")
            or previous.get("source_video_sha256") != event.get("source_video_sha256")
            or previous.get("event_id") != event.get("event_id")):
        return {"status": "SOURCE_BINDING_REQUIRED", "holes": [], "count": 0}
    observations = event.get("visual_samples") or []
    if not isinstance(observations, list) or any(
            not isinstance(row, dict) or type(row.get("media_ms")) is not int for row in observations):
        return {"status": "INVALID_SOURCE_OBSERVATIONS", "holes": [], "count": 0}

    # This mirrors the existing scheduler's declared-span check, solely to
    # spot its blind spots. It does not call or change the scheduler.
    declared = sorted([rows[0]["media_ms"], rows[-1]["media_ms"]]
                      for segment in previous.get("segments") or []
                      if isinstance(segment, dict)
                      if isinstance((rows := segment.get("samples")), list) and len(rows) >= 2
                      and all(isinstance(s, dict) and type(s.get("media_ms")) is int for s in (rows[0], rows[-1])))
    actual = audited_display_spans(previous)
    holes = []
    for a, b in endpoint_pairs(observations):
        lo, hi = a["media_ms"], b["media_ms"]
        if hi - lo < 60:
            continue

        def covers(spans):
            far = lo
            for start, stop in spans:
                if start <= far + 2 and stop > far:
                    far = stop
            return far >= hi - 2

        if not covers(declared) or covers(actual):
            continue
        # Report the interval; the exact missing video PTS require a source
        # decoder and frontend acceptance, never an inferred regular FPS.
        holes.append({"start_ms": lo, "end_ms": hi,
                      "reason": "DECLARED_SEGMENT_SPAN_HAS_UNPROVEN_SOURCE_FRAMES"})
    return {"status": "AUDITED", "holes": holes[:32], "count": len(holes),
            "declared_spans": len(declared), "supported_source_runs": len(actual)}
