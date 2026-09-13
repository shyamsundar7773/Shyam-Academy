import sys
import types

import pytest

from ai.gateway import get_gateway
from ai.providers.cloudflare_provider import CloudflareProvider, CloudflareProviderError
from config import bootstrap


AI_KEYS = {
    "SHYAM_ACADEMY_AI_PROVIDER": "cloudflare",
    "SHYAM_ACADEMY_AI_MODEL": "@cf/test-model",
    "SHYAM_ACADEMY_AI_API_KEY": "test-token",
    "SHYAM_ACADEMY_AI_BASE_URL": "https://example.com/v1",
    "SHYAM_ACADEMY_AI_ACCOUNT_REFERENCE": "test-account",
}


@pytest.fixture
def isolated_configuration(monkeypatch):
    for key in AI_KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(bootstrap, "_dotenv_configuration", lambda: {})


def fake_streamlit_secrets(values):
    return types.SimpleNamespace(secrets=values)


def test_environment_configuration_selects_cloudflare(monkeypatch, isolated_configuration):
    for key, value in AI_KEYS.items():
        monkeypatch.setenv(key, value)
    assert isinstance(get_gateway(), CloudflareProvider)


def test_local_dotenv_configuration_selects_cloudflare(
    monkeypatch, isolated_configuration
):
    monkeypatch.setattr(bootstrap, "_dotenv_configuration", lambda: AI_KEYS)
    monkeypatch.setattr(bootstrap, "_streamlit_secret_value", lambda key: None)
    assert isinstance(get_gateway(), CloudflareProvider)


def test_streamlit_secrets_configuration_selects_cloudflare(
    monkeypatch, isolated_configuration
):
    monkeypatch.setitem(sys.modules, "streamlit", fake_streamlit_secrets(AI_KEYS))
    assert isinstance(get_gateway(), CloudflareProvider)


def test_configuration_works_without_streamlit(monkeypatch, isolated_configuration):
    monkeypatch.setattr(bootstrap, "_streamlit_secret_value", lambda key: None)
    for key, value in AI_KEYS.items():
        monkeypatch.setenv(key, value)
    assert isinstance(get_gateway(), CloudflareProvider)


def test_environment_values_override_streamlit_secrets(
    monkeypatch, isolated_configuration
):
    secrets = dict(AI_KEYS)
    secrets["SHYAM_ACADEMY_AI_PROVIDER"] = "mock"
    monkeypatch.setitem(sys.modules, "streamlit", fake_streamlit_secrets(secrets))
    monkeypatch.setenv("SHYAM_ACADEMY_AI_PROVIDER", "cloudflare")
    for key, value in AI_KEYS.items():
        if key != "SHYAM_ACADEMY_AI_PROVIDER":
            monkeypatch.setenv(key, value)
    assert isinstance(get_gateway(), CloudflareProvider)


def test_missing_provider_preserves_mock_default(monkeypatch, isolated_configuration):
    monkeypatch.setitem(sys.modules, "streamlit", fake_streamlit_secrets({}))
    assert get_gateway().__class__.__name__ == "MockProvider"


def test_mock_provider_remains_explicit_option(monkeypatch, isolated_configuration):
    monkeypatch.setenv("SHYAM_ACADEMY_AI_PROVIDER", "mock")
    assert get_gateway().__class__.__name__ == "MockProvider"


def test_cloudflare_missing_key_does_not_fall_back(
    monkeypatch, isolated_configuration
):
    monkeypatch.setenv("SHYAM_ACADEMY_AI_PROVIDER", "cloudflare")
    monkeypatch.setenv("SHYAM_ACADEMY_AI_MODEL", "model")
    monkeypatch.setenv("SHYAM_ACADEMY_AI_BASE_URL", "https://example.com/v1")
    monkeypatch.setenv("SHYAM_ACADEMY_AI_ACCOUNT_REFERENCE", "account")
    with pytest.raises(CloudflareProviderError, match="token"):
        get_gateway()
