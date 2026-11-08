"""Audit the retained full-frame illustration; never grant ball-track approval."""
import cv2, numpy as np, json, gzip, base64, hashlib, sys
from pathlib import Path
import argparse
parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--workspace',type=Path,required=True);args=parser.parse_args()
root=args.workspace; repo=root/'VedoScout'
sys.path.insert(0,str(repo/'backend'))
from motion_compensation import estimate_camera
cv2.setNumThreads(2)
source=root/'source_audit/video/canonical_web-dd5a84b1-3dc9-40b0-80c4-89232903774f.web.mp4'
sha=hashlib.sha256(source.read_bytes()).hexdigest()
assert sha=='fa56f933859508d037b1f0ecb929c8b14ee3d2a5886fe8be312dcdc24a8be5e2'
render=json.load(open(root/'arrow_effects_full/render.json')); rows={r['ms']:r for r in render['samples']}
masks=json.loads(gzip.decompress(base64.b64decode((repo/'testdata/matchroom-completion/orman1000-approved-direction-2026-11-07.json.gz.b64').read_text())))
assert masks['source_video_sha256']==sha
masks={r['media_ms']:r['foreground'] for r in masks['samples']}
c=cv2.VideoCapture(str(source));c.set(cv2.CAP_PROP_POS_MSEC,49300);frames={};cams={};prev=None;cam=np.eye(3)
while c.grab():
 t=round(c.get(cv2.CAP_PROP_POS_MSEC))
 if t>50400:break
 if t<49400:continue
 ok,a=c.retrieve();assert ok
 g=cv2.cvtColor(cv2.resize(a,(480,853)),cv2.COLOR_BGR2GRAY)
 if prev is not None:
  m,_=estimate_camera(prev,g,[(0,853*.42,480,853*.23)]);assert m is not None
  cam=np.vstack([m,[0,0,1]])@cam
 frames[t]=a;cams[t]=cam.copy();prev=g
scale=np.array([480/1080,853/1920])
start=np.linalg.inv(cams[49865])@np.r_[np.array([435,1095])*scale,1]
end=np.linalg.inv(cams[50381])@np.r_[np.array([381.36,1065.05])*scale,1]
checks=[]
for t,r in rows.items():
 u=(t-49865)/(50381-49865);p=(cams[t]@start)[:2]/scale;q=(cams[t]@(start*(1-u)+end*u))[:2]/scale
 fg=np.zeros((1920,1080),np.uint8)
 assert masks[t]['media_ms']==t
 for poly in masks[t]['polygons']:cv2.fillPoly(fg,[np.round(np.array(poly)*[1080,1920]).astype(np.int32)],255)
 fg=cv2.dilate(fg,np.ones((3,3),np.uint8));person_fg=fg.copy();h=cv2.cvtColor(frames[t],cv2.COLOR_BGR2HSV)
 color=(((h[:,:,0]>=80)&(h[:,:,0]<=125)&(h[:,:,1]>70))|((h[:,:,0]<24)&(h[:,:,1]>85)&(h[:,:,2]>65))).astype(np.uint8)*255
 fg=cv2.bitwise_or(fg,cv2.dilate(color,np.ones((3,3),np.uint8)))
 x,y=np.round(q).astype(int)
 fade=min(1.,max(0.,(t-49865)/65),max(0.,(50331-t)/55));fade=fade*fade*(3-2*fade)
 checks.append(dict(ms=t,interpolation_fraction=u,start=p.tolist(),tip=q.tolist(),geometry_reproduction_error_px=float(max(np.linalg.norm(p-r['start']),np.linalg.norm(q-r['tip']))),tip_center_masked=bool(fg[y,x]),tip_center_in_person_mask=bool(person_fg[y,x]),fade_multiplier=fade))
model=json.loads(json.load(open(repo/'testdata/matchroom-position-llm/result.json'))['receipts'][0]['raw_response'])
positions=[o for o in model['observations'] if min(rows)<=int(o['frame_id'][1:])<=max(rows)]
v=cv2.VideoCapture(str(root/'arrow_effects_full/MatchRoom_pil_effekter_hele_billedet.mp4'));size=[int(v.get(cv2.CAP_PROP_FRAME_WIDTH)),int(v.get(cv2.CAP_PROP_FRAME_HEIGHT))];count=0
while v.grab():count+=1
out=dict(source_video_sha256=sha,verdict='NOT_VERIFIED_AS_PRECISE_BALL_MOVEMENT',render_geometry_reproduction='PASS',source_frame_count=len(checks),max_reproduction_error_px=max(x['geometry_reproduction_error_px'] for x in checks),first_ms=min(rows),last_ms=max(rows),assumed_endpoint_ms=50381,ends_before_assumed_endpoint_ms=50381-max(rows),last_progress_fraction=checks[-1]['interpolation_fraction'],tip_center_masked_frames=sum(x['tip_center_masked'] for x in checks),tip_center_in_person_mask_frames=sum(x['tip_center_in_person_mask'] for x in checks),decoded_output_frames=count,output_dimensions=size,original_frame_preserved=size==[1080,1920],model_observations_in_display_interval=len(positions),model_nonnull_ball_positions_in_display_interval=sum(o['ball']['xy'] is not None for o in positions),release_time_measured=False,reception_time_measured=False,independent_ball_position_error_px=None,assist_acceptance_changed=False,production_playback_approval_changed=False,new_model_calls=0,limitations=['Numerical reproduction validates rendering only; it is not independent ball evidence.','Manual start anchor and assumed endpoint are not measured contacts.','Hidden ball positions cannot be filled from constant-speed interpolation and called verified.','Masked-tip count refers to rounded tip center, not entire arrowhead.','Final preview runs at half speed.'],samples=checks)
(root/'arrow_precision_audit/verification.json').write_text(json.dumps(out,indent=2));print(json.dumps({k:v for k,v in out.items() if k!='samples'},indent=2))
