import sqlite3

import pytest

from alarms.models import alarm_id_for_session, calculate_next_occurrence
from alarms.repository import get_alarm, list_alarms
from alarms.schedulers import AndroidAlarmScheduler, WindowsAlarmScheduler
from alarms.service import reconcile_recurring_alarm, reconcile_session_alarm
from database.schema import initialize_database
from services.module_service import add_module
from services.timetable_service import add_session, save_session


@pytest.fixture
def connection():
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    initialize_database(connection)
    yield connection
    connection.close()


def make_session(connection, user="u"):
    module_id = add_module(connection, "SQL", "desc", user)
    session_id = add_session(
        connection, module_id, 1, "2026-09-13", "Level 1", "Joins",
        "10:00 AM", "prompt", user,
    )
    return connection.execute(
        "SELECT * FROM sessions WHERE session_id=?", (session_id,)
    ).fetchone()


def test_alarm_has_stable_session_identifier_and_is_idempotent(connection):
    session = make_session(connection)
    first = get_alarm(connection, alarm_id_for_session(session["session_id"]), "u")
    reconcile_session_alarm(connection, "u", session)
    second = get_alarm(connection, first["alarm_id"], "u")
    assert first["alarm_id"] == f"academy_alarm_{session['session_id']}"
    assert second["scheduled_at"] == first["scheduled_at"]
    assert len(list_alarms(connection, "u")) == 1
    assert second["scheduled_at"].endswith("+05:30")


def test_alarm_reconciliation_updates_time_and_cancels_completed_session(connection):
    session = make_session(connection)
    save_session(connection, session["session_id"], "11:00 AM", "Joins", "prompt", "Scheduled", "u")
    alarm = get_alarm(connection, alarm_id_for_session(session["session_id"]), "u")
    assert "11:00" in alarm["scheduled_at"]
    save_session(connection, session["session_id"], "11:00 AM", "Joins", "prompt", "Completed", "u")
    assert get_alarm(connection, alarm["alarm_id"], "u")["status"] == "CANCELLED"


def test_platform_scheduler_contracts_are_safe_boundaries():
    assert not WindowsAlarmScheduler().schedule({}).scheduled
    assert not AndroidAlarmScheduler().cancel("academy_alarm_1").scheduled


def test_weekly_recurrence_keeps_identity_and_calculates_next_occurrence(connection):
    session = make_session(connection)
    alarm = reconcile_recurring_alarm(
        connection, "u", session, weekday=0,
    )
    assert alarm["alarm_id"] == f"academy_alarm_{session['session_id']}"
    assert alarm["recurrence_rule"] == "WEEKLY:0"
    assert alarm["next_occurrence"]
    assert calculate_next_occurrence(
        "2026-09-14T10:00:00+05:30", "WEEKLY:0",
    )
    updated = reconcile_recurring_alarm(connection, "u", session, weekday=2)
    assert updated["alarm_id"] == alarm["alarm_id"]
    assert updated["recurrence_rule"] == "WEEKLY:2"


def test_disabling_recurrence_cancels_future_occurrence(connection):
    session = make_session(connection)
    reconcile_recurring_alarm(connection, "u", session, weekday=0)
    from alarms.repository import cancel_alarm
    cancel_alarm(connection, "u", session["session_id"])
    alarm = get_alarm(connection, alarm_id_for_session(session["session_id"]), "u")
    assert alarm["status"] == "CANCELLED"
    assert alarm["enabled"] == 0
    assert alarm["next_occurrence"] is None
