"""Isolated real selection routes with a local authentication fixture.

Avoid importing the app's unrelated Mongo/Stripe/LLM startup dependencies.
Route bodies and decorators are compiled unchanged from server.py.
"""
import ast
import asyncio
import json
import logging
from pathlib import Path
from fastapi import FastAPI, APIRouter, Depends, HTTPException, UploadFile, File, Form, Header


def selection_app():
    async def get_current_user(authorization: str = Header(default="")):
        if authorization != "Bearer selection-test-only":
            raise HTTPException(401, "Authentication required")
        return {"id": "isolated-selection-test"}
    router = APIRouter(prefix="/api")
    namespace = {**globals(), "api_router": router, "get_current_user": get_current_user,
                 "_selection_slots": asyncio.Semaphore(2), "logger": logging.getLogger("selection-test")}
    source = ast.parse((Path(__file__).resolve().parents[1] / "server.py").read_text())
    names = {"suggest_player_selection_mask", "preview_player_selection_tracking"}
    nodes = [n for n in source.body if isinstance(n, ast.AsyncFunctionDef) and n.name in names]
    assert len(nodes) == 2
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "production-selection-routes", "exec"), namespace)
    app = FastAPI(); app.include_router(router)
    return app
