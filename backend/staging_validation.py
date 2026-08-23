"""Deterministic FIX09B/FIX09C staging acceptance validator.

Run this against an exported final report document after a real staging upload.
It does not re-analyse video or infer football facts.  It verifies that the
production pipeline persisted one internally consistent authority from
GLOBAL_TARGET through canonical events, stats, evidence, snapshots and proof
clips.  A non-zero CLI exit code means the staging run is not acceptable.
"""
from __future__ import annotations

import argparse
import json
from copy import deepcopy
from pathlib import Path

SCHEMA = "FIX09BC_STAGING_VALIDATION_V1"
DEFAULT_EXPECTATIONS = {
    "goals": 1,
    "assists": 3,
    "extra_shots": 1,
    "min_proof_clips": 3,
}


def _rows(value):
    return [x for x in (value or []) if isinstance(x, dict)]


def _event_counts(events):
    goals = sum(str(e.get("canonical_event_type") or "").upper() == "GOAL" for e in events)
    assists = sum(str(e.get("canonical_event_type") or "").upper() == "ASSIST" for e in events)
    shots = sum(str(e.get("canonical_action_type") or "").upper() == "SHOT" for e in events)
    return {"goals": goals, "assists": assists, "shots": shots,
            "extra_shots": max(0, shots - goals)}


def _inside_unsafe_window(media_ms, barriers):
    if not isinstance(media_ms, int):
        return True
    sec = media_ms / 1000.0
    for row in (barriers or {}).get("unsafe_intervals") or []:
        if (isinstance(row, (list, tuple)) and len(row) == 2
                and all(isinstance(v, (int, float)) and not isinstance(v, bool)
                        for v in row)):
            lo, hi = sorted((float(row[0]), float(row[1])))
            if lo <= sec <= hi:
                return True
    return False


