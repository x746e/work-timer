"""The Timer."""
from datetime import timedelta
from collections.abc import Callable
import time

from work_timer import timelog
from work_timer.taskdb import TaskID
from work_timer.timer.single_task_timer import SingleTaskTimer, TimerInfo
from work_timer.utils.clock import Clock


class Timer:

    """The timer.

    For now just forwards everything to the underlying _SingleTaskTimer.  The
    plan is to move all the timing logic from ui.timer into this class.
    """

    State = SingleTaskTimer.State

    def __init__(
            self,
            task_id: TaskID,
            period_length: timedelta,
            time_log: timelog.TimeLog,
            clock: Clock = time):
        self._single_task_timer = SingleTaskTimer(
            task_id, period_length, time_log, clock)

    def stop(self):
        self._single_task_timer.stop()

    def pause(self):
        self._single_task_timer.pause()

    def resume(self):
        self._single_task_timer.resume()

    def get_info(self) -> 'TimerInfo':
        return self._single_task_timer.get_info()

    def set_on_period_end_callback(self, callback: Callable[['TimerInfo'], None]):
        self._single_task_timer.set_on_period_end_callback(callback)
