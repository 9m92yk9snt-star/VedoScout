"""Standalone sequence experiment. No production imports, detector or model SDK.

Input preparation reads ONLY the source video, checksums and original taps.
Reference answers, historical model observations and derived tracking identities
cannot influence sampling, prompts or attribution. This is an experimental
event reader, not a replacement production report pipeline.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import time

VERSION = 1
PROMPT = """Observe these chronological football source images. Images are actual
source instants, not playback seconds. First understand each uninterrupted play,
including buildup and aftermath, then attribute actions to the selected person.
Selected-player references are original user selections, not predicted tracks.
Their crop/point can include another person: compare the visible person, kit,
number when readable, build and continuous motion. Do not guess hidden numbers.
Observe all ball-involved players even when the selected person is off-camera.
Use one person_id per physical person within a play. Keep passer, receiver and
finisher separate; do not transfer the selected identity to the receiver. A
camera pan is not a cut. State unknown identity/contact/outcome when unseen.
Follow the active ball before and after occlusion. A ball stationary relative
to goal/ground before the shot is a spare, even if a camera pan moves it on screen.
A keeper diving is not itself a save. Follow the ball's subsequent motion; a
goal needs the active ball in the goal, not celebration or a spare ball. Describe
visible before/after evidence; never invent the hidden trajectory. The shooter
may leave the picture while the same play continues. Ignore all audio.
For passes, follow the recipient through the finish. TEAMMATE_GOAL means a
direct assist: the recipient of this pass is the finisher, without another
player's intervening pass. Otherwise retain the completed pass/teammate shot.
Include dribbles, passes, shots, duels, recoveries, receives and runs when seen.
contact_frame is the actual passing/striking touch, not an earlier dribble.
Use only supplied frame/reference IDs. Times come from the supplied images;
no expected event counts, event times or results are supplied. Cite source
frames and short concrete observations. Do not return per-frame empty rows,
invent boxes, perform numerical speed estimates or add report prose.
Return one JSON object:
{"plays":[{"start_frame":"s...","end_frame":"s...",
"people":[{"person_id":"p1","selected":true,"kit_consistent":true,
"reference_ids":["r1"],"evidence_frames":["s..."],"appearance":"visible features"}],
"actions":[{"action_id":"a1","kind":"PASS|CROSS|SHOT|DRIBBLE|CARRY|DUEL|RECOVERY|RECEIVE|RUN|OTHER",
"actor":"p1","start_frame":"s...","contact_frame":"s...","end_frame":"s...",
"actor_evidence_frames":["s..."],"ball_id":"b1",
"outcome":"GOAL|SAVED|BLOCKED|OFF_TARGET|COMPLETED|INCOMPLETE|TEAMMATE_SHOT|TEAMMATE_GOAL|UNKNOWN",
"receiver":null,"receiver_frame":null,"receiver_is_teammate":null,
"finisher":null,"shot_frame":null,"outcome_frame":null,
"same_active_ball":null,"continuous_play":true,
"outcome_evidence":[{"frame":"s...","fact":"what is visible"}],
"details":"what happens, including any visible contradiction"}],
"questions":[{"reason":"IDENTITY|CONTACT|RECEIVER|OUTCOME","action_id":"a1"}]}]}.
selected, kit_consistent and receiver_is_teammate are true/false/null. For a
visible teammate goal on a pass include recipient, receiving frame, finisher,
finishing contact and the goal evidence. For observed different people use
selected=false; don't identify everyone in matching kit as the selected person.
If the packet ends during a play, keep its partial observation and ask the
specific missing-link question. Report the actual unsuccessful result too.
"""


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text())


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    temporary.replace(path)


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def original_taps(document):
    rows = document.get("raw_marker_anchors") or document.get("anchors")
    for _ in range(3):
        if not isinstance(rows, str):
            break
        rows = json.loads(rows)
    if not isinstance(rows, list) or not 1 <= len(rows) <= 30:
        raise ValueError("ORIGINAL_TAPS_REQUIRED")
    result = []
    for i, row in enumerate(rows):
        box, point = row.get("box") or {}, row.get("target_point") or {}
        if not _number(row.get("t")) or row["t"] < 0:
            raise ValueError("INVALID_TAP_TIME")
        if not all(_number(box.get(k)) for k in ("x", "y", "w", "h")) or not (
            0 <= box["x"] < 1 and 0 <= box["y"] < 1 and box["w"] > 0 and box["h"] > 0
            and box["x"] + box["w"] <= 1.001 and box["y"] + box["h"] <= 1.001
        ):
            raise ValueError("INVALID_TAP_BOX")
        if not all(_number(point.get(k)) and 0 <= point[k] <= 1 for k in ("x", "y")):
            raise ValueError("ORIGINAL_POSITIVE_POINT_REQUIRED")
        # Ignore stored jersey/shorts colours, predicted identities and outcomes.
        result.append({"reference_id": f"r{i+1}", "requested_ms": round(row["t"] * 1000),
                       "box": {k: box[k] for k in ("x", "y", "w", "h")},
                       "target_point": {k: point[k] for k in ("x", "y")}})
        # Keep original user visibility/exclusion/mask hints, never derived tracks.
        from player_selection import selection_metadata
        result[-1]["selection_hints"] = selection_metadata(row)
    return result


def plan_packets(last_ms, chunk_ms=30000, overlap_ms=6000):
    if not 0 < last_ms or not 1000 <= chunk_ms <= 60000 or not 0 <= overlap_ms < chunk_ms / 2:
        raise ValueError("INVALID_PACKET_BOUNDS")
    packets, start = [], 0
    while start < last_ms:
        end = min(last_ms, start + chunk_ms)
        packets.append({"packet_id": f"sequence_{len(packets)+1:03}", "start_ms": start, "end_ms": end,
                        "phase": "INITIAL"})
        if end == last_ms:
            break
        start = end - overlap_ms
    return packets


def _save_image(path, pixels, max_edge, quality=75):
    import cv2
    height, width = pixels.shape[:2]
    ratio = min(1., max_edge / max(height, width))
    if ratio < 1:
        pixels = cv2.resize(pixels, (max(1, round(width * ratio)), max(1, round(height * ratio))),
                            interpolation=cv2.INTER_AREA)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(path), pixels, [cv2.IMWRITE_JPEG_QUALITY, quality]):
        raise ValueError("IMAGE_WRITE_FAILED")
    return {"path": str(path.resolve()), "sha256": digest(path), "bytes": path.stat().st_size,
            "width": pixels.shape[1], "height": pixels.shape[0]}


def plan_visual_packets(frames, last_ms):
    """Find large image changes, not event times; preserve all sampled instants.

    Camera movement alone is insufficient: both colour-distribution and pixel
    changes must be large. Short flashes merge into one boundary. Half a second
    on either side remains visible; unresolved actions can request wider context.
    No detector, reference answer, target location or historical event is read.
    """
    import cv2
    import numpy as np
    started, changes, previous = time.monotonic(), [], None
    for f in frames:
        image = cv2.imread(f["path"])
        if image is None:
            raise ValueError("PREPARED_IMAGE_UNREADABLE")
        image = cv2.resize(image, (96, 160))
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        hist = cv2.calcHist([hsv], [0, 1, 2], None, [12, 8, 8], [0, 180, 0, 256, 0, 256])
        cv2.normalize(hist, hist)
        if previous is not None:
            colour = cv2.compareHist(previous[0], hist, cv2.HISTCMP_BHATTACHARYYA)
            pixels = float(np.mean(np.abs(image.astype("float32") - previous[1].astype("float32"))) / 255)
            if colour >= .30 and pixels >= .10 and 2500 <= f["media_ms"] <= last_ms - 2500:
                change = {"media_ms": f["media_ms"], "colour_distance": round(colour, 6),
                          "pixel_difference": round(pixels, 6)}
                if changes and change["media_ms"] - changes[-1]["media_ms"] < 2500:
                    if change["colour_distance"] > changes[-1]["colour_distance"]:
                        changes[-1] = change
                else:
                    changes.append(change)
        previous = hist, image
    boundaries = [0] + [c["media_ms"] for c in changes] + [last_ms]
    jobs = []
    for left, right in zip(boundaries, boundaries[1:]):
        pieces = max(1, math.ceil((right - left) / 20000))
        for index in range(pieces):
            core_start = round(left + (right - left) * index / pieces)
            core_end = round(left + (right - left) * (index + 1) / pieces)
            jobs.append({"packet_id": f"sequence_{len(jobs)+1:03}", "phase": "INITIAL",
                "start_ms": max(0, core_start - 500), "end_ms": min(last_ms, core_end + 500),
                "core_start_ms": core_start, "core_end_ms": core_end,
                "visual_cut_candidates_ms": [c["media_ms"] for c in changes
                    if core_start - 500 <= c["media_ms"] <= core_end + 500]})
    return jobs, {"strategy": "SOURCE_IMAGE_CHANGES", "changes": changes,
                  "seconds": round(time.monotonic() - started, 3)}


def prepare(evidence_dir, output_dir, *, fps=8., max_edge=768, chunk_ms=30000,
            overlap_ms=6000, timeout_s=60., scene_packets=False):
    """One sequential source decode; zero detector forwards and model calls."""
    import cv2
    if not _number(fps) or not 1 <= fps <= 30 or not 320 <= max_edge <= 1920:
        raise ValueError("INVALID_SAMPLING_SETTINGS")
    started = time.monotonic()
    root, out = Path(evidence_dir).resolve(), Path(output_dir).resolve()
    if out.exists() and any(out.iterdir()):
        raise ValueError("OUTPUT_MUST_BE_NEW_OR_EMPTY")
    videos = sorted((root / "video").glob("*.mp4"))
    if len(videos) != 1:
        raise ValueError("EXACTLY_ONE_SOURCE_VIDEO_REQUIRED")
    video = videos[0]
    # Verify only the actual inputs. Do not read report.json or old model results.
    sums = dict((name.strip().lstrip("*"), sha) for sha, name in
                (line.split(None, 1) for line in (root / "SHA256SUMS").read_text().splitlines() if line.strip()))
    for path in (video, root / "anchors.json"):
        if sums.get(path.relative_to(root).as_posix()) != digest(path):
            raise ValueError("SOURCE_INPUT_CHECKSUM_MISMATCH")
    taps = original_taps(read_json(root / "anchors.json"))
    pending = sorted(taps, key=lambda r: r["requested_ms"])
    frames, references = [], []
    cap = cv2.VideoCapture(str(video))
    next_ms, previous_ms, last_pixels, decoded, largest_native_gap = 0., -1, None, 0, 0
    try:
        if not cap.isOpened():
            raise ValueError("SOURCE_VIDEO_UNREADABLE")
        while True:
            if time.monotonic() - started > timeout_s:
                raise TimeoutError("PREPARATION_TIME_BUDGET_EXHAUSTED")
            ok, pixels = cap.read()
            if not ok:
                break
            pts = cap.get(cv2.CAP_PROP_POS_MSEC)
            if not _number(pts) or (decoded and pts <= previous_ms):
                raise ValueError("ACTUAL_MONOTONIC_SOURCE_PTS_REQUIRED")
            ms = round(pts)
            if decoded:
                largest_native_gap = max(largest_native_gap, ms - previous_ms)
            previous_ms, decoded, last_pixels = ms, decoded + 1, pixels
            due = []
            while pending and pending[0]["requested_ms"] <= ms:
                due.append(pending.pop(0))
            if ms >= next_ms or due:
                image = _save_image(out / "frames" / f"s{ms:09}.jpg", pixels, max_edge)
                frames.append({"frame_id": f"s{ms:09}", "media_ms": ms, **image})
                while next_ms <= ms:
                    next_ms += 1000 / fps
            for tap in due:
                if ms - tap["requested_ms"] > max(80, largest_native_gap):
                    raise ValueError("TAP_SOURCE_FRAME_UNAVAILABLE")
                h, w = pixels.shape[:2]
                b = tap["box"]
                x, y = int(b["x"] * w), int(b["y"] * h)
                right, bottom = min(w, math.ceil((b["x"] + b["w"]) * w)), min(h, math.ceil((b["y"] + b["h"]) * h))
                crop = _save_image(out / "references" / f"{tap['reference_id']}.jpg", pixels[y:bottom, x:right], 480, 90)
                ref = {**tap, "media_ms": ms, "source_frame_id": f"s{ms:09}", **crop}
                if tap["selection_hints"].get("visible_mask"):
                    from player_selection import decode_mask
                    mask = decode_mask(tap["selection_hints"]["visible_mask"])
                    if mask is not None:
                        foreground = cv2.resize(mask, (right - x, bottom - y), interpolation=cv2.INTER_NEAREST)
                        selected_pixels = pixels[y:bottom, x:right].copy()
                        selected_pixels[foreground == 0] = 96
                        ref["masked_view"] = _save_image(out / "references" / f"{tap['reference_id']}-mask.jpg", selected_pixels, 480, 90)
                references.append(ref)
        if not frames or last_pixels is None or pending:
            raise ValueError("SOURCE_OR_TAP_COVERAGE_INCOMPLETE")
        if frames[-1]["media_ms"] != previous_ms:
            image = _save_image(out / "frames" / f"s{previous_ms:09}.jpg", last_pixels, max_edge)
            frames.append({"frame_id": f"s{previous_ms:09}", "media_ms": previous_ms, **image})
    finally:
        cap.release()
    visual_plan = None
    if scene_packets:
        packets, visual_plan = plan_visual_packets(frames, previous_ms)
    else:
        packets = plan_packets(previous_ms, chunk_ms, overlap_ms)
    by_id = {f["frame_id"]: f for f in frames}
    for packet in packets:
        selected = [f for f in frames if packet["start_ms"] <= f["media_ms"] <= packet["end_ms"]]
        packet["frame_ids"] = [f["frame_id"] for f in selected]
        nearby = (sorted(references, key=lambda r: r["media_ms"]) if scene_packets else
            sorted(references, key=lambda r: (not packet["start_ms"] <= r["media_ms"] <= packet["end_ms"],
                abs(r["media_ms"] - (packet["start_ms"] + packet["end_ms"]) / 2)))[:5])
        packet["reference_ids"] = [r["reference_id"] for r in nearby]
        packet["source_video_sha256"] = sums[video.relative_to(root).as_posix()]
    gaps = [b["media_ms"] - a["media_ms"] for a, b in zip(frames, frames[1:])]
    covered = {i for p in packets for i in p["frame_ids"]}
    manifest = {"version": VERSION, "status": "PREPARED_NOT_MODEL_ANALYSED", "source_video": str(video),
        "source_video_sha256": digest(video), "original_taps_sha256": digest(root / "anchors.json"),
        "source_end_ms": previous_ms, "sampling_fps": fps, "max_edge": max_edge,
        "frames": frames, "references": sorted(references, key=lambda r: int(r["reference_id"][1:])),
        "packets": packets, "visual_packet_plan": visual_plan,
        "reference_policy": "CONSENSUS_RAW" if scene_packets else "ORIGINAL_WITH_STORED_MASKS",
        "input_coverage": {"complete": covered == set(by_id),
            "decoded_source_frames": decoded, "unique_delivered_frames": len(frames),
            "frame_appearances_with_overlap": sum(len(p["frame_ids"]) for p in packets),
            "max_sample_gap_ms": max(gaps, default=0), "max_native_frame_gap_ms": largest_native_gap,
            "all_taps_preserved": len(references) == len(taps), "time_authority": "ACTUAL_SOURCE_PTS"},
        "preparation_seconds": round(time.monotonic() - started, 3),
        "model_calls": 0, "detector_forwards": 0, "historical_model_results_used": False,
        "expected_reference_answers_used": False}
    write_json(out / "manifest.json", manifest)
    return manifest


def identity_items(manifest):
    """Read the original identity examples once, without action frames or answers."""
    items = [{"type": "text", "text": "Identify the single intended football player shared across these original user selection crops. "
        "Some clicks, broad crops and occlusions include neighbours. Compare all examples. "
        "Describe visible kit, number only when legible, hair and build. Separate contradictory/ambiguous examples. "
        "Choose at most three clearest reference IDs showing that same person, with complementary front/back views. "
        "Do not describe football actions, infer outcomes or invent an unseen number. "
        'Return JSON: {"identity_clear":true,"appearance":"concise visual description",'
        '"canonical_reference_ids":["r1"],"ambiguous_reference_ids":[],"contradictions":"visible ambiguity or empty"}. '
        "Use identity_clear=false if the examples cannot establish one intended person."}]
    for ref in manifest["references"]:
        items.extend([{"type": "text", "text": "Original selection " + ref["reference_id"]},
                      {"type": "image", "path": ref["path"], "sha256": ref["sha256"]}])
    return items


def apply_identity_profile(manifest, data):
    """Reuse an observed profile, never invent a target or select action times."""
    if isinstance(data, list) and len(data) == 1:
        data = data[0]
    if not isinstance(data, dict):
        raise ValueError("IDENTITY_PROFILE_UNRESOLVED")
    valid = {r["reference_id"] for r in manifest["references"]}
    chosen = data.get("canonical_reference_ids")
    description = data.get("appearance")
    if (data.get("identity_clear") is not True or not isinstance(chosen, list)
        or not 1 <= len(chosen) <= 3
        or any(not isinstance(x, str) or x not in valid for x in chosen) or len(set(chosen)) != len(chosen)
        or not isinstance(description, str) or not 1 <= len(description) <= 2000):
        raise ValueError("IDENTITY_PROFILE_UNRESOLVED")
    updated = deepcopy(manifest)
    updated["identity_profile"] = data
    for packet in updated["packets"]:
        packet["reference_ids"] = chosen[:]
    return updated


def packet_items(manifest, packet):
    """Ordered typed parts; every image is paired with its actual source time."""
    frames = {f["frame_id"]: f for f in manifest["frames"]}
    references = {r["reference_id"]: r for r in manifest["references"]}
    items = [{"type": "text", "text": PROMPT}]
    if manifest.get("identity_profile"):
        items.append({"type": "text", "text": "Shared identity profile inferred ONCE from the original selections; "
            "it is an identity description, not action evidence. Match this person throughout the play. "
            "A clearly different number/appearance identifies another person even in the same kit. "
            "Observe the ball sequence for all participants first; attribute it using the person seen at each contact. "
            "Do not transfer identity to the recipient or goal scorer. " + json.dumps(manifest["identity_profile"])})
    consensus = manifest.get("reference_policy") == "CONSENSUS_RAW"
    if consensus:
        items.append({"type": "text", "text":
            "REFERENCE SECTION: these are identity examples, NOT timeline frames or separate plays. "
            "Infer the SAME physical player shared across the original human selection areas. "
            "A broad box or isolated click may include a neighbouring player. Use the other references "
            "to resolve that ambiguity. Automatically generated masks are deliberately not supplied. "
            "reference_ids on a person must name POSITIVE visual matches, not comparison examples. "
            "If a person matches those references, selected=true. For a different person, selected=false "
            "and reference_ids=[]. If uncertain, use selected=null and ask IDENTITY. "
            "Keep passer and receiver separate even when their kits match. Prioritize releases and their "
            "outcomes; summarize receives/carries/dribbles in details instead of listing every touch."})
    for ref_id in packet["reference_ids"]:
        r = references[ref_id]
        items.extend([{"type": "text", "text": json.dumps({"selected_reference": ref_id,
            "source_ms": r["media_ms"], "source_box": r["box"], "original_positive_point": r["target_point"],
            "selection_hints": {k: v for k, v in r.get("selection_hints", {}).items() if k != "visible_mask"}})},
            {"type": "image", "path": r["path"], "sha256": r["sha256"]}])
        if r.get("masked_view") and not consensus:
            masked = r["masked_view"]
            items.extend([{"type": "text", "text": f"{ref_id}: original stored visible-person mask, same source instant; grey pixels are excluded."},
                          {"type": "image", "path": masked["path"], "sha256": masked["sha256"]}])
    items.append({"type": "text", "text": "REFERENCE SECTION ENDED. Only the following full-source "
        "images are chronological action evidence. Observe the complete supplied interval: "
        + json.dumps({k: packet[k] for k in ("start_ms", "end_ms", "core_start_ms", "core_end_ms", "visual_cut_candidates_ms") if k in packet})})
    if packet.get("question"):
        items.append({"type": "text", "text": "Inspect this missing connection in the whole supplied play: "
                      + json.dumps(packet["question"], separators=(",", ":"))})
    for frame_id in packet["frame_ids"]:
        f = frames[frame_id]
        items.extend([{"type": "text", "text": f"Source frame {frame_id}, media_ms={f['media_ms']}"},
                      {"type": "image", "path": f["path"], "sha256": f["sha256"]}])
    return items


def parse_response(text):
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1])
    data = json.loads(text)
    if not isinstance(data, dict) or not isinstance(data.get("plays"), list):
        raise ValueError("MODEL_PLAYS_ARRAY_REQUIRED")
    return data


def resolve_response(data, manifest, packet, receipt):
    """One owner for attribution, causal outcomes and missing-link questions."""
    frames = {f["frame_id"]: f["media_ms"] for f in manifest["frames"] if f["frame_id"] in packet["frame_ids"]}
    refs = set(packet["reference_ids"])
    events, questions, invalid = [], [], []
    def ms(key):
        return frames.get(key) if isinstance(key, str) else None
    def cited(values):
        return list(dict.fromkeys(v for v in values if isinstance(v, str) and v in frames)) if isinstance(values, list) else []
    def question(play, reason, action_id=None, focus_ms=None):
        questions.append({"reason": reason, "action_id": action_id, "start_ms": ms(play.get("start_frame")),
                          "end_ms": ms(play.get("end_frame")), "focus_ms": focus_ms,
                          "source_action_key": f"{packet['packet_id']}:{play_index}:{action_id}" if action_id else None,
                          "source_packet_id": packet["packet_id"]})
    for play_index, play in enumerate(data["plays"][:100]):
        if not isinstance(play, dict) or ms(play.get("start_frame")) is None or ms(play.get("end_frame")) is None:
            invalid.append("PLAY_SOURCE_BOUNDS_MISSING"); continue
        start, end = ms(play["start_frame"]), ms(play["end_frame"])
        if start > end:
            invalid.append("PLAY_SOURCE_ORDER_INVALID"); continue
        people, identity_conflicts = {}, set()
        for p in play.get("people") or []:
            if not isinstance(p, dict) or not isinstance(p.get("person_id"), str):
                continue
            pid = p["person_id"]
            if pid in people:
                identity_conflicts.add(pid)
            ref_support = [v for v in p.get("reference_ids") or [] if isinstance(v, str) and v in refs]
            support = cited(p.get("evidence_frames"))
            selected = p.get("selected") if type(p.get("selected")) is bool else None
            if (manifest.get("reference_policy") == "CONSENSUS_RAW" and selected is False
                    and ref_support and support and p.get("kit_consistent") is True):
                selected = None  # contradictory positive match needs clarification, never forced credit
            if selected is True and (not ref_support or not support or p.get("kit_consistent") is False):
                selected = None
            people[pid] = {"selected": selected, "reference_ids": ref_support, "evidence_frames": support}
        selected_ids = [pid for pid, p in people.items() if p["selected"] is True]
        if len(selected_ids) > 1:
            identity_conflicts.update(selected_ids)
        for pid in identity_conflicts:
            people[pid]["selected"] = None
        if identity_conflicts:
            question(play, "IDENTITY_CONFLICT")
        for action_index, action in enumerate(play.get("actions") or []):
            if not isinstance(action, dict):
                invalid.append("INVALID_ACTION"); continue
            kind = str(action.get("kind") or "OTHER").upper()
            kind = kind if kind in {"PASS", "CROSS", "SHOT", "DRIBBLE", "CARRY", "DUEL", "RECOVERY", "RECEIVE", "RUN", "OTHER"} else "OTHER"
            astart, aend, contact = (ms(action.get(k)) for k in ("start_frame", "end_frame", "contact_frame"))
            actor = people.get(action.get("actor"))
            evidence = cited(action.get("actor_evidence_frames"))
            if actor is None or astart is None or aend is None or not start <= astart <= aend <= end or not evidence:
                invalid.append("ACTION_ACTOR_OR_SOURCE_EVIDENCE_MISSING"); continue
            if any(not astart <= frames[f] <= aend for f in evidence) or (contact is not None and not astart <= contact <= aend):
                invalid.append("ACTION_SOURCE_ORDER_INVALID"); continue
            action_id = action.get("action_id", f"a{action_index}")
            if contact is None and kind in {"SHOT", "PASS", "CROSS"}:
                question(play, "CONTACT", action_id, astart)
            if actor["selected"] is None:
                question(play, "IDENTITY", action_id, contact or astart)
            outcome = str(action.get("outcome") or "UNKNOWN").upper()
            oms, receiver_ms, shot_ms = (ms(action.get(k)) for k in ("outcome_frame", "receiver_frame", "shot_frame"))
            outcome_evidence = [{"frame": v["frame"], "fact": str(v.get("fact") or "")[:500]}
                for v in action.get("outcome_evidence") or [] if isinstance(v, dict)
                and ms(v.get("frame")) is not None and str(v.get("fact") or "").strip()]
            visible_outcome = bool(contact is not None and oms is not None and contact <= oms <= end
                and any(contact <= frames[v["frame"]] <= end for v in outcome_evidence)
                and action.get("same_active_ball") is True and action.get("continuous_play") is True)
            event_type, resolved_outcome, reason = kind, outcome, "VISIBLE_ACTION"
            receiver = people.get(action.get("receiver"))
            if kind == "SHOT":
                if visible_outcome and outcome in {"GOAL", "SAVED", "BLOCKED", "OFF_TARGET"}:
                    event_type = "GOAL" if outcome == "GOAL" else "SHOT"
                    reason = "VISIBLE_SHOT_OUTCOME"
                else:
                    resolved_outcome, reason = "UNKNOWN", "SHOT_OUTCOME_MISSING"
                    question(play, "OUTCOME", action_id, oms or aend)
            elif kind in {"PASS", "CROSS"}:
                if action.get("receiver_is_teammate") is False:
                    resolved_outcome, reason = "INCOMPLETE", "VISIBLE_OPPONENT_RECEIPT"
                elif outcome == "TEAMMATE_GOAL":
                    chain = (visible_outcome and receiver is not None and bool(receiver["evidence_frames"])
                        and action.get("receiver") == action.get("finisher")
                        and action.get("receiver_is_teammate") is True and receiver["selected"] is False
                        and receiver_ms is not None and shot_ms is not None and contact <= receiver_ms <= shot_ms <= oms)
                    if chain:
                        event_type, reason = "ASSIST", "VISIBLE_DIRECT_ASSIST"
                    else:
                        resolved_outcome, reason = "UNKNOWN", "DIRECT_ASSIST_LINK_MISSING"
                        question(play, "RECEIVER", action_id, receiver_ms or contact or astart)
                elif outcome not in {"COMPLETED", "INCOMPLETE", "TEAMMATE_SHOT"}:
                    resolved_outcome = "UNKNOWN"
            key = f"{packet['packet_id']}:{play_index}:{action_index}"
            event = {"event_id": hashlib.sha256(key.encode()).hexdigest()[:20], "source_packet_ids": [packet["packet_id"]],
                "source_action_keys": [f"{packet['packet_id']}:{play_index}:{action_id}"],
                "source_video_sha256": manifest["source_video_sha256"], "kind": kind, "event_type": event_type,
                "outcome": resolved_outcome, "start_ms": astart, "end_ms": aend, "contact_ms": contact,
                "outcome_ms": oms, "selected_player": actor["selected"], "actor": action.get("actor"),
                "actor_scope": f"{packet['packet_id']}:{play_index}", "actor_evidence_frames": evidence,
                "reference_ids": actor["reference_ids"], "outcome_evidence": outcome_evidence,
                "receiver": action.get("receiver"), "finisher": action.get("finisher"),
                "reason": reason, "details": str(action.get("details") or "")[:1500],
                "receipts": [receipt], "review_phase": packet.get("phase", "INITIAL"),
                "proof_eligible": bool(actor["selected"] is True and
                    ((kind not in {"SHOT", "PASS", "CROSS"}) or (contact is not None and reason in
                         {"VISIBLE_SHOT_OUTCOME", "VISIBLE_DIRECT_ASSIST", "VISIBLE_ACTION", "VISIBLE_OPPONENT_RECEIPT"})))}
            events.append(event)
        for q in play.get("questions") or []:
            if isinstance(q, dict) and q.get("reason") in {"IDENTITY", "CONTACT", "RECEIVER", "OUTCOME"}:
                question(play, q["reason"], q.get("action_id"))
    return {"events": events, "questions": questions, "invalid_rows": invalid}


def reconcile(results, *, sampling_gap_ms=125):
    """Merge one release/terminal observation while preserving disagreements."""
    events, questions, conflicts = [], [], []
    for result in results:
        questions.extend(result["questions"])
        for incoming in result["events"]:
            row = deepcopy(incoming)
            def same(old):
                if old["source_video_sha256"] != row["source_video_sha256"] or old["kind"] != row["kind"]:
                    return False
                if old["selected_player"] is not True or row["selected_player"] is not True:
                    return False  # cross-packet non-target identities have not been established
                overlap = min(old["end_ms"], row["end_ms"]) >= max(old["start_ms"], row["start_ms"])
                contact_match = (old["contact_ms"] is not None and row["contact_ms"] is not None
                    and abs(old["contact_ms"] - row["contact_ms"]) <= max(100, 2 * sampling_gap_ms))
                terminal_match = (old["outcome_ms"] is not None and row["outcome_ms"] is not None
                    and abs(old["outcome_ms"] - row["outcome_ms"]) <= max(100, 2 * sampling_gap_ms))
                terminal_compatible = old["outcome"] == row["outcome"] or "UNKNOWN" in {old["outcome"], row["outcome"]}
                shared_actor_frame = bool(set(old["actor_evidence_frames"]) & set(row["actor_evidence_frames"]))
                return overlap and (contact_match or (terminal_match and terminal_compatible) or
                    (old["contact_ms"] is None and row["contact_ms"] is None and shared_actor_frame))
            old = next((e for e in events if same(e)), None)
            if old is None:
                events.append(row); continue
            disagreements = {old["outcome"], row["outcome"]} - {"UNKNOWN"}
            incompatible = len(disagreements) > 1 and not disagreements <= {"COMPLETED", "TEAMMATE_SHOT", "TEAMMATE_GOAL"}
            reviewed_again = row.get("review_phase") == "FOLLOWUP" and old.get("review_phase") != "FOLLOWUP" and row["proof_eligible"]
            if reviewed_again:
                previous = deepcopy(old); old.update(row); row = previous
                old.setdefault("superseded_observations", []).append({k: previous[k] for k in
                    ("outcome", "contact_ms", "outcome_ms", "reason", "receipts")})
                conflicts = [c for c in conflicts if c["event_id"] != previous["event_id"]]
            elif incompatible:
                old["proof_eligible"] = False
                old["reason"] = "CONFLICTING_OBSERVED_OUTCOMES"
                conflicts.append({"event_id": old["event_id"], "observed_outcomes": sorted(disagreements)})
                questions.append({"reason": "OUTCOME_CONFLICT", "start_ms": min(old["start_ms"], row["start_ms"]),
                                  "end_ms": max(old["end_ms"], row["end_ms"]), "source_packet_id": row["source_packet_ids"][0]})
            elif old["reason"] == "CONFLICTING_OBSERVED_OUTCOMES":
                pass  # another initial opinion cannot silently settle a conflict
            elif row["proof_eligible"] and not old["proof_eligible"]:
                previous = deepcopy(old); old.update(row); row = previous
            elif old["outcome"] == "UNKNOWN" and row["outcome"] != "UNKNOWN":
                previous = deepcopy(old); old.update(row); row = previous
            old["source_packet_ids"] = sorted(set(old["source_packet_ids"] + row["source_packet_ids"]))
            old["source_action_keys"] = sorted(set(old["source_action_keys"] + row["source_action_keys"]))
            old["receipts"].extend(row["receipts"])
            old["actor_evidence_frames"] = sorted(set(old["actor_evidence_frames"] + row["actor_evidence_frames"]))
            contacts = [v for v in (old.get("contact_ms"), row.get("contact_ms")) if v is not None]
            if contacts:
                old["contact_interval_ms"] = [min(contacts), max(contacts)]
    target = sorted([e for e in events if e["selected_player"] is True and e["proof_eligible"]], key=lambda e: e["contact_ms"] or e["start_ms"])
    # A wider overlapping packet may already provide exactly the missing link.
    # Do not ask the model to approve that completed observation again.
    def answered(q):
        for e in events:
            if not q.get("source_action_key") or q["source_action_key"] not in e["source_action_keys"]:
                continue
            if q["reason"] == "IDENTITY" and e["selected_player"] is not None:
                return True
            if q["reason"] == "CONTACT" and e["contact_ms"] is not None:
                return True
            if q["reason"] == "OUTCOME" and e["proof_eligible"] and e["outcome"] != "UNKNOWN":
                return True
            if q["reason"] == "RECEIVER" and e["reason"] in {"VISIBLE_DIRECT_ASSIST", "VISIBLE_OPPONENT_RECEIPT"}:
                return True
        return False
    questions = [q for q in questions if not answered(q)]
    return {"events": events, "target_events": target, "counts": dict(Counter(e["event_type"] for e in target)),
            "questions": questions, "conflicts": conflicts}


def followup_plan(manifest, resolved, *, limit=2, max_span_ms=30000):
    """Only concrete missing links, one round, complete context around the play."""
    jobs = []
    priorities = {"IDENTITY_CONFLICT": 0, "OUTCOME_CONFLICT": 0, "RECEIVER": 1, "OUTCOME": 1, "CONTACT": 2, "IDENTITY": 3}
    questions = sorted(resolved["questions"], key=lambda q: (priorities.get(q["reason"], 4), q.get("start_ms") or 0))
    for q in questions:
        if len(jobs) >= limit:
            break
        if not _number(q.get("start_ms")) or not _number(q.get("end_ms")):
            continue
        start = max(0, q["start_ms"] - 1500)
        end = min(manifest["source_end_ms"], q["end_ms"] + 5000)
        if end - start > max_span_ms:
            continue  # never silently truncate an observation's full context
        if any(start <= j["question"]["end_ms"] and end >= j["question"]["start_ms"] for j in jobs):
            continue
        base = min(manifest["packets"], key=lambda p: abs((p["start_ms"] + p["end_ms"]) / 2 - (start + end) / 2))
        jobs.append({"packet_id": f"followup_{len(jobs)+1:03}", "phase": "FOLLOWUP", "round": 1,
            "start_ms": start, "end_ms": end, "question": q, "source_video_sha256": manifest["source_video_sha256"],
            "reference_ids": base["reference_ids"],
            "frame_ids": [f["frame_id"] for f in manifest["frames"] if start <= f["media_ms"] <= end]})
    return jobs


def prepare_followups(manifest, jobs, output_dir, *, detail_fps=24., timeout_s=30.):
    """Reuse the complete overview; add native detail around the missing link.

    No detector, old identity flags or predicted ball coordinates are consulted.
    One sequential decode supplies at most 2.4 seconds of denser images per job.
    """
    import cv2
    if not _number(detail_fps) or not 1 <= detail_fps <= 30:
        raise ValueError("INVALID_DETAIL_SAMPLING_RATE")
    if not jobs:
        return deepcopy(manifest), []
    if digest(manifest["source_video"]) != manifest["source_video_sha256"]:
        raise ValueError("SOURCE_VIDEO_CHANGED")
    started, enriched = time.monotonic(), deepcopy(manifest)
    by_ms = {f["media_ms"]: f for f in enriched["frames"]}
    neighborhoods = []
    for j in jobs:
        center = j["question"].get("focus_ms")
        center = center if _number(center) else (j["question"]["start_ms"] + j["question"]["end_ms"]) / 2
        lo, hi = max(j["start_ms"], center - 1200), min(j["end_ms"], center + 1200)
        neighborhoods.append({"start_ms": lo, "end_ms": hi, "next_ms": lo})
    cap = cv2.VideoCapture(manifest["source_video"])
    try:
        previous_ms = -1
        while True:
            if time.monotonic() - started > timeout_s:
                raise TimeoutError("DETAIL_PREPARATION_TIME_BUDGET_EXHAUSTED")
            ok, pixels = cap.read()
            if not ok:
                break
            pts = cap.get(cv2.CAP_PROP_POS_MSEC)
            if not _number(pts) or pts <= previous_ms:
                raise ValueError("ACTUAL_MONOTONIC_SOURCE_PTS_REQUIRED")
            ms, previous_ms = round(pts), pts
            needed = [n for n in neighborhoods if n["next_ms"] <= ms <= n["end_ms"]]
            if needed:
                frame_id = f"s{ms:09}"
                image = _save_image(Path(output_dir) / "details" / f"{frame_id}.jpg", pixels, 1280, 80)
                by_ms[ms] = {"frame_id": frame_id, "media_ms": ms, **image}
                for n in needed:
                    while n["next_ms"] <= ms:
                        n["next_ms"] += 1000 / detail_fps
            if ms > max(n["end_ms"] for n in neighborhoods):
                break
    finally:
        cap.release()
    enriched["frames"] = sorted(by_ms.values(), key=lambda f: f["media_ms"])
    enriched["detail_preparation_seconds"] = round(time.monotonic() - started, 3)
    for j in jobs:
        j["frame_ids"] = [f["frame_id"] for f in enriched["frames"] if j["start_ms"] <= f["media_ms"] <= j["end_ms"]]
    write_json(Path(output_dir) / "followup-manifest.json", enriched)
    return enriched, jobs


def assess_reference_cases(cases, resolved):
    """Evaluation-only navigation anchors. Never imported by request planning."""
    events, used, checks = resolved.get("target_events") or [], set(), []
    for case in cases:
        reference, tolerance = case["reference_ms"], case.get("tolerance_ms", 1000)
        eligible = []
        for e in events:
            if e["event_id"] in used or (e["event_type"], e["outcome"]) != (case["expected_type"], case["expected_outcome"]):
                continue
            contact = e["contact_ms"] if e["contact_ms"] is not None else e["start_ms"]
            # User times locate the actor's action, not necessarily its final kick.
            distance = max(e["start_ms"] - reference, reference - contact, 0)
            if distance <= tolerance:
                eligible.append((distance, abs(contact - reference), e))
        winner = min(eligible, key=lambda row: row[:2])[2] if eligible else None
        if winner:
            used.add(winner["event_id"])
        checks.append({"case_id": case["case_id"], "status": "MATCHED" if winner else "NOT_VERIFIED",
                       "event_id": winner["event_id"] if winner else None,
                       "observed_contact_ms": winner["contact_ms"] if winner else None})
    extras = [e["event_id"] for e in events if e["event_type"] in {"GOAL", "ASSIST", "SHOT"} and e["event_id"] not in used]
    return {"all_reference_cases_matched": all(c["status"] == "MATCHED" for c in checks),
            "unexpected_scoring_event_ids": extras, "cases": checks,
            "expected_answers_supplied_to_model": False,
            "note": "Matching stored model observations is not independent proof of visual correctness."}
