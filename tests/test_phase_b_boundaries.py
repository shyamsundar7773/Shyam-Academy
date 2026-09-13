import sqlite3

import pytest

from database.schema import initialize_database
from services.module_service import add_module, edit_module, get_modules, remove_module
from services.timetable_service import add_session
from services.notes_service import find_notes


@pytest.fixture
def connection():
    database = sqlite3.connect(":memory:")
    database.row_factory = sqlite3.Row
    database.execute("PRAGMA foreign_keys = ON")
    initialize_database(database)
    yield database
    database.close()


def test_module_and_note_service_results_are_widget_serializable(connection):
    module_id = add_module(connection, "Serializable module", "Description", "user-a")
    modules = get_modules(connection, "user-a")
    module = next(item for item in modules if item["module_id"] == module_id)
    assert type(module) is dict
    assert all(type(item) is dict for item in find_notes(connection, "user-a", module_id))


def test_remove_module_deletes_owned_module(connection):
    module_id = add_module(connection, "Delete module", "Description", "user-a")
    remove_module(connection, module_id, "user-a")
    assert not any(item["module_id"] == module_id for item in get_modules(connection, "user-a"))


def test_module_rename_and_delete_change_database_state(connection):
    module_id = add_module(connection, "SQL Developer", "SQL", "user-a")
    edit_module(connection, module_id, "Renamed Academy", "Updated", "user-a")
    row = connection.execute(
        "SELECT module_name, description FROM modules WHERE module_id=?",
        (module_id,),
    ).fetchone()
    assert dict(row) == {"module_name": "Renamed Academy", "description": "Updated"}
    add_session(
        connection, module_id, 1, "2026-09-13", "Level 1", "Joins",
        "10:00 AM", "prompt", "user-a",
    )
    remove_module(connection, module_id, "user-a")
    assert connection.execute(
        "SELECT COUNT(*) FROM modules WHERE module_id=?", (module_id,)
    ).fetchone()[0] == 0
    assert connection.execute(
        "SELECT COUNT(*) FROM sessions WHERE module_id=?", (module_id,)
    ).fetchone()[0] == 0
