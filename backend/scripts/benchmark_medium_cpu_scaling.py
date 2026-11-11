import os,sys,time,json,statistics
from pathlib import Path
import argparse
p=argparse.ArgumentParser();p.add_argument('video');p.add_argument('output');args=p.parse_args()
os.environ['SCOUTMEPLAY_MATCHROOM_ENGINE']='onnxruntime'
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import cv2,numpy as np,onnxruntime as ort
from match_room_position_contours import refinement_model
from video_timebase import read_frame_at
cpus=sorted(os.sched_getaffinity(0));assert len(cpus)>=2
cv2.setNumThreads(1)
video=args.video
cap=cv2.VideoCapture(video);inputs=[]
for stamp in (8.5,9.,9.5):
 ok,pixels,actual=read_frame_at(cap,stamp);assert ok
 image=cv2.resize(pixels,(720,round(pixels.shape[0]*720/pixels.shape[1])))
 h,w=image.shape[:2];image=image[int(.38*h):int(.76*h),:];h,w=image.shape[:2];scale=640/max(h,w);nw,nh=max(1,round(w*scale)),max(1,round(h*scale))
 pad=np.full((640,640,3),114,np.uint8);pad[:nh,:nw]=cv2.resize(image,(nw,nh));inputs.append(cv2.dnn.blobFromImage(pad,1/255.,(640,640),swapRB=True))
cap.release();ort.disable_telemetry_events();sessions={}
from match_room_reacquisition import MODEL_PATH, MODEL_SHA256
from player_segmentation_assets import ensure_model_asset
ensure_model_asset(MODEL_PATH,MODEL_SHA256)
path=str(MODEL_PATH)
for n in (1,2):
 os.sched_setaffinity(0,set(cpus[:n]));opt=ort.SessionOptions();opt.intra_op_num_threads=n;opt.inter_op_num_threads=1
 sessions[n]=ort.InferenceSession(path,sess_options=opt,providers=['CPUExecutionProvider'])
name=sessions[1].get_inputs()[0].name
os.sched_setaffinity(0,{cpus[0]});expected=[sessions[1].run(None,{name:x}) for x in inputs]
rows=[];equal=True;max_diff=0.
for rnd in range(3):
 for n in ((1,2) if rnd%2==0 else (2,1)):
  os.sched_setaffinity(0,set(cpus[:n]));start=time.perf_counter();out=[sessions[n].run(None,{name:x}) for x in inputs];elapsed=time.perf_counter()-start
  for a,b in zip(expected,out):
   for x,y in zip(a,b):equal &= np.array_equal(x,y);max_diff=max(max_diff,float(np.max(np.abs(x-y))))
  row={'round':rnd,'cpu_count':n,'seconds':elapsed};rows.append(row);print(json.dumps(row),flush=True)
r={'rounds':rows,'exact_raw_output_equal':bool(equal),'maximum_absolute_difference':max_diff,'median_seconds':{n:statistics.median(r['seconds'] for r in rows if r['cpu_count']==n) for n in (1,2)},'scope':'CPU affinity experiment, three source-derived crops, runtime 1.31.1. No production activation or full pipeline parity.'}
open(args.output,'w').write(json.dumps(r,indent=2));print(json.dumps(r),flush=True)
