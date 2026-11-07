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
    def normalized(p):
        return (isinstance(p, list) and len(p) == 2
                and all(type(v) in (int, float) and 0 <= v <= 1 for v in p))
    if (type(row.get("player_width")) not in (int, float)
            or not .005 <= row["player_width"] <= .4
            or type(row.get("confidence")) not in (int, float)
            or not .55 <= row["confidence"] <= 1):
        return False
    ground = row.get("ground")
    if not normalized(ground) and not (
            ground is None
            and row.get("display_estimated") is True
            and row.get("source_ground_observation") is False
            and normalized(row.get("display_ground"))):
        return False
    fg = row.get("foreground") or {}
    polygons = fg.get("polygons")
    return (fg.get("method") == "SOURCE_PERSON_MASK"
            and fg.get("frame_id") == row.get("frame_id")
            and fg.get("media_ms") == ms
            and isinstance(polygons, list) and 0 < len(polygons) <= 48
            and all(isinstance(p, list) and 3 <= len(p) <= 512
                    and all(normalized(v) for v in p) for p in polygons))


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


def contour_budget_observation(track):
    """Metadata only: scheduler COMPLETED != every source contour completed.

    A TIME_BUDGET result says a processing window was interrupted, even if
    subsequent refinement recovered some or all frames. This flag does not
    claim uncovered frames or authorize interpolation / further model calls.
    """
    diagnostics = (track.get("contour_diagnostics") or {}) if isinstance(track, dict) else {}
    windows = diagnostics.get("windows") or []
    if not isinstance(windows, list):
        windows = []
    statuses = [w.get("status") for w in windows if isinstance(w, dict)]
    return {
        "kind": "INITIAL_CONTOUR_PROCESSING",
        "initial_windows_examined": len(statuses),
        "initial_windows_time_budget_reached": statuses.count("TIME_BUDGET"),
        "initial_windows_with_supported_observations": statuses.count("SUPPORTED_SOURCE_OBSERVATIONS"),
        "total_accepted_segments": len(track.get("segments") or []) if isinstance(track, dict) else 0,
        "source_frame_coverage_complete": None,
        "status": "INITIAL_WINDOW_TIME_BUDGET_REACHED"
                  if "TIME_BUDGET" in statuses else "NO_INITIAL_TIME_BUDGET_RECORDED",
    }
