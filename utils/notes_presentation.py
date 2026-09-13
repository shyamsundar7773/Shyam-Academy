from collections.abc import Iterable, Mapping


def normalize_note_category(category: str) -> str:
    return {
        "On-time Test": "Test",
        "Daily Test": "Test",
        "Weekly Test": "Test",
    }.get(category, category)


def group_notes_by_date(notes: Iterable[Mapping]) -> list[tuple[int, str, list[dict]]]:
    by_date: dict[str, list[dict]] = {}
    for note in notes:
        item = dict(note)
        item["category"] = normalize_note_category(item["category"])
        by_date.setdefault(item["note_date"], []).append(item)

    return [
        (day_number, note_date, sorted(day_notes, key=_note_sort_key))
        for day_number, (note_date, day_notes) in enumerate(
            sorted(by_date.items()), start=1
        )
    ]


def _note_sort_key(note: Mapping) -> tuple[str, str, int]:
    return (
        note.get("scheduled_time") or "",
        note.get("category") or "",
        int(note.get("note_id") or 0),
    )
