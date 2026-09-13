import sqlite3
from datetime import datetime, timezone

import pytest

from database.schema import initialize_database
from services.attendance_service import mark_attended
from services.module_service import add_module
from services.timetable_service import add_session
from notifications import repository
from notifications.models import Notification, parse_scheduled_at
from notifications.providers import (
    AndroidNotificationProvider,
    DesktopNotificationProvider,
    MockNotificationProvider,
)
from notifications.scheduler import process_due_notifications
from notifications.service import (
    cancel_deleted_session,
    in_quiet_hours,
    reschedule_session,
    schedule_interview_reminder,
    schedule_mentor_recommendation,
    schedule_session_notifications,
    schedule_test_reminder,
    user_timezone,
)


@pytest.fixture
def connection():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    initialize_database(db)
    yield db
    db.close()


def session(connection, user="u", day="2026-09-12", time="10:00 AM", category="Level 1"):
    module = add_module(connection, "SQL", "desc", user)
    sid = add_session(connection, module, 1, day, category, "Joins", time, "prompt", user)
    return connection.execute("SELECT * FROM sessions WHERE session_id=?", (sid,)).fetchone()


def count(connection, user="u"):
    return connection.execute("SELECT COUNT(*) AS n FROM notifications WHERE user_id=?", (user,)).fetchone()["n"]


def test_notification_model_defaults():
    item = Notification("id", "u", "SYSTEM", "Title", "Body", "2026-09-12T10:00:00+00:00")
    assert item.status == "SCHEDULED"


def test_notification_types_reject_unknown(connection):
    with pytest.raises(ValueError):
        repository.create_notification(connection, "u", "UNKNOWN", "x", "y", "2026-09-12T10:00:00+00:00")


def test_status_validation(connection):
    with pytest.raises(ValueError):
        repository.update_status(connection, "missing", "BOGUS")


def test_priority_validation(connection):
    with pytest.raises(ValueError):
        repository.create_notification(connection, "u", "SYSTEM", "x", "y", "2026-09-12T10:00:00+00:00", priority="BOGUS")


def test_default_preferences(connection):
    prefs = repository.get_preferences(connection, "u")
    assert prefs["notifications_enabled"] is True
    assert prefs["reminder_offset_minutes"] == 5


def test_preference_persistence(connection):
    repository.save_preferences(connection, "u", {"reminder_offset_minutes": 10, "timezone": "UTC"})
    prefs = repository.get_preferences(connection, "u")
    assert prefs["reminder_offset_minutes"] == 10
    assert prefs["timezone"] == "UTC"


def test_unknown_preference_rejected(connection):
    with pytest.raises(ValueError):
        repository.save_preferences(connection, "u", {"secret": "no"})


def test_user_notification_isolation(connection):
    repository.create_notification(connection, "a", "SYSTEM", "a", "body", "2026-09-12T10:00:00+00:00")
    assert repository.list_notifications(connection, "b") == []


def test_notification_persistence(connection):
    identifier = repository.create_notification(connection, "u", "SYSTEM", "a", "body", "2026-09-12T10:00:00+00:00")
    assert repository.get_notification(connection, identifier, "u")["title"] == "a"


def test_session_creates_five_minute_reminder(connection):
    row = session(connection)
    ids = schedule_session_notifications(connection, "u", row)
    assert len(ids) == 3
    item = repository.get_notification(connection, ids[0], "u")
    assert item["type"] == "SESSION_REMINDER"
    assert item["scheduled_at"].startswith("2026-09-12T09:55")


def test_session_start_notification(connection):
    row = session(connection)
    schedule_session_notifications(connection, "u", row)
    assert connection.execute("SELECT COUNT(*) FROM notifications WHERE type='SESSION_START'").fetchone()[0] == 1


def test_missed_notification_is_fifteen_minutes(connection):
    row = session(connection)
    schedule_session_notifications(connection, "u", row)
    item = connection.execute("SELECT scheduled_at FROM notifications WHERE type='SESSION_MISSED'").fetchone()
    assert item["scheduled_at"].startswith("2026-09-12T10:15")


def test_session_schedule_is_idempotent(connection):
    row = session(connection)
    schedule_session_notifications(connection, "u", row)
    schedule_session_notifications(connection, "u", row)
    assert count(connection) == 3


def test_completion_suppresses_missed(connection):
    row = session(connection)
    schedule_session_notifications(connection, "u", row)
    mark_attended(connection, "u", row["session_id"])
    assert connection.execute("SELECT status FROM notifications WHERE type='SESSION_MISSED'").fetchone()["status"] == "SUPPRESSED"


def test_reschedule_cancels_old_and_preserves_session(connection):
    row = session(connection)
    schedule_session_notifications(connection, "u", row)
    connection.execute("UPDATE sessions SET scheduled_time='11:00 AM' WHERE session_id=?", (row["session_id"],))
    connection.commit()
    updated = connection.execute("SELECT * FROM sessions WHERE session_id=?", (row["session_id"],)).fetchone()
    reschedule_session(connection, "u", updated)
    assert connection.execute("SELECT COUNT(*) FROM notifications WHERE status='CANCELLED'").fetchone()[0] == 3
    assert connection.execute("SELECT COUNT(*) FROM notifications WHERE scheduled_at LIKE '%10:55%'").fetchone()[0] == 1
    assert updated["session_id"] == row["session_id"]


