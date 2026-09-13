"""Device-neutral timetable alarms and platform scheduler contracts."""

from alarms.models import Alarm, alarm_id_for_session

__all__ = ["Alarm", "alarm_id_for_session"]
