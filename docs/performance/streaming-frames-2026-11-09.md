# Streaming timeline decoding

Localization now consumes iter_frames_at continuously instead of restarting read_frames_at after every eight requested frames. The existing materializing API wraps the same iterator. Actual PTS selection, fallback rejection, one-second gap seeking and bounded forward steps remain unchanged. JPEG encoding, sampling and model input formatting are untouched. Only the current decoded image is retained by the iterator.

Real-source replay of eight saved localization timelines compared 169 requested frames: actual timestamps and SHA-256 of every decoded image matched the prior eight-frame batching strategy. Single-run read/hash time was 5.779437s before and 3.104160s after. This uses saved frame timestamps, not a new paid analysis or an end-to-end request-byte replay; no total-analysis improvement is claimed. Reproduce with benchmark_streaming_frames.py and the original video/export ZIP.

41 focused localization, timebase and streaming tests passed. Three server-import timebase tests could not run locally because server dependencies (first missing bcrypt) were unavailable; they were explicitly deselected in the focused rerun, not counted as passing. Added tests cover lazy retrieval, one initial seek for nearby frames and fallback-time rejection. Existing localization missing-frame failure and reference preservation tests pass after adapting their fake decoder to the streaming interface.

No engine, threshold, identity gate, synchronization or deployment change.
