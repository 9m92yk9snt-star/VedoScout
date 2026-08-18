# FIX 01 — EVENT / EVIDENCE AUTHORITY behavioural tests.
# Deterministic only: FakeDB-free pure helpers, monkeypatched frame extraction,
# node-run frontend helpers. ZERO live LLM calls, zero real video decoding.
import json
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from evidence_authority import (  # noqa: E402
    EVIDENCE_AUTHORITY_VERSION,
    attach_clip_authority,
    attach_event_evidence_authority,
    frame_time_ms,
    ts_to_ms,
)

AUTHORITY_MJS = BACKEND.parent / "frontend" / "src" / "lib" / "authorityJoin.mjs"


def _evt(ts, **kw):
    return {"timestamp": ts, "title": f"evt {ts}", "action_type": "pass", **kw}


def _com(ts, **kw):
    return {"timestamp": ts, "comment": f"com {ts}", **kw}


def _body(events, comments, **extra):
    b = {"action_timeline": events, "video_comments": comments}
    b.update(extra)
    return b


# ---------- canonical time parsing ----------

def test_ts_to_ms_canonical():
    assert ts_to_ms("00:36") == 36000
    assert ts_to_ms("12:05") == 725000
    assert ts_to_ms("1:02:03") == 3723000
    assert ts_to_ms("00:36.250") == 36250
    assert ts_to_ms(36) == 36000
    assert ts_to_ms(37.5) == 37500
    assert ts_to_ms("General") is None
    assert ts_to_ms(None) is None
    assert ts_to_ms(True) is None


# ---------- TEST 1 — unique IDs ----------

def test_T1_unique_ids():
    full = _body([_evt("00:10"), _evt("00:20"), _evt("00:30")],
                 [_com("00:10"), _com("00:21"), _com("00:30")])
    attach_event_evidence_authority(full)
    ev_ids = [e["event_id"] for e in full["action_timeline"]]
    evd_ids = [c["evidence_id"] for c in full["video_comments"]]
    assert len(set(ev_ids)) == 3 and all(ev_ids)
    assert len(set(evd_ids)) == 3 and all(evd_ids)
    assert full["evidence_authority_version"] == EVIDENCE_AUTHORITY_VERSION == 1
    assert full["authority_run_id"]
    assert full["action_timeline"][0]["event_start_ms"] == 10000
    assert full["action_timeline"][0]["event_end_ms"] == 10000  # point event
    assert full["video_comments"][1]["evidence_time_ms"] == 21000
    # presentation timestamps untouched
    assert full["action_timeline"][2]["timestamp"] == "00:30"
    assert full["video_comments"][2]["timestamp"] == "00:30"


# ---------- TEST 2 — idempotence ----------

def test_T2_idempotent():
    full = _body([_evt("00:10"), _evt("00:20")], [_com("00:10")])
    attach_event_evidence_authority(full)
    snap = json.loads(json.dumps(full))
    attach_event_evidence_authority(full)
    assert full == snap  # IDs, run id and ms fields all unchanged


# ---------- TEST 3 — filter stability ----------

def test_T3_filter_stability():
    full = _body([_evt("00:10"), _evt("00:20"), _evt("00:30")], [])
    attach_event_evidence_authority(full)
    id_a = full["action_timeline"][0]["event_id"]
    id_c = full["action_timeline"][2]["event_id"]
    # verifier drops B
    full["action_timeline"] = [full["action_timeline"][0], full["action_timeline"][2]]
    attach_event_evidence_authority(full)
    assert full["action_timeline"][0]["event_id"] == id_a
    assert full["action_timeline"][1]["event_id"] == id_c  # never renumbered


# ---------- TEST 4 — exact bind ----------

def test_T4_exact_bind():
    full = _body([_evt("00:36")], [_com("00:36")])
    attach_event_evidence_authority(full)
    assert full["video_comments"][0]["event_id"] == full["action_timeline"][0]["event_id"]


