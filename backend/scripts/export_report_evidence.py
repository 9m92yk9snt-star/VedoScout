#!/usr/bin/env python3
"""Run inside the selected live environment; no app import or deployment.

Uses one reports.find_one and read-only R2 GETs. No model keys are used.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from report_evidence_export import R2Reader, build_export, validate_report_id  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, default=BACKEND.parent)
    parser.add_argument("--upload-dir", type=Path, default=BACKEND / "uploads")
    parser.add_argument("--env-file", type=Path, default=BACKEND / ".env")
    parser.add_argument("--environment", required=True, choices=("live", "staging", "preview"))
    parser.add_argument("--deployment-id")
    parser.add_argument("--no-video", action="store_true",
                        help="Small ZIP; expiring R2 video links when available")
    args = parser.parse_args()
    validate_report_id(args.report_id)
    from dotenv import load_dotenv
    from pymongo import MongoClient

    load_dotenv(args.env_file, override=False)
    mongo_url, db_name = os.environ.get("MONGO_URL"), os.environ.get("DB_NAME")
    if not mongo_url or not db_name:
        raise ValueError("Database configuration is unavailable in this environment")
    client = MongoClient(mongo_url, serverSelectionTimeoutMS=10000)
    run_records = model_call_records = None
    try:
        doc = client[db_name].reports.find_one({"id": args.report_id}, {"_id": 0})
        if doc is not None:
            from report_evidence_export import MAX_MODEL_CALLS
            run_records = list(client[db_name].analysis_runs.find(
                {"report_id": args.report_id}, {"_id": 0}).limit(MAX_MODEL_CALLS))
            model_call_records = list(client[db_name].analysis_model_calls.find(
                {"report_id": args.report_id}, {"_id": 0}).limit(MAX_MODEL_CALLS))
    finally:
        client.close()
    if doc is None:
        raise ValueError("Report not found in selected environment")
    # Supports running these two exporter files from a private /tmp directory,
    # while reading the deployed application's existing R2 adapter/source.
    sys.path.append(str(args.source_root / "backend"))
    import r2_storage

    reader = R2Reader(r2_storage) if r2_storage.is_configured() else None
    summary = build_export(doc, args.output, upload_dir=args.upload_dir,
        source_root=args.source_root, environment=args.environment,
        deployment_id=args.deployment_id, object_reader=reader, include_video=not args.no_video,
        run_records=run_records, model_call_records=model_call_records)
    with args.output.open("rb") as stream:
        summary["zip_sha256"] = hashlib.file_digest(stream, "sha256").hexdigest()
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # Never print Mongo/R2 connection strings or underlying exception text.
        print(f"Export failed ({type(exc).__name__}). Check environment and report references.", file=sys.stderr)
        sys.exit(1)
