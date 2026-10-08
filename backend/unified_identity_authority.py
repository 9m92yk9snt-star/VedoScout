"""FIX 09B.0 — Unified GLOBAL_TARGET identity authority.

Pure deterministic fusion layer that turns the existing FIX04 local tap-seeded
track and FIX09A global identity timeline into ONE canonical target authority.

The module deliberately does not detect players, call models, or understand
football events. It only reconciles identity evidence already produced by the
existing pipeline.

Design contract
---------------
* FIX00A user taps remain absolute identity authority inside a bounded tap
  window. A later tracker/timeline disagreement may never override a tap.
* FIX04 is trusted LOCAL geometry/evidence, not whole-video identity truth.
* FIX09A supplies scene-aware GLOBAL_TARGET identity and cut/re-ID semantics.
* Agreement strengthens identity. Disagreement outside tap authority becomes
  explicit UNRESOLVED hypotheses; boxes are never averaged between two bodies.
* Predicted/occluded geometry is continuity evidence only and is never
  proof-eligible.
* Inputs are never mutated.
* All time is canonical media milliseconds.

This is the identity spine consumed by later FIX09B stages. It intentionally
keeps a compatibility adapter (`to_production_track`) so existing deterministic
movement/event/evidence code can migrate to the same authority incrementally.
"""
from __future__ import annotations

from copy import deepcopy

VERSION = 1
GLOBAL_TARGET_ID = "GLOBAL_TARGET"
JERSEY_HANDOFF_MAX_TAP_GAP_MS = 6000
JERSEY_HANDOFF_LOCAL_VOTE_RADIUS_MS = 1200
JERSEY_HANDOFF_NEAREST_VOTE_MAX_MS = 350

FUSE_TOL_MS = 140
TAP_AUTHORITY_MS = 650
AGREE_IOU_MIN = 0.18
AGREE_CENTER_H = 0.70
MAX_RESOLVE_INTERP_MS = 500
PRODUCTION_SEGMENT_GAP_S = 0.35


def _is_num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _normalise_jersey_number(value):
    if value is None or isinstance(value, bool):
        return None
    text = str(value).strip()
    if not text.isdigit():
        return None
    number = int(text)
    return str(number) if 0 <= number <= 99 else None


def _valid_box(b) -> bool:
    if not isinstance(b, dict):
        return False
    try:
        x, y, w, h = (float(b[k]) for k in ("x", "y", "w", "h"))
    except (KeyError, TypeError, ValueError):
        return False
    return 0.0 <= x <= 1.0 and 0.0 <= y <= 1.0 and 0.0 < w <= 1.0 and 0.0 < h <= 1.0


def _box(b):
    return {k: float(b[k]) for k in ("x", "y", "w", "h")}


def _iou(a, b) -> float:
    ax0, ay0, ax1, ay1 = a["x"], a["y"], a["x"] + a["w"], a["y"] + a["h"]
    bx0, by0, bx1, by1 = b["x"], b["y"], b["x"] + b["w"], b["y"] + b["h"]
    ix = max(0.0, min(ax1, bx1) - max(ax0, bx0))
    iy = max(0.0, min(ay1, by1) - max(ay0, by0))
    inter = ix * iy
    union = a["w"] * a["h"] + b["w"] * b["h"] - inter
    return inter / union if union > 0 else 0.0


def _centers_agree(a, b) -> bool:
    acx, acy = a["x"] + a["w"] / 2.0, a["y"] + a["h"] / 2.0
    bcx, bcy = b["x"] + b["w"] / 2.0, b["y"] + b["h"] / 2.0
    ref_h = max(a["h"], b["h"], 1e-6)
    return ((acx - bcx) ** 2 + (acy - bcy) ** 2) ** 0.5 <= AGREE_CENTER_H * ref_h


def boxes_agree(a, b) -> bool:
    """Timestamp-near identity geometry agreement, never an identity decision alone."""
    if not (_valid_box(a) and _valid_box(b)):
        return False
    aa, bb = _box(a), _box(b)
    return _iou(aa, bb) >= AGREE_IOU_MIN or _centers_agree(aa, bb)


def _scene_for_ms(scenes, ms):
    for s in scenes or []:
        if not isinstance(s, dict):
            continue
        a, b = s.get("start_ms"), s.get("end_ms")
        if _is_num(a) and _is_num(b) and int(a) <= ms <= int(b):
            return s.get("scene_id")
    return None


def _tap_times(anchors, anchor_time_offset) -> list[int]:
    from player_selection import full_body_anchors
    out = []
    off = float(anchor_time_offset or 0.0)
    for a in full_body_anchors(anchors):
        if isinstance(a, dict) and _is_num(a.get("t")):
            out.append(int(round((float(a["t"]) + off) * 1000.0)))
    return sorted(set(out))


