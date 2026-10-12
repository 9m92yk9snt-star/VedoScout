"""User selection must bind to measured pixels at the selected media frame."""
from pathlib import Path
import sys

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import cv_shadow
import dense_track_refinement as dense
import player_identity_timeline as pit
import player_selection as selection
import unified_identity_authority as uia


def test_point_selection_keeps_ambiguity_and_exclusions():
    boxes = [(0, 0, 2, 3), (1, 0, 2, 3), (5, 0, 1, 3)]
    assert selection.body_indices_at_point(boxes, (1.5, 1)) == [0, 1]
    assert selection.body_indices_at_point(boxes, (1.5, 1), [(2.5, 1)]) == [0]
    assert selection.body_indices_at_point(boxes, (4, 1)) == []
    assert selection.body_indices_at_point(boxes, (float("nan"), 1)) == []


def _authority(point=(.23, .43)):
    anchor = {"t": 1.0, "box": {"x": .15, "y": .30, "w": .60, "h": .50},
              "target_point": {"x": point[0], "y": point[1]}}
    return uia.build_unified_identity_authority(
        identity_timeline={"scenes": [{"scene_id": "scene_1", "start_ms": 0, "end_ms": 3000}]},
        anchors=[anchor])


def _players():
    return [{"local_track_id": "chosen", "association_state": "VERIFIED_LOCAL",
             "box": {"x": .20, "y": .30, "w": .12, "h": .50}},
            {"local_track_id": "crop_center", "association_state": "VERIFIED_LOCAL",
             "box": {"x": .50, "y": .30, "w": .17, "h": .50}}]


def test_direct_selection_keeps_the_users_point_in_canonical_authority():
    row = _authority()["target_points"][0]
    assert row["target_point"] == {"x": .23, "y": .43}


def test_dense_tap_uses_selected_body_instead_of_broad_crop_center():
    result = dense._resolve_dense_target(_authority(), 1000, _players())
    assert result["status"] == "VERIFIED"
    assert result["local_track_id"] == "chosen"
    assert result["proof_eligible"] is True


@pytest.mark.parametrize("ms,point,reason", [
    (1000, (.4, .43), "TAP_POINT_BODY_NOT_FOUND"),
    (1050, (.23, .43), "TARGET_GAP"),
])
def test_dense_point_never_substitutes_nearby_body_or_different_frame(ms, point, reason):
    result = dense._resolve_dense_target(_authority(point), ms, _players())
    assert result["proof_eligible"] is False
    assert result["reason"] == reason


def test_dense_point_shared_by_two_bodies_remains_unresolved():
    players = _players()
    players[1]["box"] = {"x": .21, "y": .30, "w": .15, "h": .50}
    result = dense._resolve_dense_target(_authority(), 1000, players)
    assert result["proof_eligible"] is False
    assert result["reason"] == "TAP_POINT_BODY_AMBIGUOUS"


def test_scene_graph_cannot_replace_selected_point_with_broad_crop_center():
    import football_scene_graph as graph
    result = graph._target_candidates(_authority(), 1000, _players())
    assert result["proof_eligible"] and result["local_track_id"] == "chosen"
    players = _players()
    players[1]["box"] = {"x": .21, "y": .30, "w": .15, "h": .50}
    result = graph._target_candidates(_authority(), 1000, players)
    assert not result["proof_eligible"] and result["reason"] == "TAP_POINT_BODY_AMBIGUOUS"


@pytest.mark.parametrize("candidate_ids", [["selected", "occluder"], []])
def test_better_matching_ambiguous_body_cannot_be_replaced_by_associated_bystander(candidate_ids):
    box = {"x": .22, "y": .45, "w": .14, "h": .12}
    authority = uia.build_unified_identity_authority(anchors=[{"t": 1., "box": box}])
    players = [
        {"local_track_id": "bystander", "association_state": "VERIFIED_LOCAL",
         "box": {"x": .34, "y": .46, "w": .067, "h": .11}},
        {"local_track_id": None, "association_state": "HYPOTHESES",
         "candidate_local_track_ids": candidate_ids, "box": box},
    ]
    result = dense._resolve_dense_target(authority, 1000, players)
    assert result["proof_eligible"] is False
    assert result["reason"] == "DENSE_TARGET_COMPETING_ASSOCIATION"
    assert "bystander" in result["candidate_local_track_ids"]


