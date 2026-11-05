import os,sys,json,time,importlib.util
from pathlib import Path
os.sched_setaffinity(0,{min(os.sched_getaffinity(0))});sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import argparse
ap=argparse.ArgumentParser(description='Compare cached motion windows against a baseline module without provider calls.')
ap.add_argument('--baseline-module',required=True);ap.add_argument('--document',required=True);ap.add_argument('--video',required=True);ap.add_argument('--output',required=True);ap.add_argument('--event-id',action='append',required=True)
args=ap.parse_args()
import cv2;cv2.setNumThreads(2)
import match_room_tracking as new
from match_room_localization import validate
from match_room_position_evidence import bound_samples
spec=importlib.util.spec_from_file_location('old',args.baseline_module);old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
p=json.load(open(args.document));results=[]
for eid in args.event_id:
 e=next(e for e in p['canonical_events']['events'] if e['event_id']==eid);obs=bound_samples(e,{'raw_marker_anchors':p['raw_marker_anchors']},p['match_room_localization']['events'][eid],validate,packet='positions_'+eid)
 out={};tim={}
 for name,mod in [('before',old),('after',new)]:
  t=time.monotonic();out[name]=mod.observed_motion(args.video,obs,include_ground=False);tim[name]=time.monotonic()-t
 r={'event':eid,'seconds':tim,'identical':out['before']==out['after']};results.append(r);print(json.dumps(r),flush=True)
 Path(args.output).write_text(json.dumps(results));assert r['identical']
