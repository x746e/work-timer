"""A facility for the Timer to log the time periods."""

import dataclasses
import datetime

from work_timer import taskdb


class TimeLog:
    """Stores the periods, provides reporting."""

    def __init__(self):
        self._periods = []

    def add_period(self, task_id: taskdb.TaskID, start: datetime.datetime,
                   duration: datetime.timedelta):
        self._periods.append(
                Period(task_id=task_id, start=start, duration=duration))

    def get_periods(self) -> list['Period']:
        return self._periods


@dataclasses.dataclass
class Period:
    task_id: taskdb.TaskID
    start: datetime.datetime
    duration: datetime.timedelta
