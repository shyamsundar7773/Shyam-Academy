import json

import streamlit as st


FIREBASE_REFRESH_COOKIE = "shyam_academy_firebase_refresh"
COOKIE_MAX_AGE = 60 * 60 * 24 * 30


def get_persisted_refresh_token() -> str | None:
    value = st.context.cookies.get(FIREBASE_REFRESH_COOKIE)
    return value.strip() if value and value.strip() else None


def persist_refresh_token(refresh_token: str | None) -> None:
    if not refresh_token:
        return
    value = json.dumps(refresh_token)
    st.html(
        f"""
        <script>
        (() => {{
            const token = {value};
            const secure = window.location.protocol === "https:" ? "; Secure" : "";
            document.cookie =
                "{FIREBASE_REFRESH_COOKIE}=" + encodeURIComponent(token) +
                "; Max-Age={COOKIE_MAX_AGE}; Path=/; SameSite=Lax" + secure;
        }})();
        </script>
        """,
        unsafe_allow_javascript=True,
    )


def clear_persisted_refresh_token() -> None:
    st.html(
        f"""
        <script>
        (() => {{
            document.cookie =
                "{FIREBASE_REFRESH_COOKIE}=; Max-Age=0; Path=/; SameSite=Lax";
            window.parent.location.reload();
        }})();
        </script>
        """,
        unsafe_allow_javascript=True,
    )
