"""ScoutMePlay unified analysis engine — FIX09B → FIX09C orchestration.

This is the single production spine. Specialist modules remain modular, but
none owns a competing player/event truth:

    FIX04 local evidence + FIX09A global identity
        → FIX09B.0 GLOBAL_TARGET authority
        → FIX09B.1 all-player + ball scene graph
        → FIX09B.2 sequence discovery/understanding plan
        → (one injected whole-video multimodal call; one bounded contract retry)
        → FIX09B.2 strict normalisation
        → FIX09B.3 canonical target event resolution
        → FIX09C output projection

The module deliberately does NOT import server.py, database code, Emergent,
Gemini, or any network client. The server owns the model call and persistence;
this engine owns the analysis state and deterministic truth transformation.
"""
from __future__ import annotations

from copy import deepcopy

import canonical_event_resolver
import canonical_output_authority
import football_scene_graph
import football_sequence_intelligence
import unified_event_bridge
import unified_identity_authority

VERSION = 1
BARRIER_RISK_PAD_S = 0.25


def compact_identity_timeline(identity_timeline: dict | None) -> dict:
    """Persist FIX09A run metadata without a second dense target-point copy."""
    tl = identity_timeline if isinstance(identity_timeline, dict) else {}
    return {
        "version": tl.get("version"),
        "status": tl.get("status"),
        "reason": tl.get("reason"),
        "global_target_id": tl.get("global_target_id"),
        "timebase": tl.get("timebase") or "canonical_media_ms",
        "scenes": deepcopy(tl.get("scenes") or []),
        "unresolved_intervals": deepcopy(tl.get("unresolved_intervals") or []),
        "other_tracks": deepcopy(tl.get("other_tracks") or []),
        "profile_bank": deepcopy(tl.get("profile_bank") or {}),
        "recovery": deepcopy(tl.get("recovery") or {}),
        "counts": deepcopy(tl.get("counts") or {}),
        "config": deepcopy(tl.get("config") or {}),
        "target_point_count": len(tl.get("target_points") or []),
        "dense_target_points_persisted": False,
    }


def _compact_identity_authority(authority: dict | None) -> dict:
    """Keep identity decisions/metrics without duplicating render geometry."""
    auth = authority if isinstance(authority, dict) else {}
    return {
        "version": auth.get("version"),
        "status": auth.get("status"),
        "global_target_id": auth.get("global_target_id"),
        "timebase": auth.get("timebase"),
        "scenes": deepcopy(auth.get("scenes") or []),
        "unresolved_intervals": deepcopy(auth.get("unresolved_intervals") or []),
        "tap_times_ms": deepcopy(auth.get("tap_times_ms") or []),
        "metrics": deepcopy(auth.get("metrics") or {}),
        "identity_profile": deepcopy(auth.get("identity_profile") or {}),
        "target_point_count": len(auth.get("target_points") or []),
        "dense_target_points_persisted": False,
    }


def _compact_production_track(track: dict | None) -> dict:
    """Persist the one geometry stream required by proof/render consumers."""
    src = track if isinstance(track, dict) else {}
    points = []
    for p in src.get("points") or []:
        if not isinstance(p, dict):
            continue
        if not all(isinstance(p.get(k), (int, float)) and not isinstance(p.get(k), bool)
                   for k in ("t", "x", "y", "w", "h")):
            continue
        points.append({
            "t": p["t"], "x": p["x"], "y": p["y"], "w": p["w"], "h": p["h"],
            "conf": p.get("conf", 0.9),
        })
    return {
        "version": src.get("version"),
        "authority": src.get("authority"),
        "global_target_id": src.get("global_target_id"),
        "points": points,
        "segments": deepcopy(src.get("segments") or []),
        "seed_count": src.get("seed_count"),
    }


