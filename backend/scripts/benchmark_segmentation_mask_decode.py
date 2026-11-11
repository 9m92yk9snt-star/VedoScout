"""Real-source decoder parity with identical retained ONNX outputs; no LLM."""
import argparse,hashlib,json,os,sys,time,statistics
from pathlib import Path
import cv2,numpy as np
from threadpoolctl import threadpool_limits
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import native_player_segmentation as native


def legacy(a,bounds):
    mask=(a>=.5).astype(np.uint8);result=np.zeros_like(mask)
    x0,y0,x1,y1=bounds;result[y0:y1,x0:x1]=mask[y0:y1,x0:x1];return result

class RetainedNet:
    def __init__(self,outputs,blob):self.outputs=outputs;self.blob=blob
    def setInput(self,blob):np.testing.assert_array_equal(blob,self.blob)
    def getUnconnectedOutLayersNames(self):return ['retained']
    def forward(self,names):return self.outputs

class CaptureNet:
    def __init__(self,net):self.net=net
    def setInput(self,blob):self.blob=blob.copy();self.net.setInput(blob)
    def getUnconnectedOutLayersNames(self):return self.net.getUnconnectedOutLayersNames()
    def forward(self,names):self.outputs=self.net.forward(names);return self.outputs


def run():
    p=argparse.ArgumentParser();p.add_argument('--video',type=Path,required=True);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    sha=hashlib.sha256(args.video.read_bytes()).hexdigest();assert sha=='fa56f933859508d037b1f0ecb929c8b14ee3d2a5886fe8be312dcdc24a8be5e2'
    os.environ['SCOUTMEPLAY_MATCHROOM_ENGINE']='onnxruntime';cv2.setNumThreads(1)
    original=native._bounded_threshold_mask;cap=cv2.VideoCapture(str(args.video));cases=[];inference_s=0
    with threadpool_limits(limits=1):
        model=native.PersonSegmenter();real=CaptureNet(model.net);model.net=real
        for ms in [4000,8333,9416,12000,15350,24633,30915,44015,49865,50381,50648,56448]:
            cap.set(cv2.CAP_PROP_POS_MSEC,ms);ok,a=cap.read();assert ok;actual=round(cap.get(cv2.CAP_PROP_POS_MSEC));a=cv2.resize(a,(720,1280))
            # Both full-frame and native Match Room sized lower-field crops.
            for image in [a,a[500:900].copy()]:
                t=time.perf_counter();model.predict(image);inference_s+=time.perf_counter()-t
                replay=native.PersonSegmenter.__new__(native.PersonSegmenter);replay.net=RetainedNet(real.outputs,real.blob)
                native._bounded_threshold_mask=legacy;before=replay.predict(image)
                native._bounded_threshold_mask=original;after=replay.predict(image)
                assert len(before)==len(after)
                for b,c in zip(before,after):
                    assert {k:v for k,v in b.items() if k!='mask'}=={k:v for k,v in c.items() if k!='mask'}
                    np.testing.assert_array_equal(b['mask'],c['mask'])
                cases.append((image,replay,actual,len(after)))
        old_times=[];new_times=[]
        for trial in range(7):
            for name,fn in ([('old',legacy),('new',original)] if trial%2==0 else [('new',original),('old',legacy)]):
                native._bounded_threshold_mask=fn;t=time.perf_counter()
                for image,model,_,_ in cases:model.predict(image)
                (old_times if name=='old' else new_times).append(time.perf_counter()-t)
        native._bounded_threshold_mask=original
    result={'source_sha256':sha,'model_sha256':native.MODEL_SHA256,'cases':len(cases),'instances':sum(c[3] for c in cases),'pixel_mismatches':0,'preprocessing_blob_mismatches':0,'metadata_mismatches':0,'real_inference_and_new_decode_seconds':inference_s,'legacy_decode_seconds':old_times,'optimized_decode_seconds':new_times,'legacy_median_seconds':statistics.median(old_times),'optimized_median_seconds':statistics.median(new_times),'decoder_speedup_percent':100*(1-statistics.median(new_times)/statistics.median(old_times)),'engine':'onnxruntime','blas_threads_in_benchmark':1,'measured_scope':'preprocessing and mask decoding with retained real model outputs; excludes inference from paired timing','end_to_end_analysis_speedup_claimed':False,'provider_calls':0}
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
if __name__=='__main__':run()
