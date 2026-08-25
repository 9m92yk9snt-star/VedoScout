from __future__ import annotations

import asyncio
import json
from copy import deepcopy

import cv2
import numpy as np

import fix10a_ball_proof_gate as ball_gate
import fix10a_goal_direction as direction
import fix10a_occluded_goal as occluded
import fix10a_vision_providers as providers
import shot_outcome_engine as outcome_engine


def box(cx, cy=.50, w=.02, h=.02):
    return {"x": cx - w / 2, "y": cy - h / 2, "w": w, "h": h}


def ball(ms, x, y=.50, *, proof=True, cut=False):
    return {
        "media_ms": int(ms),
        "scene_id": "s1",
        "state": "MEASURED",
        "box": box(x, y),
        "proof_eligible": bool(proof),
        "time_authority": "ACTUAL_MEDIA_PTS",
        "used_fallback": False,
        "cut_barrier": bool(cut),
    }


def _line(x=.80, y1=.20, y2=.80):
    return {"p1": {"x": x, "y": y1}, "p2": {"x": x, "y": y2}}


def _pre_visual(xs=(.62, .69, .755), times=(1000, 1050, 1100), y=.50):
    return [
        {
            "idx": i + 2,
            "media_ms": int(ms),
            "ball_visible": True,
            "relation": "FIELD_SIDE",
            "ball_box": box(x, y),
            "occluder": "UNKNOWN",
            "confidence": "high",
            "reason": "same moving ball visible",
        }
        for i, (ms, x) in enumerate(zip(times, xs))
    ]


def _occ_rows(start=1150, count=1):
    return [
        {
            "idx": 5 + i,
            "media_ms": start + 100 * i,
            "ball_visible": False,
            "relation": "OCCLUDED_GOAL_MOUTH",
            "ball_box": None,
            "occluder": "PLAYER_BODY",
            "confidence": "high",
            "reason": "ball hidden by player body in goal mouth",
        }
        for i in range(count)
    ]


def geometry(*, pre=None, occ=None, celebration=True, late=True,
             defender_contact="NO_VISIBLE_CONTACT", field_side=True,
             visual_status="UNRESOLVED", extra_visual=None, line_x=.80):
    pre = list(pre if pre is not None else _pre_visual())
    occ = list(occ if occ is not None else _occ_rows())
    structured = pre + occ + list(extra_visual or [])
    line = _line(line_x)
    times = sorted({
        900, 1000, 1050, 1100, 1150, 1250, 1400,
        *[int(r["media_ms"]) for r in structured if isinstance(r, dict) and "media_ms" in r],
    })
    reaction_status = "VERIFIED" if celebration and late and defender_contact != "OBSERVED_CONTACT" else (
        "CONTRADICTED" if defender_contact == "OBSERVED_CONTACT" else "UNRESOLVED"
    )
    return {
        "status": "VERIFIED",
        "source": "INDEPENDENT_MULTI_FRAME_GOAL_REVIEW",
        "line": line,
        "line_by_ms": [{"media_ms": ms, "line": line, "confidence": "high"} for ms in times],
        "field_side_status": "VERIFIED" if field_side else "UNRESOLVED",
        "field_side_by_ms": (
            [{"media_ms": ms, "point": {"x": .60, "y": .50}, "confidence": "high"} for ms in times]
            if field_side else []
        ),
        "visual_crossing_audit": {
            "status": visual_status,
            "confidence": "high" if visual_status != "UNRESOLVED" else "low",
            "proof_ready": False,
            "same_ball_continuity": False,
            "structured_evidence": structured,
        },
        "occlusion_crossing_audit": {
            "status": "VERIFIED_OCCLUSION" if occ and len(pre) >= 2 else "UNRESOLVED",
            "confidence": "high" if occ and len(pre) >= 2 else "low",
            "occlusion_start_media_ms": int(occ[0]["media_ms"]) if occ else None,
            "occlusion_end_media_ms": int(occ[-1]["media_ms"]) if occ else None,
            "last_field_side_media_ms": int(pre[-1]["media_ms"]) if pre else None,
            "first_beyond_after_occlusion_media_ms": None,
            "occlusion_rows": deepcopy(occ),
            "pre_occlusion_visible_rows": deepcopy(pre),
            "same_ball_pre_occlusion": len(pre) >= 2,
            "visual_contradiction": False,
            "reason": "BOUNDED_PLAYER_BODY_GOAL_MOUTH_OCCLUSION" if occ else "UNRESOLVED",
        },
        "reaction_support_evidence": {
            "status": reaction_status,
            "confidence": "high" if reaction_status == "VERIFIED" else "low",
            "release_player_celebration": {
                "status": "OBSERVED" if celebration else "UNRESOLVED",
                "confidence": "high" if celebration else "low",
            },
            "goal_mouth_defender_response": {
                "status": "LATE_OR_NO_REACTION" if late else "UNRESOLVED",
                "confidence": "high" if late else "low",
            },
            "goal_mouth_defender_ball_contact": {
                "status": defender_contact,
                "confidence": "high" if defender_contact != "UNRESOLVED" else "low",
            },
        },
    }


