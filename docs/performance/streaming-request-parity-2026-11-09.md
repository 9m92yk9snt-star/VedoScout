# Exact streaming localization request replay

Compared the pre-streaming prepare implementation from fb271c18000bcbc71f51b443f87fd48beedd02bc with the new implementation on the SHA-bound original export/video. Nine requests (eight primary plus one completion) contain 186 timeline-frame entries and ten human references per request. Entire build_request return values (URL, encoded request body and audit) matched byte-for-byte. Frame/reference records also matched after excluding temporary local file paths. No requests were sent to a provider.

Preparation plus a second request serialization took 9.498935s before and 6.135075s after in this single sweep. This is not a repeated timing benchmark or full-analysis speedup. The earlier raw-image parity check covered 169 primary frames; this extends verification through the actual JPEG and provider-wire representation including completion coverage.

All three GitHub workflows succeeded for production-code commit ecbb8fbd8dcf51e1899eecb9306ef625d8e34654: Production verification, Standalone sequence experiment and Sequence full-report integration. No new live model analysis, synchronization or deployment.

Reproduce with backend/scripts/verify_streaming_requests.py, supplying the original video, export ZIP and output JSON. Baseline commit must be available in local Git history. Raw results are in testdata/performance/streaming-request-parity-2026-11-09.json.
