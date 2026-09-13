import sqlite3
from datetime import datetime

import pytest

from database.schema import initialize_database
from services.attendance_service import (
    attendance_summary,
    calculate_status,
    get_attendance,
    get_attendance_display_state,
    get_session_status,
    mark_attended,
    mark_attended_from_note,
    mark_missed,
)
from services.learning_service import load_classroom_context, record_successful_generation
from services.module_service import add_module
from services.notes_service import save_note
from services.timetable_service import add_session, save_session


@pytest.fixture
def classroom():
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    initialize_database(connection)
    module_id = add_module(connection, "SQL Developer", "SQL", "user-a")
    session_id = add_session(
        connection, module_id, 1, "2026-09-12", "Level 1",
        "JOIN", "10:00 AM", "Teach joins.", "user-a"
    )
    yield connection, module_id, session_id
    connection.close()


def test_timing_states_and_grace_period(classroom):
    connection, _, session_id = classroom
    session = connection.execute(
        "SELECT * FROM sessions WHERE session_id = ?", (session_id,)
    ).fetchone()
    assert calculate_status(session, None, datetime(2026, 9, 12, 9, 59)) == "Upcoming"
    assert calculate_status(session, None, datetime(2026, 9, 12, 10, 10)) == "Current"
    assert calculate_status(session, None, datetime(2026, 9, 12, 10, 16)) == "Missed"


def test_successful_generation_does_not_mark_attendance(classroom):
    connection, module_id, session_id = classroom
    _, context = load_classroom_context(connection, session_id, "user-a")
    assert record_successful_generation(connection, context) != "Attended"
    assert connection.execute(
        "SELECT COUNT(*) FROM attendance WHERE user_id = ? AND session_id = ?",
        ("user-a", session_id),
    ).fetchone()[0] == 0
    assert get_attendance(connection, "user-a", session_id) is None


def test_mark_missed_and_historical_missed_state(classroom):
    connection, _, session_id = classroom
    assert mark_missed(connection, "user-a", session_id) == "Missed"
    assert get_session_status(
        connection, "user-a",
        connection.execute("SELECT * FROM sessions WHERE session_id = ?", (session_id,)).fetchone(),
        datetime(2026, 9, 12, 10, 30),
    ) == "Missed"
    assert mark_attended(connection, "user-a", session_id) == "Missed"


def test_time_edit_preserves_attendance_identity_and_updates_schedule(classroom):
    connection, _, session_id = classroom
    mark_attended(connection, "user-a", session_id)
    save_session(
        connection, session_id, "11:00 AM", "JOIN", "Teach joins.",
        "Scheduled", "user-a"
    )
    row = get_attendance(connection, "user-a", session_id)
    assert row["session_id"] == session_id
    assert connection.execute(
        "SELECT COUNT(*) FROM attendance WHERE session_id = ?", (session_id,)
    ).fetchone()[0] == 1
    assert get_attendance(connection, "user-a", session_id)["scheduled_time"] == "11:00 AM"


def test_stale_attended_row_does_not_override_upcoming_status(classroom):
    connection, _, session_id = classroom
    mark_attended(connection, "user-a", session_id)
    session = connection.execute(
        "SELECT * FROM sessions WHERE session_id = ?", (session_id,)
    ).fetchone()
    assert get_session_status(
        connection, "user-a", session, datetime(2026, 9, 12, 9, 50)
    ) == "Upcoming"


def test_browser_equivalent_655_session_at_650_is_upcoming(classroom):
    connection, _, session_id = classroom
    save_session(
        connection, session_id, "06:55 PM", "JOIN", "Teach joins.",
        "Scheduled", "user-a",
    )
    mark_attended(connection, "user-a", session_id)
    session = connection.execute(
        "SELECT * FROM sessions WHERE session_id = ?", (session_id,)
    ).fetchone()
    assert get_session_status(
        connection, "user-a", session, datetime(2026, 9, 12, 18, 50)
    ) == "Upcoming"


def test_display_state_rejects_legacy_and_invalid_evidence(classroom):
    connection, module_id, session_id = classroom
    mark_attended(connection, "user-a", session_id)
    session = connection.execute(
        "SELECT * FROM sessions WHERE session_id = ?", (session_id,)
    ).fetchone()
    assert get_attendance_display_state(
        connection, "user-a", session, datetime(2026, 9, 12, 9, 50)
    )["attended"] is False

    other_session = add_session(
        connection, module_id, 2, "2026-09-13", "Level 1", "Other",
        "11:00 AM", "Other prompt", "user-a",
    )
    other_note, _ = save_note(
        connection, "user-a", module_id, other_session, "Level 1", "Other",
        "Other note", "content",
    )
    connection.execute(
        "UPDATE attendance SET evidence_note_id=?, evidence_source='save_notes' "
        "WHERE user_id='user-a' AND session_id=?", (other_note, session_id)
    )
    connection.commit()
    assert get_attendance_display_state(
        connection, "user-a", session, datetime(2026, 9, 12, 9, 50)
    )["attended"] is False

    wrong_module = add_module(connection, "Python Developer", "Python", "user-a")
    note_id, _ = save_note(
        connection, "user-a", wrong_module, session_id, "Level 1", "JOIN",
        "Wrong module", "content",
    )
    connection.execute(
        "UPDATE attendance SET evidence_note_id=?, evidence_source='save_notes' "
        "WHERE user_id='user-a' AND session_id=?", (note_id, session_id)
    )
    connection.commit()
    assert get_attendance_display_state(
        connection, "user-a", session, datetime(2026, 9, 12, 9, 50)
    )["attended"] is False


def test_attended_status_requires_note_for_exact_session(classroom):
    connection, module_id, session_id = classroom
    note_id, _ = save_note(
        connection, "user-a", module_id, session_id, "Level 1", "JOIN",
        "JOIN notes", "saved content",
    )
    mark_attended_from_note(connection, "user-a", session_id, note_id)
    session = connection.execute(
        "SELECT * FROM sessions WHERE session_id = ?", (session_id,)
    ).fetchone()
    assert get_session_status(
        connection, "user-a", session, datetime(2026, 9, 12, 9, 50)
    ) == "Attended"


def test_user_isolation_and_summary_excludes_future_as_missed(classroom):
    connection, module_id, session_id = classroom
    assert get_attendance(connection, "user-b", session_id) is None
    summary = attendance_summary(
        connection, "user-a", module_id, datetime(2026, 9, 11, 10, 0)
    )
    assert summary["total"] == 1
    assert summary["upcoming"] == 1
    assert summary["missed"] == 0
