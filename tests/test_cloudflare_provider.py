import json
from urllib.error import HTTPError, URLError

import pytest

from ai.gateway import get_gateway
from ai.providers.cloudflare_provider import (
    CloudflareProvider,
    CloudflareProviderError,
    build_cloudflare_endpoint,
)


class Response:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return json.dumps(self.payload).encode()


def provider(**kwargs):
    return CloudflareProvider(
        api_key="token", model="@cf/test-model",
        base_url="https://api.cloudflare.com/client/v4/accounts/{ACCOUNT_ID}/ai/v1",
        account_id="account", **kwargs,
    )


def test_endpoint_resolves_account_and_path():
    assert build_cloudflare_endpoint(
        "https://api.cloudflare.com/client/v4/accounts/{ACCOUNT_ID}/ai/v1", "abc"
    ) == "https://api.cloudflare.com/client/v4/accounts/abc/ai/v1/chat/completions"


def test_endpoint_does_not_duplicate_chat_path():
    url = "https://api.cloudflare.com/client/v4/accounts/abc/ai/v1/chat/completions"
    assert build_cloudflare_endpoint(url, "abc") == url


def test_complete_endpoint_does_not_require_separate_account():
    url = "https://api.cloudflare.com/client/v4/accounts/abc/ai/v1/chat/completions"
    assert build_cloudflare_endpoint(url, None) == url


def test_endpoint_does_not_duplicate_v1():
    url = "https://api.cloudflare.com/client/v4/accounts/abc/ai/v1"
    assert build_cloudflare_endpoint(url, "abc").count("/v1") == 1


def test_missing_token():
    with pytest.raises(CloudflareProviderError, match="token"):
        CloudflareProvider(api_key="", model="m", base_url="https://example.com/v1", account_id="a")


def test_missing_account():
    with pytest.raises(CloudflareProviderError, match="Account ID"):
        CloudflareProvider(api_key="t", model="m", base_url="https://example.com/v1", account_id="")


def test_missing_model():
    with pytest.raises(CloudflareProviderError, match="model"):
        CloudflareProvider(api_key="t", model="", base_url="https://example.com/v1", account_id="a")


def test_invalid_endpoint():
    with pytest.raises(CloudflareProviderError, match="base URL"):
        CloudflareProvider(api_key="t", model="m", base_url="not-a-url", account_id="a")


def test_success_forwards_model_and_messages(monkeypatch):
    captured = {}

    def fake_urlopen(req, timeout):
        captured["url"] = req.full_url
        captured["payload"] = json.loads(req.data.decode())
        captured["auth"] = req.headers["Authorization"]
        return Response({"choices": [{"message": {"content": "answer"}}]})

    monkeypatch.setattr(
        "ai.providers.cloudflare_provider.request.urlopen", fake_urlopen
    )
    result = provider().generate_advanced("GENERAL", "hello")
    assert result == "answer"
    assert captured["payload"]["model"] == "@cf/test-model"
    assert captured["payload"]["messages"][0]["role"] == "system"
    assert captured["payload"]["messages"][1]["content"] == "hello"
    assert captured["url"].endswith("/chat/completions")
    assert captured["auth"] == "Bearer token"


def test_sequential_requests_return_non_empty_content(monkeypatch):
    calls = []

    def fake_urlopen(req, timeout):
        prompt = json.loads(req.data.decode())["messages"][-1]["content"]
        calls.append(prompt)
        return Response({"choices": [{"message": {"content": f"reply:{prompt}"}}]})

    monkeypatch.setattr("ai.providers.cloudflare_provider.request.urlopen", fake_urlopen)
    cloudflare = provider()
    results = [
        cloudflare.generate_timetable("SHYAM_GATEWAY_TEST_1"),
        cloudflare.generate_timetable("SHYAM_GATEWAY_TEST_2"),
        cloudflare.generate_timetable("SHYAM_GATEWAY_TEST_3"),
    ]
    assert calls == ["SHYAM_GATEWAY_TEST_1", "SHYAM_GATEWAY_TEST_2", "SHYAM_GATEWAY_TEST_3"]
    assert all(result.strip() for result in results)


