"""This module contains Timer, the class responsible for timing the work periods."""
from datetime import timedelta, datetime
from dataclasses import dataclass
import enum
import sched
import time
import threading
import weakref
from collections.abc import Callable

from typing import NewType, Tuple

from work_timer import timelog
from work_timer.taskdb import TaskID
from work_timer.utils import state_machine
from work_timer.utils.clock import Clock


Seconds = NewType('Seconds', int)


class _TimeKeeper:

    # TODO: Consider start the Timer in a Started state, in which case this
    # wouldn't ever be None.
    # TODO: And disallow STOPPED -> STARTED transition.
    _started_at: float | None
    _elapsed_seconds: float
    _period_left: float
    _period_length: float

    def __init__(self, period_length: float):
        self._started_at = None
        # `self.elapsed_seconds` and `self.period_left` are updated when the
        # Timer isn't ticking (when changing into STOPPED or PAUSED from RUNNING).
        # How much time from the current period has already passed.
        self._elapsed_seconds = 0
        # How much time from the current period is still left, in seconds.
        self._period_left = period_length
        self._period_length = period_length

    def __repr__(self) -> str:
        return (f'<{self.__class__.__name__}: '
                f'_started_at={self._started_at!r}, '
                f'_elapsed_seconds={self._elapsed_seconds!r}, '
                f'_period_left={self._period_left!r}, '
                f'_period_length={self._period_length!r}>')

    # TODO: Do I need to pass timestamps into it?  Maybe just give the class a clock?
    def pause(self, ts_now: float) -> Tuple[float, float]:  # pylint: disable=missing-function-docstring
        assert self._started_at is not None
        elapsed_seconds = ts_now - self._started_at
        if elapsed_seconds > self._period_left:
            # That's a very late tick, but that can happen.
            self._elapsed_seconds += self._period_left
            self._period_left = 0
        else:
            self._elapsed_seconds += elapsed_seconds
            self._period_left -= elapsed_seconds
        return (self._started_at, elapsed_seconds)

    def start(self, ts_now: float) -> None:
        self._started_at = ts_now

    def get_elapsed_seconds(self) -> float:
        return self._elapsed_seconds

    def get_started_at(self) -> float:
        assert self._started_at is not None
        return self._started_at

    def get_period_left(self) -> float:
        return self._period_left

    def get_period_length(self) -> timedelta:
        return timedelta(seconds=self._period_length)

    # TODO: Replace `int` with datetime classes for internal usage.


class Timer(state_machine.StateMachine):
    """The timer."""

    # TODO: Try removing it, now with _TimeKeeper we can we OK.
    # pylint: disable=too-many-instance-attributes

    class State(enum.Enum):
        STOPPED = enum.auto()
        RUNNING = enum.auto()
        PAUSED = enum.auto()

    def __init__(
            self,
            task_id: TaskID,
            period_length: timedelta,
            clock: Clock = time,
            time_log: timelog.TimeLog = timelog.TimeLog()):
        super().__init__()
        self._clock = clock
        self._time_log = time_log

        self._task_id = task_id

        self._tk = _TimeKeeper(period_length.total_seconds())

        # TODO: Can I group these arguments together into a class?
        self._scheduler = sched.scheduler(self._clock.time, self._clock.sleep)
        self._thread = None
        self._evt_id = None
        self._on_period_end_callback = None

    # Public API of the class.
    def start(self):
        self.transition_to(self.State.RUNNING)

    def stop(self):
        self.transition_to(self.State.STOPPED)

    def pause(self):
        self.transition_to(self.State.PAUSED)

    def resume(self):
        self.transition_to(self.State.RUNNING)

    def get_info(self) -> 'TimerInfo':
        """Returns information about the current timer state."""
        with self._state_transition_lock:
            return self._get_info(state=self.get_state())

    def _get_info(self, state: 'Timer.State') -> 'TimerInfo':
        elapsed_seconds = self._tk.get_elapsed_seconds()

        if state == self.State.RUNNING:
            # TODO: Can we have all time related logic inside _TimeKeeper?
            elapsed_seconds += self._clock.time() - self._tk.get_started_at()

        return TimerInfo(
            state=self.get_state(),
            elapsed_time=timedelta(seconds=elapsed_seconds),
            period_length=self._tk.get_period_length(),
        )

    def set_on_period_end_callback(self, callback: Callable[['TimerInfo'], None]):
        self._on_period_end_callback = callback

    # State transition handlers.
    @state_machine.handler(State.STOPPED, State.RUNNING)
    @state_machine.handler(State.PAUSED, State.RUNNING)
    def _when_timer_starts_ticking(self):
        self._tk.start(self._clock.time())
        self._schedule_period_end()

    @state_machine.handler(State.RUNNING, State.STOPPED)
    @state_machine.handler(State.RUNNING, State.PAUSED)
    def _when_timer_stops_ticking(self):
        started_at, elapsed_seconds = self._tk.pause(self._clock.time())
        self._cancel_period_end()
        self._time_log.add_period(
                task_id=self._task_id,
                start=datetime.fromtimestamp(started_at),
                duration=timedelta(seconds=elapsed_seconds))

    @state_machine.handler(State.PAUSED, State.STOPPED)
    @state_machine.handler(State.RUNNING, State.STOPPED)
    def _when_stopping_the_timer_call_the_callback(self):
        if self._on_period_end_callback:
            self._on_period_end_callback(self._get_info(self.State.STOPPED))

    # End-of-period callback handling.

    def _schedule_period_end(self):
        assert self._evt_id is None
        on_period_end = weakref.WeakMethod(self._on_period_end)()
        assert on_period_end is not None  # to make pyright happy.
        self._evt_id = self._scheduler.enter(
                delay=self._tk.get_period_left(), priority=1,
                action=on_period_end)
        self._thread = threading.Thread(target=self._scheduler.run, daemon=True)
        self._thread.start()

    def _on_period_end(self):
        self._evt_id = None
        self.transition_to(self.State.STOPPED)

    def _cancel_period_end(self):
        if self._evt_id:
            self._scheduler.cancel(self._evt_id)
            self._evt_id = None


@dataclass(frozen=True)
class TimerInfo:
    """Information about the current Timer state."""
    state: Timer.State
    period_length: timedelta
    elapsed_time: timedelta = timedelta(0)

    def __post_init__(self):
        self._validate()

    def _validate(self):
        eps = timedelta(seconds=1)
        if self.period_length:
            assert self.elapsed_time <= self.period_length + eps, (
                f"{self.elapsed_time=}, shouldn't be (much) more than "
                f"{self.period_length + eps=}."
            )
