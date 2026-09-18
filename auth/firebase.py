import os
import json
import base64
import hashlib
import secrets
from urllib.parse import urlencode, quote
from urllib import error, request
from dataclasses import dataclass

from config.bootstrap import load_environment


@dataclass(frozen=True)
class FirebaseConfiguration:
    """Configuration boundary for Firebase clients without embedding credentials."""

    project_id: str | None
    web_api_key: str | None
    auth_domain: str | None
    enabled: bool


@dataclass(frozen=True)
class GoogleOAuthConfiguration:
    client_id: str | None
    redirect_uri: str | None
    client_secret: str | None

    @property
    def enabled(self) -> bool:
        return bool(self.client_id and self.redirect_uri)


def get_google_oauth_configuration() -> GoogleOAuthConfiguration:
    load_environment()
    return GoogleOAuthConfiguration(
        os.getenv("SHYAM_ACADEMY_FIREBASE_GOOGLE_CLIENT_ID"),
        os.getenv("SHYAM_ACADEMY_FIREBASE_GOOGLE_REDIRECT_URI"),
        os.getenv("SHYAM_ACADEMY_FIREBASE_GOOGLE_CLIENT_SECRET"),
    )


def create_google_pkce_state() -> tuple[str, str, str]:
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode("ascii")).digest()
    ).rstrip(b"=").decode("ascii")
    return secrets.token_urlsafe(32), verifier, challenge


def build_google_authorization_url(state: str, code_challenge: str) -> str:
    config = get_google_oauth_configuration()
    if not config.enabled:
        raise FirebaseAuthError("Google sign-in is not configured.")
    return "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode({
        "client_id": config.client_id,
        "redirect_uri": config.redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "access_type": "offline",
        "prompt": "select_account",
    })


def get_firebase_configuration() -> FirebaseConfiguration:
    load_environment()
    project_id = os.getenv("SHYAM_ACADEMY_FIREBASE_PROJECT_ID")
    web_api_key = os.getenv("SHYAM_ACADEMY_FIREBASE_WEB_API_KEY")
    auth_domain = os.getenv(
        "SHYAM_ACADEMY_FIREBASE_AUTH_DOMAIN",
        f"{project_id}.firebaseapp.com" if project_id else None,
    )
    return FirebaseConfiguration(
        project_id=project_id, web_api_key=web_api_key,
        auth_domain=auth_domain, enabled=bool(project_id and web_api_key),
    )


def mask_secret(value: str | None) -> str:
    if not value:
        return "Not configured"
    return f"{'•' * max(0, len(value) - 4)}{value[-4:]}"


class FirebaseAuthError(RuntimeError):
    """Safe, user-facing Firebase authentication error."""


def _firebase_request(endpoint: str, payload: dict, timeout: float = 10) -> dict:
    body = json.dumps(payload).encode("utf-8")
    try:
        with request.urlopen(
            request.Request(endpoint, data=body, headers={"Content-Type": "application/json"}),
            timeout=timeout,
        ) as response:
            return json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        try:
            detail = json.loads(exc.read().decode("utf-8")).get("error", {}).get("message", "")
        except (json.JSONDecodeError, UnicodeDecodeError):
            detail = ""
        if "INVALID" in detail or "TOKEN" in detail or "PASSWORD" in detail:
            raise FirebaseAuthError("Invalid email, password, or authentication token.") from exc
        raise FirebaseAuthError("Firebase authentication is temporarily unavailable.") from exc
    except (error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise FirebaseAuthError("Firebase authentication is temporarily unavailable.") from exc


def sign_in_email_password(email: str, password: str) -> dict:
    config = get_firebase_configuration()
    if not config.enabled:
        raise FirebaseAuthError("Firebase authentication is not configured.")
    if not email.strip() or not password:
        raise FirebaseAuthError("Email and password are required.")
    return _firebase_request(
        f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={config.web_api_key}",
        {"email": email.strip(), "password": password, "returnSecureToken": True},
    )


def sign_in_google_id_token(id_token: str, request_uri: str | None = None) -> dict:
    config = get_firebase_configuration()
    if not config.enabled or not id_token.strip():
        raise FirebaseAuthError("Google authentication is invalid or Firebase is not configured.")
    post_body = urlencode({"id_token": id_token.strip(), "providerId": "google.com"})
    return _firebase_request(
        f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithIdp?key={config.web_api_key}",
        {
            "postBody": post_body,
            "requestUri": request_uri or get_google_oauth_configuration().redirect_uri,
            "returnSecureToken": True,
            "returnIdpCredential": False,
        },
    )


def exchange_google_code(code: str, verifier: str) -> dict:
    config = get_google_oauth_configuration()
    if not config.enabled or not code.strip() or not verifier:
        raise FirebaseAuthError("Google authentication callback is invalid.")
    payload = urlencode({
        "code": code.strip(),
        "client_id": config.client_id,
        "client_secret": config.client_secret or "",
        "redirect_uri": config.redirect_uri,
        "grant_type": "authorization_code",
        "code_verifier": verifier,
    }).encode("utf-8")
    try:
        with request.urlopen(
            request.Request(
                "https://oauth2.googleapis.com/token",
                data=payload,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            ),
            timeout=10,
        ) as response:
            result = json.loads(response.read().decode("utf-8"))
    except (error.HTTPError, error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise FirebaseAuthError("Google authentication is temporarily unavailable.") from exc
    if not result.get("id_token"):
        raise FirebaseAuthError("Google authentication did not return a valid identity.")
    return sign_in_google_id_token(result["id_token"], config.redirect_uri)


def verify_id_token(id_token: str) -> dict:
    """Verify an ID token through Firebase's authenticated account lookup API."""
    config = get_firebase_configuration()
    if not config.enabled or not id_token.strip():
        raise FirebaseAuthError("Authentication token is invalid or Firebase is not configured.")
    result = _firebase_request(
        f"https://identitytoolkit.googleapis.com/v1/accounts:lookup?key={config.web_api_key}",
        {"idToken": id_token.strip()},
    )
    users = result.get("users") or []
    if not users or not users[0].get("localId"):
        raise FirebaseAuthError("Authentication token is invalid or expired.")
    return users[0]


def refresh_id_token(refresh_token: str) -> dict:
    config = get_firebase_configuration()
    if not config.enabled or not refresh_token.strip():
        raise FirebaseAuthError("Authentication session is invalid or expired.")
    try:
        with request.urlopen(
            request.Request(
                f"https://securetoken.googleapis.com/v1/token?key={config.web_api_key}",
                data=urlencode({
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token.strip(),
                }).encode("utf-8"),
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            ),
            timeout=10,
        ) as response:
            result = json.loads(response.read().decode("utf-8"))
    except (error.HTTPError, error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise FirebaseAuthError("Authentication session is invalid or expired.") from exc
    if not result.get("id_token") or not result.get("user_id"):
        raise FirebaseAuthError("Authentication session is invalid or expired.")
    return result
