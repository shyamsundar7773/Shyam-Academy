import sqlite3
from datetime import datetime, timezone


def list_modules(connection: sqlite3.Connection, owner_user_id: str) -> list[sqlite3.Row]:
    return connection.execute(
        "SELECT * FROM modules WHERE owner_user_id = ? ORDER BY module_name",
        (owner_user_id,),
    ).fetchall()


def get_module(connection: sqlite3.Connection, module_id: int) -> sqlite3.Row | None:
    return connection.execute(
        "SELECT * FROM modules WHERE module_id = ?", (module_id,)
    ).fetchone()


def get_owned_module(
    connection: sqlite3.Connection, module_id: int, owner_user_id: str
) -> sqlite3.Row | None:
    return connection.execute(
        "SELECT * FROM modules WHERE module_id = ? AND owner_user_id = ?",
        (module_id, owner_user_id),
    ).fetchone()


def create_module(
    connection: sqlite3.Connection,
    module_name: str,
    description: str,
    owner_user_id: str,
) -> int:
    now = datetime.now(timezone.utc).isoformat()
    cursor = connection.execute(
        """
        INSERT INTO modules
            (module_name, description, owner_user_id, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (module_name.strip(), description.strip(), owner_user_id, now, now),
    )
    connection.commit()
    return int(cursor.lastrowid)


def update_module(
    connection: sqlite3.Connection,
    module_id: int,
    module_name: str,
    description: str,
    owner_user_id: str,
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    cursor = connection.execute(
        """
        UPDATE modules
        SET module_name = ?, description = ?, updated_at = ?
        WHERE module_id = ? AND owner_user_id = ?
        """,
        (module_name.strip(), description.strip(), now, module_id, owner_user_id),
    )
    if cursor.rowcount != 1:
        raise ValueError("The selected module could not be updated.")
    connection.commit()


def delete_module(
    connection: sqlite3.Connection, module_id: int, owner_user_id: str
) -> None:
    cursor = connection.execute(
        "DELETE FROM modules WHERE module_id = ? AND owner_user_id = ?",
        (module_id, owner_user_id),
    )
    if cursor.rowcount != 1:
        raise ValueError("The selected module could not be deleted.")
    connection.commit()
