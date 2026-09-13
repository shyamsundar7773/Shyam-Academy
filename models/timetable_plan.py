from dataclasses import dataclass
from datetime import date

from services.timetable_service import CATEGORIES


@dataclass
class PlannedSession:
    session_date: str
    scheduled_time: str
    category: str
    topic: str
    session_title: str
    prompt: str
    scheduled_end_time: str | None = None
    status: str = "Scheduled"
    day_number: int = 1


@dataclass
class TimetablePlan:
    title: str
    module_name: str
    description: str
    start_date: str
    end_date: str
    timezone: str
    assumptions: list[str]
    sessions: list[PlannedSession]

    @property
    def total_sessions(self) -> int:
        return len(self.sessions)
