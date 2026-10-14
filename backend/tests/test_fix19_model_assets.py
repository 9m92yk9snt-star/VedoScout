"""Real bundled CPU graphs and atomic, tamper-safe local model restoration."""
import hashlib
import json
from pathlib import Path
import shutil

import numpy as np
import pytest

from player_segmentation_assets import ensure_model_asset
from native_player_segmentation import MODEL_PATH, MODEL_SHA256, PersonSegmenter
from prompt_player_segmentation import MODEL_DIR, MODEL_HASHES, PromptSegmenter


def test_bundled_graphs_restore_exactly_and_load_on_cpu(tmp_path):
    bundle = tmp_path / 'segmentation-assets'
    shutil.copytree(MODEL_DIR / 'segmentation-assets', bundle)
    for name, expected in {MODEL_PATH.name: MODEL_SHA256, **MODEL_HASHES}.items():
        path = ensure_model_asset(tmp_path / name, expected)
        assert hashlib.sha256(path.read_bytes()).hexdigest() == expected
        assert path.stat().st_size == json.loads((bundle / 'manifest.json').read_text())['assets'][name]['bytes']
    # Exercise both real model families and decoder prompt axes. A synthetic
    # pitch has no independently identified player and must not be accepted.
    person = PersonSegmenter()
    image = np.full((160, 100, 3), [40, 110, 40], np.uint8)
    assert person.predict(image) == []
    prompt = PromptSegmenter()
    assert prompt.encoder.get_providers() == ['CPUExecutionProvider']
    assert prompt.decoder.get_providers() == ['CPUExecutionProvider']
    embedding, _, _ = prompt._embedding(image)
    assert embedding.shape == (1, 256, 64, 64) and np.isfinite(embedding).all()
    for positives, negatives in [([(50, 70)], []), ([(50, 70), (50, 100)], [(75, 50)])]:
        proposal = prompt._decode(image, positives, negatives, (20, 10, 80, 150))
        assert proposal is None or proposal.shape == image.shape[:2]
    assert prompt.predict(image, [(50, 70)], [], (20, 10, 80, 150)) is None
    assert prompt.predict(image, [(50, 70), (50, 100)], [(75, 50)], (20, 10, 80, 150)) is None


def test_corrupt_bundle_never_creates_a_runtime_graph(tmp_path):
    bundle = tmp_path / 'segmentation-assets'; bundle.mkdir()
    data = b'corrupt graph bytes'; good = b'original graph data'
    expected = hashlib.sha256(good).hexdigest()
    name = 'model.onnx'; part = name + '.part001'
    (bundle / part).write_bytes(data)
    record = {'bytes': len(data), 'sha256': expected, 'parts': [{'file': part, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}]}
    (bundle / 'manifest.json').write_text(json.dumps({'version': 1, 'assets': {name: record}}))
    with pytest.raises(ValueError, match='checksum'):
        ensure_model_asset(tmp_path / name, expected)
    assert not (tmp_path / name).exists()
    assert not list(tmp_path.glob('.player-model-*'))


def test_missing_part_and_manifest_path_escape_fail_closed(tmp_path):
    bundle = tmp_path / 'segmentation-assets'; bundle.mkdir()
    expected = hashlib.sha256(b'graph').hexdigest()
    part = {'file': 'model.onnx.part001', 'bytes': 5, 'sha256': expected}
    record = {'bytes': 5, 'sha256': expected, 'parts': [part]}
    manifest = bundle / 'manifest.json'
    manifest.write_text(json.dumps({'version': 1, 'assets': {'model.onnx': record}}))
    with pytest.raises(ValueError, match='unavailable'):
        ensure_model_asset(tmp_path / 'model.onnx', expected)
    part['file'] = '../../outside'
    manifest.write_text(json.dumps({'version': 1, 'assets': {'model.onnx': record}}))
    with pytest.raises(ValueError, match='Invalid player model part'):
        ensure_model_asset(tmp_path / 'model.onnx', expected)
    assert not (tmp_path / 'model.onnx').exists()
