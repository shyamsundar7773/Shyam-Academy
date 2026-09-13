import json
import sqlite3
from datetime import date, timedelta

import pytest

from ai.gateway import AIGateway
from database.schema import initialize_database
from services.module_service import add_module
from services.timetable_creator_service import (
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


def test_empty_request_rejected():
    with pytest.raises(ValueError, match="Describe"):
        generate_plan(Gateway("{}"), " ")


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