def _compact_event_barriers(track: dict | None) -> dict:
    """Persist identity barriers without duplicating the geometry track.

    The event adapter contains the same accepted geometry as the production
    track plus time-only barrier rows.  Persisting both complete tracks wastes
    document budget; dropping the barriers, however, lets later proof renders
    interpolate straight through a short unresolved/predicted interval.
    """
    src = track if isinstance(track, dict) else {}
    points = []
    for p in src.get("points") or []:
        if not (isinstance(p, dict) and p.get("identity_barrier") is True
                and isinstance(p.get("t"), (int, float))
                and not isinstance(p.get("t"), bool)):
            continue
        points.append({
            "t": round(float(p["t"]), 3),
            "scene_id": p.get("scene_id"),
            "barrier_reason": p.get("barrier_reason"),
            "barrier_reasons": deepcopy(p.get("barrier_reasons") or []),
            "identity_barrier": True,
            "proof_eligible": False,
        })
    by_t = {}
    for p in points:
        by_t[p["t"]] = p
    points = [by_t[t] for t in sorted(by_t)]

    intervals = []
    for row in src.get("unresolved_intervals") or []:
        if not isinstance(row, dict):
            continue
        a, b = row.get("start_ms"), row.get("end_ms")
        if not all(isinstance(v, (int, float)) and not isinstance(v, bool)
                   for v in (a, b)):
            continue
        lo, hi = sorted((max(0.0, float(a) / 1000.0),
                         max(0.0, float(b) / 1000.0)))
        intervals.append([lo, hi])
    for p in points:
        intervals.append([
            max(0.0, float(p["t"]) - BARRIER_RISK_PAD_S),
            float(p["t"]) + BARRIER_RISK_PAD_S,
        ])
    merged = []
    for lo, hi in sorted(intervals):
        if merged and lo <= merged[-1][1] + 1e-9:
            merged[-1][1] = max(merged[-1][1], hi)
        else:
            merged.append([lo, hi])
    return {
        "version": src.get("version"),
        "points": points,
        "unsafe_intervals": [[round(a, 3), round(b, 3)] for a, b in merged],
        "barrier_point_count": len(points),
    }


def restore_event_track(production_track: dict | None,
                        barrier_payload: dict | None) -> dict:
    """Rebuild the persisted proof-safe track view for legacy consumers."""
    production = deepcopy(production_track) if isinstance(production_track, dict) else {}
    barriers = barrier_payload if isinstance(barrier_payload, dict) else {}
    rows = []
    for p in production.get("points") or []:
        if isinstance(p, dict) and isinstance(p.get("t"), (int, float)):
            rows.append(deepcopy(p))
    rows.extend(deepcopy(barriers.get("points") or []))
    by_t = {}
    for p in rows:
        if not isinstance(p, dict) or not isinstance(p.get("t"), (int, float)):
            continue
        t = round(float(p["t"]), 3)
        old = by_t.get(t)
        if old is None or p.get("identity_barrier") is True:
            p["t"] = t
            by_t[t] = p
    production["points"] = [by_t[t] for t in sorted(by_t)]
    # Keep the compact seconds-based proof mask under its own explicit schema.
    # Legacy ``unresolved_intervals`` uses millisecond dictionaries; reusing
    # that key for ``[start_s, end_s]`` pairs creates a silent type conflict.
    production["proof_unsafe_intervals"] = proof_unsafe_intervals(barriers)
    return production


def proof_unsafe_intervals(barrier_payload: dict | None) -> list[list[float]]:
    """Return validated global video-time windows where proof must be hidden."""
    src = barrier_payload if isinstance(barrier_payload, dict) else {}
    out = []
    for row in src.get("unsafe_intervals") or []:
        if not (isinstance(row, (list, tuple)) and len(row) == 2):
            continue
        a, b = row
        if not all(isinstance(v, (int, float)) and not isinstance(v, bool)
                   for v in (a, b)):
            continue
        lo, hi = sorted((max(0.0, float(a)), max(0.0, float(b))))
        out.append([lo, hi])
    return out


def is_proof_time_safe(barrier_payload: dict | None, media_ms) -> bool:
    """Return whether one exact media instant is outside identity barriers."""
    if (not isinstance(media_ms, int) or isinstance(media_ms, bool)
            or media_ms < 0):
        return False
    sec = media_ms / 1000.0
    return not any(lo <= sec <= hi for lo, hi in proof_unsafe_intervals(barrier_payload))


