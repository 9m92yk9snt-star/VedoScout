"""Quantify saved polygon differences without approving an engine switch."""
import argparse, json
from pathlib import Path
import cv2
import numpy as np

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('before',type=Path);p.add_argument('after',type=Path);p.add_argument('video',type=Path);p.add_argument('output',type=Path)
    args=p.parse_args();a=json.loads(args.before.read_text());b=json.loads(args.after.read_text())
    import hashlib
    with args.video.open('rb') as f:sha=hashlib.file_digest(f,'sha256').hexdigest()
    if any(r['source_video_sha256']!=sha for r in (a,b)):raise ValueError('Source mismatch')
    if a['event_id']!=b['event_id'] or a['window_ms']!=b['window_ms']:raise ValueError('Context mismatch')
    cap=cv2.VideoCapture(str(args.video));ok,image=cap.read();cap.release()
    if not ok:raise ValueError('Source unavailable')
    w=720;h=round(image.shape[0]*w/image.shape[1]);changes=[];sample_count=0
    if len(a['segments'])!=len(b['segments']):raise ValueError('Segment count mismatch')
    for first,last in zip(a['segments'],b['segments']):
        if first['id']!=last['id'] or len(first['samples'])!=len(last['samples']):raise ValueError('Segment mismatch')
        for x,y in zip(first['samples'],last['samples']):
            if x['media_ms']!=y['media_ms']:raise ValueError('Time mismatch')
            sample_count+=1
            for key in set(x)|set(y):
                if key not in ('foreground','confidence') and x.get(key)!=y.get(key):raise ValueError('Position or other sample changed: '+key)
            if x['foreground']==y['foreground']:continue
            masks=[]
            for row in (x,y):
                mask=np.zeros((h,w),np.uint8)
                # Union independently filled polygons: overlapping people must
                # not become holes through an even/odd multi-contour fill rule.
                for poly in row['foreground']['polygons']:
                    points=np.rint(np.asarray(poly)*[w,h]).astype(np.int32)
                    cv2.fillPoly(mask,[points],1)
                masks.append(mask)
            removed=np.argwhere((masks[0]==1)&(masks[1]==0));added=np.argwhere((masks[0]==0)&(masks[1]==1))
            changes.append({'segment_id':first['id'],'media_ms':x['media_ms'],
                            'removed_raster_pixels':len(removed),'added_raster_pixels':len(added),
                            'removed_xy':removed[:,::-1].tolist(),'added_xy':added[:,::-1].tolist()})
    result={'source_sha256':sha,'raster_dimensions':[w,h],'samples_compared':sample_count,
            'non_foreground_non_confidence_sample_fields_equal':True,'changes':changes,
            'scope':'Rounded polygon union on analysis raster; not raw detector mask equality, visual quality judgment or permission to relax gates.'}
    args.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))

if __name__=='__main__':main()
