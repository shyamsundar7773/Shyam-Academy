import streamlit as st
from auth.session import require_current_user

from ai.gateway import get_gateway
from components.chat_classroom import render_shared_classroom
from database.connection import get_connection
from services.module_service import (
    get_or_create_classroom_module,
    rename_classroom_module,
)
from services.attendance_service import mark_attended_from_note
from services.notes_service import save_note

connection = get_connection()
user_id = require_current_user().user_id
linked_session_id = st.session_state.get("learning_session_id")
linked_session = None
if linked_session_id:
    linked_session = connection.execute(
        """SELECT session_id,module_id,session_date,scheduled_time,category,topic
           FROM sessions WHERE session_id=? AND owner_user_id=?""",
        (linked_session_id, user_id),
    ).fetchone()
    if linked_session and linked_session["category"] != "Interview Room":
        linked_session = None

session_token = linked_session["session_id"] if linked_session else "independent"
context_id = f"interview_room:session:{session_token}"
classroom_id = context_id.replace(":", "_")
module = (
    dict(connection.execute(
        "SELECT module_id,module_name FROM modules WHERE module_id=? AND owner_user_id=?",
        (linked_session["module_id"], user_id),
    ).fetchone())
    if linked_session else get_or_create_classroom_module(
        connection, user_id, classroom_id, "Interview Room",
        "Independent Interview Room",
    )
)
module_id = int(module["module_id"])

st.title("Interview Room")
st.caption("Practice in the separate Interview Room classroom.")


def save_room_notes(classroom_title, history):
    content = "\n\n".join(
        f"{item['role'].title()}: {item['content']}" for item in history
    )
    note_id, _ = save_note(
        connection, user_id, module_id,
        int(linked_session["session_id"]) if linked_session else None,
        "Interview Room", "Interview Room", classroom_title, content,
        "Interview Room classroom", context_id,
    )
    if linked_session:
        mark_attended_from_note(
            connection, user_id, int(linked_session["session_id"]), note_id
        )

def update_room_title(title):
    rename_classroom_module(connection, user_id, module_id, title)

render_shared_classroom(
    connection, user_id, classroom_id, "interview_room",
    module["module_name"],
    f"Module: {module['module_name']}. "
    "Use this separate room for interview simulation and follow-up practice.",
    get_gateway(), save_room_notes, update_room_title,
)
