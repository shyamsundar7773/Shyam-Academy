import json
import sqlite3
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from ai.gateway import AIGateway
from database.schema import initialize_database
from services.module_service import add_module
from services.timetable_creator_service import (
    CATEGORIES,
    _parse_time,
    _assign_random_times,
    _request_constraints,
    detect_conflicts,
    generate_plan,
    parse_plan,
    persist_plan,
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


def test_valid_free_form_request_calls_gateway_once():
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
        "with upcoming random time in fit in all categories"
    )
    payload = json.loads(_adversarial_response())
    payload["assumptions"] = "Small workshop sessions."
    plan = generate_plan(Gateway(json.dumps(payload)), prompt)
    assert plan.assumptions == ["Small workshop sessions."]
    assert {session.session_date for session in plan.sessions} == {"2026-09-13"}
    assert {session.category for session in plan.sessions} == set(CATEGORIES)
    assert plan.timezone == "Asia/Kolkata"
    now = datetime.now(ZoneInfo("Asia/Kolkata"))
    for session in plan.sessions:
        scheduled = datetime.combine(
            date.fromisoformat(session.session_date),
            datetime.strptime(session.scheduled_time, "%I:%M %p").time(),
            tzinfo=ZoneInfo("Asia/Kolkata"),
        )
        assert scheduled > now


def test_real_world_pipeline_has_canonical_random_times_and_all_categories():
    prompt = (
        "create a timetable on sep 13 only as small sql workshop session "
        "with upcoming random time in fit in all categories"
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
    "SQL workshop on Sep 13 only with random upcoming time",
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
    topic_count, day_count, categories
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
    assert plan.total_sessions == topic_count
    assert all(session.topic.startswith("SQL curriculum topic ") for session in plan.sessions)
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
    plan = generate_plan(
        Gateway(json.dumps(payload)),
        "Create three days between September 13 to September 16.",
    )
    assert [session.session_date for session in plan.sessions] == [
        "2026-09-13", "2026-09-14", "2026-09-15"
    ]


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
    with pytest.raises(ValueError, match="duplicate"):
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
    with pytest.raises(ValueError, match="invalid status"):
        parse_plan(json.dumps(payload))
