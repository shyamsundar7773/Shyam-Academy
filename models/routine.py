from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from enum import StrEnum


class RoutineFrequency(StrEnum):
    DAILY = "DAILY"
    WEEKLY = "WEEKLY"
    SELECTED_DAYS = "SELECTED_DAYS"


class RoutineOccurrenceStatus(StrEnum):
    PENDING = "PENDING"
    UPCOMING = "UPCOMING"
    DUE = "DUE"
    COMPLETED = "COMPLETED"
    SKIPPED = "SKIPPED"
    MISSED = "MISSED"
    CANCELLED = "CANCELLED"


@dataclass(frozen=True)
class Routine:
    routine_id: str
    user_id: str
    name: str
    description: str
    frequency: str
    start_date: str
    end_date: str | None
    time_local: str
    duration_minutes: int
    timezone: str
    selected_days: tuple[int, ...] = ()
    enabled: bool = True
    category: str = "CUSTOM"


@dataclass(frozen=True)
class RoutineOccurrence:
    occurrence_id: str
    routine_id: str
    user_id: str
    occurrence_date: str
    scheduled_at: str
    status: str = RoutineOccurrenceStatus.PENDING
    completed_at: str | None = None
    skipped_at: str | None = None
    note: str = ""


@dataclass(frozen=True)
class RoutineMetrics:
    scheduled: int = 0
    completed: int = 0
    skipped: int = 0
    missed: int = 0
    current_streak: int = 0
    best_streak: int = 0
    consistency_percentage: float = 0.0


def validate_frequency(value: str) -> str:
    try:
        return RoutineFrequency(value).value
    except ValueError as error:
        raise ValueError("Frequency must be DAILY, WEEKLY, or SELECTED_DAYS.") from error


def validate_time(value: str) -> str:
    try:
        parsed = time.fromisoformat(value)
    except (TypeError, ValueError) as error:
        raise ValueError("Routine time must use HH:MM format.") from error
    return parsed.strftime("%H:%M")


def normalize_selected_days(days) -> tuple[int, ...]:
    result = tuple(sorted({int(day) for day in (days or ())}))
    if any(day < 0 or day > 6 for day in result):
        raise ValueError("Selected days must be weekday numbers from 0 to 6.")
    return result


def occurs_on(routine: Routine, day: date) -> bool:
    if day < date.fromisoformat(routine.start_date):
        return False
    if routine.end_date and day > date.fromisoformat(routine.end_date):
        return False
    frequency = validate_frequency(routine.frequency)
    if frequency == RoutineFrequency.DAILY:
        return True
    if frequency == RoutineFrequency.SELECTED_DAYS:
        return day.weekday() in routine.selected_days
    return (day - date.fromisoformat(routine.start_date)).days % 7 == 0


def generate_occurrences(routine: Routine, start: date, end: date) -> list[tuple[str, datetime]]:
    if end < start:
        return []
    routine_start = max(start, date.fromisoformat(routine.start_date))
    routine_end = min(end, date.fromisoformat(routine.end_date)) if routine.end_date else end
    if routine_end < routine_start:
        return []
    local_time = time.fromisoformat(validate_time(routine.time_local))
    result = []
    cursor = routine_start
    while cursor <= routine_end:
        if occurs_on(routine, cursor):
            result.append((cursor.isoformat(), datetime.combine(cursor, local_time)))
        cursor += timedelta(days=1)
    return result
