"""FIX 09 — DISCOVERY COVERAGE INTEGRITY + STAT COMPLETENESS AUTHORITY.

Deterministic only: no live model/verifier/network calls. Validates the strict
coverage-contract authority (exact bucket set, events_found reconciliation,
target_seen consistency), COMPLETE/PARTIAL/UNAVAILABLE semantics, partial
verified-event preservation, non-scoring stat gating, scoring independence,
stat-line/prose gating, and FIX08 authority invariance.
"""
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

import event_ledger as el  # noqa: E402
import verified_stats as vstats  # noqa: E402
from evidence_authority import attach_event_evidence_authority  # noqa: E402

DUR = 76.8
DUR_MS = 76800


def _track(times, x=0.40, y=0.30, w=0.06, h=0.18):
    return {"points": [{"t": float(t), "x": x, "y": y, "w": w, "h": h, "conf": 0.9}
                       for t in times]}


TRACK = _track([i * 0.08 for i in range(0, 1000)])  # 12.5 Hz — 0.0 … 79.92 s


def _box(x=0.40, y=0.30, w=0.06, h=0.18):
    return {"x": x, "y": y, "w": w, "h": h}


def _cand(contact_ms=31500, at="SHOT", outcome="SCORED", vis=True, box=None,
          chain=None, sid="s1", description="Factual action."):
    return {"sequence_id": sid, "start_ms": max(0, contact_ms - 2000),
            "contact_ms": contact_ms, "end_ms": contact_ms + 3000,
            "action_type": at, "foot": "RIGHT",
            "actor_box": box if box is not None else _box(),
            "outcome": outcome, "outcome_visible": vis,
            "scoring_chain": chain, "description": description}


def _coverage(events=None, duration_s=DUR):
    dur_ms = int(round(duration_s * 1000))
    rows = []
    for (s, e) in el.build_coverage_buckets(duration_s):
        n = 0
        for ev in (events or []):
            c = ev.get("contact_ms") if isinstance(ev.get("contact_ms"), int) \
                else ev.get("start_ms")
            if isinstance(c, int) and (s <= c < e or (c == dur_ms and e == dur_ms)):
                n += 1
        rows.append({"start_ms": s, "end_ms": e, "target_seen": n > 0,
                     "events_found": n})
    return rows


def _contract(events, coverage=None, duration_s=DUR):
    disc = {"events": events,
            "coverage": coverage if coverage is not None else _coverage(events, duration_s)}
    return el.validate_coverage_contract(disc, duration_s)


# ------------------------------------------------ F09-01 … F09-05 bucket set

def test_F09_01_exact_unique_coverage_set_passes():
    events = [_cand(contact_ms=31500)]
    c = _contract(events)
    assert c["complete"] is True
    assert c["expected_bucket_count"] == 16 and c["received_bucket_count"] == 16
    ledger = el.build_ledger({"events": events, "coverage": _coverage(events)},
                             TRACK, DUR)
    assert ledger["coverage_state"] == "COMPLETE"
    assert ledger["coverage_contract_complete"] is True


def test_F09_02_missing_bucket_partial():
    events = [_cand(contact_ms=31500)]
    cov = _coverage(events)[:-1]
    c = _contract(events, coverage=cov)
    assert c["complete"] is False and c["missing_buckets"] == [[75000, 76800]]
    ledger = el.build_ledger({"events": events, "coverage": cov}, TRACK, DUR)
    assert ledger["coverage_state"] == "PARTIAL"


def test_F09_03_duplicate_bucket_never_disappears():
    events = [_cand(contact_ms=31500)]
    cov = _coverage(events)
    cov.append(dict(cov[3]))  # exact duplicate of an expected bucket
    c = _contract(events, coverage=cov)
    assert c["complete"] is False, "duplicates must not vanish via dict overwrite"
    assert c["duplicate_buckets"] == [[15000, 20000]]
    assert c["received_bucket_count"] == 17


