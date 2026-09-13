from collections import defaultdict


import streamlit as st
from auth.session import require_current_user

from database.connection import get_connection
from services.attendance_service import (
    attendance_summary,
    get_attendance_display_state,
)
from services.module_service import get_modules
from services.timetable_service import CATEGORIES, get_timetable, seed_development_timetable
from utils.formatting import display_date

connection = get_connection()
user_id = require_current_user().user_id
seed_key = f"development_timetable_seeded_{user_id}"
if not st.session_state.get(seed_key):
    seed_development_timetable(connection, user_id)
    st.session_state[seed_key] = True
modules = get_modules(connection, user_id)

st.title("Attendance")
st.caption("Attendance is earned only by saving notes from the linked timetable session.")


@st.fragment(run_every="15s")
def render_attendance():
    if not modules:
        st.info("No modules available yet. Create a module from the Timetable page.")
        return

    module_ids = [module["module_id"] for module in modules]
    active_module_id = st.session_state.get("active_module_id", module_ids[0])
    if active_module_id not in module_ids:
        active_module_id = module_ids[0]
    selected_module = st.selectbox(
        "Module",
        modules,
        index=module_ids.index(active_module_id),
        format_func=lambda module: module["module_name"],
        key="attendance_module_selector",
    )
    st.session_state.active_module_id = selected_module["module_id"]

    summary = attendance_summary(connection, user_id, selected_module["module_id"])
    metric_columns = st.columns(5)
    metric_columns[0].metric("Total sessions", summary["total"])
    metric_columns[1].metric("Attended", summary["attended"])
    metric_columns[2].metric("Missed", summary["missed"])
    metric_columns[3].metric("Upcoming", summary["upcoming"])
    metric_columns[4].metric("Attendance", f"{summary['percentage']}%")

    sessions = get_timetable(connection, selected_module["module_id"], user_id)
    grouped = defaultdict(list)
    for session in sessions:
        grouped[(session["day_number"], session["session_date"])].append(session)

    st.caption("Green = Attended · Blue = Active · Gray = Upcoming/Past · Red = Missed")
    for (day_number, session_date), day_sessions in grouped.items():
        with st.container(border=True):
            st.markdown(f"### Day {day_number}")
            st.caption(f"Date: {display_date(session_date)}")
            by_category = {session["category"]: session for session in day_sessions}
            columns = st.columns(len(CATEGORIES), gap="small")
            for column, category in zip(columns, CATEGORIES):
                session = by_category.get(category)
                if session is None:
                    column.caption("—")
                    continue
                display_state = get_attendance_display_state(
                    connection, user_id, session
                )
                status = display_state["display_status"]
                color = "#d1fae5" if display_state["attended"] else {
                    "Missed": "#fee2e2",
                    "Active": "#dbeafe",
                    "Upcoming": "#f3f4f6",
                    "Past": "#f3f4f6",
                }[status]
                column.markdown(
                    f"<div style='background:{color};padding:0.45rem;border-radius:0.4rem;"
                    f"font-size:0.78rem;color:#000000'><b>{category}</b><br>{status}</div>",
                    unsafe_allow_html=True,
                )
                tooltip = (
                    f"Day: Day {day_number}\nDate: {display_date(session_date)}\n"
                    f"Time: {session['scheduled_time']}\nCategory: {category}\n"
                    f"Topic: {session['topic']}\nAttendance: {status}\n"
                    f"Session ID: {session['session_id']}"
                )
                if column.button(
                    session["scheduled_time"],
                    key=f"attendance_session_{session['session_id']}",
                    help=tooltip,
                ):
                    st.session_state.selected_session_id = session["session_id"]
                    st.switch_page("pages/session_details.py")


render_attendance()
