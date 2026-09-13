import json
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from ai.actions import AIActionRegistry
from ai.agent_registry import AIAgentRegistry
from ai.context import CrossSystemContextBuilder, build_context
from ai.daily_plan import create_daily_plan
from ai.interview_voice import InterviewVoiceBoundary
from ai.orchestrator import (
    AdvancedAIOrchestrator, AIResponseValidationError, validate_advanced_response,
)
from ai.policies import AIPolicyEngine, AIPolicyError
from ai.settings import get_settings, save_settings
from ai.task_repository import (
    add_audit, create_proposal, create_task, get_proposal, get_task, list_audit,
    list_proposals, list_tasks, update_proposal,
)
from ai.tools import AIToolRegistry
from ai.voice import (
    MockSpeechToTextProvider, MockTextToSpeechProvider, UnconfiguredSpeechToTextProvider,
    VoiceStatus, voice_lifecycle,
)
from database.schema import initialize_database
from models.ai import AITaskStatus, AITaskType, ProposalStatus
from services.module_service import add_module
from services.timetable_service import add_session


@pytest.fixture
def connection():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    initialize_database(db)
    return db


class Gateway:
    def __init__(self, value=None, error=None):
        self.value = value or json.dumps({
            "answer": "Bounded answer.",
            "evidence": ["progress"],
            "suggested_actions": ["review"],
            "proposals": [],
        })
        self.error = error
        self.calls = 0

    def generate_advanced(self, task_type, prompt):
        self.calls += 1
        if self.error:
            raise self.error
        return self.value


def setup_plan(connection, user="u"):
    module = add_module(connection, "SQL", "plan", user)
    session = add_session(connection, module, 1, "2026-09-20", "Level 1",
                           "Joins", "10:00 AM", "Teach joins", user)
    return module, session


def run_task(connection, task_type=AITaskType.GENERAL_ACADEMIC_ASSIST,
             user="u", gateway=None, request="help"):
    if gateway is None:
        from ai.gateway import get_gateway
        gateway = get_gateway()
    return AdvancedAIOrchestrator(connection, gateway or Gateway()).run(
        user, task_type, request
    )


def test_ai_schema_tables(connection):
    names = {r["name"] for r in connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"ai_tasks", "ai_action_proposals", "ai_audit_log", "ai_user_settings"} <= names


def test_task_creation(connection):
    task = create_task(connection, "u", AITaskType.LEARNING_ASSIST, "learning_coach", "x")
    assert task.status == AITaskStatus.CREATED


def test_task_type_validation(connection):
    with pytest.raises(ValueError):
        create_task(connection, "u", "UNKNOWN", "learning_coach")


def test_task_lifecycle(connection):
    task, response = run_task(connection)
    assert task.status == AITaskStatus.COMPLETED and response.answer


def test_task_persistence(connection):
    task, _ = run_task(connection)
    assert get_task(connection, task.task_id, "u").task_id == task.task_id


def test_task_user_isolation(connection):
    task, _ = run_task(connection, user="a")
    assert get_task(connection, task.task_id, "b") is None
    assert list_tasks(connection, "b") == []


def test_task_history_bounded(connection):
    for _ in range(4):
        run_task(connection)
    assert len(list_tasks(connection, "u", 2)) == 2


def test_context_builder_identity(connection):
    context = build_context(connection, "u", "GENERAL")
    assert context.user_id == "u"


def test_context_rejects_mismatched_identity(connection):
    with pytest.raises(PermissionError):
        build_context(connection, "a", "GENERAL", authenticated_user_id="b")


def test_context_builder_facade(connection):
    assert CrossSystemContextBuilder(connection, "u").build("u", "GENERAL").user_id == "u"


def test_context_bounds(connection):
    module, _ = setup_plan(connection)
    context = build_context(connection, "u", "GENERAL", module_id=module,
                            limits={"timetable": 1})
    assert len(context.timetable) <= 1


def test_timetable_context(connection):
    module, _ = setup_plan(connection)
    context = build_context(connection, "u", "GENERAL", module_id=module)
    assert context.timetable[0]["topic"] == "Joins"


def test_learning_context(connection):
    context = build_context(connection, "u", "GENERAL")
    assert "pending_sessions" in context.learning


def test_notes_context(connection):
    assert isinstance(build_context(connection, "u", "GENERAL").notes, tuple)


def test_attendance_context(connection):
    assert isinstance(build_context(connection, "u", "GENERAL").attendance, tuple)


def test_tests_context(connection):
    assert isinstance(build_context(connection, "u", "GENERAL").tests, tuple)


