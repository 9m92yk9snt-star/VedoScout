"""Native pixel-work reuse, never identity/event approval or model perception."""
import ast
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from contextvars import copy_context
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

import cv_detect as cv
import dense_track_refinement as dense
import football_scene_graph as graph


def head():
    raw = np.zeros((1, 84, 100), np.float32)
    raw[0, :4, :5] = np.array([[100, 200, 300, 400, 500], [200]*5, [30]*5, [50]*5])
    raw[0, 4, 0] = .8
    raw[0, 36, 1] = .4
    raw[0, 36, 2] = .04
    raw[0, 6, 3] = .3  # Other top class must not hide class-32 support.
    raw[0, 36, 3] = .002
    raw[0, 36, 4] = .0009
    return raw


class Net:
    def __init__(self):
        self.calls = 0

    def setInput(self, tensor):
        self.tensor = tensor

    def forward(self):
        self.calls += 1
        return head()


def detector():
    instance = cv.PersonDetector.__new__(cv.PersonDetector)
    instance.net, instance.ok, instance.model_sha256 = Net(), True, 'a'*64
    return instance


@contextmanager
def scope(cache):
    token = cv.CURRENT_PREDICTIONS.set(cache)
    try:
        yield
    finally:
        cv.CURRENT_PREDICTIONS.reset(token)


IMAGE = np.zeros((480, 640, 3), np.uint8)


def readers(d, image=IMAGE):
    return (d.detect(image), graph._detect_people_and_ball(d, image),
            dense._detect_dense_people_and_ball(d, image, include_a7_support=True))


def test_identity_scene_and_dense_readers_share_exact_inference_with_independent_thresholds():
    expected = readers(detector())
    d, cache = detector(), cv.PredictionCache()
    with scope(cache):
        observed = readers(d)
    assert observed == expected
    assert d.net.calls == 1 and cache.metrics()['hits'] == 2
    assert len(observed[1][1]) == 1 and len(observed[2][1]) == 2
    assert any(b['top_class_id'] == 2 for b in observed[2][2])
    assert all(b['proof_eligible'] is False for b in observed[2][2])


def test_different_detector_instances_reuse_values_without_sharing_results_or_decisions():
    first, second, cache = detector(), detector(), cv.PredictionCache()
    with scope(cache):
        rows = cv.predict(first, IMAGE)
        rows.xywh[:] = -100
        cached = cv.predict(second, IMAGE.copy())
        cached.xywh[:] = -200
        clean = readers(second)
    assert first.net.calls == 1 and second.net.calls == 0
    assert clean == readers(detector())


@pytest.mark.parametrize('change', ['pixel', 'shape', 'model', 'person_threshold', 'ball_floor', 'input_size'])
def test_changed_source_or_model_settings_cannot_reuse_old_predictions(monkeypatch, change):
    d, cache, image = detector(), cv.PredictionCache(), IMAGE.copy()
    with scope(cache):
        cv.predict(d, image)
        kwargs = {}
        if change == 'pixel': image[0, 0, 0] = 1
        elif change == 'shape': image = image.reshape(640, 480, 3)
        elif change == 'model': d.model_sha256 = 'b'*64
        elif change == 'person_threshold': monkeypatch.setattr(cv, 'CONF_T', .3)
        elif change == 'ball_floor': kwargs['ball_floor'] = .0001
        else: monkeypatch.setattr(cv, 'INPUT', 320)
        cv.predict(d, image, **kwargs)
    assert d.net.calls == 2 and cache.metrics()['hits'] == 0


def test_failed_or_unidentified_network_is_not_cached():
    d, cache = detector(), cv.PredictionCache()
    class Flaky(Net):
        def forward(self):
            self.calls += 1
            if self.calls == 1: raise RuntimeError('native failure')
            return head()
    d.net = Flaky()
    with scope(cache):
        with pytest.raises(RuntimeError, match='native failure'): cv.predict(d, IMAGE)
        cv.predict(d, IMAGE)
        assert d.net.calls == 2
        d.model_sha256 = None
        cv.predict(d, IMAGE); cv.predict(d, IMAGE)
    assert d.net.calls == 4 and cache.metrics()['hits'] == 0


def test_payload_and_entries_remain_bounded_and_reports_do_not_share_cache():
    d, cache = detector(), cv.PredictionCache(max_bytes=4096, max_entries=2)
    with scope(cache):
        for value in (0, 1, 2, 0): cv.predict(d, np.full_like(IMAGE, value))
    assert cache.metrics()['entries'] == 2 and cache.metrics()['evictions'] == 2
    assert cache.metrics()['payload_bytes'] <= 4096 and d.net.calls == 4
    with scope(cv.PredictionCache(max_bytes=1)):
        cv.predict(d, IMAGE); cv.predict(d, IMAGE)
    assert d.net.calls == 6
    with scope(cv.PredictionCache()): cv.predict(d, IMAGE)
    assert d.net.calls == 7 and cv.CURRENT_PREDICTIONS.get() is None


def test_concurrent_identical_requests_spend_one_forward_and_return_separate_arrays():
    d, cache = detector(), cv.PredictionCache()
    with scope(cache), ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(copy_context().run, cv.predict, d, IMAGE) for _ in range(8)]
        results = [f.result() for f in futures]
    assert d.net.calls == 1 and cache.metrics()['hits'] == 7
    results[0].xywh[:] = -1
    assert all(np.all(row.xywh >= 0) for row in results[1:])


async def test_report_noop_restores_outer_context_and_preserves_previous_metrics():
    # Run the real task's early return/finally without server startup or DB.
    tree = ast.parse((Path(__file__).resolve().parents[1] / 'server.py').read_text())
    task = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == 'generate_full_report_task')
    updates = []
    async def find_one(*_a): return None
    async def update_one(*a): updates.append(a)
    namespace = {'db': SimpleNamespace(reports=SimpleNamespace(find_one=find_one, update_one=update_one))}
    exec(compile(ast.Module(body=[task], type_ignores=[]), 'server_task', 'exec'), namespace)
    outer = cv.PredictionCache()
    with scope(outer):
        await namespace['generate_full_report_task']('missing')
        assert cv.CURRENT_PREDICTIONS.get() is outer
    assert updates == []
