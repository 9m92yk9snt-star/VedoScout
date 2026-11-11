"""Compare feature votes and full pair results on decoded source frames."""
import argparse
import hashlib
import json
from pathlib import Path
import statistics
import time
import cv2
import numpy as np
import match_room_contours as contours
import match_room_reacquisition as recovery
from native_player_segmentation import PersonSegmenter


def legacy(mask, points):
    return sum(contours.owns(mask, point) for point in points)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('video', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    cv2.setNumThreads(1)
    model = PersonSegmenter()
    cap = cv2.VideoCapture(str(args.video))
    frames, rows = [], []
    try:
        cap.set(cv2.CAP_PROP_POS_MSEC, 49440)
        for _ in range(2):
            ok, image = cap.read()
            if not ok:
                raise RuntimeError('source frame unavailable')
            h,w = image.shape[:2]
            image = cv2.resize(image, (720, round(h*720/w)))
            frame = {'image':image, 'gray':cv2.cvtColor(image,cv2.COLOR_BGR2GRAY),
                     'media_ms':round(cap.get(cv2.CAP_PROP_POS_MSEC))}
            frames.append(frame)
            h,w = image.shape[:2]
            rows.append(contours.detect_frame(frame,(0,0,w,h),model))
    finally:
        cap.release()
    assert all(rows), 'source must contain detected players'
    engine = recovery.IdentityAssociator(frames, rows, [0,1], [{'x':.5,'y':.5}]*2)
    jobs = [(a,1-a,j) for a in (0,1) for j in range(len(rows[a]))]
    candidate, workloads = recovery.count_owned, []
    def record(mask, points):
        workloads.append((mask.copy(),points.copy()))
        return legacy(mask,points)
    def replay(fn):
        recovery.count_owned = fn
        engine.pair_cache.clear()
        return [engine.pair(*job) for job in jobs]
    try:
        old = replay(record)
        new = replay(candidate)
        assert old == new
        assert workloads and any(len(points) for _,points in workloads)
        assert all(legacy(mask,points) == candidate(mask,points) for mask,points in workloads)
        vote_times = {'legacy':[], 'candidate':[]}
        pair_times = {'legacy':[], 'candidate':[]}
        for round_id in range(7):
            order = [('legacy',legacy),('candidate',candidate)]
            if round_id % 2: order.reverse()
            for name,fn in order:
                start = time.perf_counter()
                for _ in range(20):
                    for mask,points in workloads: fn(mask,points)
                vote_times[name].append(time.perf_counter()-start)
                start = time.perf_counter()
                assert replay(fn) == old
                pair_times[name].append(time.perf_counter()-start)
    finally:
        recovery.count_owned = candidate
    medians = {kind:{key:statistics.median(values) for key,values in times.items()}
               for kind,times in [('votes',vote_times),('pairs',pair_times)]}
    with args.video.open('rb') as source:
        source_sha = hashlib.file_digest(source,'sha256').hexdigest()
    result = {'source_sha256':source_sha,'model_sha256':model.sha256,
              'source_frame_ms':[f['media_ms'] for f in frames],
              'pair_results_compared':len(jobs),'vote_workloads':len(workloads),
              'vote_points':sum(len(p) for _,p in workloads),'differences':0,
              'vote_rounds_seconds':vote_times,'pair_rounds_seconds':pair_times,
              'median_seconds':medians,
              'reduction_percent':{kind:100*(1-v['candidate']/v['legacy']) for kind,v in medians.items()},
              'scope':'feature votes and pair association only; no end-to-end analysis claim'}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))

if __name__ == '__main__': main()
