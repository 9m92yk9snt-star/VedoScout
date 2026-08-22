"""FIX09B.3 — canonical actor/causal event-resolution tests."""
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

import canonical_event_resolver as cer  # noqa: E402


TB = {"x": .10, "y": .20, "w": .10, "h": .30}
OB = {"x": .55, "y": .20, "w": .10, "h": .30}
RB = {"x": .35, "y": .20, "w": .10, "h": .30}


def player(ms, tid, box, *, target_candidate=False, target_verified=False,
           team=None, team_confidence=None, team_source=None):
    return {
        "media_ms": ms, "scene_id": "scene_001", "local_track_id": tid,
        "box": dict(box), "confidence": .9, "team": team,
        "team_confidence": team_confidence, "team_source": team_source,
        "global_target_candidate": target_candidate,
        "global_target_verified": target_verified,
    }


def frame(ms, *, target="p001", status="VERIFIED", candidates=None,
          p1=TB, p2=OB, p3=RB, include_p3=True, teams=None, holder=None):
    cand = list(candidates if candidates is not None else ([target] if target else []))
    team_map = ({"p001": "target_team", "p002": "opponent", "p003": "target_team"}
                if teams is None else dict(teams))

    def team_kwargs(tid):
        label = team_map.get(tid)
        return {
            "team": label,
            "team_confidence": .95 if label else None,
            "team_source": cer.fsg.TEAM_SOURCE if label else None,
        }

    players = [
        player(ms, "p001", p1, target_candidate="p001" in cand,
               target_verified=status == "VERIFIED" and target == "p001",
               **team_kwargs("p001")),
        player(ms, "p002", p2, target_candidate="p002" in cand,
               target_verified=status == "VERIFIED" and target == "p002",
               **team_kwargs("p002")),
    ]
    if include_p3:
        players.append(player(ms, "p003", p3, target_candidate="p003" in cand,
                              target_verified=status == "VERIFIED" and target == "p003",
                              **team_kwargs("p003")))
    return {
        "media_ms": ms, "scene_id": "scene_001", "players": players,
        "global_target": {
            "status": status, "reason": "test",
            "local_track_id": target if status == "VERIFIED" else None,
            "candidate_local_track_ids": cand,
            "identity_strength": "GLOBAL", "proof_eligible": status == "VERIFIED",
        },
        "ball": None, "ball_state": "MISSING", "ball_candidates": [],
        "possession": {
            "status": "LIKELY" if holder else "NO_BALL",
            "holder_local_track_id": holder,
            "candidate_local_track_ids": [holder] if holder else [],
            "target_relation": (
                "TARGET_LIKELY_POSSESSION" if holder == target
                else "OTHER_PLAYER_POSSESSION_CANDIDATE" if holder
                else "UNKNOWN"
            ),
        },
    }


def graph(frames):
    return {
        "version": 1, "status": "ok", "global_target_id": "GLOBAL_TARGET",
        "timebase": "canonical_media_ms",
        "scenes": [{"scene_id": "scene_001", "start_ms": min(f["media_ms"] for f in frames),
                    "end_ms": max(f["media_ms"] for f in frames)}],
        "frames": list(frames), "player_points": [], "ball_points": [], "metrics": {},
    }


def authority(points=None):
    pts = []
    for ms, box in (points or []):
        pts.append({
            "media_ms": ms, "scene_id": "identity_scene_001",
            "global_target_id": "GLOBAL_TARGET", "box": dict(box),
            "state": "VISIBLE", "identity_strength": "GLOBAL",
            "sources": ["FIX09A"], "primary_source": "FIX09A",
            "predicted": False, "proof_eligible": True, "tap_authority": False,
            "reason": None, "hypotheses": [],
        })
    return {
        "version": 1, "status": "ok" if pts else "empty",
        "global_target_id": "GLOBAL_TARGET", "timebase": "canonical_media_ms",
        "scenes": [{"scene_id": "identity_scene_001", "start_ms": 0, "end_ms": 10000}],
        "target_points": pts, "unresolved_intervals": [], "tap_times_ms": [], "metrics": {},
    }


