import streamlit as st
from auth.session import require_current_user

from database.connection import get_connection
from services.module_service import get_modules
from services.timetable_service import get_timetable, seed_development_timetable
from services.schedule_status import can_start_learning, session_status
from alarms.repository import get_alarm_for_session
from datetime import datetime

connection = get_connection()
user_id = require_current_user().user_id
seed_key = f"development_timetable_seeded_{user_id}"
if not st.session_state.get(seed_key):
    seed_development_timetable(connection, user_id)
    st.session_state[seed_key] = True
modules = get_modules(connection, user_id)

st.title("Today")
st.caption(datetime.now().strftime("%A, %d %B %Y · %I:%M %p"))

if modules:
    today = datetime.now().date().isoformat()
    today_sessions = []
    for module in modules:
        for session in get_timetable(connection, module["module_id"], user_id):
            if session["session_date"] == today:
                session = dict(session)
                session["module_name"] = module["module_name"]
                session["display_status"] = session_status(session)
                session["alarm"] = get_alarm_for_session(
                    connection, user_id, session["session_id"]
                )
                today_sessions.append(session)
    today_sessions.sort(key=lambda row: row["scheduled_time"])
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
else:
    st.info("Create your first timetable with AI.")
