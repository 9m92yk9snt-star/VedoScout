"""Package verified exported graphs as bounded binary Git files."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from player_segmentation_assets import MAX_PART_BYTES, ensure_model_asset
from export_player_selection_models import OUTPUT_HASHES, verify


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-dir", type=Path, default=Path(__file__).resolve().parents[1] / "models")
    args = parser.parse_args()
    bundle = args.model_dir / "segmentation-assets"
    assets = {}
    for name, expected in OUTPUT_HASHES.items():
        source = args.model_dir / name
        verify(source, expected)
        bundle.mkdir(parents=True, exist_ok=True)
        parts = []
        with source.open("rb") as stream:
            while data := stream.read(MAX_PART_BYTES):
                part = f"{name}.part{len(parts) + 1:03d}"
                (bundle / part).write_bytes(data)
                parts.append({"file": part, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})
        assets[name] = {"bytes": source.stat().st_size, "sha256": expected, "parts": parts}
    (bundle / "manifest.json").write_text(json.dumps({"version": 1, "assets": assets}, indent=2) + "\n")
    for name, expected in OUTPUT_HASHES.items():
        ensure_model_asset(args.model_dir / name, expected)
    print(f"Packaged {len(assets)} checksum-pinned local models.")


if __name__ == "__main__":
    main()
