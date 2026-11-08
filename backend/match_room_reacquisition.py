"""Bounded, two-anchor contour reacquisition. Display interpolation is separate."""
from pathlib import Path
import time
import cv2
import numpy as np
import match_room_contours as contours

MODEL_SHA256 = '20877569fcfc4744855b1d6d05b0cd7031987ae31894af5c7e1e74328d18e653'
MODEL_PATH = Path(__file__).resolve().parent / 'models' / 'yolov8m-seg.onnx'
METHOD = 'TAP_REACQUIRED_INSTANCE_CONTOUR'

def count_owned(mask, points):
    """Count the same rounded point votes in one array operation, including repeats."""
    if len(points) == 0:
        return 0
    xy = np.round(points).astype(int)
    x, y = xy[:, 0], xy[:, 1]
    inside = (x >= 0) & (x < mask.shape[1]) & (y >= 0) & (y < mask.shape[0])
    return int(np.count_nonzero(mask[y[inside], x[inside]]))


class IdentityAssociator:
    MAX_GAP_MS = 300
    APPEARANCE_LIMIT = .56

    def __init__(self, frames, detections, indices, targets):
        self.frames, self.rows = frames, detections
        self.indices, self.targets = indices, targets
        self.shape = frames[0]['gray'].shape
        self.histograms = []
        self.pair_cache = {}
        self.sources = []
        for i, target in zip(indices, targets):
            owners = contours.seed_candidates(detections[i], target, self.shape)
            self.sources.append(owners[0] if len(owners) == 1 else None)
        for frame, rows in zip(frames, detections):
            hsv = cv2.cvtColor(frame['image'], cv2.COLOR_BGR2HSV)
            hs = []
            for row in rows:
                h = cv2.calcHist([hsv], [0, 1], contours.measured_mask(row),
                                [24, 16], [0, 180, 0, 256])
                hs.append(cv2.normalize(h, None, norm_type=cv2.NORM_L1))
            self.histograms.append(hs)

    def appearance(self, i, j):
        if None in self.sources:
            return float('inf')
        return max(cv2.compareHist(self.histograms[i][j], self.histograms[a][k],
                                   cv2.HISTCMP_BHATTACHARYYA)
                   for a, k in zip(self.indices, self.sources))

    def pair(self, a, b, j):
        key = (a, b, j)
        if key in self.pair_cache:
            return self.pair_cache[key]
        mask = cv2.erode(contours.measured_mask(self.rows[a][j]), np.ones((3, 3), np.uint8))
        p = cv2.goodFeaturesToTrack(self.frames[a]['gray'], 100, .005, 3, mask=mask)
        result = {'n': 0, 'valid': 0, 'votes': []}
        if p is not None:
            q, st, _ = cv2.calcOpticalFlowPyrLK(self.frames[a]['gray'], self.frames[b]['gray'],
                                              p, None, winSize=(21, 21), maxLevel=3)
            if q is not None:
                back, sb, _ = cv2.calcOpticalFlowPyrLK(self.frames[b]['gray'], self.frames[a]['gray'],
                                                     q, None, winSize=(21, 21), maxLevel=3)
                if back is not None:
                    valid = ((st[:, 0] > 0) & (sb[:, 0] > 0) &
                             (np.linalg.norm(p[:, 0]-back[:, 0], axis=1) < 1.5))
                    q = q[valid, 0]
                    votes = []
                    for k, row in enumerate(self.rows[b]):
                        dst = cv2.dilate(contours.measured_mask(row), np.ones((3, 3), np.uint8))
                        votes.append((count_owned(dst, q), k))
                    result = {'n': len(p), 'valid': int(sum(valid)), 'votes': sorted(votes, reverse=True)}
        self.pair_cache[key] = result
        return result

    def feature_link(self, a, b, j):
        forward = self.pair(a, b, j)
        compatible = [(n, k) for n, k in forward['votes']
                      if self.appearance(b, k) <= self.APPEARANCE_LIMIT]
        if not compatible:
            return None
        n, k = compatible[0]
        second = max((count for count, other in forward['votes'] if other != k), default=0)
        if n < 6 or n < forward['valid']*.5 or n < forward['n']*.25 or second > n*.4:
            return None
        reverse = self.pair(b, a, k)
        back = next((count for count, other in reverse['votes'] if other == j), 0)
        other = max((count for count, other in reverse['votes'] if other != j), default=0)
        if back < 6 or back < reverse['valid']*.3 or other > back*.4:
            return None
        return k

    def center(self, i, j):
        x, y, width, height = self.rows[i][j]['box']
        return np.array([x+width/2, y+height/2])

    def motion_link(self, history, b):
        history = history[-5:]
        if len(history) < 3:
            return None
        ts = np.array([self.frames[i]['media_ms'] for i, _ in history])/1000
        centers = np.array([self.center(i, j) for i, j in history])
        velocities = [(centers[k]-centers[l])/(ts[k]-ts[l])
                      for k in range(len(ts)) for l in range(k) if ts[k] != ts[l]]
        velocity = np.median(velocities, axis=0)
        origin = np.median(centers-(ts-ts[-1])[:, None]*velocity, axis=0)
        residual = float(np.max(np.linalg.norm(centers-origin-(ts-ts[-1])[:, None]*velocity, axis=1)))
        height = float(np.median([self.rows[i][j]['box'][3] for i, j in history]))
        if height <= 0 or residual > height*.15:
            return None
        prediction = origin+(self.frames[b]['media_ms']/1000-ts[-1])*velocity
        candidates = []
        for k, row in enumerate(self.rows[b]):
            error = float(np.linalg.norm(self.center(b, k)-prediction))
            if (self.appearance(b, k) <= self.APPEARANCE_LIMIT and
                    error <= height*.22 and .7 < row['box'][3]/height < 1.4):
                candidates.append((k, error))
        if len(candidates) != 1:
            return None
        k, error = candidates[0]
        # Prediction associates a fresh detection; it is never a display point.
        return k, {'error_px': error, 'height_px': height, 'fit_residual_px': residual}

    def follow(self, seed_number):
        si, source = self.indices[seed_number], self.sources[seed_number]
        if source is None:
            return {}, []
        result, events = {si: source}, []
        for direction in (-1, 1):
            a, j, history = si, source, [(si, source)]
            stop = len(self.frames) if direction > 0 else -1
            for b in range(si+direction, stop, direction):
                gap = abs(self.frames[b]['media_ms']-self.frames[a]['media_ms'])
                if not 0 < gap <= self.MAX_GAP_MS:
                    break
                previous = b-direction
                if abs(self.frames[b]['media_ms']-self.frames[previous]['media_ms']) > 75:
                    break
                x = cv2.resize(self.frames[previous]['gray'], (160, 90))
                y = cv2.resize(self.frames[b]['gray'], (160, 90))
                if float(cv2.absdiff(x, y).mean()) > 45:
                    break
                k = self.feature_link(a, b, j)
                kind, detail = 'FEATURES', {}
                if k is None:
                    alternative = self.motion_link(history, b)
                    if alternative is None:
                        continue
                    k, detail = alternative
                    kind = 'MOTION_ASSOCIATION'
                result[b] = k
                events.append({'from_index': a, 'to_index': b, 'kind': kind, **detail})
                history.append((b, k))
                a, j = b, k
        return result, events

    def review(self):
        paths_and_events = [self.follow(n) for n in (0, 1)]
        paths = [p for p, _ in paths_and_events]
        shared = sorted(set(paths[0]) & set(paths[1]))
        conflicts = [i for i in shared if paths[0][i] != paths[1][i]]
        reaches = any(all(p.get(i) == j for i, j in zip(self.indices, self.sources)) for p in paths)
        consecutive = any(all(self.frames[shared[k+1]]['media_ms']-self.frames[shared[k]]['media_ms'] <= 75
                              for k in range(n, n+4)) for n in range(max(0, len(shared)-4)))
        passed = None not in self.sources and reaches and consecutive and not conflicts
        chosen = {i: paths[0].get(i, paths[1].get(i)) for i in sorted(set(paths[0]) | set(paths[1]))}
        return {'identity_link_passed_on_this_clip': passed, 'paths': paths,
                'shared_frames': len(shared), 'conflict_indices': conflicts,
                'events': [e for _, e in paths_and_events],
                'samples': [{'media_ms': self.frames[i]['media_ms'], 'detection_index': j,
                             'ground': self.rows[i][j]['ground'],
                             'player_width': self.rows[i][j]['player_width']}
                            for i, j in chosen.items()] if passed else []}


