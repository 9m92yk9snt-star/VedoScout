"""Stage the already-paid 00:08 Orman1000 completion receipt, WITHOUT model calls.

This produces a new, unpublished report snapshot with only its exact-source
localization checkpoint extended. It does not change the 21 events, active
player, approved results, report prose, score, or on-video graphics. Later
normal localization MUST freshly rebuild the exact same request and verify
the receipt against current original pixels before treating it as reusable.
"""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import zipfile

from match_room_position_evidence import selection_digest, bound_samples
from match_room_localization import validate, completion_windows
from sequence_run_checkpoint import reusable_receipt

SOURCE = "fa56f933859508d037b1f0ecb929c8b14ee3d2a5886fe8be312dcdc24a8be5e2"
ARCHIVE = "3b27260511ed965952a497f97d1c6345a0f1b4bef1b89a60912a62e0f6530c0c"
SELECTION = "ca4bc63080b8de6b986c370f809c89ad1050b5d1c883fe7e748da0ab8400d016"
DUEL = "966c91c7243829d6fab0"
WINDOW = [10125,12133]
PACKET = "positions_" + DUEL + "_coverage_10125_12133"


def stage(doc, response):
    """Clone and stage only the validated source-specific completion audit."""
    doc=deepcopy(doc)
    bundle=doc.get("canonical_events") or {}
    audit=doc.get("match_room_localization") or {}
    if bundle.get("source_video_sha256") != SOURCE or audit.get("source_video_sha256") != SOURCE:
        raise ValueError("DUEL_SOURCE_VIDEO_CHANGED")
    raw=doc.get("raw_marker_anchors")
    while isinstance(raw,str):
        raw=json.loads(raw)
    selection={"raw_marker_anchors":raw}
    if selection_digest(selection)!=SELECTION or audit.get("original_selection_values_sha256")!=SELECTION:
        raise ValueError("DUEL_ORIGINAL_HUMAN_SELECTION_CHANGED")
    events=[e for e in bundle.get("events") or [] if e.get("event_id")==DUEL]
    if len(events)!=1 or events[0].get("source_video_sha256")!=SOURCE:
        raise ValueError("DUEL_EVENT_IDENTITY_CHANGED")
    event=events[0]
    saved=(audit.get("events") or {}).get(DUEL) or {}
    if (saved.get("status")!="OBSERVATIONS_RETURNED"
            or saved.get("source_video_sha256")!=SOURCE
            or saved.get("original_selection_values_sha256")!=SELECTION
            or saved.get("window_ms")!=[7500,10000]
            or WINDOW not in completion_windows(event,saved)):
        raise ValueError("PRIMARY_DUEL_PROOF_WINDOW_CHANGED")
    if response.get("status")!="OBSERVATIONS_RETURNED":
        raise ValueError("DUEL_COMPLETION_NOT_APPROVED")
    record=response.get("record") or {}
    receipt=record.get("receipt") or {}
    if (record.get("event_id")!=DUEL or record.get("packet_id")!=PACKET
            or record.get("source_video_sha256")!=SOURCE
            or record.get("original_selection_values_sha256")!=SELECTION
            or record.get("window_ms")!=WINDOW):
        raise ValueError("COMPLETION_EVIDENCE_CROSS_SOURCE")
    if not reusable_receipt(receipt,record.get("request") or {},
                            provider="emergent",model="gpt-6-astra",packet_id=PACKET):
        raise ValueError("PAID_COMPLETION_RECEIPT_NOT_IDENTICAL")
    observed=bound_samples(event,selection,record,validate,packet=PACKET)
    if observed != response.get("samples") or len(observed)!=17:
        raise ValueError("COMPLETION_SOURCE_OBSERVATIONS_CHANGED")
    if (observed[0].get("media_ms"),observed[-1].get("media_ms"))!=(10133,12133):
        raise ValueError("COMPLETION_SOURCE_PTS_CHANGED")
    if any(s.get("media_ms")<WINDOW[0]-50 or s.get("media_ms")>WINDOW[1]+50 for s in observed):
        raise ValueError("COMPLETION_OUTSIDE_APPROVED_WINDOW")
    current=saved.get("completion") or {}
    if PACKET in current and current[PACKET]!=record:
        raise ValueError("COMPLETION_CHECKPOINT_CONFLICT")
    staged=deepcopy(saved)
    staged["completion"]={**current,PACKET:deepcopy(record)}
    # Never claim these observations are already rendered contours. Normal
    # source-localizer rechecks the rebuilt request and merges them at replay.
    doc["match_room_localization"]["events"][DUEL]=staged
    doc["offline_checkpoint_staging"]={
        "event_id":DUEL,"packet_id":PACKET,
        "source_video_sha256":SOURCE,
        "status":"STAGED_FOR_REVALIDATED_REPLAY_NOT_RENDERED",
        "source_observations":17,
        "model_calls":0,
        "published":False,
        "source_event_and_report_unchanged":True,
    }
    return doc


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--original-zip",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    args=p.parse_args()
    if args.output.exists():p.error("Refusing output overwrite")
    h=hashlib.sha256()
    with args.original_zip.open("rb") as f:
        for block in iter(lambda:f.read(1024*1024),b""):h.update(block)
    if h.hexdigest()!=ARCHIVE:raise ValueError("WRONG_ORMAN1000_ARCHIVE")
    with zipfile.ZipFile(args.original_zip) as z:
        if z.testzip():raise ValueError("CORRUPT_SOURCE_ARCHIVE")
        doc=json.loads(z.read("report.json"))
    receipt=json.loads((Path(__file__).resolve().parents[2] /
                        "testdata/matchroom-completion/result.json").read_text())
    staged=stage(doc,receipt)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(staged,ensure_ascii=False,separators=(",",":")))
    print(json.dumps(staged["offline_checkpoint_staging"]))


if __name__=="__main__":
    main()
