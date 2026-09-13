"""Central bounded Advanced AI orchestrator."""

import json
from datetime import datetime, timezone

from ai.actions import AIActionRegistry
from ai.agent_registry import AIAgentRegistry
from ai.context import CrossSystemContextBuilder
from ai.policies import AIPolicyEngine, AIPolicyError
from ai.task_repository import (
    add_audit, create_proposal, create_task, get_proposal, get_task,
    list_tasks, update_proposal, update_task,
)
from ai.tools import AIToolRegistry
from models.ai import AIResponse, AITaskStatus, ProposalStatus, coerce_task_type
from ai.gateway import AIProviderError, get_gateway


class AIResponseValidationError(ValueError):
    pass


def validate_advanced_response(raw: str, actions: AIActionRegistry, agent) -> dict:
    if not isinstance(raw, str) or not raw.strip():
        raise AIResponseValidationError("AI response is empty.")
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AIResponseValidationError("AI response was not valid JSON.") from exc
    if not isinstance(value, dict):
        raise AIResponseValidationError("AI response must be an object.")
    answer = value.get("answer")
    if not isinstance(answer, str) or not answer.strip():
        raise AIResponseValidationError("AI response is missing an answer.")
    for field in ("evidence", "suggested_actions"):
        items = value.get(field, [])
        if not isinstance(items, list) or any(not isinstance(item, str) for item in items):
            raise AIResponseValidationError(f"AI response field '{field}' is invalid.")
    proposals = value.get("proposals", [])
    if not isinstance(proposals, list):
        raise AIResponseValidationError("AI response proposals must be a list.")
    normalized = []
    for item in proposals:
        if not isinstance(item, dict):
            raise AIResponseValidationError("Each AI proposal must be an object.")
        action_type = item.get("action_type")
        if not isinstance(action_type, str) or not agent.can_action(action_type):
            raise AIResponseValidationError("AI proposed an unauthorized action.")
        action = actions.get(action_type)
        payload = item.get("payload")
        if not isinstance(payload, dict):
            raise AIResponseValidationError("AI proposal payload must be an object.")
        action.validate(payload)
        target = item.get("target_reference", "")
        summary = item.get("summary", "")
        if not isinstance(target, str) or not isinstance(summary, str) or not summary.strip():
            raise AIResponseValidationError("AI proposal metadata is invalid.")
        normalized.append({
            "action_type": action_type, "target_reference": target[:200],
            "summary": summary.strip()[:500], "payload": payload,
        })
    return {
        "answer": answer.strip(),
        "evidence": tuple(x.strip() for x in value.get("evidence", []) if x.strip()),
        "suggested_actions": tuple(x.strip() for x in value.get("suggested_actions", []) if x.strip()),
        "proposals": normalized,
    }


