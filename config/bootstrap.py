"""Application configuration bootstrap.

Environment values are loaded once, without overriding values injected by the
process, test runner, or deployment secret manager.
"""

import os
from pathlib import Path

from dotenv import dotenv_values, load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent.parent
_loaded = False


def load_environment() -> Path:
    global _loaded
    env_path = PROJECT_ROOT / ".env"
    if not _loaded:
        load_dotenv(env_path, override=False)
        _loaded = True
    return env_path


load_environment()


def _dotenv_configuration() -> dict[str, str]:
    return {
        key: value
        for key, value in dotenv_values(PROJECT_ROOT / ".env").items()
        if value is not None
    }


def _streamlit_secret_value(key: str) -> str | None:
    try:
        import streamlit as st
    except ImportError:
        return None
    try:
        from streamlit.errors import StreamlitSecretNotFoundError
    except ImportError:
        StreamlitSecretNotFoundError = KeyError
    try:
        value = st.secrets.get(key)
    except StreamlitSecretNotFoundError:
        return None
    return str(value) if value is not None else None


def get_config_value(key: str, default: str | None = None) -> str | None:
    """Read configuration with process, Streamlit, then local dotenv precedence."""
    load_environment()
    dotenv = _dotenv_configuration()
    environment_value = os.environ.get(key)
    if (
        environment_value is not None
        and (key not in dotenv or environment_value != dotenv.get(key))
    ):
        return environment_value
    secret_value = _streamlit_secret_value(key)
    if secret_value is not None:
        return secret_value
    if environment_value is not None:
        return environment_value
    return dotenv.get(key, default)
