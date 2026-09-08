"""READ-ONLY diagnostic: reproduce the FIX10A per-window IndexError locally.

- Uses the SAME canonical web video (downloaded from prod R2, read-only).
- Regenerates the dense scene_graph deterministically (LLM-free, 0 credit).
  The persisted scene_graph is compacted (dense_graph_persisted=False), so the
  per-frame players must be rebuilt to reproduce the failing windows.
- (A) Drives the REAL reconstruct_physical_match with window-selection patched
  to only the 4 production-failed windows -> confirms it records the identical
  WINDOW_RECONSTRUCTION_ERROR:IndexError signature seen in production.
- (B) Runs the identical per-window body with full traceback capture to pin the
  exact file:line + stage.

No Mongo writes, no report changes, no production calls, no LLM calls.
"""
import os
import sys
import traceback

sys.path.insert(0, "/app/backend")
for _line in open("/app/backend/.env"):
    _line = _line.strip()
    if _line and not _line.startswith("#") and "=" in _line:
        _k, _v = _line.split("=", 1)
        os.environ.setdefault(_k, _v.strip().strip('"'))

import dense_replay
import dense_track_refinement
import ball_trajectory
import ball_contact_engine
import short_occlusion_contact_recovery
import touch_graph
import contact_role_resolver
import jersey_consensus
import shot_outcome_engine
import post_strike_intervention
import fix10a_goal_direction
import fix10a_ball_proof_gate
import event_trace
import football_scene_graph
import physical_match_reconstruction as PMR

VIDEO = "/tmp/fix10a_diag/canonical.web.mp4"

# The 4 production-failed windows (from prod fix10a_physical_summary.windows).
FAILED = [
    ("dense_5ea1411c2b448489", 16002, 19199, "scene_001"),
    ("dense_f34b25b028cc8125", 25599, 33599, "scene_004"),
    ("dense_fdc29146178b6c05", 53065, 58931, "scene_007"),  # canonical GOAL ~57.2s
    ("dense_174c9ceb9e511e71", 67065, 75065, "scene_008"),
]


def build_graph():
    print("[build] regenerating dense scene_graph (deterministic, 0 credit)...", flush=True)
    sg = football_scene_graph.build_scene_graph(VIDEO, {})
    frames = sg.get("frames") or []
    print(f"[build] scene_graph status={sg.get('status')} frames={len(frames)} "
          f"compute_s={sg.get('compute_s')}", flush=True)
    bounds = {}
    for f in frames:
        s = str(f.get("scene_id") or "")
        ms = int(f.get("media_ms"))
        lo, hi = bounds.get(s, (10**12, -1))
        bounds[s] = (min(lo, ms), max(hi, ms))
    print("[build] scenes:", {k: bounds[k] for k in sorted(bounds)}, flush=True)
    return sg, bounds


def pick_scene(bounds, start, end, prod_scene):
    if prod_scene in bounds:
        return prod_scene
    best, best_ov = None, -1
    for s, (lo, hi) in bounds.items():
        ov = min(end, hi) - max(start, lo)
        if ov > best_ov:
            best_ov, best = ov, s
    return best


def run_real_reconstruct(sg, bounds):
    print("\n========== (A) REAL reconstruct_physical_match, windows patched to the 4 failed ==========", flush=True)
    windows = [{"dense_window_id": wid, "scene_id": pick_scene(bounds, s, e, ps),
                "start_ms": s, "end_ms": e} for (wid, s, e, ps) in FAILED]
    orig = dense_replay.select_critical_windows
    dense_replay.select_critical_windows = lambda plan, analysis: windows
    try:
        res = PMR.reconstruct_physical_match(
            VIDEO, {}, {"coverage_complete": True}, sg, {},
            None, source_video={}, goal_geometry_provider=None,
            role_evidence={}, role_evidence_provider=None,
        )
    finally:
        dense_replay.select_critical_windows = orig
    print("[A] status:", res.get("status"), flush=True)
    for row in res.get("windows") or []:
        print(f"[A] window {row.get('dense_window_id')} scene={row.get('scene_id')} "
              f"{row.get('start_ms')}-{row.get('end_ms')} -> status={row.get('status')} "
              f"reason={row.get('reason')}", flush=True)