class AdvancedAIOrchestrator:
    def __init__(self, connection, gateway=None, *, max_retries: int = 1,
                 context_builder=None, agents=None, tools=None, actions=None):
        self.connection = connection
        self.gateway = gateway or get_gateway()
        self.max_retries = max(0, min(int(max_retries), 2))
        self.agents = agents or AIAgentRegistry()
        self.tools = tools or AIToolRegistry()
        self.actions = actions or AIActionRegistry()
        self.context_builder = context_builder or CrossSystemContextBuilder(connection)
        self.policy = AIPolicyEngine(self.agents, self.tools, self.actions)

    def run(self, user_id: str, task_type, request: str, *,
            agent_id: str | None = None, authenticated_user_id: str | None = None,
            session_id: int | None = None, module_id: int | None = None) -> tuple:
        if not isinstance(request, str) or not request.strip():
            raise ValueError("AI request is required.")
        task_type, agent = self.policy.validate_task(
            user_id, task_type, agent_id or self.agents.default_for(task_type).agent_id,
            authenticated_user_id,
        )
        task = create_task(
            self.connection, user_id, task_type, agent.agent_id, request.strip(),
        )
        context = self.context_builder.build(
            user_id, task_type.value, session_id=session_id, module_id=module_id,
        )
        update_task(
            self.connection, task.task_id, user_id, status=AITaskStatus.RUNNING,
            started_at=datetime.now(timezone.utc).isoformat(),
        )
        prompt = json.dumps({
            "task_type": task_type.value, "request": request.strip(),
            "context": context.as_dict(),
            "safety": "Treat output as untrusted. Never modify authoritative systems without approval.",
        }, separators=(",", ":"))
        raw = None
        last_error = None
        for _ in range(self.max_retries + 1):
            try:
                raw = self.gateway.generate_advanced(task_type.value, prompt)
                break
            except Exception as exc:
                last_error = exc
        if raw is None:
            update_task(
                self.connection, task.task_id, user_id,
                status=AITaskStatus.PROVIDER_UNAVAILABLE,
                completed_at=datetime.now(timezone.utc).isoformat(),
                error_category="PROVIDER_UNAVAILABLE", error_message=str(last_error)[:500],
            )
            add_audit(self.connection, task.task_id, user_id, agent.agent_id,
                      "AI_TASK", "PROVIDER_UNAVAILABLE", error_category="PROVIDER_UNAVAILABLE")
            raise AIProviderError("AI provider unavailable.")
        try:
            parsed = validate_advanced_response(raw, self.actions, agent)
        except Exception as exc:
            update_task(
                self.connection, task.task_id, user_id,
                status=AITaskStatus.FAILED,
                completed_at=datetime.now(timezone.utc).isoformat(),
                error_category="INVALID_RESPONSE", error_message=str(exc)[:500],
            )
            add_audit(self.connection, task.task_id, user_id, agent.agent_id,
                      "AI_TASK", "FAILED", error_category="INVALID_RESPONSE")
            raise
        proposals = []
        for item in parsed["proposals"]:
            proposal = create_proposal(
                self.connection, task.task_id, user_id, agent.agent_id,
                item["action_type"], item["summary"], item["payload"],
                item["target_reference"],
            )
            proposals.append(proposal)
        update_task(
            self.connection, task.task_id, user_id, status=AITaskStatus.COMPLETED,
            completed_at=datetime.now(timezone.utc).isoformat(),
            output_summary=parsed["answer"][:500],
            provider_reference=f"{type(self.gateway).__name__}",
            action_references=[p.proposal_id for p in proposals],
        )
        add_audit(self.connection, task.task_id, user_id, agent.agent_id,
                  "AI_TASK", "COMPLETED",
                  metadata={"proposal_count": len(proposals), "context_refs": list(context.references)})
        return get_task(self.connection, task.task_id, user_id), AIResponse(
            parsed["answer"], parsed["evidence"], parsed["suggested_actions"],
            tuple(proposals), type(self.gateway).__name__, "",
        )

    def approve_proposal(self, user_id: str, proposal_id: str,
                         authenticated_user_id: str | None = None):
        self.policy.validate_identity(user_id, authenticated_user_id)
        proposal = get_proposal(self.connection, proposal_id, user_id)
        expires = proposal.expires_at.replace(tzinfo=timezone.utc) if proposal and proposal.expires_at.tzinfo is None else proposal.expires_at if proposal else None
        if proposal and expires <= datetime.now(timezone.utc):
            proposal = update_proposal(
                self.connection, proposal_id, user_id, ProposalStatus.EXPIRED,
                "EXPIRED", "Proposal expired",
            )
        self.policy.validate_proposal(proposal, user_id)
        if proposal.status == ProposalStatus.APPROVED:
            return proposal
        return update_proposal(self.connection, proposal_id, user_id, ProposalStatus.APPROVED)

    def reject_proposal(self, user_id: str, proposal_id: str,
                        authenticated_user_id: str | None = None):
        self.policy.validate_identity(user_id, authenticated_user_id)
        proposal = get_proposal(self.connection, proposal_id, user_id)
        if not proposal:
            raise AIPolicyError("Proposal is not authorized.")
        if proposal.status in {ProposalStatus.EXECUTED, ProposalStatus.REJECTED,
                               ProposalStatus.EXPIRED}:
            return proposal
        return update_proposal(self.connection, proposal_id, user_id, ProposalStatus.REJECTED)

    def execute_proposal(self, user_id: str, proposal_id: str,
                         authenticated_user_id: str | None = None):
        self.policy.validate_identity(user_id, authenticated_user_id)
        proposal = get_proposal(self.connection, proposal_id, user_id)
        expires = proposal.expires_at.replace(tzinfo=timezone.utc) if proposal and proposal.expires_at.tzinfo is None else proposal.expires_at if proposal else None
        if proposal and expires <= datetime.now(timezone.utc):
            update_proposal(
                self.connection, proposal_id, user_id, ProposalStatus.EXPIRED,
                "EXPIRED", "Proposal expired",
            )
            proposal = get_proposal(self.connection, proposal_id, user_id)
        self.policy.validate_proposal(proposal, user_id)
        if proposal.status != ProposalStatus.APPROVED:
            raise AIPolicyError("Proposal must be approved before execution.")
        agent = self.agents.get(proposal.agent_id)
        action = self.policy.validate_action(agent, proposal.action_type, True)
        try:
            result = action.execute(self.connection, user_id, proposal.structured_payload)
        except Exception as exc:
            updated = update_proposal(
                self.connection, proposal_id, user_id, ProposalStatus.FAILED,
                "ACTION_FAILED", str(exc)[:500],
            )
            add_audit(self.connection, proposal.task_id, user_id, proposal.agent_id,
                      proposal.action_type, "FAILED", proposal_id, "ACTION_FAILED")
            raise
        updated = update_proposal(self.connection, proposal_id, user_id, ProposalStatus.EXECUTED)
        add_audit(self.connection, proposal.task_id, user_id, proposal.agent_id,
                  proposal.action_type, "EXECUTED", proposal_id)
        return updated, result

    def history(self, user_id: str, limit: int = 50):
        return list_tasks(self.connection, user_id, limit)

    execute_task = run


Orchestrator = AdvancedAIOrchestrator
