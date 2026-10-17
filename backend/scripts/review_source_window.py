"""Review one existing source window with its original taps; no upload or DB.

Default: prepare the exact production video input, with no model call.
--run-model: use one production action reader and the shared identity/resolver.
No expected event types, player numbers or reference contact times are inputs.
This focused review is not a full-report latency measurement.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import json
import os
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def review(export_dir, video_path, trace_id, output_dir, *, run_model=False, api_key=None):
    import action_evidence_review as inspection
    import canonical_event_resolver as resolver
    import dense_event_reconciliation as reconciliation
    import dense_identity_continuity as identity
    import dense_track_refinement as refinement
    import fix10a_vision_providers as vision
    import sequence_observation_context as context
    import unified_identity_authority as authority
    import video_model_input as video

    started = time.monotonic()
    root, output = Path(export_dir), Path(output_dir)
    digest = video.sha256(video_path)
    selected = [t for p in sorted((root/"traces").glob("*.json"))
                if (t := json.loads(p.read_text())).get("trace_id") == trace_id]
    if len(selected) != 1:
        raise ValueError("SOURCE_WINDOW_NOT_UNIQUE")
    trace = deepcopy(selected[0])
    if (trace.get("source_video") or {}).get("sha256") != digest:
        raise ValueError("SOURCE_VIDEO_DOES_NOT_MATCH_TRACE")
    if output.exists() and any(output.iterdir()):
        raise ValueError("USE_NEW_EMPTY_OUTPUT_DIRECTORY")
    if run_model and not api_key:
        raise ValueError("MODEL_KEY_NOT_CONFIGURED")
    output.mkdir(parents=True, exist_ok=True)
    report = json.loads((root/"report.json").read_text())
    anchors = json.loads((root/"anchors.json").read_text())
    scenes = (report.get("football_scene_graph") or {}).get("scenes") or []
    points = [{**row, "primary_source": "USER_TAP", "tap_authority": True,
               "proof_eligible": not row.get("partial")}
              for row in authority._tap_rows(anchors.get("anchors"), anchors.get("anchor_time_offset"), scenes)]
    bundle = vision.build_shadow_providers(api_key, "source-window-review", str(video_path))
    bundle.bind_selected_reference({"target_points": points})
    reference = bundle._reference_for_window(trace["window"])
    if not reference or reference.get("source_video_sha256") != digest:
        raise ValueError("ORIGINAL_SELECTED_SOURCE_PIXELS_UNAVAILABLE")
    summary = {"mode": "FRESH_SOURCE_WINDOW_REVIEW" if run_model else "SOURCE_INPUT_PREPARATION_ONLY",
        "source_video_sha256": digest, "trace_id": trace_id, "window": trace["window"],
        "reference_source": reference["source"], "reference_sha256": reference["input_sha256"],
        "reference_source_ms": reference["evidence_ms"], "new_model_calls": 0,
        "full_report_latency_measured": False, "fresh_model_response_recorded": False,
        "qualified_saved_shot_count": 0}
    if not run_model:
        from scripts.audit_temporal_video_inputs import audit
        summary["input_audit"] = audit(root, video_path, output/"input", [trace_id])
    else:
        frames, window = trace["decoded_frames"], trace["window"]
        job = {**window, "inspection_id": "source_window_"+trace_id, "selected": True,
               "selection_rank": 0, "has_contact_time": False, "source_action_ids": []}
        job["center_ms"] = (window["start_ms"]+window["end_ms"])//2
        job["sequence_context"] = context.build(window, frames, trace=trace, source_video=trace["source_video"])
        observation = bundle.action_evidence_provider(str(video_path), job, deepcopy(frames))
        applied = inspection.apply_observations(frames, observation, job["inspection_id"])
        frames = applied["frames"]
        if observation.get("target_observations"):
            identified = identity.apply_reference_matches(frames, observation)
            if any((new.get("global_target") or {}).get("proof_eligible") is True
                   and (old.get("global_target") or {}).get("proof_eligible") is not True
                   for old, new in zip(frames, identified)):
                frames = identity.apply(identified)["frames"]
                refinement._apply_dense_team_labels(frames)
        # Keep the older model responses out of this fresh observation result.
        trace.update(decoded_frames=frames, action_inspections=[{**job, **observation}])
        resolved = reconciliation.resolve_motion_observations(trace)
        qualified = [e for e in resolved.get("events") or [] if resolver.has_motion_proof(e)]
        summary.update(new_model_calls=bundle.inspection_calls, model=observation.get("model"),
            observation_status=observation.get("status"),
            fresh_model_response_recorded=bool(observation.get("input_sha256") and observation.get("response_sha256")),
            qualified_saved_shot_count=sum(e.get("canonical_event_type") == "SHOT"
                and e.get("canonical_outcome") == "SAVED" for e in qualified), qualified_events=qualified,
            unresolved=resolved.get("unresolved") or [], rejected=resolved.get("rejected") or [],
            requested_searches=(observation.get("sequence_reasoning") or {}).get("review_requests") or [])
        (output/"fresh_observation.json").write_text(json.dumps(observation, indent=2)+"\n")
        (output/"fresh_trace.json").write_text(json.dumps(trace, indent=2)+"\n")
    summary["elapsed_seconds"] = round(time.monotonic()-started, 3)
    (output/"review_summary.json").write_text(json.dumps(summary, indent=2)+"\n")
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("export_dir", type=Path)
    parser.add_argument("video_path", type=Path)
    parser.add_argument("trace_id")
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--run-model", action="store_true")
    parser.add_argument("--key-env", default="EMERGENT_LLM_KEY")
    args = parser.parse_args()
    os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")
    if args.run_model:
        from dotenv import load_dotenv
        load_dotenv(Path(__file__).resolve().parents[1]/".env")
    else:
        import socket
        def blocked(*_args, **_kwargs):
            raise RuntimeError("SOURCE_INPUT_PREPARATION_CANNOT_ACCESS_NETWORK")
        socket.socket.connect = socket.create_connection = blocked
    result = review(args.export_dir, args.video_path, args.trace_id, args.output_dir,
                    run_model=args.run_model, api_key=os.environ.get(args.key_env) if args.run_model else None)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
