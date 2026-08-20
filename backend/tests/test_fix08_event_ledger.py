"""FIX 08 — PLAYER EVENT LEDGER + EVENT-NATIVE EVIDENCE (E01–E25 + integration).

Deterministic only: synthetic discovery dicts, synthetic FIX04 tracks, no live
model/network calls. The ledger's spatial actor gate, goal/assist chains,
coverage contract, timestamped claim reconciliation, event-native evidence and
snapshot authority are exercised directly against the real logic.
"""
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

import event_ledger as el  # noqa: E402
import verified_stats as vstats  # noqa: E402
from evidence_authority import (  # noqa: E402
    attach_event_evidence_authority,
    apply_fail_closed_proof_authority,
    compute_proof_frame_verified,
)

DUR = 76.8


def _track(times, x=0.40, y=0.30, w=0.06, h=0.18):
    return {"points": [{"t": float(t), "x": x, "y": y, "w": w, "h": h, "conf": 0.9}
                       for t in times]}


TRACK = _track([i * 0.5 for i in range(0, 160)])  # 0.0s … 79.5s every 0.5 s


def _box(x=0.40, y=0.30, w=0.06, h=0.18):
    return {"x": x, "y": y, "w": w, "h": h}


def _cand(contact_ms=31500, at="SHOT", outcome="SCORED", vis=True, box=None,
          chain=None, sid="s1", description="Factual action.", **kw):
    c = {"sequence_id": sid, "start_ms": max(0, contact_ms - 2000),
         "contact_ms": contact_ms, "end_ms": contact_ms + 1500,
         "action_type": at, "foot": "RIGHT",
         "actor_box": box if box is not None else _box(),
         "outcome": outcome, "outcome_visible": vis,
         "scoring_chain": chain, "description": description}
    c.update(kw)
    return c


def _chain(contact_ms, shot=True, goal=True, cont=True):
    return {"pass_contact_ms": contact_ms,
            "teammate_receive_ms": contact_ms + 800,
            "teammate_shot_ms": (contact_ms + 1600) if shot else None,
            "goal_outcome_ms": (contact_ms + 2100) if goal else None,
            "continuous_causal_sequence": cont}


def _coverage(duration_s=DUR):
    return [{"start_ms": b[0], "end_ms": b[1], "target_seen": True, "events_found": 0}
            for b in el.build_coverage_buckets(duration_s)]


def _discovery(events, duration_s=DUR, coverage=None):
    return {"events": events,
            "coverage": coverage if coverage is not None else _coverage(duration_s)}


# ------------------------------------------ E01–E05 spatial actor validation

def test_E01_matching_actor_box_verified():
    ok, reason, contact = el.validate_actor(_cand(), TRACK)
    assert ok is True and reason == "ACTOR_MATCH" and contact == 31500


def test_E02_different_nearby_player_dropped():
    ok, reason, _ = el.validate_actor(_cand(box=_box(x=0.70)), TRACK)
    assert ok is False and reason == "ACTOR_MISMATCH"
    ledger = el.build_ledger(_discovery([_cand(box=_box(x=0.70))]), TRACK, DUR)
    assert ledger["events"] == []
    assert ledger["dropped"][0]["reason"] == "ACTOR_MISMATCH"


def test_E03_nearby_in_time_but_track_gap_at_contact_drops():
    # target existed 20–29.5s and 40–49.5s (within ±8 s of 31.5s) but NOT at contact
    gap_track = _track([20 + i * 0.5 for i in range(20)] + [40 + i * 0.5 for i in range(20)])
    ok, reason, _ = el.validate_actor(_cand(contact_ms=31500), gap_track)
    assert ok is False and reason == "TRACK_GAP", "±8s presence must NOT be actor authority"
    ledger = el.build_ledger(_discovery([_cand(contact_ms=31500)]), gap_track, DUR)
    assert ledger["events"] == []


def test_E04_missing_or_invalid_actor_box_fails_closed():
    for bad in (None, {}, {"x": 0.4}, _box(w=0.0), _box(x=1.5), "box"):
        c = _cand()
        c["actor_box"] = bad
        ok, reason, _ = el.validate_actor(c, TRACK)
        assert ok is False and reason == "INVALID_ACTOR_BOX", f"accepted: {bad}"


