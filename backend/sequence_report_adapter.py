"""Sequence V1 -> existing report contract. No perception, tracking or model calls.

Contact brackets remain brackets. Visual actor attribution is never presented
as a measured player box. Completed calls do not establish exhaustive coverage.
"""
from copy import deepcopy
from collections import Counter
import hashlib

from canonical_output_authority import project_event
from evidence_authority import attach_event_evidence_authority, apply_fail_closed_proof_authority, _iter_structured_rows
from verified_stats import apply_verified_stats_authority

ENGINE = "SEQUENCE_V1"


def canonical_bundle(result, manifest, receipts):
    source = manifest["source_video_sha256"]
    if result.get("source_video_sha256") != source:
        raise ValueError("SEQUENCE_SOURCE_MISMATCH")
    if result.get("status") != "MODEL_OBSERVATIONS_RETURNED" or not result.get("fresh_end_to_end_run"):
        raise ValueError("SEQUENCE_RUN_INCOMPLETE")
    if result.get("historical_action_results_used"):
        raise ValueError("SEQUENCE_HISTORY_NOT_ALLOWED")
    frames = {f["frame_id"]: f["media_ms"] for f in manifest["frames"]}
    refs = {r["reference_id"] for r in manifest["references"]}
    checked = set()
    for r in receipts:
        if r.get("status") != "COMPLETED" or r.get("origin") != "LIVE_MODEL_REQUEST":
            raise ValueError("SEQUENCE_RECEIPT_INCOMPLETE")
        if hashlib.sha256(r["raw_response"].encode()).hexdigest() != r.get("response_sha256"):
            raise ValueError("SEQUENCE_RESPONSE_CHANGED")
        checked.add((r["packet_id"], r["payload_sha256"], r["response_sha256"]))
    if len(checked) != result.get("model_jobs_completed") or not checked:
        raise ValueError("SEQUENCE_RECEIPTS_MISSING")
    events = []
    for raw in result.get("target_events") or []:
        if not (raw.get("selected_player") is True and raw.get("proof_eligible") is True
                and raw.get("model_requested_clarification") is False):
            continue
        if raw.get("source_video_sha256") != source or not raw.get("actor") or not raw.get("actor_scope"):
            raise ValueError("SEQUENCE_ACTOR_SOURCE_MISSING")
        if not raw.get("reference_ids") or not set(raw["reference_ids"]) <= refs:
            raise ValueError("SEQUENCE_REFERENCE_MISSING")
        if not raw.get("receipts") or any((r.get("packet_id"), r.get("payload_sha256"), r.get("response_sha256"))
                                         not in checked for r in raw["receipts"]):
            raise ValueError("SEQUENCE_EVENT_RECEIPT_MISSING")
        cited = list(raw.get("actor_evidence_frames") or [])
        cited += [r.get("frame") for r in raw.get("outcome_evidence") or []]
        if not cited or any(f not in frames for f in cited):
            raise ValueError("SEQUENCE_FRAME_MISSING")
        interval = raw.get("contact_interval_ms")
        contact = raw.get("contact_ms")
        kind = raw["event_type"]
        if kind in {"GOAL", "ASSIST", "SHOT"}:
            if contact is None and not (isinstance(interval, list) and len(interval) == 2
                                        and all(isinstance(t, int) for t in interval) and interval[0] <= interval[1]):
                raise ValueError("SEQUENCE_CONTACT_UNRESOLVED")
            if not raw.get("outcome_evidence") or raw.get("outcome") == "UNKNOWN":
                raise ValueError("SEQUENCE_OUTCOME_UNRESOLVED")
        if kind == "ASSIST" and (not raw.get("receiver") or not raw.get("finisher")
                                  or raw["finisher"] == raw["actor"]):
            raise ValueError("SEQUENCE_ASSIST_ROLE_UNRESOLVED")
        # Display an actual cited source moment; never manufacture a contact midpoint.
        pivot = contact if contact is not None else interval[0] if interval else raw["start_ms"]
        frame_id = min(raw["actor_evidence_frames"], key=lambda f: abs(frames[f] - pivot))
        ms = frames[frame_id]
        outcome_ms = raw.get("outcome_ms")
        proof_times = [frames[f] for f in cited] + [raw["start_ms"], raw["end_ms"]]
        if isinstance(outcome_ms, int):
            proof_times.append(outcome_ms)
        events.append({
            "event_id": raw["event_id"], "canonical_ms": ms,
            "start_ms": raw["start_ms"], "end_ms": raw["end_ms"],
            "contact_ms": contact, "contact_interval_ms": deepcopy(interval),
            "canonical_event_type": kind,
            "canonical_action_type": "SHOT" if kind == "GOAL" else "PASS" if kind == "ASSIST" else raw["kind"],
            "canonical_outcome": raw["outcome"],
            "causal_verified": kind in {"GOAL", "ASSIST"} or raw["outcome"] == "SAVED",
            "global_target_id": "GLOBAL_TARGET", "actor_local_track_id": None,
            "actor_visual_id": raw["actor_scope"] + ":" + raw["actor"],
            "identity_resolution": "ORIGINAL_SELECTION_SEQUENCE_CONTINUITY",
            "details": [raw["details"]] if isinstance(raw.get("details"), str) else [],
            "foot": "UNKNOWN", "foot_verification": "ANATOMICAL_SIDE_NOT_VERIFIED",
            "source_video_sha256": source,
            "source_action_ids": deepcopy(raw.get("source_action_keys") or []),
            "source_sequence_ids": deepcopy(raw.get("source_packet_ids") or []),
            "causal_chain": {"target_contact_ms": contact, "goal_outcome_ms": outcome_ms,
                             "receiver_visual_id": raw.get("receiver"), "finisher_visual_id": raw.get("finisher")},
            "proof": {"proof_eligible": True, "source_video_sha256": source,
                      "frame_id": frame_id, "frame_ms": ms,
                      "cited_frames": {f: frames[f] for f in cited},
                      "reference_ids": deepcopy(raw["reference_ids"]),
                      "receipts": deepcopy(raw["receipts"]),
                      "proof_start_ms": min(proof_times), "proof_end_ms": max(proof_times),
                      "outcome_ms": outcome_ms},
        })
    if not events:
        raise ValueError("SEQUENCE_NO_VERIFIED_EVENTS")
    if len({e["event_id"] for e in events}) != len(events):
        raise ValueError("SEQUENCE_DUPLICATE_EVENT")
    return {"version": 1, "authority": ENGINE, "source_video_sha256": source,
            "events": sorted(events, key=lambda e: e["canonical_ms"]),
            "coverage_complete": False, "questions": deepcopy(result.get("questions") or [])}


