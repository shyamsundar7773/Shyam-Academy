import sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo

from database.schema import initialize_database
from services.module_service import add_module, remove_module
from services.schedule_status import can_start_learning, session_status
from services.timetable_service import add_session, seed_development_timetable


def test_seed_is_one_time_and_deleted_defaults_do_not_return():
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    initialize_database(connection)
    seed_development_timetable(connection, "user-a")
    module_id = connection.execute(
        "SELECT module_id FROM modules WHERE owner_user_id='user-a'"
    ).fetchone()[0]
    remove_module(connection, module_id, "user-a")
    seed_development_timetable(connection, "user-a")
    assert connection.execute(
        "SELECT COUNT(*) FROM modules WHERE owner_user_id='user-a'"
    ).fetchone()[0] == 0


def test_existing_user_with_no_modules_is_not_seeded():
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    initialize_database(connection)
    add_module(connection, "Temporary", "x", "user-a")
    connection.execute("DELETE FROM modules WHERE owner_user_id='user-a'")
    connection.execute(
        "INSERT INTO user_bootstrap(user_id, initialized_at) VALUES ('user-a', 'now')"
    )
    connection.commit()
    seed_development_timetable(connection, "user-a")
    assert connection.execute(
        "SELECT COUNT(*) FROM modules WHERE owner_user_id='user-a'"
    ).fetchone()[0] == 0


def test_dashboard_session_status_is_time_aware():
    session = {
        "session_date": "2026-09-13",
        "scheduled_time": "10:00 AM",
        "status": "Scheduled",
    }
    zone = ZoneInfo("Asia/Kolkata")
    assert session_status(session, now=datetime(2026, 9, 13, 9, 0, tzinfo=zone)) == "Upcoming"
    assert session_status(session, now=datetime(2026, 9, 13, 10, 30, tzinfo=zone)) == "Active"
    assert session_status(session, now=datetime(2026, 9, 13, 12, 0, tzinfo=zone)) == "Past"


def test_learning_access_is_blocked_before_start_and_allowed_at_start():
    session = {
        "session_date": "2026-09-13",
        "scheduled_time": "5:45 PM",
        "scheduled_end_time": "6:45 PM",
        "status": "Scheduled",
    }
    zone = ZoneInfo("Asia/Kolkata")
    assert not can_start_learning(
        session, now=datetime(2026, 9, 13, 17, 39, tzinfo=zone)
    )
    assert can_start_learning(
        session, now=datetime(2026, 9, 13, 17, 45, tzinfo=zone)
    )


def test_learning_access_rejects_past_completed_and_skipped_sessions():
    zone = ZoneInfo("Asia/Kolkata")
    base = {
        "session_date": "2026-09-13",
        "scheduled_time": "5:45 PM",
        "scheduled_end_time": "6:45 PM",
    }
    assert not can_start_learning(
        {**base, "status": "Scheduled"},
        now=datetime(2026, 9, 13, 19, 0, tzinfo=zone),
    )
    assert not can_start_learning(
        {**base, "status": "Completed"},
        now=datetime(2026, 9, 13, 18, 0, tzinfo=zone),
    )
    assert not can_start_learning(
        {**base, "status": "Skipped"},
        now=datetime(2026, 9, 13, 18, 0, tzinfo=zone),
    )