def test_E05_track_unavailable_no_false_confirmation():
    tiny = _track([1.0, 2.0, 3.0])  # < 10 points → not usable
    ok, reason, _ = el.validate_actor(_cand(), tiny)
    assert ok is False and reason == "NO_TARGET_TRACK"
    ledger = el.build_ledger(_discovery([_cand()]), tiny, DUR)
    assert ledger["events"] == [] and ledger["track_usable"] is False


# ------------------------------------------------ E06–E10 goal/assist chains

def test_E06_goal_requires_full_visible_chain():
    et, at, res, vis = el.classify_candidate(_cand())
    assert (et, at, res, vis) == ("GOAL", "SHOT", "SCORED", True)
    ledger = el.build_ledger(_discovery([_cand()]), TRACK, DUR)
    assert ledger["events"][0]["canonical_event_type"] == "GOAL"
    assert ledger["events"][0]["actor_spatial_verified"] is True


def test_E07_scored_but_outcome_not_visible_no_goal():
    et, at, res, vis = el.classify_candidate(_cand(vis=False))
    assert et == "SHOT" and res == "OUTCOME_NOT_VISIBLE" and vis is False


def test_E08_assist_requires_continuous_chain():
    good = _cand(contact_ms=10000, at="PASS", outcome="TEAMMATE_SCORED",
                 chain=_chain(10000))
    et, at, res, vis = el.classify_candidate(good)
    assert (et, at, res, vis) == ("ASSIST", "PASS", "TEAMMATE_SCORED", True)
    no_chain = _cand(contact_ms=10000, at="PASS", outcome="TEAMMATE_SCORED", chain=None)
    et, *_ = el.classify_candidate(no_chain)
    assert et != "ASSIST", "an ASSIST without the visible causal chain is not allowed"
    broken = _cand(contact_ms=10000, at="PASS", outcome="TEAMMATE_SCORED",
                   chain=_chain(10000, cont=False))
    et, *_ = el.classify_candidate(broken)
    assert et != "ASSIST"


def test_E09_teammate_shot_no_goal_is_key_pass():
    c = _cand(contact_ms=10000, at="PASS", outcome="TEAMMATE_SHOT",
              chain=_chain(10000, goal=False))
    et, at, res, vis = el.classify_candidate(c)
    assert (et, res) == ("KEY_PASS", "TEAMMATE_SHOT")


def test_E10_goal_outcome_not_visible_no_assist():
    c = _cand(contact_ms=10000, at="PASS", outcome="TEAMMATE_SCORED",
              vis=False, chain=_chain(10000))
    et, at, res, vis = el.classify_candidate(c)
    assert et != "ASSIST" and vis is False


# ------------------------------------------------ E11–E13 coverage contract

def test_E11_complete_coverage_buckets():
    buckets = el.build_coverage_buckets(DUR)
    assert len(buckets) == 16 and buckets[0] == (0, 5000) and buckets[-1] == (75000, 76800)
    ledger = el.build_ledger(_discovery([_cand()]), TRACK, DUR)
    assert ledger["discovery_complete"] is True


def test_E12_missing_bucket_incomplete():
    cov = _coverage()[:-1]
    ledger = el.build_ledger(_discovery([_cand()], coverage=cov), TRACK, DUR)
    assert ledger["discovery_complete"] is False, "missing bucket cannot be exhaustive"
    for bad_cov in (None, "junk", [{"start_ms": 0}], _coverage() + [{"bad": 1}]):
        lg = el.build_ledger({"events": [], "coverage": bad_cov}, TRACK, DUR)
        assert lg["discovery_complete"] is False


def test_E13_no_6_to_15_truncation():
    cands = [_cand(contact_ms=2000 + i * 3000, at="PASS", outcome="COMPLETED",
                   sid=f"s{i}") for i in range(20)]
    ledger = el.build_ledger(_discovery(cands), TRACK, DUR)
    assert len(ledger["events"]) == 20, "old 6-15 cap must not truncate the ledger"
    assert len(el.project_to_timeline(ledger)) == 20
    import server
    assert "6-15" not in server.FULL_REPORT_PROMPT


# ------------------------------- E14–E17 timestamped outcome claim authority

