import sqlite3
import logging
import os
from datetime import date, datetime, timedelta, timezone
from services.schedule_status import session_status

from database.repositories.attendance_repository import (
    get_attendance as repository_get_attendance,
    list_attendance as repository_list_attendance,
    upsert_attendance,
)
from database.repositories.session_repository import get_session, list_sessions
from services.module_service import get_module

GRACE_PERIOD = timedelta(minutes=15)
_logger = logging.getLogger(__name__)


def _session_start(session: sqlite3.Row) -> datetime:
    try:
        session_date = date.fromisoformat(session["session_date"])
        scheduled = datetime.strptime(session["scheduled_time"], "%I:%M %p").time()
    except (TypeError, ValueError) as error:
        raise ValueError("The session has an invalid date or scheduled time.") from error
    return datetime.combine(session_date, scheduled)


def calculate_status(
    session: sqlite3.Row, attendance: sqlite3.Row | None, now: datetime | None = None
) -> str:
    if attendance and attendance["status"] == "Attended":
        return "Attended"
    current_time = now or datetime.now()
    start = _session_start(session)
    if current_time < start:
        return "Upcoming"
    if current_time <= start + GRACE_PERIOD:
        return "Current"
    return "Missed"


def get_attendance(
    connection: sqlite3.Connection, user_id: str, session_id: int
) -> sqlite3.Row | None:
    return repository_get_attendance(connection, user_id, session_id)


def get_attendance_for_session(
    connection: sqlite3.Connection, user_id: str, session_id: int
) -> sqlite3.Row | None:
    return get_attendance(connection, user_id, session_id)


def get_attendance_for_module(
    connection: sqlite3.Connection, user_id: str, module_id: int
) -> list[sqlite3.Row]:
    get_module(connection, module_id, user_id)
    return repository_list_attendance(connection, user_id, module_id)


def get_session_status(
    connection: sqlite3.Connection,
    user_id: str,
    session: sqlite3.Row,
    now: datetime | None = None,
    persist_missed: bool = True,
) -> str:
    attendance = get_attendance(connection, user_id, int(session["session_id"]))
    return get_attendance_display_state(
        connection, user_id, session, now, persist_missed
    )["display_status"]


def get_attendance_display_state(
    connection: sqlite3.Connection,
    user_id: str,
    session: sqlite3.Row,
    now: datetime | None = None,
    persist_missed: bool = True,
) -> dict[str, object]:
    """Return the sole persisted-evidence-backed Attendance display decision."""
    session_id = int(session["session_id"])
    module_id = int(session["module_id"])
    timing_status = session_status(dict(session), now=now)
    attendance = get_attendance(connection, user_id, session_id)
    evidence_note = None
    if (
        attendance
        and attendance["status"] == "Attended"
        and attendance["evidence_source"] == "save_notes"
        and attendance["evidence_note_id"] is not None
    ):
        evidence_note = connection.execute(
            """SELECT note_id, user_id, module_id, session_id, category,
                      created_at, saved_at, source, context_id
               FROM learning_notes
               WHERE note_id=? AND user_id=? AND module_id=? AND session_id=?
               LIMIT 1""",
            (
                attendance["evidence_note_id"],
                user_id,
                module_id,
                session_id,
            ),
        ).fetchone()
    evidence_valid = evidence_note is not None
    attended = bool(
        attendance
        and attendance["status"] == "Attended"
        and evidence_valid
    )
    display_status = (
        "Attended"
        if attended
        else "Missed"
        if attendance and attendance["status"] == "Missed"
        else timing_status
    )
    result = {
        "session_status": timing_status,
        "attended": attended,
        "display_status": display_status,
        "evidence_valid": evidence_valid,
        "session_id": session_id,
        "module_id": module_id,
        "attendance": attendance,
        "evidence_note": evidence_note,
    }
    if os.getenv("SHYAM_ACADEMY_ATTENDANCE_DEBUG") == "1":
        _logger.warning(
            "ATTENDANCE DEBUG uid=%s session_id=%s module_id=%s date=%s "
            "start=%s end=%s now=%s session_status=%s attendance_id=%s "
            "attendance_status=%s evidence_note_id=%s evidence_valid=%s "
            "rendered_status=%s rendered_color=%s",
            user_id, session_id, module_id, session["session_date"],
            session["scheduled_time"], session["scheduled_end_time"],
            datetime.now().astimezone(), timing_status,
            attendance["attendance_id"] if attendance else None,
            attendance["status"] if attendance else None,
            attendance["evidence_note_id"] if attendance else None,
            evidence_valid, display_status,
            "green" if attended else "non-green",
        )
    return result


