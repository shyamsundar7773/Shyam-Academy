from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from alarms import repository
from alarms.models import alarm_id_for_session
from alarms.models import calculate_next_occurrence
from notifications import repository as notification_repository


def _session_start(session, zone):
    try:
        local = datetime.strptime(
            f"{session['session_date']} {session['scheduled_time']}",
            "%Y-%m-%d %I:%M %p",
        ).replace(tzinfo=zone)
    except (TypeError, ValueError) as error:
        raise ValueError("Session has an invalid schedule.") from error
    return local


def reconcile_session_alarm(connection, user_id, session, scheduler=None):
    session_id = int(session["session_id"])
    if (session["status"] if "status" in session.keys() else "Scheduled") != "Scheduled":
        repository.cancel_alarm(connection, user_id, session_id)
        if scheduler:
            scheduler.cancel(alarm_id_for_session(session_id))
        return None
    preferences = notification_repository.get_preferences(connection, user_id)
    timezone_name = preferences["timezone"]
    try:
        zone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        timezone_name, zone = "Asia/Kolkata", ZoneInfo("Asia/Kolkata")
    when = _session_start(session, zone)
    alarm_id = repository.upsert_alarm(
        connection, user_id, session_id, int(session["module_id"]),
        f"Learning session: {session['topic']}",
        f"{session['topic']} starts now.",
        when.isoformat(), timezone_name,
    )
    alarm = repository.get_alarm(connection, alarm_id, user_id)
    if scheduler:
        scheduler.schedule(alarm)
    return alarm


def reconcile_recurring_alarm(
    connection, user_id, session, weekday, scheduler=None, now=None
):
    if not 0 <= int(weekday) <= 6:
        raise ValueError("Weekly recurrence weekday must be between 0 and 6.")
    preferences = notification_repository.get_preferences(connection, user_id)
    timezone_name = preferences["timezone"]
    try:
        zone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        timezone_name, zone = "Asia/Kolkata", ZoneInfo("Asia/Kolkata")
    scheduled = _session_start(session, zone)
    next_occurrence = calculate_next_occurrence(
        scheduled.isoformat(), f"WEEKLY:{int(weekday)}", now
    )
    alarm_id = repository.upsert_alarm(
        connection, user_id, int(session["session_id"]), int(session["module_id"]),
        f"Learning session: {session['topic']}", f"{session['topic']} starts now.",
        scheduled.isoformat(), timezone_name, recurrence_rule=f"WEEKLY:{int(weekday)}",
        next_occurrence=next_occurrence,
    )
    alarm = repository.get_alarm(connection, alarm_id, user_id)
    if scheduler:
        scheduler.schedule(alarm)
    return alarm


def sync_session_alarm(connection, user_id, session, scheduler=None):
    """Idempotently reconcile one timetable session with the alarm store."""
    return reconcile_session_alarm(connection, user_id, session, scheduler)


def cancel_session_alarm(connection, user_id, session_id, scheduler=None):
    repository.cancel_alarm(connection, user_id, session_id)
    if scheduler:
        return scheduler.cancel(alarm_id_for_session(int(session_id)))
    return None
