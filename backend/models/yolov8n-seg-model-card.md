# Local player-outline model

This is an Ultralytics YOLOv8n instance-segmentation model, not the existing
box-only `yolov8n.onnx`. The person class provides separate visible-pixel masks
for candidate people in a bounded crop around the human's tap.

- Source: https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov8n-seg.pt
- Source bytes: 7,071,756
- Source SHA256: `a7cd8f929e1903d78a12a48efecab430209f18dc46cb96c3599a5980c63c423c`
- Export: Ultralytics 8.3.0, PyTorch 2.5.1+cpu, ONNX 1.17.0, static 640,
  opset 12, CPU, no simplification
- Export bytes: 13,841,502
- Export SHA256: `015043fb9cc94830ad7065dd3e28d6f8e5758fe03071451675120f6a6b6e44e9`
- Output shapes: `(1,116,8400)` and `(1,32,160,160)`
- License: Ultralytics AGPL-3.0 (https://github.com/ultralytics/ultralytics/blob/v8.3.0/LICENSE)
- Documentation: https://docs.ultralytics.com/tasks/segment/

The bundled model is checksum-checked and restored locally from the binary
parts in `segmentation-assets/manifest.json`. The original source license is
preserved in `Ultralytics-AGPL-3.0.txt`. The complete package remains a review
candidate until CI/review, not a production deployment.
See `docs/fix19-player-cutout-validation.md` for current validation and known
limitations. Serving uses the existing OpenCV
CPU dependency; it does not install Torch, download weights, call an LLM,
transmit the frame to another service, or infer hidden body parts.

The model can miss small, blurred or heavily occluded people. A tap must match
one visible person mask; unresolved alternatives return no mask. Behind-mode
selections remain partial, exclude the independently marked foreground person,
and do not seed a full-body identity or certify hidden contact/scoring actions.

To reproduce the graph in an isolated export environment with the versions
above, verify the source checksum and run:

```python
from ultralytics import YOLO
YOLO("yolov8n-seg.pt").export(format="onnx", imgsz=640, opset=12,
                            simplify=False, dynamic=False, device="cpu")
```
