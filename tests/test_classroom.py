import sqlite3

import pytest

from database.schema import initialize_database
from services.classroom_service import (
    clear_history,
    get_classroom,
    load_history,
    rename_classroom,
    save_history,
)


@pytest.fixture
def connection():
    database = sqlite3.connect(":memory:")
    database.row_factory = sqlite3.Row
    initialize_database(database)
    yield database
    database.close()


def test_classroom_history_persists_and_isolated(connection):
    history = [{"role": "user", "content": "Teach joins."},
               {"role": "assistant", "content": "A join combines rows."}]
    save_history(connection, "user-a", "session-1", history)
    assert load_history(connection, "user-a", "session-1") == history
    assert load_history(connection, "user-b", "session-1") == []
    assert load_history(connection, "user-a", "session-2") == []


def test_classroom_history_reloads_and_renames(connection):
    save_history(connection, "user-a", "test-1", [{"role": "assistant", "content": "Ready."}])
    rename_classroom(connection, "user-a", "test-1", "SQL Test Classroom")
    row = get_classroom(connection, "user-a", "test-1")
    assert row["title"] == "SQL Test Classroom"
    assert row["history_json"] == '[{"role":"assistant","content":"Ready."}]'


def test_clear_history_does_not_affect_other_classrooms(connection):
    save_history(connection, "user-a", "doubt", [{"role": "assistant", "content": "Answer"}])
    save_history(connection, "user-a", "other", [{"role": "assistant", "content": "Keep"}])
    clear_history(connection, "user-a", "doubt")
    assert load_history(connection, "user-a", "doubt") == []
    assert load_history(connection, "user-a", "other")[0]["content"] == "Keep"


def test_classroom_rejects_invalid_history(connection):
    with pytest.raises(ValueError):
        save_history(connection, "user-a", "x", [{"role": "system", "content": "no"}])


def test_test_and_interview_classrooms_are_isolated(connection):
    save_history(connection, "user-a", "test_1", [{"role": "assistant", "content": "Test"}])
    save_history(
        connection, "user-a", "interview_hr_session-1",
        [{"role": "assistant", "content": "HR"}],
    )
    save_history(
        connection, "user-a", "interview_technical_session-1",
        [{"role": "assistant", "content": "Technical"}],
    )
    assert load_history(connection, "user-a", "test_1")[0]["content"] == "Test"
    assert load_history(connection, "user-a", "interview_hr_session-1")[0]["content"] == "HR"
    assert load_history(connection, "user-a", "interview_technical_session-1")[0]["content"] == "Technical"
