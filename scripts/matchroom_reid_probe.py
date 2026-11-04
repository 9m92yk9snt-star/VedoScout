"""Offline appearance reacquisition experiment, not imported by report workers.

Download the public Open Model Zoo 0287 source ONNX separately; this module has
no downloader or telemetry runtime. Supply original measured crops/masks. Match
scores are cosine similarities, not calibrated probabilities. A proposal does
not establish any hidden position, foot contact, or report identity authority.
"""
from pathlib import Path
import hashlib
import cv2
import numpy as np

SOURCE_SHA384 = 'c650c97722d597efd65fe041d67e17658d776c45d56736b817264ec544d8a9b5a5e8cdc1a0920cc2aada61151c1a9191'


def prepare_opencv_model(source, destination):
    """Make source MVN numerics match published FP32 IR (epsilon inside sqrt).

    The source ONNX has 12 MeanVarianceNormalization operations without an
    epsilon and can emit NaNs. The official FP32 IR uses 1e-5 INSIDE_SQRT.
    Weights are unchanged. Preprocessing is applied by AppearanceProbe.
    """
    import onnx
    from onnx import helper, numpy_helper
    source = Path(source)
    if hashlib.sha384(source.read_bytes()).hexdigest() != SOURCE_SHA384:
        raise ValueError('Unexpected public source model')
    model = onnx.load(str(source))
    replacements, count = [], 0
    for node in model.graph.node:
        if node.op_type != 'MeanVarianceNormalization':
            replacements.append(node)
            continue
        axes = list(next(a.ints for a in node.attribute if a.name == 'axes'))
        prefix = f'stable_mvn_{count}'
        count += 1
        model.graph.initializer.append(numpy_helper.from_array(
            np.array(1e-5, np.float32), prefix+'_epsilon'))
        def op(kind, inputs, suffix, **attributes):
            return helper.make_node(kind, inputs, [prefix+suffix], **attributes)
        replacements.extend([
            op('ReduceMean', [node.input[0]], '_mean', axes=axes, keepdims=1),
            op('Sub', [node.input[0], prefix+'_mean'], '_center'),
            op('Mul', [prefix+'_center', prefix+'_center'], '_squared'),
            op('ReduceMean', [prefix+'_squared'], '_variance', axes=axes, keepdims=1),
            op('Add', [prefix+'_variance', prefix+'_epsilon'], '_stable'),
            op('Sqrt', [prefix+'_stable'], '_std'),
            helper.make_node('Div', [prefix+'_center', prefix+'_std'], list(node.output)),
        ])
    if count != 12:
        raise ValueError('Unexpected normalization graph')
    del model.graph.node[:]
    model.graph.node.extend(replacements)
    onnx.checker.check_model(model)
    onnx.save(model, str(destination))
    return hashlib.sha256(Path(destination).read_bytes()).hexdigest()


class AppearanceProbe:
    def __init__(self, model_path, expected_sha256):
        if hashlib.sha256(Path(model_path).read_bytes()).hexdigest() != expected_sha256:
            raise ValueError('Unexpected prepared model')
        self.net = cv2.dnn.readNetFromONNX(str(model_path))

    def embedding(self, image, mask=None, rotation=0):
        if image.size == 0:
            raise ValueError('Empty crop')
        image = image.copy()
        if mask is not None:
            if mask.shape != image.shape[:2] or not np.any(mask):
                raise ValueError('Invalid source mask')
            image[mask == 0] = 114
        image = np.rot90(image, rotation).copy()
        rgb = cv2.cvtColor(cv2.resize(image, (128,256)), cv2.COLOR_BGR2RGB).astype(np.float32)
        rgb = (rgb-np.array([123.675,116.28,103.53], np.float32))/np.array([58.395,57.12,57.375], np.float32)
        self.net.setInput(rgb.transpose(2,0,1)[None])
        value = self.net.forward().reshape(-1)
        norm = np.linalg.norm(value)
        if value.shape != (256,) or not np.isfinite(value).all() or norm <= 0:
            raise ValueError('Invalid appearance vector')
        return value/norm


def reciprocal_choice(scores, reference_index):
    """Require a unique best match in both directions; no nearest-only fallback."""
    scores = np.asarray(scores)
    if scores.ndim != 2 or not scores.shape[1] or not np.isfinite(scores).all():
        return None
    row = scores[reference_index]
    candidate = int(np.argmax(row))
    if np.count_nonzero(row == row[candidate]) != 1:
        return None
    column = scores[:,candidate]
    if (int(np.argmax(column)) != reference_index or
            np.count_nonzero(column == column[reference_index]) != 1):
        return None
    return candidate


def consensus_choice(raw_scores, masked_scores, reference_index):
    """Background-present and source-mask-only views must choose the same instance."""
    a = reciprocal_choice(raw_scores, reference_index)
    b = reciprocal_choice(masked_scores, reference_index)
    return a if a is not None and a == b else None


def stable_proposal(samples):
    """Require one measured track across >=5 matches and >=200ms.

    Caller supplies independently linked track IDs, not per-frame row numbers.
    This returns only a research proposal, never an interpolated ground point.
    """
    run = []
    for sample in samples:
        if sample.get('track_id') is None:
            run = []
            continue
        if run and (sample['track_id'] != run[-1]['track_id'] or
                    not 0 < sample['media_ms']-run[-1]['media_ms'] <= 100):
            run = []
        run.append(sample)
        if len(run) >= 5 and run[-1]['media_ms']-run[0]['media_ms'] >= 200:
            return {'track_id': run[-1]['track_id'], 'from_ms': run[0]['media_ms'],
                    'confirmed_ms': run[-1]['media_ms'], 'samples': len(run),
                    'report_identity_approved': False}
    return None


def replay_validation(path):
    """Re-evaluate recorded scores, without rerunning inference or source video."""
    import json
    evidence = json.loads(Path(path).read_text())
    results = evidence['details']['results']
    checked = []
    for stamp in sorted({r['ms'] for r in results}):
        modes = [next(r for r in results if r['ms'] == stamp and r['masked'] == mode)
                 for mode in (False, True)]
        target = modes[0]['target']
        matrices = []
        for mode in modes:
            matrix = np.empty((len(mode['forward']), len(mode['forward'][0]['ranking'])))
            for reference in mode['forward']:
                for item in reference['ranking']:
                    matrix[reference['reference_at_31'],item['candidate']] = item['cosine']
            matrices.append(matrix)
        selected = consensus_choice(*matrices, evidence['target_reference_index'])
        remaining = [k for k in range(matrices[0].shape[1]) if k != target]
        absent = consensus_choice(matrices[0][:,remaining], matrices[1][:,remaining],
                                  evidence['target_reference_index'])
        checked.append({'media_ms': stamp, 'correct': selected == target,
                        'target_absent_rejected': absent is None})
    return {'kind': 'cached_score_replay', 'checked': checked,
            'report_identity_approved': False}


if __name__ == '__main__':
    import argparse
    import json
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--validation', required=True, help='Saved source-score validation JSON')
    arguments = parser.parse_args()
    print(json.dumps(replay_validation(arguments.validation), indent=2))
