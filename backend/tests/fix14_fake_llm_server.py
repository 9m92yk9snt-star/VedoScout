"""FIX14 test-only loopback chat-completions server; logs request shape, never image bytes."""

import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

STATE = {"mode": "success", "active": 0, "max_active": 0, "log": []}
LOCK = threading.Lock()
KINDS = (
    ("Inspect visible pixel locations only", "action"),
    ("classify only visibly supported football player roles", "role"),
    ("inspect football goal geometry", "goal"),
    ("inspect only visible football pitch/goal geometry", "field_side"),
    ("read visible football shirt numbers", "number"),
)
FIELD = {"visible": True, "field_side": {"x": 0.5, "y": 0.6}, "confidence": "high", "reason": "fake offline server"}
CONTENT = {
    "action": {"frames": [{"idx": 1, "balls": [], "selected_body_ids": []}]},
    "role": {"role": "OUTFIELD", "confidence": "high", "reason": "fake offline server"},
    "goal": {
        "geometry_status": "UNRESOLVED",
        "frames": [],
        "ball_evidence": [],
        "crossing": "UNRESOLVED",
        "crossing_confidence": "low",
        "reason": "fake offline server",
    },
    "field_side": {"frames": [{"idx": 1, **FIELD}, {"idx": 2, **FIELD}]},
    "number": {"readable": True, "number": "88", "confidence": "high", "reason": "fake offline server"},
}


def response_content(kind, messages, mode):
    if kind in {"action", "goal"}:
        image_count = sum(
            part.get("type") == "image_url"
            for message in messages or []
            if isinstance(message, dict) and isinstance(message.get("content"), list)
            for part in message["content"]
            if isinstance(part, dict)
        )
        if kind == "goal":
            geometry_count = max(0, image_count - 1) if mode == "partial_goal" else image_count
            return {
                **CONTENT["goal"],
                "frames": [{"idx": i, "visible": False} for i in range(1, geometry_count + 1)],
                "ball_evidence": [{"idx": i, "ball_visible": False, "relation": "UNRESOLVED"}
                                  for i in range(1, image_count + 1)],
            }
        if mode != "partial_action":
            return {"frames": [{"idx": i, "balls": [], "selected_body_ids": []} for i in range(1, image_count + 1)]}
    return CONTENT.get(kind, {})


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *_args):
        pass

    def _json(self, code, body):
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        with LOCK:
            self._json(200, dict(STATE))

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        if self.path == "/__mode":
            with LOCK:
                STATE.update(mode=json.loads(body)["mode"], max_active=0, log=[])
            for _ in range(40):
                if STATE["active"] == 0:
                    break
                time.sleep(0.05)
            return self._json(200, {"ok": True})
        request = json.loads(body)
        messages = json.dumps(request.get("messages"))
        auth = self.headers.get("Authorization", "")
        with LOCK:
            mode = STATE["mode"]
            STATE["active"] += 1
            STATE["max_active"] = max(STATE["max_active"], STATE["active"])
            STATE["log"].append(
                {
                    "path": self.path,
                    "mode": mode,
                    "model": request.get("model"),
                    "kind": next((k for marker, k in KINDS if marker in messages), "unknown"),
                    "auth_scheme": auth.split(" ")[0],
                    "key_prefix": auth.split(" ")[-1][:12],
                    "images": messages.count("image_url"),
                    "body_bytes": len(body),
                }
            )
            kind = STATE["log"][-1]["kind"]
        try:
            started = time.monotonic()
            while mode == "hang" and STATE["mode"] == "hang" and time.monotonic() - started < 120:
                time.sleep(0.05)
            if mode == "hang":
                return
            if mode.startswith("slow:"):
                time.sleep(float(mode[5:]))
            if mode == "api_error":
                return self._json(500, {"error": {"message": "fake offline server error", "type": "server_error"}})
            self._json(
                200,
                {
                    "id": "chatcmpl-fix14",
                    "object": "chat.completion",
                    "created": int(time.time()),
                    "model": request.get("model"),
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
                    "choices": [
                        {
                            "index": 0,
                            "finish_reason": "stop",
                            "message": {
                                "role": "assistant",
                                "content": json.dumps(response_content(kind, request.get("messages"), mode)),
                            },
                        }
                    ],
                },
            )
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            with LOCK:
                STATE["active"] -= 1


if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    sys.stdout.write(f"{server.server_address[1]}\n")
    sys.stdout.flush()
    server.serve_forever()
