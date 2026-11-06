"""Audit retained report coverage metadata without rerunning source perception.

This is a read-only diagnostic, not real-video PTS validation. It reports
suspected gaps inside accepted segment spans, never invents ground positions,
changes identity, or schedules an extra model call.
"""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from match_room_coverage_audit import source_gap_audit


def audit_report(doc):
    bundle = doc.get("canonical_events") or {}
    source = bundle.get("source_video_sha256")
    if not isinstance(source, str) or len(source) != 64:
        raise ValueError("CANONICAL_VIDEO_SOURCE_REQUIRED")
    rows = (doc.get("full_report") or {}).get("video_comments")
    if not isinstance(rows, list) or not rows:
        raise ValueError("RETAINED_REPORT_VIDEO_COMMENTS_REQUIRED")
    checks = []
    seen = set()
    for row in rows:
        eid = row.get("event_id")
        room = row.get("match_room") or {}
        track = room.get("tracking") or {}
        if not isinstance(eid, str) or eid in seen:
            raise ValueError("EVENT_ID_MISSING_OR_DUPLICATED")
        seen.add(eid)
        if not all(item == source for item in (
                row.get("source_video_sha256"),
                room.get("source_video_sha256"),
                track.get("source_video_sha256"))):
            raise ValueError("CROSS_VIDEO_TRACK_DATA_REJECTED")
        if room.get("event_id") != eid or track.get("event_id") != eid:
            raise ValueError("TRACK_EVENT_BINDING_CHANGED")
        observations = room.get("samples") or []
        if not isinstance(observations, list):
            raise ValueError("SOURCE_OBSERVATIONS_REQUIRED")
        event = {"event_id": eid, "source_video_sha256": source,
                 "localization_method": "EXPLICIT_SOURCE_POSITIONS",
                 "visual_samples": observations}
        summary = source_gap_audit(event, track)
        checks.append({"event_id": eid, "status": summary["status"],
                       "hidden_source_pair_count": summary["count"],
                       "holes": summary["holes"]})
    return {"scope": "RETAINED_METADATA_ONLY_NOT_VIDEO_DECODER_OR_BROWSER",
            "source_video_sha256": source,
            "checked_events": len(checks), "checks": checks,
            "total_hidden_source_pairs": sum(r["hidden_source_pair_count"] for r in checks),
            "model_calls": 0, "score_or_approved_evidence_changed": False,
            "real_video_pts_verified": False, "production_behavior_changed": False}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--report", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    if args.output.exists():
        ap.error("output path must be new")
    result = audit_report(json.loads(args.report.read_text()))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2))
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
