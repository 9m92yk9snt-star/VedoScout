"""Native camera/ball measurements must distinguish motion from a nearby body."""
from copy import deepcopy
from pathlib import Path
import sys

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ball_motion_evidence as motion
import ball_contact_engine as contact
import dense_track_refinement as dense
import short_occlusion_contact_recovery as recovery
import event_trace

P = {"x": .10, "y": .20, "w": .10, "h": .30}


def frames(width=1000, height=1000, offsets=(0., 0., 0.), times=(880, 1000, 1120)):
    rows = []
    for i, (ms, shift) in enumerate(zip(times, offsets)):
        rows.append({"media_ms": ms, "scene_id": "s", "used_fallback": False,
                     "time_authority": "ACTUAL_MEDIA_PTS",
                     "frame_dimensions": {"width": width, "height": height, "source": "DECODED_NATIVE_PIXELS"},
                     "players": [{"local_track_id": "actor", "association_state": "VERIFIED_LOCAL",
                                  "box": {**P, "x": P["x"]+shift}}],
                     "camera_state": "AFFINE_VERIFIED" if i else "SEED_OR_FIRST_FRAME",
                     "camera_motion": {"source": "NATIVE_BACKGROUND_AFFINE", "units": "DECODED_PIXELS",
                                       "from_media_ms": times[i-1], "to_media_ms": ms,
                                       "matrix": [[1., 0., (shift-offsets[i-1])*width], [0., 1., 0.]]}
                     if i else None})
    return rows


def balls(times=(880, 1000, 1120), offsets=(0., 0., 0.)):
    return [{"media_ms": ms, "state": "MEASURED", "proof_eligible": True,
             "time_authority": "ACTUAL_MEDIA_PTS", "box": {"x": .14+shift, "y": .48, "w": .02, "h": .02}}
            for ms, shift in zip(times, offsets)]


def accepted(fs, bs):
    return contact.resolve_contacts(contact.detect_contact_candidates(fs, bs))["accepted"]


def legacy(fs):
    result = deepcopy(fs)
    for f in result: f.pop("camera_motion")
    return result


def test_player_walking_past_a_stationary_ball_is_not_a_verified_touch():
    fs, bs = frames(), balls()
    fs[2]["players"][0]["box"]["x"] = .33
    assert accepted(legacy(fs), bs)  # Prior API behavior demonstrates the false contact.
    assert accepted(fs, bs) == []
    middle = next(c for c in contact.detect_contact_candidates(fs, bs) if c["media_ms"] == 1000)
    assert middle["possession_evidence"]["kind"] == "RELEASE"
    assert "BALL_MOVEMENT_BELOW_NATIVE_RESOLUTION" in middle["rejection_reasons"]


def test_sub_ball_radius_detector_jitter_cannot_create_a_direction_change_touch():
    fs, bs = frames(), balls(offsets=(-.001, 0., -.001))
    assert accepted(legacy(fs), bs)
    assert accepted(fs, bs) == []


@pytest.mark.parametrize("width,height", [(1000,1000), (1920,1080), (1080,1920)])
def test_accelerating_camera_does_not_turn_a_stationary_ball_into_a_touch(width, height):
    shifts = (0., .06, .24)
    fs, bs = frames(width, height, shifts), balls(offsets=shifts)
    result = motion.relative_ball_motion(fs, *bs)
    assert result["status"] == "MEASURED"
    assert result["maximum_residual_px"] == 0.
    assert result["resolved_motion"] is False
    assert accepted(fs, bs) == []


def test_real_ball_release_remains_visible_after_removing_camera_pan():
    fs = frames(offsets=(0., .02, .05))
    bs = balls(offsets=(0., .02, .15))
    result = motion.relative_ball_motion(fs, *bs)
    assert result["resolved_motion"] is True
    assert result["maximum_residual_px"] == pytest.approx(100.)
    assert result["after_velocity"] == pytest.approx([100/1000/.12, 0.])
    assert [c["media_ms"] for c in accepted(fs, bs)] == [1000]


def test_rotation_and_zoom_vectors_use_the_same_current_frame_axes():
    fs, bs = frames(), balls()
    theta = np.radians(2.)
    linear = 1.03*np.array([[np.cos(theta),-np.sin(theta)], [np.sin(theta),np.cos(theta)]])
    matrix = np.column_stack((linear, [20., -5.]))
    fs[2]["camera_motion"]["matrix"] = matrix.tolist()
    cur = np.array([.15*1000,.49*1000])
    actual = matrix @ np.append(cur + [60., 0.], 1.)
    bs[2]["box"].update(x=actual[0]/1000-.01,y=actual[1]/1000-.01)
    result = motion.relative_ball_motion(fs, *bs)
    assert result["after_velocity"] == pytest.approx([.06/.12, 0.], abs=1e-10)