class AdaptiveAssociator(IdentityAssociator):
    def __init__(self, frames, indices, targets, small_detect, large_detect, deadline=None):
        self.deadline = deadline
        self.small_detect, self.large_detect = small_detect, large_detect
        rows = [[] for _ in frames]
        for i in indices:
            self.check_time()
            rows[i] = large_detect(i)
        super().__init__(frames, rows, indices, targets)
        self.small_done, self.upgraded, self.locked = set(), set(indices), set()

    def check_time(self):
        if self.deadline is not None and time.monotonic() >= self.deadline:
            raise TimeoutError('Reacquisition budget exhausted')

    def fill(self, i, large=False):
        self.check_time()
        if large and (i in self.upgraded or i in self.locked):
            return
        if not large and (i in self.small_done or i in self.upgraded):
            return
        self.rows[i] = (self.large_detect if large else self.small_detect)(i)
        hsv = cv2.cvtColor(self.frames[i]['image'], cv2.COLOR_BGR2HSV)
        self.histograms[i] = []
        for row in self.rows[i]:
            h = cv2.calcHist([hsv], [0,1], contours.measured_mask(row), [24,16], [0,180,0,256])
            self.histograms[i].append(cv2.normalize(h,None,norm_type=cv2.NORM_L1))
        # A pair depends only on its source/destination detections and fixed
        # decoded frames. Updating another frame cannot change its flow/votes.
        # Invalidate both directions involving this frame; retain all others.
        for key in list(self.pair_cache):
            if i in key[:2]:
                del self.pair_cache[key]
        (self.upgraded if large else self.small_done).add(i)

    def candidate(self, a, b, j, history):
        self.fill(b)
        k = self.feature_link(a,b,j)
        if k is not None:
            return k, 'FEATURES'
        result = self.motion_link(history,b)
        return (result[0], 'MOTION_ASSOCIATION') if result else (None,None)

    def follow(self, seed_number):
        si, source = self.indices[seed_number], self.sources[seed_number]
        if source is None:
            return {}, []
        result, events = {si:source}, []
        lo,hi = min(self.indices),max(self.indices)
        for direction in (-1,1):
            a,j,history = si,source,[(si,source)]
            cursor,last_upgrade = si+direction,None
            while lo <= cursor <= hi:
                self.check_time()
                if abs(self.frames[cursor]['media_ms']-self.frames[a]['media_ms']) > self.MAX_GAP_MS:
                    break
                b,k,kind = cursor,None,None
                far = cursor+direction
                if lo <= far <= hi and abs(self.frames[far]['media_ms']-self.frames[a]['media_ms']) <= self.MAX_GAP_MS:
                    k,kind = self.candidate(a,far,j,history)
                if k is not None:
                    b = far
                else:
                    k,kind = self.candidate(a,b,j,history)
                if (k is None and (last_upgrade is None or abs(self.frames[b]['media_ms']-last_upgrade) >= 200)
                        and b not in self.upgraded and b not in self.locked):
                    self.fill(b,True)
                    last_upgrade = self.frames[b]['media_ms']
                    k,kind = self.candidate(a,b,j,history)
                if k is None:
                    cursor += direction
                    continue
                result[b] = k
                events.append({'from_index':a,'to_index':b,'kind':kind})
                history.append((b,k))
                a,j,cursor = b,k,b+direction
        self.locked.update(result)
        return result,events


