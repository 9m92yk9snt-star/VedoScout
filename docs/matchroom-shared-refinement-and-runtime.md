# Integrated CPU worker and shared refinement allowance

ONNX Runtime uses the same checksum-pinned weights, preprocessing and postprocessing via a small CPU-only adapter. Only owned Match Room children select it; ordinary nonworker callers retain OpenCV. Existing dependency pin updated from1.31.0 to tested1.31.1. Intra/inter-op threads fixed to1; no GPU/model/provider changes.

The existing three-refinement allowance of3*210=630s is shared against a parent monotonic deadline. Each pending candidate reserves up to105s for each later candidate; completed work releases unused time. At most three refinement children, and the nominal total initial/refinement ceiling remains8*35+630=910s. This changes per-child deadlines; it does not enlarge the aggregate allowance. Each child retains its own hard timeout and records the assigned budget.

Missing windows gain up to800ms of preceding CONFIRMED source context within the same1.5s inference-window bound. Explicit identity barriers and gaps over250ms stop expansion. Existing measured/approved segments and ball evidence remain preserved when refined segments are merged.

Unit controls cover shared-budget conservation, context barriers, input immutability, existing nonworker loader, CPU model input/output contract and rejection of unsupported engines. Full integrated eight-clip replay and actual React playback review are in progress; this document is not acceptance evidence. Keep PR56 draft until those results are recorded. No merge or deploy.
