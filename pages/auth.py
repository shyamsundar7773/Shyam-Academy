import streamlit as st

from auth.firebase import (
    FirebaseAuthError,
    build_google_authorization_url,
    create_google_pkce_state,
    exchange_google_code,
    get_firebase_configuration,
    get_google_oauth_configuration,
)
from auth.session import sign_in, sign_in_google


def handle_google_callback() -> None:
    params = st.query_params
    code = params.get("code")
    state = params.get("state")
    if not code and not state:
        return
    expected = st.session_state.get("google_oauth_state")
    verifier = st.session_state.get("google_oauth_verifier")
    if not code or not state or state != expected or not verifier:
        st.error("Google sign-in could not be verified. Please try again.")
        return
    try:
        sign_in_google(exchange_google_code(code, verifier))
    except FirebaseAuthError as exc:
        st.error(str(exc))
    else:
        st.query_params.clear()
        st.rerun()

def render_auth_screen() -> None:
    handle_google_callback()
    st.markdown(
        """
        <style>
        [data-testid="stAppViewContainer"] > .main {
            min-height: 100vh;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    left, center, right = st.columns([1, 1.4, 1])
    with center:
        st.markdown("<h1 style='text-align:center'>SHYAM ACADEMY</h1>", unsafe_allow_html=True)
        st.caption("Sign in to continue to your personal learning workspace.")
        with st.form("firebase_sign_in"):
            email = st.text_input("Email", autocomplete="email")
            password = st.text_input("Password", type="password", autocomplete="current-password")
            submit = st.form_submit_button("Sign in", type="primary", use_container_width=True)
        st.divider()
        google = get_google_oauth_configuration()
        if google.enabled:
            if "google_oauth_state" not in st.session_state:
                state, verifier, challenge = create_google_pkce_state()
                st.session_state.google_oauth_state = state
                st.session_state.google_oauth_verifier = verifier
                st.session_state.google_oauth_url = build_google_authorization_url(
                    state, challenge
                )
            st.link_button(
                "Sign in with Google",
                st.session_state.google_oauth_url,
                use_container_width=True,
            )
        else:
            st.button("Sign in with Google", use_container_width=True, disabled=True)
            st.caption("Google sign-in requires OAuth client configuration.")
        if not get_firebase_configuration().enabled:
            st.warning("Firebase Authentication is not configured for this deployment.")
        if submit:
            try:
                sign_in(email, password)
                st.rerun()
            except FirebaseAuthError as exc:
                st.error(str(exc))
