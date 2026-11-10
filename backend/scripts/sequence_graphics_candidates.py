"""Identify only graphics events guaranteed to survive report card selection."""


def guaranteed_graphics_event_ids(bundle, limit=8):
    events = bundle['events']
    if len(events) <= limit:
        return [event['event_id'] for event in events]
    priority = [event['event_id'] for event in events
                if event['canonical_event_type'] in {'GOAL', 'ASSIST', 'SHOT'}]
    # Prose mentions break ties within a tier. If the entire priority tier
    # cannot fit, no member is guaranteed before the writer returns.
    return priority if len(priority) <= limit else []