def _tap_rows(anchors, anchor_time_offset, scenes) -> list[dict]:
    """Preserve the box the user actually selected at the selected media time."""
    out = []
    off = float(anchor_time_offset or 0.0)
    from player_selection import expanded_anchors
    for anchor in expanded_anchors(anchors):
        if (not isinstance(anchor, dict) or not _is_num(anchor.get("t"))
                or not _valid_box(anchor.get("box"))):
            continue
        ms = int(round((float(anchor["t"]) + off) * 1000.0))
        out.append({"media_ms": ms, "scene_id": _scene_for_ms(scenes, ms),
                    "box": _box(anchor["box"]), "partial": anchor.get("visibility") == "partial",
                    "exclude_points": anchor.get("exclude_points") or []})
    return out


def _near_tap(ms, taps) -> bool:
    return any(abs(ms - t) <= TAP_AUTHORITY_MS for t in taps)


def _near_matching_tap(ms, box, tap_rows, taps, scene_id=None) -> bool:
    # Legacy time-only anchors keep their old behavior. With a selected box,
    # only geometry on that same body inherits the bounded tap authority.
    if any(abs(ms - t) <= TAP_AUTHORITY_MS
           and not any(row["media_ms"] == t for row in tap_rows) for t in taps):
        return True
    return any(not row.get("partial") and abs(ms - row["media_ms"]) <= TAP_AUTHORITY_MS
               and (scene_id is None or row["scene_id"] is None
                    or row["scene_id"] == scene_id)
               and boxes_agree(box, row["box"]) for row in tap_rows)


def _timeline_rows(identity_timeline) -> list[dict]:
    rows = []
    tl = identity_timeline if isinstance(identity_timeline, dict) else {}
    for p in tl.get("target_points") or []:
        if not isinstance(p, dict) or not _is_num(p.get("media_ms")) or not _valid_box(p.get("box")):
            continue
        rows.append({
            "media_ms": int(round(float(p["media_ms"]))),
            "scene_id": p.get("scene_id"),
            "box": _box(p["box"]),
            "state": str(p.get("state") or "VISIBLE"),
            "predicted": p.get("predicted") is True,
            "proof_eligible": p.get("proof_eligible") is True and p.get("predicted") is not True,
            "identity_score": p.get("identity_score") if _is_num(p.get("identity_score")) else None,
            "local_track_id": p.get("local_track_id"),
            "geometry_source": p.get("geometry_source"),
        })
    return sorted(rows, key=lambda r: r["media_ms"])


def _fix04_rows(fix04_track, scenes) -> list[dict]:
    rows = []
    tr = fix04_track if isinstance(fix04_track, dict) else {}
    for p in tr.get("points") or []:
        if not isinstance(p, dict) or not _is_num(p.get("t")):
            continue
        b = {k: p.get(k) for k in ("x", "y", "w", "h")}
        if not _valid_box(b):
            continue
        ms = int(round(float(p["t"]) * 1000.0))
        rows.append({
            "media_ms": ms,
            "scene_id": _scene_for_ms(scenes, ms),
            "box": _box(b),
            "conf": float(p["conf"]) if _is_num(p.get("conf")) else None,
        })
    return sorted(rows, key=lambda r: r["media_ms"])


def _nearest(rows, ms, tol_ms=FUSE_TOL_MS):
    best = None
    best_d = None
    for r in rows:
        d = abs(r["media_ms"] - ms)
        if d <= tol_ms and (best_d is None or d < best_d):
            best, best_d = r, d
        if r["media_ms"] > ms + tol_ms:
            break
    return best


def _hyp(source, row):
    if not row:
        return None
    h = {"source": source, "media_ms": int(row["media_ms"]), "box": deepcopy(row["box"])}
    if source == "FIX09A":
        h.update({"scene_id": row.get("scene_id"), "state": row.get("state"),
                  "identity_score": row.get("identity_score"),
                  "local_track_id": row.get("local_track_id")})
    else:
        h["conf"] = row.get("conf")
    return h


def _canonical(source, row, *, strength, sources, tap_authority=False,
               proof_eligible=True, hypotheses=None, reason=None):
    state = "PINNED" if tap_authority else (row.get("state") or "VISIBLE")
    if row.get("predicted"):
        state = "OCCLUDED"
    return {
        "media_ms": int(row["media_ms"]),
        "scene_id": row.get("scene_id"),
        "global_target_id": GLOBAL_TARGET_ID,
        "box": deepcopy(row.get("box")) if _valid_box(row.get("box")) else None,
        "state": state,
        "identity_strength": strength,
        "sources": list(sources),
        "primary_source": source,
        "predicted": row.get("predicted") is True,
        "proof_eligible": bool(proof_eligible and not row.get("predicted")),
        "tap_authority": bool(tap_authority),
        "reason": reason,
        "hypotheses": [h for h in (hypotheses or []) if h],
    }


