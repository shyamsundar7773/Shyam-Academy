"""Safe Advanced AI preferences; provider credentials remain outside the database."""

from datetime import datetime, timezone


DEFAULTS = {
    "enabled": True,
    "preferred_provider": "",
    "preferred_model": "",
    "voice_input_provider": "not_configured",
    "voice_output_provider": "not_configured",
}


def get_settings(connection, user_id: str) -> dict:
    if not isinstance(user_id, str) or not user_id.strip():
        raise ValueError("A user identity is required.")
    row = connection.execute(
        "SELECT * FROM ai_user_settings WHERE user_id=?", (user_id,)
    ).fetchone()
    result = {"user_id": user_id, **DEFAULTS}
    if row:
        result.update(dict(row))
        result["enabled"] = bool(result["enabled"])
    return result


def save_settings(connection, user_id: str, values: dict) -> dict:
    unknown = set(values) - set(DEFAULTS)
    if unknown:
        raise ValueError("Unknown AI setting.")
    current = get_settings(connection, user_id)
    current.update(values)
    for key in ("preferred_provider", "preferred_model", "voice_input_provider",
                "voice_output_provider"):
        current[key] = str(current[key]).strip()[:100]
    connection.execute(
        """INSERT INTO ai_user_settings
        (user_id,enabled,preferred_provider,preferred_model,voice_input_provider,
         voice_output_provider,updated_at) VALUES (?,?,?,?,?,?,?)
        ON CONFLICT(user_id) DO UPDATE SET enabled=excluded.enabled,
        preferred_provider=excluded.preferred_provider,preferred_model=excluded.preferred_model,
        voice_input_provider=excluded.voice_input_provider,
        voice_output_provider=excluded.voice_output_provider,updated_at=excluded.updated_at""",
        (user_id, int(bool(current["enabled"])), current["preferred_provider"],
         current["preferred_model"], current["voice_input_provider"],
         current["voice_output_provider"], datetime.now(timezone.utc).isoformat()),
    )
    connection.commit()
    return get_settings(connection, user_id)
