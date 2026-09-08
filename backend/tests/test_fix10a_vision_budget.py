"""Deterministic regression for the FIX10A shadow cost/hang guards (0 LLM credit).

Covers:
  1. The shared per-report vision budget fails closed by request count and by
     wall-clock deadline, so providers stop issuing gpt-4o traffic.
  2. run_shadow enforces an outer wall-clock ceiling -> terminal "timeout"
     state persisted, canonical authority never asserted.
  3. run_shadow success path still persists the diagnostic fix10a_* fields.

No network, no real video, no provider calls are made.
"""
import asyncio
import os
import time

os.environ["FIX10A_SHADOW_ENABLED"] = "1"
# Skip real supporting-vision provider construction (needs an API key/network).
os.environ["FIX10A_SUPPORT_VISION_ENABLED"] = "0"

import fix10a_vision_providers as vp
import fix10a_shadow_runtime as rt


class _FakeReports:
    def __init__(self):
        self.updates = []

    async def update_one(self, flt, update):
        self.updates.append((flt, update))
        return None


class _FakeDB:
    def __init__(self):
        self.reports = _FakeReports()


def _ok_unified():
    return {
        "status": "ok",
        "sequence_analysis": {"coverage_complete": True},
        "sequence_plan": {},
        "scene_graph": {},
        "identity_authority": {},
    }


def test_budget_fails_closed_by_count():
    os.environ["FIX10A_MAX_VISION_REQUESTS"] = "0"
    os.environ["FIX10A_VISION_BUDGET_SEC"] = "720"
    bundle = vp.ShadowVisionProviders("fake-key", "sess")
    assert bundle._budget_open() is False
    assert bundle._budget_take(5) == 0
    # Providers must short-circuit with no work when budget is spent.
    assert bundle.jersey_vote_provider("v.mp4", [{"track_id": "t", "media_ms": 1000, "box": {"x": 0.1, "y": 0.1, "w": 0.1, "h": 0.2}}]) == {}
    assert bundle.goal_geometry_provider({"end_ms": 2000}, {"media_ms": 1000}) is None
    print("PASS budget_fails_closed_by_count")


def test_budget_reserves_then_exhausts():
    os.environ["FIX10A_MAX_VISION_REQUESTS"] = "3"
    os.environ["FIX10A_VISION_BUDGET_SEC"] = "720"
    bundle = vp.ShadowVisionProviders("fake-key", "sess")
    assert bundle._budget_open() is True
    assert bundle._budget_take(2) == 2      # 2 granted, 1 remaining
    assert bundle.vision_requests_used() == 2
    assert bundle._budget_take(5) == 1      # only 1 left
    assert bundle.vision_requests_used() == 3
    assert bundle._budget_open() is False   # fully spent
    assert bundle._budget_take(1) == 0
    print("PASS budget_reserves_then_exhausts")


def test_budget_fails_closed_by_deadline():
    os.environ["FIX10A_MAX_VISION_REQUESTS"] = "100"
    os.environ["FIX10A_VISION_BUDGET_SEC"] = "720"
    bundle = vp.ShadowVisionProviders("fake-key", "sess")
    bundle._budget_deadline = time.monotonic() - 1.0  # already past
    assert bundle._budget_open() is False
    assert bundle._budget_take(10) == 0
    print("PASS budget_fails_closed_by_deadline")


def test_run_shadow_outer_timeout_is_terminal():
    os.environ["FIX10A_SHADOW_MAX_SEC"] = "1"

    def _slow(*a, **k):
        time.sleep(3)
        return {"status": "ok", "traces": []}

    orig = rt.physical_match_reconstruction.reconstruct_physical_match
    rt.physical_match_reconstruction.reconstruct_physical_match = _slow
    db = _FakeDB()
    try:
        res = asyncio.run(rt.run_shadow(
            report_id="rid-timeout", video_path="/nonexistent.mp4",
            unified_result=_ok_unified(), db=db,
        ))
    finally:
        rt.physical_match_reconstruction.reconstruct_physical_match = orig
    assert res["status"] == "timeout", res
    assert res["fix10a_canonical_authority"] is False
    assert db.reports.updates, "timeout state was not persisted"
    saved = db.reports.updates[-1][1]["$set"]
    assert saved["fix10a_status"] == "timeout"
    assert saved["fix10a_canonical_authority"] is False
    print("PASS run_shadow_outer_timeout_is_terminal")


def test_run_shadow_success_persists_fields():
    os.environ["FIX10A_SHADOW_MAX_SEC"] = "900"

    def _fast(*a, **k):
        return {"version": 1, "status": "ok", "traces": [], "windows": [],
                "trace_summaries": [], "unresolved_reasons": [], "metrics": {}}

    orig = rt.physical_match_reconstruction.reconstruct_physical_match
    rt.physical_match_reconstruction.reconstruct_physical_match = _fast
    db = _FakeDB()
    try:
        res = asyncio.run(rt.run_shadow(
            report_id="rid-ok", video_path="/nonexistent.mp4",
            unified_result=_ok_unified(), db=db,
        ))
    finally:
        rt.physical_match_reconstruction.reconstruct_physical_match = orig
    assert res["status"] == "ok", res
    saved = db.reports.updates[-1][1]["$set"]
    assert saved["fix10a_status"] == "ok"
    assert saved["fix10a_canonical_authority"] is False
    assert "fix10a_physical_summary" in saved
    print("PASS run_shadow_success_persists_fields")


if __name__ == "__main__":
    test_budget_fails_closed_by_count()
    test_budget_reserves_then_exhausts()
    test_budget_fails_closed_by_deadline()
    test_run_shadow_outer_timeout_is_terminal()
    test_run_shadow_success_persists_fields()
    print("\nALL FIX10A VISION-BUDGET TESTS PASSED")
