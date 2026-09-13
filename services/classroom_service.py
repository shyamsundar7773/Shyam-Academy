"""Shared, provider-neutral conversation state for learning classrooms."""

from __future__ import annotations

import json
from datetime import datetime, timezone


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_history(connection, user_id: str, classroom_id: str) -> list[dict]:
    row = connection.execute(
        "SELECT history_json FROM classroom_conversations WHERE user_id=? AND classroom_id=?",
        (user_id, classroom_id),
    ).fetchone()
    if not row:
        return []
    try:
        value = json.loads(row["history_json"])
    except (TypeError, json.JSONDecodeError) as error:
        raise ValueError("The saved classroom conversation is corrupted.") from error
    if not isinstance(value, list) or any(
        not isinstance(item, dict)
        or item.get("role") not in {"user", "assistant"}
        or not isinstance(item.get("content"), str)
        for item in value
    ):
        raise ValueError("The saved classroom conversation is invalid.")
    return value


def save_history(
    connection, user_id: str, classroom_id: str, history: list[dict],
    title: str | None = None,
) -> None:
    if not user_id or not classroom_id:
        raise ValueError("A classroom identity is required.")
    if not isinstance(history, list) or any(
        not isinstance(item, dict)
        or item.get("role") not in {"user", "assistant"}
        or not isinstance(item.get("content"), str)
        or not item["content"].strip()
        for item in history
    ):
        raise ValueError("Classroom history is invalid.")
    connection.execute(
        """INSERT INTO classroom_conversations
           (user_id,classroom_id,title,history_json,created_at,updated_at)
           VALUES(?,?,?, ?,?,?)
           ON CONFLICT(user_id,classroom_id) DO UPDATE SET
             history_json=excluded.history_json, updated_at=excluded.updated_at""",
        (user_id, classroom_id, title or classroom_id,
         json.dumps(history, separators=(",", ":")), _now(), _now()),
    )
    connection.commit()


def clear_history(connection, user_id: str, classroom_id: str) -> None:
    """Clear the active transcript without touching notes or other user data."""
    if not user_id or not classroom_id:
        raise ValueError("A classroom identity is required.")
    connection.execute(
        "DELETE FROM classroom_conversations WHERE user_id=? AND classroom_id=?",
        (user_id, classroom_id),
    )
    connection.commit()


def rename_classroom(connection, user_id: str, classroom_id: str, title: str) -> None:
    if not title or not title.strip():
        raise ValueError("Classroom title is required.")
    now = _now()
    connection.execute(
        """INSERT INTO classroom_conversations
           (user_id, classroom_id, title, history_json, created_at, updated_at)
           VALUES (?, ?, ?, '[]', ?, ?)
           ON CONFLICT(user_id, classroom_id) DO UPDATE SET
             title=excluded.title, updated_at=excluded.updated_at""",
        (user_id, classroom_id, title.strip(), now, now),
    )
    connection.commit()


def get_classroom(connection, user_id: str, classroom_id: str) -> dict | None:
    row = connection.execute(
        "SELECT * FROM classroom_conversations WHERE user_id=? AND classroom_id=?",
        (user_id, classroom_id),
    ).fetchone()
    return dict(row) if row else None
