"""
FIX 00A — Tap Authority Contract regression tests (review-corrected).

Behavioural tests exercising the ACTUAL anchor-building/persistence logic and
the ACTUAL frontend serializer — no source-string assertions for persistence.
Deterministic — NO live Gemini/GPT calls, no video decoding, no Mongo writes.

Run: cd /app/backend && python -m pytest tests/test_fix00a_tap_authority.py -v
"""
import asyncio
import base64
import json
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

import identity_verify
import player_tracking
import server

BOX = {"x": 0.4, "y": 0.4, "w": 0.05, "h": 0.12}
THUMB = "data:image/jpeg;base64," + base64.b64encode(b"fix00a-thumb").decode()


def _anchors(n_normal=10, n_verify=3, thumbs=False):
    out = [{"t": float(i * 3), "box": dict(BOX), "segment": 0} for i in range(n_normal)]
    out += [{"t": 60.0 + i, "box": dict(BOX), "segment": 1, "verify": True} for i in range(n_verify)]
    if thumbs:
        for a in out:
            a["thumb"] = THUMB
    return out


class _FakeFP:
    def __init__(self, crop_path, box):
        self.crop_path = crop_path
        self.box = box
        self.jersey_name = "red"
        self.shorts_name = "navy"
        self.body_ratio = 0.42


def _install_fakes(monkeypatch, created, frame_fail_ts=(), fp_fail_idx=()):
    """Patch the extraction seams the anchor builder actually calls.
    frame_fail_ts — anchor times whose frame extraction returns False.
    fp_fail_idx  — anchor numbers whose fingerprinting raises."""
    def fake_extract(raw_path, t, frame_path):
        return t not in frame_fail_ts

    def fake_fp(marker_image_path=None, box=None, crop_save_path=None):
        idx = int(Path(crop_save_path).stem.rsplit("-", 1)[-1])
        if idx in fp_fail_idx:
            raise RuntimeError("simulated fingerprint failure")
        Path(crop_save_path).write_bytes(b"crop")
        created.append(Path(crop_save_path))
        return _FakeFP(crop_save_path, dict(BOX))

    def fake_wide(frame_path, box, wide_path):
        return False  # skip wide crops — not under test

    monkeypatch.setattr(server, "extract_frame_at", fake_extract)
    monkeypatch.setattr(server, "extract_player_fingerprint", fake_fp)
    monkeypatch.setattr(server, "save_context_crop", fake_wide)


def _cleanup(files):
    for p in files:
        p.unlink(missing_ok=True)


# ── A: upload parse preserves 13 anchors, verify + segment ──────────────
def test_A_upload_parse_preserves_13_anchors_verify_and_segment():
    rid = f"fix00a-{uuid.uuid4().hex[:8]}"
    created = []
    try:
        out = server._detach_anchor_thumbs(json.dumps(_anchors(thumbs=True)), rid)
        parsed = json.loads(out)
        assert len(parsed) == 13
        assert sum(1 for a in parsed if a.get("verify") is True) == 3
        assert [a.get("verify") is True for a in parsed] == [False] * 10 + [True] * 3
        for i, a in enumerate(parsed):
            assert "thumb" not in a
            assert a.get("thumb_filename") == f"{rid}-anchor-{i + 1}-thumb.jpg"
            p = server.UPLOAD_DIR / a["thumb_filename"]
            created.append(p)
            assert p.exists(), f"thumb {i + 1} not detached to disk"
            assert "segment" in a and "t" in a and "box" in a
    finally:
        _cleanup(created)


# ── 1: BEHAVIOURAL — all 13 user anchors persisted with verify + segment ─
def test_1_behavioural_all_13_persisted(monkeypatch):
    rid = f"fix00a-{uuid.uuid4().hex[:8]}"
    created = []
    try:
        all_anchors = _anchors()
        _install_fakes(monkeypatch, created)
        a1 = server._build_primary_anchor_payload(
            rid, all_anchors[0]["t"], all_anchors[0]["box"], all_anchors[0], None, None)
        rest, crops, wides, verifies = asyncio.run(server._build_original_anchor_payloads(
            rid, "/fake.mp4", all_anchors))
        persisted = [a1] + rest
        assert len(persisted) == 13
        assert [a["i"] for a in persisted] == list(range(1, 14))
        assert sum(1 for a in persisted if a.get("verify") is True) == 3
        assert all("segment" in a for a in persisted)
        assert [a.get("segment") for a in persisted] == [0] * 10 + [1] * 3
        assert len(crops) == 12 and len(verifies) == 3  # all enrichments succeeded
    finally:
        _cleanup(created)


