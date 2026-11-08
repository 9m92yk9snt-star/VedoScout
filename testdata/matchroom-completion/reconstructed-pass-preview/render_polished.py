import sys,cv2,numpy as np,json,argparse,subprocess,gzip,base64,hashlib
from pathlib import Path
sys.path.insert(0,str(Path('VedoScout/backend').resolve()))
from motion_compensation import estimate_camera
parser=argparse.ArgumentParser(description='User-guided illustrative pass preview with retained source masks. Not automatic ball tracking.')
parser.add_argument('--stop-before-ms',type=int,default=50331)
parser.add_argument('--output-dir',type=Path,default=Path('arrow_polished'))
args=parser.parse_args()
args.output_dir.mkdir(parents=True,exist_ok=True)
source=Path('source_audit/video/canonical_web-dd5a84b1-3dc9-40b0-80c4-89232903774f.web.mp4')
source_sha=hashlib.sha256(source.read_bytes()).hexdigest()
if source_sha!='fa56f933859508d037b1f0ecb929c8b14ee3d2a5886fe8be312dcdc24a8be5e2':raise ValueError('SOURCE_MISMATCH')
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
mask_doc=json.loads(gzip.decompress(base64.b64decode(Path('VedoScout/testdata/matchroom-completion/orman1000-approved-direction-2026-11-07.json.gz.b64').read_text())))
if mask_doc['source_video_sha256']!=source_sha:raise ValueError('MASK_SOURCE_MISMATCH')
mask_rows={r['media_ms']:r['foreground'] for r in mask_doc['samples']}
# New user-guided source anchor: visible ball/boot area at screenshot-matched 49.865s.
# Visual placement only; do not promote to a measured contact or automatic tracking observation.
start=world(49865,[435,1095]);end=world(50381,[381.36,1065.05]);rows=[]
w=subprocess.Popen(['ffmpeg','-y','-loglevel','error','-f','rawvideo','-pix_fmt','bgr24','-s','960x780','-r','60','-i','pipe:0','-an','-c:v','libx264','-crf','18','-pix_fmt','yuv420p','-movflags','+faststart',str(args.output_dir/'raw.mp4')],stdin=subprocess.PIPE)
for (t,a),cam in zip(frames,cams):
 if 49881<=t<=50315 and (args.stop_before_ms is None or t<args.stop_before_ms):
  u=np.clip((t-49865)/(50381-49865),0,1);p=(cam@start)[:2]/scale;q=(cam@(start*(1-u)+end*u))[:2]/scale
  overlay=np.zeros(a.shape[:2],np.uint8);length=np.linalg.norm(q-p)
  if length>3:
   # Supersample only the arrow's local rectangle, preserving exact endpoints.
   lo=np.maximum(0,np.floor(np.minimum(p,q)-20).astype(int))
   hi=np.minimum([1080,1920],np.ceil(np.maximum(p,q)+21).astype(int))
   factor=4;patch=np.zeros(((hi[1]-lo[1])*factor,(hi[0]-lo[0])*factor),np.uint8)
   d=(q-p)/length;n=np.array([-d[1],d[0]])
   head=min(12.,length);half=head*.37
   xy=lambda z:tuple(np.round((z-lo)*factor).astype(int))
   stem_end=q-d*head*.50
   cv2.line(patch,xy(p),xy(stem_end),245,12,cv2.LINE_AA)
   cv2.circle(patch,xy(p),6,245,-1,cv2.LINE_AA)
   pts=np.array([xy(q),xy(q-d*head+n*half),xy(q-d*head*.70),xy(q-d*head-n*half)],np.int32)
   cv2.fillPoly(patch,[pts],245,cv2.LINE_AA)
   overlay[lo[1]:hi[1],lo[0]:hi[0]]=cv2.resize(patch,(hi[0]-lo[0],hi[1]-lo[1]),interpolation=cv2.INTER_AREA)
  # Retained source-bound person masks, not grass-color visibility.
  # Never change the rejected old direction's approval: reuse only its masks.
  if t not in mask_rows:raise ValueError('SOURCE_PERSON_MASK_MISSING')
  foreground=np.zeros(a.shape[:2],np.uint8)
  for poly in mask_rows[t]['polygons']:
   cv2.fillPoly(foreground,[np.round(np.array(poly)*[1080,1920]).astype(np.int32)],255)
  foreground=cv2.dilate(foreground,np.ones((3,3),np.uint8))
  hsv=cv2.cvtColor(a,cv2.COLOR_BGR2HSV)
  blue=((hsv[:,:,0]>=80)&(hsv[:,:,0]<=125)&(hsv[:,:,1]>70)).astype(np.uint8)*255
  orange=((hsv[:,:,0]<24)&(hsv[:,:,1]>85)&(hsv[:,:,2]>65)).astype(np.uint8)*255
  foreground=cv2.bitwise_or(foreground,cv2.dilate(cv2.bitwise_or(blue,orange),np.ones((3,3),np.uint8)))
  overlay[foreground>0]=0
  shadow=cv2.GaussianBlur(overlay,(5,5),1.1).astype(np.float32)/255*.35
  shadow[foreground>0]=0
  a=np.uint8(a*(1-shadow[:,:,None]))
  fade=min(1.,max(.25,(t-49865)/50),max(.25,(50331-t)/50))
  alpha=overlay[:,:,None].astype(np.float32)/255*fade;gold=np.array([155,220,246]);a=np.uint8(a*(1-alpha)+gold*alpha)
  rows.append({'ms':t,'start':p.tolist(),'tip':q.tolist(),'visible_pixels':int(np.count_nonzero(overlay))})
 out=cv2.resize(a[650:1300,40:840],(960,780));cv2.rectangle(out,(0,0),(960,39),(20,20,20),-1);cv2.putText(out,'VISUEL PROEVE - rekonstrueret afleveringspil',(15,27),cv2.FONT_HERSHEY_SIMPLEX,.65,(230,230,230),1,cv2.LINE_AA);w.stdin.write(out.tobytes())
w.stdin.close();code=w.wait();
if code:raise RuntimeError(f'Video encoder failed: {code}')
(args.output_dir/'render.json').write_text(json.dumps({'stop_before_ms':args.stop_before_ms,'user_guided_anchor':{'media_ms':49865,'xy':[435,1095]},'style':'warm_gold_supersampled_rounded_shaft_slim_tip','geometry_matches_refined_preview':True,'trajectory_retimed':False,'is_measured_ball_trajectory':False,'approved':False,'timing':'illustrative start based on user screenshot at 49.865; ends 50.315 before finish bracket; not measured ball trajectory','occlusion':'retained same-frame SOURCE_PERSON_MASK plus blue-kit and orange-boot exclusion; visual QA required','samples':rows},indent=2));print('frames',len(frames),'arrowframes',len(rows),'visible',sum(r['visible_pixels']>0 for r in rows))
