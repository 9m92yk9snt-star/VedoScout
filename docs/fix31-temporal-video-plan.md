# FIX31: Temporal video, person identity and one action authority

This follows [the saved-evidence audit](fix30-shared-evidence-audit.md) on draft PR #35. It changes recognition inputs, identity sharing, scoring reconciliation and repeated work. It does not claim that the five real reference actions have already passed fresh automatic recognition.

## Implementation order

| Order | Problem | Implemented change | Verification |
| --- | --- | --- | --- |
| 1 | A prompt asking for more frames does not control provider sampling. The pinned LiteLLM converter drops per-file metadata; Emergent keys route through a proxy. | Explicit native metadata where local conversion occurs; source-indexed short videos retain about eight source views per second by holding each view for one playback second. Input hashes and separate source/playback clocks are recorded. | Exact deployed LiteLLM 1.80.0 wheel tested without HTTP; actual encoded videos inspected. Proxy receipt remains unconfirmed. |
| 2 | The static reader sees at most 12 views; crowded bodies disappear because a jersey-crop isolation rule is used for person labels. | Up to 65 chronological views per bounded window. Label every distinct measured local body, including overlapping people. Use existing nearby selected-person crops; compare hair, build, socks, boots and sleeves. Clear the gallery when the video changes. | In the saved 49.448 s frame, p031 had zero eligible old labels and now has one video body label. Duel regression acquires identity without jersey isolation or digits. |
| 3 | Identity, team inference, passing, finishing and outcome use incompatible evidence requirements. Final reconciliation removes visual goals/assists unless a separate physical certificate exists. | Source-bound motion observations enter the existing actor/causal resolver. Selected appearance refreshes team samples; dense team evidence is accepted consistently. Explicit visible ball-control observations can establish a transfer when the class-32 detector misses the ball. Complete visual scoring chains survive final reconciliation. A teammate's finish can correct an older semantic shot label. | Synthetic goal, saved-shot and assist chains pass through reconciliation, ledger, timeline, statistics and reference validation. Wrong actor, opposing receiver, missing control, false source, scene cut and conflicting outcomes remain distinguishable. |
| 4 | A resolved outcome is reconstructed/reviewed again; report writing starts another full-video perception task. | Reuse a matching actor/contact outcome; skip its repeated native post-strike tracking, intervention, role and geometry reads. Whole-window motion coverage reduces duplicate clarification requests while retaining native recall. A short feedback clip cannot claim whole-window coverage. The report writer receives canonical facts and the existing report schema. | Orchestration tests prohibit repeated native/provider work for a resolved clip. Report input audit records CANONICAL_FACTS with no video. |
| 5 | A full expensive rerun is needed to learn whether the five chains work. | Add a read-only motion-only review of the existing ZIP and saved native graph. It uses the production video reader and production reconciliation, without new jersey, role, geometry, feedback or report-writing model calls. | Reader-count, source binding, no physical rerun, unchanged database and honest failed-reference tests. Actual model recognition still needs the configured runtime. |

## Evidence from the real export

Source SHA-256: `b9e2ba4975ed9dc2497f860a80644711bfd12a2125d9fba6390600b0409ab999`.

The input-only audit decoded the five saved source windows and encoded the actual production motion views. No external model was called. Every selected timestamp is an actual exported source PTS. The 264 source views have a maximum gap of 134 ms. The first window has measured body labels in 41 of 49 views; the other windows have labels in every view. This is input coverage, not evidence that the model identifies the correct player in every view.

| Reference | Source window (seconds) | Views | Maximum gap |
| --- | --- | ---: | ---: |
| Saved shot, 23.68 s | 19.466–25.466 | 49 | 133 ms |
| Goal, 30.83 s | 25.599–33.599 | 65 | 133 ms |
| Assist, 43.19 s | 40.332–47.198 | 56 | 134 ms |
| Assist, 49.44 s | 47.331–52.931 | 46 | 134 ms |
| Assist, 56.44 s | 53.065–58.931 | 48 | 134 ms |

The original descriptions are not five proved events. In particular, two assist references were described as target shots. Replaying the unchanged saved observations still supplies no new verified goal or assist and reopens the old incorrect shot. Fresh temporal observations are required to test the new recognition route.

Google documents a default video sample rate of 1 FPS and warns that fast motion can lose detail: [video understanding](https://ai.google.dev/gemini-api/docs/video-understanding). The short rendition makes its source views available at that default rate. Source time is burned into every frame; model output uses integer frame indices mapped back to the actual source clock. The first broad discovery call still records proxy sampling as unconfirmed when the native converter is not observed. The client never claims a provider receipt that it cannot verify.

## Validation and remaining limits

- Final combined local run: **2,384 passed, 19 skipped** in 73.09 seconds. This includes historical FIX regressions, physical reconstruction, shared identity, canonical reconciliation, unified-engine projections and evidence export. Syntax and `git diff --check` also pass.
- Local verification includes the pinned Emergent LiteLLM wheel, native model loading, synthetic video encoding and the real source-window input audit. CI-style SDK stubs prohibit external model/payment calls. Tests requiring the installed Emergent SDK are skipped here because that SDK is unavailable.
- Automatic recognition and approval of the five real actions have not been established. Synthetic 5/5 is a test of data flow and decision logic, not a substitute for that result.
- New full-run latency is not measured. The old run spent about 69 minutes inside physical reconstruction. This change removes repeated work, but retained dense decoding/detection and model latency still need the existing stage timings. There is no supported percentage speedup or accuracy estimate for the complete pipeline.
- No new learned ReID model is enabled. Selected-person video comparisons and existing native continuity are the implemented identity path. A replacement model needs a benchmark on this footage before it can be treated as an improvement.
- A visual observation and a physical crossing certificate remain explicitly different evidence types. Both can support a correctly bound event; an old action label alone cannot.

## Reproduce without a new upload or taps

Input preparation only, with network access blocked by the utility:

```bash
cd backend
PYTHONPATH=. python scripts/audit_temporal_video_inputs.py \
  /private/export /private/export/video/canonical.web.mp4 /private/input-audit \
  --trace-id dense_e29df0078338b31c \
  --trace-id recall_72554e852f36c920 \
  --trace-id recall_30df768b8d18b6f8 \
  --trace-id dense_f72307202e61d854 \
  --trace-id recall_bdbaabd5fe9a824d
```

The following separate command enables real model calls and is intended only for the project's configured runtime. It has not been executed in this workspace:

```bash
cd backend
PYTHONPATH=. python scripts/replay_report_evidence.py /private/evidence.zip \
  --support-vision --motion-only \
  --cases-json ../docs/examples/five_action_reference_cases.json \
  --output-dir /private/five-action-review
```

The five reference cases select five existing windows. Expected labels/results are withheld from the readers and used only afterwards for validation. The output includes raw motion observations, source/input/response hashes, canonical events, reference diagnostics and a checksummed evidence ZIP. No database record is rewritten. A nonzero exit with `NOT_VERIFIED` is a failed acceptance result, not a reason to silently force the expected action into the report.
