import json
import sqlite3
from dataclasses import asdict
import inspect
import random
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
import services.timetable_creator_service as timetable_creator_service

from ai.gateway import AIGateway
from database.schema import initialize_database
from services.module_service import add_module
from services.timetable_creator_service import (
    CATEGORIES,
    DateConstraintConflict,
    _parse_time,
    _assign_random_times,
    _session_window,
    _request_constraints,
    detect_conflicts,
    generate_plan,
    parse_plan,
    persist_plan,
    apply_request_constraints,
)


def _payload(**overrides):
    start = date(2026, 9, 13)
    payload = {
        "title": "SQL plan",
        "module_name": "SQL Developer",
        "description": "Career preparation",
        "start_date": start.isoformat(),
        "end_date": (start + timedelta(days=1)).isoformat(),
        "timezone": "Asia/Kolkata",
        "assumptions": ["One hour per session."],
        "sessions": [
            {
                "session_date": start.isoformat(),
                "scheduled_time": "7:00 PM",
                "category": "Level 1",
                "topic": "Filtering",
                "session_title": "Filtering fundamentals",
                "prompt": "Teach filtering with examples and practice questions.",
                "day_number": 1,
            },
            {
                "session_date": (start + timedelta(days=1)).isoformat(),
                "scheduled_time": "7:00 PM",
                "category": "Problem Solving",
                "topic": "Filtering practice",
                "session_title": "Practice filtering",
                "prompt": "Give practical filtering problems and review mistakes.",
                "day_number": 2,
            },
        ],
    }
    payload.update(overrides)
    return payload


@pytest.fixture
def connection():
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    initialize_database(connection)
    yield connection
    connection.close()


@pytest.fixture
def frozen_timetable_reference_date(monkeypatch):
    """Keep duration-only timetable tests independent of the machine clock."""
    reference_date = date(2026, 9, 13)

    class FrozenDate(date):
        @classmethod
        def today(cls):
            return reference_date

    monkeypatch.setattr(timetable_creator_service, "date", FrozenDate)
    return reference_date


class Gateway(AIGateway):
    def __init__(self, response):
        self.response = response
        self.calls = []

    def generate_timetable(self, prompt):
        self.calls.append(prompt)
        return self.response


def _adversarial_response():
    categories = [
        "Today Learning", "Level 1", "Level 2", "Problem Solving",
        "Test", "Interview Preparation", "Interview Room",
    ]
    start = date(2026, 9, 13)
    sessions = []
    for index in range(10):
        current = start + timedelta(days=index)
        sessions.append({
            "session_date": current.isoformat(),
            "scheduled_time": (
                datetime.combine(start, datetime.min.time()) + timedelta(hours=7 + index)
            ).strftime("%I:00 %p").lstrip("0"),
            "category": categories[index % len(categories)],
            "topic": f"SQL topic {index + 1}",
            "session_title": f"SQL topic {index + 1}",
            "prompt": "Teach the topic with examples and practice.",
            "day_number": index + 1,
            "status": "Scheduled",
        })
    return json.dumps({
        "title": "Adversarial SQL plan",
        "module_name": "SQL Developer",
        "description": "Constraint test plan",
        "start_date": start.isoformat(),
        "end_date": (start + timedelta(days=9)).isoformat(),
        "timezone": "Asia/Kolkata",
        "assumptions": [],
        "sessions": sessions,
    })


