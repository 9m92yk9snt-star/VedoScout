# FIX 02 — FAIL-CLOSED VERIFICATION behavioural tests.
# Deterministic only: pure helpers, FakeDB-free, monkeypatched verifier seams,
# node-run frontend helpers. ZERO live LLM calls, zero real video analysis.
import asyncio
import json
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

import server  # noqa: E402
from evidence_authority import (  # noqa: E402
    apply_fail_closed_proof_authority,
    attach_event_evidence_authority,
    compute_proof_frame_verified,
)
from score_meaning import _pick_evidence  # noqa: E402

AUTHORITY_MJS = BACKEND.parent / "frontend" / "src" / "lib" / "authorityJoin.mjs"


def _evt(ts, **kw):
    return {"timestamp": ts, "title": f"evt {ts}", "action_type": "pass", **kw}


def _com(ts, **kw):
    return {"timestamp": ts, "comment": f"com {ts}", **kw}


def _run_xv(timeline, verdicts):
    full = {"action_timeline": timeline, "scores": {}}
    verify = {"verdicts": verdicts, "independent_scores": {}}
    meta = server._apply_cross_verification(full, verify, None)
    return full, meta


# ---------- T1 — fully confirmed survives ----------

def test_T1_confirmed_survives():
    full, meta = _run_xv(
        [_evt("00:10")],
        [{"claim_id": 0, "identity": "CONFIRMED", "event": "CONFIRMED"}],
    )
    assert len(full["action_timeline"]) == 1
    assert full["action_timeline"][0]["cross_verified"] is True
    assert meta["status"] == "verified"


def test_T1b_corrected_timestamp_only_for_confirmed():
    full, _ = _run_xv(
        [_evt("00:10"), _evt("00:20")],
        [{"claim_id": 0, "identity": "CONFIRMED", "event": "CONFIRMED", "corrected_timestamp": "00:12"},
         {"claim_id": 1, "identity": "NOT_VISIBLE", "event": "CONFIRMED", "corrected_timestamp": "00:25"}],
    )
    assert len(full["action_timeline"]) == 1
    assert full["action_timeline"][0]["timestamp"] == "00:12"  # applied to confirmed


# ---------- T2 — NOT_VISIBLE removed ----------

def test_T2_not_visible_removed():
    full, meta = _run_xv(
        [_evt("00:10")],
        [{"claim_id": 0, "identity": "NOT_VISIBLE", "event": "CONFIRMED"}],
    )
    assert full["action_timeline"] == []
    assert meta["dropped"][0]["reason"] == "NOT_VISIBLE"


# ---------- T3 — WRONG_PLAYER removed ----------

def test_T3_wrong_player_removed():
    full, meta = _run_xv(
        [_evt("00:10")],
        [{"claim_id": 0, "identity": "WRONG_PLAYER", "event": "CONFIRMED"}],
    )
    assert full["action_timeline"] == []
    assert meta["dropped"][0]["reason"] == "WRONG_PLAYER"


# ---------- T4 — NOT_SEEN removed ----------

def test_T4_not_seen_removed():
    full, meta = _run_xv(
        [_evt("00:10")],
        [{"claim_id": 0, "identity": "CONFIRMED", "event": "NOT_SEEN"}],
    )
    assert full["action_timeline"] == []
    assert meta["dropped"][0]["reason"] == "NOT_SEEN"


# ---------- T5 — missing verdict removed ----------

def test_T5_missing_verdict_removed():
    full, meta = _run_xv([_evt("00:10")], [])
    assert full["action_timeline"] == []
    assert meta["dropped"][0]["reason"] == "NO_VERDICT"


def test_T5b_missing_identity_or_event_removed():
    full, meta = _run_xv(
        [_evt("00:10"), _evt("00:20")],
        [{"claim_id": 0, "event": "CONFIRMED"},
         {"claim_id": 1, "identity": "CONFIRMED"}],
    )
    assert full["action_timeline"] == []
    assert {d["reason"] for d in meta["dropped"]} == {"INVALID_VERDICT"}


# ---------- T6 — malformed / unknown verdict removed ----------