def validate_report_document(report_doc: dict, expectations: dict | None = None) -> dict:
    """Return machine-readable staging checks for one final report document."""
    doc = report_doc if isinstance(report_doc, dict) else {}
    expected = {**DEFAULT_EXPECTATIONS, **(expectations or {})}
    checks = []

    def check(cid, passed, *, expected_value=None, actual=None, detail=""):
        checks.append({
            "id": cid,
            "status": "PASS" if bool(passed) else "FAIL",
            "expected": deepcopy(expected_value),
            "actual": deepcopy(actual),
            "detail": detail,
        })

    full = doc.get("full_report") if isinstance(doc.get("full_report"), dict) else {}
    canonical = doc.get("canonical_events") if isinstance(doc.get("canonical_events"), dict) else {}
    sequence = (doc.get("football_sequence_analysis")
                if isinstance(doc.get("football_sequence_analysis"), dict) else {})
    graph = doc.get("football_scene_graph") if isinstance(doc.get("football_scene_graph"), dict) else {}
    team = graph.get("team_authority") if isinstance(graph.get("team_authority"), dict) else {}
    ledger = doc.get("event_ledger") if isinstance(doc.get("event_ledger"), dict) else {}
    scoring = doc.get("unified_scoring_scan") if isinstance(doc.get("unified_scoring_scan"), dict) else {}
    events = _rows(canonical.get("events"))
    timeline = _rows(full.get("action_timeline"))
    comments = _rows(full.get("video_comments"))
    snapshots = _rows(full.get("snapshot_moments"))
    barriers = doc.get("unified_event_barriers") if isinstance(doc.get("unified_event_barriers"), dict) else {}

    check("report.ready", doc.get("full_report_status") == "ready",
          expected_value="ready", actual=doc.get("full_report_status"),
          detail="Final assets and identity gate must finish before acceptance.")
    check("engine.unified_status", doc.get("unified_analysis_status") == "ok",
          expected_value="ok", actual=doc.get("unified_analysis_status"))
    check("engine.event_track", doc.get("unified_event_track_source") == "UNIFIED_IDENTITY",
          expected_value="UNIFIED_IDENTITY", actual=doc.get("unified_event_track_source"))
    check("engine.movement_track", doc.get("movement_track_source") == "UNIFIED_GLOBAL_TARGET",
          expected_value="UNIFIED_GLOBAL_TARGET", actual=doc.get("movement_track_source"))
    check("identity.global_target",
          (doc.get("unified_identity_authority") or {}).get("global_target_id") == "GLOBAL_TARGET",
          expected_value="GLOBAL_TARGET",
          actual=(doc.get("unified_identity_authority") or {}).get("global_target_id"))
    check("scene_graph.ok", graph.get("status") == "ok",
          expected_value="ok", actual=graph.get("status"))
    check("team_authority.ok", team.get("status") == "ok",
          expected_value="ok", actual=team.get("status"),
          detail=str(team.get("reason") or ""))
    check("coverage.complete",
          sequence.get("coverage_complete") is True
          and not (sequence.get("incomplete_sequence_ids") or []),
          expected_value={"coverage_complete": True, "incomplete_sequence_ids": []},
          actual={"coverage_complete": sequence.get("coverage_complete"),
                  "incomplete_sequence_ids": sequence.get("incomplete_sequence_ids") or []})
    check("events.authority", canonical.get("status") == "ok"
          and canonical.get("global_target_id") == "GLOBAL_TARGET",
          expected_value={"status": "ok", "global_target_id": "GLOBAL_TARGET"},
          actual={"status": canonical.get("status"),
                  "global_target_id": canonical.get("global_target_id")})
    check("ledger.authority",
          ledger.get("authority") == "FIX09B_CANONICAL_EVENTS"
          and ledger.get("discovery_complete") is True,
          expected_value={"authority": "FIX09B_CANONICAL_EVENTS",
                          "discovery_complete": True},
          actual={"authority": ledger.get("authority"),
                  "discovery_complete": ledger.get("discovery_complete")})

    canonical_ids = [e.get("event_id") for e in events]
    check("events.unique_ids",
          bool(canonical_ids) and all(isinstance(x, str) and x for x in canonical_ids)
          and len(canonical_ids) == len(set(canonical_ids)),
          expected_value="non-empty unique event_id for every event",
          actual=canonical_ids)
    check("events.global_target_only",
          bool(events) and all(e.get("global_target_id") == "GLOBAL_TARGET" for e in events),
          expected_value="GLOBAL_TARGET", actual=sorted({e.get("global_target_id") for e in events}))

    counts = _event_counts(events)
    expected_counts = {k: int(expected[k]) for k in ("goals", "assists", "extra_shots")}
    check("reference.canonical_counts",
          all(counts[k] == expected_counts[k] for k in expected_counts),
          expected_value=expected_counts,
          actual={k: counts[k] for k in expected_counts})

    goals = [e for e in events if str(e.get("canonical_event_type") or "").upper() == "GOAL"]
    assists = [e for e in events if str(e.get("canonical_event_type") or "").upper() == "ASSIST"]
    check("scoring.causal_verified",
          all(e.get("causal_verified") is True for e in goals + assists),
          expected_value=True,
          actual={e.get("event_id"): e.get("causal_verified") for e in goals + assists})
    assist_team = {e.get("event_id"): e.get("receiver_team_resolution") for e in assists}
    check("assists.teammate_verified",
          len(assists) == int(expected["assists"])
          and all(isinstance(v, dict) and v.get("status") == "VERIFIED"
                  and int((v.get("sample_counts") or {}).get("target_team") or 0) >= 2
                  and (v.get("actor_ball_relation") or {}).get("status") == "VERIFIED"
                  and (v.get("receiver_ball_relation") or {}).get("status") == "VERIFIED"
                  for v in assist_team.values()),
          expected_value=("VERIFIED receiver with >=2 target_team samples and "
                          "verified target-to-receiver ball transfer"),
          actual=assist_team)

    scan_actual = {
        "performed": scoring.get("performed"),
        "authority": scoring.get("authority"),
        "verified_goals": scoring.get("verified_goals"),
        "verified_assists": scoring.get("verified_assists"),
    }
    check("scoring_scan.consistent",
          scan_actual == {"performed": True, "authority": "FIX09B_CANONICAL_EVENTS",
                          "verified_goals": counts["goals"],
                          "verified_assists": counts["assists"]},
          expected_value={"performed": True, "authority": "FIX09B_CANONICAL_EVENTS",
                          "verified_goals": counts["goals"],
                          "verified_assists": counts["assists"]},
          actual=scan_actual)

    timeline_ids = [e.get("event_id") for e in timeline]
    check("timeline.same_event_ids",
          len(timeline_ids) == len(set(timeline_ids))
          and set(timeline_ids) == set(canonical_ids),
          expected_value=sorted(canonical_ids), actual=sorted(timeline_ids))
    by_canonical = {e.get("event_id"): e for e in events}
    time_mismatches = []
    for row in timeline:
        source = by_canonical.get(row.get("event_id"))
        if (source is None or row.get("event_source") != "fix09b_canonical"
                or row.get("cross_verified") is not True
                or row.get("event_start_ms") != source.get("canonical_ms")):
            time_mismatches.append(row.get("event_id"))
    check("timeline.canonical_time_and_source", not time_mismatches,
          expected_value="FIX09B canonical source and identical canonical media_ms",
          actual=time_mismatches)

    verified = full.get("verified_stats") if isinstance(full.get("verified_stats"), dict) else {}
    stats_actual = {k: verified.get(k) for k in ("goals", "assists", "shots")}
    check("stats.same_counts",
          verified.get("available") is True
          and verified.get("goals_assists_available") is True
          and stats_actual == {"goals": counts["goals"], "assists": counts["assists"],
                               "shots": counts["shots"]},
          expected_value={"goals": counts["goals"], "assists": counts["assists"],
                          "shots": counts["shots"]},
          actual=stats_actual)
    discovery = full.get("event_discovery") if isinstance(full.get("event_discovery"), dict) else {}
    check("report.event_authority",
          discovery.get("authority") == "FIX09B_CANONICAL_EVENTS"
          and discovery.get("event_discovery_complete") is True,
          expected_value={"authority": "FIX09B_CANONICAL_EVENTS",
                          "event_discovery_complete": True},
          actual={"authority": discovery.get("authority"),
                  "event_discovery_complete": discovery.get("event_discovery_complete")})

    scoring_ids = {e.get("event_id") for e in goals + assists}
    comments_by_event = {}
    for row in comments:
        if row.get("event_id"):
            comments_by_event.setdefault(row["event_id"], []).append(row)
    missing_proof = []
    proof_rows = {}
    for event_id in scoring_ids:
        source = by_canonical[event_id]
        candidates = comments_by_event.get(event_id) or []
        good = next((c for c in candidates
                     if c.get("canonical_event_native") is True
                     and c.get("event_source") == "fix09b_canonical"
                     and c.get("proof_frame_verified") is True and c.get("frame_url")
                     and c.get("event_track_locked") is True
                     and c.get("frame_time_authority") == "ACTUAL_MEDIA_PTS"
                     and c.get("canonical_event_ms") == source.get("canonical_ms")
                     and isinstance(c.get("frame_time_ms"), int)
                     and c.get("frame_time_ms") == c.get("evidence_time_ms")
                     and not _inside_unsafe_window(c.get("frame_time_ms"), barriers)), None)
        if good is None:
            missing_proof.append(event_id)
        else:
            proof_rows[event_id] = good
    check("proof.scoring_frames", not missing_proof,
          expected_value=sorted(scoring_ids), actual=sorted(proof_rows),
          detail="Every goal/assist needs an exact, event-bound, target-locked frame.")

    snapshot_ids = {m.get("event_id") for m in snapshots if m.get("proof_verified") is True
                    and m.get("frame_url")}
    expected_snapshot_ids = scoring_ids if len(scoring_ids) <= 4 else set(sorted(scoring_ids)[:4])
    check("snapshots.scoring_events",
          full.get("snapshot_moments_authority") is True
          and expected_snapshot_ids.issubset(snapshot_ids),
          expected_value=sorted(expected_snapshot_ids), actual=sorted(snapshot_ids))

    clip_rows = [c for c in proof_rows.values() if c.get("tele_clip_url")]
    bad_clips = []
    for c in clip_rows:
        event = by_canonical.get(c.get("event_id")) or {}
        if not (c.get("clip_id") and isinstance(c.get("clip_start_ms"), int)
                and isinstance(c.get("clip_end_ms"), int)
                and c["clip_start_ms"] < c["clip_end_ms"]
                and c.get("moment_local_ms") == event.get("canonical_ms") - c["clip_start_ms"]
                and c.get("telestrated") is True and c.get("tele_ring") is True
                and c.get("tele_authority") == "FIX09B_CANONICAL_GEOMETRY"):
            bad_clips.append(c.get("event_id"))
    check("proof.clips_and_ellipse",
          len(clip_rows) >= int(expected["min_proof_clips"]) and not bad_clips,
          expected_value={"minimum": int(expected["min_proof_clips"]),
                          "canonical_clip_authority": True, "ellipse": True},
          actual={"count": len(clip_rows), "invalid_event_ids": bad_clips})

    unsafe_scoring = [e.get("event_id") for e in goals + assists
                      if _inside_unsafe_window(e.get("canonical_ms"), barriers)]
    check("proof.outside_identity_barriers", not unsafe_scoring,
          expected_value=[], actual=unsafe_scoring)

    failures = [c["id"] for c in checks if c["status"] == "FAIL"]
    return {
        "schema": SCHEMA,
        "status": "pass" if not failures else "fail",
        "expectations": expected,
        "metrics": {
            **counts,
            "canonical_events": len(events),
            "timeline_events": len(timeline),
            "scoring_proof_frames": len(proof_rows),
            "scoring_proof_clips": len(clip_rows),
            "checks_passed": len(checks) - len(failures),
            "checks_total": len(checks),
        },
        "failures": failures,
        "checks": checks,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Validate one final FIX09B/C staging report JSON")
    parser.add_argument("report_json", type=Path)
    parser.add_argument("--goals", type=int, default=DEFAULT_EXPECTATIONS["goals"])
    parser.add_argument("--assists", type=int, default=DEFAULT_EXPECTATIONS["assists"])
    parser.add_argument("--extra-shots", type=int, default=DEFAULT_EXPECTATIONS["extra_shots"])
    parser.add_argument("--min-proof-clips", type=int,
                        default=DEFAULT_EXPECTATIONS["min_proof_clips"])
    args = parser.parse_args(argv)
    with args.report_json.open("r", encoding="utf-8") as handle:
        doc = json.load(handle)
    result = validate_report_document(doc, {
        "goals": args.goals,
        "assists": args.assists,
        "extra_shots": args.extra_shots,
        "min_proof_clips": args.min_proof_clips,
    })
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
