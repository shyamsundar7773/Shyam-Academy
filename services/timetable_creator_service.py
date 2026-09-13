import json
import re
import sqlite3
from datetime import date, datetime, timedelta, timezone

from ai.gateway import AIGateway, AIProviderError
from database.repositories.module_repository import get_owned_module
from models.timetable_plan import PlannedSession, TimetablePlan
from services.timetable_service import CATEGORIES, TIME_PATTERN

VALID_STATUSES = {"Scheduled", "Completed", "Skipped"}
_TIME_FORMAT = "%I:%M %p"
_MONTH_PATTERN = (
    r"(?:January|February|March|April|May|June|July|August|September|October|November|December)"
)


def _required_string(value, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Plan field '{field}' is required.")
    return value.strip()


def _parse_date(value, field: str) -> str:
    value = _required_string(value, field)
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError as error:
        raise ValueError(f"Plan field '{field}' must be a valid ISO date.") from error


def _parse_time(value, field: str, allow_empty: bool = False) -> str | None:
    if allow_empty and (value is None or not str(value).strip()):
        return None
    value = _required_string(value, field).strip().upper()
    normalized = value.replace(".", "")
    if re.fullmatch(r"\d{1,2}\s*[AP]M", normalized):
        normalized = re.sub(r"(?i)(\d{1,2})\s*([AP]M)", r"\1:00 \2", normalized)
    elif re.fullmatch(r"\d{1,2}:\d{2}\s*[AP]M", normalized):
        normalized = re.sub(r"\s+", " ", normalized)
    elif re.fullmatch(r"\d{1,2}:\d{2}", normalized):
        try:
            return datetime.strptime(normalized, "%H:%M").strftime(_TIME_FORMAT).lstrip("0")
        except ValueError as error:
            raise ValueError(
                f"{field.replace('_', ' ').capitalize()} is invalid."
            ) from error
    else:
        raise ValueError(f"{field.replace('_', ' ').capitalize()} must use h:mm AM or h:mm PM.")
    try:
        return datetime.strptime(normalized, _TIME_FORMAT).strftime(_TIME_FORMAT).lstrip("0")
    except ValueError as error:
        raise ValueError(f"{field.replace('_', ' ').capitalize()} is invalid.") from error


def _normalize_category(value: str) -> str:
    normalized = re.sub(r"\s+", " ", value.strip()).casefold()
    exact = {
        category.casefold(): category
        for category in CATEGORIES
    }
    if normalized in exact:
        return exact[normalized]
    if normalized in {
        "sql",
        "sql fundamental",
        "sql fundamentals",
        "sql fundamental concepts",
        "sql fundamentals concepts",
    }:
        return "Level 1"
    if re.fullmatch(r"[a-z][a-z0-9 +#.-]* fundamentals?(?: concepts?)?", normalized):
        return "Level 1"
    raise ValueError("The timetable contains an invalid learning category.")


def _request_constraints(request: str) -> tuple[int | None, date | None, date | None, int | None, int | None]:
    day_words = {
        "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
        "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
        "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
        "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
        "nineteen": 19, "twenty": 20,
    }
    days_match = re.search(
        r"\b(\d+|one|two|three|four|five|six|seven|eight|nine|ten|"
        r"eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|"
        r"eighteen|nineteen|twenty)\s+days?\b",
        request,
        re.IGNORECASE,
    )
    requested_days = (
        int(days_match.group(1))
        if days_match and days_match.group(1).isdigit()
        else day_words.get(days_match.group(1).casefold()) if days_match else None
    )
    date_match = re.search(
        rf"\b{_MONTH_PATTERN}\s+(\d{{1,2}})(?:,?\s*(\d{{4}}))?"
        rf"\s*(?:to|-)\s*"
        rf"(?:(?:{_MONTH_PATTERN})\s+)?(\d{{1,2}})(?:,?\s*(\d{{4}}))?",
        request,
        re.IGNORECASE,
    )
    start_date = end_date = None
    if date_match:
        month_names = re.findall(_MONTH_PATTERN, date_match.group(0), re.IGNORECASE)
        start_year = int(date_match.group(2) or date.today().year)
        end_year = int(date_match.group(4) or start_year)
        try:
            start_date = date(
                start_year,
                datetime.strptime(month_names[0], "%B").month,
                int(date_match.group(1)),
            )
            end_date = date(
                end_year,
                datetime.strptime(month_names[-1], "%B").month,
                int(date_match.group(3)),
            )
            if end_date < start_date and not date_match.group(4):
                end_date = end_date.replace(year=end_date.year + 1)
        except (IndexError, ValueError):
            start_date = end_date = None

    time_match = re.search(
        r"\b(?:between|from)\s+([0-9]{1,2}(?::[0-9]{2})?\s*(?:am|pm)?|[0-9]{1,2}:[0-9]{2})"
        r"\s+(?:to|and|-)\s+([0-9]{1,2}(?::[0-9]{2})?\s*(?:am|pm)?|[0-9]{1,2}:[0-9]{2})\b",
        request,
        re.IGNORECASE,
    )
    start_minutes = end_minutes = None
    if time_match:
        try:
            start = _parse_time(time_match.group(1), "start_time")
            end = _parse_time(time_match.group(2), "end_time")
            start_minutes = datetime.strptime(start, _TIME_FORMAT).hour * 60 + datetime.strptime(
                start, _TIME_FORMAT
            ).minute
            end_minutes = datetime.strptime(end, _TIME_FORMAT).hour * 60 + datetime.strptime(
                end, _TIME_FORMAT
            ).minute
        except ValueError:
            start_minutes = end_minutes = None
    return requested_days, start_date, end_date, start_minutes, end_minutes


def _apply_request_constraints(
    plan: TimetablePlan, request: str
) -> TimetablePlan:
    requested_days, window_start, window_end, time_start, time_end = _request_constraints(request)
    sessions = plan.sessions
    if window_start and window_end:
        sessions = [
            session for session in sessions
            if window_start.isoformat() <= session.session_date <= window_end.isoformat()
        ]
    if requested_days is not None and window_start and window_end:
        allowed_dates = sorted({session.session_date for session in sessions})[:requested_days]
        sessions = [session for session in sessions if session.session_date in allowed_dates]
        if len(allowed_dates) != requested_days:
            raise ValueError(
                "The AI timetable did not produce the requested number of dates "
                "inside the requested date range."
            )
    if time_start is not None and time_end is not None:
        def in_range(session: PlannedSession) -> bool:
            value = datetime.strptime(session.scheduled_time, _TIME_FORMAT)
            minutes = value.hour * 60 + value.minute
            return time_start <= minutes <= time_end

        if any(not in_range(session) for session in sessions):
            raise ValueError("A generated session falls outside the requested time range.")
    return TimetablePlan(
        plan.title, plan.module_name, plan.description, plan.start_date,
        plan.end_date, plan.timezone, plan.assumptions, sessions,
    )


def _session_window(session: PlannedSession) -> tuple[datetime, datetime]:
    start = datetime.combine(
        date.fromisoformat(session.session_date),
        datetime.strptime(session.scheduled_time, _TIME_FORMAT).time(),
    )
    if session.scheduled_end_time:
        end = datetime.combine(
            date.fromisoformat(session.session_date),
            datetime.strptime(session.scheduled_end_time, _TIME_FORMAT).time(),
        )
        if end <= start:
            raise ValueError("A session end time must be after its start time.")
    else:
        end = start + timedelta(hours=1)
    return start, end


def _validate_sessions(raw_sessions) -> list[PlannedSession]:
    if not isinstance(raw_sessions, list) or not raw_sessions:
        raise ValueError("The timetable proposal must contain at least one session.")
    sessions = []
    seen = set()
    for index, raw in enumerate(raw_sessions, start=1):
        if not isinstance(raw, dict):
            raise ValueError("Each planned session must be an object.")
        session_date = _parse_date(raw.get("session_date"), "session_date")
        scheduled_time = _parse_time(raw.get("scheduled_time"), "scheduled_time")
        scheduled_end_time = _parse_time(
            raw.get("scheduled_end_time"), "scheduled_end_time", allow_empty=True
        )
        try:
            category = _normalize_category(_required_string(raw.get("category"), "category"))
        except ValueError as error:
            raise ValueError(f"Session {index} has an invalid category.") from error
        topic = _required_string(raw.get("topic"), "topic")
        title = _required_string(raw.get("session_title"), "session_title")
        prompt = _required_string(raw.get("prompt"), "prompt")
        day_number = raw.get("day_number", index)
        if not isinstance(day_number, int) or isinstance(day_number, bool) or day_number < 1:
            raise ValueError(f"Session {index} has an invalid day number.")
        status = raw.get("status", "Scheduled")
        if status not in VALID_STATUSES:
            raise ValueError(f"Session {index} has an invalid status.")
        key = (session_date, scheduled_time)
        if key in seen:
            raise ValueError("The timetable proposal contains duplicate sessions.")
        seen.add(key)
        session = PlannedSession(
            session_date, scheduled_time, category, topic, title, prompt,
            scheduled_end_time, status, day_number,
        )
        _session_window(session)
        sessions.append(session)

    sessions.sort(key=lambda item: (item.session_date, item.scheduled_time))
    for index, left in enumerate(sessions):
        for right in sessions[index + 1:]:
            if left.session_date != right.session_date:
                break
            left_start, left_end = _session_window(left)
            right_start, right_end = _session_window(right)
            if left_start < right_end and right_start < left_end:
                raise ValueError("The timetable proposal contains overlapping sessions.")
    return sessions


def _validate_assumptions(value) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError("Plan field 'assumptions' must be a list of strings.")
    return [item.strip() for item in value if item.strip()]


def parse_plan(response: str) -> TimetablePlan:
    if not isinstance(response, str) or not response.strip():
        raise ValueError("The AI returned an empty timetable proposal.")
    candidate = response.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)\s*```", candidate, re.IGNORECASE | re.DOTALL)
    if fenced:
        candidate = fenced.group(1).strip()
    else:
        start, end = candidate.find("{"), candidate.rfind("}")
        if start >= 0 and end > start:
            candidate = candidate[start:end + 1]
    try:
        raw = json.loads(candidate)
    except json.JSONDecodeError as error:
        raise ValueError("The AI timetable response was not valid JSON.") from error
    if not isinstance(raw, dict):
        raise ValueError("The AI timetable response must be an object.")
    sessions = _validate_sessions(raw.get("sessions"))
    start_date = _parse_date(raw.get("start_date"), "start_date")
    end_date = _parse_date(raw.get("end_date"), "end_date")
    if date.fromisoformat(end_date) < date.fromisoformat(start_date):
        raise ValueError("The timetable end date cannot be before its start date.")
    if any(
        not (start_date <= session.session_date <= end_date) for session in sessions
    ):
        raise ValueError("A session falls outside the plan date range.")
    return TimetablePlan(
        title=_required_string(raw.get("title"), "title"),
        module_name=_required_string(raw.get("module_name"), "module_name"),
        description=_required_string(raw.get("description"), "description"),
        start_date=start_date,
        end_date=end_date,
        timezone=_required_string(raw.get("timezone", "local"), "timezone"),
        assumptions=_validate_assumptions(raw.get("assumptions", [])),
        sessions=sessions,
    )


def generate_plan(gateway: AIGateway, request: str) -> TimetablePlan:
    if not isinstance(request, str) or not request.strip():
        raise ValueError("Describe the timetable you want first.")
    try:
        response = gateway.generate_timetable(request.strip())
    except AIProviderError:
        raise
    except Exception as error:
        raise AIProviderError("The AI provider is currently unavailable.") from error
    return _apply_request_constraints(parse_plan(response), request)


def detect_conflicts(
    connection: sqlite3.Connection, user_id: str, plan: TimetablePlan,
    module_id: int | None = None,
) -> list[str]:
    if module_id is None:
        return []
    existing = connection.execute(
        """
        SELECT session_date, scheduled_time FROM sessions
        WHERE owner_user_id = ? AND module_id = ?
        """,
        (user_id, module_id),
    ).fetchall()
    occupied = []
    for row in existing:
        start = datetime.combine(
            date.fromisoformat(row["session_date"]),
            datetime.strptime(row["scheduled_time"], _TIME_FORMAT).time(),
        )
        occupied.append((start, start + timedelta(hours=1)))
    conflicts = []
    for session in plan.sessions:
        start, end = _session_window(session)
        if any(start < old_end and old_start < end for old_start, old_end in occupied):
            conflicts.append(f"{session.session_date} at {session.scheduled_time}")
    return conflicts


def persist_plan(
    connection: sqlite3.Connection, user_id: str, plan: TimetablePlan,
    module_id: int | None = None,
) -> tuple[int, list[int]]:
    connection.execute("BEGIN")
    try:
        if module_id is None:
            duplicate = connection.execute(
                "SELECT module_id FROM modules WHERE owner_user_id = ? AND module_name = ?",
                (user_id, plan.module_name),
            ).fetchone()
            if duplicate is not None:
                raise ValueError(
                    "A module with that name already exists. Select it to reuse it."
                )
            now = datetime.now(timezone.utc).isoformat()
            cursor = connection.execute(
                """
                INSERT INTO modules
                    (module_name, description, owner_user_id, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (plan.module_name, plan.description, user_id, now, now),
            )
            module_id = int(cursor.lastrowid)
        elif get_owned_module(connection, module_id, user_id) is None:
            raise ValueError("The selected module could not be found.")

        conflicts = detect_conflicts(connection, user_id, plan, module_id)
        if conflicts:
            raise ValueError("Existing sessions conflict with: " + ", ".join(conflicts))
        session_ids = []
        for session in plan.sessions:
            cursor = connection.execute(
                """
                INSERT INTO sessions
                    (module_id, day_number, session_date, category, topic,
                     scheduled_time, scheduled_end_time, prompt, status, owner_user_id,
                     created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
                """,
                (
                    module_id, session.day_number, session.session_date,
                    session.category, session.topic, session.scheduled_time,
                    session.scheduled_end_time or "", session.prompt, session.status, user_id,
                ),
            )
            session_ids.append(int(cursor.lastrowid))
        connection.commit()
        from alarms.service import reconcile_session_alarm
        for session_id in session_ids:
            session = connection.execute(
                "SELECT * FROM sessions WHERE session_id=?", (session_id,)
            ).fetchone()
            reconcile_session_alarm(connection, user_id, session)
        return module_id, session_ids
    except Exception:
        connection.rollback()
        raise
