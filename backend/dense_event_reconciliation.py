"""Feed later dense identity proof back to unresolved sequence observations.

Only existing observations are reconsidered. This cannot discover a new action
or turn model-only scoring into a physical goal/assist. Those stay in FIX10B's
separate release/outcome proof path.
"""
from copy import deepcopy

import canonical_event_resolver as resolver
import unified_identity_authority as uia
import cross_window_evidence
import fix10b_reconciliation as physical_resolution


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
    bundle = deepcopy(canonical or {})
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
