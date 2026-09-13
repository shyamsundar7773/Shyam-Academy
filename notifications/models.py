from dataclasses import dataclass, field
from datetime import datetime

NOTIFICATION_TYPES = {
    "SESSION_REMINDER", "SESSION_START", "SESSION_MISSED",
    "TEST_REMINDER", "INTERVIEW_REMINDER", "MENTOR_RECOMMENDATION", "SYSTEM",
    "ROUTINE_REMINDER", "ROUTINE_MISSED",
}
NOTIFICATION_STATUSES = {
    "SCHEDULED", "READY", "DELIVERED", "READ", "FAILED", "CANCELLED", "SUPPRESSED",
}
PRIORITIES = {"LOW", "NORMAL", "HIGH", "URGENT"}


@dataclass(frozen=True)
class Notification:
    notification_id: str
    user_id: str
    notification_type: str
    title: str
    body: str
    scheduled_at: str
    session_id: int | None = None
    module_id: int | None = None
    status: str = "SCHEDULED"
    priority: str = "NORMAL"
    metadata: dict = field(default_factory=dict)
    delivered_at: str | None = None
    read_at: str | None = None
    cancelled_at: str | None = None


def validate_notification_type(value):
    if value not in NOTIFICATION_TYPES:
        raise ValueError("Invalid notification type.")


def validate_status(value):
    if value not in NOTIFICATION_STATUSES:
        raise ValueError("Invalid notification status.")


def validate_priority(value):
    if value not in PRIORITIES:
        raise ValueError("Invalid notification priority.")


def parse_scheduled_at(value):
    if not isinstance(value, str):
        raise ValueError("Notification time must be an ISO timestamp.")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("Notification time must be a valid ISO timestamp.") from error
    if parsed.tzinfo is None:
        raise ValueError("Notification time must include a timezone.")
    return parsed