def run_window_body(sg, bounds, wid, start, end, prod_scene):
    scene = pick_scene(bounds, start, end, prod_scene)
    print(f"\n----- (B) WINDOW {wid} {start}-{end} prod_scene={prod_scene} local_scene={scene} -----", flush=True)
    authority = {}
    graph = sg
    try:
        dense_iter = dense_replay.iter_dense_frames(VIDEO, start, end)
        refined = dense_track_refinement.refine_window(dense_iter, graph, authority, scene)
        dense_frames = list(refined.get("frames") or [])
        print(f"    dense_frames={len(dense_frames)}", flush=True)
        trajectory = ball_trajectory.reconstruct_ball_trajectory(dense_frames)
        candidates = ball_contact_engine.detect_contact_candidates(dense_frames, trajectory)
        contact_result = ball_contact_engine.resolve_contacts(candidates)
        step3 = short_occlusion_contact_recovery.recover_short_occlusion_contacts(
            dense_frames, trajectory, contact_result, video_path=VIDEO)
        contact_result = short_occlusion_contact_recovery.apply_recovered_contacts(contact_result, step3)
        touches = touch_graph.build_touch_graph(contact_result, authority, dense_frames)
        touches = contact_role_resolver.apply_contact_roles(touches, contact_result)
        requests = jersey_consensus.select_jersey_review_requests(dense_frames, touches)
        votes_by_track = {}
        jr = jersey_consensus.apply_jersey_consensus(dense_frames, touches, votes_by_track)
        dwj = jr.get("window_evidence") or dense_frames
        twj = jr.get("touch_graph") or touches
        strikes = shot_outcome_engine.find_strike_releases(twj, trajectory)
        a7 = [post_strike_intervention.detect_post_strike_intervention(s, dwj, trajectory) for s in strikes]
        window_roles = {}
        outcomes = []
        for s, a in zip(strikes, a7):
            o = shot_outcome_engine.reconstruct_post_strike_outcome(
                s, trajectory, twj, goal_geometry=None, role_evidence=window_roles)
            o = post_strike_intervention.apply_intervention_evidence(o, a, window_roles)
            o = fix10a_goal_direction.apply_direction_gate(o, trajectory, None)
            o = fix10a_ball_proof_gate.apply_ball_proof_gate(o, trajectory)
            outcomes.append(o)
        unresolved = PMR._window_unresolved_reasons(contact_result, jr, outcomes)
        trace = event_trace.build_event_trace(
            trace_id=wid, source_video={},
            window={"dense_window_id": wid, "scene_id": scene, "start_ms": start, "end_ms": end},
            dense_frames=dwj, ball_trajectory=trajectory, contact_result=contact_result,
            touch_graph=twj, jersey_consensus=jr, strike_evidence=strikes,
            outcome_evidence=outcomes, sequence_analysis={}, contradictions=[],
            unresolved_reasons=unresolved,
        )
        print(f"    NO CRASH: strikes={len(strikes)} touches={len(twj.get('touches') or [])} "
              f"contacts={len(contact_result.get('accepted') or [])}", flush=True)
    except Exception:
        print(f"    !!! EXCEPTION reproduced in window {wid}:", flush=True)
        traceback.print_exc()


if __name__ == "__main__":
    sg, bounds = build_graph()
    run_real_reconstruct(sg, bounds)
    print("\n========== (B) per-window body with traceback capture ==========", flush=True)
    for (wid, s, e, ps) in FAILED:
        run_window_body(sg, bounds, wid, s, e, ps)
    print("\n[done]", flush=True)
