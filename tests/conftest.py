import pytest


@pytest.fixture(autouse=True)
def isolate_default_ai_provider(monkeypatch):
    """Keep the automated suite deterministic; live-provider tests opt in explicitly."""
    monkeypatch.setenv("SHYAM_ACADEMY_AI_PROVIDER", "mock")
    monkeypatch.setenv("SHYAM_ACADEMY_AI_MODEL", "development-classroom")
