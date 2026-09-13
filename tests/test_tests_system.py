import json
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from ai.gateway import AIGateway, AIProviderError
from database.schema import initialize_database
from services.module_service import add_module
from services.test_service import (
    attempt_expired,
    completed_test_event,
    create_test,
    evaluate_test,
    generate_test,
    get_result,
    parse_test,
    public_test,
    start_attempt,
)


def payload(**changes):
    value = {
        "title": "SQL assessment",
        "description": "Assessment",
        "category": "Daily Test",
        "topic": "Joins",
        "difficulty": "Intermediate",
        "duration_minutes": 20,
        "questions": [
            {
                "order_index": 1,
                "question_type": "mcq",
                "question_text": "Which join keeps matching rows?",
                "options": ["INNER JOIN", "CROSS JOIN"],
                "correct_answer": "INNER JOIN",
                "explanation": "INNER JOIN returns matching rows.",
                "points": 1,
                "weak_area": "INNER JOIN",
            },
            {
                "order_index": 2,
                "question_type": "multiple_select",
                "question_text": "Which are join practices?",
                "options": ["Use keys", "Review cardinality", "Ignore nulls"],
                "correct_answer": ["Use keys", "Review cardinality"],
                "explanation": "Keys and cardinality matter.",
                "points": 2,
                "weak_area": "Join design",
            },
            {
                "order_index": 3,
                "question_type": "short_answer",
                "question_text": "Explain a join.",
                "options": [],
                "correct_answer": "A join combines related rows.",
                "explanation": "Relate rows through keys.",
                "points": 2,
                "weak_area": "Join reasoning",
            },
        ],
    }
    value.update(changes)
    return value


class FakeGateway(AIGateway):
    def __init__(self, response=None, evaluation=None):
        self.response = response
        self.evaluation = evaluation or {
            "correct": True, "points_awarded": 2, "feedback": "Good explanation."
        }
        self.generate_calls = 0
        self.evaluate_calls = 0

    def generate_test(self, prompt):
        self.generate_calls += 1
        return self.response

    def evaluate_test_answer(self, prompt):
        self.evaluate_calls += 1
        return json.dumps(self.evaluation)


@pytest.fixture
def connection():
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    initialize_database(connection)
    yield connection
    connection.close()


def make_plan():
    return parse_test(json.dumps(payload()))


def make_test(connection, user="user-a", module_id=None, session_id=None):
    return create_test(connection, user, make_plan(), module_id, session_id)


def test_model_validation():
    assert make_plan().total_questions == 3


def test_empty_test_rejected():
    with pytest.raises(ValueError, match="at least one"):
        parse_test(json.dumps(payload(questions=[])))


def test_malformed_response_rejected():
    with pytest.raises(ValueError, match="valid JSON"):
        parse_test("{bad")


def test_fenced_and_explanatory_json_is_accepted():
    encoded = json.dumps(payload())
    assert parse_test(f"```json\n{encoded}\n```").topic == "Joins"
    assert parse_test(f"Here is the test:\n{encoded}").topic == "Joins"


def test_invalid_question_type_rejected():
    questions = payload()["questions"]
    questions[0]["question_type"] = "essay"
    with pytest.raises(ValueError, match="question type"):
        parse_test(json.dumps(payload(questions=questions)))


def test_missing_question_text_rejected():
    questions = payload()["questions"]
    del questions[0]["question_text"]
    with pytest.raises(ValueError, match="question_text"):
        parse_test(json.dumps(payload(questions=questions)))


def test_missing_options_rejected():
    questions = payload()["questions"]
    questions[0]["options"] = []
    with pytest.raises(ValueError, match="options"):
        parse_test(json.dumps(payload(questions=questions)))


def test_duplicate_questions_rejected():
    questions = payload()["questions"]
    questions[1]["question_text"] = questions[0]["question_text"]
    with pytest.raises(ValueError, match="duplicate"):
        parse_test(json.dumps(payload(questions=questions)))


def test_generation_uses_gateway_once():
    gateway = FakeGateway(json.dumps(payload()))
    assert generate_test(gateway, "Create a joins test.").topic == "Joins"
    assert gateway.generate_calls == 1


def test_empty_generation_prompt_rejected():
    with pytest.raises(ValueError, match="Describe"):
        generate_test(FakeGateway(json.dumps(payload())), "")


def test_provider_failure_is_safe():
    class Failing(FakeGateway):
        def generate_test(self, prompt):
            raise RuntimeError("provider down")
    with pytest.raises(AIProviderError):
        generate_test(Failing(), "test joins")


def test_test_persistence_and_id(connection):
    test_id = make_test(connection)
    assert test_id
    assert connection.execute("SELECT COUNT(*) FROM tests").fetchone()[0] == 1


