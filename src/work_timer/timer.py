"""This module contains Timer, the class responsible for timing the work periods."""
import datetime
import dataclasses
import enum
import sched
import time
import threading
import weakref
from collections.abc import Callable
from typing import Protocol


class Timer:
    """The timer.
    """

    def __init__(self, clock: 'Clock' = time):
        self._clock = clock

        self._status = Status.STOPPED
        self._started_at = None
        # `self._elapsed_seconds` and `self._period_left` are updated when the
        # Timer isn't ticking (when changing into STOPPED or PAUSED from RUNNING).
        # How much time from the current period has already passed.
        self._elapsed_seconds = 0
        # How much time from the current period is still left, in seconds.
        self._period_left = None

        self._scheduler = sched.scheduler(self._clock.time, self._clock.sleep)
        self._thread = None
        self._evt_id = None
        self._on_period_end_callback = None

        # TODO: Maybe refactor it into a state machine?
        # TODO: Consider adding invariants about started_at / elapsed_seconds / period_left.

    def _sched_period_end(self, delay: float):
        assert self._evt_id is None
        on_period_end = weakref.WeakMethod(self._on_period_end)()
        assert on_period_end is not None  # to make pyright happy.
        self._evt_id = self._scheduler.enter(
                delay=delay, priority=1,
                action=on_period_end)
        self._thread = threading.Thread(target=self._scheduler.run)
        self._thread.start()

    def _cancel_period_end(self):
        assert self._evt_id is not None
        self._scheduler.cancel(self._evt_id)
        self._evt_id = None

    def _on_period_end(self):
        self._stop()
        if self._on_period_end_callback:
            self._on_period_end_callback(self.get_state())

    def start(self, task_id: int, period_length: datetime.timedelta):
        self._status = Status.RUNNING
        self._started_at = self._clock.time()
        self._period_left = period_length.seconds
        self._sched_period_end(period_length.seconds)

    def _stop_pause_timekeeping(self):
        assert self._started_at is not None
        assert self._period_left is not None
        elapsed_seconds = self._clock.time() - self._started_at
        if elapsed_seconds > self._period_left:
            # If the _on_period_end got executed a bit later than the scheduled
            # end time...
            self._elapsed_seconds += self._period_left
            self._period_left = 0
        else:
            self._elapsed_seconds += elapsed_seconds
            self._period_left -= elapsed_seconds

    def _stop(self):
        if self._status == Status.STOPPED:
            return
        if self._status == Status.RUNNING:
            self._stop_pause_timekeeping()
        self._status = Status.STOPPED

    def stop(self):
        assert self._status in (Status.RUNNING, Status.PAUSED)
        self._stop()
        if self._status == Status.RUNNING:
            self._cancel_period_end()

    def pause(self):
        assert self._status == Status.RUNNING
        assert self._started_at is not None
        self._status = Status.PAUSED
        self._stop_pause_timekeeping()
        self._cancel_period_end()

    def resume(self):
        assert self._status == Status.PAUSED
        self._status = Status.RUNNING
        self._started_at = self._clock.time()
        assert self._period_left is not None
        self._sched_period_end(self._period_left)

    def get_state(self) -> 'TimerState':
        elapsed_seconds = self._elapsed_seconds
        if self._status == Status.RUNNING:
            assert self._started_at is not None
            elapsed_seconds += self._clock.time() - self._started_at

        return TimerState(
            status=self._status,
            elapsed_time=datetime.timedelta(seconds=elapsed_seconds),
        )

    def set_on_period_end_callback(self, callback: Callable[['TimerState'], None]):
        self._on_period_end_callback = callback


class Clock(Protocol):
    def time(self) -> float:
        ...

    def sleep(self, seconds: float, /):
        ...


@dataclasses.dataclass
class TimerState:
    status: 'Status'
    elapsed_time: datetime.timedelta = datetime.timedelta(0)


class Status(enum.Enum):
    STOPPED = enum.auto()
    RUNNING = enum.auto()
    PAUSED = enum.auto()