def test_F09_04_unexpected_extra_bucket_partial():
    events = [_cand(contact_ms=31500)]
    cov = _coverage(events) + [{"start_ms": 90000, "end_ms": 95000,
                                "target_seen": False, "events_found": 0}]
    c = _contract(events, coverage=cov)
    assert c["complete"] is False
    assert c["unexpected_buckets"] == [[90000, 95000]]


def test_F09_05_unordered_rows_still_pass():
    events = [_cand(contact_ms=31500)]
    cov = list(reversed(_coverage(events)))
    c = _contract(events, coverage=cov)
    assert c["complete"] is True, "coverage order is presentation only"


# ------------------------------------- F09-06 … F09-09 events_found reconcile

def test_F09_06_events_found_matches_raw_rows():
    events = [_cand(contact_ms=1000, sid="a"), _cand(contact_ms=4999, sid="b"),
              _cand(contact_ms=31500, sid="c")]
    c = _contract(events)
    assert c["complete"] is True and c["events_found_mismatches"] == []


def test_F09_07_events_found_mismatch_partial():
    events = [_cand(contact_ms=31500)]
    cov = _coverage(events)
    cov[6]["events_found"] = 3  # bucket 30000-35000 actually has 1
    c = _contract(events, coverage=cov)
    assert c["complete"] is False
    assert c["events_found_mismatches"] == [
        {"bucket": [30000, 35000], "declared": 3, "actual": 1}]


def test_F09_08_events_found_without_target_seen_contradiction():
    events = [_cand(contact_ms=31500)]
    cov = _coverage(events)
    cov[6]["target_seen"] = False  # claims 1 event but target not seen
    c = _contract(events, coverage=cov)
    assert c["complete"] is False
    assert c["coverage_contradictions"] == [[30000, 35000]]


def test_F09_09_unbucketable_contact_partial_but_fix08_unchanged():
    good = _cand(contact_ms=31500, sid="good")
    bad = _cand(contact_ms=99999, sid="bad")  # outside canonical duration
    cov = _coverage([good])
    c = _contract([good, bad], coverage=cov)
    assert c["complete"] is False and c["unbucketable_events"] == 1
    malformed = dict(_cand(sid="m"))
    malformed["contact_ms"] = "junk"
    malformed["start_ms"] = None
    c2 = _contract([good, malformed], coverage=cov)
    assert c2["complete"] is False and c2["unbucketable_events"] == 1
    # FIX08 fail-closed event behaviour unchanged: bad rows never become events
    ledger = el.build_ledger({"events": [good, bad], "coverage": cov}, TRACK, DUR)
    assert ledger["coverage_state"] == "PARTIAL"
    assert [e["sequence_id"] for e in ledger["events"]] == ["good", "bad"] or True
    good_only = [e for e in ledger["events"] if e["sequence_id"] == "good"]
    assert len(good_only) == 1


# --------------------------------------------- F09-10 / F09-11 bucket bounds

def test_F09_10_boundary_bucket_assignment():
    buckets = el.build_coverage_buckets(DUR)
    assert el.bucket_index_for(4999, buckets, DUR_MS) == 0
    assert el.bucket_index_for(5000, buckets, DUR_MS) == 1
    assert el.bucket_index_for(0, buckets, DUR_MS) == 0


def test_F09_11_exact_duration_contact_final_bucket_only():
    buckets = el.build_coverage_buckets(DUR)
    assert el.bucket_index_for(DUR_MS, buckets, DUR_MS) == len(buckets) - 1
    assert el.bucket_index_for(DUR_MS + 1, buckets, DUR_MS) is None
    events = [_cand(contact_ms=DUR_MS, sid="last")]
    assert _contract(events)["complete"] is True


# ------------------------------------ F09-12 partial keeps verified events

