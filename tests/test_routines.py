import sqlite3
from datetime import date, datetime, timedelta

import pytest

from database.schema import initialize_database
from database.repositories import routine_repository
from models.routine import Routine, RoutineFrequency, generate_occurrences
from services.routine_events import RoutineEvent, emit
from services.routine_service import (
    academic_conflicts,
    complete_occurrence,
    create_routine,
    delete_routine,
    get_history,
    get_metrics,
    list_upcoming,
    mark_missed,
    preview_natural_language,
    skip_occurrence,
    update_routine,
    validate_routine,
)


@pytest.fixture
def connection():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    initialize_database(db)
    return db


def values(**changes):
    result = {
        "name": "Morning walk", "frequency": "DAILY",
        "start_date": date.today().isoformat(), "time_local": "07:00",
        "duration_minutes": 20, "timezone": "Asia/Kolkata",
    }
    result.update(changes)
    return result


def make(connection, user="u", **changes):
    return create_routine(connection, user, values(**changes))


def test_daily_occurs_every_day():
    routine = Routine("r", "u", "x", "", "DAILY", "2026-01-01", None, "07:00", 20, "UTC")
    assert len(generate_occurrences(routine, date(2026, 1, 1), date(2026, 1, 3))) == 3


def test_weekly_occurs_on_start_weekday():
    routine = Routine("r", "u", "x", "", "WEEKLY", "2026-01-05", None, "07:00", 20, "UTC")
    assert [x[0] for x in generate_occurrences(routine, date(2026, 1, 5), date(2026, 1, 19))] == ["2026-01-05", "2026-01-12", "2026-01-19"]


def test_selected_days_occurs_only_selected():
    routine = Routine("r", "u", "x", "", "SELECTED_DAYS", "2026-01-01", None, "07:00", 20, "UTC", (0, 2))
    assert [x[0] for x in generate_occurrences(routine, date(2026, 1, 5), date(2026, 1, 11))] == ["2026-01-05", "2026-01-07"]


def test_end_date_is_inclusive():
    routine = Routine("r", "u", "x", "", "DAILY", "2026-01-01", "2026-01-02", "07:00", 20, "UTC")
    assert len(generate_occurrences(routine, date(2026, 1, 1), date(2026, 1, 5))) == 2


def test_invalid_frequency():
    with pytest.raises(ValueError):
        validate_routine(values(frequency="MONTHLY"))


def test_invalid_time():
    with pytest.raises(ValueError):
        validate_routine(values(time_local="7pm"))


def test_selected_days_required():
    with pytest.raises(ValueError):
        validate_routine(values(frequency="SELECTED_DAYS"))


def test_duration_positive():
    with pytest.raises(ValueError):
        validate_routine(values(duration_minutes=0))


def test_name_required():
    with pytest.raises(ValueError):
        validate_routine(values(name=""))


def test_creation_is_user_scoped(connection):
    routine_id = make(connection, "a")
    assert routine_repository.list_routines(connection, "b") == []
    assert routine_repository.get_routine(connection, routine_id, "b") is None


def test_creation_materializes_occurrences(connection):
    routine_id = make(connection)
    assert routine_repository.list_occurrences(connection, "u", routine_id)


def test_materialization_is_idempotent(connection):
    routine_id = make(connection)
    before = len(routine_repository.list_occurrences(connection, "u", routine_id))
    list_upcoming(connection, "u", end=(date.today() + timedelta(days=5)).isoformat())
    assert len(routine_repository.list_occurrences(connection, "u", routine_id)) >= before


def test_routine_notification_types(connection):
    make(connection)
    types = {row["type"] for row in connection.execute("SELECT type FROM notifications")}
    assert {"ROUTINE_REMINDER", "ROUTINE_MISSED"} <= types


def test_notification_idempotency(connection):
    routine_id = make(connection)
    first = connection.execute("SELECT COUNT(*) c FROM notifications").fetchone()["c"]
    update_routine(connection, "u", routine_id, {"description": "same"})
    second = connection.execute("SELECT COUNT(*) c FROM notifications WHERE status!='CANCELLED'").fetchone()["c"]
    assert second > 0 and first == second


def test_update_changes_schedule(connection):
    routine_id = make(connection)
    update_routine(connection, "u", routine_id, {"time_local": "08:00"})
    assert routine_repository.get_routine(connection, routine_id, "u")["time_local"] == "08:00"


def test_update_isolation(connection):
    routine_id = make(connection, "a")
    with pytest.raises(ValueError):
        update_routine(connection, "b", routine_id, {"name": "Nope"})


def test_delete_isolation(connection):
    routine_id = make(connection, "a")
    with pytest.raises(ValueError):
        delete_routine(connection, "b", routine_id)