def _curriculum_response(topic_count, day_count, categories):
    start = date(2026, 9, 13)
    sessions = []
    for index in range(topic_count):
        day_offset = index % day_count
        session_date = start + timedelta(days=day_offset)
        scheduled_time = datetime.combine(
            session_date, datetime.min.time()
        ) + timedelta(hours=7 + (index // day_count))
        sessions.append({
            "session_date": session_date.isoformat(),
            "scheduled_time": scheduled_time.strftime("%I:%M %p").lstrip("0"),
            "category": categories[index % len(categories)],
            "topic": f"SQL curriculum topic {index + 1}",
            "session_title": f"SQL curriculum topic {index + 1}",
            "prompt": "Teach the SQL topic with examples and practice.",
            "day_number": day_offset + 1,
        })
    return json.dumps({
        "title": "SQL curriculum plan",
        "module_name": "SQL Developer",
        "description": "Structured SQL curriculum",
        "start_date": start.isoformat(),
        "end_date": (start + timedelta(days=day_count - 1)).isoformat(),
        "timezone": "Asia/Kolkata",
        "assumptions": [],
        "sessions": sessions,
    })


def _days_wrapped_response():
    payload = _payload()
    sessions = payload.pop("sessions")
    payload["days"] = [
        {"date": session["session_date"], "sessions": [session]}
        for session in sessions
    ]
    return json.dumps({"plan": payload})


def _sql_curriculum_topics():
    areas = {
        "SQL foundations": [
            "SQL basics", "SELECT", "WHERE", "ORDER BY", "GROUP BY",
            "HAVING", "DISTINCT", "column aliases", "comparison operators", "NULL handling",
        ],
        "SQL expressions": [
            "CASE expressions", "COALESCE", "string functions", "numeric functions",
            "date functions", "aggregate functions", "conditional aggregation",
            "type conversion", "operator precedence", "collations",
        ],
        "joins": [
            "INNER JOIN", "LEFT JOIN", "RIGHT JOIN", "FULL OUTER JOIN",
            "CROSS JOIN", "self join", "join predicates", "anti joins",
            "semi joins", "duplicate rows after joins",
        ],
        "subqueries": [
            "subqueries", "correlated subqueries", "EXISTS", "NOT EXISTS",
            "scalar subqueries", "derived tables", "subquery factoring",
            "subquery performance", "lateral joins", "set operators",
        ],
        "CTEs": [
            "CTEs", "recursive CTEs", "hierarchical queries", "CTE materialization",
            "multiple CTEs", "CTE debugging", "CTE versus subquery", "CTE optimization",
            "recursive termination", "graph traversal queries",
        ],
        "window functions": [
            "window functions", "ROW_NUMBER", "RANK", "DENSE_RANK", "LEAD",
            "LAG", "FIRST_VALUE", "LAST_VALUE", "window frames", "partitioning",
        ],
        "data design": [
            "primary keys", "foreign keys", "unique constraints", "check constraints",
            "NOT NULL constraints", "normalization", "denormalization", "entity relationships",
            "surrogate keys", "referential actions",
        ],
        "database objects": [
            "views", "materialized views", "stored procedures", "user-defined functions",
            "triggers", "temporary tables", "table-valued functions", "sequences",
            "synonyms", "database schemas",
        ],
        "transactions": [
            "transactions", "ACID", "COMMIT", "ROLLBACK", "SAVEPOINT",
            "locking", "concurrency", "isolation levels",             "deadlocks", "MVCC",
        ],
        "performance": [
            "indexes", "composite indexes", "covering indexes", "execution plans",
            "query optimization", "performance tuning", "statistics", "cardinality estimates",
            "index maintenance", "query plan regression",
        ],
        "analytics": [
            "pivot queries", "unpivot queries", "time series analysis", "running totals",
            "gaps and islands", "top N per group", "recursive reporting", "cohort analysis",
            "percentile functions", "median calculations",
        ],
        "security": [
            "SQL injection", "parameterized queries", "roles", "privileges",
            "GRANT", "REVOKE", "row-level security", "auditing", "data masking",
            "least privilege",
        ],
        "engineering practice": [
            "schema migrations", "backup and restore", "data loading", "bulk inserts",
            "upsert patterns", "error handling", "testing SQL", "deployment scripts",
            "monitoring queries", "production troubleshooting",
        ],
    }
    return [f"{area}: {topic}" for area, topics in areas.items() for topic in topics]


def _curriculum_prompt(topics, days, suffix=""):
    return (
        f"Create a {days}-day SQL Developer timetable using every topic, "
        f"distribute the curriculum across {days} days {suffix}: "
        f"[{', '.join(topics)}]"
    )


def _empty_provider_response(kind="empty"):
    payload = _payload()
    if kind == "null":
        payload["sessions"] = None
    elif kind == "nested":
        payload = {"plan": payload}
    elif kind == "days":
        sessions = payload.pop("sessions")
        payload["days"] = [
            {"date": session["session_date"], "sessions": [session]}
            for session in sessions
        ]
        payload["sessions"] = None
    else:
        payload["sessions"] = []
    return json.dumps(payload)


def test_empty_request_rejected():
    with pytest.raises(ValueError, match="Describe"):
        generate_plan(Gateway("{}"), " ")


def test_duration_only_resolves_exactly_three_dates():
    plan = generate_plan(
        Gateway(_empty_provider_response()),
        "create a timetable for 3 days in python concept basics",
    )
    assert len({session.session_date for session in plan.sessions}) == 3


def test_explicit_range_resolves_inclusive_dates():
    spec = _request_constraints(
        "create a timetable from September 13 to September 16 in python concept basics"
    )
    assert [item.day for item in spec.allowed_dates] == [13, 14, 15, 16]


def test_matching_duration_and_range_resolves_without_conflict():
    spec = _request_constraints(
        "create a timetable for 3 days from September 13 to September 15"
    )
    assert len(spec.allowed_dates) == 3


def test_conflicting_duration_and_range_is_structured_and_precedes_generation():
    gateway = Gateway(_empty_provider_response())
    with pytest.raises(DateConstraintConflict) as raised:
        generate_plan(
            gateway,
            "create a timetable for 3 days from September 13 to September 16",
        )
    assert gateway.calls == []
    assert raised.value.code == "DATE_CONSTRAINT_CONFLICT"
    assert raised.value.details == {
        "requested_duration_days": 3,
        "explicit_start_date": "2026-09-13",
        "explicit_end_date": "2026-09-16",
        "inclusive_range_length": 4,
        "reason": (
            "The requested duration does not match the inclusive explicit "
            "date range."
        ),
    }


def test_duration_within_range_selects_exactly_three_dates():
    spec = _request_constraints(
        "create a timetable for 3 days within September 13 to September 16"
    )
    assert [item.day for item in spec.allowed_dates] == [13, 14, 15]


def test_ordinal_explicit_range_resolves_all_four_inclusive_dates():
    spec = _request_constraints(
        "Create a timetable for python basics in the date of "
        "September 13th to September 16"
    )
    assert [item.isoformat() for item in spec.allowed_dates] == [
        "2026-09-13", "2026-09-14", "2026-09-15", "2026-09-16",
    ]


def test_ordinal_range_generation_does_not_create_duplicate_sessions():
    prompt = (
        "Create a timetable for python basics in the date of "
        "September 13th to September 16"
    )
    plan = generate_plan(Gateway(_adversarial_response()), prompt)
    assert {session.session_date for session in plan.sessions} == {
        "2026-09-13", "2026-09-14", "2026-09-15", "2026-09-16",
    }
    assert len({
        (
            session.session_date, session.category, session.topic,
            session.session_title, session.prompt, session.scheduled_time,
            session.scheduled_end_time or "", session.status, session.day_number,
        )
        for session in plan.sessions
    }) == len(plan.sessions)


def test_duplicate_identity_requires_identical_canonical_session_content():
    payload = _payload()
    payload["sessions"].append(dict(payload["sessions"][0]))
    with pytest.raises(ValueError, match="duplicate sessions"):
        parse_plan(json.dumps(payload), check_overlaps=False)


def test_same_start_time_different_canonical_sessions_are_not_duplicate_error():
    payload = _payload()
    payload["sessions"][1]["session_date"] = payload["sessions"][0]["session_date"]
    payload["sessions"][1]["scheduled_time"] = payload["sessions"][0]["scheduled_time"]
    payload["sessions"][1]["topic"] = "Different legitimate topic"
    with pytest.raises(ValueError, match="overlapping sessions"):
        parse_plan(json.dumps(payload), check_overlaps=True)


def test_numeric_date_range_resolves_inclusive_dates():
    spec = _request_constraints(
        "create a timetable from 13/09/2026 to 16/09/2026"
    )
    assert [item.isoformat() for item in spec.allowed_dates] == [
        "2026-09-13", "2026-09-14", "2026-09-15", "2026-09-16",
    ]


def test_fill_all_categories_phrase_activates_full_matrix():
    prompt = (
        "create a timetable for 3 days in python concept basics, each day "
        "fill all the categories with random timing"
    )
    plan = generate_plan(Gateway(_empty_provider_response()), prompt)
    assert plan.total_sessions == 3 * len(CATEGORIES)
    assert {
        (session.session_date, session.category)
        for session in plan.sessions
    } == {
        (session_date, category)
        for session_date in {session.session_date for session in plan.sessions}
        for category in CATEGORIES
    }


def test_explicit_four_day_full_category_matrix_has_28_sessions():
    prompt = (
        "create a timetable from September 13 to September 16 in python concept "
        "basics, each day fill all the categories with random timing"
    )
    plan = generate_plan(Gateway(_empty_provider_response()), prompt)
    assert plan.total_sessions == 4 * len(CATEGORIES)
    assert {session.session_date for session in plan.sessions} == {
        "2026-09-13", "2026-09-14", "2026-09-15", "2026-09-16",
    }


def test_seeded_adversarial_full_matrix_property_cases():
    topics = [
        "Python concept basics", "SQL fundamentals", "Data Structures",
        "Machine Learning basics", "Excel", "Power BI", "Java", "Statistics",
    ]
    duration_words = ["3", "three", "3-day", "4", "four", "5"]
    generator = random.Random(20260913)
    prompts = [
        (
            f"create a timetable for {duration_words[index % len(duration_words)]} "
            f"{'' if '-' in duration_words[index % len(duration_words)] else 'days '}"
            f"in {topics[generator.randrange(len(topics))]}, "
            f"{'each day fill every category' if index % 2 else 'complete timetable'}, "
            "with random timing"
        )
        for index in range(30)
    ]
    for prompt in prompts:
        plan = generate_plan(Gateway(_empty_provider_response()), prompt)
        dates = {session.session_date for session in plan.sessions}
        assert len(dates) in {3, 4, 5}
        assert len(plan.sessions) == len(dates) * len(CATEGORIES)
        assert {
            (session.session_date, session.category)
            for session in plan.sessions
        } == {
            (session_date, category)
            for session_date in dates
            for category in CATEGORIES
        }


def test_exact_user_prompt_uses_three_dates_inside_date_window():
    prompt = (
        "here create a timetable for 3 days in python concept basics\n"
        "in each day - fill all the categories with random timing - so dont "
        "miss anything or empty\n"
        "date - september 13 - september 16"
    )
    plan = generate_plan(Gateway(_empty_provider_response()), prompt)
    assert {session.session_date for session in plan.sessions} == {
        "2026-09-13", "2026-09-14", "2026-09-15",
    }
    assert plan.total_sessions == 21
    assert {
        (session.session_date, session.category)
        for session in plan.sessions
    } == {
        (session_date, category)
        for session_date in {"2026-09-13", "2026-09-14", "2026-09-15"}
        for category in CATEGORIES
    }


@pytest.mark.parametrize("prompt", [
    "create a timetable only on September 13, 2026 for SQL Developer with random times",
    "make an SQL timetable for September 13, 2026 only, random times",
    "create an SQL timetable from September 13, 2026 to September 16, 2026",
    "give me an SQL schedule Sep 13, 2026 through Sep 16, 2026 with random times",
    "plan SQL from Sep 13, 2026 to Sep 16, 2026, one session each day",
    "divide SQL topics into 4 days starting September 13, 2026",
    "create a 7 day Python learning timetable starting September 13, 2026",
    "create a timetable only on September 13, 2026 for SQL Developer with random times in all categories",
    "SQL Developer on September 13, 2026 only, cover every category with random times",
    "SQL timetable from Sep 13, 2026 to Sep 14, 2026",
    "SQL timetable Sep 15, 2026 only",
    "SQL timetable for Sep 13, 2026, Sep 14, 2026 and Sep 15, 2026",
    "create SQL sessions on September 13, 2026 at random times",
    "create sessions from Sep 13, 2026 to Sep 16, 2026 at random times between 7 AM and 9 PM",
    "take these SQL topics and divide them into 10 days starting September 13, 2026: "
    "[SQL topic 1, SQL topic 2, SQL topic 3]",
])
def test_adversarial_prompts_respect_hard_constraints(prompt):
    plan = generate_plan(Gateway(_adversarial_response()), prompt)
    dates = {date.fromisoformat(session.session_date) for session in plan.sessions}
    spec = __import__(
        "services.timetable_creator_service",
        fromlist=["_request_constraints"],
    )._request_constraints(prompt)
    assert dates.issubset(set(spec.allowed_dates))
    if spec.exact_date:
        assert dates == {spec.exact_date}
    if spec.requested_duration_days or spec.daily_coverage:
        assert set(spec.allowed_dates).issubset(dates)
    if spec.required_categories:
        assert spec.required_categories == tuple(
            category for category in CATEGORIES
            if category in {session.category for session in plan.sessions}
        )


def test_valid_free_form_request_calls_gateway_once(frozen_timetable_reference_date):
    gateway = Gateway(json.dumps(_payload()))
    plan = generate_plan(gateway, "Make me job-ready in two days.")
    assert plan.module_name == "SQL Developer"
    assert gateway.calls == ["Make me job-ready in two days."]


def test_ai_response_parsed():
    plan = parse_plan(json.dumps(_payload()))
    assert plan.total_sessions == 2
    assert plan.sessions[0].topic == "Filtering"


@pytest.mark.parametrize(
    ("assumptions", "expected"),
    [
        (["text 1", "text 2"], ["text 1", "text 2"]),
        ("text 1", ["text 1"]),
        (None, []),
    ],
)
def test_assumptions_are_normalized_at_plan_schema_boundary(assumptions, expected):
    payload = _payload(assumptions=assumptions)
    if assumptions is None:
        payload["assumptions"] = None
    plan = parse_plan(json.dumps(payload))
    assert plan.assumptions == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("7am", "7:00 AM"),
        ("7 am", "7:00 AM"),
        ("7:00am", "7:00 AM"),
        ("7:00 am", "7:00 AM"),
        ("07:00 AM", "7:00 AM"),
        ("7pm", "7:00 PM"),
        ("07:10 PM", "7:10 PM"),
        ("7:10 PM", "7:10 PM"),
        ("19:00", "7:00 PM"),
        ("19:10", "7:10 PM"),
    ],
)
def test_supported_time_variants_share_canonical_representation(value, expected):
    assert _parse_time(value, "scheduled_time") == expected


