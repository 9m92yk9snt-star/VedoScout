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


def video_observations(observation, frames, window):
    """Translate clip indices to measured bodies/source PTS for the existing resolver.

    This creates observations, not events. Player identity, team/ball transfer
    and causal ownership are still resolved against the shared native graph.
    """
    import football_sequence_intelligence as sequence
    obs = observation or {}
    clip, transport = obs.get("motion_clip") or {}, obs.get("video_input") or {}
    times = clip.get("frame_source_ms") or []
    if (obs.get("observation_protocol") != "SOURCE_INDEXED_MOTION_CLIP_V1"
            or obs.get("clip_review_complete") is not True
            or obs.get("status") not in {"COMPLETED", "PARTIAL_RESPONSE"}
            or transport.get("sampling_prepared_for_provider") is not True
            or transport.get("sampling_strategy") != "SOURCE_INDEXED_1FPS_PLAYBACK"
            or transport.get("playback_fps") != 1
            or transport.get("frame_source_ms") != times
            or not obs.get("input_sha256") or not obs.get("response_sha256")
            or not clip.get("clip_sha256") or clip["clip_sha256"] != transport.get("model_video_sha256")
            or len(times) < 2 or any(type(t) is not int for t in times)
            or any(b <= a for a, b in zip(times, times[1:]))):
        return {"sequences": []}
    by_ms = {f["media_ms"]: f for f in frames if actual(f, window.get("scene_id"))}
    if any(t not in by_ms for t in times):
        return {"sequences": []}
    served = {row["media_ms"]: {b["body_id"]: b.get("local_track_id") for b in row.get("source_bodies") or []}
              for row in obs.get("body_search_regions") or []}
    def at(index):
        return times[index-1] if type(index) is int and 1 <= index <= len(times) else None
    def body(index, label):
        ms = at(index)
        track = served.get(ms, {}).get(label)
        candidates = [p for p in by_ms.get(ms, {}).get("players") or []
                      if track and p.get("local_track_id") == track and p.get("association_state") == "VERIFIED_LOCAL"]
        return candidates[0] if len(candidates) == 1 else None
    sid = "motion_" + str(obs["input_sha256"])[:20]
    actions = []
    for index, raw in enumerate(_rows(obs.get("video_actions"))):
        if not isinstance(raw, dict):
            continue
        if any(raw.get(k) is not None and at(raw[k]) is None for k in
               ("start_idx", "contact_idx", "end_idx", "receiver_idx", "shot_idx", "outcome_idx")):
            continue
        start, contact, end = (at(raw.get(k)) for k in ("start_idx", "contact_idx", "end_idx"))
        if start is None or end is None or start > end or (contact is not None and not start <= contact <= end):
            continue
        actor_evidence, actor_ids = [], set()
        for i in _rows(raw.get("actor_evidence_indices")):
            b, ms = body(i, raw.get("actor_body_id")), at(i)
            if b and start <= ms <= end:
                actor_evidence.append({"media_ms": ms, "box": deepcopy(b["box"]), "visibility": "VISIBLE"})
                actor_ids.add(b["local_track_id"])
        if len(actor_ids) != 1 or not actor_evidence:
            continue
        actor = next(iter(actor_ids))
        receiver, finisher = body(raw.get("receiver_idx"), raw.get("receiver_body_id")), body(raw.get("shot_idx"), raw.get("finisher_body_id"))
        outcome_ms = at(raw.get("outcome_idx"))
        outcome_evidence = sorted({at(i) for i in _rows(raw.get("outcome_evidence_indices")) if at(i) is not None})
        terminal = outcome_ms if outcome_ms is not None else end
        continuous = (raw.get("continuous_visible_sequence") is True
            and not any(start <= f.get("media_ms", -1) <= terminal and not actual(f, window.get("scene_id")) for f in frames)
            and not any(b-a > 250 for a, b in zip(times, times[1:]) if start <= a <= terminal))
        visible = (continuous and raw.get("outcome_visible") is True and bool(outcome_evidence)
                   and min(outcome_evidence) >= (contact if contact is not None else start)
                   and (outcome_ms is None or outcome_ms in outcome_evidence))
        if raw.get("outcome") == "TEAMMATE_GOAL" and (receiver is None or finisher is None):
            visible = False
        chain = {"target_contact_ms": contact, "receiver_local_track_id": receiver["local_track_id"] if receiver else None,
            "receiver_ms": at(raw.get("receiver_idx")), "teammate_shot_ms": at(raw.get("shot_idx")),
            "goal_outcome_ms": outcome_ms, "continuous_visible_sequence": continuous}
        action = sequence._normalise_action({"action_id": f"{sid}_{index}", "kind": raw.get("kind"),
            "start_ms": start, "end_ms": end, "contact_ms": contact,
            "actor_local_track_id": actor, "actor_candidate_local_track_ids": [actor],
            "actor_evidence": actor_evidence, "evidence_ms": [e["media_ms"] for e in actor_evidence],
            "target_status": "UNRESOLVED", "outcome": raw.get("outcome"), "outcome_visible": visible,
            "contact_visibility": raw.get("contact_visibility"), "foot": raw.get("foot"),
            "details": _rows(raw.get("details")), "causal_chain": chain}, window)
        if action is None:
            continue
        action["causal_chain"]["finisher_local_track_id"] = finisher["local_track_id"] if finisher else None
        action["video_observation"] = {"authority": "TEMPORAL_VIDEO_OBSERVATION", "input_sha256": obs["input_sha256"],
            "response_sha256": obs["response_sha256"], "clip_sha256": clip["clip_sha256"],
            "source_video_sha256": obs.get("source_video_sha256"), "model": obs.get("model"),
            "outcome_evidence_ms": outcome_evidence, "source_frame_indices": list(_rows(raw.get("actor_evidence_indices"))),
            "source_bounds_ms": [times[0], times[-1]], "provider_requested_fps": transport.get("requested_fps"),
            "source_sampling_fps": transport.get("source_sampling_fps"), "playback_fps": transport.get("playback_fps")}
        actions.append(action)
    return {"sequences": [{"sequence_id": sid, "scene_id": window.get("scene_id"),
        "start_ms": times[0], "end_ms": times[-1], "actions": actions}]}


