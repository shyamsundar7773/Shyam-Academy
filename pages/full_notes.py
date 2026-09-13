import streamlit as st
from auth.session import require_current_user

from database.connection import get_connection
from services.notes_service import find_notes_for_cell, remove_note

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
module_ids = [int(value) for value in selection.get("module_ids", [])]
if selection.get("module_id") is not None:
    module_ids.append(int(selection["module_id"]))
module_ids = sorted(set(module_ids))
notes = find_notes_for_cell(connection, user_id, note_date, category, module_ids)

st.markdown(f"**Date:** {note_date}")
st.markdown(f"**Category:** {category}")
st.divider()

if not notes:
    st.info("No notes match this selection.")
else:
    grouped = {}
    for note in notes:
        grouped.setdefault(int(note["module_id"]), []).append(note)
    for module_id, module_notes in grouped.items():
        module_name = module_notes[0]["module_name"]
        with st.expander(module_name, expanded=False):
            for note in module_notes:
                with st.expander(
                    f"{note['title']} · {note['saved_at']}",
                    expanded=False,
                ):
                    st.caption(
                        f"Session: {note['session_id'] or 'independent'}"
                    )
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