def _point_timeline(*, fallback=False, decoded_ms=1000):
    observations = []
    for ms in range(0, 2200, 200):
        detections = [{"box": (96., 81., 57.6, 135.), "emb": {"ident": "left"}},
                      {"box": (240., 81., 81.6, 135.), "emb": {"ident": "right"}}]
        observations.append({"media_ms": ms, "width": 480, "height": 270,
                             "cam_dx": 0., "cam_dy": 0., "cut": False,
                             "time_authority": "ACTUAL_MEDIA_PTS", "used_fallback": False,
                             "detections": detections})
    if fallback:
        observations[5].update(time_authority="FRAME_INDEX_FALLBACK", used_fallback=True)
    tap = {"media_ms": 1000, "decoded_media_ms": decoded_ms,
           "box": (72., 81., 288., 135.), "target_point": (110.4, 116.1)}
    return pit.assemble_timeline(observations, [tap], lambda _e: 0.)


def test_coarse_timeline_pins_point_body_when_broad_crop_covers_two_players():
    timeline = _point_timeline()
    visible = [p for p in timeline["target_points"] if not p["predicted"]]
    assert visible
    assert all(p["box"]["x"] < .3 for p in visible)
    assert timeline["recovery"]["tap_point_pins"] == 1


@pytest.mark.parametrize("fallback,decoded_ms", [(True, 1000), (False, 1200), (False, None)])
def test_coarse_point_requires_same_measured_frame(fallback, decoded_ms):
    timeline = _point_timeline(fallback=fallback, decoded_ms=decoded_ms)
    assert not [p for p in timeline["target_points"] if p["proof_eligible"]]
    assert timeline["recovery"]["tap_point_unresolved"] == 1


def test_reference_crop_follows_the_selected_point(monkeypatch):
    import video_timebase
    image = np.full((270, 480, 3), 128, dtype=np.uint8)
    monkeypatch.setattr(video_timebase, "read_frame_at", lambda *a, **k: (True, image, 1.))
    monkeypatch.setattr(cv_shadow, "_blobs", lambda *a, **k: [])
    monkeypatch.setattr(cv_shadow, "_zone_embedding", lambda *a, **k: {"owned": True})

    class Detector:
        ok = True
        def detect(self, _frame):
            return [(p["box"]["x"], p["box"]["y"], p["box"]["w"], p["box"]["h"], .9)
                    for p in _players()]

    anchor = {"t": 1., "box": {"x": .15, "y": .30, "w": .60, "h": .50},
              "target_point": {"x": .23, "y": .43}}
    references, _negatives = cv_shadow._build_tap_references(None, 60., [anchor], 0., 480, 270, 1., Detector())
    assert len(references) == 1
    assert references[0]["box"][0] == 96


def test_reference_cannot_apply_selected_pixels_to_a_different_picture(monkeypatch):
    import video_timebase
    image = np.full((270, 480, 3), 128, dtype=np.uint8)
    monkeypatch.setattr(video_timebase, "read_frame_at", lambda *a, **k: (True, image, 1.2))
    monkeypatch.setattr(cv_shadow, "_pitch_l", lambda *_: pytest.fail("misaligned reference was inspected"))
    anchor = {"t": 1., "box": {"x": .15, "y": .30, "w": .60, "h": .50},
              "target_point": {"x": .23, "y": .43}}
    assert cv_shadow._build_tap_references(None, 60., [anchor], 0., 480, 270, 1.) == ([], [])


def test_optical_tracking_keeps_the_tap_picture_without_moving_its_sample_grid():
    import player_tracking as tracking
    from test_fix04_tracking_geometry import FakeCap
    times = [i / 100 for i in range(31)]
    legacy = tracking._read_window(FakeCap(times, fps=100), 0, .3, .08, fps=100)
    selected = tracking._read_window(FakeCap(times, fps=100), 0, .3, .08, fps=100, seed_time=.105)
    old_times = [round(f[0], 3) for f in legacy]
    new_times = [round(f[0], 3) for f in selected]
    assert .11 in new_times and .11 not in old_times
    assert [t for t in new_times if t != .11] == old_times
    seed = next(f for f in selected if round(f[0], 3) == .11)
    assert int(seed[1][0, 0]) == 11  # actual pixels, not a timestamp alias


