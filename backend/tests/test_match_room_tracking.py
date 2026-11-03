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
    event={'canonical_ms':1000,'event_id':'e','source_video_sha256':'source','visual_samples':observations(),
           'proof':{'proof_start_ms':1000,'proof_end_ms':1200,'frame_ms':1000,'frame_id':'f'}}
    full={'video_comments':[{'event_id':'e','sequence_event_native':True,'source_video_sha256':'source',
           'evidence_time_ms':1000,'source_frame_id':'f','evidence_id':'proof'}]}
    tracks={'e':{'version':1,'event_id':'e','source_video_sha256':'source','segments':[]}}
    with tempfile.TemporaryDirectory() as directory, patch.dict(sys.modules,{'cv2':fake_cv,'video_timebase':fake_time,'media_binaries':types.SimpleNamespace(FFMPEG_BIN='ffmpeg')}), patch.object(tracking,'bounded_tracks',return_value=(tracks,'COMPLETED')) as build, patch.object(subprocess,'run'):
        namespace['render_assets']('video',full,{'source_video_sha256':'source','events':[event]},directory,[{'t':1}])
        assert build.call_args.args[1]==[{'t':1}]
        room=full['video_comments'][0]['match_room']
        assert room['tracking']==tracks['e']
        assert room['samples']==event['visual_samples']
