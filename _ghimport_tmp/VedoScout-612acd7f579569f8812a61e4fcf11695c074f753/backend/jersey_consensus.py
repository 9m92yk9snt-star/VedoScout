"""FIX10A6 — multi-frame jersey-number evidence consensus.

Jersey numbers are supporting identity evidence for materially involved scene-
local players.  They never create or upgrade GLOBAL_TARGET identity and never
promote an event.  The vision reader is intentionally separate: this module is
pure deterministic selection/aggregation/application logic.
"""
from __future__ import annotations

from copy import deepcopy

VERSION = 1
MIN_TEMPORAL_SEPARATION_MS = 120
MIN_BOX_AREA = 0.008
MAX_REVIEW_FRAMES = 5
MIN_REVIEW_FRAMES = 3
VERIFY_MIN_AGREEING_FRAMES = 2
VERIFY_MIN_POSTERIOR = 0.70
VERIFY_MIN_MARGIN = 0.25

_CONF_WEIGHT = {"high": 1.0, "medium": 0.60, "low": 0.25}


def _num(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _valid_box(box) -> bool:
    if not isinstance(box, dict):
        return False
    try:
        x, y, w, h = (float(box[k]) for k in ("x", "y", "w", "h"))
    except (KeyError, TypeError, ValueError):
        return False
    return -0.05 <= x <= 1.05 and -0.05 <= y <= 1.05 and 0 < w <= 1.1 and 0 < h <= 1.1


def _normalise_number(value):
    if value is None or isinstance(value, bool):
        return None
    text = str(value).strip()
    if not text.isdigit():
        return None
    number = int(text)
    if not 0 <= number <= 99:
        return None
    return str(number)


def _involved_tracks(touch_graph: dict | None) -> list[str]:
    graph = touch_graph if isinstance(touch_graph, dict) else {}
    out = []
    for touch in graph.get("touches") or []:
        if not isinstance(touch, dict):
            continue
        track = touch.get("player_track_id")
        if isinstance(track, str) and track and track not in out:
            out.append(track)
    return out


def select_jersey_review_requests(window_evidence, touch_graph: dict | None) -> list[dict]:
    """Choose 3–5 clear/larger, temporally separated crops per involved track."""
    involved = set(_involved_tracks(touch_graph))
    if not involved:
        return []
    candidates: dict[str, list[dict]] = {track: [] for track in involved}
    for frame in window_evidence or []:
        if not isinstance(frame, dict) or not _num(frame.get("media_ms")):
            continue
        media_ms = int(round(float(frame["media_ms"])))
        if frame.get("used_fallback") is True:
            continue
        for player in frame.get("players") or []:
            if not isinstance(player, dict):
                continue
            track = player.get("local_track_id")
            box = player.get("box")
            if track not in involved or not _valid_box(box):
                continue
            if str(player.get("association_state") or "") == "HYPOTHESES":
                continue
            area = float(box["w"]) * float(box["h"])
            if area < MIN_BOX_AREA:
                continue
            candidates[track].append({
                "track_id": track,
                "media_ms": media_ms,
                "box": deepcopy(box),
                "area": area,
                "association_state": player.get("association_state"),
            })

    requests = []
    for track in sorted(involved):
        ranked = sorted(
            candidates.get(track) or [],
            key=lambda row: (-float(row["area"]), int(row["media_ms"])),
        )
        chosen = []
        for row in ranked:
            if any(abs(int(row["media_ms"]) - int(old["media_ms"])) < MIN_TEMPORAL_SEPARATION_MS
                   for old in chosen):
                continue
            chosen.append(row)
            if len(chosen) >= MAX_REVIEW_FRAMES:
                break
        # Fewer than three clear frames is allowed as supporting evidence; the
        # deterministic consensus will simply refuse VERIFIED status.
        chosen.sort(key=lambda row: int(row["media_ms"]))
        for index, row in enumerate(chosen):
            requests.append({
                "request_id": f"jersey_{track}_{int(row['media_ms']):010d}",
                "track_id": track,
                "media_ms": int(row["media_ms"]),
                "box": deepcopy(row["box"]),
                "selection_rank": index + 1,
                "expected_jersey_number": None,
            })
    return requests


def aggregate_jersey_votes(votes) -> dict:
    """Aggregate independent frame reads into a fail-closed posterior."""
    cleaned = []
    for vote in votes or []:
        if not isinstance(vote, dict):
            continue
        confidence = str(vote.get("confidence") or "low").lower()
        if confidence not in _CONF_WEIGHT:
            confidence = "low"
        number = _normalise_number(vote.get("number")) if vote.get("readable") is True else None
        cleaned.append({
            "media_ms": int(vote["media_ms"]) if _num(vote.get("media_ms")) else None,
            "readable": bool(vote.get("readable") is True and number is not None),
            "number": number,
            "confidence": confidence,
            "weight": _CONF_WEIGHT[confidence] if number is not None else 0.0,
            "reason": str(vote.get("reason") or "")[:160],
        })
    readable = [v for v in cleaned if v["readable"] and v["number"] is not None]
    if not readable:
        return {
            "version": VERSION, "status": "UNKNOWN", "number": None,
            "posterior": {}, "top_posterior": 0.0, "margin": 0.0,
            "agreeing_frames": 0, "votes": cleaned,
            "reason": "NO_READABLE_NUMBER_EVIDENCE",
        }
    weights = {}
    support_counts = {}
    for vote in readable:
        weights[vote["number"]] = weights.get(vote["number"], 0.0) + float(vote["weight"])
        if vote["confidence"] in {"high", "medium"}:
            support_counts[vote["number"]] = support_counts.get(vote["number"], 0) + 1
    total = sum(weights.values())
    posterior = {
        number: (weight / total if total > 0 else 0.0)
        for number, weight in weights.items()
    }
    ordered = sorted(posterior.items(), key=lambda item: (-item[1], int(item[0])))
    top_number, top_prob = ordered[0]
    second_prob = ordered[1][1] if len(ordered) > 1 else 0.0
    margin = top_prob - second_prob
    agreeing = int(support_counts.get(top_number, 0))
    conflict = len(ordered) > 1 and margin < VERIFY_MIN_MARGIN
    verified = bool(
        agreeing >= VERIFY_MIN_AGREEING_FRAMES
        and top_prob >= VERIFY_MIN_POSTERIOR
        and margin >= VERIFY_MIN_MARGIN
    )
    if verified:
        status, reason = "VERIFIED", "MULTI_FRAME_NUMBER_CONSENSUS"
    elif conflict:
        status, reason = "UNRESOLVED", "CONFLICTING_JERSEY_NUMBER_VOTES"
    else:
        status, reason = "SUPPORTING", "INSUFFICIENT_MULTI_FRAME_CONSENSUS"
    return {
        "version": VERSION,
        "status": status,
        "number": top_number if verified else None,
        "leading_number": top_number,
        "posterior": {k: round(v, 4) for k, v in ordered},
        "top_posterior": round(top_prob, 4),
        "margin": round(margin, 4),
        "agreeing_frames": agreeing,
        "votes": cleaned,
        "reason": reason,
    }


def apply_jersey_consensus(window_evidence, touch_graph: dict | None,
                           votes_by_track: dict | None) -> dict:
    """Attach jersey posteriors to copies of dense players and touch nodes.

    GLOBAL_TARGET mappings are copied verbatim and never modified by jersey
    evidence.  This function therefore cannot become a parallel target identity
    authority even when a jersey number is highly confident.
    """
    frames = deepcopy(list(window_evidence or []))
    graph = deepcopy(touch_graph) if isinstance(touch_graph, dict) else {"touches": []}
    raw_votes = votes_by_track if isinstance(votes_by_track, dict) else {}
    consensus = {
        track: aggregate_jersey_votes(votes)
        for track, votes in raw_votes.items() if isinstance(track, str)
    }
    for frame in frames:
        if not isinstance(frame, dict):
            continue
        for player in frame.get("players") or []:
            if not isinstance(player, dict):
                continue
            track = player.get("local_track_id")
            player["jersey_posterior"] = deepcopy(consensus.get(track)) if track in consensus else None
    for touch in graph.get("touches") or []:
        if not isinstance(touch, dict):
            continue
        track = touch.get("player_track_id")
        touch["jersey_posterior"] = deepcopy(consensus.get(track)) if track in consensus else None
    return {
        "version": VERSION,
        "window_evidence": frames,
        "touch_graph": graph,
        "consensus_by_track": consensus,
    }
