import json
import sqlite3
from datetime import date, datetime, timedelta

import pytest

from auth.firebase import mask_secret
from config.provider_config import get_provider_configuration
from database.schema import initialize_database
from services.attendance_service import mark_attended
from services.module_service import add_module
from services.progress_service import get_progress_snapshot
from services.test_service import create_test, evaluate_test, parse_test, start_attempt
from services.timetable_service import add_session


def make_test_payload(topic="Joins", percentage=80):
    return {
        "title": "Progress test", "description": "test", "category": "Daily Test",
        "topic": topic, "difficulty": "Intermediate", "duration_minutes": 10,
        "questions": [{
            "order_index": 1, "question_type": "mcq", "question_text": f"{topic} question",
            "options": ["correct", "wrong"], "correct_answer": "correct",
            "explanation": "Because it is correct.", "points": 1, "weak_area": topic,
        }],
    }


@pytest.fixture
def connection():
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    initialize_database(connection)
    yield connection
    connection.close()


def add_module_with_sessions(connection, user="user-a", name="SQL", count=3):
    module_id = add_module(connection, name, "description", user)
    ids = []
    for index in range(count):
        ids.append(add_session(
            connection, module_id, index + 1, f"2026-09-{10 + index:02d}",
            "Level 1" if index < 2 else "Problem Solving",
            "Joins" if index < 2 else "CTEs", "10:00 AM",
            "Teach this topic.", user,
        ))
    return module_id, ids


def snapshot(connection, user="user-a", **kwargs):
    return get_progress_snapshot(
        connection, user, now=datetime(2026, 9, 20, 12, 0), **kwargs
    )


def add_evaluated_test(connection, user="user-a", module_id=None, topic="Joins", score=True):
    plan = parse_test(json.dumps(make_test_payload(topic)))
    test_id = create_test(connection, user, plan, module_id)
    attempt_id = start_attempt(connection, test_id, user)
    question_id = connection.execute(
        "SELECT question_id FROM test_questions WHERE test_id=?", (test_id,)
    ).fetchone()[0]
    evaluate_test(connection, type("Gateway", (), {})(), attempt_id, user, {
        question_id: "correct" if score else "wrong"
    })
    return test_id, attempt_id


class NoAi:
    def evaluate_test_answer(self, prompt):
        raise AssertionError("MCQ evaluation should remain deterministic")


def test_empty_progress_state(connection):
    result = snapshot(connection)
    assert result.overall.scheduled == 0
    assert result.modules == []


def test_progress_model_defaults():
    from models.progress import ProgressMetrics
    assert ProgressMetrics().completion_percentage == 0


def test_scheduled_count(connection):
    add_module_with_sessions(connection)
    assert snapshot(connection).overall.scheduled == 3


def test_completed_count_from_attendance(connection):
    _, sessions = add_module_with_sessions(connection)
    mark_attended(connection, "user-a", sessions[0])
    assert snapshot(connection).overall.completed == 1


def test_missed_count_from_attendance(connection):
    module, sessions = add_module_with_sessions(connection)
    connection.execute(
        "INSERT INTO attendance (user_id,module_id,session_id,status,scheduled_date,scheduled_time,created_at,updated_at) "
        "VALUES (?,?,?,'Missed','2026-09-11','10:00 AM','now','now')",
        ("user-a", module, sessions[0]),
    )
    connection.commit()
    assert snapshot(connection).overall.missed == 3


def test_upcoming_count(connection):
    module_id = add_module(connection, "Future", "", "user-a")
    add_session(connection, module_id, 1, "2026-09-30", "Level 1", "Future", "10:00 AM", "p", "user-a")
    assert snapshot(connection).overall.upcoming == 1


def test_completion_percentage(connection):
    _, sessions = add_module_with_sessions(connection)
    mark_attended(connection, "user-a", sessions[0])
    assert snapshot(connection).overall.completion_percentage == 33.3


def test_user_isolation(connection):
    add_module_with_sessions(connection, "user-a")
    add_module_with_sessions(connection, "user-b", "Other")
    assert snapshot(connection, "user-a").overall.scheduled == 3


