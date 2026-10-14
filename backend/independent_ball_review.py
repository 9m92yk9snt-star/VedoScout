"""Source-bound image classifications; never user testimony or event identity.

Normalises the existing independent image reader's classifications. Numeric
detector confidence and local weight hashes are deliberately not invented for
a remote image model. Local pixel re-identification still decides identity.
"""
import hashlib
import json
import re
from pathlib import Path
from copy import deepcopy

import native_ball_reappearance as native

SOURCE='INDEPENDENT_MULTI_FRAME_IMAGE_BALL_CLASSIFICATION'
PROTOCOL='ALL_VISIBLE_BALLS_V1'


def classified(row):
    return bool(isinstance(row,dict) and row.get('classification_source')==SOURCE
        and row.get('source')=='INDEPENDENT_IMAGE_CLASSIFIED_ORIGINAL_PIXELS'
        and row.get('state')=='VISUAL_MEASURED' and row.get('proof_eligible') is False
        and row.get('classifier_confidence')=='high'
        and row.get('classification_provider') in {'openai','LOCAL_NATIVE_CPU'}
        and isinstance(row.get('classification_model'),str) and row['classification_model']
        and all(isinstance(row.get(k),str) and re.fullmatch(r'[0-9a-f]{64}',row[k])
                for k in ('classification_input_sha256','classification_response_sha256','native_pixel_sha256')))


def bound_to_review(row,model_audit):
    """Final gate can recheck the classification source without image decoding."""
    if not classified(row) or not isinstance(model_audit,dict):return False
    raw=model_audit.get('raw_response')
    return bool(isinstance(raw,str)
        and hashlib.sha256(raw.encode()).hexdigest()==row['classification_response_sha256']
        and model_audit.get('response_sha256')==row['classification_response_sha256']
        and model_audit.get('input_sha256')==row['classification_input_sha256']
        and model_audit.get('provider')==row['classification_provider']
        and model_audit.get('model')==row['classification_model'])


def bind_input(review, paths, times, images_by_ms):
    """Bind the reader's encoded inputs to the parent's original native arrays.

    Called inside the provider, while its input files still exist. Any binding
    supplied by a reader is overwritten. No image decoding or model call.
    """
    import numpy as np
    audit=review.get('model_review_audit') if isinstance(review,dict) else None
    if not isinstance(audit,dict) or audit.get('media_ms')!=times or len(paths)!=len(times):return None
    try:encoded=[hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in paths]
    except (OSError,TypeError):return None
    if audit.get('image_sha256')!=encoded:return None
    rows=[]
    for ms,digest in zip(times,encoded):
        image=images_by_ms.get(ms)
        if (not isinstance(image,np.ndarray) or image.dtype!=np.uint8
                or image.ndim!=3 or image.shape[2]!=3):return None
        rows.append({'media_ms':ms,'encoded_input_sha256':digest,
                     'native_bgr_sha256':native._sha(image),'shape':list(image.shape)})
    return {'source':'ORIGINAL_NATIVE_READER_INPUT_BINDING',
            'model_input_sha256':audit.get('input_sha256'),'rows':rows}


