from copy import deepcopy
import subprocess
import sys
import tempfile
import match_room_tracking as tracking


def points(times=(1., 1.08, 1.16)):
    return [dict(t=t, x=.4, y=.3, w=.1, h=.3, conf=.8) for t in times]


def observations():
    return [dict(media_ms=1080, ground=[.45,.59], frame_id='source1')]


def test_no_identity_bridge_without_same_action_ground_observation():
    assert tracking.bind_segments(points(), [], 900, 2000) == []
    bad = [dict(media_ms=1080, ground=[.8,.7], frame_id='other')]
    assert tracking.bind_segments(points(), bad, 900, 2000) == []


def test_calibrated_proxy_preserves_input_and_splits_gaps():
    p=points((1,1.08,1.16,1.6,1.68,1.76));before=deepcopy(p)
    rows=tracking.bind_segments(p, observations(), 900, 2000)
    assert len(rows)==1 and len(rows[0]['samples'])==3
    assert rows[0]['samples'][1]['ground']==[.45,.59]
    assert p==before


def test_later_conflicting_observation_rejects_whole_segment():
    obs=observations()+[dict(media_ms=1160,ground=[.8,.6],frame_id='source2')]
    assert tracking.bind_segments(points(), obs, 900, 2000)==[]


def test_camera_only_motion_has_no_arrow_and_leftward_motion_stays_leftward():
    group=tracking.bind_segments(points(), observations(), 900, 2000)[0]
    motion=dict(w=1000,h=1000,samples=[dict(t0=1.,t1=1.08,ok=True,rx=0,ry=0),dict(t0=1.08,t1=1.16,ok=True,rx=-10,ry=0)])
    tracking.add_motion(group,motion)
    assert 'groundTrail' not in group['samples'][1]
    arrow=group['samples'][2]['groundTrail']
    assert arrow[1][0]<arrow[0][0]


def test_unknown_camera_and_missing_interval_do_not_create_arrows():
    group=tracking.bind_segments(points(), observations(), 900, 2000)[0]
    tracking.add_motion(group,dict(w=100,h=100,samples=[dict(t0=1.,t1=1.08,ok=False),dict(t0=.5,t1=1.16,ok=True,rx=10,ry=0)]))
    assert all('groundTrail' not in s for s in group['samples'])


def test_timeout_returns_sparse_fallback(monkeypatch):
    def timeout(*args,**kwargs):
        assert kwargs['timeout']==25
        raise subprocess.TimeoutExpired('tracking',25)
    monkeypatch.setattr(tracking.subprocess,'run',timeout)
    assert tracking.bounded_tracks('video',[{'t':1}],[{'visual_samples':[{}]}])==({},'TRACKING_UNAVAILABLE')


def test_no_samples_means_no_process(monkeypatch):
    monkeypatch.setattr(tracking.subprocess,'run',lambda *a,**k: (_ for _ in ()).throw(AssertionError('called')))
    assert tracking.bounded_tracks('video',[{'t':1}],[{}])==({},'NO_TRACK_INPUT')


def test_timeout_preserves_atomically_completed_graphics(monkeypatch):
    import json
    from pathlib import Path
    completed={'event':{'event_id':'event','segments':[]}}
    def timeout(command, **kwargs):
        Path(command[-1]).write_text(json.dumps(completed))
        raise subprocess.TimeoutExpired('tracking',25)
    monkeypatch.setattr(tracking.subprocess,'run',timeout)
    assert tracking.bounded_tracks('video',[{'t':1}],[{'visual_samples':[{}]}])==(completed,'PARTIAL_TIMEOUT')


