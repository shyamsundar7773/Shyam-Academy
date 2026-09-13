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