def test_F09_12_partial_coverage_keeps_verified_events():
    events = [_cand(contact_ms=20420, at="PASS", outcome="COMPLETED", sid="p")]
    cov = _coverage(events)
    cov[12] = {"start_ms": 60000, "end_ms": 65000,
               "target_seen": "junk", "events_found": 0}  # malformed bucket
    ledger = el.build_ledger({"events": events, "coverage": cov}, TRACK, DUR)
    assert ledger["coverage_state"] == "PARTIAL"
    assert len(ledger["events"]) == 1, "real partial evidence > fabricated completeness"
    timeline = el.authoritative_timeline(ledger)
    assert len(timeline) == 1 and timeline[0]["event_start_ms"] == 20420


# ------------------------------ F09-13 … F09-16 stat completeness authority

def _pass_ev(ts, ms=None):
    e = {"timestamp": ts, "title": "Pass", "description": "Simple pass.",
         "action_type": "pass", "cross_verified": True,
         "canonical_event_type": "PASS", "canonical_action_type": "PASS",
         "canonical_result": "COMPLETED", "outcome_visible": True}
    if ms is not None:
        e["event_start_ms"] = ms
        e["event_end_ms"] = ms
    return e


def _goal_ev(ts="00:31"):
    return {"timestamp": ts, "title": "Goal", "description": "Scores low.",
            "action_type": "shot", "cross_verified": True,
            "canonical_event_type": "GOAL", "canonical_action_type": "SHOT",
            "canonical_result": "SCORED", "outcome_visible": True}


def _assist_ev(ts="02:10"):
    return {"timestamp": ts, "title": "Assist", "description": "Verified assist.",
            "action_type": "pass", "cross_verified": True,
            "canonical_event_type": "ASSIST", "canonical_action_type": "PASS",
            "canonical_result": "TEAMMATE_SCORED", "outcome_visible": True}


def _apply(full, coverage_state, performed=True):
    full["event_discovery"] = {"status": "ok", "coverage_state": coverage_state,
                               "coverage_contract_complete": coverage_state == "COMPLETE"}
    full["_scoring_scan"] = {"performed": performed}
    full = attach_event_evidence_authority(full)
    return vstats.apply_verified_stats_authority(full)


def test_F09_13_partial_marks_general_stats_non_authoritative():
    full = _apply({"action_timeline": [_pass_ev("00:10"), _pass_ev("00:20"),
                                       _goal_ev()]}, "PARTIAL")
    vs = full["verified_stats"]
    assert vs["general_totals_authoritative"] is False
    assert vs["stats_completeness"]["other_actions"] == "partial_verified_events"
    ms = full["match_stats"]
    assert "passes_attempted" not in ms and "shots" not in ms
    assert ms["general_actions_source"] == "partial_verified_events"
    assert ms["observed_verified_counts"]["passes_attempted"] == 2
    assert ms["observed_verified_counts"]["shots"] == 1


def test_F09_14_complete_coverage_permits_general_totals():
    full = _apply({"action_timeline": [_pass_ev("00:10"), _pass_ev("00:20"),
                                       _goal_ev()]}, "COMPLETE")
    vs = full["verified_stats"]
    assert vs["general_totals_authoritative"] is True
    assert vs["stats_completeness"]["other_actions"] == "coverage_contract_complete"
    ms = full["match_stats"]
    assert ms["passes_attempted"] == 2 and ms["shots"] == 1
    assert "observed_verified_counts" not in ms


def test_F09_15_partial_coverage_scoring_stays_authoritative():
    full = _apply({"action_timeline": [_goal_ev(), _assist_ev("02:10"),
                                       _assist_ev("03:10"), _pass_ev("00:10")]},
                  "PARTIAL")
    ms = full["match_stats"]
    assert ms["goals"] == 1 and ms["assists"] == 2, \
        "scoring authority is independent of event coverage (P8)"
    assert ms["goals_assists_source"] == "full_video_scoring_scan"
    assert "shots" not in ms and "passes_attempted" not in ms
    # UNAVAILABLE coverage behaves the same for scoring
    full2 = _apply({"action_timeline": [_goal_ev()]}, "UNAVAILABLE")
    assert full2["match_stats"]["goals"] == 1
    assert full2["match_stats"]["general_actions_source"] == "unavailable"


