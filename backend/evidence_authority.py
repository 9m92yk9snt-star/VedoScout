"""FIX 01 — EVENT / EVIDENCE AUTHORITY layer.

Deterministic, idempotent application logic (ZERO LLM calls) that gives newly
generated full reports stable object identity + explicit millisecond metadata
+ exact deterministic joins:

- authority_run_id            one namespace per produced analysis body
- evidence_authority_version  marker: "this report has authoritative IDs"
- action_timeline[]           event_id, event_start_ms, event_end_ms
- video_comments[]            evidence_id, evidence_time_ms, (event_id when
                              EXACTLY and unambiguously bindable)
- skill evidence rows         evidence_id / event_id (EXACT only)
- frames                      frame_time_ms (the ACTUAL frame moment — never
                              overwrites the cited moment)
- proof clips                 clip_id, clip_start_ms, clip_end_ms,
                              moment_local_ms

Presentation timestamps ("MM:SS") are kept untouched for UI/backward
compatibility. Legacy reports without the marker are never migrated at read
time. Binding is EXACT canonical milliseconds only — never nearest, never
guessing, never ambiguous.
"""
import re
import uuid
from typing import Optional

EVIDENCE_AUTHORITY_VERSION = 1

_TS_RE = re.compile(r"^\s*(?:(\d+):)?(\d{1,2}):(\d{2})(?:\.(\d{1,3}))?\s*$")


def ts_to_ms(ts) -> Optional[int]:
    """Canonical parse of a cited time to milliseconds.
    Accepts 'MM:SS', 'H:MM:SS', optional '.mmm', or numeric seconds."""
    if isinstance(ts, bool):
        return None
    if isinstance(ts, (int, float)):
        return int(round(float(ts) * 1000))
    if not isinstance(ts, str):
        return None
    m = _TS_RE.match(ts)
    if not m:
        return None
    h = int(m.group(1) or 0)
    mm = int(m.group(2))
    ss = int(m.group(3))
    frac = m.group(4)
    ms = int(frac.ljust(3, "0")) if frac else 0
    return ((h * 60 + mm) * 60 + ss) * 1000 + ms


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def frame_time_ms(frame_picked_ts, cited_seconds) -> Optional[int]:
    """Authoritative time of the ACTUAL frame used: the replacement/extracted
    frame moment when known, otherwise the cited extraction time. Never used
    to overwrite evidence_time_ms / event_start_ms."""
    src = frame_picked_ts if isinstance(frame_picked_ts, (int, float)) and not isinstance(frame_picked_ts, bool) else cited_seconds
    if isinstance(src, (int, float)) and not isinstance(src, bool):
        return int(round(float(src) * 1000))
    return None


def attach_event_evidence_authority(full: dict) -> dict:
    """Assign/preserve authority IDs and millisecond metadata on an analysis
    body. Idempotent: already-assigned IDs are preserved; dropping an entry
    never renumbers the rest. EXACT-only joins — zero candidates → unbound;
    multiple exact candidates → unbound (ambiguous). Never guesses."""
    if not isinstance(full, dict):
        return full
    if not full.get("authority_run_id"):
        full["authority_run_id"] = uuid.uuid4().hex[:12]
    full["evidence_authority_version"] = EVIDENCE_AUTHORITY_VERSION

    events = [e for e in (full.get("action_timeline") or []) if isinstance(e, dict)]
    for e in events:
        if not e.get("event_id"):
            e["event_id"] = _new_id("evt")
        if e.get("event_start_ms") is None:
            ms = ts_to_ms(e.get("timestamp"))
            if ms is not None:
                e["event_start_ms"] = ms
        if e.get("event_end_ms") is None and e.get("event_start_ms") is not None:
            # point-event schema: no real end exists — never invent duration
            e["event_end_ms"] = e["event_start_ms"]

    comments = [c for c in (full.get("video_comments") or []) if isinstance(c, dict)]
    for c in comments:
        if not c.get("evidence_id"):
            c["evidence_id"] = _new_id("evd")
        if c.get("evidence_time_ms") is None:
            ms = ts_to_ms(c.get("timestamp"))
            if ms is not None:
                c["evidence_time_ms"] = ms

    # EXACT event ↔ evidence binding (equal canonical ms, exactly one candidate)
    events_by_ms: dict = {}
    for e in events:
        ms = e.get("event_start_ms")
        if isinstance(ms, int):
            events_by_ms.setdefault(ms, []).append(e)
    for c in comments:
        if c.get("event_id"):
            continue  # preserve an existing binding
        ms = c.get("evidence_time_ms")
        cands = events_by_ms.get(ms) if isinstance(ms, int) else None
        if cands and len(cands) == 1:
            c["event_id"] = cands[0]["event_id"]
        elif cands and len(cands) > 1:
            c["event_binding_ambiguous"] = True

    # Sub-skill evidence + structured point-moment references — EXACT unique
    # mapping only; text and timestamps stay untouched; nothing is deleted here.
    evidence_by_ms: dict = {}
    for c in comments:
        ms = c.get("evidence_time_ms")
        if isinstance(ms, int):
            evidence_by_ms.setdefault(ms, []).append(c)

    def _bind_row(row) -> None:
        if not isinstance(row, dict):
            return
        ms = ts_to_ms(row.get("timestamp"))
        if ms is None:
            return
        if not row.get("evidence_id"):
            ec = evidence_by_ms.get(ms)
            if ec and len(ec) == 1:
                row["evidence_id"] = ec[0]["evidence_id"]
        if not row.get("event_id"):
            ev = events_by_ms.get(ms)
            if ev and len(ev) == 1:
                row["event_id"] = ev[0]["event_id"]

    for row in _iter_structured_rows(full):
        _bind_row(row)
    return full


