"""Measure post/crossbar image candidates; projected frame is not goal depth.

A ball inside this 2D rectangle may still be in front of the goal. These
measurements aid image review and never substitute for a goal-plane verdict.
"""
import math

import native_ball_reappearance as native


def candidates(image,reference_box=None,*,details=False):
    import cv2
    import numpy as np
    h,w=image.shape[:2]
    # Structural line detection is independent of ball/event labels.
    gray=cv2.cvtColor(image,cv2.COLOR_BGR2GRAY)
    edges=cv2.Canny(gray,25,65)
    if native.box_ok(reference_box):
        cy=(reference_box['y']+reference_box['h']/2)*h
        y0,y1=max(0,int(cy-.16*h)),min(h,int(cy+.12*h))
        edges[:y0]=0;edges[y1:]=0
    found=cv2.HoughLinesP(edges,1,np.pi/720,threshold=35,
        minLineLength=max(25,round(h*.025)),maxLineGap=15)
    empty={'projected_frame_candidates':[],'post_line_candidates':[],'crossbar_line_candidates':[]}
    if found is None:return empty if details else []
    vertical,horizontal=[],[]
    found=np.asarray(found)
    if found.size%4 or not found.size:return empty if details else []
    for x1,y1,x2,y2 in found.reshape(-1,4):
        dx,dy=x2-x1,y2-y1
        if dy<0:x1,y1,x2,y2=x2,y2,x1,y1;dx,dy=-dx,-dy
        length=math.hypot(dx,dy)
        count=max(20,int(length/3))
        xx=np.clip(np.linspace(x1,x2,count).round().astype(int),1,w-2)
        yy=np.clip(np.linspace(y1,y2,count).round().astype(int),1,h-2)
        # Look just inside either detected edge for a light frame member.
        brightness=np.maximum.reduce([gray[yy,xx],gray[yy,xx-1],gray[yy,xx+1],
                                      gray[yy-1,xx],gray[yy+1,xx]])
        if float(np.median(brightness))<65:continue
        if dy>h*.025 and abs(dx)<dy*.13:
            vertical.append((float(x1),float(y1),float(x2),float(y2)))
        elif abs(dx)>w*.10 and abs(dy)<abs(dx)*.13:
            if dx<0:x1,y1,x2,y2=x2,y2,x1,y1
            horizontal.append((float(x1),float(y1),float(x2),float(y2)))
    vertical.sort(key=lambda r:r[0])
    merged=[]
    for line in vertical:
        match=next((i for i,old in enumerate(merged) if abs((line[0]+line[2]-old[0]-old[2])/2)<8
            and max(line[1],old[1])-min(line[3],old[3])<h*.08),None)
        if match is None:merged.append(line)
        else:
            old=merged[match];upper=min((old,line),key=lambda r:r[1]);lower=max((old,line),key=lambda r:r[3])
            merged[match]=(upper[0],upper[1],lower[2],lower[3])
    vertical=merged
    horizontal.sort(key=lambda r:r[0])
    merged=[]
    for line in horizontal:
        def compatible(old):
            slope=(old[3]-old[1])/(old[2]-old[0])
            other_slope=(line[3]-line[1])/(line[2]-line[0])
            join=(max(line[0],old[0])+min(line[2],old[2]))/2
            difference=abs(old[1]+slope*(join-old[0])-line[1]-other_slope*(join-line[0]))
            return (max(line[0],old[0])-min(line[2],old[2])<=18
                and abs(slope-other_slope)<=.035 and difference<=3)
        match=next((i for i,old in enumerate(merged) if compatible(old)),None)
        if match is None:merged.append(line)
        else:
            old=merged[match];left=min((old,line),key=lambda r:r[0]);right=max((old,line),key=lambda r:r[2])
            merged[match]=(left[0],left[1],right[2],right[3])
    horizontal=merged
    quads=[]
    for bar in horizontal:
        bx1,by1,bx2,by2=bar
        def bar_y(x):return by1+(x-bx1)*(by2-by1)/(bx2-bx1)
        for left in vertical:
            lx=(left[0]+left[2])/2;ly=bar_y(lx)
            if abs(left[1]-ly)>24 or not bx1-24<=lx<=bx2+24:continue
            for right in vertical:
                rx=(right[0]+right[2])/2;ry=bar_y(rx)
                width=rx-lx
                if (not w*.10<=width<=w*.65 or abs(right[1]-ry)>24
                        or abs(bx1-lx)>30 or abs(bx2-rx)>30):continue
                heights=(left[3]-ly,right[3]-ry)
                if min(heights)<h*.065 or max(heights)>h*.65 or max(heights)>min(heights)*1.5:continue
                if not 1.1<=width/(sum(heights)/2)<=4.:continue
                quad={'top_left':{'x':lx/w,'y':ly/h},'top_right':{'x':rx/w,'y':ry/h},
                      'bottom_left':{'x':left[2]/w,'y':left[3]/h},
                      'bottom_right':{'x':right[2]/w,'y':right[3]/h}}
                if any(not 0<=v<=1 for p in quad.values() for v in p.values()):continue
                # Edge duplicates of one structure are one candidate.
                if any(max(math.dist((q[k]['x']*w,q[k]['y']*h),(quad[k]['x']*w,quad[k]['y']*h))
                               for k in quad)<24 for q in quads):continue
                quads.append(quad)
    if not details:return quads[:8]
    def segment(line):
        return {'p1':{'x':line[0]/w,'y':line[1]/h},'p2':{'x':line[2]/w,'y':line[3]/h}}
    return {'projected_frame_candidates':quads[:8],
            'post_line_candidates':[segment(line) for line in vertical[:40]],
            'crossbar_line_candidates':[segment(line) for line in horizontal[:40]]}


def inspect(frames_by_ms,reference_box=None):
    import numpy as np
    result={'status':'SEARCH_ONLY','source':'LOCAL_NATIVE_POST_CROSSBAR_SEARCH',
            'proof_eligible':False,'depth_verified':False,'rows':[]}
    if not isinstance(frames_by_ms,dict) or not 2<=len(frames_by_ms)<=56:
        return {**result,'reason':'GOAL_FRAME_NATIVE_FRAME_BUDGET_INVALID'}
    shape=None
    if any(type(ms) is not int for ms in frames_by_ms):
        return {**result,'reason':'GOAL_FRAME_NATIVE_SOURCE_INVALID'}
    for ms,image in sorted(frames_by_ms.items()):
        if (type(ms) is not int or ms<0 or not isinstance(image,np.ndarray) or image.dtype!=np.uint8
                or image.ndim!=3 or image.shape[2]!=3 or shape is not None and shape!=image.shape):
            return {**result,'reason':'GOAL_FRAME_NATIVE_SOURCE_INVALID'}
        shape=image.shape
        result['rows'].append({'media_ms':ms,'time_authority':'ACTUAL_MEDIA_PTS',
            'source_bgr_pixel_sha256':native._sha(image),**candidates(image,reference_box,details=True)})
    result['reason']='PROJECTED_GOAL_FRAME_REQUIRES_INDEPENDENT_DEPTH_AND_SEMANTIC_REVIEW'
    return result
