"""FIX 09A — GLOBAL TARGET IDENTITY TIMELINE (A01–A25 + structural).

Deterministic only: synthetic per-frame observations drive the real
assemble_timeline() core. No video decode, no model calls.
"""
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

import player_identity_timeline as pit  # noqa: E402

W, H = 480, 270
STEP = 200  # ms between samples (5 Hz)

SIMS = {"target": 0.80, "mate": 0.40, "opp": 0.15}


def ident_sim(emb):
    return SIMS.get((emb or {}).get("ident"), 0.0)


def neg_sim(emb):
    return 0.90 if (emb or {}).get("ident") == "known_mate" else 0.0


def det(x, y, w=30.0, h=60.0, ident="target", owned=None, team=None):
    emb = {"ident": ident}
    if owned is not None:
        emb["owned"] = owned
    return {"box": (float(x), float(y), float(w), float(h)), "emb": emb, "team": team}


def obs(ms, dets, cut=False, cam=(0.0, 0.0)):
    return {"media_ms": int(ms), "cut": cut, "cam_dx": cam[0], "cam_dy": cam[1],
            "width": W, "height": H, "detections": dets}


def tap(ms, x, y, w=30.0, h=60.0):
    return {"media_ms": int(ms), "box": (float(x), float(y), float(w), float(h))}


def run(observations, taps=None, sims=None):
    fn = ident_sim if sims is None else (lambda e: sims.get((e or {}).get("ident"), 0.0))
    return pit.assemble_timeline(observations, taps or [], fn, neg_sim)


def target_pts(tl):
    return [p for p in tl["target_points"] if not p["predicted"]]


def px(p):
    return p["box"]["x"] * W, p["box"]["y"] * H