def test_T6_malformed_and_unknown_removed():
    full, meta = _run_xv(
        [_evt("00:10"), _evt("00:20")],
        [{"claim_id": 0, "identity": "MAYBE", "event": "CONFIRMED"},
         "garbage-not-a-dict"],
    )
    assert full["action_timeline"] == []
    reasons = {d["reason"] for d in meta["dropped"]}
    assert reasons == {"INVALID_VERDICT", "NO_VERDICT"}


# ---------- T7 — all rejected: EMPTY, never restored ----------

def test_T7_all_rejected_timeline_stays_empty():
    full, meta = _run_xv(
        [_evt("00:10"), _evt("00:20"), _evt("00:30")],
        [{"claim_id": 0, "identity": "WRONG_PLAYER", "event": "CONFIRMED"},
         {"claim_id": 1, "identity": "NOT_VISIBLE", "event": "CONFIRMED"},
         {"claim_id": 2, "identity": "CONFIRMED", "event": "NOT_SEEN"}],
    )
    assert full["action_timeline"] == []          # NEVER restored
    assert meta["status"] == "rejected_all"
    assert len(meta["dropped"]) == 3


# ---------- T8 — verifier error is not success ----------

def test_T8_cross_verifier_error_fails_closed(monkeypatch):
    async def boom(**kw):
        raise RuntimeError("gemini down")
    monkeypatch.setattr(server, "call_gemini_with_video", boom)
    full = {"action_timeline": [_evt("00:10"), _evt("00:20")], "scores": {}}
    asyncio.run(server._cross_verify_full_report(
        "fix02-t8", full,
        file_path="video.mp4", marker_path=None, crop_path_str=None,
        anchor_crops=[], anchor_payload_list=[], gt_track=None, gt_t_off=0.0, doc={},
    ))
    assert full["action_timeline"] == []          # pass-1 never exposed as verified
    cv = full["cross_verification"]
    assert cv["status"] == "fail_closed_error"
    assert cv["events_checked"] == 2 and cv["events_dropped"] == 2


# ---------- T9 / T10 — proof eligibility ----------

def _proofed_body():
    full = {
        "action_timeline": [
            _evt("00:36", cross_verified=True),
            _evt("00:50", cross_verified=False),
            _evt("01:00"),  # no verifier state at all
        ],
        "video_comments": [
            _com("00:36"),   # binds to verified event
            _com("00:50"),   # binds to unverified event
            _com("00:38"),   # unbound
        ],
    }
    attach_event_evidence_authority(full)
    apply_fail_closed_proof_authority(full)
    return full


def test_T9_verified_exact_bind_is_proof_verified():
    full = _proofed_body()
    assert full["action_timeline"][0]["proof_verified"] is True
    assert full["video_comments"][0]["proof_verified"] is True


def test_T10_unbound_ambiguous_rejected_are_not_proof():
    full = _proofed_body()
    assert full["action_timeline"][1]["proof_verified"] is False
    assert full["action_timeline"][2]["proof_verified"] is False
    assert full["video_comments"][1]["proof_verified"] is False  # rejected event
    assert full["video_comments"][2]["proof_verified"] is False  # unbound
    # ambiguous: two verified events at same ms -> comment unbound -> False
    amb = {
        "action_timeline": [_evt("00:36", cross_verified=True), _evt("00:36", cross_verified=True)],
        "video_comments": [_com("00:36")],
    }
    attach_event_evidence_authority(amb)
    apply_fail_closed_proof_authority(amb)
    assert amb["video_comments"][0]["proof_verified"] is False


# ---------- T11 — structured rows inherit ONLY via exact IDs ----------