def test_deleted_session_cancellation(connection):
    row = session(connection)
    schedule_session_notifications(connection, "u", row)
    cancel_deleted_session(connection, "u", row["session_id"])
    assert connection.execute("SELECT COUNT(*) FROM notifications WHERE status='CANCELLED'").fetchone()[0] == 3


def test_test_reminder(connection):
    identifier = schedule_test_reminder(connection, "u", {"title": "SQL test"}, "2026-09-12T10:00:00+00:00")
    assert repository.get_notification(connection, identifier, "u")["type"] == "TEST_REMINDER"


def test_interview_reminder(connection):
    row = session(connection, category="Interview Preparation")
    identifier = schedule_interview_reminder(connection, "u", row)
    assert repository.get_notification(connection, identifier, "u")["type"] == "INTERVIEW_REMINDER"


def test_mentor_recommendation(connection):
    identifier = schedule_mentor_recommendation(connection, "u", {"reason": "Review joins", "topic": "Joins", "priority": "HIGH"})
    assert repository.get_notification(connection, identifier, "u")["type"] == "MENTOR_RECOMMENDATION"


def test_mentor_duplicate_protection(connection):
    item = {"reason": "Review joins", "topic": "Joins", "priority": "HIGH"}
    first = schedule_mentor_recommendation(connection, "u", item, "2026-09-12T10:00:00+00:00")
    second = schedule_mentor_recommendation(connection, "u", item, "2026-09-12T10:00:00+00:00")
    assert first == second


def test_quiet_hours_normal():
    prefs = {"quiet_start": "23:00", "quiet_end": "07:00"}
    assert in_quiet_hours(datetime(2026, 1, 1, 23, 30), prefs)
    assert in_quiet_hours(datetime(2026, 1, 1, 6, 30), prefs)
    assert not in_quiet_hours(datetime(2026, 1, 1, 12, 0), prefs)


def test_quiet_hours_midnight_crossing():
    prefs = {"quiet_start": "10:00", "quiet_end": "12:00"}
    assert in_quiet_hours(datetime(2026, 1, 1, 11, 0), prefs)
    assert not in_quiet_hours(datetime(2026, 1, 1, 13, 0), prefs)


def test_timezone_aware_schedule(connection):
    row = session(connection)
    schedule_session_notifications(connection, "u", row)
    assert parse_scheduled_at(connection.execute("SELECT scheduled_at FROM notifications").fetchone()["scheduled_at"]).tzinfo


def test_invalid_timezone_falls_back(connection):
    repository.save_preferences(connection, "u", {"timezone": "invalid/zone"})
    assert user_timezone(connection, "u").key == "Asia/Kolkata"


def test_due_delivery_marks_delivered(connection):
    identifier = repository.create_notification(connection, "u", "SYSTEM", "a", "body", "2026-09-12T09:00:00+00:00")
    result = process_due_notifications(connection, MockNotificationProvider(), datetime(2026, 9, 12, 10, tzinfo=timezone.utc))
    assert (identifier, "DELIVERED") in result


def test_scheduler_is_restart_safe(connection):
    repository.create_notification(connection, "u", "SYSTEM", "a", "body", "2026-09-12T09:00:00+00:00")
    provider = MockNotificationProvider()
    process_due_notifications(connection, provider, datetime(2026, 9, 12, 10, tzinfo=timezone.utc))
    process_due_notifications(connection, provider, datetime(2026, 9, 12, 10, tzinfo=timezone.utc))
    assert len(provider.deliveries) == 1


def test_mock_provider_success():
    result = MockNotificationProvider().deliver({"notification_id": "a"})
    assert result.delivered


def test_mock_provider_failure():
    assert not MockNotificationProvider(fail=True).deliver({"notification_id": "a"}).delivered


def test_failed_delivery_retries_bounded(connection):
    identifier = repository.create_notification(connection, "u", "SYSTEM", "a", "body", "2026-09-12T09:00:00+00:00")
    provider = MockNotificationProvider(fail=True)
    for _ in range(4):
        process_due_notifications(connection, provider, datetime(2026, 9, 12, 10, tzinfo=timezone.utc))
    item = repository.get_notification(connection, identifier, "u")
    assert item["status"] == "FAILED"
    assert item["delivery_attempts"] == 3


def test_failed_notification_persists_error(connection):
    identifier = repository.create_notification(connection, "u", "SYSTEM", "a", "body", "2026-09-12T09:00:00+00:00")
    process_due_notifications(connection, MockNotificationProvider(fail=True), datetime(2026, 9, 12, 10, tzinfo=timezone.utc))
    assert repository.get_notification(connection, identifier, "u")["last_error"]


def test_android_boundary_is_not_configured():
    assert AndroidNotificationProvider().deliver({"notification_id": "a"}).delivered is False