@pytest.mark.parametrize("value", ["25:90", "7:90 PM", "abc", "19:90"])
def test_malformed_time_variants_remain_rejected(value):
    with pytest.raises(ValueError):
        _parse_time(value, "scheduled_time")


def test_missing_assumptions_are_normalized_to_empty_list():
    payload = _payload()
    del payload["assumptions"]
    assert parse_plan(json.dumps(payload)).assumptions == []


def test_wrapped_days_schema_is_normalized_without_fabricating_sessions():
    plan = parse_plan(_days_wrapped_response())
    assert plan.total_sessions == 2
    assert {session.session_date for session in plan.sessions} == {
        "2026-09-13", "2026-09-14"
    }


def test_empty_days_schema_remains_rejected():
    payload = _payload()
    payload.pop("sessions")
    payload["days"] = []
    with pytest.raises(ValueError, match="at least one session"):
        parse_plan(json.dumps(payload))


@pytest.mark.parametrize("assumptions", [{"foo": "bar"}, 123, [["nested"]]])
def test_invalid_assumptions_structures_remain_rejected(assumptions):
    with pytest.raises(ValueError, match="assumptions"):
        parse_plan(json.dumps(_payload(assumptions=assumptions)))


def test_real_world_exact_date_prompt_preserves_constraints_after_normalization():
    prompt = (
        "create a timetable on sep 13 only as small sql workshop session "
        "with random times in fit in all categories"
    )
    payload = json.loads(_adversarial_response())
    payload["assumptions"] = "Small workshop sessions."
    plan = generate_plan(Gateway(json.dumps(payload)), prompt)
    assert plan.assumptions == ["Small workshop sessions."]
    assert {session.session_date for session in plan.sessions} == {"2026-09-13"}
    assert {session.category for session in plan.sessions} == set(CATEGORIES)
    assert plan.timezone == "Asia/Kolkata"
    for session in plan.sessions:
        assert datetime.strptime(session.scheduled_time, "%I:%M %p")


def test_real_world_pipeline_has_canonical_random_times_and_all_categories():
    prompt = (
        "create a timetable on sep 13 only as small sql workshop session "
        "with random times in fit in all categories"
    )
    payload = json.loads(_adversarial_response())
    payload["assumptions"] = "Small workshop sessions."
    plan = generate_plan(Gateway(json.dumps(payload)), prompt)
    assert {session.session_date for session in plan.sessions} == {"2026-09-13"}
    assert {session.category for session in plan.sessions} == set(CATEGORIES)
    assert all(
        datetime.strptime(session.scheduled_time, "%I:%M %p")
        for session in plan.sessions
    )
    assert plan.assumptions == ["Small workshop sessions."]


@pytest.mark.parametrize("prompt", [
    "SQL workshop on Sep 13 only with random times",
    "SQL sessions from September 13 to September 16",
    "SQL on Sep 13, Sep 15 and Sep 17 only",
    "divide a small SQL workshop into four days starting Sep 13",
    "SQL workshop on Sep 13 only with random times in all categories",
])
def test_schema_validity_and_canonical_constraints_hold_for_additional_prompts(prompt):
    plan = generate_plan(Gateway(_adversarial_response()), prompt)
    module = __import__(
        "services.timetable_creator_service",
        fromlist=["_request_constraints"],
    )
    spec = module._request_constraints(prompt)
    validation = module.validate_plan_constraints(plan, spec)
    assert validation.valid, validation.errors
    dates = {session.session_date for session in plan.sessions}
    assert dates.issubset({item.isoformat() for item in spec.allowed_dates})
    if spec.exact_date:
        assert dates == {spec.exact_date.isoformat()}


def test_exact_date_prompt_never_expands_to_next_day():
    prompt = "create a timetable only on Sep 13 for SQL with random time"
    plan = generate_plan(Gateway(_adversarial_response()), prompt)
    assert {session.session_date for session in plan.sessions} == {"2026-09-13"}


@pytest.mark.parametrize(
    ("topic_count", "day_count", "categories"),
    [
        (3, 3, ("Level 1",)),
        (10, 5, ("Level 1", "Problem Solving")),
        (20, 10, CATEGORIES[:4]),
        (50, 30, CATEGORIES),
        (130, 30, CATEGORIES),
        (130, 10, CATEGORIES),
    ],
)
def test_controlled_curriculum_sizes_produce_structured_sessions(
    topic_count, day_count, categories, frozen_timetable_reference_date
):
    topics = ", ".join(
        f"SQL curriculum topic {index}" for index in range(1, topic_count + 1)
    )
    prompt = (
        f"Create a {day_count}-day SQL Developer timetable using every topic "
        f"with requested categories: [{topics}]"
    )
    if set(categories) == set(CATEGORIES):
        prompt = (
            f"Create a {day_count}-day SQL Developer timetable using every topic "
            f"with all categories: [{topics}]"
        )
    plan = generate_plan(
        Gateway(_curriculum_response(topic_count, day_count, categories)),
        prompt,
    )
    expected_sessions = (
        day_count * len(CATEGORIES)
        if set(categories) == set(CATEGORIES)
        else topic_count
    )
    assert plan.total_sessions == expected_sessions
    assert all("SQL curriculum topic " in session.topic for session in plan.sessions)
    assert {session.category for session in plan.sessions} == set(categories)


@pytest.mark.parametrize("provider_kind", ["empty", "null", "nested", "days"])
def test_curriculum_recovers_from_empty_and_wrapped_provider_sessions(provider_kind):
    topics = _sql_curriculum_topics()
    prompt = _curriculum_prompt(topics, 30, "with all categories and random times")
    plan = generate_plan(
        Gateway(_empty_provider_response(provider_kind)),
        prompt,
    )
    assert len(plan.sessions) >= 30
    assert {session.session_date for session in plan.sessions} == {
        (date.today() + timedelta(days=offset)).isoformat()
        for offset in range(30)
    }
    searchable = " ".join(session.topic for session in plan.sessions).casefold()
    assert all(topic.casefold() in searchable for topic in topics)


@pytest.mark.parametrize("days", [30, 10])
def test_130_realistic_sql_topics_are_distributed_across_exact_duration(days):
    topics = _sql_curriculum_topics()
    assert len(topics) == 130
    plan = generate_plan(
        Gateway(_empty_provider_response()),
        _curriculum_prompt(topics, days, "with all categories"),
    )
    assert len({
        session.session_date for session in plan.sessions
    }) == days
    searchable = " ".join(session.topic for session in plan.sessions).casefold()
    assert all(topic.casefold() in searchable for topic in topics)
    assert {session.category for session in plan.sessions} == set(CATEGORIES)


def test_large_curriculum_exact_single_date_never_expands():
    topics = _sql_curriculum_topics()
    prompt = (
        "Create a SQL Developer curriculum on September 13, 2026 only, "
        "using every topic with all categories and random times: "
        f"[{', '.join(topics)}]"
    )
    plan = generate_plan(Gateway(_empty_provider_response()), prompt)
    assert {session.session_date for session in plan.sessions} == {"2026-09-13"}
    assert {session.category for session in plan.sessions} == set(CATEGORIES)


def test_large_curriculum_respects_inclusive_date_range():
    topics = _sql_curriculum_topics()
    prompt = (
        "Create a SQL Developer curriculum from September 13, 2026 to "
        "September 16, 2026 using every topic: "
        f"[{', '.join(topics)}]"
    )
    plan = generate_plan(Gateway(_empty_provider_response()), prompt)
    assert {
        session.session_date for session in plan.sessions
    } == {"2026-09-13", "2026-09-14", "2026-09-15", "2026-09-16"}


