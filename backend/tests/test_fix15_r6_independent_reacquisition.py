"""Weak flow corroboration must bind independent observations and the A3 ball."""
from copy import deepcopy
import math

import pytest

import short_occlusion_contact_recovery as recovery
from test_fix10a4_short_occlusion_recovery import (
    _empty_contacts, _exact_tap_fixture, _flow_provider,
    _tap_continuity_release_fixture,
)


def node(ms, x=.4, *, strong=False):
    return {'media_ms': ms, 'box': {'x': x, 'y': .5, 'w': .02, 'h': .02},
            'a3_eligible': strong, 'proof_eligible': False}


def count(flow, detected, strong=None):
    return recovery._flow_path_match_count(
        flow, detected, required_detector_node=strong)


def test_one_detection_cannot_corroborate_two_later_flow_frames():
    flow = [node(1000), node(1017), node(1033)]
    detected = [node(1000), node(1033, strong=True)]
    assert recovery._flow_path_match_count(flow, detected) == 1


@pytest.mark.parametrize('side', ['flow', 'detected'])
def test_repeated_timestamp_does_not_supply_an_independent_observation(side):
    flow = [node(1000), node(1017), node(1033)]
    detected = [node(1000), node(1017), node(1033, strong=True)]
    if side == 'flow':
        flow[2]['media_ms'] = 1017
    else:
        detected[2]['media_ms'] = 1017
    assert recovery._flow_path_match_count(flow, detected) == 1


def test_two_distinct_measurements_still_corroborate_two_flow_frames():
    flow = [node(1000), node(1017), node(1033)]
    detected = [node(1000), node(1017), node(1033, strong=True)]
    assert count(flow, detected, detected[2]) == 2


def test_maximum_matching_is_not_a_greedy_order_dependent_count():
    # The first flow point can use either detector; the second can use only
    # the first. Reassign the first match rather than rejecting valid evidence.
    flow = [node(1000), node(1030), node(1050)]
    detected = [node(1000), node(1040), node(1010, strong=True)]
    assert count(flow, detected, detected[2]) == 2
    assert count([flow[0], *reversed(flow[1:])], detected, detected[2]) == 2


def test_unmatched_strong_ball_cannot_borrow_weak_flow_matches():
    flow = [node(1000), node(1017), node(1033)]
    detected = [node(1000), node(1017), node(1033), node(1020, .8, strong=True)]
    assert count(flow, detected) == 2
    assert count(flow, detected, detected[3]) == 0


def test_strong_ball_must_appear_in_the_detector_path():
    flow = [node(1000), node(1017), node(1033)]
    detected = [node(1000), node(1017), node(1033)]
    assert count(flow, detected, node(1033, strong=True)) == 0


def test_seed_is_not_an_independent_later_flow_match():
    assert count([node(1000), node(1040)], [node(1000), node(1000, strong=True)]) == 0


def test_same_timestamp_weak_object_cannot_stand_in_for_required_strong_object():
    flow = [node(1000), node(1017), node(1033)]
    detected = [node(1000), node(1017), node(1033), node(1033, .8, strong=True)]
    assert count(flow, detected, detected[3]) == 0


@pytest.mark.parametrize('bad', [True, 1017.5, None, math.nan, math.inf])
def test_non_actual_integer_times_cannot_supply_independent_matches(bad):
    flow = [node(1000), node(bad), node(1033)]
    detected = [node(1000), node(1017), node(1033, strong=True)]
    assert count(flow, detected, detected[2]) == 1


@pytest.mark.parametrize('ms,x,expected', [
    (1058, .4, 1), (1059, .4, 0), (1033, .449, 1), (1033, .451, 0),
])
def test_existing_time_and_distance_gates_are_not_widened(ms, x, expected):
    flow = [node(1000), node(1033)]
    detected = [node(1000), node(ms, x, strong=True)]
    assert count(flow, detected, detected[1]) == expected


def test_matching_does_not_modify_weak_support_or_any_inputs():
    flow = [node(1000), node(1017), node(1033)]
    detected = [node(1000), node(1017), node(1033, strong=True)]
    before = deepcopy((flow, detected))
    assert count(flow, detected, detected[2]) == 2
    assert (flow, detected) == before
    assert all(n['proof_eligible'] is False for n in flow + detected)


@pytest.mark.parametrize('mode', ['exact_tap', 'tap_continuity'])
def test_both_recovery_producers_reject_a_strong_ball_outside_the_flow(mode):
    frames = (_exact_tap_fixture() if mode == 'exact_tap'
              else _tap_continuity_release_fixture())
    # An intermediate weak measurement can be reused by both later optical
    # samples. The strong endpoint is beyond .05, yet inside the broader
    # detector continuity gate: the old producer wrongly bound the two paths.
    final = frames[-1]['a7_ball_support_candidates'][0]
    final['box']['x'] = .65 - final['box']['w']/2
    middle = deepcopy(frames[-2])
    middle['media_ms'] = (frames[-2]['media_ms'] + frames[-1]['media_ms']) // 2
    middle['players'][0]['box']['x'] = (frames[-2]['players'][0]['box']['x']
                                       + frames[-1]['players'][0]['box']['x']) / 2
    middle['a7_ball_support_candidates'] = [{
        'box': {'x': .602-.015, 'y': .64-.01, 'w': .03, 'h': .02},
        'confidence': .008, 'support_only': True, 'proof_eligible': False,
    }]
    frames.insert(-1, middle)
    before = deepcopy(frames)
    result = recovery.recover_short_occlusion_contacts(
        frames, [], _empty_contacts(), video_path='synthetic.mp4',
        flow_frame_provider=_flow_provider())
    forbidden = ('EXACT_TARGET_SUPPORT_PATH' if mode == 'exact_tap'
                 else 'TAP_CONTINUITY_SUPPORT_RELEASE')
    assert not any(r.get('recovery_mode') == forbidden for r in result['verified'])
    assert frames == before


def test_source_shaped_endpoint_cannot_be_certified_by_one_reused_weak_measurement():
    # Anonymised local geometry; no reference event or player label is used.
    flow = [node(1000, .405634765625), node(1017, .4057753849),
            node(1033, .4083016363)]
    flow[0]['box'].update(w=.03333984375, h=.0171875, y=.6359375)
    flow[1]['box'].update(w=.03333984375, h=.0171875, y=.6360578898)
    flow[2]['box'].update(w=.03333984375, h=.0171875, y=.6364579615)
    strong = node(1017, .3472900390625, strong=True)
    strong['box'].update(w=.027783203125, h=.0140625, y=.640625)
    weak = node(1033, .350068359375)
    weak['box'].update(w=.083349609375, h=.015625, y=.640625)
    detected = [deepcopy(flow[0]), strong, weak]
    assert recovery._flow_path_match_count(flow, detected) == 1
    assert count(flow, detected, strong) == 0
