import sqlite3

import pytest

from database.schema import initialize_database
from services.doubt_service import save_doubt
from services.classroom_service import load_history, save_history


def test_doubt_can_persist_without_a_module():
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    initialize_database(connection)
    note_id = save_doubt(
        connection, "firebase-user-a", "doubt_general_firebase-user-a",
        "JOIN confusion",
        [{"role": "user", "content": "Why use a join?"},
         {"role": "assistant", "content": "A join combines related rows."}],
    )
    row = connection.execute(
        "SELECT * FROM doubt_notes WHERE doubt_note_id=?", (note_id,)
    ).fetchone()
    assert row["user_id"] == "firebase-user-a"
    assert row["title"] == "JOIN confusion"
    assert "combines related rows" in row["content"]


def test_doubt_classroom_history_is_user_isolated():
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    initialize_database(connection)
    save_history(
        connection, "firebase-user-a", "doubt_general_firebase-user-a",
        [{"role": "assistant", "content": "Private answer"}],
    )
    assert load_history(
        connection, "firebase-user-b", "doubt_general_firebase-user-a"
    ) == []


def test_doubt_notes_remain_persistent_and_user_scoped_for_management():
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    initialize_database(connection)
    note_id = save_doubt(
        connection, "firebase-user-a", "doubt_general_firebase-user-a",
        "Persistent doubt",
        [{"role": "assistant", "content": "Saved explanation"}],
    )
    assert connection.execute(
        "SELECT COUNT(*) FROM doubt_notes WHERE user_id=? AND doubt_note_id=?",
        ("firebase-user-a", note_id),
    ).fetchone()[0] == 1
    assert connection.execute(
        "SELECT COUNT(*) FROM doubt_notes WHERE user_id=? AND doubt_note_id=?",
        ("firebase-user-b", note_id),
    ).fetchone()[0] == 0