# ---------- TEST 5 — no nearest bind ----------

def test_T5_no_nearest_bind():
    full = _body([_evt("00:36")], [_com("00:38")])
    attach_event_evidence_authority(full)
    assert "event_id" not in full["video_comments"][0]


# ---------- TEST 6 — ambiguous bind ----------

def test_T6_ambiguous_bind():
    full = _body([_evt("00:36"), _evt("00:36")], [_com("00:36")])
    attach_event_evidence_authority(full)
    c = full["video_comments"][0]
    assert "event_id" not in c  # never guess
    assert c.get("event_binding_ambiguous") is True


# ---------- TEST 7 — skill evidence ----------

def test_T7_skill_evidence():
    full = _body(
        [_evt("00:36")],
        [_com("00:36")],
        technical={"passing": {"score": 7, "evidence": [
            {"timestamp": "00:36", "what": "switch of play"},
            {"timestamp": "00:50", "what": "no matching comment"},
        ]}},
    )
    attach_event_evidence_authority(full)
    rows = full["technical"]["passing"]["evidence"]
    assert rows[0]["evidence_id"] == full["video_comments"][0]["evidence_id"]
    assert rows[0]["event_id"] == full["action_timeline"][0]["event_id"]
    assert "evidence_id" not in rows[1] and "event_id" not in rows[1]
    # text/timestamp untouched, nothing deleted
    assert rows[0]["what"] == "switch of play" and rows[0]["timestamp"] == "00:36"
    assert len(rows) == 2


def test_T7b_skill_evidence_ambiguous_comment():
    full = _body(
        [],
        [_com("00:36"), _com("00:36")],
        tactical={"positioning": {"score": 6, "evidence": [
            {"timestamp": "00:36", "what": "two exact comments"},
        ]}},
    )
    attach_event_evidence_authority(full)
    assert "evidence_id" not in full["tactical"]["positioning"]["evidence"][0]


# ---------- TEST 8 — frame time distinction ----------

def test_T8_frame_time_distinction_helper():
    assert frame_time_ms(38.0, 36.0) == 38000   # replacement frame wins
    assert frame_time_ms(None, 36.0) == 36000   # cited extraction time
    assert frame_time_ms(None, None) is None
    assert frame_time_ms(True, 36.0) == 36000   # bool is not a time


def test_T8_frame_time_distinction_pipeline(monkeypatch, tmp_path):
    import server

    def fake_extract(video_path, seconds, out_path, *a, **kw):
        Path(out_path).write_bytes(b"jpg")
        return True

    monkeypatch.setattr(server, "_extract_video_frame", fake_extract)
    vid = tmp_path / "v.mp4"
    vid.write_bytes(b"x")
    full = _body([], [_com("00:36")])
    attach_event_evidence_authority(full)
    doc = {
        "id": "fix01-frame-test",
        "full_report": full,
        # user tap at 37.0 + calibrated drift 1.0 → ACTUAL frame at 38.0s
        "anchors": [{"t": 37.0, "box": {"x": 0.1, "y": 0.1, "w": 0.1, "h": 0.2}}],
        "anchor_time_offset": 1.0,
    }
    enriched = server.ensure_video_frames(doc, str(vid))
    c = enriched[0]
    assert c["evidence_time_ms"] == 36000       # cited moment untouched
    assert c["frame_picked_ts"] == 38.0
    assert c["frame_time_ms"] == 38000          # ACTUAL frame moment recorded
    import shutil
    shutil.rmtree(server.UPLOAD_DIR / "frames" / "fix01-frame-test", ignore_errors=True)


def test_T8_legacy_comment_gets_no_frame_time(monkeypatch, tmp_path):
    import server

    def fake_extract(video_path, seconds, out_path, *a, **kw):
        Path(out_path).write_bytes(b"jpg")
        return True

    monkeypatch.setattr(server, "_extract_video_frame", fake_extract)
    vid = tmp_path / "v.mp4"
    vid.write_bytes(b"x")
    doc = {"id": "fix01-legacy-frame", "full_report": _body([], [_com("00:36")])}
    enriched = server.ensure_video_frames(doc, str(vid))  # no authority attach
    assert "frame_time_ms" not in enriched[0]
    import shutil
    shutil.rmtree(server.UPLOAD_DIR / "frames" / "fix01-legacy-frame", ignore_errors=True)


