"""Restore pinned local ONNX graphs from repository-bundled binary parts.

The connector's request limit is smaller than the graphs. Parts are ordinary
binary Git files; assembly is local, bounded, checksum-checked and atomic.
There is no model download or build dependency in the serving process.
"""
import hashlib
import json
import os
from pathlib import Path
import tempfile

MAX_PART_BYTES = 8 * 1024 * 1024
MAX_MODEL_BYTES = 64 * 1024 * 1024


def ensure_model_asset(path, expected_sha256):
    path = Path(path)
    if path.is_file():
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected_sha256:
            raise ValueError("Player model checksum mismatch")
        return path
    bundle = path.parent / "segmentation-assets"
    try:
        manifest = json.loads((bundle / "manifest.json").read_text())
        record = manifest["assets"][path.name]
        if (manifest.get("version") != 1 or record["sha256"] != expected_sha256
                or not 0 < record["bytes"] <= MAX_MODEL_BYTES
                or not 1 <= len(record["parts"]) <= 8):
            raise ValueError("Invalid player model bundle")
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError("Player model bundle unavailable") from exc
    temporary = None
    try:
        digest = hashlib.sha256()
        total = 0
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".player-model-", delete=False) as output:
            temporary = Path(output.name)
            for index, part in enumerate(record["parts"], 1):
                if (part["file"] != f"{path.name}.part{index:03d}"
                        or not 0 < part["bytes"] <= MAX_PART_BYTES):
                    raise ValueError("Invalid player model part")
                source = bundle / part["file"]
                if source.stat().st_size != part["bytes"]:
                    raise ValueError("Player model part size mismatch")
                part_digest = hashlib.sha256()
                with source.open("rb") as stream:
                    while data := stream.read(1024 * 1024):
                        total += len(data)
                        if total > record["bytes"]:
                            raise ValueError("Player model bundle size mismatch")
                        part_digest.update(data); digest.update(data); output.write(data)
                if part_digest.hexdigest() != part["sha256"]:
                    raise ValueError("Player model part checksum mismatch")
            if total != record["bytes"] or digest.hexdigest() != expected_sha256:
                raise ValueError("Player model checksum mismatch")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
        temporary = None
    except (OSError, KeyError, TypeError) as exc:
        raise ValueError("Player model bundle unavailable") from exc
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return path
