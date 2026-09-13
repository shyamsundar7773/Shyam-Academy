import json
import re
import sqlite3
import random
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from ai.gateway import AIGateway, AIProviderError
from database.repositories.module_repository import get_owned_module
from models.timetable_plan import PlannedSession, TimetablePlan
from services.timetable_service import CATEGORIES, TIME_PATTERN

VALID_STATUSES = {"Scheduled", "Completed", "Skipped"}
_TIME_FORMAT = "%I:%M %p"
_MONTH_PATTERN = (
    r"(?:January|February|March|April|May|June|July|August|September|October|November|December|"
    r"Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)"
)
_MONTHS = {
    name.casefold(): index
    for index, name in enumerate(
        ("January", "February", "March", "April", "May", "June",
         "July", "August", "September", "October", "November", "December"),
        start=1,
    )
}
_MONTHS.update({
    alias.casefold(): index
    for alias, index in (
        ("jan", 1), ("feb", 2), ("mar", 3), ("apr", 4), ("jun", 6),
        ("jul", 7), ("aug", 8), ("sep", 9), ("sept", 9), ("oct", 10),
        ("nov", 11), ("dec", 12),
    )
})


class DateConstraintConflict(ValueError):
    """Raised when a duration contradicts an explicit timetable range."""

    code = "DATE_CONSTRAINT_CONFLICT"

    def __init__(
        self,
        requested_duration_days: int,
        explicit_start_date: date,
        explicit_end_date: date,
        range_days: int,
    ):
        self.details = {
            "requested_duration_days": requested_duration_days,
            "explicit_start_date": explicit_start_date.isoformat(),
            "explicit_end_date": explicit_end_date.isoformat(),
            "inclusive_range_length": range_days,
            "reason": (
                "The requested duration does not match the inclusive explicit "
                "date range."
            ),
        }
        super().__init__(
            f"{self.code}: requested duration "
            f"{requested_duration_days} days, explicit range "
            f"{explicit_start_date.isoformat()} to {explicit_end_date.isoformat()} "
            f"contains {range_days} inclusive days. {self.details['reason']}"
        )


@dataclass(frozen=True)
class TimetableSpec:
    domain: str | None
    topic_list: tuple[str, ...]
    start_date: date | None
    end_date: date | None
    exact_date: date | None
    explicit_dates: tuple[date, ...]
    requested_duration_days: int | None
    requested_session_count: int | None
    sessions_per_day: int | None
    allowed_categories: tuple[str, ...]
    required_categories: tuple[str, ...]
    excluded_categories: tuple[str, ...]
    random_time_requested: bool
    upcoming_time_requested: bool
    time_start_minutes: int | None
    time_end_minutes: int | None
    timezone: str
    daily_coverage: bool

    @property
    def allowed_dates(self) -> tuple[date, ...]:
        if self.explicit_dates:
            return self.explicit_dates
        if self.exact_date:
            return (self.exact_date,)
        if self.start_date and self.end_date:
            return tuple(
                self.start_date + timedelta(days=offset)
                for offset in range((self.end_date - self.start_date).days + 1)
            )
        return ()


@dataclass(frozen=True)
class ConstraintResult:
    valid: bool
    errors: tuple[str, ...]


@dataclass(frozen=True)
class CurriculumTopic:
    topic_id: str
    original_text: str
    normalized_text: str
    classification: str
    suggested_category: str


def _normalize_topic_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip(" \t\r\n-•*"))


def extract_curriculum_topics(request: str) -> tuple[CurriculumTopic, ...]:
    """Extract and deduplicate explicit curriculum items without trusting the AI."""
    match = re.search(r"\[([^\]]+)\]", request, re.DOTALL)
    if match:
        candidates = re.split(r",|\n|;", match.group(1))
    else:
        marker = re.search(
            r"(?:topics?|curriculum)\s*:\s*(.*)", request, re.IGNORECASE | re.DOTALL
        )
        candidates = (
            re.split(r"\n", marker.group(1))
            if marker
            else []
        )
    topics: list[CurriculumTopic] = []
    seen: set[str] = set()
    for candidate in candidates:
        normalized = _normalize_topic_text(candidate)
        normalized = re.sub(r"^\d+[\.)]\s*", "", normalized)
        if len(normalized) < 2 or normalized.casefold() in seen:
            continue
        seen.add(normalized.casefold())
        lowered = normalized.casefold()
        if re.search(r"\b(interview|mock interview)\b", lowered):
            category = "Interview Room" if "mock" in lowered else "Interview Preparation"
        elif re.search(r"\b(test|assessment|quiz)\b", lowered):
            category = "Test"
        elif re.search(r"\b(problem|challenge|practice|exercise)\b", lowered):
            category = "Problem Solving"
        elif re.search(r"\b(advanced|optimization|performance|window|cte|index|transaction)\b", lowered):
            category = "Level 2"
        else:
            category = "Level 1"
        topics.append(CurriculumTopic(
            topic_id=f"topic-{len(topics) + 1}",
            original_text=normalized,
            normalized_text=normalized.casefold(),
            classification=category,
            suggested_category=category,
        ))
    return tuple(topics)


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
        normalized = re.sub(r"(?i)\s*([AP]M)$", r" \1", normalized)
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


