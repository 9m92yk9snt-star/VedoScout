"""Measured shared context and bounded searches; never canonical event proof.

Rebuilt from FIX28's recorded design on the verified FIX22 source. Expected
shirt numbers, reference event times and model event claims are not facts here.
"""
from copy import deepcopy
import hashlib
import json
import math

SOURCE = "MEASURED_SEQUENCE_CONTEXT"
QUESTIONS = {"CONTACT", "RECEIVER", "SHOT", "OUTCOME", "IDENTITY", "BALL_REAPPEARANCE"}
STEPS = {"RECEIVE", "CONTROL", "TURN", "RELEASE", "SHOT_MOTION", "INTERVENTION", "BALL_NEAR_GOAL", "UNRESOLVED"}
KINDS = {"PASS_CHAIN", "SHOT_CHAIN", "SAVE_POSSIBILITY", "GOAL_POSSIBILITY", "UNKNOWN"}


def num(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def actual(frame, scene=None):
    return (isinstance(frame, dict) and num(frame.get("media_ms"))
            and frame.get("time_authority") == "ACTUAL_MEDIA_PTS"
            and not any(frame.get(k) for k in ("cut", "cut_barrier", "used_fallback"))
            and (scene is None or frame.get("scene_id") == scene))


def labels(frames):
    tracks = sorted({p["local_track_id"] for f in frames for p in f.get("players") or []
                     if isinstance(p.get("local_track_id"), str)})
    return {track: f"body_{i+1}" for i, track in enumerate(tracks)}


def fingerprint(packet):
    packet.pop("fingerprint", None)
    packet["fingerprint"] = hashlib.sha256(json.dumps(packet, sort_keys=True, separators=(",", ":"),
                                                        allow_nan=False).encode()).hexdigest()
    return packet


def _rows(value):
    return value if isinstance(value, (list, tuple)) else []


def _choice(value, choices):
    return value if isinstance(value, str) and value in choices else None


def native_focuses(job, frames):
    """Repeated near-foot native proposals choose pixels, never a contact."""
    import dense_track_refinement
    import ball_contact_engine
    import frame_geometry
    groups = {}
    for f in frames:
        scale = frame_geometry.horizontal_scale(f)
        if not actual(f, job.get("scene_id")) or scale is None:
            continue
        target = f.get("global_target") or {}
        for p in f.get("players") or []:
            if p.get("association_state") != "VERIFIED_LOCAL" or not isinstance(p.get("local_track_id"), str):
                continue
            for b in f.get("ball_candidates") or []:
                if (not num(b.get("confidence")) or b["confidence"] < dense_track_refinement.DENSE_BALL_CONF_T
                        or b.get("proof_eligible") is False or b.get("support_only") or b.get("used_fallback")
                        or b.get("state") not in {None, "MEASURED", "MEASURED_REACQUISITION"}):
                    continue
                try:
                    distance = ball_contact_engine._lower_body_geometry(p["box"], b["box"], scale)["distance_h"]
                except (KeyError, TypeError, ValueError, ZeroDivisionError):
                    continue
                if distance <= ball_contact_engine.POSSESSION_MAX_H:
                    key = p["local_track_id"]
                    groups.setdefault(key, []).append((int(f["media_ms"]), distance,
                        target.get("proof_eligible") is True and target.get("local_track_id") == key))
    candidates = []
    for track, samples in groups.items():
        clusters = []
        for row in sorted(set(samples)):
            if not clusters or row[0]-clusters[-1][-1][0] > 80:
                clusters.append([])
            clusters[-1].append(row)
        for cluster in clusters:
            if len({r[0] for r in cluster}) < 2:
                continue
            middle = cluster[len(cluster)//2][0]
            pivot = min(cluster, key=lambda r: (r[1], abs(r[0]-middle), r[0]))
            variation = max(r[1] for r in cluster)-min(r[1] for r in cluster)
            candidates.append((not any(r[2] for r in cluster), -variation, -len(cluster), pivot[0], track))
    return [{"media_ms": r[3], "local_track_id": r[4], "reason": "NATIVE_LOWER_BODY_SEARCH",
             "canonical_authority": False} for r in sorted(candidates)[:1]]


def sampling_plan(job, frames, budget=12):
    if budget <= 0:
        return {"media_ms": [], "focuses": [], "canonical_authority": False}
    available = sorted({int(f["media_ms"]) for f in frames if actual(f, job.get("scene_id"))
                        and job["start_ms"] <= f["media_ms"] <= job["end_ms"]})
    if len(available) <= budget:
        return {"media_ms": available, "focuses": [], "canonical_authority": False}
    if budget <= 2:
        return {"media_ms": sorted({available[0], available[-1]})[:max(0, budget)],
                "focuses": [], "canonical_authority": False}
    available_set = set(available)
    valid = [f for f in frames if f.get("media_ms") in available_set]
    focus = ([{"media_ms": job["center_ms"], "reason": "SUPPLIED_SEARCH_TIME", "canonical_authority": False}]
             if job.get("has_contact_time") and num(job.get("center_ms")) else native_focuses(job, valid))
    near = lambda ms: min(available, key=lambda t: (abs(t-ms), t))
    selected = {available[0], available[-1]}
    for row in focus:
        for offset in ((-50, 0, 50) if job.get("has_contact_time") else (-33, 0, 17, 50)):
            if len(selected) < budget:
                selected.add(near(row["media_ms"]+offset))
    if not focus and num(job.get("center_ms")):
        selected.add(near(job["center_ms"]))
    while len(selected) < budget:
        selected.add(max((t for t in available if t not in selected),
                         key=lambda t: (min(abs(t-s) for s in selected), -t)))
    return {"media_ms": sorted(selected), "focuses": focus, "canonical_authority": False}


def build(window, frames, *, trace=None, times=None, source_video=None):
    trace = trace if isinstance(trace, dict) else {}
    scene = window.get("scene_id")
    valid = [f for f in frames if actual(f, scene)]
    mapping = labels(frames)
    if times is None and valid:
        times = [valid[round((len(valid)-1)*i/max(1, min(23, len(valid)-1)))]["media_ms"]
                 for i in range(min(24, len(valid)))]
    wanted = set(times or [])
    bodies = []
    seen = set()
    for f in valid:
        if f["media_ms"] not in wanted:
            continue
        for p in f.get("players") or []:
            track = p.get("local_track_id")
            if (track not in mapping or p.get("association_state") != "VERIFIED_LOCAL"
                    or (f["media_ms"], track) in seen):
                continue
            seen.add((f["media_ms"], track))
            target = f.get("global_target") or {}
            bodies.append({"media_ms": f["media_ms"], "body_id": mapping[track], "track_id": track,
                           "box": deepcopy(p.get("box")), "target_observed": bool(
                               target.get("proof_eligible") is True and target.get("local_track_id") == track)})
    contacts = [{k: deepcopy(t.get(k)) for k in ("touch_id", "media_ms", "representative_ms", "scene_id",
                 "player_track_id", "global_target_id", "contact_role", "team_relation")}
                for t in (trace.get("touch_graph") or {}).get("touches") or []
                if t.get("status") == "VERIFIED" and t.get("proof_eligible") is True]
    # Relevant target contacts lead, then retain chronological neighboring acts.
    contacts.sort(key=lambda t: (t.get("global_target_id") != "GLOBAL_TARGET", t.get("media_ms") or 0))
    return fingerprint({"source": SOURCE, "canonical_authority": False, "scene_id": scene,
        "source_video_sha256": (source_video or trace.get("source_video") or {}).get("sha256"),
        "bounds_ms": [window.get("start_ms"), window.get("end_ms")],
        "requested_question": window.get("reason"),
        "source_trace_ids": trace.get("source_trace_ids") or ([trace["trace_id"]] if trace.get("trace_id") else []),
        "body_observations": bodies, "verified_contacts": contacts[:32],
        "roles": {track: {"role": role.get("role"), "status": role.get("status"),
                  "evidence_ms": [v.get("media_ms") for v in role.get("votes") or []][:8]}
                  for track, role in (trace.get("role_evidence") or {}).items() if isinstance(role, dict)},
        "barrier_media_ms": sorted({f["media_ms"] for f in frames if num(f.get("media_ms")) and not actual(f, scene)}),
        "searches": deepcopy(trace.get("attack_search_plan") or {}),
        "unresolved_reasons": list(trace.get("unresolved_reasons") or [])[:12]})


def with_related(packet, related, trace_id):
    if (not isinstance(related, dict) or related.get("source") != SOURCE
            or trace_id not in (related.get("source_trace_ids") or []) or packet.get("scene_id") != related.get("scene_id")
            or not packet.get("source_video_sha256")
            or packet["source_video_sha256"] != related.get("source_video_sha256")):
        return packet
    result = deepcopy(packet)
    result["related_sequence"] = deepcopy(related)
    # Related tracks use explicit entity IDs, never the local crop's body_N.
    for row in result["related_sequence"].get("body_observations") or []:
        row.pop("body_id", None)
        row["entity_id"] = row.pop("track_id")
    result["local_to_entity"] = (related.get("entity_mappings") or {}).get(trace_id) or {}
    return fingerprint(result)


def reader_view(packet):
    result = {k: deepcopy(packet.get(k)) for k in ("source", "fingerprint", "scene_id", "source_video_sha256",
                "bounds_ms", "requested_question", "source_trace_ids", "roles", "barrier_media_ms", "unresolved_reasons")}
    result["contacts"] = [{"id": t.get("touch_id"), "ms": t.get("representative_ms") or t.get("media_ms"),
        "track_id": t.get("player_track_id"), "target_observed": t.get("global_target_id") == "GLOBAL_TARGET",
        "role": (t.get("contact_role") or {}).get("role"), "role_status": (t.get("contact_role") or {}).get("status"),
        "team": (t.get("team_relation") or {}).get("team")} for t in packet.get("verified_contacts") or []]
    search = packet.get("searches") or {}
    result["searches"] = {"questions": search.get("questions", [])[:4],
        "episodes": [{k: e.get(k) for k in ("strike_id", "contact_ms", "start_ms", "end_ms", "terminal_observed_ms")}
                     for e in search.get("episodes", [])[:4]], "canonical_authority": False}
    relevant = {t.get("player_track_id") for t in packet.get("verified_contacts") or []}
    seen = set(); result["body_references"] = []
    for row in packet.get("body_observations") or []:
        track = row.get("track_id") or row.get("entity_id")
        if track not in seen and (row.get("target_observed") or track in relevant):
            seen.add(track); result["body_references"].append(deepcopy(row))
    result["body_references"] = result["body_references"][:16]
    if packet.get("related_sequence"):
        result["local_to_entity"] = deepcopy(packet.get("local_to_entity"))
        result["related_sequence"] = reader_view(packet["related_sequence"])
    result["canonical_authority"] = False
    return result


def parse_reasoning(data, times, manifest):
    data = data if isinstance(data, dict) else {}
    by_ms = {r["media_ms"]: r for r in manifest or []}
    def when(index):
        return times[index-1] if type(index) is int and 1 <= index <= len(times) else None
    hypotheses, requests = [], []
    for row in _rows(data.get("hypotheses"))[:4]:
        if not isinstance(row, dict) or not _choice(row.get("kind"), KINDS):
            continue
        steps = []
        for step in _rows(row.get("steps"))[:8]:
            if not isinstance(step, dict) or not _choice(step.get("observation"), STEPS):
                continue
            ms, body = when(step.get("idx")), step.get("body_id")
            supplied = {b.get("body_id") for b in by_ms.get(ms, {}).get("bodies") or []}
            if ms is not None and (body is None or isinstance(body, str) and body in supplied):
                steps.append({"media_ms": ms, "body_id": body, "observation": step["observation"]})
        if steps:
            hypotheses.append({"kind": row["kind"], "steps": steps, "status": "HYPOTHESIS", "canonical_authority": False})
    for row in _rows(data.get("review_requests"))[:4]:
        if not isinstance(row, dict) or not _choice(row.get("question"), QUESTIONS):
            continue
        ms = when(row.get("idx"))
        if ms is not None:
            requests.append({"media_ms": ms, "question": row["question"], "source": "MODEL_SEQUENCE_SEARCH",
                             "direction": _choice(row.get("direction"), {"BEFORE", "AFTER", "AROUND"}) or "AROUND",
                             "canonical_authority": False})
    return {"hypotheses": hypotheses, "review_requests": requests, "canonical_authority": False}


def outcome_explanations(data, times):
    result = []
    for row in _rows((data or {}).get("outcome_explanations"))[:5] if isinstance(data, dict) else []:
        if not isinstance(row, dict) or not _choice(row.get("hypothesis"), {"GOAL_AFTER_OCCLUSION", "KEEPER_CONTACT", "OUTSIDE_GOAL", "OTHER_BALL", "UNRESOLVED"}):
            continue
        result.append({"hypothesis": row["hypothesis"], "status": "EXPLANATION_ONLY", "canonical_authority": False,
            **{key.replace("indices", "media_ms"): sorted({times[i-1] for i in _rows(row.get(key))
                if type(i) is int and 1 <= i <= len(times)}) for key in ("supporting_indices", "contradicting_indices")},
            "missing_observation": str(row.get("missing_observation") or "")[:240]})
    return result


def model_requests(trace):
    result = [r for i in trace.get("action_inspections") or []
              for r in _rows((i.get("sequence_reasoning") or {}).get("review_requests"))]
    result.extend(r for o in trace.get("outcome_evidence") or []
                  for r in _rows((o.get("goal_geometry_evidence") or {}).get("goal_review_requests")))
    return result


def requested_centers(trace, frames, extra=()):
    result = []
    scene = (trace.get("window") or {}).get("scene_id")
    for request in model_requests(trace)+list(extra):
        if (not isinstance(request, dict) or request.get("canonical_authority") is not False
                or not _choice(request.get("question"), QUESTIONS) or not num(request.get("media_ms"))):
            continue
        ms = request["media_ms"]
        pivot = ms + (250 if request.get("direction") == "AFTER" else -150 if request.get("direction") == "BEFORE" else 0)
        path = sorted([f for f in frames if num(f.get("media_ms")) and min(ms, pivot) <= f["media_ms"] <= max(ms, pivot)], key=lambda f: f["media_ms"])
        if (not any(f["media_ms"] == ms for f in path) or any(not actual(f, scene) for f in path)
                or any(b["media_ms"]-a["media_ms"] > 80 for a, b in zip(path, path[1:]))):
            continue
        measured = request.get("source") == "MEASURED_CHAIN_SEARCH"
        rank = -2 if measured and request.get("utility", 0) >= 5 else -1
        result.append((rank, min((f["media_ms"] for f in path), key=lambda t: abs(t-pivot)),
                       ("CHAIN_SEARCH_" if measured else "MODEL_SEQUENCE_")+request["question"]))
    return result
