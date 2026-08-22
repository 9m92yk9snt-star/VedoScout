#!/usr/bin/env python3
"""Scratch-only patcher for FIX09B/FIX09C production integration.

Runs on a disposable integration branch. It edits backend/server.py using
asserted anchors so we never silently patch the wrong place in the large file.
The resulting server.py is later audited and copied to the real FIX09B branch;
this script itself is not intended for the final PR.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SERVER = ROOT / "server.py"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly 1 literal match, found {count}")
    return text.replace(old, new, 1)


def regex_once(text: str, pattern: str, repl: str, label: str) -> str:
    out, count = re.subn(pattern, repl, text, count=1, flags=re.S)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly 1 regex match, found {count}")
    return out


def main() -> None:
    text = SERVER.read_text(encoding="utf-8")
    original = text

    text = replace_once(
        text,
        "import event_ledger\nimport player_identity_timeline\n",
        "import event_ledger\nimport player_identity_timeline\nimport unified_analysis_engine\n",
        "import unified_analysis_engine",
    )

    # Replace the old observe-only FIX09A + FIX08 discovery block with the
    # unified B.0→B.3 preparation/call, while keeping a bounded legacy fallback
    # only when the new engine cannot prepare or execute.
    unified_block = r'''        # ── FIX 09A / FIX 09B — ONE GLOBAL_TARGET production spine.
        # FIX09A remains the scene-aware identity evidence source. FIX09B now
        # fuses it with FIX04, builds the all-player/ball graph, constructs the
        # sequence plan and makes ONE whole-video sequence-intelligence call.
        _idtl = {}
        _unified_prepared = None
        _unified_result = None
        if player_identity_timeline.TIMELINE_ENABLED and valid_anchors:
            try:
                _idtl = await asyncio.to_thread(
                    player_identity_timeline.build_identity_timeline,
                    str(file_path),
                    {"anchors": valid_anchors, "anchor_time_offset": gt_t_off},
                )
                _idtl_cmp = player_identity_timeline.compare_with_production(_idtl, gt_track)
                await db.reports.update_one(
                    {"id": report_id},
                    {"$set": {"identity_timeline": _idtl,
                              "identity_timeline_compare": _idtl_cmp}},
                )
                logger.info(
                    f"[fix09a] {report_id}: status={_idtl.get('status')} "
                    f"scenes={len(_idtl.get('scenes') or [])} "
                    f"points={len(_idtl.get('target_points') or [])} "
                    f"agreement={_idtl_cmp.get('agreement_rate')}"
                )
            except Exception:
                logger.exception(f"[fix09a] identity timeline failed for {report_id}")
                _idtl = {}

        try:
            if valid_anchors and isinstance(_idtl, dict) and _idtl.get("status") == "ok":
                _unified_prepared = await asyncio.to_thread(
                    unified_analysis_engine.prepare_analysis,
                    video_path=str(file_path),
                    fix04_track=gt_track or {},
                    identity_timeline=_idtl,
                    anchors=valid_anchors,
                    anchor_time_offset=gt_t_off,
                    identity_profile=doc.get("identity_profile") or {},
                    player_details=doc.get("player_details") or {},
                )
                logger.info(
                    f"[fix09b] {report_id}: prepared status={_unified_prepared.get('status')} "
                    f"identity_points={_unified_prepared.get('metrics', {}).get('identity_points')} "
                    f"scene_frames={_unified_prepared.get('metrics', {}).get('scene_graph_frames')} "
                    f"sequence_windows={_unified_prepared.get('metrics', {}).get('sequence_windows')}"
                )
        except Exception:
            logger.exception(f"[fix09b] unified preparation failed for {report_id}")
            _unified_prepared = None

        event_ledger_obj = None
        if isinstance(_unified_prepared, dict) and _unified_prepared.get("status") == "prepared":
            try:
                sequence_prompt = str(_unified_prepared.get("analysis_prompt") or "")
                try:
                    _idp = doc.get("identity_profile")
                    if _idp:
                        sequence_prompt += identity_profile_block(_idp)
                except Exception:
                    pass
                try:
                    _gtb = _ground_truth_positions_block(anchor_payload_list, gt_track, gt_t_off)
                    if _gtb:
                        sequence_prompt += _gtb
                except Exception:
                    pass
                sequence_raw = await call_gemini_with_video(
                    session_id=f"sequence-{report_id}",
                    prompt=sequence_prompt,
                    video_path=str(file_path),
                    marker_path=marker_path,
                    crop_path=crop_path_str,
                    anchor_crops=anchor_crops_full if anchor_crops_full else None,
                    timeout_s=420.0,
                )
                _unified_result = unified_analysis_engine.finalise_analysis(
                    sequence_raw, _unified_prepared)
                event_ledger_obj = _unified_result.get("event_ledger")
                _payload = unified_analysis_engine.persistence_payload(_unified_result)
                _payload["football_sequence_raw"] = sequence_raw
                # Compatibility name for existing admin/debug tooling. This raw
                # payload is no longer FIX08's isolated event schema.
                _payload["event_discovery_raw"] = sequence_raw
                await db.reports.update_one({"id": report_id}, {"$set": _payload})
                logger.info(
                    f"[fix09b] {report_id}: canonical events="
                    f"{_unified_result.get('metrics', {}).get('events_accepted')} "
                    f"unresolved={_unified_result.get('metrics', {}).get('events_unresolved')} "
                    f"coverage_complete={_unified_result.get('metrics', {}).get('coverage_complete')}"
                )
            except Exception:
                logger.exception(f"[fix09b] unified sequence analysis failed for {report_id}")
                _unified_result = None
                event_ledger_obj = None

        # Migration fallback only: if the new production spine could not run at
        # all, preserve the already-shipped FIX08 safety path instead of
        # fabricating an empty report. Successful FIX09B runs never use FIX04 as
        # the final event authority.
        if _unified_result is None:
            try:
                _disc_dur = await asyncio.to_thread(_video_duration_seconds, file_path)
                disc_prompt = event_ledger.build_discovery_prompt(
                    _disc_dur, doc.get("player_details") or {})
                try:
                    _idp = doc.get("identity_profile")
                    if _idp:
                        disc_prompt += identity_profile_block(_idp)
                except Exception:
                    pass
                try:
                    _gtb = _ground_truth_positions_block(anchor_payload_list, gt_track, gt_t_off)
                    if _gtb:
                        disc_prompt += _gtb
                except Exception:
                    pass
                discovery = await call_gemini_with_video(
                    session_id=f"discover-{report_id}",
                    prompt=disc_prompt,
                    video_path=str(file_path),
                    marker_path=marker_path,
                    crop_path=crop_path_str,
                    anchor_crops=anchor_crops_full if anchor_crops_full else None,
                    timeout_s=420.0,
                )
                event_ledger_obj = event_ledger.build_ledger(discovery, gt_track, _disc_dur)
                await db.reports.update_one(
                    {"id": report_id},
                    {"$set": {"event_discovery_raw": discovery,
                              "event_ledger": event_ledger_obj,
                              "unified_analysis_status": "legacy_fallback"}},
                )
                logger.warning(
                    f"[fix09b] {report_id}: LEGACY FIX08 fallback "
                    f"{event_ledger_obj.get('candidates_verified')}/"
                    f"{event_ledger_obj.get('candidates_total')} verified"
                )
            except Exception:
                logger.exception(f"[fix08] fallback event discovery failed for {report_id}")
                event_ledger_obj = None

        # ── CV SHADOW MODE'''
    text = regex_once(
        text,
        r'        # ── FIX 09A — GLOBAL TARGET IDENTITY TIMELINE \(synchronous, observe-only\)\..*?        # ── CV SHADOW MODE',
        unified_block,
        "replace FIX09A/FIX08 production block",
    )

    # The full prose model is no longer allowed to own the event list. On a
    # successful FIX09B run, B.3/C projection replaces it. Legacy reports keep
    # the old FIX08 projection.
    post_full_block = '''        full = scrub_hedging(full)\n        _analysis_track = gt_track\n        if isinstance(_unified_result, dict):\n            full = unified_analysis_engine.apply_result_to_report(full, _unified_result)\n            _analysis_track = (\n                _unified_result.get("event_track")\n                or _unified_result.get("production_track")\n                or gt_track\n            )\n        else:\n            # Legacy fallback: only the validated FIX08 ledger may populate the timeline.\n            full["action_timeline"] = event_ledger.authoritative_timeline(event_ledger_obj)\n            full["event_discovery"] = event_ledger.discovery_summary(event_ledger_obj)\n        _apply_tracking_verification(full, anchor_payload_list, _analysis_track, gt_t_off)\n        # GROW YOUR GAME'''
    text = regex_once(
        text,
        r'        full = scrub_hedging\(full\)\n        # FIX 08 C06 —.*?        _apply_tracking_verification\(full, anchor_payload_list, gt_track, gt_t_off\)\n        # GROW YOUR GAME',
        post_full_block,
        "replace full-report event authority projection",
    )

    # Existing second verifier becomes legacy-only. FIX09B B.3 is already the
    # deterministic actor/causal verifier over the sequence model + scene graph;
    # letting the legacy scan add/promote events would recreate two authorities.
    verify_block = '''        # INTELLIGENT verification / canonical authority.\n        # A successful FIX09B run already passed deterministic B.3 actor + causal\n        # resolution, so the legacy verifier is NOT allowed to rediscover or\n        # promote events. Legacy fallback keeps the shipped verifier unchanged.\n        await db.reports.update_one(\n            {"id": report_id},\n            {"$set": {"full_report_status": "verifying"}},\n        )\n        if isinstance(_unified_result, dict):\n            full["cross_verification"] = {\n                "status": "canonical_authority",\n                "reason": "FIX09B.3 deterministic actor + causal resolution",\n                "events_checked": len(full.get("action_timeline") or []),\n                "events_dropped": 0,\n                "verified_at": now_iso(),\n            }\n            full["_scoring_scan"] = dict(_unified_result.get("scoring_scan") or {})\n        else:\n            await _cross_verify_full_report(\n                report_id, full,\n                file_path=file_path, marker_path=marker_path, crop_path_str=crop_path_str,\n                anchor_crops=anchor_crops_full, anchor_payload_list=anchor_payload_list,\n                gt_track=gt_track, gt_t_off=gt_t_off, doc=doc,\n            )\n        # FIX 01 — attach the event/evidence authority layer'''
    text = regex_once(
        text,
        r'        # INTELLIGENT DUAL-PASS — independent verification of every claim.*?        # FIX 01 — attach the event/evidence authority layer',
        verify_block,
        "make legacy cross verifier fallback-only",
    )

    text = replace_once(
        text,
        '        full = event_ledger.create_event_native_evidence(full, track=gt_track)\n',
        '        if _unified_result is None:\n            full = event_ledger.create_event_native_evidence(full, track=gt_track)\n',
        "avoid legacy event evidence on canonical run",
    )

    # Corrective prose regeneration must retain the same canonical events. It is
    # not allowed to project the compatibility ledger back into a second truth
    # or run the legacy scoring rediscovery pass.
    corrective_block = '''        _lg = fresh.get("event_ledger")\n        _canonical = fresh.get("canonical_events")\n        if isinstance(_canonical, dict):\n            retry = unified_analysis_engine.apply_result_to_report(\n                retry,\n                {\n                    "canonical_events": _canonical,\n                    "sequence_analysis": fresh.get("football_sequence_analysis") or {},\n                },\n            )\n            _corr_track = (\n                fresh.get("unified_event_track")\n                or fresh.get("unified_production_track")\n                or gt_track\n            )\n            _apply_tracking_verification(retry, anchor_payload_list, _corr_track, gt_t_off)\n            retry["cross_verification"] = {\n                "status": "canonical_authority",\n                "reason": "FIX09B canonical events retained during corrective prose regeneration",\n                "events_checked": len(retry.get("action_timeline") or []),\n                "events_dropped": 0,\n                "verified_at": now_iso(),\n            }\n            retry["_scoring_scan"] = {\n                "performed": bool((fresh.get("football_sequence_analysis") or {}).get("coverage_complete")),\n                "authority": "FIX09B_CANONICAL_EVENTS",\n                "unresolved_goal_attempts": 0,\n                "unresolved_assist_candidates": 0,\n            }\n        else:\n            retry["action_timeline"] = event_ledger.authoritative_timeline(_lg)\n            retry["event_discovery"] = event_ledger.discovery_summary(_lg)\n            _apply_tracking_verification(retry, anchor_payload_list, gt_track, gt_t_off)\n            await _cross_verify_full_report(\n                report_id, retry,\n                file_path=file_path, marker_path=marker_path, crop_path_str=crop_path_str,\n                anchor_crops=(anchor_crops_full + wide_crops_full) or None,\n                anchor_payload_list=anchor_payload_list,\n                gt_track=gt_track, gt_t_off=gt_t_off, doc=doc,\n            )\n        # FIX 01 — the corrective replacement'''
    text = regex_once(
        text,
        r'        _lg = fresh.get\("event_ledger"\).*?        # FIX 01 — the corrective replacement',
        corrective_block,
        "retain canonical authority in corrective pass",
    )

    # Proof clips/rendering follow the canonical GLOBAL_TARGET track when a
    # unified report provides it; the legacy tap track is only a compatibility
    # fallback for old reports.
    text = replace_once(
        text,
        '    track_pts = ((doc.get("player_track") or {}).get("points")) or []\n',
        '    _unified_pts = ((doc.get("unified_production_track") or {}).get("points")) or []\n'
        '    track_pts = _unified_pts or ((doc.get("player_track") or {}).get("points")) or []\n',
        "prefer unified proof/render track",
    )

    if text == original:
        raise RuntimeError("no changes produced")
    SERVER.write_text(text, encoding="utf-8")
    print("FIX09B/FIX09C production integration patch applied")


if __name__ == "__main__":
    main()
