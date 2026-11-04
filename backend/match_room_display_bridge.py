"""Camera-corrected presentation between independently identified endpoints.

Reuses the approved fall preview algorithm. Positions between endpoints are
presentation estimates, never source observations or identity evidence.
The caller must bind endpoint identity and measured camera transforms.
"""
import numpy as np


def display_bridge(media_ms, camera_from_reference, stable_start, stable_end,
                   incoming_per_ms, outgoing_per_ms):
    times = np.asarray(media_ms, dtype=float)
    camera = np.asarray(camera_from_reference, dtype=float)
    start, end = np.asarray(stable_start, dtype=float), np.asarray(stable_end, dtype=float)
    before, after = np.asarray(incoming_per_ms, dtype=float), np.asarray(outgoing_per_ms, dtype=float)
    if (times.ndim != 1 or len(times) < 2 or camera.shape != (len(times),3,3)
            or any(p.shape != (2,) for p in (start,end,before,after))
            or not all(np.isfinite(a).all() for a in (times,camera,start,end,before,after))
            or np.any(np.diff(times) <= 0) or np.any(np.diff(times) > 75)
            or not 0 < times[-1]-times[0] <= 800
            or not np.allclose(camera[:,2,:], [0,0,1])
            or np.any(np.abs(np.linalg.det(camera[:,:2,:2])) < 1e-8)):
        raise ValueError('Unsupported presentation bridge')
    duration = times[-1]-times[0]
    delta = end-start
    tangents = [before.copy()*duration, after.copy()*duration]
    # Preserve the measured endpoints; avoid overshoot when pose changes.
    for v in tangents:
        for axis in (0,1):
            if abs(delta[axis]) < 1e-8 or v[axis]*delta[axis] <= 0:
                v[axis] = 0
            else:
                v[axis] = np.sign(delta[axis])*min(abs(v[axis]),3*abs(delta[axis]))
    result = []
    for stamp,matrix in zip(times,camera):
        u = (stamp-times[0])/duration
        stable = ((2*u**3-3*u**2+1)*start + (u**3-2*u**2+u)*tangents[0]
                  + (-2*u**3+3*u**2)*end + (u**3-u**2)*tangents[1])
        pixel = (matrix @ np.r_[stable,1])[:2]
        result.append({'media_ms': int(stamp), 'display_position_px': pixel.tolist(),
                       'display_estimated': bool(times[0] < stamp < times[-1]),
                       'source_ground_observation': False})
    return {'kind': 'REVIEW_ONLY_CAMERA_SPACE_DISPLAY', 'samples': result,
            'report_identity_approved': False}


def tracked_display_positions(frames, detections, interval, *, deadline):
    """Use the approved display curve only inside a caller-verified identity path.

    The source ground stays absent. Measured masks and both independently bound
    paths remain mandatory on every frame. Camera failure rejects the bridge.
    """
    import time
    from motion_compensation import estimate_camera

    indices, owners = interval['indices'], interval['instances']
    selected = [dict(detections[i][j]) for i, j in zip(indices, owners)]
    endpoints = interval.get('source_endpoint_ground') or {}
    for k, i in enumerate(indices):
        if i in endpoints:
            selected[k]['ground'] = endpoints[i]
    if not endpoints and all(row.get('ground') is not None for row in selected):
        return {}
    if selected[0].get('ground') is None or selected[-1].get('ground') is None:
        return None
    cameras = [np.eye(3)]
    for ai, bi in zip(indices, indices[1:]):
        if time.monotonic() >= deadline-1:
            return None
        # Every detected person is excluded from the background estimate.
        matrix, _ = estimate_camera(frames[ai]['gray'], frames[bi]['gray'],
                                    [r['box'] for k in (ai, bi) for r in detections[k]])
        if matrix is None:
            return None
        cameras.append(np.vstack([matrix, [0, 0, 1]]) @ cameras[-1])
    h, w = frames[indices[0]]['gray'].shape
    stable = {k: (np.linalg.inv(cameras[k]) @ np.r_[np.array(r['ground'])*[w,h], 1])[:2]
              for k, r in enumerate(selected) if r.get('ground') is not None}
    result = {i: {'display_ground': point, 'display_estimated': True,
                  'display_origin': 'BOUND_SOURCE_OBSERVATION', 'source_ground_observation': False}
              for i, point in endpoints.items()}
    measured = list(stable)
    for a, b in zip(measured, measured[1:]):
        if b == a+1:
            continue
        stamps = [frames[indices[k]]['media_ms'] for k in range(a, b+1)]
        # Measured neighbours supply endpoint velocity; the endpoint secant is
        # the fallback at a window edge. The shared curve bounds overshoot.
        def velocity(x, y):
            return (stable[y]-stable[x])/(frames[indices[y]]['media_ms']-frames[indices[x]]['media_ms'])
        incoming = velocity(a-1, a) if a-1 in stable else velocity(a, b)
        outgoing = velocity(b, b+1) if b+1 in stable else velocity(a, b)
        try:
            bridge = display_bridge(stamps, cameras[a:b+1], stable[a], stable[b], incoming, outgoing)
        except ValueError:
            return None
        for k, sample in zip(range(a, b+1), bridge['samples']):
            if k in stable:
                continue
            point = np.array(sample['display_position_px'])/[w,h]
            if not np.isfinite(point).all() or (point < 0).any() or (point > 1).any():
                return None
            result[indices[k]] = {'display_ground': point.tolist(), 'display_estimated': True,
                                  'source_ground_observation': False}
    return result
