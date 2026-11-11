# Shared report-card selection

The report adapter now calls a shared pure selection function with the same priority, mention count, source timestamp tie-break and stable eight-card slice as before. Guaranteed early candidates use the same priority function and limit. The previous offline helper re-exports the shared implementation.

Four standard-library tests passed, including 1,000 seeded comparisons against the prior selection expression, input non-mutation, priority overflow, eight low-priority events and five guaranteed candidates despite prose favoring other events. Outputs and order matched. This is selection-level validation, not a new full report model run.

Concurrent writer/localization remains disabled. This change removes duplicated selection policy as a prerequisite; shared budget accounting, receipt reuse and cancellation integration remain before activation. No deployment or measured speedup claimed.
