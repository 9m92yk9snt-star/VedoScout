from __future__ import annotations
import sys
from pathlib import Path
BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
import post_strike_intervention as a7


def _box(x, y, w=.08, h=.24): return {"x":x,"y":y,"w":w,"h":h}
def _ball(ms, x, y, proof=True):
    return {"media_ms":ms,"scene_id":"s1","state":"MEASURED","box":_box(x,y,.02,.02),
            "time_authority":"ACTUAL_MEDIA_PTS","used_fallback":False,"proof_eligible":proof}
def _frame(ms, player_box, state="VERIFIED_LOCAL"):
    return {"media_ms":ms,"scene_id":"s1","used_fallback":False,"cut_barrier":False,
            "players":[{"local_track_id":"p002","box":player_box,"association_state":state}]}
def _strike():
    return {"status":"VERIFIED_PHYSICAL_RELEASE","media_ms":1000,"scene_id":"s1","player_track_id":"p001"}


def test_a701_full_body_intervention_does_not_need_a4_touch():
    body=_box(.46,.28,.12,.40)
    frames=[_frame(1080,body),_frame(1120,body),_frame(1160,body)]
    # Ball enters torso then reverses sharply. No touch graph is supplied at all.
    trajectory=[_ball(1080,.43,.43),_ball(1120,.50,.43),_ball(1160,.43,.43)]
    out=a7.detect_post_strike_intervention(_strike(),frames,trajectory)
    assert out["status"]=="VERIFIED"
    assert out["player_track_id"]=="p002"
    assert out["source"]=="A7_INDEPENDENT_FULL_BODY_INTERVENTION"
    assert out["touch_graph_mutated"] is False


def test_a702_near_body_without_ball_consequence_is_not_intervention():
    body=_box(.46,.28,.12,.40)
    frames=[_frame(1080,body),_frame(1120,body),_frame(1160,body)]
    trajectory=[_ball(1080,.47,.43),_ball(1120,.50,.43),_ball(1160,.53,.43)]
    out=a7.detect_post_strike_intervention(_strike(),frames,trajectory)
    assert out["status"]=="UNRESOLVED"


def test_a703_ambiguous_body_fails_closed():
    body=_box(.46,.28,.12,.40)
    frames=[_frame(1080,body),_frame(1120,body,"HYPOTHESES"),_frame(1160,body)]
    trajectory=[_ball(1080,.43,.43),_ball(1120,.50,.43),_ball(1160,.43,.43)]
    out=a7.detect_post_strike_intervention(_strike(),frames,trajectory)
    assert out["status"]=="UNRESOLVED"


def test_a704_save_requires_verified_keeper_and_verified_no_crossing():
    base={"physical_outcome":"UNRESOLVED","goal_plane_crossing":{"status":"REJECTED"},
          "goal_geometry_evidence":{"visual_crossing_audit":{"status":"VERIFIED_NO_CROSSING"}},
          "canonical_event_type":None}
    ev={"status":"VERIFIED","player_track_id":"p002","media_ms":1120,
        "kind":"DEFLECTION_OR_PARRY_LIKE","proof_eligible":True}
    roles={"p002":{"status":"VERIFIED","role":"GOALKEEPER","reason":"multi_frame_role"}}
    out=a7.apply_intervention_evidence(base,ev,roles)
    assert out["physical_outcome"]=="GOALKEEPER_SAVE_EVIDENCE"
    assert out["save_evidence"]["status"]=="VERIFIED"
    assert out["canonical_event_type"] is None


def test_a705_unknown_role_never_becomes_save():
    base={"physical_outcome":"UNRESOLVED","goal_plane_crossing":{"status":"REJECTED"},
          "goal_geometry_evidence":{"visual_crossing_audit":{"status":"VERIFIED_NO_CROSSING"}}}
    ev={"status":"VERIFIED","player_track_id":"p002","media_ms":1120,"proof_eligible":True}
    out=a7.apply_intervention_evidence(base,ev,{})
    assert out["physical_outcome"]=="PLAYER_INTERVENTION"
    assert out["save_evidence"]["status"]=="UNRESOLVED"
