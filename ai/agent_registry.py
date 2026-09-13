"""Logical agent roles with centrally enforced capabilities."""

from dataclasses import dataclass

from models.ai import AITaskType


@dataclass(frozen=True)
class AIAgent:
    agent_id: str
    name: str
    description: str
    capabilities: tuple[str, ...]
    allowed_tools: tuple[str, ...]
    allowed_actions: tuple[str, ...]
    task_types: tuple[AITaskType, ...]
    enabled: bool = True

    def can_task(self, task_type) -> bool:
        value = task_type if isinstance(task_type, AITaskType) else AITaskType(str(task_type))
        return self.enabled and value in self.task_types

    def can_tool(self, tool: str) -> bool:
        return self.enabled and tool in self.allowed_tools

    def can_action(self, action: str) -> bool:
        return self.enabled and action in self.allowed_actions


def _agent(agent_id, name, description, tools, actions, tasks, capabilities):
    return AIAgent(agent_id, name, description, tuple(capabilities), tuple(tools),
                   tuple(actions), tuple(AITaskType(x) for x in tasks))


class AIAgentRegistry:
    def __init__(self):
        common = ("get_recent_progress", "get_weak_areas", "get_notes")
        self._agents = {
            "study_planner": _agent(
                "study_planner", "Study Planner Agent", "Prepares bounded study plans.",
                ("get_today_timetable", *common), ("CREATE_STUDY_PLAN_PROPOSAL",),
                ("STUDY_PLAN", "DAILY_PLAN", "TEST_PREPARATION", "GENERAL_ACADEMIC_ASSIST"),
                ("planning", "recommendations"),
            ),
            "learning_coach": _agent(
                "learning_coach", "Learning Coach Agent", "Explains authorized learning context.",
                ("get_current_session", "get_today_timetable", "get_notes", "get_recent_progress"),
                ("CREATE_NOTE",), ("LEARNING_ASSIST", "GENERAL_ACADEMIC_ASSIST"),
                ("explanations", "learning_support"),
            ),
            "progress_analyst": _agent(
                "progress_analyst", "Progress Analyst Agent", "Analyzes progress and weak areas.",
                ("get_recent_progress", "get_weak_areas", "get_recent_tests",
                 "get_interview_history", "get_today_timetable"),
                ("CREATE_MENTOR_RECOMMENDATION",),
                ("PROGRESS_ANALYSIS", "WEAK_AREA_ANALYSIS"),
                ("analysis", "evidence"),
            ),
            "interview_coach": _agent(
                "interview_coach", "Interview Coach Agent", "Prepares safe interview practice.",
                ("get_interview_history", "get_weak_areas", "get_recent_progress"),
                ("CREATE_MENTOR_RECOMMENDATION",),
                ("INTERVIEW_COACHING", "CAREER_GUIDANCE"),
                ("interview_practice", "coaching"),
            ),
            "routine_coach": _agent(
                "routine_coach", "Routine Coach Agent", "Analyzes routine consistency without medical advice.",
                ("get_today_routines", "get_recent_routine_history", "get_today_timetable"),
                ("CREATE_ROUTINE_PROPOSAL",),
                ("ROUTINE_ANALYSIS", "DAILY_PLAN"),
                ("routine_analysis", "schedule_conflicts"),
            ),
        }

    def get(self, agent_id: str) -> AIAgent:
        try:
            return self._agents[agent_id]
        except KeyError as exc:
            raise ValueError("Unknown AI agent.") from exc

    def list(self):
        return tuple(self._agents.values())

    def default_for(self, task_type) -> AIAgent:
        value = task_type if isinstance(task_type, AITaskType) else AITaskType(str(task_type))
        for agent in self._agents.values():
            if agent.can_task(value):
                return agent
        raise ValueError("No enabled AI agent supports this task type.")


AgentRegistry = AIAgentRegistry
