"""Exact, temporary prediction reuse within one report's contour workers.

No nearest-frame reuse, mask propagation, identity inference or model changes.
The parent owns and removes the directory after all child workers finish.
"""
import hashlib
import importlib.metadata
import json
import os
import zipfile
from pathlib import Path

import cv2
import numpy as np

MAX_BYTES = 64 * 1024 * 1024


class CachedSegmenter:
    def __init__(self, model, directory, source_sha):
        self.model, self.sha256 = model, model.sha256
        self.directory = Path(directory)
        engine = os.environ.get('SCOUTMEPLAY_MATCHROOM_ENGINE', 'opencv')
        runtime = importlib.metadata.version('onnxruntime') if engine == 'onnxruntime' else cv2.__version__
        self.namespace = json.dumps(['v1', source_sha, self.sha256, engine, runtime, cv2.__version__, np.__version__]).encode()
        self.hits = 0
        self.misses = 0

    def predict(self, image):
        key = hashlib.sha256(self.namespace + str((image.shape, image.dtype.str)).encode() + image.tobytes()).hexdigest()
        path = self.directory / (key + '.npz')
        try:
            with np.load(path, allow_pickle=False) as data:
                meta = json.loads(str(data['meta']))
                shape = tuple(int(x) for x in data['shape'])
                if (str(data['key']) != key or len(shape) != 3 or not 0 <= shape[0] <= 24
                        or shape[1:] != image.shape[:2] or len(meta) != shape[0]):
                    raise ValueError('Invalid prediction cache')
                masks = np.unpackbits(data['bits'], count=int(np.prod(shape))).reshape(shape)
                rows = [{**row, 'box': tuple(row['box']), 'mask': mask.copy()}
                        for row, mask in zip(meta, masks)]
            self.hits += 1
            return rows
        except (OSError, ValueError, KeyError, EOFError, zipfile.BadZipFile):
            pass
        self.misses += 1
        rows = self.model.predict(image)
        # Cache failure must never turn successful inference into a failure.
        try:
            if sum(p.stat().st_size for p in self.directory.glob('*.npz')) < MAX_BYTES:
                masks = np.stack([r['mask'] for r in rows]) if rows else np.empty((0, *image.shape[:2]), np.uint8)
                meta = [{k: v for k, v in row.items() if k != 'mask'} for row in rows]
                temporary = path.with_suffix('.tmp')
                with temporary.open('wb') as stream:
                    np.savez_compressed(stream, key=key, meta=json.dumps(meta), shape=masks.shape, bits=np.packbits(masks))
                used = sum(p.stat().st_size for p in self.directory.glob('*.npz'))
                if used + temporary.stat().st_size <= MAX_BYTES:
                    temporary.replace(path)
                else:
                    temporary.unlink()
        except (OSError, ValueError, TypeError):
            pass
        return rows