def test_asset_renderer_attaches_event_bound_tracks_without_changing_samples():
    import ast
    import types
    from pathlib import Path
    from unittest.mock import patch
    tree=ast.parse((Path(__file__).parents[1]/'sequence_report_runtime.py').read_text())
    function=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='render_assets')
    namespace={'Path':Path,'pilot':types.SimpleNamespace(digest=lambda p:'source'),
               'attach_clip_authority':lambda *args:None}
    exec(compile(ast.Module(body=[function],type_ignores=[]),'<renderer>','exec'),namespace)
    cap=types.SimpleNamespace(release=lambda:None)
    fake_cv=types.SimpleNamespace(VideoCapture=lambda p:cap,imwrite=lambda *a:True)
    fake_time=types.SimpleNamespace(read_frame_at=lambda *a:(True,object(),1.))
    event={'canonical_action_type':'DRIBBLE','canonical_ms':1000,'event_id':'e','source_video_sha256':'source','visual_samples':observations(),
           'proof':{'proof_start_ms':1000,'proof_end_ms':1200,'frame_ms':1000,'frame_id':'f'}}
    full={'video_comments':[{'event_id':'e','sequence_event_native':True,'source_video_sha256':'source',
           'evidence_time_ms':1000,'source_frame_id':'f','evidence_id':'proof'}]}
    enhanced=[{**observations()[0], 'motion_method':'BACKGROUND_AFFINE_ENDPOINTS', 'motion_start_ms':1000, 'groundTrail':[[.4,.59],[.45,.59]]},
              {'frame_id':'ball-source','media_ms':1200,'ball':[.6,.7],'ball_motion_method':'BACKGROUND_AFFINE_BALL_ENDPOINTS','ball_motion_start_ms':1080,'ballTrail':[[.5,.7],[.6,.7]]}]
    tracks={'e':{'version':1,'event_id':'e','source_video_sha256':'source','segments':[], 'observed_samples':enhanced}}
    with tempfile.TemporaryDirectory() as directory, patch.dict(sys.modules,{'cv2':fake_cv,'video_timebase':fake_time,'media_binaries':types.SimpleNamespace(FFMPEG_BIN='ffmpeg')}), patch.object(tracking,'bounded_tracks',return_value=(tracks,'COMPLETED')) as build, patch.object(subprocess,'run'):
        namespace['render_assets']('video',full,{'source_video_sha256':'source','events':[event]},directory,[{'t':1}])
        assert build.call_args.args[1]==[{'t':1}]
        room=full['video_comments'][0]['match_room']
        assert room['tracking']==tracks['e']
        assert room['samples']==enhanced
        assert event['visual_samples']==observations()
        assert [s['media_ms'] for s in room['stops']]==[1000,1200]
        assert room['stops'][-1]['label']=='Ball movement'


def test_endpoint_arrow_removes_camera_pan_and_keeps_player_direction():
    a={'media_ms':1000,'ground':[.4,.8]};b={'media_ms':1200,'ground':[.5,.8]}
    camera=[[1,0,100],[0,1,0],[0,0,1]]
    assert tracking.endpoint_arrow(a,b,camera,1000,1000) is None
    b['ground']=[.47,.8]
    tail,tip=tracking.endpoint_arrow(a,b,camera,1000,1000)
    assert tail==[.5,.8] and tip[0]<tail[0]


def test_endpoint_arrows_reject_long_gaps_and_invalid_transforms():
    a={'media_ms':1000,'ground':[.4,.8]};b={'media_ms':2200,'ground':[.5,.8]}
    identity=[[1,0,0],[0,1,0],[0,0,1]]
    assert tracking.endpoint_arrow(a,b,identity,1000,1000) is None
    b['media_ms']=1200
    assert tracking.endpoint_arrow(a,b,[[float('nan')]*3]*3,1000,1000) is None
    assert tracking.endpoint_arrow(a,b,identity,0,1000) is None


def test_intermediate_camera_failure_does_not_make_endpoint_arrow():
    import numpy as np
    from unittest.mock import patch
    import player_tracking
    import motion_compensation
    import cv2
    frames=[(t,np.zeros((100,100),dtype=np.uint8),None,None) for t in (1.,1.033,1.067,1.1)]
    obs=[{'media_ms':1000,'ground':[.4,.8],'player_width':.1},
         {'media_ms':1100,'ground':[.5,.8],'player_width':.1}]
    cap=type('Cap',(),{'release':lambda self:None})()
    with patch.object(cv2,'VideoCapture',return_value=cap), patch.object(player_tracking,'_read_window',return_value=frames), patch.object(player_tracking,'_cut_flags',return_value=[False]*4), patch.object(motion_compensation,'estimate_camera',side_effect=[(np.array([[1.,0,0],[0,1.,0]]),20),(None,'features')]):
        result=tracking.observed_motion('video',obs)
    assert all('groundTrail' not in row for row in result)
    assert all('groundTrail' not in row for row in obs)