def _parse_requested_date(month: str, day: str, year: str | None) -> date:
    parsed_year = int(year or date.today().year)
    numeric_day = re.sub(r"(?:st|nd|rd|th)$", "", str(day), flags=re.IGNORECASE)
    return date(parsed_year, _MONTHS[month.casefold()], int(numeric_day))


def _request_constraints(request: str) -> TimetableSpec:
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
        r"eighteen|nineteen|twenty)\s*[- ]\s*days?\b",
        request,
        re.IGNORECASE,
    )
    requested_days = (
        int(days_match.group(1))
        if days_match and days_match.group(1).isdigit()
        else day_words.get(days_match.group(1).casefold()) if days_match else None
    )
    session_match = re.search(
        r"\b(\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s+sessions?\b"
        r"(?!\s+(?:each|per)\s+day)",
        request, re.IGNORECASE,
    )
    requested_session_count = None
    if session_match:
        token = session_match.group(1).casefold()
        requested_session_count = (
            int(token) if token.isdigit() else day_words[token]
        )
    date_token = (
        rf"({_MONTH_PATTERN})\s+(\d{{1,2}}(?:st|nd|rd|th)?)(?:,?\s*(\d{{4}}))?"
    )
    range_match = re.search(
        rf"\b(?:between\s+)?{date_token}\s*(?:to|through|and|-)\s*"
        rf"(?:(?P<end_month>{_MONTH_PATTERN})\s+)?"
        rf"(?P<end_day>\d{{1,2}}(?:st|nd|rd|th)?)(?:,?\s*(?P<end_year>\d{{4}}))?",
        request, re.IGNORECASE,
    )
    numeric_range_match = re.search(
        r"\b(?P<start_day>\d{1,2})[/-](?P<start_month>\d{1,2})[/-]"
        r"(?P<start_year>\d{4})\s*(?:to|through|-)\s*"
        r"(?P<end_day>\d{1,2})[/-](?P<end_month>\d{1,2})[/-]"
        r"(?P<end_year>\d{4})\b",
        request,
        re.IGNORECASE,
    )
    range_start_index = (
        range_match.start() if range_match
        else numeric_range_match.start() if numeric_range_match
        else None
    )
    start_date = end_date = exact_date = None
    explicit_dates: tuple[date, ...] = ()
    if range_match:
        try:
            start_date = _parse_requested_date(
                range_match.group(1), range_match.group(2), range_match.group(3)
            )
            end_month = range_match.group("end_month") or range_match.group(1)
            end_year = range_match.group("end_year") or range_match.group(3)
            end_date = _parse_requested_date(
                end_month, range_match.group("end_day"), end_year
            )
            if end_date < start_date and not range_match.group("end_year"):
                end_date = end_date.replace(year=end_date.year + 1)
        except (KeyError, ValueError):
            start_date = end_date = None
    elif numeric_range_match:
        try:
            start_date = date(
                int(numeric_range_match.group("start_year")),
                int(numeric_range_match.group("start_month")),
                int(numeric_range_match.group("start_day")),
            )
            end_date = date(
                int(numeric_range_match.group("end_year")),
                int(numeric_range_match.group("end_month")),
                int(numeric_range_match.group("end_day")),
            )
            if end_date < start_date:
                raise ValueError("The numeric date range ends before it starts.")
        except ValueError:
            start_date = end_date = None
    else:
        listed_dates = []
        for match in re.finditer(date_token, request, re.IGNORECASE):
            try:
                listed_dates.append(
                    _parse_requested_date(match.group(1), match.group(2), match.group(3))
                )
            except (KeyError, ValueError):
                listed_dates = []
                break
        if len(listed_dates) > 1:
            explicit_dates = tuple(dict.fromkeys(listed_dates))
        single_match = re.search(
            rf"\b{date_token}\b", request, re.IGNORECASE
        )
        if single_match and not explicit_dates:
            try:
                exact_date = _parse_requested_date(
                    single_match.group(1), single_match.group(2), single_match.group(3)
                )
            except (KeyError, ValueError):
                exact_date = None

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
    starts_duration = bool(
        re.search(r"\b(?:starting|beginning|commencing)\b", request, re.I)
    )
    if exact_date is not None and requested_days and starts_duration:
        start_date, end_date, exact_date = (
            exact_date,
            exact_date + timedelta(days=requested_days - 1),
            None,
        )
    elif exact_date is None and start_date and end_date and requested_days:
        range_days = (end_date - start_date).days + 1
        if range_days != requested_days:
            range_prefix = request[:range_start_index] if range_start_index is not None else ""
            means_window = bool(
                re.search(
                    r"(?:\bwithin\b|\bdate\s*[-:]?)\s*$",
                    range_prefix,
                    re.IGNORECASE,
                )
            )
            if means_window:
                explicit_dates = tuple(
                    start_date + timedelta(days=offset)
                    for offset in range(requested_days)
                )
            else:
                raise DateConstraintConflict(
                    requested_days, start_date, end_date, range_days
                )
    daily_coverage = bool(
        re.search(r"\b(?:daily|each day|every day|one session each day|one per day)\b", request, re.I)
    )
    sessions_per_day_match = re.search(
        r"\b(\d+|one|two|three|four|five)\s+sessions?\s+per\s+day\b",
        request, re.I,
    )
    sessions_per_day = None
    if sessions_per_day_match:
        token = sessions_per_day_match.group(1).casefold()
        sessions_per_day = int(token) if token.isdigit() else day_words[token]
        daily_coverage = True
    all_categories = bool(re.search(
        r"\ball (?:the )?(?:timetable )?categories?\b|\bevery category\b|"
        r"\bfull category coverage\b|\bcomplete timetable\b",
        request,
        re.I,
    ))
    required_categories = tuple(CATEGORIES if all_categories else ())
    random_time_requested = bool(re.search(
        r"\brandom(?:ly)?(?:\s+\w+){0,2}\s+(?:times?|timing)\b|"
        r"\brandomly\s+timed\b|"
        r"\bfill\s+the\s+random\b|\brandom\s+in\s+all\s+categories\b",
        request,
        re.I,
    ))
    upcoming_time_requested = bool(re.search(r"\bupcoming\b|\bin the future\b", request, re.I))
    topic_list = tuple(topic.original_text for topic in extract_curriculum_topics(request))
    if requested_days and not (start_date or exact_date or explicit_dates):
        start_date = date.today()
        end_date = start_date + timedelta(days=requested_days - 1)
    return TimetableSpec(
        domain=None,
        topic_list=topic_list,
        start_date=start_date,
        end_date=end_date,
        exact_date=exact_date,
        explicit_dates=explicit_dates,
        requested_duration_days=requested_days,
        requested_session_count=requested_session_count,
        sessions_per_day=sessions_per_day or (1 if daily_coverage else None),
        allowed_categories=tuple(CATEGORIES),
        required_categories=required_categories,
        excluded_categories=(),
        random_time_requested=random_time_requested,
        upcoming_time_requested=upcoming_time_requested,
        time_start_minutes=start_minutes,
        time_end_minutes=end_minutes,
        timezone="Asia/Kolkata",
        daily_coverage=daily_coverage,
    )


