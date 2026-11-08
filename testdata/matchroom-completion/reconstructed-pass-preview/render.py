import sys,cv2,numpy as np,json,argparse,subprocess
from pathlib import Path
sys.path.insert(0,str(Path('VedoScout/backend').resolve()))
from motion_compensation import estimate_camera
parser=argparse.ArgumentParser(description='Reproduce the illustrative pass; optional conservative stop leaves its motion unchanged.')
parser.add_argument('--stop-before-ms',type=int,default=None)
parser.add_argument('--output-dir',type=Path,default=Path('arrow_preview'))
args=parser.parse_args()
args.output_dir.mkdir(parents=True,exist_ok=True)
cv2.setNumThreads(2)
c=cv2.VideoCapture('source_audit/video/canonical_web-dd5a84b1-3dc9-40b0-80c4-89232903774f.web.mp4');c.set(cv2.CAP_PROP_POS_MSEC,49300);frames=[];cams=[];prev=None;cam=np.eye(3)
while c.grab():
 t=round(c.get(cv2.CAP_PROP_POS_MSEC))
 if t>51600:break
 if t<49400:continue
 ok,a=c.retrieve();g=cv2.cvtColor(cv2.resize(a,(480,853)),cv2.COLOR_BGR2GRAY)
 if prev is not None:
  m,_=estimate_camera(prev,g,[(0,853*.42,480,853*.23)])
  if m is None:raise RuntimeError('camera missing')
  cam=np.vstack([m,[0,0,1]])@cam
 frames.append((t,a));cams.append(cam.copy());prev=g
scale=np.array([480/1080,853/1920])
def world(t,xy):
 i=min(range(len(frames)),key=lambda i:abs(frames[i][0]-t));return np.linalg.inv(cams[i])@np.r_[np.array(xy)*scale,1]
start=world(50015,[448,1082]);end=world(50381,[381.36,1065.05]);rows=[]
w=subprocess.Popen(['ffmpeg','-y','-loglevel','error','-f','rawvideo','-pix_fmt','bgr24','-s','960x780','-r','60','-i','pipe:0','-an','-c:v','libx264','-crf','18','-pix_fmt','yuv420p','-movflags','+faststart',str(args.output_dir/'raw.mp4')],stdin=subprocess.PIPE)
for (t,a),cam in zip(frames,cams):
 if 49900<=t<=50398 and (args.stop_before_ms is None or t<args.stop_before_ms):
  u=np.clip((t-49900)/(50381-49900),0,1);p=(cam@start)[:2]/scale;q=(cam@(start*(1-u)+end*u))[:2]/scale
  overlay=np.zeros(a.shape[:2],np.uint8);length=np.linalg.norm(q-p)
  if length>3:
   cv2.line(overlay,tuple(np.round(p).astype(int)),tuple(np.round(q).astype(int)),180,2,cv2.LINE_AA)
   d=(q-p)/length;n=np.array([-d[1],d[0]]);pts=np.array([q,q-d*10+n*4.5,q-d*10-n*4.5],np.int32);cv2.fillConvexPoly(overlay,pts,240,cv2.LINE_AA)
  hsv=cv2.cvtColor(a,cv2.COLOR_BGR2HSV);grass=((hsv[:,:,0]>=24)&(hsv[:,:,0]<=85)&(hsv[:,:,1]>=48)&(hsv[:,:,2]>=55)).astype(np.uint8)
  grass=cv2.erode(grass,np.ones((5,5),np.uint8));overlay=overlay*grass
  alpha=overlay[:,:,None].astype(np.float32)/255;gold=np.array([156,237,240]);a=np.uint8(a*(1-alpha)+gold*alpha)
  rows.append({'ms':t,'start':p.tolist(),'tip':q.tolist(),'visible_pixels':int(np.count_nonzero(overlay))})
 out=cv2.resize(a[650:1300,40:840],(960,780));cv2.rectangle(out,(0,0),(960,39),(20,20,20),-1);cv2.putText(out,'VISUEL PROEVE - rekonstrueret afleveringspil',(15,27),cv2.FONT_HERSHEY_SIMPLEX,.65,(230,230,230),1,cv2.LINE_AA);w.stdin.write(out.tobytes())
w.stdin.close();code=w.wait();
if code:raise RuntimeError(f'Video encoder failed: {code}')
(args.output_dir/'render.json').write_text(json.dumps({'stop_before_ms':args.stop_before_ms,'trajectory_retimed':False,'is_measured_ball_trajectory':False,'approved':False,'timing':'illustrative 49.900-50.398, optionally truncated by stop_before_ms; not verified first contact','occlusion':'conservative eroded grass-only visibility, NOT person segmentation','samples':rows},indent=2));print('frames',len(frames),'arrowframes',len(rows),'visible',sum(r['visible_pixels']>0 for r in rows))