def refresh_module_statuses(
    connection: sqlite3.Connection, user_id: str, module_id: int,
    now: datetime | None = None,
) -> dict[int, str]:
    get_module(connection, module_id, user_id)
    return {
        int(session["session_id"]): get_attendance_display_state(
            connection, user_id, session, now
        )["display_status"]
        for session in list_sessions(connection, module_id, user_id)
    }


def mark_attended(
    connection: sqlite3.Connection, user_id: str, session_id: int
) -> str:
    session = get_session(connection, session_id, user_id)
    if session is None:
        raise ValueError("The selected session could not be found.")
    existing = get_attendance(connection, user_id, session_id)
    if existing and existing["status"] == "Missed":
        return "Missed"
    upsert_attendance(
        connection, user_id, int(session["module_id"]), session_id, "Attended",
        session["session_date"], session["scheduled_time"],
        datetime.now(timezone.utc).isoformat(),
    )
    from notifications.service import suppress_missed_for_completion
    suppress_missed_for_completion(connection, user_id, session_id)
    return "Attended"


def mark_attended_from_note(
    connection: sqlite3.Connection,
    user_id: str,
    session_id: int,
    note_id: int,
) -> str:
    session = get_session(connection, session_id, user_id)
    note = connection.execute(
        """SELECT note_id, module_id, session_id
           FROM learning_notes
           WHERE note_id=? AND user_id=?""",
        (note_id, user_id),
    ).fetchone()
    if session is None or note is None:
        raise ValueError("The selected session note could not be found.")
    if (
        int(note["session_id"] or 0) != session_id
        or int(note["module_id"]) != int(session["module_id"])
    ):
        raise ValueError("The note is not linked to the selected timetable session.")
    existing = get_attendance(connection, user_id, session_id)
    if existing and existing["status"] == "Missed":
        return "Missed"
    upsert_attendance(
        connection, user_id, int(session["module_id"]), session_id, "Attended",
        session["session_date"], session["scheduled_time"],
        datetime.now(timezone.utc).isoformat(), note_id, "save_notes",
    )
    from notifications.service import suppress_missed_for_completion
    suppress_missed_for_completion(connection, user_id, session_id)
    return "Attended"


def mark_missed(
    connection: sqlite3.Connection, user_id: str, session_id: int
) -> str:
    session = get_session(connection, session_id, user_id)
    if session is None:
        raise ValueError("The selected session could not be found.")
    existing = get_attendance(connection, user_id, session_id)
    if existing and existing["status"] == "Attended":
        return "Attended"
    upsert_attendance(
        connection, user_id, int(session["module_id"]), session_id, "Missed",
        session["session_date"], session["scheduled_time"],
    )
    return "Missed"


def attendance_summary(
    connection: sqlite3.Connection, user_id: str, module_id: int,
    now: datetime | None = None,
) -> dict[str, int | float]:
    sessions = list_sessions(connection, module_id, user_id)
    statuses = [
        get_session_status(connection, user_id, session, now)
        for session in sessions
    ]
    attended = statuses.count("Attended")
    missed = statuses.count("Missed")
    completed = attended + missed
    return {
        "total": len(statuses),
        "attended": attended,
        "missed": missed,
        "upcoming": statuses.count("Upcoming") + statuses.count("Current"),
        "percentage": round(attended / completed * 100, 1) if completed else 0.0,
    }


def record_learning_completion(
    connection: sqlite3.Connection, user_id: str, session_id: int
) -> str:
    """Compatibility boundary; generation alone does not create attendance."""
    session = get_session(connection, session_id, user_id)
    if session is None:
        raise ValueError("The selected session could not be found.")
    return get_session_status(connection, user_id, session)