# ── 2: BEHAVIOURAL — crop failure on a NORMAL anchor keeps the anchor ───
def test_2_normal_anchor_crop_failure_keeps_anchor(monkeypatch):
    rid = f"fix00a-{uuid.uuid4().hex[:8]}"
    created = []
    try:
        all_anchors = _anchors()
        # anchor 3 (t=6.0): frame extraction fails; anchor 5: fingerprint raises
        _install_fakes(monkeypatch, created, frame_fail_ts=(6.0,), fp_fail_idx=(5,))
        rest, crops, wides, verifies = asyncio.run(server._build_original_anchor_payloads(
            rid, "/fake.mp4", all_anchors))
        assert len(rest) == 12, "a failed crop must NOT delete the user anchor"
        for failed_i, failed_t in ((3, 6.0), (5, 12.0)):
            fa = next(a for a in rest if a["i"] == failed_i)
            assert fa["t"] == failed_t and fa["box"] == BOX and fa["segment"] == 0
            assert "crop_filename" not in fa and "jersey_name" not in fa \
                and "body_ratio" not in fa, "crop fields must not be faked"
        assert len(crops) == 10  # only the 10 successful enrichments
        assert len(verifies) == 3
    finally:
        _cleanup(created)


# ── 3: BEHAVIOURAL — crop failure on a VERIFY anchor keeps verify:true ──
def test_3_verify_anchor_crop_failure_keeps_verify(monkeypatch):
    rid = f"fix00a-{uuid.uuid4().hex[:8]}"
    created = []
    try:
        all_anchors = _anchors()
        # anchor 11 = first manual verify tap (t=60.0): fingerprint raises
        _install_fakes(monkeypatch, created, fp_fail_idx=(11,))
        rest, crops, wides, verifies = asyncio.run(server._build_original_anchor_payloads(
            rid, "/fake.mp4", all_anchors))
        assert len(rest) == 12
        fa = next(a for a in rest if a["i"] == 11)
        assert fa.get("verify") is True, "verify:true must survive crop failure"
        assert fa["t"] == 60.0 and fa["box"] == BOX and fa["segment"] == 1
        assert "crop_filename" not in fa
        assert len(verifies) == 2  # only the 2 verify taps whose crops succeeded
        assert sum(1 for a in rest if a.get("verify") is True) == 3
    finally:
        _cleanup(created)


# ── 4: BEHAVIOURAL — anchor 1 metadata contract incl. segment ────────────
def test_4_anchor1_preserves_segment_and_contract():
    a1_meta = {"t": 0.5, "box": dict(BOX), "segment": 2}
    p = server._build_primary_anchor_payload("fix00a-a1", 0.5, dict(BOX), a1_meta, None, None)
    assert p["i"] == 1 and p["t"] == 0.5
    assert p["segment"] == 2, "anchor 1 must preserve its segment"
    assert p["box"] == BOX, "fingerprint failure → user box persisted"
    assert "verify" not in p, "verify must not be inferred from index"
    assert "crop_filename" not in p and "jersey_name" not in p
    # enrichment when fingerprint succeeded — metadata still intact
    fpobj = _FakeFP("/tmp/x.jpg", {"x": 0.41, "y": 0.4, "w": 0.05, "h": 0.12})
    p2 = server._build_primary_anchor_payload("fix00a-a1", 0.5, dict(BOX), a1_meta, fpobj, "c.jpg")
    assert p2["segment"] == 2 and p2["crop_filename"] == "c.jpg" and p2["box"] == fpobj.box
    # explicit verify flag on anchor 1 is preserved
    p3 = server._build_primary_anchor_payload(
        "fix00a-a1", 0.5, dict(BOX), {**a1_meta, "verify": True}, None, None)
    assert p3.get("verify") is True
    # legacy: no first_anchor metadata at all → marker fallbacks, no extra keys
    p4 = server._build_primary_anchor_payload("fix00a-a1", 1.25, dict(BOX), None, None, None)
    assert p4["t"] == 1.25 and p4["box"] == BOX
    assert "segment" not in p4 and "verify" not in p4