def test_ball_endpoints_use_their_own_positions_and_shorter_interval():
    a={'media_ms':1000,'ground':[.4,.8],'ball':[.6,.7]}
    b={'media_ms':1200,'ground':[.55,.8],'ball':[.65,.7]}
    camera=[[1,0,100],[0,1,0],[0,0,1]]
    assert tracking.endpoint_arrow(a,b,camera,1000,1000)[1][0] > .5
    tail,tip=tracking.endpoint_arrow(a,b,camera,1000,1000,field='ball',max_gap=300)
    assert tail == [.7,.7] and tip[0] < tail[0]
    b['ball']=[.7,.7]
    assert tracking.endpoint_arrow(a,b,camera,1000,1000,field='ball',max_gap=300) is None
    b.update(media_ms=1400,ball=[.65,.7])
    assert tracking.endpoint_arrow(a,b,camera,1000,1000,field='ball',max_gap=300) is None
    b.update(media_ms=1200); b.pop('ball')
    assert tracking.endpoint_arrow(a,b,camera,1000,1000,field='ball',max_gap=300) is None


def test_ball_only_observations_work_without_player_geometry_and_fail_on_camera_loss():
    import numpy as np
    from unittest.mock import patch
    import player_tracking, motion_compensation, cv2
    frames=[(t,np.zeros((100,100),dtype=np.uint8),None,None) for t in (1.,1.033,1.067,1.1)]
    obs=[{'media_ms':1000,'ball':[.6,.7]}, {'media_ms':1100,'ball':[.5,.7]}]
    cap=type('Cap',(),{'release':lambda self:None})()
    camera=np.array([[1.,0,0],[0,1.,0]])
    with patch.object(cv2,'VideoCapture',return_value=cap), patch.object(player_tracking,'_read_window',return_value=frames), patch.object(player_tracking,'_cut_flags',return_value=[False]*4), patch.object(motion_compensation,'estimate_camera',return_value=(camera,20)) as estimate:
        result=tracking.observed_motion('video',obs)
        assert result[1]['ballTrail']==[[.6,.7],[.5,.7]]
        assert result[1]['ball_motion_start_ms']==1000
        assert 'groundTrail' not in result[1]
        estimate.side_effect=[(camera,20),(None,'features')]
        assert all('ballTrail' not in row for row in tracking.observed_motion('video',obs))
    assert all('ballTrail' not in row for row in obs)


def test_pass_direction_requires_release_receiver_and_camera_proof(monkeypatch):
    event={'canonical_action_type':'PASS','canonical_outcome':'COMPLETED','contact_ms':1000,
           'causal_chain':{'receiver_visual_id':'p7'},'proof':{'proof_start_ms':900,'proof_end_ms':2500}}
    obs=[{'frame_id':'release','media_ms':1000,'ball':[.6,.7],'ball_phase':'RELEASE'},
         {'frame_id':'reception','media_ms':1800,'ball':[.2,.7],'ball_phase':'RECEIVED','receiver':'p7',
          'ballTrail':[[.3,.7],[.2,.7]],'ball_motion_method':'BACKGROUND_AFFINE_BALL_ENDPOINTS'}]
    monkeypatch.setattr(tracking,'observed_motion',lambda video,rows,**kwargs: rows)
    assert tracking.pass_motion('video',event,obs) == obs  # no old arrow promoted on camera failure
    def measured(video,rows,**kwargs):
        assert kwargs == {'ball_gap_ms':2000, 'separate_bands':True}
        return [rows[0],{**rows[1],'ballTrail':[[.5,.7],[.2,.7]]}]
    monkeypatch.setattr(tracking,'observed_motion',measured)
    assert tracking.pass_motion('video',event,obs)[1]['ball_motion_method']=='BACKGROUND_AFFINE_PASS_ENDPOINTS'
    for change in [{'canonical_action_type':'DRIBBLE'},{'canonical_outcome':'INCOMPLETE'},{'contact_ms':1300},{'causal_chain':{'receiver_visual_id':'other'}}]:
        assert tracking.pass_motion('video',{**event,**change},obs) == obs
    assert tracking.pass_motion('video',event,[obs[0],{**obs[1],'media_ms':3300}])[1]['ball_motion_method']=='BACKGROUND_AFFINE_BALL_ENDPOINTS'


def test_foreground_includes_people_not_ball_and_preserves_offset():
    import numpy as np
    from match_room_tracking import foreground_polygons
    mask = np.zeros((60, 80), dtype=np.uint8)
    mask[10:50, 20:40] = 1
    rows = [{'class_id': 0, 'mask': mask}, {'class_id': 32, 'mask': np.ones_like(mask)}]
    polygons = foreground_polygons(rows, 80, 100, 20)
    assert len(polygons) == 1
    assert all(0 <= x <= 1 and .2 <= y <= .8 for x, y in polygons[0])
    assert foreground_polygons(rows[1:], 80, 100, 20) is None


