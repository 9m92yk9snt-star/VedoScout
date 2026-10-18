# Standalone sequence experiment

Orman400 took 84m56s, including 74m48s in the physical phase, and still produced
incorrect identities, outcomes and duplicate goals. Its 20 temporal inspections
represented 99.831 seconds of overlapping source spans as 1,395 seconds of
one-image-per-second model video. The first whole-video call requested 8 fps,
but the export does not establish that its proxy forwarded that setting.

This experiment is a separate command-line path. It does not change the
production analysis, its detector, reports, UI, database or deployment. Main
at the start of this work is `d6561de530c35aaecb5af53a62cf5723c3ed43e8`.

## What is built

- One sequential decode of the canonical source. Sample by actual media PTS,
  retain the original positive user points, visibility/exclusion hints and
  stored visible-person masks. There is no inferred track identity or colour
  profile in the input. No new detector or segmentation model runs.
- Complete source coverage in 30-second packets with six-second overlaps.
  An uninterrupted play can span packets; a camera pan is not an identity cut.
  The model sees explicit chronological images, each preceded by its actual
  source frame ID and timestamp. No slowed playback or provider fps conversion
  is required. Default overview is 8 fps / max 768 pixels / JPEG quality 75.
- All ball-involved players are observed before selected-player attribution.
  Passer, receiver and finisher have separate play-local person IDs. Two
  distinct people cannot simultaneously receive the selected identity.
- One resolver owns attribution and the visible causal chain. A complete
  visual observation does not need another native-ball/jersey/geometry approval.
  Unknown facts remain unknown; the runner never fills an expected total.
- A missing connection can open at most two targeted jobs in one round. They
  retain the play's overview and add up to 2.4 seconds of 24-fps / max-1280-pixel
  source detail around the missing connection. A resolved overlapping read
  suppresses that job. No generic second full-video pass runs.
- Observations of the same selected player's release/terminal outcome merge
  with provenance. A terminal match can merge two goals whose guessed contact
  times disagree. Separate rebound shots remain separate. Initial conflicting
  outcomes need the targeted read; repeated opinions do not silently settle it.

The image requests are larger and potentially use more image tokens than
video-native input. Fewer requests and removal of the physical reconstruction
do **not** establish faster model inference or equal perception quality. This
must be measured with actual responses before adopting this path. The 8-fps
overview is sampling, not an assertion that every native frame was inspected.
Original source pixels remain available for targeted detail.

## Run independently

Python 3.11+ and `opencv-python-headless` are needed for preparation/detail.
Model transport uses only Python's standard library. The existing pure
`player_selection` helper preserves human selection metadata; no production
orchestrator or model SDK is imported.

Extract the existing evidence ZIP to a local folder. Preparation reads only
`video/*.mp4`, `anchors.json` and `SHA256SUMS`. In particular it does not load
`report.json`, old model replies, canonical events or the five reference cases.

```bash
python backend/scripts/run_sequence_pilot.py prepare \
  --evidence-dir /path/to/extracted-evidence \
  --output /path/to/new-prepared-folder
```

With `GEMINI_API_KEY` already configured in the process environment:

```bash
python backend/scripts/run_sequence_pilot.py run \
  --prepared /path/to/new-prepared-folder/manifest.json \
  --output /path/to/new-run-folder \
  --provider gemini --model gemini-2.5-pro --budget-s 300
```

The optional `--provider emergent` adapter uses the Universal Key proxy's
OpenAI-compatible image interface with `EMERGENT_LLM_KEY` from the environment.
Pass the exact model identifier supported by that account using `--model`.
Neither adapter has been authenticated in this environment. The previous
unauthenticated proxy probe returned HTTP 403; no workaround or alternate route
is attempted after an access rejection. Native Gemini is an independently
selected provider, not an automatic fallback.

Keys are never CLI arguments, committed files, saved headers or error output.
There is no login, secret acquisition, server deployment or database access.

The execution budget is 300 seconds by default, including model request
preparation and targeted work, after the explicitly separate offline preparation.
At most four initial jobs plus two follow-ups are allowed, with two concurrent
owned processes and a 90-second per-job wall deadline. The Orman400 input needs
three initial jobs. Actual workers are terminated at their deadline; there is
no SDK retry, provider retry or recursively opened feedback round.

Every complete encoded request is checked against 19.5 MB. It is rejected
before sending if too large; images are never silently dropped. Receipts save
input/response hashes, explicit image counts, model version/usage when returned,
elapsed time and raw model text. Only a model run can produce these responses.
An unset key produces `MODEL_KEY_NOT_CONFIGURED` and zero jobs, never a claimed
five-action result.

## Evaluate separately

```bash
python backend/scripts/run_sequence_pilot.py evaluate \
  --result /path/to/new-run-folder/result.json \
  --cases docs/examples/five_action_reference_cases.json
```

Reference times are navigation anchors. Matching allows the actor's observed
buildup-to-contact interval and the case tolerance; the model's actual contact
time is preserved. This evaluator does not feed answers or search locations
back into preparation or model requests. It also lists unmatched additional
target goals, assists and shots. A matching result still requires visual review
of the cited source images; self-reported model certainty is not ground truth.

The acceptance experiment needs all five correct target actions, no opponent
goals/spare-ball goals/duplicate finishes, actual latency and returned usage.
Compare only against this source, these taps and a recorded configuration.
After success on this video, use additional videos and changed time origins
before claiming general reliability. The old exports are not independent
test videos just because their encodings or report IDs differ.

## What was actually verified here

`docs/examples/sequence-pilot-orman400-preparation.json` records actual offline
preparation on the existing source: 4,606 native frames decoded, 622 unique
sampled instants, 718 frame appearances across three packets, all ten taps and
three masks retained, maximum sample gap 134 ms. Preparation with the final
settings took 11.229 seconds, with zero detector forwards and zero model calls.
Both adapters' complete payloads were constructed and size-checked offline.

The tests exercise actual source decoding/cropping/checksums, attribution and
causal failures, duplicate/rebound handling, process termination, access-stop
behaviour and no-key failure. Their observation fixtures are synthetic tests.
The standalone GitHub Actions workflow runs these checks plus the shared
selection tests without model credentials or uploaded match footage.
No new model perception, five-action success, production report completion or
end-to-end speed improvement has been verified. An authenticated model endpoint
is the outstanding requirement for that next experiment.

Provider contracts used:

- <https://ai.google.dev/api/generate-content>
- <https://ai.google.dev/gemini-api/docs/image-understanding>
- <https://ai.google.dev/gemini-api/docs/video-understanding>
- <https://help.emergent.sh/the-universal-llm-key>