def action(kind="SHOT", *, aid="a1", start=900, contact=1000, end=1300,
           actor="p001", box=TB, outcome="SAVED", visible=True,
           target_status="VERIFIED", evidence=None, chain=None, duplicate_of=None,
           contact_visibility="VISIBLE"):
    ev = evidence if evidence is not None else [
        {"media_ms": contact if contact is not None else 1000,
         "box": dict(box), "visibility": "VISIBLE"}
    ]
    if chain is None:
        chain = {"target_contact_ms": contact, "receiver_local_track_id": None,
                 "receiver_ms": None, "teammate_shot_ms": None,
                 "goal_outcome_ms": None, "continuous_visible_sequence": False}
    return {
        "action_id": aid, "kind": kind, "start_ms": start, "contact_ms": contact,
        "end_ms": end, "target_status": target_status,
        "actor_local_track_id": actor,
        "actor_candidate_local_track_ids": [actor] if actor else [],
        "actor_box": dict(box) if box else None,
        "actor_evidence": ev,
        "evidence_ms": sorted({e["media_ms"] for e in ev}),
        "foot": "RIGHT", "pressure": {"level": "MEDIUM", "nearby_players": 1},
        "details": ["visible action detail"], "outcome": outcome,
        "outcome_visible": visible, "causal_chain": chain,
        "contact_visibility": contact_visibility, "duplicate_of": duplicate_of,
    }


def analysis(actions, *, seq="seq_1", start=0, end=5000):
    return {
        "version": 1, "status": "ok", "global_target_id": "GLOBAL_TARGET",
        "timebase": "canonical_media_ms",
        "sequences": [{"sequence_id": seq, "scene_id": "scene_001",
                       "start_ms": start, "end_ms": end, "summary": "",
                       "actions": list(actions)}],
        "coverage": [{"sequence_id": seq, "reviewed": True,
                      "target_seen": True, "actions_found": len(actions)}],
        "coverage_complete": True, "metrics": {},
    }


def standard_graph():
    return graph([
        frame(ms, holder="p001" if ms == 1000 else "p003" if ms == 1500 else None)
        for ms in (500, 750, 1000, 1250, 1500, 2000, 2500, 3000)
    ])


def test_b301_visible_actor_matching_verified_global_target_becomes_canonical_event():
    out = cer.resolve_canonical_events(analysis([action()]), standard_graph(), authority())
    assert len(out["events"]) == 1
    e = out["events"][0]
    assert e["canonical_event_type"] == "SHOT"
    assert e["actor_local_track_id"] == "p001"
    assert e["identity_resolution"] == "VISIBLE_TARGET_MATCH"


def test_b302_visible_other_player_action_is_rejected_not_attributed_to_target():
    wrong = action(actor="p002", box=OB)
    out = cer.resolve_canonical_events(analysis([wrong]), standard_graph(), authority())
    assert out["events"] == []
    assert out["rejected"][0]["reason"] == "OTHER_PLAYER_VISIBLE_AT_ACTION"


def test_b303_model_wrong_actor_id_cannot_override_visible_target_geometry():
    # Model says p002 but its actor box/evidence is physically p001.
    a = action(actor="p002", box=TB)
    out = cer.resolve_canonical_events(analysis([a]), standard_graph(), authority())
    assert len(out["events"]) == 1
    assert out["events"][0]["actor_local_track_id"] == "p001"


def test_b304_hypothesis_at_contact_can_resolve_from_same_track_before_and_after():
    frames = [
        frame(500, target="p001", status="VERIFIED"),
        frame(750, target="p001", status="VERIFIED"),
        frame(1000, target=None, status="HYPOTHESES", candidates=["p001", "p002"]),
        frame(1250, target="p001", status="VERIFIED"),
        frame(1500, target="p001", status="VERIFIED"),
    ]
    ev = [{"media_ms": 900, "box": dict(TB), "visibility": "VISIBLE"},
          {"media_ms": 1100, "box": dict(TB), "visibility": "VISIBLE"}]
    a = action(start=850, contact=1000, end=1150, actor="p001", box=None,
               evidence=ev, target_status="HYPOTHESES", contact_visibility="OCCLUDED")
    out = cer.resolve_canonical_events(analysis([a]), graph(frames), authority())
    assert len(out["events"]) == 1
    assert out["events"][0]["identity_resolution"] == "BOUNDED_FORWARD_BACKWARD_CONTINUITY"
    assert out["events"][0]["proof"]["contact_geometry"] is None


