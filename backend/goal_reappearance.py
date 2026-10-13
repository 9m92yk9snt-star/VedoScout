"""Observed whole-ball goal reappearance after a short body occlusion.

Uses independent AFTER positions, not constant-velocity projection or player
celebration. Preserves a crossing interval instead of inventing the hidden
crossing instant. Native identity, whole-ball geometry and proof before the
occlusion remain mandatory. Neither user testimony nor goalkeeper reaction can
create a goal by itself.
"""
from __future__ import annotations

from copy import deepcopy
import math
import re

import native_ball_reappearance as native

VERSION = 1
LANE = "OBSERVED_POST_OCCLUSION_GOAL"
MAX_GAP_MS = 900
MAX_FIRST_AFTER_OCCLUSION_MS = 220
MIN_BEFORE_ROWS = 3
MIN_AFTER_ROWS = 3
GEOMETRY_NEAR_MS = 500


def _iou(a, b):
    if not (native.box_ok(a) and native.box_ok(b)):
        return 0.
    ix = max(0., min(a["x"]+a["w"], b["x"]+b["w"])-max(a["x"], b["x"]))
    iy = max(0., min(a["y"]+a["h"], b["y"]+b["h"])-max(a["y"], b["y"]))
    area = ix*iy
    return area/max(a["w"]*a["h"]+b["w"]*b["h"]-area, 1e-12)


def _timed(rows, ms):
    if not isinstance(rows, list):
        return None
    usable = [r for r in rows or [] if isinstance(r, dict) and type(r.get("media_ms")) is int
              and r.get("confidence") in {"high", "medium"}]
    if not usable:
        return None
    result = min(usable, key=lambda r: abs(r["media_ms"]-ms))
    return result if abs(result["media_ms"]-ms) <= GEOMETRY_NEAR_MS else None


def _metrics(box, geometry, ms):
    if geometry.get("field_side_status") != "VERIFIED":
        return None
    line_row = _timed(geometry.get("line_by_ms"), ms)
    field_row = _timed(geometry.get("field_side_by_ms"), ms)
    try:
        line = line_row["line"]
        a = [float(line["p1"][k]) for k in ("x", "y")]
        b = [float(line["p2"][k]) for k in ("x", "y")]
        field = [float(field_row["point"][k]) for k in ("x", "y")]
    except (TypeError, KeyError, ValueError):
        return None
    if not all(math.isfinite(v) and 0 <= v <= 1 for v in (*a, *b, *field)):
        return None
    vx, vy = b[0]-a[0], b[1]-a[1]
    length = math.hypot(vx, vy)
    if length < .04:
        return None
    tx, ty = vx/length, vy/length
    nx, ny = -ty, tx
    cx, cy = box["x"]+box["w"]/2, box["y"]+box["h"]/2
    d = (cx-a[0])*nx+(cy-a[1])*ny
    field_d = (field[0]-a[0])*nx+(field[1]-a[1])*ny
    if abs(field_d) < .015:
        return None
    extent = abs(nx)*box["w"]/2+abs(ny)*box["h"]/2
    tangent_extent = abs(tx)*box["w"]/2+abs(ty)*box["h"]/2
    along = (cx-a[0])*tx+(cy-a[1])*ty
    sign = 1 if field_d > 0 else -1
    return {"field_signed_distance": d*sign, "normal_extent": extent,
            "mouth_margin": min(along, length-along)-tangent_extent,
            "field_side_sign": sign}


def build_audit(ball_rows, occlusion, identity_link):
    """Preserve a measured native packet, without promoting user testimony."""
    empty = {"status": "UNRESOLVED", "reason": "CLASSIFIED_BALL_REAPPEARANCE_NOT_PROVEN",
             "post_occlusion_rows": [], "identity_link": None}
    if not isinstance(identity_link, dict):
        return empty
    if identity_link.get("source") != native.SOURCE or identity_link.get("method") != native.METHOD:
        return {**empty, "reason": "REAPPEARANCE_IDENTITY_SOURCE_NOT_NATIVE"}
    result = {**empty, "identity_link": deepcopy(identity_link),
              "reason": str(identity_link.get("reason") or empty["reason"])}
    if not isinstance(occlusion, dict) or type(occlusion.get("occlusion_end_media_ms")) is not int:
        return result
    end = occlusion["occlusion_end_media_ms"]
    result["post_occlusion_rows"] = [
        deepcopy(r) for r in (ball_rows if isinstance(ball_rows, list) else []) if isinstance(r, dict)
        and type(r.get("media_ms")) is int and r["media_ms"] > end
        and r.get("ball_visible") is True and r.get("confidence") == "high"
        and r.get("relation") == "BEYOND_LINE_INSIDE_MOUTH"
        and native.box_ok(r.get("ball_box"))
    ]
    if identity_link.get("status") == "VERIFIED_SAME_BALL" and len(result["post_occlusion_rows"]) >= MIN_AFTER_ROWS:
        result.update(status="NATIVE_LINK_AND_AFTER_OBSERVATIONS_PRESENT",
                      reason="REAPPEARANCE_REQUIRES_PHYSICAL_AND_DIRECTION_VALIDATION")
    return result


