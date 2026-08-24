"""FIX10A — open-world observation preservation helper.

The legacy FIX09B canonical action enum remains untouched for stats/B3
compatibility.  This helper preserves a bounded, sanitized copy of what the
perception model actually described so a novel football behaviour is not erased
merely because it has no canonical enum member yet.

Raw observations are evidence/context only.  They never become countable stats
or canonical events by existing.
"""
from __future__ import annotations

import re
from copy import deepcopy

VERSION = 1
MAX_RAW_KIND = 96
MAX_RAW_DESCRIPTION = 360
MAX_RAW_DETAILS = 12
MAX_RAW_DETAIL = 180

_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_SPACE = re.compile(r"\s+")


def _clean_text(value, limit: int) -> str | None:
    if value is None:
        return None
    text = str(value)
    text = _CONTROL.sub(" ", text)
    text = _SPACE.sub(" ", text).strip()
    if not text:
        return None
    return text[: max(1, int(limit))]


def sanitize_raw_kind(value) -> str | None:
    """Preserve model wording without letting arbitrary payloads grow unbounded."""
    return _clean_text(value, MAX_RAW_KIND)


def sanitize_raw_description(value) -> str | None:
    return _clean_text(value, MAX_RAW_DESCRIPTION)


def sanitize_raw_details(values) -> list[str]:
    rows = values if isinstance(values, (list, tuple)) else []
    out = []
    for value in rows:
        text = _clean_text(value, MAX_RAW_DETAIL)
        if text and text not in out:
            out.append(text)
        if len(out) >= MAX_RAW_DETAILS:
            break
    return out


def preserve_open_observation(raw_action: dict | None,
                              normalized_action: dict | None) -> dict:
    """Attach non-authoritative raw semantics to a normalized action copy.

    ``kind``/outcome/actor/timestamps in the normalized action remain exactly as
    decided by the existing FIX09B normalizer.  No raw field may overwrite an
    authoritative field.
    """
    raw = raw_action if isinstance(raw_action, dict) else {}
    out = deepcopy(normalized_action) if isinstance(normalized_action, dict) else {}
    model_kind = sanitize_raw_kind(raw.get("raw_kind") or raw.get("kind"))
    description = sanitize_raw_description(
        raw.get("raw_description")
        or raw.get("description")
        or raw.get("visible_description")
    )
    details = sanitize_raw_details(raw.get("details"))
    out["raw_kind"] = model_kind
    out["raw_description"] = description
    out["raw_details"] = details
    out["raw_observation_authority"] = "PERCEPTION_CONTEXT_ONLY"
    out["raw_countable_stat"] = False
    return out


def raw_observation_is_countable(action: dict | None) -> bool:
    """Explicit guard used by tests/future consumers."""
    return False
