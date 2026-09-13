from datetime import date, timedelta

import pytest

from services.timetable_service import CATEGORIES
from utils.timetable_presentation import group_sessions_by_date


def _sessions(day_count):
    start = date(2026, 9, 13)
    sessions = []
    for day_index in range(day_count):
        session_date = (start + timedelta(days=day_index)).isoformat()
        for category_index, category in enumerate(CATEGORIES):
            sessions.append({
                "session_date": session_date,
                "category": category,
                "scheduled_time": f"{category_index + 5}:00 PM",
                "day_number": day_index * len(CATEGORIES) + category_index + 1,
            })
    return sessions


def _assert_grouping(groups, expected_dates):
    assert len(groups) == len(expected_dates)
    assert [session_date for _, session_date, _ in groups] == expected_dates
    assert [display_day for display_day, _, _ in groups] == list(
        range(1, len(expected_dates) + 1)
    )
    for _, session_date, sessions in groups:
        assert {session["session_date"] for session in sessions} == {session_date}
        assert {session["category"] for session in sessions} == set(CATEGORIES)
        assert len(sessions) == len(CATEGORIES)


@pytest.mark.parametrize("day_count", [1, 3, 4, 5])
def test_one_day_container_per_unique_calendar_date(day_count):
    sessions = _sessions(day_count)
    groups = group_sessions_by_date(sessions, CATEGORIES)
    expected_dates = [
        (date(2026, 9, 13) + timedelta(days=index)).isoformat()
        for index in range(day_count)
    ]
    _assert_grouping(groups, expected_dates)


def test_exact_user_prompt_shape_has_three_containers_and_21_sessions():
    sessions = _sessions(3)
    groups = group_sessions_by_date(sessions, CATEGORIES)
    _assert_grouping(
        groups,
        ["2026-09-13", "2026-09-14", "2026-09-15"],
    )
    assert sum(len(day_sessions) for _, _, day_sessions in groups) == 21


def test_random_session_order_is_grouped_and_sorted_by_date_and_category():
    sessions = list(reversed(_sessions(3)))
    groups = group_sessions_by_date(sessions, CATEGORIES)
    _assert_grouping(
        groups,
        ["2026-09-13", "2026-09-14", "2026-09-15"],
    )
    for _, _, day_sessions in groups:
        assert [session["category"] for session in day_sessions] == list(CATEGORIES)


def test_same_date_different_times_stays_in_one_container():
    sessions = _sessions(1)
    sessions[0]["scheduled_time"] = "5:30 PM"
    sessions[1]["scheduled_time"] = "6:15 PM"
    groups = group_sessions_by_date(sessions, CATEGORIES)
    assert len(groups) == 1
    assert len(groups[0][2]) == 7
