"""Bounded, human-confirmed selection hints. No model calls or persistence.

Partial boxes describe visible pixels, never the hidden player's full body.
Masks are box-relative binary RLE, not transferable to another video frame.
"""
from copy import deepcopy
import math


def number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def valid_box(box):
    return (isinstance(box, dict) and all(number(box.get(k)) for k in ("x", "y", "w", "h"))
            and box["x"] >= 0 and box["y"] >= 0 and box["w"] > 0 and box["h"] > 0
            and box["x"] + box["w"] <= 1.00001 and box["y"] + box["h"] <= 1.00001)


def valid_point(point):
    return isinstance(point, dict) and all(number(point.get(k)) and 0 <= point[k] <= 1 for k in ("x", "y"))


def valid_mask(mask):
    if not isinstance(mask, dict) or mask.get("width") != 96 or mask.get("height") != 192:
        return False
    runs = mask.get("runs")
    return (isinstance(runs, list) and 2 <= len(runs) <= 8192
            and all(isinstance(n, int) and not isinstance(n, bool) and n >= 0 for n in runs)
            and sum(runs) == 96 * 192 and sum(runs[1::2]) >= 20)


def selection_metadata(anchor):
    """Whitelist bounded human hints; legacy anchors remain untouched."""
    if not isinstance(anchor, dict):
        return {}
    out = {}
    if anchor.get("visibility") == "partial":
        out["visibility"] = "partial"
    if valid_point(anchor.get("target_point")):
        out["target_point"] = {k: float(anchor["target_point"][k]) for k in ("x", "y")}
    if isinstance(anchor.get("include_points"), list):
        out["include_points"] = [{k: float(p[k]) for k in ("x", "y")} for p in anchor["include_points"][:4] if valid_point(p)]
    negatives = anchor.get("exclude_points")
    if isinstance(negatives, list):
        out["exclude_points"] = [{k: float(p[k]) for k in ("x", "y")} for p in negatives[:4] if valid_point(p)]
        box = anchor.get("box")
        if valid_box(box) and any(box["x"] <= p["x"] <= box["x"] + box["w"] and box["y"] <= p["y"] <= box["y"] + box["h"] for p in out["exclude_points"]):
            out["visibility"] = "partial"
    if valid_mask(anchor.get("visible_mask")):
        out["visible_mask"] = deepcopy(anchor["visible_mask"])
    check = anchor.get("tracking_check")
    if (isinstance(check, dict) and check.get("status") == "user_confirmed"
            and number(check.get("start")) and number(check.get("end")) and 0 < check["end"] - check["start"] <= 0.7):
        out["tracking_check"] = {"status": "user_confirmed", "start": check["start"], "end": check["end"]}
    links = []
    for link in (anchor.get("continuity") or [])[:2] if isinstance(anchor.get("continuity"), list) else []:
        if (isinstance(link, dict) and link.get("same_player") is True and number(anchor.get("t"))
                and number(link.get("t")) and 0.02 <= abs(link["t"] - anchor["t"]) <= 0.7
                and link.get("segment") == anchor.get("segment") and valid_box(link.get("box"))
                and selection_metadata({k: v for k, v in link.items() if k != "continuity"}).get("visibility") != "partial"):
            links.append({"t": link["t"], "box": deepcopy(link["box"]), "segment": link.get("segment"),
                          "same_player": True, **selection_metadata({k: v for k, v in link.items() if k != "continuity"})})
    if links:
        out["continuity"] = links
    return out


def expanded_anchors(anchors):
    out = []
    for anchor in (anchors or [])[:16]:
        if not isinstance(anchor, dict):
            continue
        row = {**{k: v for k, v in anchor.items() if k not in ("target_point", "include_points", "exclude_points", "visible_mask", "continuity", "tracking_check")}, **selection_metadata(anchor)}
        out.append(row)
        for link in selection_metadata(anchor).get("continuity", []):
            out.append({**link, "human_continuity": True})
    return out


def full_body_anchors(anchors):
    return [a for a in expanded_anchors(anchors) if a.get("visibility") != "partial"]


def decode_mask(mask):
    import numpy as np
    if not valid_mask(mask):
        return None
    flat = np.zeros(96 * 192, dtype=np.uint8)
    pos = 0
    for i, run in enumerate(mask["runs"]):
        if i % 2:
            flat[pos:pos + run] = 255
        pos += run
    return flat.reshape(192, 96)


def valid_image_shape(width, height):
    return (32 <= width <= 4096 and 32 <= height <= 4096 and width * height <= 3000000
            and 0.1 <= width / height <= 10)