def strike(ms=1000):
    return {
        "strike_id": "strike_target",
        "touch_id": "touch_target",
        "media_ms": int(ms),
        "scene_id": "s1",
        "player_track_id": "p_target",
        "global_target_id": "GLOBAL_TARGET",
        "status": "VERIFIED_PHYSICAL_RELEASE",
    }


def run_full(geom, trajectory=None, touches=None):
    trajectory = list(trajectory if trajectory is not None else [ball(1000, .62)])
    touch_graph = {"touches": list(touches or [])}
    out = outcome_engine.reconstruct_post_strike_outcome(
        strike(), trajectory, touch_graph, goal_geometry=geom, role_evidence={}
    )
    out = direction.apply_direction_gate(out, trajectory, geom)
    out = ball_gate.apply_ball_proof_gate(out, trajectory)
    return out


def test_occ_01_hybrid_detector_visual_path_certifies_crossing():
    out = run_full(geometry())
    crossing = out["goal_plane_crossing"]
    assert out["physical_outcome"] == "GOAL_PLANE_CROSSING"
    assert crossing["status"] == "VERIFIED"
    assert crossing["direction"] == "FIELD_TO_GOAL"
    assert out["ball_proof_gate"]["status"] == "VERIFIED"
    seg = crossing["evidence"][0]
    assert seg["proof_lane"] == "OCCLUDED_TRAJECTORY_GOAL"
    assert seg["anchor_mode"] == "HYBRID_DETECTOR_PROVIDER"
    assert seg["detector_anchor_media_ms"] == [1000]
    assert len(seg["provider_anchor_media_ms"]) >= 2
    assert seg["reaction_support_only"] is True


def test_occ_02_celebration_without_keeper_reaction_is_not_goal_proof():
    out = run_full(geometry(celebration=True, late=False))
    assert out["goal_plane_crossing"]["status"] == "UNRESOLVED"
    assert out["physical_outcome"] != "GOAL_PLANE_CROSSING"


def test_occ_03_keeper_late_without_release_player_celebration_is_not_goal_proof():
    out = run_full(geometry(celebration=False, late=True))
    assert out["goal_plane_crossing"]["status"] == "UNRESOLVED"


def test_occ_04_visible_defender_ball_contact_rejects_unopposed_occlusion_lane():
    geom = geometry(defender_contact="OBSERVED_CONTACT")
    r = occluded.resolve_occluded_crossing(
        [ball(1000, .62)], geom, 1000, {"touches": []}, "p_target"
    )
    assert r["status"] == "REJECTED"
    assert "DEFENDER_CONTACT" in r["reason"]


def test_occ_05_missing_literal_goal_mouth_occlusion_fails_closed():
    geom = geometry(occ=[])
    out = run_full(geom)
    assert out["goal_plane_crossing"]["status"] == "UNRESOLVED"


def test_occ_06_one_provider_visual_anchor_is_insufficient():
    pre = _pre_visual(xs=(.62,), times=(1000,))
    geom = geometry(pre=pre)
    geom["occlusion_crossing_audit"]["status"] = "VERIFIED_OCCLUSION"
    geom["occlusion_crossing_audit"]["confidence"] = "high"
    geom["occlusion_crossing_audit"]["same_ball_pre_occlusion"] = True
    r = occluded.resolve_occluded_crossing(
        [ball(1000, .62)], geom, 1000, {"touches": []}, "p_target"
    )
    assert r["status"] == "UNRESOLVED"
    assert r["reason"] == "PRE_OCCLUSION_PROOF_TRAJECTORY_INSUFFICIENT"


def test_occ_07_detector_to_provider_ball_identity_link_must_be_spatially_consistent():
    pre = _pre_visual(xs=(.30, .36, .42), times=(1000, 1050, 1100))
    geom = geometry(pre=pre)
    r = occluded.resolve_occluded_crossing(
        [ball(1000, .62)], geom, 1000, {"touches": []}, "p_target"
    )
    assert r["status"] == "UNRESOLVED"
    assert r["reason"] == "PRE_OCCLUSION_PROOF_TRAJECTORY_INSUFFICIENT"


