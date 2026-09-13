from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class SchedulerResult:
    scheduled: bool
    platform: str
    detail: str = ""


class AlarmScheduler(Protocol):
    platform: str

    def schedule(self, alarm: dict) -> SchedulerResult: ...
    def cancel(self, alarm_id: str) -> SchedulerResult: ...


class WindowsAlarmScheduler:
    platform = "windows"

    def schedule(self, alarm):
        return SchedulerResult(False, self.platform, "Windows scheduler integration is not configured.")

    def cancel(self, alarm_id):
        return SchedulerResult(False, self.platform, "Windows scheduler integration is not configured.")


class AndroidAlarmScheduler:
    platform = "android"

    def schedule(self, alarm):
        return SchedulerResult(False, self.platform, "Android scheduler integration is not configured.")

    def cancel(self, alarm_id):
        return SchedulerResult(False, self.platform, "Android scheduler integration is not configured.")