def suggest_mask(image_bytes, box, target, exclude_points, include_points=None):
    """CPU GrabCut suggestion on a small crop, anchored to human points.

    This is not semantic person recognition. Caller must display for approval.
    It may fail on similar kits/blur; never substitute a rectangular mask.
    """
    import cv2
    import numpy as np
    if not valid_box(box) or not valid_point(target):
        raise ValueError("Invalid player selection")
    if not (box["x"] <= target["x"] <= box["x"] + box["w"] and box["y"] <= target["y"] <= box["y"] + box["h"]):
        raise ValueError("Tap inside your player box")
    # Check image dimensions before allocating the decompressed image.
    from PIL import Image
    from io import BytesIO
    with Image.open(BytesIO(image_bytes)) as header:
        if header.format not in ("JPEG", "PNG") or not valid_image_shape(header.width, header.height):
            raise ValueError("Frame too large")
    image = cv2.imdecode(np.frombuffer(image_bytes, np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("Unreadable frame")
    height, width = image.shape[:2]
    x0, y0 = int(box["x"] * width), int(box["y"] * height)
    x1, y1 = min(width, round((box["x"] + box["w"]) * width)), min(height, round((box["y"] + box["h"]) * height))
    if x1 - x0 < 6 or y1 - y0 < 12:
        return {"status": "unavailable", "reason": "too_small"}
    crop = cv2.resize(image[y0:y1, x0:x1], (96, 192))
    # A surrounding background border gives GrabCut real background samples.
    padded = cv2.copyMakeBorder(crop, 4, 4, 4, 4, cv2.BORDER_REPLICATE)
    labels = np.full(padded.shape[:2], cv2.GC_BGD, np.uint8)
    labels[4:-4, 4:-4] = cv2.GC_PR_FGD
    def pixel(p):
        return (4 + min(95, max(0, round((p["x"] - box["x"]) / box["w"] * 95))),
                4 + min(191, max(0, round((p["y"] - box["y"]) / box["h"] * 191))))
    px, py = pixel(target)
    cv2.circle(labels, (px, py), 2, cv2.GC_FGD, -1)
    positives = [(px, py)]
    for point in (include_points or [])[:4]:
        if valid_point(point) and box["x"] <= point["x"] <= box["x"] + box["w"] and box["y"] <= point["y"] <= box["y"] + box["h"]:
            positives.append(pixel(point)); cv2.circle(labels, positives[-1], 2, cv2.GC_FGD, -1)
    for point in exclude_points[:4]:
        if not valid_point(point):
            continue
        if box["x"] <= point["x"] <= box["x"] + box["w"] and box["y"] <= point["y"] <= box["y"] + box["h"]:
            nx, ny = pixel(point)
            if any(math.hypot(nx - sx, ny - sy) < 6 for sx, sy in positives):
                return {"status": "unavailable", "reason": "points_overlap"}
            cv2.circle(labels, (nx, ny), 4, cv2.GC_BGD, -1)
    cv2.grabCut(padded, labels, None, np.zeros((1, 65), np.float64), np.zeros((1, 65), np.float64), 3, cv2.GC_INIT_WITH_MASK)
    binary = ((labels == cv2.GC_FGD) | (labels == cv2.GC_PR_FGD)).astype(np.uint8)[4:-4, 4:-4]
    _, components = cv2.connectedComponents(binary)
    selected = {int(components[sy - 4, sx - 4]) for sx, sy in positives} - {0}
    if not selected:
        return {"status": "unavailable", "reason": "no_visible_component"}
    binary = np.isin(components, list(selected)).astype(np.uint8)
    fraction = float(binary.mean())
    if fraction < 0.02 or fraction > 0.96:
        return {"status": "unavailable", "reason": "cannot_separate"}
    runs, last, count = [], 0, 0
    for value in binary.reshape(-1):
        if value == last:
            count += 1
        else:
            runs.append(count); count = 1; last = int(value)
    runs.append(count)
    mask = {"width": 96, "height": 192, "runs": runs, "method": "grabcut_suggestion"}
    return {"status": "suggested", "mask": mask} if valid_mask(mask) else {"status": "unavailable", "reason": "complex_mask"}


def tracking_preview(images, times, anchor):
    """Run the production optical tracker on a short, same-scene preview.

    Results are provisional UI suggestions, never persisted as event evidence.
    """
    import cv2
    import numpy as np
    from PIL import Image
    from io import BytesIO
    from player_tracking import _run_direction, _cut_flags, TARGET_W, COLOR_W
    if (not 3 <= len(images) <= 5 or len(times) != len(images) or not valid_box(anchor.get("box"))
            or anchor.get("visibility") == "partial" or not all(number(t) for t in times)
            or any(b <= a for a, b in zip(times, times[1:])) or times[-1] - times[0] > 0.7):
        raise ValueError("Choose a short, fully visible tracking check")
    frames = []
    dimensions = None
    for data, time in zip(images, times):
        with Image.open(BytesIO(data)) as header:
            if header.format not in ("JPEG", "PNG") or not valid_image_shape(header.width, header.height):
                raise ValueError("Frame too large")
            shape = (header.width, header.height)
        if dimensions is not None and dimensions != shape:
            raise ValueError("Frame dimensions changed")
        dimensions = shape
        bgr = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
        if bgr is None:
            raise ValueError("Unreadable frame")
        small = cv2.resize(bgr, (TARGET_W, max(2, int(bgr.shape[0] * TARGET_W / bgr.shape[1]))))
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        hsv = cv2.cvtColor(cv2.resize(small, (COLOR_W, max(2, small.shape[0] // 2))), cv2.COLOR_BGR2HSV)
        tiny = cv2.resize(gray, (160, max(2, int(gray.shape[0] * 160 / gray.shape[1])))).astype("float32")
        frames.append((time, gray, hsv, tiny))
    height, width = frames[0][1].shape
    b = anchor["box"]
    seed = [b["x"] * width, b["y"] * height, (b["x"] + b["w"]) * width, (b["y"] + b["h"]) * height]
    points, doubts = {}, []
    mask = decode_mask(anchor.get("visible_mask"))
    cuts = _cut_flags(frames)
    first_cut = next((i for i, cut in enumerate(cuts) if cut), len(frames))
    _run_direction(frames, 0, seed, points, +1, doubts, cuts, **({"seed_mask": mask} if mask is not None else {}))
    result = [{"t": times[0], "box": b, "status": "human_seed"}]
    for index, time in enumerate(times[1:], 1):
        p = points.get(round(time, 2))
        result.append({"t": time, "box": {k: p[k] for k in ("x", "y", "w", "h")} if p else None,
                       "status": "scene_cut" if index >= first_cut else "suggested" if p else "uncertain"})
    return {"frames": result, "provisional": True}
