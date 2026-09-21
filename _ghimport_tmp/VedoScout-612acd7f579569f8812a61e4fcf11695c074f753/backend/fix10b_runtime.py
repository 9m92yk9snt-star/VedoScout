"""FIX10B production bridge — reconcile physical proof into canonical truth.

FIX10B is deterministic and side-effect free. It consumes the already verified
FIX09B unified result plus FIX10A physical reconstruction and returns one
internally consistent canonical result. There is no shadow/canonical feature
gate in production: proof-qualified proposals are applied, ambiguous evidence
fails closed and leaves the FIX09B event unchanged.
"""
from __future__ import annotations

from copy import deepcopy

import canonical_output_authority
import fix10b_reconciliation

VERSION = 2


def _scoring_scan(canonical: dict, sequence_analysis: dict) -> dict:
    unresolved = [
        u for u in (canonical or {}).get("unresolved") or [] if isinstance(u, dict)
    ]
    goal_unresolved = sum(
        1 for u in unresolved if str(u.get("kind") or "").upper() == "SHOT"
    )
    assist_unresolved = sum(
        1
        for u in unresolved
        if str(u.get("kind") or "").upper() in {"PASS", "CROSS", "KEY_PASS"}
    )
    reconciliation = canonical.get("reconciliation") if isinstance(canonical, dict) else {}
    return {
        "performed": (sequence_analysis or {}).get("coverage_complete") is True,
        "authority": "FIX10B_PHYSICAL_RECONCILIATION",
        "verified_goals": int((canonical or {}).get("metrics", {}).get("goals") or 0),
        "verified_assists": int((canonical or {}).get("metrics", {}).get("assists") or 0),
        "unresolved_goal_attempts": goal_unresolved,
        "unresolved_assist_candidates": assist_unresolved,
        "fix10b_proposals_applied": int((reconciliation or {}).get("proposals_applied") or 0),
    }


def _summary(canonical: dict) -> dict:
    reconciliation = canonical.get("reconciliation") if isinstance(canonical, dict) else {}
    return {
        "version": VERSION,
        "status": (
            "applied"
            if int((reconciliation or {}).get("proposals_applied") or 0) > 0
            else "no_change"
        ),
        "mode": "production",
        "authority": "FIX10B_PHYSICAL_RECONCILIATION",
        "proposals_total": int((reconciliation or {}).get("proposals_total") or 0),
        "proposals_applied": int((reconciliation or {}).get("proposals_applied") or 0),
        "proposals_contradictory": int(
            (reconciliation or {}).get("proposals_contradictory") or 0
        ),
        "changes": deepcopy((reconciliation or {}).get("changes") or []),
        "counts": deepcopy(canonical.get("counts") or {}) if isinstance(canonical, dict) else {},
    }


def reconcile_unified_result(
    unified_result: dict | None,
    physical_result: dict | None,
) -> dict:
    """Build the complete production unified result without mutating inputs.

    A partial FIX10A run may contribute only from successful traces. Every
    proposal still has to pass FIX10B's strict physical-proof gates. Failed or
    ambiguous windows therefore cannot invent events.
    """
    source = deepcopy(unified_result) if isinstance(unified_result, dict) else {}
    canonical_before = (
        source.get("canonical_events")
        if isinstance(source.get("canonical_events"), dict)
        else {}
    )
    sequence = (
        source.get("sequence_analysis")
        if isinstance(source.get("sequence_analysis"), dict)
        else {}
    )

    canonical = fix10b_reconciliation.reconcile_canonical_events(
        canonical_before,
        physical_result if isinstance(physical_result, dict) else {},
    )
    ledger = canonical_output_authority.build_ledger_compat(
        canonical,
        coverage_complete=sequence.get("coverage_complete") is True,
    )
    timeline = canonical_output_authority.project_timeline(canonical)
    evidence = canonical_output_authority.build_event_native_evidence(canonical)
    scoring = _scoring_scan(canonical, sequence)

    metrics = deepcopy(source.get("metrics") or {})
    cmetrics = (
        canonical.get("metrics") if isinstance(canonical.get("metrics"), dict) else {}
    )
    metrics.update({
        "events_accepted": int(cmetrics.get("events_accepted") or 0),
        "events_unresolved": int(cmetrics.get("observations_unresolved") or 0),
        "events_rejected": int(cmetrics.get("observations_rejected") or 0),
        "verified_goals": int(cmetrics.get("goals") or 0),
        "verified_assists": int(cmetrics.get("assists") or 0),
        "verified_shots": int(cmetrics.get("shots") or 0),
        "fix10b_proposals_applied": int(
            (canonical.get("reconciliation") or {}).get("proposals_applied") or 0
        ),
    })

    source.update({
        "version": "FIX10B.2",
        "canonical_events": canonical,
        "event_resolution_status": canonical.get("status"),
        "event_ledger": ledger,
        "action_timeline": timeline,
        "event_native_evidence": evidence,
        "scoring_scan": scoring,
        "metrics": metrics,
        "fix10b_summary": _summary(canonical),
    })
    return source


def build_candidate(
    unified_result: dict | None,
    physical_result: dict | None,
) -> dict:
    """Return the authoritative production reconciliation candidate."""
    reconciled = reconcile_unified_result(unified_result, physical_result)
    return {
        "version": VERSION,
        "enabled": True,
        "mode": "production",
        "summary": deepcopy(reconciled.get("fix10b_summary") or {}),
        "unified_result": reconciled,
    }
