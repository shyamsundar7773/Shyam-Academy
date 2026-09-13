from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


def session_status(session: dict, timezone_name: str = "Asia/Kolkata", now=None) -> str:
    zone = ZoneInfo(timezone_name)
    if now is None:
        current = datetime.now(zone)
    elif now.tzinfo is None:
        current = now.replace(tzinfo=zone)
    else:
        current = now.astimezone(zone)
    start = datetime.strptime(
        f"{session['session_date']} {session['scheduled_time']}",
        "%Y-%m-%d %I:%M %p",
    ).replace(tzinfo=zone)
    if session.get("status") == "Completed":
        return "Completed"
    if session.get("status") == "Skipped":
        return "Skipped"
    end_time = session.get("scheduled_end_time")
    if end_time:
        end = datetime.strptime(
            f"{session['session_date']} {end_time}", "%Y-%m-%d %I:%M %p"
        ).replace(tzinfo=zone)
    else:
        end = start + timedelta(hours=1)
    if current < start:
        return "Upcoming"
    if current < end:
        return "Active"
    return "Past"


def can_start_learning(
    session: dict, timezone_name: str = "Asia/Kolkata", now=None
) -> bool:
    return session_status(session, timezone_name, now) == "Active"
