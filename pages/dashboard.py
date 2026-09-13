import streamlit as st
from auth.session import require_current_user

from database.connection import get_connection
from services.module_service import get_modules
from services.timetable_service import get_timetable, seed_development_timetable
from services.attendance_service import get_attendance_display_state
from services.schedule_status import can_start_learning
from alarms.repository import get_alarm_for_session
from utils.module_context import get_active_module_id
from utils.dashboard_presentation import (
    current_dashboard_time,
    order_dashboard_sessions,
)

connection = get_connection()
user_id = require_current_user().user_id
seed_key = f"development_timetable_seeded_{user_id}"
if not st.session_state.get(seed_key):
    seed_development_timetable(connection, user_id)
    st.session_state[seed_key] = True
modules = get_modules(connection, user_id)

st.title("Today")
current_time = current_dashboard_time()
st.caption(current_time.strftime("%A, %d %B %Y · %I:%M %p"))

if modules:
    active_module_id = get_active_module_id(st.session_state, user_id, modules)
    active_module = next(
        module for module in modules if module["module_id"] == active_module_id
    )
    sessions = []
    for session in get_timetable(connection, active_module_id, user_id):
        session = dict(session)
        session["module_name"] = active_module["module_name"]
        session["display_status"] = get_attendance_display_state(
            connection, user_id, session, now=current_time, persist_missed=False
        )["display_status"]
        session["alarm"] = get_alarm_for_session(
            connection, user_id, session["session_id"]
        )
        sessions.append(session)
    ordered_sessions = order_dashboard_sessions(sessions, current_time)
    today = current_time.date().isoformat()
    today_sessions = [
        session for session in ordered_sessions if session["session_date"] == today
    ]
    if not today_sessions:
        st.info("No learning sessions are scheduled for today.")
    else:
        current = next(
            (item for item in today_sessions if item["display_status"] == "Active"),
            next((item for item in today_sessions if item["display_status"] == "Upcoming"), None),
        )
        if current:
            with st.container(border=True):
                st.subheader("Next Learning")
                st.write(f"**{current['module_name']} · {current['topic']}**")
                st.caption(f"{current['scheduled_time']} · {current['display_status']}")
                if current["alarm"]:
                    st.caption(f"Backend alarm synced · {current['alarm']['alarm_id']}")
                if can_start_learning(current) and st.button(
                    "Take Learning", key=f"dashboard_learn_{current['session_id']}", type="primary"
                ):
                    st.session_state.learning_session_id = current["session_id"]
                    st.switch_page("pages/today_learning.py")
                elif current["display_status"] == "Upcoming":
                    st.caption(f"Available at {current['scheduled_time']}")
        st.subheader("Today's Schedule")
        for item in today_sessions:
            with st.container(border=True):
                left, right = st.columns([4, 1])
                left.write(f"**{item['scheduled_time']} · {item['topic']}**")
                left.caption(f"{item['module_name']} · {item['display_status']}")
                if item["alarm"]:
                    left.caption(f"Alarm: {item['alarm']['status']} · {item['alarm']['timezone']}")
                if right.button(
                    "Learn" if can_start_learning(item) else item["display_status"],
                    key=f"dashboard_learn_list_{item['session_id']}",
                    disabled=not can_start_learning(item),
                ):
                    st.session_state.learning_session_id = item["session_id"]
                    st.switch_page("pages/today_learning.py")
    future_sessions = [
        session for session in ordered_sessions if session["session_date"] > today
    ]
    if future_sessions:
        st.subheader("Upcoming Dates")
        for item in future_sessions:
            with st.container(border=True):
                st.write(
                    f"**{item['session_date']} · {item['scheduled_time']} · "
                    f"{item['topic']}**"
                )
                st.caption(f"{item['module_name']} · {item['display_status']}")
    history_sessions = [
        session for session in ordered_sessions if session["session_date"] < today
    ]
    if history_sessions:
        st.subheader("Past History")
        for item in history_sessions:
            with st.container(border=True):
                st.write(
                    f"**{item['session_date']} · {item['scheduled_time']} · "
                    f"{item['topic']}**"
                )
                st.caption(f"{item['module_name']} · {item['display_status']}")
else:
    st.info("Create your first timetable with AI.")
