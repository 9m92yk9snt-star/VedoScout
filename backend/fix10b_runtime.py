"""FIX10B runtime bridge — convert proof-gated physical reconciliation into
one internally consistent unified-analysis result.

The module is deterministic and side-effect free. It does not touch Mongo or
report objects directly. Canonical activation is explicitly feature-flagged so
FIX10A remains independently observe-only.
"""
from __future__ import annotations

import os
from copy import deepcopy

import canonical_output_authority
import fix10b_reconciliation

VERSION = 1
FLAG = "FIX10B_CANONICAL_ENABLED"


def canonical_enabled() -> bool:
    return str(os.environ.get(FLAG, "0")).strip().lower() in {"1", "true", "yes", "on"}


def _scoring_scan(canonical: dict, sequence_analysis: dict) -> dict:
    unresolved = [u for u in (canonical or {}).get("unresolved") or [] if isinstance(u, dict)]
    goal_unresolved = sum(1 for u in unresolved if str(u.get("kind") or "").upper() == "SHOT")
    assist_unresolved = sum(
        1 for u in unresolved
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
        "status": "applied" if int((reconciliation or {}).get("proposals_applied") or 0) > 0 else "no_change",
        "authority": "FIX10B_PHYSICAL_RECONCILIATION",
        "proposals_total": int((reconciliation or {}).get("proposals_total") or 0),
        "proposals_applied": int((reconciliation or {}).get("proposals_applied") or 0),
        "proposals_contradictory": int((reconciliation or {}).get("proposals_contradictory") or 0),
        "changes": deepcopy((reconciliation or {}).get("changes") or []),
        "counts": deepcopy(canonical.get("counts") or {}) if isinstance(canonical, dict) else {},
    }


def reconcile_unified_result(unified_result: dict | None,
                             physical_result: dict | None) -> dict:
    """Build a complete FIX10B unified result without mutating either input.

    A partial FIX10A run is allowed to contribute only from its successful
    traces. Every individual proposal still has to pass FIX10B's strict proof
    gates. Failed windows therefore cannot invent events, but a fully proven
    chain in another successful window need not be discarded.
    """
    source = deepcopy(unified_result) if isinstance(unified_result, dict) else {}
    canonical_before = source.get("canonical_events") if isinstance(source.get("canonical_events"), dict) else {}
    sequence = source.get("sequence_analysis") if isinstance(source.get("sequence_analysis"), dict) else {}

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
    cmetrics = canonical.get("metrics") if isinstance(canonical.get("metrics"), dict) else {}
    metrics.update({
        "events_accepted": int(cmetrics.get("events_accepted") or 0),
        "events_unresolved": int(cmetrics.get("observations_unresolved") or 0),
        "events_rejected": int(cmetrics.get("observations_rejected") or 0),
        "verified_goals": int(cmetrics.get("goals") or 0),
        "verified_assists": int(cmetrics.get("assists") or 0),
        "verified_shots": int(cmetrics.get("shots") or 0),
        "fix10b_proposals_applied": int((canonical.get("reconciliation") or {}).get("proposals_applied") or 0),
    })

    source.update({
        "version": "FIX10B.1",
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


def build_candidate(unified_result: dict | None,
                    physical_result: dict | None) -> dict:
    """Return both an auditable summary and the in-memory reconciled result.

    The caller decides whether the candidate becomes canonical. This function
    itself grants no authority and performs no persistence.
    """
    reconciled = reconcile_unified_result(unified_result, physical_result)
    return {
        "version": VERSION,
        "enabled": canonical_enabled(),
        "summary": deepcopy(reconciled.get("fix10b_summary") or {}),
        "unified_result": reconciled,
    }
