import zipfile,json,cv2,hashlib,time
from video_timebase import read_frames_at,iter_frames_at
import argparse
p=argparse.ArgumentParser();p.add_argument('video');p.add_argument('export_zip');args=p.parse_args();video=args.video
with zipfile.ZipFile(args.export_zip) as z:r=json.loads(z.read('sequence/match-room-localization.json'))
count=0;elapsed=[0.,0.]
for e in r['events'].values():
 ts=[f['media_ms'] for f in e['frames']];out=[]
 for mode in (0,1):
  cap=cv2.VideoCapture(video);start=time.perf_counter()
  pairs=((k,v) for i in range(0,len(ts),8) for k,v in read_frames_at(cap,ts[i:i+8]).items()) if mode==0 else iter_frames_at(cap,ts)
  out.append([(k,v[0],hashlib.sha256(v[1].tobytes()).hexdigest()) for k,v in pairs]);elapsed[mode]+=time.perf_counter()-start;cap.release()
 assert out[0]==out[1];count+=len(out[0])
print(json.dumps({'frames':count,'seconds':elapsed,'equal':True}))
