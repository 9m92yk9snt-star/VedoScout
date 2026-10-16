"""Reproduce the FIX19 WIP assets from explicitly supplied official weights.

Build-time only: serving must never download models or install Torch.
See docs/continuation-fix19-player-cutout-20261014.md for pinned dependencies,
source URLs, MobileSAM revision and licensing. Output hashes are checked; an
unexpected export needs review rather than silently changing runtime pins.
"""
import argparse
import hashlib
from pathlib import Path
import shutil
import sys


SOURCE_HASHES = {
    "yolo": "a7cd8f929e1903d78a12a48efecab430209f18dc46cb96c3599a5980c63c423c",
    "sam": "6dbb90523a35330fedd7f1d3dfc66f995213d81b29a5ca8108dbcdd4e37d6c2f",
}
OUTPUT_HASHES = {
    "yolov8n-seg.onnx": "015043fb9cc94830ad7065dd3e28d6f8e5758fe03071451675120f6a6b6e44e9",
    "mobile-sam-encoder.onnx": "85dc9194671a1173fc5632fc1ffae698f3ca0c82c7b208ed618a568377380d7e",
    "mobile-sam-decoder.onnx": "43c7655a81b62c0f2b0e31d2bc91d3811b48d7f736ecf93b3a4a1254318241cf",
}


def verify(path, expected):
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != expected:
        raise ValueError(f"Checksum mismatch for {path.name}: {actual}")
    print(f"{path.name}: {path.stat().st_size} bytes, SHA256 {actual}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--yolo-weights", type=Path, required=True)
    parser.add_argument("--mobile-sam-source", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path,
                        default=Path(__file__).resolve().parents[1] / "models")
    args = parser.parse_args()
    sam_weights = args.mobile_sam_source / "weights" / "mobile_sam.pt"
    verify(args.yolo_weights, SOURCE_HASHES["yolo"])
    verify(sam_weights, SOURCE_HASHES["sam"])
    args.output_dir.mkdir(parents=True, exist_ok=True)
    import torch
    from ultralytics import YOLO
    torch.set_num_threads(4)
    exported = Path(YOLO(str(args.yolo_weights)).export(
        format="onnx", imgsz=640, opset=12, simplify=False,
        dynamic=False, device="cpu"))
    yolo_target = args.output_dir / "yolov8n-seg.onnx"
    if exported.resolve() != yolo_target.resolve():
        shutil.copyfile(exported, yolo_target)
    verify(yolo_target, OUTPUT_HASHES[yolo_target.name])
    sys.path.insert(0, str(args.mobile_sam_source.resolve()))
    from mobile_sam import sam_model_registry
    from mobile_sam.utils.onnx import SamOnnxModel
    sam = sam_model_registry["vit_t"](checkpoint=str(sam_weights)).eval()
    encoder = args.output_dir / "mobile-sam-encoder.onnx"
    decoder = args.output_dir / "mobile-sam-decoder.onnx"
    torch.onnx.export(
        sam.image_encoder, torch.zeros(1, 3, 1024, 1024), str(encoder),
        input_names=["images"], output_names=["embeddings"],
        opset_version=17, do_constant_folding=True)
    model = SamOnnxModel(sam, return_single_mask=False).eval()
    inputs = (
        torch.zeros(1, 256, 64, 64),
        torch.tensor([[[512., 512.], [100., 100.], [0., 0.], [1024., 1024.]]]),
        torch.tensor([[1., 0., 2., 3.]]), torch.zeros(1, 1, 256, 256),
        torch.tensor([0.]), torch.tensor([512., 512.]))
    torch.onnx.export(
        model, inputs, str(decoder), opset_version=17, do_constant_folding=True,
        input_names=["image_embeddings", "point_coords", "point_labels",
                     "mask_input", "has_mask_input", "orig_im_size"],
        output_names=["masks", "iou_predictions", "low_res_masks"],
        dynamic_axes={"point_coords": {1: "num_points"},
                      "point_labels": {1: "num_points"}})
    for path in (encoder, decoder):
        verify(path, OUTPUT_HASHES[path.name])


if __name__ == "__main__":
    main()
