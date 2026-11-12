import asyncio
import json
import hashlib
from copy import deepcopy
from pathlib import Path
import sys
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from match_room_asset import publish_graphics


def test_large_graphics_round_trip_without_precision_loss(tmp_path):
    room={'version':1,'event_id':'e','source_video_sha256':'source','start_ms':1,'end_ms':3,
          'tracking':{'samples':[{'media_ms':i,'polygon':[[.123456789,.987654321]]*100} for i in range(7000)]}}
    row={'match_room':deepcopy(room)}
    async def publish(path,mime):
        assert mime=='application/json'
        assert json.loads(path.read_bytes())==room
        return '/asset.json'
    asyncio.run(publish_graphics(row,tmp_path,publish))
    ref=row['match_room']['graphics_asset']
    data=(tmp_path/('graphics-'+ref['sha256']+'.json')).read_bytes()
    assert len(data)>16_000_000
    assert hashlib.sha256(data).hexdigest()==ref['sha256']
    assert len(json.dumps(row))<1000
    assert json.loads(data)==room


def test_failed_upload_keeps_original_and_never_returns_reference(tmp_path):
    row={'match_room':{'samples':['x'*200000]}};before=deepcopy(row)
    async def publish(*a):return None
    with pytest.raises(RuntimeError,match='GRAPHICS_PUBLISH_FAILED'):
        asyncio.run(publish_graphics(row,tmp_path,publish))
    assert row==before


def test_small_graphics_remain_inline(tmp_path):
    row={'match_room':{'version':1,'samples':[]}};before=deepcopy(row)
    async def forbidden(*a):pytest.fail('Small graphics should stay inline')
    asyncio.run(publish_graphics(row,tmp_path,forbidden));assert row==before


def test_graphics_route_restores_exact_file_and_rejects_unbound_requests(tmp_path):
    import ast
    from types import SimpleNamespace
    source=(Path(__file__).resolve().parents[1]/'server.py').read_text()
    tree=ast.parse(source);node=next(n for n in tree.body if isinstance(n,ast.AsyncFunctionDef) and n.name=='report_graphics_asset');node.decorator_list=[]
    payload=b'{"graphics":"exact"}';sha=hashlib.sha256(payload).hexdigest()
    class NotFound(Exception):pass
    class Collection:
        async def find_one(self,*a):return {'full_report':{'video_comments':[{'match_room':{'graphics_asset':{'sha256':sha}}}]}}
    calls=[]
    def download(key,path):calls.append(key);path.write_bytes(payload);return True
    ns={'Path':Path,'asyncio':asyncio,'os':__import__('os'),'db':SimpleNamespace(reports=Collection()),
        'HTTPException':NotFound,'FileResponse':lambda path,**kw:path,
        '_analysis_frames_dir':lambda rid:tmp_path/rid,
        'r2_storage':SimpleNamespace(is_configured=lambda:True,download_to_file=download)}
    exec(compile(ast.Module(body=[node],type_ignores=[]),'<route>','exec'),ns)
    rid='c74d5920-0219-4d9f-a01a-66f6605db0b1'
    path=asyncio.run(ns['report_graphics_asset'](rid,sha));assert path.read_bytes()==payload
    assert len(calls)==1
    asyncio.run(ns['report_graphics_asset'](rid,sha));assert len(calls)==1
    with pytest.raises(NotFound):asyncio.run(ns['report_graphics_asset'](rid,'f'*64))
    with pytest.raises(NotFound):asyncio.run(ns['report_graphics_asset']('../secret',sha))
    assert len(calls)==1


def test_final_database_write_contains_reference_not_large_graphics(tmp_path, monkeypatch):
    import sequence_report_runtime as runtime
    room={'version':1,'event_id':'e','source_video_sha256':'source','tracking':{'data':'x'*17_000_000}}
    doc={'id':'r','full_report':{'video_comments':[{'event_id':'e'}]}}
    def render(video,full,*a,**kw):
        full['video_comments'][0]['match_room']=room
        return [(full['video_comments'][0],tmp_path/'frame.jpg',tmp_path/'clip.mp4')]
    async def localizer(*a,**kw):return {}
    async def publish(path,mime):return '/assets/'+path.name
    writes=[]
    class Collection:
        async def update_one(self,query,update):
            assert len(json.dumps(update))<16000000, 'update command document too large'
            writes.append(update)
    monkeypatch.setattr(runtime,'render_assets',render)
    monkeypatch.setattr(runtime,'compute_proof_frame_verified',lambda row:True)
    asyncio.run(runtime.persist_assets(Collection(),doc,'source.mp4',tmp_path,publish,localizer=localizer))
    final=writes[-1]['$set'];assert final['full_report_status']=='finalizing'
    assert 'graphics_asset' in final['full_report']['video_comments'][0]['match_room']
    assert 'match_room' not in doc['full_report']['video_comments'][0]
