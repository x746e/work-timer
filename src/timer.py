import datetime
import dataclasses
import enum
import time
from collections.abc import Callable
from typing import Protocol


class Timer:

    def __init__(self, clock: 'Clock' = time):
        self._clock = clock
        self._on_end_callback = None

        self._status = Status.STOPPED
        self._started_at = None
        self._elapsed_seconds = 0

    def start(self, task_id: int, period_length: datetime.timedelta):
        self._status = Status.RUNNING
        self._started_at = self._clock.time()

    def stop(self):
        assert self._status in (Status.RUNNING, Status.PAUSED)
        if self._status == Status.RUNNING:
            assert self._started_at is not None
            self._elapsed_seconds += self._clock.time() - self._started_at
        self._status = Status.STOPPED

    def pause(self):
        assert self._status == Status.RUNNING
        assert self._started_at is not None
        self._status = Status.PAUSED
        self._elapsed_seconds += self._clock.time() - self._started_at

    def resume(self):
        assert self._status == Status.PAUSED
        self._status = Status.RUNNING
        self._started_at = self._clock.time()

    def get_state(self) -> 'TimerState':
        elapsed_seconds = self._elapsed_seconds
        if self._status == Status.RUNNING:
            assert self._started_at is not None
            elapsed_seconds += self._clock.time() - self._started_at

        return TimerState(
            status=self._status,
            elapsed_time=datetime.timedelta(seconds=elapsed_seconds),
        )

    def set_on_end_callback(self, callback: Callable[['TimerState'], None]):
        self._on_end_callback = callback


class Clock(Protocol):
    def time(self) -> float:
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


def td(s: str | datetime.timedelta) -> datetime.timedelta:
    if isinstance(s, datetime.timedelta):
        return s
    if s[-1] == 'm':
        return datetime.timedelta(minutes=int(s[:-1]))
    raise ValueError(s)


class TestStatusChanges(unittest.TestCase):

    def test_not_started_timer_state(self):
        t = Timer()
        self.assertEqual(t.get_state().status, Status.STOPPED)

    def test_started_timer_state(self):
        t = Timer()
        t.start(task_id=42, period_length=td('5m'))
        self.assertEqual(t.get_state().status, Status.RUNNING)

    def test_stopped_timer_state(self):
        t = Timer()
        t.start(task_id=42, period_length=td('5m'))
        t.stop()
        self.assertEqual(t.get_state().status, Status.STOPPED)

    def test_paused_state(self):
        t = Timer()
        t.start(task_id=42, period_length=td('5m'))
        t.pause()
        self.assertEqual(t.get_state().status, Status.PAUSED)

    def test_state_after_resume(self):
        t = Timer()
        t.start(task_id=42, period_length=td('5m'))
        t.pause()
        t.resume()
        self.assertEqual(t.get_state().status, Status.RUNNING)

    def test_stop_after_pause(self):
        t = Timer()
        t.start(task_id=42, period_length=td('5m'))
        t.pause()
        t.stop()
        self.assertEqual(t.get_state().status, Status.STOPPED)


class TestTimePassage(unittest.TestCase):

    def test_elapsed_time(self):
        clock = FakeClock()
        t = Timer(clock=clock)

        t.start(task_id=42, period_length=td('5m'))
        clock.advance('1m')
        state = t.get_state()

        self.assertEqual(state.elapsed_time, td('1m'))

    def test_elapsed_time_doesnt_increase_after_calling_stop(self):
        clock = FakeClock()
        t = Timer(clock=clock)

        t.start(task_id=42, period_length=td('5m'))
        clock.advance('1m')
        t.stop()
        clock.advance('10m')

        self.assertEqual(t.get_state().elapsed_time, td('1m'))

    def test_elapsed_time_doesnt_increase_after_calling_pause(self):
        clock = FakeClock()
        t = Timer(clock=clock)

        t.start(task_id=42, period_length=td('5m'))
        clock.advance('1m')
        t.pause()
        clock.advance('10m')

        self.assertEqual(t.get_state().elapsed_time, td('1m'))

    def test_elapsed_time_increases_after_resume(self):
        clock = FakeClock()
        t = Timer(clock=clock)

        t.start(task_id=42, period_length=td('5m'))
        clock.advance('1m')
        t.pause()
        clock.advance('10m')
        t.resume()
        clock.advance('1m')

        self.assertEqual(t.get_state().elapsed_time, td('2m'))

    def test_stop_after_pause(self):
        clock = FakeClock()
        t = Timer(clock=clock)

        t.start(task_id=42, period_length=td('5m'))
        clock.advance('1m')
        t.pause()
        clock.advance('10m')
        t.stop()
        clock.advance('1m')

        self.assertEqual(t.get_state().elapsed_time, td('1m'))


class FakeClock(Clock):

    def __init__(self):
        self._time = 0

    def advance(self, delta: datetime.timedelta | str):
        self._time += td(delta).seconds

    def time(self) -> int:
        return self._time


if __name__ == '__main__':
    unittest.main()