def _compact_scene_graph(scene_graph: dict | None) -> dict:
    """Persist diagnostics without duplicating the dense per-frame graph.

    At 8 Hz, ``frames`` plus the duplicated ``player_points`` collection can
    exceed MongoDB's 16 MB document limit on ordinary match footage. The full
    graph remains in memory for B.2/B.3; persistence keeps reproducible run
    metadata and scene boundaries only.
    """
    sg = scene_graph if isinstance(scene_graph, dict) else {}
    return {
        "version": sg.get("version"),
        "status": sg.get("status"),
        "reason": sg.get("reason"),
        "global_target_id": sg.get("global_target_id"),
        "timebase": sg.get("timebase"),
        "hz": sg.get("hz"),
        "scenes": deepcopy(sg.get("scenes") or []),
        "metrics": deepcopy(sg.get("metrics") or {}),
        "team_authority": deepcopy(sg.get("team_authority") or {}),
        "compute_s": sg.get("compute_s"),
        "detector": sg.get("detector"),
        "dense_graph_persisted": False,
    }


def _compact_sequence_plan(plan: dict | None) -> dict:
    """Remove repeated graph_context rows while retaining exact window truth."""
    src = plan if isinstance(plan, dict) else {}
    analysis = []
    for w in src.get("analysis_windows") or []:
        if not isinstance(w, dict):
            continue
        analysis.append({
            k: deepcopy(w.get(k)) for k in (
                "sequence_id", "scene_id", "start_ms", "end_ms", "review_hz",
                "coverage_reason", "verified_frames", "hypothesis_frames",
            )
        } | {"graph_context_rows": len(w.get("graph_context") or [])})
    refinement = []
    for r in src.get("refinement_windows") or []:
        if not isinstance(r, dict):
            continue
        refinement.append({
            k: deepcopy(r.get(k)) for k in (
                "refinement_id", "scene_id", "start_ms", "end_ms", "review_hz",
                "reasons", "sequence_ids",
            )
        } | {"trigger_count": len(r.get("trigger_ms") or [])})
    return {
        "version": src.get("version"),
        "status": src.get("status"),
        "global_target_id": src.get("global_target_id"),
        "timebase": src.get("timebase"),
        "analysis_windows": analysis,
        "refinement_windows": refinement,
        "metrics": deepcopy(src.get("metrics") or {}),
        "graph_context_persisted": False,
    }


def prepare_analysis(
    *,
    video_path: str,
    fix04_track: dict | None,
    identity_timeline: dict | None,
    anchors: list | None,
    anchor_time_offset: float = 0.0,
    identity_profile: dict | None = None,
    player_details: dict | None = None,
) -> dict:
    """Build deterministic identity/scene/sequence state and model prompt.

    This function decodes the video for the B.1 graph and may therefore be
    called through ``asyncio.to_thread`` by an async server. It performs zero
    network/model calls and mutates none of its inputs.
    """
    bundle = unified_event_bridge.build_identity_bundle(
        fix04_track=deepcopy(fix04_track) if isinstance(fix04_track, dict) else {},
        identity_timeline=deepcopy(identity_timeline) if isinstance(identity_timeline, dict) else {},
        anchors=deepcopy(anchors) if isinstance(anchors, list) else [],
        anchor_time_offset=float(anchor_time_offset or 0.0),
        identity_profile=deepcopy(identity_profile) if isinstance(identity_profile, dict) else {},
    )
    authority = bundle.get("authority") or {}
    scene_graph = football_scene_graph.build_scene_graph(str(video_path), authority)
    sequence_plan = football_sequence_intelligence.build_sequence_plan(scene_graph)
    identity_context = bundle.get("identity_context") or {}
    prompt = football_sequence_intelligence.build_analysis_prompt(
        sequence_plan,
        deepcopy(player_details) if isinstance(player_details, dict) else {},
        identity_context,
    )
    production_track = unified_identity_authority.to_production_track(authority)
    event_track, event_track_source = unified_event_bridge.choose_event_track(
        bundle, fallback_fix04_track=fix04_track or {})
    return {
        "version": VERSION,
        "status": "prepared" if sequence_plan.get("analysis_windows") else "no_target_coverage",
        "authority": authority,
        "identity_context": identity_context,
        "production_track": production_track,
        "event_track": event_track,
        "event_track_source": event_track_source,
        "scene_graph": scene_graph,
        "sequence_plan": sequence_plan,
        "analysis_prompt": prompt,
        "metrics": {
            "identity_points": len(authority.get("target_points") or []),
            "production_track_points": len(production_track.get("points") or []),
            "scene_graph_frames": len(scene_graph.get("frames") or []),
            "sequence_windows": len(sequence_plan.get("analysis_windows") or []),
            "refinement_windows": len(sequence_plan.get("refinement_windows") or []),
        },
    }