def test_optical_tracker_cannot_pin_a_selected_point_to_a_picture_fifty_ms_late(monkeypatch):
    import player_tracking as tracking
    from test_fix04_tracking_geometry import FakeCap, finish
    image = np.full((270, 480, 3), 128, dtype=np.uint8)
    monkeypatch.setattr(tracking.cv2, "VideoCapture", lambda _: FakeCap([0, 1, 2], fps=1))
    monkeypatch.setattr(tracking, "_read_window", lambda *a, **k:
                        [finish(t, image) for t in [.8, 1.05, 1.2]])
    anchor = {"t": 1., "box": {"x": .2, "y": .3, "w": .12, "h": .5},
              "target_point": {"x": .23, "y": .43}}
    assert not tracking.track_player("unused", [anchor])["points"]


def test_optical_tracker_seeds_the_forward_decoded_tap_picture(monkeypatch):
    import player_tracking as tracking
    from test_fix04_tracking_geometry import FakeCap, finish
    image = np.full((270, 480, 3), 128, dtype=np.uint8)
    monkeypatch.setattr(tracking.cv2, "VideoCapture", lambda _: FakeCap([0, 1, 2], fps=1))
    monkeypatch.setattr(tracking, "_read_window", lambda *a, **k:
                        [finish(t, image) for t in [.99, 1.016, 1.05]])
    chosen_times = []
    monkeypatch.setattr(tracking, "_run_direction", lambda frames, i0, *a, **k:
                        chosen_times.append(frames[i0][0]))
    anchor = {"t": 1., "box": {"x": .2, "y": .3, "w": .12, "h": .5},
              "target_point": {"x": .23, "y": .43}}
    points = tracking.track_player("unused", [anchor])["points"]
    assert len(points) == 1 and points[0]["t"] == round(1.016, 2) and points[0]["conf"] == 1.
    assert chosen_times == [1.016, 1.016]


@pytest.mark.parametrize("include_mask", [False, True])
def test_video_ingestion_samples_taps_without_moving_regular_sampling_grid(monkeypatch, include_mask):
    import cv2
    import cv_detect
    times = [0, 83, 167, 183, 200, 217, 400, 600]
    image = np.full((270, 480, 3), 128, dtype=np.uint8)
    captured = {}

    class Capture:
        i = -1
        def isOpened(self): return True
        def set(self, _key, _value): self.i = -1; return True
        def grab(self): self.i += 1; return self.i < len(times)
        def retrieve(self): return True, image
        def release(self): pass
        def get(self, key):
            return {cv2.CAP_PROP_FPS: 60., cv2.CAP_PROP_FRAME_WIDTH: 480,
                    cv2.CAP_PROP_FRAME_HEIGHT: 270, cv2.CAP_PROP_POS_FRAMES: self.i + 1,
                    cv2.CAP_PROP_POS_MSEC: times[min(max(self.i, 0), len(times) - 1)]}.get(key, 0.)

    class Detector:
        ok = True
        def __init__(self, **_kwargs): pass
        def detect(self, _frame): return []

    def assemble(observations, taps, *_args, **_kwargs):
        captured.update(observations=observations, taps=taps)
        return {"scenes": [], "target_points": [], "counts": {}, "unresolved_intervals": []}

    monkeypatch.setattr(cv2, "VideoCapture", lambda _path: Capture())
    monkeypatch.setattr(cv_detect, "PersonDetector", Detector)
    monkeypatch.setattr(cv_shadow, "_build_tap_references", lambda *a, **k: ([{}, {}], []))
    monkeypatch.setattr(pit, "assemble_timeline", assemble)
    monkeypatch.setattr(pit, "HZ", 5.)
    document = {"anchors": [{"t": t, "box": {"x": .2, "y": .3, "w": .1, "h": .5},
                             "target_point": {"x": .23, "y": .43}} for t in (.183, .210)]}
    if include_mask:
        from test_fix15_selected_mask_identity import mask
        for anchor in document["anchors"]:
            anchor["visible_mask"] = mask()
    result = pit.build_identity_timeline("unused.mp4", document)
    assert [o["media_ms"] for o in captured["observations"]] == [0, 183, 200, 217, 400, 600]
    assert [t["decoded_media_ms"] for t in captured["taps"]] == [183, 217]
    assert all(o["time_authority"] == "ACTUAL_MEDIA_PTS" for o in captured["observations"])
    assert result["tap_frame_bindings"][1]["frame_delta_ms"] == 7
    if include_mask:
        for original, ingested in zip(document["anchors"], captured["taps"]):
            assert ingested["visible_mask"] == original["visible_mask"]
            assert ingested["visible_mask"] is not original["visible_mask"]
    else:
        assert all("visible_mask" not in row for row in captured["taps"])