def segments_for_review(engine, review, observations):
    """Bind both original selections to observations before admitting middle marks."""
    if not review['identity_link_passed_on_this_clip']:
        return []
    references = []
    for i,j in zip(engine.indices,engine.sources):
        nearby = [s for s in observations if s.get('ground') and
                  abs(s['media_ms']-engine.frames[i]['media_ms']) <= 40]
        if not nearby or any(not contours.agrees_with_observation(engine.rows[i][j],s,engine.shape) for s in nearby):
            return []
        references.append(nearby[0]['frame_id'])
    groups = []
    for sample in review['samples']:
        if sample['ground'] is None:
            continue
        if not groups or sample['media_ms']-groups[-1][-1]['media_ms'] > 200:
            groups.append([])
        i = next(i for i,f in enumerate(engine.frames) if f['media_ms']==sample['media_ms'])
        row = engine.rows[i][sample['detection_index']]
        groups[-1].append({k:sample[k] for k in ('media_ms','ground','player_width')} | {'confidence':row['confidence']})
    return [{'id':f'reacquired:{n}','reference_frame':references[0],
             'identity_reference_frames':references,'seed_ms':[engine.frames[i]['media_ms'] for i in engine.indices],
             'overlap_frames':review['shared_frames'],'ground_method':'LOWER_VISIBLE_CONTOUR',
             'presentation_gap_ms':200,'samples':group}
            for n,group in enumerate(groups) if len(group)>=3]