def test_T11_structured_rows_inherit_via_ids():
    full = {
        "action_timeline": [_evt("00:36", cross_verified=True)],
        "video_comments": [_com("00:36"), _com("00:50")],
        "technical": {"passing": {"score": 7, "evidence": [
            {"timestamp": "00:36", "what": "verified"},
            {"timestamp": "00:50", "what": "bound but unverified event-less"},
            {"timestamp": "00:41", "what": "unbound"},
        ]}},
        "snapshot_moments": [{"key": "strength", "timestamp": "00:36"},
                             {"key": "noticed", "timestamp": "00:50"}],
        "parents_package": {"watch_together": {"moments": [{"timestamp": "00:36", "say_this": "x"}]}},
        "grow_your_game": {"lessons": [{"topic_id": "t", "moments": [{"timestamp": "00:50", "what": "y"}]}]},
        "parent_value_metrics": {"reaction_after_mistake": {"timestamp": "00:36", "rating": "strong"}},
    }
    attach_event_evidence_authority(full)
    apply_fail_closed_proof_authority(full)
    rows = full["technical"]["passing"]["evidence"]
    assert rows[0]["proof_verified"] is True
    assert rows[1]["proof_verified"] is False
    assert rows[2]["proof_verified"] is False
    assert full["snapshot_moments"][0]["proof_verified"] is True
    assert full["snapshot_moments"][1]["proof_verified"] is False
    assert full["parents_package"]["watch_together"]["moments"][0]["proof_verified"] is True
    assert full["grow_your_game"]["lessons"][0]["moments"][0]["proof_verified"] is False
    assert full["parent_value_metrics"]["reaction_after_mistake"]["proof_verified"] is True


# ---------- T12 / T13 — Score Meaning ----------

def test_T12_score_meaning_authority_fail_closed():
    vsecs = [("anchor", 36.0), ("anchor", 50.0)]
    # verified candidate exists -> may select it (state preserved)
    out = _pick_evidence(
        [{"timestamp": "00:50", "evidence_id": "E2", "proof_verified": False},
         {"timestamp": "00:36", "evidence_id": "E1", "event_id": "EV1", "proof_verified": True}],
        vsecs, [], None, authority=True,
    )
    assert out["timestamp"] == "00:36"
    assert out["evidence_id"] == "E1" and out["event_id"] == "EV1"
    assert out["proof_verified"] is True
    # no verified evidence -> None; NEVER an unverified fallback
    out2 = _pick_evidence(
        [{"timestamp": "00:50", "evidence_id": "E2", "proof_verified": False},
         {"timestamp": "00:40", "evidence_id": "E3"}],
        vsecs, [], None, authority=True,
    )
    assert out2 is None


def test_T13_score_meaning_legacy_unchanged():
    vsecs = [("anchor", 36.0)]
    out = _pick_evidence([{"timestamp": "00:36"}], vsecs, [], None)
    assert out == {"timestamp": "00:36", "verified": True}


# ---------- T14 / T15 — frame identity fails closed ----------

def _frame_doc():
    return {"fingerprint": {}, "player_details": {"jersey_color": "red"}}


def _run_verify(monkeypatch, tmp_path, verdict_fn, enriched):
    frames_dir = tmp_path / "frames"
    frames_dir.mkdir(exist_ok=True)
    for c in enriched:
        if c.get("_make_file"):
            (frames_dir / Path(str(c["frame_url"])).name).write_bytes(b"jpg")
    monkeypatch.setattr(server, "verify_frame_identity", verdict_fn)
    async def no_sleep(_):
        return None
    monkeypatch.setattr(server.asyncio, "sleep", no_sleep)
    try:
        stats = asyncio.run(server._verify_enriched_frames(
            "fix02-frames", _frame_doc(), tmp_path / "v.mp4", frames_dir, enriched, ["ref.jpg"],
        ))
    finally:
        monkeypatch.undo()
    return stats


def test_T14_persistent_error_fails_closed_without_hard_reject(monkeypatch, tmp_path):
    async def always_error(*a, **kw):
        return "error"
    c = {**_com("00:36"), "frame_url": "/api/uploads/frames/x/f1.jpg", "_make_file": True}
    stats = _run_verify(monkeypatch, tmp_path, always_error, [c])
    assert c["identity_verified"] is False           # never null while usable
    assert c["identity_verification_status"] == "error"
    assert c["frame_url"] is None                    # unusable as proof
    assert c.get("identity_hard_reject") is not True  # infra != WRONG_PLAYER
    assert stats["hard_rejected"] == 0


def test_T14b_task_exception_fails_closed_without_hard_reject(monkeypatch, tmp_path):
    async def raises(*a, **kw):
        raise RuntimeError("api exploded")
    c = {**_com("00:36"), "frame_url": "/api/uploads/frames/x/f2.jpg", "_make_file": True}
    stats = _run_verify(monkeypatch, tmp_path, raises, [c])
    assert c["identity_verified"] is False
    assert c["identity_verification_status"] == "error"
    assert c["frame_url"] is None
    assert c.get("identity_hard_reject") is not True
    assert stats["hard_rejected"] == 0


