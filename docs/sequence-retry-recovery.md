# Sequence failure diagnosis and exact-request recovery

## Why this change exists

The retained Orman500 export shows a failed first attempt after 502.960 seconds,
followed by a successful attempt. It records only `SEQUENCE_PROCESS_FAILED` for
the failure. The old parent process raised on a nonzero exit before reading the
child's structured result, then deleted its temporary directory. The historical
root cause cannot be recovered from this export.

The successful attempt's internal timings are 604.954 seconds for source
analysis/preparation, 177.526 for writing/projection and 39.224 for assets. The
full-start to ready interval is 823.696 seconds. First start to final ready is
1819.661 seconds, including a 493.006-second gap between the failure and the
second start. That gap is not established processing time.

## New behavior

- The transport writes each returned receipt atomically before waiting for the
  entire batch. The parent checks for changes every 0.5 seconds and persists
  them in the report's `sequence_retry` field. An interrupted retry preserves
  prior receipts that its runner has not reached yet. Persistence is bounded
  to 4 MB and fails closed if storage fails; it is not an exactly-once billing
  guarantee during a crash between provider completion and database storage.
- Nonzero exits and process timeouts retain safe phase, elapsed time, exit
  status, completed-receipt count and allowlisted error categories. No stderr,
  provider error body, exception text, credentials or temporary paths enter
  that diagnostic. Up to eight failures survive subsequent retries.
- Recovery is limited to the same report ID, source checksum, original
  selection checksum and code fingerprint. A code change invalidates old
  checkpoints conservatively. The current code does not retroactively add
  recovery information to the old live failure.
- Preparation is rebuilt. For each initial or automatically planned detail
  request, the runner rebuilds the full provider payload and checks its exact
  SHA256, provider/model, original raw-response SHA256 and completion status.
  It reparses and resolves a candidate against the rebuilt source context.
  Only a valid exact match avoids a new request. Incomplete, corrupt or changed
  requests are sent normally. No expected answers, historical action hints,
  inferred identity profile or alternate model are introduced.
- Retry admission changes `failed` to `generating` before generation starts.
  Both states permit validated checkpoint recovery; `ready` does not. Startup
  no longer deletes valid checkpoints before replacement data is persisted.
- A resumed run is explicitly `EXACT_REQUEST_RETRY` with reused packet IDs and
  `fresh_end_to_end_run=false`. The canonical adapter admits it only with the
  completed-run and per-receipt retry verification checks. Partial runs remain
  unpublished. Existing identity, contact, ball/outcome and proof checks stay
  in place, including unresolved foot side and unavailable weak-foot grades.
- Read-only evidence export includes `sequence/failures.json` and
  `sequence/retry.json`. Normal report/status/list routes omit bulk retry
  receipts just as they omit the full sequence audit.

## Validation and limits

Offline tests use synthetic workers for exit, timeout, persistence ordering,
changed/corrupt receipt rejection and selective retry, plus retained real
receipts for canonical publication and existing role/proof regressions. These
tests send no model requests. They establish orchestration behavior, not a new
perception result or a measured reduction in live analysis time.

No concurrency increase, image reduction or writer/model change is included.
Those require a separately reviewed speed experiment preserving the five
reference actions and all identity/proof gates. A healthy fresh run is not
claimed to be faster as a result of this recovery change.