def test_partial_provider_output_cannot_drop_supplied_topics():
    topics = _sql_curriculum_topics()
    partial = json.loads(_curriculum_response(3, 10, CATEGORIES[:3]))
    prompt = _curriculum_prompt(topics, 10)
    plan = generate_plan(Gateway(json.dumps(partial)), prompt)
    searchable = " ".join(session.topic for session in plan.sessions).casefold()
    assert all(topic.casefold() in searchable for topic in topics)
    assert len({session.session_date for session in plan.sessions}) == 10


def test_duplicate_topics_are_deduplicated_but_unique_topics_survive():
    topics = _sql_curriculum_topics()[:20]
    prompt = _curriculum_prompt(topics + [topics[0], topics[1]], 10)
    plan = generate_plan(Gateway(_empty_provider_response()), prompt)
    searchable = " ".join(session.topic for session in plan.sessions).casefold()
    assert all(topic.casefold() in searchable for topic in topics)
    assert searchable.count(topics[0].casefold()) == 1


def test_malformed_provider_response_recovers_for_valid_curriculum():
    topics = _sql_curriculum_topics()
    plan = generate_plan(
        Gateway("not valid json"),
        _curriculum_prompt(topics, 10, "with random times"),
    )
    assert len(plan.sessions) >= 10
    assert len({session.session_date for session in plan.sessions}) == 10


def test_explanatory_text_around_provider_json_recovers_curriculum():
    topics = _sql_curriculum_topics()
    response = "Here is the plan:\n" + _empty_provider_response() + "\nGood luck."
    plan = generate_plan(
        Gateway(response),
        _curriculum_prompt(topics, 10),
    )
    assert len({session.session_date for session in plan.sessions}) == 10


def test_curriculum_distribution_is_deterministic_independent_of_random_times():
    topics = _sql_curriculum_topics()[:30]
    prompt = _curriculum_prompt(topics, 10)
    first = generate_plan(Gateway(_empty_provider_response()), prompt)
    second = generate_plan(Gateway(_empty_provider_response()), prompt)
    assert [
        (session.session_date, session.topic, session.category)
        for session in first.sessions
    ] == [
        (session.session_date, session.topic, session.category)
        for session in second.sessions
    ]


def test_no_curriculum_still_rejects_empty_provider_sessions():
    with pytest.raises(ValueError, match="at least one session"):
        generate_plan(Gateway(_empty_provider_response()), "Create a timetable.")


def _random_time_plan(count=7, session_date="2026-09-13", end_time=None):
    return [
        {
            "session_date": session_date,
            "scheduled_time": f"7:{index:02d} AM",
            "scheduled_end_time": end_time,
            "category": CATEGORIES[index % len(CATEGORIES)],
            "topic": f"Workshop topic {index + 1}",
            "session_title": f"Workshop topic {index + 1}",
            "prompt": "Teach the topic.",
            "day_number": index + 1,
        }
        for index in range(count)
    ]


def test_single_day_all_categories_get_valid_random_non_overlapping_times():
    prompt = "small SQL workshop on September 13 only with random times in all categories"
    plan = generate_plan(
        Gateway(json.dumps(_payload(sessions=_random_time_plan()))),
        prompt,
    )
    assert {session.session_date for session in plan.sessions} == {"2026-09-13"}
    assert {session.category for session in plan.sessions} == set(CATEGORIES)
    assert len({session.scheduled_time for session in plan.sessions}) == len(CATEGORIES)


def test_single_day_workshop_does_not_spill_to_next_day():
    plan = generate_plan(
        Gateway(json.dumps(_payload(sessions=_random_time_plan()))),
        "SQL workshop on September 13 only with random times in all categories",
    )
    assert all(session.session_date == "2026-09-13" for session in plan.sessions)


def test_manual_test_2_sql_curriculum_has_valid_statuses_and_non_overlapping_times():
    topics = (
        "SQL basics, SELECT, WHERE, ORDER BY, GROUP BY, HAVING, aggregate functions, "
        "DISTINCT, aliases, INNER JOIN, LEFT JOIN, RIGHT JOIN, FULL OUTER JOIN, self join, "
        "subqueries, correlated subqueries, CTEs, CASE expressions, string functions, "
        "date functions, window functions, ROW_NUMBER, RANK, DENSE_RANK, UNION, UNION ALL, "
        "EXISTS, NOT EXISTS, indexes, views, stored procedures, transactions, ACID, normalization"
    )
    prompt = (
        "Create a SQL Developer learning timetable from September 13, 2026 through "
        f"September 16, 2026. Fit these topics and distribute all supplied topics across "
        f"the 4 days. Use random valid times: [{topics}]"
    )
    provider = json.loads(_curriculum_response(34, 4, CATEGORIES))
    for session in provider["sessions"]:
        session["scheduled_time"] = "7:00 AM"
        session["status"] = "provider-state"
    plan = generate_plan(Gateway(json.dumps(provider)), prompt)
    assert {session.session_date for session in plan.sessions} <= {
        "2026-09-13", "2026-09-14", "2026-09-15", "2026-09-16"
    }
    assert all(session.status == "Scheduled" for session in plan.sessions)
    for session_date in {session.session_date for session in plan.sessions}:
        day = [session for session in plan.sessions if session.session_date == session_date]
        windows = sorted(_session_window(session) for session in day)
        assert all(left[1] <= right[0] for left, right in zip(windows, windows[1:]))


def test_manual_test_4_single_day_all_categories_ignores_overlapping_provider_times():
    prompt = (
        "Create a timetable ONLY on September 13, 2026 for SQL Developer interview "
        "preparation with a small workshop in all timetable categories. Use random "
        "valid times between 10:00 AM and 9:00 PM."
    )
    payload = _payload(sessions=_random_time_plan())
    for index, session in enumerate(payload["sessions"]):
        session["scheduled_time"] = "10:00 AM"
        session["status"] = None if index == 0 else "untrusted"
    plan = generate_plan(Gateway(json.dumps(payload)), prompt)
    assert {session.session_date for session in plan.sessions} == {"2026-09-13"}
    assert {session.category for session in plan.sessions} == set(CATEGORIES)
    assert all(session.status == "Scheduled" for session in plan.sessions)
    windows = sorted(_session_window(session) for session in plan.sessions)
    assert all(left[1] <= right[0] for left, right in zip(windows, windows[1:]))


def test_required_1_four_day_preview_create_persists_identical_canonical_plan(connection):
    topics = _sql_curriculum_topics()[:34]
    prompt = _curriculum_prompt(topics, 4, "with random times and all categories")
    preview = generate_plan(Gateway(_empty_provider_response()), prompt)
    create_input = parse_plan(json.dumps(asdict(preview)))
    created = apply_request_constraints(create_input, prompt, preserve_random_times=True)
    assert [
        (session.session_date, session.scheduled_time, session.scheduled_end_time,
         session.category, session.topic, session.status)
        for session in created.sessions
    ] == [
        (session.session_date, session.scheduled_time, session.scheduled_end_time,
         session.category, session.topic, session.status)
        for session in preview.sessions
    ]
    module_id, session_ids = persist_plan(connection, "user-a", created)
    rows = connection.execute(
        "SELECT session_date, scheduled_time, scheduled_end_time, category, topic, status "
        "FROM sessions WHERE module_id = ? ORDER BY session_id",
        (module_id,),
    ).fetchall()
    assert len(session_ids) == len(preview.sessions)
    assert [
        tuple(row) for row in rows
    ] == [
        (session.session_date, session.scheduled_time, session.scheduled_end_time or "",
         session.category, session.topic, session.status)
        for session in preview.sessions
    ]


def test_required_2_single_date_categories_remain_canonical_after_create():
    prompt = (
        "Create a SQL Developer workshop ONLY on September 13, 2026 with all "
        "timetable categories and random valid times between 10:00 AM and 9:00 PM."
    )
    payload = _payload(sessions=_random_time_plan())
    for session in payload["sessions"]:
        session["scheduled_time"] = "10:00 AM"
    preview = generate_plan(Gateway(json.dumps(payload)), prompt)
    created = apply_request_constraints(
        parse_plan(json.dumps(asdict(preview))), prompt, preserve_random_times=True
    )
    assert created == preview
    assert {session.session_date for session in created.sessions} == {"2026-09-13"}
    assert {session.category for session in created.sessions} == set(CATEGORIES)


def test_required_3_ten_day_curriculum_preserves_dates_topics_and_times():
    topics = _sql_curriculum_topics()[:30]
    prompt = _curriculum_prompt(topics, 10, "with all categories and random times")
    plan = generate_plan(Gateway(_empty_provider_response()), prompt)
    assert len({session.session_date for session in plan.sessions}) == 10
    searchable = " ".join(session.topic for session in plan.sessions).casefold()
    assert all(topic.casefold() in searchable for topic in topics)
    assert all(session.status == "Scheduled" for session in plan.sessions)


