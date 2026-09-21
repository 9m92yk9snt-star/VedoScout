"""Regression coverage for FIX10A per-window failure diagnostics.

The shadow worker must fail closed on one bad critical window while preserving
enough bounded diagnostic context to identify the exact deterministic stage.
Nothing in this test grants canonical authority.
"""

import physical_match_reconstruction as pmr


def test_index_error_records_exact_stage_and_traceback(monkeypatch):
    window = {
        "dense_window_id": "dense_diag_goal",
        "scene_id": "scene_007",
        "start_ms": 53065,
        "end_ms": 58931,
    }

    monkeypatch.setattr(
        pmr.dense_replay,
        "select_critical_windows",
        lambda plan, analysis: [dict(window)],
    )

    def explode(*args, **kwargs):
        raise IndexError("synthetic real-shape regression")

    monkeypatch.setattr(pmr.dense_track_refinement, "refine_window", explode)

    result = pmr.reconstruct_physical_match(
        "/tmp/diagnostic.mp4",
        {},
        {},
        {},
        {},
        dense_frame_provider=lambda *args: [],
    )

    assert result["status"] == "error"
    assert result["metrics"]["critical_windows"] == 1
    assert result["metrics"]["windows_ok"] == 0
    assert result["metrics"]["windows_failed"] == 1
    assert result["metrics"]["windows_failed_by_stage"] == {
        "dense_track_refinement": 1
    }

    row = result["windows"][0]
    assert row["dense_window_id"] == "dense_diag_goal"
    assert row["status"] == "error"
    assert row["reason"] == "WINDOW_RECONSTRUCTION_ERROR:IndexError"
    assert row["error_stage"] == "dense_track_refinement"
    assert row["error_type"] == "IndexError"
    assert row["error_message"] == "synthetic real-shape regression"
    assert "IndexError: synthetic real-shape regression" in row["error_traceback"]
    assert len(row["error_traceback"]) <= pmr.MAX_TRACEBACK_CHARS

    # FIX10A remains evidence-only: no canonical authority fields are created.
    forbidden = {
        "canonical_events",
        "event_ledger",
        "verified_stats",
        "goals",
        "assists",
        "scorer",
    }
    assert forbidden.isdisjoint(result)