# ---------- TEST 9 — clip metadata ----------

def test_T9_clip_metadata_evidence_bound():
    c = {"evidence_id": "evd_x", "evidence_time_ms": 36000}
    attach_clip_authority(c, 33.5, 39.5, {})
    assert c["clip_start_ms"] == 33500
    assert c["clip_end_ms"] == 39500
    assert c["moment_local_ms"] == 2500
    assert c["clip_id"].startswith("clip_")


def test_T9_clip_metadata_event_bound_takes_priority():
    c = {"evidence_id": "evd_x", "evidence_time_ms": 35000, "event_id": "evt_y"}
    attach_clip_authority(c, 33.5, 39.5, {"evt_y": 36000})
    assert c["moment_local_ms"] == 36000 - 33500  # authoritative event moment


def test_T9_clip_metadata_legacy_row_untouched():
    c = {"timestamp": "00:36"}  # legacy: no authority evidence_id
    attach_clip_authority(c, 33.5, 39.5, {})
    assert "clip_id" not in c and "clip_start_ms" not in c


# ---------- TEST 14 — corrective replacement namespace ----------

def test_T14_corrective_new_namespace():
    original = _body([_evt("00:10")], [_com("00:10")])
    attach_event_evidence_authority(original)
    # corrective replacement = brand-new analysis body from full-retry
    replacement = _body([_evt("00:10")], [_com("00:10")])
    attach_event_evidence_authority(replacement)
    assert replacement["authority_run_id"] != original["authority_run_id"]
    assert (replacement["action_timeline"][0]["event_id"]
            != original["action_timeline"][0]["event_id"])
    assert (replacement["video_comments"][0]["evidence_id"]
            != original["video_comments"][0]["evidence_id"])


def test_T14_both_pipelines_use_same_helper():
    src = (BACKEND / "server.py").read_text()
    # exactly two production call sites: normal full report + corrective pass
    assert src.count("attach_event_evidence_authority(") == 2
    assert "full = attach_event_evidence_authority(full)" in src
    assert "retry = attach_event_evidence_authority(retry)" in src


# ---------- TEST 15 — zero new LLM cost ----------

def test_T15_no_new_llm_call_sites():
    src = (BACKEND / "server.py").read_text()
    # pinned pre-FIX-01 model-call-site counts — FIX 01 adds none
    assert src.count("call_gemini_with_video(") == 7
    assert src.count("call_gemini_text(") == 2
    assert src.count("verify_frame_identity(") == 5
    assert src.count("verify_ring_placement(") == 1
    assert src.count("verify_preview_summary(") == 2
    ea = (BACKEND / "evidence_authority.py").read_text()
    for banned in ("gemini", "openai", "gpt", "httpx", "requests", "llm",
                   "emergent", "LlmChat", "UserMessage"):
        assert banned not in ea.lower() or banned == "llm" and "llm calls" in ea.lower()
    import evidence_authority as ea_mod
    assert set(n for n in dir(ea_mod) if n in ("re", "uuid")) == {"re", "uuid"}


# ---------- frontend node tests (T10–T13) ----------

def _run_node(script: str) -> dict:
    out = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        capture_output=True, text=True, timeout=30,
    )
    assert out.returncode == 0, f"node failed: {out.stderr}"
    return json.loads(out.stdout.strip().splitlines()[-1])


