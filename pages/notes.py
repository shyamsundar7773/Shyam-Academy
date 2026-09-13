from datetime import datetime
from zoneinfo import ZoneInfo

import streamlit as st
from auth.session import require_current_user

from database.connection import get_connection
from services.module_service import get_modules
from utils.module_context import get_active_module_id, set_active_module_id
from utils.notes_presentation import group_notes_by_date

connection = get_connection()
user_id = require_current_user().user_id
modules = get_modules(connection, user_id)

st.title("My notes")
st.caption("Your saved learning history, organized by date, category, and module.")

if not modules:
    st.info("No modules available yet. Open a classroom to create notes.")
    st.stop()

active_module_id = get_active_module_id(st.session_state, user_id, modules)
module_ids = [module["module_id"] for module in modules]
if st.session_state.get("notes_module_selector") != active_module_id:
    st.session_state.notes_module_selector = active_module_id
selected_module = st.selectbox(
    "Module",
    module_ids,
    index=module_ids.index(active_module_id),
    format_func=lambda module_id: next(
        module["module_name"] for module in modules
        if module["module_id"] == module_id
    ),
    key="notes_module_selector",
)
selected_module = next(
    module for module in modules
    if module["module_id"] == selected_module
)
set_active_module_id(st.session_state, user_id, selected_module["module_id"], modules)
if st.session_state.get("notes_rendered_module_id") != selected_module["module_id"]:
    st.session_state.pop("notes_cell_selection", None)
    st.session_state.notes_rendered_module_id = selected_module["module_id"]

note_categories = (
    "Today Learning", "Level 1", "Level 2", "Problem Solving",
    "Doubts", "Test", "Interview Preparation", "Interview Room",
)
notes = [
    dict(row) for row in connection.execute(
        """SELECT n.note_id, n.module_id, n.category, n.topic, n.title,
                  n.saved_at, n.session_id, m.module_name,
                  s.day_number, s.session_date, s.scheduled_time
           FROM learning_notes n
           JOIN modules m ON m.module_id=n.module_id
           LEFT JOIN sessions s ON s.session_id=n.session_id
           WHERE n.user_id=? AND n.module_id=?
           ORDER BY COALESCE(s.session_date, substr(n.saved_at, 1, 10)),
                    n.category, n.learning_number""",
        (user_id, selected_module["module_id"]),
    ).fetchall()
]

for note in notes:
    if note["session_date"]:
        note["note_date"] = note["session_date"]
    else:
        saved_at = datetime.fromisoformat(note["saved_at"].replace("Z", "+00:00"))
        note["note_date"] = saved_at.astimezone(
            ZoneInfo("Asia/Kolkata")
        ).date().isoformat()

grouped_notes = group_notes_by_date(notes)
if not grouped_notes:
    st.info("No learning notes saved yet. Use Save Notes in a classroom to build this library.")

for matrix_row, (day_number, note_date, day_notes) in enumerate(grouped_notes):
    with st.container(border=True):
        st.markdown(f"### Day {day_number}")
        st.caption(f"Date: {note_date}")
        columns = st.columns(len(note_categories) + 1, gap="small")
        columns[0].markdown("**Date**")
        columns[0].caption(note_date)
        for index, category_name in enumerate(note_categories, start=1):
            category_notes = [
                note for note in day_notes if note["category"] == category_name
            ]
            module_ids = [selected_module["module_id"]] if category_notes else []
            label = f"{len(module_ids)} Module" if len(module_ids) == 1 else f"{len(module_ids)} Modules"
            columns[index].markdown(f"**{category_name}**")
            if columns[index].button(
                label,
                key=f"notes_cell_{matrix_row}_{note_date}_{category_name}",
                disabled=not module_ids,
            ):
                st.session_state.notes_cell_selection = {
                    "date": note_date,
                    "category": category_name,
                    "module_ids": module_ids,
                }
                st.switch_page("pages/full_notes.py")
            times = sorted({
                note["scheduled_time"] for note in category_notes
                if note["scheduled_time"]
            })
            if times:
                columns[index].caption(" · ".join(times))
