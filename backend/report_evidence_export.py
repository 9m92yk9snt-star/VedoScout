"""Read-only export of ONE persisted report. No server/model imports or writes.

The caller supplies a database snapshot and optional read-only object adapter.
Only the private output workspace is written. Historical evidence is never
reconstructed, and current source/configuration is never labelled historical.
"""
from __future__ import annotations

import ast
import gzip
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

VERSION = 1
MAX_FILE_BYTES = 128 * 1024 * 1024
MAX_TOTAL_BYTES = 512 * 1024 * 1024
MAX_TRACE_JSON_BYTES = 64 * 1024 * 1024
MAX_TRACES = 200
CHUNK = 1024 * 1024
CONFIG_KEYS = ("IDENTITY_TIMELINE_ENABLED", "IDENTITY_TIMELINE_HZ",
               "FIX10A_SUPPORT_VISION_ENABLED", "CV_SHADOW_ENABLED")
SOURCE_MODULES = (
    "unified_analysis_engine.py", "unified_identity_authority.py",
    "player_identity_timeline.py", "player_tracking.py", "video_timebase.py",
    "football_scene_graph.py", "football_sequence_intelligence.py",
    "canonical_event_resolver.py", "canonical_output_authority.py",
    "fix10a_runtime.py", "fix10b_runtime.py", "fix10b_reconciliation.py",
    "physical_match_reconstruction.py", "dense_replay.py", "event_trace.py",
    "ball_trajectory.py", "ball_contact_engine.py", "touch_graph.py",
    "shot_outcome_engine.py", "evidence_authority.py", "full_video_event_recall.py",
)
SECRET_KEY = re.compile(
    r"(^|_)(password|passwd|secret|token|api_key|access_key|authorization|cookie|"
    r"mongo_url|database_url|connection_string|client_secret)($|_)", re.I)
SECRET_TEXT = re.compile(r"\b(Bearer\s+)[A-Za-z0-9._~+/=-]+", re.I)


class ExportLimitError(ValueError):
    pass


def validate_report_id(report_id):
    if not isinstance(report_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,99}", report_id):
        raise ValueError("Invalid report ID")
    return report_id


def json_bytes(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False,
                      separators=(",", ":"), default=str).encode("utf-8")


def redact(value, paths, location="report"):
    """Strip credential fields and signed URL queries; retain diagnostic keys."""
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            loc = f"{location}.{key}"
            normalized_key = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", str(key))
            if SECRET_KEY.search(normalized_key):
                paths.append(loc)
                out[key] = "[REDACTED]"
            else:
                out[key] = redact(item, paths, loc)
        return out
    if isinstance(value, (tuple, list)):
        return [redact(item, paths, f"{location}[{i}]") for i, item in enumerate(value)]
    if isinstance(value, str):
        if value.lstrip().startswith(("{", "[")):
            try:
                parsed = json.loads(value)
                before = len(paths)
                clean = redact(parsed, paths, location)
                if len(paths) != before:
                    return json_bytes(clean).decode()
            except (ValueError, TypeError):
                pass
        clean = SECRET_TEXT.sub(r"\1[REDACTED]", value)
        if clean.startswith(("https://", "http://", "mongodb://", "mongodb+srv://")):
            try:
                url = urlsplit(clean)
                if url.username or url.password or url.query or url.fragment:
                    host = url.hostname or ""
                    if ":" in host:
                        host = f"[{host}]"
                    if url.port:
                        host += f":{url.port}"
                    clean = urlunsplit((url.scheme, host, url.path, "", ""))
            except ValueError:
                clean = "[REDACTED_INVALID_URL]"
        if clean != value:
            paths.append(location)
        return clean
    return value


def safe_local(root, reference):
    if not isinstance(reference, str) or not reference or "\\" in reference:
        return None
    raw = Path(reference)
    if ".." in raw.parts:
        return None
    root = Path(root).resolve()
    path = (raw if raw.is_absolute() else root / raw).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        return None
    return path


