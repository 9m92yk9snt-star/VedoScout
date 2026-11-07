import cv2,numpy as np,json,hashlib
from pathlib import Path
cv2.setNumThreads(2)
p=Path('receiver_probe');v=next(Path('source_audit/video').glob('*.mp4'));c=cv2.VideoCapture(str(v));c.set(cv2.CAP_PROP_POS_MSEC,49500);frames={}
while c.grab():
 t=round(c.get(cv2.CAP_PROP_POS_MSEC))
 if t>50648:break
 if t>=49615:
  ok,a=c.retrieve();frames[t]=a
keys=sorted(frames);gray={t:cv2.cvtColor(a,cv2.COLOR_BGR2GRAY) for t,a in frames.items()}
def run(seed,xy,step):
 idx=keys.index(seed);point=np.array(xy,np.float32);origin=cv2.getRectSubPix(gray[seed],(19,19),tuple(point));rows=[{'ms':seed,'xy':point.tolist(),'status':'MANUAL_VISIBLE_SEED'}]
 for j in range(idx+step,len(keys) if step>0 else -1,step):
  prev,t=keys[j-step],keys[j];grid=np.array([point+[dx,dy] for dx in [-3,0,3] for dy in [-3,0,3]],np.float32).reshape(-1,1,2)
  q,st,_=cv2.calcOpticalFlowPyrLK(gray[prev],gray[t],grid,None,winSize=(21,21),maxLevel=2)
  back,st2,_=cv2.calcOpticalFlowPyrLK(gray[t],gray[prev],q,None,winSize=(21,21),maxLevel=2)
  err=np.linalg.norm(back-grid,axis=2).ravel();valid=(st.ravel()>0)&(st2.ravel()>0)&(err<1.5)
  if sum(valid)<5:rows.append({'ms':t,'status':'STOP_FLOW_INCONSISTENT','valid_points':int(sum(valid))});break
  nxt=point+np.median((q-grid).reshape(-1,2)[valid],axis=0);patch=cv2.getRectSubPix(gray[t],(19,19),tuple(nxt));ncc=float(cv2.matchTemplate(patch,origin,cv2.TM_CCOEFF_NORMED)[0,0]);row={'ms':t,'xy':nxt.tolist(),'seed_patch_ncc':ncc,'fb_error':float(np.median(err[valid])),'status':'FLOW_CANDIDATE_NOT_BALL_PROOF'}
  if ncc<.6:row['status']='STOP_APPEARANCE_CHANGED';rows.append(row);break
  rows.append(row);point=nxt
 return rows
out={'source_sha256':hashlib.sha256(v.read_bytes()).hexdigest(),'llm_calls':0,'arrow_approved':False,'method':'Local pyramidal LK, nine points, forward-backward error under 1.5 px for at least five points; fixed seed 19px patch NCC >= .6. Exploratory thresholds, not calibrated ball verification. Lossless decoded frames.','forward':run(49665,[479.5,1103],1),'backward':run(50431,[371,1060],-1),'backward_seed_scope':'User-directed pre-shot candidate visually localized at 50.431 s. Exact first receiving contact and player association not automatically verified.'}
(p/'result.json').write_text(json.dumps(out,indent=2));print(json.dumps(out,indent=2))
from PIL import Image,ImageDraw
panels=[]
for direction in ['forward','backward']:
 for row in out[direction]:
  t=row['ms'];a=Image.fromarray(cv2.cvtColor(frames[t],cv2.COLOR_BGR2RGB));d=ImageDraw.Draw(a)
  if 'xy' in row:
   x,y=row['xy'];d.rectangle((x-10,y-10,x+10,y+10),outline='red',width=2)
  b=Image.new('RGB',(550,340));b.paste(a.crop((100,850,650,1160)),(0,30));ImageDraw.Draw(b).text((5,5),f"{direction} {t} {row['status']}",fill='white');panels.append(b)
sheet=Image.new('RGB',(1100,340*((len(panels)+1)//2)))
for i,b in enumerate(panels):sheet.paste(b,((i%2)*550,(i//2)*340))
sheet.thumbnail((1000,1600));sheet.save(p/'review.jpg')