def apply_verified_jersey_handoff(identity_authority: dict | None, dense_frames,
                                  touch_graph: dict | None,
                                  consensus_by_track: dict | None) -> dict:
    """Bind a split local track to GLOBAL_TARGET through independent jersey proof.

    This is a narrow re-identification handoff owned by the canonical identity
    layer.  A user-stated number alone is never enough: the number must be read
    consistently on at least two independent frames, be unique among involved
    tracks, occur in the same scene and within a bounded interval of a direct
    user tap, and must not conflict with an existing verified dense target.
    """
    authority = identity_authority if isinstance(identity_authority, dict) else {}
    frames = [row for row in (dense_frames or [])
              if isinstance(row, dict) and _is_num(row.get("media_ms"))]
    graph = deepcopy(touch_graph) if isinstance(touch_graph, dict) else {"touches": []}
    consensus = consensus_by_track if isinstance(consensus_by_track, dict) else {}
    stated = _normalise_jersey_number(
        (authority.get("identity_profile") or {}).get("stated_jersey_number")
        if isinstance(authority.get("identity_profile"), dict) else None
    )
    diagnostic = {
        "version": 1,
        "status": "UNRESOLVED",
        "reason": None,
        "stated_jersey_number": stated,
        "candidate_track_ids": [],
        "bound_touch_ids": [],
    }
    if stated is None:
        diagnostic["reason"] = "STATED_JERSEY_NUMBER_MISSING"
        graph["jersey_identity_handoff"] = diagnostic
        return graph

    matching = []
    for track, row in consensus.items():
        if not isinstance(track, str) or not isinstance(row, dict):
            continue
        if (
            row.get("status") == "VERIFIED"
            and _normalise_jersey_number(row.get("number")) == stated
            and int(row.get("agreeing_frames") or 0) >= 2
            and _is_num(row.get("top_posterior"))
            and float(row["top_posterior"]) >= 0.70
        ):
            matching.append(track)
    matching = sorted(set(matching))
    diagnostic["candidate_track_ids"] = matching
    if not matching:
        diagnostic["reason"] = "NO_UNIQUE_VERIFIED_JERSEY_MATCH"
        graph["jersey_identity_handoff"] = diagnostic
        return graph

    taps = [
        row for row in authority.get("target_points") or []
        if isinstance(row, dict) and _is_num(row.get("media_ms"))
        and row.get("tap_authority") is True
        and row.get("proof_eligible") is True
        and (
            row.get("primary_source") == "USER_TAP"
            or "USER_TAP" in (row.get("sources") or [])
        )
    ]
    if not taps:
        diagnostic["reason"] = "DIRECT_USER_TAP_MISSING"
        graph["jersey_identity_handoff"] = diagnostic
        return graph

    def nearest_frame(media_ms):
        if not frames:
            return None
        frame = min(frames, key=lambda row: abs(int(row["media_ms"]) - int(media_ms)))
        return frame if abs(int(frame["media_ms"]) - int(media_ms)) <= 100 else None

    def tap_scene(tap):
        if tap.get("scene_id") is not None:
            return tap.get("scene_id")
        frame = nearest_frame(int(tap["media_ms"]))
        return frame.get("scene_id") if isinstance(frame, dict) else None

    def local_matching_votes(track_id, media_ms):
        row = consensus.get(track_id) if isinstance(consensus.get(track_id), dict) else {}
        return [
            vote for vote in row.get("votes") or []
            if isinstance(vote, dict)
            and vote.get("readable") is True
            and _normalise_jersey_number(vote.get("number")) == stated
            and str(vote.get("confidence") or "low").lower() in {"high", "medium"}
            and _is_num(vote.get("media_ms"))
            and abs(int(round(float(vote["media_ms"]))) - int(media_ms))
            <= JERSEY_HANDOFF_LOCAL_VOTE_RADIUS_MS
        ]

    def nearest_matching_vote_gap_ms(track_id, media_ms):
        votes = local_matching_votes(track_id, media_ms)
        return min(
            (
                abs(int(round(float(vote["media_ms"]))) - int(media_ms))
                for vote in votes
            ),
            default=None,
        )

    for touch in graph.get("touches") or []:
        track_id = touch.get("player_track_id") if isinstance(touch, dict) else None
        if not (
            isinstance(touch, dict)
            and track_id in matching
            and touch.get("status") == "VERIFIED"
            and touch.get("proof_eligible") is True
        ):
            continue
        value = (touch.get("representative_ms")
                 if _is_num(touch.get("representative_ms")) else touch.get("media_ms"))
        if not _is_num(value):
            continue
        media_ms = int(round(float(value)))
        local_votes = local_matching_votes(track_id, media_ms)
        nearest_vote_gap_ms = nearest_matching_vote_gap_ms(track_id, media_ms)
        if (
            len(local_votes) < 2
            or nearest_vote_gap_ms is None
            or nearest_vote_gap_ms > JERSEY_HANDOFF_NEAREST_VOTE_MAX_MS
        ):
            continue
        scene = touch.get("scene_id")
        nearby_taps = [
            tap for tap in taps
            if abs(media_ms - int(round(float(tap["media_ms"])))) <= JERSEY_HANDOFF_MAX_TAP_GAP_MS
            and (scene is None or tap_scene(tap) is None or tap_scene(tap) == scene)
        ]
        if not nearby_taps:
            continue
        frame = nearest_frame(media_ms)
        if not isinstance(frame, dict):
            continue
        bodies = [
            player for player in frame.get("players") or []
            if isinstance(player, dict)
            and player.get("local_track_id") == track_id
            and player.get("association_state") != "HYPOTHESES"
            and _valid_box(player.get("box"))
        ]
        if len(bodies) != 1:
            continue
        candidate_body = bodies[0]
        candidate_team = str(candidate_body.get("team") or "").lower()
        candidate_team_conf = candidate_body.get("team_confidence")
        candidate_team_reliable = bool(
            candidate_team in {"target_team", "opponent"}
            and _is_num(candidate_team_conf)
            and float(candidate_team_conf) >= 0.70
        )
        # The dense two-kit model is independently anchored on the user's tap.
        # A jersey number seen on a confidently opposing kit cannot re-identify
        # the target, even when both teams happen to use that shirt number.
        if candidate_team_reliable and candidate_team == "opponent":
            continue
        # Duplicate shirt numbers are common. Refuse only a *simultaneous*
        # second body that independently has two matching time-local reads;
        # stale votes on a tracker id that switched bodies do not veto a valid
        # handoff forever.
        competing = []
        visible_ids = {
            player.get("local_track_id") for player in frame.get("players") or []
            if isinstance(player, dict)
            and isinstance(player.get("local_track_id"), str)
            and player.get("association_state") != "HYPOTHESES"
        }
        for other in matching:
            other_votes = local_matching_votes(other, media_ms)
            other_nearest_gap = nearest_matching_vote_gap_ms(other, media_ms)
            if (
                other == track_id
                or other not in visible_ids
                or len(other_votes) < 2
                or other_nearest_gap is None
                or other_nearest_gap > JERSEY_HANDOFF_NEAREST_VOTE_MAX_MS
            ):
                continue
            other_bodies = [
                player for player in frame.get("players") or []
                if isinstance(player, dict)
                and player.get("local_track_id") == other
                and player.get("association_state") != "HYPOTHESES"
                and _valid_box(player.get("box"))
            ]
            if len(other_bodies) == 1:
                other_team = str(other_bodies[0].get("team") or "").lower()
                other_conf = other_bodies[0].get("team_confidence")
                if (
                    other_team == "opponent"
                    and _is_num(other_conf)
                    and float(other_conf) >= 0.70
                ):
                    # Time-local jersey votes belong to the old body before a
                    # tracker collision; current independent kit evidence shows
                    # that this simultaneously visible body is not the target.
                    continue
            competing.append(other)
        if competing:
            continue
        dense_target = frame.get("global_target") if isinstance(frame.get("global_target"), dict) else {}
        if (
            dense_target.get("status") == "VERIFIED"
            and dense_target.get("proof_eligible") is True
            and dense_target.get("local_track_id") != track_id
        ):
            continue
        tap = min(nearby_taps, key=lambda row: abs(media_ms - int(row["media_ms"])))
        touch["global_target_id"] = GLOBAL_TARGET_ID
        touch["global_target_resolution"] = {
            "global_target_id": GLOBAL_TARGET_ID,
            "status": "VERIFIED",
            "reason": "UNIQUE_MULTI_FRAME_JERSEY_REID_AFTER_USER_TAP",
            "stated_jersey_number": stated,
            "verified_jersey_number": stated,
            "agreeing_frames": int(consensus[track_id].get("agreeing_frames") or 0),
            "time_local_agreeing_frames": len(local_votes),
            "time_local_vote_radius_ms": JERSEY_HANDOFF_LOCAL_VOTE_RADIUS_MS,
            "nearest_vote_gap_ms": nearest_vote_gap_ms,
            "nearest_vote_max_ms": JERSEY_HANDOFF_NEAREST_VOTE_MAX_MS,
            "tap_media_ms": int(tap["media_ms"]),
            "touch_media_ms": media_ms,
            "gap_ms": abs(media_ms - int(tap["media_ms"])),
        }
        diagnostic["bound_touch_ids"].append(touch.get("touch_id"))

    diagnostic["bound_touch_ids"] = [x for x in diagnostic["bound_touch_ids"] if isinstance(x, str)]
    if diagnostic["bound_touch_ids"]:
        diagnostic["status"] = "VERIFIED"
        diagnostic["reason"] = "UNIQUE_MULTI_FRAME_JERSEY_REID_AFTER_USER_TAP"
    else:
        diagnostic["reason"] = (
            "DUPLICATE_OR_STALE_VERIFIED_JERSEY_MATCH"
            if len(matching) > 1 else "NO_PROOF_ELIGIBLE_TOUCH_WITHIN_TAP_BOUND"
        )
    graph["jersey_identity_handoff"] = diagnostic
    return graph


