from utils.notes_presentation import group_notes_by_date


def _notes(module_id, dates, times):
    return [
        {
            "note_id": index,
            "module_id": module_id,
            "note_date": note_date,
            "category": category,
            "scheduled_time": time,
        }
        for index, (note_date, category, time) in enumerate(
            zip(dates, ("Level 1",) * len(dates), times), start=1
        )
    ]


def test_grouping_rebuilds_calendar_days_and_preserves_selected_module_records():
    python = _notes(
        1,
        ["2026-09-13", "2026-09-14", "2026-09-15"],
        ["7:00 AM", "8:00 AM", "9:00 AM"],
    )
    biology = _notes(
        2,
        ["2026-09-13", "2026-09-14", "2026-09-15", "2026-09-16"],
        ["10:00 AM", "11:00 AM", "12:00 PM", "1:00 PM"],
    )

    python_days = group_notes_by_date(python)
    biology_days = group_notes_by_date(biology)
    python_again_days = group_notes_by_date(python)

    assert [date for _, date, _ in python_days] == [
        "2026-09-13", "2026-09-14", "2026-09-15"
    ]
    assert [date for _, date, _ in biology_days] == [
        "2026-09-13", "2026-09-14", "2026-09-15", "2026-09-16"
    ]
    assert {note["module_id"] for _, _, day in biology_days for note in day} == {2}
    assert {note["category"] for _, _, day in biology_days for note in day} == {"Level 1"}
    assert [
        note["scheduled_time"]
        for _, _, day in biology_days
        for note in day
    ] == ["10:00 AM", "11:00 AM", "12:00 PM", "1:00 PM"]
    assert [date for _, date, _ in python_again_days] == [
        "2026-09-13", "2026-09-14", "2026-09-15"
    ]
    assert {note["module_id"] for _, _, day in python_again_days for note in day} == {1}


def test_grouping_assigns_day_numbers_from_sorted_calendar_dates():
    grouped = group_notes_by_date(
        _notes(
            1,
            ["2026-09-15", "2026-09-13", "2026-09-14"],
            ["9:00 AM", "7:00 AM", "8:00 AM"],
        )
    )

    assert [(day, date) for day, date, _ in grouped] == [
        (1, "2026-09-13"),
        (2, "2026-09-14"),
        (3, "2026-09-15"),
    ]