def test_distinct_clips_have_separate_budgets_and_duplicate_cards_share_results(monkeypatch):
    calls=[]
    def run(video,anchors,events):
        calls.append(events[0]['event_id'])
        return {events[0]['event_id']:{'segments':[]}},'COMPLETED'
    monkeypatch.setattr(tracking,'_bounded_event',run)
    a={'event_id':'a','visual_samples':[{}]};b={'event_id':'b','visual_samples':[{}]}
    result,status=tracking.bounded_tracks('video',[{'t':1}],[a,a,b,a,b])
    assert calls==['a','b'] and set(result)=={'a','b'} and status=='COMPLETED'


def test_ball_only_events_do_not_require_unrelated_player_anchors(monkeypatch):
    event = {'event_id':'ball', 'visual_samples':[{'media_ms':1000,'ball':[.4,.7]}]}
    calls = []
    def run(video, anchors, events):
        calls.append((anchors, events))
        return {'ball': {'ball_playback': []}}, 'COMPLETED'
    monkeypatch.setattr(tracking, '_bounded_event', run)
    result, status = tracking.bounded_tracks('video', [], [event])
    assert status == 'COMPLETED' and result == {'ball': {'ball_playback': []}}
    assert calls == [([], [event])]


def test_refinement_preserves_initial_paths_and_ball_evidence_with_separate_budget(monkeypatch):
    from copy import deepcopy
    method = 'SOURCE_OBSERVATION_INSTANCE_CONTOUR'
    events = [{'event_id': e, 'source_video_sha256':'source', 'localization_method':'EXPLICIT_SOURCE_POSITIONS',
               'visual_samples':[{}]} for e in ('covered','missing1','missing2','missing3','missing4')]
    originals = {e['event_id']:{'event_id':e['event_id'], 'source_video_sha256':'source', 'method':method,
                  'segments':[{'id':'original'}] if e['event_id']=='covered' else [],
                  'ball_playback':[{'id':'ball-'+e['event_id']}], 'observed_samples':[{'identity_status':'UNCERTAIN'}]}
                 for e in events}
    originals['missing2']['contour_diagnostics'] = {'windows':[{'status':'TIME_BUDGET'}]}
    calls = []
    def run(video, anchors, batch, *, refinement=False):
        eid = batch[0]['event_id']; calls.append((eid,refinement))
        if not refinement: return {eid:deepcopy(originals[eid])}, 'COMPLETED'
        return {eid:{'event_id':eid, 'source_video_sha256':'source', 'method':method,
                     'segments':[{'id':'measured'}], 'ball_playback':[{'id':'must-not-replace'}]}}, 'COMPLETED'
    monkeypatch.setattr(tracking, '_bounded_event', run)
    result, status = tracking.bounded_tracks('video', [], events)
    assert calls == [(e['event_id'],False) for e in events]+[('missing2','small'),('missing1','medium'),('missing3','medium')]
    assert result['covered'] == originals['covered']
    assert result['missing4'] == originals['missing4']
    for eid in ('missing1','missing2','missing3'):
        assert result[eid]['segments'] == [{'id':'measured'}]
        assert result[eid]['ball_playback'] == originals[eid]['ball_playback']
        assert result[eid]['observed_samples'] == originals[eid]['observed_samples']
    assert status == 'COMPLETED' and tracking.TIMEOUT_S == 25


def test_failed_refinement_keeps_original_evidence(monkeypatch):
    event = {'event_id':'e','source_video_sha256':'source','localization_method':'EXPLICIT_SOURCE_POSITIONS','visual_samples':[{}]}
    original = {'event_id':'e','source_video_sha256':'source','method':'SOURCE_OBSERVATION_INSTANCE_CONTOUR',
                'segments':[], 'ball_playback':[{'id':'measured-ball'}]}
    def run(video, anchors, events, *, refinement=False):
        return ({}, 'TRACKING_UNAVAILABLE') if refinement else ({'e':original.copy()}, 'COMPLETED')
    monkeypatch.setattr(tracking, '_bounded_event', run)
    result, status = tracking.bounded_tracks('video', [], [event])
    assert result['e'] == original and status == 'TRACKING_PARTIAL'
