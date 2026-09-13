from datetime import datetime
from typing import Iterable, Mapping
from zoneinfo import ZoneInfo

from services.schedule_status import session_status


DASHBOARD_TIMEZONE = ZoneInfo("Asia/Kolkata")


def current_dashboard_time() -> datetime:
    return datetime.now(DASHBOARD_TIMEZONE)


def _session_start(session: Mapping, timezone=DASHBOARD_TIMEZONE) -> datetime:
    return datetime.strptime(
        f"{session['session_date']} {session['scheduled_time']}",
        "%Y-%m-%d %I:%M %p",
    ).replace(tzinfo=timezone)


def order_dashboard_sessions(
    sessions: Iterable[Mapping],
    now: datetime,
) -> list[dict]:
    current = (
        now.astimezone(DASHBOARD_TIMEZONE)
        if now.tzinfo is not None
        else now.replace(tzinfo=DASHBOARD_TIMEZONE)
    )
    today = current.date().isoformat()
    ordered = []
    for session in sessions:
        item = dict(session)
        start = _session_start(item)
        status = item.get("display_status") or session_status(item, now=current)
        if item["session_date"] == today:
            group = {
                "Active": 0,
                "Upcoming": 1,
            }.get(status, 2)
        elif start.date() > current.date():
            group = 3
        else:
            group = 4
        ordered.append((group, start, item))
    ordered.sort(key=lambda entry: (entry[0], entry[1], entry[2].get("session_id", 0)))
    return [item for _, _, item in ordered]
