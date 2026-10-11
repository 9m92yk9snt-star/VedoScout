"""Fail-closed local pytest harness; no credentials, network, video or real SDK."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import socket
import sys


parser = argparse.ArgumentParser()
parser.add_argument("--backend", required=True)
parser.add_argument("--tb", choices=["short", "line", "long"], default="short")
parser.add_argument("tests", nargs="+")
args = parser.parse_args()
backend = Path(args.backend).resolve()
if (backend / ".env").exists():
    raise SystemExit("Refuse tests with an environment file in the selected backend")
for name in list(os.environ):
    if any(token in name.upper() for token in ("API_KEY", "EMERGENT_LLM_KEY", "OPENAI_KEY")):
        os.environ.pop(name, None)
os.environ["LITELLM_LOCAL_MODEL_COST_MAP"] = "True"
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
sys.dont_write_bytecode = True
sys.path.insert(0, str(backend))
attempts = {"network": 0, "actual_sdk": 0, "video_decode": 0}


def block(kind):
    def forbidden(*_args, **_kwargs):
        attempts[kind] += 1
        raise RuntimeError("OFFLINE_TEST_FORBIDDEN_" + kind.upper())
    return forbidden


socket.socket.connect = block("network")
socket.socket.connect_ex = block("network")
socket.create_connection = block("network")
import cv2
cv2.VideoCapture = block("video_decode")
import fix10a_vision_providers
import identity_verify
fix10a_vision_providers.LlmChat = block("actual_sdk")
identity_verify.LlmChat = block("actual_sdk")
import pytest

rc = pytest.main(["-q", "--tb=" + args.tb, "-p", "no:cacheprovider", "-o", "asyncio_mode=auto", *args.tests])
print(json.dumps({"kind": "R6_LOCAL_OFFLINE_TEST_RECEIPT", "backend": str(backend),
                  "pytest_exit_code": int(rc), "forbidden_attempts": attempts,
                  "new_model_calls": 0, "native_video_decode_calls": 0}, sort_keys=True))
raise SystemExit(int(rc) if not any(attempts.values()) else 90)
