import streamlit as st
from auth.session import require_current_user

from database.connection import get_connection
from services.notes_service import find_notes_for_cell, remove_note
from services.module_service import get_modules
from utils.module_context import get_active_module_id, set_active_module_id

connection = get_connection()
user_id = require_current_user().user_id
selection = st.session_state.get("notes_cell_selection")

st.title("Full Notes")
if not selection:
    st.info("Select a date and category cell from My Notes.")
    if st.button("Back to My Notes"):
        st.switch_page("pages/notes.py")
    st.stop()

note_date = selection["date"]
category = selection["category"]
modules = get_modules(connection, user_id)
if not modules:
    st.info("No modules available.")
    st.stop()
active_module_id = get_active_module_id(st.session_state, user_id, modules)
module_ids = [module["module_id"] for module in modules]
if st.session_state.get("full_notes_module_selector") != active_module_id:
    st.session_state.full_notes_module_selector = active_module_id
selected_module = st.selectbox(
    "Module",
    module_ids,
    index=module_ids.index(active_module_id),
    format_func=lambda module_id: next(
        module["module_name"] for module in modules
        if module["module_id"] == module_id
    ),
    key="full_notes_module_selector",
)
selected_module = next(
    module for module in modules
    if module["module_id"] == selected_module
)
set_active_module_id(st.session_state, user_id, selected_module["module_id"], modules)
notes = find_notes_for_cell(
    connection, user_id, note_date, category, [selected_module["module_id"]]
)

st.markdown(f"**Date:** {note_date}")
st.markdown(f"**Category:** {category}")
st.divider()

if not notes:
    st.info("No notes match this selection.")
else:
    for note in notes:
        with st.expander(
            f"{note['title']} · {note['saved_at']}",
            expanded=False,
        ):
            st.caption(f"Session: {note['session_id'] or 'independent'}")
            if note.get("context_id"):
                st.caption(f"Context: {note['context_id']}")
            st.markdown(note["content"])
            if st.button(
                "Delete note",
                key=f"full_notes_delete_{note['note_id']}",
            ):
                remove_note(connection, note["note_id"], user_id)
                st.rerun()

if st.button("Back to My Notes", icon=":material/arrow_back:"):
    st.switch_page("pages/notes.py")
