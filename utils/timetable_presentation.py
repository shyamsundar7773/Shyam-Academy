from collections import defaultdict
from typing import Iterable, Mapping


def group_sessions_by_date(
    sessions: Iterable[Mapping],
    categories: Iterable[str],
) -> list[tuple[int, str, list[Mapping]]]:
    """Return one display group per canonical calendar date."""
    category_order = {category: index for index, category in enumerate(categories)}
    grouped: dict[str, list[Mapping]] = defaultdict(list)
    for session in sessions:
        grouped[str(session["session_date"])].append(session)

    result = []
    for display_day, session_date in enumerate(sorted(grouped), start=1):
        day_sessions = sorted(
            grouped[session_date],
            key=lambda session: (
                category_order.get(session["category"], len(category_order)),
                str(session.get("scheduled_time", "")),
            ),
        )
        result.append((display_day, session_date, day_sessions))
    return result
