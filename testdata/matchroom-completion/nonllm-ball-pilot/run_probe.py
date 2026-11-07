import sys,json,time,hashlib,cv2,numpy as np
from pathlib import Path
sys.path.insert(0,str(Path('VedoScout/backend').resolve()))
from cv_detect import PersonDetector,predict,MODEL_PATH
cv2.setNumThreads(2)
p=Path('nonllm_probe');video=next(Path('source_audit/video').glob('*.mp4'));sha=hashlib.sha256(video.read_bytes()).hexdigest();assert sha=='fa56f933859508d037b1f0ecb929c8b14ee3d2a5886fe8be312dcdc24a8be5e2'
detector=PersonDetector(enabled=True);assert detector.ok

def detect(im,regions):
 rows=[]
 for x0,y0,x1,y1 in regions:
  image=im[y0:y1,x0:x1];pred=predict(detector,image);scale=640/max(image.shape[:2])
  for box,cl,score in zip(pred.xywh,pred.classes,pred.scores):
   if cl!=32 or score<.25:continue
   x,y,w,h=box/scale;rows.append({'box':[float(x-w/2+x0),float(y-h/2+y0),float(w),float(h)],'confidence':float(score)})
 if not rows:return []
 keep=cv2.dnn.NMSBoxes([r['box'] for r in rows],[r['confidence'] for r in rows],.25,.45)
 return [rows[int(i)] for i in np.asarray(keep).reshape(-1)]

def classic(im):
 crop=im[850:1160,100:650];hsv=cv2.cvtColor(crop,cv2.COLOR_BGR2HSV);mask=((hsv[:,:,1]<90)&(hsv[:,:,2]>130)).astype(np.uint8)*255;cnts,_=cv2.findContours(mask,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE);out=[]
 for c in cnts:
  area=cv2.contourArea(c);per=cv2.arcLength(c,True);x,y,w,h=cv2.boundingRect(c)
  if 30<=area<=1500 and per and 4*np.pi*area/per**2>=.55 and .6<=w/h<=1.7:
   out.append({'box':[x+100,y+850,w,h],'circularity':float(4*np.pi*area/per**2)})
 return out
c=cv2.VideoCapture(str(video));c.set(cv2.CAP_PROP_POS_MSEC,49400);rows=[];i=0;times={k:0. for k in ['full','roi','tiles','classic']};start=time.monotonic()
while c.grab():
 ms=round(c.get(cv2.CAP_PROP_POS_MSEC))
 if ms>50648:break
 if ms<49615:continue
 if i%3:i+=1;continue
 i+=1;ok,im=c.retrieve();row={'media_ms':ms}
 for name,regions in [('full',[(0,0,1080,1920)]),('roi',[(100,850,650,1160)]),('tiles',[(x,y,x+320,y+320) for x in [100,260,420] for y in [800,960]])]:
  t=time.monotonic();row[name]=detect(im,regions);times[name]+=time.monotonic()-t
 t=time.monotonic();row['classic']=classic(im);times['classic']+=time.monotonic()-t;rows.append(row);cv2.imwrite(str(p/f'{ms}.jpg'),im)
result={'scope':'NON_LLM_SUPPORTING_CANDIDATES_NOT_APPROVAL','source_video_sha256':sha,'model_sha256':hashlib.sha256(MODEL_PATH.read_bytes()).hexdigest(),'model':'existing COCO YOLOv8n, NOT football-finetuned','tiling':'custom overlapping tile inference, SAHI-style mechanism; not SAHI package','roi':[100,850,650,1160],'tile_size':320,'frames':rows,'seconds':times,'elapsed_seconds':time.monotonic()-start,'llm_calls':0,'arrow_approved':False,'kalman_prediction_is_evidence':False}
(p/'result.json').write_text(json.dumps(result,indent=2));print(json.dumps({'frames':len(rows),'seconds':times,'candidates':{k:sum(len(r[k]) for r in rows) for k in times},'frames_with_candidates':{k:sum(bool(r[k]) for r in rows) for k in times}}))
