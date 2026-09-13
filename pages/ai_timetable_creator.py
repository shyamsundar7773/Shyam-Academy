import json
from dataclasses import asdict
from datetime import date, datetime

import streamlit as st
from auth.session import require_current_user

from ai.gateway import AIProviderError, get_gateway
from database.connection import get_connection
from services.module_service import get_modules
from services.timetable_creator_service import (
    detect_conflicts,
    apply_request_constraints,
    generate_plan,
    parse_plan,
    persist_plan,
)
from services.timetable_service import CATEGORIES

connection = get_connection()
user_id = require_current_user().user_id

st.title("AI timetable creator")
st.caption("Describe the outcome you want. The AI will propose a schedule for your review.")

modules = get_modules(connection, user_id)
module_options = {"Create a new module": None}
module_options.update({module["module_name"]: int(module["module_id"]) for module in modules})

with st.form("ai_timetable_request"):
    request = st.text_area(
        "Your learning request",
        key="ai_timetable_request_widget",
        placeholder=(
            "I want to become job-ready as a SQL Developer in 15 days. "
            "I can study 3 hours every weekday from 7 PM to 10 PM."
        ),
        height=160,
    )
    selected_module_name = st.selectbox(
        "Add to an existing module (optional)",
        list(module_options),
        help="Leave this on Create a new module to create the inferred module only after confirmation.",
    )
    generate = st.form_submit_button(
        "Generate timetable", type="primary", icon=":material/auto_awesome:"
    )

if generate:
    submitted_request = request.strip()
    st.session_state.ai_timetable_submitted_request = submitted_request
    st.session_state.ai_timetable_plan = None
    try:
        if not submitted_request:
            raise ValueError("Describe the learning outcome you want to plan.")
        st.session_state.ai_timetable_plan = generate_plan(get_gateway(), submitted_request)
        st.session_state.ai_timetable_module_id = module_options[selected_module_name]
        st.session_state.ai_timetable_error = None
    except (ValueError, AIProviderError) as error:
        st.session_state.ai_timetable_error = str(error)
        st.session_state.ai_timetable_plan = None
    st.rerun()

if st.session_state.get("ai_timetable_error"):
    st.error(st.session_state.ai_timetable_error)

plan = st.session_state.get("ai_timetable_plan")
if plan is None:
    st.info("Your generated proposal will appear here before anything is saved.")
    st.stop()

st.subheader("Preview")
with st.container(border=True):
    st.markdown(f"### {plan.title}")
    st.write(f"**Module:** {plan.module_name}")
    st.write(f"**Date range:** {plan.start_date} to {plan.end_date}")
    st.write(f"**Total planned sessions:** {plan.total_sessions}")
    if plan.assumptions:
        st.markdown("**Planning assumptions**")
        for assumption in plan.assumptions:
            st.write(f"- {assumption}")

st.caption("Edit any session below. Changes are kept in this preview until you confirm or clear it.")
removed = []
edited = []
for index, session in enumerate(plan.sessions):
    with st.container(border=True):
        st.markdown(f"**Day {session.day_number} · {session.session_date}**")
        columns = st.columns([1.2, 1.2, 1.6, 2.2])
        edited_date = columns[0].date_input(
            "Date", date.fromisoformat(session.session_date), key=f"creator_date_{index}"
        )
        edited_time = columns[1].time_input(
            "Start time",
            datetime.strptime(session.scheduled_time, "%I:%M %p").time(),
            key=f"creator_time_{index}",
        )
        edited_category = columns[2].selectbox(
            "Category", list(CATEGORIES),
            index=list(CATEGORIES).index(session.category),
            key=f"creator_category_{index}",
        )
        edited_topic = columns[3].text_input(
            "Topic", session.topic, key=f"creator_topic_{index}"
        )
        edited_title = st.text_input(
            "Session title", session.session_title, key=f"creator_title_{index}"
        )
        edited_prompt = st.text_area(
            "AI teaching prompt", session.prompt, key=f"creator_prompt_{index}", height=90
        )
        if st.checkbox("Remove this session", key=f"creator_remove_{index}"):
            removed.append(index)
        edited.append({
            "session_date": edited_date.isoformat(),
            "scheduled_time": edited_time.strftime("%I:%M %p"),
            "scheduled_end_time": session.scheduled_end_time or "",
            "category": edited_category,
            "topic": edited_topic,
            "session_title": edited_title,
            "prompt": edited_prompt,
            "status": session.status,
            "day_number": session.day_number,
        })

action_columns = st.columns(3)
if action_columns[0].button("Regenerate", icon=":material/refresh:"):
    try:
        st.session_state.ai_timetable_plan = generate_plan(
            get_gateway(), st.session_state.get("ai_timetable_submitted_request", "")
        )
        st.session_state.ai_timetable_error = None
    except (ValueError, AIProviderError) as error:
        st.session_state.ai_timetable_error = str(error)
    st.rerun()
if action_columns[1].button("Clear preview", icon=":material/delete:"):
    st.session_state.ai_timetable_plan = None
    st.session_state.ai_timetable_error = None
    st.rerun()
if action_columns[2].button("Create timetable", type="primary", icon=":material/check:"):
    try:
        raw_plan = asdict(plan)
        raw_plan["sessions"] = [
            session for index, session in enumerate(edited) if index not in removed
        ]
        updated_plan = apply_request_constraints(
            parse_plan(json.dumps(raw_plan)),
            st.session_state.get("ai_timetable_submitted_request", ""),
        )
        module_id = st.session_state.get("ai_timetable_module_id")
        conflicts = detect_conflicts(connection, user_id, updated_plan, module_id)
        if conflicts:
            raise ValueError("Existing sessions conflict with: " + ", ".join(conflicts))
        saved_module_id, _ = persist_plan(connection, user_id, updated_plan, module_id)
    except (ValueError, AIProviderError) as error:
        st.error(str(error))
    else:
        st.session_state.active_module_id = saved_module_id
        st.session_state.ai_timetable_plan = None
        st.success("Timetable created. Your sessions are now available in Timetable.")
        st.switch_page("pages/timetable.py")
