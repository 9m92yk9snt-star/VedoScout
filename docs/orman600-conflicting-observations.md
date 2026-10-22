# Orman600: comparison of the conflicting goal observations

This offline investigation compares the preserved receipts from PR47 and PR50. It sends no model requests and makes no production code/report changes.

## Verified image delivery

Image SHA256 sets in the actual transport receipts show that **all 150 images from the earlier goal review are also in PR50**, byte for byte. PR50 adds 33 images; no earlier image is removed. Both requests use gpt-6-astra, medium reasoning and high image detail.

PR50 includes the exact contact interval and native detail through the outcome. At existing overview instants, the native crop is stored in zoom_view and sent as an additional image. The 16.633s native crop was verified in the actual request image set. Looking only at frame.path would incorrectly suggest this instant had only a downscaled overview.

Visual inspection of delivered contact crops at 16.533s and 16.733s shows the involved players' bodies, legs and the goalmouth within the crop. This does not prove every relevant limb is unoccluded. There is no demonstrated crop-boundary loss explaining the changed scorer judgement at those instants. JPEG quality 50 and visual overlap remain limitations, but neither has been isolated as the cause.

## What changed in the answers

| Item | Earlier goal review (PR47) | PR49 evaluation (PR50) |
| --- | --- | --- |
| Selected person | White #10 | White #10 |
| Ball later in net | Observed | Observed |
| Shot action | a5 | a6 |
| Contact actor unique | true | false |
| Shot outcome field | GOAL | UNKNOWN |
| Contact bracket supplied | 16.500–16.767s | 16.533–16.833s, rejected because actor not unique |
| Other-touch uncertainty | Keeper brush and later defender contact unresolved in questions | Releasing touch and later clearance unresolved in questions |
| Goal admitted by resolver | No | No |
| Supported anatomical foot | No | No; anatomical_foot omitted |

The earlier answer internally combined GOAL/unique actor with unresolved contact questions. It was not a clean automatic confirmation. The newer answer explicitly withholds the shot attribution. The disagreement is present in the raw model responses before resolution; it is not introduced solely by report wording.

The prompt and image set both changed between requests. These two runs therefore do not isolate model randomness, prompt influence or added visual context. A definite causal explanation would be unsupported.

## Foot-specific finding

The PR49 instruction says a model **may add** anatomical_foot and may omit it if there is no limb evidence. The latest reply therefore satisfies the current observation contract while supplying no anatomical assessment. Parser success must not be reported as successful execution of a substantive foot assessment.

An explicit per-action assessment, including an explicit insufficient-evidence result, would make this omission detectable. It would not by itself establish LEFT or resolve scorer attribution. This investigation does not implement or validate such a contract change.

## Decision

This case does not yet demonstrate reliable automatic scorer or striking-foot approval. Preserve the observed ball-in-goal fact separately from unresolved scorer attribution in internal review. Do not manually set LEFT, reuse the earlier GOAL field as final proof, label the claim user-confirmed, or present another successful API call as proof of correctness.

Further implementation should make the separate questions observable: selected-player releasing touch, ball entering goal, possible intervening opponent contact and its effect, and anatomical side. Any subsequent model comparison should hold the source image set fixed and change one input factor at a time. No additional paid request was made during this investigation.
