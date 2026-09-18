from pathlib import Path

from auth import session
from models.academy import AcademyUser


def test_auth_shell_is_rendered_before_navigation():
    source = (Path(__file__).parents[1] / "app.py").read_text(encoding="utf-8")
    assert "render_auth_screen()" in source
    assert 'st.Page("pages/auth.py"' not in source
    assert "page = st.navigation(pages" in source


def test_sign_in_stores_firebase_identity_and_logout_clears_it(monkeypatch):
    monkeypatch.setattr(
        session,
        "sign_in_email_password",
        lambda email, password: {
            "idToken": "runtime-token",
            "localId": "firebase-user",
            "email": email,
        },
    )
    session.sign_out()
    user = session.sign_in("learner@example.com", "private-password")
    assert user.user_id == "firebase-user"
    assert session.st.session_state.current_user.user_id == "firebase-user"
    assert session.st.session_state.firebase_email == "learner@example.com"

    session.sign_out()
    assert "current_user" not in session.st.session_state
    assert "firebase_id_token" not in session.st.session_state
    assert "firebase_refresh_token" not in session.st.session_state
    assert "firebase_email" not in session.st.session_state


def test_missing_current_user_is_stopped_without_creating_identity(monkeypatch):
    session.st.session_state.clear()
    monkeypatch.setattr(session.st, "stop", lambda: (_ for _ in ()).throw(RuntimeError("stopped")))
    try:
        session.require_current_user()
    except RuntimeError as error:
        assert str(error) == "stopped"
    assert "current_user" not in session.st.session_state


def test_require_current_user_returns_canonical_identity():
    session.st.session_state.current_user = AcademyUser("firebase-user")
    assert session.require_current_user().user_id == "firebase-user"
    session.st.session_state.clear()


def test_persisted_firebase_session_is_refreshed_and_verified(monkeypatch):
    session.st.session_state.clear()
    monkeypatch.setattr(
        session,
        "get_persisted_refresh_token",
        lambda: "browser-refresh-token",
    )
    monkeypatch.setattr(
        session,
        "refresh_id_token",
        lambda token: {
            "id_token": "restored-id-token",
            "refresh_token": "rotated-refresh-token",
            "user_id": "firebase-user",
        },
    )
    monkeypatch.setattr(
        session,
        "verify_id_token",
        lambda token: {"localId": "firebase-user", "email": "learner@example.com"},
    )
    user = session.get_current_user()
    assert user.user_id == "firebase-user"
    assert session.st.session_state.firebase_refresh_token == "rotated-refresh-token"


def test_invalid_persisted_session_remains_unauthenticated(monkeypatch):
    session.st.session_state.clear()
    monkeypatch.setattr(
        session,
        "get_persisted_refresh_token",
        lambda: "expired-refresh-token",
    )
    monkeypatch.setattr(
        session,
        "refresh_id_token",
        lambda token: (_ for _ in ()).throw(
            session.FirebaseAuthError("expired")
        ),
    )
    assert session.get_current_user() is None
    assert "current_user" not in session.st.session_state


def test_new_sign_in_keeps_accounts_separate(monkeypatch):
    session.st.session_state.clear()
    monkeypatch.setattr(
        session,
        "sign_in_email_password",
        lambda email, password: {
            "idToken": "account-b-token",
            "refreshToken": "account-b-refresh",
            "localId": "account-b",
            "email": email,
        },
    )
    user = session.sign_in("b@example.com", "private-password")
    assert user.user_id == "account-b"
    assert session.st.session_state.firebase_refresh_token == "account-b-refresh"
