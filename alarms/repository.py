from datetime import datetime, timezone

from alarms.models import alarm_id_for_session, validate_alarm_timestamp


def _now():
    return datetime.now(timezone.utc).isoformat()


def _row(row):
    return dict(row) if row is not None else None


def upsert_alarm(connection, user_id, session_id, module_id, title, body,
                 scheduled_at, timezone_name, status="ACTIVE", source="timetable",
                 recurrence_rule="", next_occurrence=None, enabled=True):
    if not user_id:
        raise ValueError("A user identity is required.")
    if status not in {"ACTIVE", "CANCELLED"}:
        raise ValueError("Invalid alarm status.")
    scheduled_at = validate_alarm_timestamp(scheduled_at)
    alarm_id = alarm_id_for_session(int(session_id))
    now = _now()
    connection.execute(
        """INSERT INTO alarms
           (alarm_id,user_id,session_id,module_id,title,body,scheduled_at,timezone,
            status,source,recurrence_rule,next_occurrence,enabled,created_at,updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(alarm_id) DO UPDATE SET
             user_id=excluded.user_id, module_id=excluded.module_id,
             title=excluded.title, body=excluded.body,
             scheduled_at=excluded.scheduled_at, timezone=excluded.timezone,
             status=excluded.status, source=excluded.source,
             recurrence_rule=excluded.recurrence_rule,
             next_occurrence=excluded.next_occurrence, enabled=excluded.enabled,
             updated_at=excluded.updated_at""",
        (alarm_id, user_id, int(session_id), module_id, title.strip(), body.strip(),
         scheduled_at, timezone_name, status, source, recurrence_rule,
         next_occurrence, int(enabled), now, now),
    )
    connection.commit()
    return alarm_id


def get_alarm(connection, alarm_id, user_id=None):
    query = "SELECT * FROM alarms WHERE alarm_id=?"
    args = [alarm_id]
    if user_id is not None:
        query += " AND user_id=?"
        args.append(user_id)
    return _row(connection.execute(query, args).fetchone())


def get_alarm_for_session(connection, user_id, session_id):
    return _row(connection.execute(
        "SELECT * FROM alarms WHERE user_id=? AND session_id=?",
        (user_id, int(session_id)),
    ).fetchone())


def list_alarms(connection, user_id, include_cancelled=False):
    clause = "" if include_cancelled else " AND status='ACTIVE'"
    return [_row(row) for row in connection.execute(
        f"SELECT * FROM alarms WHERE user_id=?{clause} ORDER BY scheduled_at, alarm_id",
        (user_id,),
    ).fetchall()]


def cancel_alarm(connection, user_id, session_id):
    connection.execute(
        """UPDATE alarms SET status='CANCELLED', enabled=0,
           recurrence_rule='', next_occurrence=NULL, updated_at=?
           WHERE user_id=? AND session_id=?""",
        (_now(), user_id, int(session_id)),
    )
    connection.commit()
