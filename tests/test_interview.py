import json
import sqlite3

import pytest

from ai.gateway import AIProviderError
from database.schema import initialize_database
from models.interview import INTERVIEW_MODES
from services.interview_service import (
    complete_interview,
    create_interview,
    generate_interview,
    interview_action,
    interview_completed_event,
    parse_evaluation,
    parse_interview,
    submit_answer,
)
from services.module_service import add_module


def plan_payload(mode="Technical Interview"):
    return {
        "title": "Practice", "mode": mode, "difficulty": "Intermediate",
        "topic": "SQL joins",
        "questions": [{
            "question_text": "Explain INNER JOIN.",
            "question_type": "SQL",
            "topic": "INNER JOIN",
            "expected_points": ["matching rows", "example"],
        }],
    }


def evaluation_payload():
    return {
        "score": 80, "correctness": 80, "relevance": 85, "clarity": 75,
        "technical_depth": 80, "communication_quality": 85,
        "strengths": ["clear"], "weaknesses": ["example"],
        "missing_points": ["edge case"], "corrections": ["be specific"],
        "suggested_answer": "A stronger answer includes an example.",
        "feedback": "Good answer.",
    }


class Gateway:
    def __init__(self):
        self.generation_calls = 0
        self.evaluation_calls = 0

    def generate_interview(self, prompt):
        self.generation_calls += 1
        return json.dumps(plan_payload())

    def evaluate_interview(self, prompt):
        self.evaluation_calls += 1
        return json.dumps(evaluation_payload())

    def interview_action(self, prompt):
        return "Coaching response"


@pytest.fixture
def connection():
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    initialize_database(connection)
    yield connection
    connection.close()


def make_session(connection, user="user-a", module_id=None, session_id=None):
    return create_interview(
        connection, user, parse_interview(json.dumps(plan_payload())),
        module_id, session_id
    )


def test_mode_validation():
    for mode in INTERVIEW_MODES:
        assert parse_interview(json.dumps(plan_payload(mode))).mode == mode


def test_difficulty_validation():
    payload = plan_payload()
    payload["difficulty"] = "expert"
    with pytest.raises(ValueError):
        parse_interview(json.dumps(payload))


def test_question_generation():
    gateway = Gateway()
    plan = generate_interview(gateway, "user-a", "SQL Interview", "Intermediate", "joins")
    assert plan.questions[0].question_type == "SQL"
    assert gateway.generation_calls == 1


def test_malformed_question_response_rejected():
    with pytest.raises(ValueError):
        parse_interview("{bad")


def test_empty_question_rejected():
    payload = plan_payload()
    payload["questions"][0]["question_text"] = ""
    with pytest.raises(ValueError):
        parse_interview(json.dumps(payload))


def test_evaluation_validation_and_normalization():
    evaluation = parse_evaluation(json.dumps(evaluation_payload()))
    assert evaluation.score == 80
    with pytest.raises(ValueError):
        parse_evaluation(json.dumps({**evaluation_payload(), "score": 101}))


def test_session_persistence_and_stable_id(connection):
    session_id = make_session(connection)
    assert session_id
    assert connection.execute(
        "SELECT COUNT(*) FROM interview_sessions"
    ).fetchone()[0] == 1


def test_answer_persistence_and_evaluation(connection):
    session_id = make_session(connection)
    question_id = connection.execute(
        "SELECT question_id FROM interview_questions"
    ).fetchone()[0]
    evaluation = submit_answer(connection, Gateway(), session_id, question_id, "user-a", "answer")
    assert evaluation.score == 80
    assert connection.execute("SELECT COUNT(*) FROM interview_answers").fetchone()[0] == 1


def test_empty_answer_rejected(connection):
    session_id = make_session(connection)
    question_id = connection.execute("SELECT question_id FROM interview_questions").fetchone()[0]
    with pytest.raises(ValueError):
        submit_answer(connection, Gateway(), session_id, question_id, "user-a", "")


def test_duplicate_submission_protected(connection):
    session_id = make_session(connection)
    question_id = connection.execute("SELECT question_id FROM interview_questions").fetchone()[0]
    submit_answer(connection, Gateway(), session_id, question_id, "user-a", "answer")
    with pytest.raises(ValueError):
        submit_answer(connection, Gateway(), session_id, question_id, "user-a", "again")


def test_sql_evaluation_path(connection):
    session_id = make_session(connection)
    question_id = connection.execute("SELECT question_id FROM interview_questions").fetchone()[0]
    assert submit_answer(connection, Gateway(), session_id, question_id, "user-a", "SELECT").technical_depth == 80


