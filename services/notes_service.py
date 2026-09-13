import sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo

from database.repositories.note_repository import (
    create_note,
    delete_note,
    get_note,
    list_notes,
    update_note,
)
from services.module_service import get_module


def _validate_note_data(
    connection: sqlite3.Connection,
    user_id: str,
    module_id: int,
    category: str,
    topic: str,
    title: str,
    content: str,
) -> None:
    get_module(connection, module_id, user_id)
    if not category.strip():
        raise ValueError("Note category is required.")
    if not topic.strip():
        raise ValueError("Note topic is required.")
    if not title.strip():
        raise ValueError("Note title is required.")
    if not content.strip():
        raise ValueError("Note content is required.")


def save_note(
    connection: sqlite3.Connection,
    user_id: str,
    module_id: int,
    session_id: int | None,
    category: str,
    topic: str,
    title: str,
    content: str,
    source: str = "AI classroom",
    context_id: str = "",
) -> tuple[int, int]:
    _validate_note_data(
        connection, user_id, module_id, category, topic, title, content
    )
    note_id = create_note(
        connection, user_id, module_id, session_id, category, topic,
        title, content, source, context_id
    )
    row = get_note(connection, note_id, user_id)
    return note_id, int(row["learning_number"])


def get_user_note(connection: sqlite3.Connection, note_id: int, user_id: str):
    if not isinstance(note_id, int) or note_id <= 0:
        raise ValueError("Invalid note ID.")
    note = get_note(connection, note_id, user_id)
    if note is None:
        raise ValueError("The selected note could not be found.")
    return note


def find_notes(
    connection: sqlite3.Connection,
    user_id: str,
    module_id: int | None = None,
    category: str | None = None,
    search: str = "",
):
    if module_id is not None:
        get_module(connection, module_id, user_id)
    return [dict(note) for note in list_notes(connection, user_id, module_id, category, search)]


def find_notes_for_selection(
    connection: sqlite3.Connection,
    user_id: str,
    module_id: int,
    note_date: str,
    category: str,
) -> list[dict]:
    """Return only notes belonging to one user/module/date/category cell."""
    get_module(connection, module_id, user_id)
    canonical = {"On-time Test": "Test", "Daily Test": "Test", "Weekly Test": "Test"}
    rows = connection.execute(
        """
        SELECT n.*, m.module_name, s.session_date, s.scheduled_time,
               s.day_number, s.category AS session_category
        FROM learning_notes n
        JOIN modules m ON m.module_id = n.module_id
        LEFT JOIN sessions s ON s.session_id = n.session_id
        WHERE n.user_id = ? AND n.module_id = ?
          AND n.category IN (?, ?, ?, ?)
        ORDER BY n.saved_at, n.note_id
        """,
        (user_id, module_id, category, "On-time Test", "Daily Test", "Weekly Test"),
    ).fetchall()
    result = []
    local_zone = ZoneInfo("Asia/Kolkata")
    for row in rows:
        item = dict(row)
        item["category"] = canonical.get(item["category"], item["category"])
        saved_at = datetime.fromisoformat(item["saved_at"].replace("Z", "+00:00"))
        saved_date = saved_at.astimezone(local_zone).date().isoformat()
        item["note_date"] = item["session_date"] or saved_date
        if item["category"] == category and item["note_date"] == note_date:
            result.append(item)
    return result


def find_notes_for_cell(
    connection: sqlite3.Connection,
    user_id: str,
    note_date: str,
    category: str,
    module_ids: list[int],
) -> list[dict]:
    """Return notes for one My Notes date/category cell."""
    if not module_ids:
        return []
    return [
        note
        for module_id in module_ids
        for note in find_notes_for_selection(
            connection, user_id, int(module_id), note_date, category
        )
    ]


def edit_note(
    connection: sqlite3.Connection,
    note_id: int,
    user_id: str,
    title: str,
    content: str,
) -> None:
    get_user_note(connection, note_id, user_id)
    update_note(connection, note_id, user_id, title, content)


def remove_note(connection: sqlite3.Connection, note_id: int, user_id: str) -> None:
    get_user_note(connection, note_id, user_id)
    delete_note(connection, note_id, user_id)
