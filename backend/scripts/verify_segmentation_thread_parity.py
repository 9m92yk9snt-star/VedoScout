"""Check exact medium-model masks with inherited versus single BLAS thread."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import cv2
import numpy as np
from threadpoolctl import threadpool_info, threadpool_limits


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('video',type=Path)
    p.add_argument('output',type=Path)
    args=p.parse_args()
    os.environ['SCOUTMEPLAY_MATCHROOM_ENGINE']='onnxruntime'
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    cv2.setNumThreads(2)
    from match_room_position_contours import refinement_model
    model=refinement_model()
    threads=next(x['num_threads'] for x in threadpool_info() if x['user_api']=='blas')
    assert threads>1
    cap=cv2.VideoCapture(str(args.video))
    compared=views=0
    try:
        for seconds in (8.75,23.68,30.83,49.44,56.44):
            cap.set(cv2.CAP_PROP_POS_MSEC,seconds*1000)
            ok,image=cap.read()
            assert ok
            h,w=image.shape[:2]
            image=cv2.resize(image,(720,round(h*720/w)))
            for view in (image,image[image.shape[0]//3:3*image.shape[0]//4]):
                with threadpool_limits(limits=threads,user_api='blas'):
                    before=model.predict(view)
                with threadpool_limits(limits=1,user_api='blas'):
                    after=model.predict(view)
                assert len(before)==len(after)
                for a,b in zip(before,after):
                    np.testing.assert_array_equal(a['mask'],b['mask'])
                    assert {k:v for k,v in a.items() if k!='mask'}=={k:v for k,v in b.items() if k!='mask'}
                    compared+=1
                views+=1
    finally:
        cap.release()
    with args.video.open('rb') as source:
        digest=hashlib.file_digest(source,'sha256').hexdigest()
    result={'source_sha256':digest,'model_sha256':model.sha256,'engine':'onnxruntime',
            'baseline_blas_threads':threads,'candidate_blas_threads':1,
            'views':views,'masks_compared':compared,'mask_or_metadata_differences':0,
            'scope':'medium model on five real frames, full and detail views; no live publication'}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))

if __name__=='__main__': main()
