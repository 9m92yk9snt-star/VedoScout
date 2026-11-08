"""Offline byte-identical request comparison; never contacts a model provider."""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import statistics
import time
import tracemalloc
import sequence_pilot_transport as transport


def baseline_builder(path):
    tree=ast.parse(path.read_text())
    fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='build_request')
    ns=dict(vars(transport))
    exec(compile(ast.Module(body=[fn],type_ignores=[]),str(path),'exec'),ns)
    return ns['build_request']


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--baseline',type=Path,required=True)
    p.add_argument('--image',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    old=baseline_builder(args.baseline)
    data=args.image.read_bytes();sha=hashlib.sha256(data).hexdigest()
    # Bound payload while retaining many image entries and the original bytes.
    count=min(147,max(1,12_000_000//max(1,(len(data)*4//3+100))))
    items=[{'type':'text','text':'Offline request serialization benchmark.'}]+[
        {'type':'image','path':str(args.image),'sha256':sha} for _ in range(count)]
    result={'image_sha256':sha,'image_bytes':len(data),'image_count':count,'providers':{},
            'baseline_source_sha256':hashlib.sha256(args.baseline.read_bytes()).hexdigest(),
            'provider_calls':0,'scope':'request building only, unchanged provider payload bytes'}
    for provider,model in [('emergent','gpt-6-astra'),('gemini','gemini-2.5-pro')]:
        funcs={'baseline':old,'candidate':transport.build_request}
        expected=old(provider,model,items,image_detail='high')
        assert transport.build_request(provider,model,items,image_detail='high')==expected
        timings={key:[] for key in funcs};peaks={}
        for round_id in range(7):
            for name in (['baseline','candidate'] if round_id%2==0 else ['candidate','baseline']):
                start=time.perf_counter()
                value=funcs[name](provider,model,items,image_detail='high')
                timings[name].append(time.perf_counter()-start)
                assert value==expected
                del value
        for name,fn in funcs.items():
            tracemalloc.start()
            value=fn(provider,model,items,image_detail='high')
            peaks[name]=tracemalloc.get_traced_memory()[1]
            tracemalloc.stop()
            assert value==expected
            del value
        medians={k:statistics.median(v) for k,v in timings.items()}
        result['providers'][provider]={'rounds_seconds':timings,'median_seconds':medians,
            'peak_python_bytes':peaks,'payload_bytes':len(expected[1]),
            'payload_sha256':hashlib.sha256(expected[1]).hexdigest(),'payload_or_audit_differences':0,
            'time_reduction_percent':100*(1-medians['candidate']/medians['baseline'])}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
