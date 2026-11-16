"""Timezone-aware half-open appointment intervals."""
from datetime import datetime, timedelta


def overlaps(start: datetime, minutes: int, other: datetime, other_minutes: int) -> bool:
    if start.tzinfo is None or other.tzinfo is None or minutes <= 0 or other_minutes <= 0:
        raise ValueError('Timezone-aware positive intervals required')
    return start < other + timedelta(minutes=other_minutes) and other < start + timedelta(minutes=minutes)