def _unresolved(ms, scene_id, hypotheses, reason="SOURCE_CONFLICT"):
    return {
        "media_ms": int(ms),
        "scene_id": scene_id,
        "global_target_id": GLOBAL_TARGET_ID,
        "box": None,
        "state": "UNRESOLVED",
        "identity_strength": "UNRESOLVED",
        "sources": sorted({h["source"] for h in hypotheses if h}),
        "primary_source": None,
        "predicted": False,
        "proof_eligible": False,
        "tap_authority": False,
        "reason": reason,
        "hypotheses": [h for h in hypotheses if h],
    }


def _dedupe_points(points):
    """Keep the strongest canonical row when two rows land on the same media ms."""
    rank = {"USER_TAP": 7, "PARTIAL": 6, "PINNED": 6, "FUSED": 5, "GLOBAL": 4, "LOCAL": 3,
            "PREDICTED": 2, "UNRESOLVED": 1}
    by_ms = {}
    for p in points:
        ms = p["media_ms"]
        old = by_ms.get(ms)
        if old is None or rank.get(p.get("identity_strength"), 0) > rank.get(old.get("identity_strength"), 0):
            by_ms[ms] = p
        elif old and old.get("state") == "UNRESOLVED" and p.get("state") == "UNRESOLVED":
            old_h = {(h["source"], h["media_ms"]) for h in old.get("hypotheses") or []}
            for h in p.get("hypotheses") or []:
                if (h["source"], h["media_ms"]) not in old_h:
                    old["hypotheses"].append(h)
    return [by_ms[k] for k in sorted(by_ms)]


