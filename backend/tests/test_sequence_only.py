"""Production retirement boundaries, using actual server code and offline runtimes."""
import ast
import asyncio
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.run_sequence_report_trial import server_harness

SERVER = Path(__file__).resolve().parents[1] / 'server.py'


def test_retired_orchestrators_and_runtime_imports_are_physically_absent():
    tree = ast.parse(SERVER.read_text())
    names = {n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    assert not names & {
        '_continue_identity_analysis', '_verify_doubt_taps', '_verify_enriched_frames',
        '_cross_verify_full_report', '_run_identity_corrective_pass', '_corrective_only_recovery',
        '_compose_full_prompt', '_telestrate_verified_frames', '_generate_tele_clips',
        '_teleclip_verified_window', '_identity_gate_required',
    }
    imports = {a.name for n in tree.body if isinstance(n, ast.Import) for a in n.names}
    assert not imports & {'fix10a_runtime', 'fix10b_runtime', 'player_identity_timeline'}
    worker = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == 'generate_full_report_task')
    source = ast.unparse(worker)
    assert 'sequence_report_runtime.enabled()' not in source
    assert 'sequence_report_runtime.generate(' in source
    assert 'call_gemini_with_video(' not in source
    assert 'track_player(' not in source
    assert 'cv_shadow.run_shadow(' not in source


def test_paid_preflight_skips_all_three_preview_model_stages():
    """Execute the actual guarded paid preflight, with no provider globals available.

    Accidentally invoking the free preview/profile/clip path fails with NameError.
    """
    tree = ast.parse(SERVER.read_text())
    worker = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == 'analyze_preview_task')
    statements = next(n for n in worker.body if isinstance(n, ast.Try)).body
    guards = [deepcopy(n) for n in statements if isinstance(n, ast.If) and (
        'identity_profile_task = asyncio.ensure_future' in ast.unparse(n)
        or 'preview_clip_path = await' in ast.unparse(n)
        or 'paid_preview_skipped_sequence' in ast.unparse(n))]
    assert len(guards) == 3
    stages = []

    async def trace(report_id, stage):
        stages.append((report_id, stage))

    function = ast.parse('async def preflight(doc, report_id, anchor_crop_paths):\n    pass').body[0]
    function.body = guards + [ast.Return(value=ast.Name(id='preview', ctx=ast.Load()))]
    ns = {'_trace': trace}
    exec(compile(ast.fix_missing_locations(ast.Module(body=[function], type_ignores=[])), 'paid-preflight', 'exec'), ns)
    assert asyncio.run(ns['preflight']({'is_paid': True}, 'paid-report', ['original-tap.jpg'])) == {'assessment_status': 'deferred_to_sequence'}
    assert stages == [('paid-report', 'paid_preview_skipped_sequence')]
    # Free uploads must retain the separate preview flow rather than silently bypassing it.
    with pytest.raises(NameError, match='asyncio'):
        asyncio.run(ns['preflight']({'is_paid': False}, 'free-report', ['original-tap.jpg']))


@pytest.mark.parametrize('status', ['failed', 'generating', 'verifying', 'finalizing'])
def test_incomplete_legacy_body_never_calls_a_model_or_becomes_ready(tmp_path, status):
    original = {'summary': 'Historical report; not verified by Sequence'}
    doc = {'id': 'legacy', 'full_report_status': status, 'full_report': deepcopy(original)}
    ns, store, _, _ = server_harness(tmp_path / 'absent.mp4', doc, tmp_path, runtime=SimpleNamespace())
    asyncio.run(ns['generate_full_report_task']('legacy'))
    assert store.doc['full_report_status'] == 'failed'
    assert store.doc['full_report'] == original
    assert store.doc['full_report_error'] == 'LEGACY_INCOMPLETE_REPORT_REQUIRES_NEW_SEQUENCE_ANALYSIS'
    assert 'ready' not in store.states


@pytest.mark.parametrize('status', ['ready', None])
def test_completed_archived_reports_remain_available_without_reanalysis(tmp_path, status):
    full = {'summary': 'Saved historical report', 'video_comments': [{'frame_url': '/saved.jpg'}]}
    doc = {'id': 'archived', 'full_report': deepcopy(full)}
    if status:
        doc['full_report_status'] = status
    ns, store, _, _ = server_harness(tmp_path / 'absent.mp4', doc, tmp_path, runtime=SimpleNamespace())
    asyncio.run(ns['generate_full_report_task']('archived'))
    assert store.doc['full_report_status'] == 'ready'
    assert store.doc['full_report'] == full


