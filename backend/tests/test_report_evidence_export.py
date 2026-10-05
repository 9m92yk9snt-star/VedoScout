"""Offline evidence/export regressions: read-only, provenance and access safety."""
from __future__ import annotations

import asyncio
import copy
import gzip
import hashlib
import io
import json
import sys
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import report_evidence_export as ex


@pytest.fixture
def case(tmp_path):
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    root = tmp_path / "app"
    (root / "backend").mkdir(parents=True)
    doc = {"id": "report-123", "video_filename": "match.web.mp4",
           "original_video_filename": "match.mov", "anchors": [{"t": 49.44,
               "box": {"x": .2, "y": .3, "w": .1, "h": .3}}],
           "raw_marker_anchors": '[{"t":49.44,"box":{"x":0.2,"y":0.3,"w":0.1,"h":0.3}}]',
           "anchor_time_offset": .08,
           "canonical_events": {"accepted": [], "unresolved": [{"reason": "identity_unresolved"}]},
           "football_sequence_analysis": {"sequences": []},
           "football_sequence_raw": {"schema": "FIX09B_SEQUENCE_RESPONSE_SUMMARY", "raw_actions_persisted": False}}
    return doc, uploads, root, tmp_path / "result.zip"


def build(case, **kwargs):
    doc, uploads, root, output = case
    return ex.build_export(doc, output, upload_dir=uploads, source_root=root, **kwargs)


def read(case, name):
    with zipfile.ZipFile(case[3]) as archive:
        return json.loads(archive.read(name))


def trace(case, row, **entry):
    doc, uploads, _, _ = case
    folder = uploads / ".fix10a_traces" / doc["id"] / "match-intelligence"
    folder.mkdir(parents=True)
    path = folder / "trace.json.gz"
    path.write_bytes(gzip.compress(ex.json_bytes(row), mtime=0))
    doc["fix10a_trace_manifest"] = [{"trace_id": "one", "local_path": str(path),
        "sha256": hashlib.sha256(ex.json_bytes(row)).hexdigest(), **entry}]


def test_snapshot_anchors_and_canonical_decisions_are_not_modified(case):
    before = copy.deepcopy(case[0])
    result = build(case)
    assert case[0] == before
    assert read(case, "report.json") == before
    assert read(case, "anchors.json")["raw_marker_anchors"] == before["raw_marker_anchors"]
    assert read(case, "anchors.json")["anchor_time_offset"] == .08
    assert read(case, "canonical.json")["canonical_events"] == before["canonical_events"]
    assert result["missing_count"] > 0
    ex.verify_export(case[3])


def test_raw_summaries_missing_original_and_unknown_historical_version_are_explicit(case):
    build(case, environment="live", deployment_id="export-pod")
    missing = read(case, "missing_data.json")
    assert any(r["item"] == "original_upload" for r in missing)
    assert any(r["item"] == "football_sequence_raw.original_model_response" for r in missing)
    assert any(r["item"] == "analysis_commit" for r in missing)
    runtime = read(case, "runtime.json")
    assert runtime["at_export"]["historical_code_or_configuration"] is False
    assert runtime["at_export"]["deployment_id_source"] == "operator"
    assert not read(case, "manifest.json")["complete"]


def test_nested_credentials_bearer_values_and_signed_queries_are_redacted(case):
    case[0]["diagnostic"] = {"apiKey": "TOPSECRET", "accessToken": "TOPSECRET",
        "password": "TOPSECRET", "error": "Bearer TOPSECRET",
        "url": "https://bob:TOPSECRET@example.com/file?token=TOPSECRET"}
    build(case)
    with zipfile.ZipFile(case[3]) as archive:
        for name in archive.namelist():
            assert b"TOPSECRET" not in archive.read(name)
    assert len(read(case, "redactions.json")) == 5


def test_exact_exported_video_bytes_are_hashed_and_private(case, monkeypatch):
    monkeypatch.setattr(ex, "probe_video", lambda p: {"bytes_seen": p.read_bytes().hex()})
    (case[1] / "match.web.mp4").write_bytes(b"video bytes")
    (case[1] / "match.mov").write_bytes(b"original bytes")
    result = build(case)
    assert result["video_files"] == 2
    assert case[3].stat().st_mode & 0o777 == 0o600
    assert read(case, "video_metadata.json")["references"][0]["probe"]["bytes_seen"] == b"video bytes".hex()
    files = read(case, "manifest.json")["files"]
    assert next(f for f in files if f["path"] == "video/canonical_web-match.web.mp4")["sha256"] == hashlib.sha256(b"video bytes").hexdigest()