# ── A01: crossing player in front → same GLOBAL_TARGET after separation ──
def test_A01_crossing_keeps_global_target():
    o = []
    for k in range(16):
        d = [det(100 + 15 * k, 100, ident="target"),
             det(300 - 15 * k, 100, ident="mate")]
        o.append(obs(k * STEP, d))
    tl = run(o, [tap(0, 100, 100)])
    pts = target_pts(tl)
    assert pts, "target must be tracked"
    assert tl["global_target_id"] == "GLOBAL_TARGET"
    late = [p for p in pts if p["media_ms"] >= 12 * STEP]
    assert late, "target must survive the crossing"
    for p in late:  # target keeps moving right (x ≈ 100+15k), mate goes left
        x, _ = px(p)
        assert abs(x - (100 + 15 * (p["media_ms"] // STEP))) < 20, \
            f"target followed the wrong body after crossing at {p['media_ms']}"


# ── A02: same-kit overlap → no instant identity switch ──
def test_A02_no_instant_switch_during_overlap():
    o = []
    for k in range(16):
        d = [det(100 + 15 * k, 100, ident="target"),
             det(300 - 15 * k, 100, ident="target" if 6 <= k <= 7 else "mate")]
        o.append(obs(k * STEP, d))
    tl = run(o, [tap(0, 100, 100)])
    pts = target_pts(tl)
    during = [p for p in pts if 6 * STEP <= p["media_ms"] <= 7 * STEP]
    for p in during:
        assert p["state"] in ("PARTIAL", "OCCLUDED"), \
            "overlapped samples must never be confidently VISIBLE"
    late = [p for p in pts if p["media_ms"] >= 12 * STEP]
    for p in late:
        x, _ = px(p)
        assert x > 200, "identity must not have switched onto the leftward mate"


# ── A03: later frames resolve earlier ambiguity (retrospective resolution) ──
def test_A03_retrospective_duel_resolution():
    o = []
    # target moves right toward a stationary mate at x=250, they duel, then the
    # MATE departs along the target's old velocity while the TARGET stays put.
    for k in range(20):
        if k <= 4:
            d = [det(100 + 25 * k, 100, ident="target"), det(250, 100, ident="mate")]
        elif k <= 6:
            d = [det(min(250, 100 + 25 * k), 100, ident="target"), det(250, 100, ident="mate")]
        else:
            d = [det(250 + 25 * (k - 6), 100, ident="mate"),   # departing = mate
                 det(250, 100, ident="target")]                # stationary = target
        o.append(obs(k * STEP, d))
    tl = run(o, [tap(0, 100, 100)])
    pts = target_pts(tl)
    late = [p for p in pts if p["media_ms"] >= 10 * STEP]
    assert late, "target must be re-identified after the duel"
    for p in late:
        x, _ = px(p)
        assert abs(x - 250) < 20, \
            f"post-separation evidence must reassign target to the stationary body (x={x})"
    assert any(u["reason"] == "ambiguous_duel" for u in tl["unresolved_intervals"]), \
        "the ambiguous duel middle must be explicitly unresolved"


# ── A04: partial visibility keeps identity without contamination ──
def test_A04_partial_visibility_continuity():
    o = []
    for k in range(14):
        if 5 <= k <= 8:
            d = [det(150, 100, ident="target", owned=False),
                 det(160, 95, ident="mate")]
        else:
            d = [det(150, 100, ident="target"), det(320, 95, ident="mate")]
        o.append(obs(k * STEP, d))
    tl = run(o, [tap(0, 150, 100)])
    pts = target_pts(tl)
    assert [p for p in pts if p["media_ms"] >= 10 * STEP], "identity must survive partial visibility"
    partial = [p for p in pts if 5 * STEP <= p["media_ms"] <= 8 * STEP]
    for p in partial:
        assert p["state"] in ("PARTIAL", "OCCLUDED")
        assert p["identity_score"] is None, \
            "contaminated/overlapped samples must not carry identity evidence"


# ── A05: brief full invisibility → OCCLUDED, never a teammate substitution ──
def test_A05_brief_invisibility_is_occluded():
    o = []
    for k in range(14):
        d = [] if 5 <= k <= 7 else [det(150 + 5 * k, 100, ident="target")]
        d.append(det(400, 100, ident="mate"))
        o.append(obs(k * STEP, d))
    tl = run(o, [tap(0, 150, 100)])
    occ = [p for p in tl["target_points"] if p["state"] == "OCCLUDED"]
    assert occ, "invisible-but-resumed frames must be OCCLUDED"
    for p in occ:
        assert p["predicted"] is True and p["geometry_source"] == "predicted"
    for p in target_pts(tl):
        x, _ = px(p)
        assert x < 350, "the distant mate must never substitute the target"
    resume = [p for p in target_pts(tl) if p["media_ms"] == 8 * STEP]
    assert resume and resume[0]["state"] == "REACQUIRED"


# ── A06: wrong teammate out of overlap keeps its own local track id ──
def test_A06_teammate_keeps_distinct_track():
    o = []
    for k in range(16):
        d = [det(100 + 15 * k, 100, ident="target"),
             det(300 - 15 * k, 100, ident="mate")]
        o.append(obs(k * STEP, d))
    tl = run(o, [tap(0, 100, 100)])
    pts = target_pts(tl)
    target_tid = pts[0]["local_track_id"]
    mates = [t for t in tl["other_tracks"] if t["local_track_id"] != target_tid]
    assert mates, "the teammate must remain a distinct scene-local track"
    assert all(t["local_track_id"] != target_tid for t in mates)


# ── A07: hard cut → local tracks reset ──
def test_A07_cut_resets_local_tracks():
    o = []
    for k in range(8):
        o.append(obs(k * STEP, [det(100 + 10 * k, 100, ident="target")]))
    for k in range(8, 16):
        o.append(obs(k * STEP, [det(350, 180, ident="target")], cut=(k == 8)))
    tl = run(o, [tap(0, 100, 100)])
    assert len(tl["scenes"]) == 2
    assert tl["scenes"][0]["scene_id"] == "scene_001"
    assert tl["scenes"][1]["scene_id"] == "scene_002"
    s2 = [p for p in target_pts(tl) if p["scene_id"] == "scene_002"]
    assert s2, "target must exist in scene 2"


# ── A08: hard cut → GLOBAL_TARGET re-identified in the next scene ──
def test_A08_cut_reid_state():
    o = []
    for k in range(8):
        o.append(obs(k * STEP, [det(100, 100, ident="target"), det(300, 100, ident="mate")]))
    for k in range(8, 16):
        o.append(obs(k * STEP, [det(350, 180, ident="target"), det(60, 60, ident="mate")],
                     cut=(k == 8)))
    tl = run(o, [tap(0, 100, 100)])
    assert tl["scenes"][1]["reid_state"] == "CUT_REID"
    s2 = sorted((p for p in target_pts(tl) if p["scene_id"] == "scene_002"),
                key=lambda p: p["media_ms"])
    assert s2 and s2[0]["state"] == "CUT_REID"


# ── A09: trajectory must not cross a scene cut ──
def test_A09_no_trajectory_across_cut():
    o = []
    for k in range(8):
        o.append(obs(k * STEP, [det(100 + 10 * k, 100, ident="target")]))
    for k in range(8, 16):
        o.append(obs(k * STEP, [det(400, 200, ident="target")], cut=(k == 8)))
    tl = run(o, [tap(0, 100, 100)])
    for p in tl["target_points"]:
        if p["media_ms"] < 8 * STEP:
            assert p["scene_id"] == "scene_001"
        else:
            assert p["scene_id"] == "scene_002"
    # no predicted/occluded geometry may bridge the cut
    preds = [p for p in tl["target_points"] if p["predicted"]]
    assert not any(7 * STEP < p["media_ms"] < 9 * STEP for p in preds)


# ── A10: multiple cuts → same GLOBAL_TARGET across all scenes ──
def test_A10_multi_cut_global_identity():
    o = []
    for k in range(6):
        o.append(obs(k * STEP, [det(100, 100, ident="target")]))
    for k in range(6, 12):
        o.append(obs(k * STEP, [det(300, 150, ident="target")], cut=(k == 6)))
    for k in range(12, 18):
        o.append(obs(k * STEP, [det(200, 60, ident="target")], cut=(k == 12)))
    tl = run(o, [tap(0, 100, 100)])
    assert len(tl["scenes"]) == 3
    covered = {p["scene_id"] for p in target_pts(tl)}
    assert covered == {"scene_001", "scene_002", "scene_003"}
    assert tl["global_target_id"] == "GLOBAL_TARGET"


# ── A11: camera pan is not player movement ──
def test_A11_camera_pan_compensated():
    o = []
    for k in range(12):
        o.append(obs(k * STEP, [det(100 + 20 * k, 100, ident="target")],
                     cam=(20.0, 0.0) if k else (0.0, 0.0)))
    tl = run(o, [tap(0, 100, 100)])
    pts = target_pts(tl)
    assert len(pts) >= 11, "pan must not fragment the track"
    assert all(p["state"] in ("VISIBLE", "PARTIAL") for p in pts[1:]), \
        "no REACQUIRED/LOST during a compensated pan"
    assert len(tl["scenes"]) == 1


# ── A12: zoom keeps target scale physically plausible ──
def test_A12_zoom_scale_plausibility():
    # gradual zoom is fine …
    o = []
    h = 50.0
    for k in range(10):
        o.append(obs(k * STEP, [det(200, 100, h=h, ident="target")]))
        h *= 1.08
    tl = run(o, [tap(0, 200, 100, h=50)])
    assert len(target_pts(tl)) == 10, "gradual zoom must keep one continuous track"

    # … a 3× instant scale jump must NOT be joined as the target
    o2 = []
    for k in range(5):
        o2.append(obs(k * STEP, [det(200, 100, h=50, ident="target")]))
    o2.append(obs(5 * STEP, []))
    o2.append(obs(6 * STEP, [det(200, 60, h=150, w=90, ident="target")]))
    o2.append(obs(7 * STEP, [det(200, 60, h=150, w=90, ident="target")]))
    tl2 = run(o2, [tap(0, 200, 100, h=50)])
    joined = [p for p in target_pts(tl2) if p["media_ms"] >= 6 * STEP]
    assert not joined, "a physically implausible scale jump must not be re-acquired"


# ── A13: re-acquisition uses identity, not nearest player ──
def test_A13_reacquisition_by_identity_not_distance():
    o = []
    for k in range(20):
        d = []
        if k <= 4:
            d.append(det(100, 100, ident="target"))
        if k >= 10:
            d.append(det(400, 150, ident="target"))   # target re-enters far away
        d.append(det(130, 105, ident="mate"))          # mate stays near old spot
        o.append(obs(k * STEP, d))
    tl = run(o, [tap(0, 100, 100)])
    late = [p for p in target_pts(tl) if p["media_ms"] >= 10 * STEP]
    assert late, "target must be re-acquired"
    first = sorted(late, key=lambda p: p["media_ms"])[0]
    assert first["state"] == "REACQUIRED"
    for p in late:
        x, _ = px(p)
        assert x > 300, "re-acquisition must follow identity, not the nearest body"


# ── A14: same-kit teammate near predicted position must not steal ──
def test_A14_nearby_teammate_cannot_steal():
    o = []
    for k in range(16):
        d = []
        if k <= 4:
            d.append(det(100, 100, ident="target"))
        d.append(det(120, 102, ident="mate"))  # near predicted position, same kit
        o.append(obs(k * STEP, d))
    tl = run(o, [tap(0, 100, 100)])
    for p in target_pts(tl):
        assert p["media_ms"] <= 5 * STEP or px(p)[0] < 115, \
            "the teammate must never become GLOBAL_TARGET"
    late = [p for p in target_pts(tl) if p["media_ms"] > 6 * STEP]
    assert not late, "without the target visible, the timeline must stay unresolved"
    assert tl["unresolved_intervals"], "the absence must be explicit"


# ── A15: other players stay available as negative identity information ──
def test_A15_other_tracks_available():
    o = []
    for k in range(10):
        o.append(obs(k * STEP, [det(100, 100, ident="target"),
                                det(300, 100, ident="mate", team="target_team"),
                                det(400, 120, ident="opp", team="opponent")]))
    tl = run(o, [tap(0, 100, 100)])
    others = tl["other_tracks"]
    assert len(others) >= 2
    for t in others:
        assert t["scene_id"] == "scene_001"
        assert t["local_track_id"].startswith("p")
        assert t["end_ms"] >= t["start_ms"]
        assert t["samples"] >= 1


# ── A16: the tap is absolute identity authority ──
def test_A16_tap_overrides_appearance():
    sims = {"target": 0.50, "mate": 0.90}  # adversarial: mate LOOKS more like the profile
    o = []
    for k in range(10):
        o.append(obs(k * STEP, [det(100, 100, ident="target"),
                                det(300, 100, ident="mate")]))
    tl = pit.assemble_timeline(
        o, [tap(2 * STEP, 100, 100)],
        lambda e: sims.get((e or {}).get("ident"), 0.0), neg_sim)
    pts = target_pts(tl)
    assert pts, "the pinned track must be the target"
    for p in pts:
        x, _ = px(p)
        assert x < 200, "no appearance score may override the user's tap"
    assert tl["scenes"][0]["reid_state"] == "TAP_PINNED"


# ── A17: predicted OCCLUDED geometry is never proof-eligible ──
def test_A17_predicted_geometry_not_proof_grade():
    o = []
    for k in range(12):
        d = [] if 4 <= k <= 6 else [det(150, 100, ident="target")]
        o.append(obs(k * STEP, d))
    tl = run(o, [tap(0, 150, 100)])
    occ = [p for p in tl["target_points"] if p["state"] == "OCCLUDED"]
    assert occ
    for p in occ:
        assert p["predicted"] is True
        assert p["proof_eligible"] is False
        assert p["geometry_source"] == "predicted"
    for p in tl["target_points"]:
        if p["proof_eligible"]:
            assert p["geometry_source"] == "detection" and not p["predicted"]


# ── A18: canonical media milliseconds ──
def test_A18_canonical_media_ms():
    o = [obs(k * STEP, [det(100, 100, ident="target")]) for k in range(10)]
    tl = run(o, [tap(0, 100, 100)])
    prev = -1
    for p in tl["target_points"]:
        assert isinstance(p["media_ms"], int)
        assert p["media_ms"] >= prev
        prev = p["media_ms"]
    for s in tl["scenes"]:
        assert isinstance(s["start_ms"], int) and isinstance(s["end_ms"], int)
    for u in tl["unresolved_intervals"]:
        assert isinstance(u["start_ms"], int) and isinstance(u["end_ms"], int)


# ── A19: VFR-irregular sampling stays FIX03-compatible (exact passthrough) ──
def test_A19_vfr_timestamps_passthrough():
    times = [0, 180, 390, 585, 800, 1010, 1190, 1420, 1615, 1830]
    o = [obs(ms, [det(100 + i * 8, 100, ident="target")]) for i, ms in enumerate(times)]
    tl = run(o, [tap(0, 100, 100)])
    emitted = {p["media_ms"] for p in target_pts(tl)}
    assert emitted <= set(times), "detection points must carry EXACT input media_ms"
    assert len(emitted) >= 9


# ── A21 (C02): close tap → much smaller target after a highlight cut ──
def test_A21_close_tap_small_target_after_cut():
    o = []
    for k in range(8):
        o.append(obs(k * STEP, [det(100, 80, w=60.0, h=120.0, ident="target")]))
    for k in range(8, 16):
        o.append(obs(k * STEP, [det(350, 180, w=15.0, h=30.0, ident="target"),
                                det(60, 60, w=15.0, h=30.0, ident="mate")],
                     cut=(k == 8)))
    tl = run(o, [tap(0, 100, 80, w=60.0, h=120.0)])
    s2 = [p for p in target_pts(tl) if p["scene_id"] == "scene_002"]
    assert s2, "a much smaller target after a cut must remain a candidate"
    assert tl["scenes"][1]["reid_state"] == "CUT_REID"
    for p in s2:
        x, _ = px(p)
        assert x > 300, "CUT_REID must land on the target, not the mate"


# ── A22 (C02): wide tap → much closer/larger target in a later highlight ──
def test_A22_wide_tap_close_target_after_cut():
    o = []
    for k in range(8):
        o.append(obs(k * STEP, [det(100, 80, w=15.0, h=30.0, ident="target")]))
    for k in range(8, 16):
        o.append(obs(k * STEP, [det(300, 100, w=70.0, h=140.0, ident="target"),
                                det(80, 100, w=70.0, h=140.0, ident="mate")],
                     cut=(k == 8)))
    tl = run(o, [tap(0, 100, 80, w=15.0, h=30.0)])
    s2 = [p for p in target_pts(tl) if p["scene_id"] == "scene_002"]
    assert s2, "a much larger target after a cut must remain a candidate"
    assert tl["scenes"][1]["reid_state"] == "CUT_REID"
    for p in s2:
        x, _ = px(p)
        assert x > 200, "CUT_REID must land on the target, not the mate"


# ── A23 (C03): silent MOT switch (no miss, no overlap) ends target segment ──
def test_A23_silent_mot_switch_is_split():
    o = []
    for k in range(16):
        d = [det(100 + 10 * k, 100, ident=("target" if k <= 4 else "mate"))]
        if k >= 11:
            d.append(det(400, 150, ident="target"))  # real target visible again
        o.append(obs(k * STEP, d))
    tl = run(o, [tap(0, 100, 100)])
    for p in target_pts(tl):
        assert not (4 * STEP < p["media_ms"] < 11 * STEP), \
            "teammate tail inherited GLOBAL_TARGET after a silent switch"
    late = [p for p in target_pts(tl) if p["media_ms"] >= 11 * STEP]
    assert late, "the real target must be re-acquired"
    assert sorted(late, key=lambda p: p["media_ms"])[0]["state"] == "REACQUIRED"
    for p in late:
        x, _ = px(p)
        assert x > 300, "re-acquisition must land on the real target"
    # the teammate tail remains a distinct non-target track
    target_ids = {p["local_track_id"] for p in target_pts(tl)}
    tails = [t for t in tl["other_tracks"] if t["local_track_id"] not in target_ids]
    assert tails, "the switched teammate tail must exist as a separate local track"


# ── A24 (C03): a single noisy appearance frame must NOT split the target ──
def test_A24_noisy_frame_does_not_split():
    sims = {"target": 0.80, "noise": 0.20}
    o = []
    for k in range(12):
        o.append(obs(k * STEP, [det(100 + 5 * k, 100,
                                    ident=("noise" if k == 6 else "target"))]))
    tl = pit.assemble_timeline(
        o, [tap(0, 100, 100)],
        lambda e: sims.get((e or {}).get("ident"), 0.0), neg_sim)
    pts = target_pts(tl)
    assert len(pts) == 12, "one noisy frame must not split/fragment the target track"
    assert all(p["state"] == "VISIBLE" for p in pts)
    assert not tl["unresolved_intervals"]


# ── A25 (C04): tap during an overlap → correct body after separation ──
def test_A25_ambiguous_tap_during_overlap():
    o = []
    for k in range(14):
        d = [det(100 + 20 * k, 100, ident="target"),
             det(300 - 20 * k, 100, ident="mate")]
        o.append(obs(k * STEP, d))
    # tap lands exactly where BOTH bodies are (k=5: both at x=200)
    tl = run(o, [tap(5 * STEP, 200, 100)])
    pts = target_pts(tl)
    assert pts, "the ambiguous tap must still resolve to a target"
    late = [p for p in pts if p["media_ms"] >= 9 * STEP]
    assert late, "target must continue after the duel"
    for p in late:
        x, _ = px(p)
        assert x > 250, "GLOBAL_TARGET must follow the tapped (rightward) body"
    assert tl["scenes"][0]["reid_state"] == "TAP_PINNED"


# ── structural: schema + counts + config ──
def test_structural_schema():
    o = [obs(k * STEP, [det(100, 100, ident="target")]) for k in range(6)]
    tl = run(o, [tap(0, 100, 100)])
    assert tl["version"] == 1
    assert tl["status"] == "ok"
    assert set(tl["counts"].keys()) == set(pit.STATES)
    for p in tl["target_points"]:
        assert p["state"] in pit.STATES
        for kf in ("media_ms", "scene_id", "local_track_id", "box", "state",
                   "identity_score", "geometry_source", "predicted", "proof_eligible"):
            assert kf in p
        for bk in ("x", "y", "w", "h"):
            assert 0.0 <= p["box"][bk] <= 1.5


def test_structural_empty_input():
    tl = pit.assemble_timeline([], [], lambda e: 0.0)
    assert tl["status"] == "empty"
    assert tl["target_points"] == [] and tl["scenes"] == []


def test_structural_compare_with_production():
    o = [obs(k * STEP, [det(100, 100, ident="target")]) for k in range(10)]
    tl = run(o, [tap(0, 100, 100)])
    gt = {"points": [{"t": k * 0.08, "x": 100 / W, "y": 100 / H, "w": 30 / W, "h": 60 / H,
                      "conf": 0.9} for k in range(25)]}
    cmp_ = pit.compare_with_production(tl, gt)
    assert cmp_["gt_points"] == 25
    assert cmp_["timeline_points"] == len(target_pts(tl))
    assert cmp_["compared"] > 0
    assert cmp_["agreement_rate"] is not None and cmp_["agreement_rate"] >= 0.9
