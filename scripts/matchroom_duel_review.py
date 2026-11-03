"""Offline duel-association experiment. Not imported by the report worker.

Run from a repository checkout with --video, --seeds (two original anchors),
--model, --model-sha256 and --output. A local model is supplied explicitly;
this script never downloads a model or calls a provider.

The appearance and motion gates below are experimental, not calibrated for
arbitrary matches. A successful identity link is not approval of every foot
position, nor permission to interpolate missing silhouettes.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
import match_room_contours as contours


class ReviewAssociator:
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
                        votes.append((sum(contours.owns(dst, point) for point in q), k))
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
        consecutive = any(shared[n:n+5] == list(range(shared[n], shared[n]+5))
                          for n in range(max(0, len(shared)-4)))
        passed = None not in self.sources and reaches and consecutive and not conflicts
        chosen = {i: paths[0].get(i, paths[1].get(i)) for i in sorted(set(paths[0]) | set(paths[1]))}
        return {'identity_link_passed_on_this_clip': passed, 'paths': paths,
                'shared_frames': len(shared), 'conflict_indices': conflicts,
                'events': [e for _, e in paths_and_events],
                'samples': [{'media_ms': self.frames[i]['media_ms'], 'detection_index': j,
                             'ground': self.rows[i][j]['ground'],
                             'player_width': self.rows[i][j]['player_width']}
                            for i, j in chosen.items()] if passed else []}

    def negative_controls(self):
        """Rebuild both appearance references for every deliberately wrong tap."""
        output = []
        height, width = self.shape
        for side, i in enumerate(self.indices):
            for j, row in enumerate(self.rows[i]):
                if j == self.sources[side]:
                    continue
                mask = contours.measured_mask(row).copy()
                for k, other in enumerate(self.rows[i]):
                    if k != j:
                        mask[contours.measured_mask(other) > 0] = 0
                distance = cv2.distanceTransform(mask, cv2.DIST_L2, 5)
                y, x = np.unravel_index(np.argmax(distance), distance.shape)
                if distance[y, x] <= 0:
                    output.append({'side': side, 'detection': j, 'status': 'NO_UNIQUE_INTERIOR'})
                    continue
                targets = list(self.targets)
                targets[side] = {'x': float(x/width), 'y': float(y/height)}
                trial = ReviewAssociator(self.frames, self.rows, self.indices, targets).review()
                output.append({'side': side, 'detection': j, 'target': targets[side],
                               'status': 'REJECTED' if not trial['identity_link_passed_on_this_clip'] else 'FALSE_ACCEPT',
                               'path_frames': [len(p) for p in trial['paths']],
                               'shared_frames': trial['shared_frames'],
                               'conflict_indices': trial['conflict_indices']})
        return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('video', 'seeds', 'model', 'model-sha256', 'output'):
        parser.add_argument('--'+name, required=True)
    parser.add_argument('--negative-controls', action='store_true')
    args = parser.parse_args()
    cv2.setNumThreads(2)
    model = Path(args.model)
    if hashlib.sha256(model.read_bytes()).hexdigest() != args.model_sha256:
        raise ValueError('Review model checksum mismatch')
    seeds = sorted(json.loads(Path(args.seeds).read_text()), key=lambda s: s['t'])
    if len(seeds) != 2 or not .15 <= seeds[1]['t']-seeds[0]['t'] <= 2.5:
        raise ValueError('Exactly two nearby original taps are required')
    frames = list(contours.read_clip(args.video, round(seeds[0]['t']*1000)-330,
                                    round(seeds[1]['t']*1000)+330))
    indices = [min(range(len(frames)), key=lambda i: abs(frames[i]['media_ms']-s['t']*1000)) for s in seeds]
    if any(abs(frames[i]['media_ms']-s['t']*1000) > 25 for i, s in zip(indices, seeds)):
        raise ValueError('Original tap source frame unavailable')
    from native_player_segmentation import PersonSegmenter
    segmenter = PersonSegmenter.__new__(PersonSegmenter)
    segmenter.net = cv2.dnn.readNetFromONNX(str(model))
    roi, cached, attempts = contours.select_seed_view([frames[i] for i in indices], seeds, segmenter)
    if roi is None:
        raise ValueError('Ambiguous source tap')
    rows = [cached.get(f['media_ms']) or contours.detect_frame(f, roi, segmenter) for f in frames]
    associator = ReviewAssociator(frames, rows, indices, [s['target_point'] for s in seeds])
    result = associator.review()
    if args.negative_controls:
        result['negative_controls'] = associator.negative_controls()
    result.update(status='OFFLINE_EXPERIMENT_NOT_PRODUCTION', seed_views=attempts,
                  source_sha256=hashlib.sha256(Path(args.video).read_bytes()).hexdigest(),
                  model_sha256=args.model_sha256, original_seeds=seeds)
    Path(args.output).write_text(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
