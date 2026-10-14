"""Exercise the production worker/compatibility route without models or video."""
import ast
import asyncio
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException


SOURCE = ast.parse((Path(__file__).resolve().parents[1] / "server.py").read_text())


def load_function(name, namespace):
    node = deepcopy(next(n for n in ast.walk(SOURCE)
                         if isinstance(n, ast.AsyncFunctionDef) and n.name == name))
    node.decorator_list = []
    exec(compile(ast.Module(body=[node], type_ignores=[]), "production-identity-flow", "exec"), namespace)
    return namespace[name]


class Reports:
    def __init__(self, doc):
        self.doc = deepcopy(doc)
        self.updates = []

    async def find_one(self, *args, **kwargs):
        return deepcopy(self.doc)

    async def update_one(self, query, update):
        self.updates.append((query, deepcopy(update)))
        if self.doc is not None:
            self.doc.update(deepcopy(update.get("$set", {})))


def environment(doc):
    reports = Reports(doc)
    ns = {"db": SimpleNamespace(reports=reports), "asyncio": asyncio,
          "logger": SimpleNamespace(info=lambda *a: None, exception=lambda *a: None),
          "_wd_heartbeat": lambda: {"heartbeat": "test-heartbeat"},
          "HTTPException": HTTPException, "DoubtConfirmPayload": object,
          "Depends": lambda value: None, "get_current_user": object()}
    return ns, reports


def track():
    return {"points": [{"t": 17.2, "status": "UNKNOWN", "reason": "SCENE_CUT"}],
            "segments": [], "seed_count": 3,
            "doubt_moments": [{"t": 17.2, "reason": "kit_colour_change"}]}


def test_uncertainty_continues_without_waiting_or_changing_identity(monkeypatch):
    ns, reports = environment({"id": "r"})
    function = load_function("_continue_identity_analysis", ns)
    original = track()
    before = deepcopy(original)

    async def forbidden_wait(*args):
        raise AssertionError("Automatic analysis must not wait for an owner tap")

    monkeypatch.setattr(asyncio, "sleep", forbidden_wait)
    result = asyncio.run(function("r", original, original["doubt_moments"]))
    assert result is original and result == before
    assert len(reports.updates) == 1
    assert reports.doc["full_report_status"] == "generating"
    assert reports.doc["doubt_status"] == "automatic"
    assert reports.doc["identity_recovery"]["manual_checks_required"] is False
    assert reports.doc["identity_recovery"]["uncertain_moments"] == before["doubt_moments"]
    assert result["points"][0]["status"] == "UNKNOWN"


def test_no_uncertainty_needs_no_database_step():
    ns, reports = environment({"id": "r"})
    function = load_function("_continue_identity_analysis", ns)
    original = {"points": [], "segments": []}
    assert asyncio.run(function("r", original, [])) is original
    assert not reports.updates


@pytest.mark.parametrize("seed_count", [3, 10, 13])
@pytest.mark.parametrize("previously_resolved", [False, True])
def test_real_tracking_worker_keeps_only_initial_seeds(seed_count, previously_resolved):
    ns, reports = environment({"id": "r", "doubt_resolved": previously_resolved})
    initial = [{"t": i + .25, "box": {"x": .3, "y": .2, "w": .1, "h": .3},
                "target_point": {"x": .35, "y": .3}} for i in range(seed_count)]
    before = deepcopy(initial)
    calls = []

    def native_tracker(path, seeds, offset):
        calls.append((path, deepcopy(seeds), offset))
        return track()

    ns.update({"doc": reports.doc, "report_id": "r", "file_path": "canonical.mp4",
               "valid_anchors": initial, "marker_path": None, "track_player": native_tracker})
    load_function("_continue_identity_analysis", ns)
    function = load_function("_tracking_core", ns)
    result, offset = asyncio.run(function())
    assert calls == [("canonical.mp4", before, 0.0)]
    assert initial == before and offset == 0
    assert result["points"] == track()["points"]
    assert "doubt_moments" not in result
    assert reports.doc["doubt_status"] == "automatic"
    assert reports.doc["full_report_status"] == "generating"


def test_diagnostic_write_failure_does_not_discard_the_track():
    ns, reports = environment({"id": "r"})

    async def unavailable(*args):
        raise RuntimeError("Temporary diagnostic write failure")

    reports.update_one = unavailable
    ns.update({"doc": reports.doc, "report_id": "r", "file_path": "canonical.mp4",
               "valid_anchors": [{"t": .2, "box": {"x": .2, "y": .2, "w": .1, "h": .3}}],
               "marker_path": None, "track_player": lambda *a: track()})
    load_function("_continue_identity_analysis", ns)
    result, offset = asyncio.run(load_function("_tracking_core", ns)())
    assert result["points"] == track()["points"] and offset == 0


@pytest.mark.parametrize("status", ["automatic", "applied", "skipped", None])
def test_new_analyses_reject_late_manual_seeds(status):
    ns, reports = environment({"id": "r", "user_id": "owner", "doubt_status": status,
                               "doubt_moments": [{"t": 17.2}]})
    endpoint = load_function("confirm_doubt_moments", ns)
    payload = SimpleNamespace(skip=False, taps=[SimpleNamespace(idx=0, x=.5, y=.5)])
    with pytest.raises(HTTPException) as error:
        asyncio.run(endpoint("r", payload, {"id": "owner"}))
    assert error.value.status_code == 409
    assert not reports.updates


def test_old_waiting_worker_can_resume_without_any_new_taps():
    ns, reports = environment({"id": "r", "user_id": "owner", "doubt_status": "awaiting",
                               "doubt_moments": [{"t": 17.2}],
                               "player_details": {"jersey_number": "15"}})
    endpoint = load_function("confirm_doubt_moments", ns)
    result = asyncio.run(endpoint("r", SimpleNamespace(skip=True, taps=[]), {"id": "owner"}))
    assert result == {"ok": True, "status": "skipped"}
    assert reports.doc["doubt_resolved"] is True
    assert reports.doc["player_details"]["jersey_number"] == "15"
    assert "doubt_confirmations" not in reports.doc


@pytest.mark.parametrize("doc,code", [(None, 404), ({"id": "r", "user_id": "someone-else"}, 403)])
def test_legacy_resume_preserves_report_ownership(doc, code):
    ns, reports = environment(doc)
    endpoint = load_function("confirm_doubt_moments", ns)
    with pytest.raises(HTTPException) as error:
        asyncio.run(endpoint("r", SimpleNamespace(skip=True, taps=[]), {"id": "owner"}))
    assert error.value.status_code == code
    assert not reports.updates
