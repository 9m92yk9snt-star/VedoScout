# Automatic anatomical foot evidence

SEQUENCE_V1 previously hardcoded every event's foot to UNKNOWN. This change lets
the existing source observations carry a separate, source-cited anatomical-foot
claim through the resolver, canonical bundle and existing web/PDF publication.
It does not train a model or add a review request.

## Admission

Only SUPPORTED LEFT/RIGHT with the same action actor, excluded alternative
contact actors, torso orientation, both anatomical leg sequences and contacting
limb/ball-departure citations can publish a side. Both legs need distinct source
instants before and at/after the contact bracket. Frame references, chronology
and action/source bounds are checked. The canonical adapter rechecks the claim
instead of trusting an intermediate `foot` label. These checks validate the
model's evidence contract, not independent visual correctness.

PROBABLE, UNCERTAIN, conflicting sides, malformed evidence or an explicit FOOT
question leave public foot UNKNOWN. Candidate side and reasons stay in the
audit. Unsupported foot-specific sentences are removed from canonical action
descriptions and rejected in writer prose/evidence. When supported, the existing
action description can say “Shoots with the left foot.” Layout and CSS are
unchanged. Isolated contacts still do not establish overall weak-foot ability.

FOOT is a separate model question reason that does not block a known action,
trigger another paid request, or authorize an uncertain contact. Existing
CONTACT/IDENTITY/OUTCOME questions, including mixed legacy questions about foot
and goalkeeper/defender contact, continue to block the affected event. No text
heuristic relabels old questions. The prompt explicitly retains scorer and
pre-deflection trajectory uncertainty as contact/outcome questions.

Existing automatic terminal reviews retain 1.2 seconds of native approach detail
before a bracketed release, instead of 0.1 seconds, alongside the existing
post-release outcome. Outcome follow-ups use the same approach margin. This adds
source images to existing requests, not extra requests. Preparation and provider
request-byte/time budgets remain enforced. Larger inputs may increase latency;
actual live runtime and anatomical accuracy need a fresh authorized test.

The helper is covered by runtime fingerprints and evidence exports, preventing
old checkpoints from being silently treated as observations under the new code.

## Orman600 evidence status

The actual PR #48 anatomical-only reply remains LEFT/probable. Its unmodified raw
response and hashes are preserved in `examples/sequence-foot-probable-regression.json`.
An offline regression verifies that it stays public UNKNOWN under the new
contract. The previous experiment's anatomical-only `plays=[]` response is not
used as a production event and does not become approved through this change.
The additional goal and its scorer attribution remain unresolved for automatic
admission. Coding tests must not be described as model recognition success.

No additional paid model request, report rewrite, merge or deployment was made
while implementing this change. Synthetic tests exercise both LEFT and RIGHT,
hidden contacts, guessed sides, bad citations, contradictions, foot-only versus
contact questions, canonical revalidation and existing publication. Retained
whole-source event tests protect existing goals/assists/saves and timestamps.
