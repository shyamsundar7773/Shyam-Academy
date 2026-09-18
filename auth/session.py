import streamlit as st
from uuid import uuid4

from auth.firebase import (
    FirebaseAuthError,
    refresh_id_token,
    sign_in_email_password,
    sign_in_google_id_token,
    verify_id_token,
)
from auth.persistence import get_persisted_refresh_token
from models.academy import AcademyUser


def require_current_user() -> AcademyUser:
    """Return the verified user or stop a directly opened protected page cleanly."""
    user = st.session_state.get("current_user")
    if isinstance(user, AcademyUser) and user.user_id:
        return user
    st.info("Please sign in to access Shyam Academy.")
    st.stop()


def get_current_user() -> AcademyUser | None:
    token = st.session_state.get("firebase_id_token")
    if not token:
        refresh_token = get_persisted_refresh_token()
        if refresh_token:
            try:
                refreshed = refresh_id_token(refresh_token)
                token = refreshed["id_token"]
                st.session_state.firebase_id_token = token
                st.session_state.firebase_refresh_token = refreshed.get(
                    "refresh_token", refresh_token
                )
            except FirebaseAuthError:
                return None
    if not token:
        return None
    try:
        verified = verify_id_token(token)
    except FirebaseAuthError:
        st.session_state.pop("firebase_id_token", None)
        st.session_state.pop("current_user", None)
        return None
    user = AcademyUser(verified["localId"])
    st.session_state.current_user = user
    st.session_state.firebase_email = verified.get("email", "")
    return user


def sign_in(email: str, password: str) -> AcademyUser:
    result = sign_in_email_password(email, password)
    token = result.get("idToken")
    uid = result.get("localId")
    if not token or not uid:
        raise FirebaseAuthError("Firebase did not return a valid authenticated session.")
    st.session_state.firebase_id_token = token
    if result.get("refreshToken"):
        st.session_state.firebase_refresh_token = result["refreshToken"]
    st.session_state.firebase_email = result.get("email", email.strip())
    st.session_state.current_user = AcademyUser(uid)
    st.session_state.auth_session_id = uuid4().hex
    return st.session_state.current_user


def sign_in_google(result: dict) -> AcademyUser:
    token = result.get("idToken")
    uid = result.get("localId")
    if not token or not uid:
        raise FirebaseAuthError("Google authentication did not return a valid session.")
    st.session_state.firebase_id_token = token
    if result.get("refreshToken"):
        st.session_state.firebase_refresh_token = result["refreshToken"]
    st.session_state.firebase_email = result.get("email", "")
    st.session_state.current_user = AcademyUser(uid)
    st.session_state.auth_session_id = uuid4().hex
    st.session_state.pop("google_oauth_state", None)
    st.session_state.pop("google_oauth_verifier", None)
    st.session_state.pop("google_oauth_url", None)
    return st.session_state.current_user


def sign_out() -> None:
    for key in (
        "firebase_id_token", "firebase_refresh_token", "firebase_email", "current_user",
        "appearance_user_id", "academy_background", "academy_background_asset",
        "academy_theme", "academy_theme_toggle", "auth_session_id",
    ):
        st.session_state.pop(key, None)
    for key in list(st.session_state):
        if key.startswith(("shared_history_", "shared_title_", "shared_composer_value_")):
            st.session_state.pop(key, None)
