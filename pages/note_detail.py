import streamlit as st
from auth.session import require_current_user

from database.connection import get_connection
from services.notes_service import edit_note, get_user_note, remove_note
from utils.formatting import display_date

connection = get_connection()
user_id = require_current_user().user_id
note_id = st.session_state.get("selected_note_id")

st.title("Note details")
if note_id is None:
    st.info("Select a note from My Notes.")
    if st.button("Open my notes", icon=":material/description:"):
        st.switch_page("pages/notes.py")
    st.stop()

try:
    note = get_user_note(connection, int(note_id), user_id)
except ValueError as error:
    st.error(str(error))
    if st.button("Open my notes", icon=":material/description:"):
        st.switch_page("pages/notes.py")
    st.stop()

st.caption(
    f"{note['module_name']} · {note['category']} · {note['topic']} · "
    f"Learning {note['learning_number']}"
)
st.markdown(f"Saved: {display_date(note['saved_at'][:10])}")

with st.form("edit_note"):
    title = st.text_input("Title", value=note["title"])
    content = st.text_area("Content", value=note["content"], height=420)
    saved = st.form_submit_button("Save changes", type="primary", icon=":material/save:")
if saved:
    try:
        edit_note(connection, note["note_id"], user_id, title, content)
    except ValueError as error:
        st.error(str(error))
    else:
        st.success("Note updated.")
        st.rerun()

st.subheader(note["title"])
st.markdown(note["content"])

with st.expander("Note metadata"):
    st.write(f"Module: {note['module_name']}")
    st.write(f"Category: {note['category']}")
    st.write(f"Topic: {note['topic']}")
    st.write(f"Source: {note['source']}")
    st.write(f"Session ID: {note['session_id'] or 'Not linked'}")

with st.container(horizontal=True):
    if st.button("Delete note", icon=":material/delete:"):
        st.session_state.confirm_delete_note = True
    if st.button("Back to notes", icon=":material/arrow_back:"):
        st.switch_page("pages/notes.py")

if st.session_state.get("confirm_delete_note", False):
    st.warning("Delete this saved learning note? The timetable session will not be affected.")
    if st.button("Confirm delete", type="primary", key="confirm_delete"):
        try:
            remove_note(connection, note["note_id"], user_id)
        except ValueError as error:
            st.error(str(error))
        else:
            st.session_state.confirm_delete_note = False
            st.session_state.selected_note_id = None
            st.success("Note deleted.")
            st.switch_page("pages/notes.py")
