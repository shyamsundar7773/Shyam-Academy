from dataclasses import dataclass
from datetime import date, datetime


@dataclass(frozen=True)
class AcademyUser:
    user_id: str


@dataclass(frozen=True)
class Module:
    module_id: int
    module_name: str
    description: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class Session:
    session_id: int
    module_id: int
    day_number: int
    session_date: date
    category: str
    topic: str
    scheduled_time: str
    prompt: str
    status: str
    created_at: datetime
    updated_at: datetime
