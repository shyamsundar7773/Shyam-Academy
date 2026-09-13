import sqlite3

import pytest

from ai.gateway import AIProviderError, AIGateway, ClassroomContext
from database.schema import initialize_database
from services.learning_service import (
    ask_followup,
    explain_again,
    generate_lesson,
    give_example,
    load_classroom_context,
    save_lesson_note,
    save_lesson_note_and_attend,
)
from services.module_service import add_module
from services.timetable_service import add_session


class FakeGateway(AIGateway):
    def __init__(self):
        self.calls = []

    def generate_timetable(self, prompt):
        return prompt

    def generate_lesson(self, prompt, context):
        self.calls.append(("lesson", prompt, context))
        return "generated lesson"

    def ask_followup(self, prompt, context, lesson, history):
        self.calls.append(("followup", prompt, context, lesson, history))
        return "follow-up response"

    def generate_explanation(self, context, lesson):
        self.calls.append(("explanation", context, lesson))
        return "clearer explanation"

    def generate_example(self, context, lesson):
        self.calls.append(("example", context, lesson))
        return "practical example"


@pytest.fixture
def classroom():
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    initialize_database(connection)
    module_id = add_module(connection, "SQL Developer", "SQL", "user-a")
    session_id = add_session(
        connection, module_id, 2, "2026-09-14", "Level 1",
        "SELECT and WHERE", "11:00 AM", "Teach SELECT.", "user-a"
    )
    yield connection, module_id, session_id
    connection.close()


def test_context_preserves_user_module_session_and_prompt(classroom):
    connection, module_id, session_id = classroom
    session, context = load_classroom_context(connection, session_id, "user-a")
    assert context.user_id == "user-a"
    assert context.module_id == module_id
    assert context.session_id == session_id
    assert context.topic == session["topic"]
    assert context.session_date == session["session_date"]
    assert context.scheduled_time == session["scheduled_time"]
    assert context.session_prompt == "Teach SELECT."


def test_explicit_lesson_generation_and_empty_prompt_validation(classroom):
    connection, _, session_id = classroom
    _, context = load_classroom_context(connection, session_id, "user-a")
    gateway = FakeGateway()
    assert generate_lesson(gateway, "Use interview examples.", context) == "generated lesson"
    assert len(gateway.calls) == 1
    with pytest.raises(ValueError):
        generate_lesson(gateway, "  ", context)


def test_followup_explanation_and_example_use_same_context(classroom):
    connection, _, session_id = classroom
    _, context = load_classroom_context(connection, session_id, "user-a")
    gateway = FakeGateway()
    assert ask_followup(gateway, "Give a company example.", context, "lesson", []) == "follow-up response"
    assert explain_again(gateway, context, "lesson") == "clearer explanation"
    assert give_example(gateway, context, "lesson") == "practical example"
    assert [call[0] for call in gateway.calls] == ["followup", "explanation", "example"]
    with pytest.raises(ValueError):
        ask_followup(gateway, "", context, "lesson", [])


def test_missing_session_and_provider_failure_are_explicit(classroom):
    connection, _, _ = classroom
    with pytest.raises(ValueError):
        load_classroom_context(connection, 9999, "user-a")

    class FailingGateway(FakeGateway):
        def generate_lesson(self, prompt, context):
            raise AIProviderError("AI provider is not configured yet.")

    _, context = load_classroom_context(connection, 1, "user-a")
    with pytest.raises(AIProviderError):
        generate_lesson(FailingGateway(), "Generate", context)


def test_save_lesson_note_keeps_session_identity(classroom):
    connection, module_id, session_id = classroom
    _, context = load_classroom_context(connection, session_id, "user-a")
    note_id = save_lesson_note(connection, context, "lesson content")
    note = connection.execute(
        "SELECT * FROM learning_notes WHERE note_id = ?", (note_id,)
    ).fetchone()
    assert note["session_id"] == session_id
    assert note["module_id"] == module_id
    assert note["user_id"] == "user-a"


def test_save_lesson_note_marks_only_exact_session_after_persistence(classroom):
    connection, _, session_id = classroom
    _, context = load_classroom_context(connection, session_id, "user-a")
    note_id = save_lesson_note_and_attend(
        connection, context, "saved lesson", "Saved lesson"
    )
    assert connection.execute(
        "SELECT session_id FROM learning_notes WHERE note_id=?", (note_id,)
    ).fetchone()["session_id"] == session_id
    assert connection.execute(
        "SELECT status FROM attendance WHERE user_id=? AND session_id=?",
        ("user-a", session_id),
    ).fetchone()["status"] == "Attended"
