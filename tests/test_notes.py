import sqlite3
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from database.schema import initialize_database
from services.module_service import (
    add_module,
    get_or_create_classroom_module,
    rename_classroom_module,
)
from services.classroom_service import load_history, rename_classroom, save_history
from services.notes_service import (
    edit_note,
    find_notes,
    get_user_note,
    remove_note,
    save_note,
    find_notes_for_cell,
    find_notes_for_selection,
)


@pytest.fixture
def connection():
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    initialize_database(connection)
    yield connection
    connection.close()


def test_note_creation_numbering_and_content(connection):
    module_id = add_module(connection, "SQL Developer", "SQL", "user-a")
    first_id, first_number = save_note(
        connection, "user-a", module_id, None, "Level 1", "INNER JOIN",
        "INNER JOIN — Fundamentals", "# Heading\n\n```sql\nSELECT 1;\n```"
    )
    second_id, second_number = save_note(
        connection, "user-a", module_id, None, "Level 1", "INNER JOIN",
        "INNER JOIN — Examples", "## Examples\n\n- Example two"
    )
    assert first_number == 1
    assert second_number == 2
    assert first_id != second_id
    assert get_user_note(connection, first_id, "user-a")["content"].startswith("# Heading")


def test_note_module_and_user_isolation_and_filtering(connection):
    module_a = add_module(connection, "SQL Developer", "SQL", "user-a")
    module_b = add_module(connection, "Python Developer", "Python", "user-a")
    module_other_user = add_module(connection, "SQL Developer", "SQL", "user-b")
    save_note(connection, "user-a", module_a, None, "Level 1", "JOIN", "SQL joins", "sql")
    save_note(connection, "user-a", module_b, None, "Level 1", "Lists", "Python lists", "python")
    save_note(
        connection, "user-b", module_other_user, None, "Level 1",
        "JOIN", "Other user", "private"
    )
    notes = find_notes(connection, "user-a", module_a, "Level 1", "join")
    assert len(notes) == 1
    assert notes[0]["module_id"] == module_a
    assert len(find_notes(connection, "user-a", module_b)) == 1
    assert len(find_notes(connection, "user-b", module_other_user)) == 1


def test_note_update_and_delete_do_not_touch_session(connection):
    module_id = add_module(connection, "SQL Developer", "SQL", "user-a")
    connection.execute(
        """
        INSERT INTO sessions
            (module_id, day_number, session_date, category, topic, scheduled_time,
             prompt, status, owner_user_id, created_at, updated_at)
        VALUES (?, 1, '2026-09-13', 'Level 1', 'JOIN', '11:00 AM',
                'prompt', 'Scheduled', 'user-a', 'now', 'now')
        """,
        (module_id,),
    )
    connection.commit()
    session_id = connection.execute("SELECT last_insert_rowid()").fetchone()[0]
    note_id, _ = save_note(
        connection, "user-a", module_id, session_id, "Level 1", "JOIN",
        "Original", "Original content"
    )
    edit_note(connection, note_id, "user-a", "Updated", "Updated **content**")
    assert get_user_note(connection, note_id, "user-a")["title"] == "Updated"
    remove_note(connection, note_id, "user-a")
    assert connection.execute(
        "SELECT COUNT(*) FROM sessions WHERE session_id = ?", (session_id,)
    ).fetchone()[0] == 1
    with pytest.raises(ValueError):
        get_user_note(connection, note_id, "user-a")


def test_missing_source_session_does_not_hide_note(connection):
    module_id = add_module(connection, "SQL Developer", "SQL", "user-a")
    note_id, _ = save_note(
        connection, "user-a", module_id, None, "Today Learning", "SQL",
        "Standalone", "Readable content"
    )
    note = get_user_note(connection, note_id, "user-a")
    assert note["content"] == "Readable content"
    assert note["session_id"] is None


def test_note_context_id_preserves_exact_session_context(connection):
    module_id = add_module(connection, "SQL Developer", "SQL", "user-a")
    connection.execute(
        """INSERT INTO sessions
        (module_id,day_number,session_date,category,topic,scheduled_time,prompt,
         status,owner_user_id,created_at,updated_at)
        VALUES (?,1,'2026-09-13','Test','Joins','7:00 PM','p',
                'Scheduled','user-a','now','now')""",
        (module_id,),
    )
    connection.commit()
    session_id = connection.execute("SELECT last_insert_rowid()").fetchone()[0]
    note_id, _ = save_note(
        connection, "user-a", module_id, session_id, "Test", "Joins",
        "MCQ notes", "content", "Test classroom",
        f"test:mcq_technical:session:{session_id}",
    )
    note = get_user_note(connection, note_id, "user-a")
    assert note["session_id"] == session_id
    assert note["context_id"] == f"test:mcq_technical:session:{session_id}"


def test_interview_note_round_categories_persist_and_filter(connection):
    module_id = add_module(connection, "SQL Developer", "SQL", "user-a")
    for category in ("HR Screening", "Technical Interview", "Managerial Round"):
        save_note(
            connection, "user-a", module_id, None, category, "SQL",
            f"{category} notes", f"{category} content",
            "Interview Preparation",
        )
    notes = find_notes(connection, "user-a", module_id, "Technical Interview")
    assert len(notes) == 1
    assert notes[0]["category"] == "Technical Interview"
    assert get_user_note(connection, notes[0]["note_id"], "user-a")["content"] == (
        "Technical Interview content"
    )


