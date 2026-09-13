import sqlite3
from datetime import datetime, timezone


def _next_learning_number(
    connection: sqlite3.Connection, user_id: str, module_id: int, category: str, topic: str
) -> int:
    row = connection.execute(
        """
        SELECT COALESCE(MAX(learning_number), 0) + 1 AS next_number
        FROM learning_notes
        WHERE user_id = ? AND module_id = ? AND category = ? AND topic = ?
        """,
        (user_id, module_id, category, topic),
    ).fetchone()
    return int(row["next_number"])


def create_note(
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
) -> int:
    now = datetime.now(timezone.utc).isoformat()
    learning_number = _next_learning_number(
        connection, user_id, module_id, category, topic
    )
    cursor = connection.execute(
        """
        INSERT INTO learning_notes
            (user_id, module_id, session_id, category, topic, title, content,
             learning_number, saved_at, created_at, updated_at, source, context_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user_id, module_id, session_id, category, topic, title.strip(),
            content, learning_number, now, now, now, source.strip() or "AI classroom",
            context_id.strip(),
        ),
    )
    connection.commit()
    return int(cursor.lastrowid)


def get_note(
    connection: sqlite3.Connection, note_id: int, user_id: str
) -> sqlite3.Row | None:
    return connection.execute(
        """
        SELECT n.*, m.module_name
        FROM learning_notes n
        JOIN modules m ON m.module_id = n.module_id
        WHERE n.note_id = ? AND n.user_id = ?
        """,
        (note_id, user_id),
    ).fetchone()


def list_notes(
    connection: sqlite3.Connection,
    user_id: str,
    module_id: int | None = None,
    category: str | None = None,
    search: str = "",
) -> list[sqlite3.Row]:
    clauses = ["n.user_id = ?"]
    params: list[object] = [user_id]
    if module_id is not None:
        clauses.append("n.module_id = ?")
        params.append(module_id)
    if category and category != "All categories":
        clauses.append("n.category = ?")
        params.append(category)
    if search.strip():
        clauses.append("(n.topic LIKE ? OR n.title LIKE ?)")
        value = f"%{search.strip()}%"
        params.extend([value, value])
    return connection.execute(
        f"""
        SELECT n.note_id, n.module_id, n.category, n.topic, n.title, n.content,
               n.learning_number, n.saved_at, n.created_at, n.session_id,
               n.context_id, m.module_name
        FROM learning_notes n
        JOIN modules m ON m.module_id = n.module_id
        WHERE {' AND '.join(clauses)}
        ORDER BY m.module_name, n.category, n.topic, n.learning_number
        """,
        params,
    ).fetchall()


def update_note(
    connection: sqlite3.Connection,
    note_id: int,
    user_id: str,
    title: str,
    content: str,
) -> None:
    if not title.strip() or not content.strip():
        raise ValueError("Note title and content are required.")
    cursor = connection.execute(
        """
        UPDATE learning_notes
        SET title = ?, content = ?, updated_at = ?
        WHERE note_id = ? AND user_id = ?
        """,
        (title.strip(), content, datetime.now(timezone.utc).isoformat(), note_id, user_id),
    )
    if cursor.rowcount != 1:
        raise ValueError("The selected note could not be updated.")
    connection.commit()


def delete_note(connection: sqlite3.Connection, note_id: int, user_id: str) -> None:
    cursor = connection.execute(
        "DELETE FROM learning_notes WHERE note_id = ? AND user_id = ?",
        (note_id, user_id),
    )
    if cursor.rowcount != 1:
        raise ValueError("The selected note could not be deleted.")
    connection.commit()
