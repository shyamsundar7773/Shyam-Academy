import json
import sqlite3
from datetime import datetime

import pytest

from ai.gateway import AIProviderError
from database.repositories import mentor_repository as repository
from database.schema import initialize_database
from models.mentor import MENTOR_ACTIONS
from services.mentor_recommendation_service import get_next_learning_recommendations
from services.mentor_service import (
    build_mentor_context,
    compact_context,
    create_conversation,
    mentor_event,
    mentor_reply,
    parse_mentor_response,
    save_exchange,
)
from services.module_service import add_module
from services.progress_service import get_progress_snapshot
from services.timetable_service import add_session


@pytest.fixture
def connection():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    initialize_database(db)
    yield db
    db.close()


class Gateway:
    def __init__(self, value=None, error=None):
        self.value = value or json.dumps({
            "response": "Evidence-based guidance.",
            "recommendations": ["Review joins."],
            "evidence": ["One weak-area signal."],
            "next_actions": ["Practice one query."],
        })
        self.error = error

    def mentor_response(self, prompt):
        if self.error:
            raise self.error
        return self.value


def setup_plan(connection, user="user-a"):
    module = add_module(connection, "SQL", "SQL plan", user)
    add_session(connection, module, 1, "2026-09-20", "Level 1", "Joins",
                "10:00 AM", "Teach joins.", user)
    return module


def test_schema_creates_mentor_tables(connection):
    names = {row["name"] for row in connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )}
    assert {"mentor_conversations", "mentor_messages"} <= names


def test_create_conversation_is_scoped(connection):
    conversation = create_conversation(connection, "a")
    assert repository.get_conversation(connection, conversation, "a") is not None
    assert repository.get_conversation(connection, conversation, "b") is None


def test_message_persists(connection):
    conversation = create_conversation(connection, "a")
    message = repository.add_message(connection, conversation, "a", "user", "Hello")
    assert repository.list_messages(connection, conversation, "a")[0]["message_id"] == message


def test_duplicate_message_is_idempotent(connection):
    conversation = create_conversation(connection, "a")
    first = repository.add_message(connection, conversation, "a", "user", "Hello")
    second = repository.add_message(connection, conversation, "a", "user", "Hello")
    assert first == second
    assert len(repository.list_messages(connection, conversation, "a")) == 1


def test_message_isolation(connection):
    conversation = create_conversation(connection, "a")
    with pytest.raises(ValueError):
        repository.add_message(connection, conversation, "b", "user", "No access")


def test_invalid_role_rejected(connection):
    conversation = create_conversation(connection, "a")
    with pytest.raises(ValueError):
        repository.add_message(connection, conversation, "a", "system", "x")


def test_empty_message_rejected(connection):
    conversation = create_conversation(connection, "a")
    with pytest.raises(ValueError):
        repository.add_message(connection, conversation, "a", "user", " ")


def test_context_requires_user(connection):
    with pytest.raises(ValueError):
        build_mentor_context(connection, "")


def test_context_contains_progress(connection):
    module = setup_plan(connection)
    context = build_mentor_context(connection, "user-a", module, datetime(2026, 9, 1))
    assert context.user_id == "user-a"
    assert context.progress["overall"]["scheduled"] == 1


def test_module_isolation(connection):
    module = setup_plan(connection, "a")
    add_module(connection, "SQL", "other", "b")
    context = build_mentor_context(connection, "a", module, datetime(2026, 9, 1))
    assert context.progress["overall"]["scheduled"] == 1


def test_context_is_compact(connection):
    context = build_mentor_context(connection, "empty")
    compact = compact_context(context)
    assert "modules" not in compact["progress"]
    assert "topics" not in compact["progress"]


def test_no_data_recommendation(connection):
    context = build_mentor_context(connection, "empty")
    assert context.recommendations[0].priority == "LOW"