def test_interview_context(connection):
    assert isinstance(build_context(connection, "u", "GENERAL").interviews, tuple)


def test_progress_context(connection):
    assert "overall" in build_context(connection, "u", "GENERAL").progress


def test_mentor_context(connection):
    assert isinstance(build_context(connection, "u", "GENERAL").mentor, tuple)


def test_routine_context(connection):
    assert isinstance(build_context(connection, "u", "GENERAL").routines, tuple)


def test_notification_context(connection):
    assert isinstance(build_context(connection, "u", "GENERAL").notifications, tuple)


def test_context_excludes_other_user(connection):
    setup_plan(connection, "a")
    setup_plan(connection, "b")
    context = build_context(connection, "a", "GENERAL")
    assert all(row["module_name"] == "SQL" for row in context.timetable)


def test_tool_registry_names():
    names = AIToolRegistry().names()
    assert "get_current_session" in names and "get_weak_areas" in names


def test_tool_schema_validation(connection):
    with pytest.raises(ValueError):
        AIToolRegistry().invoke("get_today_timetable", connection, "u", {"limit": "bad"})


def test_tool_unknown_rejected(connection):
    with pytest.raises(ValueError):
        AIToolRegistry().invoke("missing", connection, "u")


def test_tool_authorized_scope(connection):
    module, session = setup_plan(connection, "a")
    assert AIToolRegistry().invoke("get_current_session", connection, "a",
                                   {"session_id": session})["topic"] == "Joins"


def test_tool_cross_user_rejected(connection):
    _, session = setup_plan(connection, "a")
    assert AIToolRegistry().invoke("get_current_session", connection, "b",
                                   {"session_id": session}) is None


def test_tool_weak_areas_structured(connection):
    assert isinstance(AIToolRegistry().invoke("get_weak_areas", connection, "u"), list)


def test_action_registry_names():
    assert {"CREATE_NOTE", "CREATE_ROUTINE_PROPOSAL"} <= set(AIActionRegistry().names())


def test_action_schema_validation():
    with pytest.raises(ValueError):
        AIActionRegistry().get("CREATE_NOTE").validate({"module_id": "bad"})


def test_action_requires_confirmation():
    assert AIActionRegistry().get("CREATE_NOTE").requires_confirmation


def test_agent_registry_roles():
    assert len(AIAgentRegistry().list()) >= 5


def test_agent_permissions():
    agent = AIAgentRegistry().get("study_planner")
    assert agent.can_tool("get_today_timetable")
    assert not agent.can_tool("get_notifications")


def test_agent_task_permissions():
    assert AIAgentRegistry().default_for(AITaskType.DAILY_PLAN).agent_id == "study_planner"


def test_policy_identity():
    AIPolicyEngine(AIAgentRegistry(), AIToolRegistry(), AIActionRegistry()).validate_identity("u", "u")


def test_policy_rejects_identity():
    with pytest.raises(AIPolicyError):
        AIPolicyEngine(AIAgentRegistry(), AIToolRegistry(), AIActionRegistry()).validate_identity("u", "b")


def test_policy_rejects_agent_task():
    policy = AIPolicyEngine(AIAgentRegistry(), AIToolRegistry(), AIActionRegistry())
    with pytest.raises(AIPolicyError):
        policy.validate_task("u", AITaskType.ROUTINE_ANALYSIS, "learning_coach")


def test_policy_rejects_tool():
    policy = AIPolicyEngine(AIAgentRegistry(), AIToolRegistry(), AIActionRegistry())
    with pytest.raises(AIPolicyError):
        policy.validate_tool(AIAgentRegistry().get("study_planner"), "get_notifications")


def test_policy_rejects_action():
    policy = AIPolicyEngine(AIAgentRegistry(), AIToolRegistry(), AIActionRegistry())
    with pytest.raises(AIPolicyError):
        policy.validate_action(AIAgentRegistry().get("study_planner"), "CREATE_NOTE")


def test_proposal_creation(connection):
    task = create_task(connection, "u", AITaskType.STUDY_PLAN, "study_planner")
    proposal = create_proposal(connection, task.task_id, "u", "study_planner",
                               "CREATE_STUDY_PLAN_PROPOSAL", "review", {"title": "x", "plan": []})
    assert proposal.status == ProposalStatus.PENDING


def test_proposal_persistence(connection):
    task = create_task(connection, "u", AITaskType.STUDY_PLAN, "study_planner")
    proposal = create_proposal(connection, task.task_id, "u", "study_planner",
                               "CREATE_STUDY_PLAN_PROPOSAL", "review", {"title": "x", "plan": []})
    assert get_proposal(connection, proposal.proposal_id, "u").proposal_id == proposal.proposal_id