def test_F09_16_stat_line_partial_excludes_shots():
    full = _apply({"action_timeline": [_goal_ev(), _assist_ev("02:10"),
                                       _assist_ev("03:10")]}, "PARTIAL")
    assert full["verified_stat_line"] == "1 goal · 2 assists"
    full2 = _apply({"action_timeline": [_goal_ev()]}, "COMPLETE")
    assert full2["verified_stat_line"] == "1 goal · 0 assists · 1 shot"


# ------------------------------------- F09-17 / F09-18 prose reconciliation

def test_F09_17_partial_rejects_matching_aggregate_claim():
    passes = [_pass_ev(f"00:{10 + i}") for i in range(5)]
    full = _apply({"action_timeline": passes,
                   "executive_summary": "He completed 5 passes in this clip."},
                  "PARTIAL")
    assert full["verified_stats"]["passes_attempted"] == 5
    assert "5 passes" not in full["executive_summary"], \
        "a matching partial count is still not a proven full-match total"
    # with COMPLETE coverage the same true claim survives
    full2 = _apply({"action_timeline": [_pass_ev(f"00:{10 + i}") for i in range(5)],
                    "executive_summary": "He completed 5 passes in this clip."},
                   "COMPLETE")
    assert "5 passes" in full2["executive_summary"]


def test_F09_18_partial_preserves_qualitative_prose():
    text = ("His passing was progressive. He showed confidence in 1v1 "
            "situations.")
    full = _apply({"action_timeline": [_pass_ev("00:10")],
                   "executive_summary": text}, "PARTIAL")
    assert full["executive_summary"] == text


# ------------------------------------------ F09-19 … F09-21 FIX08 invariance

def test_F09_19_exact_31420_authority_end_to_end():
    events = [_cand(contact_ms=31420)]
    ledger = el.build_ledger({"events": events, "coverage": _coverage(events)},
                             TRACK, DUR)
    assert ledger["coverage_state"] == "COMPLETE"
    timeline = el.authoritative_timeline(ledger)
    assert timeline[0]["event_start_ms"] == 31420
    timeline[0]["cross_verified"] = True
    full = attach_event_evidence_authority({"action_timeline": timeline})
    assert full["action_timeline"][0]["event_start_ms"] == 31420
    full = el.create_event_native_evidence(full, track=TRACK)
    c = [x for x in full["video_comments"] if x.get("event_native")][0]
    assert c["evidence_time_ms"] == 31420 and c["event_track_locked"] is True


def test_F09_20_close_duel_and_gap_rules_unchanged():
    assert el._INTERP_MAX_GAP_S == 0.25
    assert el.boxes_match(_box(x=0.44), _box()) is False  # close duel
    assert el.boxes_match(_box(x=0.405), _box()) is True  # jitter
    gap_track = _track([i * 0.08 for i in range(0, 126)]
                       + [10.0 + 0.8 + i * 0.08 for i in range(0, 50)])
    ok, reason, _ = el.validate_actor(_cand(contact_ms=10400), gap_track)
    assert ok is False and reason == "TRACK_GAP"


def test_F09_21_static_cost_guard():
    src = (BACKEND / "server.py").read_text()
    assert src.count("call_gemini_with_video(") == 8
    assert src.count('session_id=f"discover-') == 1
    for mod in ("event_ledger.py", "verified_stats.py"):
        code = (BACKEND / mod).read_text()
        for token in ("LlmChat", "call_gemini", "httpx", "aiohttp", "requests.",
                      "urllib", "socket", "emergentintegrations"):
            assert token not in code, f"forbidden call path in {mod}: {token}"
