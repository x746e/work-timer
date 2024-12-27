"""This module contains Timer, the class responsible for timing the work periods."""
from datetime import timedelta, datetime
from dataclasses import dataclass
import enum
import time
import weakref
from collections.abc import Callable

from typing import NewType, Tuple, Protocol

from loguru import logger

from work_timer.taskdb import TaskID
from work_timer.utils import state_machine
from work_timer.utils.time import td, humanize_td
from work_timer.utils.clock import Clock
from work_timer.utils.scheduler import Scheduler


Seconds = NewType('Seconds', int)


class SingleTaskTimer(state_machine.StateMachine):
    """The timer."""

    # pylint: disable=too-many-instance-attributes

    class State(enum.Enum):
        RUNNING = enum.auto()
        PAUSED = enum.auto()
        STOPPED = enum.auto()

    def __init__(  # pylint: disable=too-many-arguments,too-many-positional-arguments
            self,
            task_id: TaskID,
            period_length: timedelta,
            scheduler: Scheduler,
            on_period_end_callback: Callable[['TimerInfo'], None] | None = None,
            on_sub_period_end_callback: 'OnSubPeriodEndCallback | None' = None,
            on_sub_period_start_callback: Callable[['TimerInfo'], None] | None = None,
            clock: Clock = time):
        """
        Args:
            ...
            * scheduler: The Scheduler to schedule the callbacks execution.
            * on_period_end_callback: The callback to call at when period's
                time runs out.
            * on_sub_period_start_callback
            * on_sub_period_end_callback: callbacks that are called when the
                timer starts/stops ticking.

                Either because it was manually started/stopped, or it was
                paused/resumed, or the period ended.

                "Sub" prefix signifies that it can be less that the whole work
                period in case the timer was paused.
            ...
        """
        super().__init__()
        self._clock = clock

        self._task_id = task_id

        self._on_period_end_callback = on_period_end_callback
        self._on_sub_period_start_callback = on_sub_period_start_callback
        self._on_sub_period_end_callback = on_sub_period_end_callback

        self._scheduler = scheduler
        self._evt_id = None

        self._tk = _TimeKeeper(period_length.total_seconds(), self._clock.time())

        self._when_timer_starts_ticking()

    # Public API of the class.
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

    def _get_info(self, state: 'SingleTaskTimer.State') -> 'TimerInfo':
        """An internal version of `get_info`, allowing to specify the `state`.

        When you need to get the `TimerInfo` from inside a state transition
        handler, say, the handler from RUNNING to STOPPED, if you just call
        `get_info`, it will return `TimerInfo(state=RUNNING)` -- the
        `StateMachine`'s is updated _after_ all handlers had run.

        It seems to be a less suprising interface, to have, say, on_period_end
        callback to have TimerInfo that actually says that the timer is stopped.
        And it may make time accounting inside this class a bit easier, I'm not
        completely sure at this point.
        """
        elapsed_seconds = self._tk.get_elapsed_seconds()

        if state == self.State.RUNNING:
            # TODO: Can we have all time related logic inside _TimeKeeper?
            elapsed_seconds += self._clock.time() - self._tk.get_started_at()

        return TimerInfo(
            state=self.get_state(),
            elapsed_time=timedelta(seconds=elapsed_seconds),
            period_length=self._tk.get_period_length(),
            task_id=self._task_id,
        )

    # State transition handlers.
    @state_machine.handler(State.PAUSED, State.RUNNING)
    def _when_timer_starts_ticking(self):
        self._tk.resume(self._clock.time())
        self._schedule_period_end()
        if self._on_sub_period_start_callback:
            self._on_sub_period_start_callback(self._get_info(self.State.RUNNING))

    @state_machine.handler(State.RUNNING, State.STOPPED)
    @state_machine.handler(State.RUNNING, State.PAUSED)
    def _when_timer_stops_ticking(self):
        started_at, elapsed_seconds = self._tk.pause(self._clock.time())
        self._cancel_period_end()
        if self._on_sub_period_end_callback:
            # TODO: Can we just pass the same TimerInfo to all the callbacks?
            # (TimerInfo doesn't have all the info right now, but it can be extended.)
            self._on_sub_period_end_callback(
                task_id=self._task_id,
                started_at=datetime.fromtimestamp(started_at),
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
        self._evt_id = self._scheduler.schedule(
                on_period_end,
                after=timedelta(seconds=self._tk.get_period_left()))

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
    state: SingleTaskTimer.State
    # `task_id` isn't used by anything in this module, it's to make it easier
    # for callers to keep track of which Task is timed by this Timer.
    task_id: TaskID
    period_length: timedelta
    elapsed_time: timedelta = timedelta(0)

    def __post_init__(self):
        self._validate()

    def _validate(self):
        eps = timedelta(seconds=3)
        if self.period_length:
            if self.elapsed_time > (pl := self.period_length + eps):
                logger.warning('Elapsed time is larger than period length: '
                               f'self.elapsed_time ({td(self.elapsed_time)}) > '
                               f'self.period_length + eps ({td(pl)})')
    def __repr__(self):
        return (f'{self.__class__.__name__}('
                f'state={self.state}, '
                f'task_id={self.task_id}, '
                f'period_length=td({humanize_td(self.period_length)!r}), '
                f'elapsed_time=td({humanize_td(self.elapsed_time)!r}))')


class OnSubPeriodEndCallback(Protocol):
    def __call__(self, task_id: TaskID, started_at: datetime,
                 duration: timedelta) -> None: ...


class _TimeKeeper:

    _started_at: float
    _elapsed_seconds: float
    _period_left: float
    _period_length: float

    def __init__(self, period_length: float, ts_now: float):
        self._started_at = ts_now
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

    def resume(self, ts_now: float) -> None:
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
