from datetime import datetime
from zoneinfo import ZoneInfo

from utils.dashboard_presentation import (
    DASHBOARD_TIMEZONE,
    current_dashboard_time,
    order_dashboard_sessions,
)


def session(session_id, date, time, status="Scheduled", display_status=None):
    return {
        "session_id": session_id,
        "session_date": date,
        "scheduled_time": time,
        "scheduled_end_time": None,
        "status": status,
        **({"display_status": display_status} if display_status else {}),
    }


def test_current_dashboard_time_is_fresh_asia_kolkata_time(monkeypatch):
    first = datetime(2026, 9, 14, 9, 15, tzinfo=DASHBOARD_TIMEZONE)
    second = datetime(2026, 9, 14, 9, 16, tzinfo=DASHBOARD_TIMEZONE)
    values = iter([first, second])
    monkeypatch.setattr(
        "utils.dashboard_presentation.datetime",
        type("Clock", (), {"now": staticmethod(lambda zone: next(values))}),
    )
    assert current_dashboard_time() == first
    assert current_dashboard_time() == second


def test_today_active_session_is_first():
    now = datetime(2026, 9, 14, 10, 30, tzinfo=ZoneInfo("Asia/Kolkata"))
    sessions = [
        session(1, "2026-09-14", "08:00 AM", display_status="Attended"),
        session(2, "2026-09-14", "10:00 AM"),
        session(3, "2026-09-14", "12:00 PM"),
    ]
    assert [item["session_id"] for item in order_dashboard_sessions(sessions, now)] == [2, 3, 1]


def test_today_next_upcoming_precedes_history():
    now = datetime(2026, 9, 14, 9, 15, tzinfo=ZoneInfo("Asia/Kolkata"))
    sessions = [
        session(1, "2026-09-14", "08:00 AM", display_status="Missed"),
        session(2, "2026-09-14", "10:00 AM"),
        session(3, "2026-09-14", "02:00 PM"),
    ]
    assert [item["session_id"] for item in order_dashboard_sessions(sessions, now)] == [2, 3, 1]


def test_future_dates_follow_today_and_older_dates_are_history():
    now = datetime(2026, 9, 14, 9, 15, tzinfo=ZoneInfo("Asia/Kolkata"))
    sessions = [
        session(1, "2026-09-13", "11:00 AM"),
        session(2, "2026-09-16", "09:00 AM"),
        session(3, "2026-09-14", "10:00 AM"),
        session(4, "2026-09-15", "09:00 AM"),
    ]
    assert [item["session_id"] for item in order_dashboard_sessions(sessions, now)] == [3, 4, 2, 1]


def test_same_clock_time_on_different_dates_is_not_conflicting():
    now = datetime(2026, 9, 14, 8, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
    sessions = [
        session(1, "2026-09-14", "10:00 AM"),
        session(2, "2026-09-15", "10:00 AM"),
    ]
    ordered = order_dashboard_sessions(sessions, now)
    assert [item["session_id"] for item in ordered] == [1, 2]


def test_ordering_does_not_mutate_session_records():
    now = datetime(2026, 9, 14, 8, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
    original = session(1, "2026-09-14", "10:00 AM")
    order_dashboard_sessions([original], now)
    assert original == session(1, "2026-09-14", "10:00 AM")
