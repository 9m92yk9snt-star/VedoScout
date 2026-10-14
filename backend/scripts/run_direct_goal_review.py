"""One isolated goal-contact review. Default is preflight; --run permits one paid call."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.direct_openai_goal_transport import DirectGoalChat, Payload


def load_bundle(path, directory):
    with zipfile.ZipFile(path) as z:
        if set(z.namelist()) != {'manifest.json', 'source.mp4', 'trace.json'}:
            raise ValueError('INVALID_TEST_BUNDLE_MEMBERS')
        if sum(r.file_size for r in z.infolist()) > 80_000_000:
            raise ValueError('TEST_BUNDLE_TOO_LARGE')
        manifest = json.loads(z.read('manifest.json'))
        for name in ('source.mp4', 'trace.json'):
            data = z.read(name)
            if hashlib.sha256(data).hexdigest() != manifest['sha256'][name]:
                raise ValueError('TEST_BUNDLE_HASH_MISMATCH')
            (directory / name).write_bytes(data)
    return manifest, json.loads((directory / 'trace.json').read_text())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--bundle', type=Path, required=True)
    parser.add_argument('--run', action='store_true')
    parser.add_argument('--output', type=Path, default=Path('direct-test-work/result.json'))
    args = parser.parse_args()
    key = os.getenv('OPENAI_API_KEY', '')
    with tempfile.TemporaryDirectory(prefix='scoutmeplay-direct-') as temporary:
        root = Path(temporary)
        manifest, document = load_bundle(args.bundle, root)
        os.environ['SCOUTMEPLAY_DIRECT_GOAL_TEST'] = '1'
        import cv2
        import ball_trajectory
        import dense_track_refinement
        import fix10a_vision_providers as vision
        import goal_review_sampling
        import shot_outcome_engine
        import fix10a_goal_direction
        import fix10a_ball_proof_gate
        cv2.setNumThreads(2)
        traces = document.get('traces', [])
        if len(traces) != 1:
            raise ValueError('TEST_REQUIRES_ONE_ORIGINAL_TRACE')
        trace = traces[0]
        candidates = [s for s in trace['strike_evidence'] if s.get('strike_id') == manifest['contact_strike_id']]
        if len(candidates) != 1:
            raise ValueError('ORIGINAL_CONTACT_NOT_FOUND')
        strike = candidates[0]
        touches = [r for r in trace['touch_graph']['touches'] if r.get('touch_id') == strike['touch_id']]
        if len(touches) != 1:
            raise ValueError('ORIGINAL_TOUCH_NOT_FOUND')
        qualified = ball_trajectory.qualify_produced_contact_seed(
            trace['decoded_frames'], touches[0],
            {**touches[0]['ball_after'], 'source': 'VERIFIED_CONTACT_ROLE_BALL_AFTER'}, strike['scene_id'])
        if qualified is None:
            raise ValueError('ORIGINAL_CONTACT_SEED_UNQUALIFIED')
        strike = {**strike, 'active_ball_anchor': qualified['anchor']}
        path = ball_trajectory.select_release_ball_trajectory(trace['decoded_frames'], qualified['anchor'],
            strike['scene_id'], trace['ball_trajectory'], anchor_required=True,
            contact_ball=touches[0]['ball_at_contact'], contact_required=True, max_duration_ms=420)
        if goal_review_sampling.contact_bound_native_path(strike, path) is None:
            raise ValueError('ORIGINAL_PATH_NOT_CONTACT_BOUND')
        detector = dense_track_refinement._default_detector()
        preflight = {'scope': 'SINGLE_ORIGINAL_CONTACT_NOT_FULL_FIVE_ACTION_ACCEPTANCE',
            'source_video_sha256': manifest['sha256']['source.mp4'],
            'contact_media_ms': strike['media_ms'], 'before_positions': len(path['rows']),
            'api_key_configured': bool(key), 'native_detector_available': bool(detector.ok),
            'mode': 'LIVE_DIRECT_IMAGE_REVIEW' if args.run else 'PREFLIGHT_NO_MODEL_CALLS'}
        print(json.dumps(preflight))
        if not args.run:
            return 0 if detector.ok and key else 2
        if not key:
            raise RuntimeError('OPENAI_API_KEY_NOT_CONFIGURED')
        if not detector.ok:
            raise RuntimeError('NATIVE_DETECTOR_NOT_AVAILABLE')
        # Only this process's supporting goal reader gets the direct transport.
        # No production file, database, primary story or stats count is changed.
        vision.LlmChat = DirectGoalChat
        vision.UserMessage = vision.ImageContent = Payload
        provider = vision.build_shadow_providers(key, 'isolated-direct-goal', str(root / 'source.mp4'))
        geometry = provider.goal_geometry_provider(trace['window'],
            goal_review_sampling.provider_strike({'strike': strike, 'shot_track': path}))
        outcome = shot_outcome_engine.reconstruct_post_strike_outcome(
            strike, path['rows'], trace['touch_graph'], goal_geometry=geometry, role_evidence={})
        outcome = fix10a_goal_direction.apply_direction_gate(outcome, path['rows'], geometry)
        outcome = fix10a_ball_proof_gate.apply_ball_proof_gate(outcome, path['rows'])
        passed = bool(outcome.get('physical_outcome') == 'GOAL_PLANE_CROSSING'
                      and (outcome.get('ball_proof_gate') or {}).get('status') == 'VERIFIED')
        receipt = {**preflight, 'goal_review_invocations': provider.goal_calls,
            'original_goal_proof_verified': passed, 'full_five_action_acceptance': False,
            'production_writes': 0, 'geometry': geometry, 'outcome': outcome}
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(receipt, indent=2))
        print(json.dumps({'original_goal_proof_verified': passed, 'result': str(args.output),
                          'goal_review_invocations': provider.goal_calls}))
        return 0 if passed else 3


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        # Safe error classes/codes only; no environment or request body dumps.
        code = str(exc) if str(exc).isupper() and len(str(exc)) < 100 else type(exc).__name__
        print(json.dumps({'status': 'BLOCKED_OR_ERROR', 'reason': code}), file=sys.stderr)
        raise SystemExit(2)
