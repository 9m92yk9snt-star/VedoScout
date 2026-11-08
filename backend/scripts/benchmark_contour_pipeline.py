"""Paired exact-source contour replay; excludes paid analysis and publication.

Supply native_player_segmentation.py from baseline commit
3f13f63f7c13e51cf159a82ccf7793d116f70362 with --baseline-segmenter.
"""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import statistics
import time
import cv2
import numpy as np


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report',type=Path,required=True)
    parser.add_argument('--video',type=Path,required=True)
    parser.add_argument('--baseline-segmenter',type=Path,required=True)
    parser.add_argument('--timestamp',default='00:31')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    os.environ['SCOUTMEPLAY_MATCHROOM_ENGINE']='opencv'
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    cv2.setNumThreads(2)
    import native_player_segmentation as native
    import match_room_contours as contours
    import match_room_reacquisition as recovery
    from match_room_position_contours import contour_segments
    doc=json.loads(args.report.read_text())
    rooms=[r['match_room'] for r in doc['full_report']['video_comments'] if r['timestamp']==args.timestamp]
    assert len(rooms)==1
    room=rooms[0]
    assert 0 < room['end_ms']-room['start_ms'] <= 1500
    with args.video.open('rb') as source:
        sha=hashlib.file_digest(source,'sha256').hexdigest()
    assert sha==room['source_video_sha256']
    baseline=args.baseline_segmenter.read_text()
    tree=ast.parse(baseline)
    cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='PersonSegmenter')
    method=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='predict')
    namespace={'cv2':cv2,'np':np,'INPUT':native.INPUT}
    exec(compile(ast.Module(body=[method],type_ignores=[]),str(args.baseline_segmenter),'exec'),namespace)
    legacy_predict=namespace['predict']
    candidate_predict=native.PersonSegmenter.predict
    candidate_overlap=contours.mask_iou
    candidate_votes=recovery.count_owned
    def legacy_overlap(a,b):
        return np.count_nonzero((a>0)&(b>0))/max(1,np.count_nonzero((a>0)|(b>0)))
    def legacy_votes(mask,points):
        return sum(contours.owns(mask,p) for p in points)
    model=native.PersonSegmenter()
    model.predict(np.zeros((1280,720,3),np.uint8))  # identical warm-up, outside measurement
    timings={'legacy':[],'candidate':[]}
    reference=None
    try:
        for round_id in range(3):
            order=['legacy','candidate'] if round_id%2==0 else ['candidate','legacy']
            for name in order:
                native.PersonSegmenter.predict=legacy_predict if name=='legacy' else candidate_predict
                contours.mask_iou=legacy_overlap if name=='legacy' else candidate_overlap
                recovery.count_owned=legacy_votes if name=='legacy' else candidate_votes
                cv2.setRNGSeed(0)
                diagnostics={}
                start=time.perf_counter()
                segments=contour_segments(args.video,room['samples'],room['start_ms'],room['end_ms'],
                    deadline=time.monotonic()+180,diagnostics=diagnostics,segmenter=model)
                elapsed=time.perf_counter()-start
                timings[name].append(elapsed)
                assert diagnostics['status']=='SUPPORTED_SOURCE_OBSERVATIONS'
                assert diagnostics['source_pairs_unreached']==0
                diagnostics.pop('detector_seconds',None)
                output={'segments':segments,'diagnostics':diagnostics}
                if reference is None: reference=output
                assert output==reference, 'OUTPUT_DIFFERENCE'
                print(json.dumps({'round':round_id,'variant':name,'seconds':elapsed,
                                  'frames':diagnostics['detector_frames'],'segments':len(segments)}),flush=True)
    finally:
        native.PersonSegmenter.predict=candidate_predict
        contours.mask_iou=candidate_overlap
        recovery.count_owned=candidate_votes
    medians={k:statistics.median(v) for k,v in timings.items()}
    result={'source_sha256':sha,'event_id':room['event_id'],
            'window_ms':[room['start_ms'],room['end_ms']], 'engine':'opencv',
            'baseline_commit':'3f13f63f7c13e51cf159a82ccf7793d116f70362',
            'baseline_segmenter_sha256':hashlib.sha256(baseline.encode()).hexdigest(),
            'model_sha256':model.sha256,'single_cpu_affinity':True,'opencv_threads':2,
            'rounds_seconds':timings,'median_seconds':medians,
            'reduction_percent':100*(1-medians['candidate']/medians['legacy']),
            'output_differences':0,'output_sha256':hashlib.sha256(json.dumps(reference,sort_keys=True).encode()).hexdigest(),
            'diagnostics':reference['diagnostics'],
            'scope':'one small-model contour window; excludes model loading, medium refinement, source analysis, report writing and upload',
            'live_verified':False}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2),flush=True)

if __name__=='__main__': main()