def test_trace_original_hash_is_verified_before_export_and_redaction(case):
    trace(case, {"identity": {"status": "UNRESOLVED"}, "secret": "TOPSECRET"})
    result = build(case)
    assert result["trace_count"] == 1
    assert read(case, "traces/000.json")["secret"] == "[REDACTED]"
    assert read(case, "runtime.json")["trace_integrity"][0]["verified_against_stored_manifest"]


def test_trace_hash_mismatch_does_not_export_untrusted_trace(case):
    trace(case, {"identity": "other"}, sha256="0" * 64)
    result = build(case)
    assert result["trace_count"] == 0
    assert {"item": "trace[0]", "reason": "stored_trace_sha256_mismatch"} in read(case, "missing_data.json")


@pytest.mark.parametrize("reference", ["../private.txt", "/etc/passwd"])
def test_paths_outside_uploads_are_never_exported(case, reference):
    case[0]["video_filename"] = reference
    build(case)
    assert not read(case, "video_metadata.json")["references"][0]["archive_path"]


def test_symlink_escape_is_not_exported(case):
    private = case[1].parent / "secret"
    private.write_bytes(b"DO NOT EXPORT")
    (case[1] / "match.web.mp4").symlink_to(private)
    build(case)
    with zipfile.ZipFile(case[3]) as archive:
        assert not any(n.startswith("video/") for n in archive.namelist())


@pytest.mark.parametrize("report_id", ["../another", "a/b", "", ".", "a\\b"])
def test_invalid_report_id_is_rejected(case, report_id):
    case[0]["id"] = report_id
    with pytest.raises(ValueError, match="Invalid report ID"):
        build(case)
    assert not case[3].exists()


def test_public_uploads_output_is_rejected(case):
    doc, uploads, root, _ = case
    with pytest.raises(ValueError, match="public uploads"):
        ex.build_export(doc, uploads / "export.zip", upload_dir=uploads, source_root=root)


def test_existing_output_is_not_overwritten(case):
    case[3].write_bytes(b"existing")
    with pytest.raises(FileExistsError):
        build(case)
    assert case[3].read_bytes() == b"existing"


class Objects:
    def __init__(self, key, payload=b"video bytes"):
        self.key, self.payload, self.reads, self.signs = key, payload, [], []

    def key_from_url(self, _url):
        return self.key

    def open(self, key):
        self.reads.append(key)
        return io.BytesIO(self.payload), len(self.payload)

    def sign(self, key):
        self.signs.append(key)
        return "https://example.com/private-video?Signature=INTENTIONAL_DOWNLOAD_CAPABILITY"


def test_r2_video_is_read_without_uploads_or_database_mutations(case, monkeypatch):
    monkeypatch.setattr(ex, "probe_video", lambda _: {})
    objects = Objects("reports/report-123/match.web.mp4")
    case[0]["video_url_override"] = "https://example.com/match.web.mp4"
    result = build(case, object_reader=objects)
    assert result["video_files"] == 1
    assert len(objects.reads) == 1 and objects.signs == []
    assert list(case[1].iterdir()) == []


def test_no_video_mode_reads_no_media_and_provides_hour_long_link(case):
    objects = Objects("reports/report-123/match.web.mp4")
    case[0]["video_url_override"] = "https://example.com/video"
    result = build(case, object_reader=objects, include_video=False)
    assert result["video_files"] == 0
    assert objects.reads == []
    assert read(case, "video_links.json")[0]["expires_in_seconds"] == 3600
    assert read(case, "video_links.json")[0]["sha256"] is None


@pytest.mark.parametrize("key", ["reports/other/video.mp4", "reports/report-123/../other/video.mp4"])
def test_cross_report_object_references_are_not_read_or_signed(case, key):
    objects = Objects(key)
    case[0]["video_url_override"] = "https://example.com/video"
    build(case, object_reader=objects)
    assert objects.reads == objects.signs == []


