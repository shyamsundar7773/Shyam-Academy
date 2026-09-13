import streamlit as st
from auth.session import require_current_user

from ai.gateway import get_gateway
from components.chat_classroom import render_shared_classroom
from database.connection import get_connection
from services.module_service import (
    get_modules,
    get_or_create_classroom_module,
    rename_classroom_module,
)
from services.attendance_service import mark_attended_from_note
from services.notes_service import save_note
from services.interview_service import INTERVIEW_CONTEXTS

connection = get_connection()
user_id = require_current_user().user_id
modules = get_modules(connection, user_id)

st.title("Interview Preparation")
st.caption("Practice naturally in a persistent AI interview classroom.")

context_names = tuple(INTERVIEW_CONTEXTS)
selected_context = st.session_state.get("interview_context", context_names[0])
tabs = st.tabs(context_names)
for name, tab in zip(context_names, tabs):
    with tab:
        st.caption(f"{name} classroom")
        if st.button(
            f"Use {name}",
            key=f"use_interview_context_{INTERVIEW_CONTEXTS[name]}",
            type="primary" if selected_context == name else "secondary",
        ):
            st.session_state.interview_context = name
            st.rerun()
selected_context = st.session_state.get("interview_context", context_names[0])

linked_session_id = st.session_state.get("learning_session_id")
linked_session = None
if linked_session_id:
    linked_session = connection.execute(
        """SELECT session_id,module_id,session_date,scheduled_time,category,topic
           FROM sessions WHERE session_id=? AND owner_user_id=?""",
        (linked_session_id, user_id),
    ).fetchone()
    if linked_session and linked_session["category"] != "Interview Preparation":
        linked_session = None

session_token = linked_session["session_id"] if linked_session else "independent"
context_id = f"interview:{INTERVIEW_CONTEXTS[selected_context]}:session:{session_token}"
classroom_id = context_id.replace(":", "_")
module = (
    dict(connection.execute(
        "SELECT module_id,module_name FROM modules WHERE module_id=? AND owner_user_id=?",
        (linked_session["module_id"], user_id),
    ).fetchone())
    if linked_session else get_or_create_classroom_module(
        connection, user_id, classroom_id, selected_context,
        f"Independent Interview Preparation · {selected_context}",
    )
)
module_id = int(module["module_id"])

if linked_session:
    st.info(
        f"Timetable context: {linked_session['session_date']} · "
        f"{linked_session['scheduled_time']} · {linked_session['topic']}"
    )


def save_interview_notes(classroom_title, history):
    content = "\n\n".join(
        f"{item['role'].title()}: {item['content']}" for item in history
    )
    note_id, _ = save_note(
        connection, user_id, module_id,
        int(linked_session["session_id"]) if linked_session else None,
        "Interview Preparation", selected_context, classroom_title, content,
        "Interview Preparation classroom", context_id,
    )
    if linked_session:
        mark_attended_from_note(
            connection, user_id, int(linked_session["session_id"]), note_id
        )

def update_interview_title(title):
    rename_classroom_module(connection, user_id, module_id, title)

render_shared_classroom(
    connection, user_id, classroom_id, "interview_preparation",
    module["module_name"],
    f"Interview context: {selected_context}. Module: {module['module_name']}. "
    "Ask for an interview question, answer it, request feedback, or continue the practice.",
    get_gateway(), save_interview_notes, update_interview_title,
)