def resolve(rows, geometry, strike_ms, touch_graph=None, strike_actor=None):
    audit = geometry.get("ball_reappearance_audit") if isinstance(geometry, dict) else None
    if not isinstance(audit, dict):
        return None
    def fail(reason, status="UNRESOLVED"):
        return {"status": status, "crossing_ms": None, "evidence": [],
                "reason": reason, "reappearance_audit": deepcopy(audit)}
    if type(strike_ms) is not int or strike_ms < 0:
        return fail("REAPPEARANCE_STRIKE_TIME_INVALID")
    if (geometry.get("source") != "INDEPENDENT_MULTI_FRAME_GOAL_REVIEW"
            or geometry.get("status") != "VERIFIED"):
        return fail("REAPPEARANCE_GOAL_GEOMETRY_UNVERIFIED")
    coverage = geometry.get("response_coverage")
    if not isinstance(coverage, dict) or coverage.get("status") != "COMPLETED":
        return fail("REAPPEARANCE_IMAGE_COVERAGE_INCOMPLETE")
    occ = geometry.get("occlusion_crossing_audit")
    if not isinstance(occ, dict):
        return fail("REAPPEARANCE_LITERAL_BODY_OCCLUSION_MISSING")
    if occ.get("status") != "VERIFIED_OCCLUSION" or occ.get("confidence") not in {"high", "medium"}:
        return fail("REAPPEARANCE_LITERAL_BODY_OCCLUSION_MISSING")
    start, end = occ.get("occlusion_start_media_ms"), occ.get("occlusion_end_media_ms")
    if not (type(start) is int and type(end) is int and strike_ms <= start <= end
            and end-start <= MAX_GAP_MS):
        return fail("REAPPEARANCE_OCCLUSION_TIME_INVALID")
    occ_rows = occ.get("occlusion_rows")
    if (not isinstance(occ_rows, list) or not occ_rows
            or any(not isinstance(r, dict) or type(r.get("media_ms")) is not int
                   or not start <= r["media_ms"] <= end
                   or r.get("ball_visible") is not False
                   or r.get("relation") != "OCCLUDED_GOAL_MOUTH"
                   or r.get("occluder") not in {"PLAYER_BODY", "GOALKEEPER_BODY"}
                   or r.get("confidence") not in {"high", "medium"} for r in occ_rows)):
        return fail("REAPPEARANCE_BODY_OCCLUSION_OBSERVATIONS_INVALID")
    times = [r["media_ms"] for r in occ_rows]
    if times[0] != start or times[-1] != end or any(a >= b for a, b in zip(times, times[1:])):
        return fail("REAPPEARANCE_OCCLUSION_ORDER_INVALID")
    link = audit.get("identity_link")
    if not isinstance(link, dict) or not (
        link.get("status") == "VERIFIED_SAME_BALL" and link.get("proof_eligible") is True
        and link.get("source") == native.SOURCE and link.get("method") == native.METHOD
        and native.number(link.get("appearance_similarity")) and link["appearance_similarity"] >= native.MIN_SIMILARITY
        and link["appearance_similarity"] <= 1
        and native.number(link.get("alternative_similarity"))
        and -1 <= link["alternative_similarity"] <= 1
        and native.number(link.get("appearance_margin"))
        and abs(link["appearance_margin"]-(link["appearance_similarity"]-link["alternative_similarity"])) < 1e-6
        and link["appearance_margin"] >= native.MIN_ALTERNATIVE_MARGIN
        and native.number(link.get("motion_diameters")) and link["motion_diameters"] >= native.MIN_MOTION_DIAMETERS
        and link.get("rejected_candidates") == []
        and isinstance(link.get("source_video_sha256"), str) and re.fullmatch(r"[0-9a-f]{64}",link["source_video_sha256"])
    ):
        return fail("REAPPEARANCE_SAME_BALL_LINK_UNVERIFIED")
    if geometry.get("source_video_sha256") not in {None, link["source_video_sha256"]}:
        return fail("REAPPEARANCE_SOURCE_VIDEO_MISMATCH")
    pre = sorted([r for r in (rows if isinstance(rows, list) else []) if isinstance(r, dict)
                  and r.get("state") == "MEASURED" and r.get("proof_eligible") is True
                  and r.get("time_authority") == "ACTUAL_MEDIA_PTS"
                  and r.get("used_fallback") is not True and r.get("cut_barrier") is not True
                  and r.get("cut") is not True and r.get("support_only") is not True
                  and type(r.get("media_ms")) is int and strike_ms <= r["media_ms"] < start
                  and start-r["media_ms"] <= 500 and native.box_ok(r.get("box"))],
                 key=lambda r:r["media_ms"])
    if len({r["media_ms"] for r in pre}) < MIN_BEFORE_ROWS:
        return fail("REAPPEARANCE_CONTACT_BOUND_BEFORE_ROWS_MISSING")
    if any(r.get("scene_id") != link.get("scene_id") for r in pre):
        return fail("REAPPEARANCE_REFERENCE_SCENE_MISMATCH")
    before = pre[-1]
    if start-before["media_ms"] > 220 or link.get("before_media_ms") != before["media_ms"]:
        return fail("REAPPEARANCE_LINK_NOT_BOUND_TO_RELEASE_BALL")
    if _iou(link.get("before_box"),before["box"]) < .75:
        return fail("REAPPEARANCE_REFERENCE_BOX_MISMATCH")
    after = audit.get("post_occlusion_rows") or []
    measured = link.get("after_observations") or []
    if (not isinstance(after, list) or not isinstance(measured, list)
            or len(after) < MIN_AFTER_ROWS or len(measured) < MIN_AFTER_ROWS):
        return fail("REAPPEARANCE_MULTIFRAME_AFTER_EVIDENCE_MISSING")
    measured_by_ms = {r["media_ms"]:r for r in measured if isinstance(r,dict) and type(r.get("media_ms")) is int}
    if len(measured_by_ms) != len(measured):
        return fail("REAPPEARANCE_DUPLICATE_NATIVE_AFTER_TIMES")
    linked = []
    for r in after:
        if not (isinstance(r,dict) and type(r.get("media_ms")) is int and r["media_ms"] > end
                and r.get("ball_visible") is True and r.get("confidence") == "high"
                and r.get("relation") == "BEYOND_LINE_INSIDE_MOUTH" and native.box_ok(r.get("ball_box"))):
            return fail("REAPPEARANCE_AFTER_OBSERVATION_INVALID")
        det = measured_by_ms.get(r["media_ms"])
        if not (native._verified_time(det) and type(det.get("class_id")) is int and det["class_id"] == 32
                and native.number(det.get("confidence")) and det["confidence"] >= native.MIN_BALL_CONFIDENCE
                and det["confidence"] <= 1
                and det.get("classification_source") == "LOCAL_NATIVE_CLASS32_DETECTOR"
                and isinstance(det.get("model_sha256"), str) and re.fullmatch(r"[0-9a-f]{64}", det["model_sha256"])
                and isinstance(link.get("scene_id"), str) and bool(link["scene_id"])
                and det.get("scene_id") == link["scene_id"]
                and _iou(det.get("box"),r["ball_box"]) >= .75
                and isinstance(det.get("camera_alignment"), dict)
                and det["camera_alignment"].get("status") == "MEASURED"
                and det["camera_alignment"].get("reference_media_ms") == before["media_ms"]):
            return fail("REAPPEARANCE_AFTER_NOT_CLASSIFIED_NATIVE_BALL")
        linked.append(r)
    post_times = [r["media_ms"] for r in linked]
    if any(a >= b or b-a > 120 for a,b in zip(post_times,post_times[1:])):
        return fail("REAPPEARANCE_AFTER_TIME_COVERAGE_INVALID")
    first = linked[0]
    if not (0 < first["media_ms"]-before["media_ms"] <= MAX_GAP_MS
            and 0 < first["media_ms"]-end <= MAX_FIRST_AFTER_OCCLUSION_MS
            and post_times[-1]-post_times[0] >= native.MIN_AFTER_SPAN_MS):
        return fail("REAPPEARANCE_BOUNDED_GAP_NOT_PROVEN")
    hashes = link.get("after_crop_sha256")
    if (not isinstance(hashes,list) or len(hashes) != len(measured)
            or any(not isinstance(h,str) or not re.fullmatch(r"[0-9a-f]{64}",h) for h in hashes)
            or not isinstance(link.get("before_crop_sha256"),str)
            or not re.fullmatch(r"[0-9a-f]{64}",link["before_crop_sha256"])):
        return fail("REAPPEARANCE_NATIVE_PIXEL_PROVENANCE_MISSING")
    before_metrics = _metrics(before["box"],geometry,before["media_ms"])
    after_metrics = [_metrics(r["ball_box"],geometry,r["media_ms"]) for r in linked]
    if before_metrics is None or any(m is None for m in after_metrics):
        return fail("REAPPEARANCE_TIME_ALIGNED_FIELD_ORIENTATION_MISSING")
    if before_metrics["field_signed_distance"] <= before_metrics["normal_extent"]+1e-6:
        return fail("REAPPEARANCE_BEFORE_NOT_WHOLE_BALL_FIELD_SIDE")
    if any(m["field_side_sign"] != before_metrics["field_side_sign"] for m in after_metrics):
        return fail("REAPPEARANCE_FIELD_ORIENTATION_CHANGED")
    if any(m["field_signed_distance"] >= -m["normal_extent"]-1e-6 or m["mouth_margin"] <= 1e-6
           for m in after_metrics):
        return fail("REAPPEARANCE_AFTER_NOT_WHOLE_BALL_INSIDE_GOAL")
    visual = geometry.get("visual_crossing_audit")
    if not isinstance(visual, dict):
        return fail("REAPPEARANCE_INDEPENDENT_CONTRADICTION_REVIEW_MISSING")
    if visual.get("status") == "VERIFIED_NO_CROSSING" or occ.get("visual_contradiction") is True:
        return fail("REAPPEARANCE_INDEPENDENT_NO_GOAL_CONTRADICTION","REJECTED")
    for r in (visual.get("structured_evidence") if isinstance(visual.get("structured_evidence"), list) else []):
        if (isinstance(r,dict) and type(r.get("media_ms")) is int
                and end < r["media_ms"] <= post_times[-1] and r.get("ball_visible") is True
                and r.get("confidence") == "high" and r.get("relation") in {"FIELD_SIDE","OTHER"}):
            return fail("REAPPEARANCE_VISIBLE_OUTSIDE_GOAL_CONTRADICTION","REJECTED")
    support = geometry.get("reaction_support_evidence")
    defender = support.get("goal_mouth_defender_ball_contact") if isinstance(support, dict) else None
    if not isinstance(defender, dict):
        return fail("REAPPEARANCE_DEFENDER_CONTACT_REVIEW_MISSING")
    if defender.get("status") == "OBSERVED_CONTACT" and defender.get("confidence") in {"high","medium"}:
        return fail("REAPPEARANCE_VISIBLE_DEFENDER_CONTACT_CHANGES_BALL_HISTORY","REJECTED")
    if touch_graph is not None and not isinstance(touch_graph, dict):
        return fail("REAPPEARANCE_COMPETING_TOUCH_REVIEW_INVALID")
    touches = (touch_graph or {}).get("touches", [])
    if not isinstance(touches, list):
        return fail("REAPPEARANCE_COMPETING_TOUCH_REVIEW_INVALID")
    for touch in touches:
        if not isinstance(touch,dict) or touch.get("status") != "VERIFIED":
            continue
        ms = touch.get("representative_ms",touch.get("media_ms"))
        if type(ms) is int and before["media_ms"] < ms <= first["media_ms"]:
            return fail("REAPPEARANCE_COMPETING_VERIFIED_POST_RELEASE_TOUCH")
    segment = {
        "source":"FIX10A_OBSERVED_BALL_REAPPEARANCE","proof_lane":LANE,
        "from_ms":before["media_ms"],"to_ms":first["media_ms"],
        "crossing_ms":first["media_ms"],"crossing_time_authority":"FIRST_OBSERVED_WHOLE_BALL_GOAL_SIDE",
        "crossing_interval_ms":[before["media_ms"],first["media_ms"]],
        "before_media_ms":[r["media_ms"] for r in pre[-6:]],
        "after_media_ms":post_times,"same_ball_identity_verified":True,
        "reactions_are_support_only":True,"stationary_ball_controls":deepcopy(link.get("stationary_ball_controls") or []),
        "whole_ball_inside_goal":True,
    }
    return {"status":"VERIFIED","crossing_ms":first["media_ms"],
            "reason":"CONTACT_BOUND_BALL_REAPPEARED_WHOLE_GOAL_SIDE_AFTER_BOUNDED_BODY_OCCLUSION",
            "evidence":[segment],"reappearance_audit":deepcopy(audit),
            "occlusion_audit":deepcopy(occ),"reaction_support":deepcopy(geometry.get("reaction_support_evidence",{}))}
