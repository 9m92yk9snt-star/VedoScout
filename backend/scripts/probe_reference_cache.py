"""Two bounded synthetic cache probes. No user footage or production changes."""
import os,json,time,urllib.request,urllib.error
key=os.environ.get("EMERGENT_LLM_KEY")
if not key:
 print(json.dumps({"status":"KEY_UNAVAILABLE"}));raise SystemExit(1)
prefix="Synthetic cache capability test. Reply only OK. The following is reference data.\n"+"\n".join(f"Reference {i}: blue circle, white square, green triangle; preserve every reference." for i in range(700))
rows=[]
for n in range(2):
 body={"model":"gpt-6-astra","messages":[{"role":"user","content":[
 {"type":"text","text":prefix,"prompt_cache_breakpoint":{"mode":"explicit"}},
 {"type":"text","text":f"Query {n}: reply OK."}]}],
 "prompt_cache_options":{"mode":"explicit"},"reasoning_effort":"low","max_completion_tokens":1024}
 req=urllib.request.Request("https://integrations.emergentagent.com/llm/chat/completions",data=json.dumps(body).encode(),headers={"Authorization":"Bearer "+key,"Content-Type":"application/json"},method="POST")
 started=time.monotonic()
 try:
  with urllib.request.urlopen(req,timeout=65) as response: data=response.read(1000001)
  if len(data)>1000000:raise ValueError("response too large")
  result=json.loads(data);usage=result.get("usage") or {};details=usage.get("prompt_tokens_details") or {}
  row={"attempt":n+1,"status":"RETURNED","seconds":round(time.monotonic()-started,2)}
  for k in ("prompt_tokens","completion_tokens","total_tokens"):
   if type(usage.get(k)) is int:row[k]=usage[k]
  for k in ("cached_tokens","cache_write_tokens"):
   if type(details.get(k)) is int:row[k]=details[k]
  rows.append(row);print(json.dumps(row),flush=True)
 except urllib.error.HTTPError as exc:
  print(json.dumps({"attempt":n+1,"status":"HTTP_ERROR","http_status":exc.code}),flush=True);exc.close();break
 except Exception as exc:
  print(json.dumps({"attempt":n+1,"status":"ERROR","type":type(exc).__name__}),flush=True);break
print(json.dumps({"cache_read_observed":any(r.get("cached_tokens",0)>0 for r in rows),"note":"Synthetic text only; HTTP acceptance alone does not prove passthrough or image-cache savings."}))
