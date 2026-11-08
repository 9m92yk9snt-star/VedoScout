"""Offline perceptual comparison: approved older assist video vs Orman1000.

Rebuild the exact historical source from repository parts and verify SHA-256.
Compare 13 nonreversible image fingerprints calculated from the actual
user-uploaded Orman1000 ZIP. Never transfer observations or event IDs across
different video checksums; a visual match is source-context evidence only.
No provider calls, no new model predictions, no report writes or deployment.
"""
import argparse
import hashlib
import json
from pathlib import Path

SOURCE_SHA = "b9e2ba4975ed9dc2497f860a80644711bfd12a2125d9fba6390600b0409ab999"
TARGET_SHA = "fa56f933859508d037b1f0ecb929c8b14ee3d2a5886fe8be312dcdc24a8be5e2"
ROOT = Path(__file__).resolve().parents[2]
PARTS = ROOT / "testdata/sequence-pilot-orman400/video-parts"
MANIFEST = ROOT / "testdata/matchroom-completion/orman1000-vs-prior-verified-play-hashes.json"
PRIOR = ROOT / "docs/examples/native-third-assist-approval-receipt.json"


def digest_stream(f):
    h = hashlib.sha256()
    for chunk in iter(lambda: f.read(1024 * 1024), b""):
        h.update(chunk)
    return h.hexdigest()


def unpack(path):
    parts = sorted(PARTS.glob("*.bin"))
    if [p.name for p in parts] != [f"{i:03}.bin" for i in range(43)]:
        raise ValueError("HISTORICAL_SOURCE_PARTS_CHANGED")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as output:
        for part in parts:
            with part.open("rb") as f:
                for chunk in iter(lambda: f.read(1024 * 1024), b""):
                    output.write(chunk)
    with path.open("rb") as f:
        if digest_stream(f) != SOURCE_SHA:
            raise ValueError("HISTORICAL_VIDEO_SOURCE_HASH_MISMATCH")


def fingerprint(frame, roi):
    import cv2
    import numpy as np
    h, w = frame.shape[:2]
    x0,y0,x1,y1 = roi
    frame = frame[round(h*y0):round(h*y1), round(w*x0):round(w*x1)]
    if frame.size == 0:
        raise ValueError("INVALID_FRAME_ROI")
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    d = cv2.resize(gray,(9,8),interpolation=cv2.INTER_AREA)
    dbits = (d[:,1:] > d[:,:-1]).astype(np.uint8).flatten()
    dh = ''.join(f"{sum(dbits[i:i+4]*[8,4,2,1]):x}" for i in range(0,64,4))
    p = cv2.resize(gray,(32,32),interpolation=cv2.INTER_AREA).astype('float32')
    dct = cv2.dct(p)[:8,:8].flatten()
    median = float(np.median(dct[1:]))
    pbits = (dct > median).astype(np.uint8)
    ph = ''.join(f"{sum(pbits[i:i+4]*[8,4,2,1]):x}" for i in range(0,64,4))
    return dh, ph


