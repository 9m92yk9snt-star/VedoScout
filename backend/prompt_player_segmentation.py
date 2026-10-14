"""Bounded visible-pixel segmentation from human include/exclude points."""
from pathlib import Path
from collections import OrderedDict
import hashlib
import threading

import cv2
import numpy as np

MODEL_DIR = Path(__file__).resolve().parent / "models"
MODEL_HASHES = {
    "mobile-sam-encoder.onnx": "85dc9194671a1173fc5632fc1ffae698f3ca0c82c7b208ed618a568377380d7e",
    "mobile-sam-decoder.onnx": "43c7655a81b62c0f2b0e31d2bc91d3811b48d7f736ecf93b3a4a1254318241cf",
}
_LOCK = threading.Lock()
_MODEL = None


def choose_prompt_mask(masks, scores, positives, negatives, *, prefer_largest=False):
    """Reject any model alternative contradicting a human pixel hint."""
    from native_player_segmentation import _point_in_mask
    valid = []
    for index, (mask, score) in enumerate(zip(masks, scores)):
        if (not np.isfinite(score) or score < .5 or not np.isfinite(mask).all()
                or not all(_point_in_mask(mask > 0, p) for p in positives)
                or any(_point_in_mask(mask > 0, p) for p in negatives)):
            continue
        valid.append(index)
    if not valid:
        return None
    # For a foreground exclusion, choose the broadest supported object outline
    # rather than a high-scoring shirt-only alternative.
    best = max(valid, key=lambda i: (int(np.count_nonzero(masks[i] > 0)), float(scores[i]))) if prefer_largest else max(valid, key=lambda i: float(scores[i]))
    return (masks[best] > 0).astype(np.uint8)


class PromptSegmenter:
    def __init__(self):
        import onnxruntime as ort
        for filename, expected in MODEL_HASHES.items():
            path = MODEL_DIR / filename
            if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
                raise ValueError("Player prompt-model checksum mismatch")
        options = ort.SessionOptions()
        options.intra_op_num_threads = 2
        options.inter_op_num_threads = 1
        self.encoder = ort.InferenceSession(str(MODEL_DIR / "mobile-sam-encoder.onnx"),
                                          options, providers=["CPUExecutionProvider"])
        self.decoder = ort.InferenceSession(str(MODEL_DIR / "mobile-sam-decoder.onnx"),
                                          options, providers=["CPUExecutionProvider"])
        self.cache = OrderedDict()

    def _embedding(self, image):
        key = (image.shape, hashlib.sha256(image.tobytes()).hexdigest())
        if key in self.cache:
            self.cache.move_to_end(key)
            return self.cache[key]
        h, w = image.shape[:2]
        scale = 1024 / max(h, w)
        nw, nh = int(w * scale + .5), int(h * scale + .5)
        rgb = cv2.cvtColor(cv2.resize(image, (nw, nh)), cv2.COLOR_BGR2RGB).astype(np.float32)
        rgb = (rgb - np.array([123.675, 116.28, 103.53], np.float32)) / np.array([58.395, 57.12, 57.375], np.float32)
        tensor = np.zeros((1, 3, 1024, 1024), np.float32)
        tensor[0, :, :nh, :nw] = rgb.transpose(2, 0, 1)
        embedding = self.encoder.run(None, {"images": tensor})[0]
        self.cache[key] = (embedding, nw / w, nh / h)
        while len(self.cache) > 2:
            self.cache.popitem(last=False)
        return self.cache[key]

    def _decode(self, image, positives, negatives, bounds, *, prefer_largest=False):
        embedding, sx, sy = self._embedding(image)
        points = [*positives, *negatives, bounds[:2], bounds[2:]]
        labels = [1.] * len(positives) + [0.] * len(negatives) + [2., 3.]
        coords = np.asarray(points, np.float32) * np.asarray([sx, sy], np.float32)
        masks, scores, _ = self.decoder.run(None, {
            "image_embeddings": embedding,
            "point_coords": coords[None], "point_labels": np.asarray([labels], np.float32),
            "mask_input": np.zeros((1, 1, 256, 256), np.float32),
            "has_mask_input": np.zeros(1, np.float32),
            "orig_im_size": np.asarray(image.shape[:2], np.float32),
        })
        return choose_prompt_mask(masks[0], scores[0], positives, negatives, prefer_largest=prefer_largest)

    def predict(self, image, positives, negatives, bounds):
        mask = self._decode(image, positives, negatives, bounds)
        if mask is None:
            return None
        # A negative identifies the foreground object, not only a tiny hole at
        # that point. Decode its outline with the target points excluded, then
        # remove all of its visible pixels from the behind-player suggestion.
        for point in negatives:
            blocker = self._decode(image, [point], positives, (0, 0, image.shape[1], image.shape[0]), prefer_largest=True)
            if blocker is None:
                return None
            mask[blocker > 0] = 0
        from native_player_segmentation import _point_in_mask
        return mask if all(_point_in_mask(mask, p) for p in positives) else None


def segment_visible_player(image, positives, negatives, bounds):
    global _MODEL
    with _LOCK:
        if _MODEL is None:
            _MODEL = PromptSegmenter()
        return _MODEL.predict(image, positives, negatives, bounds), dict(MODEL_HASHES)
