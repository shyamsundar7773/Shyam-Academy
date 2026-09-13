import sqlite3
from datetime import datetime, timezone


def list_sessions(
    connection: sqlite3.Connection, module_id: int, owner_user_id: str
) -> list[sqlite3.Row]:
    return connection.execute(
        """
        SELECT * FROM sessions
        WHERE module_id = ? AND owner_user_id = ?
        ORDER BY day_number, session_date, scheduled_time, session_id
        """,
        (module_id, owner_user_id),
    ).fetchall()


def get_session(
    connection: sqlite3.Connection, session_id: int, owner_user_id: str
) -> sqlite3.Row | None:
    return connection.execute(
        """
        SELECT s.*, m.module_name
        FROM sessions s
        JOIN modules m ON m.module_id = s.module_id
        WHERE s.session_id = ? AND s.owner_user_id = ?
        """,
        (session_id, owner_user_id),
    ).fetchone()


def create_session(
    connection: sqlite3.Connection,
    module_id: int,
    day_number: int,
    session_date: str,
    category: str,
    topic: str,
    scheduled_time: str,
    prompt: str,
    owner_user_id: str,
) -> int:
    now = datetime.now(timezone.utc).isoformat()
    cursor = connection.execute(
        """
        INSERT INTO sessions
            (module_id, day_number, session_date, category, topic, scheduled_time,
             prompt, status, owner_user_id, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'Scheduled', ?, ?, ?)
        """,
        (
            module_id,
            day_number,
            session_date,
            category,
            topic,
            scheduled_time,
            prompt,
            owner_user_id,
            now,
            now,
        ),
    )
    connection.commit()
    return int(cursor.lastrowid)


def update_session(
    connection: sqlite3.Connection,
    session_id: int,
    scheduled_time: str,
    topic: str,
    prompt: str,
    status: str,
    owner_user_id: str,
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    cursor = connection.execute(
        """
        UPDATE sessions
        SET scheduled_time = ?, topic = ?, prompt = ?, status = ?, updated_at = ?
        WHERE session_id = ? AND owner_user_id = ?
        """,
        (scheduled_time, topic.strip(), prompt.strip(), status, now, session_id, owner_user_id),
    )
    if cursor.rowcount != 1:
        raise ValueError("The selected session could not be updated.")
    connection.commit()
