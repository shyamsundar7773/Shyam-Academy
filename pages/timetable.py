from collections import defaultdict

import streamlit as st
from auth.session import require_current_user

from database.connection import get_connection
from services.module_service import edit_module, get_modules, remove_module
from services.timetable_service import get_timetable, seed_development_timetable
from services.timetable_service import CATEGORIES
from utils.formatting import display_date
from services.schedule_status import session_status
from alarms.repository import get_alarm_for_session

connection = get_connection()
user_id = require_current_user().user_id
seed_key = f"development_timetable_seeded_{user_id}"
if not st.session_state.get(seed_key):
    seed_development_timetable(connection, user_id)
    st.session_state[seed_key] = True

st.title("Timetable")
st.caption("A compact view of your scheduled academy sessions.")

with st.container(horizontal=True):
    if st.button(
        "Create timetable with AI",
        icon=":material/auto_awesome:",
        help="Describe a timetable in natural language and review it before saving.",
    ):
        st.switch_page("pages/ai_timetable_creator.py")
    if st.button("Attendance", icon=":material/checklist:"):
        st.switch_page("pages/attendance.py")

st.subheader("Modules")
modules = get_modules(connection, user_id)
if not modules:
    st.info("No modules yet. Create a timetable with AI to get started.")
    st.stop()
module_names = [module["module_name"] for module in modules]
selected_name = st.selectbox(
    "Module",
    module_names,
    index=module_names.index(st.session_state.get("active_module_name", module_names[0]))
    if st.session_state.get("active_module_name") in module_names else 0,
)
selected_module = next(module for module in modules if module["module_name"] == selected_name)
st.session_state.active_module_id = selected_module["module_id"]
st.session_state.active_module_name = selected_module["module_name"]

rename_requested = st.button("Rename", key=f"rename_module_{selected_module['module_id']}")
if rename_requested:
    st.session_state[f"rename_module_open_{selected_module['module_id']}"] = True

if st.session_state.get(f"rename_module_open_{selected_module['module_id']}"):
    with st.form("edit_module"):
        edited_name = st.text_input("Module name", value=selected_module["module_name"])
        edited_description = st.text_area(
            "Description", value=selected_module["description"]
        )
        edit_submitted = st.form_submit_button("Save module changes", type="primary")
    if edit_submitted:
        try:
            edit_module(
                connection, selected_module["module_id"], edited_name,
                edited_description, user_id
            )
        except ValueError as error:
            st.error(str(error))
        else:
            st.session_state.active_module_name = edited_name.strip()
            st.session_state.pop(f"rename_module_open_{selected_module['module_id']}", None)
            st.success("Module updated.")
            st.rerun()
if st.button("Delete module", type="secondary", icon=":material/delete:"):
    try:
        remove_module(connection, selected_module["module_id"], user_id)
    except ValueError as error:
        st.error(str(error))
    else:
        st.session_state.pop("active_module_id", None)
        st.session_state.pop("active_module_name", None)
        st.success("Module and its timetable were deleted.")
        st.rerun()
sessions = get_timetable(connection, selected_module["module_id"], user_id)
categories = list(CATEGORIES)
grouped = defaultdict(list)
for session in sessions:
    grouped[(session["day_number"], session["session_date"])].append(session)

st.subheader(selected_module["module_name"])
if not grouped:
    st.info("No sessions are scheduled for this module yet.")

for (day_number, session_date), day_sessions in grouped.items():
    with st.container(border=True):
        st.markdown(f"### Day {day_number}")
        st.caption(f"Date: {display_date(session_date)}")
        header = st.columns(len(categories) + 1)
        header[0].markdown("**Day**")
        for index, category in enumerate(categories, start=1):
            header[index].markdown(f"**{category}**")
        row = st.columns(len(categories) + 1)
        row[0].write(f"Day {day_number}")
        by_category = {session["category"]: session for session in day_sessions}
        for index, category in enumerate(categories, start=1):
            session = by_category.get(category)
            if session:
                tooltip = (
                    f"Day: Day {day_number}\n"
                    f"Date: {display_date(session_date)}\n"
                    f"Time: {session['scheduled_time']}\n"
                    f"Category: {session['category']}\n"
                    f"Topic: {session['topic']}\n"
                    f"Status: {session['status']}"
                )
                display_state = session_status(dict(session))
                alarm = get_alarm_for_session(connection, user_id, session["session_id"])
                label = f"{session['scheduled_time']} · {display_state}"
                if row[index].button(
                    label,
                    key=f"session_{session['session_id']}",
                    help=tooltip + (
                        f"\nAlarm: {alarm['status']} · {alarm['alarm_id']}"
                        if alarm else "\nAlarm: not synchronized"
                    ),
                ):
                    st.session_state.selected_session_id = session["session_id"]
                    st.switch_page("pages/session_details.py")
            else:
                row[index].caption("—")