def motion_window_complete(observation, frames, window):
    """Scheduling coverage only: a short feedback clip cannot replace a whole window."""
    packet = video_observations(observation, frames, window)
    native = [f["media_ms"] for f in frames if actual(f, window.get("scene_id"))]
    times = (observation.get("motion_clip") or {}).get("frame_source_ms") or []
    return bool(packet.get("sequences") and native and times
                and times[0] <= min(native)+150 and times[-1] >= max(native)-150)


def motion_reader_context(packet):
    """Only the shared measurements actually supplied to the motion reader."""
    source = packet or {}
    return {"scene_id": source.get("scene_id"), "source_video_sha256": source.get("source_video_sha256"),
        "known_target_bodies": [{k: r.get(k) for k in ("media_ms", "body_id", "track_id", "box")}
            for r in source.get("body_observations") or [] if r.get("target_observed") is True],
        "verified_contacts": deepcopy(source.get("verified_contacts") or []),
        "roles": deepcopy(source.get("roles") or {}),
        "requested_search": deepcopy(source.get("requested_search")),
        "related_sequence": deepcopy(source.get("related_sequence"))}


def motion_review_requests(parsed, times, manifest):
    """Ask for one observed missing link, without supplying an expected result."""
    by_ms = {r["media_ms"]: {b["body_id"]: b.get("local_track_id") for b in r.get("source_bodies") or []}
             for r in manifest}
    def at(idx):
        return times[idx-1] if type(idx) is int and 1 <= idx <= len(times) else None
    requests = []
    for action in _rows((parsed or {}).get("actions")):
        if not isinstance(action, dict):
            continue
        contact = at(action.get("contact_idx"))
        if contact is None:
            # An observed outcome without a contact is a search lead, not an
            # event to silently drop or an excuse to invent a release time.
            outcome = at(action.get("outcome_idx"))
            pivot = next((value for value in (outcome, at(action.get("shot_idx")),
                                              at(action.get("start_idx"))) if value is not None), None)
            if pivot is not None and action.get("kind") in {"SHOT", "PASS", "CROSS"}:
                requests.append({"question": "CONTACT", "media_ms": pivot,
                    "anchor_media_ms": pivot, "focus_track_id": None,
                    "search_protocol": "SOURCE_INDEXED_MOTION_CLIP_V1",
                    "source": "MODEL_SEQUENCE_SEARCH", "direction": "BEFORE",
                    "canonical_authority": False})
            continue
        receiver, shot, outcome = (at(action.get(k)) for k in ("receiver_idx", "shot_idx", "outcome_idx"))
        if action.get("receiver_body_id") not in by_ms.get(receiver, {}):
            receiver = None
        if action.get("finisher_body_id") not in by_ms.get(shot, {}):
            shot = None
        unknown = action.get("outcome") in {None, "UNKNOWN", "TEAMMATE_SHOT", "TEAMMATE_GOAL"}
        question, pivot, body = None, contact, action.get("actor_body_id")
        if not action.get("actor_evidence_indices"):
            question = "IDENTITY"
        elif action.get("kind") in {"PASS", "CROSS"} and receiver is None:
            question = "RECEIVER"
        elif action.get("kind") in {"PASS", "CROSS"} and shot is None and unknown:
            question, pivot, body = "SHOT", receiver, action.get("receiver_body_id")
        elif action.get("kind") in {"PASS", "CROSS", "SHOT"} and (outcome is None or action.get("outcome_visible") is not True
                or not action.get("outcome_evidence_indices")) and unknown:
            question, pivot, body = "OUTCOME", shot or contact, action.get("finisher_body_id") or body
        if question:
            requests.append({"question": question, "media_ms": pivot, "anchor_media_ms": contact,
                "focus_track_id": by_ms.get(pivot, {}).get(body),
                "search_protocol": "SOURCE_INDEXED_MOTION_CLIP_V1",
                "source": "MODEL_SEQUENCE_SEARCH", "direction": "AROUND" if question == "IDENTITY" else "AFTER",
                "canonical_authority": False})
    return requests[:4]


