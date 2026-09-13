import streamlit as st
from auth.session import require_current_user

from ai.gateway import AIProviderError, get_gateway
from database.connection import get_connection
from database.repositories import mentor_repository as repo
from models.mentor import MENTOR_ACTIONS
from services.mentor_service import (
    build_mentor_context,
    get_or_create_conversation,
    mentor_reply,
    save_exchange,
)
from services.notes_service import save_note
from services.module_service import get_modules

connection = get_connection()
user_id = require_current_user().user_id
st.title("AI Mentor")
st.caption("Evidence-based guidance from your timetable, progress, tests, interviews, and notes.")

modules = get_modules(connection, user_id)
module_options = {"All modules": None}
module_options.update({row["module_name"]: int(row["module_id"]) for row in modules})
module_name = st.selectbox("Learning context", list(module_options))
module_id = module_options[module_name]

conversation_id = get_or_create_conversation(
    connection, user_id, st.session_state.get("mentor_conversation_id")
)
st.session_state.mentor_conversation_id = conversation_id
messages = repo.list_messages(connection, conversation_id, user_id)
context = build_mentor_context(connection, user_id, module_id)

with st.container(border=True):
    st.subheader("What should I help with?")
    action_labels = {
        "GENERAL_GUIDANCE": "Ask Mentor",
        "STUDY_RECOMMENDATION": "Suggest what to study",
        "WEAK_AREA_REVIEW": "Explain weak areas",
        "PROGRESS_REVIEW": "Review progress",
        "MISSED_SESSION_REVIEW": "Review missed learning",
        "UPCOMING_SESSION_PREP": "Prepare for upcoming session",
        "TEST_PREPARATION": "Prepare for a test",
        "INTERVIEW_PREPARATION": "Review interview readiness",
        "CAREER_GUIDANCE": "Career / skill guidance",
        "STUDY_PLAN": "Generate study strategy",
    }
    action = st.selectbox(
        "Mentor action", list(action_labels), format_func=lambda value: action_labels[value]
    )
    with st.form("mentor_prompt"):
        question = st.text_area(
            "Your question",
            placeholder="What should I study today?",
            height=110,
        )
        ask = st.form_submit_button("Ask Mentor", type="primary")

if ask:
    try:
        history = [{"role": row["role"], "message": row["message"]} for row in messages]
        response = mentor_reply(get_gateway(), context, question, history, action)
        save_exchange(connection, conversation_id, user_id, question, response, action)
        st.session_state.mentor_last_response = response
        st.rerun()
    except (ValueError, AIProviderError) as error:
        st.error(str(error))

if context.recommendations:
    st.subheader("Evidence-based recommendations")
    for index, recommendation in enumerate(context.recommendations):
        with st.container(border=True):
            st.markdown(f"**{recommendation.priority} · {recommendation.topic}**")
            st.write(recommendation.reason)
            if recommendation.evidence:
                st.caption("Evidence: " + " · ".join(recommendation.evidence))
            st.write(recommendation.suggested_action)

st.subheader("Conversation")
messages = repo.list_messages(connection, conversation_id, user_id)
if not messages:
    st.info("Ask the Mentor a question to begin.")
for row in messages:
    with st.chat_message("user" if row["role"] == "user" else "assistant"):
        st.write(row["message"])
        if row["role"] == "mentor" and st.button(
            "Save as note", key=f"mentor_note_{row['message_id']}"
        ):
            if module_id:
                save_note(
                    connection, user_id, module_id, None,
                    "Today Learning", "Mentor guidance",
                    "AI Mentor guidance", row["message"], "mentor",
                )
                st.success("Mentor guidance saved to Notes.")

with st.expander("Recent Academy evidence"):
    st.write(
        f"Completion: {context.progress['overall']['completion_percentage']}% · "
        f"Recent activity: {len(context.recent_activity)} item(s) · "
        f"Upcoming: {len(context.upcoming_sessions)} · Missed: {len(context.missed_sessions)}"
    )
    st.caption("The Mentor uses this evidence and will say when information is unavailable.")

with st.expander("Conversation history"):
    for item in repo.list_conversations(connection, user_id):
        st.caption(f"{item['title']} · {item['updated_at']}")
    if st.button("Start new conversation"):
        st.session_state.mentor_conversation_id = repo.create_conversation(connection, user_id)
        st.rerun()
