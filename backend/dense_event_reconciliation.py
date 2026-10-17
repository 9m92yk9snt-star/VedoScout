"""Resolve source-bound motion observations and revisit delayed player identity.

All observations use the shared canonical actor/causal resolver. Visual motion
evidence remains distinct from FIX10B's physical crossing certificates.
"""
from copy import deepcopy

import canonical_event_resolver as resolver
import unified_identity_authority as uia
import cross_window_evidence
import fix10b_reconciliation as physical_resolution
import sequence_observation_context


def motion_scene_frames(trace):
    """Build one source-clocked possession graph from visual/native observations."""
    import ball_contact_engine
    rows = deepcopy(trace.get("decoded_frames") or [])
    ball_by_ms = {b["media_ms"]: b for b in trace.get("ball_trajectory") or []
                  if b.get("state") == "MEASURED" and b.get("proof_eligible") is True
                  and b.get("time_authority") in {None, "ACTUAL_MEDIA_PTS"}}
    by_ms = {f["media_ms"]: f for f in rows if sequence_observation_context.actual(f)}
    for ms, f in by_ms.items():
        ball = ball_by_ms.get(ms)
        holder = ball_contact_engine._likely_holder(f, ball.get("box")) if ball else None
        if holder:
            f["possession"] = {"status": "LIKELY", "holder_local_track_id": holder,
                "candidate_local_track_ids": [holder], "source": "MEASURED_ACTIVE_BALL_TRAJECTORY"}
    # A global trajectory may follow a stationary spare ball. Reuse the new
    # motion reader's active-ball search ONLY where a separate native detector
    # measured that ball in the exact source frame. This supplies the visual
    # chain's possession context; it never rewrites a physical trajectory.
    active_holders, visible_holders = {}, {}
    source = (trace.get("source_video") or {}).get("sha256")
    import action_evidence_review
    for obs in trace.get("action_inspections") or []:
        if (not source or obs.get("source_video_sha256") != source
                or not sequence_observation_context.video_observations(obs, rows, trace.get("window") or {}).get("sequences")):
            continue
        # Complete temporal observations can establish a visible transfer even
        # when the independent ball detector misses a tiny/partly hidden ball.
        # Keep that visual evidence distinct from physical class-32 detections.
        import frame_geometry
        import math
        for control in obs.get("video_control_observations") or []:
            f = by_ms.get(control.get("media_ms"))
            box = control.get("ball_box")
            if (f is None or control.get("source") != "SOURCE_VIDEO_VISIBLE_BALL_CONTROL"
                    or control.get("control_visible") is not True or control.get("confidence") != "high"
                    or not ball_contact_engine._valid_box(box)):
                continue
            bodies = [p for p in f.get("players") or [] if p.get("local_track_id") == control.get("local_track_id")
                      and p.get("association_state") == "VERIFIED_LOCAL" and uia._valid_box(p.get("box"))]
            scale = frame_geometry.horizontal_scale(f)
            if len(bodies) != 1 or scale is None:
                continue
            body = bodies[0]["box"]
            fx, fy = ball_contact_engine._foot(body)
            bx, by = ball_contact_engine._center(box)
            if math.hypot((bx-fx)*scale, by-fy)/body["h"] <= ball_contact_engine.POSSESSION_MAX_H:
                visible_holders.setdefault(f["media_ms"], set()).add(control["local_track_id"])
        for row in obs.get("frames") or []:
            f = by_ms.get(row.get("media_ms"))
            if f is None:
                continue
            for b in row.get("ball_candidates") or []:
                if (b.get("video_active_ball") is not True or b.get("source") != "NATIVE_REVIEW_ROI_DETECTOR"
                        or not action_evidence_review._native_ball(b) or not action_evidence_review.matches_ball_search(b)):
                    continue
                holder = ball_contact_engine._likely_holder(f, b.get("box"))
                if holder:
                    active_holders.setdefault(f["media_ms"], set()).add(holder)
    active_holders.update(visible_holders)
    for ms, holders in active_holders.items():
        holder = next(iter(holders)) if len(holders) == 1 else None
        by_ms[ms]["possession"] = {"status": "LIKELY" if holder else "AMBIGUOUS",
            "holder_local_track_id": holder, "candidate_local_track_ids": sorted(holders),
            "source": "SOURCE_VIDEO_VISIBLE_BALL_CONTROL" if ms in visible_holders else "SOURCE_CLIP_ACTIVE_BALL_NATIVE_PIXELS"}
    for t in (trace.get("touch_graph") or {}).get("touches") or []:
        if t.get("status") != "VERIFIED" or t.get("proof_eligible") is not True:
            continue
        ms = t.get("representative_ms", t.get("media_ms"))
        f = by_ms.get(ms)
        if (f and ms not in active_holders
                and any(p.get("local_track_id") == t.get("player_track_id") for p in f.get("players") or [])):
            f["possession"] = {"status": "LIKELY", "holder_local_track_id": t["player_track_id"],
                "candidate_local_track_ids": [t["player_track_id"]], "source": "VERIFIED_PHYSICAL_CONTACT"}
    return rows


