"""The Timer."""
from datetime import datetime, timedelta
import time

from gcsa.event import Event

from work_timer.config import Config
from work_timer.taskdb import TaskID, BREAK_TASK_ID
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
        self._time_log = config.time_log
        self._clock = clock
        self._single_task_timer = None

    def start(self, task_id: TaskID) -> None:
        self._single_task_timer = SingleTaskTimer(
                task_id, period_length=self._config.work_period_duration,
                clock=self._clock)

        if task_id == BREAK_TASK_ID:
            return

        self._single_task_timer.set_on_next_sub_period_callback(self._on_next_sub_period)

    def stop(self) -> None:
        assert self._single_task_timer is not None
        self._single_task_timer.stop()

    def pause(self) -> None:
        assert self._single_task_timer is not None
        self._single_task_timer.pause()

    def resume(self) -> None:
        assert self._single_task_timer is not None
        self._single_task_timer.resume()

    def get_info(self) -> 'NoActiveTimer | TimerInfo':
        if self._single_task_timer is None:
            return NoActiveTimer()
        return self._single_task_timer.get_info()

    def _on_next_sub_period(self, task_id: TaskID, started_at: datetime,
                            duration: timedelta) -> None:
        self._time_log.add_period(
                task_id=task_id, start=started_at, duration=duration)

        task = self._config.task_db.get(task_id)

        if self._config.calendar:
            self._config.calendar.add_event(
                Event(
                    task.title,
                    start=started_at,
                    end=started_at + duration))


class NoActiveTimer:
    def __repr__(self) -> str:
        return f'{self.__class__.__name__}()'