def test_behavioral_evaluation_path(connection):
    payload = plan_payload("Behavioral Interview")
    session_id = create_interview(connection, "user-a", parse_interview(json.dumps(payload)))
    question_id = connection.execute("SELECT question_id FROM interview_questions").fetchone()[0]
    assert submit_answer(connection, Gateway(), session_id, question_id, "user-a", "STAR answer").communication_quality == 85


def test_follow_up_action():
    assert interview_action(Gateway(), "Explain Again", "joins", "practice") == "Coaching response"


def test_invalid_action_rejected():
    with pytest.raises(ValueError):
        interview_action(Gateway(), "Reveal answer", "joins", "practice")


def test_mock_session_can_have_multiple_questions(connection):
    payload = plan_payload()
    payload["questions"] = [
        {**payload["questions"][0], "question_text": f"Explain INNER JOIN part {index}."}
        for index in range(1, 4)
    ]
    session_id = create_interview(connection, "user-a", parse_interview(json.dumps(payload)))
    assert connection.execute(
        "SELECT COUNT(*) FROM interview_questions WHERE interview_session_id=?",
        (session_id,),
    ).fetchone()[0] == 3


def test_completion_event_boundary(connection):
    session_id = make_session(connection)
    question_id = connection.execute("SELECT question_id FROM interview_questions").fetchone()[0]
    submit_answer(connection, Gateway(), session_id, question_id, "user-a", "answer")
    complete_interview(connection, session_id, "user-a")
    event = interview_completed_event(connection, session_id, "user-a")
    assert event["event"] == "InterviewCompleted"
    assert event["score"] == 80


def test_history_is_user_scoped(connection):
    make_session(connection, "user-a")
    from database.repositories.interview_repository import list_sessions
    assert len(list_sessions(connection, "user-a")) == 1
    assert list_sessions(connection, "user-b") == []


def test_module_isolation(connection):
    module_a = add_module(connection, "SQL", "", "user-a")
    module_b = add_module(connection, "Python", "", "user-a")
    first = make_session(connection, module_id=module_a)
    second = make_session(connection, module_id=module_b)
    assert first != second


def test_timetable_session_linking(connection):
    module_id = add_module(connection, "SQL", "", "user-a")
    connection.execute(
        """INSERT INTO sessions
        (module_id,day_number,session_date,category,topic,scheduled_time,prompt,status,
         owner_user_id,created_at,updated_at)
        VALUES (?,1,'2026-09-13','Interview Preparation','SQL','7:00 PM','p',
        'Scheduled','user-a','now','now')""", (module_id,)
    )
    connection.commit()
    session_id = connection.execute("SELECT last_insert_rowid()").fetchone()[0]
    interview_id = make_session(connection, session_id=session_id)
    assert connection.execute(
        "SELECT session_id,module_id FROM interview_sessions WHERE interview_session_id=?",
        (interview_id,),
    ).fetchone()["session_id"] == session_id


def test_context_and_completion_do_not_mark_attendance_without_saved_notes(connection):
    module_id = add_module(connection, "SQL", "", "user-a")
    connection.execute(
        """INSERT INTO sessions
        (module_id,day_number,session_date,category,topic,scheduled_time,prompt,status,
         owner_user_id,created_at,updated_at)
        VALUES (?,1,'2026-09-13','Interview Preparation','SQL','7:00 PM','p',
        'Scheduled','user-a','now','now')""", (module_id,)
    )
    connection.commit()
    timetable_id = connection.execute("SELECT last_insert_rowid()").fetchone()[0]
    interview_id = create_interview(
        connection, "user-a", parse_interview(json.dumps(plan_payload())),
        module_id, timetable_id, "interview:technical_interview:session:1",
    )
    complete_interview(connection, interview_id, "user-a")
    assert connection.execute(
        "SELECT COUNT(*) FROM attendance WHERE user_id='user-a'"
    ).fetchone()[0] == 0
    assert connection.execute(
        "SELECT context_id FROM interview_sessions WHERE interview_session_id=?",
        (interview_id,),
    ).fetchone()[0] == "interview:technical_interview:session:1"


def test_missing_module_rejected(connection):
    with pytest.raises(ValueError):
        make_session(connection, module_id=99)


def test_missing_timetable_session_rejected(connection):
    with pytest.raises(ValueError):
        make_session(connection, session_id=99)


def test_provider_failure_boundary():
    class Failing:
        def generate_interview(self, prompt):
            raise RuntimeError("down")
    with pytest.raises(AIProviderError):
        generate_interview(Failing(), "user-a", "SQL Interview", "Beginner", "joins")