def _goal_event(ts="00:31", **kw):
    return {"timestamp": ts, "title": "Goal", "description": "Scores low into the corner.",
            "action_type": "shot", "cross_verified": True,
            "canonical_event_type": "GOAL", "canonical_action_type": "SHOT",
            "canonical_result": "SCORED", "outcome_visible": True, **kw}


def _assist_event(ts="02:10", **kw):
    return {"timestamp": ts, "title": "Assist", "description": "Verified assist.",
            "action_type": "pass", "cross_verified": True,
            "canonical_event_type": "ASSIST", "canonical_action_type": "PASS",
            "canonical_result": "TEAMMATE_SCORED", "outcome_visible": True, **kw}


def _recon(full):
    full.setdefault("_scoring_scan", {"performed": True})
    full = attach_event_evidence_authority(full)
    return vstats.apply_verified_stats_authority(full)


def test_E14_timestamped_goal_claim_without_goal_removed():
    full = _recon({"action_timeline": [_goal_event("00:31")],
                   "executive_summary":
                       "Strong pressing game. The goal he scored at 01:15 was superb."})
    low = full["executive_summary"].lower()
    assert "01:15" not in low, "false timestamped goal claim survived"
    assert "strong pressing game" in low, "unrelated prose must remain"


def test_E15_timestamped_assist_claim_without_assist_removed():
    full = _recon({"action_timeline": [_assist_event("02:10")],
                   "parent_summary": {"headline": "He assisted the winner at 03:20."}})
    assert "03:20" not in str(full["parent_summary"])


def test_E16_exact_verified_goal_timestamp_allowed():
    text = "He scores at 00:31 with his right foot."
    full = _recon({"action_timeline": [_goal_event("00:31")],
                   "executive_summary": text})
    assert full["executive_summary"] == text


def test_E17_exact_verified_assist_timestamp_allowed():
    text = "His assist at 02:10 changed the game."
    full = _recon({"action_timeline": [_assist_event("02:10")],
                   "executive_summary": text})
    assert full["executive_summary"] == text


# ----------------------------------------- E18–E20 event-native evidence

def _authority_chain(full):
    """Same order as the server pipeline: FIX01 → event-native → FIX01 → FIX07 → FIX02."""
    full.setdefault("_scoring_scan", {"performed": True})
    full = attach_event_evidence_authority(full)
    full = el.create_event_native_evidence(full)
    full = attach_event_evidence_authority(full)
    full = vstats.apply_verified_stats_authority(full)
    full = apply_fail_closed_proof_authority(full)
    return full


def test_E18_event_native_evidence_exact_event_id():
    full = _authority_chain({"action_timeline": [_goal_event("00:31")]})
    ev = full["action_timeline"][0]
    rows = [c for c in full["video_comments"] if c.get("event_native")]
    assert len(rows) == 1
    c = rows[0]
    assert c["event_id"] == ev["event_id"], "must bind the EXACT event id"
    assert c["evidence_time_ms"] == ev["event_start_ms"] == 31000
    assert c["evidence_id"], "FIX01 must assign the normal evidence id"
    assert c["proof_verified"] is True
    # already-bound events never get a duplicate row
    again = el.create_event_native_evidence(full)
    assert len([c for c in again["video_comments"] if c.get("event_native")]) == 1


def test_E19_event_frame_exact_canonical_time():
    full = _authority_chain({"action_timeline": [_goal_event("00:31")]})
    c = [x for x in full["video_comments"] if x.get("event_native")][0]
    c["frame_url"] = "/api/uploads/frames/f.jpg"
    c["identity_verified"] = True
    c["frame_time_ms"] = c["evidence_time_ms"]
    assert compute_proof_frame_verified(c) is True
    c["frame_time_ms"] = c["evidence_time_ms"] + 40  # nearby ≠ exact
    assert compute_proof_frame_verified(c) is False


def test_E20_no_safe_frame_no_proof_image():
    full = _authority_chain({"action_timeline": [_goal_event("00:31")]})
    c = [x for x in full["video_comments"] if x.get("event_native")][0]
    c["frame_url"] = None
    c["proof_frame_verified"] = compute_proof_frame_verified(c)
    assert c["proof_frame_verified"] is False
    moments = el.build_snapshot_moments(full)
    assert moments == [], "no exact verified frame → no snapshot card"
    assert full["snapshot_moments_authority"] is True


# ----------------------------------------- E21–E22 snapshot authority

