import sqlite3

from ai.gateway import AIGateway, ClassroomContext
from services.notes_service import get_user_note, save_note
from services.session_service import get_learning_context
from services.attendance_service import record_learning_completion


def load_classroom_context(
    connection: sqlite3.Connection, session_id: int, user_id: str
) -> tuple[dict, ClassroomContext]:
    session = get_learning_context(connection, session_id, user_id)
    return session, ClassroomContext(
        user_id=user_id,
        module_id=int(session["module_id"]),
        session_id=int(session["session_id"]),
        category=session["category"],
        topic=session["topic"],
        session_date=session["session_date"],
        scheduled_time=session["scheduled_time"],
        session_prompt=session["prompt"],
    )


def validate_prompt(prompt: str) -> str:
    value = prompt.strip()
    if not value:
        raise ValueError("Enter a prompt before generating a lesson.")
    return value


def validate_response(response: str) -> str:
    if not isinstance(response, str) or not response.strip():
        raise ValueError("The AI provider returned an empty lesson. Please try again.")
    return response.strip()


def generate_lesson(
    gateway: AIGateway, prompt: str, context: ClassroomContext
) -> str:
    return validate_response(gateway.generate_lesson(validate_prompt(prompt), context))


def ask_followup(
    gateway: AIGateway,
    prompt: str,
    context: ClassroomContext,
    lesson: str,
    history: list[dict],
) -> str:
    return validate_response(
        gateway.ask_followup(validate_prompt(prompt), context, lesson, history)
    )


def explain_again(gateway: AIGateway, context: ClassroomContext, lesson: str) -> str:
    if not lesson.strip():
        raise ValueError("Generate a lesson before asking for an explanation.")
    return validate_response(gateway.generate_explanation(context, lesson))


def give_example(gateway: AIGateway, context: ClassroomContext, lesson: str) -> str:
    if not lesson.strip():
        raise ValueError("Generate a lesson before asking for an example.")
    return validate_response(gateway.generate_example(context, lesson))


def save_lesson_note(
    connection: sqlite3.Connection,
    context: ClassroomContext,
    lesson: str,
    title: str | None = None,
) -> int:
    note_title = title.strip() if title and title.strip() else f"{context.topic} — Fundamentals"
    note_id, _ = save_note(
        connection, context.user_id, context.module_id, context.session_id,
        context.category, context.topic, note_title, lesson
    )
    return note_id


def save_lesson_note_and_attend(
    connection: sqlite3.Connection,
    context: ClassroomContext,
    lesson: str,
    title: str | None = None,
) -> int:
    note_id = save_lesson_note(connection, context, lesson, title)
    from services.attendance_service import mark_attended_from_note
    mark_attended_from_note(
        connection, context.user_id, context.session_id, note_id
    )
    return note_id


def record_successful_generation(
    connection: sqlite3.Connection, context: ClassroomContext
) -> str:
    return record_learning_completion(connection, context.user_id, context.session_id)