def test_module_isolation(connection):
    module_a, sessions = add_module_with_sessions(connection)
    module_b, _ = add_module_with_sessions(connection, "user-a", "Python")
    mark_attended(connection, "user-a", sessions[0])
    result = snapshot(connection, module_id=module_b)
    assert result.overall.completed == 0


def test_module_progress(connection):
    module_id, sessions = add_module_with_sessions(connection)
    mark_attended(connection, "user-a", sessions[0])
    module = snapshot(connection).modules[0]
    assert module.module_id == module_id
    assert module.metrics.completed == 1


def test_category_progress(connection):
    add_module_with_sessions(connection)
    result = snapshot(connection)
    level = next(item for item in result.categories if item.category == "Level 1")
    assert level.metrics.scheduled == 2


def test_topic_progress(connection):
    add_module_with_sessions(connection)
    topics = {item.topic: item for item in snapshot(connection).topics}
    assert topics["Joins"].metrics.scheduled == 2


def test_test_result_integration(connection):
    module_id, _ = add_module_with_sessions(connection)
    add_evaluated_test(connection, module_id=module_id)
    assert snapshot(connection).test_performance.count == 1


def test_multiple_attempts_preserved(connection):
    module_id, _ = add_module_with_sessions(connection)
    add_evaluated_test(connection, module_id=module_id)
    add_evaluated_test(connection, module_id=module_id)
    assert snapshot(connection).test_performance.count == 2


def test_best_score(connection):
    module_id, _ = add_module_with_sessions(connection)
    add_evaluated_test(connection, module_id=module_id)
    add_evaluated_test(connection, module_id=module_id)
    assert snapshot(connection).test_performance.best_score == 100


def test_latest_score(connection):
    module_id, _ = add_module_with_sessions(connection)
    add_evaluated_test(connection, module_id=module_id, score=False)
    add_evaluated_test(connection, module_id=module_id, score=True)
    assert snapshot(connection).test_performance.latest_score == 100


def test_average_score(connection):
    module_id, _ = add_module_with_sessions(connection)
    add_evaluated_test(connection, module_id=module_id, score=True)
    add_evaluated_test(connection, module_id=module_id, score=False)
    assert snapshot(connection).test_performance.average_score == 50


def test_weak_area_aggregation(connection):
    module_id, _ = add_module_with_sessions(connection)
    add_evaluated_test(connection, module_id=module_id, score=False)
    add_evaluated_test(connection, module_id=module_id, score=False)
    assert snapshot(connection).weak_areas[0].signals == 2


def test_weak_area_severity(connection):
    module_id, _ = add_module_with_sessions(connection)
    for _ in range(3):
        add_evaluated_test(connection, module_id=module_id, score=False)
    assert snapshot(connection).weak_areas[0].severity == "High"


def test_mastery_is_conservative_with_one_test(connection):
    module_id, sessions = add_module_with_sessions(connection)
    mark_attended(connection, "user-a", sessions[0])
    add_evaluated_test(connection, module_id=module_id)
    topic = next(item for item in snapshot(connection).topics if item.topic == "Joins")
    assert topic.mastery_score < 60


def test_mastery_requires_repeated_evidence(connection):
    module_id, sessions = add_module_with_sessions(connection)
    mark_attended(connection, "user-a", sessions[0])
    mark_attended(connection, "user-a", sessions[1])
    add_evaluated_test(connection, module_id=module_id)
    add_evaluated_test(connection, module_id=module_id)
    topic = next(item for item in snapshot(connection).topics if item.topic == "Joins")
    assert topic.mastery_score >= 80


def test_recent_activity_ordering(connection):
    _, sessions = add_module_with_sessions(connection)
    mark_attended(connection, "user-a", sessions[0])
    activity = snapshot(connection).recent_activity
    assert activity[0]["type"] == "Learning completed"