def _merge_conflict_intervals(points):
    rows = [p for p in points if p.get("state") == "UNRESOLVED"]
    if not rows:
        return []
    out = []
    for p in rows:
        cur = {"scene_id": p.get("scene_id"), "start_ms": p["media_ms"],
               "end_ms": p["media_ms"], "reason": p.get("reason") or "SOURCE_CONFLICT"}
        last = out[-1] if out else None
        if (last and last["scene_id"] == cur["scene_id"] and last["reason"] == cur["reason"]
                and cur["start_ms"] - last["end_ms"] <= 2 * FUSE_TOL_MS):
            last["end_ms"] = cur["end_ms"]
        else:
            out.append(cur)
    return out


def build_unified_identity_authority(fix04_track=None, identity_timeline=None,
                                     anchors=None, anchor_time_offset=0.0,
                                     identity_profile=None,
                                     player_details=None) -> dict:
    """Build ONE production-facing GLOBAL_TARGET identity authority.

    No source may silently overrule another. A real disagreement outside the
    user's bounded tap window is retained as competing hypotheses and therefore
    not proof-eligible until a later FIX09B stage resolves it.
    """
    tl = identity_timeline if isinstance(identity_timeline, dict) else {}
    scenes = deepcopy(tl.get("scenes") or [])
    taps = _tap_times(anchors, anchor_time_offset)
    tap_rows = _tap_rows(anchors, anchor_time_offset, scenes)
    arows = _timeline_rows(tl)
    frows = _fix04_rows(fix04_track, scenes)
    points = []

    def excluded(row):
        # Human negatives are a same-moment constraint, never a stationary
        # opponent position throughout the scene or the full ±4s tracking span.
        box = row["box"]
        return any(abs(row["media_ms"] - tap["media_ms"]) <= FUSE_TOL_MS
                   and (row.get("scene_id") is None or tap.get("scene_id") is None or row["scene_id"] == tap["scene_id"])
                   and any(box["x"] <= p["x"] <= box["x"] + box["w"] and box["y"] <= p["y"] <= box["y"] + box["h"] for p in tap["exclude_points"])
                   for tap in tap_rows)

    for source, rows in (("FIX04", frows), ("FIX09A", arows)):
        for row in rows:
            if excluded(row):
                points.append(_unresolved(row["media_ms"], row.get("scene_id"), [_hyp(source, row)], reason="USER_EXCLUDED_OPPONENT"))
    frows = [row for row in frows if not excluded(row)]
    arows = [row for row in arows if not excluded(row)]

    # FIX09A rows carry the whole-video scene-aware identity spine.
    for a in arows:
        f = _nearest(frows, a["media_ms"])
        near_pin = _near_matching_tap(a["media_ms"], f["box"] if f else a["box"],
                                     tap_rows, taps, a.get("scene_id"))
        if a["predicted"]:
            # Prediction remains useful continuity even if FIX04 is absent.
            points.append(_canonical(
                "FIX09A", a, strength="PREDICTED", sources=["FIX09A"],
                proof_eligible=False, hypotheses=[_hyp("FIX09A", a)],
                reason="OCCLUSION_CONTINUITY"))
            continue
        if f is None:
            points.append(_canonical(
                "FIX09A", a, strength="GLOBAL", sources=["FIX09A"],
                proof_eligible=a["proof_eligible"], hypotheses=[_hyp("FIX09A", a)]))
            continue
        if boxes_agree(a["box"], f["box"]):
            points.append(_canonical(
                "FIX09A", a, strength="FUSED", sources=["FIX09A", "FIX04"],
                proof_eligible=a["proof_eligible"],
                hypotheses=[_hyp("FIX09A", a), _hyp("FIX04", f)],
                reason="SOURCE_AGREEMENT"))
        elif near_pin:
            # At a user-confirmed instant FIX04 geometry wins only because it is
            # the tap-seeded local observation; the disagreement remains visible.
            ff = dict(f)
            ff["state"] = "PINNED"
            points.append(_canonical(
                "FIX04", ff, strength="PINNED", sources=["FIX04", "FIX09A"],
                tap_authority=True, proof_eligible=True,
                hypotheses=[_hyp("FIX04", f), _hyp("FIX09A", a)],
                reason="TAP_AUTHORITY_OVERRIDES_CONFLICT"))
        else:
            points.append(_unresolved(
                a["media_ms"], a.get("scene_id"),
                [_hyp("FIX09A", a), _hyp("FIX04", f)]))

    # Keep FIX04's denser local samples as trusted local evidence. They extend
    # event-contact geometry without pretending to provide whole-video identity.
    for f in frows:
        a = _nearest(arows, f["media_ms"])
        near_pin = _near_matching_tap(f["media_ms"], f["box"], tap_rows, taps,
                                     f.get("scene_id"))
        ff = dict(f)
        ff["state"] = "PINNED" if near_pin else "VISIBLE"
        if a is None:
            points.append(_canonical(
                "FIX04", ff, strength="PINNED" if near_pin else "LOCAL",
                sources=["FIX04"], tap_authority=near_pin, proof_eligible=True,
                hypotheses=[_hyp("FIX04", f)]))
        elif boxes_agree(f["box"], a["box"]):
            points.append(_canonical(
                "FIX04", ff, strength="PINNED" if near_pin else "FUSED",
                sources=["FIX04", "FIX09A"], tap_authority=near_pin,
                proof_eligible=True,
                hypotheses=[_hyp("FIX04", f), _hyp("FIX09A", a)],
                reason="SOURCE_AGREEMENT"))
        elif near_pin:
            points.append(_canonical(
                "FIX04", ff, strength="PINNED", sources=["FIX04", "FIX09A"],
                tap_authority=True, proof_eligible=True,
                hypotheses=[_hyp("FIX04", f), _hyp("FIX09A", a)],
                reason="TAP_AUTHORITY_OVERRIDES_CONFLICT"))
        else:
            points.append(_unresolved(
                f["media_ms"], f.get("scene_id"),
                [_hyp("FIX04", f), _hyp("FIX09A", a)]))

    # A timestamp alone cannot identify the selected body: a nearby tracker
    # row can belong to a different player. The selected box is authoritative
    # at the tap itself; it never makes adjacent frames proof-eligible.
    for tap in tap_rows:
        selected = _canonical(
            "USER_TAP", tap, strength="USER_TAP", sources=["USER_TAP"],
            tap_authority=not tap.get("partial"), proof_eligible=not tap.get("partial"),
            hypotheses=[_hyp("USER_TAP", tap)], reason="USER_PARTIAL_VISIBLE_BODY" if tap.get("partial") else "USER_SELECTED_BOX")
        if tap.get("partial"):
            selected["state"] = "PARTIAL"
            selected["identity_strength"] = "PARTIAL"
        points.append(selected)

    points = _dedupe_points(points)
    for point in points:
        if point.get("box") and any(tap.get("partial") and abs(point["media_ms"] - tap["media_ms"]) <= FUSE_TOL_MS
                                    and boxes_agree(point["box"], tap["box"]) for tap in tap_rows):
            point["proof_eligible"] = False
            point["tap_authority"] = False
            point["reason"] = "USER_PARTIAL_VISIBLE_BODY"
    accepted = [p for p in points if p.get("box") is not None and p.get("state") != "UNRESOLVED"]
    proof = [p for p in accepted if p.get("proof_eligible")]
    predicted = [p for p in accepted if p.get("predicted")]
    conflicts = [p for p in points if p.get("state") == "UNRESOLVED"]

    inherited_unresolved = deepcopy(tl.get("unresolved_intervals") or [])
    conflict_intervals = _merge_conflict_intervals(points)
    status = "ok" if accepted else ("unresolved" if conflicts else "empty")
    profile_summary = None
    if isinstance(identity_profile, dict) or isinstance(player_details, dict):
        # Keep only structured analysis metadata needed by later identity stages;
        # this layer never converts prose traits into target geometry.
        profile = identity_profile if isinstance(identity_profile, dict) else {}
        details = player_details if isinstance(player_details, dict) else {}
        profile_summary = {
            "same_player": profile.get("same_player"),
            "confidence": profile.get("confidence"),
            "description": profile.get("description") or profile.get("identity_description"),
            "jersey_number": profile.get("jersey_number"),
            # User-entered report metadata is retained as a stated attribute,
            # never silently upgraded into geometry or identity proof.
            "stated_jersey_number": _normalise_jersey_number(details.get("jersey_number")),
        }

    return {
        "version": VERSION,
        "status": status,
        "global_target_id": GLOBAL_TARGET_ID,
        "timebase": "canonical_media_ms",
        "scenes": scenes,
        "target_points": points,
        "unresolved_intervals": inherited_unresolved + conflict_intervals,
        "tap_times_ms": taps,
        "identity_profile": profile_summary,
        "metrics": {
            "fix04_points": len(frows),
            "fix09a_points": len(arows),
            "canonical_points": len(points),
            "accepted_points": len(accepted),
            "proof_eligible_points": len(proof),
            "predicted_points": len(predicted),
            "conflict_points": len(conflicts),
            "fused_points": sum(1 for p in points if "FIX04" in p.get("sources", []) and "FIX09A" in p.get("sources", [])
                                and p.get("state") != "UNRESOLVED"),
            "pinned_points": sum(1 for p in points if p.get("tap_authority")),
        },
    }


