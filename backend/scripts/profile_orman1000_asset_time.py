"""Read-only allocation audit of actual latest Orman1000 export timings.

This does NOT run inference, encode video or change analysis. Medium refinement
"budget_seconds" is an allowance, NOT elapsed time. The remaining asset time
may contain contours, encoding, publishing and other steps; it cannot be
attributed to one without new instrumentation.
"""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile

ZIP_SHA="3b27260511ed965952a497f97d1c6345a0f1b4bef1b89a60912a62e0f6530c0c"
VIDEO_SHA="fa56f933859508d037b1f0ecb929c8b14ee3d2a5886fe8be312dcdc24a8be5e2"

def sha256_file(path):
    digest=hashlib.sha256()
    with open(path,"rb") as stream:
        for buf in iter(lambda:stream.read(1024*1024),b""):
            digest.update(buf)
    return digest.hexdigest()

def audit(document):
    timings=document.get("sequence_timings") or {}
    locator=document.get("match_room_localization") or {}
    events=(document.get("canonical_events") or {}).get("events") or []
    cards=(document.get("full_report") or {}).get("video_comments") or []
    if (not isinstance(cards,list) or len(cards)!=8 or len(events)!=21
            or locator.get("source_video_sha256")!=VIDEO_SHA
            or (document.get("canonical_events") or {}).get("source_video_sha256")!=VIDEO_SHA):
        raise ValueError("ORMAN1000_SOURCE_21_EVENTS_8_CARDS_REQUIRED")
    keys=("source_analysis_seconds","facts_writer_and_projection_seconds",
          "before_assets_seconds","assets_seconds","total_processing_seconds")
    values=[timings.get(k) for k in keys]
    if any(type(x) not in (int,float) or x<0 for x in values):
        raise ValueError("INCOMPLETE_OR_INVALID_SOURCE_TIMINGS")
    source,writer,before,assets,total=values
    loc=locator.get("elapsed_seconds")
    if type(loc) not in (int,float) or not 0<=loc<=assets:
        raise ValueError("INVALID_REAL_LOCALIZATION_DURATION")
    if abs(source+writer-before)>.01 or abs(before+assets-total)>.01:
        raise ValueError("TIMING_TOTALS_NOT_CONSISTENT")
    rows=[]
    for card in cards:
        room=card.get("match_room") or {}
        tracker=room.get("tracking") or {}
        if (card.get("source_video_sha256")!=VIDEO_SHA
                or room.get("source_video_sha256")!=VIDEO_SHA
                or tracker.get("source_video_sha256")!=VIDEO_SHA
                or card.get("event_id")!=room.get("event_id")
                or card.get("event_id")!=tracker.get("event_id")):
            raise ValueError("CROSS_VIDEO_TRACKING_CARD")
        windows=(tracker.get("contour_diagnostics") or {}).get("windows") or []
        refine=tracker.get("refinement_diagnostics") or {}
        medium_budget=refine.get("budget_seconds")
        if medium_budget is not None and (
            type(medium_budget) not in (int,float) or medium_budget<0):
            raise ValueError("INVALID_MEDIUM_BUDGET")
        rows.append({
          "event_id":card["event_id"],"timestamp":card.get("timestamp"),
          "scheduler_status":room.get("tracking_status"),
          "initial_source_windows":len(windows),
          "initial_time_budget_windows":sum(w.get("status")=="TIME_BUDGET" for w in windows),
          "source_segments_retained":len(tracker.get("segments") or []),
          "medium_refinement_budget_allocated_seconds":round(medium_budget,3) if medium_budget is not None else None,
          "medium_refinement_windows":len(refine.get("windows") or []),
          "medium_refinement_window_statuses":[w.get("status") for w in refine.get("windows") or []]
        })
    summary={
      "scope":"EXACT_LATEST_ORMAN1000_RETAINED_TIMINGS_NOT_PER_STAGE_PROFILER",
      "source_video_sha256":VIDEO_SHA,
      "seconds":{
        "source_analysis":round(source,3),
        "facts_writer_and_projection":round(writer,3),
        "before_assets":round(before,3),
        "assets_total":round(assets,3),
        "match_room_localization_elapsed":round(loc,3),
        "assets_after_localization_unpartitioned":round(assets-loc,3),
        "complete_report":round(total,3),
      },
      "percent_of_total":{
        "assets_total":round(100*assets/total,2),
        "localization":round(100*loc/total,2),
        "after_localization_unpartitioned":round(100*(assets-loc)/total,2),
      },
      "clip_count":len(rows),
      "initial_contour_timeout_card_count":sum(r["initial_time_budget_windows"]>0 for r in rows),
      "medium_refinement_allocated_budget_seconds":round(sum(
        r["medium_refinement_budget_allocated_seconds"] or 0 for r in rows),3),
      "medium_refinement_elapsed_seconds":None,
      "asset_encoding_and_upload_elapsed_seconds":None,
      "per_card":rows,
      "quality_policy":"Do not infer detector elapsed from an allocated budget, shorten quality gates or enable prediction cache without source-identical and wall-time proof.",
      "new_provider_calls":0,"production_changed":False
    }
    return summary

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--latest-zip",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    args=p.parse_args()
    if args.output.exists():p.error("Output must be new")
    if sha256_file(args.latest_zip)!=ZIP_SHA:
        raise ValueError("NONCANONICAL_ORMAN1000_ZIP")
    with zipfile.ZipFile(args.latest_zip) as z:
        if z.testzip() is not None:
            raise ValueError("ORIGINAL_ZIP_CORRUPT")
        data=json.loads(z.read("report.json"))
    report=audit(data)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2)+"\n")
    print("ORMAN1000_ASSET_TIMING_AUDIT="+json.dumps(report))

if __name__=="__main__":
    main()