def test_camera_chain_is_composed_through_frames_with_no_ball_detection():
    fs = frames(times=(880, 940, 1000), offsets=(0., .01, .03))
    extra = frames(times=(1000, 1060, 1120), offsets=(.03,.04,.07))[1:]
    fs.extend(extra)
    bs = balls(offsets=(0.,.03,.07))
    result = motion.relative_ball_motion(fs, *bs)
    assert result["status"] == "MEASURED"
    assert result["maximum_residual_px"] == 0.


@pytest.mark.parametrize("change", [
    {"camera_motion": None}, {"camera_state": "UNRESOLVED:flow"}, {"cut_barrier": True},
    {"scene_id": "other"}, {"used_fallback": True}, {"time_authority": "FRAME_INDEX_FPS_FALLBACK"},
    {"frame_dimensions": {"width": 2000,"height": 2000,"source":"DECODED_NATIVE_PIXELS"}},
    {"frame_dimensions": {"width": True,"height": 1000,"source":"DECODED_NATIVE_PIXELS"}},
])
def test_unavailable_or_mixed_camera_evidence_cannot_fall_back_to_screen_motion(change):
    fs, bs = frames(), balls(offsets=(0., 0., .1))
    fs[2].update(change)
    assert motion.relative_ball_motion(fs, *bs)["status"] == "UNRESOLVED"
    assert accepted(fs, bs) == []


@pytest.mark.parametrize("change", [
    {"source":"MODEL_GUESS"}, {"units":"NORMALIZED"}, {"from_media_ms":881},
    {"to_media_ms":True}, {"matrix":[[1,0],[0,1]]}, {"matrix":[[1,0,float('nan')],[0,1,0]]},
    {"matrix":[[1,.2,0],[0,1,0]]}, {"matrix":[[-1,0,0],[0,1,0]]},
    {"matrix":[[2,0,0],[0,2,0]]}, {"matrix":[[1,0,1000],[0,1,0]]},
])
def test_camera_labels_cannot_substitute_for_a_valid_measured_transform(change):
    fs, bs = frames(), balls(offsets=(0., 0., .1))
    fs[1]["camera_motion"].update(change)
    assert motion.relative_ball_motion(fs, *bs)["status"] == "UNRESOLVED"
    assert accepted(fs, bs) == []


def test_missing_and_duplicate_camera_frames_break_the_source_pts_chain():
    fs, bs = frames(), balls(offsets=(0., 0., .1))
    assert motion.relative_ball_motion(fs[:1]+fs[2:], *bs)["status"] == "UNRESOLVED"
    assert motion.relative_ball_motion(fs[:1]+[deepcopy(fs[1])]+fs[1:], *bs)["status"] == "UNRESOLVED"


def test_legacy_contact_interpretation_is_preserved_without_the_native_contract():
    fs, bs = legacy(frames()), balls(offsets=(0., 0., .1))
    assert motion.relative_ball_motion(fs, *bs)["status"] == "LEGACY"
    assert accepted(fs, bs)


def test_refinement_records_the_actual_affine_matrix_and_its_decoded_pts(monkeypatch):
    monkeypatch.setattr(dense.uia, "resolve_target_at", lambda *_a, **_k: (None,"UNRESOLVED"))
    image = np.zeros((100, 200, 3), np.uint8)
    matrix = np.array([[1.,0.,3.], [0.,1.,-2.]])
    inputs = [{"media_ms": ms, "frame_bgr": image, "time_authority":"ACTUAL_MEDIA_PTS"}
              for ms in (1000, 1017)]
    result = dense.refine_window(inputs, {}, {}, "s", detector_fn=lambda _im: ([{"box":P}],[]),
                                 camera_estimator=lambda *_a: (matrix,"verified"))["frames"]
    assert result[0]["camera_motion"] is None
    assert result[1]["camera_motion"] == {"source":"NATIVE_BACKGROUND_AFFINE","units":"DECODED_PIXELS",
                                          "from_media_ms":1000,"to_media_ms":1017,"matrix":matrix.tolist(),
                                          "estimation_frame_dimensions":{"width":200,"height":100}}


def test_occlusion_recovery_cannot_reintroduce_camera_only_trajectory_change():
    shifts=(0., .01, .03, .12)
    fs=frames(times=(760,880,1000), offsets=shifts[:3])
    fs.extend(frames(times=(880,1000,1120), offsets=shifts[1:])[2:])
    bs=balls(times=(760,880,1000), offsets=shifts[:3])
    bs.extend(balls(times=(880,1000,1120), offsets=shifts[1:])[2:])
    assert recovery._trajectory_change(*bs)["score"] > 0
    change=recovery._trajectory_change(*bs, frames=fs)
    assert change["score"] == 0.
    assert change["camera_motion"]["resolved_motion"] is False