def _iter_structured_rows(full: dict):
    """Every structured point-moment row that references report evidence:
    sub-skill evidence, snapshot moments, watch-together moments, grow-your-game
    lesson moments and the parent 'reaction after mistake' moment."""
    for cat in ("technical", "tactical", "physical", "mentality"):
        sec = full.get(cat)
        if not isinstance(sec, dict):
            continue
        for sk in sec.values():
            if not isinstance(sk, dict):
                continue
            for row in (sk.get("evidence") or []):
                yield row
    for row in (full.get("snapshot_moments") or []):
        yield row
    pp = full.get("parents_package")
    wt = pp.get("watch_together") if isinstance(pp, dict) else None
    if isinstance(wt, dict):
        for row in (wt.get("moments") or []):
            yield row
    gyg = full.get("grow_your_game")
    if isinstance(gyg, dict):
        for lesson in (gyg.get("lessons") or []):
            if isinstance(lesson, dict):
                for row in (lesson.get("moments") or []):
                    yield row
    pvm = full.get("parent_value_metrics")
    ram = pvm.get("reaction_after_mistake") if isinstance(pvm, dict) else None
    if isinstance(ram, dict):
        yield ram


def apply_fail_closed_proof_authority(full: dict) -> dict:
    """FIX 02 — deterministic fail-closed proof eligibility (zero LLM).

    Events: proof-verified only when the cross verifier fully confirmed them.
    Evidence: proof-verified only through an exact event_id bind to such an
    event. Structured rows inherit ONLY through exact FIX 01 authority IDs —
    never nearest, never semantic, never first-available."""
    if not isinstance(full, dict):
        return full
    verified_event_ids = set()
    for e in (full.get("action_timeline") or []):
        if not isinstance(e, dict):
            continue
        ok = e.get("cross_verified") is True
        e["proof_verified"] = ok
        if ok and e.get("event_id"):
            verified_event_ids.add(e["event_id"])
    verified_evidence_ids = set()
    for c in (full.get("video_comments") or []):
        if not isinstance(c, dict):
            continue
        ok = bool(c.get("event_id")) and c["event_id"] in verified_event_ids
        c["proof_verified"] = ok
        if ok and c.get("evidence_id"):
            verified_evidence_ids.add(c["evidence_id"])
    for row in _iter_structured_rows(full):
        if not isinstance(row, dict):
            continue
        row["proof_verified"] = (
            (bool(row.get("evidence_id")) and row["evidence_id"] in verified_evidence_ids)
            or (bool(row.get("event_id")) and row["event_id"] in verified_event_ids)
        )
    return full


def compute_proof_frame_verified(comment: dict) -> bool:
    """FIX 02 — a frame is exact proof only when the evidence passed the
    fail-closed proof gate, identity is positively verified (or user-tap
    ground truth), and the ACTUAL frame moment IS the cited moment.
    C01: anchor_locked is trusted IDENTITY ground truth ONLY — it never
    waives the exact-time requirement. A nearby replacement frame may stay
    as internal identity info — never exact proof."""
    if not isinstance(comment, dict) or comment.get("proof_verified") is not True:
        return False
    if not comment.get("frame_url") or comment.get("frame_placeholder"):
        return False
    if comment.get("identity_verified") is not True and comment.get("anchor_locked") is not True:
        return False
    et, ft = comment.get("evidence_time_ms"), comment.get("frame_time_ms")
    return isinstance(et, int) and isinstance(ft, int) and et == ft


def attach_clip_authority(comment: dict, clip_start_s, clip_end_s,
                          event_start_ms_by_id: Optional[dict] = None) -> None:
    """Attach clip authority metadata to the exact evidence row that generated
    the clip. Records reality only — clip timing/generation is unchanged.
    moment_local_ms comes from the AUTHORITATIVE cited moment (event-bound
    start when bound, else the evidence's own cited ms) — never a UI string."""
    if not isinstance(comment, dict) or not comment.get("evidence_id"):
        return  # authority reports only — legacy rows stay untouched
    if not isinstance(clip_start_s, (int, float)) or not isinstance(clip_end_s, (int, float)):
        return
    comment["clip_id"] = _new_id("clip")
    cs = int(round(float(clip_start_s) * 1000))
    ce = int(round(float(clip_end_s) * 1000))
    comment["clip_start_ms"] = cs
    comment["clip_end_ms"] = ce
    moment_ms = None
    eid = comment.get("event_id")
    if eid and isinstance((event_start_ms_by_id or {}).get(eid), int):
        moment_ms = event_start_ms_by_id[eid]
    elif isinstance(comment.get("evidence_time_ms"), int):
        moment_ms = comment["evidence_time_ms"]
    if moment_ms is not None:
        comment["moment_local_ms"] = moment_ms - cs
