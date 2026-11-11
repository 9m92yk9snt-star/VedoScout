"""Fresh-worker CPU-affinity comparison with unchanged production inference settings."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import tempfile
import time


def trial(args):
    available=sorted(os.sched_getaffinity(0))
    assert len(available)>=args.cpus
    os.sched_setaffinity(0,set(available[:args.cpus]))
    os.environ['OPENBLAS_NUM_THREADS']='1'
    os.environ['SCOUTMEPLAY_MATCHROOM_ENGINE']='onnxruntime'
    import cv2
    import numpy as np
    from native_player_segmentation import PersonSegmenter
    from match_room_position_contours import contour_segments
    cv2.setNumThreads(2)
    report=json.loads(args.report.read_text())
    rooms=[c['match_room'] for c in report['full_report']['video_comments'] if c['timestamp']==args.timestamp]
    assert len(rooms)==1
    room=rooms[0]
    assert 0<room['end_ms']-room['start_ms']<=1500
    with args.video.open('rb') as f: sha=hashlib.file_digest(f,'sha256').hexdigest()
    assert sha==room['source_video_sha256']
    model=PersonSegmenter()
    model.predict(np.zeros((1280,720,3),np.uint8))
    cv2.setRNGSeed(0)
    diagnostic={}
    start=time.perf_counter()
    segments=contour_segments(args.video,room['samples'],room['start_ms'],room['end_ms'],
        deadline=time.monotonic()+180,diagnostics=diagnostic,segmenter=model)
    elapsed=time.perf_counter()-start
    assert diagnostic['status']=='SUPPORTED_SOURCE_OBSERVATIONS'
    assert diagnostic['source_pairs_unreached']==0
    diagnostic.pop('detector_seconds',None)
    output={'segments':segments,'diagnostics':diagnostic}
    return {'cpu_affinity':available[:args.cpus],'seconds':elapsed,'source_sha256':sha,
            'model_sha256':model.sha256,'event_id':room['event_id'],
            'window_ms':[room['start_ms'],room['end_ms']],
            'output_sha256':hashlib.sha256(json.dumps(output,sort_keys=True).encode()).hexdigest(),
            'diagnostics':diagnostic}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--report',type=Path,required=True)
    p.add_argument('--video',type=Path,required=True)
    p.add_argument('--timestamp',default='00:31')
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--cpus',type=int,choices=(1,2,4),help=argparse.SUPPRESS)
    args=p.parse_args()
    if args.cpus:
        args.output.write_text(json.dumps(trial(args)))
        return
    assert len(os.sched_getaffinity(0))>=4
    rows=[]
    with tempfile.TemporaryDirectory(prefix='scout-cpu-bench-') as directory:
        for round_id,order in enumerate(((1,2,4),(4,1,2),(2,4,1))):
            for cpus in order:
                path=Path(directory)/'trial.json'
                subprocess.run([sys.executable,__file__,'--report',str(args.report),'--video',str(args.video),
                    '--timestamp',args.timestamp,'--output',str(path),'--cpus',str(cpus)],
                    check=True,timeout=240,env={**os.environ,'OPENBLAS_NUM_THREADS':'1'})
                row=json.loads(path.read_text())
                if rows: assert row['output_sha256']==rows[0]['output_sha256'],'OUTPUT_DIFFERENCE'
                rows.append({'round':round_id,'cpus':cpus,**row})
                print(json.dumps({'round':round_id,'cpus':cpus,'seconds':row['seconds']}),flush=True)
    medians={str(n):statistics.median(r['seconds'] for r in rows if r['cpus']==n) for n in (1,2,4)}
    result={'engine':'onnxruntime','onnx_intra_threads':1,'onnx_inter_threads':1,
            'opencv_threads':2,'openblas_threads':1,'fresh_worker_per_trial':True,
            'rounds':rows,'median_seconds':medians,'output_differences':0,
            'reduction_vs_one_cpu_percent':{n:100*(1-t/medians['1']) for n,t in medians.items()},
            'scope':'Local CPU affinity, unchanged small-model worker settings; not an Emergent vCPU benchmark or complete analysis',
            'live_verified':False}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'medians':medians,'reduction':result['reduction_vs_one_cpu_percent']},indent=2))

if __name__=='__main__': main()
