"""Lifecycle/readiness API tests: no production DB, video or model calls."""
import ast
import copy
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import Depends, FastAPI, HTTPException, Header
from fastapi.testclient import TestClient

from analysis_progress import analysis_progress


def report(**updates):
    return {"id": "selected", "user_id": "owner", "is_paid": True,
            "analysis_status": "analyzing", "progress_step": 2,
            "created_at": "2026-10-08T15:00:00+00:00", "anchors": [{}] * 11, **updates}


@pytest.mark.parametrize("updates,phase,complete", [
    ({}, "preparing", False),
    ({"progress_step": 3}, "checking_video", False),
    ({"progress_step": 4}, "initial_review", False),
    ({"analysis_status": "ready", "preview": {"brief_summary": "Initial review"}}, "queued", False),
    ({"full_report_status": "generating", "full_pipeline_stage": "queued"}, "queued", False),
    ({"full_report_status": "generating", "full_pipeline_stage": "sequence_model_start"}, "analyzing", False),
    ({"full_report_status": "awaiting_confirmation"}, "awaiting_confirmation", False),
    ({"full_report_status": "verifying", "full_report": {"scores": {}}}, "verifying", False),
    ({"full_report_status": "finalizing", "full_report": {"scores": {}}}, "finalizing", False),
    ({"full_report_status": "failed", "full_report": {"scores": {}}}, "failed", False),
    ({"full_report_status": "ready"}, "preparing", False),
    ({"full_report_status": "ready", "full_report": {"scores": {}}}, "ready", True),
    ({"full_report": {"scores": {}}}, "ready", True),  # genuine legacy
    ({"analysis_status": "failed"}, "failed", False),
])
def test_paid_phase_does_not_confuse_preview_with_full_completion(updates, phase, complete):
    doc = report(**updates); before = copy.deepcopy(doc)
    progress = analysis_progress(doc)
    assert progress["analysis_phase"] == phase
    assert progress["analysis_complete"] is complete
    assert progress["full_report_ready"] is complete
    assert doc == before
    assert progress["taps_received"] == 11
    assert "percentage" not in progress and "eta" not in progress


@pytest.mark.parametrize("value", [None, "bad", {}, [], float("inf"), 0, -100, 999])
def test_legacy_or_malformed_preview_step_is_bounded(value):
    progress = analysis_progress(report(progress_step=value))
    assert 1 <= progress["progress_step"] <= 5
    assert not progress["analysis_complete"]


def test_entitlement_controls_which_report_is_complete():
    doc = report(analysis_status="ready", preview={"brief_summary": "Preview"}, is_paid=False)
    assert analysis_progress(doc)["analysis_phase"] == "preview_ready"
    assert analysis_progress(doc)["analysis_complete"]
    assert not analysis_progress(doc)["full_report_ready"]
    doc["manually_unlocked"] = True
    assert analysis_progress(doc)["analysis_target"] == "full"
    assert not analysis_progress(doc)["analysis_complete"]


def status_app(doc):
    """Execute the actual endpoint with a DB read fake and real auth dependency.
    Importing the 17k-line server is unnecessary and would initialize services.
    """
    module = ast.parse((Path(__file__).resolve().parents[1] / "server.py").read_text())
    node = next(n for n in module.body if isinstance(n, ast.AsyncFunctionDef) and n.name == "get_report_status")
    node.decorator_list = []
    reads = []

    async def find_one(query):
        reads.append(query)
        return copy.deepcopy(doc)

    async def current_user(authorization: str = Header(None)):
        if not authorization:
            raise HTTPException(status_code=401)
        return {"id": authorization, "role": "admin" if authorization == "admin" else "user"}

    namespace = {"Depends": Depends, "get_current_user": current_user, "HTTPException": HTTPException,
                 "db": SimpleNamespace(reports=SimpleNamespace(find_one=find_one)), "analysis_progress": analysis_progress}
    for name in ("video", "poster", "marker", "subject_crop", "display_crop", "player_photo"):
        namespace[f"_resolve_{name}_url"] = lambda d: "/api/uploads/test.jpg"
    exec(compile(ast.Module(body=[node], type_ignores=[]), "real-report-status", "exec"), namespace)
    app = FastAPI(); app.get("/reports/{report_id}/status")(namespace["get_report_status"])
    return TestClient(app), reads


def test_status_endpoint_preserves_auth_and_only_reads_selected_report():
    client, reads = status_app(report())
    assert client.get("/reports/selected/status").status_code == 401
    assert not reads
    assert client.get("/reports/selected/status", headers={"Authorization": "stranger"}).status_code == 403
    for user in ("owner", "admin"):
        response = client.get("/reports/selected/status", headers={"Authorization": user})
        assert response.status_code == 200
        assert response.json()["analysis_phase"] == "preparing"
        assert response.json()["player_details"] == {}
    assert reads == [{"id": "selected"}] * 3


def test_status_endpoint_preview_ready_is_not_full_ready():
    client, _ = status_app(report(analysis_status="ready", preview={"brief_summary": "Initial"},
                                  full_report_status="finalizing", full_report={"scores": {}}))
    data = client.get("/reports/selected/status", headers={"Authorization": "owner"}).json()
    assert data["status"] == "ready"  # backward-compatible preview field
    assert data["preview_ready"] and data["has_full_report"]
    assert data["analysis_phase"] == "finalizing"
    assert not data["analysis_complete"] and not data["full_report_ready"]
    assert "full_report" not in data  # status endpoint stays lightweight


def test_status_endpoint_missing_report():
    client, _ = status_app(None)
    assert client.get("/reports/missing/status", headers={"Authorization": "owner"}).status_code == 404