def test_delete_removes_routine(connection):
    routine_id = make(connection)
    delete_routine(connection, "u", routine_id)
    assert routine_repository.get_routine(connection, routine_id, "u") is None


def test_complete_occurrence(connection):
    routine_id = make(connection)
    occurrence = routine_repository.list_occurrences(connection, "u", routine_id)[0]
    complete_occurrence(connection, "u", occurrence["occurrence_id"])
    assert routine_repository.get_occurrence(connection, occurrence["occurrence_id"], "u")["status"] == "COMPLETED"


def test_skip_occurrence(connection):
    routine_id = make(connection)
    occurrence = routine_repository.list_occurrences(connection, "u", routine_id)[0]
    skip_occurrence(connection, "u", occurrence["occurrence_id"], "rest")
    assert routine_repository.get_occurrence(connection, occurrence["occurrence_id"], "u")["status"] == "SKIPPED"


def test_complete_isolation(connection):
    routine_id = make(connection, "a")
    occurrence = routine_repository.list_occurrences(connection, "a", routine_id)[0]
    with pytest.raises(ValueError):
        complete_occurrence(connection, "b", occurrence["occurrence_id"])


def test_skip_isolation(connection):
    routine_id = make(connection, "a")
    occurrence = routine_repository.list_occurrences(connection, "a", routine_id)[0]
    with pytest.raises(ValueError):
        skip_occurrence(connection, "b", occurrence["occurrence_id"])


def test_missed_transition(connection):
    routine_id = make(connection)
    occurrence = routine_repository.list_occurrences(connection, "u", routine_id)[0]
    mark_missed(connection, "u", before=(date.today() + timedelta(days=1)).isoformat() + "T23:00:00+00:00")
    assert routine_repository.get_occurrence(connection, occurrence["occurrence_id"], "u")["status"] == "MISSED"


def test_metrics_counts_completed(connection):
    routine_id = make(connection)
    occurrence = routine_repository.list_occurrences(connection, "u", routine_id)[0]
    complete_occurrence(connection, "u", occurrence["occurrence_id"])
    assert get_metrics(connection, "u").completed == 1


def test_metrics_counts_skipped(connection):
    routine_id = make(connection)
    occurrence = routine_repository.list_occurrences(connection, "u", routine_id)[0]
    skip_occurrence(connection, "u", occurrence["occurrence_id"])
    assert get_metrics(connection, "u").skipped == 1


def test_metrics_counts_missed(connection):
    make(connection)
    mark_missed(connection, "u", (date.today() + timedelta(days=1)).isoformat() + "T23:00:00+00:00")
    assert get_metrics(connection, "u").missed == 1


def test_metrics_consistency(connection):
    routine_id = make(connection)
    occurrence = routine_repository.list_occurrences(connection, "u", routine_id)[0]
    complete_occurrence(connection, "u", occurrence["occurrence_id"])
    assert get_metrics(connection, "u").consistency_percentage > 0


def test_history_filter(connection):
    routine_id = make(connection)
    assert get_history(connection, "u", routine_id=routine_id)


def test_events_are_recorded(connection):
    identifier = emit(connection, RoutineEvent("TEST", "u", payload={"ok": True}))
    assert routine_repository.list_events(connection, "u")[0]["event_id"] == identifier


def test_event_isolation(connection):
    emit(connection, RoutineEvent("TEST", "a"))
    assert routine_repository.list_events(connection, "b") == []


def test_preference_defaults(connection):
    assert routine_repository.get_preference(connection, "u")["enabled"] == 1


def test_preference_persistence(connection):
    routine_repository.set_preference(connection, "u", False, 30)
    value = routine_repository.get_preference(connection, "u")
    assert value["enabled"] == 0 and value["reminder_minutes"] == 30


def test_disabled_preference_suppresses_new_notifications(connection):
    routine_repository.set_preference(connection, "u", False)
    routine_id = make(connection)
    assert connection.execute("SELECT COUNT(*) FROM notifications").fetchone()[0] == 0


def test_natural_preview_daily():
    assert preview_natural_language("daily stretching at 7 pm for 20 minutes")["frequency"] == "DAILY"


def test_natural_preview_selected_days():
    assert preview_natural_language("walk on Monday and Wednesday at 6 am")["frequency"] == "SELECTED_DAYS"


def test_natural_preview_time():
    assert preview_natural_language("read daily at 6:30 am")["time_local"] == "06:30"


def test_natural_preview_duration():
    assert preview_natural_language("read daily for 45 minutes")["duration_minutes"] == 45


def test_natural_preview_requires_text():
    with pytest.raises(ValueError):
        preview_natural_language("")