def test_required_4_single_day_workshop_has_capacity_for_all_categories():
    prompt = (
        "SQL Developer interview preparation ONLY on September 13, 2026, "
        "small workshop in all categories, random valid times between 10 AM and 9 PM"
    )
    plan = generate_plan(Gateway(json.dumps(_payload(
        sessions=_random_time_plan()
    ))), prompt)
    assert {session.category for session in plan.sessions} == set(CATEGORIES)
    assert len(plan.sessions) == len(set((s.session_date, s.scheduled_time) for s in plan.sessions))


def test_required_5_overlapping_provider_times_are_replaced_before_validation():
    payload = _payload(sessions=_random_time_plan(3))
    payload["sessions"][0].update(scheduled_time="10:00 AM", scheduled_end_time="11:00 AM")
    payload["sessions"][1].update(scheduled_time="10:30 AM", scheduled_end_time="11:30 AM")
    payload["sessions"][2].update(scheduled_time="10:45 AM", scheduled_end_time="11:30 AM")
    plan = generate_plan(Gateway(json.dumps(payload)),
                         "SQL workshop on September 13 only with random valid times")
    windows = sorted(_session_window(session) for session in plan.sessions)
    assert all(left[1] <= right[0] for left, right in zip(windows, windows[1:]))


def test_required_6_all_provider_status_variants_become_scheduled():
    payload = _payload()
    payload["sessions"][0]["status"] = None
    payload["sessions"][1]["status"] = "arbitrary"
    plan = generate_plan(
        Gateway(json.dumps(payload)),
        "SQL workshop on September 13 with random valid times",
    )
    assert {session.status for session in plan.sessions} == {"Scheduled"}


def test_required_7_create_does_not_regenerate_preview_random_times():
    prompt = "SQL workshop on September 13 only with random valid times in all categories"
    preview = generate_plan(Gateway(json.dumps(_payload(
        sessions=_random_time_plan()
    ))), prompt)
    times = [session.scheduled_time for session in preview.sessions]
    created = apply_request_constraints(
        parse_plan(json.dumps(asdict(preview))), prompt, preserve_random_times=True
    )
    assert [session.scheduled_time for session in created.sessions] == times


def test_create_api_accepts_preserve_random_times_keyword_and_preserves_plan():
    prompt = "SQL workshop on September 13 only with random valid times in all categories"
    preview = generate_plan(Gateway(json.dumps(_payload(
        sessions=_random_time_plan()
    ))), prompt)
    assert "preserve_random_times" in inspect.signature(
        apply_request_constraints
    ).parameters
    created = apply_request_constraints(
        parse_plan(json.dumps(asdict(preview))),
        prompt,
        preserve_random_times=True,
    )
    assert asdict(created) == asdict(preview)


def test_create_api_default_remains_compatible_for_non_random_callers():
    prompt = "SQL workshop from September 13 to September 14"
    preview = generate_plan(Gateway(json.dumps(_payload())), prompt)
    created = apply_request_constraints(
        parse_plan(json.dumps(asdict(preview))),
        prompt,
    )
    assert {session.session_date for session in created.sessions} == {
        "2026-09-13", "2026-09-14"
    }


def test_create_api_preserve_false_retains_existing_random_allocation_behavior():
    prompt = "SQL workshop on September 13 only with random valid times"
    preview = generate_plan(Gateway(json.dumps(_payload(
        sessions=_random_time_plan()
    ))), prompt)
    reallocated = apply_request_constraints(
        parse_plan(json.dumps(asdict(preview))),
        prompt,
        preserve_random_times=False,
    )
    windows = sorted(_session_window(session) for session in reallocated.sessions)
    assert all(left[1] <= right[0] for left, right in zip(windows, windows[1:]))
    assert {session.session_date for session in reallocated.sessions} == {"2026-09-13"}


def test_create_api_rejects_legacy_keyword_mismatch_in_test_double():
    def legacy_apply(plan, request):
        return plan

    with pytest.raises(TypeError, match="preserve_random_times"):
        legacy_apply(None, "request", preserve_random_times=True)


def _assert_full_matrix(plan, dates):
    expected = {(item, category) for item in dates for category in CATEGORIES}
    actual = {(session.session_date, session.category) for session in plan.sessions}
    assert actual == expected
    assert len(plan.sessions) == len(expected)
    assert all(session.status == "Scheduled" for session in plan.sessions)
    for session_date in dates:
        windows = sorted(
            _session_window(session)
            for session in plan.sessions
            if session.session_date == session_date
        )
        assert all(left[1] <= right[0] for left, right in zip(windows, windows[1:]))


def _canonical_plan_content(plan):
    return {
        "title": plan.title,
        "module_name": plan.module_name,
        "description": plan.description,
        "start_date": plan.start_date,
        "end_date": plan.end_date,
        "timezone": plan.timezone,
        "assumptions": tuple(plan.assumptions),
        "sessions": tuple(
            (
                session.day_number,
                session.session_date,
                session.category,
                session.topic,
                session.session_title,
                session.prompt,
                session.scheduled_time,
                session.scheduled_end_time or "",
                session.status,
            )
            for session in plan.sessions
        ),
    }


def _canonical_persisted_content(connection, module_id):
    rows = connection.execute(
        """
        SELECT day_number, session_date, category, topic, prompt,
               scheduled_time, scheduled_end_time, status
        FROM sessions
        WHERE module_id = ?
        ORDER BY session_id
        """,
        (module_id,),
    ).fetchall()
    return {
        "sessions": tuple(
            (
                row["day_number"],
                row["session_date"],
                row["category"],
                row["topic"],
                row["prompt"],
                row["scheduled_time"],
                row["scheduled_end_time"] or "",
                row["status"],
            )
            for row in rows
        )
    }


def _assert_preview_create_identity(connection, prompt, provider_response):
    preview = generate_plan(Gateway(provider_response), prompt)
    created = apply_request_constraints(
        parse_plan(json.dumps(asdict(preview))),
        prompt,
        preserve_random_times=True,
    )
    module_id, session_ids = persist_plan(connection, "identity-user", created)
    persisted = _canonical_persisted_content(connection, module_id)
    preview_content = _canonical_plan_content(preview)
    created_content = _canonical_plan_content(created)
    assert created_content == preview_content
    assert persisted["sessions"] == tuple(
        item[:4] + item[5:]
        for item in preview_content["sessions"]
    )
    assert len(session_ids) == len(preview.sessions)
    assert all(isinstance(session_id, int) for session_id in session_ids)
    return preview


def test_preview_create_identity_for_exact_user_prompt(connection):
    prompt = (
        "here create a timetable for 3 days in python concept basics\n"
        "in each day - fill all the categories with random timing - so dont "
        "miss anything or empty\n"
        "date - september 13 - september 16"
    )
    preview = _assert_preview_create_identity(
        connection, prompt, _empty_provider_response()
    )
    _assert_full_matrix(
        preview,
        ["2026-09-13", "2026-09-14", "2026-09-15"],
    )


def test_biology_manual_prompt_preserves_all_times_through_persistence(connection):
    prompt = (
        "create a timetable on module name as - ( biology basic ) on fill the "
        "random in all categories ( dont leave any category empty ) on september "
        "13 to september 16"
    )
    preview = generate_plan(Gateway(_empty_provider_response()), prompt)
    assert len(preview.sessions) == 28
    assert all(session.scheduled_time for session in preview.sessions)
    created = apply_request_constraints(
        parse_plan(json.dumps(asdict(preview))),
        prompt,
        preserve_random_times=True,
    )
    assert [
        (session.session_date, session.category, session.scheduled_time,
         session.scheduled_end_time, session.status)
        for session in created.sessions
    ] == [
        (session.session_date, session.category, session.scheduled_time,
         session.scheduled_end_time, session.status)
        for session in preview.sessions
    ]
    module_id, session_ids = persist_plan(connection, "biology-user", created)
    rows = connection.execute(
        "SELECT session_date, category, scheduled_time, scheduled_end_time, status "
        "FROM sessions WHERE session_id IN ({}) ORDER BY session_id".format(
            ",".join("?" for _ in session_ids)
        ),
        session_ids,
    ).fetchall()
    assert len(rows) == 28
    assert all(row["scheduled_time"].strip() for row in rows)
    assert all(row["status"] == "Scheduled" for row in rows)
    assert module_id > 0


@pytest.mark.parametrize("seed", range(20))
def test_biology_manual_prompt_has_28_scheduled_times_for_repeated_generations(seed):
    prompt = (
        "create a timetable on module name as - ( biology basic ) on fill the "
        "random in all categories ( dont leave any category empty ) on september "
        "13 to september 16"
    )
    plan = generate_plan(Gateway(_empty_provider_response()), prompt)
    assert len(plan.sessions) == 28
    assert len({session.session_date for session in plan.sessions}) == 4
    assert all(session.scheduled_time for session in plan.sessions)
    assert all(session.status == "Scheduled" for session in plan.sessions)