def resolve_motion_observations(trace):
    """Send fresh clip observations through the SAME actor/causal resolver."""
    rows = motion_scene_frames(trace)
    sequences = []
    source = (trace.get("source_video") or {}).get("sha256")
    for observation in trace.get("action_inspections") or []:
        if not source or observation.get("source_video_sha256") != source:
            continue
        packet = sequence_observation_context.video_observations(observation, rows, trace.get("window") or {})
        for seq in packet.get("sequences") or []:
            for action in seq.get("actions") or []:
                chain = action.get("causal_chain") or {}
                receiver, scorer = chain.get("receiver_local_track_id"), chain.get("finisher_local_track_id")
                if action.get("outcome") == "TEAMMATE_GOAL" and receiver != scorer:
                    def touch(track, pivot):
                        candidates = [t for t in (trace.get("touch_graph") or {}).get("touches") or []
                            if t.get("status") == "VERIFIED" and t.get("proof_eligible") is True
                            and t.get("player_track_id") == track and isinstance(pivot, int)
                            and abs(t.get("representative_ms", t.get("media_ms", -1000000))-pivot) <= 150]
                        return min(candidates, key=lambda t: abs(t.get("representative_ms", t.get("media_ms"))-pivot), default={})
                    linked, evidence = physical_resolution._same_actor_after_track_split(trace,
                        touch(receiver, chain.get("receiver_ms")), touch(scorer, chain.get("teammate_shot_ms")))
                    action["video_observation"]["receiver_finisher_link"] = evidence
                    if not linked:
                        action["outcome_visible"] = False
            sequences.append(seq)
    result = (resolver.resolve_canonical_events({"sequences": sequences}, {"frames": rows}, {})
              if sequences else {"events": [], "unresolved": [], "rejected": []})
    actions = {a["action_id"]: a for s in sequences for a in s.get("actions") or []}
    for lane in ("unresolved", "rejected"):
        for diagnostic in result.get(lane) or []:
            observation = (actions.get(diagnostic.get("action_id")) or {}).get("video_observation")
            if observation:
                diagnostic["video_observation"] = deepcopy(observation)
    return result


def merge_motion_observations(canonical, physical):
    bundle = deepcopy(canonical or {})
    events = bundle.setdefault("events", [])
    conflicts, observed, diagnostics_added = [], 0, 0
    blocked = [c for c in bundle.get("unresolved") or [] if c.get("reason") == "CONFLICTING_VIDEO_OUTCOMES"]
    for trace in (physical or {}).get("traces") or []:
        resolved = resolve_motion_observations(trace)
        for lane in ("unresolved", "rejected"):
            for diagnostic in resolved.get(lane) or []:
                if diagnostic not in bundle.setdefault(lane, []):
                    bundle[lane].append(deepcopy(diagnostic))
                    diagnostics_added += 1
        for event in resolved.get("events") or []:
            old = next((e for e in events if resolver._same_real_action(e, event)), None)
            if any(resolver._same_real_action(e, event) for c in [*blocked, *conflicts] for e in c["observed_events"]):
                continue
            old_video = (old.get("proof") or {}).get("video_observation") if old else None
            new_video = (event.get("proof") or {}).get("video_observation") or {}
            if (old and old.get("event_id") == event.get("event_id") and old_video
                    and all(old_video.get(k) == new_video.get(k) for k in ("input_sha256", "response_sha256"))):
                continue
            if old and ((old.get("proof") or {}).get("fix10b_physical") or {}).get("proof_eligible") is True:
                continue
            if old and old.get("causal_verified") and event.get("causal_verified") and old.get("canonical_outcome") != event.get("canonical_outcome"):
                if (old.get("proof") or {}).get("video_observation"):
                    conflicts.append({"reason": "CONFLICTING_VIDEO_OUTCOMES", "scene_id": event.get("scene_id"),
                        "contact_ms": event.get("contact_ms"), "kind": event.get("canonical_action_type"),
                        "observed_events": [deepcopy(old), deepcopy(event)]})
                    events.remove(old)
                    continue
            if old:
                if old.get("causal_verified") and not event.get("causal_verified"):
                    continue
                event.setdefault("proof", {})["superseded_semantic_event_ids"] = [old.get("event_id")]
                events.remove(old)
            events.append(event)
            observed += 1
    if observed or conflicts or diagnostics_added:
        bundle["events"] = sorted(events, key=lambda e: e.get("canonical_ms", 0))
        bundle.setdefault("unresolved", []).extend(conflicts)
        bundle["motion_observation_feedback"] = {"observations_applied": observed, "conflicts": len(conflicts),
            "diagnostics_added": diagnostics_added,
            "authority": "FIX09B_CANONICAL_EVENTS", "physical_certificate_required": False}
        counts = {}
        for e in bundle["events"]:
            kind = e.get("canonical_event_type")
            counts[kind] = counts.get(kind, 0)+1
        bundle["counts"] = counts
        bundle.setdefault("metrics", {}).update(events_accepted=len(bundle["events"]),
            goals=counts.get("GOAL", 0), assists=counts.get("ASSIST", 0), shots=counts.get("GOAL", 0)+counts.get("SHOT", 0),
            observations_unresolved=len(bundle.get("unresolved") or []))
        bundle["metrics"]["observations_rejected"] = len(bundle.get("rejected") or [])
    return bundle


