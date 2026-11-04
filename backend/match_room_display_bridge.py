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
