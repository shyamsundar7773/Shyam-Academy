from dataclasses import dataclass


class AIProviderError(RuntimeError):
    """An expected provider/configuration failure safe to show to the user."""


@dataclass(frozen=True)
class ClassroomContext:
    user_id: str
    module_id: int
    session_id: int
    category: str
    topic: str
    session_date: str
    scheduled_time: str
    session_prompt: str


class AIGateway:
    """Provider-neutral interface for explicitly requested classroom actions."""

    def generate_timetable(self, prompt: str) -> str:
        raise NotImplementedError(
            "AI timetable generation is not enabled in this phase."
        )

    def generate_advanced(self, task_type: str, prompt: str) -> str:
        raise NotImplementedError

    def generate_routine(self, prompt: str) -> str:
        raise NotImplementedError

    def generate_test(self, prompt: str) -> str:
        raise NotImplementedError

    def evaluate_test_answer(self, prompt: str) -> str:
        raise NotImplementedError

    def generate_interview(self, prompt: str) -> str:
        raise NotImplementedError

    def evaluate_interview(self, prompt: str) -> str:
        raise NotImplementedError

    def interview_action(self, prompt: str) -> str:
        raise NotImplementedError

    def mentor_response(self, prompt: str) -> str:
        raise NotImplementedError

    def generate_lesson(self, prompt: str, context: ClassroomContext) -> str:
        raise NotImplementedError

    def ask_followup(
        self, prompt: str, context: ClassroomContext, lesson: str, history: list[dict]
    ) -> str:
        raise NotImplementedError

    def generate_explanation(
        self, context: ClassroomContext, lesson: str
    ) -> str:
        raise NotImplementedError

    def generate_example(self, context: ClassroomContext, lesson: str) -> str:
        raise NotImplementedError


class TimetableGenerationService:
    """Boundary for a future free-form timetable generation workflow."""

    def __init__(self, gateway: AIGateway):
        self.gateway = gateway

    def create_from_prompt(self, prompt: str) -> str:
        if not prompt.strip():
            raise ValueError("Describe the timetable you want first.")
        return self.gateway.generate_timetable(prompt.strip())


class UnconfiguredGateway(AIGateway):
    def _unavailable(self):
        raise AIProviderError("AI provider is not configured yet.")

    def generate_timetable(self, prompt):
        self._unavailable()

    def generate_advanced(self, task_type, prompt):
        self._unavailable()

    def generate_test(self, prompt):
        self._unavailable()

    def evaluate_test_answer(self, prompt):
        self._unavailable()

    def generate_interview(self, prompt):
        self._unavailable()

    def evaluate_interview(self, prompt):
        self._unavailable()

    def interview_action(self, prompt):
        self._unavailable()

    def mentor_response(self, prompt):
        self._unavailable()

    def generate_lesson(self, prompt, context):
        self._unavailable()

    def ask_followup(self, prompt, context, lesson, history):
        self._unavailable()

    def generate_explanation(self, context, lesson):
        self._unavailable()

    def generate_example(self, context, lesson):
        self._unavailable()


def get_gateway() -> AIGateway:
    import os
    from ai.providers.mock_provider import MockProvider
    from config.bootstrap import load_environment
    load_environment()
    provider = os.getenv("SHYAM_ACADEMY_AI_PROVIDER", "mock").strip().lower()

    if provider in {"mock", "development"}:
        return MockProvider()
    if provider == "cloudflare":
        from ai.providers.cloudflare_provider import CloudflareProvider
        return CloudflareProvider()
    if provider in {"openai", "real", "openai-compatible"}:
        from ai.providers.real_provider import RealProvider
        return RealProvider()
    return UnconfiguredGateway()
