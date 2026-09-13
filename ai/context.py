"""Bounded, deterministic, user-scoped context for Advanced AI tasks."""

from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from typing import Any

from services.progress_service import get_progress_snapshot
from services.routine_service import get_history
from database.repositories import progress_repository
from database.repositories import routine_repository


@dataclass(frozen=True)
class AIContext:
    user_id: str
    task_type: str
    current_session: dict[str, Any] | None = None
    timetable: tuple[dict[str, Any], ...] = ()
    learning: dict[str, Any] = field(default_factory=dict)
    notes: tuple[dict[str, Any], ...] = ()
    attendance: tuple[dict[str, Any], ...] = ()
    tests: tuple[dict[str, Any], ...] = ()
    interviews: tuple[dict[str, Any], ...] = ()
    progress: dict[str, Any] = field(default_factory=dict)
    mentor: tuple[dict[str, Any], ...] = ()
    routines: tuple[dict[str, Any], ...] = ()
    notifications: tuple[dict[str, Any], ...] = ()
    references: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _require_identity(user_id: str, authenticated_user_id: str | None = None) -> str:
    if not isinstance(user_id, str) or not user_id.strip():
        raise ValueError("A user identity is required.")
    if authenticated_user_id is not None and user_id != authenticated_user_id:
        raise PermissionError("AI context identity does not match the authenticated user.")
    return user_id.strip()


def _dicts(rows, limit):
    return tuple(dict(row) for row in list(rows)[:limit])


def _safe_session(connection, session_id, user_id):
    if session_id is None:
        return None
    row = connection.execute(
        """SELECT session_id,module_id,session_date,category,topic,scheduled_time,
        scheduled_end_time,prompt,status FROM sessions
        WHERE session_id=? AND owner_user_id=?""", (session_id, user_id)
    ).fetchone()
    return dict(row) if row else None


def build_context(connection, user_id: str, task_type: str = "GENERAL_ACADEMIC_ASSIST",
                  *, authenticated_user_id: str | None = None, session_id: int | None = None,
                  module_id: int | None = None, now: datetime | None = None,
                  limits: dict[str, int] | None = None) -> AIContext:
    user_id = _require_identity(user_id, authenticated_user_id)
    now = now or datetime.now()
    limits = {
        "timetable": 8, "notes": 5, "attendance": 8, "tests": 5,
        "interviews": 5, "mentor": 5, "routines": 8, "notifications": 5,
        **(limits or {}),
    }
    current = _safe_session(connection, session_id, user_id)
    sessions = progress_repository.list_sessions(connection, user_id, module_id)
    timetable = _dicts(sessions, limits["timetable"])
    notes = _dicts(progress_repository.list_notes(connection, user_id, module_id), limits["notes"])
    attempts = _dicts(progress_repository.list_attempts(connection, user_id, module_id), limits["tests"])
    interviews = _dicts(progress_repository.list_interviews(connection, user_id, module_id), limits["interviews"])
    attendance = _dicts(
        connection.execute(
            """SELECT session_id,status,scheduled_date,scheduled_time,attended_at
            FROM attendance WHERE user_id=? ORDER BY scheduled_date DESC LIMIT ?""",
            (user_id, limits["attendance"]),
        ).fetchall(), limits["attendance"]
    )
    progress = asdict(get_progress_snapshot(connection, user_id, module_id, now=now))
    progress.pop("modules", None)
    progress.pop("categories", None)
    progress.pop("topics", None)
    mentor = _dicts(
        connection.execute(
            """SELECT role,message,action_type,created_at FROM mentor_messages
            WHERE user_id=? ORDER BY created_at DESC LIMIT ?""",
            (user_id, limits["mentor"]),
        ).fetchall(), limits["mentor"]
    )
    routines = _dicts(
        get_history(connection, user_id, start=now.date().isoformat(),
                    end=now.date().isoformat())[:limits["routines"]], limits["routines"]
    )
    notifications = _dicts(
        connection.execute(
            """SELECT type,title,scheduled_at,status FROM notifications
            WHERE user_id=? ORDER BY scheduled_at DESC LIMIT ?""",
            (user_id, limits["notifications"]),
        ).fetchall(), limits["notifications"]
    )
    learning = {
        "pending_sessions": [
            item for item in timetable
            if item.get("attendance_status") not in {"Attended", "Missed"}
        ][:5],
        "recent_notes": len(notes),
    }
    references = tuple(
        name for name, values in (
            ("timetable", timetable), ("learning", learning), ("notes", notes),
            ("attendance", attendance), ("tests", attempts), ("interviews", interviews),
            ("progress", progress), ("mentor", mentor), ("routines", routines),
            ("notifications", notifications),
        ) if values
    )
    return AIContext(
        user_id=user_id, task_type=str(task_type), current_session=current,
        timetable=timetable, learning=learning, notes=notes, attendance=attendance,
        tests=attempts, interviews=interviews, progress=progress, mentor=mentor,
        routines=routines, notifications=notifications, references=references,
    )


class CrossSystemContextBuilder:
    """Reusable facade used by orchestrators and future API/voice clients."""

    def __init__(self, connection, authenticated_user_id: str | None = None):
        self.connection = connection
        self.authenticated_user_id = authenticated_user_id

    def build(self, user_id: str, task_type: str, **kwargs) -> AIContext:
        return build_context(
            self.connection, user_id, task_type,
            authenticated_user_id=self.authenticated_user_id, **kwargs
        )


ContextBuilder = CrossSystemContextBuilder
AIContextBuilder = CrossSystemContextBuilder
