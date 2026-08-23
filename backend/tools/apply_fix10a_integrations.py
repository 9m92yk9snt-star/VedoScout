"""One-shot FIX10A branch patcher.

Guarded string edits are used only because the connected GitHub contents API
supports complete-file replacement but not patch application.  Every anchor
must occur exactly once or the script aborts without writing either target.
Delete this helper after the integration commit is verified.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FSI = ROOT / "football_sequence_intelligence.py"
SERVER = ROOT / "server.py"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one anchor, found {count}")
    return text.replace(old, new, 1)


def patch_fsi(text: str) -> str:
    text = replace_once(
        text,
        "import math\nfrom copy import deepcopy\n",
        "import math\nfrom copy import deepcopy\n\nimport open_observation_compat\n",
        "fsi-import",
    )
    text = replace_once(
        text,
        "- Record micro-actions separately when they are genuinely visible. Do not collapse receive → turn → feint → acceleration → shot into one generic label.\n",
        "- Record micro-actions separately when they are genuinely visible. Do not collapse receive → turn → feint → acceleration → shot into one generic label.\n"
        "- Open-world perception: if a visible football behaviour does not fit the canonical kind enum, set kind=OTHER but preserve a concise free-form raw_kind and raw_description. Never discard a visible behaviour merely because the enum has no exact label.\n",
        "fsi-open-world-rule",
    )
    text = replace_once(
        text,
        '          "kind": "RECEIVE|FIRST_TOUCH|CONTROL|CARRY|DRIBBLE|TAKE_ON|FEINT|TURN|DIRECTION_CHANGE|ACCELERATION|DECELERATION|PASS|CROSS|KEY_PASS|SHOT|DUEL|TACKLE|INTERCEPTION|RECOVERY|PRESS|RUN|OFF_BALL_RUN|SPACE_CREATION|SCAN|BODY_ORIENTATION|SUPPORT|OTHER",\n          "start_ms": 0,\n',
        '          "kind": "RECEIVE|FIRST_TOUCH|CONTROL|CARRY|DRIBBLE|TAKE_ON|FEINT|TURN|DIRECTION_CHANGE|ACCELERATION|DECELERATION|PASS|CROSS|KEY_PASS|SHOT|DUEL|TACKLE|INTERCEPTION|RECOVERY|PRESS|RUN|OFF_BALL_RUN|SPACE_CREATION|SCAN|BODY_ORIENTATION|SUPPORT|OTHER",\n          "raw_kind": "concise free-form visible football action label; may be outside canonical enum",\n          "raw_description": "concise factual visible behaviour/context; no inference",\n          "start_ms": 0,\n',
        "fsi-schema",
    )
    text = replace_once(
        text,
        '    return {\n        "action_id": str(a.get("action_id") or "")[:80] or None,\n        "kind": kind,\n',
        '    normalised = {\n        "action_id": str(a.get("action_id") or "")[:80] or None,\n        "kind": kind,\n',
        "fsi-normalised-start",
    )
    text = replace_once(
        text,
        '        "duplicate_of": str(a.get("duplicate_of"))[:80] if a.get("duplicate_of") else None,\n    }\n\n\ndef normalise_sequence_analysis(raw, plan: dict) -> dict:\n',
        '        "duplicate_of": str(a.get("duplicate_of"))[:80] if a.get("duplicate_of") else None,\n    }\n    return open_observation_compat.preserve_open_observation(a, normalised)\n\n\ndef normalise_sequence_analysis(raw, plan: dict) -> dict:\n',
        "fsi-normalised-return",
    )
    return text


def patch_server(text: str) -> str:
    text = replace_once(
        text,
        "import r2_storage\nimport video_timebase\n",
        "import r2_storage\nimport video_timebase\nimport fix10a_shadow_runtime\n",
        "server-import",
    )
    anchor = '''                    logger.info(\n                        f"[fix09b] {report_id}: canonical events="\n                        f"{_unified_result.get('metrics', {}).get('events_accepted')} "\n                        f"unresolved={_unified_result.get('metrics', {}).get('events_unresolved')} "\n                        f"coverage_complete={_unified_result.get('metrics', {}).get('coverage_complete')} "\n                        f"attempts={len(_sequence_attempts)}"\n                    )\n                else:\n'''
    replacement = '''                    logger.info(\n                        f"[fix09b] {report_id}: canonical events="\n                        f"{_unified_result.get('metrics', {}).get('events_accepted')} "\n                        f"unresolved={_unified_result.get('metrics', {}).get('events_unresolved')} "\n                        f"coverage_complete={_unified_result.get('metrics', {}).get('coverage_complete')} "\n                        f"attempts={len(_sequence_attempts)}"\n                    )\n                    # FIX10A — observe-only physical reconstruction. Feature flag\n                    # defaults OFF. The task writes only fix10a_* diagnostics and\n                    # can never mutate canonical B3/FIX09C truth.\n                    if fix10a_shadow_runtime.shadow_enabled():\n                        asyncio.create_task(fix10a_shadow_runtime.run_shadow(\n                            report_id=report_id,\n                            video_path=str(file_path),\n                            unified_result=_unified_result,\n                            db=db,\n                            r2_storage=r2_storage,\n                            source_video={\n                                "role": "CANONICAL_WEB_VIDEO",\n                                "fingerprint": doc.get("fingerprint") or {},\n                            },\n                            local_dir=UPLOAD_DIR / ".fix10a_traces",\n                        ))\n                else:\n'''
    text = replace_once(text, anchor, replacement, "server-shadow-call")
    return text


def main() -> None:
    original_fsi = FSI.read_text(encoding="utf-8")
    original_server = SERVER.read_text(encoding="utf-8")
    new_fsi = patch_fsi(original_fsi)
    new_server = patch_server(original_server)
    if new_fsi == original_fsi or new_server == original_server:
        raise RuntimeError("guard: expected both files to change")
    # Only write after BOTH complete transformations validated successfully.
    FSI.write_text(new_fsi, encoding="utf-8")
    SERVER.write_text(new_server, encoding="utf-8")
    print("FIX10A integration patch applied: football_sequence_intelligence.py + server.py")


if __name__ == "__main__":
    main()
