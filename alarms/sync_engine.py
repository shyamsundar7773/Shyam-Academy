"""Idempotent reconciliation between timetable sessions and device-neutral alarms."""

from alarms.service import cancel_session_alarm, reconcile_session_alarm


def reconcile_sessions(connection, user_id, sessions, scheduler=None):
    alarms = []
    for session in sessions:
        alarm = reconcile_session_alarm(connection, user_id, session, scheduler)
        if alarm is not None:
            alarms.append(alarm)
    return alarms


def reconcile_timetable(connection, user_id, module_id, scheduler=None):
    sessions = connection.execute(
        "SELECT * FROM sessions WHERE module_id=? AND owner_user_id=? "
        "ORDER BY session_date, scheduled_time, session_id",
        (int(module_id), user_id),
    ).fetchall()
    return reconcile_sessions(connection, user_id, sessions, scheduler)


__all__ = ["reconcile_sessions", "reconcile_timetable", "cancel_session_alarm"]