@pytest.mark.parametrize("code, message", [
    (401, "authentication"),
    (403, "not authorized"),
    (404, "not found"),
    (429, "rate limit"),
])
def test_http_errors_are_classified(monkeypatch, code, message):
    error = HTTPError("url", code, "provider", {}, None)
    monkeypatch.setattr(
        "ai.providers.cloudflare_provider.request.urlopen",
        lambda req, timeout: (_ for _ in ()).throw(error),
    )
    with pytest.raises(CloudflareProviderError, match=message):
        provider().generate_advanced("GENERAL", "hello")


def test_network_error(monkeypatch):
    monkeypatch.setattr(
        "ai.providers.cloudflare_provider.request.urlopen",
        lambda req, timeout: (_ for _ in ()).throw(URLError("offline")),
    )
    with pytest.raises(CloudflareProviderError, match="network"):
        provider().generate_advanced("GENERAL", "hello")


def test_timeout_error(monkeypatch):
    monkeypatch.setattr(
        "ai.providers.cloudflare_provider.request.urlopen",
        lambda req, timeout: (_ for _ in ()).throw(TimeoutError()),
    )
    with pytest.raises(CloudflareProviderError, match="network"):
        provider().generate_advanced("GENERAL", "hello")


def test_malformed_json(monkeypatch):
    class Bad(Response):
        def read(self):
            return b"{bad"

    monkeypatch.setattr(
        "ai.providers.cloudflare_provider.request.urlopen", lambda req, timeout: Bad({})
    )
    with pytest.raises(CloudflareProviderError, match="malformed JSON"):
        provider().generate_advanced("GENERAL", "hello")


def test_malformed_response(monkeypatch):
    monkeypatch.setattr(
        "ai.providers.cloudflare_provider.request.urlopen",
        lambda req, timeout: Response({"result": {}}),
    )
    with pytest.raises(CloudflareProviderError, match="malformed response"):
        provider().generate_advanced("GENERAL", "hello")


def test_empty_response(monkeypatch):
    monkeypatch.setattr(
        "ai.providers.cloudflare_provider.request.urlopen",
        lambda req, timeout: Response({"choices": [{"message": {"content": ""}}]}),
    )
    with pytest.raises(CloudflareProviderError, match="empty"):
        provider().generate_advanced("GENERAL", "hello")


def test_secret_is_not_in_errors(monkeypatch):
    monkeypatch.setattr(
        "ai.providers.cloudflare_provider.request.urlopen",
        lambda req, timeout: (_ for _ in ()).throw(URLError("token")),
    )
    with pytest.raises(CloudflareProviderError) as raised:
        CloudflareProvider(api_key="super-secret", model="m",
                           base_url="https://example.com/v1", account_id="a").generate_advanced("x", "y")
    assert "super-secret" not in str(raised.value)


def test_gateway_selects_cloudflare(monkeypatch):
    monkeypatch.setenv("SHYAM_ACADEMY_AI_PROVIDER", "cloudflare")
    monkeypatch.setenv("SHYAM_ACADEMY_AI_API_KEY", "token")
    monkeypatch.setenv("SHYAM_ACADEMY_AI_MODEL", "@cf/test")
    monkeypatch.setenv("SHYAM_ACADEMY_AI_ACCOUNT_REFERENCE", "account")
    monkeypatch.setenv("SHYAM_ACADEMY_AI_BASE_URL", "https://example.com/v1")
    assert isinstance(get_gateway(), CloudflareProvider)


def test_mock_gateway_remains_available(monkeypatch):
    monkeypatch.setenv("SHYAM_ACADEMY_AI_PROVIDER", "mock")
    assert get_gateway().__class__.__name__ == "MockProvider"