def _apply_request_constraints(
    plan: TimetablePlan, request: str, reallocate_random_times: bool = True
) -> TimetablePlan:
    spec = _request_constraints(request)
    sessions = list(plan.sessions)
    allowed_dates = spec.allowed_dates
    if spec.exact_date:
        sessions = [_replace_session_date(session, spec.exact_date) for session in sessions]
        if spec.required_categories:
            by_category = {
                session.category: session
                for session in reversed(sessions)
                if session.category in spec.required_categories
            }
            if set(by_category) == set(spec.required_categories):
                sessions = [
                    by_category[category] for category in spec.required_categories
                ]
        if spec.sessions_per_day and not spec.required_categories:
            if len(sessions) < spec.sessions_per_day:
                raise ValueError("SESSION_COUNT_MISMATCH")
            sessions = sessions[:spec.sessions_per_day]
    elif allowed_dates:
        allowed_values = {item.isoformat() for item in allowed_dates}
        outside = [session for session in sessions if session.session_date not in allowed_values]
        if outside:
            if spec.requested_duration_days:
                sessions = [
                    session for session in sessions
                    if session.session_date in allowed_values
                ]
            else:
                sessions = [
                    _replace_session_date(
                        session, allowed_dates[index % len(allowed_dates)]
                    )
                    for index, session in enumerate(sessions)
                ]
        if (spec.daily_coverage or spec.requested_duration_days) and not (
            spec.required_categories
        ):
            missing = {
                item.isoformat() for item in allowed_dates
            } - {session.session_date for session in sessions}
            if missing:
                raise ValueError("DATE_COVERAGE_MISMATCH")
        if spec.sessions_per_day and not spec.required_categories:
            selected: list[PlannedSession] = []
            for allowed_date in allowed_dates:
                day_sessions = [
                    session for session in sessions
                    if session.session_date == allowed_date.isoformat()
                ]
                if len(day_sessions) < spec.sessions_per_day:
                    raise ValueError("SESSION_COUNT_MISMATCH")
                selected.extend(day_sessions[:spec.sessions_per_day])
            sessions = selected
    if spec.required_categories and reallocate_random_times:
        sessions = _ensure_category_matrix(sessions, spec, request)
    if spec.random_time_requested and reallocate_random_times:
        sessions = _assign_random_times(sessions, spec)
    elif spec.required_categories and reallocate_random_times:
        sessions = _assign_random_times(sessions, spec, seed=0)
    if spec.time_start_minutes is not None and spec.time_end_minutes is not None:
        def in_range(session: PlannedSession) -> bool:
            value = datetime.strptime(session.scheduled_time, _TIME_FORMAT)
            minutes = value.hour * 60 + value.minute
            return spec.time_start_minutes <= minutes <= spec.time_end_minutes

        if any(not in_range(session) for session in sessions):
            raise ValueError("A generated session falls outside the requested time range.")
    if (
        spec.requested_session_count is not None
        and len(sessions) != spec.requested_session_count
    ):
        raise ValueError("SESSION_COUNT_MISMATCH")
    if allowed_dates:
        start_date = allowed_dates[0].isoformat()
        end_date = allowed_dates[-1].isoformat()
    else:
        start_date, end_date = plan.start_date, plan.end_date
    result = TimetablePlan(
        plan.title, plan.module_name, plan.description, start_date,
        end_date, spec.timezone, plan.assumptions, _validate_sessions(
            [vars(session) for session in sessions]
        ),
    )
    validation = validate_plan_constraints(result, spec)
    if not validation.valid:
        raise ValueError(validation.errors[0])
    if any(
        not (result.start_date <= session.session_date <= result.end_date)
        for session in result.sessions
    ):
        raise ValueError("SESSION_DATE_OUTSIDE_REQUESTED_RANGE")
    return result


