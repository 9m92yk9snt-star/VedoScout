"""ScoutMePlay unified analysis engine — FIX09B → FIX09C orchestration.

This is the single production spine. Specialist modules remain modular, but
none owns a competing player/event truth:

    FIX04 local evidence + FIX09A global identity
        → FIX09B.0 GLOBAL_TARGET authority
        → FIX09B.1 all-player + ball scene graph
        → FIX09B.2 sequence discovery/understanding plan
        → (one injected whole-video multimodal call)
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

    status = "ok"
    if not sequence_analysis.get("coverage_complete"):
        status = "partial_coverage"
    if canonical.get("status") == "unresolved" and not canonical.get("events"):
        status = "unresolved"
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
        },
    }


def apply_result_to_report(full: dict, result: dict | None) -> dict:
    """Apply ONLY the canonical B.3 truth to report/event/evidence surfaces."""
    r = result if isinstance(result, dict) else {}
    canonical = r.get("canonical_events") if isinstance(r.get("canonical_events"), dict) else {}
    sequence = r.get("sequence_analysis") if isinstance(r.get("sequence_analysis"), dict) else {}
    return canonical_output_authority.apply_to_report(full, canonical, sequence)


def persistence_payload(result: dict | None) -> dict:
    """Compact, explicit DB payload for diagnostics/replay without raw prompt.

    The raw model response may be persisted separately by the server if needed;
    the authoritative structures below are deterministic outputs.
    """
    r = result if isinstance(result, dict) else {}
    return {
        "unified_analysis_version": VERSION,
        "unified_analysis_status": r.get("status"),
        "unified_identity_authority": deepcopy(r.get("identity_authority") or {}),
        "football_scene_graph": deepcopy(r.get("scene_graph") or {}),
        "football_sequence_plan": deepcopy(r.get("sequence_plan") or {}),
        "football_sequence_analysis": deepcopy(r.get("sequence_analysis") or {}),
        "canonical_events": deepcopy(r.get("canonical_events") or {}),
        "event_ledger": deepcopy(r.get("event_ledger") or {}),
        "unified_scoring_scan": deepcopy(r.get("scoring_scan") or {}),
        "unified_analysis_metrics": deepcopy(r.get("metrics") or {}),
        "unified_production_track": deepcopy(r.get("production_track") or {}),
        "unified_event_track": deepcopy(r.get("event_track") or {}),
        "unified_event_track_source": r.get("event_track_source"),
    }
