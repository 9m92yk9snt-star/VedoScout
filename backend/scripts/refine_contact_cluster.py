"""One unresolved final-touch review; reuse checked source JPEGs and context."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import sequence_pilot as p
import sequence_pilot_transport as t


def cluster_box(pixels, source_box, references, source_height):
    """A pixel-only kit-cluster proposal, not a predicted identity or contact."""
    import cv2
    hsv=cv2.cvtColor(pixels,cv2.COLOR_BGR2HSV)
    mask=(((hsv[:,:,1]<90)&(hsv[:,:,2]>95))|((hsv[:,:,0]>90)&(hsv[:,:,0]<135)&
        (hsv[:,:,1]>80)&(hsv[:,:,2]>75))).astype('uint8')*255
    lo=max(0,int(min(r['box']['y'] for r in references)*source_height)-source_box[1])
    hi=min(pixels.shape[0],int(max(r['box']['y']+r['box']['h'] for r in references)*source_height)-source_box[1])
    mask[:lo]=0;mask[hi:]=0
    mask=cv2.morphologyEx(mask,cv2.MORPH_CLOSE,cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(11,11)))
    _,_,stats,_=cv2.connectedComponentsWithStats(mask)
    rows=[s for s in stats[1:] if .06*source_height<=s[3]<=.25*source_height and s[2]<.7*pixels.shape[1]]
    if not rows:return [0,0,pixels.shape[1],pixels.shape[0]],'FULL_CHECKED_SOURCE_BAND_FALLBACK'
    x,y,w,h,_=map(int,max(rows,key=lambda s:s[4]))
    box=[max(0,x-int(1.2*h)),max(0,y-int(.35*h)),min(pixels.shape[1],x+w+int(1.2*h)),min(pixels.shape[0],y+h+int(.35*h))]
    return box,'LARGEST_WHITE_BLUE_KIT_COMPONENT_WITH_BODY_HEIGHT_MARGIN'


def run(cached, video, profile_path, previous_path, output):
    import cv2
    started,cached,output=time.monotonic(),Path(cached),Path(output)
    previous=p.read_json(previous_path);result0=previous['result']
    prior=result0['prior_native_trial_seconds']+result0['analysis_seconds']+previous['workflow_source_preparation_seconds']
    remaining=max(1.,300.-prior)
    manifest=p.read_json(cached/'sequence-pilot-prepared/manifest.json')
    if p.digest(video)!=manifest['source_video_sha256'] or manifest['source_video_sha256']!=result0['source_video_sha256']:
        raise ValueError('SOURCE_INPUT_MISMATCH')
    questions=[q for q in result0['questions'] if q['reason']=='FINAL_TOUCH_ACTOR_WITHOUT_LOCAL_IDENTITY_MARK'
        and result0['observations'].get(q['packet_id'],{}).get('outcome',{}).get('uncertainty')]
    if len(questions)!=1:raise ValueError('ONE_EXPLICIT_UNRESOLVED_FINAL_TOUCH_REQUIRED')
    q=questions[0];pid=q['packet_id'];root=cached/'sequence-pilot-result'
    request=p.read_json(root/'requests'/(pid+'.json'))
    receipt=p.read_json(root/'responses'/(pid+'.json'))
    if (receipt['origin']!='LIVE_MODEL_REQUEST' or receipt['status']!='COMPLETED'
            or receipt['payload_sha256']!=request['audit']['payload_sha256']
            or hashlib.sha256(receipt['raw_response'].encode()).hexdigest()!=receipt['response_sha256']):
        raise ValueError('CACHED_SOURCE_RECEIPT_INVALID')
    profile=p.read_json(profile_path)
    if (profile['source_video_sha256']!=manifest['source_video_sha256'] or
            hashlib.sha256(profile['receipt']['raw_response'].encode()).hexdigest()!=profile['receipt']['response_sha256']):
        raise ValueError('IDENTITY_PROFILE_UNRESOLVED')
    identity=json.loads(profile['receipt']['raw_response']);ids=identity['canonical_reference_ids']
    refs={r['reference_id']:r for r in manifest['references']}
    cap=cv2.VideoCapture(video);height=int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT));width=int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    reference_images=[]
    try:
        for rid in ids:
            r=refs[rid];cap.set(cv2.CAP_PROP_POS_MSEC,max(0,r['media_ms']-100));pixels=None
            for _ in range(12):
                ok,frame=cap.read()
                if not ok:break
                ms=round(cap.get(cv2.CAP_PROP_POS_MSEC))
                if ms==r['media_ms']:pixels=frame;break
                if ms>r['media_ms']:break
            if pixels is None:raise ValueError('EXACT_ORIGINAL_REFERENCE_FRAME_REQUIRED')
            b=r['box'];x,y=int(b['x']*width),int(b['y']*height)
            image=p._save_image(output/'references'/(rid+'.jpg'),pixels[y:math.ceil((b['y']+b['h'])*height),x:math.ceil((b['x']+b['w'])*width)],480,90)
            if image['sha256']!=r['sha256']:raise ValueError('ORIGINAL_REFERENCE_BYTES_CHANGED')
            reference_images.append(image)
    finally:cap.release()
    rows=[]
    for folder,kind in [('overview','overview'),('detail','native detail')]:
        for path in (root/pid/folder).glob('s?????????.jpg'):
            rows.append({'frame_id':path.stem,'media_ms':int(path.stem[1:]),'kind':kind,'path':str(path), 'sha256':p.digest(path)})
    rows.sort(key=lambda f:(f['media_ms'],f['kind']))
    expected=request['audit']['images']
    if [x['sha256'] for x in reference_images]+[r['sha256'] for r in rows]!=[x['sha256'] for x in expected]:
        raise ValueError('CACHED_SOURCE_IMAGE_SEQUENCE_CHANGED')
    detail=[f for f in rows if f['kind']=='native detail']
    focus=min(detail,key=lambda f:abs(f['media_ms']-q['focus_ms']))
    source_box=request['source_crop_box']
    relative,policy=cluster_box(cv2.imread(focus['path']),source_box,manifest['references'],height)
    crop=[source_box[0]+relative[0],source_box[1]+relative[1],source_box[0]+relative[2],source_box[1]+relative[3]]
    items=[{'type':'text','text':
        "Inspect the selected player's release and the final touch in this complete chronological play. "
        "Keep the selected person and any separate teammate as distinct physical people across camera motion. "
        "Native detail is newly cropped from exactly the checked prior source images using a pixel-only "
        "white/blue kit-cluster proposal, with no person identity or football event annotation. The full "
        "8-fps overview is retained unchanged. Compare each person's location, stance, foot swing and the "
        "ball's change of motion before/after occlusion. Proximity alone is not a touch. If the exact "
        "foot-ball instant is hidden, state whether visible before/after motion uniquely establishes "
        "the actor or leaves alternatives. Do not award the recipient's goal to the selected passer. "
        "Return uncertainty when another actor can plausibly have touched the ball. No expected event "
        "type, count, time or outcome is provided. Identity pictures identify the originally selected person. "
        'Return JSON {"selected_player_actions":[{"action":"observed action","before_frame":"s...",'
        '"after_frame":"s...","recipient":"visible person or unknown","evidence":"concrete visible motion",'
        '"uncertainty":"remaining alternatives or empty"}],"final_touch":{"person":"visible person or unknown",'
        '"same_as_selected":null,"before_frame":"s...","after_frame":"s...","evidence":"visible motion",'
        '"uncertainty":"remaining alternatives or empty"},"outcome":{"kind":"observed result or UNKNOWN",'
        '"evidence":"visible active-ball evidence","uncertainty":"remaining alternatives or empty"}}.'}]
    for rid,image in zip(ids,reference_images):items.extend([{'type':'text','text':'Original identity reference '+rid},{'type':'image','path':image['path'],'sha256':image['sha256']}])
    for row in rows:
        image=row
        if row['kind']=='native detail':
            pixels=cv2.imread(row['path']);image=p._save_image(output/'cluster-detail'/(row['frame_id']+'.jpg'),pixels[relative[1]:relative[3],relative[0]:relative[2]],1280,90)
        label=f"Source frame {row['frame_id']}, source_ms={row['media_ms']}, {row['kind']}"
        if row['kind']=='native detail':label+=', source pixel crop='+json.dumps(crop)+', parent JPEG sha256='+row['sha256']
        items.extend([{'type':'text','text':label},{'type':'image','path':image['path'],'sha256':image['sha256']}])
    _,_,audit=t.build_request('emergent','gemini-3.8-flash',items,reasoning_effort='low',image_detail='high')
    result={'status':'SOURCE_CLUSTER_FINAL_TOUCH_PROBE','target_events':[], 'production_pipeline_changed':False,
        'expected_answers_used_as_input':False,'independent_visual_correctness_verified':False,
        'source_video_sha256':manifest['source_video_sha256'],'source_packet_id':pid,'question':q,
        'cached_source_payload_sha256':receipt['payload_sha256'],'source_images_verified_in_original_order':True,
        'crop_policy':policy,'source_crop_box':crop,'request_audit':audit,'accounted_prior_seconds':prior,
        'unchanged_overview_instants':sum(r['kind']=='overview' for r in rows), 'new_detail_instants':len(detail),
        'cached_source_manifest_sha256':p.digest(cached/'sequence-pilot-prepared/manifest.json'),
        'remaining_budget_seconds':remaining,'preparation_seconds':round(time.monotonic()-started,3)}
    p.write_json(output/'result.json',result)
    response=t.run_jobs([{'packet_id':pid,'items':items,'reasoning_effort':'low','image_detail':'high'}],
        'emergent','gemini-3.8-flash',deadline=started+remaining,per_call_s=min(120,remaining))[0]
    p.write_json(output/'responses'/(pid+'.json'),response)
    if response['status']=='COMPLETED':result['observations']=json.loads(response['raw_response'])
    result.update(model_status=response['status'],analysis_seconds=round(time.monotonic()-started,3))
    p.write_json(output/'result.json',result);return result


if __name__=='__main__':
    cli=argparse.ArgumentParser(description=__doc__)
    for flag in ('cached','video','profile','previous','output'):cli.add_argument('--'+flag,required=True)
    a=cli.parse_args();r=run(a.cached,a.video,a.profile,a.previous,a.output)
    raise SystemExit(0 if r['model_status']=='COMPLETED' else 3)