# ── B: production tracker receives all 13 original seeds ────────────────
def test_B_tracker_receives_all_13_seeds():
    r = player_tracking.track_player("/nonexistent-fix00a.mp4", _anchors())
    assert r["seed_count"] == 13


# ── C: 3 doubt-confirmation taps prepended → 16 seeds (hard cap) ────────
def test_C_tracker_receives_16_seeds_with_doubt_taps():
    assert player_tracking.MAX_TRACKER_SEEDS == 16
    doubt = [{"t": 90.0 + i, "box": dict(BOX)} for i in range(3)]
    r = player_tracking.track_player("/nonexistent-fix00a.mp4", doubt + _anchors())
    assert r["seed_count"] == 16
    r17 = player_tracking.track_player(
        "/nonexistent-fix00a.mp4", doubt + _anchors() + [{"t": 999.0, "box": dict(BOX)}])
    assert r17["seed_count"] == 16


def _doc_with_crops(rid, verify_idx):
    subj = f"{rid}-subject.jpg"
    (server.UPLOAD_DIR / subj).write_bytes(b"x")
    files = [server.UPLOAD_DIR / subj]
    anchors = []
    for i in range(1, 14):
        cf = f"{rid}-anchor-{i}.jpg"
        (server.UPLOAD_DIR / cf).write_bytes(b"x")
        files.append(server.UPLOAD_DIR / cf)
        a = {"i": i, "t": float(i), "box": dict(BOX), "crop_filename": cf}
        if (i - 1) in verify_idx:
            a["verify"] = True
        anchors.append(a)
    return {"subject_crop_filename": subj, "anchors": anchors}, files


# ── D: evidence identity refs prefer the 3 manual verify taps ───────────
def test_D_evidence_refs_prefer_the_3_manual_verify_taps():
    rid = f"fix00a-{uuid.uuid4().hex[:8]}"
    doc, files = _doc_with_crops(rid, verify_idx={10, 11, 12})
    try:
        refs = server._identity_ref_crops(doc)
        assert [Path(r).name for r in refs] == [
            f"{rid}-anchor-11.jpg", f"{rid}-anchor-12.jpg", f"{rid}-anchor-13.jpg"]
    finally:
        _cleanup(files)


def test_D2_partial_verify_fills_remaining_slots_in_legacy_order():
    rid = f"fix00a-{uuid.uuid4().hex[:8]}"
    doc, files = _doc_with_crops(rid, verify_idx={12})
    try:
        refs = server._identity_ref_crops(doc)
        assert [Path(r).name for r in refs] == [
            f"{rid}-anchor-13.jpg", f"{rid}-subject.jpg", f"{rid}-anchor-2.jpg"]
    finally:
        _cleanup(files)


# ── E: identity-profile refs — 3 verify within EXISTING budget of 5 ──────
def test_E_profile_refs_include_all_3_verify_within_budget_of_5():
    crops = [f"/tmp/fix00a-c{i}.jpg" for i in range(13)]
    vs = crops[10:13]
    out = server._prioritized_profile_crops(crops, vs)
    assert set(vs) <= set(out[:identity_verify.MAX_PROFILE_CROPS])
    assert sorted(out) == sorted(crops)  # same images — nothing added or removed


# ── F: legacy anchors without verify behave exactly as before ────────────
def test_F_legacy_docs_without_verify_unchanged():
    rid = f"fix00a-{uuid.uuid4().hex[:8]}"
    doc, files = _doc_with_crops(rid, verify_idx=set())
    try:
        refs = server._identity_ref_crops(doc)
        assert [Path(r).name for r in refs] == [
            f"{rid}-subject.jpg", f"{rid}-anchor-2.jpg", f"{rid}-anchor-3.jpg"]
    finally:
        _cleanup(files)
    assert server._prioritized_profile_crops(["a", "b", "c"], []) == ["a", "b", "c"]


