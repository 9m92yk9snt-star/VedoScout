# Build only the selected provider's request

`build_request` previously built both Gemini inlineData and Emergent data-URL objects for every call, then discarded the unused representation. Data-URL concatenation retained an extra base64-sized string per image. The function now builds only the selected provider's objects.

Each media file is still read and SHA-256-checked on every occurrence. Image/video order, bytes, detail settings, video FPS, prompts, output token budgets, model parameters, request-size limits and audit hashes remain unchanged. No lossy encoding, caching, fewer images or provider requests are introduced.

Sixteen committed pre-change wire fixtures cover two providers, four provider/model combinations, image and video items, both detail modes, text ordering, reasoning settings and explicit token limits. Tests require byte-identical serialized requests and audit objects, and still reject changed source files.

## Measurement

The offline benchmark constructed a synthetic packet repeating one real source JPEG sixteen times: 11.4 MB of serialized data. This is a stress fixture, not an actual production model request. Seven alternating rounds compared the pre-change function against the candidate; no request was sent.

| Provider | Median before | Median after | Python peak before | Python peak after |
|---|---:|---:|---:|---:|
| Emergent | 54.21 ms | 49.17 ms | 46.12 MB | 35.44 MB |
| Gemini | 45.49 ms | 41.39 ms | 46.12 MB | 34.72 MB |

All URL, payload byte and audit comparisons passed. The practical benefit is reduced transient memory; approximately 4–5 ms saved in this test does not establish a meaningful end-to-end latency reduction. Request payload size and model cost are unchanged.

Reproduce with `backend/scripts/benchmark_request_build.py --baseline <pre-change-transport.py> --image <source.jpg> --output <result.json>` and `PYTHONPATH=backend`. The baseline is `backend/sequence_pilot_transport.py` from commit `afc2015806f012d3df1bfddf8cfe8d4b5d6bead4`. JSON evidence records input and baseline checksums.

Results: `testdata/performance/request-build-2026-11-08.json`; regression fixtures: `testdata/performance/request-wire-parity.json`. No synchronization or deployment.
