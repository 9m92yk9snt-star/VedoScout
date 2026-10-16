"""Local per-person outline suggestions bound to one uploaded still.

No identity inference, hidden-body reconstruction, model download or report
write. The user must confirm each suggestion before it becomes an anchor.
"""
from pathlib import Path
from io import BytesIO
import hashlib
import threading

import cv2
import numpy as np
from PIL import Image

from player_selection import valid_box, valid_point, valid_image_shape, valid_mask
from player_segmentation_assets import ensure_model_asset

MODEL_PATH = Path(__file__).resolve().parent / "models" / "yolov8n-seg.onnx"
MODEL_SHA256 = "015043fb9cc94830ad7065dd3e28d6f8e5758fe03071451675120f6a6b6e44e9"
INPUT = 640
_LOCK = threading.Lock()
_MODEL = None


class PersonSegmenter:
    def __init__(self):
        self.net = None
        self.sha256 = None
        ensure_model_asset(MODEL_PATH, MODEL_SHA256)
        self.sha256 = MODEL_SHA256
        self.net = cv2.dnn.readNetFromONNX(str(MODEL_PATH))
        self.net.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
        self.net.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)

    def predict(self, image):
        if self.net is None:
            return []
        height, width = image.shape[:2]
        scale = INPUT / max(height, width)
        nw, nh = max(1, round(width * scale)), max(1, round(height * scale))
        padded = np.full((INPUT, INPUT, 3), 114, dtype=np.uint8)
        padded[:nh, :nw] = cv2.resize(image, (nw, nh))
        self.net.setInput(cv2.dnn.blobFromImage(padded, 1 / 255.0, (INPUT, INPUT), swapRB=True))
        outputs = self.net.forward(self.net.getUnconnectedOutLayersNames())
        detections = next((a for a in outputs if a.ndim == 3), None)
        prototypes = next((a for a in outputs if a.ndim == 4), None)
        if (detections is None or prototypes is None or detections.shape[1] != 116
                or prototypes.shape[1] != 32):
            return []
        rows = detections[0].T
        classes = rows[:, 4:84]
        labels = classes.argmax(axis=1)
        keep = ((labels == 0) | (labels == 32)) & (classes.max(axis=1) >= .35)
        rows = rows[keep]
        labels = labels[keep]
        boxes = [[float(r[0] - r[2] / 2), float(r[1] - r[3] / 2), float(r[2]), float(r[3])] for r in rows]
        scores = [float(r[4 + label]) for r, label in zip(rows, labels)]
        indices = []
        for label in (0, 32):
            group = [i for i, value in enumerate(labels) if value == label]
            picked = cv2.dnn.NMSBoxes([boxes[i] for i in group], [scores[i] for i in group], .35, .7)
            indices.extend(group[int(i)] for i in np.asarray(picked).reshape(-1))
        result = []
        for index in np.asarray(indices).reshape(-1)[:24]:
            row, box = rows[index], boxes[index]
            logits = row[84:] @ prototypes[0].reshape(32, -1)
            probabilities = 1 / (1 + np.exp(-np.clip(logits, -30, 30)))
            probabilities = cv2.resize(probabilities.reshape(prototypes.shape[2:]), (INPUT, INPUT))[:nh, :nw]
            mask = (cv2.resize(probabilities, (width, height)) >= .5).astype(np.uint8)
            x0, y0 = max(0, int(box[0] / scale)), max(0, int(box[1] / scale))
            x1 = min(width, int(np.ceil((box[0] + box[2]) / scale)))
            y1 = min(height, int(np.ceil((box[1] + box[3]) / scale)))
            bounded = np.zeros_like(mask)
            bounded[y0:y1, x0:x1] = mask[y0:y1, x0:x1]
            if x1 > x0 and y1 > y0:
                result.append({"box": (x0, y0, x1 - x0, y1 - y0),
                               "mask": bounded, "score": scores[index], "class_id": int(labels[index])})
        return result


def _instances(image):
    global _MODEL
    # OpenCV nets have mutable inference buffers; both load and use are locked.
    with _LOCK:
        if _MODEL is None:
            _MODEL = PersonSegmenter()
        return _MODEL.predict(image), _MODEL.sha256


def _point_in_mask(mask, point):
    x, y = point
    x, y = int(round(x)), int(round(y))
    if not 0 <= x < mask.shape[1] or not 0 <= y < mask.shape[0]:
        return False
    return bool(mask[y, x])


def _rle(binary, method="native_person_instance"):
    flat = binary.reshape(-1)
    edges = np.flatnonzero(np.diff(flat)) + 1
    runs = np.diff(np.r_[0, edges, flat.size]).astype(int).tolist()
    if flat[0]:
        runs.insert(0, 0)
    return {"width": 96, "height": 192, "runs": runs, "method": method}