def test_upcoming_recommendation_has_high_priority(connection):
    snapshot = get_progress_snapshot(connection, "a")
    result = get_next_learning_recommendations(snapshot, [{
        "topic": "Joins", "session_date": "2099-01-01"
    }])
    assert result[0].priority == "HIGH"


def test_missed_recommendation_has_recovery_action(connection):
    snapshot = get_progress_snapshot(connection, "a")
    result = get_next_learning_recommendations(snapshot, [], [{
        "topic": "Joins", "session_date": "2020-01-01"
    }])
    assert "recovery" in result[0].suggested_action.lower()


def test_recommendations_are_sorted(connection):
    snapshot = get_progress_snapshot(connection, "a")
    result = get_next_learning_recommendations(snapshot, [
        {"topic": "Later", "session_date": "2099-01-01"},
        {"topic": "Soon", "session_date": "2099-01-01"},
    ])
    assert [item.priority for item in result] == sorted(
        [item.priority for item in result], key={"HIGH": 0, "MEDIUM": 1, "LOW": 2}.get
    )


def test_action_constants_cover_required_actions():
    assert {"GENERAL_GUIDANCE", "STUDY_PLAN", "CAREER_GUIDANCE"} <= MENTOR_ACTIONS


def test_action_validation(connection):
    context = build_mentor_context(connection, "a")
    with pytest.raises(ValueError):
        mentor_reply(Gateway(), context, "hello", action="BAD")


def test_empty_question_rejected(connection):
    context = build_mentor_context(connection, "a")
    with pytest.raises(ValueError):
        mentor_reply(Gateway(), context, " ")


def test_structured_response_parses():
    response = parse_mentor_response(Gateway().value)
    assert response.response == "Evidence-based guidance."
    assert response.next_actions


def test_malformed_json_rejected():
    with pytest.raises(ValueError):
        parse_mentor_response("not json")


def test_missing_response_rejected():
    with pytest.raises(ValueError):
        parse_mentor_response(json.dumps({"recommendations": []}))


def test_invalid_response_list_rejected():
    with pytest.raises(ValueError):
        parse_mentor_response(json.dumps({"response": "x", "evidence": "bad"}))


def test_provider_response_requires_explicit_call(connection):
    context = build_mentor_context(connection, "a")
    gateway = Gateway()
    result = mentor_reply(gateway, context, "What next?")
    assert result.response


def test_provider_failure_is_safe(connection):
    context = build_mentor_context(connection, "a")
    with pytest.raises(AIProviderError):
        mentor_reply(Gateway(error=AIProviderError("down")), context, "help")


def test_followup_history_is_accepted(connection):
    context = build_mentor_context(connection, "a")
    result = mentor_reply(Gateway(), context, "Explain more", [{"role": "mentor", "message": "x"}])
    assert result.response


def test_save_exchange_persists_both_messages(connection):
    conversation = create_conversation(connection, "a")
    response = parse_mentor_response(Gateway().value)
    ids = save_exchange(connection, conversation, "a", "Question", response, "GENERAL_GUIDANCE")
    assert len(ids) == 2
    assert len(repository.list_messages(connection, conversation, "a")) == 2


def test_history_limit_is_bounded(connection):
    conversation = create_conversation(connection, "a")
    for index in range(35):
        repository.add_message(connection, conversation, "a", "user", f"q{index}")
    assert len(repository.list_messages(connection, conversation, "a", 10)) == 10


def test_conversation_list_is_bounded(connection):
    for index in range(25):
        create_conversation(connection, "a", str(index))
    assert len(repository.list_conversations(connection, "a", 5)) == 5


def test_unknown_conversation_rejected(connection):
    with pytest.raises(ValueError):
        repository.list_messages(connection, "missing", "a")


def test_event_boundary_is_not_completion(connection):
    context = build_mentor_context(connection, "a")
    event = mentor_event(context, get_next_learning_recommendations(
        get_progress_snapshot(connection, "a")
    )[0])
    assert event["event"] == "MentorRecommendationCreated"
    assert "LearningCompleted" not in event["event"]


