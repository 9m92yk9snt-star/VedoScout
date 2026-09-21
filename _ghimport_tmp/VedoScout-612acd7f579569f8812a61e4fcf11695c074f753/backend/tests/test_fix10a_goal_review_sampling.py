from __future__ import annotations

import numpy as np

import fix10a_vision_providers as providers


def test_goal_review_sampling_is_dense_immediately_after_release_and_dedupes_actual_pts(monkeypatch):
    captured = {}

    def fake_read_frames(_video_path, requested):
        requested = list(requested)
        captured["requested"] = requested
        out = {}
        strike = 30900
        for ms in requested:
            actual = 30967 if ms in {strike + 50, strike + 100} else int(ms)
            out[int(ms)] = (actual, np.zeros((32, 32, 3), dtype=np.uint8))
        return out

    def fake_write(path, _image):
        path.write_bytes(b"x")
        return True

    async def fake_review(_api_key, _session_id, _paths, media_ms):
        captured["actual_times"] = list(media_ms)
        return {
            "geometry_status": "UNRESOLVED",
            "frames": [],
            "reason": "sampling-test",
            "proof_reason": "sampling-test",
        }

    monkeypatch.setattr(providers, "_read_frames", fake_read_frames)
    monkeypatch.setattr(providers, "_write_jpg", fake_write)
    monkeypatch.setattr(providers, "read_goal_scene_evidence", fake_review)

    bundle = providers.ShadowVisionProviders("key", "sample").bind_video_path("dummy.mp4")
    result = bundle.goal_geometry_provider(
        {"dense_window_id": "w", "end_ms": 34000},
        {"media_ms": 30900},
    )

    requested = captured["requested"]
    early = [ms for ms in requested if 30900 <= ms <= 31100]
    assert early == [30900, 30950, 31000, 31050, 31100]
    actual = captured["actual_times"]
    assert len(actual) == len(set(actual))
    assert actual.count(30967) == 1
    assert result["status"] == "UNRESOLVED"