def test_proposal_approval(connection):
    _, response = run_task(connection, AITaskType.DAILY_PLAN)
    proposal = response.proposals[0]
    assert AdvancedAIOrchestrator(connection).approve_proposal("u", proposal.proposal_id).status == ProposalStatus.APPROVED


def test_proposal_rejection(connection):
    _, response = run_task(connection, AITaskType.DAILY_PLAN)
    proposal = response.proposals[0]
    assert AdvancedAIOrchestrator(connection).reject_proposal("u", proposal.proposal_id).status == ProposalStatus.REJECTED


def test_proposal_expiration(connection):
    task = create_task(connection, "u", AITaskType.STUDY_PLAN, "study_planner")
    proposal = create_proposal(connection, task.task_id, "u", "study_planner",
                               "CREATE_STUDY_PLAN_PROPOSAL", "old", {"title": "x", "plan": []},
                               expires_at=(datetime.now(timezone.utc) - timedelta(hours=1)).isoformat())
    with pytest.raises(AIPolicyError):
        AdvancedAIOrchestrator(connection).approve_proposal("u", proposal.proposal_id)


def test_duplicate_approval_is_idempotent(connection):
    _, response = run_task(connection, AITaskType.DAILY_PLAN)
    orchestrator = AdvancedAIOrchestrator(connection)
    first = orchestrator.approve_proposal("u", response.proposals[0].proposal_id)
    second = orchestrator.approve_proposal("u", response.proposals[0].proposal_id)
    assert first.proposal_id == second.proposal_id


def test_action_execution(connection):
    _, response = run_task(connection, AITaskType.DAILY_PLAN)
    orchestrator = AdvancedAIOrchestrator(connection)
    proposal = orchestrator.approve_proposal("u", response.proposals[0].proposal_id)
    assert orchestrator.execute_proposal("u", proposal.proposal_id)[0].status == ProposalStatus.EXECUTED


def test_action_cannot_execute_twice(connection):
    _, response = run_task(connection, AITaskType.DAILY_PLAN)
    orchestrator = AdvancedAIOrchestrator(connection)
    proposal = orchestrator.approve_proposal("u", response.proposals[0].proposal_id)
    orchestrator.execute_proposal("u", proposal.proposal_id)
    with pytest.raises(AIPolicyError):
        orchestrator.execute_proposal("u", proposal.proposal_id)


def test_action_failure_is_recorded(connection):
    module, _ = setup_plan(connection)
    task = create_task(connection, "u", AITaskType.LEARNING_ASSIST, "learning_coach")
    proposal = create_proposal(connection, task.task_id, "u", "learning_coach", "CREATE_NOTE",
                               "bad", {"module_id": module, "category": "", "topic": "x",
                                       "title": "x", "content": "x"})
    orchestrator = AdvancedAIOrchestrator(connection)
    orchestrator.approve_proposal("u", proposal.proposal_id)
    with pytest.raises(ValueError):
        orchestrator.execute_proposal("u", proposal.proposal_id)
    assert get_proposal(connection, proposal.proposal_id, "u").status == ProposalStatus.FAILED


def test_audit_logging(connection):
    task = create_task(connection, "u", AITaskType.LEARNING_ASSIST, "learning_coach")
    event = add_audit(connection, task.task_id, "u", "learning_coach", "TEST", "OK")
    assert event.result_status == "OK"


def test_audit_isolation(connection):
    task = create_task(connection, "u", AITaskType.LEARNING_ASSIST, "learning_coach")
    with pytest.raises(ValueError):
        add_audit(connection, task.task_id, "b", "learning_coach", "TEST", "OK")


def test_provider_routing(connection):
    gateway = Gateway()
    run_task(connection, gateway=gateway)
    assert gateway.calls == 1


def test_provider_unavailable(connection):
    with pytest.raises(Exception, match="unavailable"):
        run_task(connection, gateway=Gateway(error=RuntimeError("down")))


def test_bounded_retry(connection):
    gateway = Gateway(error=RuntimeError("down"))
    with pytest.raises(Exception):
        AdvancedAIOrchestrator(connection, gateway, max_retries=10).run("u", AITaskType.LEARNING_ASSIST, "x")
    assert gateway.calls == 3


def test_malformed_ai_output(connection):
    with pytest.raises(AIResponseValidationError):
        run_task(connection, gateway=Gateway("bad"))


def test_invalid_action_output(connection):
    value = json.dumps({"answer": "x", "proposals": [{"action_type": "SHELL", "payload": {}}]})
    with pytest.raises(AIResponseValidationError):
        run_task(connection, gateway=Gateway(value))