def test_T15_missing_frame_cannot_become_proof(monkeypatch, tmp_path):
    async def never_called(*a, **kw):
        raise AssertionError("verifier must not run for a missing frame")
    c = {**_com("00:36"), "frame_url": "/api/uploads/frames/x/gone.jpg"}
    _run_verify(monkeypatch, tmp_path, never_called, [c])
    assert c["identity_verified"] is False
    assert c["identity_verification_status"] == "missing"
    assert c["frame_url"] is None
    assert c.get("identity_hard_reject") is not True


def test_T14c_confirmed_sets_status(monkeypatch, tmp_path):
    async def confirmed(*a, **kw):
        return "confirmed"
    c = {**_com("00:36"), "frame_url": "/api/uploads/frames/x/f3.jpg", "_make_file": True}
    _run_verify(monkeypatch, tmp_path, confirmed, [c])
    assert c["identity_verified"] is True
    assert c["identity_verification_status"] == "confirmed"
    assert c["frame_url"] is not None


# ---------- T16 / T17 — exact frame moment requirement ----------

def test_T16_shifted_replacement_frame_is_not_proof_frame():
    c = {**_com("00:36"), "evidence_id": "e", "proof_verified": True,
         "identity_verified": True, "frame_url": "/f/x.jpg",
         "evidence_time_ms": 36000, "frame_time_ms": 38000}
    assert compute_proof_frame_verified(c) is False   # internal info, never proof
    # evidence_time_ms itself untouched by the check
    assert c["evidence_time_ms"] == 36000


def test_T17_exact_verified_frame_is_proof_frame():
    c = {**_com("00:36"), "evidence_id": "e", "proof_verified": True,
         "identity_verified": True, "frame_url": "/f/x.jpg",
         "evidence_time_ms": 36000, "frame_time_ms": 36000}
    assert compute_proof_frame_verified(c) is True


def test_T17b_gate_conditions():
    base = {"evidence_id": "e", "frame_url": "/f/x.jpg",
            "evidence_time_ms": 36000, "frame_time_ms": 36000}
    assert compute_proof_frame_verified({**base, "proof_verified": False,
                                         "identity_verified": True}) is False
    assert compute_proof_frame_verified({**base, "proof_verified": True,
                                         "identity_verified": None}) is False
    assert compute_proof_frame_verified({**base, "proof_verified": True,
                                         "identity_verified": True,
                                         "frame_url": None}) is False
    # C01 — anchor_locked is identity ground truth ONLY: it substitutes for
    # identity_verified but NEVER waives the exact-time requirement.
    assert compute_proof_frame_verified({**base, "proof_verified": True,
                                         "anchor_locked": True,
                                         "frame_time_ms": 36800}) is False
    assert compute_proof_frame_verified({**base, "proof_verified": True,
                                         "anchor_locked": True}) is True  # 36000 == 36000
    # placeholder frames are never proof
    assert compute_proof_frame_verified({**base, "proof_verified": True,
                                         "identity_verified": True,
                                         "frame_placeholder": True}) is False


# ---------- T18 / T19 / T20 — frontend fail closed ----------

def _run_node(script: str) -> dict:
    out = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        capture_output=True, text=True, timeout=30,
    )
    assert out.returncode == 0, f"node failed: {out.stderr}"
    return json.loads(out.stdout.strip().splitlines()[-1])


