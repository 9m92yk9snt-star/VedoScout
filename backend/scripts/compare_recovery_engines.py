"""Compare pinned medium-model outputs across CPU engines; never publish."""
import argparse, hashlib, json, os, time
from pathlib import Path
import cv2
import numpy as np
from native_player_segmentation import PersonSegmenter
from match_room_reacquisition import MODEL_PATH, MODEL_SHA256
from player_segmentation_assets import ensure_model_asset
from match_room_inference import OnnxCpuNet


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('video',type=Path);p.add_argument('output',type=Path)
    args=p.parse_args()
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    cv2.setNumThreads(2)
    ensure_model_asset(MODEL_PATH,MODEL_SHA256)
    models={}
    for name in ('opencv','onnxruntime'):
        model=PersonSegmenter.__new__(PersonSegmenter)
        model.net=cv2.dnn.readNetFromONNX(str(MODEL_PATH)) if name=='opencv' else OnnxCpuNet(MODEL_PATH)
        models[name]=model
    cap=cv2.VideoCapture(str(args.video));records=[]
    try:
        for seconds in (8.75,23.68,30.83,49.44,56.44):
            cap.set(cv2.CAP_PROP_POS_MSEC,seconds*1000)
            ok,image=cap.read()
            if not ok:raise ValueError('Source frame unavailable')
            image=cv2.resize(image,(720,round(image.shape[0]*720/image.shape[1])))
            outputs={};timings={}
            for name,model in models.items():
                started=time.perf_counter();outputs[name]=model.predict(image)
                timings[name]=time.perf_counter()-started
            a,b=outputs.values();equal_count=len(a)==len(b)
            record={'requested_seconds':seconds,'counts':{k:len(v) for k,v in outputs.items()},'seconds':timings,
                    'same_count':equal_count,'mask_pixel_differences':None,'metadata_differences':None}
            if equal_count:
                record['mask_pixel_differences']=sum(int(np.count_nonzero(x['mask']!=y['mask'])) for x,y in zip(a,b))
                record['metadata_differences']=sum({k:v for k,v in x.items() if k!='mask'}!={k:v for k,v in y.items() if k!='mask'} for x,y in zip(a,b))
            record['box_differences']=sum(x['box']!=y['box'] for x,y in zip(a,b)) if equal_count else None
            record['class_differences']=sum(x['class_id']!=y['class_id'] for x,y in zip(a,b)) if equal_count else None
            record['max_score_difference']=max((abs(x['score']-y['score']) for x,y in zip(a,b)),default=0) if equal_count else None
            records.append(record);print(json.dumps(record),flush=True)
    finally:cap.release()
    with args.video.open('rb') as stream:sha=hashlib.file_digest(stream,'sha256').hexdigest()
    result={'source_sha256':sha,'model_sha256':MODEL_SHA256,'frames':records,
            'exact_parity':all(r['same_count'] and r['mask_pixel_differences']==0 and r['metadata_differences']==0 for r in records),
            'scope':'Five fixed real frames; timings include cold effects, no end-to-end speed claim or engine-switch approval.'}
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(result,indent=2)+'\n')

if __name__=='__main__':main()
