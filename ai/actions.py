"""Explicit, permission-aware AI actions. No action is implicit."""

from dataclasses import dataclass
from typing import Any, Callable

from models.ai import AIActionProposal
from services.notes_service import save_note
from services.routine_service import create_routine


@dataclass(frozen=True)
class AIAction:
    name: str
    description: str
    input_schema: dict[str, Any]
    requires_confirmation: bool
    handler: Callable

    def validate(self, payload: dict[str, Any]) -> None:
        if not isinstance(payload, dict):
            raise ValueError("Action payload must be an object.")
        properties = self.input_schema.get("properties", {})
        required = set(self.input_schema.get("required", []))
        if set(payload) - set(properties) or required - set(payload):
            raise ValueError("Action payload does not match the declared schema.")
        for key, rule in properties.items():
            if key not in payload:
                continue
            kinds = rule.get("type")
            if isinstance(kinds, str):
                kinds = [kinds]
            value = payload[key]
            if kinds and not (
                ("integer" in kinds and isinstance(value, int) and not isinstance(value, bool))
                or ("string" in kinds and isinstance(value, str))
                or ("array" in kinds and isinstance(value, list))
                or ("null" in kinds and value is None)
            ):
                raise ValueError(f"Action field '{key}' has an invalid type.")
        if self.name == "CREATE_NOTE":
            if int(payload["module_id"]) <= 0 or any(
                not str(payload.get(field, "")).strip()
                for field in ("category", "topic", "title", "content")
            ):
                raise ValueError("Note action contains invalid fields.")
        elif self.name == "CREATE_ROUTINE_PROPOSAL":
            from services.routine_service import validate_routine
            validate_routine(payload)
        elif self.name == "SCHEDULE_NOTIFICATION_PROPOSAL":
            if "+" not in payload["scheduled_at"] and "Z" not in payload["scheduled_at"]:
                raise ValueError("Notification time must include a timezone.")

    def execute(self, connection, user_id: str, payload: dict[str, Any]):
        self.validate(payload)
        return self.handler(connection, user_id, payload)


def _note(connection, user_id, payload):
    if payload.get("session_id") is not None:
        owned = connection.execute(
            "SELECT 1 FROM sessions WHERE session_id=? AND owner_user_id=?",
            (payload["session_id"], user_id),
        ).fetchone()
        if not owned:
            raise ValueError("The note session is not owned by this user.")
    return save_note(
        connection, user_id, int(payload["module_id"]), payload.get("session_id"),
        payload["category"], payload["topic"], payload["title"], payload["content"],
        payload.get("source", "Advanced AI"),
    )


def _routine(connection, user_id, payload):
    values = dict(payload)
    values.pop("approval_note", None)
    return create_routine(connection, user_id, values)


class AIActionRegistry:
    def __init__(self):
        self._actions = {
            "CREATE_NOTE": AIAction(
                "CREATE_NOTE", "Create a user note after approval.",
                {"type": "object", "required": ["module_id", "category", "topic", "title", "content"],
                 "properties": {
                     "module_id": {"type": "integer"}, "session_id": {"type": ["integer", "null"]},
                     "category": {"type": "string"}, "topic": {"type": "string"},
                     "title": {"type": "string"}, "content": {"type": "string"},
                     "source": {"type": "string"},
                 }},
                True, _note,
            ),
            "CREATE_ROUTINE_PROPOSAL": AIAction(
                "CREATE_ROUTINE_PROPOSAL", "Create a routine only after explicit approval.",
                {"type": "object", "required": ["name", "frequency", "start_date", "time_local",
                                                "duration_minutes", "timezone"],
                 "properties": {
                     "name": {"type": "string"}, "description": {"type": "string"},
                     "category": {"type": "string"}, "frequency": {"type": "string"},
                     "start_date": {"type": "string"}, "end_date": {"type": ["string", "null"]},
                     "time_local": {"type": "string"}, "duration_minutes": {"type": "integer"},
                     "timezone": {"type": "string"}, "selected_days": {"type": "array"},
                 }},
                True, _routine,
            ),
            "CREATE_STUDY_PLAN_PROPOSAL": AIAction(
                "CREATE_STUDY_PLAN_PROPOSAL", "Store no authoritative timetable changes; return a plan artifact.",
                {"type": "object", "required": ["title", "plan"], "properties": {
                    "title": {"type": "string"}, "plan": {"type": "array"},
                }},
                True, lambda _c, _u, payload: {"status": "PLAN_ACCEPTED", **payload},
            ),
            "CREATE_MENTOR_RECOMMENDATION": AIAction(
                "CREATE_MENTOR_RECOMMENDATION", "Return an evidence-backed mentor recommendation.",
                {"type": "object", "required": ["topic", "reason"], "properties": {
                    "topic": {"type": "string"}, "reason": {"type": "string"},
                    "priority": {"type": "string"},
                }},
                True, lambda _c, _u, payload: {"status": "RECOMMENDATION_ACCEPTED", **payload},
            ),
            "SCHEDULE_NOTIFICATION_PROPOSAL": AIAction(
                "SCHEDULE_NOTIFICATION_PROPOSAL", "Schedule through the existing notification service.",
                {"type": "object", "required": ["title", "body", "scheduled_at"], "properties": {
                    "title": {"type": "string"}, "body": {"type": "string"},
                    "scheduled_at": {"type": "string"}, "priority": {"type": "string"},
                }},
                True, _schedule_notification,
            ),
        }

    def get(self, name: str) -> AIAction:
        try:
            return self._actions[name]
        except KeyError as exc:
            raise ValueError("Unknown AI action.") from exc

    def names(self):
        return tuple(self._actions)

    def execute(self, name, connection, user_id, payload):
        return self.get(name).execute(connection, user_id, payload)


def _schedule_notification(connection, user_id, payload):
    from notifications.repository import create_notification
    from notifications.repository import get_preferences
    if not get_preferences(connection, user_id)["notifications_enabled"]:
        raise ValueError("Notification preferences disable AI-scheduled notifications.")
    return create_notification(
        connection, user_id, "SYSTEM", payload["title"], payload["body"],
        payload["scheduled_at"], priority=payload.get("priority", "NORMAL"),
        metadata={"source": "advanced_ai"},
    )


ActionRegistry = AIActionRegistry
