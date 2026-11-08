"""Offline same-player reference alignment: Orman500 vs latest Orman1000 ZIP.

Only exact SOURCE MEDIA TIME anchors are compared. Cross-video perceptual
scene matching has a separate receipt. Similar tap boxes corroborate selected
subject context; they NEVER establish goal scorer, finisher or contact.
No provider calls, model, network, image synthesis or report publication.
"""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile

ROOT=Path(__file__).resolve().parents[2]
PRIOR_ANCHORS=ROOT/"testdata/sequence-pilot-orman400/anchors.json"
ORMAN1000_ARCHIVE_SHA="3b27260511ed965952a497f97d1c6345a0f1b4bef1b89a60912a62e0f6530c0c"


def unwrap(value):
    while isinstance(value,str):
        value=json.loads(value)
    if not isinstance(value,list):
        raise ValueError("INVALID_HUMAN_ANCHORS")
    return value


def within(point,box):
    if (not isinstance(point,dict) or not isinstance(box,dict) or
            not all(isinstance(point.get(k),(float,int)) for k in ("x","y")) or
            not all(isinstance(box.get(k),(float,int)) for k in ("x","y","w","h"))):
        raise ValueError("INVALID_SOURCE_SELECTION_GEOMETRY")
    x,y,w,h=(box[k] for k in ("x","y","w","h"))
    if not (0<=x<=1 and 0<=y<=1 and 0<w<=1-x and 0<h<=1-y):
        raise ValueError("INVALID_SOURCE_BOX")
    px,py=point["x"],point["y"]
    return min(px-x,x+w-px,py-y,y+h-py)


def compare(previous,newer):
    old=unwrap(previous); new=unwrap(newer)
    if len(old)!=10 or len(new)!=10:
        raise ValueError("TEN_HUMAN_SELECTIONS_REQUIRED")
    old_by_time={round(item["t"]*1000):item for item in old}
    new_by_time={round(item["t"]*1000):item for item in new}
    if len(old_by_time)!=10 or len(new_by_time)!=10:
        raise ValueError("DUPLICATE_SOURCE_MEDIA_TIMES")
    common=sorted(set(old_by_time)&set(new_by_time))
    if len(common)<6:
        raise ValueError("NOT_ENOUGH_IDENTICAL_SELECTION_INSTANTS")
    rows=[]
    for t in common:
        prev,cur=old_by_time[t],new_by_time[t]
        p1=within(prev["target_point"],cur["box"])
        p2=within(cur["target_point"],prev["box"])
        a,b=prev["box"],cur["box"]
        inter_w=max(0,min(a["x"]+a["w"],b["x"]+b["w"])-max(a["x"],b["x"]))
        inter_h=max(0,min(a["y"]+a["h"],b["y"]+b["h"])-max(a["y"],b["y"]))
        rows.append({
            "media_ms":t,
            "prior_point_margin_in_current_box":round(p1,6),
            "current_point_margin_in_prior_box":round(p2,6),
            "box_intersection_area":round(inter_w*inter_h,8),
            "mutual_subject_region_compatible":p1>=-.01 and p2>=-.01 and inter_w*inter_h>0
        })
    compatible=all(x["mutual_subject_region_compatible"] for x in rows)
    return {
        "scope":"IDENTICAL_PTS_MANUAL_SELECTION_REGION_COMPATIBILITY_NOT_PERSON_OR_FINISHER_APPROVAL",
        "previous_selection_count":len(old),
        "current_selection_count":len(new),
        "exact_shared_selection_times":len(common),
        "all_six_source_regions_compatible":compatible and len(common)==6,
        "matches":rows,
        "prior_person_local_ids_transferred":False,
        "ball_contact_or_goal_scoring_actor_verified":False,
        "new_provider_calls":0,
    }


def sha256(path):
    h=hashlib.sha256()
    with path.open("rb") as src:
        for chunk in iter(lambda:src.read(1024*1024),b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--latest-zip",type=Path,required=True)
    parser.add_argument("--new-output",type=Path,required=True)
    args=parser.parse_args()
    if args.new_output.exists(): parser.error("Refusing overwrite")
    if sha256(args.latest_zip)!=ORMAN1000_ARCHIVE_SHA:
        raise ValueError("FOREIGN_ORMAN1000_ZIP")
    with zipfile.ZipFile(args.latest_zip) as archive:
        if archive.testzip() is not None:raise ValueError("CORRUPT_SOURCE_ARCHIVE")
        current=json.loads(archive.read("anchors.json"))
    prior=json.loads(PRIOR_ANCHORS.read_text())
    report=compare(prior["raw_marker_anchors"],current["raw_marker_anchors"])
    if not report["all_six_source_regions_compatible"]:
        raise ValueError("SELECTED_PLAYER_REFERENCE_ALIGNMENT_NOT_CONFIRMED")
    args.new_output.parent.mkdir(parents=True,exist_ok=True)
    args.new_output.write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps(report))


if __name__=="__main__":
    main()
