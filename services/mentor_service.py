import json
from dataclasses import asdict
from datetime import datetime

from ai.gateway import AIGateway, AIProviderError
from database.repositories import mentor_repository as repo
from database.repositories import progress_repository
from models.mentor import MENTOR_ACTIONS, MentorContext, MentorResponse
from services.mentor_recommendation_service import get_next_learning_recommendations
from services.progress_service import get_progress_snapshot


def _row_dict(row):
    return dict(row) if row is not None else {}


def _validate_action(action):
    if action not in MENTOR_ACTIONS:
        raise ValueError("Unsupported Mentor action.")


def build_mentor_context(connection, user_id, module_id=None, now=None):
    if not isinstance(user_id, str) or not user_id.strip():
        raise ValueError("A user identity is required for Mentor context.")
    now = now or datetime.now()
    snapshot = get_progress_snapshot(connection, user_id, module_id, now=now)
    sessions = progress_repository.list_sessions(connection, user_id, module_id)
    upcoming = []
    missed = []
    for row in sessions:
        item = _row_dict(row)
        status = row["attendance_status"]
        try:
            starts = datetime.strptime(
                f"{row['session_date']} {row['scheduled_time']}", "%Y-%m-%d %I:%M %p"
            )
        except (TypeError, ValueError):
            continue
        if status == "Missed" or (not status and starts <= now):
            missed.append(item)
        elif starts > now:
            upcoming.append(item)
    notes = [_row_dict(row) for row in progress_repository.list_notes(connection, user_id, module_id)[:5]]
    recommendations = get_next_learning_recommendations(snapshot, upcoming[:5], missed[:5])
    from database.repositories import routine_repository
    routine_rows = routine_repository.list_occurrences(
        connection, user_id,
        start=now.date().isoformat(),
        end=(now.date()).isoformat(),
    )
    routine_evidence = [
        {"routine_id": row["routine_id"], "date": row["occurrence_date"],
         "status": row["status"], "scheduled_at": row["scheduled_at"]}
        for row in routine_rows[:10]
    ]
    return MentorContext(
        user_id=user_id,
        module_id=module_id,
        progress=asdict(snapshot),
        upcoming_sessions=upcoming[:5],
        missed_sessions=missed[:5],
        recent_activity=snapshot.recent_activity[:10],
        notes=notes,
        recommendations=recommendations[:8],
        routine_evidence=routine_evidence,
    )


def compact_context(context):
    data = asdict(context)
    data["progress"].pop("modules", None)
    data["progress"].pop("categories", None)
    data["progress"].pop("topics", None)
    return data


def parse_mentor_response(response):
    if not isinstance(response, str) or not response.strip():
        raise ValueError("The Mentor returned an empty response.")
    try:
        raw = json.loads(response)
    except json.JSONDecodeError as error:
        raise ValueError("The Mentor response was not valid JSON.") from error
    if not isinstance(raw, dict):
        raise ValueError("The Mentor response must be an object.")
    text = raw.get("response")
    if not isinstance(text, str) or not text.strip():
        raise ValueError("The Mentor response is missing its message.")
    values = []
    for field in ("recommendations", "evidence", "next_actions"):
        value = raw.get(field, [])
        if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
            raise ValueError(f"The Mentor response field '{field}' is invalid.")
        values.append([item.strip() for item in value if item.strip()])
    return MentorResponse(text.strip(), *values)


def mentor_reply(gateway: AIGateway, context, user_message, history=None, action="GENERAL_GUIDANCE"):
    _validate_action(action)
    if not isinstance(user_message, str) or not user_message.strip():
        raise ValueError("Ask the Mentor a question first.")
    messages = history or []
    prompt = json.dumps({
        "action": action,
        "request": user_message.strip(),
        "context": compact_context(context),
        "conversation": messages[-8:],
        "safety": "Use only the evidence supplied. Say when data is unavailable. Do not claim guaranteed outcomes.",
    })
    try:
        return parse_mentor_response(gateway.mentor_response(prompt))
    except AIProviderError:
        raise
    except Exception as error:
        raise AIProviderError("The Mentor provider is currently unavailable.") from error


def create_conversation(connection, user_id, title="AI Mentor"):
    if not isinstance(user_id, str) or not user_id.strip():
        raise ValueError("A user identity is required.")
    return repo.create_conversation(connection, user_id, title)


def get_or_create_conversation(connection, user_id, conversation_id=None):
    if conversation_id and repo.get_conversation(connection, conversation_id, user_id):
        return conversation_id
    return create_conversation(connection, user_id)


def save_exchange(connection, conversation_id, user_id, question, response, action):
    user_message_id = repo.add_message(connection, conversation_id, user_id, "user", question, action)
    mentor_message_id = repo.add_message(
        connection, conversation_id, user_id, "mentor", response.response, action
    )
    return user_message_id, mentor_message_id


def mentor_event(context, recommendation):
    return {
        "event": "MentorRecommendationCreated",
        "user_id": context.user_id,
        "module_id": context.module_id,
        "topic": recommendation.topic,
        "priority": recommendation.priority,
        "evidence": recommendation.evidence,
        "created_at": datetime.now().isoformat(),
    }


def advanced_mentor_assist(connection, user_id, request, *, module_id=None,
                           authenticated_user_id=None):
    """Run Mentor-adjacent assistance through the Phase 12 boundary.

    Existing Mentor conversations and recommendations remain authoritative;
    this helper only records a bounded AI task and returns its evidence.
    """
    from ai.orchestrator import AdvancedAIOrchestrator
    from models.ai import AITaskType
    return AdvancedAIOrchestrator(connection).run(
        user_id, AITaskType.GENERAL_ACADEMIC_ASSIST, request,
        authenticated_user_id=authenticated_user_id, module_id=module_id,
        agent_id="learning_coach",
    )
