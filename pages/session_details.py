from datetime import datetime

import streamlit as st
from auth.session import require_current_user

from database.connection import get_connection
from services.session_service import get_learning_context, get_learning_route
from services.timetable_service import save_session
from services.schedule_status import can_start_learning, session_status
from utils.formatting import display_date

connection = get_connection()
user_id = require_current_user().user_id
session_id = st.session_state.get("selected_session_id")

if session_id is None:
    st.title("Session details")
    st.info("Select a scheduled time from the Timetable.")
    if st.button("Back to timetable", icon=":material/arrow_back:"):
        st.switch_page("pages/timetable.py")
    st.stop()

session = get_learning_context(connection, int(session_id), user_id)
current_state = session_status(session)
st.title("Session details")
st.caption(f"Session ID: {session['session_id']} · {session['module_name']}")

with st.container(border=True):
    st.subheader(f"Day {session['day_number']}")
    st.write(display_date(session["session_date"]))
    st.markdown("**Category**")
    st.write(session["category"])
    st.markdown("**Topic**")
    st.write(session["topic"])
    st.caption(f"Session state: {current_state}")

    with st.form("session_details"):
        topic = st.text_input("Topic", value=session["topic"])
        scheduled_time = st.time_input(
            "Time",
            value=datetime.strptime(session["scheduled_time"], "%I:%M %p").time(),
        )
        prompt = st.text_area("AI learning prompt", value=session["prompt"], height=130)
        status = st.selectbox(
            "Status", ["Scheduled", "Completed", "Skipped"],
            index=["Scheduled", "Completed", "Skipped"].index(session["status"]),
        )
        update_time = st.form_submit_button(
            "Update time", icon=":material/schedule:"
        )
        save = st.form_submit_button("Save", type="primary", icon=":material/save:")

    if update_time or save:
        try:
            save_session(
                connection, session["session_id"], scheduled_time.strftime("%I:%M %p"),
                topic.strip(), prompt.strip(), status, user_id
            )
        except ValueError as error:
            st.error(str(error))
        else:
            st.success("Session updated without changing its session ID.")
            st.rerun()

if st.button(
    "Take learning" if current_state == "Active" else "Review session",
    type="primary",
    icon=":material/play_arrow:",
    disabled=not can_start_learning(session) and current_state == "Upcoming",
    help="This session has not started yet." if current_state == "Upcoming" else None,
):
    st.session_state.learning_session_id = session["session_id"]
    st.switch_page(get_learning_route(session["category"]))

if st.button("Back to timetable", icon=":material/arrow_back:"):
    st.switch_page("pages/timetable.py")
