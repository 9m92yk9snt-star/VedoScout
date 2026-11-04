import ast
from pathlib import Path
import pytest


def validator():
    tree = ast.parse((Path(__file__).parents[1]/'sequence_report_runtime.py').read_text())
    function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'validate_rendered_clip')
    namespace = {}
    exec(compile(ast.Module(body=[function], type_ignores=[]), '<clip-validator>', 'exec'), namespace)
    return namespace['validate_rendered_clip']


def test_unfinished_mp4_cannot_be_published_as_ready(tmp_path):
    path = tmp_path/'unfinished.mp4'
    path.write_bytes(bytes.fromhex('000000206674797069736f6d0000020069736f6d69736f32617663316d7034310000000866726565000000006d646174'))
    with pytest.raises(ValueError, match='SEQUENCE_CLIP_DECODE_FAILED'):
        validator()(path)


def test_corrupt_final_picture_is_rejected_and_decoder_is_closed(monkeypatch):
    import cv2
    import numpy as np
    class Capture:
        closed = False
        calls = 0
        def get(self, key): return 10
        def set(self, key, value): assert value == 9
        def read(self):
            self.calls += 1
            return (True, np.zeros((2,2,3))) if self.calls == 1 else (False, None)
        def release(self): self.closed = True
    capture = Capture()
    monkeypatch.setattr(cv2, 'VideoCapture', lambda *a: capture)
    with pytest.raises(ValueError, match='SEQUENCE_CLIP_DECODE_FAILED'):
        validator()('unused')
    assert capture.closed