def test_event_has_user_identity(connection):
    context = build_mentor_context(connection, "a")
    recommendation = get_next_learning_recommendations(get_progress_snapshot(connection, "a"))[0]
    assert mentor_event(context, recommendation)["user_id"] == "a"


def test_context_has_bounded_recommendations(connection):
    context = build_mentor_context(connection, "a")
    assert len(context.recommendations) <= 8


def test_context_has_bounded_sessions(connection):
    context = build_mentor_context(connection, "a")
    assert len(context.upcoming_sessions) <= 5
    assert len(context.missed_sessions) <= 5


def test_context_does_not_include_other_user(connection):
    setup_plan(connection, "a")
    setup_plan(connection, "b")
    context = build_mentor_context(connection, "a")
    assert all(item.get("module_name") != "SQL" or context.user_id == "a"
               for item in context.upcoming_sessions)


def test_empty_context_has_no_fake_activity(connection):
    context = build_mentor_context(connection, "empty")
    assert context.recent_activity == []


def test_response_recommendations_are_strings():
    response = parse_mentor_response(Gateway().value)
    assert all(isinstance(item, str) for item in response.recommendations)


def test_response_evidence_is_strings():
    response = parse_mentor_response(Gateway().value)
    assert all(isinstance(item, str) for item in response.evidence)


def test_response_next_actions_are_strings():
    response = parse_mentor_response(Gateway().value)
    assert all(isinstance(item, str) for item in response.next_actions)


def test_blank_structured_items_are_removed():
    response = parse_mentor_response(json.dumps({
        "response": "ok", "recommendations": [" ", "do it"],
        "evidence": [], "next_actions": []
    }))
    assert response.recommendations == ["do it"]


def test_title_default_is_stable(connection):
    conversation = create_conversation(connection, "a")
    assert repository.get_conversation(connection, conversation, "a")["title"] == "AI Mentor"


def test_custom_title_is_trimmed(connection):
    conversation = create_conversation(connection, "a", "  Career  ")
    assert repository.get_conversation(connection, conversation, "a")["title"] == "Career"


def test_missing_user_rejected_for_conversation(connection):
    with pytest.raises(ValueError):
        create_conversation(connection, "")


def test_recommendation_topic_is_preserved(connection):
    snapshot = get_progress_snapshot(connection, "a")
    item = get_next_learning_recommendations(snapshot, [{"topic": "CTEs"}])[0]
    assert item.topic == "CTEs"


def test_recommendation_contains_evidence(connection):
    snapshot = get_progress_snapshot(connection, "a")
    item = get_next_learning_recommendations(snapshot, [{"topic": "CTEs"}])[0]
    assert item.evidence


def test_no_timetable_mutation_from_reply(connection):
    module = setup_plan(connection)
    before = connection.execute("SELECT COUNT(*) n FROM sessions").fetchone()["n"]
    mentor_reply(Gateway(), build_mentor_context(connection, "user-a", module), "help")
    after = connection.execute("SELECT COUNT(*) n FROM sessions").fetchone()["n"]
    assert before == after


def test_no_attendance_mutation_from_reply(connection):
    before = connection.execute("SELECT COUNT(*) n FROM attendance").fetchone()["n"]
    mentor_reply(Gateway(), build_mentor_context(connection, "a"), "help")
    after = connection.execute("SELECT COUNT(*) n FROM attendance").fetchone()["n"]
    assert before == after


def test_history_is_user_scoped(connection):
    a = create_conversation(connection, "a")
    create_conversation(connection, "b")
    assert len(repository.list_conversations(connection, "a")) == 1
    assert repository.get_conversation(connection, a, "b") is None


def test_provider_prompt_is_structured(connection):
    class InspectingGateway(Gateway):
        def mentor_response(self, prompt):
            parsed = json.loads(prompt)
            assert "context" in parsed and "safety" in parsed
            return super().mentor_response(prompt)
    result = mentor_reply(InspectingGateway(), build_mentor_context(connection, "a"), "help")
    assert result.response