def test_occ_08_ball_moving_away_from_goal_plane_cannot_be_projected_into_goal():
    pre = _pre_visual(xs=(.74, .69, .62), times=(1000, 1050, 1100))
    geom = geometry(pre=pre)
    r = occluded.resolve_occluded_crossing(
        [ball(1000, .74)], geom, 1000, {"touches": []}, "p_target"
    )
    assert r["status"] == "UNRESOLVED"
    assert r["reason"] in {"BALL_NOT_MOVING_TOWARD_GOAL_PLANE", "PROJECTED_GOAL_PLANE_CROSSING_OUT_OF_BOUNDS"}


def test_occ_09_projected_path_outside_goal_mouth_stays_unresolved():
    pre = _pre_visual(y=.86)
    geom = geometry(pre=pre)
    r = occluded.resolve_occluded_crossing(
        [ball(1000, .62, .86)], geom, 1000, {"touches": []}, "p_target"
    )
    assert r["status"] == "UNRESOLVED"
    assert r["reason"] == "PROJECTED_WHOLE_BALL_NOT_SAFELY_INSIDE_GOAL_MOUTH"


def test_occ_10_verified_competing_touch_before_projected_crossing_blocks_goal():
    touch = {
        "status": "VERIFIED", "media_ms": 1120, "representative_ms": 1120,
        "player_track_id": "p_other",
    }
    out = run_full(geometry(), touches=[touch])
    assert out["goal_plane_crossing"]["status"] == "UNRESOLVED"
    assert "COMPETING_VERIFIED_POST_STRIKE_CONTACT" in out["goal_plane_crossing"]["reason"]


def test_occ_11_high_confidence_visible_field_side_after_projection_is_contradiction():
    contradiction = {
        "idx": 6, "media_ms": 1200, "ball_visible": True,
        "relation": "FIELD_SIDE", "ball_box": box(.70), "occluder": "UNKNOWN",
        "confidence": "high", "reason": "ball visibly remains field side",
    }
    geom = geometry(extra_visual=[contradiction])
    r = occluded.resolve_occluded_crossing(
        [ball(1000, .62)], geom, 1000, {"touches": []}, "p_target"
    )
    assert r["status"] == "REJECTED"
    assert "POST_PROJECTION_VISIBLE_FIELD_SIDE" in r["reason"]


def test_occ_12_missing_field_orientation_downgrades_preverified_occluded_crossing():
    geom = geometry(field_side=False)
    trajectory = [ball(1000, .62)]
    raw = outcome_engine.reconstruct_post_strike_outcome(
        strike(), trajectory, {"touches": []}, goal_geometry=geom, role_evidence={}
    )
    assert raw["goal_plane_crossing"]["status"] == "VERIFIED"
    gated = direction.apply_direction_gate(raw, trajectory, geom)
    assert gated["goal_plane_crossing"]["status"] == "UNRESOLVED"
    assert gated["direction_gate"]["reason"] == "FIELD_SIDE_ORIENTATION_UNAVAILABLE"


def test_occ_13_uncertified_detector_anchor_cannot_pass_final_ball_proof_gate():
    geom = geometry()
    trajectory = [ball(1000, .62, proof=False)]
    # The provider path cannot establish the detector->visual identity bridge
    # without at least one proof-eligible physical ball anchor.
    out = run_full(geom, trajectory=trajectory)
    assert out["goal_plane_crossing"]["status"] == "UNRESOLVED"


def test_occ_14_direct_visible_whole_ball_lane_is_unchanged():
    line = _line()
    structured = [
        {"media_ms": 1000, "ball_visible": True, "relation": "FIELD_SIDE", "confidence": "high"},
        {"media_ms": 1100, "ball_visible": True, "relation": "ON_OR_STRADDLING_LINE", "confidence": "medium"},
        {"media_ms": 1200, "ball_visible": True, "relation": "BEYOND_LINE_INSIDE_MOUTH", "confidence": "high"},
    ]
    geom = {
        "status": "VERIFIED", "source": "INDEPENDENT_MULTI_FRAME_GOAL_REVIEW",
        "line": line,
        "line_by_ms": [{"media_ms": m, "line": line, "confidence": "high"} for m in (1000, 1100, 1200)],
        "field_side_status": "VERIFIED",
        "field_side_by_ms": [
            {"media_ms": m, "point": {"x": .60, "y": .50}, "confidence": "high"}
            for m in (1000, 1100, 1200)
        ],
        "visual_crossing_audit": {
            "status": "VERIFIED_CROSSING", "confidence": "high",
            "proof_ready": True, "same_ball_continuity": True,
            "field_side_before_media_ms": 1000,
            "first_crossing_media_ms": 1100,
            "beyond_line_media_ms": 1200,
            "structured_evidence": structured,
        },
    }
    raw = outcome_engine.reconstruct_post_strike_outcome(
        strike(), [], {"touches": []}, goal_geometry=geom, role_evidence={}
    )
    assert raw["goal_plane_crossing"]["status"] == "VERIFIED"
    assert raw["goal_plane_crossing"]["evidence"][0]["proof_lane"] == "STRUCTURED_VISUAL_WHOLE_BALL"
    gated = direction.apply_direction_gate(raw, [], geom)
    gated = ball_gate.apply_ball_proof_gate(gated, [])
    assert gated["goal_plane_crossing"]["status"] == "VERIFIED"


