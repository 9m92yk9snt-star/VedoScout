# Shared monotonic localization deadline

localize accepts an optional shared_deadline. All primary/supplementary preparation guards and both transport deadlines use min(started + budget_seconds, shared_deadline). Without it the existing stage allowance remains. An expired shared deadline cannot be refreshed; nonfinite/invalid values fail before source work.

Seven standard-library unit tests passed for default allowance, staged reuse, no extension, expiry, zero budget and invalid inputs. Modified modules compile. Full localization integration tests and overlapping provider replay were not run in this step.

The outer pipeline does not yet pass this parameter or enable overlap. This is a prerequisite, not a measured speedup. The deadline is monotonic and process-lifetime scoped; it must not be persisted across process restarts. Request-count limits remain the responsibility of the existing bounded runner. Shared supervision, receipt reuse and failure cleanup still require outer orchestration integration.
