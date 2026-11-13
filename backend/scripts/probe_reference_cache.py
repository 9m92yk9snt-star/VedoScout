"""Bounded image-cache capability probe; no production analysis changes."""
import base64, hashlib, json, os, time, urllib.request, urllib.error
from pathlib import Path
import cv2

source = Path("testdata/sequence-pilot-orman400")
target = Path(os.environ["RUNNER_TEMP"]) / "image-cache-source"
(target / "video").mkdir(parents=True, exist_ok=True)
parts = sorted((source / "video-parts").glob("*.bin"))
assert [p.name for p in parts] == [f"{i:03}.bin" for i in range(43)]
video = target / "video/source.mp4"
with video.open("wb") as output:
    for part in parts:
        with part.open("rb") as stream:
            while chunk := stream.read(1024*1024):
                output.write(chunk)
for name in ("anchors.json", "SHA256SUMS"):
    (target/name).write_bytes((source/name).read_bytes())
for line in (target/"SHA256SUMS").read_text().splitlines():
    expected, name = line.split(None, 1)
    with (target/name).open("rb") as stream:
        assert hashlib.file_digest(stream, "sha256").hexdigest() == expected

raw = json.loads((target/"anchors.json").read_text())["raw_marker_anchors"]
anchors = json.loads(raw) if isinstance(raw, str) else raw
print(json.dumps({"anchor_container":type(anchors).__name__}), flush=True)
if isinstance(anchors, dict):
    anchors = anchors.get("anchors", anchors.get("markers"))
assert isinstance(anchors, list) and len(anchors) == 10
content = [{"type":"text","text":"Inspect the supplied football reference images. Describe visible kit colours only. Do not infer player identities or hidden shirt numbers. Reply in JSON with reference_id and visible_kit_colours."}]
cap = cv2.VideoCapture(str(video))
assert cap.isOpened()
for index, anchor in enumerate(anchors):
    # Raw original selection times; no derived player labels.
    t = anchor.get("t", anchor.get("time", anchor.get("timestamp")))
    assert isinstance(t, (int,float)), sorted(anchor)
    cap.set(cv2.CAP_PROP_POS_MSEC, t*1000)
    ok, frame = cap.read()
    assert ok
    h,w = frame.shape[:2]
    scale = min(1,1920/max(h,w))
    if scale < 1:
        frame = cv2.resize(frame,(round(w*scale),round(h*scale)))
    ok, encoded = cv2.imencode(".jpg",frame,[cv2.IMWRITE_JPEG_QUALITY,85])
    assert ok
    content += [{"type":"text","text":f"Reference r{index+1}; source time {t} seconds."},
                {"type":"image_url","image_url":{"url":"data:image/jpeg;base64,"+base64.b64encode(encoded).decode(),"detail":"high"}}]
cap.release()
content[-1]["prompt_cache_breakpoint"]={"mode":"explicit"}
key = os.environ["EMERGENT_LLM_KEY"]
rows=[]
for n in range(2):
    body={"model":"gpt-6-astra","messages":[{"role":"user","content":content+[{"type":"text","text":f"Describe visible kit colours in reference r{n+1} only."}]}],"prompt_cache_options":{"mode":"explicit"},"reasoning_effort":"low","max_completion_tokens":1024}
    request=urllib.request.Request("https://integrations.emergentagent.com/llm/chat/completions",data=json.dumps(body).encode(),headers={"Authorization":"Bearer "+key,"Content-Type":"application/json"},method="POST")
    started=time.monotonic()
    try:
        with urllib.request.urlopen(request,timeout=100) as response:
            data=response.read(1000001)
        assert len(data)<=1000000
        result=json.loads(data)
        usage=result.get("usage") or {}
        details=usage.get("prompt_tokens_details") or {}
        row={"attempt":n+1,"seconds":round(time.monotonic()-started,2),"images":10}
        for k in ("prompt_tokens","completion_tokens","total_tokens"):
            if type(usage.get(k)) is int:row[k]=usage[k]
        for k in ("cached_tokens","cache_write_tokens"):
            if type(details.get(k)) is int:row[k]=details[k]
        answer=result["choices"][0]["message"].get("content","")
        row["answer"]=answer[:2000] if isinstance(answer,str) else "NON_TEXT"
        rows.append(row)
        print(json.dumps(row),flush=True)
    except urllib.error.HTTPError as exc:
        print(json.dumps({"status":"HTTP_ERROR","http_status":exc.code}),flush=True)
        exc.close()
        raise SystemExit(1)
print(json.dumps({"cache_read_observed":len(rows)==2 and rows[1].get("cached_tokens",0)>0,"note":"Capability probe only, not football accuracy validation."}),flush=True)
