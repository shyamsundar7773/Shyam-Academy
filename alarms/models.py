from dataclasses import dataclass
from datetime import datetime, timedelta


ALARM_STATUSES = {"ACTIVE", "CANCELLED"}


def alarm_id_for_session(session_id: int) -> str:
    if not isinstance(session_id, int) or session_id <= 0:
        raise ValueError("A positive session ID is required.")
    return f"academy_alarm_{session_id}"


@dataclass(frozen=True)
class Alarm:
    alarm_id: str
    user_id: str
    session_id: int
    module_id: int | None
    title: str
    body: str
    scheduled_at: str
    timezone: str
    status: str = "ACTIVE"
    source: str = "timetable"

    def scheduled_datetime(self) -> datetime:
        value = datetime.fromisoformat(self.scheduled_at.replace("Z", "+00:00"))
        if value.tzinfo is None:
            raise ValueError("Alarm time must include a timezone.")
        return value


def validate_alarm_timestamp(value: str) -> str:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError) as error:
        raise ValueError("Alarm time must be a valid ISO timestamp.") from error
    if parsed.tzinfo is None:
        raise ValueError("Alarm time must include a timezone.")
    return parsed.isoformat()


def next_weekly_occurrence(
    scheduled_at: str, weekday: int, now: datetime | None = None
) -> str:
    current = datetime.fromisoformat(validate_alarm_timestamp(scheduled_at))
    reference = now or datetime.now(current.tzinfo)
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=current.tzinfo)
    days = (weekday - reference.weekday()) % 7
    candidate = current.replace(
        year=reference.year, month=reference.month, day=reference.day
    ) + timedelta(days=days)
    if candidate <= reference:
        candidate += timedelta(days=7)
    return candidate.isoformat()


def calculate_next_occurrence(
    scheduled_at: str, recurrence_rule: str, now: datetime | None = None
) -> str | None:
    if not recurrence_rule:
        return validate_alarm_timestamp(scheduled_at)
    prefix, _, value = recurrence_rule.partition(":")
    if prefix != "WEEKLY" or not value.isdigit():
        raise ValueError("Unsupported recurrence rule.")
    return next_weekly_occurrence(scheduled_at, int(value), now)
