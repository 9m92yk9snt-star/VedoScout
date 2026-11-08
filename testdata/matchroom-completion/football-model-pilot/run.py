import os
os.environ['ORT_DISABLE_TELEMETRY']='1'
import onnxruntime as ort
ort.disable_telemetry_events()
import cv2,numpy as np,json,time,hashlib
from pathlib import Path
p=Path(__file__).parent
cv2.setNumThreads(2)
o=ort.SessionOptions();o.intra_op_num_threads=2;o.inter_op_num_threads=1
s=ort.InferenceSession(str(p/'best.onnx'),sess_options=o,providers=['CPUExecutionProvider'])
print([(i.name,i.shape) for i in s.get_inputs()],flush=True)
results=[];start=time.monotonic()
for f in sorted(Path('nonllm_probe').glob('[0-9]*.jpg')):
 im=cv2.imread(str(f));row={'media_ms':int(f.stem)}
 for label,box in [('full',(0,0,1080,1920)),('roi',(100,800,740,1280))]:
  x0,y0,x1,y1=box;crop=im[y0:y1,x0:x1];h,w=crop.shape[:2];scale=min(1920/w,1920/h);nw,nh=round(w*scale),round(h*scale);dx=(1920-nw)//2;dy=(1920-nh)//2
  a=np.full((1920,1920,3),114,np.uint8);a[dy:dy+nh,dx:dx+nw]=cv2.resize(crop,(nw,nh));tensor=np.ascontiguousarray(a[:,:,::-1].transpose(2,0,1)[None],dtype=np.float32)/255
  t=time.monotonic();out=s.run(None,{s.get_inputs()[0].name:tensor})[0][0];row[label+'_seconds']=time.monotonic()-t
  row[label]=[{'xyxy':[(float(z[0])-dx)/scale+x0,(float(z[1])-dy)/scale+y0,(float(z[2])-dx)/scale+x0,(float(z[3])-dy)/scale+y0],'score':float(z[4])} for z in out if round(float(z[5]))==1 and z[4]>=.1]
 results.append(row);print(row['media_ms'],len(row['full']),len(row['roi']),flush=True)
 (p/'result.json').write_text(json.dumps({'model_sha256':hashlib.sha256((p/'best.onnx').read_bytes()).hexdigest(),'model':json.loads((p/'provenance.json').read_text()),'llm_calls':0,'arrow_approved':False,'frames':results,'elapsed_seconds':time.monotonic()-start},indent=2))
