"""Read-only presentation of the preview and full-report lifecycles.

No elapsed-time percentages or estimates: a heartbeat proves activity, and
only the persisted full-report body plus its ready state prove completion.
"""


def analysis_progress(doc: dict) -> dict:
    preview_status = doc.get("analysis_status") or "ready"  # pre-async documents
    full_status = doc.get("full_report_status") or ("ready" if doc.get("full_report") else None)
    has_full = bool(doc.get("full_report"))
    full_ready = has_full and full_status == "ready"
    preview_ready = preview_status == "ready" and bool(doc.get("preview"))
    target = "full" if doc.get("is_paid") or doc.get("manually_unlocked") else "preview"
    try:
        step = max(1, min(5, int(doc.get("progress_step") or (5 if preview_status == "ready" else 1))))
    except (ValueError, TypeError, OverflowError):
        step = 1

    if target == "full" and full_ready:
        phase = "ready"
    elif preview_status == "failed" or (target == "full" and full_status == "failed"):
        phase = "failed"
    elif target == "full" and full_status in ("awaiting_confirmation", "verifying", "finalizing"):
        phase = full_status
    elif target == "full" and full_status == "generating":
        phase = "queued" if doc.get("full_pipeline_stage") in (None, "queued", "full_start") else "analyzing"
    elif preview_ready:
        phase = "queued" if target == "full" else "preview_ready"
    elif step >= 4 and preview_status == "analyzing":
        phase = "initial_review"
    elif step == 3 and preview_status == "analyzing":
        phase = "checking_video"
    else:
        phase = "preparing"

    return {
        "analysis_status": preview_status,
        "progress_step": step,
        "analysis_target": target,
        "analysis_phase": phase,
        "analysis_complete": full_ready if target == "full" else preview_ready,
        "preview_ready": preview_ready,
        "full_report_status": full_status,
        "has_full_report": has_full,
        "full_report_ready": full_ready,
        "full_report_error": doc.get("full_report_error"),
        "analysis_error": doc.get("analysis_error"),
        "analysis_started_at": doc.get("created_at") or doc.get("full_report_started_at"),
        "full_report_started_at": doc.get("full_report_started_at"),
        "last_progress_at": doc.get("last_progress_at"),
        "full_pipeline_stage": doc.get("full_pipeline_stage"),
        "physical_windows_completed": doc.get("fix10a_completed_windows"),
        "retry_in_progress": bool(doc.get("retry_in_progress")),
        "taps_received": len(doc.get("anchors") or []),
    }
