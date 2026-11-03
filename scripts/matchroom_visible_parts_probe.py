"""Offline visible-part bridge audit; deliberately not a report tracking method.

Tracks original source features without replenishing them across intermediate
frames. A plausible moving point or a prompt mask is never identity evidence on
its own. Both directions must land uniquely on the opposite measured instance.
The returned evidence is diagnostic only: no masks, feet or display points are
created. Call audit_bridge with decoded source frames and measured row lists.
"""
from pathlib import Path
import sys
import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
import match_room_contours as contours


def trace_parts(frames, rows, start, selected, end):
    mask = cv2.erode(contours.measured_mask(rows[start][selected]),
                     np.ones((3, 3), np.uint8))
    points = cv2.goodFeaturesToTrack(frames[start]['gray'], 200, .005, 3, mask=mask)
    initial = 0 if points is None else len(points)
    records = []
    if points is None or start == end:
        return {'initial': initial, 'records': records, 'endpoint_votes': []}
    direction = 1 if end > start else -1
    for i in range(start + direction, end + direction, direction):
        previous = frames[i-direction]
        current = frames[i]
        if not 0 < abs(current['media_ms']-previous['media_ms']) <= 75:
            break
        if cv2.absdiff(cv2.resize(previous['gray'], (160,90)),
                       cv2.resize(current['gray'], (160,90))).mean() > 45:
            break
        q, status, error = cv2.calcOpticalFlowPyrLK(
            previous['gray'], current['gray'], points, None, winSize=(21,21), maxLevel=3)
        if q is None or status is None or error is None:
            break
        back, reverse, _ = cv2.calcOpticalFlowPyrLK(
            current['gray'], previous['gray'], q, None, winSize=(21,21), maxLevel=3)
        if back is None or reverse is None:
            break
        valid = ((status[:,0] > 0) & (reverse[:,0] > 0) &
                 (np.linalg.norm(points[:,0]-back[:,0], axis=1) < 1.5) &
                 (error[:,0] < 30))
        points = q[valid]
        votes = sorted([(int(sum(contours.owns(contours.measured_mask(row), p)
                              for p in points[:,0])), k)
                        for k,row in enumerate(rows[i])], reverse=True)
        records.append({'index': i, 'media_ms': current['media_ms'],
                        'surviving': len(points), 'votes': votes})
        if not len(points):
            break
    reached = records and records[-1]['index'] == end
    return {'initial': initial, 'records': records,
            'endpoint_votes': records[-1]['votes'] if reached else []}


def unique_endpoint(trace, expected):
    if not trace['endpoint_votes']:
        return False
    count = next((n for n,k in trace['endpoint_votes'] if k == expected), 0)
    other = max((n for n,k in trace['endpoint_votes'] if k != expected), default=0)
    return (count >= 6 and count >= trace['initial']*.25 and
            count >= trace['records'][-1]['surviving']*.5 and other <= count*.4)


def audit_bridge(frames, rows, start, source, end, destination):
    forward = trace_parts(frames, rows, start, source, end)
    reverse = trace_parts(frames, rows, end, destination, start)
    return {'from_ms': frames[start]['media_ms'], 'to_ms': frames[end]['media_ms'],
            'partial_feature_support': bool(unique_endpoint(forward, destination) and
                                            unique_endpoint(reverse, source)),
            'forward': forward, 'reverse': reverse,
            'report_identity_approved': False}