def test_missing_trace_and_size_limit_do_not_turn_into_empty_success(case):
    case[0]["fix10a_trace_manifest"] = [{"local_path": "/etc/passwd"}]
    (case[1] / "match.web.mp4").write_bytes(b"x" * 10000)
    build(case, max_file_bytes=5000)
    missing = read(case, "missing_data.json")
    assert any(r["item"] == "trace[0]" for r in missing)
    assert any(r["item"] == "canonical_web" and r["reason"] == "ExportLimitError" for r in missing)
    ex.verify_export(case[3])


def test_gzip_expansion_is_bounded(case, monkeypatch):
    trace(case, {"dense_frames": "x" * 10000})
    monkeypatch.setattr(ex, "MAX_TRACE_JSON_BYTES", 100)
    assert build(case)["trace_count"] == 0
    assert any(r["item"] == "trace[0]" for r in read(case, "missing_data.json"))


def test_checksum_tampering_is_detected(case):
    build(case)
    modified = case[3].with_name("tampered.zip")
    with zipfile.ZipFile(case[3]) as source, zipfile.ZipFile(modified, "w") as target:
        for name in source.namelist():
            target.writestr(name, b"{}" if name == "report.json" else source.read(name))
    with pytest.raises(ValueError, match="checksum mismatch"):
        ex.verify_export(modified)


def test_source_is_current_allowlisted_and_never_includes_environment(case):
    (case[2] / "backend" / "video_timebase.py").write_text("# current source\n")
    (case[2] / "backend" / ".env").write_text("PASSWORD=TOPSECRET")
    (case[2] / "backend" / "server.py").write_text(
        'ADMIN_PASSWORD="TOPSECRET"\nasync def generate_full_report_task(report_id):\n    return report_id\n')
    build(case)
    with zipfile.ZipFile(case[3]) as archive:
        assert "source/current/video_timebase.py" in archive.namelist()
        assert "generate_full_report_task" in archive.read("source/current/server_analysis_functions.txt").decode()
        assert not any(n.endswith(".env") for n in archive.namelist())
        assert all(b"TOPSECRET" not in archive.read(n) for n in archive.namelist())


def test_admin_route_rejects_non_admin_before_accessing_database(case):
    from fastapi import FastAPI, HTTPException
    from fastapi.testclient import TestClient
    from report_export_routes import create_report_export_router

    async def deny():
        raise HTTPException(403, "Admin required")

    class Reports:
        async def find_one(self, *_args):
            pytest.fail("Denied request accessed database")

    app = FastAPI()
    app.include_router(create_report_export_router(db=SimpleNamespace(reports=Reports()),
        upload_dir=case[1], source_root=case[2], admin_dependency=deny))
    with TestClient(app) as client:
        assert client.get("/admin/reports/report-123/evidence-export").status_code == 403


def test_admin_download_reads_only_one_report_and_cleans_private_zip(case):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from report_export_routes import create_report_export_router

    calls = []

    async def allow():
        return {"role": "admin"}

    class Reports:
        async def find_one(self, query, projection):
            calls.append((query, projection))
            return copy.deepcopy(case[0])

    app = FastAPI()
    app.include_router(create_report_export_router(db=SimpleNamespace(reports=Reports()),
        upload_dir=case[1], source_root=case[2], admin_dependency=allow))
    with TestClient(app) as client:
        first = client.get("/admin/reports/report-123/evidence-export?include_video=false")
        assert first.status_code == 200
        assert first.headers["cache-control"] == "no-store"
        with zipfile.ZipFile(io.BytesIO(first.content)) as archive:
            assert json.loads(archive.read("manifest.json"))["database_writes"] == 0
        assert client.get("/admin/reports/report-123/evidence-export").status_code == 200
    assert calls == [({"id": "report-123"}, {"_id": 0})] * 2


def test_response_disconnect_still_cleans_private_files(tmp_path):
    from report_export_routes import PrivateExportResponse
    path = tmp_path / "download.zip"
    path.write_bytes(b"some bytes")
    cleaned = []
    response = PrivateExportResponse(path, cleanup=lambda: cleaned.append(True))

    async def send(_message):
        raise RuntimeError("disconnected")

    with pytest.raises(RuntimeError, match="disconnected"):
        asyncio.run(response({"type": "http", "method": "GET", "headers": []}, None, send))
    assert cleaned == [True]


