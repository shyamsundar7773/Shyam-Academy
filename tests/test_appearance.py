import sqlite3

from database.schema import initialize_database
from services.appearance_service import (
    get_appearance,
    save_background,
    save_custom_background,
)


def connection():
    database = sqlite3.connect(":memory:")
    database.row_factory = sqlite3.Row
    initialize_database(database)
    return database


def test_predefined_background_persists_and_is_user_scoped():
    database = connection()
    save_background(database, "user-a", "blue")
    save_background(database, "user-b", "green")
    assert get_appearance(database, "user-a")["background"] == "blue"
    assert get_appearance(database, "user-b")["background"] == "green"


def test_custom_background_persists_by_reference_without_binary_sqlite_data():
    database = connection()
    saved = save_custom_background(database, "user-a", b"image-bytes", "image/png")
    loaded = get_appearance(database, "user-a")
    assert saved["background"] == "custom"
    assert loaded["asset_path"].endswith(".png")
    assert database.execute(
        "SELECT length(asset_path), background FROM user_appearance WHERE user_id='user-a'"
    ).fetchone()[1] == "custom"


def test_missing_custom_asset_falls_back_to_default():
    database = connection()
    save_custom_background(database, "user-a", b"image-bytes", "image/png")
    database.execute(
        "UPDATE user_appearance SET asset_path='missing.png' WHERE user_id='user-a'"
    )
    database.commit()
    appearance = get_appearance(database, "user-a")
    assert appearance["background"] == "paper"
    assert appearance["asset_path"] is None