def test_sequence_without_status_cannot_bypass_missing_asset_checks(tmp_path):
    doc = {'id': 'sequence', 'analysis_engine': 'SEQUENCE_V1', 'full_report': {'summary': 'Unpublished'}}
    ns, store, _, _ = server_harness(tmp_path / 'absent.mp4', doc, tmp_path, runtime=SimpleNamespace())
    asyncio.run(ns['generate_full_report_task']('sequence'))
    assert store.doc['full_report_status'] == 'failed'
    assert 'ready' not in store.states


@pytest.mark.parametrize('engine,status,expected', [
    ('LEGACY', 'ready', 409), ('SEQUENCE_V1', 'generating', 409),
    ('SEQUENCE_V1', 'ready', None), ('SEQUENCE_V1', 'failed', None),
])
def test_asset_repair_keeps_saved_urls_and_uses_the_leased_worker(tmp_path, engine, status, expected):
    from scripts.run_sequence_report_trial import ReportStore

    class HttpError(Exception):
        def __init__(self, status_code, detail):
            self.status_code = status_code

    class RepairStore(ReportStore):
        async def update_one(self, query, update):
            if self.doc['full_report_status'] in query['full_report_status']['$nin']:
                return SimpleNamespace(matched_count=0)
            await super().update_one({'id': self.doc['id']}, update)
            return SimpleNamespace(matched_count=1)

    doc = {'id': 'repair', 'analysis_engine': engine, 'full_report_status': status,
           'full_report': {'video_comments': [{'frame_url': '/saved.jpg', 'tele_clip_url': '/saved.mp4'}]}}
    store = RepairStore(doc)
    lease, scheduled, executed = object(), [], []

    async def local(_):
        return tmp_path / 'source.mp4'

    async def claim(collection, report_id, **kwargs):
        assert collection is store and store.doc['full_report_status'] == 'failed'
        return lease

    async def leased_worker(report_id, admitted_lease):
        executed.append((report_id, admitted_lease))

    ns = {'db': SimpleNamespace(reports=store), 'HTTPException': HttpError,
          'Depends': lambda _: None, 'get_current_admin': None,
          '_ensure_report_video_local': local, 'FULL_REPORT_STALL_SECONDS': 1200,
          'analysis_jobs': SimpleNamespace(IN_FLIGHT=('generating', 'verifying', 'finalizing'), claim=claim),
          '_full_report_with_heartbeat': leased_worker,
          'asyncio': SimpleNamespace(create_task=lambda coroutine: scheduled.append(coroutine))}
    node = deepcopy(next(n for n in ast.parse(SERVER.read_text()).body
                         if isinstance(n, ast.AsyncFunctionDef) and n.name == 'admin_regenerate_evidence'))
    node.decorator_list = []
    exec(compile(ast.Module(body=[node], type_ignores=[]), 'admin-evidence-repair', 'exec'), ns)

    async def run():
        if expected:
            with pytest.raises(HttpError) as error:
                await ns['admin_regenerate_evidence']('repair')
            assert error.value.status_code == expected
            assert not scheduled
        else:
            assert await ns['admin_regenerate_evidence']('repair') == {'started': True, 'cleared_frames': 0}
            assert len(scheduled) == 1
            await scheduled[0]
            assert executed == [('repair', lease)]

    asyncio.run(run())
    assert store.doc['full_report'] == doc['full_report']


def test_sequence_watchdog_limits_apply_to_every_production_admission():
    tree = ast.parse(SERVER.read_text())
    expected = {'FULL_REPORT_STALL_SECONDS': 180, 'FULL_REPORT_MAX_RUN_SECONDS': 1800,
                'FULL_REPORT_MAX_RETRIES': 1}
    values = {n.targets[0].id: eval(compile(ast.Expression(n.value), 'watchdog-constant', 'eval'), {})
              for n in tree.body if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name)
              and n.targets[0].id in expected}
    assert values == expected
    claims = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
              and isinstance(n.func.value, ast.Name) and n.func.value.id == 'analysis_jobs' and n.func.attr == 'claim']
    assert len(claims) == 4
    for claim in claims:
        bound = next(k.value for k in claim.keywords if k.arg == 'stall_seconds')
        assert isinstance(bound, ast.Name) and bound.id == 'FULL_REPORT_STALL_SECONDS'


def test_paid_metadata_preview_is_prepared_without_player_claims():
    from analysis_progress import analysis_progress
    progress = analysis_progress({'is_paid': True, 'analysis_status': 'ready',
                                  'preview': {'assessment_status': 'deferred_to_sequence'}})
    assert progress['preview_ready'] is True
    assert progress['analysis_complete'] is False
    assert progress['analysis_phase'] == 'queued'
