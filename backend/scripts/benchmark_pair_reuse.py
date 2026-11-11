"""Replay adaptive association on fixed real detections; no identity claim."""
import argparse
from copy import deepcopy
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

class FullInvalidation(recovery.AdaptiveAssociator):
    def fill(self, i, large=False):
        before = (set(self.small_done), set(self.upgraded))
        super().fill(i, large)
        if before != (self.small_done, self.upgraded):
            self.pair_cache.clear()

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('video', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    cv2.setNumThreads(1)
    frames = list(contours.read_clip(str(args.video), 49440, 49650, sample_step=0))
    if len(frames) < 5:
        raise ValueError('Insufficient real source frames')
    model = PersonSegmenter()
    rows = [contours.detect_frame(f, (0,0,f['gray'].shape[1],f['gray'].shape[0]), model) for f in frames]
    def targets(index):
        h,w = frames[index]['gray'].shape
        result = []
        for row in rows[index]:
            mask = contours.measured_mask(row)
            distance = cv2.distanceTransform(mask.astype(np.uint8), cv2.DIST_L2, 3)
            y,x = np.unravel_index(distance.argmax(), distance.shape)
            point = {'x':float(x/w),'y':float(y/h)}
            if len(contours.seed_candidates(rows[index],point,(h,w))) == 1:
                result.append(point)
        return result
    first,last = targets(0),targets(-1)
    if not first or not last:
        raise ValueError('No unique visible instances for pair-cache workload')
    # Exercise every combination, without asserting cross-frame player identity.
    jobs = [(a,b) for a in first for b in last]
    counts, times, expected = {'before':[], 'after':[]}, {'before':[], 'after':[]}, None
    original = cv2.goodFeaturesToTrack
    calls = [0]
    def counted(*a, **kw):
        calls[0] += 1
        return original(*a, **kw)
    cv2.goodFeaturesToTrack = counted
    try:
        for repeat in range(5):
            order = [('before',FullInvalidation),('after',recovery.AdaptiveAssociator)]
            if repeat % 2:
                order.reverse()
            for name,kind in order:
                calls[0] = 0
                started = time.perf_counter()
                output = []
                for a,b in jobs:
                    engine = kind(frames,[0,len(frames)-1],[a,b],
                                  lambda i: deepcopy(rows[i]),lambda i: deepcopy(rows[i]))
                    output.append(engine.review())
                times[name].append(time.perf_counter()-started)
                counts[name].append(calls[0])
                if expected is None:
                    expected = output
                assert output == expected, 'Association replay changed'
    finally:
        cv2.goodFeaturesToTrack = original
    with args.video.open('rb') as source:
        source_sha = hashlib.file_digest(source,'sha256').hexdigest()
    result = {'source_sha256':source_sha,'model_sha256':model.sha256,
              'frame_ms':[f['media_ms'] for f in frames], 'replays_per_round':len(jobs),
              'feature_extractions':counts,'round_seconds':times,
              'median_seconds':{k:statistics.median(v) for k,v in times.items()},
              'differences':0,
              'scope':'Association only with fixed real detections and synthetic endpoint combinations; no identity or full-analysis speed claim.'}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result))

if __name__ == '__main__': main()
