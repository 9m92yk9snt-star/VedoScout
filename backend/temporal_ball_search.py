"""Native appearance proposals through a short loss, never ball/event proof.

Unlike semantic detection, admission here does not require a class-32 score.
The known contact ball supplies appearance and size. Independent classification
and geometry still decide whether a proposed reappearance can certify a goal.
"""
from copy import deepcopy
import math
import re

import native_ball_reappearance as native

MAX_FRAMES = 56
MAX_POINTS = 320
MAX_PROPOSALS = 192
MAX_TRACKS = 480
MIN_SEARCH_SIMILARITY = .66
SCALES = (.4, .55, .75, 1., 1.3)


def _matrix(value):
    import numpy as np
    if not isinstance(value, dict) or value.get('status') != 'MEASURED':
        return None
    try:
        a = np.asarray(value['affine_to_reference'], dtype=float)
        if a.shape != (2, 3) or not np.isfinite(a).all() or np.linalg.det(a[:, :2]) <= 0:
            return None
        s = np.linalg.svd(a[:, :2], compute_uv=False)
        return a if .5 <= s.min() <= s.max() <= 2 else None
    except (KeyError, TypeError, ValueError, np.linalg.LinAlgError):
        return None


def _proposals(image, references, before_box,reference_patches):
    import cv2
    import numpy as np
    h, w = image.shape[:2]
    # A generic band around the original contact height, across the image.
    # No user circle, goal label or hard-coded event coordinate selects pixels.
    cy = (before_box['y'] + before_box['h']/2)*h
    cx = (before_box['x'] + before_box['w']/2)*w
    x_start, x_end = max(0,int(cx-.30*w)), min(w,int(cx+.30*w))
    y0, y1 = max(0, int(cy-.20*h)), min(h, int(cy+.20*h))
    region = image[y0:y1,x_start:x_end]
    gray = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY).astype(np.float32)
    diameter = max(before_box['w']*w, before_box['h']*h)
    proposals = []
    seen_sizes, seen_boxes = set(), set()
    for scale in SCALES:
        side = max(6, round(diameter*scale))
        # Several requested scales round to the same native size for a small
        # ball. They inspect exactly the same pixels and are not extra evidence.
        if side in seen_sizes:
            continue
        seen_sizes.add(side)
        sigma = max(1., side/5)
        # Bright local blobs, including blurred/partially exposed candidates.
        small = cv2.GaussianBlur(gray, (0, 0), sigma*.55)
        large = cv2.GaussianBlur(gray, (0, 0), sigma*1.15)
        # A partly exposed shaded ball can be a dark blob. Both contrast signs
        # are search candidates; neither becomes a semantic ball detection.
        response = np.abs(small-large)
        # Correlation searches patch texture as well as blob extrema. A partly
        # exposed ball need not have a brightness maximum at its centre.
        correlations=[]
        seen_templates=set()
        for patch in reference_patches:
            template=cv2.resize(cv2.cvtColor(patch,cv2.COLOR_BGR2GRAY),(side,side),interpolation=cv2.INTER_AREA).astype(np.float32)
            if float(template.std())<5:continue
            key=template.tobytes()
            if key in seen_templates:continue
            seen_templates.add(key)
            correlations.append(cv2.matchTemplate(gray,template,cv2.TM_CCOEFF_NORMED))
        correlation=np.maximum.reduce(correlations) if correlations else None
        maximum = cv2.dilate(response, np.ones((max(3, side//2),)*2, np.uint8))
        yy, xx = np.where((response >= maximum-1e-5) & (response > 1.))
        if correlation is not None:
            peaks=cv2.dilate(correlation,np.ones((max(3,side//2),)*2,np.uint8))
            ty,tx=np.where((correlation>=peaks-1e-5)&(correlation>.4))
            # Keep texture peaks alongside contrast peaks with finite scores.
            yy=np.concatenate([yy,ty+side//2]);xx=np.concatenate([xx,tx+side//2])
        rank_response=response.copy()
        if correlation is not None:
            offset=side//2
            rank_response[offset:offset+correlation.shape[0],offset:offset+correlation.shape[1]]+=np.maximum(correlation,0)*24
        # Preserve spatial coverage: bright clothes in one corner must not
        # consume every peak slot and hide a small low-contrast ball elsewhere.
        order=[]
        for cell_y in range(4):
            for cell_x in range(8):
                inside=np.flatnonzero((xx>=cell_x*region.shape[1]/8)&(xx<(cell_x+1)*region.shape[1]/8)
                    &(yy>=cell_y*region.shape[0]/4)&(yy<(cell_y+1)*region.shape[0]/4))
                order.extend(inside[np.argsort(-rank_response[yy[inside],xx[inside]],kind='stable')[:MAX_POINTS//32]])
        for index in order:
            x, y = int(xx[index])+x_start, int(yy[index])+y0
            x0, py0 = x-side//2, y-side//2
            if x0 < 0 or py0 < 0 or x0+side > w or py0+side > h:
                continue
            key=(x0,py0,side)
            if key in seen_boxes:continue
            seen_boxes.add(key)
            patch = image[py0:py0+side, x0:x0+side]
            descriptor = native._descriptor(patch)
            if descriptor is None:
                continue
            score = max(float(np.clip(np.dot(reference, descriptor), -1., 1.)) for reference in references)
            if score < MIN_SEARCH_SIMILARITY:
                continue
            proposals.append({'box':{'x':x0/w, 'y':py0/h, 'w':side/w, 'h':side/h},
                'appearance_similarity':score, 'local_blob_response':float(response[yy[index], xx[index]]),
                'native_pixel_sha256':native._sha(patch),
                'source':'NATIVE_APPEARANCE_SEARCH', 'state':'SEARCH_ONLY', 'proof_eligible':False})
    # Competing pixels are retained. Multiple crop scales at the same blob
    # cannot fabricate independent observations or independent candidates.
    proposals.sort(key=lambda p: (-p['appearance_similarity'], -p['local_blob_response'], p['box']['x']))
    kept,cell_counts = [],{}
    for p in proposals:
        b = p['box']; center = ((b['x']+b['w']/2)*w, (b['y']+b['h']/2)*h)
        if any(math.dist(center, ((q['box']['x']+q['box']['w']/2)*w,
                    (q['box']['y']+q['box']['h']/2)*h)) < .45*max(b['w']*w, q['box']['w']*w)
               for q in kept):
            continue
        cell=(int((center[0]-x_start)*8/max(region.shape[1],1)),int((center[1]-y0)*4/max(region.shape[0],1)))
        if cell_counts.get(cell,0)>=MAX_PROPOSALS//32:continue
        kept.append(p)
        cell_counts[cell]=cell_counts.get(cell,0)+1
        if len(kept) >= MAX_PROPOSALS:
            break
    return kept


def search(before, frames_by_ms, alignments, *, video_sha256,reference_history=()):
    """Return unclassified pixel candidates and review times, not a certificate."""
    import numpy as np
    empty = {'status':'SEARCH_ONLY', 'source':'TEMPORAL_NATIVE_APPEARANCE_SEARCH',
             'proof_eligible':False, 'canonical_events_applied':0,
             'rows':[], 'candidate_tracks':[], 'suggested_review_ms':[]}
    if not (native._verified_time(before) and before.get('proof_eligible') is True
            and before.get('state') == 'MEASURED' and native.box_ok(before.get('box'))
            and isinstance(frames_by_ms, dict) and isinstance(alignments, dict)
            and isinstance(video_sha256, str) and re.fullmatch(r'[0-9a-f]{64}',video_sha256)):
        return {**empty, 'reason':'TEMPORAL_SEARCH_REFERENCE_INVALID'}
    if any(type(ms) is not int for ms in frames_by_ms):
        return {**empty, 'reason':'TEMPORAL_SEARCH_TIME_COVERAGE_INVALID'}
    times = sorted(frames_by_ms)
    if (not times or len(times)>MAX_FRAMES or times[0]!=before['media_ms']
            or any(type(ms) is not int or not 0<=ms-times[0]<=native.MAX_GAP_MS for ms in times)):
        return {**empty, 'reason':'TEMPORAL_SEARCH_TIME_COVERAGE_INVALID'}
    first = frames_by_ms[times[0]]
    if not isinstance(first,np.ndarray) or first.dtype!=np.uint8 or first.ndim!=3 or first.shape[2]!=3:
        return {**empty, 'reason':'TEMPORAL_SEARCH_NATIVE_PIXELS_MISSING'}
    patch = native._crop(first,before['box'])
    descriptor = native._descriptor(patch) if patch is not None else None
    if descriptor is None:
        return {**empty, 'reason':'TEMPORAL_SEARCH_REFERENCE_UNINFORMATIVE'}
    references=[descriptor]
    reference_patches=[patch]
    history_audit=[]
    for entry in list(reference_history)[:6]:
        if not isinstance(entry,(list,tuple)) or len(entry)!=2:continue
        row,image=entry
        if (not native._verified_time(row) or row.get('proof_eligible') is not True
                or row.get('state')!='MEASURED' or row.get('scene_id')!=before.get('scene_id')
                or not before['media_ms']-500<=row['media_ms']<before['media_ms']
                or not isinstance(image,np.ndarray) or image.shape!=first.shape or image.dtype!=np.uint8):continue
        crop=native._crop(image,row.get('box'))
        vector=native._descriptor(crop) if crop is not None else None
        if vector is not None:
            references.append(vector)
            reference_patches.append(crop)
            history_audit.append({'media_ms':row['media_ms'],'crop_sha256':native._sha(crop)})
    h,w = first.shape[:2]
    paths, rows = [], []
    for ms in times[1:]:
        image = frames_by_ms[ms]
        alignment = alignments.get(str(ms))
        matrix = _matrix(alignment)
        if (not isinstance(image,np.ndarray) or image.dtype!=np.uint8 or image.shape!=first.shape
                or matrix is None or alignment.get('reference_media_ms')!=times[0]):
            return {**empty,'rows':rows, 'reason':'TEMPORAL_SEARCH_SOURCE_OR_CAMERA_INVALID'}
        proposals = _proposals(image,references,before['box'],reference_patches)
        for p in proposals:
            b=p['box']; center=np.array([(b['x']+b['w']/2)*w,(b['y']+b['h']/2)*h,1.])
            p.update(media_ms=ms,scene_id=before.get('scene_id'),time_authority='ACTUAL_MEDIA_PTS',
                     reference_center=(matrix@center).tolist())
        rows.append({'media_ms':ms,'source_bgr_pixel_sha256':native._sha(image),'proposals':proposals})
        pairs=[]
        for i,path in enumerate(paths):
            if not 0 < ms-path[-1]['media_ms'] <= 80:
                continue
            previous=path[-1]
            for j,p in enumerate(proposals):
                diameter=max(p['box']['w']*w,previous['box']['w']*w)
                distance=math.dist(p['reference_center'],previous['reference_center'])
                horizon=math.sqrt((ms-previous['media_ms'])/(1000/60))
                if distance <= max(5.,diameter*.85*horizon):
                    pairs.append((distance/max(diameter,1.),i,j))
        # Bidirectional nearest assignment avoids merging nearby candidate
        # tracks. Association uncertainty remains visible, never ball identity.
        pairs.sort()
        best_paths,best_proposals={},{}
        for _distance,i,j in pairs:
            best_paths.setdefault(j,i)
            best_proposals.setdefault(i,j)
        used_paths,used_proposals=set(),set()
        for distance,i,j in pairs:
            if i in used_paths or j in used_proposals:
                continue
            if best_paths[j]!=i or best_proposals[i]!=j:
                continue
            paths[i].append(proposals[j]);used_paths.add(i);used_proposals.add(j)
        for j,p in enumerate(proposals):
            if j not in used_proposals:
                paths.append([p])
        # Trim expired short search fragments only; never overwrite a complete
        # competing path. Budget saturation cannot be silently called a PASS.
        paths=[p for p in paths if len(p)>=3 or ms-p[-1]['media_ms']<=80]
        if len(paths)>MAX_TRACKS:
            return {**empty,'rows':rows,'reason':'TEMPORAL_SEARCH_CANDIDATE_BUDGET_EXCEEDED'}
    tracks=[]
    for i,path in enumerate(paths):
        span=path[-1]['media_ms']-path[0]['media_ms']
        if len(path)<3 or span<80:
            continue
        centers=[p['reference_center'] for p in path]
        diameter=float(np.median([p['box']['w']*w for p in path]))
        motion=max(math.dist(centers[0],p) for p in centers)/max(diameter,1.)
        moving_fraction=sum(math.dist(a,b)>.05*diameter for a,b in zip(centers,centers[1:]))/max(len(centers)-1,1)
        tracks.append({'track_id':f'appearance-{i}','observations':deepcopy(path),
            'span_ms':span,'motion_diameters':motion,'moving_fraction':moving_fraction,
            'median_appearance_similarity':float(np.median([p['appearance_similarity'] for p in path])),
            'classification_status':'UNCLASSIFIED','proof_eligible':False})
    moving=[t for t in tracks if t['motion_diameters']>=.5 and t['moving_fraction']>=.5]
    moving.sort(key=lambda t:(-t['median_appearance_similarity'],-t['span_ms'],t['track_id']))
    picks=[]
    for track in moving[:2]:
        observations=track['observations']
        picks.extend(observations[i]['media_ms'] for i in (0,len(observations)//2,len(observations)-1))
    return {**empty,'rows':rows,'candidate_tracks':tracks,'suggested_review_ms':sorted(set(picks)),
        'reference_media_ms':times[0],'source_video_sha256':video_sha256,
        'reference_history':history_audit,
        'reference_crop_sha256':native._sha(patch),
        'reason':'TEMPORAL_CANDIDATES_REQUIRE_INDEPENDENT_BALL_AND_GOAL_REVIEW'}
