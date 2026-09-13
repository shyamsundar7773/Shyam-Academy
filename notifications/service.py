from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from database.repositories import progress_repository
from notifications import repository
from notifications.models import parse_scheduled_at


def user_timezone(connection, user_id):
    value = repository.get_preferences(connection, user_id)["timezone"]
    try:
        return ZoneInfo(value)
    except ZoneInfoNotFoundError:
        return ZoneInfo("Asia/Kolkata")


def _local_session_time(session, zone):
    try:
        local = datetime.strptime(
            f"{session['session_date']} {session['scheduled_time']}", "%Y-%m-%d %I:%M %p"
        )
    except (TypeError, ValueError) as error:
        raise ValueError("Session has an invalid schedule.") from error
    return local.replace(tzinfo=zone)


def _enabled(preferences, notification_type):
    return preferences["notifications_enabled"] and {
        "SESSION_REMINDER": preferences["session_reminders"],
        "SESSION_START": preferences["session_start"],
        "SESSION_MISSED": preferences["missed_session"],
        "TEST_REMINDER": preferences["test_reminders"],
        "INTERVIEW_REMINDER": preferences["interview_reminders"],
        "MENTOR_RECOMMENDATION": preferences["mentor_recommendations"],
        "ROUTINE_REMINDER": preferences.get("routine_enabled", True),
        "ROUTINE_MISSED": preferences.get("routine_enabled", True),
        "SYSTEM": True,
    }[notification_type]


def in_quiet_hours(value, preferences):
    local = value.timetz().replace(tzinfo=None)
    current = local.hour * 60 + local.minute
    start_h, start_m = map(int, preferences["quiet_start"].split(":"))
    end_h, end_m = map(int, preferences["quiet_end"].split(":"))
    start, end = start_h * 60 + start_m, end_h * 60 + end_m
    return current >= start or current < end if start > end else start <= current < end


def schedule_session_notifications(connection, user_id, session, reminder_offset=None):
    preferences = repository.get_preferences(connection, user_id)
    zone = user_timezone(connection, user_id)
    start = _local_session_time(session, zone)
    offset = preferences["reminder_offset_minutes"] if reminder_offset is None else int(reminder_offset)
    created = []
    configs = [
        ("SESSION_REMINDER", start - timedelta(minutes=offset), "Upcoming learning session",
         f"{session['topic']} starts in {offset} minutes.", "NORMAL"),
        ("SESSION_START", start, "Learning session starting", f"Your session on {session['topic']} starts now.", "NORMAL"),
        ("SESSION_MISSED", start + timedelta(minutes=15), "Learning session missed?",
         f"{session['topic']} has not been completed yet.", "HIGH"),
    ]
    for kind, when, title, body, priority in configs:
        if _enabled(preferences, kind):
            created.append(repository.create_notification(
                connection, user_id, kind, title, body, when.isoformat(),
                int(session["session_id"]), int(session["module_id"]), priority,
                {"source": "timetable", "session_id": int(session["session_id"])},
            ))
    return created


def schedule_test_reminder(connection, user_id, test, when):
    if not repository.get_preferences(connection, user_id)["test_reminders"]:
        return None
    return repository.create_notification(
        connection, user_id, "TEST_REMINDER", "Test reminder",
        f"Prepare for {test['title']}.", parse_scheduled_at(when).isoformat(),
        test.get("session_id"), test.get("module_id"), "HIGH", {"source": "test"},
    )


def schedule_interview_reminder(connection, user_id, session):
    preferences = repository.get_preferences(connection, user_id)
    if not preferences["interview_reminders"]:
        return None
    zone = user_timezone(connection, user_id)
    start = _local_session_time(session, zone)
    return repository.create_notification(
        connection, user_id, "INTERVIEW_REMINDER", "Interview preparation reminder",
        f"Prepare for {session['topic']}.", start.isoformat(), int(session["session_id"]),
        int(session["module_id"]), "HIGH", {"source": "interview"},
    )


def schedule_mentor_recommendation(connection, user_id, recommendation, scheduled_at=None):
    when = scheduled_at or datetime.now(timezone.utc).isoformat()
    return repository.create_notification(
        connection, user_id, "MENTOR_RECOMMENDATION", "Mentor recommendation",
        recommendation["reason"], parse_scheduled_at(when).isoformat(),
        recommendation.get("session_id"), recommendation.get("module_id"),
        recommendation.get("priority", "NORMAL"), {"source": "mentor", "topic": recommendation.get("topic", "")},
    )


def reschedule_session(connection, user_id, session):
    repository.cancel_for_session(connection, user_id, int(session["session_id"]), "Session rescheduled")
    return schedule_session_notifications(connection, user_id, session)


def cancel_deleted_session(connection, user_id, session_id):
    repository.cancel_for_session(connection, user_id, session_id, "Session deleted")
    from alarms.service import cancel_session_alarm
    cancel_session_alarm(connection, user_id, session_id)


def suppress_missed_for_completion(connection, user_id, session_id):
    connection.execute(
        """UPDATE notifications SET status='SUPPRESSED', updated_at=?
        WHERE user_id=? AND session_id=? AND type='SESSION_MISSED'
        AND status IN ('SCHEDULED','READY','FAILED')""",
        (datetime.now(timezone.utc).isoformat(), user_id, session_id),
    )
    connection.commit()


def schedule_routine_notifications(connection, user_id, routine_id):
    from database.repositories import routine_repository
    from services.routine_service import _zone
    routine = routine_repository.get_routine(connection, routine_id, user_id)
    if not routine:
        raise ValueError("Routine not found.")
    preference = routine_repository.get_preference(connection, user_id)
    if not preference["enabled"]:
        return []
    created = []
    for occurrence in routine_repository.list_occurrences(connection, user_id, routine_id):
        when = parse_scheduled_at(occurrence["scheduled_at"])
        reminder = when - timedelta(minutes=int(preference["reminder_minutes"]))
        created.append(repository.create_notification(
            connection, user_id, "ROUTINE_REMINDER", f"Routine: {routine['name']}",
            f"{routine['name']} starts in {preference['reminder_minutes']} minutes.",
            reminder.isoformat(), priority="NORMAL",
            metadata={"source": "routine", "routine_id": routine_id},
            routine_occurrence_id=occurrence["occurrence_id"],
        ))
        created.append(repository.create_notification(
            connection, user_id, "ROUTINE_MISSED", f"Routine missed: {routine['name']}",
            f"Mark {routine['name']} complete or skip it in your Body & Routine history.",
            (when + timedelta(minutes=int(routine["duration_minutes"]))).isoformat(),
            priority="HIGH", metadata={"source": "routine", "routine_id": routine_id},
            routine_occurrence_id=occurrence["occurrence_id"],
        ))
    return created


def cancel_routine_notifications(connection, user_id, routine_id):
    repository.cancel_for_routine(connection, user_id, routine_id, "Routine cancelled")