def test_desktop_boundary_is_not_configured():
    assert DesktopNotificationProvider().deliver({"notification_id": "a"}).delivered is False


def test_device_registration(connection):
    repository.register_device(connection, "u", "device", "android", "secret-token", "1")
    assert repository.list_devices(connection, "u")[0]["device_id"] == "device"


def test_device_isolation(connection):
    repository.register_device(connection, "a", "device", "android")
    assert repository.list_devices(connection, "b") == []


def test_device_unregister(connection):
    repository.register_device(connection, "u", "device", "desktop")
    repository.unregister_device(connection, "u", "device")
    assert repository.list_devices(connection, "u")[0]["active"] == 0


def test_push_token_not_returned_in_device_list(connection):
    repository.register_device(connection, "u", "device", "android", "secret-token")
    assert "push_token" not in repository.list_devices(connection, "u")[0].keys()


def test_read_state(connection):
    identifier = repository.create_notification(connection, "u", "SYSTEM", "a", "body", "2026-09-12T09:00:00+00:00")
    repository.mark_read(connection, identifier, "u")
    assert repository.get_notification(connection, identifier, "u")["read_at"]


def test_unread_count(connection):
    repository.create_notification(connection, "u", "SYSTEM", "a", "body", "2026-09-12T09:00:00+00:00")
    assert repository.count_unread(connection, "u") == 1


def test_notification_center_is_bounded(connection):
    for index in range(10):
        repository.create_notification(connection, "u", "SYSTEM", str(index), "body", f"2026-09-12T{index:02d}:00:00+00:00")
    assert len(repository.list_notifications(connection, "u", 5)) == 5


def test_notification_to_session_route(connection):
    row = session(connection)
    identifier = schedule_session_notifications(connection, "u", row)[0]
    assert repository.get_notification(connection, identifier, "u")["session_id"] == row["session_id"]


def test_disabled_session_reminder(connection):
    repository.save_preferences(connection, "u", {"session_reminders": False})
    assert len(schedule_session_notifications(connection, "u", session(connection))) == 2


def test_disabled_test_reminder(connection):
    repository.save_preferences(connection, "u", {"test_reminders": False})
    assert schedule_test_reminder(connection, "u", {"title": "x"}, "2026-09-12T10:00:00+00:00") is None


def test_disabled_interview_reminder(connection):
    repository.save_preferences(connection, "u", {"interview_reminders": False})
    assert schedule_interview_reminder(connection, "u", session(connection, category="Interview Preparation")) is None


def test_notification_cancel(connection):
    identifier = repository.create_notification(connection, "u", "SYSTEM", "a", "body", "2026-09-12T09:00:00+00:00")
    repository.cancel_notification(connection, identifier, "u")
    assert repository.get_notification(connection, identifier, "u")["status"] == "CANCELLED"


def test_due_batch_is_bounded(connection):
    for index in range(20):
        repository.create_notification(connection, "u", "SYSTEM", str(index), "body", f"2026-09-12T{index:02d}:00:00+00:00")
    assert len(repository.due_notifications(connection, datetime(2026, 9, 13, tzinfo=timezone.utc), 5)) == 5


def test_missing_user_rejected(connection):
    with pytest.raises(ValueError):
        repository.create_notification(connection, "", "SYSTEM", "a", "b", "2026-09-12T10:00:00+00:00")


def test_invalid_timestamp_rejected():
    with pytest.raises(ValueError):
        parse_scheduled_at("2026-09-12T10:00:00")


def test_malformed_quiet_hours_rejected(connection):
    repository.save_preferences(connection, "u", {"quiet_start": "bad"})
    repository.create_notification(connection, "u", "SYSTEM", "a", "body", "2026-09-12T09:00:00+00:00")
    with pytest.raises(ValueError):
        process_due_notifications(connection, MockNotificationProvider(), datetime.now(timezone.utc))


def test_system_notification_does_not_need_session(connection):
    identifier = repository.create_notification(connection, "u", "SYSTEM", "a", "body", "2026-09-12T09:00:00+00:00")
    assert repository.get_notification(connection, identifier, "u")["session_id"] is None


def test_metadata_is_persisted(connection):
    identifier = repository.create_notification(connection, "u", "SYSTEM", "a", "body", "2026-09-12T09:00:00+00:00", metadata={"why": "test"})
    assert repository.get_notification(connection, identifier, "u")["metadata"]["why"] == "test"


def test_reschedule_does_not_change_session_id(connection):
    row = session(connection)
    original = row["session_id"]
    reschedule_session(connection, "u", row)
    assert {item["session_id"] for item in repository.list_notifications(connection, "u")} == {original}


def test_notification_database_migration(connection):
    initialize_database(connection)
    assert connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='notification_preferences'"
    ).fetchone()


def test_no_raw_token_in_device_list(connection):
    repository.register_device(connection, "u", "d", "android", "raw-token")
    assert all("raw-token" not in str(row) for row in repository.list_devices(connection, "u"))


def test_provider_registration_boundary():
    result = AndroidNotificationProvider().register_device("u", "d", "android")
    assert result["status"] == "NOT_CONFIGURED"
