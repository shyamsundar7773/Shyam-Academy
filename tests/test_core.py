import sqlite3

import pytest

from database.schema import initialize_database
from services.module_service import add_module, edit_module, get_module
from services.session_service import get_learning_context
from services.timetable_service import add_session, get_session_details, save_session


@pytest.fixture
def connection():
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    initialize_database(connection)
    yield connection
    connection.close()


def create_test_module(connection, user_id="user-a"):
    return add_module(connection, "SQL Developer", "SQL preparation", user_id)


def test_module_create_retrieve_edit_and_validation(connection):
    module_id = create_test_module(connection)
    assert get_module(connection, module_id, "user-a")["module_name"] == "SQL Developer"
    edit_module(connection, module_id, "Python Developer", "Python preparation", "user-a")
    module = get_module(connection, module_id, "user-a")
    assert module["module_name"] == "Python Developer"
    assert module["description"] == "Python preparation"
    with pytest.raises(ValueError):
        add_module(connection, "  ", "", "user-a")
    with pytest.raises(ValueError):
        add_module(connection, "Python Developer", "", "user-a")


def test_session_create_update_preserves_identity_and_prompt(connection):
    module_id = create_test_module(connection)
    session_id = add_session(
        connection, module_id, 1, "2026-09-13", "Level 1",
        "SELECT and WHERE", "11:00 AM", "Teach SELECT.", "user-a"
    )
    save_session(
        connection, session_id, "11:30 AM", "SELECT and WHERE",
        "Teach SELECT with interview examples.", "Scheduled", "user-a"
    )
    session = get_session_details(connection, session_id, "user-a")
    assert session["session_id"] == session_id
    assert session["scheduled_time"] == "11:30 AM"
    assert session["prompt"] == "Teach SELECT with interview examples."
    assert connection.execute(
        "SELECT COUNT(*) FROM sessions WHERE module_id = ?", (module_id,)
    ).fetchone()[0] == 1


def test_session_validation_and_module_reference(connection):
    module_id = create_test_module(connection)
    with pytest.raises(ValueError):
        add_session(
            connection, 999, 1, "2026-09-13", "Level 1",
            "Topic", "11:00 AM", "Prompt", "user-a"
        )
    with pytest.raises(ValueError):
        add_session(
            connection, module_id, 1, "not-a-date", "Level 1",
            "Topic", "11:00 AM", "Prompt", "user-a"
        )
    with pytest.raises(ValueError):
        add_session(
            connection, module_id, 1, "2026-09-13", "Level 1",
            "Topic", "25:00 PM", "Prompt", "user-a"
        )


def test_module_isolation_and_session_lookup(connection):
    module_a = create_test_module(connection, "user-a")
    module_b = add_module(connection, "Python Developer", "Python", "user-a")
    add_session(
        connection, module_a, 1, "2026-09-13", "Level 1",
        "SQL", "11:00 AM", "SQL prompt", "user-a"
    )
    add_session(
        connection, module_b, 1, "2026-09-13", "Level 1",
        "Python", "11:00 AM", "Python prompt", "user-a"
    )
    assert len(connection.execute(
        "SELECT * FROM sessions WHERE module_id = ?", (module_a,)
    ).fetchall()) == 1
    assert get_learning_context(
        connection,
        connection.execute("SELECT MAX(session_id) FROM sessions").fetchone()[0],
        "user-a",
    )["topic"] == "Python"