def test_F2_legacy_anchor_json_without_verify_parses_unchanged():
    rid = f"fix00a-{uuid.uuid4().hex[:8]}"
    legacy = [{"t": float(i), "box": dict(BOX)} for i in range(5)]
    out = json.loads(server._detach_anchor_thumbs(json.dumps(legacy), rid))
    assert len(out) == 5
    assert all("verify" not in a and "segment" not in a for a in out)


def test_F3_legacy_anchors_behavioural_no_verify_no_segment(monkeypatch):
    rid = f"fix00a-{uuid.uuid4().hex[:8]}"
    created = []
    try:
        legacy = [{"t": float(i * 3), "box": dict(BOX)} for i in range(5)]
        _install_fakes(monkeypatch, created)
        rest, crops, wides, verifies = asyncio.run(server._build_original_anchor_payloads(
            rid, "/fake.mp4", legacy))
        assert len(rest) == 4 and len(verifies) == 0
        assert all("verify" not in a and "segment" not in a for a in rest)
        assert all(a.get("crop_filename") for a in rest)  # enrichment unchanged
    finally:
        _cleanup(created)


# ── G: verify follows the flag, never the array index ────────────────────
def test_G_verify_follows_flag_not_index():
    rid = f"fix00a-{uuid.uuid4().hex[:8]}"
    doc, files = _doc_with_crops(rid, verify_idx={1, 4, 7})
    try:
        refs = server._identity_ref_crops(doc)
        assert [Path(r).name for r in refs] == [
            f"{rid}-anchor-2.jpg", f"{rid}-anchor-5.jpg", f"{rid}-anchor-8.jpg"]
    finally:
        _cleanup(files)


# ── H + I: LLM call sites and image budgets unchanged ────────────────────
def test_H_I_llm_budgets_and_call_sites_unchanged():
    assert identity_verify.MAX_REF_CROPS == 3
    assert identity_verify.MAX_PROFILE_CROPS == 5
    assert identity_verify.MAX_PROFILE_WIDE == 3
    src = (BACKEND / "server.py").read_text()
    assert src.count("build_identity_profile(") == 1
    assert src.count("verify_preview_summary(") == 2


# ── 5: BEHAVIOURAL — the ACTUAL frontend serializer output ───────────────
def test_5_frontend_serializer_actual_payload():
    script = (
        "import('/app/frontend/src/lib/anchorSerialization.mjs').then(m => {"
        "const mk=(t,x)=>Object.assign({t,box:{x:0.11115,y:0.2,w:0.05,h:0.12}},x||{});"
        "const modern=[...Array(10).keys()].map(i=>mk(i*3,{segment:0}))"
        ".concat([0,1,2].map(i=>mk(60+i,{segment:1,verify:true})));"
        "const legacy=[mk(1),mk(2,{verify:'yes'}),mk(3,{verify:1})];"
        "console.log(JSON.stringify({modern:m.serializeMarkerAnchors(modern),"
        "legacy:m.serializeMarkerAnchors(legacy)}));"
        "}).catch(e=>{console.error(e);process.exit(1);});"
    )
    out = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    data = json.loads(out.stdout.strip())
    modern, legacy = data["modern"], data["legacy"]
    assert len(modern) == 13
    assert sum(1 for a in modern if a.get("verify") is True) == 3
    assert all("verify" not in a for a in modern[:10]), "verify never inferred"
    assert all("segment" in a for a in modern)
    assert [a.get("segment") for a in modern] == [0] * 10 + [1] * 3
    assert modern[0]["box"] == {"x": 0.1111, "y": 0.2, "w": 0.05, "h": 0.12}  # 4-dec rounding
    # legacy anchors: no segment key; non-boolean truthy verify is NOT sent
    assert all("segment" not in a and "verify" not in a for a in legacy)
    # UploadPage actually uses this serializer for the upload payload
    up = Path("/app/frontend/src/pages/UploadPage.jsx").read_text()
    assert "serializeMarkerAnchors(_markerAnchors)" in up
