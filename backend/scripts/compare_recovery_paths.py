"""Compare complete adaptive decisions on identical real frames and seed points."""
import argparse, hashlib, json, os, time
from pathlib import Path
import cv2
import numpy as np
from native_player_segmentation import PersonSegmenter
from match_room_inference import OnnxCpuNet
from match_room_reacquisition import AdaptiveAssociator, MODEL_PATH, MODEL_SHA256
from player_segmentation_assets import ensure_model_asset
import match_room_contours as contours


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('video',type=Path);p.add_argument('output',type=Path)
    args=p.parse_args();os.sched_setaffinity(0,{min(os.sched_getaffinity(0))});cv2.setNumThreads(2)
    frames=list(contours.read_clip(str(args.video),49440,49650,sample_step=0))
    if len(frames)<5:raise ValueError('Insufficient source frames')
    ensure_model_asset(MODEL_PATH,MODEL_SHA256)
    os.environ['SCOUTMEPLAY_MATCHROOM_ENGINE']='onnxruntime'
    small=PersonSegmenter()
    def detect(model):
        return [contours.detect_frame(f,(0,0,f['gray'].shape[1],f['gray'].shape[0]),model) for f in frames]
    small_rows=detect(small);large_rows={};times={}
    for name in ('opencv','onnxruntime'):
        model=PersonSegmenter.__new__(PersonSegmenter)
        model.net=cv2.dnn.readNetFromONNX(str(MODEL_PATH)) if name=='opencv' else OnnxCpuNet(MODEL_PATH)
        start=time.perf_counter();large_rows[name]=detect(model);times[name]=time.perf_counter()-start
        print(name+' detections complete',flush=True)
    def targets(index):
        h,w=frames[index]['gray'].shape;result=[]
        for row in large_rows['opencv'][index]:
            mask=contours.measured_mask(row)
            distance=cv2.distanceTransform(mask.astype(np.uint8),cv2.DIST_L2,3)
            y,x=np.unravel_index(distance.argmax(),distance.shape);point={'x':float(x/w),'y':float(y/h)}
            if len(contours.seed_candidates(large_rows['opencv'][index],point,(h,w)))==1:result.append(point)
        return result
    cases=[]
    for a in targets(0):
        for b in targets(-1):
            reviews={};used={}
            for name,rows in large_rows.items():
                engine=AdaptiveAssociator(frames,[0,len(frames)-1],[a,b],lambda i:small_rows[i],lambda i:rows[i])
                reviews[name]=engine.review()
                used[name]={'small':sorted(engine.small_done),'medium':sorted(engine.upgraded)}
            cases.append({'seeds':[a,b],'reviews':reviews,'detection_requests':used,
                          'equal':reviews['opencv']==reviews['onnxruntime'] and used['opencv']==used['onnxruntime']})
    if not cases:raise ValueError('No endpoint workloads')
    with args.video.open('rb') as f:sha=hashlib.file_digest(f,'sha256').hexdigest()
    result={'source_sha256':sha,'medium_model_sha256':MODEL_SHA256,'frame_ms':[f['media_ms'] for f in frames],
            'medium_detection_seconds':times,'cases':cases,'all_decisions_equal':all(c['equal'] for c in cases),
            'scope':'Offline adaptive review with baseline-derived endpoint combinations, not verified player identity or production deadline/segment parity.'}
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'cases':len(cases),'equal':result['all_decisions_equal'],'accepted':sum(c['reviews']['opencv']['identity_link_passed_on_this_clip'] for c in cases)}))

if __name__=='__main__':main()