def distance(a,b):
    if not (isinstance(a,str) and isinstance(b,str) and len(a)==len(b)==16):
        raise ValueError("INVALID_SOURCE_FINGERPRINT")
    return (int(a,16)^int(b,16)).bit_count()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args=parser.parse_args()
    if args.work.exists() or args.output.exists():
        parser.error("Fresh work directory and output required")

    import cv2
    manifest=json.loads(MANIFEST.read_text())
    if (manifest["latest_source_sha256"] != TARGET_SHA or
            manifest["previous_approved_receipt_source_sha256"] != SOURCE_SHA or
            len(manifest["samples"]) != 13):
        raise ValueError("SOURCE_FINGERPRINT_MANIFEST_CHANGED")
    prior=json.loads(PRIOR.read_text())
    if (prior["source_video_sha256"] != SOURCE_SHA or
            prior["response_sha256"] != manifest["previous_approved_receipt_response_sha256"]):
        raise ValueError("PRIOR_APPROVED_RECEIPT_CHANGED")
    approved=prior.get("result",{}).get("target_events") or []
    if not any(e.get("event_type")=="ASSIST" and
               e.get("outcome")=="TEAMMATE_GOAL" and
               e.get("actor")=="p1" and e.get("receiver")=="p3" and e.get("finisher")=="p3"
               for e in approved):
        raise ValueError("PRIOR_ASSIST_EVIDENCE_NOT_IN_RECEIPT")
    old_video=args.work/"historical-source.mp4"
    unpack(old_video)
    cap=cv2.VideoCapture(str(old_video))
    if not cap.isOpened():
        raise ValueError("HISTORICAL_VIDEO_UNREADABLE")
    cap.set(cv2.CAP_PROP_POS_MSEC, 47.35*1000)
    candidates=[]
    try:
        while True:
            if not cap.grab():
                break
            ms=cap.get(cv2.CAP_PROP_POS_MSEC)
            if ms > 51_800:
                break
            if ms < 47_300:
                continue
            if not ms or (candidates and ms<=candidates[-1]["media_ms"]):
                raise ValueError("HISTORICAL_SOURCE_PTS_UNRELIABLE")
            ok,frame=cap.retrieve()
            if not ok:
                break
            a,b=fingerprint(frame,(0,0,1,1))
            c,d=fingerprint(frame,manifest["dynamic_pitch_normalized_roi"])
            candidates.append({"media_ms":int(round(ms)), "whole":(a,b), "player_area":(c,d)})
    finally:
        cap.release()
    if len(candidates)<140:
        raise ValueError("TOO_FEW_HISTORICAL_SOURCE_PTS")

    rows=[]
    for target in manifest["samples"]:
        t=target[0]
        if len(target)!=5:
            raise ValueError("MALFORMED_TARGET_FINGERPRINT")
        nearby=[c for c in candidates if abs(c["media_ms"]-t)<=250]
        if not nearby:
            rows.append({"target_ms":t, "status":"NO_MATCHING_PTS"})
            continue
        def measure(c):
            distances=[distance(target[1],c["whole"][0]),
                       distance(target[2],c["whole"][1]),
                       distance(target[3],c["player_area"][0]),
                       distance(target[4],c["player_area"][1])]
            return distances
        # Prioritize dynamic pitch-area matching, with global context tie-break.
        best=min(nearby,key=lambda c:(sum(measure(c)[2:]),sum(measure(c)[:2]),
                                     abs(c["media_ms"]-t)))
        d=measure(best)
        rows.append({"target_ms":t,"historical_ms":best["media_ms"],
                     "source_time_offset_ms":best["media_ms"]-t,
                     "whole_dhash_hamming":d[0],"whole_phash_hamming":d[1],
                     "player_dhash_hamming":d[2],"player_phash_hamming":d[3],
                     "visual_near_match": d[1]<=12 and d[3]<=14 and d[0]<=20 and d[2]<=22})
    matched=sum(row.get("visual_near_match",False) for row in rows)
    result={
      "scope":"CROSS_SHA_PERCEPTUAL_SOURCE_SIMILARITY_NOT_ACTION_RECLASSIFICATION",
      "orman1000_source_sha256":TARGET_SHA,
      "historical_approved_source_sha256":SOURCE_SHA,
      "historical_source_pts_scanned":len(candidates),
      "source_sample_count":len(rows),
      "visually_near_matches":matched,
      "same_underlying_video_supported":matched>=10,
      "match_threshold":"at least 10 of 13 source frames within 250ms with DCT and edge fingerprints satisfying both field and whole frame",
      "matching_frame_evidence":rows,
      "prior_receipt_status":"APPROVED_ASSIST_P1_TO_P3",
      "prior_receipt_source_is_distinct":True,
      "result_cross_source_authoritative_for_current_orman1000":False,
      "active_orman1000_canonical_event_overwritten":False,
      "full_visual_player_identity_verified":False,
      "provider_calls":0
    }
    args.output.write_text(json.dumps(result,indent=2))
    print("CROSS_SHA_ORMAN1000_ASSIST_FRAME_MATCH="+json.dumps(result),flush=True)


if __name__=="__main__":
    main()
