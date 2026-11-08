import copy
import pytest
import match_room_reviewed_direction as module
from match_room import presentation


def event():
    return {'event_id':'e','source_video_sha256':'source','canonical_action_type':'PASS',
            'canonical_outcome':'TEAMMATE_GOAL','proof':{'proof_start_ms':1000,'proof_end_ms':1300,'frame_ms':1000},
            'reviewed_direction_review':{'start_ms':1000,'end_ms':1100}}


def test_normal_analysis_does_no_extra_work(monkeypatch):
    e=event();del e['reviewed_direction_review'];room=presentation(e);before=copy.deepcopy(room)
    monkeypatch.setattr(module,'build_reviewed_direction',lambda *a:pytest.fail('Unexpected decoding'))
    module.attach_reviewed_direction(room,e,'absent',0)
    assert room==before


def test_display_payload_attached_without_changing_assist_or_observations(monkeypatch):
    e=event();before=copy.deepcopy(e);room=presentation(e,[{'media_ms':1050,'ball':[.4,.5]}]);samples=copy.deepcopy(room['samples'])
    payload={'playback_status':'PENDING','is_measured_ball_trajectory':False,'samples':[{'media_ms':1000}]}
    monkeypatch.setattr(module,'build_reviewed_direction',lambda *a:payload)
    module.attach_reviewed_direction(room,e,'video',100)
    assert room['reviewed_direction']==payload
    assert room['reviewed_direction_diagnostics']['status']=='PENDING_PLAYBACK_REVIEW'
    assert room['samples']==samples and e==before
    assert room['action_type']=='PASS' and room['action_outcome']=='TEAMMATE_GOAL'


@pytest.mark.parametrize('change',[{'canonical_action_type':'SHOT'},{'canonical_outcome':'UNKNOWN'},
    {'reviewed_direction_review':{'start_ms':900,'end_ms':1100}}, {'reviewed_direction_review':[]}])
def test_incompatible_event_never_generates_display(monkeypatch,change):
    e={**event(),**change};room=presentation(e)
    monkeypatch.setattr(module,'build_reviewed_direction',lambda *a:pytest.fail('Unexpected decoding'))
    module.attach_reviewed_direction(room,e,'absent',0)
    assert 'reviewed_direction' not in room
    assert room['reviewed_direction_diagnostics']['status']=='REJECTED'


def test_incomplete_render_does_not_break_report_or_publish_stale_overlay(monkeypatch):
    e=event();room=presentation(e);room['reviewed_direction']={'stale':True}
    def failed(*a):raise ValueError('incomplete masks')
    monkeypatch.setattr(module,'build_reviewed_direction',failed)
    module.attach_reviewed_direction(room,e,'video',0)
    assert 'reviewed_direction' not in room
    assert room['reviewed_direction_diagnostics']['status']=='UNAVAILABLE'
    assert room['action_type']=='PASS'
