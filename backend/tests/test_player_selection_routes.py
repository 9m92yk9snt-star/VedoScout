import io
import json
from PIL import Image
from fastapi.testclient import TestClient
from selection_route_fixture import selection_app


def image():
    out = io.BytesIO(); Image.new("RGB", (160, 240), "green").save(out, "JPEG"); return out.getvalue()


def test_real_route_dependency_and_request_limits():
    client = TestClient(selection_app())
    hints = json.dumps({"box": {"x": .3, "y": .2, "w": .2, "h": .4}, "target_point": {"x": .4, "y": .3}})
    args = {"files": {"frame": ("frame.jpg", image(), "image/jpeg")}, "data": {"hints": hints}}
    assert client.post("/api/player-selection/mask", **args).status_code == 401
    headers = {"Authorization": "Bearer selection-test-only"}
    assert client.post("/api/player-selection/mask", headers=headers, **args).status_code == 200
    response = client.post("/api/player-selection/mask", headers=headers,
                           files={"frame": ("frame.jpg", b"x" * (2 * 1024 * 1024 + 1), "image/jpeg")}, data={"hints": hints})
    assert response.status_code == 413
    assert client.post("/api/player-selection/mask", headers=headers, files=args["files"], data={"hints": "[]"}).status_code == 400


def test_tracking_route_rejects_partial_and_nonmonotonic_images():
    client = TestClient(selection_app()); headers = {"Authorization": "Bearer selection-test-only"}
    files = [("frames", ("frame.jpg", image(), "image/jpeg"))] * 3
    for times, visibility in (([0, .2, .4], "partial"), ([0, .2, .1], "visible")):
        hints = json.dumps({"times": times, "anchor": {"box": {"x": .3, "y": .2, "w": .2, "h": .4}, "visibility": visibility}})
        assert client.post("/api/player-selection/tracking-preview", files=files, data={"hints": hints}).status_code == 401
        assert client.post("/api/player-selection/tracking-preview", files=files, data={"hints": hints}, headers=headers).status_code == 400


def test_original_anchor_persistence_keeps_hints_without_partial_fingerprints(tmp_path):
    import ast
    from pathlib import Path
    import asyncio
    source = ast.parse((Path(__file__).resolve().parents[1] / "server.py").read_text())
    nodes = [n for n in source.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in {"_build_primary_anchor_payload", "_build_original_anchor_payloads"}]
    namespace = {"UPLOAD_DIR": tmp_path, "ORIGINAL_ANCHOR_LIMIT": 13, "asyncio": asyncio, "Path": Path}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "production-anchor-builders", "exec"), namespace)
    box = {"x": .3, "y": .2, "w": .2, "h": .4}
    anchor = {"t": 4, "box": box, "segment": 0, "visibility": "partial", "exclude_points": [{"x": .6, "y": .3}],
              "continuity": [{"t": 4.5, "box": box, "segment": 0, "same_player": True}]}
    primary = namespace["_build_primary_anchor_payload"]("test", 4, box, anchor, None, None)
    assert primary["visibility"] == "partial" and primary["continuity"][0]["same_player"]
    rows, crops, wides, verifies = asyncio.run(namespace["_build_original_anchor_payloads"]("test", "unused", [{"t": 0, "box": box}, anchor]))
    assert rows[0]["continuity"][0]["t"] == 4.5
    assert rows[0]["exclude_points"] == anchor["exclude_points"]
    assert not crops and not wides and not verifies
