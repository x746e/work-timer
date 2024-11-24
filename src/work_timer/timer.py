"""This module contains Timer, the class responsible for timing the work periods."""
import datetime
import dataclasses
import enum
import sched
import time
import threading
import weakref
from collections.abc import Callable

from work_timer import timelog
from work_timer.utils import state_machine
from work_timer.utils.clock import Clock


class Timer(state_machine.StateMachine):
    """The timer."""

    # pylint: disable=too-many-instance-attributes

    class State(enum.Enum):
        STOPPED = enum.auto()
        RUNNING = enum.auto()
        PAUSED = enum.auto()

    def __init__(self, clock: Clock = time, time_log: timelog.TimeLog = timelog.TimeLog()):
        super().__init__()
        self._clock = clock
        self._time_log = time_log

        self._started_at = None
        # `self._elapsed_seconds` and `self._period_left` are updated when the
        # Timer isn't ticking (when changing into STOPPED or PAUSED from RUNNING).
        # How much time from the current period has already passed.
        self._elapsed_seconds = 0
        # How much time from the current period is still left, in seconds.
        self._period_left = None

        self._task_id = None

        self._scheduler = sched.scheduler(self._clock.time, self._clock.sleep)
        self._thread = None
        self._evt_id = None
        self._on_period_end_callback = None

    # Public API of the class.
    def start(self, task_id: int, period_length: datetime.timedelta):
        self.transition_to(self.State.RUNNING, task_id=task_id, period_length=period_length)

    def stop(self):
        self.transition_to(self.State.STOPPED)

    def pause(self):
        self.transition_to(self.State.PAUSED)

    def resume(self):
        self.transition_to(self.State.RUNNING)

    def get_info(self) -> 'TimerInfo':
        elapsed_seconds = self._elapsed_seconds
        if self.get_state() == self.State.RUNNING:
            assert self._started_at is not None
            elapsed_seconds += self._clock.time() - self._started_at

        return TimerInfo(
            state=self.get_state(),
            elapsed_time=datetime.timedelta(seconds=elapsed_seconds),
        )

    def set_on_period_end_callback(self, callback: Callable[['TimerInfo'], None]):
        self._on_period_end_callback = callback

    # State transition handlers.
    @state_machine.handler(State.STOPPED, State.RUNNING)
    def _when_starting_a_new_period(self, task_id: int, period_length: datetime.timedelta):
        assert self._task_id is None
        assert self._period_left is None
        self._task_id = task_id
        self._period_left = period_length.seconds

    @state_machine.handler(State.STOPPED, State.RUNNING)
    @state_machine.handler(State.PAUSED, State.RUNNING)
    def _when_timer_starts_ticking(self, *unused_args, **unused_kwargs):
        self._started_at = self._clock.time()
        self._schedule_period_end()

    @state_machine.handler(State.RUNNING, State.STOPPED)
    @state_machine.handler(State.RUNNING, State.PAUSED)
    def _when_timer_stops_ticking(self):
        self._update_elapsed_seconds_and_period_left()
        self._cancel_period_end()

    def _update_elapsed_seconds_and_period_left(self):
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

        assert self._task_id is not None
        self._time_log.add_period(
                task_id=self._task_id,
                start=datetime.datetime.fromtimestamp(self._started_at),
                duration=datetime.timedelta(seconds=elapsed_seconds))
        self._started_at = None

    @state_machine.handler(State.RUNNING, State.STOPPED)
    @state_machine.handler(State.PAUSED, State.STOPPED)
    def _when_stopping_a_timer(self):
        self._task_id = None
        self._period_left = None

    # End-of-period callback handling.

    def _schedule_period_end(self):
        assert self._evt_id is None
        assert self._period_left is not None
        on_period_end = weakref.WeakMethod(self._on_period_end)()
        assert on_period_end is not None  # to make pyright happy.
        self._evt_id = self._scheduler.enter(
                delay=self._period_left, priority=1,
                action=on_period_end)
        self._thread = threading.Thread(target=self._scheduler.run)
        self._thread.start()

    def _on_period_end(self):
        self._evt_id = None
        self.transition_to(self.State.STOPPED)
        if self._on_period_end_callback:
            self._on_period_end_callback(self.get_info())

    def _cancel_period_end(self):
        if self._evt_id:
            self._scheduler.cancel(self._evt_id)
            self._evt_id = None


@dataclasses.dataclass
class TimerInfo:
    state: Timer.State
    elapsed_time: datetime.timedelta = datetime.timedelta(0)
