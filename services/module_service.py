import sqlite3

from database.repositories.module_repository import (
    create_module,
    delete_module,
    get_owned_module,
    list_modules,
    update_module,
)


def get_modules(connection: sqlite3.Connection, user_id: str):
    return [dict(module) for module in list_modules(connection, user_id)]


def get_module(connection: sqlite3.Connection, module_id: int, user_id: str):
    if not isinstance(module_id, int) or module_id <= 0:
        raise ValueError("Invalid module ID.")
    module = get_owned_module(connection, module_id, user_id)
    if module is None:
        raise ValueError("The selected module could not be found.")
    return module


def add_module(
    connection: sqlite3.Connection, name: str, description: str, user_id: str
) -> int:
    if not name.strip():
        raise ValueError("Module name is required.")
    try:
        return create_module(connection, name, description, user_id)
    except sqlite3.IntegrityError as error:
        raise ValueError("A module with that name already exists.") from error


def edit_module(
    connection: sqlite3.Connection,
    module_id: int,
    name: str,
    description: str,
    user_id: str,
) -> None:
    if not isinstance(module_id, int) or module_id <= 0:
        raise ValueError("Invalid module ID.")
    if not name.strip():
        raise ValueError("Module name is required.")
    if get_owned_module(connection, module_id, user_id) is None:
        raise ValueError("The selected module could not be found.")
    try:
        update_module(connection, module_id, name, description, user_id)
    except sqlite3.IntegrityError as error:
        raise ValueError("A module with that name already exists.") from error


def get_or_create_classroom_module(
    connection: sqlite3.Connection,
    user_id: str,
    classroom_id: str,
    name: str,
    description: str,
) -> dict:
    marker = f"AI classroom:{classroom_id}"
    row = connection.execute(
        """SELECT module_id, module_name, description
           FROM modules WHERE owner_user_id=? AND description LIKE ?""",
        (user_id, f"{marker}%"),
    ).fetchone()
    if row:
        return dict(row)
    module_name = name.strip() or "AI Classroom"
    try:
        module_id = create_module(
            connection, module_name, f"{marker}\n{description.strip()}", user_id
        )
    except sqlite3.IntegrityError as error:
        raise ValueError(
            "A module with this name already exists. Choose a different classroom title."
        ) from error
    return dict(get_owned_module(connection, module_id, user_id))


def rename_classroom_module(
    connection: sqlite3.Connection,
    user_id: str,
    module_id: int,
    name: str,
) -> None:
    module = get_module(connection, module_id, user_id)
    edit_module(connection, module_id, name, module["description"], user_id)


def remove_module(connection: sqlite3.Connection, module_id: int, user_id: str) -> None:
    if not isinstance(module_id, int) or module_id <= 0:
        raise ValueError("Invalid module ID.")
    if get_owned_module(connection, module_id, user_id) is None:
        raise ValueError("The selected module could not be found.")
    delete_module(connection, module_id, user_id)
