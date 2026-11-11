# Guaranteed pre-writer graphics candidates

The current report adapter ranks GOAL/ASSIST/SHOT before other events, then writer mentions within each tier, and selects eight. When there are at most eight priority events, all are guaranteed to survive regardless of prose. If the entire bundle has at most eight events, all survive. If more than eight priority events exist, this conservative helper returns no early candidates.

The retained export contains 21 events and five priority events; all five occur in the final eight cards. Historical timings: writer/projection 155.729s, assets 1166.845s. This identifies possible overlap, not a measured speedup. Production remains sequential.

The helper was checked against 50,362 selection permutations for 1–6 events with both priority tiers, arbitrary within-tier ranks and a three-card limit. Every returned ID survived selection. This checks selection only, not model outcomes or concurrency.

Before activation: use shared transport capacity/backoff; preserve final eight-card selection and request identity; account for early graphics time in the existing localization budget; persist completed receipts; cancel and join owned workers on writer failure; reuse receipts during final localization. Do not start all 21 graphics events or parallelize CPU-heavy contour workers on one vCPU.
