"""Offline seed-detection feasibility at every original tap; not identity proof."""
import argparse, hashlib, json, os, sys, time
from pathlib import Path


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--video',type=Path,required=True)
    p.add_argument('--selection-json',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if a.output.exists():p.error('Choose a new output file')
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    os.environ['OPENBLAS_NUM_THREADS']='1'
    os.environ['OMP_NUM_THREADS']='1'
    def offline(event,args):
        if event=='socket.connect':raise RuntimeError('NETWORK_FORBIDDEN')
    sys.addaudithook(offline)
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    import cv2,numpy as np
    import cv_detect as cv
    from dense_replay import iter_dense_frames
    from scripts.benchmark_local_bytetrack import person_proposals
    with a.video.open('rb') as f:sha=hashlib.file_digest(f,'sha256').hexdigest()
    selection=json.loads(a.selection_json.read_text())
    if selection['source_video_sha256']!=sha:raise ValueError('SOURCE_MISMATCH')
    cv2.setNumThreads(1)
    detector=cv.PersonDetector(enabled=True)
    if not detector.ok:raise RuntimeError('MODEL_UNAVAILABLE')
    results=[];started=time.perf_counter()
    for index,tap in enumerate(selection['taps']):
        requested=round(tap['t']*1000)
        tick=time.perf_counter()
        frames=list(iter_dense_frames(str(a.video),max(0,requested-25),requested+25,proc_max_width=0))
        usable=[r for r in frames if not r['used_fallback'] and r['time_authority']=='ACTUAL_MEDIA_PTS']
        if not usable:
            results.append({'tap_index':index,'requested_ms':requested,'status':'SOURCE_FRAME_UNAVAILABLE'});continue
        frame=min(usable,key=lambda r:abs(r['media_ms']-requested))
        image=frame['frame_bgr'];boxes,scores=person_proposals(cv.predict(detector,image),frame['width'],frame['height'],cv,np)
        point=tap['target_point'];x=point['x']*frame['width'];y=point['y']*frame['height']
        matches=[i for i,b in enumerate(boxes) if b[0]<=x<=b[2] and b[1]<=y<=b[3]]
        results.append({'tap_index':index,'requested_ms':requested,'media_ms':frame['media_ms'],
            'status':'UNIQUE_DETECTION_CANDIDATE' if len(matches)==1 else 'OVERLAPPING_DETECTIONS' if matches else 'NO_DETECTION_AT_TAP',
            'matching_detection_indices':matches,'boxes':boxes.tolist(),'scores':scores.tolist(),
            'point':point,'width':frame['width'],'height':frame['height'],
            'source_frame_sha256':hashlib.sha256(image.tobytes()).hexdigest(),
            'proof_eligible':False,'seconds':time.perf_counter()-tick})
    result={'scope':'TAP_DETECTION_FEASIBILITY_ONLY_NO_TRACK_IDENTITY_VALIDATION','source_video_sha256':sha,
            'model_sha256':detector.model_sha256,'opencv_version':cv2.__version__,'numpy_version':np.__version__,
            'cpu_affinity_count':len(os.sched_getaffinity(0)),'llm_calls':0,'seconds':time.perf_counter()-started,
            'unique_candidates':sum(r['status']=='UNIQUE_DETECTION_CANDIDATE' for r in results),'tap_count':len(results),'results':results}
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='results'}))
    print(json.dumps([{k:r.get(k) for k in ('tap_index','requested_ms','status','matching_detection_indices')} for r in results]))

if __name__=='__main__':main()