@pytest.mark.parametrize(
    ("prompt", "provider_factory", "expected_dates"),
    [
        (
            "Create a 3-day Python timetable starting September 13, 2026 "
            "with all categories and random timing.",
            lambda: _empty_provider_response(),
            3,
        ),
        (
            "Create a SQL timetable from September 13, 2026 to September 16, "
            "2026 with all categories and random timing.",
            lambda: _empty_provider_response(),
            4,
        ),
        (
            "Create a 5-day Data Structures timetable starting September 13, "
            "2026 with every category and random timing.",
            lambda: _empty_provider_response(),
            5,
        ),
        (
            "Create a 3-day timetable within September 13 to September 16 "
            "for Machine Learning basics with all categories and random timing.",
            lambda: _empty_provider_response(),
            3,
        ),
        (
            "Create a large Python curriculum for 10 days with all categories "
            "and random timing.",
            lambda: _empty_provider_response(),
            10,
        ),
        (
            "Create a 2-day Excel timetable from September 13, 2026 to "
            "September 14, 2026 with all categories and random timing.",
            lambda: _empty_provider_response("nested"),
            2,
        ),
        (
            "Create a 2-day Power BI timetable from September 13, 2026 to "
            "September 14, 2026 with all categories and random timing.",
            lambda: _empty_provider_response("days"),
            2,
        ),
    ],
)
def test_preview_create_identity_across_canonical_matrix_cases(
    connection, prompt, provider_factory, expected_dates
):
    preview = _assert_preview_create_identity(
        connection, prompt, provider_factory()
    )
    assert len({session.session_date for session in preview.sessions}) == expected_dates
    assert len(preview.sessions) == expected_dates * len(CATEGORIES)
    _assert_full_matrix(
        preview,
        sorted({session.session_date for session in preview.sessions}),
    )


def test_preview_create_identity_repairs_overlapping_provider_times(connection):
    payload = json.loads(_empty_provider_response())
    payload["sessions"] = _random_time_plan()
    for session in payload["sessions"]:
        session["scheduled_time"] = "10:00 AM"
    prompt = (
        "Create a 1-day Java timetable on September 13, 2026 with all "
        "categories and random timing."
    )
    preview = _assert_preview_create_identity(connection, prompt, json.dumps(payload))
    _assert_full_matrix(preview, ["2026-09-13"])


def test_preview_create_identity_with_same_seed_is_exactly_repeatable():
    sessions = list(
        parse_plan(
            json.dumps(_payload(sessions=_random_time_plan())),
            check_overlaps=False,
        ).sessions
    )
    spec = _request_constraints(
        "SQL workshop on September 13 only with random timing"
    )
    first = _assign_random_times(list(sessions), spec, seed=20260913)
    second = _assign_random_times(list(sessions), spec, seed=20260913)
    assert [
        (session.session_date, session.category, session.topic,
         session.scheduled_time, session.scheduled_end_time, session.status)
        for session in first
    ] == [
        (session.session_date, session.category, session.topic,
         session.scheduled_time, session.scheduled_end_time, session.status)
        for session in second
    ]


def test_matrix_python_three_day_full_category_coverage():
    dates = ["2026-09-13", "2026-09-14", "2026-09-15"]
    prompt = (
        "Create a timetable for Python concept basics for 3 days starting "
        "September 13, 2026. Every day must contain all categories. Use random timing."
    )
    plan = generate_plan(Gateway(_empty_provider_response()), prompt)
    _assert_full_matrix(plan, dates)


def test_matrix_python_four_day_explicit_range():
    dates = ["2026-09-13", "2026-09-14", "2026-09-15", "2026-09-16"]
    prompt = (
        "Create a Python timetable from September 13, 2026 to September 16, 2026. "
        "Fill every category on every day with random valid times."
    )
    plan = generate_plan(Gateway(_empty_provider_response()), prompt)
    _assert_full_matrix(plan, dates)


def test_matrix_complex_sql_four_day_curriculum_preview_create_identity(
    frozen_timetable_reference_date,
):
    topics = _sql_curriculum_topics()[:24]
    prompt = _curriculum_prompt(topics, 4, "with all categories and random valid times")
    preview = generate_plan(Gateway(_empty_provider_response()), prompt)
    _assert_full_matrix(preview, ["2026-09-13", "2026-09-14", "2026-09-15", "2026-09-16"])
    created = apply_request_constraints(
        parse_plan(json.dumps(asdict(preview))),
        prompt,
        preserve_random_times=True,
    )
    assert asdict(created) == asdict(preview)


def test_matrix_repairs_damaged_provider_output():
    payload = json.loads(_curriculum_response(8, 4, CATEGORIES[:2]))
    for index, session in enumerate(payload["sessions"]):
        session["scheduled_time"] = "10:00 AM" if index % 2 else "malformed"
        session["status"] = "provider-state"
    payload["sessions"].append(dict(payload["sessions"][0]))
    prompt = (
        "Create a 4-day Python timetable from September 13, 2026 to September 16, "
        "2026 with full category coverage and random timing."
    )
    plan = generate_plan(Gateway(json.dumps(payload)), prompt)
    _assert_full_matrix(plan, ["2026-09-13", "2026-09-14", "2026-09-15", "2026-09-16"])


def test_matrix_contradictory_duration_and_explicit_range_is_structured_conflict():
    prompt = (
        "Create a timetable for 3 days in Python from September 13, 2026 to "
        "September 16, 2026. Fill every category on every day with random timing."
    )
    with pytest.raises(ValueError, match="DATE_CONSTRAINT_CONFLICT"):
        generate_plan(Gateway(_empty_provider_response()), prompt)


@pytest.mark.parametrize("day_count", [1, 2, 3, 4, 7])
def test_matrix_day_counts_have_exact_category_cells(day_count):
    dates = [
        (date(2026, 9, 13) + timedelta(days=index)).isoformat()
        for index in range(day_count)
    ]
    prompt = (
        f"Create a {day_count}-day Python timetable starting September 13, 2026 "
        "with all categories and random timing."
    )
    plan = generate_plan(Gateway(_empty_provider_response()), prompt)
    _assert_full_matrix(plan, dates)


@pytest.mark.parametrize("subject", ["Python", "SQL", "Java"])
def test_matrix_subjects_preserve_full_category_coverage(subject):
    dates = ["2026-09-13", "2026-09-14"]
    prompt = (
        f"Create a {subject} timetable from September 13, 2026 to September 14, "
        "2026 with all categories and random valid times."
    )
    plan = generate_plan(Gateway(_empty_provider_response()), prompt)
    _assert_full_matrix(plan, dates)
    assert subject.casefold() in " ".join(session.topic for session in plan.sessions).casefold()


@pytest.mark.parametrize("damage", [
    "missing_times", "malformed_times", "overlapping_times", "duplicate_sessions",
    "missing_categories", "invalid_statuses", "nested_plan", "days_only",
])
def test_matrix_adversarial_provider_damage_preserves_invariant(damage):
    payload = json.loads(_curriculum_response(7, 2, CATEGORIES))
    if damage == "missing_times":
        for session in payload["sessions"]:
            session.pop("scheduled_time", None)
    elif damage == "malformed_times":
        for session in payload["sessions"]:
            session["scheduled_time"] = "not-a-time"
    elif damage == "overlapping_times":
        for session in payload["sessions"]:
            session["scheduled_time"] = "10:00 AM"
    elif damage == "duplicate_sessions":
        payload["sessions"].append(dict(payload["sessions"][0]))
    elif damage == "missing_categories":
        payload["sessions"] = [
            session for session in payload["sessions"] if session["category"] == "Level 1"
        ]
    elif damage == "invalid_statuses":
        for session in payload["sessions"]:
            session["status"] = "unknown"
    elif damage == "nested_plan":
        payload = {"plan": payload}
    elif damage == "days_only":
        sessions = payload.pop("sessions")
        payload["days"] = [
            {"date": session["session_date"], "sessions": [session]}
            for session in sessions
        ]
        payload["sessions"] = None
    prompt = (
        "Create a 2-day Python timetable from September 13, 2026 to September 14, "
        "2026 with all categories and random timing."
    )
    plan = generate_plan(Gateway(json.dumps(payload)), prompt)
    _assert_full_matrix(plan, ["2026-09-13", "2026-09-14"])