def test_T10_duplicate_timestamp_proof_uses_evidence_id():
    script = f"""
import {{ resolveProofClip }} from "file://{AUTHORITY_MJS}";
const comments = [
  {{ timestamp: "00:36", evidence_id: "evd_A", tele_clip_url: "/clips/A.mp4" }},
  {{ timestamp: "00:36", evidence_id: "evd_B", tele_clip_url: "/clips/B.mp4" }},
];
const auth = resolveProofClip(comments, {{ evidenceId: "evd_B", timestamp: "00:36" }}, true);
const legacy = resolveProofClip(comments, {{ timestamp: "00:36" }}, false);
console.log(JSON.stringify({{ auth: auth.tele_clip_url, legacy: legacy.tele_clip_url }}));
"""
    r = _run_node(script)
    assert r["auth"] == "/clips/B.mp4"      # never A's clip
    assert r["legacy"] == "/clips/A.mp4"    # historical first-match retained


def test_T11_event_proof_join():
    script = f"""
import {{ resolveProofClip }} from "file://{AUTHORITY_MJS}";
const comments = [
  {{ timestamp: "00:20", evidence_id: "evd_A", event_id: "EVT-X", tele_clip_url: "/clips/X.mp4" }},
  {{ timestamp: "00:36", evidence_id: "evd_B", tele_clip_url: "/clips/B.mp4" }},
];
const hit = resolveProofClip(comments, {{ eventId: "EVT-X", timestamp: "00:20" }}, true);
const miss = resolveProofClip(comments, {{ eventId: "EVT-NONE", timestamp: "00:36" }}, true);
console.log(JSON.stringify({{ hit: hit.tele_clip_url, miss: miss === null }}));
"""
    r = _run_node(script)
    assert r["hit"] == "/clips/X.mp4"
    assert r["miss"] is True  # no unrelated proof


def test_T12_authority_no_nearest_frame():
    script = f"""
import {{ buildFrameLookup }} from "file://{AUTHORITY_MJS}";
const comments = [
  {{ timestamp: "00:38", evidence_id: "evd_38", frame_url: "/f/38.jpg", identity_verified: true }},
];
const auth = buildFrameLookup(comments, true);
const a = auth.find("00:36", {{ evidenceId: "evd_36_missing" }});
const b = auth.find("00:36", {{}});
const idHit = buildFrameLookup(comments, true).find("00:38", {{ evidenceId: "evd_38" }});
console.log(JSON.stringify({{ a: a === null, b: b === null, idHit: idHit && idHit.url }}));
"""
    r = _run_node(script)
    assert r["a"] is True and r["b"] is True  # no <=8s, no any-unused fallback
    assert r["idHit"] == "/f/38.jpg"          # exact ID join still works


def test_T13_legacy_frontend_fallback_retained():
    script = f"""
import {{ buildFrameLookup, isAuthorityReport }} from "file://{AUTHORITY_MJS}";
const comments = [
  {{ timestamp: "00:38", frame_url: "/f/38.jpg", identity_verified: true }},
];
const legacy = buildFrameLookup(comments, false);
const near = legacy.find("00:36", {{}});
const legacy2 = buildFrameLookup(comments, false);
const any = legacy2.find("59:59", {{}});
console.log(JSON.stringify({{
  near: near && near.url, any: any && any.url,
  isAuthNew: isAuthorityReport({{ evidence_authority_version: 1 }}),
  isAuthLegacy: isAuthorityReport({{}}),
  isAuthNull: isAuthorityReport(null),
}}));
"""
    r = _run_node(script)
    assert r["near"] == "/f/38.jpg"   # nearest <=8s kept for legacy
    assert r["any"] == "/f/38.jpg"    # any-unused fallback kept for legacy
    assert r["isAuthNew"] is True
    assert r["isAuthLegacy"] is False
    assert r["isAuthNull"] is False


# ==================================================================
# FIX 01 — CORRECTION 01: authority proof presentation / ID propagation
# ==================================================================

