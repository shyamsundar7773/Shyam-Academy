"""Deterministic safety policy for AI tools, tasks, proposals, and actions."""

from datetime import datetime, timezone

from models.ai import ProposalStatus, coerce_task_type


class AIPolicyError(PermissionError):
    pass


class AIPolicyEngine:
    def __init__(self, agents, tools, actions):
        self.agents = agents
        self.tools = tools
        self.actions = actions

    def validate_identity(self, user_id: str, authenticated_user_id: str | None = None):
        if not isinstance(user_id, str) or not user_id.strip():
            raise AIPolicyError("Invalid user identity.")
        if authenticated_user_id is not None and user_id != authenticated_user_id:
            raise AIPolicyError("User identity is not authorized.")

    def validate_task(self, user_id, task_type, agent_id, authenticated_user_id=None):
        self.validate_identity(user_id, authenticated_user_id)
        task = coerce_task_type(task_type)
        agent = self.agents.get(agent_id)
        if not agent.can_task(task):
            raise AIPolicyError("Agent is not authorized for this task type.")
        return task, agent

    def validate_tool(self, agent, tool_name):
        if not agent.can_tool(tool_name):
            raise AIPolicyError("Agent is not authorized to use this tool.")
        self.tools.get(tool_name)

    def validate_action(self, agent, action_name, requires_confirmation=True):
        if not agent.can_action(action_name):
            raise AIPolicyError("Agent is not authorized for this action.")
        action = self.actions.get(action_name)
        if requires_confirmation and not action.requires_confirmation:
            return action
        if action.requires_confirmation and not requires_confirmation:
            raise AIPolicyError("Explicit confirmation is required for this action.")
        return action

    @staticmethod
    def validate_proposal(proposal, user_id, now=None):
        if proposal is None or proposal.user_id != user_id:
            raise AIPolicyError("Proposal is not authorized.")
        if proposal.status in {ProposalStatus.REJECTED, ProposalStatus.EXPIRED,
                               ProposalStatus.EXECUTED, ProposalStatus.FAILED}:
            raise AIPolicyError("Proposal cannot be executed in its current state.")
        now = now or datetime.now(timezone.utc)
        expires = proposal.expires_at
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if expires <= now:
            raise AIPolicyError("Proposal has expired.")


PolicyEngine = AIPolicyEngine