def test_T18_frame_lookup_fail_closed():
    script = f"""
import {{ buildFrameLookup, resolveAuthorityFrame }} from "file://{AUTHORITY_MJS}";
const comments = [
  {{ timestamp: "00:36", evidence_id: "evd_ok", frame_url: "/f/ok.jpg", identity_verified: true, proof_frame_verified: true }},
  {{ timestamp: "00:40", evidence_id: "evd_noproof", frame_url: "/f/np.jpg", identity_verified: true }},
  {{ timestamp: "00:44", evidence_id: "evd_null", frame_url: "/f/null.jpg" }},
  {{ timestamp: "00:48", evidence_id: "evd_false", frame_url: "/f/false.jpg", identity_verified: false, proof_frame_verified: false }},
];
const lk = buildFrameLookup(comments, true);
const ok = lk.find("00:36", {{ evidenceId: "evd_ok" }});
const lk2 = buildFrameLookup(comments, true);
const noproof = lk2.find("00:40", {{ evidenceId: "evd_noproof" }});
const nul = buildFrameLookup(comments, true).find("00:44", {{ evidenceId: "evd_null" }});
const rej = buildFrameLookup(comments, true).find("00:48", {{ evidenceId: "evd_false" }});
const raOk = resolveAuthorityFrame(comments, {{ evidence_id: "evd_ok" }});
const raNo = resolveAuthorityFrame(comments, {{ evidence_id: "evd_noproof" }});
console.log(JSON.stringify({{
  ok: ok && ok.url, noproof: noproof === null, nul: nul === null, rej: rej === null,
  raOk: raOk && raOk.frame_url, raNo: raNo === null,
}}));
"""
    r = _run_node(script)
    assert r["ok"] == "/f/ok.jpg"
    assert r["noproof"] is True and r["nul"] is True and r["rej"] is True
    assert r["raOk"] == "/f/ok.jpg" and r["raNo"] is True


def test_T19_proof_clip_requires_proof_verified():
    script = f"""
import {{ resolveProofClip }} from "file://{AUTHORITY_MJS}";
const comments = [
  {{ timestamp: "00:36", evidence_id: "evd_A", proof_verified: false, tele_clip_url: "/clips/A.mp4" }},
  {{ timestamp: "00:40", evidence_id: "evd_B", event_id: "EVT-B", proof_verified: true, tele_clip_url: "/clips/B.mp4" }},
  {{ timestamp: "00:44", evidence_id: "evd_L", tele_clip_url: "/clips/L.mp4" }},
];
const blocked = resolveProofClip(comments, {{ evidenceId: "evd_A" }}, true);
const okEvd = resolveProofClip(comments, {{ evidenceId: "evd_B" }}, true);
const okEvt = resolveProofClip(comments, {{ eventId: "EVT-B" }}, true);
const legacy = resolveProofClip(comments, {{ timestamp: "00:44" }}, false);
console.log(JSON.stringify({{
  blocked: blocked === null,
  okEvd: okEvd && okEvd.tele_clip_url,
  okEvt: okEvt && okEvt.tele_clip_url,
  legacy: legacy && legacy.tele_clip_url,
}}));
"""
    r = _run_node(script)
    assert r["blocked"] is True
    assert r["okEvd"] == "/clips/B.mp4" and r["okEvt"] == "/clips/B.mp4"
    assert r["legacy"] == "/clips/L.mp4"


def test_T20_can_use_authority_proof_requires_proof_state():
    script = f"""
import {{ canUseAuthorityProof }} from "file://{AUTHORITY_MJS}";
console.log(JSON.stringify({{
  idOnly: canUseAuthorityProof(true, {{ evidenceId: "evd_A" }}),
  idProof: canUseAuthorityProof(true, {{ evidenceId: "evd_A", proof_verified: true }}),
  camel: canUseAuthorityProof(true, {{ eventId: "evt_A", proofVerified: true }}),
  proofNoId: canUseAuthorityProof(true, {{ proof_verified: true }}),
  legacy: canUseAuthorityProof(false, {{ timestamp: "00:36" }}),
}}));
"""
    r = _run_node(script)
    assert r["idOnly"] is False       # ID alone no longer sufficient
    assert r["idProof"] is True and r["camel"] is True
    assert r["proofNoId"] is False
    assert r["legacy"] is True


# ---------- T21 — ActionTimeline defense-in-depth ----------

