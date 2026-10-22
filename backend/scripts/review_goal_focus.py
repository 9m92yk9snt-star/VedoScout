"""Isolated single-call source review. Never publishes or changes a report."""
import argparse
import base64
import gzip
import hashlib
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import sequence_pilot as p
import sequence_pilot_transport as transport


def main():
    cli = argparse.ArgumentParser()
    cli.add_argument('--bundle', required=True)
    cli.add_argument('--output', required=True)
    cli.add_argument('--run-model', action='store_true')
    args = cli.parse_args()
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=False)
    encoded = Path(args.bundle).read_text().strip()
    bundle = json.loads(gzip.decompress(base64.b64decode(encoded, validate=True)))
    items = []
    for index, part in enumerate(bundle['items']):
        if part['type'] == 'text':
            items.append(part)
            continue
        data = base64.b64decode(part['data'], validate=True)
        if hashlib.sha256(data).hexdigest() != part['sha256']:
            raise ValueError('IMAGE_HASH_MISMATCH')
        path = out / 'images' / f'{index:04}.jpg'
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(data)
        items.append({'type': 'image', 'path': str(path), 'sha256': part['sha256']})
    focus_instruction = "GOAL-ATTRIBUTION REVIEW PRIORITY. Independently assess the selected player's attack and the active ball's visible goal outcome. The sole evaluation priority is whether a selected-player GOAL is supported; do not spend this review resolving anatomical foot. There is no expected scorer or required answer. Keep the supplied plays/actions/people/questions JSON contract. Evaluate separately (1) the releasing actor from the approach, body/limb motion and ball departure, (2) continuity of that active ball into the goal, (3) any goalkeeper or defender intervention and its visible effect. Follow the sequence before and after each occlusion. Distinguish an observed touch from a hypothetical possible touch, and a failed clearance from controlled opponent possession or a decisive redirection. An exact boot-ball frame, unknown striking foot, keeper movement, or brief occlusion alone neither proves nor disproves attribution. If a later touch is unclear, assess whether the existing images establish the ball was already travelling into the goal before it; do not assume every possible brush changes the scorer, and do not assume an obscured intervention is harmless. Return GOAL and contact_actor_unique=true only if the source sequence supports them; otherwise retain the specific uncertainty. Add a top-level goal_review object containing releasing_actor, actor_assessment (SUPPORTED/UNCERTAIN), ball_in_goal_assessment (SUPPORTED/UNCERTAIN), intervention_assessment, attribution_assessment (SUPPORTED/UNCERTAIN), and evidence arrays of {frame,fact} for release, ball path and any intervention. Explain the strongest competing attribution and which supplied frames exclude it or why it remains unresolved. Do not invent a contact or goal-line crossing time. No earlier model answer, user scorer label or desired result is supplied."
    items.append({'type': 'text', 'text': focus_instruction})
    job = {'packet_id': 'orman600_goal_focus', 'items': items,
           'reasoning_effort': 'medium', 'image_detail': 'high', 'max_output_tokens': 12288}
    _, _, audit = transport.build_request('emergent', 'gpt-6-astra', items,
        reasoning_effort='medium', image_detail='high', max_output_tokens=12288)
    result = {**bundle['provenance'], 'bundle_sha256': p.digest(args.bundle),
              'goal_focus_instruction': focus_instruction,
              'comparison': 'PR50 image bytes, order and base prompt unchanged; one appended focus instruction',
              'request_audit': audit, 'status': 'PREFLIGHT_ONLY', 'model_calls': 0,
              'production_changed': False, 'independently_verified': False}
    p.write_json(out / 'result.json', result)
    if args.run_model:
        # One request only: the remaining wall budget cannot accommodate a retry.
        receipt = transport.run_jobs([job], 'emergent', 'gpt-6-astra',
            deadline=time.monotonic()+211, per_call_s=210, workers=1)[0]
        result.update(receipt=receipt, model_calls=1, status=receipt['status'])
        p.write_json(out / 'result.json', result)
        if receipt['status'] == 'COMPLETED':
            try:
                raw = p.parse_response(receipt['raw_response'])
                # Preserve raw observations; validation is not visual proof.
                result['observations'] = raw
                manifest = bundle['manifest']
                result['resolved'] = p.reconcile([p.resolve_response(raw, manifest, bundle['packet'],
                    {k: receipt[k] for k in ('packet_id','payload_sha256','response_sha256','origin')})])
            except (ValueError, KeyError, TypeError):
                result['validation_error'] = 'OBSERVATION_CONTRACT_FAILED'
            p.write_json(out / 'result.json', result)
    print(json.dumps({k:result[k] for k in ('status','model_calls','production_changed')}), flush=True)
    if result['status'] not in ('PREFLIGHT_ONLY', 'COMPLETED'):
        raise SystemExit(3)


if __name__ == '__main__':
    main()

