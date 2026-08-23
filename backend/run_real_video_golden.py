"""Command-line runner for the locked FIX10 real-video Golden Fixture.

The reference video remains external/private. Dense FIX10A traces are supplied
as .json or deterministic .json.gz artifacts (normally downloaded from R2).
This script never runs or influences production analysis; it only validates
already-produced evidence against an external acceptance manifest.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import event_trace
import golden_fixture_validator as gfv


def _load_json(path: str | Path) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"JSON_OBJECT_REQUIRED:{path}")
    return data


def _load_trace(path: str | Path) -> dict:
    p = Path(path)
    if p.suffix == ".gz":
        data = event_trace.decode_trace_gzip(p.read_bytes())
    else:
        data = _load_json(p)
    if not isinstance(data, dict) or not data.get("trace_id"):
        raise ValueError(f"INVALID_FIX10A_TRACE:{path}")
    return data


def run_validation(*, manifest_path: str, video_path: str,
                   trace_paths, sequence_analysis_path: str | None = None) -> dict:
    manifest = gfv.load_manifest(manifest_path)
    source = gfv.verify_source_fingerprint(video_path, manifest)
    if source["status"] == gfv.FAIL:
        return {
            "fixture_id": manifest.get("fixture_id"),
            "status": gfv.FAIL,
            "source": source,
            "cases": [],
            "reason": "REFERENCE_VIDEO_FINGERPRINT_MISMATCH",
        }
    if source["status"] != gfv.PASS:
        return {
            "fixture_id": manifest.get("fixture_id"),
            "status": gfv.UNRESOLVED,
            "source": source,
            "cases": [],
            "reason": "REFERENCE_VIDEO_NOT_VERIFIED",
        }
    traces = [_load_trace(path) for path in trace_paths]
    sequence = _load_json(sequence_analysis_path) if sequence_analysis_path else {}
    verdict = gfv.validate_fixture(manifest, {"traces": traces}, sequence)
    verdict["source"] = source
    verdict["trace_files"] = len(traces)
    return verdict


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Validate FIX10A real-video Golden Fixture")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--video", required=True)
    parser.add_argument("--trace", action="append", default=[], help="FIX10A trace .json/.json.gz; repeatable")
    parser.add_argument("--sequence-analysis", default=None)
    parser.add_argument("--output", default=None)
    args = parser.parse_args(argv)
    result = run_validation(
        manifest_path=args.manifest,
        video_path=args.video,
        trace_paths=args.trace,
        sequence_analysis_path=args.sequence_analysis,
    )
    text = json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    else:
        print(text)
    if result.get("status") == gfv.PASS:
        return 0
    if result.get("status") == gfv.FAIL:
        return 2
    return 3


if __name__ == "__main__":
    sys.exit(main())
