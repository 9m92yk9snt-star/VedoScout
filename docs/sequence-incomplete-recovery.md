# Recover incomplete Sequence source work before optional reviews

A deployed 32.5-second upload produced two failed runs. Stored diagnostics showed
HTTP 429 in the first run and a missing initial packet in the second. Two completed
initial answers were reused, but two optional contact reviews still ran while the
third initial packet remained missing. A partial run must never publish a report.

## Changes

- Keep the existing source/selection/request/response checks for reuse. Completed
  initial packets are not resent during in-run recovery.
- Retry only transiently failed initial packets, once, before contact/outcome
  reviews. The retry has up to 1.5 times the normal per-call budget, capped by the
  existing 210-second transport ceiling (180 seconds for production's 120-second
  first call). It must fit inside the unchanged overall source-run deadline.
- If any initial packet is still missing or invalid, skip optional reviews and
  return a partial run. Never publish partial results as a completed assessment.
- For HTTP 429 with a temporary or unspecified limit, allow one transport retry
  per request. Pause all new batch requests for Retry-After (minimum one second,
  default two), only when the wait is at most 30 seconds and a full call still fits
  within the deadline. Running siblings are not cancelled for a recoverable 429.
- Known exhausted quota, HTTP 402, access denial, repeated 429, an unsupported
  Retry-After value, excessive cooldown or insufficient budget stop the batch.
  HTTP-date Retry-After is supported. No alternate provider/model is attempted.
- Keep the initial recovery error and prior 429 diagnostics in saved receipts.
  Failure summaries retain allowlisted limit categories, never provider bodies.
- Distinguish a worker exiting without a receipt from its wall deadline expiring.
  Socket timeouts also have a separate allowlisted code.

## Image coverage and scope

The four completed exported receipts contained 194, 197, 110 and 107 images,
respectively, with no repeated pixel hashes within any request. Native contact
detail and full-source overview are different views. This patch does not thin
frames, alter crops, lower image detail or claim that those views are redundant.
It removes wasted optional calls while required source work is incomplete.

The retired production chain stays retired. Layout, saved report rendering,
preview entitlement rules and the watchdog limits are unchanged. Existing strict
code fingerprints still apply: old-version checkpoints are not silently trusted
after a code change. Same-version retries retain exact-request reuse.

## Validation limits

Offline tests exercise real spawned workers for 429 cooldown/retry exhaustion,
known quota, queue suppression, worker crash, deadlines and process cleanup.
Synthetic runner responses verify that only the missing initial packet is retried,
the deadline is unchanged and both review planners remain blocked after failure.
These checks do not establish perception quality, actual deployed completion time
or provider availability. No paid model calls or deployment are part of this fix.
