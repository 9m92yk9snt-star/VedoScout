"""FIX11 - semantic-independent physical event recall planning.

FIX09B already reviews every GLOBAL_TARGET-active sequence, but FIX10 dense
reconstruction used to become most useful only when the semantic pass had
already found an action or when a short refinement window happened to contain
the full outcome. That is unsafe for scoring recall: a missed pass/shot can
also prevent the physical stage from seeing the later save/shot/goal.

This module creates a second deterministic recall lane from evidence that
already exists before semantic event classification:

* FIX09B refinement triggers (target possession, ball-near-target, possession
  change, target/ball relation change), and
* the whole-video scene graph's target/possession relation.

It does not classify PASS/SHOT/GOAL/ASSIST. It only opens bounded dense replay
windows long enough to verify a later physical outcome. Scene cuts remain hard
barriers and no GLOBAL_TARGET identity is created here.
"""
from __future__ import annotations

import hashlib
from copy import deepcopy

VERSION = 1

RECALL_PRE_MS = 1400
RECALL_POST_MS = 5600
TRIGGER_GROUP_GAP_MS = 900
UNION_GAP_MS = 220
MAX_RECALL_WINDOW_MS = 8000
SPLIT_OVERLAP_MS = 1800

PHYSICAL_TRIGGER_REASONS = {
    "TARGET_POSSESSION",
    "TARGET_POSSESSION_CANDIDATE",
    "BALL_NEAR_TARGET",
    "TARGET_POSSESSION_CHANGE",
    "TARGET_BALL_RELATION_CHANGE",
}


