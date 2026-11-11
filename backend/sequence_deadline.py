"""Monotonic deadlines shared across stages of one running analysis."""
import math


def bounded_deadline(started, budget_seconds, shared_deadline=None):
    for value in (started, budget_seconds):
        if type(value) not in (int, float) or not math.isfinite(value):
            raise ValueError('INVALID_LOCALIZATION_BUDGET')
    if budget_seconds < 0:
        raise ValueError('INVALID_LOCALIZATION_BUDGET')
    own = started + budget_seconds
    if not math.isfinite(own):
        raise ValueError('INVALID_LOCALIZATION_BUDGET')
    if shared_deadline is None:
        return own
    if type(shared_deadline) not in (int, float) or not math.isfinite(shared_deadline):
        raise ValueError('INVALID_LOCALIZATION_DEADLINE')
    # A caller may shorten a stage's allowance, never enlarge it. An expired
    # deadline stays expired; resuming must not create a fresh allowance.
    return min(own, shared_deadline)