def test_user_isolation(connection):
    test_id = make_test(connection, "user-a")
    with pytest.raises(ValueError):
        public_test(connection, test_id, "user-b")


def test_module_isolation(connection):
    module_a = add_module(connection, "SQL", "", "user-a")
    module_b = add_module(connection, "Python", "", "user-a")
    test_id = make_test(connection, "user-a", module_a)
    assert connection.execute("SELECT module_id FROM tests WHERE test_id=?", (test_id,)).fetchone()[0] == module_a
    assert module_b != module_a


def test_session_relationship(connection):
    module_id = add_module(connection, "SQL", "", "user-a")
    connection.execute(
        """INSERT INTO sessions
        (module_id,day_number,session_date,category,topic,scheduled_time,prompt,
         status,owner_user_id,created_at,updated_at)
        VALUES (?,1,'2026-09-13','Daily Test','Joins','7:00 PM','test',
        'Scheduled','user-a','now','now')""", (module_id,)
    )
    connection.commit()
    session_id = connection.execute("SELECT last_insert_rowid()").fetchone()[0]
    test_id = make_test(connection, "user-a", module_id, session_id)
    row = connection.execute("SELECT session_id FROM tests WHERE test_id=?", (test_id,)).fetchone()
    assert row["session_id"] == session_id


def test_context_relationship_and_completion_do_not_mark_attendance_without_saved_notes(connection):
    module_id = add_module(connection, "SQL", "", "user-a")
    connection.execute(
        """INSERT INTO sessions
        (module_id,day_number,session_date,category,topic,scheduled_time,prompt,
         status,owner_user_id,created_at,updated_at)
        VALUES (?,1,'2026-09-13','Test','Joins','7:00 PM','test',
        'Scheduled','user-a','now','now')""", (module_id,)
    )
    connection.commit()
    session_id = connection.execute("SELECT last_insert_rowid()").fetchone()[0]
    test_id = make_test(connection, "user-a", module_id, session_id)
    connection.execute(
        "UPDATE tests SET context_id=? WHERE test_id=?",
        (f"test:mcq_technical:session:{session_id}", test_id),
    )
    connection.commit()
    attempt_id = start_attempt(connection, test_id, "user-a")
    _, questions = public_test(connection, test_id, "user-a")
    evaluate_test(
        connection, FakeGateway(), attempt_id, "user-a",
        {questions[0]["question_id"]: "INNER JOIN"},
    )
    assert connection.execute(
        "SELECT COUNT(*) FROM attendance WHERE user_id='user-a'"
    ).fetchone()[0] == 0
    assert connection.execute(
        "SELECT context_id FROM tests WHERE test_id=?", (test_id,)
    ).fetchone()[0] == f"test:mcq_technical:session:{session_id}"


def test_independent_test_has_null_session(connection):
    test_id = make_test(connection)
    assert connection.execute("SELECT session_id FROM tests WHERE test_id=?", (test_id,)).fetchone()[0] is None


def test_attempt_id_generation_and_start(connection):
    test_id = make_test(connection)
    attempt_id = start_attempt(connection, test_id, "user-a")
    assert attempt_id
    assert connection.execute("SELECT status FROM test_attempts").fetchone()[0] == "In Progress"


def test_public_view_hides_answer_key(connection):
    test_id = make_test(connection)
    _, questions = public_test(connection, test_id, "user-a")
    assert "correct_answer" not in questions[0]


def test_attempt_answer_evaluation_mcq_and_multiple_select(connection):
    test_id = make_test(connection)
    attempt_id = start_attempt(connection, test_id, "user-a")
    _, questions = public_test(connection, test_id, "user-a")
    answers = {
        questions[0]["question_id"]: "INNER JOIN",
        questions[1]["question_id"]: ["Review cardinality", "Use keys"],
        questions[2]["question_id"]: "wrong",
    }
    result = evaluate_test(connection, FakeGateway(), attempt_id, "user-a", answers)
    assert result["score"] == 5
    assert result["percentage"] == 100


def test_open_answer_uses_ai_evaluation(connection):
    test_id = make_test(connection)
    attempt_id = start_attempt(connection, test_id, "user-a")
    _, questions = public_test(connection, test_id, "user-a")
    result = evaluate_test(
        connection, FakeGateway(evaluation={"correct": True, "points_awarded": 2, "feedback": "Clear."}),
        attempt_id, "user-a",
        {q["question_id"]: "A thoughtful answer" for q in questions},
    )
    assert result["score"] == 2


def test_submission_persists_result(connection):
    test_id = make_test(connection)
    attempt_id = start_attempt(connection, test_id, "user-a")
    _, questions = public_test(connection, test_id, "user-a")
    evaluate_test(connection, FakeGateway(), attempt_id, "user-a", {})
    attempt, _ = get_result(connection, attempt_id, "user-a")
    assert attempt["status"] == "Evaluated"
    assert attempt["percentage"] == 0