def _num(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _stable_id(scene_id: str, start_ms: int, end_ms: int) -> str:
    raw = f"FIX11|{scene_id}|{int(start_ms)}|{int(end_ms)}".encode("utf-8")
    return "recall_" + hashlib.sha1(raw).hexdigest()[:16]


def _scene_bounds(sequence_plan: dict, scene_graph: dict) -> dict[str, tuple[int, int]]:
    bounds = {}
    for row in (scene_graph or {}).get("scenes") or []:
        if not isinstance(row, dict) or not (_num(row.get("start_ms")) and _num(row.get("end_ms"))):
            continue
        a, b = int(round(float(row["start_ms"]))), int(round(float(row["end_ms"])))
        if b < a:
            a, b = b, a
        scene = str(row.get("scene_id") or f"scene@{a}")
        bounds[scene] = (max(0, a), max(0, b))

    for key in ("analysis_windows", "refinement_windows"):
        for row in (sequence_plan or {}).get(key) or []:
            if not isinstance(row, dict) or not (_num(row.get("start_ms")) and _num(row.get("end_ms"))):
                continue
            scene = str(row.get("scene_id") or "")
            if not scene:
                continue
            a, b = int(row["start_ms"]), int(row["end_ms"])
            if b < a:
                a, b = b, a
            if scene not in bounds:
                bounds[scene] = (max(0, a), max(0, b))
            else:
                lo, hi = bounds[scene]
                bounds[scene] = (min(lo, max(0, a)), max(hi, max(0, b)))
    return bounds


def _target_ids(frame: dict) -> set[str]:
    target = frame.get("global_target") if isinstance(frame, dict) else {}
    target = target if isinstance(target, dict) else {}
    ids = {
        x for x in target.get("candidate_local_track_ids") or []
        if isinstance(x, str) and x
    }
    local = target.get("local_track_id")
    if isinstance(local, str) and local:
        ids.add(local)
    return ids


def _graph_trigger(frame: dict, previous: dict | None) -> tuple[bool, list[str]]:
    if not isinstance(frame, dict) or not _num(frame.get("media_ms")):
        return False, []
    target = frame.get("global_target") if isinstance(frame.get("global_target"), dict) else {}
    if str(target.get("status") or "UNRESOLVED") not in {"VERIFIED", "HYPOTHESES"}:
        return False, []
    ids = _target_ids(frame)
    if not ids:
        return False, []

    reasons = []
    possession = frame.get("possession") if isinstance(frame.get("possession"), dict) else {}
    relation = str(possession.get("target_relation") or "")
    if relation == "TARGET_LIKELY_POSSESSION":
        reasons.append("TARGET_POSSESSION")
    elif relation == "TARGET_POSSESSION_CANDIDATE":
        reasons.append("TARGET_POSSESSION_CANDIDATE")

    holder = possession.get("holder_local_track_id")
    if isinstance(holder, str) and holder in ids and "TARGET_POSSESSION" not in reasons:
        reasons.append("TARGET_POSSESSION")

    if previous is not None and str(previous.get("scene_id")) == str(frame.get("scene_id")):
        prev_pos = previous.get("possession") if isinstance(previous.get("possession"), dict) else {}
        prev_ids = _target_ids(previous)
        prev_holder = prev_pos.get("holder_local_track_id")
        if prev_holder != holder and (
            (isinstance(prev_holder, str) and prev_holder in prev_ids)
            or (isinstance(holder, str) and holder in ids)
        ):
            reasons.append("TARGET_POSSESSION_CHANGE")
        prev_relation = str(prev_pos.get("target_relation") or "")
        if prev_relation != relation and ("TARGET" in prev_relation or "TARGET" in relation):
            reasons.append("TARGET_BALL_RELATION_CHANGE")

    return bool(reasons), sorted(set(reasons))


def _clip(bounds, scene: str, start_ms: int, end_ms: int) -> tuple[int, int] | None:
    lo, hi = int(start_ms), int(end_ms)
    if hi < lo:
        lo, hi = hi, lo
    if scene in bounds:
        slo, shi = bounds[scene]
        lo, hi = max(lo, int(slo)), min(hi, int(shi))
    lo = max(0, lo)
    hi = max(0, hi)
    return (lo, hi) if hi >= lo else None


def _split(row: dict) -> list[dict]:
    start, end = int(row["start_ms"]), int(row["end_ms"])
    if end - start <= MAX_RECALL_WINDOW_MS:
        out = deepcopy(row)
        out["dense_window_id"] = _stable_id(str(out["scene_id"]), start, end)
        return [out]

    result = []
    step = max(1000, MAX_RECALL_WINDOW_MS - SPLIT_OVERLAP_MS)
    cursor = start
    while cursor <= end:
        piece_end = min(end, cursor + MAX_RECALL_WINDOW_MS)
        piece = deepcopy(row)
        piece["start_ms"] = cursor
        piece["end_ms"] = piece_end
        piece["trigger_ms"] = [
            int(ms) for ms in row.get("trigger_ms") or []
            if cursor <= int(ms) <= piece_end
        ]
        piece["dense_window_id"] = _stable_id(str(piece["scene_id"]), cursor, piece_end)
        result.append(piece)
        if piece_end >= end:
            break
        cursor += step
    return result


def _group_trigger_rows(rows: list[dict], bounds) -> list[dict]:
    groups = []
    current = None
    for row in sorted(rows, key=lambda x: (str(x["scene_id"]), int(x["media_ms"]))):
        scene, ms = str(row["scene_id"]), int(row["media_ms"])
        if (
            current is None
            or current["scene_id"] != scene
            or ms - current["last_ms"] > TRIGGER_GROUP_GAP_MS
        ):
            if current is not None:
                groups.append(current)
            current = {
                "scene_id": scene,
                "first_ms": ms,
                "last_ms": ms,
                "trigger_ms": [ms],
                "reasons": set(row.get("reasons") or []),
                "source_refinement_ids": set(row.get("source_refinement_ids") or []),
                "source_sequence_ids": set(row.get("source_sequence_ids") or []),
            }
        else:
            current["last_ms"] = ms
            current["trigger_ms"].append(ms)
            current["reasons"].update(row.get("reasons") or [])
            current["source_refinement_ids"].update(row.get("source_refinement_ids") or [])
            current["source_sequence_ids"].update(row.get("source_sequence_ids") or [])
    if current is not None:
        groups.append(current)

    windows = []
    for group in groups:
        clipped = _clip(
            bounds,
            group["scene_id"],
            group["first_ms"] - RECALL_PRE_MS,
            group["last_ms"] + RECALL_POST_MS,
        )
        if clipped is None:
            continue
        start_ms, end_ms = clipped
        base = {
            "scene_id": group["scene_id"],
            "start_ms": start_ms,
            "end_ms": end_ms,
            "reasons": sorted({"FIX11_PHYSICAL_RECALL", *group["reasons"]}),
            "trigger_ms": sorted(set(int(x) for x in group["trigger_ms"])),
            "source_refinement_ids": sorted(group["source_refinement_ids"]),
            "source_sequence_ids": sorted(group["source_sequence_ids"]),
            "source_action_ids": [],
            "recall_window": True,
        }
        windows.extend(_split(base))
    return windows


def build_physical_recall_windows(
    sequence_plan: dict | None,
    scene_graph: dict | None,
) -> dict:
    """Build semantic-independent dense windows for target ball interactions.

    scan_complete means the available scene-graph/refinement substrate was
    scanned deterministically. It does not mean every football event has
    already been verified.
    """
    plan = sequence_plan if isinstance(sequence_plan, dict) else {}
    graph = scene_graph if isinstance(scene_graph, dict) else {}
    bounds = _scene_bounds(plan, graph)
    trigger_rows = []

    for row in plan.get("refinement_windows") or []:
        if not isinstance(row, dict):
            continue
        reasons = set(str(x) for x in row.get("reasons") or [])
        physical = sorted(reasons.intersection(PHYSICAL_TRIGGER_REASONS))
        if not physical:
            continue
        trigger_times = [int(x) for x in row.get("trigger_ms") or [] if _num(x)]
        if not trigger_times and _num(row.get("start_ms")) and _num(row.get("end_ms")):
            trigger_times = [int((int(row["start_ms"]) + int(row["end_ms"])) // 2)]
        for ms in trigger_times:
            trigger_rows.append({
                "scene_id": str(row.get("scene_id") or "scene_unknown"),
                "media_ms": ms,
                "reasons": physical,
                "source_refinement_ids": [row.get("refinement_id")] if row.get("refinement_id") else [],
                "source_sequence_ids": [
                    x for x in row.get("sequence_ids") or [] if isinstance(x, str)
                ],
            })

    frames = sorted(
        [
            f for f in graph.get("frames") or []
            if isinstance(f, dict) and _num(f.get("media_ms"))
        ],
        key=lambda f: (str(f.get("scene_id") or ""), int(f["media_ms"])),
    )
    previous_by_scene = {}
    target_active_frames = 0
    graph_trigger_frames = 0
    for frame in frames:
        scene = str(frame.get("scene_id") or "scene_unknown")
        if _target_ids(frame):
            target_active_frames += 1
        previous = previous_by_scene.get(scene)
        is_trigger, reasons = _graph_trigger(frame, previous)
        previous_by_scene[scene] = frame
        if not is_trigger:
            continue
        graph_trigger_frames += 1
        ms = int(frame["media_ms"])
        overlapping_sequences = [
            w.get("sequence_id")
            for w in plan.get("analysis_windows") or []
            if isinstance(w, dict)
            and str(w.get("scene_id") or "") == scene
            and _num(w.get("start_ms")) and _num(w.get("end_ms"))
            and int(w["start_ms"]) <= ms <= int(w["end_ms"])
            and isinstance(w.get("sequence_id"), str)
        ]
        trigger_rows.append({
            "scene_id": scene,
            "media_ms": ms,
            "reasons": reasons,
            "source_refinement_ids": [],
            "source_sequence_ids": overlapping_sequences,
        })

    by_key = {}
    for row in trigger_rows:
        key = (str(row["scene_id"]), int(row["media_ms"]))
        current = by_key.setdefault(key, {
            "scene_id": key[0],
            "media_ms": key[1],
            "reasons": set(),
            "source_refinement_ids": set(),
            "source_sequence_ids": set(),
        })
        current["reasons"].update(row.get("reasons") or [])
        current["source_refinement_ids"].update(
            x for x in row.get("source_refinement_ids") or [] if isinstance(x, str)
        )
        current["source_sequence_ids"].update(
            x for x in row.get("source_sequence_ids") or [] if isinstance(x, str)
        )
    clean_rows = [
        {
            **row,
            "reasons": sorted(row["reasons"]),
            "source_refinement_ids": sorted(row["source_refinement_ids"]),
            "source_sequence_ids": sorted(row["source_sequence_ids"]),
        }
        for row in by_key.values()
    ]
    windows = _group_trigger_rows(clean_rows, bounds)
    return {
        "version": VERSION,
        "status": "ok" if (frames or plan.get("refinement_windows")) else "no_recall_substrate",
        "scan_complete": bool(frames or plan.get("refinement_windows")),
        "windows": windows,
        "metrics": {
            "scene_graph_frames": len(frames),
            "target_active_frames": target_active_frames,
            "graph_trigger_frames": graph_trigger_frames,
            "distinct_trigger_points": len(clean_rows),
            "recall_windows": len(windows),
        },
    }


def _merge_metadata(target: dict, source: dict) -> None:
    for key in (
        "reasons",
        "source_refinement_ids",
        "source_sequence_ids",
        "source_action_ids",
        "trigger_ms",
    ):
        values = [*(target.get(key) or []), *(source.get(key) or [])]
        target[key] = sorted(set(values))
    target["recall_window"] = bool(target.get("recall_window") or source.get("recall_window"))


def union_dense_windows(existing, recall) -> list[dict]:
    """Union semantic FIX10 windows with FIX11 recall windows conservatively."""
    rows = [
        deepcopy(x) for x in [*(existing or []), *(recall or [])]
        if isinstance(x, dict)
        and _num(x.get("start_ms")) and _num(x.get("end_ms"))
        and x.get("scene_id") is not None
    ]
    rows.sort(key=lambda x: (str(x["scene_id"]), int(x["start_ms"]), int(x["end_ms"])))
    merged = []
    for row in rows:
        row["start_ms"], row["end_ms"] = sorted((int(row["start_ms"]), int(row["end_ms"])))
        if not row.get("dense_window_id"):
            row["dense_window_id"] = _stable_id(str(row["scene_id"]), row["start_ms"], row["end_ms"])
        last = merged[-1] if merged else None
        if (
            last is not None
            and str(last.get("scene_id")) == str(row.get("scene_id"))
            and int(row["start_ms"]) <= int(last["end_ms"]) + UNION_GAP_MS
            and (
                max(int(last["end_ms"]), int(row["end_ms"]))
                - min(int(last["start_ms"]), int(row["start_ms"]))
                <= MAX_RECALL_WINDOW_MS
            )
        ):
            last["start_ms"] = min(int(last["start_ms"]), int(row["start_ms"]))
            last["end_ms"] = max(int(last["end_ms"]), int(row["end_ms"]))
            _merge_metadata(last, row)
            last["dense_window_id"] = _stable_id(
                str(last["scene_id"]), int(last["start_ms"]), int(last["end_ms"])
            )
        else:
            row.setdefault("reasons", [])
            row.setdefault("source_refinement_ids", [])
            row.setdefault("source_sequence_ids", [])
            row.setdefault("source_action_ids", [])
            row.setdefault("trigger_ms", [])
            row.setdefault("recall_window", False)
            merged.append(row)
    return merged