def test_note_activity(connection):
    module_id, _ = add_module_with_sessions(connection)
    connection.execute(
        "INSERT INTO learning_notes (user_id,module_id,category,topic,title,content,learning_number,saved_at,updated_at) "
        "VALUES ('user-a',?,?,?,'title','content',1,'2026-09-19T10:00:00+00:00','2026-09-19T10:00:00+00:00')",
        (module_id, "Level 1", "Joins"),
    )
    connection.commit()
    assert any(item["type"] == "Note saved" for item in snapshot(connection).recent_activity)


def test_active_learning_days(connection):
    _, sessions = add_module_with_sessions(connection)
    mark_attended(connection, "user-a", sessions[0])
    assert snapshot(connection).active_learning_days == 1


def test_current_streak(connection):
    module_id = add_module(connection, "Streak", "", "user-a")
    for index, day in enumerate(["2026-09-18", "2026-09-19", "2026-09-20"], 1):
        session = add_session(connection, module_id, index, day, "Level 1", f"Topic {index}",
                              "10:00 AM", "p", "user-a")
        mark_attended(connection, "user-a", session)
    assert snapshot(connection).current_streak == 3


def test_learning_velocity(connection):
    _, sessions = add_module_with_sessions(connection)
    mark_attended(connection, "user-a", sessions[0])
    assert snapshot(connection, since=date(2026, 9, 9)).learning_velocity > 0


def test_planned_vs_actual(connection):
    _, sessions = add_module_with_sessions(connection)
    mark_attended(connection, "user-a", sessions[0])
    result = snapshot(connection).overall
    assert result.scheduled == 3 and result.completed == 1 and result.missed == 2


def test_missing_timestamps_do_not_crash(connection):
    module_id = add_module(connection, "Bad", "", "user-a")
    connection.execute(
        "INSERT INTO sessions (module_id,day_number,session_date,category,topic,scheduled_time,prompt,owner_user_id,created_at,updated_at) "
        "VALUES (?,1,'bad-date','Level 1','Bad','bad','p','user-a','now','now')",
        (module_id,),
    )
    connection.commit()
    result = snapshot(connection)
    assert result.overall.scheduled == 1


def test_invalid_weak_area_json_does_not_crash(connection):
    module_id, _ = add_module_with_sessions(connection)
    connection.execute(
        "INSERT INTO tests (test_id,user_id,title,description,category,topic,difficulty,total_questions,created_at,updated_at) "
        "VALUES ('t','user-a','t','','Daily Test','Joins','Beginner',1,'now','now')"
    )
    connection.execute(
        "INSERT INTO test_attempts (attempt_id,test_id,user_id,started_at,status,percentage,weak_areas_json) "
        "VALUES ('a','t','user-a','2026-09-19T10:00:00+00:00','Evaluated',50,'bad')"
    )
    connection.commit()
    assert snapshot(connection).test_performance.count == 1


def test_module_filtered_snapshot(connection):
    module_a, _ = add_module_with_sessions(connection)
    add_module_with_sessions(connection, "user-a", "Python")
    assert len(snapshot(connection, module_id=module_a).modules) == 1


def test_category_filtered_snapshot(connection):
    add_module_with_sessions(connection)
    result = snapshot(connection, category="Problem Solving")
    assert result.overall.scheduled == 1


def test_time_period_filter(connection):
    add_module_with_sessions(connection)
    assert snapshot(connection, since=date(2026, 9, 12)).overall.scheduled == 1


def test_no_timetable_mutation(connection):
    module_id, _ = add_module_with_sessions(connection)
    before = connection.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
    get_progress_snapshot(connection, "user-a", module_id, now=datetime(2026, 9, 20))
    assert connection.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == before


def test_no_attendance_duplication(connection):
    _, sessions = add_module_with_sessions(connection)
    mark_attended(connection, "user-a", sessions[0])
    before = connection.execute("SELECT COUNT(*) FROM attendance").fetchone()[0]
    snapshot(connection)
    assert connection.execute("SELECT COUNT(*) FROM attendance").fetchone()[0] == before


def test_attempts_are_not_mutated(connection):
    module_id, _ = add_module_with_sessions(connection)
    add_evaluated_test(connection, module_id=module_id)
    before = connection.execute("SELECT COUNT(*) FROM test_attempts").fetchone()[0]
    snapshot(connection)
    assert connection.execute("SELECT COUNT(*) FROM test_attempts").fetchone()[0] == before