class R2Reader:
    """Adapter deliberately exposes only GET and expiring GET links."""
    def __init__(self, storage):
        self.storage = storage

    def key_from_url(self, value):
        return self.storage.key_from_url(value) if self.storage.is_configured() else None

    def open(self, key):
        row = self.storage.get_stream(key)
        return row["Body"], row.get("ContentLength")

    def sign(self, key):
        return self.storage._get_client().generate_presigned_url(
            "get_object", Params={"Bucket": self.storage._bucket(), "Key": key},
            ExpiresIn=3600)


def current_runtime(source_root, environment, deployment_id=None):
    root = Path(source_root)
    commit = None
    try:
        commit = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"],
                                capture_output=True, text=True, timeout=5, check=True).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass
    return {
        "environment_label": environment, "environment_label_source": "operator",
        "deployment_id": deployment_id, "deployment_id_source": "operator" if deployment_id else "unavailable",
        "source_commit_at_export": commit,
        "hostname_at_export": os.uname().nodename,
        "configuration_at_export": {key: os.environ[key] for key in CONFIG_KEYS if key in os.environ},
        "historical_code_or_configuration": False,
    }


def probe_video(path):
    """Read container metadata only, without generating media or model calls."""
    binary = shutil.which("ffprobe")
    if not binary:
        return {"status": "unavailable", "reason": "ffprobe_not_installed"}
    try:
        result = subprocess.run([binary, "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=codec_name,width,height,avg_frame_rate,r_frame_rate,time_base,start_time,duration,nb_frames:format=duration,start_time",
            "-of", "json", str(path)], capture_output=True, text=True, timeout=20, check=True)
        return {"status": "measured_from_exported_bytes", "metadata": json.loads(result.stdout),
                "note": "avg_frame_rate/r_frame_rate are container metadata; frame PTS remains authoritative."}
    except (OSError, subprocess.SubprocessError, ValueError):
        return {"status": "unavailable", "reason": "metadata_probe_failed"}


