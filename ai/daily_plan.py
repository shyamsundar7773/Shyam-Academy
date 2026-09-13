"""Daily AI plan workflow. Plans are proposals and never rewrite authoritative schedules."""

from ai.orchestrator import AdvancedAIOrchestrator
from models.ai import AITaskType


def create_daily_plan(orchestrator: AdvancedAIOrchestrator, user_id: str,
                      request: str = "Create a bounded plan for today.",
                      **kwargs):
    return orchestrator.run(user_id, AITaskType.DAILY_PLAN, request, **kwargs)
