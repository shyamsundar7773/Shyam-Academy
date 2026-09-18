from urllib.parse import parse_qs, urlparse

import pytest

from auth import firebase


def test_google_authorization_url_uses_pkce(monkeypatch):
    monkeypatch.setenv("SHYAM_ACADEMY_FIREBASE_GOOGLE_CLIENT_ID", "client-id")
    monkeypatch.setenv("SHYAM_ACADEMY_FIREBASE_GOOGLE_REDIRECT_URI", "http://localhost:8501/")
    url = firebase.build_google_authorization_url("state-value", "challenge-value")
    query = parse_qs(urlparse(url).query)
    assert query["client_id"] == ["client-id"]
    assert query["state"] == ["state-value"]
    assert query["code_challenge"] == ["challenge-value"]
    assert query["code_challenge_method"] == ["S256"]


def test_google_oauth_requires_client_configuration(monkeypatch):
    monkeypatch.delenv("SHYAM_ACADEMY_FIREBASE_GOOGLE_CLIENT_ID", raising=False)
    monkeypatch.delenv("SHYAM_ACADEMY_FIREBASE_GOOGLE_REDIRECT_URI", raising=False)
    with pytest.raises(firebase.FirebaseAuthError, match="not configured"):
        firebase.build_google_authorization_url("state", "challenge")


def test_google_id_token_payload_uses_firebase_idp(monkeypatch):
    captured = {}

    def fake_request(endpoint, payload, timeout=10):
        captured["endpoint"] = endpoint
        captured["payload"] = payload
        return {"idToken": "token", "localId": "google-user"}

    monkeypatch.setattr(firebase, "_firebase_request", fake_request)
    monkeypatch.setenv("SHYAM_ACADEMY_FIREBASE_PROJECT_ID", "project")
    monkeypatch.setenv("SHYAM_ACADEMY_FIREBASE_WEB_API_KEY", "web-key")
    result = firebase.sign_in_google_id_token("google-id-token", "http://localhost/")
    assert result["localId"] == "google-user"
    assert "providerId=google.com" in captured["payload"]["postBody"]
    assert "google-id-token" in captured["payload"]["postBody"]


def test_refresh_id_token_uses_firebase_secure_token_endpoint(monkeypatch):
    captured = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return b'{"id_token":"new-id-token","user_id":"firebase-user","refresh_token":"rotated"}'

    def fake_urlopen(req, timeout):
        captured["url"] = req.full_url
        captured["body"] = req.data.decode("utf-8")
        return Response()

    monkeypatch.setattr(firebase.request, "urlopen", fake_urlopen)
    monkeypatch.setenv("SHYAM_ACADEMY_FIREBASE_PROJECT_ID", "project")
    monkeypatch.setenv("SHYAM_ACADEMY_FIREBASE_WEB_API_KEY", "web-key")
    result = firebase.refresh_id_token("browser-refresh-token")
    assert result["user_id"] == "firebase-user"
    assert captured["url"].startswith(
        "https://securetoken.googleapis.com/v1/token?key=web-key"
    )
    assert "grant_type=refresh_token" in captured["body"]
