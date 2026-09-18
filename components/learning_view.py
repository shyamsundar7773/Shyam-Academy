import streamlit as st
from auth.session import require_current_user

from ai.gateway import AIProviderError, get_gateway
from components.chat_classroom import render_shared_classroom
from services.classroom_service import load_history, save_history
from database.connection import get_connection
from database.repositories.session_repository import list_sessions
from services.learning_service import (
    generate_lesson,
    load_classroom_context,
    save_lesson_note_and_attend,
)
from services.notes_service import get_user_note
from services.module_service import get_modules
from utils.module_context import get_active_module_id
from utils.formatting import display_date
from services.schedule_status import session_status


def _select_today_session(connection, user_id: str) -> int | None:
    modules = get_modules(connection, user_id)
    if not modules:
        return None
    active_module_id = get_active_module_id(st.session_state, user_id, modules)
    sessions = [
        row for row in list_sessions(connection, active_module_id, user_id)
        if row["category"] == "Today Learning"
    ]
    if not sessions:
        return None
    labels = {
        row["session_id"]: f"{row['topic']} · {row['scheduled_time']}"
        for row in sessions
    }
    selected = st.selectbox(
        "Choose today's session",
        list(labels),
        format_func=lambda session_id: labels[session_id],
        key="today_learning_session_picker",
    )
    return int(selected)


def render_learning_page(expected_category: str | None = None) -> None:
    connection = get_connection()
    user_id = require_current_user().user_id
    session_id = st.session_state.get("learning_session_id")

    st.title(expected_category or "AI classroom")
    if session_id is None and expected_category == "Today Learning":
        session_id = _select_today_session(connection, user_id)
        if session_id is not None:
            st.session_state.learning_session_id = session_id
    if session_id is None:
        st.info("No learning session selected. Choose a session from the Timetable.")
        if st.button("Open timetable", icon=":material/calendar_month:"):
            st.switch_page("pages/timetable.py")
        return

    try:
        session, context = load_classroom_context(connection, int(session_id), user_id)
    except ValueError as error:
        st.error(str(error))
        if st.button("Open timetable", icon=":material/calendar_month:"):
            st.switch_page("pages/timetable.py")
        return

    current_state = session_status(session)
    if current_state == "Upcoming":
        st.warning(
            f"This session is upcoming and becomes available at {session['scheduled_time']}."
        )
        return

    if expected_category and session["category"] != expected_category:
        st.warning("This session belongs to a different learning category.")

    state_key = f"classroom_{context.session_id}"
    prompt_key = f"{state_key}_prompt"
    lesson_key = f"{state_key}_lesson"
    title_key = f"{state_key}_title"
    history_key = f"{state_key}_history"
    st.session_state.setdefault(prompt_key, context.session_prompt)
    st.session_state.setdefault(lesson_key, "")
    st.session_state.setdefault(title_key, f"{context.topic} — Fundamentals")
    st.session_state.setdefault(
        history_key, load_history(connection, context.user_id, str(context.session_id))
    )

    if not st.session_state[lesson_key]:
        st.caption(
            f"Day {session['day_number']} · {display_date(session['session_date'])} · "
            f"{session['category']} · {session['scheduled_time']}"
        )
        st.subheader(session["topic"])
    with st.expander("Lesson prompt", expanded=False):
        st.text_area(
            "Lesson prompt",
            key=prompt_key,
            height=120,
            help="This prompt is sent to the configured AI provider for this session.",
        )

    if not st.session_state[lesson_key] and not st.session_state.get(f"{state_key}_attempted"):
        st.session_state[f"{state_key}_attempted"] = True
        try:
            with st.spinner("Preparing your lesson..."):
                lesson = generate_lesson(get_gateway(), st.session_state[prompt_key], context)
        except (ValueError, AIProviderError) as error:
            st.error(str(error))
        else:
            st.session_state[lesson_key] = lesson
            st.session_state[history_key].append(
                {"role": "assistant", "content": lesson}
            )
            save_history(
                connection, context.user_id, str(context.session_id),
                st.session_state[history_key],
                f"{context.topic} — Fundamentals",
            )
            st.rerun()

    if lesson := st.session_state[lesson_key]:
        def save_learning_notes(classroom_title, history):
            note_id = save_lesson_note_and_attend(
                connection, context,
                "\n\n".join(item["content"] for item in history if item["role"] == "assistant"),
                classroom_title,
            )
            get_user_note(connection, note_id, context.user_id)

        render_shared_classroom(
            connection,
            context.user_id,
            str(context.session_id),
            "today_learning",
            st.session_state[title_key],
            f"Session topic: {context.topic}. Date: {context.session_date}.",
            get_gateway(),
            save_learning_notes,
        )
        return

    return
