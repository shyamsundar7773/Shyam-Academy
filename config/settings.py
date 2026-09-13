import os
from pathlib import Path

from config.bootstrap import PROJECT_ROOT

DATABASE_PATH = Path(
    os.getenv("SHYAM_ACADEMY_DB_PATH", "data/shyam_academy.sqlite3")
)
if not DATABASE_PATH.is_absolute():
    DATABASE_PATH = PROJECT_ROOT / DATABASE_PATH

DEFAULT_USER_ID = os.getenv("SHYAM_ACADEMY_USER_ID", "local-dev-user")
AI_PROVIDER = os.getenv("SHYAM_ACADEMY_AI_PROVIDER", "mock").strip().lower()
AI_MODEL = os.getenv("SHYAM_ACADEMY_AI_MODEL", "development-classroom")
