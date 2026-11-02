import os,json,base64,hashlib,gzip,tempfile,sys
from pathlib import Path
from cryptography.hazmat.primitives import serialization,hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
sys.path.insert(0,'backend')
import sequence_pilot_transport as transport
from match_room import INSTRUCTION,samples
env=json.loads(Path('testdata/matchroom-probe/packet.enc.json').read_text())
b64=base64.b64decode
key=hashlib.scrypt(os.environ['EMERGENT_LLM_KEY'].encode(),salt=b64(env['salt']),n=16384,r=8,p=1,dklen=32)
pem=AESGCM(key).decrypt(b64(env['nonce']),b64(env['wrapped']),b'matchroom-55')
private=serialization.load_pem_private_key(pem,password=None)
content_key=private.decrypt(b64(env['key']),padding.OAEP(mgf=padding.MGF1(hashes.SHA256()),algorithm=hashes.SHA256(),label=None))
data=gzip.decompress(AESGCM(content_key).decrypt(b64(env['data_nonce']),b64(env['data']),b'matchroom-frames'))
assert hashlib.sha256(data).hexdigest()==env['packet_sha256']
records=[]
class Sink:
 def send(self,value):self.value=value
 def close(self):pass
with tempfile.TemporaryDirectory() as work:
 for packet in json.loads(data):
  items=[{'type':'text','text':'Identify the selected player from the original selection crops, then inspect ONLY the supplied chronological full source frames. Return JSON with actor:"selected", visual_samples:[], action_description, and uncertainties. Each sample actor must be "selected". Include only observed positions, not guesses. No scores, no expected result or direction is supplied.\n'+INSTRUCTION}]
  for group in ['references','frames']:
   for i,f in enumerate(packet[group]):
    fid=f.get('frame_id',f.get('reference_id'));path=Path(work)/(packet['name']+'-'+fid+'.jpg');pixels=b64(f['jpeg']);path.write_bytes(pixels)
    items.extend([{'type':'text','text':('Original player selection CROP ' if group=='references' else 'FULL source frame ')+fid+' media_ms='+str(f['media_ms'])},{'type':'image','path':str(path),'sha256':hashlib.sha256(pixels).hexdigest()}])
  sink=Sink();transport._worker(sink,{'packet_id':packet['name'],'items':items,'max_output_tokens':8192,'image_detail':'high','reasoning_effort':'medium'},'emergent','gpt-6-astra',180)
  receipt=sink.value;accepted=[]
  if receipt['status']=='COMPLETED':
   try:
    reply=json.loads(receipt['raw_response']);accepted=samples(reply.get('visual_samples'),actor='selected',frames={f['frame_id']:{'media_ms':f['media_ms']} for f in packet['frames']},start=7000,end=9400)
   except (ValueError,TypeError):pass
  records.append({'name':packet['name'],'source_video_sha256':packet['source_video_sha256'],'receipt':receipt,'accepted_samples':accepted})
  print(json.dumps({'name':packet['name'],'status':receipt['status'],'accepted_samples':len(accepted),'elapsed_seconds':receipt['elapsed_seconds'],'error':receipt.get('error')}),flush=True)
Path(os.environ['RUNNER_TEMP'],'matchroom-two-source-results.json').write_text(json.dumps(records,indent=2))
raise SystemExit(0 if all(r['receipt']['status']=='COMPLETED' for r in records) else 3)
