"""Exact-request retry receipts and bounded, credential-free failure metadata."""
import hashlib
from pathlib import Path


def code_fingerprint():
    root = Path(__file__).parent
    paths = [root / name for name in (
        "sequence_pilot.py", "sequence_pilot_transport.py", "player_selection.py",
        "sequence_run_checkpoint.py", "sequence_report_runtime.py", "sequence_report_adapter.py",
        "sequence_foot_evidence.py", "sequence_action_evidence.py", "match_room.py",
        "sequence_report_selection.py", "sequence_deadline.py")]
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


def merge_retry_receipts(previous, current):
    """An unsuccessful attempt must not erase an intact completed response.

    Retention is not reuse: the runner still verifies the rebuilt request hash.
    A new completed response supersedes the old one for its packet ID.
    """
    by_id = {r["packet_id"]: r for r in previous}
    for row in current:
        prior = by_id.get(row["packet_id"])
        if prior and row.get("status") != "COMPLETED" and reusable_receipt(
                prior, {"payload_sha256": prior.get("payload_sha256")},
                provider=prior.get("provider"), model=prior.get("requested_model"),
                packet_id=row["packet_id"]):
            continue
        by_id[row["packet_id"]] = row
    return [by_id[k] for k in sorted(by_id)]


SAFE_ERRORS = frozenset({
    "MODEL_ACCESS_DENIED", "MODEL_KEY_NOT_CONFIGURED", "MODEL_QUOTA_OR_RATE_LIMIT",
    "MODEL_HTTP_ERROR", "MODEL_CONNECTION_FAILED", "MODEL_CALL_TIMEOUT", "MODEL_CHILD_EXITED",
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
    kinds = sorted({r["limit_kind"] for r in rows
                    if r.get("limit_kind") in {"QUOTA_EXHAUSTED", "RATE_LIMITED", "UNSPECIFIED"}})
    if kinds:
        value["limit_kinds"] = kinds
    if result.get("error_type") in {"ValueError", "TimeoutError", "OSError", "KeyError", "TypeError"}:
        value["error_type"] = result["error_type"]
    if result.get("status") in {"PARTIAL_MODEL_RUN", "EXPERIMENT_STOPPED", "MODEL_ACCESS_DENIED",
                                 "MODEL_KEY_NOT_CONFIGURED", "MODEL_OBSERVATIONS_RETURNED"}:
        value["result_status"] = result["status"]
    return value


# One bounded migration for raw receipts from the pre-split release. This only
# admits candidates; reusable_receipt still requires an identical full payload,
# intact response hash, provider/model/packet ID and current-parser validation.
_PRE_SPLIT_CODE = {'match_room.py': 'a3443e30891199a91a7dbc3d8c88cb8a7372a7507ed0c00334abf82ba294bf3d', 'player_selection.py': 'ea5f699ccd586fcf9f1e1f813eabb8ca2f389c5b80251fdb7e064f3d59e59f4d', 'run_sequence_pilot.py': '0d49574586cd5ad547563966a7f4a4f0a34842e3af120643363693fcd45d3a02', 'sequence_action_evidence.py': 'e922d414e6656b37fb4b3a8c9de88fc29218cab958b35228fadd761202d4876c', 'sequence_foot_evidence.py': 'ac9cf01076d82dd85e26ec3e3a574842a843c525cbb2b65b3fd96f3fed9c6186', 'sequence_pilot.py': '89bc18abdddeb83b2f8b9d89dd6c0a1f0e04712a31523eac074a9aa3c38cf01a', 'sequence_pilot_transport.py': '25b85d01426662f662e37c3bbe94888b2904e3683d4f961c157338e2a32a6cdf', 'sequence_report_adapter.py': '9719e53b65727fc6184b89fc6007fc8db51ae21d29a6a6903afc35e720befb6f', 'sequence_report_runtime.py': 'bc096796f7948bc9fa0834877da031b079129303f5f2e1807c4e1bcf647c9b81', 'sequence_run_checkpoint.py': 'd534250fda9b7b66a29664c185e423b171279205d3d5a50fb50aa5d7e30ad652'}


_PRE_RATE_LIMIT_CODE = {'match_room.py': 'a3443e30891199a91a7dbc3d8c88cb8a7372a7507ed0c00334abf82ba294bf3d', 'player_selection.py': 'ea5f699ccd586fcf9f1e1f813eabb8ca2f389c5b80251fdb7e064f3d59e59f4d', 'run_sequence_pilot.py': '52d64ec0e71803641fc833596b19d6485ac607333e6f97dc4831e2c6e3f87107', 'sequence_action_evidence.py': 'e922d414e6656b37fb4b3a8c9de88fc29218cab958b35228fadd761202d4876c', 'sequence_foot_evidence.py': 'ac9cf01076d82dd85e26ec3e3a574842a843c525cbb2b65b3fd96f3fed9c6186', 'sequence_pilot.py': '89bc18abdddeb83b2f8b9d89dd6c0a1f0e04712a31523eac074a9aa3c38cf01a', 'sequence_pilot_transport.py': '25b85d01426662f662e37c3bbe94888b2904e3683d4f961c157338e2a32a6cdf', 'sequence_report_adapter.py': '9719e53b65727fc6184b89fc6007fc8db51ae21d29a6a6903afc35e720befb6f', 'sequence_report_runtime.py': 'fa80d2a02d78ef7ba8f94bc2ae52927a6a568389e728213a466c35072762e103', 'sequence_run_checkpoint.py': '3bea039bb707fbdbec4c32b9f72438764770b9f0b1aa8ff7dd727459c8b82a8d'}


def retry_code_compatible(saved, current=None):
    current = code_fingerprint() if current is None else current
    if saved == current:
        return True
    changed = {"run_sequence_pilot.py", "sequence_report_runtime.py", "sequence_run_checkpoint.py"}
    changed.add("sequence_pilot_transport.py")
    return (saved in (_PRE_SPLIT_CODE, _PRE_RATE_LIMIT_CODE) and set(current) == set(saved)
            and all(current[k] == saved[k] for k in saved if k not in changed))