def _matches(diagnostic, event):
    return (diagnostic.get("action_id") in (event.get("source_action_ids") or [])
            and (not diagnostic.get("scene_id") or diagnostic["scene_id"] == event.get("scene_id"))
            and (not diagnostic.get("sequence_id") or diagnostic["sequence_id"] in
                 (event.get("source_sequence_ids") or [event.get("sequence_id")])))


def _refined_candidates(selected, context_rows):
    for context, rows in context_rows:
        if rows:
            for event in resolver.resolve_canonical_events(selected, {"frames": rows}, {}).get("events") or []:
                yield event, context


def recover(canonical, sequence, physical, authority):
    bundle = merge_motion_observations(canonical, physical)
    pending = [(lane, row) for lane in ("unresolved", "rejected")
               for row in bundle.get(lane) or []
               if row.get("action_id") and (row.get("reason") or
                   row.get("actor_resolution", {}).get("reason")) in resolver.REVISITABLE_IDENTITY_REASONS]
    if not pending:
        return bundle
    candidates = {}
    contexts = cross_window_evidence.build(physical or {})["contexts"]
    # Legacy single-window exports may omit a trace ID. They can contribute
    # their own observations, but cannot claim any cross-window association.
    contexts.extend(t for t in (physical or {}).get("traces") or [] if not t.get("trace_id"))
    context_rows = []
    for trace in contexts:
        local_rows = []
        for f in trace.get("decoded_frames") or []:
            target = f.get("global_target") or {}
            if (target.get("status") == "VERIFIED" and target.get("proof_eligible") is True
                    and f.get("time_authority") == "ACTUAL_MEDIA_PTS" and not f.get("used_fallback")
                    and not f.get("cut_barrier")):
                body = next((p for p in f.get("players") or []
                             if p.get("local_track_id") == target.get("local_track_id")), {})
                if uia._valid_box(body.get("box")):
                    local_rows.append(f)
                    candidates.setdefault((f.get("scene_id"), f.get("media_ms")), []).append(f)
        context_rows.append((trace, local_rows))
    rows, conflicts = [], set()
    for key, variants in candidates.items():
        body_boxes = []
        usable = []
        for f in variants:
            target = f["global_target"]
            p = next((p for p in f.get("players") or []
                      if p.get("local_track_id") == target.get("local_track_id")), None)
            if p and uia._valid_box(p.get("box")):
                body_boxes.append(p["box"])
                usable.append(f)
        if not body_boxes:
            continue
        if any(not uia.boxes_agree(body_boxes[0], b) for b in body_boxes[1:]):
            conflicts.add(key)
            continue
        rows.append(deepcopy(usable[0]))
    if not rows:
        return bundle
    # Revisit the original observations, not a synthesized expected action.
    # Action IDs are local to a sequence; never reopen/remove another scene's
    # a1 because one a1 acquired new identity evidence.
    selected = deepcopy(sequence or {})
    for seq in selected.get("sequences") or []:
        seq["actions"] = [a for a in seq.get("actions") or [] if any(
            d.get("action_id") == a.get("action_id")
            and (not d.get("scene_id") or d["scene_id"] == seq.get("scene_id"))
            and (not d.get("sequence_id") or d["sequence_id"] == seq.get("sequence_id"))
            for _, d in pending)]
    # A stale coarse identity rejection is precisely what is being revisited.
    # It cannot independently bless a new action: use fresh dense proof only.
    episodes = physical_resolution.target_release_episodes(physical, contexts=contexts)
    additions = []
    for e, context in _refined_candidates(selected, context_rows):
        kind = e.get("canonical_action_type")
        if not any(_matches(d, e) for _, d in pending):
            continue
        if any(scene == e.get("scene_id") and e.get("start_ms", 0) <= ms <= e.get("end_ms", 0)
               for scene, ms in conflicts):
            continue
        if kind in {"SHOT", "PASS", "CROSS", "KEY_PASS"}:
            # Recovered identity alone cannot establish an unseen ball release.
            contact_ms = e.get("contact_ms", e.get("canonical_ms"))
            releases = [s for s in context.get("strike_evidence") or []
                        if s.get("scene_id") == e.get("scene_id")
                        and s.get("global_target_id") == uia.GLOBAL_TARGET_ID
                        and s.get("status") == "VERIFIED_PHYSICAL_RELEASE"
                        and s.get("proof_eligible") is True
                        and s.get("player_track_id") == e.get("actor_local_track_id")
                        and isinstance(contact_ms, (int, float))
                        and abs(s.get("media_ms", -1000000) - contact_ms) <= 120]
            if kind == "SHOT":
                # The original SHOT reader may be a few frames early. Use
                # exactly the existing unique-release interval contract, not
                # the narrower pass-contact feedback tolerance.
                matching = [episode for episode in episodes if episode[0][0] == e.get("scene_id")
                    and e.get("start_ms", 0) <= episode[0][1] <= e.get("end_ms", 0)
                    and isinstance(contact_ms, (int, float))
                    and abs(episode[0][1] - contact_ms) <= physical_resolution.UNRESOLVED_SHOT_RELEASE_MATCH_MS]
                releases = matching if len(matching) == 1 and matching[0][0][3] is context \
                    and matching[0][0][2].get("player_track_id") == e.get("actor_local_track_id") else []
            if not releases:
                continue
            if kind == "SHOT":
                release = releases[0][0][2]
                release_ms = releases[0][0][1]
                e.update(contact_ms=release_ms, canonical_ms=release_ms,
                         end_ms=max(e.get("end_ms", release_ms), release_ms))
                proof = e.setdefault("proof", {})
                proof["contact_geometry"] = None  # do not retime an old model rectangle
                proof["contact_visibility"] = "PHYSICALLY_VERIFIED"
                proof["evidence_ms"] = sorted(set(proof.get("evidence_ms") or []) | {release_ms})
                e["identity_feedback_release"] = {"source_trace_id": context.get("trace_id"),
                    "source_strike_id": release.get("strike_id"), "media_ms": release_ms}
            # Identity/release recovery establishes the action, not a model's
            # scoring or save story. FIX10B upgrades it from physical outcomes.
            e.update(canonical_event_type=kind, canonical_outcome="UNKNOWN", causal_verified=False)
            e.setdefault("proof", {})["causal_verified"] = False
            e["causal_chain"] = {}
        e["identity_feedback_authority"] = "DENSE_PHYSICAL_IDENTITY"
        key = (e.get("scene_id"), e.get("canonical_action_type"), e.get("canonical_ms"),
               tuple(sorted(e.get("source_sequence_ids") or [])), tuple(sorted(e.get("source_action_ids") or [])))
        if not any((old.get("scene_id"), old.get("canonical_action_type"), old.get("canonical_ms"),
                    tuple(sorted(old.get("source_sequence_ids") or [])),
                    tuple(sorted(old.get("source_action_ids") or []))) == key for old in additions):
            additions.append(e)
    resolved = [(lane, d) for lane, d in pending if any(_matches(d, e) for e in additions)]
    bundle.setdefault("events", []).extend(additions)
    for lane in ("unresolved", "rejected"):
        bundle[lane] = [u for u in bundle.get(lane) or []
                        if not any(old_lane == lane and d == u for old_lane, d in resolved)]
    previous = bundle.get("dense_identity_feedback") or {}
    bundle["dense_identity_feedback"] = {
        "recovered_actions": int(previous.get("recovered_actions") or 0) + len(additions),
        "resolved_action_ids": sorted(set(previous.get("resolved_action_ids") or []) |
                                      {d["action_id"] for _, d in resolved}),
        "previous_decisions": list(previous.get("previous_decisions") or []) +
            [{"lane": lane, **{k: d.get(k) for k in
                ("scene_id", "sequence_id", "action_id", "reason")}} for lane, d in resolved]}
    bundle.setdefault("metrics", {}).update(events_accepted=len(bundle["events"]),
        observations_unresolved=len(bundle.get("unresolved") or []),
        observations_rejected=len(bundle.get("rejected") or []))
    return bundle