def test_progress_snapshot_reusable(connection):
    assert hasattr(snapshot(connection), "topics")


def test_category_names_are_canonical(connection):
    result = snapshot(connection)
    assert all(item.category in ("Today Learning", "Level 1", "Level 2", "Problem Solving",
                                 "On-time Test", "Daily Test", "Weekly Test",
                                 "Interview Preparation", "Interview Room")
               for item in result.categories)


def test_firebase_secret_masking():
    masked = mask_secret("abcdefghijkl")
    assert masked.endswith("ijkl")
    assert "abcdefgh" not in masked


def test_firebase_missing_configuration(monkeypatch):
    monkeypatch.delenv("SHYAM_ACADEMY_FIREBASE_PROJECT_ID", raising=False)
    monkeypatch.delenv("SHYAM_ACADEMY_FIREBASE_WEB_API_KEY", raising=False)
    from auth.firebase import get_firebase_configuration
    assert not get_firebase_configuration().enabled


def test_provider_configuration_defaults(monkeypatch):
    monkeypatch.delenv("SHYAM_ACADEMY_AI_API_KEY", raising=False)
    monkeypatch.setattr("config.bootstrap._dotenv_configuration", lambda: {})
    config = get_provider_configuration()
    assert config.provider == "mock"
    assert not config.credential_configured


def test_mock_provider_compatibility():
    from ai.gateway import get_gateway
    assert get_gateway().generate_timetable("Create a short SQL plan.")


def test_user_without_records_has_no_activity(connection):
    assert snapshot(connection, "user-b").recent_activity == []


def test_duplicate_completion_does_not_inflate_progress(connection):
    _, sessions = add_module_with_sessions(connection)
    mark_attended(connection, "user-a", sessions[0])
    mark_attended(connection, "user-a", sessions[0])
    assert snapshot(connection).overall.completed == 1


def test_progress_does_not_create_test_records(connection):
    before = connection.execute("SELECT COUNT(*) FROM tests").fetchone()[0]
    snapshot(connection)
    assert connection.execute("SELECT COUNT(*) FROM tests").fetchone()[0] == before


def test_progress_does_not_create_notes(connection):
    before = connection.execute("SELECT COUNT(*) FROM learning_notes").fetchone()[0]
    snapshot(connection)
    assert connection.execute("SELECT COUNT(*) FROM learning_notes").fetchone()[0] == before


def test_progress_handles_no_module_filter(connection):
    add_module_with_sessions(connection)
    assert snapshot(connection).overall.scheduled == 3


def test_progress_handles_category_with_no_rows(connection):
    result = snapshot(connection, category="Interview Room")
    assert result.overall.scheduled == 0


def test_progress_performance_missing_scores(connection):
    connection.execute(
        "INSERT INTO tests (test_id,user_id,title,description,category,topic,difficulty,total_questions,created_at,updated_at) "
        "VALUES ('t2','user-a','t','','Daily Test','Joins','Beginner',1,'now','now')"
    )
    connection.execute(
        "INSERT INTO test_attempts (attempt_id,test_id,user_id,started_at,status) "
        "VALUES ('a2','t2','user-a','2026-09-19T10:00:00+00:00','Evaluated')"
    )
    connection.commit()
    assert snapshot(connection).test_performance.count == 0


def test_progress_uses_user_scoped_tests(connection):
    connection.execute(
        "INSERT INTO tests (test_id,user_id,title,description,category,topic,difficulty,total_questions,created_at,updated_at) "
        "VALUES ('other','user-b','t','','Daily Test','Joins','Beginner',1,'now','now')"
    )
    connection.execute(
        "INSERT INTO test_attempts (attempt_id,test_id,user_id,started_at,status,percentage) "
        "VALUES ('other-a','other','user-b','2026-09-19T10:00:00+00:00','Evaluated',100)"
    )
    connection.commit()
    assert snapshot(connection).test_performance.count == 0