def build_export(doc, output, *, upload_dir, source_root, environment="unspecified",
                 deployment_id=None, object_reader=None, include_video=True,
                 max_file_bytes=MAX_FILE_BYTES, max_total_bytes=MAX_TOTAL_BYTES):
    """Build private ZIP from a supplied snapshot. Return non-secret summary.

    Snapshot is never mutated. No arbitrary HTTP fetch, DB/model access, media
    generation, public URL upload, source-file change or overwrite is performed.
    """
    report_id = validate_report_id(doc.get("id"))
    output = Path(output).resolve()
    uploads = Path(upload_dir).resolve()
    if output.is_relative_to(uploads):
        raise ValueError("Exports must be outside the public uploads directory")
    if max_file_bytes <= 0 or max_total_bytes <= 0:
        raise ValueError("Export limits must be positive")
    output.parent.mkdir(parents=True, exist_ok=True)
    missing, redactions, files, videos, links, trace_integrity = [], [], [], [], [], []
    cleaned = redact(doc, redactions)
    total = 0
    now = datetime.now(timezone.utc)
    # Leave room for source snapshots and required metadata after optional media.
    optional_limit = max(0, max_total_bytes - min(4 * CHUNK, max_total_bytes // 2))

    def absent(item, reason):
        missing.append({"item": item, "reason": reason})

    with tempfile.TemporaryDirectory(prefix="scout-export-", dir=output.parent) as tmp:
        os.chmod(tmp, 0o700)
        archive = Path(tmp) / "evidence.zip"
        with zipfile.ZipFile(archive, "w", allowZip64=True) as z:
            def add_stream(name, stream, size=None, *, compressed=False, optional=False, probe=False):
                nonlocal total
                limit = optional_limit if optional else max_total_bytes
                if size is not None and (size > max_file_bytes or total + size > limit):
                    raise ExportLimitError("artifact_size_limit")
                staged = Path(tmp) / "artifact"
                digest, count = hashlib.sha256(), 0
                try:
                    with staged.open("wb") as target:
                        while True:
                            chunk = stream.read(CHUNK)
                            if not chunk:
                                break
                            count += len(chunk)
                            if count > max_file_bytes or total + count > limit:
                                raise ExportLimitError("artifact_size_limit")
                            digest.update(chunk)
                            target.write(chunk)
                    if count == 0:
                        raise ValueError("empty_artifact")
                    if size is not None and count != size:
                        raise ValueError("artifact_length_mismatch")
                    z.write(staged, name, compress_type=zipfile.ZIP_DEFLATED if compressed else zipfile.ZIP_STORED)
                    total += count
                    files.append({"path": name, "bytes": count, "sha256": digest.hexdigest()})
                    return probe_video(staged) if probe else None
                finally:
                    staged.unlink(missing_ok=True)

            def add_json(name, value):
                payload = json_bytes(value)
                add_stream(name, io.BytesIO(payload), len(payload), compressed=True)

            add_json("report.json", cleaned)
            add_json("anchors.json", {"raw_marker_anchors": cleaned.get("raw_marker_anchors"),
                "raw_marker_box": cleaned.get("raw_marker_box"),
                "marker_timestamp": cleaned.get("marker_timestamp"), "anchors": cleaned.get("anchors"),
                "anchor_time_offset": cleaned.get("anchor_time_offset"),
                "coordinate_note": "Original fields retained. t is seconds; box x/y/w/h is normalized in upload contract. No retapping or time conversion."})
            add_json("canonical.json", {key: cleaned.get(key) for key in (
                "canonical_events", "event_ledger", "unified_scoring_scan", "full_report", "preview")})
            for key in ("anchors", "canonical_events", "football_sequence_analysis", "fix10a_trace_manifest"):
                if not doc.get(key):
                    absent(key, "not_stored_or_empty_in_report")
            for key in ("football_sequence_raw", "event_discovery_raw"):
                raw = doc.get(key)
                if not raw or (isinstance(raw, dict) and raw.get("raw_actions_persisted") is False):
                    absent(f"{key}.original_model_response", "not_stored; summary is not a raw response")
            for key in ("analysis_commit", "analysis_deployment_id", "analysis_config"):
                if not doc.get(key):
                    absent(key, "not_stored; current runtime is not historical provenance")

            def media(role, filename, url=None):
                name = f"video/{role}-{Path(filename).name}" if isinstance(filename, str) else None
                row = {"role": role, "filename": filename, "archive_path": None}
                videos.append(row)
                key = object_reader.key_from_url(url) if object_reader and isinstance(url, str) else None
                if key and (not key.startswith(f"reports/{report_id}/") or ".." in Path(key).parts):
                    absent(role, "object_key_outside_report_namespace")
                    return
                if not include_video:
                    absent(role, "video_bytes_excluded_by_operator")
                else:
                    local = safe_local(uploads, filename)
                    try:
                        if local:
                            with local.open("rb") as stream:
                                metadata = add_stream(name, stream, local.stat().st_size, optional=True, probe=True)
                            row.update(archive_path=name, storage="local", probe=metadata,
                                historical_byte_binding="stored_report_reference; no historical video hash is inferred")
                            return
                        if key:
                            stream, size = object_reader.open(key)
                            try:
                                metadata = add_stream(name or f"video/{role}.mp4", stream, size, optional=True, probe=True)
                            finally:
                                stream.close()
                            row.update(archive_path=name or f"video/{role}.mp4", storage="r2", probe=metadata,
                                historical_byte_binding="stored_report_reference; no historical video hash is inferred")
                            return
                        absent(role, "referenced_video_not_available_locally_or_in_configured_R2")
                    except Exception as exc:
                        absent(role, type(exc).__name__)
                if key:
                    try:
                        links.append({"role": role, "url": object_reader.sign(key),
                            "expires_in_seconds": 3600, "created_at": now.isoformat(),
                            "sha256": None, "sha256_status": "external_bytes_not_exported"})
                    except Exception as exc:
                        absent(f"{role}.download_link", type(exc).__name__)

            media("canonical_web", doc.get("video_filename"), doc.get("video_url_override"))
            original = doc.get("original_video_filename") or doc.get("raw_upload_filename")
            if original == doc.get("video_filename") and original:
                videos.append({"role": "original_upload", "same_reference_as": "canonical_web", "filename": original})
            else:
                media("original_upload", original, doc.get("original_video_url_override"))

            manifests = doc.get("fix10a_trace_manifest") or []
            if not isinstance(manifests, list):
                absent("fix10a_trace_manifest", "invalid_stored_manifest_type")
                manifests = []
            if len(manifests) > MAX_TRACES:
                absent("fix10a_trace_manifest", "trace_count_limit; remaining traces omitted")
            for i, entry in enumerate(manifests[:MAX_TRACES]):
                item = f"trace[{i}]"
                if not isinstance(entry, dict):
                    absent(item, "invalid_manifest_entry")
                    continue
                key = entry.get("object_key")
                trace_root = uploads / ".fix10a_traces" / report_id / "match-intelligence"
                local = safe_local(trace_root, entry.get("local_path"))
                stream = None
                try:
                    if local:
                        if local.stat().st_size > max_file_bytes:
                            raise ExportLimitError("trace_size_limit")
                        stream = local.open("rb")
                    elif object_reader and isinstance(key, str) and key.startswith(f"reports/{report_id}/match-intelligence/") and ".." not in Path(key).parts:
                        stream, size = object_reader.open(key)
                        if size is not None and size > max_file_bytes:
                            raise ExportLimitError("trace_size_limit")
                    else:
                        absent(item, "trace_missing_or_reference_outside_report_namespace")
                        continue
                    payload = stream.read(max_file_bytes + 1)
                    if len(payload) > max_file_bytes:
                        raise ExportLimitError("trace_size_limit")
                    with gzip.GzipFile(fileobj=io.BytesIO(payload)) as gz:
                        decoded = gz.read(MAX_TRACE_JSON_BYTES + 1)
                    if len(decoded) > MAX_TRACE_JSON_BYTES:
                        raise ExportLimitError("trace_expansion_limit")
                    trace = json.loads(decoded)
                    digest = hashlib.sha256(json_bytes(trace)).hexdigest()
                    expected = entry.get("sha256")
                    if expected and digest != expected:
                        raise ValueError("stored_trace_sha256_mismatch")
                    integrity = {"index": i, "trace_id": entry.get("trace_id"),
                        "stored_payload_sha256": digest, "stored_gzip_sha256": hashlib.sha256(payload).hexdigest(),
                        "expected_sha256": expected, "verified_against_stored_manifest": bool(expected)}
                    clean_trace = redact(trace, redactions, item)
                    encoded = json_bytes(clean_trace)
                    add_stream(f"traces/{i:03d}.json", io.BytesIO(encoded), len(encoded), compressed=True, optional=True)
                    trace_integrity.append(integrity)
                except Exception as exc:
                    # Never serialize exception text: storage errors may contain secrets.
                    reason = str(exc) if type(exc) is ValueError and str(exc) == "stored_trace_sha256_mismatch" else type(exc).__name__
                    absent(item, reason)
                finally:
                    if stream is not None:
                        stream.close()

            backend = Path(source_root) / "backend"
            for filename in SOURCE_MODULES:
                path = safe_local(backend, filename)
                if not path:
                    absent(f"source/{filename}", "module_not_available_in_export_runtime")
                    continue
                try:
                    with path.open("rb") as stream:
                        add_stream(f"source/current/{filename}", stream, path.stat().st_size, compressed=True, optional=True)
                except (OSError, ExportLimitError) as exc:
                    absent(f"source/{filename}", type(exc).__name__)
            server = safe_local(backend, "server.py")
            if server:
                text = server.read_text()
                tree = ast.parse(text)
                lines = text.splitlines(keepends=True)
                functions = [node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                             and node.name in {"analyze_preview_task", "generate_full_report_task", "_build_primary_anchor_payload"}]
                snippet = "\n".join("".join(lines[n.lineno - 1:n.end_lineno]) for n in functions)
                if snippet:
                    payload = snippet.encode()
                    try:
                        add_stream("source/current/server_analysis_functions.txt", io.BytesIO(payload), len(payload), compressed=True, optional=True)
                    except ExportLimitError:
                        absent("source/server_analysis_functions", "source_size_limit")
            add_json("runtime.json", {"at_export": current_runtime(source_root, environment, deployment_id),
                "stored_analysis_provenance": {k: cleaned[k] for k in cleaned
                    if k in {"analysis_commit", "analysis_deployment_id", "analysis_config", "pipeline_trace"}
                    or k.startswith(("fix10a_", "fix10b_", "unified_analysis_"))},
                "trace_integrity": trace_integrity})
            add_json("video_metadata.json", {"references": videos,
                "stored_metadata": {k: cleaned[k] for k in cleaned if k.startswith(("video_", "original_video_", "raw_upload_")) or k == "anchor_time_offset"},
                "note": "No transcode, frame extraction or inferred time mapping. Available ffprobe metadata is measured on exported bytes. Historical timebase must be read from stored fields/traces."})
            add_json("video_links.json", links)
            add_json("missing_data.json", missing)
            add_json("redactions.json", sorted(set(redactions)))
            manifest = {"schema_version": VERSION, "report_id": report_id,
                "exported_at": now.isoformat(), "read_only": True, "new_model_calls": 0,
                "database_writes": 0, "files": list(files), "complete": not missing,
                "checksum_scope": "Every payload file. manifest.json and SHA256SUMS are metadata; SHA256SUMS additionally hashes manifest.json.",
                "limits": {"per_file_bytes": max_file_bytes, "total_payload_bytes": max_total_bytes}}
            manifest_payload = json_bytes(manifest)
            z.writestr("manifest.json", manifest_payload, compress_type=zipfile.ZIP_DEFLATED)
            sums = "".join(f"{f['sha256']}  {f['path']}\n" for f in files)
            sums += f"{hashlib.sha256(manifest_payload).hexdigest()}  manifest.json\n"
            z.writestr("SHA256SUMS", sums)
        verify_export(archive)
        # Exclusive create; no overwriting an earlier package or public file.
        created = False
        try:
            with archive.open("rb") as src, output.open("xb") as dest:
                created = True
                os.chmod(output, 0o600)
                shutil.copyfileobj(src, dest, CHUNK)
        except BaseException:
            if created:
                output.unlink(missing_ok=True)
            raise
    return {"report_id": report_id, "path": str(output), "bytes": output.stat().st_size,
            "missing_count": len(missing), "trace_count": len(trace_integrity),
            "video_files": sum(bool(v.get("archive_path")) for v in videos)}


def verify_export(path):
    with zipfile.ZipFile(path) as z:
        manifest = json.loads(z.read("manifest.json"))
        expected = {f["path"]: f["sha256"] for f in manifest["files"]}
        checked = set()
        for line in z.read("SHA256SUMS").decode().splitlines():
            digest, name = line.split("  ", 1)
            if name in checked or name not in set(expected) | {"manifest.json"}:
                raise ValueError("Unexpected checksum entry")
            checked.add(name)
            if name in expected and expected[name] != digest:
                raise ValueError("Checksum metadata mismatch")
            with z.open(name) as stream:
                actual = hashlib.file_digest(stream, "sha256").hexdigest()
            if actual != digest:
                raise ValueError("Export checksum mismatch")
        if checked != set(expected) | {"manifest.json"}:
            raise ValueError("Missing checksum entry")
        if len(z.namelist()) != len(set(z.namelist())) or set(z.namelist()) != set(expected) | {"manifest.json", "SHA256SUMS"}:
            raise ValueError("Unmanifested artifact")
        for name in z.namelist():
            if name.endswith(".json"):
                json.loads(z.read(name))
    return manifest