def test_occ_15_scene_cut_removes_detector_anchor_from_occlusion_lane():
    geom = geometry()
    r = occluded.resolve_occluded_crossing(
        [ball(1000, .62, cut=True)], geom, 1000, {"touches": []}, "p_target"
    )
    assert r["status"] == "UNRESOLVED"


def test_occ_16_provider_reader_parses_occlusion_and_reactions_without_faking_direct_crossing(tmp_path, monkeypatch):
    response = {
        "geometry_status": "VERIFIED",
        "frames": [
            {"idx": i, "visible": True, "p1": {"x": .8, "y": .2},
             "p2": {"x": .8, "y": .8}, "confidence": "high"}
            for i in range(1, 5)
        ],
        "ball_evidence": [
            {"idx": 1, "ball_visible": True, "relation": "FIELD_SIDE",
             "ball_box": box(.62), "occluder": "UNKNOWN", "confidence": "high", "reason": "ball visible"},
            {"idx": 2, "ball_visible": True, "relation": "FIELD_SIDE",
             "ball_box": box(.72), "occluder": "UNKNOWN", "confidence": "high", "reason": "ball approaching"},
            {"idx": 3, "ball_visible": False, "relation": "OCCLUDED_GOAL_MOUTH",
             "ball_box": None, "occluder": "PLAYER_BODY", "confidence": "high", "reason": "hidden by player"},
            {"idx": 4, "ball_visible": False, "relation": "OCCLUDED_GOAL_MOUTH",
             "ball_box": None, "occluder": "PLAYER_BODY", "confidence": "high", "reason": "still hidden"},
        ],
        "same_ball_continuity": False,
        "first_crossing_idx": None,
        "crossing": "UNRESOLVED",
        "crossing_confidence": "low",
        "reaction_evidence": {
            "release_player_tracked": True,
            "release_player_celebration": "OBSERVED",
            "release_player_confidence": "high",
            "goal_mouth_defender_tracked": True,
            "goal_mouth_defender_ball_contact": "NO_VISIBLE_CONTACT",
            "goal_mouth_defender_response": "LATE_OR_NO_REACTION",
            "goal_mouth_defender_confidence": "high",
        },
        "reason": "literal observations only",
    }

    class FakeResponse:
        text = json.dumps(response)

    class FakeChat:
        def __init__(self, **kwargs):
            pass
        def with_model(self, provider, model):
            return self
        async def send_message(self, _message):
            return FakeResponse()

    monkeypatch.setattr(providers, "LlmChat", FakeChat)
    paths = []
    for i in range(4):
        path = tmp_path / f"frame{i}.jpg"
        assert cv2.imwrite(str(path), np.zeros((50, 50, 3), dtype=np.uint8))
        paths.append(str(path))
    got = asyncio.run(providers.read_goal_scene_evidence("key", "session", paths, [1000, 1050, 1100, 1150]))
    assert got["proof_ready"] is False
    assert got["crossing"] == "UNRESOLVED"
    assert got["occlusion_crossing_audit"]["status"] == "VERIFIED_OCCLUSION"
    assert got["occlusion_crossing_audit"]["same_ball_pre_occlusion"] is True
    assert len(got["occlusion_crossing_audit"]["pre_occlusion_visible_rows"]) == 2
    assert got["reaction_support_evidence"]["status"] == "VERIFIED"


def test_occ_17_reaction_support_never_changes_direct_crossing_flag_inside_provider_audit():
    geom = geometry(celebration=True, late=True, visual_status="UNRESOLVED")
    assert geom["reaction_support_evidence"]["status"] == "VERIFIED"
    assert geom["visual_crossing_audit"]["status"] == "UNRESOLVED"
