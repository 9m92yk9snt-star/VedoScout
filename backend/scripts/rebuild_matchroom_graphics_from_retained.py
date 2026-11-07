"""Offline current-branch Match Room graphics on exactly the retained source.

Only two selected events; all original human references and source-bound
localization receipts are validated anew. No paid model/provider calls, no
report/database mutations, no new outcome or score authority. Use the normal
bounded ONNX graphics scheduler to compare with the older stored graphics.
"""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

import sequence_pilot as pilot
from match_room import presentation
from match_room_position_evidence import selection_digest
from match_room_tracking import bounded_tracks
from scripts.run_matchroom_single_tap_trial import prepare
from scripts.verify_matchroom_onnx_scheduler_parity import (
    PINNED_SOURCE, TARGET_EVENT_IDS, observations_from_retained,
)

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--report", type=Path, required=True)
    ap.add_argument("--work", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    if args.work.exists() or args.output.exists():
        ap.error("Fresh output and work paths required")
    doc = json.loads(args.report.read_text())
    bundle = doc["canonical_events"]
    if bundle["source_video_sha256"] != PINNED_SOURCE or doc.get("full_report_status") != "ready":
        raise ValueError("RETAINED_REPORT_NOT_READY_OR_WRONG_SOURCE")
    fixture = json.loads((ROOT / "testdata/sequence-pilot-orman400/anchors.json").read_text())
    raw = doc["raw_marker_anchors"]
    original = fixture["raw_marker_anchors"]
    while isinstance(raw, str):
        raw = json.loads(raw)
    while isinstance(original, str):
        original = json.loads(original)
    if raw != original:
        raise ValueError("ORIGINAL_TAPS_CHANGED")
    selection = {"raw_marker_anchors": raw}
    taps = pilot.original_taps(selection)
    if len(taps) != 10:
        raise ValueError("ALL_TEN_ORIGINAL_SELECTIONS_REQUIRED")
    audit = doc["match_room_localization"]
    if (audit.get("source_video_sha256") != PINNED_SOURCE or
            audit.get("original_selection_values_sha256") != selection_digest(selection)):
        raise ValueError("LOCALIZATION_SOURCE_OR_SELECTION_CHANGED")
    video, _ = prepare(ROOT / "testdata/sequence-pilot-orman400", args.work)
    with video.open("rb") as stream:
        if hashlib.file_digest(stream, "sha256").hexdigest() != PINNED_SOURCE:
            raise ValueError("ORIGINAL_VIDEO_BYTES_CHANGED")
    events = {e["event_id"]: deepcopy(e) for e in bundle["events"]}
    comments = {r["event_id"]: r for r in doc["full_report"]["video_comments"]}
    selected = []
    for eid in TARGET_EVENT_IDS:
        if eid not in events or eid not in comments or eid not in (audit.get("events") or {}):
            raise ValueError("RETAINED_SOURCE_EVENT_MISSING")
        event = events[eid]
        record = audit["events"][eid]
        event["visual_samples"] = observations_from_retained(event, selection, record)
        event["localization_method"] = "EXPLICIT_SOURCE_POSITIONS"
        if record.get("context_after_ms") == 750:
            event["graphics_context_ms"] = 750
        selected.append(event)
    anchors = [{"t": t["requested_ms"]/1000, "box": t["box"],
                "target_point": t["target_point"], **t["selection_hints"]}
               for t in taps]
    start = time.monotonic()
    graphics, status = bounded_tracks(video, anchors, selected, reuse_predictions=False)
    seconds = time.monotonic() - start
    for event in selected:
        eid = event["event_id"]
        row = comments[eid]
        if row.get("source_video_sha256") != PINNED_SOURCE:
            raise ValueError("REPORT_CARD_CROSS_SOURCE")
        new_room = presentation(event, event["visual_samples"])
        track = graphics.get(eid)
        new_room["tracking"] = track
        new_room["tracking_status"] = status if track else "NO_TRACK_INPUT"
        if track and isinstance(track.get("observed_samples"), list):
            new_room["samples"] = track["observed_samples"]
        row["match_room"] = new_room
    doc["test_scope"] = {
        "mode":"OFFLINE_TWO_EVENT_GRAPHICS_REBUILD_FROM_RETAINED_EVIDENCE",
        "source_analysis_reused":True, "localization_receipts_reused":True,
        "new_provider_calls":0, "model_engine":"onnxruntime",
        "existing_report_prose_reused":True, "production_database_used":False,
        "deployed":False, "live_browser_verified":False,
        "tracking_status":status, "tracking_seconds":round(seconds,3)}
    args.output.write_text(json.dumps(doc, separators=(",", ":")))
    out = {"scope": doc["test_scope"], "event_segments": {
        e["event_id"]: len((graphics.get(e["event_id"]) or {}).get("segments") or [])
        for e in selected}}
    print("MATCHROOM_CURRENT_GRAPHICS_REBUILD=" + json.dumps(out), flush=True)
    if status != "COMPLETED" or any(e["event_id"] not in graphics for e in selected):
        raise RuntimeError("SOURCE_GRAPHICS_REBUILD_INCOMPLETE")


if __name__ == "__main__":
    main()