def test_duplicate_submission_prevented(connection):
    test_id = make_test(connection)
    attempt_id = start_attempt(connection, test_id, "user-a")
    evaluate_test(connection, FakeGateway(), attempt_id, "user-a", {})
    with pytest.raises(ValueError, match="already"):
        evaluate_test(connection, FakeGateway(), attempt_id, "user-a", {})


def test_score_and_percentage_calculation(connection):
    test_id = make_test(connection)
    attempt_id = start_attempt(connection, test_id, "user-a")
    _, questions = public_test(connection, test_id, "user-a")
    result = evaluate_test(connection, FakeGateway(), attempt_id, "user-a", {
        questions[0]["question_id"]: "INNER JOIN",
    })
    assert result["score"] == 1
    assert result["percentage"] == 20


def test_feedback_and_explanation_persist(connection):
    test_id = make_test(connection)
    attempt_id = start_attempt(connection, test_id, "user-a")
    evaluate_test(connection, FakeGateway(), attempt_id, "user-a", {})
    answer = connection.execute("SELECT * FROM test_answers LIMIT 1").fetchone()
    assert answer["feedback"]
    assert answer["explanation"]


def test_weak_area_extraction(connection):
    test_id = make_test(connection)
    attempt_id = start_attempt(connection, test_id, "user-a")
    result = evaluate_test(connection, FakeGateway(), attempt_id, "user-a", {})
    assert "INNER JOIN" in result["weak_areas"]


def test_history_retrieval(connection):
    test_id = make_test(connection)
    start_attempt(connection, test_id, "user-a")
    from database.repositories.test_repository import list_attempts
    assert len(list_attempts(connection, "user-a")) == 1


def test_retake_creates_separate_attempt(connection):
    test_id = make_test(connection)
    first = start_attempt(connection, test_id, "user-a")
    evaluate_test(connection, FakeGateway(), first, "user-a", {})
    second = start_attempt(connection, test_id, "user-a")
    assert first != second
    assert connection.execute("SELECT COUNT(*) FROM test_attempts").fetchone()[0] == 2


def test_timer_behavior():
    now = datetime.now(timezone.utc)
    attempt = {"started_at": (now - timedelta(minutes=21)).isoformat(), "duration_minutes": 20}
    assert attempt_expired(attempt, now)


def test_non_timed_attempt_not_expired():
    assert not attempt_expired({"started_at": datetime.now(timezone.utc).isoformat(), "duration_minutes": None})


def test_future_progress_event_boundary(connection):
    test_id = make_test(connection)
    attempt_id = start_attempt(connection, test_id, "user-a")
    evaluate_test(connection, FakeGateway(), attempt_id, "user-a", {})
    attempt, _ = get_result(connection, attempt_id, "user-a")
    event = completed_test_event(attempt, {"score": 0, "percentage": 0, "weak_areas": ["Joins"]})
    assert event["event"] == "TestCompleted"
    assert event["attempt_id"] == attempt_id


def test_session_id_does_not_create_attendance(connection):
    module_id = add_module(connection, "SQL", "", "user-a")
    connection.execute(
        """INSERT INTO sessions
        (module_id,day_number,session_date,category,topic,scheduled_time,prompt,
         status,owner_user_id,created_at,updated_at)
        VALUES (?,1,'2026-09-13','Daily Test','Joins','7:00 PM','test',
        'Scheduled','user-a','now','now')""", (module_id,)
    )
    connection.commit()
    session_id = connection.execute("SELECT last_insert_rowid()").fetchone()[0]
    test_id = make_test(connection, "user-a", module_id, session_id)
    start_attempt(connection, test_id, "user-a")
    assert connection.execute("SELECT COUNT(*) FROM attendance").fetchone()[0] == 0


def test_notes_schema_remains_available(connection):
    assert connection.execute("SELECT name FROM sqlite_master WHERE name='learning_notes'").fetchone()


def test_evaluation_failure_is_explicit(connection):
    test_id = make_test(connection)
    attempt_id = start_attempt(connection, test_id, "user-a")
    _, questions = public_test(connection, test_id, "user-a")
    class Failing(FakeGateway):
        def evaluate_test_answer(self, prompt):
            raise RuntimeError("down")
    with pytest.raises(AIProviderError):
        evaluate_test(connection, Failing(), attempt_id, "user-a", {
            questions[2]["question_id"]: "answer"
        })


def test_no_duplicate_evaluation_after_success(connection):
    test_id = make_test(connection)
    attempt_id = start_attempt(connection, test_id, "user-a")
    gateway = FakeGateway()
    _, questions = public_test(connection, test_id, "user-a")
    evaluate_test(connection, gateway, attempt_id, "user-a", {
        questions[2]["question_id"]: "answer"
    })
    assert gateway.evaluate_calls == 1
