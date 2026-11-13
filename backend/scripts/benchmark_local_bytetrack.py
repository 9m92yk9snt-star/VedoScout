"""Offline YOLO + ByteTrack feasibility benchmark, never report authority.

Uses all decoded frames at original resolution and the existing YOLOv8n
weights/preprocessor. No model downloads, LLM, inferred target identity or
event approval. Output tracks are proposals requiring identity validation.
Install requirements-local-tracking-test.txt in an isolated environment.
"""
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import sys
import time


def person_proposals(prediction, width, height, cv, np):
    # Preserve low-confidence candidates for ByteTrack's second association.
    selected = (prediction.classes == 0) & (prediction.scores > .1)
    boxes, scores = [], []
    scale = cv.INPUT / max(width, height)
    for row, score in zip(prediction.xywh[selected], prediction.scores[selected]):
        cx, cy, w, h = map(float, row)
        if not all(np.isfinite([cx, cy, w, h, score])) or min(w, h) <= 0:
            continue
        boxes.append([cx-w/2, cy-h/2, w, h])
        scores.append(float(score))
    indices = cv.cv2.dnn.NMSBoxes(boxes, scores, .1, cv.NMS_T)
    xyxy, kept = [], []
    for i in np.asarray(indices).reshape(-1):
        x, y, w, h = boxes[int(i)]
        box = [max(0., x/scale), max(0., y/scale),
               min(float(width), (x+w)/scale), min(float(height), (y+h)/scale)]
        if box[2] > box[0] and box[3] > box[1]:
            xyxy.append(box); kept.append(scores[int(i)])
    return np.asarray(xyxy, dtype=float).reshape(-1, 4), np.asarray(kept)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--video', type=Path, required=True)
    parser.add_argument('--start-ms', type=int, required=True)
    parser.add_argument('--end-ms', type=int, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--selection-json', type=Path, help='Source-bound JSON with source_video_sha256 and original taps')
    args = parser.parse_args()
    if not 0 <= args.start_ms < args.end_ms <= args.start_ms + 10000:
        parser.error('Choose a positive window of at most ten seconds')
    if args.output.exists():
        parser.error('Output must not already exist')
    if not hasattr(os, 'sched_setaffinity'):
        parser.error('Linux CPU affinity is required for this one-core benchmark')
    core = min(os.sched_getaffinity(0))
    os.sched_setaffinity(0, {core})
    os.environ['OPENBLAS_NUM_THREADS'] = '1'
    os.environ['OMP_NUM_THREADS'] = '1'
    def offline(event, _args):
        if event == 'socket.connect':
            raise RuntimeError('LOCAL_TRACKING_NETWORK_FORBIDDEN')
    sys.addaudithook(offline)
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    import cv2
    import numpy as np
    import supervision as sv
    import cv_detect as cv
    from dense_replay import iter_dense_frames
    cv2.setNumThreads(1)
    if importlib.metadata.version('supervision') != '0.26.1':
        raise RuntimeError('Use the pinned experimental ByteTrack version')
    detector = cv.PersonDetector(enabled=True)
    if not detector.ok:
        raise RuntimeError('Existing local YOLO weights unavailable')
    cap = cv2.VideoCapture(str(args.video))
    fps = cap.get(cv2.CAP_PROP_FPS)
    cap.release()
    if not np.isfinite(fps) or not 1 <= fps <= 240:
        raise RuntimeError('Invalid source frame rate')
    tracker = sv.ByteTrack(frame_rate=round(fps))
    rows, previous, previous_ms, scene = [], None, None, 0
    timings = dict(decode=0., detection=0., tracking=0.)
    frames = iter(iter_dense_frames(str(args.video),args.start_ms,args.end_ms,proc_max_width=0))
    started = time.perf_counter()
    while True:
        tick = time.perf_counter()
        row = next(frames, None)
        timings['decode'] += time.perf_counter()-tick
        if row is None: break
        if row['used_fallback'] or row['time_authority'] != 'ACTUAL_MEDIA_PTS':
            raise RuntimeError('Actual source timestamps required')
        image = row['frame_bgr']; ms = row['media_ms']
        if previous_ms is not None and ms <= previous_ms:
            raise RuntimeError('Non-increasing media timestamps')
        tiny = cv2.resize(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY),(160,90))
        cut = previous is not None and float(cv2.absdiff(previous,tiny).mean()) > 45
        gap = previous_ms is not None and ms-previous_ms > max(120, 2000/fps)
        if cut or gap:
            tracker.reset(); scene += 1
        previous, previous_ms = tiny, ms
        tick = time.perf_counter()
        prediction = cv.predict(detector,image)
        boxes,scores = person_proposals(prediction,row['width'],row['height'],cv,np)
        timings['detection'] += time.perf_counter()-tick
        tick = time.perf_counter()
        tracked = tracker.update_with_detections(sv.Detections(xyxy=boxes,confidence=scores,class_id=np.zeros(len(scores),dtype=int)))
        timings['tracking'] += time.perf_counter()-tick
        rows.append({'media_ms':ms,'width':row['width'],'height':row['height'],'scene':scene,'barrier':bool(cut or gap),
                     'person_detections':len(scores),'detection_boxes':boxes.tolist(),'detection_scores':scores.tolist(),'tracks':[{
                         'id':f'{scene}:{int(track_id)}','box':box.tolist(),
                         'confidence':float(score),'proof_eligible':False}
                         for box,score,track_id in zip(tracked.xyxy,tracked.confidence,tracked.tracker_id)]})
    if not rows: raise RuntimeError('No frames decoded')
    elapsed = time.perf_counter()-started
    with args.video.open('rb') as stream:
        source_sha = hashlib.file_digest(stream,'sha256').hexdigest()
    summary={'scope':'LOCAL_PROPOSALS_ONLY_NOT_PLAYER_IDENTITY_OR_REPORT_PARITY',
             'source_video_sha256':source_sha,'model_sha256':detector.model_sha256,
             'engine':'opencv','window_ms':[args.start_ms,args.end_ms],'frames':len(rows),'llm_calls':0,
             'cpu_affinity_count':len(os.sched_getaffinity(0)),'opencv_threads':cv2.getNumThreads(),
             'versions':{name:importlib.metadata.version(name) for name in ('supervision','numpy','opencv-python')},
             'seconds':elapsed,'stage_seconds':timings,
             'frames_with_tracks':sum(bool(row['tracks']) for row in rows),
             'distinct_track_ids':len({t['id'] for row in rows for t in row['tracks']}),
             'identity_switches':'NOT_MEASURED_REQUIRES_LABELLED_TARGET',
             'rows':rows}
    if args.selection_json:
        from local_track_selection import bind_taps
        selection = json.loads(args.selection_json.read_text())
        summary['tap_candidates'] = bind_taps(rows, selection['taps'],
            source_sha=source_sha, expected_source_sha=selection['source_video_sha256'])
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps({k:v for k,v in summary.items() if k!='rows'},indent=2))


if __name__ == '__main__':
    main()