def test_C01_D_snapshot_moments_bound():
    full = _body(
        [_evt("00:36")],
        [_com("00:36"), _com("00:40"), _com("00:40")],
        snapshot_moments=[
            {"key": "strength", "title": "t", "timestamp": "00:36"},   # exact unique
            {"key": "noticed", "title": "t", "timestamp": "00:38"},    # no candidate
            {"key": "hidden", "title": "t", "timestamp": "00:40"},     # ambiguous
            {"key": "develop", "title": "t", "timestamp": "General"},  # unparseable
        ],
    )
    attach_event_evidence_authority(full)
    sm = full["snapshot_moments"]
    assert sm[0]["evidence_id"] == full["video_comments"][0]["evidence_id"]
    assert sm[0]["event_id"] == full["action_timeline"][0]["event_id"]
    assert "evidence_id" not in sm[1] and "event_id" not in sm[1]
    assert "evidence_id" not in sm[2]  # two exact candidates — never guess
    assert "evidence_id" not in sm[3] and "event_id" not in sm[3]
    assert sm[0]["timestamp"] == "00:36"  # presentation untouched


def test_C01_F_watch_together_and_gyg_bound():
    full = _body(
        [_evt("00:36")],
        [_com("00:36"), _com("01:10")],
        parents_package={"watch_together": {"moments": [
            {"timestamp": "00:36", "say_this": "great run"},
            {"timestamp": "00:38", "say_this": "no match"},
        ]}},
        grow_your_game={"lessons": [
            {"topic_id": "scanning", "moments": [
                {"timestamp": "01:10", "what": "exact"},
                {"timestamp": "01:11", "what": "no match"},
            ]},
        ]},
    )
    attach_event_evidence_authority(full)
    wt = full["parents_package"]["watch_together"]["moments"]
    assert wt[0]["evidence_id"] == full["video_comments"][0]["evidence_id"]
    assert wt[0]["event_id"] == full["action_timeline"][0]["event_id"]
    assert "evidence_id" not in wt[1] and "event_id" not in wt[1]
    gm = full["grow_your_game"]["lessons"][0]["moments"]
    assert gm[0]["evidence_id"] == full["video_comments"][1]["evidence_id"]
    assert "event_id" not in gm[0]  # no event at 01:10
    assert "evidence_id" not in gm[1]


def test_C01_idempotent_with_structured_moments():
    full = _body(
        [_evt("00:36")],
        [_com("00:36")],
        snapshot_moments=[{"key": "strength", "timestamp": "00:36"}],
        parents_package={"watch_together": {"moments": [{"timestamp": "00:36"}]}},
        grow_your_game={"lessons": [{"moments": [{"timestamp": "00:36"}]}]},
    )
    attach_event_evidence_authority(full)
    snap = json.loads(json.dumps(full))
    attach_event_evidence_authority(full)
    assert full == snap


def test_C01_E_score_meaning_preserves_ids():
    from score_meaning import _pick_evidence
    vsecs = [("anchor", 36.0)]
    out = _pick_evidence(
        [{"timestamp": "00:36", "evidence_id": "E1", "event_id": "EV1"}],
        vsecs, [], None,
    )
    assert out == {"timestamp": "00:36", "verified": True,
                   "evidence_id": "E1", "event_id": "EV1"}
    legacy = _pick_evidence([{"timestamp": "00:36"}], vsecs, [], None)
    assert legacy == {"timestamp": "00:36", "verified": True}
    assert "evidence_id" not in legacy and "event_id" not in legacy


def test_C01_frontend_wiring_passes_ids():
    # supporting wiring check (behaviour proven via the pure-helper node tests)
    rv2 = BACKEND.parent / "frontend" / "src" / "components" / "report-v2"
    sections = (rv2 / "sections.jsx").read_text()
    assert "strengthThumb(authority, s.thumb, fallbackThumb)" in sections
    assert sections.count("{ evidenceId: s.evidenceId, eventId: s.eventId }") == 2
    sm = (rv2 / "scoremeaning.jsx").read_text()
    assert "onPlayAt(ev.timestamp, { evidenceId: ev.evidence_id, eventId: ev.event_id })" in sm
    assert "canUseAuthorityProof(authority, ev)" in sm
    gyg = (rv2 / "growyourgame.jsx").read_text()
    assert "canUseAuthorityProof(authority, m)" in gyg
    assert "{ evidenceId: m.evidence_id, eventId: m.event_id }" in gyg
    parents = (rv2 / "parents.jsx").read_text()
    assert "canUseAuthorityProof(authority, m)" in parents
    assert "{ evidenceId: m.evidence_id, eventId: m.event_id }" in parents
    derive = (rv2 / "derive.js").read_text()
    assert "resolveAuthorityFrame(full.video_comments, x)" in derive