def reacquire(video, seeds, observations, small_segmenter, small_roi, deadline, diagnostic):
    from native_player_segmentation import PersonSegmenter
    from player_segmentation_assets import ensure_model_asset
    start,end = [round(s['t']*1000) for s in seeds]
    frames = list(contours.read_clip(video,start-25,end+25))
    if len(frames)<3:
        return []
    indices = [min(range(len(frames)),key=lambda i:abs(frames[i]['media_ms']-s['t']*1000)) for s in seeds]
    if any(abs(frames[i]['media_ms']-s['t']*1000)>25 for i,s in zip(indices,seeds)):
        return []
    # All source frames, including those without inference, must pass cut/time checks.
    for a,b in zip(frames,frames[1:]):
        if not 0 < b['media_ms']-a['media_ms'] <=75:
            return []
        if cv2.absdiff(cv2.resize(a['gray'],(160,90)),cv2.resize(b['gray'],(160,90))).mean()>45:
            return []
    # Validate the source before loading the expensive recovery model. These
    # gates do not depend on predictions; failed clips cannot reach inference.
    if deadline is not None and time.monotonic() >= deadline:
        raise TimeoutError('Recovery deadline expired before model loading')
    ensure_model_asset(MODEL_PATH,MODEL_SHA256)
    large = PersonSegmenter.__new__(PersonSegmenter)
    large.net = cv2.dnn.readNetFromONNX(str(MODEL_PATH))
    roi,cache,attempts = contours.select_seed_view([frames[i] for i in indices],seeds,large,deadline=deadline)
    diagnostic['reacquisition_views'] = attempts
    if roi is None:
        return []
    def large_detect(i):
        return cache.get(frames[i]['media_ms']) or contours.detect_frame(frames[i],roi,large)
    engine = AdaptiveAssociator(frames,indices,[s['target_point'] for s in seeds],
        lambda i: contours.detect_frame(frames[i],small_roi,small_segmenter),large_detect,deadline)
    review = engine.review()
    diagnostic.update(reacquisition_paths=[len(p) for p in review['paths']],
                      shared_frames=review['shared_frames'],small_frames=len(engine.small_done),large_frames=len(engine.upgraded))
    return segments_for_review(engine,review,observations)
