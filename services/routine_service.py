import re
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from database.repositories import routine_repository as repo
from models.routine import (
    Routine,
    RoutineFrequency,
    RoutineMetrics,
    generate_occurrences,
    normalize_selected_days,
    validate_frequency,
    validate_time,
)
from notifications import repository as notification_repository
from notifications.service import schedule_routine_notifications


def _zone(name):
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError:
        return ZoneInfo("Asia/Kolkata")


def _routine(row):
    return Routine(
        row["routine_id"], row["user_id"], row["name"], row["description"],
        row["frequency"], row["start_date"], row["end_date"], row["time_local"],
        int(row["duration_minutes"]), row["timezone"], tuple(row["selected_days"]), bool(row["enabled"]),
        row["category"],
    )


def validate_routine(values):
    values = dict(values)
    values["name"] = str(values.get("name", "")).strip()
    values["category"] = str(values.get("category", "CUSTOM")).strip().upper() or "CUSTOM"
    if not values["name"]:
        raise ValueError("Routine name is required.")
    values["frequency"] = validate_frequency(values.get("frequency", ""))
    values["time_local"] = validate_time(values.get("time_local", ""))
    values["selected_days"] = normalize_selected_days(values.get("selected_days", ()))
    if values["frequency"] == RoutineFrequency.SELECTED_DAYS and not values["selected_days"]:
        raise ValueError("Choose at least one day for a selected-days routine.")
    date.fromisoformat(values["start_date"])
    if values.get("end_date"):
        date.fromisoformat(values["end_date"])
        if values["end_date"] < values["start_date"]:
            raise ValueError("Routine end date cannot precede its start date.")
    values["duration_minutes"] = int(values.get("duration_minutes", 0))
    if values["duration_minutes"] <= 0 or values["duration_minutes"] > 1440:
        raise ValueError("Routine duration must be between 1 and 1440 minutes.")
    _zone(values.get("timezone", "Asia/Kolkata"))
    return values


def academic_conflicts(connection, user_id, occurrences, duration_minutes):
    conflicts = []
    sessions = connection.execute(
        "SELECT session_id,session_date,scheduled_time,scheduled_end_time,topic "
        "FROM sessions WHERE owner_user_id=?", (user_id,)
    ).fetchall()
    for occurrence_date, local_dt in occurrences:
        start = local_dt.time()
        start_minutes = start.hour * 60 + start.minute
        end_minutes = start_minutes + duration_minutes
        for session in sessions:
            if session["session_date"] != occurrence_date:
                continue
            try:
                parsed = datetime.strptime(session["scheduled_time"], "%I:%M %p")
                s_start = parsed.hour * 60 + parsed.minute
                if session["scheduled_end_time"]:
                    parsed_end = datetime.strptime(session["scheduled_end_time"], "%I:%M %p")
                    s_end = parsed_end.hour * 60 + parsed_end.minute
                else:
                    s_end = s_start + 60
            except ValueError:
                continue
            if start_minutes < s_end and s_start < end_minutes:
                conflicts.append({
                    "session_id": session["session_id"], "topic": session["topic"],
                    "date": occurrence_date, "routine_start": local_dt.strftime("%H:%M"),
                })
    return conflicts


def create_routine(connection, user_id, values, generate=True, schedule_notifications=True):
    values = validate_routine(values)
    routine_id = repo.create_routine(connection, user_id, values)
    if generate:
        materialize_occurrences(connection, user_id, routine_id, date.fromisoformat(values["start_date"]))
    if schedule_notifications:
        schedule_routine_notifications(connection, user_id, routine_id)
    from services.routine_events import emit, RoutineEvent
    emit(connection, RoutineEvent("ROUTINE_CREATED", user_id, routine_id))
    return routine_id


def update_routine(connection, user_id, routine_id, values):
    current = repo.get_routine(connection, routine_id, user_id)
    if not current:
        raise ValueError("Routine not found.")
    merged = dict(current)
    merged.update(values)
    merged = validate_routine(merged)
    notification_repository.cancel_for_routine(connection, user_id, routine_id, "Routine rescheduled")
    repo.update_routine(connection, routine_id, user_id, merged)
    connection.execute(
        "DELETE FROM routine_occurrences WHERE routine_id=? AND status IN ('UPCOMING','DUE')",
        (routine_id,),
    )
    connection.commit()
    materialize_occurrences(connection, user_id, routine_id, date.fromisoformat(merged["start_date"]))
    schedule_routine_notifications(connection, user_id, routine_id)


def delete_routine(connection, user_id, routine_id):
    notification_repository.cancel_for_routine(connection, user_id, routine_id, "Routine deleted")
    repo.delete_routine(connection, routine_id, user_id)
    from services.routine_events import emit, RoutineEvent
    emit(connection, RoutineEvent("ROUTINE_DELETED", user_id, routine_id))