def apply_request_constraints(
    plan: TimetablePlan, request: str, preserve_random_times: bool = False
) -> TimetablePlan:
    """Re-apply canonical hard constraints after preview edits."""
    return _apply_request_constraints(
        plan, request, reallocate_random_times=not preserve_random_times
    )


def validate_plan_constraints(
    plan: TimetablePlan, spec: TimetableSpec | str
) -> ConstraintResult:
    """Validate hard user constraints without relying on model prose."""
    requested = _request_constraints(spec) if isinstance(spec, str) else spec
    errors: list[str] = []
    allowed = {item.isoformat() for item in requested.allowed_dates}
    dates = {session.session_date for session in plan.sessions}
    if requested.exact_date and dates != {requested.exact_date.isoformat()}:
        errors.append("EXACT_DATE_CONSTRAINT_VIOLATED")
    elif allowed and any(item not in allowed for item in dates):
        errors.append("SESSION_DATE_OUTSIDE_REQUESTED_RANGE")
    if requested.daily_coverage or requested.requested_duration_days:
        if not set(allowed).issubset(dates):
            errors.append("DATE_COVERAGE_MISMATCH")
    if requested.sessions_per_day and allowed and not requested.required_categories:
        for allowed_date in allowed:
            if sum(
                session.session_date == allowed_date
                for session in plan.sessions
            ) != requested.sessions_per_day:
                errors.append("SESSION_COUNT_MISMATCH")
                break
    if requested.requested_session_count is not None and (
        len(plan.sessions) != requested.requested_session_count
    ):
        errors.append("SESSION_COUNT_MISMATCH")
    categories = {session.category for session in plan.sessions}
    if requested.required_categories and not set(requested.required_categories).issubset(categories):
        errors.append("REQUIRED_CATEGORY_MISSING")
    if requested.required_categories and requested.allowed_dates:
        matrix = [
            (session.session_date, session.category)
            for session in plan.sessions
        ]
        expected = {
            (item.isoformat(), category)
            for item in requested.allowed_dates
            for category in requested.required_categories
        }
        if len(matrix) != len(expected) or set(matrix) != expected:
            errors.append("CATEGORY_MATRIX_MISMATCH")
    if requested.time_start_minutes is not None and requested.time_end_minutes is not None:
        for session in plan.sessions:
            parsed = datetime.strptime(session.scheduled_time, _TIME_FORMAT)
            minutes = parsed.hour * 60 + parsed.minute
            if not requested.time_start_minutes <= minutes <= requested.time_end_minutes:
                errors.append("TIME_WINDOW_VIOLATION")
                break
    if requested.topic_list:
        searchable = " ".join(
            f"{session.topic} {session.session_title} {session.prompt}"
            for session in plan.sessions
        ).casefold()
        if any(topic.casefold() not in searchable for topic in requested.topic_list):
            errors.append("TOPIC_NOT_COVERED")
    return ConstraintResult(not errors, tuple(dict.fromkeys(errors)))


