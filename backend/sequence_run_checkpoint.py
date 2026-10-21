"""Exact-request retry receipts and bounded, credential-free failure metadata."""
import hashlib
from pathlib import Path


def code_fingerprint():
    root = Path(__file__).parent
    paths = [root / name for name in (
        "sequence_pilot.py", "sequence_pilot_transport.py", "player_selection.py",
        "sequence_run_checkpoint.py", "sequence_report_runtime.py", "sequence_report_adapter.py")]
    paths.append(root / "scripts/run_sequence_pilot.py")
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


def reusable_receipt(receipt, request, *, provider, model, packet_id):
    """The rebuilt request covers source pixels, selections, prompts and settings."""
    raw = receipt.get("raw_response")
    return (receipt.get("packet_id") == packet_id
            and receipt.get("origin") == "LIVE_MODEL_REQUEST"
            and receipt.get("status") == "COMPLETED"
            and receipt.get("provider") == provider
            and receipt.get("requested_model") == model
            and receipt.get("payload_sha256") == request.get("payload_sha256")
            and isinstance(raw, str) and bool(raw)
            and hashlib.sha256(raw.encode()).hexdigest() == receipt.get("response_sha256"))


SAFE_ERRORS = frozenset({
    "MODEL_ACCESS_DENIED", "MODEL_KEY_NOT_CONFIGURED", "MODEL_QUOTA_OR_RATE_LIMIT",
    "MODEL_HTTP_ERROR", "MODEL_CONNECTION_FAILED", "MODEL_CHILD_EXITED",
    "MODEL_WALL_DEADLINE_EXCEEDED", "MODEL_ACCESS_STOPPED", "RUN_TIME_BUDGET_EXHAUSTED",
    "INVALID_PROVIDER_RESPONSE", "INCOMPLETE_MODEL_RESPONSE", "EMPTY_MODEL_RESPONSE",
    "REQUEST_IMAGE_BUDGET_EXCEEDED", "RESPONSE_BYTE_BUDGET_EXCEEDED", "PREPARED_IMAGE_CHANGED",
    "SOURCE_VIDEO_CHANGED", "DETAIL_PREPARATION_TIME_BUDGET_EXHAUSTED",
    "EXPERIMENT_PROCESSING_FAILED", "INVALID_EXECUTION_BUDGET", "IDENTITY_PROFILE_UNRESOLVED",
    "INITIAL_RECEIPT_INPUT_MISMATCH", "INVALID_OBSERVATION_RESPONSE",
})


def failure_metadata(phase, elapsed, *, returncode=None, timeout=False, result=None, receipts=()):
    """Never copy stderr, provider bodies, paths, prompts or exception text."""
    result = result if isinstance(result, dict) else {}
    rows = list(receipts)[:32]
    errors = {r.get("error") for r in rows if r.get("error") in SAFE_ERRORS}
    if result.get("error_code") in SAFE_ERRORS:
        errors.add(result["error_code"])
    if any(r.get("status") == "INVALID_OBSERVATION_RESPONSE" for r in rows):
        errors.add("INVALID_OBSERVATION_RESPONSE")
    value = {"phase": phase if phase in {"preparation", "observations"} else "unknown",
             "elapsed_seconds": round(elapsed, 3), "timeout": bool(timeout),
             "returncode": returncode if isinstance(returncode, int) else None,
             "completed_receipts": sum(r.get("status") == "COMPLETED" for r in rows),
             "error_codes": sorted(errors),
             "http_statuses": sorted({r["http_status"] for r in rows
                 if type(r.get("http_status")) is int and 100 <= r["http_status"] <= 599})}
    if result.get("error_type") in {"ValueError", "TimeoutError", "OSError", "KeyError", "TypeError"}:
        value["error_type"] = result["error_type"]
    if result.get("status") in {"PARTIAL_MODEL_RUN", "EXPERIMENT_STOPPED", "MODEL_ACCESS_DENIED",
                                 "MODEL_KEY_NOT_CONFIGURED", "MODEL_OBSERVATIONS_RETURNED"}:
        value["result_status"] = result["status"]
    return value
