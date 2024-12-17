"""The Timer."""
from collections.abc import Callable
import time

from work_timer.config import Config
from work_timer.taskdb import TaskID
from work_timer.timer.single_task_timer import SingleTaskTimer, TimerInfo
from work_timer.utils.clock import Clock


class Timer:

    """The timer.

    For now just forwards everything to the underlying _SingleTaskTimer.  The
    plan is to move all the timing logic from ui.timer into this class.
    """

    State = SingleTaskTimer.State

    def __init__(self, config: Config, clock: Clock = time) -> None:
        self._config = config
        self._clock = clock
        self._single_task_timer = None

    def start(self, task_id: TaskID) -> None:
        self._single_task_timer = SingleTaskTimer(
                task_id, period_length=self._config.work_period_duration,
                time_log=self._config.time_log, clock=self._clock)

    def stop(self):
        assert self._single_task_timer is not None
        self._single_task_timer.stop()

    def pause(self):
        assert self._single_task_timer is not None
        self._single_task_timer.pause()

    def resume(self):
        assert self._single_task_timer is not None
        self._single_task_timer.resume()

    def get_info(self) -> 'NoActiveTimer | TimerInfo':
        if self._single_task_timer is None:
            return NoActiveTimer()
        return self._single_task_timer.get_info()

    def set_on_period_end_callback(self, callback: Callable[['TimerInfo'], None]):
        assert self._single_task_timer is not None
        self._single_task_timer.set_on_period_end_callback(callback)


class NoActiveTimer:
    def __repr__(self) -> str:
        return f'{self.__class__.__name__}()'
