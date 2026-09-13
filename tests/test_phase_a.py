import json
from urllib.error import HTTPError

import pytest

from auth import firebase
from ai.providers.real_provider import RealProvider, RealProviderError


class Response:
    def __init__(self, value):
        self.value = value

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return json.dumps(self.value).encode()


def configure_firebase(monkeypatch):
    monkeypatch.setenv("SHYAM_ACADEMY_FIREBASE_PROJECT_ID", "project")
    monkeypatch.setenv("SHYAM_ACADEMY_FIREBASE_WEB_API_KEY", "public-key")


def test_firebase_configuration_does_not_require_private_credentials(monkeypatch):
    configure_firebase(monkeypatch)
    assert firebase.get_firebase_configuration().enabled


def test_sign_in_calls_firebase_without_exposing_password(monkeypatch):
    configure_firebase(monkeypatch)
    captured = {}

    def fake_urlopen(req, timeout):
        captured["body"] = json.loads(req.data.decode())
        return Response({"idToken": "token", "localId": "uid"})

    monkeypatch.setattr(firebase.request, "urlopen", fake_urlopen)
    result = firebase.sign_in_email_password("a@example.com", "secret")
    assert result["localId"] == "uid"
    assert captured["body"]["returnSecureToken"] is True


def test_verify_token_returns_firebase_uid(monkeypatch):
    configure_firebase(monkeypatch)
    monkeypatch.setattr(
        firebase.request, "urlopen",
        lambda req, timeout: Response({"users": [{"localId": "verified-uid", "email": "a@example.com"}]}),
    )
    assert firebase.verify_id_token("id-token")["localId"] == "verified-uid"


def test_invalid_token_is_rejected(monkeypatch):
    configure_firebase(monkeypatch)
    monkeypatch.setattr(firebase.request, "urlopen", lambda req, timeout: Response({"users": []}))
    with pytest.raises(firebase.FirebaseAuthError):
        firebase.verify_id_token("bad")


def test_firebase_http_auth_error_is_safe(monkeypatch):
    configure_firebase(monkeypatch)
    error = HTTPError("url", 401, "bad", {}, None)
    error.read = lambda: b'{"error":{"message":"INVALID_ID_TOKEN"}}'
    monkeypatch.setattr(firebase.request, "urlopen", lambda req, timeout: (_ for _ in ()).throw(error))
    with pytest.raises(firebase.FirebaseAuthError, match="Invalid"):
        firebase.verify_id_token("bad")


def test_missing_firebase_configuration_is_blocked(monkeypatch):
    monkeypatch.delenv("SHYAM_ACADEMY_FIREBASE_PROJECT_ID", raising=False)
    monkeypatch.delenv("SHYAM_ACADEMY_FIREBASE_WEB_API_KEY", raising=False)
    with pytest.raises(firebase.FirebaseAuthError, match="not configured"):
        firebase.sign_in_email_password("a@example.com", "secret")


def test_real_provider_requires_key(monkeypatch):
    monkeypatch.delenv("SHYAM_ACADEMY_AI_API_KEY", raising=False)
    with pytest.raises(RealProviderError, match="not configured"):
        RealProvider(model="test")


def test_real_provider_success(monkeypatch):
    monkeypatch.setattr(
        "ai.providers.real_provider.request.urlopen",
        lambda req, timeout: Response({"choices": [{"message": {"content": "real answer"}}]}),
    )
    provider = RealProvider(api_key="secret", model="test")
    assert provider.generate_advanced("GENERAL", "hello") == "real answer"


def test_real_provider_auth_failure_is_safe(monkeypatch):
    error = HTTPError("url", 401, "bad", {}, None)
    monkeypatch.setattr(
        "ai.providers.real_provider.request.urlopen",
        lambda req, timeout: (_ for _ in ()).throw(error),
    )
    with pytest.raises(RealProviderError, match="authentication failed"):
        RealProvider(api_key="secret", model="test").generate_advanced("GENERAL", "hello")


def test_real_provider_rate_limit_is_safe(monkeypatch):
    error = HTTPError("url", 429, "rate", {}, None)
    monkeypatch.setattr(
        "ai.providers.real_provider.request.urlopen",
        lambda req, timeout: (_ for _ in ()).throw(error),
    )
    with pytest.raises(RealProviderError, match="rate limit"):
        RealProvider(api_key="secret", model="test").generate_advanced("GENERAL", "hello")


def test_real_provider_malformed_response_is_safe(monkeypatch):
    monkeypatch.setattr(
        "ai.providers.real_provider.request.urlopen",
        lambda req, timeout: Response({"unexpected": "shape"}),
    )
    with pytest.raises(RealProviderError, match="malformed"):
        RealProvider(api_key="secret", model="test").generate_advanced("GENERAL", "hello")


def test_secret_is_not_in_provider_error(monkeypatch):
    monkeypatch.setattr(
        "ai.providers.real_provider.request.urlopen",
        lambda req, timeout: (_ for _ in ()).throw(TimeoutError()),
    )
    with pytest.raises(RealProviderError) as raised:
        RealProvider(api_key="super-secret", model="test").generate_advanced("GENERAL", "hello")
    assert "super-secret" not in str(raised.value)


def test_gateway_routes_openai(monkeypatch):
    monkeypatch.setenv("SHYAM_ACADEMY_AI_PROVIDER", "openai")
    monkeypatch.setenv("SHYAM_ACADEMY_AI_API_KEY", "key")
    monkeypatch.setenv("SHYAM_ACADEMY_AI_MODEL", "test")
    from ai.gateway import get_gateway
    assert isinstance(get_gateway(), RealProvider)


def test_mock_provider_remains_available(monkeypatch):
    monkeypatch.setenv("SHYAM_ACADEMY_AI_PROVIDER", "mock")
    from ai.gateway import get_gateway
    assert get_gateway().generate_advanced("GENERAL", "hello")