def test_cli_uses_one_snapshot_and_no_server_import(case, monkeypatch, capsys):
    import importlib.util
    server_was_loaded = "server" in sys.modules
    script = Path(__file__).resolve().parents[1] / "scripts" / "export_report_evidence.py"
    spec = importlib.util.spec_from_file_location("evidence_export_cli_test", script)
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    calls = []

    class Collection:
        def __init__(self, name):
            self.name = name

        def find_one(self, query, projection):
            calls.append(("find_one", self.name, query, projection))
            return copy.deepcopy(case[0])

        def find(self, query, projection):
            calls.append(("find", self.name, query, projection))
            return SimpleNamespace(limit=lambda _n: [])

    database = SimpleNamespace(reports=Collection("reports"),
                              analysis_runs=Collection("analysis_runs"),
                              analysis_model_calls=Collection("analysis_model_calls"))

    class Client:
        def __init__(self, url, **_kwargs):
            assert url == "mongodb://test.invalid"

        def __getitem__(self, name):
            assert name == "fake-live"
            return database

        def close(self):
            calls.append("closed")

    monkeypatch.setitem(sys.modules, "pymongo", SimpleNamespace(MongoClient=Client))
    monkeypatch.setitem(sys.modules, "r2_storage", SimpleNamespace(is_configured=lambda: False))
    monkeypatch.setitem(sys.modules, "dotenv", SimpleNamespace(load_dotenv=lambda *_args, **_kwargs: None))
    monkeypatch.setenv("MONGO_URL", "mongodb://test.invalid")
    monkeypatch.setenv("DB_NAME", "fake-live")
    monkeypatch.setattr(sys, "argv", [str(script), "--report-id", "report-123",
        "--output", str(case[3]), "--source-root", str(case[2]),
        "--upload-dir", str(case[1]), "--environment", "live", "--no-video"])
    cli.main()
    result = json.loads(capsys.readouterr().out)
    # Exactly one report snapshot; audit collections read read-only and report-scoped; then closed.
    assert calls == [
        ("find_one", "reports", {"id": "report-123"}, {"_id": 0}),
        ("find", "analysis_runs", {"report_id": "report-123"}, {"_id": 0}),
        ("find", "analysis_model_calls", {"report_id": "report-123"}, {"_id": 0}),
        "closed"]
    assert result["zip_sha256"] == hashlib.sha256(case[3].read_bytes()).hexdigest()
    assert ("server" in sys.modules) == server_was_loaded



def test_run_audit_collections_scoped_to_report_and_exclude_foreign(case):
    doc = case[0]
    runs = [{"run_id": "run-A", "report_id": doc["id"], "outputs": {"fix10b_status": "no_change"}},
            {"run_id": "run-X", "report_id": "other-999", "outputs": {"fix10b_status": "leak"}}]
    calls = [{"call_id": "c1", "run_id": "run-A", "report_id": doc["id"], "model": "gemini-2.5-pro",
              "status": "responded", "raw_response": "MINE goals=1", "response_bytes": 11},
             {"call_id": "cX", "run_id": "run-X", "report_id": "other-999", "model": "gemini-2.5-pro",
              "status": "responded", "raw_response": "FOREIGN leak", "response_bytes": 12}]
    build(case, run_records=runs, model_call_records=calls)
    exported_runs = read(case, "analysis_runs.json")
    assert [r["run_id"] for r in exported_runs] == ["run-A"]
    index = read(case, "analysis_model_calls/index.json")
    assert [c["call_id"] for c in index] == ["c1"]
    first = read(case, "analysis_model_calls/000.json")
    assert first["raw_response"] == "MINE goals=1"
    with zipfile.ZipFile(case[3]) as archive:
        names = archive.namelist()
        assert not any(name.startswith("analysis_model_calls/001") for name in names)
        blob = b"".join(archive.read(n) for n in names)
    assert b"other-999" not in blob
    assert b"FOREIGN" not in blob
    assert b"leak" not in blob
    ex.verify_export(case[3])


def test_run_audit_absent_when_not_provided(case):
    build(case)
    missing = {entry["item"] for entry in read(case, "missing_data.json")}
    assert "analysis_runs" not in missing
    assert "analysis_model_calls" not in missing