def _scoring_scan(canonical: dict, sequence_analysis: dict) -> dict:
    """Expose FIX09B's exhaustive scoring-authority state to FIX07.

    FIX07 historically required a separate whole-video scoring scan before it
    would publish goal/assist totals. In the unified engine, that responsibility
    belongs to the same B.2 sequence review + B.3 canonical resolver. The scan
    is considered performed only when every planned sequence window was
    reviewed. Unresolved target SHOT/PASS/CROSS observations remain explicit
    diagnostics; they never become goals/assists by themselves.
    """
    unresolved = [u for u in (canonical or {}).get("unresolved") or [] if isinstance(u, dict)]
    goal_unresolved = sum(1 for u in unresolved if str(u.get("kind") or "").upper() == "SHOT")
    assist_unresolved = sum(
        1 for u in unresolved
        if str(u.get("kind") or "").upper() in {"PASS", "CROSS", "KEY_PASS"}
    )
    return {
        "performed": (sequence_analysis or {}).get("coverage_complete") is True,
        "authority": "FIX09B_CANONICAL_EVENTS",
        "verified_goals": int((canonical or {}).get("metrics", {}).get("goals") or 0),
        "verified_assists": int((canonical or {}).get("metrics", {}).get("assists") or 0),
        "unresolved_goal_attempts": goal_unresolved,
        "unresolved_assist_candidates": assist_unresolved,
    }


def finalise_analysis(raw_model_result: dict | None, prepared: dict | None) -> dict:
    """Turn one B.2 observation response into canonical event/output truth."""
    ctx = prepared if isinstance(prepared, dict) else {}
    plan = ctx.get("sequence_plan") if isinstance(ctx.get("sequence_plan"), dict) else {}
    scene_graph = ctx.get("scene_graph") if isinstance(ctx.get("scene_graph"), dict) else {}
    authority = ctx.get("authority") if isinstance(ctx.get("authority"), dict) else {}

    sequence_analysis = football_sequence_intelligence.normalise_sequence_analysis(
        raw_model_result if isinstance(raw_model_result, dict) else {}, plan)
    canonical = canonical_event_resolver.resolve_canonical_events(
        sequence_analysis, scene_graph, authority)
    ledger = canonical_output_authority.build_ledger_compat(
        canonical, coverage_complete=sequence_analysis.get("coverage_complete") is True)
    timeline = canonical_output_authority.project_timeline(canonical)
    evidence = canonical_output_authority.build_event_native_evidence(canonical)
    scoring_scan = _scoring_scan(canonical, sequence_analysis)

    # Complete review is operationally successful even when every observed
    # action remains explicitly unresolved.  Falling back to legacy FIX08 in
    # precisely that case would let weaker identity evidence overrule the new
    # fail-closed authority.
    status = "ok" if sequence_analysis.get("coverage_complete") else "partial_coverage"
    return {
        "version": VERSION,
        "status": status,
        "global_target_id": "GLOBAL_TARGET",
        "timebase": "canonical_media_ms",
        "identity_authority": authority,
        "scene_graph": scene_graph,
        "sequence_plan": plan,
        "sequence_analysis": sequence_analysis,
        "canonical_events": canonical,
        "event_resolution_status": canonical.get("status"),
        "event_ledger": ledger,
        "action_timeline": timeline,
        "event_native_evidence": evidence,
        "scoring_scan": scoring_scan,
        "production_track": deepcopy(ctx.get("production_track") or {}),
        "event_track": deepcopy(ctx.get("event_track") or {}),
        "event_track_source": ctx.get("event_track_source"),
        "metrics": {
            **deepcopy(ctx.get("metrics") or {}),
            "actions_observed": sequence_analysis.get("metrics", {}).get("actions_total", 0),
            "events_accepted": canonical.get("metrics", {}).get("events_accepted", 0),
            "events_unresolved": canonical.get("metrics", {}).get("observations_unresolved", 0),
            "events_rejected": canonical.get("metrics", {}).get("observations_rejected", 0),
            "coverage_complete": sequence_analysis.get("coverage_complete") is True,
            "model_attempts": max(
                1,
                int(raw_model_result.get("attempts") or 1)
                if isinstance(raw_model_result, dict)
                and isinstance(raw_model_result.get("attempts"), int)
                and not isinstance(raw_model_result.get("attempts"), bool)
                else 1,
            ),
        },
    }


