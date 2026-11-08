"""Full-frame coaching-direction preview; no simulated ball-flight timing."""
import argparse,cv2,numpy as np,json,gzip,base64,hashlib,sys,subprocess
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--workspace',type=Path,required=True);a=p.parse_args();root=a.workspace;repo=root/'VedoScout';out=root/'arrow_direction_pause';out.mkdir(exist_ok=True)
sys.path.insert(0,str(repo/'backend'));from motion_compensation import estimate_camera
cv2.setNumThreads(2)
src=root/'source_audit/video/canonical_web-dd5a84b1-3dc9-40b0-80c4-89232903774f.web.mp4';sha=hashlib.sha256(src.read_bytes()).hexdigest();assert sha=='fa56f933859508d037b1f0ecb929c8b14ee3d2a5886fe8be312dcdc24a8be5e2'
c=cv2.VideoCapture(str(src));c.set(cv2.CAP_PROP_POS_MSEC,49300);frames=[]
while c.grab():
 t=round(c.get(cv2.CAP_PROP_POS_MSEC))
 if t>51600:break
 ok,img=c.retrieve();assert ok
 if t>=49400:frames.append((t,img))
by=dict(frames);freeze=49881;frame=by[freeze]
# Reuse user-indicated ball/toe area and the same-scene visible teammate's
# ground anchor only as a coaching diagram. Neither is a measured contact.
prev=cv2.cvtColor(cv2.resize(by[49865],(480,853)),cv2.COLOR_BGR2GRAY);cur=cv2.cvtColor(cv2.resize(frame,(480,853)),cv2.COLOR_BGR2GRAY)
m,_=estimate_camera(prev,cur,[(0,853*.42,480,853*.23)]);assert m is not None
scale=np.array([480/1080,853/1920]);project=lambda xy:(m@np.r_[np.array(xy)*scale,1])/scale
start=project([435,1095]);target=project([.5426*1080,.5651*1920]);delta=target-start;d=delta/np.linalg.norm(delta);n=np.array([-d[1],d[0]]);tip=target-d*9
maskdoc=json.loads(gzip.decompress(base64.b64decode((repo/'testdata/matchroom-completion/orman1000-approved-direction-2026-11-07.json.gz.b64').read_text())));assert maskdoc['source_video_sha256']==sha
fg=next(x['foreground'] for x in maskdoc['samples'] if x['media_ms']==freeze);mask=np.zeros((1920,1080),np.uint8)
for poly in fg['polygons']:cv2.fillPoly(mask,[np.round(np.array(poly)*[1080,1920]).astype(np.int32)],255)
mask=cv2.dilate(mask,np.ones((3,3),np.uint8))
# Native-resolution graphic, supersampled locally. No source image resizing.
lo=np.maximum(0,np.floor(np.minimum(start,tip)-25).astype(int));hi=np.minimum([1080,1920],np.ceil(np.maximum(start,tip)+26).astype(int));patch=np.zeros(((hi[1]-lo[1])*4,(hi[0]-lo[0])*4),np.uint8);xy=lambda z:tuple(np.round((z-lo)*4).astype(int));head=11
cv2.line(patch,xy(start),xy(tip-d*head*.55),245,20,cv2.LINE_AA);cv2.circle(patch,xy(start),10,245,-1,cv2.LINE_AA);cv2.fillPoly(patch,[np.array([xy(tip),xy(tip-d*head+n*head*.38),xy(tip-d*head*.7),xy(tip-d*head-n*head*.38)])],245,cv2.LINE_AA)
base=np.zeros((1920,1080),np.float32);base[lo[1]:hi[1],lo[0]:hi[0]]=cv2.resize(patch,(hi[0]-lo[0],hi[1]-lo[1]),interpolation=cv2.INTER_AREA)/255
layers=[(cv2.GaussianBlur(base,(0,0),3)*.45,[55,183,255]),(base,[104,218,255]),(cv2.erode(base,np.ones((3,3),np.uint8))*.65,[235,250,255])]
def draw(strength):
 result=frame.astype(np.float32)
 for alpha,color in layers:
  alpha=(alpha*(mask==0)*strength)[:,:,None];result=result*(1-alpha)+np.array(color)*alpha
 result=np.uint8(np.clip(result,0,255));return result
# Labels occupy the sky; the entire original frame stays in view.
def label(img):
 cv2.rectangle(img,(40,70),(740,172),(20,25,31),-1)
 cv2.putText(img,'AFLEVERINGSRETNING',(65,112),cv2.FONT_HERSHEY_SIMPLEX,.9,(235,235,235),2,cv2.LINE_AA)
 cv2.putText(img,'Illustration - ikke maalt boldbane',(65,148),cv2.FONT_HERSHEY_SIMPLEX,.65,(205,205,205),1,cv2.LINE_AA)
 return img
preview=label(draw(1));cv2.imwrite(str(out/'check.jpg'),preview)
cmd=['ffmpeg','-y','-loglevel','error','-f','rawvideo','-pix_fmt','bgr24','-s','1080x1920','-r','60','-i','pipe:0','-an','-c:v','libx264','-crf','18','-pix_fmt','yuv420p','-movflags','+faststart',str(out/'MatchRoom_afleveringsretning_pause.mp4')]
w=subprocess.Popen(cmd,stdin=subprocess.PIPE);count=0
for t,img in frames:
 if t==freeze:
  for i in range(108):
   strength=min(1,(i+1)/12,(108-i)/12);strength=strength*strength*(3-2*strength)
   w.stdin.write(label(draw(strength)).tobytes());count+=1
 w.stdin.write(img.tobytes());count+=1
w.stdin.close();assert w.wait()==0
x,y=np.round(tip).astype(int)
headmask=np.zeros_like(mask);cv2.fillPoly(headmask,[np.round(np.array([tip,tip-d*head+n*head*.38,tip-d*head-n*head*.38])).astype(np.int32)],255)
report={'mode':'PAUSED_COACHING_DIRECTION','source_video_sha256':sha,'freeze_source_ms':freeze,'pause_seconds':1.8,'frames_encoded':count,'dimensions':[1080,1920],'crop':False,'zoom':False,'moving_tip':False,'start_px':start.tolist(),'target_ground_px':target.tolist(),'rendered_tip_px':tip.tolist(),'tip_center_masked':bool(mask[y,x]),'head_visible_fraction':float(np.count_nonzero((headmask>0)&(mask==0))/np.count_nonzero(headmask)),'foreground_source_ms':fg['media_ms'],'is_measured_ball_trajectory':False,'production_integration':False,'playback_approved':False,'notes':['User-indicated origin; not measured ball contact.','Candidate teammate ground from retained model at 49865, background-projected 16ms to freeze; not reception contact.','Full-length direction fades in together; tip does not simulate ball travel.','No new semantic adjudication or production approval.']}
(out/'render.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
