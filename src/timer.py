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
        self._evt_id = self._scheduler.enter(
                delay=delay, priority=1,
                action=weakref.WeakMethod(self._on_period_end)())
        self._thread = threading.Thread(target=self._scheduler.run)
        self._thread.start()
        # print('_sched_period_end:', f'{self._evt_id=}; {len(self._scheduler._queue)=}')

    def _cancel_period_end(self):
        assert self._evt_id is not None
        self._scheduler.cancel(self._evt_id)
        # print('_cancel_period_end:', f'{self._evt_id=}; {len(self._scheduler._queue)=}')
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
        self._elapsed_seconds += elapsed_seconds
        self._period_left -= elapsed_seconds
        assert self._period_left >= 0, f'Invalid {self._period_left=}'

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


import sys
import trace

class Trace:

    def __enter__(self):
        self.tracer = trace.Trace(count=1, trace=True)
        sys.settrace(self.tracer.globaltrace)
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        sys.settrace(None)
        self.tracer.results().write_results(show_missing=True, summary=True)


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


import unittest


class TestStatusChanges(unittest.TestCase):

    def setUp(self):
        self._clock = FakeClock()
        self.addCleanup(self._clock.stop)

    def test_not_started_timer_state(self):
        t = Timer(clock=self._clock)
        self.assertEqual(t.get_state().status, Status.STOPPED)

    def test_started_timer_state(self):
        t = Timer(clock=self._clock)
        t.start(task_id=42, period_length=td('5m'))
        self.assertEqual(t.get_state().status, Status.RUNNING)

    def test_stopped_timer_state(self):
        t = Timer(clock=self._clock)
        t.start(task_id=42, period_length=td('5m'))
        t.stop()
        self.assertEqual(t.get_state().status, Status.STOPPED)

    def test_paused_state(self):
        t = Timer(clock=self._clock)
        t.start(task_id=42, period_length=td('5m'))
        t.pause()
        self.assertEqual(t.get_state().status, Status.PAUSED)

    def test_state_after_resume(self):
        t = Timer(clock=self._clock)
        t.start(task_id=42, period_length=td('5m'))
        t.pause()
        t.resume()
        self.assertEqual(t.get_state().status, Status.RUNNING)

    def test_stop_after_pause(self):
        t = Timer(clock=self._clock)
        t.start(task_id=42, period_length=td('5m'))
        t.pause()
        t.stop()
        self.assertEqual(t.get_state().status, Status.STOPPED)


class TestTimePassage(unittest.TestCase):

    def setUp(self):
        self._clock = FakeClock()
        self.addCleanup(self._clock.stop)

    def test_elapsed_time(self):
        t = Timer(clock=self._clock)

        t.start(task_id=42, period_length=td('5m'))
        self._clock.advance('1m')
        state = t.get_state()

        self.assertEqual(state.elapsed_time, td('1m'))

    def test_elapsed_time_doesnt_increase_after_calling_stop(self):
        t = Timer(clock=self._clock)

        t.start(task_id=42, period_length=td('5m'))
        self._clock.advance('1m')
        t.stop()
        self._clock.advance('10m')

        self.assertEqual(t.get_state().elapsed_time, td('1m'))

    def test_elapsed_time_doesnt_increase_after_calling_pause(self):
        t = Timer(clock=self._clock)

        t.start(task_id=42, period_length=td('5m'))
        self._clock.advance('1m')
        t.pause()
        self._clock.advance('10m')

        self.assertEqual(t.get_state().elapsed_time, td('1m'))

    def test_elapsed_time_increases_after_resume(self):
        t = Timer(clock=self._clock)

        t.start(task_id=42, period_length=td('5m'))
        self._clock.advance('1m')
        t.pause()
        self._clock.advance('10m')
        t.resume()
        self._clock.advance('1m')

        self.assertEqual(t.get_state().elapsed_time, td('2m'))

    def test_stop_after_pause(self):
        t = Timer(clock=self._clock)

        t.start(task_id=42, period_length=td('5m'))
        self._clock.advance('1m')
        t.pause()
        self._clock.advance('10m')
        t.stop()
        self._clock.advance('1m')

        self.assertEqual(t.get_state().elapsed_time, td('1m'))


class TestScheduledEnding(unittest.TestCase):

    def setUp(self):
        self._clock = FakeClock()
        self.addCleanup(self._clock.stop)

    def test_it_stops_itself_after_period_end(self):
        t = Timer(clock=self._clock)

        t.start(task_id=42, period_length=td('5m'))
        self._clock.advance('5m')

        self.assertEqual(t.get_state().status, Status.STOPPED)

    def test_elapsed_time_is_right(self):
        t = Timer(clock=self._clock)

        t.start(task_id=42, period_length=td('5m'))
        self._clock.advance('10m')

        self.assertEqual(t.get_state().elapsed_time, td('5m'))

    def test_it_stops_after_resume_as_well(self):
        t = Timer(clock=self._clock)

        t.start(task_id=42, period_length=td('5m'))
        t.pause()
        t.resume()
        self._clock.advance('5m')

        self.assertEqual(t.get_state().status, Status.STOPPED)

    def test_elapsed_time_after_pause_resume_is_right(self):
        t = Timer(clock=self._clock)

        t.start(task_id=42, period_length=td('5m'))
        self._clock.advance('1m')
        t.pause()
        self._clock.advance('10m')
        t.resume()
        self._clock.advance('10m')

        self.assertEqual(t.get_state().elapsed_time, td('5m'))


class CallbackTest(unittest.TestCase):

    def setUp(self):
        self._clock = FakeClock()
        self.addCleanup(self._clock.stop)

    def test_callback_gets_called(self):
        t = Timer(clock=self._clock)
        callback_called = False
        def callback(s: TimerState):
            nonlocal callback_called
            callback_called = True
        t.set_on_period_end_callback(callback)

        t.start(task_id=42, period_length=td('5m'))
        self._clock.advance('5m')
        self._clock.advance('5m')

        self.assertTrue(callback_called)


class FakeClock(Clock):

    def __init__(self):
        self._time = 0.
        self._stopped = False

    def advance(self, delta: datetime.timedelta | str):
        delta = td(delta).seconds
        print(delta)
        for i in range(int(delta)):
            self._time += 1
            time.sleep(0)

    def time(self) -> float:
        return self._time

    def sleep(self, seconds: float):
        until = self._time + seconds
        while self._time < until and not self._stopped:
            pass

    def stop(self):
        # Move forward for a bit, to allow callbacks to fire.
        self._stopped = True
        for i in range(1000):
            self._time += 1
            time.sleep(0)
        time.sleep(.00001)
        self._time = 2**32


def td(s: str | datetime.timedelta) -> datetime.timedelta:
    if isinstance(s, datetime.timedelta):
        return s
    if s[-1] == 's':
        return datetime.timedelta(seconds=int(s[:-1]))
    if s[-1] == 'm':
        return datetime.timedelta(minutes=int(s[:-1]))
    if s[-1] == 'h':
        return datetime.timedelta(hours=int(s[:-1]))
    raise ValueError(s)


if __name__ == '__main__':
    unittest.main()
