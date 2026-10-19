"""Read concrete gaps from actual native observations using new source images.

No reference-event answers or desired outcome counts are imported. Packet times
come from the source plan and focus times from the actual model's ball sequence.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.probe_native_play import spatial_reference_items
import sequence_pilot as p
import sequence_pilot_transport as t


def plan(manifest, native):
    candidates = []
    for play in native["plays"]:
        raw = play.get("raw_native_observations", {})
        if not isinstance(raw, dict):
            continue
        people = {x["id"]: x for x in raw.get("players", [])}
        selected = {k for k,v in people.items() if v.get("selected") is True}
        actions = raw.get("ball_sequence", [])
        outcome = raw.get("outcome", {})
        lo, hi = play["source_start_ms"], play["source_end_ms"]
        shots = [a for a in actions if a.get("actor") in selected and
                 any(word in a.get("action", "").lower() for word in ("shot", "shoot", "tap-in"))]
        uncertain = [a for a in actions if a.get("uncertainty") and a.get("actor") in selected]
        local = [r for r in manifest["references"] if lo <= r["media_ms"] < hi]
        if uncertain and outcome.get("kind", "").lower() in {"goal", "saved", "miss", "off_target", "wide"}:
            a, reason, extra = uncertain[0], "INTERVENING_CONTACT_OR_CONTROL", 0
            question = "Inspect the selected player's release, any opponent touch versus controlled possession, and the recipient's next contact."
        elif shots and outcome.get("kind", "").lower() in {"miss", "off_target", "wide"}:
            a, reason, extra = shots[-1], "ACTIVE_BALL_OUTCOME_AFTER_ATTEMPT", 700
            question = "Follow the same active ball after the attempt. Establish any goalkeeper touch or change of motion, and distinguish spare balls from the active ball."
        elif shots and outcome.get("kind", "").lower() == "goal" and not local:
            a, reason, extra = shots[-1], "FINAL_TOUCH_ACTOR_WITHOUT_LOCAL_IDENTITY_MARK", 0
            question = "Identify the physical player at the selected player's release and at the final touch. Determine whether they are the same person and whether another teammate touches the active ball before the outcome."
        else:
            continue
        focus = lo+round(a["clip_s"]*1000)+extra
        focus = min(hi-1, max(lo, focus))
        candidates.append({"packet_id": play["selected_packet"], "start_ms": lo, "end_ms": hi-1,
            "focus_ms": focus, "reason": reason, "question": question,
            "detail_start_ms": max(lo, focus-900), "detail_end_ms": min(hi-1, focus+900),
            "selection_policy": "ACTUAL_NATIVE_UNCERTAINTY_OR_TERMINAL_IDENTITY_OUTCOME_GAP"})
    return sorted(candidates, key=lambda x: x["start_ms"])[:3]


def run(manifest_path, native_path, profile_path, output):
    import cv2
    started, output = time.monotonic(), Path(output)
    manifest, native, profile = (p.read_json(x) for x in (manifest_path, native_path, profile_path))
    if (p.digest(manifest["source_video"]) != manifest["source_video_sha256"]
            or native["source_video_sha256"] != manifest["source_video_sha256"]
            or profile["source_video_sha256"] != manifest["source_video_sha256"]):
        raise ValueError("SOURCE_INPUT_MISMATCH")
    receipt = profile["receipt"]
    if (receipt["status"] != "COMPLETED" or receipt["origin"] != "LIVE_MODEL_REQUEST"
            or hashlib.sha256(receipt["raw_response"].encode()).hexdigest() != receipt["response_sha256"]
            or sorted(i["sha256"] for i in receipt["images"]) != sorted(r["sha256"] for r in manifest["references"])):
        raise ValueError("IDENTITY_PROFILE_UNRESOLVED")
    prior_seconds = native["analysis_seconds"]+native["source_preparation_seconds"]
    remaining_budget = max(1., 300.-prior_seconds)
    if output.exists() and any(output.iterdir()):
        raise ValueError("OUTPUT_MUST_BE_NEW_OR_EMPTY")
    manifest = p.apply_identity_profile(manifest, json.loads(profile["receipt"]["raw_response"]))
    jobs = plan(manifest, native)
    refs = {r["reference_id"]:r for r in manifest["references"]}
    cap = cv2.VideoCapture(manifest["source_video"])
    width, height = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    # Source-derived union avoids cropping an outcome to one earlier actor's height.
    top = max(0, min(r["box"]["y"]-r["box"]["h"] for r in manifest["references"]))
    bottom = min(1, max(r["box"]["y"]+2*r["box"]["h"] for r in manifest["references"]))
    box = [0, int(top*height), width, int(bottom*height)]
    details = {j["packet_id"]:[] for j in jobs}
    next_ms = {j["packet_id"]:j["detail_start_ms"] for j in jobs}
    try:
        while jobs:
            if time.monotonic()-started > min(45., max(1., remaining_budget-5)):
                raise TimeoutError("SOURCE_IMAGE_PREPARATION_BUDGET")
            ok, pixels = cap.read()
            if not ok:
                break
            ms = round(cap.get(cv2.CAP_PROP_POS_MSEC))
            if ms > max(j["detail_end_ms"] for j in jobs):
                break
            for j in jobs:
                pid = j["packet_id"]
                if next_ms[pid] <= ms <= j["detail_end_ms"]:
                    image = p._save_image(output/pid/"detail"/f"s{ms:09}.jpg", pixels[box[1]:box[3]], 1280, 80)
                    details[pid].append({"frame_id":f"s{ms:09}","media_ms":ms,"source_crop_box":box,**image})
                    while next_ms[pid] <= ms:
                        next_ms[pid] += 1000/24
    finally:
        cap.release()
    prepared = []
    for j in jobs:
        pid = j["packet_id"]
        items = [{"type":"text","text":
            "Inspect this complete chronological football play and the added native-pixel contact detail. "
            "The requested physical connection, not an expected answer, is: "+j["question"]+
            " First match the single selected physical player using the original user references and source-frame marks. "
            "Do not transfer identity to a teammate. Camera movement and an occlusion do not prove an intervening pass. "
            "Separate a deflection from deliberate controlled possession. For a shot outcome, inspect actual active-ball motion "
            "before and after the goalkeeper/post, distinguishing a stationary spare. A dive alone proves neither save nor miss. "
            "An exact foot/ball instant is not required if a short before/after sequence uniquely establishes the actor; "
            "state the bracket and observed motion. Proximity alone is not contact. Report uncertainty and alternatives when unresolved. "
            "No desired event count, type, timestamp or outcome is supplied. Identity pictures and cyan original marks are identity-only. "
            'Return JSON {"selected_player_actions":[{"actor_description":"visible identity",'
            '"action":"observed action","before_frame":"s...","after_frame":"s...",'
            '"recipient_description":null,"finisher_description":null,"outcome":"observed result or UNKNOWN",'
            '"evidence":[{"frame":"s...","fact":"visible fact"}],"uncertainty":"unresolved alternatives or empty"}],'
            '"ball_contact_chain":[{"person":"visible identity","before_frame":"s...","after_frame":"s...",'
            '"type":"pass, shot, deflection, control or other","evidence":"visible motion","uncertainty":"remaining ambiguity or empty"}],'
            '"outcome":{"kind":"observed result or UNKNOWN","last_touch_player":"visible identity or unknown",'
            '"evidence":[{"frame":"s...","fact":"visible fact"}],"uncertainty":"remaining ambiguity or empty"}}.'}]
        local = [r for r in manifest["references"] if j["start_ms"] <= r["media_ms"] <= j["end_ms"]]
        ids = list(dict.fromkeys(manifest["identity_profile"]["canonical_reference_ids"]+[r["reference_id"] for r in local]))
        for rid in ids:
            ref = refs[rid]
            items.extend([{"type":"text","text":"Original identity reference "+rid},
                          {"type":"image","path":ref["path"],"sha256":ref["sha256"]}])
        packet = {"core_start_ms":j["start_ms"]}
        spatial, _ = spatial_reference_items(manifest, packet, local, output/pid/"spatial")
        items.extend(spatial)
        overview = []
        for frame in manifest["frames"]:
            if j["start_ms"] <= frame["media_ms"] <= j["end_ms"]:
                image = p._save_image(output/pid/"overview"/(frame["frame_id"]+".jpg"),cv2.imread(frame["path"]),768,70)
                overview.append({"frame_id":frame["frame_id"],"media_ms":frame["media_ms"],**image})
        rows = [(f,"overview") for f in overview]+[(f,"native detail") for f in details[pid]]
        for frame,kind in sorted(rows,key=lambda row:(row[0]["media_ms"],row[1])):
            items.extend([{"type":"text","text":f"Source frame {frame['frame_id']}, {kind}, source_ms={frame['media_ms']}"+
                (", original source crop="+json.dumps(box) if kind=="native detail" else "")},
                {"type":"image","path":frame["path"],"sha256":frame["sha256"]}])
        try:
            _,_,audit=t.build_request("emergent","gpt-6-astra",items,reasoning_effort="medium",image_detail="high")
        except ValueError as exc:
            if str(exc)!="REQUEST_IMAGE_BUDGET_EXCEEDED":raise
            p.write_json(output/"responses"/(pid+".json"),{"status":"NOT_SENT","error":str(exc)})
            continue
        p.write_json(output/"requests"/(pid+".json"),{**j,"audit":audit,"overview_instants":len(overview),"native_instants":len(details[pid]),"source_crop_box":box})
        prepared.append({"packet_id":pid,"items":items,"reasoning_effort":"medium","image_detail":"high"})
    result={"status":"SOURCE_GAP_IMAGE_PROBE","source_video_sha256":manifest["source_video_sha256"],
        "production_pipeline_changed":False,"expected_answers_used_as_input":False,"target_events":[],
        "independent_visual_correctness_verified":False,"questions":jobs,"observations":{},
        "source_preparation_seconds":round(time.monotonic()-started,3),"model":"gpt-6-astra",
        "prior_native_trial_seconds":prior_seconds,"remaining_wall_budget_seconds":remaining_budget,
        "native_observations_file_sha256":p.digest(native_path)}
    p.write_json(output/"result.json",result)
    for r in t.run_jobs(prepared,"emergent","gpt-6-astra",deadline=started+remaining_budget,per_call_s=120):
        p.write_json(output/"responses"/(r["packet_id"]+".json"),r)
        if r["status"]=="COMPLETED":result["observations"][r["packet_id"]]=json.loads(r["raw_response"])
    result["analysis_seconds"]=round(time.monotonic()-started,3)
    p.write_json(output/"result.json",result)
    return result


if __name__=="__main__":
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--prepared",required=True);cli.add_argument("--native-result",required=True)
    cli.add_argument("--resume-profile",required=True);cli.add_argument("--output",required=True)
    a=cli.parse_args();r=run(a.prepared,a.native_result,a.resume_profile,a.output)
    raise SystemExit(0 if len(r["observations"])==len(r["questions"]) else 3)