def materialize_occurrences(connection, user_id, routine_id, through=None, days=14):
    row = repo.get_routine(connection, routine_id, user_id)
    if not row:
        raise ValueError("Routine not found.")
    routine = _routine(row)
    start = max(date.today(), date.fromisoformat(routine.start_date))
    end = through or (start + timedelta(days=days))
    generated = generate_occurrences(routine, start, end)
    normalized = []
    zone = _zone(routine.timezone)
    for occurrence_date, local_dt in generated:
        normalized.append((occurrence_date, local_dt.replace(tzinfo=zone)))
    return repo.upsert_occurrences(connection, routine_id, user_id, normalized)


def list_upcoming(connection, user_id, start=None, end=None):
    start = start or date.today().isoformat()
    end = end or (date.today() + timedelta(days=14)).isoformat()
    routines = repo.list_routines(connection, user_id, include_disabled=False)
    active_ids = {routine["routine_id"] for routine in routines}
    for routine in routines:
        materialize_occurrences(connection, user_id, routine["routine_id"], date.fromisoformat(end))
    return [
        row for row in repo.list_occurrences(connection, user_id, start=start, end=end)
        if row["routine_id"] in active_ids
    ]


def complete_occurrence(connection, user_id, occurrence_id, note=""):
    occurrence = repo.get_occurrence(connection, occurrence_id, user_id)
    repo.set_occurrence_status(connection, occurrence_id, user_id, "COMPLETED", note)
    notification_repository.suppress_routine_missed(connection, user_id, occurrence_id)
    from services.routine_events import occurrence_event
    occurrence_event(connection, user_id, occurrence["routine_id"], occurrence_id, "OCCURRENCE_COMPLETED")


def skip_occurrence(connection, user_id, occurrence_id, note=""):
    occurrence = repo.get_occurrence(connection, occurrence_id, user_id)
    repo.set_occurrence_status(connection, occurrence_id, user_id, "SKIPPED", note)
    notification_repository.cancel_for_routine_occurrence(connection, user_id, occurrence_id, "Routine skipped")
    from services.routine_events import occurrence_event
    occurrence_event(connection, user_id, occurrence["routine_id"], occurrence_id, "OCCURRENCE_SKIPPED")


def mark_missed(connection, user_id, before=None):
    when = before or datetime.now(timezone.utc).isoformat()
    count = repo.mark_missed_before(connection, user_id, when)
    from services.routine_events import emit, RoutineEvent
    if count:
        emit(connection, RoutineEvent("OCCURRENCES_MISSED", user_id, payload={"count": count}))
    return count


def get_metrics(connection, user_id, start=None, end=None):
    rows = repo.list_occurrences(connection, user_id, start, end)
    completed_dates = {row["occurrence_date"] for row in rows if row["status"] == "COMPLETED"}
    ordered_dates = sorted({row["occurrence_date"] for row in rows})
    best = current = 0
    previous = None
    for value in ordered_dates:
        if value in completed_dates:
            if previous and (date.fromisoformat(value) - date.fromisoformat(previous)).days == 1:
                current += 1
            else:
                current = 1
            best = max(best, current)
            previous = value
        else:
            current = 0
            previous = None
    scheduled = len(rows)
    completed = sum(row["status"] == "COMPLETED" for row in rows)
    skipped = sum(row["status"] == "SKIPPED" for row in rows)
    missed = sum(row["status"] == "MISSED" for row in rows)
    return RoutineMetrics(
        scheduled, completed, skipped, missed, current, best,
        round(completed / scheduled * 100, 1) if scheduled else 0.0,
    )


def get_history(connection, user_id, routine_id=None, start=None, end=None):
    return repo.list_occurrences(connection, user_id, routine_id, start, end)


def preview_natural_language(text, today=None):
    if not text or not text.strip():
        raise ValueError("Describe the routine first.")
    today = today or date.today()
    lowered = text.lower()
    frequency = "WEEKLY" if "weekly" in lowered or "every week" in lowered else (
        "SELECTED_DAYS" if any(day in lowered for day in ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")) else "DAILY"
    )
    days = tuple(index for index, name in enumerate(
        ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
    ) if name in lowered)
    match = re.search(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", lowered)
    hour, minute, suffix = (7, 0, "pm")
    if match:
        hour, minute, suffix = int(match.group(1)), int(match.group(2) or 0), match.group(3) or "pm"
    if suffix == "pm" and hour < 12:
        hour += 12
    if suffix == "am" and hour == 12:
        hour = 0
    duration_match = re.search(r"(\d+)\s*(?:minute|min)", lowered)
    name = re.sub(r"\b(?:every|daily|weekly|on|at|\d{1,2}(?::\d{2})?\s*(?:am|pm)?|\d+\s*(?:minutes?|mins?))\b", "", text, flags=re.I)
    name = " ".join(name.split()).strip(" ,.-") or "Personal routine"
    return {
        "name": name.title(), "description": text.strip(), "frequency": frequency,
        "category": (
            "MOVEMENT" if any(word in lowered for word in ("walk", "exercise", "stretch", "run"))
            else "CUSTOM"
        ),
        "start_date": today.isoformat(), "time_local": f"{hour:02d}:{minute:02d}",
        "duration_minutes": int(duration_match.group(1)) if duration_match else 20,
        "timezone": "Asia/Kolkata", "selected_days": days,
    }
