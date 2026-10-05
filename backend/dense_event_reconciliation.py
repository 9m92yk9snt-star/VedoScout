"""Feed later dense identity proof back to unresolved sequence observations.

Only existing observations are reconsidered. This cannot discover a new action
or turn model-only scoring into a physical goal/assist. Those stay in FIX10B's
separate release/outcome proof path.
"""
from copy import deepcopy

import canonical_event_resolver as resolver
import unified_identity_authority as uia


def recover(canonical, sequence, physical, authority):
    bundle = deepcopy(canonical or {})
    pending = {u.get("action_id") for u in bundle.get("unresolved") or []
               if u.get("actor_resolution", {}).get("reason") == "INSUFFICIENT_PHYSICAL_IDENTITY_EVIDENCE"}
    if not pending:
        return bundle
    candidates = {}
    for trace in (physical or {}).get("traces") or []:
        for f in trace.get("decoded_frames") or []:
            target = f.get("global_target") or {}
            if target.get("status") == "VERIFIED" and target.get("proof_eligible") is True:
                candidates.setdefault((f.get("scene_id"), f.get("media_ms")), []).append(f)
    rows = []
    for variants in candidates.values():
        body_boxes = []
        usable = []
        for f in variants:
            target = f["global_target"]
            p = next((p for p in f.get("players") or []
                      if p.get("local_track_id") == target.get("local_track_id")), None)
            if p and uia._valid_box(p.get("box")):
                body_boxes.append(p["box"])
                usable.append(f)
        if not body_boxes or any(not uia.boxes_agree(body_boxes[0], b) for b in body_boxes[1:]):
            continue
        rows.append(deepcopy(usable[0]))
    refined = resolver.resolve_canonical_events(sequence, {"frames": rows}, authority)
    additions = []
    for e in refined.get("events") or []:
        ids = set(e.get("source_action_ids") or [])
        kind = e.get("canonical_action_type")
        if not ids.intersection(pending) or kind == "SHOT" or e.get("canonical_event_type") in {"GOAL", "ASSIST"}:
            continue
        if kind in {"PASS", "CROSS", "KEY_PASS"}:
            # Recovered identity alone cannot establish an unseen ball release.
            contact_ms = e.get("contact_ms", e.get("canonical_ms"))
            releases = [s for t in (physical or {}).get("traces") or []
                        for s in t.get("strike_evidence") or []
                        if s.get("scene_id") == e.get("scene_id")
                        and s.get("global_target_id") == uia.GLOBAL_TARGET_ID
                        and s.get("status") == "VERIFIED_PHYSICAL_RELEASE"
                        and s.get("proof_eligible") is True
                        and isinstance(contact_ms, (int, float))
                        and abs(s.get("media_ms", -1000000) - contact_ms) <= 120]
            if not releases:
                continue
        e["identity_feedback_authority"] = "DENSE_PHYSICAL_IDENTITY"
        additions.append(e)
    resolved = {a for e in additions for a in e.get("source_action_ids") or []}
    bundle.setdefault("events", []).extend(additions)
    bundle["unresolved"] = [u for u in bundle.get("unresolved") or [] if u.get("action_id") not in resolved]
    bundle["dense_identity_feedback"] = {"recovered_actions": len(additions),
                                         "resolved_action_ids": sorted(resolved)}
    return bundle
