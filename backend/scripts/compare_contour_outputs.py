"""Compare emitted geometry, decisions and confidence without hiding differences."""
import argparse, hashlib, json
from pathlib import Path
from collections import Counter

def main():
    p=argparse.ArgumentParser();p.add_argument('before',type=Path);p.add_argument('after',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
    before=json.loads(a.before.read_text());after=json.loads(a.after.read_text())
    for key in ('source_video_sha256','event_id','window_ms','model_sha256'):
        if before[key]!=after[key]:raise ValueError('Context mismatch: '+key)
    differences=Counter();examples=[]
    def compare(x,y,path='segments'):
        if type(x)!=type(y):different(path,x,y);return
        if isinstance(x,dict):
            for k in x.keys()|y.keys():
                if k not in x or k not in y:different(path+'.'+k,x.get(k),y.get(k))
                else:compare(x[k],y[k],path+'.'+k)
        elif isinstance(x,list):
            if len(x)!=len(y):different(path+'.length',len(x),len(y))
            for i,(u,v) in enumerate(zip(x,y)):compare(u,v,f'{path}[{i}]')
        elif x!=y:different(path,x,y)
    def different(path,x,y):
        kind='confidence' if path.endswith('.confidence') else 'geometry_or_structure'
        differences[kind]+=1
        if sum(e['kind']==kind for e in examples)<12:examples.append({'kind':kind,'path':path,'before':x,'after':y})
    compare(before['segments'],after['segments'])
    exclude={'detector_seconds'}
    d=[{k:v for k,v in r['diagnostic'].items() if k not in exclude} for r in (before,after)]
    result={'context':{k:before[k] for k in ('source_video_sha256','event_id','window_ms','model_sha256')},
            'segment_counts':[len(r['segments']) for r in (before,after)],'differences':dict(differences),'examples':examples,
            'decisions_equal':d[0]==d[1],'diagnostics':d,
            'contour_seconds':[r['contour_seconds'] for r in (before,after)],
            'output_sha256':[hashlib.sha256(p.read_bytes()).hexdigest() for p in (a.before,a.after)],
            'scope':'One fixed source-bound contour window; offline geometry, not full recovery branch or production deadline verification.'}
    a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))

if __name__=='__main__':main()
