"""Replay real-source segmenter masks; no provider calls or changed inference."""
import argparse
import hashlib
import json
from pathlib import Path
import statistics
import time
import cv2
import numpy as np
import match_room_contours as contours
from native_player_segmentation import PersonSegmenter


def legacy(a, b):
    return np.count_nonzero((a > 0) & (b > 0))/max(1, np.count_nonzero((a > 0) | (b > 0)))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('video', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    model = PersonSegmenter()
    cap = cv2.VideoCapture(str(args.video))
    pairs, views = [], []
    try:
        for seconds in (23.68, 30.83, 43.19, 49.44, 56.44):
            cap.set(cv2.CAP_PROP_POS_MSEC, seconds*1000)
            ok, image = cap.read()
            if not ok:
                raise RuntimeError('source frame unavailable')
            h, w = image.shape[:2]
            image = cv2.resize(image, (720, round(h*720/w)))
            instances = model.predict(image)
            views.append((image, instances))
            for i, a in enumerate(instances):
                for b in instances[i:]:
                    pairs.append((a['mask'], b['mask']))
    finally:
        cap.release()
    assert pairs, 'no real masks'
    candidate = contours.mask_iou
    assert all(legacy(a,b) == candidate(a,b) for a,b in pairs)
    # Replay the identical model outputs through the complete duplicate filter.
    parity = 0
    class Fixed:
        def predict(self, image):
            return self.instances
    fixed = Fixed()
    try:
        for image, instances in views:
            fixed.instances = instances
            h,w = image.shape[:2]
            contours.mask_iou = legacy
            old = contours.detect_frame({'image':image}, (0,0,w,h), fixed)
            contours.mask_iou = candidate
            new = contours.detect_frame({'image':image}, (0,0,w,h), fixed)
            assert len(old) == len(new)
            for a,b in zip(old,new):
                np.testing.assert_array_equal(a['mask_bits'], b['mask_bits'])
                assert {k:v for k,v in a.items() if k != 'mask_bits'} == {k:v for k,v in b.items() if k != 'mask_bits'}
                parity += 1
    finally:
        contours.mask_iou = candidate
    timings = {'legacy':[], 'candidate':[]}
    for round_id in range(9):
        order = [('legacy',legacy), ('candidate',candidate)]
        if round_id % 2: order.reverse()
        for name, fn in order:
            start=time.perf_counter()
            for _ in range(5):
                for a,b in pairs: fn(a,b)
            timings[name].append(time.perf_counter()-start)
    medians={k:statistics.median(v) for k,v in timings.items()}
    with args.video.open('rb') as source:
        source_sha = hashlib.file_digest(source, 'sha256').hexdigest()
    result={'source_sha256':source_sha,
            'model_sha256':model.sha256,'views':len(views),'mask_pairs':len(pairs),
            'identical_returned_contours':parity,'overlap_differences':0,
            'rounds_seconds':timings,'median_seconds':medians,
            'stage_reduction_percent':100*(1-medians['candidate']/medians['legacy']),
            'scope':'mask overlap only; excludes inference and end-to-end analysis'}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))

if __name__ == '__main__':
    main()
