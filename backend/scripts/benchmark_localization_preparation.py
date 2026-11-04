import os,sys,json,time,importlib.util,resource
from pathlib import Path
os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
import argparse
parser=argparse.ArgumentParser(description='Compare source image/request parity on one CPU without model calls.')
parser.add_argument('--baseline-module',required=True)
parser.add_argument('--document',required=True)
parser.add_argument('--video',required=True)
parser.add_argument('--output',required=True)
args=parser.parse_args()
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import match_room_localization as new
spec=importlib.util.spec_from_file_location('before',args.baseline_module);old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
doc=json.load(open(args.document));selection={'raw_marker_anchors':doc['raw_marker_anchors']}
root=Path(args.output);root.mkdir(exist_ok=True)
results=[];refs={'before':None,'after':None}
for e in doc['canonical_events']['events']:
 if e['event_id'] not in doc['match_room_localization']['events']:continue
 records={};timings={}
 for name,mod in [('before',old),('after',new)]:
  start=time.monotonic();r,_=mod.prepare(args.video,selection,e,root/name/e['event_id'],refs[name]);timings[name]=time.monotonic()-start;refs[name]=r['references'];records[name]=r
 fields=lambda r:[(f['frame_id'],f['media_ms'],f['sha256']) for f in r['frames']+r['references']]
 row={'event_id':e['event_id'],'seconds':timings,'identical_images':fields(records['before'])==fields(records['after']),'identical_request':records['before']['request']==records['after']['request'],'frames':len(records['after']['frames'])}
 results.append(row);print(json.dumps(row),flush=True)
 (root/'results.json').write_text(json.dumps(results,indent=2))
 assert row['identical_images'] and row['identical_request']
print('ALL_MATCH',resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,flush=True)