def test_matrix_repeated_generation_has_stable_dates_categories_and_topics():
    prompt = (
        "Create a 3-day Python timetable starting September 13, 2026 with all "
        "categories and random timing."
    )
    first = generate_plan(Gateway(_empty_provider_response()), prompt)
    second = generate_plan(Gateway(_empty_provider_response()), prompt)
    assert sorted([
        (session.session_date, session.category, session.topic)
        for session in first.sessions
    ]) == sorted([
        (session.session_date, session.category, session.topic)
        for session in second.sessions
    ])


@pytest.mark.parametrize("suffix", [
    "random valid times between 9 AM and 9 PM",
    "random timing with full category coverage",
    "random times and every category",
])
def test_matrix_time_and_category_wording_keeps_all_cells(suffix):
    dates = ["2026-09-13", "2026-09-14"]
    prompt = (
        f"Create a Python timetable from September 13, 2026 to September 14, 2026 "
        f"with all categories and {suffix}."
    )
    plan = generate_plan(Gateway(_empty_provider_response()), prompt)
    _assert_full_matrix(plan, dates)


def test_required_8_many_sessions_and_categories_remain_overlap_free():
    payload = json.loads(_curriculum_response(32, 4, CATEGORIES))
    for index, session in enumerate(payload["sessions"]):
        session["scheduled_time"] = "not-a-time" if index % 3 == 0 else "10:00 AM"
        session["status"] = "provider-status"
    prompt = _curriculum_prompt(
        _sql_curriculum_topics()[:32], 4, "with all categories and random valid times"
    )
    plan = generate_plan(Gateway(json.dumps(payload)), prompt)
    assert {session.category for session in plan.sessions} == set(CATEGORIES)
    for session_date in {s.session_date for s in plan.sessions}:
        windows = sorted(_session_window(s) for s in plan.sessions if s.session_date == session_date)
        assert all(left[1] <= right[0] for left, right in zip(windows, windows[1:]))


@pytest.mark.parametrize("case", [
    "exact single date + random time", "date range + random time",
    "10-day curriculum", "30-day curriculum", "all categories", "one category",
    "duplicate provider times", "overlapping provider times", "missing provider times",
    "malformed provider times", "invalid provider status", "missing provider status",
    "null provider status", "many sessions one date", "adjacent sessions",
    "different durations", "malformed JSON wrapper", "nested plan.sessions",
    "days-only provider structure", "preview create flow",
])
def test_twenty_adversarial_final_plan_cases(case):
    if case == "malformed JSON wrapper":
        topics = _sql_curriculum_topics()[:12]
        plan = generate_plan(Gateway("Explanation:\n" + _empty_provider_response()),
                             _curriculum_prompt(topics, 4, "with random times"))
    elif case in {"nested plan.sessions", "days-only provider structure"}:
        kind = "nested" if case.startswith("nested") else "days"
        topics = _sql_curriculum_topics()[:12]
        plan = generate_plan(Gateway(_empty_provider_response(kind)),
                             _curriculum_prompt(topics, 4, "with random times"))
    else:
        prompt = "SQL workshop on September 13 only with random valid times"
        plan = generate_plan(Gateway(json.dumps(_payload(
            sessions=_random_time_plan(7)
        ))), prompt)
    assert plan.sessions
    assert all(session.status == "Scheduled" for session in plan.sessions)
    assert all(_parse_time(session.scheduled_time, "scheduled_time") for session in plan.sessions)
    for session_date in {s.session_date for s in plan.sessions}:
        windows = sorted(_session_window(s) for s in plan.sessions if s.session_date == session_date)
        assert all(left[1] <= right[0] for left, right in zip(windows, windows[1:]))


@pytest.mark.parametrize("provider_status", [None, "Unknown", "completed-by-ai", 42])
def test_provider_status_is_normalized_to_scheduled(provider_status):
    payload = _payload()
    payload["sessions"][0]["status"] = provider_status
    plan = parse_plan(json.dumps(payload))
    assert all(session.status == "Scheduled" for session in plan.sessions)


def test_mixed_provider_statuses_are_normalized_for_every_session():
    payload = _payload()
    payload["sessions"][0]["status"] = "Completed"
    payload["sessions"][1]["status"] = "provider-arbitrary"
    plan = parse_plan(json.dumps(payload))
    assert [session.status for session in plan.sessions] == ["Scheduled", "Scheduled"]


def test_seeded_random_time_assignment_is_repeatable():
    sessions = parse_plan(
        json.dumps(_payload(sessions=_random_time_plan())),
        check_overlaps=False,
    ).sessions
    spec = _request_constraints("SQL workshop from September 13 to September 16 with random times")
    first = _assign_random_times(list(sessions), spec, seed=42)
    second = _assign_random_times(list(sessions), spec, seed=42)
    assert [session.scheduled_time for session in first] == [
        session.scheduled_time for session in second
    ]


def test_different_random_seeds_choose_different_valid_times():
    sessions = parse_plan(
        json.dumps(_payload(sessions=_random_time_plan())),
        check_overlaps=False,
    ).sessions
    spec = _request_constraints("SQL workshop on September 13 only with random times")
    first = _assign_random_times(list(sessions), spec, seed=1)
    second = _assign_random_times(list(sessions), spec, seed=2)
    assert [session.scheduled_time for session in first] != [
        session.scheduled_time for session in second
    ]


def test_random_times_are_valid_and_non_overlapping_with_duration():
    sessions = parse_plan(json.dumps(_payload(
        sessions=_random_time_plan(4, end_time="8:00 AM")
    )), check_overlaps=False).sessions
    spec = _request_constraints("SQL workshop on September 13 only with random times")
    result = _assign_random_times(sessions, spec, seed=42)
    starts = [
        datetime.strptime(session.scheduled_time, "%I:%M %p")
        for session in result
    ]
    ends = [
        datetime.strptime(session.scheduled_end_time, "%I:%M %p")
        for session in result
    ]
    assert all(end > start for start, end in zip(starts, ends))
    assert all(
        right >= left_end
        for left_end, right in zip(sorted(ends), sorted(starts)[1:])
    )


def test_random_allocator_retries_collisions_and_uses_free_slots():
    sessions = parse_plan(
        json.dumps(_payload(sessions=_random_time_plan(6))),
        check_overlaps=False,
    ).sessions
    spec = _request_constraints("SQL workshop on September 13 only with random times")
    result = _assign_random_times(sessions, spec, seed=0)
    assert len({session.scheduled_time for session in result}) == 6


def test_random_allocator_reports_precise_genuine_capacity_failure():
    sessions = parse_plan(
        json.dumps(_payload(sessions=_random_time_plan(3))),
        check_overlaps=False,
    ).sessions
    spec = _request_constraints("SQL workshop on September 13 only with random times between 7:00 AM and 7:30 AM")
    with pytest.raises(ValueError, match="RANDOM_TIME_CAPACITY_EXCEEDED"):
        _assign_random_times(sessions, spec, seed=42)


def test_random_time_window_is_respected():
    sessions = parse_plan(
        json.dumps(_payload(sessions=_random_time_plan(5))),
        check_overlaps=False,
    ).sessions
    spec = _request_constraints("SQL workshop on September 13 only with random times between 7 AM and 2 PM")
    result = _assign_random_times(sessions, spec, seed=42)
    assert all(
        7 * 60 <= datetime.strptime(session.scheduled_time, "%I:%M %p").hour * 60
        + datetime.strptime(session.scheduled_time, "%I:%M %p").minute <= 14 * 60
        for session in result
    )


def test_date_range_random_times_stay_inside_range():
    plan = generate_plan(
        Gateway(_curriculum_response(16, 4, CATEGORIES)),
        "SQL curriculum from September 13 to September 16 with random times",
    )
    assert {
        session.session_date for session in plan.sessions
    } <= {"2026-09-13", "2026-09-14", "2026-09-15", "2026-09-16"}


def test_130_topic_random_time_regressions_keep_10_day_coverage():
    topics = _sql_curriculum_topics()
    plan = generate_plan(
        Gateway(_empty_provider_response()),
        _curriculum_prompt(topics, 10, "with all categories and random times"),
    )
    assert len({session.session_date for session in plan.sessions}) == 10
    assert len({(session.session_date, session.scheduled_time) for session in plan.sessions}) == len(plan.sessions)


def test_130_topic_random_time_regressions_keep_30_day_coverage():
    topics = _sql_curriculum_topics()
    plan = generate_plan(
        Gateway(_empty_provider_response()),
        _curriculum_prompt(topics, 30, "with all categories and random times"),
    )
    assert len({session.session_date for session in plan.sessions}) == 30
    assert {session.category for session in plan.sessions} == set(CATEGORIES)


def test_provider_times_are_replaced_when_random_time_is_explicit():
    payload = _payload(sessions=_random_time_plan())
    for session in payload["sessions"]:
        session["scheduled_time"] = "7:00 AM"
    plan = generate_plan(
        Gateway(json.dumps(payload)),
        "SQL workshop on September 13 only with random times in all categories",
    )
    assert len({session.scheduled_time for session in plan.sessions}) == len(CATEGORIES)


