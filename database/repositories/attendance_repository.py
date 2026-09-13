import sqlite3
from datetime import datetime, timezone


def get_attendance(
    connection: sqlite3.Connection, user_id: str, session_id: int
) -> sqlite3.Row | None:
    return connection.execute(
        "SELECT * FROM attendance WHERE user_id = ? AND session_id = ?",
        (user_id, session_id),
    ).fetchone()


def list_attendance(
    connection: sqlite3.Connection, user_id: str, module_id: int
) -> list[sqlite3.Row]:
    return connection.execute(
        """
        SELECT * FROM attendance
        WHERE user_id = ? AND module_id = ?
        ORDER BY scheduled_date, scheduled_time, session_id
        """,
        (user_id, module_id),
    ).fetchall()


def upsert_attendance(
    connection: sqlite3.Connection,
    user_id: str,
    module_id: int,
    session_id: int,
    status: str,
    scheduled_date: str,
    scheduled_time: str,
    attended_at: str | None = None,
    evidence_note_id: int | None = None,
    evidence_source: str | None = None,
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    connection.execute(
        """
        INSERT INTO attendance
            (user_id, module_id, session_id, evidence_note_id, evidence_source,
             status, attended_at,
             scheduled_date, scheduled_time, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_id, session_id) DO UPDATE SET
            evidence_note_id = COALESCE(excluded.evidence_note_id, attendance.evidence_note_id),
            evidence_source = COALESCE(excluded.evidence_source, attendance.evidence_source),
            status = excluded.status,
            attended_at = COALESCE(excluded.attended_at, attendance.attended_at),
            scheduled_date = excluded.scheduled_date,
            scheduled_time = excluded.scheduled_time,
            updated_at = excluded.updated_at
        """,
        (
            user_id, module_id, session_id, evidence_note_id, evidence_source,
            status, attended_at,
            scheduled_date, scheduled_time, now, now,
        ),
    )
    connection.commit()
