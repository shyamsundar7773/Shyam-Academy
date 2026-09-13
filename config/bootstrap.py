"""Application configuration bootstrap.

Environment values are loaded once, without overriding values injected by the
process, test runner, or deployment secret manager.
"""

import os
from pathlib import Path

from dotenv import load_dotenv


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