def test_b305_ambiguous_contact_without_physical_resolution_stays_unresolved():
    frames = [frame(1000, target=None, status="HYPOTHESES", candidates=["p001", "p002"])]
    a = action(actor=None, box=None, target_status="HYPOTHESES",
               evidence=[], contact_visibility="OCCLUDED")
    out = cer.resolve_canonical_events(analysis([a]), graph(frames), authority())
    assert out["events"] == []
    assert len(out["unresolved"]) == 1


def test_b306_verified_target_switch_inside_bridge_blocks_continuity_resolution():
    frames = [
        frame(500, target="p001", status="VERIFIED"),
        frame(750, target="p002", status="VERIFIED"),
        frame(1000, target=None, status="HYPOTHESES", candidates=["p001", "p002"]),
        frame(1250, target="p001", status="VERIFIED"),
    ]
    a = action(start=850, contact=1000, end=1100, actor="p001", box=None,
               evidence=[], target_status="HYPOTHESES", contact_visibility="OCCLUDED")
    out = cer.resolve_canonical_events(analysis([a]), graph(frames), authority())
    assert out["events"] == []
    assert out["unresolved"], "competing target verification must block identity bridge"


def test_b307_visible_goal_requires_target_shot_and_complete_visible_chain():
    chain = {"target_contact_ms": 1000, "receiver_local_track_id": None,
             "receiver_ms": None, "teammate_shot_ms": None,
             "goal_outcome_ms": 1400, "continuous_visible_sequence": True}
    a = action(kind="SHOT", end=1500, outcome="GOAL", visible=True, chain=chain)
    out = cer.resolve_canonical_events(analysis([a]), standard_graph(), authority())
    assert out["events"][0]["canonical_event_type"] == "GOAL"
    assert out["metrics"]["goals"] == 1


def test_b308_incomplete_goal_claim_downgrades_to_shot_instead_of_deleting_action():
    chain = {"target_contact_ms": 1000, "receiver_local_track_id": None,
             "receiver_ms": None, "teammate_shot_ms": None,
             "goal_outcome_ms": None, "continuous_visible_sequence": False}
    a = action(kind="SHOT", outcome="GOAL", visible=True, chain=chain)
    out = cer.resolve_canonical_events(analysis([a]), standard_graph(), authority())
    e = out["events"][0]
    assert e["canonical_event_type"] == "SHOT"
    assert e["canonical_outcome"] == "UNKNOWN"


def test_b309_complete_pass_receive_shot_goal_chain_becomes_assist():
    chain = {"target_contact_ms": 1000, "receiver_local_track_id": "p003",
             "receiver_ms": 1500, "teammate_shot_ms": 2200,
             "goal_outcome_ms": 2500, "continuous_visible_sequence": True}
    a = action(kind="PASS", end=2700, outcome="TEAMMATE_GOAL", visible=True, chain=chain)
    out = cer.resolve_canonical_events(analysis([a]), standard_graph(), authority())
    e = out["events"][0]
    assert e["canonical_event_type"] == "ASSIST"
    assert e["canonical_action_type"] == "PASS"
    assert e["receiver_team_resolution"]["status"] == "VERIFIED"
    assert e["proof"]["receiver_team_evidence"]["status"] == "VERIFIED"
    assert out["metrics"]["assists"] == 1


