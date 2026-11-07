import sys,time,json,hashlib,os
os.environ['ORT_DISABLE_TELEMETRY']='1'
from pathlib import Path
sys.path.insert(0,str(Path('VedoScout/backend').resolve()))
import cv2,numpy as np
cv2.setNumThreads(2)
# Reuse only the preview's camera/anchor computation; no preview masks.
source=Path('VedoScout/testdata/matchroom-completion/reconstructed-pass-preview/render.py').read_text();exec(source[:source.index("w=cv2.VideoWriter")])
from match_room_reviewed_direction import build_reviewed_direction
ref=49915;i=next(i for i,(t,a) in enumerate(frames) if t==ref)
direction=[((cams[i]@v)[:2]/scale/[1080,1920]).tolist() for v in [start,end]]
video=next(Path('source_audit/video').glob('*.mp4'));sha=hashlib.sha256(video.read_bytes()).hexdigest()
review={'status':'OWNER_APPROVED_DIRECTION','review_id':'reconstructed-preview-20261107','event_id':'47ad617d2ba76a4683cd','source_video_sha256':sha,'reference_ms':ref,'start_ms':ref,'end_ms':50398,'direction':direction,'animation':{'kind':'RECONSTRUCTED_PASS','arrival_ms':50381}}
t=time.monotonic();out=build_reviewed_direction(video,review['event_id'],sha,review,time.monotonic()+120)
Path('integrated_review/data.json').write_text(json.dumps(out));print('samples',len(out['samples']),'seconds',time.monotonic()-t,flush=True)
w=cv2.VideoWriter('integrated_review/raw.mp4',cv2.VideoWriter_fourcc(*'mp4v'),60,(960,780));by={r['media_ms']:r for r in out['samples']};checks=[]
for ms,a in frames:
 r=by.get(ms)
 if r:
  overlay=np.zeros(a.shape[:2],np.uint8);p,q=np.array(r['directionTrail'])*[1080,1920];length=np.linalg.norm(q-p)
  if length>3:
   cv2.line(overlay,tuple(p.astype(int)),tuple(q.astype(int)),180,2,cv2.LINE_AA);d=(q-p)/length;n=np.array([-d[1],d[0]]);cv2.fillConvexPoly(overlay,np.array([q,q-d*10+n*4.5,q-d*10-n*4.5],np.int32),240,cv2.LINE_AA)
  mask=np.zeros_like(overlay)
  for poly in r['foreground']['polygons']:cv2.fillPoly(mask,[np.round(np.array(poly)*[1080,1920]).astype(np.int32)],255)
  mask=cv2.dilate(mask,np.ones((3,3),np.uint8));overlay[mask>0]=0
  checks.append({'ms':ms,'visible_pixels':int(np.count_nonzero(overlay)),'mask_polygons':len(r['foreground']['polygons'])})
  alpha=overlay[:,:,None]/255.;a=np.uint8(a*(1-alpha)+np.array([156,237,240])*alpha)
 a=cv2.resize(a[650:1300,40:840],(960,780));cv2.rectangle(a,(0,0),(960,39),(20,20,20),-1);cv2.putText(a,'VISUEL PROEVE - Match Room-spillermasker',(15,27),cv2.FONT_HERSHEY_SIMPLEX,.65,(230,230,230),1,cv2.LINE_AA);w.write(a)
 if ms in [50015,50115,50215,50315,50381]:cv2.imwrite(f'integrated_review/{ms}.jpg',a)
w.release();Path('integrated_review/checks.json').write_text(json.dumps(checks,indent=2))
