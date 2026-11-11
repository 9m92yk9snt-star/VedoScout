# Orman2000 source interruption

Evidence: report c74d5920-0219-4d9f-a01a-66f6605db0b1, deployed 09044af4f768f4699710437eee52e5fd6b03dddf.

Two failures: 796.068 and 900.189 seconds, returncode 3, PARTIAL_MODEL_RUN, MODEL_WALL_DEADLINE_EXCEEDED. Five initial receipts were reused on retry. Final saved state: ten completed initial packets, two completed contact reviews, three failed contact reviews. Twelve raw-response checksums verified. No HTTP status was recorded in these failure summaries; this does not prove no provider/network issue occurred.

Three initial packets succeeded only on within-run recovery: 161.924, 136.169 and 149.527 seconds. Normal per-call budget was 120 seconds, recovery 180. Set normal calls to 180 within the unchanged 900-second source stage. This avoids the known premature cutoff for these observed durations; it does not establish a new live completion time or guarantee future responses fit.

Allow exact-request receipt migration from the exported release fingerprint only when all modules except runtime orchestration and checkpoint code remain identical. Payload/provider/model/response checksum and current-parser checks remain mandatory. This is essential to avoid invalidating the twelve paid receipts on deployment.

Remaining validation: a deployed retry must rebuild matching follow-up requests and complete remaining source reviews, report writing and graphics. No new provider calls have been made for this patch. The total source deadline can still be reached; this patch is not a claim of universal interruption immunity.
