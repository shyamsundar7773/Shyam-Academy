import streamlit as st
from auth.session import require_current_user

from ai.orchestrator import AdvancedAIOrchestrator
from ai.settings import get_settings
from ai.task_repository import list_proposals
from database.connection import get_connection
from models.ai import AITaskType, ProposalStatus

connection = get_connection()
user_id = require_current_user().user_id
orchestrator = AdvancedAIOrchestrator(connection)

st.title("AI Assistant")
st.caption("Bounded, evidence-based assistance. Persistent changes always require approval.")

settings = get_settings(connection, user_id)
if not settings["enabled"]:
    st.warning("Advanced AI assistance is disabled in Settings.")
else:
    labels = {
        AITaskType.LEARNING_ASSIST: "Ask about learning",
        AITaskType.STUDY_PLAN: "Plan my study",
        AITaskType.PROGRESS_ANALYSIS: "Analyze my progress",
        AITaskType.WEAK_AREA_ANALYSIS: "Explain my weak areas",
        AITaskType.TEST_PREPARATION: "Prepare for a test",
        AITaskType.INTERVIEW_COACHING: "Prepare for interview",
        AITaskType.CAREER_GUIDANCE: "Career guidance",
        AITaskType.ROUTINE_ANALYSIS: "Review my routines",
        AITaskType.DAILY_PLAN: "Create a daily plan",
        AITaskType.GENERAL_ACADEMIC_ASSIST: "General academic assistance",
    }
    with st.form("advanced_ai_request"):
        task_type = st.selectbox("Assistance type", list(labels), format_func=labels.get)
        request = st.text_area("What would you like help with?", height=120)
        ask = st.form_submit_button("Ask AI", type="primary")
    if ask:
        try:
            _, response = orchestrator.run(user_id, task_type, request)
            st.session_state.ai_last_response = response
        except Exception as error:
            st.error(str(error))

if st.session_state.get("ai_last_response"):
    response = st.session_state.ai_last_response
    st.subheader("Answer")
    st.write(response.answer)
    if response.evidence:
        st.subheader("Evidence used")
        for item in response.evidence:
            st.write(f"- {item}")
    if response.suggested_actions:
        st.subheader("Suggested actions")
        for item in response.suggested_actions:
            st.write(f"- {item}")

st.subheader("Voice-ready boundaries")
st.info("Voice input — Not configured")
st.info("Voice output — Not configured")

st.subheader("Pending action proposals")
for proposal in orchestrator.history(user_id, 20):
    for item in [p for p in list_proposals(connection, user_id, 100)
                 if p.task_id == proposal.task_id and p.status == ProposalStatus.PENDING]:
        with st.container(border=True):
            st.write(item.summary)
            left, right = st.columns(2)
            if left.button("Approve", key=f"approve_{item.proposal_id}"):
                orchestrator.approve_proposal(user_id, item.proposal_id)
                st.rerun()
            if right.button("Reject", key=f"reject_{item.proposal_id}"):
                orchestrator.reject_proposal(user_id, item.proposal_id)
                st.rerun()
for item in [p for p in list_proposals(connection, user_id, 100) if p.status == ProposalStatus.APPROVED]:
    with st.container(border=True):
        st.write(f"Approved: {item.summary}")
        if st.button("Execute approved action", key=f"execute_{item.proposal_id}"):
            try:
                orchestrator.execute_proposal(user_id, item.proposal_id)
                st.success("Action executed.")
                st.rerun()
            except Exception as error:
                st.error(str(error))

st.subheader("AI history")
for task in orchestrator.history(user_id, 20):
    st.caption(f"{task.task_type.value} · {task.created_at.isoformat()} · {task.status.value}")
