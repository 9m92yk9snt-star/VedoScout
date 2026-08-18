"""
FIX 00A — Tap Authority Contract regression tests.

Proves the 3 manual Scout Mode verification taps (verify:true) keep their
role through: upload parse → persistence → tracker seeding → identity
reference selection. Deterministic — NO live Gemini/GPT calls, no video
decoding, no Mongo writes.

Run: cd /app/backend && python -m pytest tests/test_fix00a_tap_authority.py -v
"""
import base64
import json
import sys
import uuid
from pathlib import Path

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


def _doc_with_crops(rid, verify_idx):
    """Report-like doc: subject crop + anchors 1..13 with crop files on disk.
    verify_idx = 0-based positions in the anchors list flagged verify:true."""
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
            assert "segment" in a
            assert "t" in a and "box" in a
    finally:
        _cleanup(created)


def test_A2_persistence_covers_all_13_original_anchors():
    assert server.ORIGINAL_ANCHOR_LIMIT == 13
    src = (BACKEND / "server.py").read_text()
    assert "all_anchors[1:ORIGINAL_ANCHOR_LIMIT]" in src
    assert '**({"verify": True} if a.get("verify") else {})' in src
    assert '"segment": int(a["segment"])' in src


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


# ── E: identity-profile tight refs — 3 verify within EXISTING budget of 5 ─
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


# ── Frontend contract: serialization preserves verify + segment ──────────
def test_frontend_serializes_verify_and_segment():
    up = Path("/app/frontend/src/pages/UploadPage.jsx").read_text()
    assert "a.verify === true" in up
    assert "a.segment" in up
    sm = Path("/app/frontend/src/components/marker-studio/ScoutMode.jsx").read_text()
    assert "verify: true" in sm
    ms = Path("/app/frontend/src/components/MarkerStudio.jsx").read_text()
    assert "verify: a.verify || undefined" in ms