def extract(review,images_by_ms,scene_id):
    """Consume only a complete hashed image-classification response."""
    import numpy as np
    if not isinstance(review,dict) or not isinstance(images_by_ms,dict):return None
    audit=review.get('model_review_audit');coverage=review.get('response_coverage')
    binding=review.get('native_reader_input_audit')
    if (not isinstance(audit,dict) or audit.get('provider') not in {'openai','LOCAL_NATIVE_CPU'}
            or not isinstance(audit.get('model'),str) or not audit['model']
            or not isinstance(coverage,dict) or coverage.get('status')!='COMPLETED'):
        return None
    raw=audit.get('raw_response');times=audit.get('media_ms')
    if (not isinstance(raw,str) or not isinstance(times,list) or not times
            or any(type(ms) is not int or ms<0 for ms in times) or times!=sorted(set(times))
            or coverage.get('input_frame_count')!=len(times) or audit.get('response_coordinate_mapping')
            or hashlib.sha256(raw.encode()).hexdigest()!=audit.get('response_sha256')
            or not isinstance(audit.get('input_sha256'),str) or not re.fullmatch(r'[0-9a-f]{64}',audit['input_sha256'])
            or not isinstance(binding,dict) or binding.get('source')!='ORIGINAL_NATIVE_READER_INPUT_BINDING'
            or binding.get('model_input_sha256')!=audit['input_sha256']
            or not isinstance(binding.get('rows'),list) or len(binding['rows'])!=len(times)
            or not isinstance(audit.get('image_sha256'),list) or len(audit['image_sha256'])!=len(times)):
        return None
    for ms,record,encoded in zip(times,binding['rows'],audit['image_sha256']):
        image=images_by_ms.get(ms)
        if (not isinstance(record,dict) or record.get('media_ms')!=ms
                or not isinstance(encoded,str) or not re.fullmatch(r'[0-9a-f]{64}',encoded)
                or record.get('encoded_input_sha256')!=encoded
                or not isinstance(image,np.ndarray) or image.dtype!=np.uint8
                or image.ndim!=3 or image.shape[2]!=3
                or record.get('shape')!=list(image.shape) or record.get('native_bgr_sha256')!=native._sha(image)):
            return None
    try:data=json.loads(raw[raw.index('{'):raw.rindex('}')+1])
    except (ValueError,TypeError):return None
    if not isinstance(data,dict) or data.get('ball_classification_protocol')!=PROTOCOL:return None
    frames=data.get('frames');rows=data.get('ball_evidence')
    if not isinstance(frames,list) or not isinstance(rows,list) or len(frames)!=len(times) or len(rows)!=len(times):return None
    if any(not isinstance(f,dict) or type(f.get('idx')) is not int for f in frames):return None
    if {f['idx'] for f in frames}!=set(range(1,len(times)+1)):return None
    by_ms={};seen=set()
    for row in rows:
        if (not isinstance(row,dict) or type(row.get('idx')) is not int
                or not 1<=row['idx']<=len(times) or row['idx'] in seen
                or row.get('visible_balls_complete') is not True
                or type(row.get('ball_visible')) is not bool
                or not isinstance(row.get('other_visible_balls'),list) or len(row['other_visible_balls'])>8):return None
        seen.add(row['idx']);ms=times[row['idx']-1]
        image=images_by_ms.get(ms)
        if (not isinstance(image,np.ndarray) or image.dtype!=np.uint8 or image.ndim!=3 or image.shape[2]!=3):return None
        primary=[]
        if row['ball_visible']:
            primary=[{'box':row.get('ball_box'),'confidence':row.get('confidence'),'primary':True}]
        boxes=primary+[{**b,'primary':False} for b in row['other_visible_balls'] if isinstance(b,dict)]
        if len(boxes)!=len(primary)+len(row['other_visible_balls']):return None
        detections=[]
        for obj in boxes:
            if obj.get('confidence')!='high' or not native.box_ok(obj.get('box')):return None
            patch=native._crop(image,obj['box'])
            if patch is None:return None
            detections.append({'media_ms':ms,'scene_id':scene_id,'box':dict(obj['box']),
                'class_id':32,'state':'VISUAL_MEASURED','proof_eligible':False,
                'time_authority':'ACTUAL_MEDIA_PTS','used_fallback':False,'cut_barrier':False,
                'source':'INDEPENDENT_IMAGE_CLASSIFIED_ORIGINAL_PIXELS',
                'classification_source':SOURCE,'classifier_confidence':'high',
                'classification_provider':audit['provider'],'classification_model':audit['model'],
                'classification_input_sha256':audit['input_sha256'],
                'classification_response_sha256':audit['response_sha256'],
                'native_pixel_sha256':native._sha(patch),'primary':obj['primary']})
        by_ms[ms]=detections
    return {'rows_by_ms':by_ms,'source':SOURCE,'protocol':PROTOCOL,
            'input_binding':deepcopy(binding),'provider':audit['provider'],'model':audit['model'],
            'input_sha256':audit['input_sha256'],'response_sha256':audit['response_sha256'],
            'confidence_method':'SYMBOLIC_FRAME_CLASSIFICATION_NOT_CALIBRATED_PROBABILITY'}