def test_independent_note_selection_uses_saved_local_date(connection, monkeypatch):
    module_id = add_module(connection, "SQL Developer", "SQL", "user-a")
    monkeypatch.setattr(
        "database.repositories.note_repository.datetime",
        type(
            "FixedDateTime",
            (),
            {"now": classmethod(lambda cls, tz=None: datetime(2026, 9, 13, 18, 0, tzinfo=timezone.utc))},
        ),
    )
    save_note(
        connection, "user-a", module_id, None, "Doubts", "JOIN",
        "JOIN doubt", "content", source="Doubt",
    )
    assert len(find_notes_for_selection(
        connection, "user-a", module_id, "2026-09-13", "Doubts"
    )) == 1
    assert not find_notes_for_selection(
        connection, "user-a", module_id, "2026-09-14", "Doubts"
    )


def test_full_notes_selection_isolated_by_date_category_module_and_user(connection):
    module_a = add_module(connection, "SQL Developer", "SQL", "user-a")
    module_b = add_module(connection, "Python Developer", "Python", "user-a")
    other_module = add_module(connection, "SQL Developer", "SQL", "user-b")
    for module_id, user_id, category, topic in (
        (module_a, "user-a", "Doubts", "JOIN"),
        (module_a, "user-a", "Test", "MCQ"),
        (module_b, "user-a", "Doubts", "JOIN"),
        (other_module, "user-b", "Doubts", "JOIN"),
    ):
        save_note(connection, user_id, module_id, None, category, topic, topic, "content")
    selected = find_notes_for_selection(
        connection, "user-a", module_a,
        datetime.now(timezone.utc).astimezone(ZoneInfo("Asia/Kolkata")).date().isoformat(), "Doubts",
    )
    assert len(selected) == 1
    assert selected[0]["module_id"] == module_a
    assert selected[0]["category"] == "Doubts"
    category_selected = find_notes_for_selection(
        connection, "user-a", module_a,
        datetime.now(timezone.utc).astimezone(ZoneInfo("Asia/Kolkata")).date().isoformat(),
        "Test",
    )
    assert len(category_selected) == 1
    assert category_selected[0]["category"] == "Test"
    module_selected = find_notes_for_selection(
        connection, "user-a", module_b,
        datetime.now(timezone.utc).astimezone(ZoneInfo("Asia/Kolkata")).date().isoformat(),
        "Doubts",
    )
    assert len(module_selected) == 1
    assert module_selected[0]["module_id"] == module_b
    assert len(find_notes_for_selection(
        connection, "user-b", other_module,
        datetime.now(timezone.utc).astimezone(ZoneInfo("Asia/Kolkata")).date().isoformat(),
        "Doubts",
    )) == 1


def test_independent_classroom_module_is_owned_stable_and_renamable(connection):
    module = get_or_create_classroom_module(
        connection, "user-a", "test_hr_independent", "HR Screening",
        "Independent test classroom",
    )
    same_module = get_or_create_classroom_module(
        connection, "user-a", "test_hr_independent", "Different title",
        "Independent test classroom",
    )
    assert same_module["module_id"] == module["module_id"]
    rename_classroom_module(connection, "user-a", module["module_id"], "HR Practice")
    renamed = connection.execute(
        "SELECT module_name, owner_user_id FROM modules WHERE module_id=?",
        (module["module_id"],),
    ).fetchone()
    assert dict(renamed) == {"module_name": "HR Practice", "owner_user_id": "user-a"}
    assert connection.execute(
        "SELECT COUNT(*) FROM modules WHERE owner_user_id='user-a'"
    ).fetchone()[0] == 1


def test_classroom_title_persists_without_losing_history(connection):
    rename_classroom(connection, "user-a", "doubt_user-a", "SQL Joins Practice")
    save_history(
        connection, "user-a", "doubt_user-a",
        [{"role": "assistant", "content": "Join explanation"}],
        "SQL Joins Practice",
    )
    rename_classroom(connection, "user-a", "doubt_user-a", "SQL Joins Review")
    assert load_history(connection, "user-a", "doubt_user-a")[0]["content"] == (
        "Join explanation"
    )
    assert connection.execute(
        "SELECT title FROM classroom_conversations "
        "WHERE user_id='user-a' AND classroom_id='doubt_user-a'"
    ).fetchone()["title"] == "SQL Joins Review"


def test_notes_cell_selection_groups_exact_modules_and_has_no_zero_fallback(connection):
    module_a = add_module(connection, "SQL Developer", "SQL", "user-a")
    module_b = add_module(connection, "Python Developer", "Python", "user-a")
    save_note(
        connection, "user-a", module_a, None, "Doubts", "JOIN",
        "SQL doubt", "sql content",
    )
    save_note(
        connection, "user-a", module_b, None, "Doubts", "Lists",
        "Python doubt", "python content",
    )
    today = datetime.now(timezone.utc).astimezone(
        ZoneInfo("Asia/Kolkata")
    ).date().isoformat()
    selected = find_notes_for_cell(
        connection, "user-a", today, "Doubts", [module_a, module_b]
    )
    assert {note["module_id"] for note in selected} == {module_a, module_b}
    assert find_notes_for_cell(connection, "user-a", today, "Doubts", []) == []
