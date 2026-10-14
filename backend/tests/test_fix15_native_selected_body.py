"""A missing selected body needs measured native pixels, not an old ID swap."""
from copy import deepcopy
import math
import numpy as np
import pytest

import dense_track_refinement as dense
import unified_identity_authority as uia

BOX = {"x": .4, "y": .3, "w": .1, "h": .2}
POINT = {"x": .46, "y": .43}
OWNER = {"x": .438, "y": .335, "w": .059, "h": .150}
BYSTANDER = {"x": .350, "y": .300, "w": .120, "h": .220}
IMAGE = np.zeros((1280, 640, 3), dtype=np.uint8)


def mask():
    arr = np.zeros((192, 96), np.uint8)
    arr[40:170, 40:90] = 1
    runs, last, count = [], 0, 0
    for value in arr.ravel():
        if value == last:
            count += 1
        else:
            runs.append(count)
            last, count = int(value), 1
    runs.append(count)
    return {"width": 96, "height": 192, "runs": runs, "method": "test_fixture"}


def authority():
    return uia.build_unified_identity_authority(anchors=[{
        "t": 1., "box": deepcopy(BOX), "target_point": deepcopy(POINT), "visible_mask": mask()}])


def tap():
    return next(r for r in authority()["target_points"] if r["primary_source"] == "USER_TAP")


class Detector:
    ok = True


def native_rois(selected=BOX, image=IMAGE):
    h, w = image.shape[:2]
    cx, cy = (selected["x"] + selected["w"] / 2) * w, (selected["y"] + selected["h"] / 2) * h
    return [(max(0, math.floor(cx - selected["w"] * w * f / 2)),
             max(0, math.floor(cy - selected["h"] * h * f / 2)),
             min(w, math.ceil(cx + selected["w"] * w * f / 2)),
             min(h, math.ceil(cy + selected["h"] * h * f / 2))) for f in (1.15, 1.5)]


def install(monkeypatch, outputs=None, *, whole=None):
    outputs = [[{"box": deepcopy(OWNER), "confidence": .4, "kit_chroma": [128., 128.]}]] * 2 if outputs is None else outputs
    calls = []
    rois = native_rois()
    def detect(_detector, image, include_a7_support=False, *, _detail_pass=False):
        if image.shape == IMAGE.shape and not _detail_pass:
            calls.append("whole")
            result = deepcopy(whole or [{"box": BYSTANDER, "confidence": .8}])
            return (result, [], []) if include_a7_support else (result, [])
        assert _detail_pass is True and include_a7_support is False
        index = sum(c != "whole" for c in calls)
        x0, y0, x1, y1 = rois[index]
        assert image.shape == (y1-y0, x1-x0, 3)
        calls.append(list(rois[index]))
        result = deepcopy(outputs[index])
        for person in result:
            b = person["box"]
            person["box"] = {"x": (b["x"]*640 - x0)/(x1-x0),
                             "y": (b["y"]*1280 - y0)/(y1-y0),
                             "w": b["w"]*640/(x1-x0), "h": b["h"]*1280/(y1-y0)}
        return result, [{"box": OWNER, "confidence": .99, "proof_eligible": True}]
    monkeypatch.setattr(dense, "_detect_dense_people_and_ball", detect)
    monkeypatch.setattr(dense, "_default_detector", lambda: Detector())
    return calls


def frame(ms=1000, **kw):
    return {"media_ms": ms, "frame_bgr": IMAGE, "scene_id": "s",
            "time_authority": "ACTUAL_MEDIA_PTS", "used_fallback": False, **kw}


def test_default_native_refinement_finds_body_without_relabelling_bystander(monkeypatch):
    calls = install(monkeypatch)
    graph = {"frames": [{"media_ms": 1000, "scene_id": "s", "players": [
        {"local_track_id": "p018", "box": BYSTANDER}]}]}
    before = deepcopy(graph)
    selected = authority()
    selected_before = deepcopy(selected)
    result = dense.refine_window([frame()], graph, selected, "s")
    row = result["frames"][0]
    assert row["global_target"]["status"] == "VERIFIED"
    assert row["global_target"]["local_track_id"] == "p019"
    assert next(p for p in row["players"] if p["local_track_id"] == "p018")["box"] == BYSTANDER
    owner = next(p for p in row["players"] if p["local_track_id"] == "p019")
    assert owner["box"] == pytest.approx(OWNER)
    assert owner["native_body_refinement"]["independent_timestamps"] == 1
    assert owner["native_body_refinement"]["temporal_identity_authority"] is False
    assert row["ball_candidates"] == []  # ROI ball callback cannot smuggle a goal seed
    assert len(calls) == 3 and calls[0] == "whole"
    assert graph == before and selected == selected_before


