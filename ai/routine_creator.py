import json

from ai.gateway import AIGateway, AIProviderError
from services.routine_service import preview_natural_language


class RoutineCreatorService:
    """Provider-neutral preview boundary; fallback remains deterministic and local."""

    def __init__(self, gateway: AIGateway | None = None):
        self.gateway = gateway

    def preview(self, prompt: str):
        if not prompt or not prompt.strip():
            raise ValueError("Describe the routine first.")
        if self.gateway is not None:
            try:
                payload = self.gateway.generate_routine(prompt.strip())
                values = json.loads(payload)
                if not isinstance(values, dict):
                    raise ValueError("Routine provider returned an invalid preview.")
                return values
            except (AIProviderError, NotImplementedError, ValueError, json.JSONDecodeError):
                pass
        return preview_natural_language(prompt)
