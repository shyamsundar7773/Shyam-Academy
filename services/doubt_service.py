from datetime import datetime, timezone

from services.notes_service import save_note
from services.module_service import add_module


def save_doubt(
    connection, user_id: str, classroom_id: str, title: str,
    history: list[dict], module_id: int | None = None,
) -> int:
    content = "\n\n".join(
        f"{item['role'].title()}: {item['content']}" for item in history
    )
    if module_id is not None:
        note_id, _ = save_note(
            connection, user_id, module_id, None, "Doubts",
            "Doubt discussion", title, content, "Doubt classroom",
            f"doubts:module:{module_id}",
        )
        return note_id
    module = connection.execute(
        "SELECT module_id FROM modules WHERE owner_user_id=? AND module_name=?",
        (user_id, "Independent Doubts"),
    ).fetchone()
    independent_module_id = (
        int(module["module_id"]) if module else
        add_module(connection, "Independent Doubts", "Module-free Doubts notes", user_id)
    )
    legacy_cursor = connection.execute(
        """INSERT INTO doubt_notes
           (user_id,classroom_id,title,content,saved_at)
           VALUES (?,?,?,?,?)""",
        (user_id, classroom_id, title, content,
         datetime.now(timezone.utc).isoformat()),
    )
    connection.commit()
    save_note(
        connection, user_id, independent_module_id, None, "Doubts",
        "Doubt discussion", title, content, "Doubt classroom",
        f"doubts:independent:{classroom_id}",
    )
    return int(legacy_cursor.lastrowid)