def _curriculum_plan(request: str, spec: TimetableSpec) -> TimetablePlan:
    topics = extract_curriculum_topics(request)
    dates = spec.allowed_dates
    if not topics and dates:
        subject = next(
            (word for word in ("Python", "SQL", "Java") if re.search(rf"\b{word}\b", request, re.I)),
            "requested subject",
        )
        topics = (CurriculumTopic(
            "topic-1", f"{subject} concept basics", f"{subject.casefold()} concept basics",
            "foundation", "Level 1",
        ),)
    if not dates:
        raise ValueError("CURRICULUM_DISTRIBUTION_REQUIRES_TOPICS_AND_DATES")
    session_count = (
        len(dates) * len(spec.required_categories)
        if spec.required_categories
        else len(dates)
    )
    topic_groups = [
        topics[index * len(topics) // session_count:
               (index + 1) * len(topics) // session_count]
        for index in range(session_count)
    ]
    topic_groups = [
        group or (topics[index % len(topics)],)
        for index, group in enumerate(topic_groups)
    ]
    module_name = "SQL Developer" if re.search(r"\bsql\b", request, re.I) else "Learning Curriculum"
    sessions = []
    for index, group in enumerate(topic_groups):
        target_date = dates[index % len(dates)]
        category = (
            spec.required_categories[index % len(spec.required_categories)]
            if spec.required_categories
            else group[0].suggested_category
        )
        topic_text = "; ".join(topic.original_text for topic in group)
        scheduled_time = (
            datetime.combine(date.today(), datetime.min.time())
            + timedelta(hours=7 + (index % 12))
        ).strftime(_TIME_FORMAT).lstrip("0")
        sessions.append(PlannedSession(
            target_date.isoformat(),
            scheduled_time,
            category,
            topic_text,
            f"{module_name}: {topic_text[:80]}",
            f"Study {topic_text} with explanation, examples, and practice.",
            None,
            "Scheduled",
            index + 1,
        ))
    plan = TimetablePlan(
        title=f"{module_name} curriculum plan",
        module_name=module_name,
        description="Deterministically distributed curriculum plan.",
        start_date=dates[0].isoformat(),
        end_date=dates[-1].isoformat(),
        timezone=spec.timezone,
        assumptions=["Curriculum topics were distributed deterministically by the application."],
        sessions=sessions,
    )
    return _apply_request_constraints(plan, request)


def _has_curriculum_coverage(plan: TimetablePlan, topics: tuple[CurriculumTopic, ...]) -> bool:
    searchable = " ".join(
        f"{session.topic} {session.session_title} {session.prompt}"
        for session in plan.sessions
    ).casefold()
    return bool(topics) and all(topic.normalized_text in searchable for topic in topics)


def _replace_session_date(session: PlannedSession, target: date) -> PlannedSession:
    return PlannedSession(
        target.isoformat(), session.scheduled_time, session.category, session.topic,
        session.session_title, session.prompt, session.scheduled_end_time,
        session.status, session.day_number,
    )


def _assign_random_times(
    sessions: list[PlannedSession], spec: TimetableSpec,
    seed: int | None = None,
) -> list[PlannedSession]:
    low = spec.time_start_minutes if spec.time_start_minutes is not None else 7 * 60
    high = spec.time_end_minutes if spec.time_end_minutes is not None else (
        23 * 60 + 50 if spec.upcoming_time_requested else 21 * 60
    )
    if high < low:
        raise ValueError("TIME_WINDOW_VIOLATION")
    slot_minutes = 5 if spec.upcoming_time_requested else 15
    default_duration = 5 if spec.upcoming_time_requested else 60
    generator = random.Random(seed) if seed is not None else random.SystemRandom()
    updated: dict[int, PlannedSession] = {}
    for session_date in dict.fromkeys(session.session_date for session in sessions):
        day_sessions = [
            (index, session) for index, session in enumerate(sessions)
            if session.session_date == session_date
        ]
        day_low = low
        if spec.upcoming_time_requested:
            local_now = datetime.now(ZoneInfo(spec.timezone))
            if date.fromisoformat(session_date) == local_now.date():
                next_minute = local_now.hour * 60 + local_now.minute + 1
                day_low = max(day_low, ((next_minute + slot_minutes - 1) // slot_minutes) * slot_minutes)
        candidates = list(range(day_low, high + 1, slot_minutes))
        duration_by_index = {}
        for index, session in day_sessions:
            duration = default_duration
            if session.scheduled_end_time:
                start = datetime.strptime(session.scheduled_time, _TIME_FORMAT)
                end = datetime.strptime(session.scheduled_end_time, _TIME_FORMAT)
                duration = int((end - start).total_seconds() // 60)
                if duration <= 0:
                    duration += 24 * 60
            duration_by_index[index] = duration
        generator.shuffle(candidates)
        occupied: list[tuple[int, int]] = []
        for index, session in day_sessions:
            duration = duration_by_index[index]
            minute = next(
                (
                    candidate for candidate in candidates
                    if candidate + duration <= high
                    if all(
                        candidate >= end or candidate + duration <= start
                        for start, end in occupied
                    )
                ),
                None,
            )
            if minute is None:
                capacity = sum(
                    candidate + duration <= high
                    for candidate in candidates
                )
                raise ValueError(
                    f"RANDOM_TIME_CAPACITY_EXCEEDED: {session_date} requires "
                    f"{len(day_sessions)} sessions but only {capacity} valid start slots exist."
                )
            occupied.append((minute, minute + duration))
            value = datetime.combine(date.today(), datetime.min.time()) + timedelta(minutes=minute)
            end_value = value + timedelta(minutes=duration)
            updated[index] = PlannedSession(
                session.session_date, value.strftime(_TIME_FORMAT).lstrip("0"),
                session.category, session.topic, session.session_title, session.prompt,
                end_value.strftime(_TIME_FORMAT).lstrip("0"),
                session.status, session.day_number,
            )
    return [updated[index] for index in range(len(sessions))]


def _ensure_category_matrix(
    sessions: list[PlannedSession], spec: TimetableSpec, request: str
) -> list[PlannedSession]:
    """Resolve exactly one canonical session for every requested date/category cell."""
    dates = tuple(item.isoformat() for item in spec.allowed_dates)
    cells = [(session_date, category) for session_date in dates for category in spec.required_categories]
    by_cell: dict[tuple[str, str], list[PlannedSession]] = {}
    for session in sessions:
        by_cell.setdefault((session.session_date, session.category), []).append(session)

    topic_context = list(spec.topic_list)
    if not topic_context:
        topic_context = [
            session.topic for session in sessions if session.topic.strip()
        ]
    subject = next(
        (word for word in ("Python", "SQL", "Java") if re.search(rf"\b{word}\b", request, re.I)),
        "requested curriculum",
    )
    templates = {
        "Today Learning": "daily concept lesson",
        "Level 1": "foundational practice",
        "Level 2": "advanced practice",
        "Problem Solving": "problem solving exercises",
        "Test": "assessment and review",
        "Interview Preparation": "interview preparation questions",
        "Interview Room": "mock interview session",
    }
    result: list[PlannedSession] = []
    used: set[int] = set()
    for cell_index, (session_date, category) in enumerate(cells):
        candidates = by_cell.get((session_date, category), [])
        if candidates:
            selected = candidates[0]
            used.add(id(selected))
            result.append(selected)
            continue
        extras = [
            session for session in sessions
            if id(session) not in used
            and (session.session_date, session.category) not in by_cell
        ]
        if extras:
            selected = extras[0]
            used.add(id(selected))
            result.append(PlannedSession(
                session_date, selected.scheduled_time, category, selected.topic,
                selected.session_title, selected.prompt, selected.scheduled_end_time,
                selected.status, cell_index + 1,
            ))
            continue
        topic = topic_context[cell_index % len(topic_context)] if topic_context else subject
        role = templates[category]
        result.append(PlannedSession(
            session_date,
            "7:00 AM",
            category,
            f"{subject}: {topic}",
            f"{category} - {role}",
            f"Study {subject} through {role} using {topic}.",
            None,
            "Scheduled",
            cell_index + 1,
        ))

    # Preserve provider curriculum that was attached to duplicate cells.
    for session in sessions:
        if id(session) in used:
            continue
        target = next(
            item for item in result
            if item.session_date == session.session_date
        )
        if session.topic.casefold() in target.topic.casefold():
            continue
        target.topic = f"{target.topic}; {session.topic}"
        target.prompt = f"{target.prompt} Also cover {session.topic}."
    return result


def _add_missing_categories(
    sessions: list[PlannedSession], missing: set[str], spec: TimetableSpec
) -> list[PlannedSession]:
    dates = [item.isoformat() for item in spec.allowed_dates] or [sessions[0].session_date]
    result = list(sessions)
    next_index = len(result) + 1
    used = {(session.session_date, session.scheduled_time) for session in result}
    candidate_minutes = iter(range(7 * 60, 22 * 60, 60))
    for category in sorted(missing, key=CATEGORIES.index):
        target_date = dates[(next_index - 1) % len(dates)]
        scheduled_time = None
        for minute in candidate_minutes:
            candidate = datetime.combine(
                date.today(), datetime.min.time()
            ) + timedelta(minutes=minute)
            formatted = candidate.strftime(_TIME_FORMAT).lstrip("0")
            if (target_date, formatted) not in used:
                scheduled_time = formatted
                used.add((target_date, formatted))
                break
        if scheduled_time is None:
            raise ValueError("CATEGORY_TIME_CAPACITY_EXCEEDED")
        result.append(PlannedSession(
            target_date, scheduled_time, category, f"{category} practice",
            f"{category} session", f"Teach {category} with examples and practice.",
            None, "Scheduled", next_index,
        ))
        next_index += 1
    return result


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


def _validate_sessions(
    raw_sessions, check_overlaps: bool = True
) -> list[PlannedSession]:
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
        key = (
            session_date,
            category,
            topic,
            title,
            prompt,
            scheduled_time,
            scheduled_end_time or "",
            status,
            day_number,
        )
        if key in seen:
            raise ValueError("The timetable proposal contains duplicate sessions.")
        seen.add(key)
        session = PlannedSession(
            session_date, scheduled_time, category, topic, title, prompt,
            scheduled_end_time, status, day_number,
        )
        _session_window(session)
        sessions.append(session)

    if check_overlaps:
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


def _normalize_plan_payload(raw: dict) -> dict:
    """Normalize safe scalar/list representations before strict field validation."""
    nested_plan = raw.get("plan")
    normalized = (
        {**raw, **nested_plan}
        if isinstance(nested_plan, dict)
        and ("sessions" not in raw or raw.get("sessions") is None)
        else dict(raw)
    )
    if normalized.get("sessions") is None and isinstance(normalized.get("days"), list):
        sessions = []
        for day_index, day in enumerate(normalized["days"], start=1):
            if not isinstance(day, dict):
                raise ValueError("Plan field 'days' must contain session objects.")
            day_sessions = day.get("sessions")
            if day_sessions is None and "session_date" in day:
                day_sessions = [day]
            if not isinstance(day_sessions, list):
                raise ValueError("Plan field 'days' must contain session lists.")
            for session in day_sessions:
                if not isinstance(session, dict):
                    raise ValueError("Each planned session must be an object.")
                normalized_session = dict(session)
                if "session_date" not in normalized_session and day.get("date"):
                    normalized_session["session_date"] = day["date"]
                normalized_session.setdefault("day_number", day_index)
                sessions.append(normalized_session)
        normalized["sessions"] = sessions
    assumptions = normalized.get("assumptions")
    if isinstance(assumptions, str):
        normalized["assumptions"] = [assumptions]
    elif assumptions is None:
        normalized["assumptions"] = []
    if isinstance(normalized.get("sessions"), list):
        normalized["sessions"] = [
            {
                **session,
                # Provider output describes curriculum, not persisted runtime state.
                "status": "Scheduled",
            }
            if isinstance(session, dict)
            else session
            for session in normalized["sessions"]
        ]
    return normalized


def parse_plan(
    response: str, check_overlaps: bool = True, enforce_plan_range: bool = True,
    ignore_session_times: bool = False,
) -> TimetablePlan:
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
    raw = _normalize_plan_payload(raw)
    if ignore_session_times and isinstance(raw.get("sessions"), list):
        placeholder_counts: dict[str, int] = {}
        normalized_sessions = []
        for session in raw["sessions"]:
            if not isinstance(session, dict):
                normalized_sessions.append(session)
                continue
            session_date = str(session.get("session_date", ""))
            offset = placeholder_counts.get(session_date, 0)
            placeholder_counts[session_date] = offset + 1
            normalized_sessions.append({
                **session,
                "scheduled_time": (
                    datetime.combine(date.today(), datetime.min.time())
                    + timedelta(hours=7 + (offset % 12))
                ).strftime(_TIME_FORMAT).lstrip("0"),
                "scheduled_end_time": None,
            })
        raw["sessions"] = normalized_sessions
    sessions = _validate_sessions(raw.get("sessions"), check_overlaps)
    start_date = _parse_date(raw.get("start_date"), "start_date")
    end_date = _parse_date(raw.get("end_date"), "end_date")
    if date.fromisoformat(end_date) < date.fromisoformat(start_date):
        raise ValueError("The timetable end date cannot be before its start date.")
    if enforce_plan_range and any(
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
    request = request.strip()
    spec = _request_constraints(request)
    curriculum_topics = extract_curriculum_topics(request)
    curriculum_request = bool(
        spec.allowed_dates
        and (
            curriculum_topics
            or spec.requested_duration_days
            or spec.required_categories
            or re.search(r"\b(?:fit|divide|distribute|every topic|all topics|curriculum)\b", request, re.I)
        )
    )
    generation_request = request
    last_error: ValueError | None = None
    for attempt in range(2):
        try:
            response = gateway.generate_timetable(generation_request)
        except AIProviderError as error:
            last_error = ValueError(str(error))
            if curriculum_request:
                return _curriculum_plan(request, spec)
            raise
        except Exception as error:
            raise AIProviderError("The AI provider is currently unavailable.") from error
        try:
            plan = _apply_request_constraints(
                parse_plan(
                    response,
                    check_overlaps=False,
                    enforce_plan_range=False,
                    ignore_session_times=spec.random_time_requested,
                ),
                request,
            )
            if (
                not curriculum_request
                or not curriculum_topics
                or _has_curriculum_coverage(plan, curriculum_topics)
            ):
                return plan
            raise ValueError("TOPIC_NOT_COVERED")
        except ValueError as error:
            last_error = error
            if curriculum_request:
                return _curriculum_plan(request, spec)
            if attempt == 0:
                generation_request = (
                    f"{request}\n\n"
                    "Hard constraint validation failed. Regenerate a structured JSON "
                    "timetable that obeys every date, time, category, count, and topic "
                    f"constraint. Validation error: {error}"
                )
    assert last_error is not None
    raise last_error


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
        for session in plan.sessions:
            _parse_time(session.scheduled_time, "scheduled_time")
            _session_window(session)
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
        placeholders = ",".join("?" for _ in session_ids)
        persisted = connection.execute(
            f"""
            SELECT COUNT(*) AS total,
                   SUM(CASE WHEN scheduled_time IS NOT NULL
                       AND TRIM(scheduled_time) != '' THEN 1 ELSE 0 END) AS timed
            FROM sessions
            WHERE session_id IN ({placeholders})
            """,
            session_ids,
        ).fetchone()
        if (
            persisted["total"] != len(plan.sessions)
            or persisted["timed"] != len(plan.sessions)
        ):
            raise ValueError(
                "TIMETABLE_PERSISTENCE_TIME_MISMATCH: persisted session times "
                "do not match the canonical timetable."
            )
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
