"""Allocate bounded inspection across scenes AND time within each scene.

Semantic observations select where to inspect, never decide the result. Only
near-identical measured ball/body contacts share a review. Every original job
still passes its own outcome and attribution gates after geometry is reused.
"""
from collections import defaultdict
from copy import deepcopy
import hashlib
import json
import math

TIME_CELL_MS = 4000
OVERLAP_CONTACT_MS = 50


def _num(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _iou(a, b):
    if not all(isinstance(box, dict) and all(_num(box.get(k)) for k in ("x", "y", "w", "h"))
               and box["w"] > 0 and box["h"] > 0 for box in (a, b)):
        return 0.0
    intersection = max(0, min(a["x"] + a["w"], b["x"] + b["w"]) - max(a["x"], b["x"])) * max(
        0, min(a["y"] + a["h"], b["y"] + b["h"]) - max(a["y"], b["y"]))
    union = a["w"] * a["h"] + b["w"] * b["h"] - intersection
    return intersection / union if union > 0 else 0.0


def _body(job):
    strike = job["strike"]
    touch = next((t for t in (job.get("touch_graph") or {}).get("touches") or []
                  if t.get("touch_id") == strike.get("touch_id")), {})
    return (touch.get("contact_geometry") or {}).get("actor_box_used")


def _same_contact(a, b):
    sa, sb = a["strike"], b["strike"]
    if sa.get("scene_id") != sb.get("scene_id") or abs(int(sa["media_ms"]) - int(sb["media_ms"])) > OVERLAP_CONTACT_MS:
        return False
    if a["window"].get("dense_window_id") == b["window"].get("dense_window_id"):
        return sa.get("touch_id") is not None and sa.get("touch_id") == sb.get("touch_id")
    aa, ab = sa.get("active_ball_anchor") or {}, sb.get("active_ball_anchor") or {}
    # Local track names from different windows have no cross-window authority.
    return bool(_num(aa.get("media_ms")) and _num(ab.get("media_ms"))
                and abs(aa["media_ms"] - ab["media_ms"]) <= OVERLAP_CONTACT_MS
                and _iou(aa.get("box"), ab.get("box")) >= .75
                and _iou(_body(a), _body(b)) >= .75)


def _context(job):
    ms, window = int(job["strike"]["media_ms"]), job["window"]
    return (max(int(window.get("start_ms") or 0), ms - 150),
            min(int(window.get("end_ms") or ms + 2600), ms + 2600))


def ordered_requests(requests, analysis):
    contacts = []
    for seq in (analysis or {}).get("sequences") or []:
        for action in seq.get("actions") or []:
            # A mislabeled DUEL/OTHER/run must not disappear from inspection.
            ms = action.get("contact_ms")
            if not _num(ms) and _num(action.get("start_ms")) and _num(action.get("end_ms")):
                ms = (action["start_ms"] + action["end_ms"]) / 2
            if _num(ms):
                contacts.append((seq.get("scene_id"), int(ms)))

    def relevance(job):
        strike = job["strike"]
        ms = int(strike.get("media_ms") or 0)
        distance = min((abs(ms - t) for scene, t in contacts if scene == strike.get("scene_id")), default=1000000)
        role = strike.get("contact_role") or {}
        return (0 if role.get("role") == "RELEASE" else 1,
                0 if distance <= 1200 else 1, distance,
                -float(strike.get("post_speed") or 0), ms)

    # Choose the widest available context before paying for overlap. The
    # provider can then cache by physical episode rather than window bounds.
    groups = []
    for job in sorted(requests, key=lambda j: int(j["strike"].get("media_ms") or 0)):
        group = next((g for g in groups if _same_contact(g[0], job)), None)
        if group is None:
            groups.append([job])
        else:
            group.append(job)
    representatives, repeats = [], []
    for group in groups:
        representative = min(group, key=lambda j: (
            j["review"].get("lane") != "VERIFIED_CHAIN", -(_context(j)[1] - _context(j)[0]), relevance(j)))
        context_job = max(group, key=lambda j: _context(j)[1] - _context(j)[0])
        start, end = _context(context_job)
        episode_id = hashlib.sha256(json.dumps([
            representative["strike"].get("scene_id"), representative["strike"].get("media_ms"),
            representative["window"].get("dense_window_id"),
            representative["strike"].get("touch_id") or representative["strike"].get("strike_id")
                or representative["strike"].get("player_track_id"),
            representative["strike"].get("active_ball_anchor")
        ], separators=(",", ":")).encode()).hexdigest()[:20]
        for original in group:
            job = dict(original)
            job["strike"] = deepcopy(original["strike"])
            job["strike"].update(_review_episode_id=episode_id,
                                 _review_lane=original["review"].get("lane"),
                                 _review_context={"start_ms": start, "end_ms": end,
                                                  "media_ms": int(context_job["strike"]["media_ms"])})
            job["review"] = {**original["review"], "physical_review_id": episode_id,
                             "overlap_jobs": len(group)}
            (representatives if original is representative else repeats).append(job)

    result = []
    for lane in ("VERIFIED_CHAIN", "CLARIFICATION"):
        scenes = defaultdict(lambda: defaultdict(list))
        visits = defaultdict(int)
        for job in representatives:
            if job["review"].get("lane") == lane:
                scenes[str(job["window"].get("scene_id") or "")][int(job["strike"]["media_ms"]) // TIME_CELL_MS].append(job)
        for cells in scenes.values():
            for group in cells.values():
                group.sort(key=relevance)
        while scenes:
            # Visit each scene before its next time cell; within a scene,
            # visit each occupied time cell before repeating one noisy cell.
            scene_order = sorted(scenes, key=lambda scene: (min(relevance(g[0]) for g in scenes[scene].values()), scene))
            for scene in scene_order:
                cells = scenes[scene]
                cell = min(cells, key=lambda c: (visits[(scene, c)], relevance(cells[c][0]), c))
                result.append(cells[cell].pop(0))
                visits[(scene, cell)] += 1
                if not cells[cell]:
                    del cells[cell]
                if not cells:
                    del scenes[scene]
    return result + repeats
