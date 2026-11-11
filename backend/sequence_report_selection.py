"""Shared card-selection rules for reports and guaranteed early candidates."""

CARD_LIMIT = 8
PRIORITY_TYPES = frozenset({'GOAL', 'ASSIST', 'SHOT'})


def event_priority(event):
    return 0 if event['canonical_event_type'] in PRIORITY_TYPES else 1


def select_report_cards(cards, events, mentions, limit=CARD_LIMIT):
    priority = {event['event_id']: event_priority(event) for event in events}
    return sorted(cards, key=lambda card: (
        priority[card['event_id']], -mentions[card['event_id']],
        card['evidence_time_ms']))[:limit]


def guaranteed_graphics_event_ids(bundle, limit=CARD_LIMIT):
    events = bundle['events']
    if len(events) <= limit:
        return [event['event_id'] for event in events]
    priority = [event['event_id'] for event in events if event_priority(event) == 0]
    return priority if len(priority) <= limit else []