def test_two_views_keep_larger_measured_box_not_an_average_or_score_winner(monkeypatch):
    other = {**OWNER, "x": OWNER["x"] + .001}
    calls = install(monkeypatch, [[{"box": OWNER, "confidence": .95}],
                                 [{"box": other, "confidence": .30}]])
    original = [{"box": deepcopy(BYSTANDER), "confidence": .8}]
    before = deepcopy(original)
    result = dense._refine_selected_native_body(Detector(), IMAGE, original, tap())
    assert result["box"] == pytest.approx(other) and result["confidence"] == .30
    assert len(calls) == 2 and original == before


def test_native_selected_body_cannot_steal_best_geometric_old_track(monkeypatch):
    install(monkeypatch)
    # An old foreground track predicts the new fragment better than its own
    # broad detection. Geometry alone must not hand that old ID to the white
    # fragment, even if the old association has no stable kit history.
    graph = {"frames": [{"media_ms": 983, "scene_id": "s", "players": [
        {"local_track_id": "p018", "box": OWNER}]}]}
    result = dense.refine_window([frame()], graph, authority(), "s")
    selected = result["frames"][0]["global_target"]
    assert selected["status"] == "VERIFIED" and selected["local_track_id"] == "p019"
    assert selected["local_track_id"] != "p018"


def test_same_selection_refinements_can_only_match_through_ordinary_measured_gates(monkeypatch):
    original = install(monkeypatch)
    detector_call = dense._detect_dense_people_and_ball
    def twice(detector, image, include_a7_support=False, *, _detail_pass=False):
        if not _detail_pass:
            original.clear()
        return detector_call(detector, image, include_a7_support, _detail_pass=_detail_pass)
    monkeypatch.setattr(dense, "_detect_dense_people_and_ball", twice)
    result = dense.refine_window([frame(983), frame(1000)], {}, authority(), "s",
                                camera_estimator=lambda *_: (np.array([[1.,0.,0.],[0.,1.,0.]]), "verified"))
    owners = [next(p for p in f["players"] if p.get("native_body_refinement")) for f in result["frames"]]
    assert owners[0]["local_track_id"] == owners[1]["local_track_id"]
    assert owners[0]["association_state"] == "NEW_LOCAL_TRACK"
    assert owners[1]["association_state"] == "VERIFIED_LOCAL"
    assert result["frames"][0]["global_target"]["proof_eligible"] is False
    assert result["frames"][1]["global_target"]["proof_eligible"] is True


@pytest.mark.parametrize("refined", [False, True])
def test_missed_fragment_cannot_reacquire_teammate_by_camera_prediction(refined):
    first = {"box": deepcopy(OWNER), "confidence": .4}
    if refined:
        first.update(body_detection_source="NATIVE_USER_SELECTION_BODY_REFINEMENT",
                     native_body_refinement={"selection_anchor_media_ms": 1000})
    rows = iter([([first], []), ([], []), ([{"box": deepcopy(OWNER), "confidence": .9}], [])])
    result = dense.refine_window([frame(1000), frame(1017), frame(1034)], {}, {}, "s",
                                detector_fn=lambda _: next(rows),
                                camera_estimator=lambda *_: (np.array([[1.,0.,0.],[0.,1.,0.]]), "verified"))
    early = result["frames"][0]["players"][0]["local_track_id"]
    late = result["frames"][2]["players"][0]["local_track_id"]
    assert (early != late) if refined else (early == late)