def test_b310_missing_assist_chain_downgrades_to_pass():
    chain = {"target_contact_ms": 1000, "receiver_local_track_id": "p003",
             "receiver_ms": 1500, "teammate_shot_ms": None,
             "goal_outcome_ms": None, "continuous_visible_sequence": True}
    a = action(kind="PASS", end=2000, outcome="TEAMMATE_GOAL", visible=True, chain=chain)
    out = cer.resolve_canonical_events(analysis([a]), standard_graph(), authority())
    e = out["events"][0]
    assert e["canonical_event_type"] == "PASS"
    assert e["canonical_outcome"] == "UNKNOWN"


def test_b311_saved_shot_remains_shot_with_visible_outcome():
    out = cer.resolve_canonical_events(analysis([action(outcome="SAVED")]), standard_graph(), authority())
    e = out["events"][0]
    assert e["canonical_event_type"] == "SHOT" and e["canonical_outcome"] == "SAVED"
    assert out["metrics"]["shots"] == 1


def test_b312_micro_action_is_preserved_when_target_identity_is_verified():
    a = action(kind="FEINT", contact=None, start=900, end=1200,
               outcome="UNKNOWN", visible=False,
               evidence=[{"media_ms": 1000, "box": dict(TB), "visibility": "VISIBLE"}])
    out = cer.resolve_canonical_events(analysis([a]), standard_graph(), authority())
    assert out["events"][0]["canonical_event_type"] == "FEINT"


def test_b313_explicit_replay_duplicate_never_enters_canonical_events():
    a = action(duplicate_of="a0")
    out = cer.resolve_canonical_events(analysis([a]), standard_graph(), authority())
    assert out["events"] == []
    assert out["rejected"][0]["reason"] == "EXPLICIT_REPLAY_OR_DUPLICATE"


def test_b314_overlapping_windows_same_real_contact_are_deduped():
    a1 = action(aid="a1", contact=1000)
    a2 = action(aid="a2", start=920, contact=1020, end=1320)
    sa = {
        "sequences": [
            {"sequence_id": "seq_a", "scene_id": "scene_001", "start_ms": 0, "end_ms": 2500,
             "actions": [a1]},
            {"sequence_id": "seq_b", "scene_id": "scene_001", "start_ms": 500, "end_ms": 3000,
             "actions": [a2]},
        ]
    }
    out = cer.resolve_canonical_events(sa, standard_graph(), authority())
    assert len(out["events"]) == 1
    assert set(out["events"][0]["source_action_ids"]) == {"a1", "a2"}
    assert any(r["reason"] == "OVERLAPPING_WINDOW_DUPLICATE" for r in out["rejected"])


def test_b315_occluded_contact_never_gets_fabricated_contact_geometry():
    ev = [{"media_ms": 900, "box": dict(TB), "visibility": "VISIBLE"},
          {"media_ms": 1100, "box": dict(TB), "visibility": "VISIBLE"}]
    a = action(start=850, contact=1000, end=1150, actor="p001", box=None,
               evidence=ev, contact_visibility="OCCLUDED")
    out = cer.resolve_canonical_events(analysis([a]), standard_graph(), authority())
    assert out["events"][0]["proof"]["contact_geometry"] is None
    assert len(out["events"][0]["proof"]["actor_keyframes"]) >= 2


def test_b316_unified_identity_geometry_can_resolve_when_scene_graph_has_no_target_mapping():
    frames = [frame(1000, target=None, status="UNRESOLVED", candidates=[])]
    a = action(actor=None, box=TB, target_status="UNRESOLVED")
    out = cer.resolve_canonical_events(analysis([a]), graph(frames), authority([(1000, TB)]))
    assert len(out["events"]) == 1
    assert out["events"][0]["identity_resolution"] == "UNIFIED_TARGET_GEOMETRY_MATCH"


def test_b317_unified_identity_geometry_mismatch_rejects_visible_wrong_body():
    frames = [frame(1000, target=None, status="UNRESOLVED", candidates=[])]
    a = action(actor=None, box=OB, target_status="UNRESOLVED")
    out = cer.resolve_canonical_events(analysis([a]), graph(frames), authority([(1000, TB)]))
    assert out["events"] == []
    assert out["rejected"][0]["reason"] == "UNIFIED_TARGET_GEOMETRY_MISMATCH"