def test_T21_action_timeline_gating():
    script = f"""
import {{ canUseAuthorityProof }} from "file://{AUTHORITY_MJS}";
console.log(JSON.stringify({{
  unverified: canUseAuthorityProof(true, {{ event_id: "evt_X", proof_verified: false }}),
  verified: canUseAuthorityProof(true, {{ event_id: "evt_X", proof_verified: true }}),
}}));
"""
    r = _run_node(script)
    assert r["unverified"] is False and r["verified"] is True
    # wiring: derive passes proofable/eventId; the row is non-clickable when false
    rv2 = BACKEND.parent / "frontend" / "src" / "components" / "report-v2"
    sections = (rv2 / "sections.jsx").read_text()
    assert "const clickable = a.proofable !== false;" in sections
    assert "onClick: () => onPlayAt?.(a.timestamp, { eventId: a.eventId })" in sections
    derive = (rv2 / "derive.js").read_text()
    assert "proofable: canUseAuthorityProof(authority, a)" in derive


# ---------- T22 — zero new production model calls ----------

def test_T22_no_new_model_call_sites():
    src = (BACKEND / "server.py").read_text()
    assert src.count("call_gemini_with_video(") == 7
    assert src.count("call_gemini_text(") == 2
    assert src.count("verify_frame_identity(") == 5
    assert src.count("verify_ring_placement(") == 1
    assert src.count("verify_preview_summary(") == 2
    # deterministic layer wiring: exactly the two shared-pipeline call sites
    assert src.count("apply_fail_closed_proof_authority(") == 2
    assert src.count("compute_proof_frame_verified(") == 3
    ea = (BACKEND / "evidence_authority.py").read_text().lower()
    for banned in ("gemini", "openai", "httpx", "emergent", "llmchat"):
        assert banned not in ea
    sm = (BACKEND / "score_meaning.py").read_text().lower()
    for banned in ("gemini", "openai", "httpx", "llmchat"):
        assert banned not in sm


# ==================================================================
# FIX 02 — CORRECTION 01
# ==================================================================

def test_C01_anchor_locked_requires_exact_time():
    base = {"evidence_id": "e", "proof_verified": True, "frame_url": "/f/x.jpg",
            "anchor_locked": True, "evidence_time_ms": 36000}
    # shifted anchor frame: identity trusted, time NOT exact -> never proof
    assert compute_proof_frame_verified({**base, "frame_time_ms": 36800}) is False
    # exact anchor frame -> proof allowed
    assert compute_proof_frame_verified({**base, "frame_time_ms": 36000}) is True
    # anchor substitutes only for identity; all other gates still apply
    assert compute_proof_frame_verified({**base, "frame_time_ms": 36000,
                                         "proof_verified": False}) is False
    assert compute_proof_frame_verified({**base, "frame_time_ms": None}) is False


def test_C01_video_highlight_fail_closed():
    script = f"""
import {{ selectEvidenceHighlight }} from "file://{AUTHORITY_MJS}";
const unverified = [
  {{ timestamp: "00:36", comment: "a", evidence_id: "e1", frame_url: "/f/1.jpg", identity_verified: true, proof_verified: false }},
  {{ timestamp: "00:40", comment: "b", evidence_id: "e2", proof_verified: false }},
];
const mixed = [
  {{ timestamp: "00:36", comment: "a", evidence_id: "e1", frame_url: "/f/1.jpg", identity_verified: true, proof_verified: false }},
  {{ timestamp: "00:40", comment: "b", evidence_id: "e2", proof_verified: true }},
  {{ timestamp: "00:44", comment: "c", evidence_id: "e3", frame_url: "/f/3.jpg", proof_verified: true, proof_frame_verified: true }},
];
const legacy = [
  {{ timestamp: "00:10", comment: "x" }},
  {{ timestamp: "00:20", comment: "y", frame_url: "/f/y.jpg" }},
  {{ timestamp: "00:30", comment: "z", frame_url: "/f/z.jpg", identity_verified: true }},
];
const A = selectEvidenceHighlight(unverified, true);
const B = selectEvidenceHighlight(mixed, true);
const C = selectEvidenceHighlight(legacy, false);
const C2 = selectEvidenceHighlight([legacy[0], legacy[1]], false);
console.log(JSON.stringify({{
  A: A === null,
  B: B && B.evidence_id,
  C: C && C.comment,
  C2: C2 && C2.comment,
}}));
"""
    r = _run_node(script)
    assert r["A"] is True                 # unverified never becomes the highlight
    assert r["B"] == "e3"                 # proof_verified (frame-proof preferred)
    assert r["C"] == "z" and r["C2"] == "y"  # legacy chain unchanged