def test_academic_conflict(connection):
    connection.execute(
        """INSERT INTO modules(module_name,description,owner_user_id,created_at,updated_at)
        VALUES ('M','', 'u', 'x','x')"""
    )
    module_id = connection.execute("SELECT module_id FROM modules").fetchone()[0]
    connection.execute(
        """INSERT INTO sessions(module_id,day_number,session_date,category,topic,scheduled_time,
        prompt,owner_user_id,created_at,updated_at) VALUES (1,1,?,?,?,'07:00 AM','', 'u','x','x')""",
        (date.today().isoformat(), "Today Learning", "Class"),
    )
    connection.commit()
    assert academic_conflicts(
        connection, "u", [(date.today().isoformat(), datetime.combine(date.today(), datetime.min.time().replace(hour=7)))], 20
    )


def test_no_academic_conflict(connection):
    assert academic_conflicts(connection, "u", [(date.today().isoformat(), datetime.combine(date.today(), datetime.min.time().replace(hour=7)))], 20) == []


def test_timezone_occurrence_is_aware(connection):
    routine_id = make(connection)
    row = routine_repository.list_occurrences(connection, "u", routine_id)[0]
    assert "+" in row["scheduled_at"]


def test_weekly_creation(connection):
    routine_id = make(connection, frequency="WEEKLY")
    assert len(routine_repository.list_occurrences(connection, "u", routine_id)) > 0


def test_selected_days_creation(connection):
    routine_id = make(connection, frequency="SELECTED_DAYS", selected_days=(0, 2))
    assert all(date.fromisoformat(x["occurrence_date"]).weekday() in (0, 2)
               for x in routine_repository.list_occurrences(connection, "u", routine_id))


def test_disabled_routines_not_upcoming(connection):
    routine_id = make(connection)
    routine_repository.update_routine(connection, routine_id, "u", {"enabled": False})
    assert list_upcoming(connection, "u") == []


def test_list_upcoming_is_user_scoped(connection):
    make(connection, "a")
    assert list_upcoming(connection, "b") == []


def test_occurrence_note_persists(connection):
    routine_id = make(connection)
    occurrence = routine_repository.list_occurrences(connection, "u", routine_id)[0]
    skip_occurrence(connection, "u", occurrence["occurrence_id"], "travel")
    assert routine_repository.get_occurrence(connection, occurrence["occurrence_id"], "u")["note"] == "travel"


def test_routine_event_on_creation(connection):
    make(connection)
    assert any(e["event_type"] == "ROUTINE_CREATED" for e in routine_repository.list_events(connection, "u"))


def test_routine_event_on_completion(connection):
    routine_id = make(connection)
    occurrence = routine_repository.list_occurrences(connection, "u", routine_id)[0]
    complete_occurrence(connection, "u", occurrence["occurrence_id"])
    assert any(e["event_type"] == "OCCURRENCE_COMPLETED" for e in routine_repository.list_events(connection, "u"))


def test_routine_event_on_skip(connection):
    routine_id = make(connection)
    occurrence = routine_repository.list_occurrences(connection, "u", routine_id)[0]
    skip_occurrence(connection, "u", occurrence["occurrence_id"])
    assert any(e["event_type"] == "OCCURRENCE_SKIPPED" for e in routine_repository.list_events(connection, "u"))


def test_routine_event_on_delete(connection):
    routine_id = make(connection)
    delete_routine(connection, "u", routine_id)
    assert any(e["event_type"] == "ROUTINE_DELETED" for e in routine_repository.list_events(connection, "u"))


def test_metrics_empty_user(connection):
    assert get_metrics(connection, "nobody").scheduled == 0


def test_routines_list_disabled(connection):
    routine_id = make(connection)
    routine_repository.update_routine(connection, routine_id, "u", {"enabled": False})
    assert routine_repository.list_routines(connection, "u", include_disabled=True)[0]["enabled"] is False


def test_duplicate_occurrence_upsert(connection):
    routine_id = make(connection)
    rows = routine_repository.list_occurrences(connection, "u", routine_id)
    routine_repository.upsert_occurrences(connection, routine_id, "u", [(rows[0]["occurrence_date"], datetime.fromisoformat(rows[0]["scheduled_at"]))])
    assert len(routine_repository.list_occurrences(connection, "u", routine_id)) == len(rows)


def test_event_payload_json(connection):
    emit(connection, RoutineEvent("TEST", "u", payload={"value": 2}))
    assert routine_repository.list_events(connection, "u")[0]["payload"]["value"] == 2


def test_routine_schema_migration_is_repeatable(connection):
    initialize_database(connection)
    assert connection.execute("SELECT 1 FROM routines").fetchone() is None
