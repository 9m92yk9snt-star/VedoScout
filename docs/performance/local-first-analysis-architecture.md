# Local-first video analysis architecture

Status: implementation design, not a deployed replacement. 13 November 2026.
Goal: minimize paid perception and end-to-end latency while retaining measured
identity, event coverage, uncertainty and report quality.

## Ownership and data flow

Video + original taps -> timestamped frames -> YOLO via ONNX Runtime ->
separate person and ball observations -> ByteTrack person proposals ->
tap-bound identity validation -> shared evidence store -> event interpretation,
Match Room and report. A targeted LLM review consumes unresolved intervals.
Its validated observations return to the same evidence store.

ONNX is the runtime for the existing model, not a substitute for YOLO or
ByteTrack. Initially retain weights, preprocessing, precision and thresholds.
GPU providers are a future execution option, not required by this design.

## Module contracts

- Frame reader: source SHA, actual media PTS, dimensions, frame digest and cut
  candidates. Stream bounded windows rather than retaining a whole match.
- Detector: one owned ONNX session per analysis worker, person/ball classes,
  scores and boxes, model SHA, preprocessing version and runtime/provider.
  Consumers reuse exact predictions; masks are calculated when required.
- Person tracker: ByteTrack IDs scoped to scene and run; actual detection
  references on every observation. Predicted or unmatched positions cannot
  become observed evidence. Reset at confirmed cuts and timestamp gaps.
- Target identity: original user taps remain the authority. Unique spatial
  matches are candidate seeds, not blanket approval of the subsequent track.
  Ambiguous same-kit overlap, ID change and disappearance raise unresolved
  intervals. No transfer of identity to the receiver or scorer.
- Ball evidence: distinct from person tracking; multiple ball candidates remain
  distinguishable. Static spare balls cannot be promoted to the active ball
  from proximity alone. Occluded trajectories stay uncertain.
- Evidence store: source SHA, selection digest, model/preprocess versions,
  timestamps, provenance, coordinates, uncertainty and validation state.
  A completed stage is checkpointed atomically; retries reuse exact compatible
  results. Large arrays live in content-addressed assets, not Mongo documents.
- LLM dispatcher: receives the specific unresolved question plus sufficient
  before/after source context and original identity references. It reuses paid
  receipts and shared-prefix caching. No repeated request for an unchanged
  resolved question. Missing evidence never becomes a confident local answer.
- Report/graphics: consume the same validated evidence. Graphics do not infer
  action truth; report prose cannot introduce unsupported events or scores.

## One-vCPU execution

Use one active inference worker and bounded queues. Start with one ONNX
intra/inter-op thread, then benchmark rather than assuming more threads help.
Decode and infer in a streaming loop; avoid competing heavyweight workers.
Reuse loaded weights and exact frame predictions across consumers.
Preserve all current evidence sampling and image quality during comparison.
Do not enable quantization, lower resolution or frame skipping as an implicit
cost optimization. Measure peak RSS as well as wall time and CPU time.

## Transition without losing existing results

1. Local proposal benchmark exists in PR66; no production behavior changes.
2. Establish a permitted ONNX execution environment and compare the exact model
   with OpenCV: numerical deltas, NMS decisions, coverage and wall time.
3. Add tap-bound identity evaluation with labelled target frames, occlusions,
   cuts and same-kit crossings on the supplied videos.
4. Compare local positions and ball measurements against reviewed source
   frames, not merely LLM outputs. Track wrong-player frames and hidden-foot
   errors separately from missed frames.
5. Enable replacement of paid localization only for the validated scope.
   Unresolved coverage retains the existing path and its context.
6. Extend shared observations to source-event interpretation only after action
   recall, outcomes and evidence attribution meet the baseline.
7. Measure complete report time and actual billable usage including retries.
   Accept each stage only with no observed quality regression on the reviewed
   set; do not claim a universal zero-regression guarantee from finite tests.

## Metrics and release decision

Record source duration, frames decoded, detector calls/cache hits, inference
seconds, tracking seconds, peak RSS, LLM calls/input/output/cached tokens,
fallback rate, wrong-player frames, identity switches, missed target frames,
active-ball coverage and event/actor/outcome correctness.
Compare the same source and taps against the current sequence implementation.
A drop in LLM tokens alone is insufficient if recall, uncertainty handling or
total latency worsens. No percentage saving is promised before this comparison.

## Current measured constraint

On one pinned CPU core, 180 frames from three seconds of uploaded footage
required 32.52 seconds: detection 30.42, decoding 1.71, ByteTrack 0.26.
This is proposal generation only. It does not establish selected-player
identity or end-to-end report speed. ONNX remains in the design, but its
comparison has no valid result: automatic review blocked an attempted
telemetry connection despite runtime telemetry being disabled.
Do not rerun the rejected configuration or route around that rejection.