def _rows(value):
    return value if isinstance(value, (list, tuple)) else []


def _choice(value, choices):
    return value if isinstance(value, str) and value in choices else None


def native_focuses(job, frames, limit=1):
    """Repeated near-foot native proposals choose pixels, never a contact."""
    import dense_track_refinement
    import ball_contact_engine
    import frame_geometry
    if limit <= 0:
        return []
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
    selected = []
    for r in sorted(candidates):
        if all(abs(r[3]-old["media_ms"]) >= 300 for old in selected):
            selected.append({"media_ms": r[3], "local_track_id": r[4], "reason": "NATIVE_LOWER_BODY_SEARCH",
                             "canonical_authority": False})
        if len(selected) >= limit:
            break
    return selected


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
    centers = job.get("search_centers_ms") or []
    if len(centers) > 1:
        focus = [{"media_ms": ms, "reason": "SHARED_WINDOW_SEARCH_TIME", "canonical_authority": False}
                 for ms in centers if num(ms)]
    near = lambda ms: min(available, key=lambda t: (abs(t-ms), t))
    selected = {available[0], available[-1]}
    # Every joined observation retains its own focus before adding neighbours.
    for row in focus:
        if len(selected) < budget:
            selected.add(near(row["media_ms"]))
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
        "requested_search": {k: deepcopy(window.get(k)) for k in
            ("missing_link_question", "center_ms", "anchor_media_ms", "focus_track_id") if window.get(k) is not None},
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


def review_search_hints(inspections, frames):
    """Connect an observed shot/release hypothesis to its native body for search.

    These hints allocate inspection; they have no identity or outcome authority.
    """
    tracks = {label: track for track, label in labels(frames).items()}
    by_ms = {f["media_ms"]: f for f in frames if actual(f)}
    hints = []
    for review in inspections or []:
        for hypothesis in (review.get("sequence_reasoning") or {}).get("hypotheses") or []:
            for step in hypothesis.get("steps") or []:
                if step.get("observation") not in {"SHOT_MOTION", "RELEASE"}:
                    continue
                f = by_ms.get(step.get("media_ms")); track = tracks.get(step.get("body_id"))
                if f is not None and track and any(p.get("local_track_id") == track
                        and p.get("association_state") == "VERIFIED_LOCAL" for p in f.get("players") or []):
                    hints.append({"media_ms": f["media_ms"], "player_track_id": track,
                                  "scene_id": f.get("scene_id"), "canonical_authority": False})
    return hints


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
        rank = (-3 if request.get("search_protocol") == "SOURCE_INDEXED_MOTION_CLIP_V1" else
                -2 if measured and request.get("utility", 0) >= 5 else -1)
        result.append((rank, min((f["media_ms"] for f in path), key=lambda t: abs(t-pivot)),
                       ("CHAIN_SEARCH_" if measured else "MODEL_SEQUENCE_")+request["question"]))
    return result
