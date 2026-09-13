import sqlite3
from datetime import date, datetime
import re

from database.repositories.session_repository import (
    create_session,
    get_session,
    list_sessions,
    update_session,
)

CATEGORIES = (
    "Today Learning", "Level 1", "Level 2", "Problem Solving",
    "Test", "Interview Preparation",
    "Interview Room",
)
LEGACY_CATEGORY_ALIASES = {
    "On-time Test": "Test",
    "Daily Test": "Test",
    "Weekly Test": "Test",
}
TIME_PATTERN = re.compile(r"^(0?[1-9]|1[0-2]):[0-5][0-9] [AP]M$")


def get_timetable(connection: sqlite3.Connection, module_id: int, user_id: str):
    if not isinstance(module_id, int) or module_id <= 0:
        raise ValueError("Invalid module ID.")
    sessions = []
    for session in list_sessions(connection, module_id, user_id):
        row = dict(session)
        row["category"] = LEGACY_CATEGORY_ALIASES.get(row["category"], row["category"])
        sessions.append(row)
    return sessions


def get_session_details(connection: sqlite3.Connection, session_id: int, user_id: str):
    if not isinstance(session_id, int) or session_id <= 0:
        raise ValueError("Invalid session ID.")
    session = get_session(connection, session_id, user_id)
    if session is None:
        return None
    row = dict(session)
    row["category"] = LEGACY_CATEGORY_ALIASES.get(row["category"], row["category"])
    return row


def save_session(
    connection: sqlite3.Connection,
    session_id: int,
    scheduled_time: str,
    topic: str,
    prompt: str,
    status: str,
    user_id: str,
) -> None:
    if not isinstance(session_id, int) or session_id <= 0:
        raise ValueError("Invalid session ID.")
    if not TIME_PATTERN.fullmatch(scheduled_time.strip()):
        raise ValueError("Time must use the format h:mm AM or h:mm PM.")
    if not topic.strip():
        raise ValueError("Topic is required.")
    if status not in {"Scheduled", "Completed", "Skipped"}:
        raise ValueError("Invalid session status.")
    update_session(
        connection, session_id, scheduled_time.strip(), topic, prompt, status, user_id
    )
    from notifications.service import reschedule_session
    from alarms.service import reconcile_session_alarm
    session = get_session(connection, session_id, user_id)
    if session is not None:
        connection.execute(
            """UPDATE attendance
               SET scheduled_date=?, scheduled_time=?, updated_at=?
               WHERE user_id=? AND session_id=?""",
            (
                session["session_date"], session["scheduled_time"],
                datetime.now().isoformat(), user_id, session_id,
            ),
        )
        connection.commit()
        if status == "Scheduled":
            reschedule_session(connection, user_id, session)
        else:
            from alarms.service import cancel_session_alarm
            cancel_session_alarm(connection, user_id, session_id)
        reconcile_session_alarm(connection, user_id, session)


def add_session(
    connection: sqlite3.Connection,
    module_id: int,
    day_number: int,
    session_date: str,
    category: str,
    topic: str,
    scheduled_time: str,
    prompt: str,
    user_id: str,
) -> int:
    if not isinstance(module_id, int) or module_id <= 0:
        raise ValueError("Invalid module ID.")
    if not isinstance(day_number, int) or day_number <= 0:
        raise ValueError("Day number must be positive.")
    try:
        date.fromisoformat(session_date)
    except ValueError as error:
        raise ValueError("Session date must be a valid date.") from error
    category = LEGACY_CATEGORY_ALIASES.get(category, category)
    if category not in CATEGORIES:
        raise ValueError("Invalid session category.")
    if not topic.strip():
        raise ValueError("Topic is required.")
    if not TIME_PATTERN.fullmatch(scheduled_time.strip()):
        raise ValueError("Time must use the format h:mm AM or h:mm PM.")
    try:
        session_id = create_session(
            connection, module_id, day_number, session_date, category, topic,
            scheduled_time.strip(), prompt, user_id
        )
        from notifications.service import schedule_session_notifications
        from alarms.service import reconcile_session_alarm
        session = get_session(connection, session_id, user_id)
        schedule_session_notifications(connection, user_id, session)
        reconcile_session_alarm(connection, user_id, session)
        return session_id
    except sqlite3.IntegrityError as error:
        raise ValueError("The selected module does not exist.") from error


def seed_development_timetable(connection: sqlite3.Connection, user_id: str) -> None:
    marker = connection.execute(
        "SELECT user_id FROM user_bootstrap WHERE user_id=?", (user_id,)
    ).fetchone()
    if marker:
        return
    modules = connection.execute(
        "SELECT module_id FROM modules WHERE module_name = ? AND owner_user_id = ?",
        ("SQL Developer", user_id),
    ).fetchone()
    if modules is None:
        existing_any = connection.execute(
            "SELECT 1 FROM modules WHERE owner_user_id=? LIMIT 1", (user_id,)
        ).fetchone()
        if existing_any:
            connection.execute(
                "INSERT INTO user_bootstrap(user_id, initialized_at) VALUES (?, ?)",
                (user_id, datetime.now().isoformat()),
            )
            connection.commit()
            return
        from database.repositories.module_repository import create_module

        module_id = create_module(
            connection,
            "SQL Developer",
            "SQL Developer career preparation",
            user_id,
        )
    else:
        module_id = int(modules["module_id"])

    existing = connection.execute(
        "SELECT COUNT(*) AS count FROM sessions WHERE module_id = ? AND owner_user_id = ?",
        (module_id, user_id),
    ).fetchone()["count"]
    if existing:
        return

    samples = [
        (1, "2026-09-13", "Today Learning", "SQL foundations", "09:00 AM",
         "Study SQL foundations and explain the relational model."),
        (1, "2026-09-13", "Level 1", "SELECT and WHERE", "11:00 AM",
         "Learn SELECT and WHERE clauses with practical SQL examples."),
        (1, "2026-09-13", "Level 2", "JOIN fundamentals", "02:00 PM",
         "Understand INNER JOIN and LEFT JOIN using two related tables."),
        (1, "2026-09-13", "Problem Solving", "Filtering practice", "05:00 PM",
         "Solve filtering exercises using WHERE, IN, BETWEEN, and LIKE."),
        (2, "2026-09-14", "Today Learning", "Aggregate functions", "09:00 AM",
         "Learn COUNT, SUM, AVG, MIN, and MAX."),
        (2, "2026-09-14", "Test", "SQL basics review", "05:00 PM",
         "Review SQL basics and answer a short practice set."),
        (3, "2026-09-15", "Interview Preparation", "SQL interview questions", "11:00 AM",
         "Practice explaining common SQL interview questions clearly."),
    ]
    for day, session_date, category, topic, scheduled_time, prompt in samples:
        add_session(
            connection,             module_id, day, session_date, LEGACY_CATEGORY_ALIASES.get(category, category), topic,
            scheduled_time, prompt, user_id
        )
    connection.execute(
        "INSERT INTO user_bootstrap(user_id, initialized_at) VALUES (?, ?)",
        (user_id, datetime.now().isoformat()),
    )
    connection.commit()