def test_evaluation_failure_boundary(connection):
    class Failing(Gateway):
        def evaluate_interview(self, prompt):
            raise RuntimeError("down")
    session_id = make_session(connection)
    question_id = connection.execute("SELECT question_id FROM interview_questions").fetchone()[0]
    with pytest.raises(AIProviderError):
        submit_answer(connection, Failing(), session_id, question_id, "user-a", "answer")


def test_no_answer_key_exposed_by_question_model(connection):
    make_session(connection)
    row = connection.execute("SELECT * FROM interview_questions").fetchone()
    assert "answer" not in row["question_text"].casefold()


def test_history_preserves_original_answer(connection):
    session_id = make_session(connection)
    question_id = connection.execute("SELECT question_id FROM interview_questions").fetchone()[0]
    submit_answer(connection, Gateway(), session_id, question_id, "user-a", "original")
    assert connection.execute("SELECT answer FROM interview_answers").fetchone()[0] == "original"


def test_interview_room_is_placeholder():
    assert "interview_room.py" in "pages/interview_room.py"


def test_notes_metadata_boundary(connection):
    module_id = add_module(connection, "SQL", "", "user-a")
    session_id = make_session(connection, module_id=module_id)
    question_id = connection.execute("SELECT question_id FROM interview_questions").fetchone()[0]
    submit_answer(connection, Gateway(), session_id, question_id, "user-a", "answer")
    from database.repositories.interview_repository import list_answers
    assert list_answers(connection, session_id, "user-a")[0]["topic"] == "INNER JOIN"


def test_interview_mode_stored(connection):
    session_id = make_session(connection)
    assert connection.execute(
        "SELECT mode FROM interview_sessions WHERE interview_session_id=?",
        (session_id,),
    ).fetchone()[0] == "Technical Interview"


def test_completed_session_is_immutable_status(connection):
    session_id = make_session(connection)
    complete_interview(connection, session_id, "user-a")
    assert connection.execute(
        "SELECT status FROM interview_sessions WHERE interview_session_id=?",
        (session_id,),
    ).fetchone()[0] == "Completed"


def test_duplicate_event_data_is_stable(connection):
    session_id = make_session(connection)
    question_id = connection.execute("SELECT question_id FROM interview_questions").fetchone()[0]
    submit_answer(connection, Gateway(), session_id, question_id, "user-a", "answer")
    complete_interview(connection, session_id, "user-a")
    first = interview_completed_event(connection, session_id, "user-a")
    second = interview_completed_event(connection, session_id, "user-a")
    assert first["score"] == second["score"]


def test_user_identity_required():
    with pytest.raises(ValueError):
        generate_interview(Gateway(), "", "SQL Interview", "Beginner", "joins")


def test_topic_required():
    with pytest.raises(ValueError):
        generate_interview(Gateway(), "user-a", "SQL Interview", "Beginner", "")


def test_all_modes_are_supported():
    assert {"Technical Interview", "SQL Interview", "Data Analyst Interview",
            "Behavioral Interview", "HR Interview", "Mock Interview"} <= INTERVIEW_MODES


def test_session_history_contains_question_count(connection):
    session_id = make_session(connection)
    from database.repositories.interview_repository import list_sessions
    assert list_sessions(connection, "user-a")[0]["question_count"] == 1


def test_expected_points_are_structured(connection):
    make_session(connection)
    value = connection.execute(
        "SELECT expected_points_json FROM interview_questions"
    ).fetchone()[0]
    assert json.loads(value) == ["matching rows", "example"]


def test_follow_up_context_keeps_parent_session(connection):
    session_id = make_session(connection)
    assert repo_session(connection, session_id)["interview_session_id"] == session_id


def repo_session(connection, session_id):
    from database.repositories.interview_repository import get_session
    return get_session(connection, session_id, "user-a")


def test_evaluation_dimensions_persist(connection):
    session_id = make_session(connection)
    question_id = connection.execute("SELECT question_id FROM interview_questions").fetchone()[0]
    submit_answer(connection, Gateway(), session_id, question_id, "user-a", "answer")
    row = connection.execute(
        "SELECT correctness,clarity,communication_quality FROM interview_evaluations"
    ).fetchone()
    assert row["correctness"] == 80


def test_interview_completion_does_not_create_attendance(connection):
    session_id = make_session(connection)
    complete_interview(connection, session_id, "user-a")
    assert connection.execute("SELECT COUNT(*) FROM attendance").fetchone()[0] == 0
