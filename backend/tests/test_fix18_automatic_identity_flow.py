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
