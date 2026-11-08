# Shared model supervision for writer/localization overlap

This follow-up adds the transport prerequisite for the heavy overlap opportunity identified in `heavy-bottlenecks-2026-11-08.md`. It does not enable concurrent writer and localization stages or claim a minute-scale speedup.

`RunCoordination` can be shared by independent transport supervisors. Reservations cap the combined active model children at two (or one when explicitly selected). A 429 response publishes a common pause for new requests, while already-running bounded calls may finish. An external stop prevents new launches and terminates active children through the existing supervisor cleanup. Slots are released on completion, callback failure, process/pipe setup failure and cleanup.

`run_jobs_async` shields and owns the supervising thread. On async cancellation it signals the coordinator, continues servicing the event loop for receipt-checkpoint callbacks, and waits until the supervisor has stopped/joined its actual child processes. Merely cancelling `asyncio.to_thread` did not provide that ownership. The writer and localizer now use this wrapper; existing per-call deadlines, request bytes, model choices, image inputs and receipt validators are unchanged.

The writer accepts an optional coordinator. Localization accepts an optional coordinator and worker count, preserving its default of two workers. No coordinator is currently shared by the outer writer/localization stages, so their production order remains sequential.

`RunLane` adds a dynamic stage limit inside the same shared cap. A one-slot writer lane and one-slot localization lane reserve capacity for each stage, including between writer sections. Once writing completes, the localization lane can expand to two without restarting its supervisor or changing requests. Lane acquisition updates both counters atomically under the shared lock; pauses and cancellation remain shared. This mechanism is tested but not yet composed by the outer pipeline.

## Verification

253 sequence, report and localization tests pass locally. New tests use spawned local synthetic workers, not provider calls, and cover:

- Two independent three-job pools sharing a two-call cap, with unchanged result ordering.
- Shared pauses that cannot be shortened by later shorter delays.
- A genuine synthetic 429 receipt applying its pause to the shared coordinator.
- Cancellation stopping/joining an actual spawned process and releasing its reservation.
- Pipe creation failure releasing the reservation for later work.
- A queued localization job cannot take the slot reserved for a subsequent writer section.
- An already-running synthetic localization pool expands to two concurrent children after writing finishes, with all jobs completed and all reservations released.
- Lane limits reject invalid values and preserve shared backoff/cancellation.

Existing request-wire, checkpoint/retry, provider-error, writer-budget and localization reuse regressions also pass. No paid model request, synchronization or deployment was performed.

## Remaining integration constraint

The tested dynamic lanes now provide the capacity-allocation prerequisite. The outer integration still needs a common elapsed-time budget, saved receipts through writer failure, and exact receipt reuse for the final selected cards. Enable the overlap only with those checks and an output/timing comparison. The five guaranteed scoring cards remain the candidate subset; optional cards retain final writer-based selection.
