from pathlib import Path

p = Path("backend/server.py")
s = p.read_text()

old_import = "import fix10a_shadow_runtime\n"
new_import = "import fix10a_runtime\nimport fix10b_runtime\n"
if new_import not in s:
    n = s.count(old_import)
    if n != 1:
        raise SystemExit(f"import replacement expected 1 occurrence, found {n}")
    s = s.replace(old_import, new_import, 1)

old = '''                    # FIX10A — observe-only physical reconstruction. Feature flag
                    # defaults OFF. The task writes only fix10a_* diagnostics and
                    # can never mutate canonical B3/FIX09C truth.
                    if fix10a_shadow_runtime.shadow_enabled():
                        fix10a_shadow_runtime.spawn_shadow(
                            report_id=report_id,
                            video_path=str(file_path),
                            unified_result=_unified_result,
                            db=db,
                            r2_storage=r2_storage,
                            source_video={
                                "role": "CANONICAL_WEB_VIDEO",
                                "fingerprint": doc.get("fingerprint") or {},
                            },
                            local_dir=UPLOAD_DIR / ".fix10a_traces",
                        )
'''
new = '''                    # FIX10A + FIX10B production path. Physical reconstruction
                    # is awaited here; there is no shadow/background task. FIX10A
                    # contributes physical evidence and FIX10B is the proof-gated
                    # canonical reconciliation authority.
                    try:
                        _fix10a_result = await fix10a_runtime.run(
                            report_id=report_id,
                            video_path=str(file_path),
                            unified_result=_unified_result,
                            db=db,
                            r2_storage=r2_storage,
                            source_video={
                                "role": "CANONICAL_WEB_VIDEO",
                                "fingerprint": doc.get("fingerprint") or {},
                            },
                            local_dir=UPLOAD_DIR / ".fix10a_traces",
                        )
                        _fix10b_candidate = (
                            (_fix10a_result or {}).get("_fix10b_candidate")
                            if isinstance(_fix10a_result, dict) else None
                        )
                        if (
                            isinstance(_fix10b_candidate, dict)
                            and _fix10b_candidate.get("enabled") is True
                            and isinstance(_fix10b_candidate.get("unified_result"), dict)
                        ):
                            _unified_result = _fix10b_candidate["unified_result"]
                            event_ledger_obj = _unified_result.get("event_ledger")
                            _fix10b_summary = dict(_fix10b_candidate.get("summary") or {})
                            _payload = unified_analysis_engine.persistence_payload(_unified_result)
                            _payload.update({
                                "fix10b_status": _fix10b_summary.get("status") or "no_change",
                                "fix10b_version": int(_fix10b_candidate.get("version") or 2),
                                "fix10b_mode": "production",
                                "fix10b_summary": _fix10b_summary,
                                "fix10b_canonical_authority": True,
                            })
                            await db.reports.update_one({"id": report_id}, {"$set": _payload})
                            logger.info(
                                "[fix10b] %s: production reconciliation status=%s applied=%d",
                                report_id,
                                _fix10b_summary.get("status"),
                                int(_fix10b_summary.get("proposals_applied") or 0),
                            )
                    except Exception:
                        logger.exception(
                            "[fix10] production physical reconciliation failed for %s; retaining FIX09B truth",
                            report_id,
                        )
'''
if new not in s:
    n = s.count(old)
    if n != 1:
        raise SystemExit(f"FIX10 block replacement expected 1 occurrence, found {n}")
    s = s.replace(old, new, 1)

leftovers = [
    x
    for x in (
        "fix10a_shadow_runtime",
        "FIX10A_SHADOW_ENABLED",
        "FIX10B_CANONICAL_ENABLED",
        "_fix10a_task",
    )
    if x in s
]
if leftovers:
    raise SystemExit(f"forbidden FIX10 shadow leftovers: {leftovers}")

p.write_text(s)