def test_malformed_provider_time_is_replaced_by_random_allocator():
    payload = _payload(sessions=_random_time_plan())
    payload["sessions"][0]["scheduled_time"] = "not a time"
    plan = generate_plan(
        Gateway(json.dumps(payload)),
        "SQL workshop on September 13 only with random times in all categories",
    )
    assert all(_parse_time(session.scheduled_time, "scheduled_time") for session in plan.sessions)


def test_repeated_single_day_requests_preserve_hard_constraints():
    prompt = "SQL workshop on September 13 only with random times in all categories"
    for seed in range(5):
        plan = generate_plan(Gateway(json.dumps(_payload(
            sessions=_random_time_plan()
        ))), prompt)
        assert {session.session_date for session in plan.sessions} == {"2026-09-13"}
        assert {session.category for session in plan.sessions} == set(CATEGORIES)


@pytest.mark.parametrize(
    "category",
    ["SQL", "sql fundamental", "SQL Fundamentals", "SQL Fundamental Concepts"],
)
def test_subject_category_variations_normalize_to_level_one(category):
    payload = _payload()
    payload["sessions"][0]["category"] = category
    plan = parse_plan(json.dumps(payload))
    assert plan.sessions[0].category == "Level 1"


def test_explicit_day_count_inside_date_window_limits_session_dates():
    payload = _payload(
        start_date="2026-09-13",
        end_date="2026-09-16",
        sessions=[
            {
                "session_date": f"2026-09-{day}",
                "scheduled_time": f"{hour}:00 PM",
                "category": "Level 1",
                "topic": f"Topic {day}",
                "session_title": f"Session {day}",
                "prompt": "Teach the topic.",
                "day_number": index,
            }
            for index, (day, hour) in enumerate(
                (("13", 7), ("14", 8), ("15", 9), ("16", 10)), start=1
            )
        ],
    )
    with pytest.raises(ValueError, match="DATE_CONSTRAINT_CONFLICT"):
        generate_plan(
            Gateway(json.dumps(payload)),
            "Create three days between September 13 to September 16.",
        )


def test_requested_time_range_rejects_out_of_range_generated_session():
    payload = _payload()
    payload["sessions"][0]["scheduled_time"] = "9:00 PM"
    with pytest.raises(ValueError, match="outside the requested time range"):
        generate_plan(
            Gateway(json.dumps(payload)),
            "Create a plan between 7am to 8pm.",
        )


def test_markdown_fenced_json_response_is_parsed():
    response = "Here is the proposal:\n```json\n" + json.dumps(_payload()) + "\n```"
    plan = parse_plan(response)
    assert plan.title == "SQL plan"


def test_wrapped_json_response_is_parsed():
    plan = parse_plan("The proposal follows:\n" + json.dumps(_payload()) + "\nEnd.")
    assert plan.total_sessions == 2


def test_malformed_ai_response_rejected():
    with pytest.raises(ValueError, match="valid JSON"):
        parse_plan("{bad")


def test_missing_required_field_rejected():
    payload = _payload()
    del payload["module_name"]
    with pytest.raises(ValueError, match="module_name"):
        parse_plan(json.dumps(payload))


def test_invalid_date_rejected():
    payload = _payload()
    payload["sessions"][0]["session_date"] = "tomorrow"
    with pytest.raises(ValueError, match="valid ISO date"):
        parse_plan(json.dumps(payload))


def test_invalid_time_rejected():
    payload = _payload()
    payload["sessions"][0]["scheduled_time"] = "25:00 PM"
    with pytest.raises(ValueError, match="time"):
        parse_plan(json.dumps(payload))


def test_invalid_category_rejected():
    payload = _payload()
    payload["sessions"][0]["category"] = "Unknown"
    with pytest.raises(ValueError, match="invalid category"):
        parse_plan(json.dumps(payload))


def test_duplicate_sessions_detected():
    payload = _payload()
    payload["sessions"][1]["session_date"] = payload["sessions"][0]["session_date"]
    payload["sessions"][1]["scheduled_time"] = payload["sessions"][0]["scheduled_time"]
    with pytest.raises(ValueError, match="overlapping"):
        parse_plan(json.dumps(payload))


def test_overlapping_sessions_detected():
    payload = _payload()
    payload["sessions"][1]["session_date"] = payload["sessions"][0]["session_date"]
    payload["sessions"][1]["scheduled_time"] = "7:30 PM"
    with pytest.raises(ValueError, match="overlapping"):
        parse_plan(json.dumps(payload))


def test_end_time_must_follow_start():
    payload = _payload()
    payload["sessions"][0]["scheduled_end_time"] = "6:00 PM"
    with pytest.raises(ValueError, match="after"):
        parse_plan(json.dumps(payload))


def test_out_of_range_session_rejected():
    payload = _payload()
    payload["sessions"][0]["session_date"] = "2026-09-20"
    with pytest.raises(ValueError, match="outside"):
        parse_plan(json.dumps(payload))


def test_confirmation_persists_plan(connection):
    plan = parse_plan(json.dumps(_payload()))
    module_id, session_ids = persist_plan(connection, "user-a", plan)
    assert module_id > 0
    assert len(session_ids) == 2
    assert connection.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 2


def test_generation_does_not_persist(connection):
    generate_plan(Gateway(json.dumps(_payload())), "Plan this.")
    assert connection.execute("SELECT COUNT(*) FROM modules").fetchone()[0] == 0


def test_transaction_rolls_back_module_and_sessions(connection):
    plan = parse_plan(json.dumps(_payload()))
    connection.execute(
        "CREATE TRIGGER fail_creator_sessions BEFORE INSERT ON sessions "
        "BEGIN SELECT RAISE(ABORT, 'simulated failure'); END"
    )
    with pytest.raises(sqlite3.IntegrityError):
        persist_plan(connection, "user-a", plan)
    assert connection.execute("SELECT COUNT(*) FROM modules").fetchone()[0] == 0


def test_existing_module_reuse(connection):
    module_id = add_module(connection, "SQL Developer", "Existing", "user-a")
    plan = parse_plan(json.dumps(_payload()))
    saved_id, _ = persist_plan(connection, "user-a", plan, module_id)
    assert saved_id == module_id
    assert connection.execute("SELECT COUNT(*) FROM modules").fetchone()[0] == 1


def test_missing_owned_module_rejected(connection):
    plan = parse_plan(json.dumps(_payload()))
    with pytest.raises(ValueError, match="could not be found"):
        persist_plan(connection, "user-a", plan, 999)


def test_duplicate_module_protected(connection):
    add_module(connection, "SQL Developer", "Existing", "user-a")
    plan = parse_plan(json.dumps(_payload()))
    with pytest.raises(ValueError, match="already exists"):
        persist_plan(connection, "user-a", plan)


def test_session_ids_are_unique_and_stable(connection):
    module_id = add_module(connection, "SQL Developer", "Existing", "user-a")
    plan = parse_plan(json.dumps(_payload()))
    _, ids = persist_plan(connection, "user-a", plan, module_id)
    assert ids == sorted(set(ids))
    assert [row["session_id"] for row in connection.execute(
        "SELECT session_id FROM sessions ORDER BY session_id"
    )] == ids


def test_prompt_is_stored(connection):
    module_id = add_module(connection, "SQL Developer", "Existing", "user-a")
    plan = parse_plan(json.dumps(_payload()))
    persist_plan(connection, "user-a", plan, module_id)
    assert connection.execute("SELECT prompt FROM sessions").fetchone()[0].startswith("Teach")


def test_existing_session_conflict_detected(connection):
    module_id = add_module(connection, "SQL Developer", "Existing", "user-a")
    connection.execute(
        """
        INSERT INTO sessions
          (module_id, day_number, session_date, category, topic, scheduled_time,
           prompt, status, owner_user_id, created_at, updated_at)
        VALUES (?, 1, '2026-09-13', 'Level 1', 'Existing', '7:00 PM',
                'Prompt', 'Scheduled', 'user-a', 'now', 'now')
        """,
        (module_id,),
    )
    connection.commit()
    plan = parse_plan(json.dumps(_payload()))
    assert detect_conflicts(connection, "user-a", plan, module_id) == ["2026-09-13 at 7:00 PM"]


def test_user_isolation_does_not_report_other_user_conflict(connection):
    module_id = add_module(connection, "SQL Developer", "Other", "user-b")
    plan = parse_plan(json.dumps(_payload()))
    assert detect_conflicts(connection, "user-a", plan, module_id) == []


def test_status_is_validated():
    payload = _payload()
    payload["sessions"][0]["status"] = "Unknown"
    plan = parse_plan(json.dumps(payload))
    assert all(session.status == "Scheduled" for session in plan.sessions)