def test_b318_event_ids_are_stable_for_same_scene_action_time_and_actor():
    a = action()
    one = cer.resolve_canonical_events(analysis([a]), standard_graph(), authority())
    two = cer.resolve_canonical_events(analysis([a]), standard_graph(), authority())
    assert one["events"][0]["event_id"] == two["events"][0]["event_id"]


def test_b319_pass_outcome_is_unknown_when_outcome_is_not_visible():
    a = action(kind="PASS", outcome="COMPLETED", visible=False)
    out = cer.resolve_canonical_events(analysis([a]), standard_graph(), authority())
    e = out["events"][0]
    assert e["canonical_event_type"] == "PASS"
    assert e["canonical_outcome"] == "UNKNOWN"
    assert e["causal_verified"] is False


def test_b320_micro_outcome_is_unknown_when_outcome_is_not_visible():
    a = action(kind="DUEL", outcome="WON", visible=False)
    out = cer.resolve_canonical_events(analysis([a]), standard_graph(), authority())
    assert out["events"][0]["canonical_outcome"] == "UNKNOWN"


def test_b321_conflicting_visible_actor_samples_never_verify_from_one_good_frame():
    frames = [
        frame(1000, target="p001", status="VERIFIED"),
        frame(1100, target="p002", status="VERIFIED"),
    ]
    ev = [
        {"media_ms": 1000, "box": dict(TB), "visibility": "VISIBLE"},
        {"media_ms": 1100, "box": dict(TB), "visibility": "VISIBLE"},
    ]
    a = action(start=1000, contact=1000, end=1100, actor="p001",
               box=TB, evidence=ev)
    out = cer.resolve_canonical_events(
        analysis([a]), graph(frames), authority([(1000, TB), (1100, OB)]))
    assert out["events"] == []
    assert out["rejected"][0]["reason"] == "INCONSISTENT_ACTOR_EVIDENCE"


def test_b322_goal_chain_contact_must_equal_canonical_action_contact():
    chain = {"target_contact_ms": 1050, "receiver_local_track_id": None,
             "receiver_ms": None, "teammate_shot_ms": None,
             "goal_outcome_ms": 1400, "continuous_visible_sequence": True}
    a = action(kind="SHOT", contact=1000, end=1500,
               outcome="GOAL", visible=True, chain=chain)
    out = cer.resolve_canonical_events(analysis([a]), standard_graph(), authority())
    assert out["events"][0]["canonical_event_type"] == "SHOT"
    assert out["events"][0]["canonical_outcome"] == "UNKNOWN"


def test_b323_assist_chain_must_be_ordered_inside_the_action_interval():
    chain = {"target_contact_ms": 1000, "receiver_local_track_id": "p003",
             "receiver_ms": 1500, "teammate_shot_ms": 2200,
             "goal_outcome_ms": 2600, "continuous_visible_sequence": True}
    a = action(kind="PASS", contact=1000, end=2400,
               outcome="TEAMMATE_GOAL", visible=True, chain=chain)
    out = cer.resolve_canonical_events(analysis([a]), standard_graph(), authority())
    assert out["events"][0]["canonical_event_type"] == "PASS"
    assert out["events"][0]["canonical_outcome"] == "UNKNOWN"


def test_b324_interpolated_identity_geometry_cannot_directly_verify_actor():
    frames = [frame(1000, target=None, status="UNRESOLVED", candidates=[])]
    a = action(actor=None, box=TB, target_status="UNRESOLVED")
    # No exact identity observation at the action time.  A midpoint could be
    # geometrically interpolated from these two points, but interpolation is
    # continuity evidence and must not become actor proof.
    auth = authority([(900, TB), (1100, TB)])
    out = cer.resolve_canonical_events(analysis([a]), graph(frames), auth)
    assert out["events"] == []
    assert out["unresolved"][0]["reason"] == "INSUFFICIENT_PHYSICAL_IDENTITY_EVIDENCE"