def test_invalid_ids_are_rejected(connection):
    with pytest.raises(ValueError):
        create_task(connection, "", AITaskType.LEARNING_ASSIST, "learning_coach")


def test_daily_plan(connection):
    task, response = create_daily_plan(AdvancedAIOrchestrator(connection), "u")
    assert task.task_type == AITaskType.DAILY_PLAN and response.proposals


def test_daily_plan_is_not_timetable_mutation(connection):
    setup_plan(connection)
    before = connection.execute("SELECT COUNT(*) c FROM sessions").fetchone()["c"]
    run_task(connection, AITaskType.DAILY_PLAN)
    after = connection.execute("SELECT COUNT(*) c FROM sessions").fetchone()["c"]
    assert before == after


def test_routine_proposal_is_explicit(connection):
    _, response = run_task(connection, AITaskType.ROUTINE_ANALYSIS)
    assert response.proposals[0].status == ProposalStatus.PENDING


def test_notification_preference_boundary(connection):
    connection.execute("INSERT INTO notification_preferences(user_id,notifications_enabled,updated_at) VALUES ('u',0,'x')")
    connection.commit()
    assert connection.execute("SELECT notifications_enabled FROM notification_preferences WHERE user_id='u'").fetchone()[0] == 0


def test_mentor_integration_helper(connection):
    from services.mentor_service import advanced_mentor_assist
    _, response = advanced_mentor_assist(connection, "u", "help")
    assert response.answer


def test_progress_ai_metrics_separate(connection):
    from services.progress_service import get_ai_assistance_metrics, get_progress_snapshot
    before = get_progress_snapshot(connection, "u").overall.completed
    run_task(connection)
    assert get_progress_snapshot(connection, "u").overall.completed == before
    assert get_ai_assistance_metrics(connection, "u")["tasks"] == 1


def test_mock_ai_provider():
    from ai.gateway import get_gateway
    assert json.loads(get_gateway().generate_advanced("GENERAL_ACADEMIC_ASSIST", "{}"))["answer"]


def test_speech_to_text_mock():
    result = MockSpeechToTextProvider("hello").transcribe(b"audio")
    assert result.status == VoiceStatus.READY and result.text == "hello"


def test_text_to_speech_mock():
    result = MockTextToSpeechProvider().synthesize("hello")
    assert result.status == VoiceStatus.READY and result.audio == b"hello"


def test_voice_input_not_configured():
    assert UnconfiguredSpeechToTextProvider().transcribe(b"x").status == VoiceStatus.NOT_CONFIGURED


def test_voice_lifecycle():
    result = voice_lifecycle(b"x", MockSpeechToTextProvider("ask"),
                             lambda text: f"answer:{text}", MockTextToSpeechProvider())
    assert result.status == VoiceStatus.READY and result.text == "answer:ask"


def test_interview_voice_boundary():
    boundary = InterviewVoiceBoundary(MockSpeechToTextProvider("answer"), MockTextToSpeechProvider())
    assert boundary.transcribe_answer(b"x").text == "answer"
    assert boundary.speak_feedback("good").status == VoiceStatus.READY


def test_ai_history(connection):
    run_task(connection)
    assert len(AdvancedAIOrchestrator(connection).history("u")) == 1


def test_settings_defaults(connection):
    assert get_settings(connection, "u")["voice_input_provider"] == "not_configured"


def test_settings_persistence(connection):
    value = save_settings(connection, "u", {"enabled": False, "preferred_model": "safe"})
    assert not value["enabled"] and value["preferred_model"] == "safe"


def test_settings_reject_secrets_field(connection):
    with pytest.raises(ValueError):
        save_settings(connection, "u", {"api_key": "secret"})


def test_migration_repeatable(connection):
    initialize_database(connection)
    assert connection.execute("SELECT 1 FROM ai_tasks").fetchone() is None


def test_response_validation_requires_answer():
    with pytest.raises(AIResponseValidationError):
        validate_advanced_response(json.dumps({"evidence": []}), AIActionRegistry(),
                                   AIAgentRegistry().get("learning_coach"))


def test_response_validation_rejects_nonlist_evidence():
    with pytest.raises(AIResponseValidationError):
        validate_advanced_response(json.dumps({"answer": "x", "evidence": "bad"}),
                                   AIActionRegistry(), AIAgentRegistry().get("learning_coach"))


def test_proposal_history_is_scoped(connection):
    _, response = run_task(connection, user="a", task_type=AITaskType.DAILY_PLAN)
    assert list_proposals(connection, "b") == []
    assert list_proposals(connection, "a") == list(response.proposals)
