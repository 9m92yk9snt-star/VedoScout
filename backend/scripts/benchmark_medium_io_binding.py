import os,sys,time,hashlib,json,statistics
from pathlib import Path
import argparse
parser=argparse.ArgumentParser()
parser.add_argument('video');parser.add_argument('output')
args=parser.parse_args()
os.sched_setaffinity(0,{min(os.sched_getaffinity(0))});os.environ['SCOUTMEPLAY_MATCHROOM_ENGINE']='onnxruntime'
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import cv2,numpy as np,onnxruntime as ort
from match_room_position_contours import refinement_model
from video_timebase import read_frame_at
cv2.setNumThreads(2)
model=refinement_model();s=model.net.session
video=args.video
cap=cv2.VideoCapture(video);inputs=[]
for stamp in (8.5,9.0,9.5):
 ok,pixels,actual=read_frame_at(cap,stamp);assert ok
 image=cv2.resize(pixels,(720,round(pixels.shape[0]*720/pixels.shape[1])))
 h,w=image.shape[:2];image=image[int(.38*h):int(.76*h),:]
 h,w=image.shape[:2];scale=640/max(h,w);nw,nh=max(1,round(w*scale)),max(1,round(h*scale))
 pad=np.full((640,640,3),114,np.uint8);pad[:nh,:nw]=cv2.resize(image,(nw,nh))
 inputs.append(cv2.dnn.blobFromImage(pad,1/255.0,(640,640),swapRB=True))
cap.release();name=s.get_inputs()[0].name;names=[x.name for x in s.get_outputs()]
reference=[s.run(names,{name:x}) for x in inputs]
buffers=[np.empty_like(x) for x in reference[0]]
binding=s.io_binding()
for n,b in zip(names,buffers):binding.bind_output(n,'cpu',0,b.dtype,b.shape,b.ctypes.data)
rows=[]
for round_id in range(4):
 for mode in (('run','binding') if round_id%2==0 else ('binding','run')):
  elapsed=0
  for x,expected in zip(inputs,reference):
   start=time.perf_counter()
   if mode=='run':out=s.run(names,{name:x})
   else:
    binding.bind_cpu_input(name,x);s.run_with_iobinding(binding);out=buffers
   elapsed+=time.perf_counter()-start
   assert all(np.array_equal(a,b) for a,b in zip(expected,out)), 'RAW_OUTPUT_CHANGED'
  rows.append({'round':round_id,'mode':mode,'seconds':elapsed})
  print(json.dumps(rows[-1]),flush=True)
med={m:statistics.median(r['seconds'] for r in rows if r['mode']==m) for m in ('run','binding')}
result={'model_sha256':model.sha256,'onnxruntime':ort.__version__,'one_cpu':True,'frames':3,'rounds':rows,'median_seconds':med,'all_raw_outputs_exact':True,'scope':'Offline same-session forward-only comparison. Fixed output-buffer reuse, three source-derived crops. No production activation or overall-analysis claim.'}
open(args.output,'w').write(json.dumps(result,indent=2));print(json.dumps(result),flush=True)
