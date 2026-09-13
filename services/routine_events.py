from dataclasses import dataclass, field
from datetime import datetime, timezone

from database.repositories import routine_repository


@dataclass(frozen=True)
class RoutineEvent:
    event_type: str
    user_id: str
    routine_id: str | None = None
    occurrence_id: str | None = None
    payload: dict = field(default_factory=dict)
    created_at: str = ""


def emit(connection, event: RoutineEvent):
    return routine_repository.record_event(
        connection, event.user_id, event.event_type, event.payload,
        event.routine_id, event.occurrence_id,
    )


def occurrence_event(connection, user_id, routine_id, occurrence_id, event_type, **payload):
    return emit(connection, RoutineEvent(
        event_type, user_id, routine_id, occurrence_id, payload,
        datetime.now(timezone.utc).isoformat(),
    ))