@pytest.mark.parametrize("existing", [
    [{"box": OWNER, "confidence": .26}],
    [{"box": OWNER, "confidence": .26}, {"box": OWNER, "confidence": .99}],
])
def test_existing_compatible_body_or_ambiguity_is_not_replaced(monkeypatch, existing):
    calls = install(monkeypatch)
    assert dense._refine_selected_native_body(Detector(), IMAGE, existing, tap()) is None
    assert calls == []


@pytest.mark.parametrize("bad", [None, {}, {"width": 96, "height": 192, "runs": [18432]}])
def test_no_usable_original_mask_means_no_roi_authority(monkeypatch, bad):
    calls = install(monkeypatch)
    selected = tap()
    selected["visible_mask"] = bad
    assert dense._refine_selected_native_body(Detector(), IMAGE, [], selected) is None
    assert calls == []


@pytest.mark.parametrize("change", [{"proof_eligible": False}, {"tap_authority": False},
                                   {"primary_source": "INTERPOLATED"}, {"target_point": None},
                                   {"target_point": {"x": .8, "y": .8}}])
def test_no_user_selection_means_no_refinement(monkeypatch, change):
    calls = install(monkeypatch)
    selected = tap()
    selected.update(change)
    assert dense._refine_selected_native_body(Detector(), IMAGE, [], selected) is None
    assert calls == []


@pytest.mark.parametrize("second", [[], [{"box": OWNER, "confidence": .24}],
    [{"box": OWNER, "confidence": .25}],
    [{"box": OWNER, "confidence": float("nan")}],
    [{"box": OWNER, "confidence": .4}, {"box": OWNER, "confidence": .99}],
    [{"box": {**OWNER, "x": .55}, "confidence": .99}]])
def test_missing_weak_ambiguous_or_other_person_view_does_not_supply_body(monkeypatch, second):
    calls = install(monkeypatch, [[{"box": OWNER, "confidence": .4}], second])
    assert dense._refine_selected_native_body(Detector(), IMAGE, [], tap()) is None
    assert len(calls) == 2


def test_disagreeing_but_point_mask_compatible_boxes_do_not_supply_body(monkeypatch):
    smaller = {"x": .441, "y": .341, "w": .053, "h": .137}
    larger = {"x": .410, "y": .310, "w": .086, "h": .179}
    calls = install(monkeypatch, [[{"box": smaller, "confidence": .4}],
                                 [{"box": larger, "confidence": .99}]])
    assert dense._refine_selected_native_body(Detector(), IMAGE, [], tap()) is None
    assert len(calls) == 2


def test_exclusion_cannot_be_overridden_by_detector_confidence(monkeypatch):
    calls = install(monkeypatch)
    selected = tap()
    selected["exclude_points"] = [{"x": .46, "y": .44}]
    assert dense._refine_selected_native_body(Detector(), IMAGE, [], selected) is None
    assert len(calls) == 1


def test_detector_authority_fields_are_not_imported(monkeypatch):
    injected = {"box": OWNER, "confidence": .4, "local_track_id": "p018",
                "team": "target_team", "proof_eligible": True, "global_target_id": "GLOBAL_TARGET"}
    install(monkeypatch, [[injected], [injected]])
    result = dense._refine_selected_native_body(Detector(), IMAGE, [], tap())
    assert not any(k in result for k in ("team", "local_track_id", "global_target_id", "proof_eligible"))


@pytest.mark.parametrize("fields", [{"used_fallback": True}, {"time_authority": "FPS_FALLBACK"},
                                    {"cut": True}, {"media_ms": 1100}])
def test_native_time_or_scene_failure_does_not_refine(monkeypatch, fields):
    calls = install(monkeypatch)
    result = dense.refine_window([frame(**fields)], {}, authority(), "s")
    assert calls == ["whole"]
    assert all(not p.get("native_body_refinement") for p in result["frames"][0]["players"])


def test_injected_detector_keeps_existing_contract_and_never_loads_real_net(monkeypatch):
    monkeypatch.setattr(dense, "_default_detector", lambda: pytest.fail("must not load a real detector"))
    result = dense.refine_window([frame()], {}, authority(), "s",
                                detector_fn=lambda _: ([{"box": BYSTANDER, "confidence": .8}], []))
    assert result["frames"][0]["global_target"]["proof_eligible"] is False
