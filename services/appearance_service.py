from __future__ import annotations

import hashlib
from pathlib import Path

from database.connection import get_connection


ALLOWED_BACKGROUNDS = {"paper", "blue", "green", "lavender", "sand"}
ALLOWED_THEMES = {"light", "dark"}
ASSET_ROOT = Path(__file__).resolve().parents[1] / ".academy_assets" / "backgrounds"


def _asset_path(user_id: str, mime_type: str) -> Path:
    digest = hashlib.sha256(user_id.encode("utf-8")).hexdigest()
    extension = {"image/jpeg": ".jpg", "image/webp": ".webp"}.get(mime_type, ".png")
    return ASSET_ROOT / f"{digest}{extension}"


def get_appearance(connection, user_id: str) -> dict:
    row = connection.execute(
        "SELECT * FROM user_appearance WHERE user_id=?", (user_id,)
    ).fetchone()
    result = dict(row) if row else {
        "user_id": user_id, "background": "paper", "theme": "light",
        "asset_path": None, "asset_mime": None,
    }
    result.setdefault("theme", "light")
    if result.get("asset_path") and not Path(result["asset_path"]).is_file():
        result["background"] = "paper"
        result["asset_path"] = None
    return result


def save_background(connection, user_id: str, background: str) -> dict:
    if background not in ALLOWED_BACKGROUNDS:
        raise ValueError("Unknown background.")
    current = get_appearance(connection, user_id)
    connection.execute(
        """INSERT INTO user_appearance(user_id,background,theme,asset_path,asset_mime)
           VALUES(?,?,?,?,?)
           ON CONFLICT(user_id) DO UPDATE SET background=excluded.background""",
        (
            user_id, background, current.get("theme", "light"),
            current.get("asset_path"),
            current.get("asset_mime"),
        ),
    )
    connection.commit()
    return get_appearance(connection, user_id)


def save_theme(connection, user_id: str, theme: str) -> dict:
    if theme not in ALLOWED_THEMES:
        raise ValueError("Unknown application theme.")
    current = get_appearance(connection, user_id)
    connection.execute(
        """INSERT INTO user_appearance(user_id,background,theme,asset_path,asset_mime)
           VALUES(?, ?, ?, ?, ?)
           ON CONFLICT(user_id) DO UPDATE SET theme=excluded.theme""",
        (
            user_id, current["background"], theme,
            current.get("asset_path"), current.get("asset_mime"),
        ),
    )
    connection.commit()
    return get_appearance(connection, user_id)


def save_custom_background(connection, user_id: str, content: bytes, mime_type: str) -> dict:
    if not content or mime_type not in {"image/png", "image/jpeg", "image/webp"}:
        raise ValueError("Choose a PNG, JPEG, or WebP image.")
    path = _asset_path(user_id, mime_type)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    connection.execute(
        """INSERT INTO user_appearance(user_id,background,asset_path,asset_mime)
           VALUES(?, 'custom', ?, ?)
           ON CONFLICT(user_id) DO UPDATE SET
             background='custom', asset_path=excluded.asset_path,
             asset_mime=excluded.asset_mime""",
        (user_id, str(path), mime_type),
    )
    connection.commit()
    return get_appearance(connection, user_id)
