"""Read-only, schema-validated tools exposed to Advanced AI."""

from dataclasses import dataclass
from typing import Any, Callable

from ai.context import build_context


@dataclass(frozen=True)
class AITool:
    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Callable

    def invoke(self, connection, user_id: str, arguments: dict[str, Any],
               authenticated_user_id: str | None = None):
        if not isinstance(arguments, dict):
            raise ValueError("Tool arguments must be an object.")
        allowed = set(self.input_schema.get("properties", {}))
        required = set(self.input_schema.get("required", []))
        unknown = set(arguments) - allowed
        missing = required - set(arguments)
        if unknown or missing:
            raise ValueError("Tool arguments do not match the declared schema.")
        for key, rule in self.input_schema.get("properties", {}).items():
            if key not in arguments:
                continue
            value = arguments[key]
            kinds = rule.get("type")
            if isinstance(kinds, str):
                kinds = [kinds]
            if kinds and not (
                ("integer" in kinds and isinstance(value, int) and not isinstance(value, bool))
                or ("string" in kinds and isinstance(value, str))
                or ("array" in kinds and isinstance(value, list))
                or ("null" in kinds and value is None)
            ):
                raise ValueError(f"Tool argument '{key}' has an invalid type.")
        return self.handler(
            connection, user_id, arguments,
            authenticated_user_id=authenticated_user_id,
        )


def _context_tool(section: str, limit: int = 10):
    def handler(connection, user_id, arguments, authenticated_user_id=None):
        context = build_context(
            connection, user_id, "TOOL",
            authenticated_user_id=authenticated_user_id,
            session_id=arguments.get("session_id"),
            module_id=arguments.get("module_id"),
            limits={section: max(1, min(int(arguments.get("limit", limit)), limit))},
        )
        value = getattr(context, section)
        if section == "progress":
            value = value.get("weak_areas", []) if arguments.get("_weak_areas") else value
        return list(value) if isinstance(value, tuple) else value
    return handler


class AIToolRegistry:
    def __init__(self):
        schema = {
            "type": "object",
            "properties": {
                "module_id": {"type": "integer"},
                "session_id": {"type": "integer"},
                "limit": {"type": "integer"},
            },
            "required": [],
        }
        self._tools = {
            "get_current_session": AITool(
                "get_current_session", "Get one authorized current session.",
                {**schema, "properties": {"session_id": {"type": "integer"}},
                 "required": ["session_id"]},
                lambda c, u, a, authenticated_user_id=None:
                build_context(c, u, "TOOL", authenticated_user_id=authenticated_user_id,
                              session_id=a["session_id"]).current_session,
            ),
        }
        for name, section in (
            ("get_today_timetable", "timetable"), ("get_recent_progress", "progress"),
            ("get_weak_areas", "progress"), ("get_recent_tests", "tests"),
            ("get_interview_history", "interviews"), ("get_notes", "notes"),
            ("get_today_routines", "routines"), ("get_recent_routine_history", "routines"),
            ("get_notifications", "notifications"),
        ):
            handler = _context_tool(section)
            if name == "get_weak_areas":
                def weak_handler(c, u, a, authenticated_user_id=None, h=handler):
                    a = dict(a)
                    a["_weak_areas"] = True
                    return h(c, u, a, authenticated_user_id)
                handler = weak_handler
            self._tools[name] = AITool(
                name, f"Read bounded {section} context.",
                schema, handler,
            )

    def get(self, name: str) -> AITool:
        try:
            return self._tools[name]
        except KeyError as exc:
            raise ValueError("Unknown AI tool.") from exc

    def names(self) -> tuple[str, ...]:
        return tuple(self._tools)

    def invoke(self, name: str, connection, user_id: str, arguments=None,
               *, authenticated_user_id: str | None = None):
        return self.get(name).invoke(
            connection, user_id, arguments or {},
            authenticated_user_id=authenticated_user_id,
        )


ToolRegistry = AIToolRegistry