def _assist_action():
    chain = {"target_contact_ms": 1000, "receiver_local_track_id": "p003",
             "receiver_ms": 1500, "teammate_shot_ms": 2200,
             "goal_outcome_ms": 2500, "continuous_visible_sequence": True}
    return action(kind="PASS", end=2700, outcome="TEAMMATE_GOAL",
                  visible=True, chain=chain)


def test_b325_opponent_receiver_cannot_be_promoted_to_assist():
    frames = [frame(ms, teams={"p001": "target_team", "p002": "opponent",
                               "p003": "opponent"},
                    holder="p001" if ms == 1000 else "p003" if ms == 1500 else None)
              for ms in (500, 750, 1000, 1250, 1500, 2000, 2500, 3000)]
    out = cer.resolve_canonical_events(analysis([_assist_action()]), graph(frames), authority())
    event = out["events"][0]
    assert event["canonical_event_type"] == "PASS"
    assert event["canonical_outcome"] == "UNKNOWN"
    assert event["resolution_reason"] == "ASSIST_RECEIVER_NOT_TEAMMATE"
    assert event["receiver_team_resolution"]["status"] == "REJECTED"
    assert out["metrics"]["assists"] == 0


def test_b326_unknown_receiver_team_downgrades_to_pass_without_deleting_action():
    frames = [frame(ms, teams={"p001": "target_team", "p002": "opponent"},
                    holder="p001" if ms == 1000 else "p003" if ms == 1500 else None)
              for ms in (500, 750, 1000, 1250, 1500, 2000, 2500, 3000)]
    out = cer.resolve_canonical_events(analysis([_assist_action()]), graph(frames), authority())
    event = out["events"][0]
    assert event["canonical_event_type"] == "PASS"
    assert event["resolution_reason"] == "ASSIST_RECEIVER_TEAM_UNRESOLVED"
    assert event["receiver_team_resolution"]["status"] == "UNRESOLVED"
    assert out["metrics"]["assists"] == 0


def test_b327_conflicting_receiver_team_samples_fail_closed():
    frames = [frame(ms, holder="p001" if ms == 1000 else "p003" if ms == 1500 else None)
              for ms in (500, 750, 1000, 1250, 1500, 2000, 2500, 3000)]
    for fr in frames:
        if fr["media_ms"] == 1500:
            receiver = next(p for p in fr["players"] if p["local_track_id"] == "p003")
            receiver["team"] = "opponent"
    out = cer.resolve_canonical_events(analysis([_assist_action()]), graph(frames), authority())
    event = out["events"][0]
    assert event["canonical_event_type"] == "PASS"
    assert event["receiver_team_resolution"]["reason"] == "RECEIVER_TEAM_EVIDENCE_CONFLICT"


def test_b328_single_receiver_team_sample_is_not_enough_for_assist():
    frames = [frame(ms, teams={"p001": "target_team", "p002": "opponent"},
                    holder="p001" if ms == 1000 else "p003" if ms == 1500 else None)
              for ms in (500, 750, 1000, 1250, 1500, 2000, 2500, 3000)]
    receiver = next(p for p in frames[4]["players"] if p["local_track_id"] == "p003")
    receiver.update({"team": "target_team", "team_confidence": .95,
                     "team_source": cer.fsg.TEAM_SOURCE})
    out = cer.resolve_canonical_events(analysis([_assist_action()]), graph(frames), authority())
    event = out["events"][0]
    assert event["canonical_event_type"] == "PASS"
    assert event["receiver_team_resolution"]["reason"] == "RECEIVER_TEAM_EVIDENCE_INSUFFICIENT"


def test_b329_teammate_label_without_ball_transfer_is_not_an_assist():
    frames = [frame(ms) for ms in (500, 750, 1000, 1250, 1500, 2000, 2500, 3000)]
    out = cer.resolve_canonical_events(analysis([_assist_action()]), graph(frames), authority())
    event = out["events"][0]
    assert event["canonical_event_type"] == "PASS"
    assert event["receiver_team_resolution"]["status"] == "UNRESOLVED"
    assert event["receiver_team_resolution"]["reason"] == "TARGET_PASS_CONTACT_BALL_UNRESOLVED"