def test_C01_A_B_C_strength_thumb_and_affordance():
    script = f"""
import {{ canUseAuthorityProof, strengthThumb }} from "file://{AUTHORITY_MJS}";
console.log(JSON.stringify({{
  A_afford: canUseAuthorityProof(true, {{ timestamp: "00:36" }}),
  A_thumb: strengthThumb(true, null, "/marker.jpg"),
  B_afford: canUseAuthorityProof(true, {{ evidenceId: "evd_A" }}),
  B_afford_evt: canUseAuthorityProof(true, {{ eventId: "evt_A" }}),
  B_afford_snake: canUseAuthorityProof(true, {{ evidence_id: "evd_A" }}),
  B_thumb: strengthThumb(true, "/f/36.jpg", "/marker.jpg"),
  C_afford: canUseAuthorityProof(false, {{ timestamp: "00:36" }}),
  C_thumb: strengthThumb(false, null, "/marker.jpg"),
  C_null: canUseAuthorityProof(true, null),
}}));
"""
    r = _run_node(script)
    assert r["A_afford"] is False          # no proof affordance
    assert r["A_thumb"] is None            # never fallbackThumb as evidence
    assert r["B_afford"] is True and r["B_afford_evt"] is True and r["B_afford_snake"] is True
    assert r["B_thumb"] == "/f/36.jpg"     # exact authority frame shown
    assert r["C_afford"] is True           # legacy keeps timestamp behaviour
    assert r["C_thumb"] == "/marker.jpg"   # legacy fallback retained
    assert r["C_null"] is False


def test_C01_D_frontend_snapshot_frame_resolution():
    script = f"""
import {{ resolveAuthorityFrame }} from "file://{AUTHORITY_MJS}";
const comments = [
  {{ timestamp: "00:36", evidence_id: "evd_36", event_id: "evt_36", frame_url: "/f/36.jpg", identity_verified: true }},
  {{ timestamp: "00:38", evidence_id: "evd_38", frame_url: "/f/38.jpg", identity_verified: true }},
  {{ timestamp: "00:50", evidence_id: "evd_50", frame_url: "/f/50.jpg", identity_verified: false }},
  {{ timestamp: "00:55", evidence_id: "evd_55", frame_url: "/f/55.jpg", frame_placeholder: true }},
];
const byEvd = resolveAuthorityFrame(comments, {{ evidence_id: "evd_36" }});
const byEvt = resolveAuthorityFrame(comments, {{ eventId: "evt_36" }});
const noIds = resolveAuthorityFrame(comments, {{ timestamp: "00:36" }});
const rejected = resolveAuthorityFrame(comments, {{ evidence_id: "evd_50" }});
const placeholder = resolveAuthorityFrame(comments, {{ evidence_id: "evd_55" }});
console.log(JSON.stringify({{
  byEvd: byEvd && byEvd.frame_url,
  byEvt: byEvt && byEvt.frame_url,
  noIds: noIds === null,
  rejected: rejected === null,
  placeholder: placeholder === null,
}}));
"""
    r = _run_node(script)
    assert r["byEvd"] == "/f/36.jpg"
    assert r["byEvt"] == "/f/36.jpg"
    assert r["noIds"] is True        # 00:38 frame never substituted
    assert r["rejected"] is True     # identity-rejected frame unusable
    assert r["placeholder"] is True  # placeholder unusable