def build_report(prose, bundle):
    if not isinstance(prose, dict) or not prose:
        raise ValueError("SEQUENCE_REPORT_WRITER_INVALID")
    full = deepcopy(prose)
    for row in _iter_structured_rows(full):
        if isinstance(row, dict):
            for key in ("evidence_id", "proof_verified", "identity_verified", "canonical_event_ids"):
                row.pop(key, None)
    weak_foot = (full.get("technical") or {}).get("weak_foot")
    if isinstance(weak_foot, dict):
        # The sequence contract has no verified anatomical side. A writer's
        # event citation cannot manufacture weak-foot evidence from UNKNOWN.
        weak_foot["evidence"] = []
    # Writer has no authority over events, physical metrics, evidence or totals.
    for key in ("match_stats", "verified_stats", "movement_map", "pace_metrics", "heatmap", "speed_metrics",
                "verified_stat_line", "cross_verification", "analysis_authority", "_scoring_scan"):
        full.pop(key, None)
    full["analysis_authority"] = {"output": ENGINE, "source_video_sha256": bundle["source_video_sha256"]}
    full["action_timeline"], full["video_comments"] = [], []
    for e in bundle["events"]:
        row = project_event(e)
        row.update(event_source="sequence_v1", actor_spatial_verified=False, actor_visual_verified=True,
                   contact_ms=e["contact_ms"], contact_interval_ms=e["contact_interval_ms"])
        if e["canonical_action_type"] == "DRIBBLE":
            # Pilot DRIBBLE includes uncontested carries. Neither a completed
            # carry nor missing take-on evidence establishes a won/lost 1v1.
            row.update(canonical_action_type="OTHER", canonical_event_type="OTHER",
                       stat_mapping_status="CARRY_VS_TAKE_ON_UNRESOLVED")
        if e["canonical_action_type"] == "RECOVERY" and e["canonical_outcome"] == "COMPLETED":
            row["canonical_result"] = "POSSESSION_WON"
        full["action_timeline"].append(row)
        full["video_comments"].append({
            "event_id": e["event_id"], "timestamp": row["timestamp"],
            "comment": f"Verified {row['title'].lower()} by the selected player.",
            "evidence_time_ms": e["proof"]["frame_ms"], "source_frame_id": e["proof"]["frame_id"],
            "sequence_event_native": True, "source_sequence_verified": True,
            "source_video_sha256": bundle["source_video_sha256"], "event_source": "sequence_v1",
            "proof_media_style": "SOURCE_UNANNOTATED", "identity_confidence": "high",
            "contact_ms": e["contact_ms"], "contact_interval_ms": e["contact_interval_ms"],
        })
    priority = {e["event_id"]: (0 if e["canonical_event_type"] in {"GOAL", "ASSIST", "SHOT"} else 1)
                for e in bundle["events"]}
    mentions = Counter(row.get("event_id") for row in _iter_structured_rows(full) if isinstance(row, dict))
    full["video_comments"] = sorted(full["video_comments"],
        key=lambda c: (priority[c["event_id"]], -mentions[c["event_id"]], c["evidence_time_ms"]))[:8]
    full["_scoring_scan"] = {"performed": True, "coverage_complete": False,
                              "coverage_status": "PARTIAL", "authority": ENGINE}
    attach_event_evidence_authority(full)
    full = apply_verified_stats_authority(full)
    if (full.get("overall_benchmark") or {}).get("tier") is None:
        # A withheld aggregate cannot retain a recruitment/level label from
        # presentation generated before reconciliation or an older writer.
        potential = full.get("potential_assessment")
        if isinstance(potential, dict):
            potential["current_level"] = "Insufficient verified evidence to establish a playing level."
        outlook = full.get("scout_outlook")
        if isinstance(outlook, dict):
            outlook.update(current_level_label="Insufficient verified evidence", current_level_dots=None,
                           potential_level_label="Not established from partial observations",
                           potential_level_dots=None, recruitment_readiness="Further full-match observation needed")
    by_event = {c["event_id"]: c for c in full["video_comments"]}
    for row in _iter_structured_rows(full):
        if not isinstance(row, dict):
            continue
        row.pop("evidence_id", None)  # a rounded timestamp is not a semantic join
        event_id = row.get("event_id")
        if (event_id in by_event and row.get("canonical_event_ids") == [event_id]
                and row.get("identity_verified") is True):
            evidence = by_event[event_id]
            row.update(evidence_id=evidence["evidence_id"], evidence_time_ms=evidence["evidence_time_ms"],
                       timestamp=evidence["timestamp"])
    if any(e["canonical_action_type"] == "PASS" and e["canonical_outcome"] not in
           {"COMPLETED", "INCOMPLETE", "TEAMMATE_GOAL"} for e in bundle["events"]):
        # An observed attempt with an unseen result is not a failed pass.
        full["match_stats"]["pass_completion_pct"] = None
        full["verified_stats"]["pass_completion_pct"] = None
    if any(e["canonical_action_type"] == "DUEL" and e["canonical_outcome"] not in
           {"WON", "LOST"} for e in bundle["events"]):
        full["match_stats"]["duels_won"] = None
        full["verified_stats"]["stats_completeness"]["duels"] = "only_resolved_outcomes_counted"
    if any(e["canonical_action_type"] == "DRIBBLE" for e in bundle["events"]):
        for key in ("dribbles_attempted", "successful_dribbles"):
            full["match_stats"][key] = None
            full["verified_stats"][key] = None
            full["verified_stats"]["observed_counts"][key] = None
        full["verified_stats"]["stats_completeness"]["dribbles"] = "carry_vs_take_on_unresolved"
    return apply_fail_closed_proof_authority(full)