def _framed(full, comment):
    comment["frame_url"] = "/api/uploads/frames/x.jpg"
    comment["identity_verified"] = True
    comment["frame_time_ms"] = comment["evidence_time_ms"]
    comment["proof_frame_verified"] = compute_proof_frame_verified(comment)
    assert comment["proof_frame_verified"] is True
    return comment


def test_E21_goal_assist_prioritized_for_snapshot():
    pass_ev = {"timestamp": "00:10", "title": "Pass", "description": "Simple pass.",
               "action_type": "pass", "cross_verified": True,
               "canonical_event_type": "PASS", "canonical_action_type": "PASS",
               "canonical_result": "COMPLETED", "outcome_visible": True}
    full = _authority_chain({"action_timeline": [pass_ev, _goal_event("00:31"),
                                                 _assist_event("02:10")]})
    for c in full["video_comments"]:
        _framed(full, c)
    moments = el.build_snapshot_moments(full)
    assert len(moments) == 3
    ids = {e["event_id"]: e for e in full["action_timeline"]}
    assert ids[moments[0]["event_id"]]["canonical_event_type"] == "GOAL"
    assert ids[moments[1]["event_id"]]["canonical_event_type"] == "ASSIST"
    assert moments[0]["frame_url"] and moments[0]["evidence_id"]


def test_E22_two_real_frames_only_two_moments():
    evs = [_goal_event("00:31"), _assist_event("02:10")]
    for i in range(3):
        evs.append({"timestamp": f"00:{40 + i}", "title": "Pass", "description": "Pass.",
                    "action_type": "pass", "cross_verified": True,
                    "canonical_event_type": "PASS", "canonical_action_type": "PASS",
                    "canonical_result": "COMPLETED", "outcome_visible": True})
    full = _authority_chain({"action_timeline": evs})
    native = [c for c in full["video_comments"] if c.get("event_native")]
    for c in native[:2]:  # only the goal + assist rows get real frames
        _framed(full, c)
    moments = el.build_snapshot_moments(full)
    assert len(moments) == 2, "must not fabricate 4 image moments from 2 real frames"


# --------------------------------------------- E23–E25 authority preservation

def test_E23_fix07_consumes_ledger_events_unchanged():
    cands = [
        _cand(contact_ms=31500, sid="g1", description="Right-foot finish."),
        _cand(contact_ms=10000, at="PASS", outcome="TEAMMATE_SCORED",
              chain=_chain(10000), sid="a1", description="Final pass, teammate scores."),
    ]
    ledger = el.build_ledger(_discovery(cands), TRACK, DUR)
    timeline = el.project_to_timeline(ledger)
    # simulate the EXISTING verifier confirming both claims with canonical fields
    for row, e in zip(timeline, sorted(ledger["events"], key=lambda x: x["contact_ms"])):
        row["cross_verified"] = True
        vstats.attach_canonical(row, {
            "canonical_event_type": e["canonical_event_type"],
            "canonical_action_type": e["canonical_action_type"],
            "canonical_result": e["canonical_result"],
            "outcome_visible": e["outcome_visible"]})
    full = _authority_chain({"action_timeline": timeline})
    vs = full["verified_stats"]
    assert vs["goals"] == 1 and vs["assists"] == 1
    assert full["match_stats"]["goals"] == 1 and full["match_stats"]["assists"] == 1


def test_E24_no_duplicate_after_scoring_scan_promotion():
    ledger = el.build_ledger(
        _discovery([_cand(contact_ms=31000, vis=False, outcome="UNKNOWN")]), TRACK, DUR)
    timeline = el.project_to_timeline(ledger)
    timeline[0]["cross_verified"] = True
    vstats.attach_canonical(timeline[0], {
        "canonical_event_type": "SHOT", "canonical_action_type": "SHOT",
        "canonical_result": "OUTCOME_NOT_VISIBLE", "outcome_visible": False})
    full = {"action_timeline": timeline}
    scan = vstats.merge_discovered_scoring_events(
        full, [{"timestamp": "00:31", "identity": "CONFIRMED",
                "canonical_event_type": "GOAL", "canonical_action_type": "SHOT",
                "canonical_result": "SCORED", "outcome_visible": True,
                "note": "shot crosses the line"}])
    assert len(full["action_timeline"]) == 1, "promotion must not duplicate"
    assert full["action_timeline"][0]["canonical_event_type"] == "GOAL"
    full["_scoring_scan"] = scan
    full = attach_event_evidence_authority(full)
    full = vstats.apply_verified_stats_authority(full)
    assert full["verified_stats"]["goals"] == 1