def _same_scene(a, b) -> bool:
    sa, sb = a.get("scene_id"), b.get("scene_id")
    return sa is None or sb is None or sa == sb


def _unresolved_overlap(authority, start_ms: int, end_ms: int,
                        scene_id=None) -> bool:
    """Return whether an explicit identity barrier intersects this span.

    Exact points and interpolation use the same barrier contract. Otherwise a
    raw B.1/B.3 consumer could cross a FIX09A/FIX09B unresolved interval even
    though the legacy event adapter correctly fails closed there.
    """
    lo, hi = sorted((int(start_ms), int(end_ms)))
    for row in (authority or {}).get("unresolved_intervals") or []:
        if not isinstance(row, dict):
            continue
        a, b = row.get("start_ms"), row.get("end_ms")
        if not (_is_num(a) and _is_num(b)):
            continue
        ua, ub = sorted((int(round(float(a))), int(round(float(b)))))
        row_scene = row.get("scene_id")
        if scene_id is not None and row_scene is not None and scene_id != row_scene:
            continue
        if max(lo, ua) <= min(hi, ub):
            return True
    return False


def resolve_target_at(authority, media_ms: int, *, proof_required=False,
                      max_interp_ms=MAX_RESOLVE_INTERP_MS):
    """Resolve canonical target geometry at one media time.

    Returns ``(point_or_none, reason)``. Interpolation is allowed only between
    accepted points in the same scene, never across a source conflict, cut, or
    predicted geometry when proof is required.
    """
    if (not isinstance(authority, dict) or not isinstance(media_ms, int)
            or isinstance(media_ms, bool)):
        return None, "INVALID_INPUT"
    pts = [p for p in authority.get("target_points") or []
           if isinstance(p, dict) and isinstance(p.get("media_ms"), int)]
    if proof_required:
        pts = [p for p in pts if p.get("proof_eligible") and _valid_box(p.get("box"))]
    else:
        pts = [p for p in pts if p.get("state") != "UNRESOLVED" and _valid_box(p.get("box"))]
    if not pts:
        return None, "NO_TARGET_AUTHORITY"
    pts.sort(key=lambda p: p["media_ms"])
    exact = next((p for p in pts if p["media_ms"] == media_ms), None)
    if exact:
        # A direct user tap may intentionally resolve a weaker inherited
        # timeline interval. Every other exact point remains subordinate to an
        # explicit identity barrier.
        if (_unresolved_overlap(authority, media_ms, media_ms, exact.get("scene_id"))
                and not (exact.get("tap_authority") is True
                         and exact.get("proof_eligible") is True)):
            return None, "UNRESOLVED_IDENTITY"
        return deepcopy(exact), "OK_EXACT"
    before = max((p for p in pts if p["media_ms"] < media_ms), key=lambda p: p["media_ms"], default=None)
    after = min((p for p in pts if p["media_ms"] > media_ms), key=lambda p: p["media_ms"], default=None)
    if before is None or after is None:
        return None, "TARGET_GAP"
    if not _same_scene(before, after):
        return None, "SCENE_CUT"
    if after["media_ms"] - before["media_ms"] > int(max_interp_ms):
        return None, "TARGET_GAP"
    # Never interpolate across any part of an explicitly unresolved interval,
    # even when the requested instant itself sits just outside the barrier.
    interp_scene = before.get("scene_id") or after.get("scene_id")
    if _unresolved_overlap(
            authority, before["media_ms"], after["media_ms"], interp_scene):
        return None, "UNRESOLVED_IDENTITY"
    f = (media_ms - before["media_ms"]) / max(1, after["media_ms"] - before["media_ms"])
    bb, ab = before["box"], after["box"]
    box = {k: float(bb[k]) + (float(ab[k]) - float(bb[k])) * f for k in ("x", "y", "w", "h")}
    out = {
        "media_ms": media_ms,
        "scene_id": before.get("scene_id") or after.get("scene_id"),
        "global_target_id": GLOBAL_TARGET_ID,
        "box": box,
        "state": "VISIBLE",
        "identity_strength": "INTERPOLATED",
        "sources": sorted(set(before.get("sources") or []) | set(after.get("sources") or [])),
        "primary_source": "UNIFIED",
        "predicted": True,
        "proof_eligible": False,
        "tap_authority": False,
        "reason": "BOUNDED_INTERPOLATION",
        "hypotheses": [],
    }
    return out, "OK_INTERPOLATED"


