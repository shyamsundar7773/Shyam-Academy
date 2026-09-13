import json
from datetime import datetime, timezone
from uuid import uuid4


def _now():
    return datetime.now(timezone.utc).isoformat()


def _routine(row):
    if not row:
        return None
    value = dict(row)
    value["selected_days"] = tuple(json.loads(value.pop("selected_days_json") or "[]"))
    value["enabled"] = bool(value["enabled"])
    return value


def _occurrence(row):
    return dict(row) if row else None


def create_routine(connection, user_id, values):
    if not user_id:
        raise ValueError("A user identity is required.")
    required = ("name", "frequency", "start_date", "time_local", "duration_minutes", "timezone")
    if any(values.get(key) in (None, "") for key in required):
        raise ValueError("Routine name, schedule, duration, and timezone are required.")
    routine_id = values.get("routine_id") or str(uuid4())
    now = _now()
    connection.execute(
        """INSERT INTO routines
        (routine_id,user_id,name,description,frequency,start_date,end_date,time_local,
         duration_minutes,timezone,selected_days_json,enabled,category,created_at,updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (routine_id, user_id, values["name"].strip(), values.get("description", "").strip(),
         values["frequency"], values["start_date"], values.get("end_date"),
         values["time_local"], int(values["duration_minutes"]), values["timezone"],
         json.dumps(list(values.get("selected_days", ()))),
         int(bool(values.get("enabled", True))), values.get("category", "CUSTOM"), now, now),
    )
    connection.commit()
    return routine_id


def get_routine(connection, routine_id, user_id):
    return _routine(connection.execute(
        "SELECT * FROM routines WHERE routine_id=? AND user_id=?", (routine_id, user_id)
    ).fetchone())


def list_routines(connection, user_id, include_disabled=True):
    clause = "" if include_disabled else " AND enabled=1"
    return [_routine(row) for row in connection.execute(
        f"SELECT * FROM routines WHERE user_id=?{clause} ORDER BY start_date,time_local,name",
        (user_id,),
    ).fetchall()]


def update_routine(connection, routine_id, user_id, values):
    current = get_routine(connection, routine_id, user_id)
    if not current:
        raise ValueError("Routine not found.")
    current.update(values)
    connection.execute(
        """UPDATE routines SET name=?,description=?,category=?,frequency=?,start_date=?,end_date=?,
        time_local=?,duration_minutes=?,timezone=?,selected_days_json=?,enabled=?,updated_at=?
        WHERE routine_id=? AND user_id=?""",
        (current["name"].strip(), current.get("description", ""), current.get("category", "CUSTOM"),
         current["frequency"],
         current["start_date"], current.get("end_date"), current["time_local"],
         int(current["duration_minutes"]), current["timezone"],
         json.dumps(list(current.get("selected_days", ()))), int(bool(current.get("enabled", True))),
         _now(), routine_id, user_id),
    )
    connection.commit()


def delete_routine(connection, routine_id, user_id):
    cursor = connection.execute(
        "DELETE FROM routines WHERE routine_id=? AND user_id=?", (routine_id, user_id)
    )
    connection.commit()
    if cursor.rowcount != 1:
        raise ValueError("Routine not found.")


def upsert_occurrences(connection, routine_id, user_id, occurrences):
    created = []
    for occurrence_date, scheduled_at in occurrences:
        existing = connection.execute(
            "SELECT occurrence_id FROM routine_occurrences WHERE routine_id=? AND user_id=? AND occurrence_date=?",
            (routine_id, user_id, occurrence_date),
        ).fetchone()
        if existing:
            created.append(existing["occurrence_id"])
            continue
        identifier = str(uuid4())
        connection.execute(
            """INSERT INTO routine_occurrences
            (occurrence_id,routine_id,user_id,occurrence_date,scheduled_at,status,created_at,updated_at)
            VALUES (?,?,?,?,?,'UPCOMING',?,?)""",
            (identifier, routine_id, user_id, occurrence_date,
             scheduled_at.isoformat(), _now(), _now()),
        )
        created.append(identifier)
    connection.commit()
    return created


def get_occurrence(connection, occurrence_id, user_id):
    return _occurrence(connection.execute(
        "SELECT * FROM routine_occurrences WHERE occurrence_id=? AND user_id=?",
        (occurrence_id, user_id),
    ).fetchone())


def list_occurrences(connection, user_id, routine_id=None, start=None, end=None):
    clauses, params = ["user_id=?"], [user_id]
    if routine_id:
        clauses.append("routine_id=?")
        params.append(routine_id)
    if start:
        clauses.append("occurrence_date>=?")
        params.append(start)
    if end:
        clauses.append("occurrence_date<=?")
        params.append(end)
    return [_occurrence(row) for row in connection.execute(
        f"SELECT * FROM routine_occurrences WHERE {' AND '.join(clauses)} "
        "ORDER BY occurrence_date, scheduled_at, occurrence_id", params
    ).fetchall()]


def set_occurrence_status(connection, occurrence_id, user_id, status, note=""):
    if status not in {"COMPLETED", "SKIPPED", "MISSED", "UPCOMING", "DUE", "CANCELLED"}:
        raise ValueError("Invalid routine occurrence status.")
    now = _now()
    cursor = connection.execute(
        """UPDATE routine_occurrences SET status=?,
        completed_at=CASE WHEN ?='COMPLETED' THEN ? ELSE completed_at END,
        skipped_at=CASE WHEN ?='SKIPPED' THEN ? ELSE skipped_at END,
        note=?,updated_at=? WHERE occurrence_id=? AND user_id=?""",
        (status, status, now, status, now, note.strip(), now, occurrence_id, user_id),
    )
    connection.commit()
    if cursor.rowcount != 1:
        raise ValueError("Routine occurrence not found.")


def mark_missed_before(connection, user_id, before_iso):
    cursor = connection.execute(
        """UPDATE routine_occurrences SET status='MISSED',updated_at=?
        WHERE user_id=? AND status IN ('UPCOMING','DUE') AND scheduled_at<?""",
        (_now(), user_id, before_iso),
    )
    connection.commit()
    return cursor.rowcount


def set_preference(connection, user_id, enabled=None, reminder_minutes=None):
    existing = connection.execute(
        "SELECT * FROM routine_preferences WHERE user_id=?", (user_id,)
    ).fetchone()
    current = {"enabled": 1, "reminder_minutes": 10}
    if existing:
        current.update(dict(existing))
    if enabled is not None:
        current["enabled"] = int(bool(enabled))
    if reminder_minutes is not None:
        current["reminder_minutes"] = int(reminder_minutes)
    connection.execute(
        """INSERT INTO routine_preferences(user_id,enabled,reminder_minutes,updated_at)
        VALUES (?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET enabled=excluded.enabled,
        reminder_minutes=excluded.reminder_minutes,updated_at=excluded.updated_at""",
        (user_id, current["enabled"], current["reminder_minutes"], _now()),
    )
    connection.commit()


def get_preference(connection, user_id):
    row = connection.execute(
        "SELECT * FROM routine_preferences WHERE user_id=?", (user_id,)
    ).fetchone()
    return dict(row) if row else {"user_id": user_id, "enabled": 1, "reminder_minutes": 10}


def record_event(connection, user_id, event_type, payload=None, routine_id=None, occurrence_id=None):
    identifier = str(uuid4())
    connection.execute(
        """INSERT INTO routine_events(event_id,user_id,routine_id,occurrence_id,event_type,
        payload_json,created_at) VALUES (?,?,?,?,?,?,?)""",
        (identifier, user_id, routine_id, occurrence_id, event_type,
         json.dumps(payload or {}, separators=(",", ":")), _now()),
    )
    connection.commit()
    return identifier


def list_events(connection, user_id, routine_id=None, limit=100):
    params = [user_id]
    clause = "user_id=?"
    if routine_id:
        clause += " AND routine_id=?"
        params.append(routine_id)
    params.append(max(1, min(int(limit), 500)))
    rows = connection.execute(
        f"SELECT * FROM routine_events WHERE {clause} ORDER BY created_at DESC LIMIT ?",
        params,
    ).fetchall()
    result = []
    for row in rows:
        value = dict(row)
        value["payload"] = json.loads(value.pop("payload_json") or "{}")
        result.append(value)
    return result