def test_E25_fix01_ids_exact_deterministic_joins():
    ledger = el.build_ledger(_discovery([_cand()]), TRACK, DUR)
    timeline = el.project_to_timeline(ledger)
    timeline[0]["cross_verified"] = True
    full = attach_event_evidence_authority({"action_timeline": timeline})
    e = full["action_timeline"][0]
    assert e["event_id"].startswith("evt_")
    assert e["event_start_ms"] == 32000  # 31500 ms → "00:32" → exact canonical ms
    eid = e["event_id"]
    full = attach_event_evidence_authority(full)  # idempotent
    assert full["action_timeline"][0]["event_id"] == eid
    full = el.create_event_native_evidence(full)
    full = attach_event_evidence_authority(full)
    c = full["video_comments"][0]
    assert c["event_id"] == eid and c["evidence_time_ms"] == e["event_start_ms"]


# --------------------------------------------------- integration-style pure

def test_integration_pass_teammate_shot_goal_becomes_assist():
    c = _cand(contact_ms=12000, at="CROSS", outcome="TEAMMATE_SCORED",
              chain=_chain(12000), sid="ia", description="Driven cross, teammate scores.")
    ledger = el.build_ledger(_discovery([c]), TRACK, DUR)
    assert ledger["events"][0]["canonical_event_type"] == "ASSIST"
    timeline = el.project_to_timeline(ledger)
    timeline[0]["cross_verified"] = True
    vstats.attach_canonical(timeline[0], {
        "canonical_event_type": "ASSIST", "canonical_action_type": "CROSS",
        "canonical_result": "TEAMMATE_SCORED", "outcome_visible": True})
    full = _authority_chain({"action_timeline": timeline})
    assert full["verified_stats"]["assists"] == 1


def test_integration_other_player_shot_not_credited():
    # ~00:36 — a DIFFERENT player shoots while the tapped player is nearby;
    # the tapped player's own creative pass just before must survive.
    other_shot = _cand(contact_ms=36200, at="SHOT", outcome="BLOCKED",
                       box=_box(x=0.72, y=0.55), sid="wrong")
    target_pass = _cand(contact_ms=34500, at="PASS", outcome="COMPLETED",
                        sid="build", description="Sharp lay-off before the shot.")
    ledger = el.build_ledger(_discovery([other_shot, target_pass]), TRACK, DUR)
    kinds = [e["action_type"] for e in ledger["events"]]
    assert "SHOT" not in kinds, "wrong-actor shot must never enter the target ledger"
    assert kinds == ["PASS"]
    assert any(d["reason"] == "ACTOR_MISMATCH" and d["sequence_id"] == "wrong"
               for d in ledger["dropped"])


# --------------------------------------------------- pipeline cost contract

def test_discovery_prompt_contract():
    p = el.build_discovery_prompt(DUR, {"player_name": "Test", "age": 12, "position": "ST"})
    for token in ("COVERAGE CONTRACT", "actor_box", "contact_ms", "scoring_chain",
                  "bucket 15", "EVENT DISCOVERY ONLY"):
        assert token in p, f"missing discovery contract token: {token}"
    assert "score" not in p.split("EVENT DISCOVERY ONLY")[0].lower()


def test_exactly_one_discovery_call_site():
    src = (BACKEND / "server.py").read_text()
    assert src.count('session_id=f"discover-') == 1, \
        "FIX08 adds EXACTLY ONE dedicated discovery call"
    body = src.split("async def generate_full_report_task", 1)[1].split("\nasync def ", 1)[0]
    assert body.count("call_gemini_with_video(") == 2, \
        "normal pipeline: discovery + full analysis only (verify lives in its own helper)"
    lsrc = (BACKEND / "event_ledger.py").read_text()
    for token in ("LlmChat", "call_gemini", "httpx", "aiohttp", "requests.",
                  "urllib", "socket", "emergentintegrations"):
        assert token not in lsrc, f"forbidden call path in event_ledger.py: {token}"
