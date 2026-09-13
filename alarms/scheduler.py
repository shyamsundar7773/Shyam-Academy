"""Compatibility exports for platform scheduler contracts."""

from alarms.schedulers import (
    AlarmScheduler,
    AndroidAlarmScheduler,
    SchedulerResult,
    WindowsAlarmScheduler,
)

__all__ = [
    "AlarmScheduler", "SchedulerResult", "WindowsAlarmScheduler",
    "AndroidAlarmScheduler",
]
