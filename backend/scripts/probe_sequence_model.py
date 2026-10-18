"""One small authenticated connection check; no footage, retries or key output."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import sequence_pilot_transport as transport


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def probe():
    started = time.monotonic()
    result = {"status": "NOT_SENT", "request_attempts": 0,
              "requested_model": "gemini-2.5-pro", "max_output_tokens": 64,
              "footage_sent": False, "football_perception_verified": False}
    key = os.environ.get("EMERGENT_LLM_KEY")
    if not key:
        result.update(status="MODEL_KEY_NOT_CONFIGURED", elapsed_seconds=0.)
        return result
    try:
        url, payload, _ = transport.build_request("emergent", result["requested_model"],
            [{"type": "text", "text": 'Reply with this JSON object only: {"ok":true}'}])
        body = json.loads(payload)
        body["max_tokens"] = result["max_output_tokens"]
        request = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
            headers={"Content-Type": "application/json", "Authorization": "Bearer " + key})
        opener = urllib.request.build_opener(NoRedirect())
        result["request_attempts"] = 1
        with opener.open(request, timeout=30.) as response:
            result["http_status"] = response.status
            raw = response.read(65537)
        if len(raw) > 65536:
            raise ValueError("RESPONSE_TOO_LARGE")
        response = json.loads(raw)
        choice = response["choices"][0]
        text = choice["message"]["content"]
        reply_ok = isinstance(text, str) and json.loads(text) == {"ok": True}
        result["probe_reply_ok"] = reply_ok
        result["status"] = ("MODEL_PROBE_COMPLETED" if reply_ok and choice.get("finish_reason") == "stop"
                            else "MODEL_RESPONSE_INCOMPLETE")
        usage = response.get("usage") or {}
        result["usage"] = {k: usage[k] for k in ("prompt_tokens", "completion_tokens", "total_tokens")
                           if type(usage.get(k)) is int and usage[k] >= 0}
    except urllib.error.HTTPError as exc:
        result.update(http_status=exc.code, status=("MODEL_ACCESS_DENIED" if exc.code in {401, 403}
            else "MODEL_QUOTA_OR_RATE_LIMIT" if exc.code in {402, 429}
            else "MODEL_REDIRECT_REFUSED" if 300 <= exc.code < 400 else "MODEL_HTTP_ERROR"))
        exc.close()
    except (urllib.error.URLError, TimeoutError, OSError):
        result["status"] = "MODEL_CONNECTION_FAILED"
    except (ValueError, KeyError, TypeError, IndexError):
        result["status"] = "INVALID_MODEL_RESPONSE"
    result["elapsed_seconds"] = round(time.monotonic() - started, 3)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit("OUTPUT_MUST_BE_NEW")
    result = probe()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2), flush=True)
    return 0 if result["status"] == "MODEL_PROBE_COMPLETED" else 3


if __name__ == "__main__":
    raise SystemExit(main())