def test_occlusion_recovery_uses_the_actual_outgoing_pair_after_the_gap():
    fs=frames(times=(760,880,1000))
    fs.extend(frames(times=(880,1000,1120))[2:])
    bs=balls(times=(760,880,1000),offsets=(-.06,0.,0.))
    bs.extend(balls(times=(880,1000,1120),offsets=(0.,0.,-.06))[2:])
    change=recovery._trajectory_change(*bs,frames=fs)
    assert change["before"]["x"] == pytest.approx(.5)
    assert change["after"]["x"] == pytest.approx(-.5)
    assert change["direction_change_deg"] == pytest.approx(180.)
    assert recovery._strong_trajectory_consequence(change)


def test_exact_tap_and_player_separation_cannot_promote_a_stationary_ball():
    fs,bs=frames(),balls()
    assert recovery._exact_tap_path_evidence(bs[0],bs[2],.7)["score"] == 1.
    assert recovery._exact_tap_path_evidence(bs[0],bs[2],.7,fs)["score"] == 0.


def test_support_path_ball_motion_removes_camera_pan_but_retains_real_release():
    shifts=(0., .02, .05)
    fs,bs=frames(offsets=shifts),balls(offsets=shifts)
    assert recovery._exact_tap_path_evidence(bs[0],bs[2],.7,fs)["score"] == 0.
    bs[2]["box"]["x"] += .1
    result=recovery._exact_tap_path_evidence(bs[0],bs[2],.7,fs)
    assert result["score"] > 0
    assert result["after"]["x"] == pytest.approx(.1/.24)


def test_missing_camera_transform_blocks_a_support_path_even_with_large_separation():
    fs,bs=frames(),balls(offsets=(0.,0.,.1))
    fs[1]["camera_motion"]=None
    assert recovery._exact_tap_path_evidence(bs[0],bs[2],.7,fs)["score"] == 0.


def test_rounded_portrait_estimation_pixels_preserve_a_valid_camera_transform():
    fs,bs=frames(960,1707),balls()
    theta=np.radians(1.)
    source=np.array([[np.cos(theta),-np.sin(theta),3.], [np.sin(theta),np.cos(theta),-1.], [0.,0.,1.]])
    scale=np.diag([.5,854/1707,1.])
    native=np.linalg.inv(scale) @ source @ scale
    center=np.array([.15*960,.49*1707,1.])
    for i in (1,2):
        fs[i]["camera_motion"]["matrix"]=native[:2].tolist()
        fs[i]["camera_motion"]["estimation_frame_dimensions"]={"width":480,"height":854}
        center=native @ center
        bs[i]["box"].update(x=center[0]/960-.01,y=center[1]/1707-.01)
    result=motion.relative_ball_motion(fs,*bs)
    assert result["status"] == "MEASURED"
    assert result["maximum_residual_px"] == 0.


def test_export_and_replay_preserve_camera_geometry_and_support_only_proposals():
    fs,bs=frames(960,1707),balls(offsets=(0.,0.,.1))
    fs[1]["a7_ball_support_candidates"]=[{"box":bs[1]["box"],"confidence":.02,"proof_eligible":False,
                                           "support_only":True,"image_bgr":np.zeros((2,2,3),np.uint8)}]
    exported=event_trace._compact_dense_frames(fs)
    assert exported[1]["camera_motion"] == fs[1]["camera_motion"]
    assert exported[1]["frame_dimensions"] == fs[1]["frame_dimensions"]
    assert exported[1]["a7_ball_support_candidates"][0]["proof_eligible"] is False
    assert "image_bgr" not in exported[1]["a7_ball_support_candidates"][0]
    assert motion.relative_ball_motion(exported,*bs) == motion.relative_ball_motion(fs,*bs)
    assert [c["media_ms"] for c in accepted(exported,bs)] == [c["media_ms"] for c in accepted(fs,bs)]


def test_malformed_exported_geometry_cannot_silently_become_legacy_evidence():
    fs=frames();fs[1]["camera_motion"]={"matrix":np.zeros((2,3))}
    exported=event_trace._compact_dense_frames(fs)
    assert "camera_motion" in exported[1]
    assert motion.relative_ball_motion(exported,*balls())["status"] == "UNRESOLVED"


def test_mixed_native_and_legacy_frames_cannot_authorize_a_legacy_fallback():
    fs=legacy(frames())
    fs.extend(frames(times=(1500,1600,1700)))
    assert motion.relative_ball_motion(fs,*balls(offsets=(0.,0.,.1)))["status"] == "UNRESOLVED"