def build_retry_request(prepared: dict | None, sequence_ids,
                        player_details: dict | None = None) -> dict:
    """Build one bounded retry request for incomplete original windows only."""
    ctx = prepared if isinstance(prepared, dict) else {}
    plan = football_sequence_intelligence.subset_sequence_plan(
        ctx.get("sequence_plan"), sequence_ids)
    prompt = football_sequence_intelligence.build_analysis_prompt(
        plan,
        deepcopy(player_details) if isinstance(player_details, dict) else {},
        deepcopy(ctx.get("identity_context") or {}),
    )
    return {"sequence_plan": plan, "analysis_prompt": prompt}


def merge_model_attempts(results) -> dict:
    """Public orchestration wrapper for deterministic bounded-attempt merge."""
    return football_sequence_intelligence.merge_raw_sequence_results(results)


def is_production_ready(result: dict | None) -> bool:
    """True only when every supplied B.2 window passed its response contract."""
    r = result if isinstance(result, dict) else {}
    seq = r.get("sequence_analysis") if isinstance(r.get("sequence_analysis"), dict) else {}
    canonical = r.get("canonical_events") if isinstance(r.get("canonical_events"), dict) else {}
    return bool(
        r.get("status") == "ok"
        and seq.get("coverage_complete") is True
        and not (seq.get("incomplete_sequence_ids") or [])
        and int((r.get("metrics") or {}).get("sequence_windows") or 0) > 0
        and canonical.get("status") in {"ok", "empty", "unresolved"}
    )


def apply_result_to_report(full: dict, result: dict | None) -> dict:
    """Apply ONLY the canonical B.3 truth to report/event/evidence surfaces."""
    r = result if isinstance(result, dict) else {}
    canonical = r.get("canonical_events") if isinstance(r.get("canonical_events"), dict) else {}
    sequence = r.get("sequence_analysis") if isinstance(r.get("sequence_analysis"), dict) else {}
    return canonical_output_authority.apply_to_report(full, canonical, sequence)


def canonical_event_telestration_box(comment: dict | None) -> dict | None:
    """Expose FIX09C's fail-closed still-frame geometry to server rendering."""
    return canonical_output_authority.canonical_event_telestration_box(comment)


def persistence_payload(result: dict | None) -> dict:
    """Compact, explicit DB payload for diagnostics/audit without raw prompt.

    Dense frame data stays ephemeral to respect MongoDB's document limit; the
    authoritative decisions and enough run metadata for operational audit are
    retained below.
    """
    r = result if isinstance(result, dict) else {}
    return {
        "unified_analysis_version": VERSION,
        "unified_analysis_status": r.get("status"),
        "unified_identity_authority": _compact_identity_authority(r.get("identity_authority")),
        "football_scene_graph": _compact_scene_graph(r.get("scene_graph")),
        "football_sequence_plan": _compact_sequence_plan(r.get("sequence_plan")),
        "football_sequence_analysis": deepcopy(r.get("sequence_analysis") or {}),
        "canonical_events": deepcopy(r.get("canonical_events") or {}),
        "event_ledger": deepcopy(r.get("event_ledger") or {}),
        "unified_scoring_scan": deepcopy(r.get("scoring_scan") or {}),
        "unified_analysis_metrics": deepcopy(r.get("metrics") or {}),
        "unified_production_track": _compact_production_track(r.get("production_track")),
        "unified_event_barriers": _compact_event_barriers(r.get("event_track")),
        "unified_event_track_source": r.get("event_track_source"),
    }