def to_production_track(authority) -> dict:
    """Compatibility adapter for existing FIX04-track consumers.

    Only accepted, non-predicted, proof-eligible canonical geometry is exported.
    Unresolved conflicts, explicit identity barriers, and occlusion predictions
    are intentionally omitted. A direct user tap may remain as an isolated
    authoritative point inside an inherited barrier, but continuity segments
    never bridge that barrier.
    """
    pts = []
    if isinstance(authority, dict):
        for p in authority.get("target_points") or []:
            if not (isinstance(p, dict) and p.get("proof_eligible") and not p.get("predicted")
                    and p.get("state") != "UNRESOLVED" and _valid_box(p.get("box"))):
                continue
            media_ms = p.get("media_ms")
            if not _is_num(media_ms):
                continue
            # Every production consumer must obey the same explicit identity
            # barriers as resolve_target_at(). Otherwise movement/evidence can
            # silently use geometry that event attribution correctly rejects.
            if (_unresolved_overlap(
                    authority, int(round(float(media_ms))),
                    int(round(float(media_ms))), p.get("scene_id"))
                    and not (p.get("tap_authority") is True
                             and p.get("proof_eligible") is True)):
                continue
            b = p["box"]
            pts.append({
                "t": round(float(media_ms) / 1000.0, 3),
                "x": round(float(b["x"]), 4), "y": round(float(b["y"]), 4),
                "w": round(float(b["w"]), 4), "h": round(float(b["h"]), 4),
                "conf": 1.0 if p.get("tap_authority") else 0.9,
                "authority_source": p.get("identity_strength"),
                "scene_id": p.get("scene_id"),
            })
    # stable unique time rows, preserving strongest evidence on duplicate times
    best = {}
    rank = {"PINNED": 4, "FUSED": 3, "GLOBAL": 2, "LOCAL": 1}
    for p in pts:
        old = best.get(p["t"])
        if old is None or rank.get(p.get("authority_source"), 0) > rank.get(old.get("authority_source"), 0):
            best[p["t"]] = p
    out = [best[k] for k in sorted(best)]
    segments = []
    last_scene = None
    last_point = None
    for p in out:
        scene = p.get("scene_id")
        crosses_barrier = bool(
            last_point is not None
            and _unresolved_overlap(
                authority,
                int(round(float(last_point["t"]) * 1000.0)),
                int(round(float(p["t"]) * 1000.0)),
                scene or last_scene,
            )
        )
        if (segments and scene == last_scene
                and float(p["t"]) - float(segments[-1][1]) <= PRODUCTION_SEGMENT_GAP_S
                and not crosses_barrier):
            segments[-1][1] = float(p["t"])
        else:
            segments.append([float(p["t"]), float(p["t"])])
        last_scene = scene
        last_point = p
    segments = [
        [round(a, 3), round(b, 3)] for a, b in segments
        if b - a >= PRODUCTION_SEGMENT_GAP_S - 1e-9
    ]
    return {
        "version": "FIX09B.0",
        "global_target_id": GLOBAL_TARGET_ID,
        "authority": "UNIFIED_IDENTITY",
        "points": out,
        "segments": segments,
        "seed_count": len((authority or {}).get("tap_times_ms") or []) if isinstance(authority, dict) else 0,
    }