def suggest_person_cutout(image_bytes, box, target, exclude_points=(), include_points=(),
                          *, player_behind=False, auto_box=True):
    """Suggest only the visible pixels of the instance at the human's point.

    A rectangle alone cannot identify a hidden player. In behind mode a visible
    target point is required and foreground instances marked in red are removed
    in their entirety. Disconnected visible limbs are retained from that same
    instance; hidden pixels are never synthesised or filled.
    """
    if not valid_box(box) or not valid_point(target):
        raise ValueError("Mark the area and tap a visible part of your player")
    if not box["x"] <= target["x"] <= box["x"] + box["w"] or not box["y"] <= target["y"] <= box["y"] + box["h"]:
        raise ValueError("Tap inside the marked player area")
    with Image.open(BytesIO(image_bytes)) as header:
        if header.format not in ("JPEG", "PNG") or not valid_image_shape(header.width, header.height):
            raise ValueError("Frame too large")
    image = cv2.imdecode(np.frombuffer(image_bytes, np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("Unreadable frame")
    height, width = image.shape[:2]
    sx, sy = int(box["x"] * width), int(box["y"] * height)
    ex, ey = min(width, round((box["x"] + box["w"]) * width)), min(height, round((box["y"] + box["h"]) * height))
    if ex - sx < 6 or ey - sy < 12:
        return {"status": "unavailable", "reason": "too_small"}
    # Zoom only this bounded context, so a distant child remains large enough
    # for the person model. No adjacent video frame or identity label is used.
    px, py = max(8, ex - sx), max(12, (ey - sy) // 2)
    rx, ry = max(0, sx - px), max(0, sy - py)
    re, rb = min(width, ex + px), min(height, ey + py)
    roi = image[ry:rb, rx:re]
    def local(point):
        return (min(width - 1, point["x"] * width) - rx,
                min(height - 1, point["y"] * height) - ry)
    positive = [target] + [p for p in (include_points or [])[:4] if valid_point(p)]
    negative = [p for p in (exclude_points or [])[:4] if valid_point(p)]
    method = "native_person_instance"
    if player_behind:
        from prompt_player_segmentation import segment_visible_player
        binary, model_sha = segment_visible_player(
            roi, [local(p) for p in positive], [local(p) for p in negative],
            (sx - rx, sy - ry, ex - rx, ey - ry))
        if binary is None:
            return {"status": "unavailable", "reason": "behind_player_not_isolated"}
        method = "native_person_prompt"
        body = None
    else:
        instances, model_sha = _instances(roi)
        candidates = [i for i, instance in enumerate(instances)
                      if instance.get("class_id", 0) == 0 and all(_point_in_mask(instance["mask"], local(p)) for p in positive)]
        if len(candidates) != 1:
            return {"status": "unavailable", "reason": "no_visible_person" if not candidates else "ambiguous_person"}
        chosen = candidates[0]
        binary = instances[chosen]["mask"].copy()
        for point in negative:
            blockers = [i for i, instance in enumerate(instances) if instance.get("class_id", 0) == 0 and _point_in_mask(instance["mask"], local(point))]
            if chosen in blockers:
                return {"status": "unavailable", "reason": "points_overlap"}
            if len(blockers) != 1:
                return {"status": "unavailable", "reason": "occluder_not_resolved"}
            binary[instances[blockers[0]]["mask"] > 0] = 0
        if not all(_point_in_mask(binary, local(p)) for p in positive):
            return {"status": "unavailable", "reason": "target_not_visible"}
        body = instances[chosen]["box"]
    # A sports-ball outline is never a body part. Remove its measured visible
    # pixels even when the ball touches a hand or boot in the player proposal.
    objects = _instances(roi)[0] if player_behind else instances
    for item in objects:
        if item.get("class_id", 0) == 32:
            binary[item["mask"] > 0] = 0
    if not all(_point_in_mask(binary, local(p)) for p in positive) or any(_point_in_mask(binary, local(p)) for p in negative):
        return {"status": "unavailable", "reason": "point_conflict"}
    ys, xs = np.nonzero(binary)
    if len(xs) < 20:
        return {"status": "unavailable", "reason": "too_few_visible_pixels"}
    if not player_behind and (ys.max() - ys.min() + 1) / max(1, body[3]) < .65:
        return {"status": "unavailable", "reason": "partial_outline"}
    if auto_box and not player_behind:
        # Fit the measured person outline, including head, arms and feet.
        # Small context padding remains background in the returned mask.
        sx, ex = max(0, rx + int(xs.min()) - 2), min(width, rx + int(xs.max()) + 3)
        sy, ey = max(0, ry + int(ys.min()) - 2), min(height, ry + int(ys.max()) + 3)
    canvas = np.zeros((height, width), np.uint8)
    canvas[ry:rb, rx:re] = binary
    selected = canvas[sy:ey, sx:ex]
    fraction = float(selected.mean())
    if fraction < .01 or fraction > .96:
        return {"status": "unavailable", "reason": "cannot_separate"}
    mask = _rle(cv2.resize(selected, (96, 192), interpolation=cv2.INTER_NEAREST), method)
    if not valid_mask(mask):
        return {"status": "unavailable", "reason": "complex_mask"}
    return {"status": "suggested", "mask": mask,
            "box": {"x": sx / width, "y": sy / height, "w": (ex - sx) / width, "h": (ey - sy) / height},
            "player_behind": bool(player_behind), "visible_only": True,
            "model_sha256": model_sha, "frame_sha256": hashlib.sha256(image_bytes).hexdigest()}
